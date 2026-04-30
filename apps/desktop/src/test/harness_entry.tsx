// Doctrine §8 used-as-user harness — entry point.
//
// Mounts the production SettingsDrawer (which embeds PersonaSection)
// with a Tauri-IPC mock installed BEFORE any module imports invoke().
// Playwright drives the resulting page; see tools/used-as-user/ for the
// runner + report.
//
// Test fixture only — never bundled into a release build. Production
// `index.html` does NOT reference this file.

import { mockIPC } from "@tauri-apps/api/mocks";
import { createRoot } from "react-dom/client";
import { useEffect, useState } from "react";

import "../styles/globals.css";
import { SettingsDrawer } from "../components/SettingsDrawer";

/* ----------------------------------------------------------------- *
 * Scenario state — exposed on window so Playwright can flip variants
 * without re-mounting the whole tree.
 * ----------------------------------------------------------------- */

interface ScenarioState {
  /** Initial autonomy preset returned by `current_autonomy_preset`. */
  initialAutonomy: string | null;
  /** Force `current_autonomy_preset` to reject for the error scenario. */
  failAutonomyLoad: boolean;
  /** Force `set_autonomy_preset` to reject when called. */
  failAutonomySet: boolean;
  /** Force `list_personas` to reject for the persona-error scenario. */
  failListPersonas: boolean;
  /** Catalog returned from `list_personas`. */
  catalog: Array<{ id: string; name: string; tagline: string; version: string }>;
  /** Banner returned from `companion_banner`. */
  bannerPersonaId: string;
}

const DEFAULT_SCENARIO: ScenarioState = {
  initialAutonomy: "assistant",
  failAutonomyLoad: false,
  failAutonomySet: false,
  failListPersonas: false,
  catalog: [
    { id: "aurora", name: "Aurora", tagline: "Calm, careful watcher.", version: "0.1.0" },
    { id: "marcus_chen", name: "Marcus Chen", tagline: "Crisp engineer.", version: "0.1.0" },
  ],
  bannerPersonaId: "aurora",
};

declare global {
  interface Window {
    __HARNESS_STATE__: ScenarioState;
    __HARNESS_CALLS__: Array<{ cmd: string; payload: unknown }>;
    __HARNESS_RESET__: (next?: Partial<ScenarioState>) => void;
  }
}

window.__HARNESS_STATE__ = { ...DEFAULT_SCENARIO };
window.__HARNESS_CALLS__ = [];

/* ----------------------------------------------------------------- *
 * Tauri-IPC mock — covers every command SettingsDrawer + PersonaSection
 * call. Reads from window.__HARNESS_STATE__ so scenarios can be flipped
 * at runtime by the Playwright driver.
 * ----------------------------------------------------------------- */

mockIPC((cmd, payload) => {
  window.__HARNESS_CALLS__.push({ cmd, payload });
  const s = window.__HARNESS_STATE__;
  switch (cmd) {
    case "get_media_permissions":
      return { camera: "ask", screen: "ask" };
    case "set_media_permission": {
      const p = payload as { kind: "camera" | "screen"; state: string };
      return { camera: "ask", screen: "ask", [p.kind]: p.state };
    }
    case "get_mic_permission":
      return { state: "ask" };
    case "set_mic_permission": {
      const p = payload as { state: string };
      return { state: p.state };
    }
    case "get_presence_config":
      return {
        enabled: true,
        history_in_trust_drawer: true,
        idle_after_s: 60,
        away_after_s: 300,
      };
    case "set_presence_config":
      return payload;
    case "get_memory_config":
      return {
        default_risk: {
          session: "auto",
          durable: "auto",
          facts: "ask",
          projects: "auto",
          preferences: "auto",
          artifacts: "ask",
        },
        retention_days: {
          session: null,
          durable: 30,
          facts: null,
          projects: null,
          preferences: null,
          artifacts: null,
        },
      };
    case "set_memory_config":
      return payload;
    case "current_autonomy_preset":
      if (s.failAutonomyLoad)
        throw new Error("backend rejected: autonomy load failed (harness)");
      return s.initialAutonomy;
    case "set_autonomy_preset":
      if (s.failAutonomySet)
        throw new Error("backend rejected: unknown autonomy preset (harness)");
      return { slug: s.bannerPersonaId };
    case "list_personas":
      if (s.failListPersonas)
        throw new Error("backend rejected: list_personas failed (harness)");
      return s.catalog;
    case "switch_persona": {
      const p = payload as { id: string };
      s.bannerPersonaId = p.id;
      return {
        persona_id: p.id,
        persona_name: s.catalog.find((c) => c.id === p.id)?.name ?? p.id,
        persona_version: "0.1.0",
        preferred_tier: "T2",
        provider_mode: "ollama",
        provider_label: "Ollama",
        output_detail: "balanced",
        tagline: "",
        system_prompt: "",
      };
    }
    case "install_persona":
      // Simulate slow install — Playwright will assert busy state.
      return new Promise((resolve) =>
        setTimeout(() => resolve({ ok: true }), 250),
      );
    case "companion_banner":
      return {
        persona_id: s.bannerPersonaId,
        persona_name:
          s.catalog.find((c) => c.id === s.bannerPersonaId)?.name ?? s.bannerPersonaId,
        persona_version: "0.1.0",
        preferred_tier: "T2",
        provider_mode: "ollama",
        provider_label: "Ollama",
        output_detail: "balanced",
        tagline: "",
        system_prompt: "",
      };
    default:
      throw new Error(`harness: unhandled IPC command ${cmd}`);
  }
});

/* ----------------------------------------------------------------- *
 * Harness shell.
 * ----------------------------------------------------------------- */

function Harness() {
  const [open, setOpen] = useState(true);
  // Used to remount on scenario reset so useEffect refires.
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    window.__HARNESS_RESET__ = (next) => {
      window.__HARNESS_STATE__ = { ...DEFAULT_SCENARIO, ...(next ?? {}) };
      window.__HARNESS_CALLS__ = [];
      setOpen(false);
      // re-open on next tick so useEffect cleanup runs first
      setTimeout(() => {
        setNonce((n) => n + 1);
        setOpen(true);
      }, 10);
    };
  }, []);

  return (
    <div className="h-screen w-screen bg-aether-bg">
      <div className="p-4 text-[12px] text-aether-muted">
        <div className="mb-2 text-aether-text">
          T2.3 / T2.4 used-as-user harness — drawer mounted on the right.
        </div>
        <div>
          Active autonomy seed:{" "}
          <code className="text-aether-dim">
            {String(window.__HARNESS_STATE__.initialAutonomy)}
          </code>{" "}
          | banner persona:{" "}
          <code className="text-aether-dim">
            {window.__HARNESS_STATE__.bannerPersonaId}
          </code>
        </div>
      </div>
      <SettingsDrawer
        key={nonce}
        open={open}
        onClose={() => setOpen(false)}
      />
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Harness />);
