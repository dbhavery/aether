// Thin typed wrapper around Tauri's invoke() + event bus. The rest of the
// UI imports only from here so swapping the backend transport is a one-
// file change.

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import type {
  AttentionEventPayload,
  CompanionBanner,
  FrameAnalysisOutcome,
  MediaKind,
  MediaPermissions,
  MediaPermissionState,
  MemoryConfig,
  MemoryDomain,
  MemoryEditOutcome,
  MemoryForgetOutcome,
  MemoryListPayload,
  MicPermission,
  PersonaCatalogEntry,
  PresenceConfig,
  PresenceHistoryEntry,
  PresencePayload,
  PresenceStatusPayload,
  ResolveApprovalReply,
  UserChoice,
  SpeechModelList,
  TranscribeUtteranceRequest,
  TranscriptMessage,
  TrustAuditRow,
  TurnOutcome,
  UtteranceOutcome,
  VisionModelList,
  VisionStatus,
  VoiceStatus,
  ReadinessState,
  Tier,
  TierConfig,
} from "./types";

export async function companionBanner(): Promise<CompanionBanner> {
  return invoke<CompanionBanner>("companion_banner");
}

export async function submitTurn(text: string): Promise<TurnOutcome> {
  return invoke<TurnOutcome>("submit_turn", { text });
}

/**
 * Wave 14 (T1.3 §5.3) — `resolve_approval` now takes the four-option
 * `UserChoice` tagged enum (`allow` / `allow_session` / `allow_task` /
 * `defer_to_draft` / `deny`) instead of a binary `approve: boolean`.
 * The L5 engine receives the actual scope the user picked so the
 * audit row + grant carry the right `ApprovalScope`.
 *
 * Wave 11 introduced the tagged `ResolveApprovalReply` so the same
 * wire surface serves both the chat-surface (`kind: "turn"`) and the
 * executor flavour (`kind: "executor"`). The chat surface should call
 * [`resolveApprovalForTurn`] which preserves the pre-Wave-11
 * `Promise<TurnOutcome>` ergonomics; new executor surfaces should
 * call the raw `resolveApproval` and dispatch on `kind`.
 */
export async function resolveApproval(
  ticketId: string,
  userChoice: UserChoice,
): Promise<ResolveApprovalReply> {
  return invoke<ResolveApprovalReply>("resolve_approval", {
    ticketId,
    userChoice,
  });
}

/**
 * Chat-surface convenience: resolve a pending Turn-flavoured approval
 * and unwrap to a `TurnOutcome` for `appendOutcome` consumers. Throws
 * if the backend reports the pending registry held an
 * `Executor`-flavoured row instead — that should never happen on the
 * chat surface (`submit_turn` only registers Turn rows).
 *
 * Wave 14: now takes a `UserChoice` instead of `approve: boolean`.
 * Callers that still want the binary shape can pass
 * `{ kind: "allow" }` for approve and `{ kind: "deny" }` for reject —
 * matches today's "Allow once" / "Decline" behaviour.
 */
export async function resolveApprovalForTurn(
  ticketId: string,
  userChoice: UserChoice,
): Promise<TurnOutcome> {
  const reply = await resolveApproval(ticketId, userChoice);
  if (reply.kind === "turn") {
    return reply.outcome;
  }
  throw new Error(
    `resolve_approval returned executor-flavoured reply for chat ticket ${ticketId}; ` +
      `method=${reply.method}`,
  );
}

export async function presenceCurrent(): Promise<PresencePayload> {
  return invoke<PresencePayload>("presence_current");
}

export async function memoryRecent(): Promise<TranscriptMessage[]> {
  return invoke<TranscriptMessage[]>("memory_recent");
}

export async function clearSession(): Promise<void> {
  return invoke<void>("clear_session");
}

export async function auditRecent(
  limit: number = 50,
): Promise<TrustAuditRow[]> {
  return invoke<TrustAuditRow[]>("audit_recent", { limit });
}

export function onPresence(
  handler: (p: PresencePayload) => void,
): Promise<UnlistenFn> {
  return listen<PresencePayload>("presence:update", (e) => handler(e.payload));
}

export async function listPersonas(): Promise<PersonaCatalogEntry[]> {
  return invoke<PersonaCatalogEntry[]>("list_personas");
}

export async function switchPersona(id: string): Promise<CompanionBanner> {
  return invoke<CompanionBanner>("switch_persona", { id });
}

