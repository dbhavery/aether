# Lessons Learned — 2026-05-02 Bare-Metal Pivot Autonomous Run

> Crisp engineering takeaways from the 5.7-hour autonomous run that
> shipped Phase 0 + Phase 2 + Phase 3-prep of the bare-metal local
> inference pivot. Each lesson includes the diagnostic signal that
> revealed it and the design response now baked into the codebase.

## 1. Hardware-of-prior bugs are not prompt-fixable

**Signal:** 8/9 framing-fail rate at 2:3 aspect ratio across:
- Default framings ("full-body shot, head to feet visible")
- Distance-language ("shot from 5 meters away")
- Lens-language ("wide angle 24mm photograph")
- Cinematic ("wide establishing shot")
- Composition ("subject occupies central 50% of vertical frame")

**Response:** Document the FLUX framing bias as a structural property
of the model's training data, not a prompt-engineering opportunity.
Locked in `reference_flux_framing_bias.md` memory. Ship a
non-prompt escape (aspect ratio + body_extension) instead.

**Generalization:** When a model fails categorically across diverse
prompts, the failure is likely structural to the model's prior —
spending time on prompt variation wastes GPU. Pivot to non-prompt
levers (resolution, conditioning, post-processing) earlier.

## 2. Aspect ratio is a load-bearing parameter for FLUX framing

**Signal:** 1024×2048 (1:2) produces ~80% body coverage where
1024×1536 (2:3) produces ~50%. 768×2304 (1:3) gets ~90% (mid-thighs).

**Response:** Extend `backend_local_flux.aspect_to_dims` with `1:2`,
`1:3`, `3:8` keys. Make recipe-locked driver `phase0_full_batch.py`
default to `--aspect-ratio 1:2`.

**Generalization:** When prompt fails, change the canvas. FLUX has
to fill more vertical pixels somehow; doubling vertical area forces
it to compose more body content into the frame.

## 3. Pose convergence is seed-locked, not prompt-locked

**Signal:** All 9 generations at 2:3 produced near-identical
crossed-arms poses despite radically different prompt language. At
1:2/1:3, different seeds produced different poses (hands-in-pockets,
wall-lean, side-profile).

**Response:** Vary seed for pose diversity, not prompt language.
Prompt controls semantic content; seed controls compositional template.

**Generalization:** In diffusion model output, high-level composition
is often locked by the seed at low-step counts. To diversify
composition, vary the seed; to diversify content, vary the prompt.

## 4. Multimodal-VLM categorical reasoning fails at smaller scales

**Signal:** Qwen2-VL-2B-Instruct, even with the strictest possible
system prompt ("if feet not visible, framing_match=no"), returns:
> *"The candidate's feet are not visible, which is consistent with
> the prompt's request for full-body framing."*

