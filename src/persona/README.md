# Module 13: Persona (Provisional — No Assigned Module Number)

Aether's proactive personality layer: availability sensing, daily check-ins,
and memory self-correction.

## Responsibility

Handles three concerns that shape Aether's behavior beyond responding to direct
requests. The busy detector infers when The user is available so other modules can gate
proactive messages correctly. The daily interview initiates a short evening check-in
at 7:00 PM, cycling through a question pool to learn the user's schedule, preferences,
and upcoming needs. The memory corrections handler detects when the user corrects
Aether mid-conversation and writes the correction to the memory store immediately.

## Key Files

- `busy_detector.py` — `BusyDetector` singleton: tracks `_last_activity` timestamp
  and a configurable sleep window (default 11 PM to 7:30 AM). Returns one of four
  availability states: `available`, `likely_busy`, `sleeping`, `do_not_disturb`.
  `should_notify(priority)` gates notification delivery by priority level (`urgent`
  always passes, `low` only passes when `available`). Sleep schedule is updated
  when the daily interview learns the user's actual hours. Subscribes to
  `EventType.USER_MESSAGE` to record activity timestamps.
- `daily_interview.py` — `start_interview_session()`: called by APScheduler at
  7:00 PM. Selects a question from a 15-item pool, tracks which questions have been
  asked in `./data\interview_asked.txt` (resets when pool exhausted), then
  publishes `EventType.PROACTIVE_MESSAGE`. Respects `notifications.max_proactive_per_day`
  from `aether_config.yaml`.
- `memory_corrections.py` — `detect_correction(text) -> (bool, str)`: regex-based
  detection of correction phrases ("no, I said...", "actually, it's...", "correction:
  ..."). `handle_memory_correction(event)`: searches memory for the relevant turn,
  then calls `store_fact()` with the corrected value at importance 0.7-0.8.

## Interface Contract

- Subscribes to:
  - `EventType.USER_MESSAGE` (busy detector — records activity)
  - `EventType.MEMORY_CORRECTION` (memory corrections handler)
- Publishes:
  - `EventType.PROACTIVE_MESSAGE` (daily interview check-in)
- Exported singletons / functions:
  - `get_busy_detector() -> BusyDetector`
  - `register_busy_detector_events()` — wire at startup
  - `register_memory_correction_handler()` — wire at startup
  - `start_interview_session()` — called by scheduler, not directly

## Dependencies

- `src.core.events` — EventBus
- `src.memory.store` — `search_memory()`, `store_fact()` (memory corrections)
- `src.shared.config` — `get_settings()`, `get_yaml_config()`
- `src.shared.types` — `EventType`, `AetherEvent`
- `loguru` — structured logging
- stdlib: `re`, `random`, `datetime`, `pathlib`