/**
 * ADR-0012 Tier-2 install — fetches a signed persona manifest, verifies
 * the signature against the bundled release public key, downloads the
 * pack zip, SHA-checks, atomically extracts, and refreshes the live
 * persona catalog. Returns the number of newly-added catalog entries
 * (0 if the slug was already installed).
 *
 * The `manifestUrl` is the absolute URL of the slug's `manifest.json`.
 * Resolution lives at the call site so the backend stays
 * registry-agnostic — see `personaManifestUrl` for the current
 * convention.
 */
export async function installPersona(
  slug: string,
  manifestUrl: string,
): Promise<number> {
  return invoke<number>("install_persona", { slug, manifestUrl });
}

/**
 * Resolve the manifest URL for a persona slug. Today the persona
 * registry / CDN base URL is not yet configured (see HANDOFF
 * 2026-04-29 — RELEASE_PUBLIC_KEY_B64 + manifest base are still
 * pending). Reads from the build-time env var
 * `VITE_PERSONA_MANIFEST_BASE`; returns `null` when unset so the
 * caller can surface an honest "install registry not configured"
 * error instead of issuing a doomed network request.
 *
 * Convention: `${base}/${slug}/manifest.json`, matching the format
 * `install_persona_via_http` already exercises in its end-to-end
 * test (`apps/desktop/src-tauri/src/main.rs` line 1058).
 */
export function personaManifestUrl(slug: string): string | null {
  const base = import.meta.env?.VITE_PERSONA_MANIFEST_BASE as
    | string
    | undefined;
  if (!base) return null;
  const trimmed = base.replace(/\/+$/, "");
  return `${trimmed}/${slug}/manifest.json`;
}

export async function setAutonomyPreset(
  preset: string | null,
): Promise<CompanionBanner> {
  return invoke<CompanionBanner>("set_autonomy_preset", { preset });
}

export async function currentAutonomyPreset(): Promise<string | null> {
  return invoke<string | null>("current_autonomy_preset");
}

export interface TelemetryEntry {
  turn_id: string;
  timestamp_ms: number;
  kind: string;
  persona_id: string;
  provider?: string;
  tier?: string;
  /** Vision-route model id, when the turn was served by a vision
   * provider that exposes one. Absent for text-only turns. */
  model?: string;
  latency_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  /** Memory V2 domain label (wire form: `"session"`, `"durable"`,
   * `"facts"`, `"projects"`, `"preferences"`, `"artifacts"`).
   * Populated only on memory-scoped telemetry kinds; see
   * `memoryTurns.ts` for the full list. */
  memory_domain?: string;
  /** Memory V2 per-item id. Stable per write; absent on
   * domain-scoped events (forget-all, sampled retrieval). */
  memory_id?: string;
}

export async function telemetryRecent(
  limit: number | null = null,
): Promise<TelemetryEntry[]> {
  return invoke<TelemetryEntry[]>("telemetry_recent", { limit });
}

export async function telemetryClear(): Promise<void> {
  return invoke<void>("telemetry_clear");
}

export interface ForgetOlderReport {
  removed: number;
  applied: boolean;
}

export async function forgetOlderThanDays(
  days: number,
): Promise<ForgetOlderReport> {
  return invoke<ForgetOlderReport>("forget_older_than_days", { days });
}

// --- Media permissions (P1) -----------------------------------------------

export async function getMediaPermissions(): Promise<MediaPermissions> {
  return invoke<MediaPermissions>("get_media_permissions");
}

/**
 * Update one device's permission. The Rust command parameter is named
 * `state_value` because `state` collides with the Tauri `State<T>`
 * extractor — the IPC layer maps camelCase TS keys onto snake_case
 * Rust params, hence `stateValue`.
 */
export async function setMediaPermission(
  kind: MediaKind,
  stateValue: MediaPermissionState,
): Promise<MediaPermissions> {
  return invoke<MediaPermissions>("set_media_permission", {
    kind,
    stateValue,
  });
}

// --- Mic permission (Voice V1 step 1) -------------------------------------

export async function getMicPermission(): Promise<MicPermission> {
  return invoke<MicPermission>("get_mic_permission");
}

/**
 * Update the mic permission. Same IPC quirk as `setMediaPermission` —
 * the Rust command uses `state_value` because `state` collides with
 * the Tauri `State<T>` extractor.
 */
export async function setMicPermission(
  stateValue: MediaPermissionState,
): Promise<MicPermission> {
  return invoke<MicPermission>("set_mic_permission", {
    stateValue,
  });
}