The model has the visual capability (it sees feet aren't visible)
but lacks the categorical-reasoning step.

**Response:** Don't use 2B for Doctrine §8 gates. Default
`selftest._DEFAULT_BACKEND` stays `openai` until 7B is validated.
Document the failure with the literal reasoning quote so future
sessions don't repeat the experiment.

**Generalization:** "Visual capability" and "categorical-reasoning
capability" are separable in VLMs. Don't assume a model that can
describe an image accurately can ALSO apply that description to a
yes/no judgement. Test both axes.

## 5. Vision-token budgets blow KV cache silently

**Signal:** Qwen2-VL evaluation got stuck at 100% GPU utilization
forever — no progress, no error. `nvidia-smi` showed 24/24 GB used.

**Cause:** 1024×1536 input at Qwen2-VL's 28×28 patch tokenizer =
~2300 vision tokens per image. Two images = ~4600 tokens. KV cache
+ generation buffer at 2B model + this context overflows VRAM.

**Response:** Always pre-resize images for VLM inputs. `selftest_qwen2vl
._open_and_resize` caps long-edge at 768 → ~756 vision tokens/image.

**Generalization:** VLM context budgets are dominated by vision
tokens, not text. A 1024-pixel input image can produce 4000+ tokens.
Always cap input resolution for VLMs.

## 6. Diffusers training requires HEAD source install

**Signal:**
```
ImportError: This example requires a source install from
HuggingFace diffusers, but the version found is 0.37.1.
```

**Response:** `pip install -e /c/Users/dbhav/Projects/diffusers/`
after cloning the repo. Documented as runbook prereq.

**Generalization:** Diffusers' training scripts under `examples/`
sometimes use APIs newer than the pip release. For training work,
always source-install. Inference paths typically work with pip
release.

## 7. Diffusers DreamBooth-LoRA crashes on non-image files in instance_data_dir

**Signal:**
```
PIL.UnidentifiedImageError: cannot identify image file '00.txt'
```

**Cause:** `train_dreambooth_lora_flux.py` walks `--instance_data_dir`
and tries to PIL.open every file. Caption .txt files crash the loader.

**Response:** `dataset_builder.py` splits to `<dataset>/images/<n>.png`
+ `<dataset>/captions/<n>.txt` sibling subdirs. `accelerate_command()`
points `--instance_data_dir` at `.../images` only. Captions remain
available for kohya-style training that expects flat layout.

**Generalization:** When integrating with third-party training
scripts, assume their dataset loaders are dumb and put only the
expected file types in the directory they walk.

## 8. tee + tqdm hides progress in log files

**Signal:** Log file frozen at "Steps: 0/50 [00:00<?, ?it/s]" for
90+ minutes despite GPU at 100% utilization the whole time.

**Cause:** tqdm uses `\r` (carriage return, no newline) for in-place
progress updates. tee buffers on `\n`. The log file only shows
output that hits a newline, so frozen-looking tqdm output means
"training is progressing but tee can't see it."

**Response:** Don't trust the log file for tqdm progress. Watch
`nvidia-smi` utilization + checkpoint directory + process state
instead.

**Generalization:** Subprocess output redirection (tee, log files,
CI captures) drops tqdm's in-place updates. For long-running jobs
with tqdm, plan an out-of-band progress signal (file checkpoints,
status endpoint, etc.).

## 9. Sequential CPU offload trades latency for reliability

**Signal:** With 9 GB free GPU, `enable_model_cpu_offload()` OOMs on
FLUX-dev's 12 GB transformer. `enable_sequential_cpu_offload()` runs
in <8 GB peak GPU at the cost of 2-3x slower inference.

**Response:** `backend_local_flux._pick_offload_strategy()` probes
`torch.cuda.mem_get_info()` and auto-picks: ≥14 GB → `model`,
otherwise `sequential`. Honors `PERSONA_REFGEN_OFFLOAD={model,sequential,none}`
override. Falls back to `sequential` on cuda OOM during pipeline
setup.

**Generalization:** Don't hardcode a single offload strategy when the
hardware is shared. Adaptive picking + OOM fallback is cheap and
makes the tool resilient on a busy workstation.

## 10. LoRA-FLUX training at 1024 res + grad checkpointing is bottlenecked on 3090 Ti

**Signal:** 50-step smoke at 1024 res + grad checkpointing + bf16 +
batch=1 + grad_accum=4 ran 90+ min without first checkpoint. CPU 1100s
wall-time, GPU 100%. Extrapolates to ~50s/step → 1500 steps = 21h.

**Response:** Document the bottleneck. Add `--resolution` CLI flag
to launch.py. Recommend Don pick lower res / smaller base model /
cloud rental before launching the full training.

**Generalization:** FLUX-dev (12B params) is too big for unattended
overnight LoRA training on a 24 GB consumer GPU at full resolution.
Either commit to multi-night training or use a smaller variant
(FLUX.1-Schnell) or rent. Don't surprise yourself by assuming 6-8
hour training fits in an autonomous window without first measuring.

## 11. The "9:16" string was misleadingly mapped to 2:3 dims

**Signal:** `aspect_to_dims["9:16"]` returned (1024, 1536) which
is actually 2:3 (0.667), not 9:16 (0.5625). The name lied.

**Response:** Kept `"9:16"` mapping for backward compat (existing
batch manifests carry it) but added `"9:16-strict"` for the actual
9:16 dims (864, 1536) and explicit `"1:2"` / `"2:3"` keys for
clarity. Comment in code documents the legacy name.

**Generalization:** Aspect-ratio strings are dimensionless. Always
verify the actual pixel dimensions, not the label. When you find a
misleading label, leave it for backward compat but add the corrected
form alongside.

## 12. Always provide `--smoke-test` flags for long-running jobs

**Signal:** I almost launched a 6-8 hour LoRA training without
verifying the pipeline launched cleanly. The smoke flag (50 steps,
~25 min) caught two real bugs (diffusers HEAD install, dataset
layout) before they cost a full overnight run.

**Response:** Built `--smoke-test` flag that overrides
`max_train_steps=50, checkpointing_steps=50, lr_warmup_steps=0`.
Mandatory step before any production training run. Documented in
runbook.

**Generalization:** Any tool that takes hours to run should have a
sub-30-minute smoke mode. The cost of writing the smoke flag is
near-zero; the cost of NOT having it is one wasted overnight per
broken config.

## 13. Auto-curation prefills selftest verdicts so dataset_builder works without humans

**Signal:** During the autonomous run, Don was AAFK — couldn't
manually curate. dataset_builder's default `require_keep_verdict=True`
filter would have produced empty datasets without keep rows.

**Response:** `auto_curate.py` translates selftest pass→keep,
flag→reject, latest-wins so Don's manual rows take precedence when
he gets back. `dataset_builder` exposes `--relax-selftest-verdict`
for cases where best-available data has Doctrine §8 framing flags
(e.g. 1:2 candidates where feet aren't visible but everything else
is good).

**Generalization:** When automating a previously-manual gate, make
the auto-version conservative + human-overrideable + tagged
distinguishable from manual rows so the next session can audit.

## 14. body_extension via FLUX-Inpaint reuses the regular FLUX checkpoint

**Signal:** Considered downloading `FLUX.1-Fill-dev` (~24 GB)
specifically for outpainting. Tried `FluxInpaintPipeline.from_pretrained
("black-forest-labs/FLUX.1-dev")` first.

**Response:** Works. No separate Fill checkpoint needed. Saved a
~24 GB download.

**Generalization:** Diffusers' inpainting pipelines often work on
generic checkpoints, not just dedicated inpaint checkpoints. Test
the cheaper path first.

## 15. Manifests are the contract; images are gitignored

**Signal:** `personas/<slug>/_pipeline/` is gitignored. Generated
images, EVALUATION.md, selftest.jsonl, curation.jsonl all stay local.
But the runner.py code that produces them and the dataset_builder
that consumes them MUST be committed and tested.

**Response:** Treat the manifest schema (`output_schema.py`) as the
canonical contract. Tests use synthetic in-memory PNG bytes + manifest
fixtures. Real image artifacts are ephemeral.

**Generalization:** When working with large generated artifacts, the
schema + the code that produces/consumes the schema is the IP. The
artifacts themselves are derivative. Version-control the schema,
gitignore the artifacts.
