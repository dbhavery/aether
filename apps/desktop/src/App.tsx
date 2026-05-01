import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearSession as apiClearSession,
  companionBanner,
  listPersonas,
  memoryRecent,
  onPresence,
  presenceCurrent,
  resolveApprovalForTurn,
  setAutonomyPreset,
  submitTurn,
  switchPersona as apiSwitchPersona,
} from "./lib/api";
import type {
  ApprovalPayload,
  CompanionBanner,
  PersonaCatalogEntry,
  PresencePayload,
  TranscriptMessage,
  TurnOutcome,
  UserChoice,
} from "./lib/types";

import { ApprovalModal } from "./components/ApprovalModal";
import { CameraPanel } from "./components/CameraPanel";
import { Disclosure } from "./components/Disclosure";
import { Header } from "./components/Header";
import { InputBar } from "./components/InputBar";
import { PersonaCard } from "./components/PersonaCard";
import { PersonaWizard } from "./components/PersonaWizard";
import { PresetPicker, readStoredPreset } from "./components/PresetPicker";
import { ScreenPanel } from "./components/ScreenPanel";
import { SettingsDrawer } from "./components/SettingsDrawer";
import { Transcript } from "./components/Transcript";
import { ToastContainer } from "./components/ToastContainer";
import { TrustDrawer } from "./components/TrustDrawer";
import { VoicePanel } from "./components/VoicePanel";

const PERSONA_STORAGE_KEY = "aether.persona.last";

function readStoredPersonaId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(PERSONA_STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStoredPersonaId(id: string) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PERSONA_STORAGE_KEY, id);
  } catch {
    // non-fatal
  }
}