// --- Single-frame analysis (P3) -------------------------------------------

export interface AnalyzeFrameRequest {
  kind: MediaKind;
  frame_data_url: string;
  note?: string | null;
}

export async function analyzeFrame(
  req: AnalyzeFrameRequest,
): Promise<FrameAnalysisOutcome> {
  return invoke<FrameAnalysisOutcome>("analyze_frame", { request: req });
}

export async function visionStatus(): Promise<VisionStatus> {
  return invoke<VisionStatus>("vision_status");
}

export async function setActiveVisionProvider(
  id: string | null,
): Promise<VisionStatus> {
  return invoke<VisionStatus>("set_active_vision_provider", { id });
}

export async function listVisionModels(): Promise<VisionModelList> {
  return invoke<VisionModelList>("list_vision_models");
}

export async function refreshVisionModels(): Promise<VisionModelList> {
  return invoke<VisionModelList>("refresh_vision_models");
}

export async function setActiveVisionModel(
  id: string,
): Promise<VisionStatus> {
  return invoke<VisionStatus>("set_active_vision_model", { id });
}

// --- Voice V1 step 5 ------------------------------------------------------

export async function transcribeUtterance(
  req: TranscribeUtteranceRequest,
): Promise<UtteranceOutcome> {
  return invoke<UtteranceOutcome>("transcribe_utterance", { request: req });
}

export async function voiceStatus(): Promise<VoiceStatus> {
  return invoke<VoiceStatus>("voice_status");
}

export async function listSpeechModels(): Promise<SpeechModelList> {
  return invoke<SpeechModelList>("list_speech_models");
}

export async function refreshSpeechModels(): Promise<SpeechModelList> {
  return invoke<SpeechModelList>("refresh_speech_models");
}

export async function setActiveSpeechProvider(
  id: string | null,
): Promise<VoiceStatus> {
  return invoke<VoiceStatus>("set_active_speech_provider", { id });
}

export async function setActiveSpeechModel(
  id: string,
): Promise<VoiceStatus> {
  return invoke<VoiceStatus>("set_active_speech_model", { id });
}

// --- Presence V1 step 1 ---------------------------------------------------

export async function getPresenceConfig(): Promise<PresenceConfig> {
  return invoke<PresenceConfig>("get_presence_config");
}

export async function setPresenceConfig(
  config: PresenceConfig,
): Promise<PresenceConfig> {
  return invoke<PresenceConfig>("set_presence_config", { config });
}

// --- Presence V1 step 2 ---------------------------------------------------

/** Current user-attention snapshot. Complementary to `presenceCurrent`
 * which returns the assistant-posture axis — the two commands are
 * orthogonal per `docs/PRESENCE-V1-ARCHITECTURE.md` §2. */
export async function presenceStatus(): Promise<PresenceStatusPayload> {
  return invoke<PresenceStatusPayload>("presence_status");
}

/** Recent user-attention transitions, newest-first. Used by the Trust
 * drawer's History tab (step 3). */
export async function presenceRecentHistory(
  limit: number | null = null,
): Promise<PresenceHistoryEntry[]> {
  return invoke<PresenceHistoryEntry[]>("presence_recent_history", { limit });
}

/** Subscribe to live attention transitions. Emitted only on state
 * change, never on every poll tick. */
export function onAttention(
  handler: (p: AttentionEventPayload) => void,
): Promise<UnlistenFn> {
  return listen<AttentionEventPayload>("presence:attention", (e) =>
    handler(e.payload),
  );
}

// --- Memory V2 step 2 ----------------------------------------------------

export async function getMemoryConfig(): Promise<MemoryConfig> {
  return invoke<MemoryConfig>("get_memory_config");
}

export async function setMemoryConfig(
  config: MemoryConfig,
): Promise<MemoryConfig> {
  return invoke<MemoryConfig>("set_memory_config", { config });
}

// --- Memory V2 step 4 — Trust drawer Memory tab commands ----------------

/** List items for one memory domain. `sessionId` is optional — the
 * backend falls back to the default session when absent, so the
 * typical Trust-drawer call is `memoryList("session")`. */
export async function memoryList(
  domain: MemoryDomain,
  sessionId?: string,
): Promise<MemoryListPayload> {
  return invoke<MemoryListPayload>("memory_list", {
    domain,
    sessionId: sessionId ?? null,
  });
}

