/**
 * Wizard store.
 *
 * Mirrors `src/onboarding/state.py::WizardState`. Persisted to sessionStorage
 * so a mid-wizard tab refresh doesn't lose non-secret inputs; the backend is
 * the real durable store (writes `wizard_state.yaml` on every validated step).
 *
 * `submitStep` is the RPC bridge:
 *   1. Sends `WIZARD_STEP_SUBMIT` over WS with step + payload + request_id.
 *   2. Resolves when a `WIZARD_STEP_RESULT` with a matching request_id arrives.
 *   3. Times out after STEP_TIMEOUT_MS so a wedged backend doesn't freeze UX.
 */

"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { getWsClient } from "../ws";
import {
  EventType,
  ExtendedEventType,
  WIZARD_STEP_ORDER,
  WizardStepId,
  type LlmProvider,
  type LlmTierMap,
  type TelemetryPrefs,
  type VoiceMode,
  type VoiceSettings,
} from "../types";

const STEP_TIMEOUT_MS = 20_000;

/* -----------------------------------------------------------------------
 * Per-step payload types — narrowed so the caller can't smuggle in garbage.
 * --------------------------------------------------------------------- */

export interface WelcomeStepPayload {
  started_at: string;
}
export interface AvatarStepPayload {
  selected_avatar_id: string;
}
export interface PersonalityStepPayload {
  selected_archetype: string;
}
export interface NameStepPayload {
  display_name: string;
}
export interface LlmStepPayload {
  llm_provider: LlmProvider;
  llm_tier_map: LlmTierMap;
  llm_model_overrides?: Record<string, string>;
  /**
   * BYOK API key. Sent to backend on submit so it can validate via litellm
   * and forward to the OS keyring. Never stored in the wizard store and
   * never persisted to disk on the frontend — gone from memory the moment
   * `submitStep` resolves.
   */
  key?: string;
}
export interface VoiceStepPayload {
  voice_mode: VoiceMode;
  voice_settings: VoiceSettings;
}
export interface TermsStepPayload {
  accepted_terms_at: string;
  telemetry: TelemetryPrefs;
}

export type WizardStepPayload =
  | WelcomeStepPayload
  | AvatarStepPayload
  | PersonalityStepPayload
  | NameStepPayload
  | LlmStepPayload
  | VoiceStepPayload
  | TermsStepPayload;

export interface WizardStepResult {
  success: boolean;
  step: WizardStepId;
  error?: string;
  next_step?: WizardStepId;
  /** Backend may echo the full state for reconciliation. */
  state?: Partial<WizardState>;
}

/* -----------------------------------------------------------------------
 * Store shape.
 * --------------------------------------------------------------------- */

export interface WizardState {
  installationId: string | null;
  currentStep: WizardStepId;
  completedSteps: WizardStepId[];
  selectedAvatarId: string | null;
  selectedArchetype: string | null;
  displayName: string | null;
  llmProvider: LlmProvider | null;
  llmTierMap: LlmTierMap | null;
  llmModelOverrides: Record<string, string> | null;
  voiceMode: VoiceMode | null;
  voiceSettings: VoiceSettings;
  telemetry: TelemetryPrefs;
  termsAcceptedAt: string | null;

  /* UX state — ephemeral per render. */
  inFlight: boolean;
  lastError: string | null;

  submitStep<P extends WizardStepPayload>(
    step: WizardStepId,
    payload: P,
  ): Promise<WizardStepResult>;
  loadFromBackend(): Promise<void>;
  hydrateFromPartial(partial: Partial<WizardState>): void;
  markStepCompleted(step: WizardStepId): void;
  resetError(): void;
  resetAll(): void;
}

const INITIAL_STATE: Omit<
  WizardState,
  | "submitStep"
  | "loadFromBackend"
  | "hydrateFromPartial"
  | "markStepCompleted"
  | "resetError"
  | "resetAll"
> = {
  installationId: null,
  currentStep: WizardStepId.WELCOME,
  completedSteps: [],
  selectedAvatarId: null,
  selectedArchetype: null,
  displayName: null,
  llmProvider: null,
  llmTierMap: null,
  llmModelOverrides: null,
  voiceMode: null,
  voiceSettings: {},
  telemetry: { crash_reports: false, usage_counters: false },
  termsAcceptedAt: null,
  inFlight: false,
  lastError: null,
};

let requestCounter = 0;
function nextRequestId(): string {
  requestCounter += 1;
  return `wiz-${Date.now().toString(36)}-${requestCounter}`;
}

/* -----------------------------------------------------------------------
 * SessionStorage guard — middleware tries to read `window` eagerly, which
 * breaks SSR snapshots. We fall back to a no-op storage during build.
 * --------------------------------------------------------------------- */
function safeSessionStorage(): Storage | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    return window.sessionStorage;
  } catch {
    return undefined;
  }
}

