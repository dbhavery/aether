// Trust drawer Memory tab — Memory V2 step 4.
//
// Read + forget + edit surface for the six memory domains. Loads one
// `MemoryListPayload` per domain in parallel on open / refresh; renders
// a lane per domain with per-row forget and edit actions, plus a
// "forget all" lane action. User-sensitive domains (Facts, Artifacts)
// route forget-item / edit through an inline confirmation dialog that
// calls the `*_after_approval` backend variants; Auto domains skip
// straight through the single-call path. Empty lanes render an honest
// `empty_reason` string rather than inventing content.
//
// Design: `docs/MEMORY-V2-ARCHITECTURE.md` §§1, 4, 6.

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  memoryEdit,
  memoryEditAfterApproval,
  memoryForget,
  memoryForgetItem,
  memoryForgetItemAfterApproval,
  memoryList,
} from "../lib/api";
import type {
  MemoryDomain,
  MemoryEditOutcome,
  MemoryForgetOutcome,
  MemoryListItem,
  MemoryListPayload,
  MemoryPrivacyClass,
  MemoryRisk,
} from "../lib/types";
import { MEMORY_DOMAINS } from "../lib/types";

interface Props {
  /** Drawer-open flag from the parent `TrustDrawer`; skips the initial
   * fetch when false so background refreshes don't thrash. */
  open: boolean;
  /** Parent-owned counter that bumps to force a re-load (mirrors the
   * pattern used by the existing Audit / History tabs). */
  refreshKey: number;
}

/** One pending confirmation triggered by a user-sensitive action.
 * Captured so the shared confirmation modal knows what to call after
 * the user approves. `kind` discriminates the backend call. */
type PendingConfirmation =
  | {
      kind: "forget_item";
      domain: MemoryDomain;
      memory_id: string;
      summary: string;
    }
  | {
      kind: "edit";
      domain: MemoryDomain;
      memory_id: string;
      new_content: string;
      summary: string;
    };

const DOMAIN_DESCRIPTIONS: Record<MemoryDomain, string> = {
  session: "Turn-by-turn conversation within one session.",
  durable: "Recent conversation across sessions.",
  facts: "Explicit user-provided facts — user-sensitive.",
  projects: "Named project scopes + associated notes.",
  preferences: "Per-user tuning — timezone, style, defaults.",
  artifacts: "Pinned files, URLs, code snippets — user-sensitive.",
};

/** Format a Rust serde-wire `MemoryRisk` for inline badge display. */
function riskLabel(r: MemoryRisk): string {
  switch (r) {
    case "auto":
      return "auto";
    case "ask":
      return "ask";
    case "deny":
      return "deny";
  }
}

function privacyLabel(p: MemoryPrivacyClass): string {
  return p === "user_sensitive" ? "user-sensitive" : "standard";
}

