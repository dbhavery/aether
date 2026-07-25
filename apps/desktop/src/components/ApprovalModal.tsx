import { useState } from "react";

import {
  APPROVAL_RADIO_OPTIONS,
  type ApprovalPayload,
  type UserChoice,
} from "../lib/types";

interface Props {
  payload: ApprovalPayload;
  working: boolean;
  /**
   * Wave 14 (T1.3 §5.3) — single resolve callback that takes the
   * full `UserChoice` instead of separate Approve / Reject hooks.
   * The modal renders the four-option radio + a separate Decline
   * button; both paths funnel into this one callback.
   */
  onResolve: (choice: UserChoice) => void;
}

type RadioId = (typeof APPROVAL_RADIO_OPTIONS)[number]["id"];
const DEFAULT_RADIO_ID: RadioId = "allow_once";

/**
 * Clear, specific approval UI. Per ARCHITECTURE.md
 * (the five permission layers), the prompt tells the user what,
 * why, what scope, and what happens if they say no.
 *
 * Wave 14 (T1.3 §5.3) — the user picks the temporal scope of their
 * approval via a radio group with four fixed-order options:
 *
 *   1. allow_once   → `UserChoice::Allow`            (default)
 *   2. allow_task   → `UserChoice::AllowTask`
 *   3. allow_session → `UserChoice::AllowSession`
 *   4. defer_draft  → `UserChoice::DeferToDraft`
 *
 * Plus a separate Decline button outside the radio group → emits
 * `UserChoice::Deny`. Decline is the safety-default escape and is
 * NOT a scope choice, so it does not live inside the radio cluster.
 *
 * V2 affordance state (Wave 15) — gating now lives behind the
 * payload's `task_id_present` and `side_effecting` flags per design
 * §5.1:
 *
 *   - `allow_task` renders only when `payload.task_id_present` —
 *     selecting it without a task lineage would be a no-op (the grant
 *     scope falls back to per-action), so the option is hidden rather
 *     than offered as a confusing choice.
 *   - `defer_draft` renders only when `payload.side_effecting` —
 *     read-only capabilities cannot meaningfully be "drafted" because
 *     there is no pending mutation to defer.
 *   - `allow_once` and `allow_session` always render. `allow_once`
 *     is the safe default whenever the previously-selected option is
 *     gated out for a particular payload.
 *
 * The Decline button stays outside the radio group; it is the
 * safety-default escape regardless of payload shape.
 */
export function ApprovalModal({ payload, working, onResolve }: Props) {
  const visibleOptions = APPROVAL_RADIO_OPTIONS.filter((opt) => {
    if (opt.id === "allow_task") return payload.task_id_present;
    if (opt.id === "defer_draft") return payload.side_effecting;
    return true;
  });
  const initialSelected: RadioId = visibleOptions.some(
    (o) => o.id === DEFAULT_RADIO_ID,
  )
    ? DEFAULT_RADIO_ID
    : (visibleOptions[0]?.id ?? DEFAULT_RADIO_ID);
  const [selected, setSelected] = useState<RadioId>(initialSelected);

  const onApproveSubmit = () => {
    const opt = visibleOptions.find((o) => o.id === selected);
    if (!opt) return;
    onResolve(opt.choice);
  };

  const onDecline = () => {
    onResolve({ kind: "deny" });
  };

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
          Companion would like permission to continue.
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
          {payload.risk_hint} If you decline, Companion will stop and let you know
          — nothing else will happen.
        </p>

        <fieldset
          className="mt-5"
          aria-labelledby="approval-radio-legend"
          disabled={working}
        >
          <legend
            id="approval-radio-legend"
            className="mb-2 text-[11px] uppercase tracking-[0.16em] text-aether-dim"
          >
            How long should this approval last?
          </legend>
          <div
            role="radiogroup"
            aria-labelledby="approval-radio-legend"
            className="flex flex-col gap-1.5"
          >
            {visibleOptions.map((opt) => {
              const inputId = `approval-radio-${opt.id}`;
              const isSelected = selected === opt.id;
              return (
                <label
                  key={opt.id}
                  htmlFor={inputId}
                  className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-[12.5px] transition-colors ${
                    isSelected
                      ? "border-aether-ok bg-aether-ok/10 text-aether-text"
                      : "border-aether-border bg-transparent text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
                  }`}
                >
                  <input
                    id={inputId}
                    type="radio"
                    name="approval-scope"
                    value={opt.id}
                    checked={isSelected}
                    onChange={() => setSelected(opt.id)}
                    disabled={working}
                    className="h-3.5 w-3.5 accent-aether-ok"
                  />
                  <span>{opt.label}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onDecline}
            disabled={working}
            className="rounded-md border border-aether-border bg-transparent px-4 py-2 text-[12.5px] text-aether-muted transition-colors hover:border-aether-borderHi hover:text-aether-text disabled:opacity-40"
          >
            Decline
          </button>
          <button
            type="button"
            onClick={onApproveSubmit}
            disabled={working}
            className="rounded-md border border-aether-ok bg-aether-ok/15 px-4 py-2 text-[12.5px] text-aether-text transition-colors hover:bg-aether-ok/25 disabled:opacity-40"
          >
            {working ? "Working…" : "Approve"}
          </button>
        </div>
      </div>
    </div>
  );
}