export const useWizardStore = create<WizardState>()(
  persist(
    (set, get) => ({
      ...INITIAL_STATE,

      resetError() {
        set({ lastError: null });
      },

      resetAll() {
        set({ ...INITIAL_STATE });
      },

      hydrateFromPartial(partial) {
        set((prev) => ({
          ...prev,
          ...partial,
          voiceSettings: { ...prev.voiceSettings, ...(partial.voiceSettings ?? {}) },
          telemetry: { ...prev.telemetry, ...(partial.telemetry ?? {}) },
        }));
      },

      markStepCompleted(step) {
        set((prev) => {
          if (prev.completedSteps.includes(step)) return prev;
          const idx = WIZARD_STEP_ORDER.indexOf(step);
          const nextIdx = idx >= 0 && idx + 1 < WIZARD_STEP_ORDER.length ? idx + 1 : idx;
          const fallbackStep: WizardStepId = WIZARD_STEP_ORDER[nextIdx] ?? prev.currentStep;
          const nextStep: WizardStepId = WIZARD_STEP_ORDER[nextIdx] ?? fallbackStep;
          return {
            ...prev,
            completedSteps: [...prev.completedSteps, step],
            currentStep: nextStep,
          };
        });
      },

      async submitStep(step, payload) {
        const ws = getWsClient();
        const requestId = nextRequestId();

        set({ inFlight: true, lastError: null });

        const applyPayloadToStore = (): void => {
          const current = get();
          switch (step) {
            case WizardStepId.AVATAR: {
              const p = payload as AvatarStepPayload;
              current.hydrateFromPartial({ selectedAvatarId: p.selected_avatar_id });
              break;
            }
            case WizardStepId.PERSONALITY: {
              const p = payload as PersonalityStepPayload;
              current.hydrateFromPartial({ selectedArchetype: p.selected_archetype });
              break;
            }
            case WizardStepId.NAME: {
              const p = payload as NameStepPayload;
              current.hydrateFromPartial({ displayName: p.display_name });
              break;
            }
            case WizardStepId.LLM: {
              const p = payload as LlmStepPayload;
              current.hydrateFromPartial({
                llmProvider: p.llm_provider,
                llmTierMap: p.llm_tier_map,
                llmModelOverrides: p.llm_model_overrides ?? null,
              });
              break;
            }
            case WizardStepId.VOICE: {
              const p = payload as VoiceStepPayload;
              current.hydrateFromPartial({
                voiceMode: p.voice_mode,
                voiceSettings: p.voice_settings,
              });
              break;
            }
            case WizardStepId.TERMS: {
              const p = payload as TermsStepPayload;
              current.hydrateFromPartial({
                termsAcceptedAt: p.accepted_terms_at,
                telemetry: p.telemetry,
              });
              break;
            }
            case WizardStepId.WELCOME:
            case WizardStepId.HANDOFF:
              break;
          }
        };

        return new Promise<WizardStepResult>((resolve) => {
          let settled = false;
          const timer = setTimeout(() => {
            if (settled) return;
            settled = true;
            unsubscribe();
            set({ inFlight: false, lastError: "Backend did not respond in time." });
            resolve({
              success: false,
              step,
              error: "Backend did not respond in time.",
            });
          }, STEP_TIMEOUT_MS);

          const unsubscribe = ws.subscribe(EventType.WIZARD_STEP_RESULT, (event) => {
            const data = event.data as {
              request_id?: string;
              success?: boolean;
              step?: string;
              error?: string;
              next_step?: string;
              state?: Partial<WizardState>;
            };
            if (data.request_id !== requestId) return;
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            unsubscribe();

            const success = data.success === true;
            if (success) {
              applyPayloadToStore();
              get().markStepCompleted(step);
              if (data.state) get().hydrateFromPartial(data.state);
            } else {
              set({ lastError: data.error ?? "Validation failed." });
            }
            set({ inFlight: false });
            resolve({
              success,
              step,
              error: data.error,
              next_step: data.next_step as WizardStepId | undefined,
              state: data.state,
            });
          });

          ws.send(EventType.WIZARD_STEP_SUBMIT, {
            request_id: requestId,
            step,
            payload,
          });
        });
      },

      async loadFromBackend() {
        const ws = getWsClient();
        const requestId = nextRequestId();

        return new Promise<void>((resolve) => {
          let settled = false;
          const timer = setTimeout(() => {
            if (settled) return;
            settled = true;
            unsubscribe();
            resolve();
          }, 2_000);

          const unsubscribe = ws.subscribe(
            ExtendedEventType.WIZARD_STATE_RESULT,
            (event) => {
              const data = event.data as {
                request_id?: string;
                state?: Partial<WizardState>;
              };
              if (data.request_id !== requestId) return;
              if (settled) return;
              settled = true;
              clearTimeout(timer);
              unsubscribe();
              if (data.state) get().hydrateFromPartial(data.state);
              resolve();
            },
          );

          ws.send(ExtendedEventType.WIZARD_STATE_REQUEST, { request_id: requestId });
        });
      },
    }),
    {
      name: "aether.wizard.v1",
      version: 1,
      storage: createJSONStorage(() => safeSessionStorage() ?? noopStorage),
      // Never persist ephemeral UX flags.
      partialize: (state) => {
        const {
          inFlight: _inFlight,
          lastError: _lastError,
          submitStep: _submitStep,
          loadFromBackend: _loadFromBackend,
          hydrateFromPartial: _hydrateFromPartial,
          markStepCompleted: _markStepCompleted,
          resetError: _resetError,
          resetAll: _resetAll,
          ...persisted
        } = state;
        return persisted;
      },
    },
  ),
);

const noopStorage: Storage = {
  length: 0,
  clear() {},
  getItem() {
    return null;
  },
  key() {
    return null;
  },
  removeItem() {},
  setItem() {},
};