function formatWallClock(ts_ms: number): string {
  if (!Number.isFinite(ts_ms) || ts_ms <= 0) return "—";
  const d = new Date(ts_ms);
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Short preview of a memory item's content for confirmation copy.
 * Truncates to 60 chars in the middle to keep the dialog compact. */
export function previewForSummary(content: string): string {
  const collapsed = content.replace(/\s+/g, " ").trim();
  if (collapsed.length <= 60) return collapsed;
  return `${collapsed.slice(0, 30)}…${collapsed.slice(-20)}`;
}

/** Helper used by the tests + UI to classify an outcome into a
 * next-action token so the caller can branch without duplicating
 * the `kind` checks. */
export type ForgetActionNext =
  | "refresh"
  | "requires_approval"
  | { error: string }
  | "already_gone";

export function classifyForget(
  outcome: MemoryForgetOutcome,
): ForgetActionNext {
  switch (outcome.kind) {
    case "allowed":
      return "refresh";
    case "requires_approval":
      return "requires_approval";
    case "denied":
      return { error: `Forget denied: ${outcome.reason}` };
    case "not_found":
      return "already_gone";
  }
}

export function classifyEdit(outcome: MemoryEditOutcome): ForgetActionNext {
  switch (outcome.kind) {
    case "allowed":
      return "refresh";
    case "requires_approval":
      return "requires_approval";
    case "denied":
      return { error: `Edit denied: ${outcome.reason}` };
    case "not_found":
      return "already_gone";
  }
}

export function MemoryTab({ open, refreshKey }: Props) {
  const [lanes, setLanes] = useState<
    Partial<Record<MemoryDomain, MemoryListPayload>>
  >({});
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<{
    memory_id: string;
    draft: string;
  } | null>(null);
  const [pending, setPending] = useState<PendingConfirmation | null>(null);
  const [working, setWorking] = useState(false);
  const [localRefresh, setLocalRefresh] = useState(0);

  const refresh = useCallback(() => setLocalRefresh((n) => n + 1), []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setErr(null);
    Promise.all(
      MEMORY_DOMAINS.map((d) =>
        memoryList(d)
          .then((payload) => [d, payload] as const)
          .catch((e) => {
            // One bad domain doesn't kill the others — surface the
            // first error and let the other lanes render what they
            // can.
            throw new Error(`memory_list(${d}): ${String(e)}`);
          }),
      ),
    )
      .then((pairs) => {
        if (cancelled) return;
        const next: Partial<Record<MemoryDomain, MemoryListPayload>> = {};
        for (const [d, p] of pairs) {
          next[d] = p;
        }
        setLanes(next);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open, refreshKey, localRefresh]);

  const handleForgetItem = useCallback(
    async (domain: MemoryDomain, memory_id: string, preview: string) => {
      setErr(null);
      setWorking(true);
      try {
        const outcome = await memoryForgetItem(domain, memory_id);
        const next = classifyForget(outcome);
        if (next === "refresh" || next === "already_gone") {
          refresh();
        } else if (next === "requires_approval") {
          setPending({
            kind: "forget_item",
            domain,
            memory_id,
            summary: previewForSummary(preview),
          });
        } else {
          setErr(next.error);
        }
      } catch (e) {
        setErr(String(e));
      } finally {
        setWorking(false);
      }
    },
    [refresh],
  );

  const handleForgetAll = useCallback(
    async (domain: MemoryDomain) => {
      setErr(null);
      setWorking(true);
      try {
        const outcome = await memoryForget(domain);
        const next = classifyForget(outcome);
        if (next === "refresh" || next === "already_gone") {
          refresh();
        } else if (next === "requires_approval") {
          // forget-all for an Ask domain is a larger surface than
          // forget-item; v1 rejects it with an explanatory error
          // rather than invent a second Ask modal. Users can still
          // forget items one at a time through the per-row action.
          setErr(
            `Forget-all is currently disabled on "${domain}" because this domain requires per-action approval. Use the per-row forget buttons instead.`,
          );
        } else {
          setErr(next.error);
        }
      } catch (e) {
        setErr(String(e));
      } finally {
        setWorking(false);
      }
    },
    [refresh],
  );

  const handleBeginEdit = useCallback((item: MemoryListItem) => {
    setEditing({ memory_id: item.memory_id, draft: item.content });
  }, []);

  const handleCancelEdit = useCallback(() => setEditing(null), []);

  const handleSaveEdit = useCallback(
    async (domain: MemoryDomain, item: MemoryListItem) => {
      if (!editing || editing.memory_id !== item.memory_id) return;
      setErr(null);
      setWorking(true);
      try {
        const outcome = await memoryEdit(
          domain,
          item.memory_id,
          editing.draft,
        );
        const next = classifyEdit(outcome);
        if (next === "refresh") {
          setEditing(null);
          refresh();
        } else if (next === "already_gone") {
          setEditing(null);
          refresh();
        } else if (next === "requires_approval") {
          setPending({
            kind: "edit",
            domain,
            memory_id: item.memory_id,
            new_content: editing.draft,
            summary: previewForSummary(item.content),
          });
        } else {
          setErr(next.error);
        }
      } catch (e) {
        setErr(String(e));
      } finally {
        setWorking(false);
      }
    },
    [editing, refresh],
  );

  const handleApproveConfirmation = useCallback(async () => {
    if (!pending) return;
    setWorking(true);
    try {
      if (pending.kind === "forget_item") {
        const outcome = await memoryForgetItemAfterApproval(
          pending.domain,
          pending.memory_id,
        );
        const next = classifyForget(outcome);
        if (typeof next === "object") {
          setErr(next.error);
        }
      } else {
        const outcome = await memoryEditAfterApproval(
          pending.domain,
          pending.memory_id,
          pending.new_content,
        );
        const next = classifyEdit(outcome);
        if (typeof next === "object") {
          setErr(next.error);
        }
      }
      setPending(null);
      setEditing(null);
      refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setWorking(false);
    }
  }, [pending, refresh]);

  const handleCancelConfirmation = useCallback(() => {
    setPending(null);
  }, []);

  const orderedLanes = useMemo(
    () => MEMORY_DOMAINS.map((d) => [d, lanes[d]] as const),
    [lanes],
  );

  return (
    <div className="flex flex-col gap-4">
      {err && (
        <div
          role="alert"
          className="rounded-md border border-aether-err/50 bg-aether-err/10 px-3 py-2 text-[12px] text-aether-err"
        >
          {err}
        </div>
      )}
      {orderedLanes.map(([domain, payload]) => (
        <DomainLane
          key={domain}
          domain={domain}
          payload={payload}
          editing={editing}
          working={working}
          onForgetItem={handleForgetItem}
          onForgetAll={handleForgetAll}
          onBeginEdit={handleBeginEdit}
          onCancelEdit={handleCancelEdit}
          onSaveEdit={handleSaveEdit}
          onDraftChange={(draft) =>
            setEditing((cur) =>
              cur ? { memory_id: cur.memory_id, draft } : cur,
            )
          }
        />
      ))}
      {pending && (
        <ConfirmationDialog
          pending={pending}
          working={working}
          onApprove={handleApproveConfirmation}
          onCancel={handleCancelConfirmation}
        />
      )}
    </div>
  );
}

function DomainLane({
  domain,
  payload,
  editing,
  working,
  onForgetItem,
  onForgetAll,
  onBeginEdit,
  onCancelEdit,
  onSaveEdit,
  onDraftChange,
}: {
  domain: MemoryDomain;
  payload: MemoryListPayload | undefined;
  editing: { memory_id: string; draft: string } | null;
  working: boolean;
  onForgetItem: (
    domain: MemoryDomain,
    memory_id: string,
    preview: string,
  ) => void;
  onForgetAll: (domain: MemoryDomain) => void;
  onBeginEdit: (item: MemoryListItem) => void;
  onCancelEdit: () => void;
  onSaveEdit: (domain: MemoryDomain, item: MemoryListItem) => void;
  onDraftChange: (draft: string) => void;
}) {
  const items = payload?.items ?? [];
  const empty_reason = payload?.empty_reason ?? null;
  return (
    <section
      aria-label={`Memory domain ${domain}`}
      className="rounded-lg border border-aether-border bg-aether-bg/40 px-4 py-3"
    >
      <header className="flex items-baseline justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            {domain}
          </div>
          <div className="text-[12.5px] text-aether-muted">
            {DOMAIN_DESCRIPTIONS[domain]}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {payload && (
            <>
              <Pill
                label={privacyLabel(payload.privacy_class)}
                tone={
                  payload.privacy_class === "user_sensitive" ? "warn" : "muted"
                }
              />
              <Pill label={`risk · ${riskLabel(payload.risk)}`} tone="muted" />
            </>
          )}
          {items.length > 0 && (
            <button
              type="button"
              onClick={() => onForgetAll(domain)}
              disabled={working}
              className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11px] text-aether-muted hover:border-aether-err hover:text-aether-err disabled:opacity-40"
            >
              Forget all
            </button>
          )}
        </div>
      </header>
      <div className="mt-3 flex flex-col gap-2">
        {items.length === 0 && (
          <p className="rounded-md border border-dashed border-aether-border bg-aether-bg/30 px-3 py-2 text-[12px] text-aether-dim">
            {empty_reason ?? "Nothing in this domain yet."}
          </p>
        )}
        {items.map((item) => {
          const isEditing = editing?.memory_id === item.memory_id;
          return (
            <article
              key={item.memory_id}
              className="rounded-md border border-aether-border bg-aether-bg/50 px-3 py-2"
              aria-label={`Memory item ${item.memory_id}`}
            >
              <div className="flex items-center justify-between gap-2 text-[10.5px] font-mono uppercase tracking-wider text-aether-dim">
                <span>
                  {item.role} · #{item.sequence} · {item.source}
                </span>
                <span>{formatWallClock(item.timestamp_ms)}</span>
              </div>
              {isEditing ? (
                <>
                  <textarea
                    aria-label="Edit memory content"
                    value={editing.draft}
                    onChange={(e) => onDraftChange(e.target.value)}
                    rows={3}
                    className="mt-2 w-full resize-y rounded-md border border-aether-borderHi bg-aether-surface px-2 py-1.5 text-[12.5px] text-aether-text focus:outline-none focus:ring-1 focus:ring-aether-ok"
                  />
                  <div className="mt-2 flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={onCancelEdit}
                      disabled={working}
                      className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11px] text-aether-muted hover:border-aether-borderHi hover:text-aether-text disabled:opacity-40"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={() => onSaveEdit(domain, item)}
                      disabled={working || editing.draft === item.content}
                      className="rounded-md border border-aether-ok bg-aether-ok/15 px-2.5 py-1 text-[11px] text-aether-text hover:bg-aether-ok/25 disabled:opacity-40"
                    >
                      Save
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="mt-1 whitespace-pre-wrap text-[12.5px] text-aether-text">
                    {item.content}
                  </p>
                  <div className="mt-2 flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onBeginEdit(item)}
                      disabled={working}
                      className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11px] text-aether-muted hover:border-aether-borderHi hover:text-aether-text disabled:opacity-40"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        onForgetItem(domain, item.memory_id, item.content)
                      }
                      disabled={working}
                      className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11px] text-aether-muted hover:border-aether-err hover:text-aether-err disabled:opacity-40"
                    >
                      Forget
                    </button>
                  </div>
                </>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}

function Pill({
  label,
  tone,
}: {
  label: string;
  tone: "muted" | "warn";
}) {
  const toneClass =
    tone === "warn"
      ? "border-aether-warn/40 bg-aether-warn/10 text-aether-warn"
      : "border-aether-border bg-aether-bg/40 text-aether-muted";
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider ${toneClass}`}
    >
      {label}
    </span>
  );
}

function ConfirmationDialog({
  pending,
  working,
  onApprove,
  onCancel,
}: {
  pending: PendingConfirmation;
  working: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  const title =
    pending.kind === "forget_item"
      ? "Forget this item?"
      : "Save this edit?";
  const body =
    pending.kind === "forget_item"
      ? `This is a user-sensitive action on the "${pending.domain}" domain. The item will be permanently removed from your memory.`
      : `This is a user-sensitive action on the "${pending.domain}" domain. The item's text will be replaced.`;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="memory-confirm-title"
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fadeIn"
    >
      <div className="neu-raised mx-6 w-full max-w-md rounded-xl p-6">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-aether-warn">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-aether-warn animate-pulseDot" />
          Approval requested
        </div>
        <h2
          id="memory-confirm-title"
          className="mt-2 text-[15px] font-medium text-aether-text"
        >
          {title}
        </h2>
        <p className="mt-3 text-[12.5px] text-aether-muted">{body}</p>
        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[12px]">
          <dt className="text-aether-dim">Item</dt>
          <dd className="font-mono text-[11px] text-aether-muted break-all">
            {pending.memory_id}
          </dd>
          <dt className="text-aether-dim">Preview</dt>
          <dd className="font-mono text-[11.5px] text-aether-text break-words">
            {pending.summary || "(empty)"}
          </dd>
        </dl>
        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={working}
            className="rounded-md border border-aether-border bg-transparent px-4 py-2 text-[12.5px] text-aether-muted hover:border-aether-borderHi hover:text-aether-text disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onApprove}
            disabled={working}
            className="rounded-md border border-aether-warn bg-aether-warn/15 px-4 py-2 text-[12.5px] text-aether-text hover:bg-aether-warn/25 disabled:opacity-40"
          >
            {working ? "Working…" : "Approve once"}
          </button>
        </div>
      </div>
    </div>
  );
}
