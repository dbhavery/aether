import { useEffect, useState } from "react";

import {
  auditRecent,
  telemetryClear,
  telemetryRecent,
  type TelemetryEntry,
} from "../lib/api";
import type { AuditDecisionLabel, TrustAuditRow } from "../lib/types";

type Tab = "audit" | "history";

interface Props {
  open: boolean;
  refreshKey: number;
  onClose: () => void;
}

const DECISION_META: Record<
  AuditDecisionLabel,
  { label: string; color: string }
> = {
  allow: { label: "allowed", color: "text-aether-ok" },
  ask: { label: "asked", color: "text-aether-warn" },
  deny: { label: "denied", color: "text-aether-err" },
  needs_upgrade: { label: "needs upgrade", color: "text-aether-warn" },
  draft_only_system: { label: "draft only", color: "text-aether-muted" },
  draft_only_user_choice: { label: "draft only", color: "text-aether-muted" },
};

/**
 * First trust-centre slice — a read-only view of the L5 audit rows this
 * session generated. Answers "what did Aether just decide, and why do I
 * trust that?" per planning/05_ux_principles §Information architecture
 * ("Action history is always reviewable").
 */
export function TrustDrawer({ open, refreshKey, onClose }: Props) {
  const [tab, setTab] = useState<Tab>("audit");
  const [rows, setRows] = useState<TrustAuditRow[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setErr(null);
    Promise.all([auditRecent(100), telemetryRecent(50)])
      .then(([a, t]) => {
        if (cancelled) return;
        setRows(a);
        setTelemetry(t);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open, refreshKey]);

  if (!open) return null;

  const onClearTelemetry = async () => {
    try {
      await telemetryClear();
      setTelemetry([]);
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <div
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-aether-border bg-aether-surface shadow-neuRaised animate-fadeIn"
      role="complementary"
      aria-label="Trust centre"
    >
      <div className="flex items-center justify-between border-b border-aether-border px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Trust · {tab}
          </div>
          <div className="text-[13px] text-aether-text">
            {tab === "audit"
              ? "What Aether decided, in order"
              : "Recent turn timing and usage"}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11px] text-aether-muted hover:border-aether-text hover:text-aether-text"
        >
          Close
        </button>
      </div>
      <div
        role="tablist"
        aria-label="Trust drawer tabs"
        className="flex gap-1 border-b border-aether-border bg-aether-bg/40 px-3 py-2"
      >
        <TabButton
          active={tab === "audit"}
          onClick={() => setTab("audit")}
          label="Audit"
        />
        <TabButton
          active={tab === "history"}
          onClick={() => setTab("history")}
          label="History"
        />
      </div>
      <div className="allow-select flex-1 overflow-y-auto px-5 py-4 text-[12.5px]">
        {err && <div className="text-aether-err">{err}</div>}
        {!err && tab === "audit" && (
          <AuditList rows={rows} />
        )}
        {!err && tab === "history" && (
          <HistoryList entries={telemetry} />
        )}
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-aether-border px-5 py-3 text-[11px] text-aether-muted">
        {tab === "audit" && (
          <span>
            Every decision is sealed in an append-only hash-chained log.
          </span>
        )}
        {tab === "history" && (
          <>
            <span>In-memory only. Cleared on app restart.</span>
            <button
              type="button"
              onClick={onClearTelemetry}
              className="rounded-md border border-aether-border bg-transparent px-2 py-1 text-[10.5px] text-aether-muted hover:border-aether-text hover:text-aether-text"
            >
              Clear
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`rounded-md px-3 py-1 text-[11.5px] transition-colors ${
        active
          ? "border border-aether-borderHi bg-aether-elevated text-aether-text"
          : "border border-aether-border bg-transparent text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
      }`}
    >
      {label}
    </button>
  );
}

function AuditList({ rows }: { rows: TrustAuditRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="mt-6 text-center text-aether-muted">
        No decisions yet. Each turn you send here leaves a sealed row in the
        audit log.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r) => {
        const meta = DECISION_META[r.decision];
        return (
          <div
            key={r.audit_id}
            className="rounded-md border border-aether-border bg-aether-bg/50 px-3 py-2"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span
                className={`text-[11px] font-mono uppercase tracking-wider ${meta.color}`}
              >
                {meta.label}
              </span>
              <span className="text-[10px] font-mono text-aether-dim">
                {r.audit_id}
              </span>
            </div>
            <div className="mt-1 font-mono text-[12px] text-aether-text break-all">
              {r.capability}
            </div>
            <div className="text-[11.5px] font-mono text-aether-muted break-all">
              {r.scope}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function HistoryList({ entries }: { entries: TelemetryEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="mt-6 text-center text-aether-muted">
        No turns logged yet. Send a message and timing will appear here.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {entries.map((e) => (
        <div
          key={e.turn_id}
          className="rounded-md border border-aether-border bg-aether-bg/50 px-3 py-2"
        >
          <div className="flex items-baseline justify-between gap-2">
            <span className={`text-[11px] font-mono uppercase tracking-wider ${kindClass(e.kind)}`}>
              {e.kind.replace(/_/g, " ")}
            </span>
            <span className="text-[10px] font-mono text-aether-dim">
              {formatLatencyMs(e.latency_ms)}
            </span>
          </div>
          <div className="mt-1 font-mono text-[12px] text-aether-text break-all">
            {e.persona_id}
            {e.provider ? ` · ${e.provider}` : ""}
            {e.tier ? ` · ${e.tier}` : ""}
          </div>
          <div className="text-[11.5px] font-mono text-aether-muted">
            {formatTokens(e.prompt_tokens, e.completion_tokens)}
          </div>
        </div>
      ))}
    </div>
  );
}

function kindClass(kind: string): string {
  switch (kind) {
    case "completed":
      return "text-aether-ok";
    case "denied":
    case "provider_error":
      return "text-aether-err";
    case "needs_upgrade":
    case "draft_only":
      return "text-aether-warn";
    default:
      return "text-aether-muted";
  }
}

function formatLatencyMs(ms: number | undefined): string {
  if (typeof ms !== "number") return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`;
  return `${ms}ms`;
}

function formatTokens(
  prompt: number | undefined,
  completion: number | undefined,
): string {
  const p = typeof prompt === "number" ? prompt : null;
  const c = typeof completion === "number" ? completion : null;
  if (p === null && c === null) return "no token count";
  const total = (p ?? 0) + (c ?? 0);
  return `${p ?? 0} prompt · ${c ?? 0} completion · ${total} total`;
}
