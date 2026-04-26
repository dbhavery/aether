# tools/evals

Quality + evaluation harness for Aether.

See [docs/QUALITY-EVAL-V1-ARCHITECTURE.md](../../docs/QUALITY-EVAL-V1-ARCHITECTURE.md)
for the full design.

This is the **v1.2 harness**: Python runner, small expectation DSL,
one seed scenario per domain, one adversarial probe per domain, a
markdown baseline report, a live Ollama backend hook (v1.1), and
structured capture + replay (v1.2). Nothing ambitious. The goal is
to start *measuring* quality on a repeatable, replayable surface —
not to finish the entire eval stack.

## Run

```bash
python tools/evals/__main__.py --help
python tools/evals/__main__.py --dry-run
python tools/evals/__main__.py --report-md out/eval_report.md
# Live Ollama (v1.1):
python tools/evals/__main__.py --backend ollama --capture-into out/captured
# Replay a capture directory (v1.2, no backend required):
python tools/evals/__main__.py --replay-from out/captured
```

`--dry-run` does not invoke any backend — it replays expectations
against the scenarios' pre-recorded `actual` field when present.
Useful for locking the expectation DSL without needing a live
model.

`--backend ollama` POSTs the final user turn of each scenario to a
local Ollama instance and evaluates the response. Controlled by:

- `AETHER_EVAL_OLLAMA_BASE_URL` — default `http://127.0.0.1:11434`
- `AETHER_EVAL_OLLAMA_MODEL`    — default `gemma4`
- `AETHER_EVAL_OLLAMA_TIMEOUT_S` — default `30`

`--capture-into <dir>` writes two files per scenario:
- `<scenario_id>.md`   — human-readable prompt + response (v1.1).
- `<scenario_id>.json` — structured, machine-replayable payload
  with `scenario_id`, `domain`, `backend`, `captured_at` (UTC
  ISO-8601), `prompt`, `response`, and `metadata` (model id,
  base URL, timeout). Unknown top-level fields are ignored on
  replay so the schema stays additive.

`--replay-from <dir>` reads those JSON captures back and evaluates
the same expectations against the captured responses. No backend
is contacted; scenarios without a matching capture are skipped
with an explanatory note. Mutually exclusive with
`--backend ollama` and `--capture-into` — captures already exist
by the time you are replaying.

Live-backend mode is deliberately minimal: single-turn, no persona
prompt compilation, no memory context injection. Richer wiring lands
in later slices.

## Tests

Stdlib-only unit tests for the capture / replay machinery live
next to the runner:

```bash
python tools/evals/test_capture_replay.py
```

13 tests cover filename stability, JSON shape, round-trip
fidelity, and graceful handling of missing / malformed captures.

Exit codes:

- `0` — every scenario either passed or had no expectations that
  could be evaluated.
- `1` — one or more scenarios failed.
- `2` — usage / IO error.

## Scenario format

One JSON object per line in `tools/evals/scenarios/<domain>/*.jsonl`:

```json
{
  "id": "chat.greeting.first_time_user",
  "domain": "chat_realism",
  "difficulty": "easy",
  "setup": { "persona": "aurora", "memory": [] },
  "turns": [{ "role": "user", "content": "hi, first time" }],
  "actual": { "text": "Hi — what would you like to do?" },
  "expectations": [
    { "kind": "forbids", "patterns": ["as an AI"] },
    { "kind": "length", "max_words": 60 }
  ]
}
```

The `actual` field is optional — when present, the runner uses
it directly (useful for locking expectations). Without it, the
runner requires `--backend` to produce a real response.

## Expectation DSL

Open-ended: the runner silently skips expectation kinds it does
not know, so adding new kinds is non-breaking. Implemented in v1:

- `forbids` — response must NOT contain any of `patterns`
  (case-insensitive substring match).
- `requires` — response MUST contain every string in `patterns`.
- `length` — `{ max_words, min_words }` bounds.
- `tone` — accepts `matches: [<tag>, ...]`; v1 just notes the
  tags as informational; future slices can plug in a tone
  classifier.

## Adding a scenario

1. Pick the right domain folder under `tools/evals/scenarios/`.
2. Append a JSON object to an existing `*.jsonl` file or create
   a new one — file boundaries don't matter to the runner.
3. Run the suite with `--dry-run` first if `actual` is present;
   then with a live backend once implemented.
4. Check in the scenario file alongside the change that motivated
   it — scenarios are as much documentation as they are tests.

## Adversarial probes

`tools/evals/adversarial/<domain>/*.jsonl` holds known-bad responses
that exercise the detector. Run separately from the baseline:

```bash
python tools/evals/__main__.py --dry-run --scenarios-root tools/evals/adversarial
```

All adversarial probes MUST fail. If one stops firing, the detector
regressed. v1.1 ships one probe per domain (chat, tool-use, voice,
memory, presence, vision).

## Aurora-strict canaries (drift detector)

`tools/evals/canaries/aurora_strict/` holds literal-token mirrors
of the six production scenarios, frozen against Aurora's recorded
`actual.text` on 2026-04-25. They are a NON-GATING drift signal —
run them when validating model / prompt / composition changes,
ignore the exit code, and read the report.

```bash
python tools/evals/__main__.py \
  --scenarios-root tools/evals/canaries/aurora_strict --dry-run
```

See `tools/evals/canaries/aurora_strict/README.md` for the contract
and update protocol. Do NOT replace `requires` with `requires_any`
in canaries — that defeats the purpose.

## Roadmap

Sequencing from the design doc §6:

1. ✅ This scaffold + one seed scenario per domain.
2. ✅ Baseline report against current provider config
   (`tools/evals/baseline/`).
3. ✅ Adversarial scenarios (one per domain, v1.1).
4. ✅ Live Ollama backend hook (v1.1).
5. ✅ Structured capture + replay (v1.2).
6. ✅ Session-log replay importer — `session_log_import.py` (v1.3).
7. ✅ `tools/lint-quality-doc/` rot guard + doc flipped to
   "Current" (Tier 2B).
8. ⏳ Regression harness + `pnpm eval` wiring.
