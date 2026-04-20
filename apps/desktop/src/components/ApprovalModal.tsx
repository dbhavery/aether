import type { ApprovalPayload } from "../lib/types";

interface Props {
  payload: ApprovalPayload;
  working: boolean;
  onApprove: () => void;
  onReject: () => void;
}

/**
 * Clear, specific approval UI. Per planning/12_permissions_autonomy §"The
 * five permission layers", the prompt tells the user what, why, what scope,
 * and what happens if they say no. Session-only grant for v0.
 */
export function ApprovalModal({ payload, working, onApprove, onReject }: Props) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="approval-title"
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fadeIn"
    >
      <div className="neu-raised mx-6 w-full max-w-md rounded-xl p-6">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-aether-warn">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-aether-warn animate-pulseDot" />
          Approval requested
        </div>
        <h2
          id="approval-title"
          className="mt-2 text-[15px] font-medium text-aether-text"
        >
          Aether would like permission to continue.
        </h2>

        <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-[12.5px]">
          <dt className="text-aether-dim">Action</dt>
          <dd className="font-mono text-aether-text break-all">
            {payload.capability}
          </dd>

          <dt className="text-aether-dim">Scope</dt>
          <dd className="font-mono text-aether-text break-all">
            {payload.scope}
          </dd>

          <dt className="text-aether-dim">Reason</dt>
          <dd className="font-mono text-aether-muted">{payload.reason}</dd>

          <dt className="text-aether-dim">Ticket</dt>
          <dd className="font-mono text-[11px] text-aether-dim">
            {payload.ticket_id}
          </dd>
        </dl>

        <p className="mt-4 rounded-md border border-aether-border bg-aether-bg/60 px-3 py-2 text-[11.5px] leading-relaxed text-aether-muted">
          {payload.risk_hint} If you decline, Aether will stop and let you know
          — nothing else will happen.
        </p>

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onReject}
            disabled={working}
            className="rounded-md border border-aether-border bg-transparent px-4 py-2 text-[12.5px] text-aether-muted transition-colors hover:border-aether-borderHi hover:text-aether-text disabled:opacity-40"
          >
            Decline
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={working}
            className="rounded-md border border-aether-ok bg-aether-ok/15 px-4 py-2 text-[12.5px] text-aether-text transition-colors hover:bg-aether-ok/25 disabled:opacity-40"
          >
            {working ? "Working…" : "Approve once"}
          </button>
        </div>
      </div>
    </div>
  );
}