export function App() {
  const [banner, setBanner] = useState<CompanionBanner | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [presence, setPresence] = useState<PresencePayload>({
    state: "quiet",
    detail: null,
    updated_at_ms: 0,
  });
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [pendingApproval, setPendingApproval] =
    useState<ApprovalPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [drawer, setDrawer] = useState<
    "none" | "memory" | "trust" | "settings" | "camera" | "screen" | "voice"
  >("none");
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0);
  const [forceDisclosure, setForceDisclosure] = useState(false);
  // Bumps whenever the Disclosure modal closes so the PresetPicker can
  // re-evaluate its open state (it only auto-shows once Disclosure is
  // acknowledged, and this lets them sequence within one session).
  const [disclosureCloseNonce, setDisclosureCloseNonce] = useState(0);
  const [sessionNonce, setSessionNonce] = useState(0);
  const [personas, setPersonas] = useState<PersonaCatalogEntry[]>([]);
  // Onboarding gate — first launch (no stored persona) shows the
  // PersonaWizard instead of the chat shell. The boot effect still
  // runs underneath so the catalog loads in time for the wizard's
  // availability filter; the wizard only takes the foreground.
  const [showWizard, setShowWizard] = useState<boolean>(
    () => readStoredPersonaId() === null,
  );

  // Boot — load banner, seed presence, subscribe to presence events.
  useEffect(() => {
    let alive = true;
    let unlisten: (() => void) | null = null;
    (async () => {
      try {
        let b = await companionBanner();
        if (!alive) return;
        // Restore the last-picked persona. AETHER_PERSONA env var takes
        // precedence on the backend (handled by state.rs::pick_default
        // at process start); this branch only runs if the user explicitly
        // chose something on a prior launch and we've booted into a
        // different default.
        const storedPersona = readStoredPersonaId();
        if (
          storedPersona &&
          storedPersona !== b.persona_id &&
          // Only restore if the persona still exists in the current
          // catalog — avoids "unknown persona" errors after a catalog
          // edit or downgrade.
          true
        ) {
          try {
            const cat = await listPersonas();
            if (cat.some((p) => p.id === storedPersona)) {
              b = await apiSwitchPersona(storedPersona);
            }
          } catch {
            // Non-fatal — fall through with the default banner.
          }
        }
        if (!alive) return;
        // Re-apply any stored autonomy preset so the engine picks up the
        // user's prior choice on boot. Storage holds "observer" |
        // "assistant" | "operator" | "later" | null. "later" and null
        // both map to "no overlay" on the backend.
        const storedPreset = readStoredPreset();
        try {
          const wire =
            storedPreset === "observer" ||
            storedPreset === "assistant" ||
            storedPreset === "operator"
              ? storedPreset
              : null;
          b = await setAutonomyPreset(wire);
        } catch {
          // Non-fatal — engine remains on whatever the last-known
          // overlay was.
        }
        if (!alive) return;
        setBanner(b);
        const p = await presenceCurrent();
        if (!alive) return;
        setPresence(p);
        const cat = await listPersonas();
        if (!alive) return;
        setPersonas(cat);
      } catch (e) {
        if (alive) setBootError(String(e));
      }
    })();
    onPresence((p) => {
      setPresence(p);
    })
      .then((u) => {
        unlisten = u;
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (unlisten) unlisten();
    };
  }, [sessionNonce]);

  const appendUser = useCallback(
    (text: string) => {
      const id = `user-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      setMessages((prev) => [
        ...prev,
        {
          id,
          role: "user",
          content: text,
          sequence: 0,
          timestamp_ms: Date.now(),
          meta: null,
        },
      ]);
    },
    [],
  );

  const appendOutcome = useCallback((outcome: TurnOutcome) => {
    if (outcome.message) {
      // Wave 16 — tag draft_only outcomes so Transcript can render the
      // dedicated "DRAFT ONLY" affordance instead of the generic
      // system-message styling. The Rust side ships a system message
      // with stable phrasing ("Draft only — no side effects were
      // produced.") and TurnOutcomeKind = "draft_only"; the variant
      // tag lives only on the renderer side.
      const message =
        outcome.kind === "draft_only"
          ? { ...outcome.message, variant: "draft_only" as const }
          : outcome.message;
      setMessages((prev) => [...prev, message]);
    }
    setMemoryRefreshKey((k) => k + 1);
  }, []);

  const handleSubmit = useCallback(
    async (text: string) => {
      if (busy) return;
      setBusy(true);
      appendUser(text);
      try {
        const outcome = await submitTurn(text);
        if (outcome.kind === "awaiting_approval" && outcome.approval) {
          setPendingApproval(outcome.approval);
          return;
        }
        appendOutcome(outcome);
      } catch (e) {
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "system",
            content: `Something went wrong: ${String(e)}`,
            sequence: 0,
            timestamp_ms: Date.now(),
            meta: null,
          },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [busy, appendUser, appendOutcome],
  );

  const handleResolve = useCallback(
    async (userChoice: UserChoice) => {
      if (!pendingApproval) return;
      setBusy(true);
      try {
        const outcome = await resolveApprovalForTurn(
          pendingApproval.ticket_id,
          userChoice,
        );
        setPendingApproval(null);
        appendOutcome(outcome);
      } catch (e) {
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "system",
            content: `Approval failed: ${String(e)}`,
            sequence: 0,
            timestamp_ms: Date.now(),
            meta: null,
          },
        ]);
        setPendingApproval(null);
      } finally {
        setBusy(false);
      }
    },
    [pendingApproval, appendOutcome],
  );

  const handleClearSession = useCallback(async () => {
    try {
      await apiClearSession();
    } catch {
      // non-fatal
    }
    setMessages([]);
    setPendingApproval(null);
    setSessionNonce((n) => n + 1);
    setMemoryRefreshKey((k) => k + 1);
  }, []);

  const handleWizardCommit = useCallback(
    async (slug: string) => {
      // The wizard already filtered down to backend-available personas
      // before exposing this slug, so switchPersona is expected to
      // succeed. We still surface a friendly message on failure rather
      // than crashing the wizard — the user can pick a different
      // companion if the catalog drifted between mount and commit.
      try {
        const b = await apiSwitchPersona(slug);
        setBanner(b);
        writeStoredPersonaId(slug);
        setShowWizard(false);
        setSessionNonce((n) => n + 1);
        setMemoryRefreshKey((k) => k + 1);
      } catch (e) {
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "system",
            content: `Could not start companion: ${String(e)}`,
            sequence: 0,
            timestamp_ms: Date.now(),
            meta: null,
          },
        ]);
      }
    },
    [],
  );

  const handleSwitchPersona = useCallback(
    async (id: string) => {
      if (busy) return;
      if (banner && id === banner.persona_id) return;
      setBusy(true);
      try {
        const b = await apiSwitchPersona(id);
        setBanner(b);
        writeStoredPersonaId(id);
        // Fetch the new session's memory so the persona-switch banner
        // (recorded server-side by switch_persona) is the first message
        // the user sees. Falls back to an empty transcript on error so
        // the UI never shows stale content from the previous persona.
        try {
          const recent = await memoryRecent();
          setMessages(recent);
        } catch {
          setMessages([]);
        }
        setPendingApproval(null);
        setSessionNonce((n) => n + 1);
        setMemoryRefreshKey((k) => k + 1);
      } catch (e) {
        setMessages((prev) => [
          ...prev,
          {
            id: `err-${Date.now()}`,
            role: "system",
            content: `Could not switch persona: ${String(e)}`,
            sequence: 0,
            timestamp_ms: Date.now(),
            meta: null,
          },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [banner, busy],
  );

  const fresh = messages.length === 0;
  const placeholder = useMemo(() => {
    if (banner?.provider_mode === "ollama") {
      return `Message ${banner.persona_name}… (running local model)`;
    }
    return `Message ${banner?.persona_name ?? "Companion"}…`;
  }, [banner]);

  if (bootError) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center">
        <div>
          <div className="text-[13px] text-aether-err">
            Companion failed to start.
          </div>
          <pre className="mt-3 whitespace-pre-wrap text-[11px] font-mono text-aether-muted">
            {bootError}
          </pre>
        </div>
      </div>
    );
  }

  if (!banner) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-[12px] text-aether-muted">
          Starting Companion…
        </div>
      </div>
    );
  }

  if (showWizard) {
    // Wait for the live catalog to land before rendering the wizard.
    // The boot effect sets `banner` first and then awaits `listPersonas`;
    // rendering with `availableSlugs=[]` mid-flight would flash the
    // "no companions available" empty state instead of the cast.
    if (personas.length === 0) {
      return (
        <div className="flex h-full items-center justify-center">
          <div className="text-[12px] text-aether-muted">
            Loading companions…
          </div>
        </div>
      );
    }
    return (
      <div className="h-full overflow-y-auto bg-aether-bg">
        <PersonaWizard
          onCommit={handleWizardCommit}
          availableSlugs={personas.map((p) => p.id)}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <Disclosure
        forceOpen={forceDisclosure}
        onClose={() => {
          setForceDisclosure(false);
          setDisclosureCloseNonce((n) => n + 1);
        }}
      />
      <PresetPicker key={`preset-${disclosureCloseNonce}`} />
      <Header
        banner={banner}
        presence={presence}
        personas={personas}
        onOpenMemory={() => setDrawer("memory")}
        onOpenTrust={() => setDrawer("trust")}
        onOpenSettings={() => setDrawer("settings")}
        onOpenCamera={() => setDrawer("camera")}
        onOpenScreen={() => setDrawer("screen")}
        onOpenVoice={() => setDrawer("voice")}
        onReopenDisclosure={() => setForceDisclosure(true)}
        onClearSession={handleClearSession}
        onSwitchPersona={handleSwitchPersona}
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col">
          {fresh && <PersonaCard banner={banner} />}
          <Transcript messages={messages} />
          <InputBar
            disabled={busy || pendingApproval !== null}
            placeholder={placeholder}
            onSubmit={handleSubmit}
          />
        </div>
      </div>
      {/* Run 5 (2026-04-23): the legacy `MemoryDrawer` was retired now
       * that Memory V2 is closed. The header Memory button opens the
       * Trust drawer on the Memory tab — one canonical surface for
       * "what does Companion remember about me", with forget/edit/approval
       * flows living next to audit + history. Both drawer states
       * (`"memory"` and `"trust"`) render the same component; the
       * `"memory"` state just picks the Memory tab initially. */}
      <TrustDrawer
        open={drawer === "memory" || drawer === "trust"}
        refreshKey={memoryRefreshKey}
        initialTab={drawer === "memory" ? "memory" : undefined}
        onClose={() => setDrawer("none")}
      />
      <SettingsDrawer
        open={drawer === "settings"}
        onClose={() => setDrawer("none")}
      />
      <CameraPanel
        open={drawer === "camera"}
        onClose={() => setDrawer("none")}
        onFrameAnalyzed={(msg) => {
          setMessages((prev) => [...prev, msg]);
          setMemoryRefreshKey((k) => k + 1);
        }}
      />
      <ScreenPanel
        open={drawer === "screen"}
        onClose={() => setDrawer("none")}
        onFrameAnalyzed={(msg) => {
          setMessages((prev) => [...prev, msg]);
          setMemoryRefreshKey((k) => k + 1);
        }}
      />
      <VoicePanel
        open={drawer === "voice"}
        onClose={() => setDrawer("none")}
        onUtteranceTranscribed={(msg) => {
          setMessages((prev) => [...prev, msg]);
          setMemoryRefreshKey((k) => k + 1);
        }}
      />
      {pendingApproval && (
        <ApprovalModal
          payload={pendingApproval}
          working={busy}
          onResolve={handleResolve}
        />
      )}
      <ToastContainer />
    </div>
  );
}
