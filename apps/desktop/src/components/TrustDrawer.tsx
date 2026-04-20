import { useEffect, useState } from "react";

import { auditRecent } from "../lib/api";
import type { AuditDecisionLabel, TrustAuditRow } from "../lib/types";

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
  const [rows, setRows] = useState<TrustAuditRow[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    auditRecent(100)
      .then((r) => {
        if (!cancelled) setRows(r);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open, refreshKey]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-aether-border bg-aether-surface shadow-neuRaised animate-fadeIn"
      role="complementary"
      aria-label="Trust centre — audit log"
    >
      <div className="flex items-center justify-between border-b border-aether-border px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Trust · audit
          </div>
          <div className="text-[13px] text-aether-text">
            What Aether decided, in order
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
      <div className="allow-select flex-1 overflow-y-auto px-5 py-4 text-[12.5px]">
        {err && <div className="text-aether-err">{err}</div>}
        {!err && rows.length === 0 && (
          <div className="mt-6 text-center text-aether-muted">
            No decisions yet. Each turn you send here leaves a sealed row in
            the audit log.
          </div>
        )}
        <div className="flex flex-col gap-2">
          {rows.map((r) => {
            const meta = DECISION_META[r.decision];
            return (
              <div
                key={r.audit_id}
                className="rounded-md border border-aether-border bg-aether-bg/50 px-3 py-2"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className={`text-[11px] font-mono uppercase tracking-wider ${meta.color}`}>
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
      </div>
      <div className="border-t border-aether-border px-5 py-3 text-[11px] text-aether-muted">
        Every decision is sealed in an append-only hash-chained log. Export
        and verify UX is on the roadmap.
      </div>
    </div>
  );
}
