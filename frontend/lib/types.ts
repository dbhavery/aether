/**
 * Frontend-side mirror of the backend's event contract.
 *
 * Source of truth: `src/shared/types.py` — this file MUST stay in sync. Any
 * drift between the two is a contract bug; when the backend adds a new event,
 * we add it here too, and vice-versa.
 *
 * Notes on current drift (as of 2026-04-17):
 *  - ARCHITECTURE-V2.md §5 mentions events that are NOT yet in `types.py`
 *    (USER_SPEECH_START, USER_SPEECH_END, RESPONSE_TEXT_CHUNK, RESPONSE_START,
 *    RESPONSE_END, AVATAR_STATE_CHANGED, RESPONSE_AUDIO_END). They are
 *    declared here under `ExtendedEventType` so the frontend can subscribe
 *    optimistically. The backend should add these to `EventType` before we
 *    rely on them.
 */

export const EventType = {
  // Core
  PING: "ping",
  PONG: "pong",
  HEALTH_CHECK: "health_check",
  MODULE_REGISTERED: "module_registered",
  MODULE_READY: "module_ready",

  // Conversation
  USER_MESSAGE: "user_message",
  RESPONSE_TEXT_READY: "response_text_ready",
  TOOL_CALL_REQUESTED: "tool_call_requested",
  TOOL_RESULT_READY: "tool_result_ready",

  // Voice
  TRANSCRIPT_READY: "transcript_ready",
  AUDIO_CHUNK_READY: "audio_chunk_ready",

  // Memory
  MEMORY_STORE_REQUEST: "memory_store_request",
  MEMORY_QUERY_REQUEST: "memory_query_request",
  MEMORY_QUERY_RESULT: "memory_query_result",

  // Settings
  SETTINGS_CHANGED: "settings_changed",

  // Onboarding wizard
  WIZARD_STEP_SUBMIT: "wizard_step_submit",
  WIZARD_STEP_RESULT: "wizard_step_result",
  ONBOARDING_COMPLETE: "onboarding_complete",

  // Persona / provider lifecycle
  PERSONA_CHANGED: "persona_changed",
  PROVIDER_CHANGED: "provider_changed",

  // Status
  PROCESSING_SLOW: "processing_slow",
  PROCESSING_VERY_SLOW: "processing_very_slow",
  ERROR: "error",
} as const;

export type EventType = (typeof EventType)[keyof typeof EventType];

/**
 * Events declared in ARCHITECTURE-V2.md but not yet in `src/shared/types.py`.
 * Subscribing to these is safe — the WS client keeps unknown types in a
 * generic bucket — but sending them will no-op on the backend until added.
 */
export const ExtendedEventType = {
  USER_SPEECH_START: "user_speech_start",
  USER_SPEECH_END: "user_speech_end",
  RESPONSE_TEXT_CHUNK: "response_text_chunk",
  RESPONSE_START: "response_start",
  RESPONSE_END: "response_end",
  RESPONSE_AUDIO_CHUNK: "response_audio_chunk",
  RESPONSE_AUDIO_END: "response_audio_end",
  AVATAR_STATE_CHANGED: "avatar_state_changed",
  ONBOARDING_STEP: "onboarding_step",
  VOICE_PREVIEW_REQUEST: "voice_preview_request",
  LLM_KEY_TEST_REQUEST: "llm_key_test_request",
  LLM_KEY_TEST_RESULT: "llm_key_test_result",
  OLLAMA_PROBE_REQUEST: "ollama_probe_request",
  OLLAMA_PROBE_RESULT: "ollama_probe_result",
  VOICE_HARDWARE_PROBE_REQUEST: "voice_hardware_probe_request",
  VOICE_HARDWARE_PROBE_RESULT: "voice_hardware_probe_result",
  WIZARD_STATE_REQUEST: "wizard_state_request",
  WIZARD_STATE_RESULT: "wizard_state_result",
} as const;

export type ExtendedEventType = (typeof ExtendedEventType)[keyof typeof ExtendedEventType];

/**
 * Union of every event type the UI speaks. `string` fallback covers unknown
 * events that slip in from a newer backend — we keep them rather than
 * dropping them silently.
 */
export type AnyEventType = EventType | ExtendedEventType | (string & {});

export interface AetherEvent<TData = Record<string, unknown>> {
  type: AnyEventType;
  data: TData;
  timestamp: number;
  source_module: string;
}

export type InteractionMode = "text" | "voice" | "video";
export type MessageRole = "user" | "assistant" | "system";

export type WsStatus = "disconnected" | "connecting" | "connected" | "error";

/**
 * Wizard step IDs — matched 1:1 to `src/onboarding/state.py::WizardStep`.
 * These values double as URL slugs.
 */
export const WizardStepId = {
  WELCOME: "1-welcome",
  AVATAR: "2-avatar",
  PERSONALITY: "3-personality",
  NAME: "4-name",
  LLM: "5-llm",
  VOICE: "6-voice",
  TERMS: "7-terms",
  HANDOFF: "8-handoff",
} as const;

export type WizardStepId = (typeof WizardStepId)[keyof typeof WizardStepId];

export const WIZARD_STEP_ORDER: readonly WizardStepId[] = [
  WizardStepId.WELCOME,
  WizardStepId.AVATAR,
  WizardStepId.PERSONALITY,
  WizardStepId.NAME,
  WizardStepId.LLM,
  WizardStepId.VOICE,
  WizardStepId.TERMS,
  WizardStepId.HANDOFF,
];

export function isWizardStepId(value: string): value is WizardStepId {
  return (WIZARD_STEP_ORDER as readonly string[]).includes(value);
}

/**
 * LLM providers — matches `docs/LLM-PROVIDERS.md` and
 * `ONBOARDING-SPEC.md §2 Screen 5 Card B`.
 */
export const LlmProvider = {
  OLLAMA: "ollama",
  ANTHROPIC: "anthropic",
  OPENAI: "openai",
  GOOGLE: "google",
  GROQ: "groq",
  OPENROUTER: "openrouter",
  GUEST: "guest",
} as const;

export type LlmProvider = (typeof LlmProvider)[keyof typeof LlmProvider];

export const BYOK_PROVIDERS: readonly LlmProvider[] = [
  LlmProvider.ANTHROPIC,
  LlmProvider.OPENAI,
  LlmProvider.GOOGLE,
  LlmProvider.GROQ,
  LlmProvider.OPENROUTER,
];

export type VoiceMode = "local" | "elevenlabs" | "off";

export interface LlmTierMap {
  fast: string;
  main: string;
  heavy: string;
}

export interface VoiceSettings {
  elevenlabs_voice_id?: string;
  device?: string;
}

export interface TelemetryPrefs {
  crash_reports: boolean;
  usage_counters: boolean;
}
