/**
 * Session-level app state — status of the backend link, onboarding flag,
 * active persona, current mode. Deliberately small. Anything that survives
 * a reload belongs in `wizard.ts` or `config.ts`, not here.
 */

"use client";

import { create } from "zustand";
import { getWsClient } from "../ws";
import { EventType, type WsStatus } from "../types";

const HEALTH_URL = "http://localhost:8767/health";

export type AppMode = "chat" | "sandbox" | "video";

export interface SessionState {
  wsStatus: WsStatus;
  wsStatusDetail?: string;
  onboardingComplete: boolean;
  onboardingCheckPerformed: boolean;
  activePersonaId: string | null;
  activeDisplayName: string | null;
  mode: AppMode;
  setMode(mode: AppMode): void;
  toggleMode(): void;
  setWsStatus(status: WsStatus, detail?: string): void;
  setOnboardingComplete(complete: boolean): void;
  setActivePersona(id: string | null, displayName: string | null): void;
  bootstrap(): Promise<void>;
}

const MODE_CYCLE: readonly AppMode[] = ["chat", "sandbox", "video"];

export const useSessionStore = create<SessionState>((set, get) => ({
  wsStatus: "disconnected",
  wsStatusDetail: undefined,
  onboardingComplete: false,
  onboardingCheckPerformed: false,
  activePersonaId: null,
  activeDisplayName: null,
  mode: "chat",

  setMode(mode) {
    set({ mode });
  },

  toggleMode() {
    const current = get().mode;
    const idx = MODE_CYCLE.indexOf(current);
    const nextIdx = (idx + 1) % MODE_CYCLE.length;
    const next = MODE_CYCLE[nextIdx] ?? "chat";
    set({ mode: next });
  },

  setWsStatus(wsStatus, wsStatusDetail) {
    set({ wsStatus, wsStatusDetail });
  },

  setOnboardingComplete(onboardingComplete) {
    set({ onboardingComplete, onboardingCheckPerformed: true });
  },

  setActivePersona(activePersonaId, activeDisplayName) {
    set({ activePersonaId, activeDisplayName });
  },

  async bootstrap() {
    if (typeof window === "undefined") return;
    const ws = getWsClient();

    // Wire WS status into the store exactly once per session.
    ws.onStatusChange((status, detail) => {
      get().setWsStatus(status, detail);
    });
    ws.subscribe(EventType.ONBOARDING_COMPLETE, (event) => {
      get().setOnboardingComplete(true);
      const { persona_id, display_name } = event.data as {
        persona_id?: string;
        display_name?: string;
      };
      if (persona_id) {
        get().setActivePersona(persona_id, display_name ?? null);
      }
    });
    ws.subscribe(EventType.PERSONA_CHANGED, (event) => {
      const { persona_id, display_name } = event.data as {
        persona_id?: string;
        display_name?: string;
      };
      if (persona_id) {
        get().setActivePersona(persona_id, display_name ?? null);
      }
    });
    ws.connect();

    // Health probe — liveness only today. The backend's /health doesn't yet
    // expose onboarding_complete (see ARCHITECTURE-V2.md §6 — config.yaml
    // carries it), so we optimistically assume "not onboarded" until the
    // backend either reports it via a future WIZARD_STATE_RESULT event or
    // we successfully load a `wizard_state.yaml` via the wizard store.
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 3_000);
      const resp = await fetch(HEALTH_URL, { signal: controller.signal, cache: "no-store" });
      clearTimeout(timer);
      if (resp.ok) {
        const payload: unknown = await resp.json();
        const onboardingComplete = extractOnboardingFlag(payload);
        set({
          onboardingComplete,
          onboardingCheckPerformed: true,
        });
        return;
      }
    } catch {
      // Backend not up or health timed out — treat as onboarding pending and
      // let the connection state drive UI.
    }
    set({ onboardingCheckPerformed: true });
  },
}));

function extractOnboardingFlag(payload: unknown): boolean {
  if (!payload || typeof payload !== "object") return false;
  // Accept either a top-level `onboarding_complete` boolean or a nested
  // `config.onboarding_complete` — whichever the backend decides to ship.
  const p = payload as Record<string, unknown>;
  if (typeof p.onboarding_complete === "boolean") return p.onboarding_complete;
  const config = p.config;
  if (config && typeof config === "object") {
    const c = config as Record<string, unknown>;
    if (typeof c.onboarding_complete === "boolean") return c.onboarding_complete;
  }
  return false;
}
