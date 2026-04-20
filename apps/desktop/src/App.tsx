import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearSession as apiClearSession,
  companionBanner,
  listPersonas,
  onPresence,
  presenceCurrent,
  resolveApproval,
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
} from "./lib/types";

import { ApprovalModal } from "./components/ApprovalModal";
import { Disclosure } from "./components/Disclosure";
import { Header } from "./components/Header";
import { InputBar } from "./components/InputBar";
import { MemoryDrawer } from "./components/MemoryDrawer";
import { PersonaCard } from "./components/PersonaCard";
import { Transcript } from "./components/Transcript";
import { TrustDrawer } from "./components/TrustDrawer";

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
  const [drawer, setDrawer] = useState<"none" | "memory" | "trust">("none");
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0);
  const [forceDisclosure, setForceDisclosure] = useState(false);
  const [sessionNonce, setSessionNonce] = useState(0);
  const [personas, setPersonas] = useState<PersonaCatalogEntry[]>([]);

  // Boot — load banner, seed presence, subscribe to presence events.
  useEffect(() => {
    let alive = true;
    let unlisten: (() => void) | null = null;
    (async () => {
      try {
        const b = await companionBanner();
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
      setMessages((prev) => [...prev, outcome.message!]);
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
    async (approve: boolean) => {
      if (!pendingApproval) return;
      setBusy(true);
      try {
        const outcome = await resolveApproval(
          pendingApproval.ticket_id,
          approve,
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

  const handleSwitchPersona = useCallback(
    async (id: string) => {
      if (busy) return;
      if (banner && id === banner.persona_id) return;
      setBusy(true);
      try {
        const b = await apiSwitchPersona(id);
        setBanner(b);
        setMessages([]);
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
    return `Message ${banner?.persona_name ?? "Aether"}…`;
  }, [banner]);

  if (bootError) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center">
        <div>
          <div className="text-[13px] text-aether-err">
            Aether failed to start.
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
          Starting Aether…
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <Disclosure
        forceOpen={forceDisclosure}
        onClose={() => setForceDisclosure(false)}
      />
      <Header
        banner={banner}
        presence={presence}
        personas={personas}
        onOpenMemory={() => setDrawer("memory")}
        onOpenTrust={() => setDrawer("trust")}
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
      <MemoryDrawer
        open={drawer === "memory"}
        refreshKey={memoryRefreshKey}
        onClose={() => setDrawer("none")}
      />
      <TrustDrawer
        open={drawer === "trust"}
        refreshKey={memoryRefreshKey}
        onClose={() => setDrawer("none")}
      />
      {pendingApproval && (
        <ApprovalModal
          payload={pendingApproval}
          working={busy}
          onApprove={() => handleResolve(true)}
          onReject={() => handleResolve(false)}
        />
      )}
    </div>
  );
}
