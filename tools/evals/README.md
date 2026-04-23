# tools/evals

Quality + evaluation harness for Aether.

See [docs/QUALITY-EVAL-V1-ARCHITECTURE.md](../../docs/QUALITY-EVAL-V1-ARCHITECTURE.md)
for the full design.

This is the **v1 scaffold**: a minimal Python runner, a small
expectation DSL, one seed scenario per domain, and a markdown
report. Nothing ambitious. The goal is to start *measuring*
quality on a repeatable, replayable surface — not to finish
the entire eval stack.

## Run

```bash
python tools/evals/__main__.py --help
python tools/evals/__main__.py --dry-run
python tools/evals/__main__.py --report-md out/eval_report.md
```

`--dry-run` does not invoke any backend — it replays expectations
against the scenarios' pre-recorded `actual` field when present.
Useful for locking the expectation DSL without needing a live
model. Without `--dry-run`, a real backend call would be made;
for v1 the runner only ships the mock / dry-run path — live
backend wiring is a later slice.

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

## Roadmap

Sequencing from the design doc §6:

1. ✅ This scaffold + one seed scenario per domain.
2. ⏳ Baseline report against current provider config.
3. ⏳ Adversarial scenarios (first per domain).
4. ⏳ Session-log replay importer.
5. ⏳ `tools/lint-quality-doc/` rot guard.
6. ⏳ Regression harness + `pnpm eval` wiring.
