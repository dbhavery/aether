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

export interface TauriMockConfig {
  /** The approval `submit_turn` raises. Omit to make `submit_turn`
   * return a plain completed turn (no modal). */
  approval?: MockApprovalPayload;
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
    // "aurora" matches the mocked catalog so the boot effect's
    // switch_persona resolves cleanly.
    try {
      const ls = window.localStorage;
      ls.setItem("aether.persona.last", "aurora");
      ls.setItem("aether.disclosure.acknowledged", "v0-2026-04-19");
      ls.setItem("aether.onboarding.autonomy-preset", "assistant");
      ls.setItem("aether.onboarding.autonomy-preset.version", "v0-2026-04-21");
    } catch {
      // origin not ready — the goto("/") init pass will set it.
    }

    const calls: RecordedCall[] = [];
    window.__MOCK_CALLS__ = calls;

    const banner = {
      persona_id: "aurora",
      persona_name: "Aurora",
      persona_version: "1.0.0",
      preferred_tier: "balanced",
      provider_mode: "reflex_stub",
      provider_label: "Reflex (stub)",
      output_detail: "balanced",
      tagline: "Companion test harness persona.",
      system_prompt: "",
    };
    const presence = { state: "quiet", detail: null, updated_at_ms: 0 };
    const personas = [
      {
        id: "aurora",
        name: "Aurora",
        tagline: "Companion test harness persona.",
        stance: "warm",
        tone: "warm",
      },
    ];

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
      companion_banner: () => banner,
      list_personas: () => personas,
      presence_current: () => presence,
      switch_persona: () => banner,
      set_autonomy_preset: () => banner,
      current_autonomy_preset: () => null,
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
