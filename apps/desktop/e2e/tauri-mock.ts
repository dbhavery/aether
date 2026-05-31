import type { Page } from "@playwright/test";

/**
 * Shape of the approval the mocked `submit_turn` will raise. Mirrors
 * `ApprovalPayload` in src/lib/types.ts. Kept as a local literal type
 * (not an import) so the init-script callback stays self-contained and
 * serialisable across the Playwright page boundary.
 */
export interface MockApprovalPayload {
  ticket_id: string;
  capability: string;
  scope: string;
  reason: string;
  risk_hint: string;
  task_id_present: boolean;
  side_effecting: boolean;
}

/** A persona the mocked `list_personas` returns and `switch_persona`
 * can activate. Mirrors `PersonaCatalogEntry`. */
export interface MockPersona {
  id: string;
  name: string;
  tagline?: string;
  stance?: string;
  tone?: string;
}

export interface TauriMockConfig {
  /** The approval `submit_turn` raises. Omit to make `submit_turn`
   * return a plain completed turn (no modal). */
  approval?: MockApprovalPayload;
  /** Installed persona catalog. Defaults to a single "aurora". Provide
   * 2+ to surface the header persona `<select>` (T2.4). The first entry
   * is the active persona on boot. */
  personas?: MockPersona[];
  /** Initial value `current_autonomy_preset` returns (T2.3). Defaults
   * to null ("not chosen"). */
  initialAutonomy?: "observer" | "assistant" | "operator" | null;
}

/** One recorded IPC call, readable from the test via
 * `page.evaluate(() => window.__MOCK_CALLS__)`. */
export interface RecordedCall {
  cmd: string;
  args: unknown;
}

declare global {
  interface Window {
    __MOCK_CALLS__?: RecordedCall[];
    __TAURI_INTERNALS__?: {
      transformCallback(cb: unknown, once?: boolean): number;
      unregisterCallback(id: number): void;
      convertFileSrc(path: string, protocol?: string): string;
      invoke(cmd: string, args: unknown, options?: unknown): Promise<unknown>;
    };
  }
}

/**
 * Install the Tauri IPC shim before the app bundle runs. Must be called
 * before `page.goto`. Returns nothing — assertions read the recorded
 * calls back via `readCalls`.
 */
