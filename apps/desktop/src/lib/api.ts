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

export async function resolveApproval(
  ticketId: string,
  approve: boolean,
): Promise<TurnOutcome> {
  return invoke<TurnOutcome>("resolve_approval", {
    ticketId,
    approve,
  });
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
  failures: number;
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
