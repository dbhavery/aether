// Thin typed wrapper around Tauri's invoke() + event bus. The rest of the
// UI imports only from here so swapping the backend transport is a one-
// file change.

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import type {
  CompanionBanner,
  PersonaCatalogEntry,
  PresencePayload,
  TranscriptMessage,
  TrustAuditRow,
  TurnOutcome,
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
