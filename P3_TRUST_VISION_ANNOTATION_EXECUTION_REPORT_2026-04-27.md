# P3 — Vision-provider annotation in Trust drawer (2026-04-27)

## What shipped

### Frontend — `lib/mediaTurns.ts`

- `VISION_PROVIDER_IDS` — set of stable ids for every shipping
  vision provider (`"ollama-vision"`, `"llamacpp-vision"`). Mirrors
  the Rust `VisionProvider::id()` returns.
- `isVisionProvider(provider: string | null | undefined): boolean`.
- `visionProviderShortLabel(provider): string | null` — friendly
  display label (`"Ollama vision"` / `"llama.cpp vision"`) or
  `null` for non-vision provider strings.

### Frontend — `lib/mediaTurns.test.ts`

- 10 new tests covering the whole table:
  - `VISION_PROVIDER_IDS` membership and size,
  - `isVisionProvider` table for known/unknown providers,
  - null/undefined handling,
  - `visionProviderShortLabel` mapping + null returns.

### Frontend — `components/TrustDrawer.tsx`

- HistoryList row gains a small green pill next to the kind label
  whenever the entry's `provider` field names a known vision
  provider. The pill carries a `title="Served by ollama-vision"`
  attribute for full-id inspection on hover.
- Provider id remains visible in the row body for non-vision turns
  so the existing "what served this turn?" question stays answered.

## What's NOT in this slice (and why)

### Audit tab annotation — deferred

The L5 audit record (`audit_recent` Tauri command → `TrustAuditRow`
TypeScript type) carries `audit_id`, `decision`, `capability`,
`scope`, `change_id`, and timestamps. It does **not** carry the L4
provider id.

Adding provider info to an audit row would require one of:

1. extending the L5 `AuditRecordEvent` schema and the policy
   engine to attach the L4 provider id at decision time, or
2. cross-referencing audit rows against telemetry rows in the UI
   by some shared id (today there is no shared id —
   `TelemetryEntry.turn_id` is L1's, `TrustAuditRow.change_id` is
   L5's).

The session charter explicitly says:

> Do **not** break or muddy the distinction between policy decision
> / capability audit and provider implementation details.

Both available paths violate that. **Conclusion:** History is the
correct surface for vision-provider annotation; Audit stays a
provider-agnostic policy view, and that distinction is documented
in this report.

## Verification

- `pnpm test` — **41 / 41** (was 31; +10 vision-provider helpers).
- `pnpm typecheck && pnpm build` — clean.

## Notes for review

- **Source of truth is telemetry.** No new metadata path; we read
  the existing `provider` string the shell already records when
  `analyze_frame`'s `maybe_apply_vision` swaps in the vision
  response.
- **Pill is opt-in, not exclusion.** Non-vision turns render
  exactly as before — the pill is additive to media-turn rows.
- **Reuses the History tab's existing media filter.** Combined with
  the "Media only" pill from the earlier filter slice, reviewers
  can answer "show me only frame turns served by a vision model"
  in two clicks.