/** Forget every row in a domain's session ("forget-all-in-domain"
 * action). */
export async function memoryForget(
  domain: MemoryDomain,
  sessionId?: string,
): Promise<MemoryForgetOutcome> {
  return invoke<MemoryForgetOutcome>("memory_forget", {
    domain,
    sessionId: sessionId ?? null,
  });
}

/** Forget a single memory item addressed by its stable
 * `mem-{session}-{sequence}` id. Returns `{kind: "requires_approval"}`
 * for user-sensitive domains (Facts / Artifacts) — the caller must
 * surface the approval modal and then call
 * `memoryForgetItemAfterApproval` with the same arguments. */
export async function memoryForgetItem(
  domain: MemoryDomain,
  memoryId: string,
): Promise<MemoryForgetOutcome> {
  return invoke<MemoryForgetOutcome>("memory_forget_item", {
    domain,
    memoryId,
  });
}

export async function memoryForgetItemAfterApproval(
  domain: MemoryDomain,
  memoryId: string,
): Promise<MemoryForgetOutcome> {
  return invoke<MemoryForgetOutcome>("memory_forget_item_after_approval", {
    domain,
    memoryId,
  });
}

/** Edit one memory item's content. Role, timestamp, and sequence are
 * preserved — this is a fact-level edit, not a new turn. */
export async function memoryEdit(
  domain: MemoryDomain,
  memoryId: string,
  newContent: string,
): Promise<MemoryEditOutcome> {
  return invoke<MemoryEditOutcome>("memory_edit", {
    domain,
    memoryId,
    newContent,
  });
}

export async function memoryEditAfterApproval(
  domain: MemoryDomain,
  memoryId: string,
  newContent: string,
): Promise<MemoryEditOutcome> {
  return invoke<MemoryEditOutcome>("memory_edit_after_approval", {
    domain,
    memoryId,
    newContent,
  });
}

// --- ADR-0006 hardware tier model -------------------------------------

/** Snapshot of the current TierConfig (selected, detected, hardware
 * snapshot). Cheap to call on every render — backend just clones from
 * the in-memory copy. */
export async function getTier(): Promise<TierConfig> {
  return invoke<TierConfig>("get_tier");
}

/** User-initiated tier change. Backend persists atomically and flips
 * `manual_override` if the new selection diverges from the detected
 * recommendation. Throws if persistence fails. */
export async function setTier(tier: Tier): Promise<TierConfig> {
  return invoke<TierConfig>("set_tier", { tier });
}

/** Re-run hardware detection. Pure read on the backend — wgpu adapter
 * enumeration, sysinfo, fs::available_space, and an optional 750ms
 * /api/ps probe (skipped when embeddings are off). Honours the existing
 * manual override: if the user previously chose a non-detected tier,
 * detection updates `detected_tier` only — their selection stays. */
export async function redetectHardware(): Promise<TierConfig> {
  return invoke<TierConfig>("redetect_hardware");
}

// --- ADR-0007 retrieval readiness -------------------------------------

/** Snapshot the current retrieval readiness per ADR-0007 D3. Read-only;
 * updates are pushed by `run_retrieval_context` (every real turn) plus
 * boot / settings-change probes on the backend. UI may poll on a
 * reasonable interval (≥1s) — backend cost is sub-microsecond. */
export async function embeddingsReadiness(): Promise<ReadinessState> {
  return invoke<ReadinessState>("embeddings_readiness");
}

// --- ADR-0007 D5 backfill ---------------------------------------------

/** Snapshot of current backfill progress. Mirrors Rust
 * `state::BackfillProgress`. UI polls during a job and reads
 * `finished` to flip the button back from Cancel to Backfill. */
export interface BackfillProgress {
  finished: boolean;
  cancelled: boolean;
  total: number;
  completed: number;
  /** Rows that exhausted every retry attempt and were skipped. A row
   * that succeeded on a retry is NOT counted here — it lands in
   * `completed` plus `recovered_failures`. Phase 3B F1 tightened this
   * definition. */
  failures: number;
  /** Rows that hit at least one transient embed failure (HTTP 5xx /
   * timeout / connection-refused) but succeeded on a subsequent retry.
   * Increments once per recovered row regardless of how many retries
   * were consumed; the row itself is also counted in `completed`.
   * Surfaced separately so the UI can show transient-error recovery
   * without conflating it with un-retried success. Mirrors the Rust
   * `BackfillProgress::recovered_failures` field landed in commit
   * 9768c17 (Phase 3B F1). */
  recovered_failures: number;
  /** Rows skipped because an embedding already exists for the
   * (domain, memory_id) pair. Surfaced separately from `completed`
   * so the UI can render "skipped X already-embedded rows" rather
   * than double-counting them as completed work. Populated by the
   * second-pass backfill fast path (EmbeddingStore::embedded_ids). */
  skipped_already_embedded: number;
  current_domain: string | null;
  started_at_ms: number;
}

