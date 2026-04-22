// Centralised classification of telemetry `kind` strings produced by
// the `transcribe_utterance` path (Voice V1 step 4).
//
// Mirrors the five string constants the Rust command emits in
// apps/desktop/src-tauri/src/commands.rs::transcribe_utterance:
//   - utterance_transcribed   — speech provider returned text AND the
//                               engine turn completed (policy allowed)
//   - utterance_blocked       — policy blocked the turn after the mic
//                               permission gate passed
//   - utterance_invalid       — shell-side validate_utterance_data_url
//                               rejected the payload before any
//                               provider call ran (no audit row)
//   - mic_permission_denied   — mic permission set to Deny
//   - mic_permission_ask      — mic permission still on Ask; UI must
//                               flip to Allow before retrying
//
// Split from `mediaTurns.ts` so the voice surface has a single home —
// the media/voice modalities have independent consent boundaries and
// will diverge further as Voice V1 step 5 (VoicePanel) lands.

export const VOICE_TURN_KINDS: ReadonlySet<string> = new Set([
  "utterance_transcribed",
  "utterance_blocked",
  "utterance_invalid",
  "mic_permission_denied",
  "mic_permission_ask",
]);

/** True when this telemetry entry came from a transcribe_utterance turn. */
export function isVoiceTurn(kind: string): boolean {
  return VOICE_TURN_KINDS.has(kind);
}
