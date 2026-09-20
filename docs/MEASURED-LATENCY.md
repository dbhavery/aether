# Measured latency

Every figure on this page came off `src.core.trace`, was produced by a run of
`tools/trace-bench/run_voice_trace.py`, and is reproducible from the raw trace
records committed at
`tools/trace-bench/measurements/2026-09-19-voice-path-rtx3090ti.jsonl`.

Nothing here is estimated, projected, or carried over from an earlier document.

## The withdrawn number

`docs/DISTRIBUTION.md` previously claimed **449 ms end to end** in four places,
plus "the latency budget lands under 500 ms". Those claims were removed on
2026-09-19 because they could not be regenerated: `time.perf_counter` appeared
zero times in the entire repository, so no code had ever measured a stage of
this pipeline. There was no instrument, so there was no measurement.

The first real measurement, below, is roughly 190 times the withdrawn figure.

## What was measured

Run date: 2026-09-19. Command:

    py -V:3.13 tools/trace-bench/run_voice_trace.py \
        --wav personas/aurora/voice/sample.wav --no-memory --mute --turns 2

Hardware and software:

| | |
|---|---|
| Machine | Dons_PC, Windows 11 (AMD64) |
| GPU | NVIDIA GeForce RTX 3090 Ti, torch 2.10.0+cu128 |
| Python | 3.13.12 |
| STT | faster-whisper, CUDA float16 |
| LLM | Ollama `qwen3.5:4b` through litellm, all three tiers |
| TTS | Chatterbox, persona voice cloning from `personas/aurora/voice/reference.wav` |
| Input | 4.00 s utterance, resampled 24 kHz to 16 kHz before the turn clock starts |

Path: the production `VoicePipeline`, `EventBus`, brain handler, `llm_client`
and `tts_handler`. The microphone is the only substitution: a WAV is loaded into
the capture buffer and the same `USER_SPEECH_END` handler that push-to-talk
fires is called.

Excluded from this run, and therefore not represented in these numbers:
ChromaDB history and RAG retrieval (`--no-memory`), and speaker playback
(`--mute`, which only suppresses output to the sound card, not synthesis).

## Result: turn 2, warm

All models resident, second turn in the same process. This is the figure to
quote for steady state.

| Stage | ms | Share |
|---|---:|---:|
| `stt` (faster-whisper, 4.00 s of audio) | 168.4 | 0.2% |
| `tier_routing` (LRU cache hit) | 0.1 | 0.0% |
| `context_build` | 16.7 | 0.0% |
| `llm_complete` (215 prompt / 2287 completion tokens) | 42,322.4 | 50.2% |
| `response_format` | 0.3 | 0.0% |
| `tts_synth` (18.08 s of audio produced) | 41,820.4 | 49.6% |
| `tts_publish_and_play` | 14.0 | 0.0% |
| `meter` | 3.1 | 0.0% |
| `memory_persist` | 0.0 | 0.0% |
| unaccounted | 6.7 | 0.0% |

**Response latency, input complete to first audio out: 84,337 ms.**
First LLM content token arrived at 41,634 ms.

## Result: turn 1, cold

Same process, first turn, so this includes loading faster-whisper, Chatterbox
and the Ollama model.

| Stage | ms |
|---|---:|
| `stt` | 3,316.0 |
| `tier_routing` (real classification call, cold model) | 6,726.0 |
| `llm_complete` | 19,842.4 |
| `tts_synth` | 48,992.9 |
| `memory_persist` | 1,729.4 |
| unaccounted | 4.7 |

**Response latency, cold: 78,910 ms.**

## Why the number is what it is

Two structural facts, both visible in the breakdown rather than inferred.

**TTS is not streamed.** `_publish_audio_chunks` runs only after `synthesize`
returns, so the first PCM chunk cannot leave until the entire reply has been
synthesised. `tts_publish_and_play` is 14 ms while `tts_synth` is 41.8 s: the
publishing is instant and the waiting is all synthesis. Perceived latency
therefore scales with the length of the whole answer, not with time to the
first word. Chunked synthesis per sentence is the change that would fix this.

**The model emits reasoning before content.** `qwen3.5:4b` is a thinking model.
First content token landed at 41,634 ms of a 42,322 ms LLM stage, so streaming
buys almost nothing here: 98% of the LLM stage elapsed before the user could
have seen a single word. A non-thinking model, or a thinking model with
reasoning disabled, is a separate and much larger win than any code change.

Note also that 2,287 completion tokens is a long answer for a spoken reply. The
system prompt does not constrain response length for voice mode, and in voice
mode length is paid for twice, once generating and once synthesising.

## Stages that are not instrumented

Reported as absent with a reason, never as zero, because a zero reads as
instant.

- **`wake_word`** does not exist in v1.0. Per `docs/PRODUCT-PLAN.md` section 1
  decision 10, push-to-talk replaced wake word and the modules were removed
  during the port. There is no code on this path to time.
- **`vad`** exists as `src/voice/vad.py` but nothing imports it. The
  push-to-talk pipeline hands the captured buffer straight to STT.

## Reproducing this

    # the run
    py -V:3.13 tools/trace-bench/run_voice_trace.py \
        --wav personas/aurora/voice/sample.wav --no-memory --mute --turns 2

    # the breakdown of any recorded turn, later, off the log
    py -V:3.13 tools/trace-bench/report.py --last 2

Traces are written to `<data_dir>/traces.jsonl` only when the user opted in to
`aether.telemetry.usage_counters`. `/health` serves the rolling per-stage p50
and p95 in its `latency` block under the same condition.

The bench needs `litellm`, which is declared in `requirements.txt`. If it is
absent from the interpreter, install it into a virtual environment rather than
globally: litellm pins `openai<3.0.0`, so a global install downgrades the
OpenAI SDK for every other project on the machine.