/** Snapshot of current backfill progress. Cheap call (lock-free read);
 * UI may poll every 250ms while a job runs. */
export async function backfillStatus(): Promise<BackfillProgress> {
  return invoke<BackfillProgress>("backfill_status");
}

/** Approximate count of un-embedded rows across embed-eligible
 * domains (Durable / Projects / Artifacts). Drives the "Backfill ~N
 * items" copy. ADR-0007 D5 approximate semantics: total memory rows
 * minus current `EmbeddingStore::count`. */
export async function backfillCount(): Promise<number> {
  return invoke<number>("backfill_count");
}

/** Run a backfill synchronously. Returns the final progress on success;
 * throws when a job is already in progress. The current implementation
 * blocks the IPC thread for the full duration — call from a UI handler
 * that shows a spinner / progress strip while the promise pends. */
export async function startBackfill(): Promise<BackfillProgress> {
  return invoke<BackfillProgress>("start_backfill");
}

/** Request cancellation of any in-progress backfill. The worker
 * observes the flag at the next row boundary; the in-flight embed call
 * finishes gracefully. Returns `true` when a job was running and the
 * flag was set, `false` when no backfill was in progress. */
export async function cancelBackfill(): Promise<boolean> {
  return invoke<boolean>("cancel_backfill");
}

/** Subscribe to `backfill:progress` events. Pairs with `startBackfill`
 * for live progress strip updates without UI polling. */
export async function onBackfillProgress(
  cb: (payload: { job_id: string } & BackfillProgress) => void,
): Promise<UnlistenFn> {
  return listen<{ job_id: string } & BackfillProgress>("backfill:progress", (e) =>
    cb(e.payload),
  );
}

/** Subscribe to `backfill:done` events. Fires once per job at terminal
 * state (success, cancel, or denial). */
export async function onBackfillDone(
  cb: (payload: { job_id: string } & BackfillProgress) => void,
): Promise<UnlistenFn> {
  return listen<{ job_id: string } & BackfillProgress>("backfill:done", (e) =>
    cb(e.payload),
  );
}

// --- ADR-0006 §Decision 5 tier_changed event bus ----------------------

/** Subscribe to `tier:changed` events. Emitted by the backend whenever
 * `setTier` or `redetectHardware` produces a new TierConfig. Tier-aware
 * subsystems (RetrievalTab today; future TTS / vision / avatar tabs)
 * subscribe to re-evaluate their model selection without polling. */
export async function onTierChanged(
  cb: (cfg: TierConfig) => void,
): Promise<UnlistenFn> {
  return listen<TierConfig>("tier:changed", (e) => cb(e.payload));
}

// --- T1.3 — L5-gated browser automation surface ----------------------
//
// Thin wrappers around the seven `browser_*` Tauri commands. The
// backend is currently the `PlaywrightExecutor` stub: every call below
// will reject with a `BackendDisabled` error string until the real
// Node-subprocess driver lands. The shape is locked now so the UI can
// build against it.

/** Opaque identifier for a live browser session. Round-trip through
 * the `browser_*` surface only — the contents are backend-defined. */
export interface SessionId {
  /** Backend-defined session identifier. */
  0: string;
}

/** A read-only snapshot of a browser page. Returned by
 * {@link browserReadPage}. `text_content` is post-JS visible text. */
export interface PageSnapshot {
  url: string;
  title: string;
  text_content: string;
  captured_at_ms: number;
}

/** A single form-field write request. `selector` is interpreted by the
 * backend (Playwright supports CSS / text / role / chained selectors). */
export interface FormField {
  selector: string;
  value: string;
}

/** Open a fresh browser session and navigate to `url`. Gated by L5
 * `BrowserOpen` — the call rejects when the policy denies. */
export async function browserOpen(url: string): Promise<SessionId> {
  return invoke<SessionId>("browser_open", { url });
}

/** Navigate an existing session to a new URL. In policy terms this is
 * a re-open and is gated by L5 `BrowserOpen` (same scope-allowlist). */