export async function installTauriMock(
  page: Page,
  config: TauriMockConfig = {},
): Promise<void> {
  await page.addInitScript((cfg: TauriMockConfig) => {
    // Skip all three first-run onboarding gates so the chat surface
    // (and thus the approval flow) is reachable. Values mirror the
    // version constants the components check:
    //   - PersonaWizard      → aether.persona.last
    //   - Disclosure         → aether.disclosure.acknowledged
    //   - PresetPicker       → aether.onboarding.autonomy-preset(.version)
    const personas =
      cfg.personas && cfg.personas.length > 0
        ? cfg.personas.map((p) => ({
            id: p.id,
            name: p.name,
            tagline: p.tagline ?? `${p.name} test persona.`,
            stance: p.stance ?? "warm",
            tone: p.tone ?? "warm",
          }))
        : [
            {
              id: "aurora",
              name: "Aurora",
              tagline: "Companion test harness persona.",
              stance: "warm",
              tone: "warm",
            },
          ];
    const activeId = personas[0].id;
    // Stateful active persona — switch_persona mutates it so a
    // subsequent companion_banner (the boot effect re-fetches on the
    // sessionNonce bump a switch triggers) reports the NEW persona, as
    // the real backend would. Without this the re-fetch clobbers the
    // switch back to the boot default.
    let currentId = activeId;

    // Skip all three first-run onboarding gates so the chat surface
    // (and thus the approval flow) is reachable. Values mirror the
    // version constants the components check:
    //   - PersonaWizard      → aether.persona.last (the active persona)
    //   - Disclosure         → aether.disclosure.acknowledged
    //   - PresetPicker       → aether.onboarding.autonomy-preset(.version)
    try {
      const ls = window.localStorage;
      ls.setItem("aether.persona.last", activeId);
      ls.setItem("aether.disclosure.acknowledged", "v0-2026-04-19");
      ls.setItem("aether.onboarding.autonomy-preset", "assistant");
      ls.setItem("aether.onboarding.autonomy-preset.version", "v0-2026-04-21");
    } catch {
      // origin not ready — the goto("/") init pass will set it.
    }

    const calls: RecordedCall[] = [];
    window.__MOCK_CALLS__ = calls;

    const bannerFor = (id: string) => {
      const p = personas.find((x) => x.id === id) ?? personas[0];
      return {
        persona_id: p.id,
        persona_name: p.name,
        persona_version: "1.0.0",
        preferred_tier: "balanced",
        provider_mode: "reflex_stub",
        provider_label: "Reflex (stub)",
        output_detail: "balanced",
        tagline: p.tagline,
        system_prompt: "",
      };
    };
    const presence = { state: "quiet", detail: null, updated_at_ms: 0 };

    const completedTurn = (turnId: string) => ({
      turn_id: turnId,
      kind: "completed",
      message: {
        id: `m-${turnId}`,
        role: "assistant",
        content: "Done.",
        sequence: 1,
        timestamp_ms: 0,
        meta: null,
      },
      approval: null,
      error_note: null,
    });

    const handlers: Record<string, (args: unknown) => unknown> = {
      companion_banner: () => bannerFor(currentId),
      list_personas: () => personas,
      presence_current: () => presence,
      // Id-aware + stateful: the header/persona-section switch echoes
      // the chosen persona's banner AND updates the active persona so
      // later companion_banner reads stay consistent.
      switch_persona: (args) => {
        const id = (args as { id?: string } | null)?.id ?? currentId;
        currentId = id;
        return bannerFor(currentId);
      },
      set_autonomy_preset: () => bannerFor(currentId),
      current_autonomy_preset: () => cfg.initialAutonomy ?? null,
      memory_recent: () => [],
      audit_recent: () => [],
      telemetry_recent: () => [],
      submit_turn: () =>
        cfg.approval
          ? {
              turn_id: "turn-1",
              kind: "awaiting_approval",
              message: null,
              approval: cfg.approval,
              error_note: null,
            }
          : completedTurn("turn-1"),
      // The chat surface unwraps `kind: "turn"`; carry a completed
      // outcome so the modal closes and an assistant bubble appends.
      resolve_approval: () => ({ kind: "turn", outcome: completedTurn("turn-1") }),
    };

    let cbId = 0;
    window.__TAURI_INTERNALS__ = {
      transformCallback(_cb: unknown, _once?: boolean) {
        return ++cbId;
      },
      unregisterCallback() {},
      convertFileSrc(p: string) {
        return p;
      },
      invoke(cmd: string, args: unknown) {
        calls.push({ cmd, args });
        // Event-plugin subscriptions (listen/unlisten) — no-op; we
        // never emit events in the harness. Resolve with a fake id.
        if (cmd.startsWith("plugin:event|")) {
          return Promise.resolve(0);
        }
        const handler = handlers[cmd];
        if (handler) {
          return Promise.resolve(handler(args));
        }
        // Surface unhandled commands loudly so the harness can grow
        // its mock surface instead of silently returning garbage.
        // eslint-disable-next-line no-console
        console.warn(`[tauri-mock] unhandled invoke: ${cmd}`, args);
        return Promise.resolve(null);
      },
    };

    // The event plugin's `unlisten` path calls
    // `window.__TAURI_EVENT_PLUGIN_INTERNALS__.unregisterListener`
    // (verified in @tauri-apps/api@2.10.1 event.js `_unlisten`). It
    // fires whenever a listener cleans up — e.g. the presence
    // subscription on a persona switch. Without this shim the cleanup
    // throws and aborts the in-flight React update (caught: banner
    // failed to commit on switch). No-op is correct; we emit no events.
    (
      window as unknown as {
        __TAURI_EVENT_PLUGIN_INTERNALS__: {
          unregisterListener(event: string, eventId: number): void;
        };
      }
    ).__TAURI_EVENT_PLUGIN_INTERNALS__ = {
      unregisterListener() {},
    };
  }, config);
}

/** Read every IPC call the app made, in order. */
export async function readCalls(page: Page): Promise<RecordedCall[]> {
  return page.evaluate(() => window.__MOCK_CALLS__ ?? []);
}

/** Read the args of the (single) `resolve_approval` call, or null. */
export async function readResolveChoice(page: Page): Promise<unknown> {
  const calls = await readCalls(page);
  const resolve = calls.find((c) => c.cmd === "resolve_approval");
  return resolve ? resolve.args : null;
}
