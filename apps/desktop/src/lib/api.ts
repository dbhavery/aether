// Thin typed wrapper around Tauri's invoke() + event bus. The rest of the
// UI imports only from here so swapping the backend transport is a one-
// file change.

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import type {
  CompanionBanner,
  FrameAnalysisOutcome,
  MediaKind,
  MediaPermissions,
  MediaPermissionState,
  MicPermission,
  PersonaCatalogEntry,
  PresenceConfig,
  PresencePayload,
  SpeechModelList,
  TranscribeUtteranceRequest,
  TranscriptMessage,
  TrustAuditRow,
  TurnOutcome,
  UtteranceOutcome,
  VisionModelList,
  VisionStatus,
  VoiceStatus,
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