export async function browserNavigate(
  session: SessionId,
  url: string,
): Promise<void> {
  return invoke<void>("browser_navigate", { session, url });
}

/** Read a snapshot of the current page contents. Gated by L5
 * `BrowserReadPage`. */
export async function browserReadPage(
  session: SessionId,
): Promise<PageSnapshot> {
  return invoke<PageSnapshot>("browser_read_page", { session });
}

/** Extract text values matching `selector`. Gated by L5
 * `BrowserExtractData`. The selector grammar is backend-defined. */
export async function browserExtract(
  session: SessionId,
  selector: string,
): Promise<string[]> {
  return invoke<string[]>("browser_extract", { session, selector });
}

/** Fill one or more form fields. Does NOT submit — submission goes
 * through {@link browserSubmit} under a separate capability. Gated by
 * L5 `BrowserFillForm`. */
export async function browserFillForm(
  session: SessionId,
  fields: FormField[],
): Promise<void> {
  return invoke<void>("browser_fill_form", { session, fields });
}

/** Submit a form, identified by `selector` (typically the form element
 * or its submit button). Gated by L5 `BrowserSubmit` — the
 * Critical-risk capability that mutates remote state. */
export async function browserSubmit(
  session: SessionId,
  selector: string,
): Promise<void> {
  return invoke<void>("browser_submit", { session, selector });
}

/** Close the session and release its resources. Intentionally ungated
 * per the L5-browser wiring contract — releasing a session is always
 * permitted, otherwise a denied close would leak browser processes. */
export async function browserClose(session: SessionId): Promise<void> {
  return invoke<void>("browser_close", { session });
}

// --- T1.3 — L5-gated file-workflow surface ----------------------------
//
// Thin wrappers around the six `files_*` Tauri commands. The backend is
// currently the `StdFsExecutor` stub: every call below will reject with
// a `BackendDisabled` error string until the real `std::fs` / `tokio::fs`
// driver lands. The shape is locked now so the UI can build against it.

/** A single grep hit returned by {@link filesGrep}. `line_no` is
 * 1-indexed (matching `grep -n`, ripgrep, and editor conventions);
 * `line_text` is the matching line with its trailing newline stripped.
 * Mirrors the Rust `aether_l5_files::GrepHit` struct. */
export interface GrepHit {
  path: string;
  line_no: number;
  line_text: string;
}

/** Read the full contents of a file as raw bytes. The caller is
 * responsible for any text-decoding choices. Gated by L5 `FilesRead`. */
export async function filesRead(path: string): Promise<number[]> {
  return invoke<number[]>("files_read", { path });
}

/** Create a new file with the given contents. The backend MUST refuse
 * to overwrite an existing path — overwrite goes through {@link filesEdit}
 * under the separate `FilesEdit` capability. Gated by L5 `FilesCreate`. */
export async function filesCreate(
  path: string,
  contents: number[],
): Promise<void> {
  return invoke<void>("files_create", { path, contents });
}

/** Replace the contents of an existing file. Real backends write
 * atomically (write-to-temp + rename). Gated by L5 `FilesEdit`. */
export async function filesEdit(
  path: string,
  contents: number[],
): Promise<void> {
  return invoke<void>("files_edit", { path, contents });
}

/** Move or rename a file from `src` to `dst`. Per T1.3 the policy
 * layer enforces an Ask gate above this call — even Operator preset
 * never auto-runs `FilesRenameMove`. Both endpoints must be in
 * approved scope. Gated by L5 `FilesRenameMove`. */
export async function filesRename(src: string, dst: string): Promise<void> {
  return invoke<void>("files_rename", { src, dst });
}

/** Delete a file. Per T1.3 the policy layer enforces an Ask gate
 * above this call — `FilesDelete` never auto-runs in any preset.
 * Gated by L5 `FilesDelete`. */
export async function filesDelete(path: string): Promise<void> {
  return invoke<void>("files_delete", { path });
}

/** Search file contents under `root` for lines matching `pattern`.
 * The pattern grammar is backend-defined (the real backend will use
 * a regex crate). Live read-side scan, no persistent index. Gated by
 * L5 `FilesRead` — anything Read already permits is already greppable
 * (mirrors the `navigate → BrowserOpen` consolidation in the browser
 * surface). */
export async function filesGrep(
  root: string,
  pattern: string,
): Promise<GrepHit[]> {
  return invoke<GrepHit[]>("files_grep", { root, pattern });
}
