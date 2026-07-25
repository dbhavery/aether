import { useEffect, useRef, useState } from "react";

import {
  auditRecent,
  getPresenceConfig,
  onAttention,
  presenceRecentHistory,
  telemetryClear,
  telemetryRecent,
  type TelemetryEntry,
} from "../lib/api";
import {
  isMediaTurn,
  MEDIA_TURN_KINDS,
  visionRouteSummary,
} from "../lib/mediaTurns";
import { speechRouteSummary } from "../lib/speechProviders";
import { isVoiceTurn, VOICE_TURN_KINDS } from "../lib/voiceTurns";
import { truncateMiddleForDisplay } from "../lib/displayString";
import { MemoryTab } from "./MemoryTab";
import { RetrievalTab } from "./RetrievalTab";
import type {
  AuditDecisionLabel,
  PresenceConfig,
  PresenceHistoryEntry,
  TrustAuditRow,
  UserAttentionLabel,
} from "../lib/types";

/** Max characters of a model id we render inline on the Trust drawer
 * body line before truncating with an ellipsis. The full id is kept
 * in the row's `title` attribute so it stays recoverable on hover. */
const MODEL_ID_DISPLAY_MAX = 28;

type Tab = "audit" | "history" | "memory" | "retrieval";
type HistoryFilter = "all" | "media" | "voice" | "presence";

/** One row of the interleaved History list. Turn telemetry and
 * presence transitions share the same timeline so the user can see
 * "you stepped away, then two minutes later sent a message" as one
 * story. Narrowed via `kind === ...` at the render site. */
type HistoryRow =
  | { kind: "telemetry"; entry: TelemetryEntry; at_ms: number }
  | { kind: "presence"; entry: PresenceHistoryEntry; at_ms: number };

// MEDIA_TURN_KINDS / isMediaTurn moved to ../lib/mediaTurns so the
// constant can be unit-tested without dragging React in. Re-export
// here for back-compat with any external consumers that imported from
// this module before the move. VOICE_TURN_KINDS and isVoiceTurn live
// in ../lib/voiceTurns; re-exported here for symmetry.
export { isMediaTurn, MEDIA_TURN_KINDS, isVoiceTurn, VOICE_TURN_KINDS };

interface Props {
  open: boolean;
  refreshKey: number;
  onClose: () => void;
  /** Tab to focus when the drawer opens. Defaults to `"audit"` to
   * preserve v0 behaviour. Used by the header Memory button to jump
   * straight to the Memory tab — the consolidated entry point for
   * anything the user wants to see/forget/edit in memory (Memory V2
   * step 4 is the durable UI; the prior MemoryDrawer was retired in
   * Run 5). Re-applied on every `open: false → true` transition so a
   * user can go audit → close → Memory button → opens on Memory. */
  initialTab?: Tab;
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
 * session generated. Answers "what did Companion just decide, and why do I
 * trust that?" per ARCHITECTURE.md (information architecture —
 * "action history is always reviewable").
 */
export function TrustDrawer({ open, refreshKey, onClose, initialTab }: Props) {
  const [tab, setTab] = useState<Tab>(initialTab ?? "audit");
  const drawerRef = useRef<HTMLDivElement>(null);
  // Remember the element that had focus when the drawer opened so we
  // can restore it on close (canonical modal-dialog pattern). Without
  // restoration, closing the drawer leaves focus on `document.body`,
  // which makes Ctrl+K (focus chat input) the only way back in.
  const previousFocusRef = useRef<HTMLElement | null>(null);

  // Re-apply `initialTab` on each open transition so the header's
  // Memory button lands on Memory even after the user previously
  // switched tabs and closed the drawer. Only fires when `open`
  // actually transitions; pure re-renders don't clobber the user's
  // current-session tab selection.
  useEffect(() => {
    if (open && initialTab) {
      setTab(initialTab);
    }
  }, [open, initialTab]);
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>("all");
  const [rows, setRows] = useState<TrustAuditRow[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryEntry[]>([]);
  const [presenceHistory, setPresenceHistory] = useState<PresenceHistoryEntry[]>(
    [],
  );
  const [presenceCfg, setPresenceCfg] = useState<PresenceConfig | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setErr(null);
    Promise.all([
      auditRecent(100),
      telemetryRecent(50),
      presenceRecentHistory(50),
      getPresenceConfig(),
    ])
      .then(([a, t, p, cfg]) => {
        if (cancelled) return;
        setRows(a);
        setTelemetry(t);
        setPresenceHistory(p);
        setPresenceCfg(cfg);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open, refreshKey]);

  // Live-update presence history while the drawer is open. New
  // transitions are pushed via the `presence:attention` event bus from
  // the shell's poll loop. Unsubscribe on close or unmount.
  useEffect(() => {
    if (!open) return;
    let unlisten: (() => void) | null = null;
    onAttention((payload) => {
      setPresenceHistory((prev) => [payload, ...prev].slice(0, 50));
    })
      .then((u) => {
        unlisten = u;
      })
      .catch((e) => {
        setErr(String(e));
      });
    return () => {
      if (unlisten) unlisten();
    };
  }, [open]);

  // Phase 6 UX audit Bug 5.2: keystrokes typed while the Trust drawer
  // was open silently accumulated in the underlying chat input — a
  // trust violation in a messaging UI. Fix is the canonical
  // accessibility pattern for a modal-style surface: capture the
  // previously-focused element on open, pull focus into the drawer,
  // trap Tab inside the drawer subtree, swallow stray keystrokes
  // whose target is outside the drawer, restore previous focus on
  // close, and Escape closes.
  useEffect(() => {
    if (!open) return;
    previousFocusRef.current =
      (document.activeElement as HTMLElement | null) ?? null;
    // Blur the chat input (or whatever owned focus) so accidental
    // keystrokes between the open transition and the user's first
    // click in the drawer do not land in the chat composer.
    previousFocusRef.current?.blur?.();
    // Move focus into the drawer. Targeting the wrapper (which is
    // tabIndex=-1) keeps screen-reader announcement scoped to
    // aria-label="Trust centre" rather than reading whichever
    // element happens to be first in tab order.
    const wrap = drawerRef.current;
    if (wrap) wrap.focus();

    const focusableSelector =
      'a[href], area[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), iframe, object, embed, [tabindex="0"], [contenteditable]';

    const handleKeyDown = (e: KeyboardEvent) => {
      const root = drawerRef.current;
      if (!root) return;
      const target = e.target as Node | null;
      const insideDrawer = !!target && root.contains(target);

      if (e.key === "Escape" && insideDrawer) {
        e.preventDefault();
        onClose();
        return;
      }

      // Tab: trap inside the drawer subtree.
      if (e.key === "Tab" && insideDrawer) {
        const focusables = Array.from(
          root.querySelectorAll<HTMLElement>(focusableSelector),
        ).filter((el) => !el.hasAttribute("disabled"));
        if (focusables.length === 0) {
          e.preventDefault();
          return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
        return;
      }

      // Stray keystroke whose target is outside the drawer — could be
      // a residual focus on the chat input. Swallow so it cannot
      // accumulate as text in a hidden composer. Modifier-only
      // shortcuts (Ctrl+K, Cmd+K, etc.) pass through so global
      // hotkeys still work.
      if (!insideDrawer && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      // Restore focus to whatever owned it before the drawer opened.
      // Guard against the previous element being detached (e.g. a
      // re-rendered chat input) by no-op'ing if focus would land on
      // a disconnected node.
      const prev = previousFocusRef.current;
      if (prev && prev.isConnected) {
        prev.focus?.();
      }
    };
  }, [open, onClose]);

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
      ref={drawerRef}
      tabIndex={-1}
      data-testid="trust-drawer-root"
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-aether-border bg-aether-surface shadow-neuRaised animate-fadeIn focus:outline-none"
      role="dialog"
      aria-modal="true"
      aria-label="Trust centre"
    >
      <div className="flex items-center justify-between border-b border-aether-border px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Trust · {tab}
          </div>
          <div className="text-[13px] text-aether-text">
            {tab === "audit"
              ? "What Companion decided, in order"
              : tab === "memory"
                ? "What Companion remembers, by domain"
                : tab === "retrieval"
                  ? "Whether Companion can find what it remembers"
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
          active={tab === "memory"}
          onClick={() => setTab("memory")}
          label="Memory"
        />
        <TabButton
          active={tab === "retrieval"}
          onClick={() => setTab("retrieval")}
          label="Retrieval"
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
        {!err && tab === "memory" && (
          <MemoryTab open={open} refreshKey={refreshKey} />
        )}
        {!err && tab === "retrieval" && (
          <RetrievalTab refreshKey={refreshKey} />
        )}
        {!err && tab === "history" && (
          <HistoryView
            entries={telemetry}
            presence={
              presenceCfg?.history_in_trust_drawer === false
                ? []
                : presenceHistory
            }
            filter={historyFilter}
            onFilterChange={setHistoryFilter}
            presenceHidden={presenceCfg?.history_in_trust_drawer === false}
          />
        )}
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-aether-border px-5 py-3 text-[11px] text-aether-muted">
        {tab === "audit" && (
          <span>
            Every decision is sealed in an append-only hash-chained log.
          </span>
        )}
        {tab === "memory" && (
          <span>
            Forget and edit land immediately. User-sensitive domains ask for
            confirmation first.
          </span>
        )}
        {tab === "retrieval" && (
          <span>
            Retrieval is auxiliary. Turns still flow when it&rsquo;s off; only
            the &ldquo;remember what we said&rdquo; quality drops.
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

/**
 * ADR-0009 §Decision 6: schema version constants used by `AuditList`
 * to branch between legacy and v2 rendering. Module-level so the
 * vitest can pin them rather than inlining magic numbers in tests.
 */
export const AUDIT_SCHEMA_VERSION_V1 = 1;
export const AUDIT_SCHEMA_VERSION_V2 = 2;

/**
 * One audit row.
 *
 * ## Layout, by schema_version
 *
 * **v1 (legacy, pre-2026-04-25)** — capability + scope as before, plus
 * a small "pre-ADR-0009 schema" badge. v1 rows had no
 * `original_utterance` field, so the user-phrasing surface stays
 * absent rather than rendered as an empty quote.
 *
 * **v2 (ADR-0009)** — the user's typed text is the headline. The
 * capability + scope drop to a secondary line. A details/summary
 * disclosure surfaces "what Companion also saw" — currently just the
 * retrieval-block summary (`N memories from {domains}`); the full
 * model-input string is intentionally NOT rendered (Open Item #3,
 * deferred to a future ADR per `DECISIONS_LOG.md` D-001).
 *
 * Patterns referenced: GitHub PR review timeline (single dominant
 * line + collapsed metadata) and Linear's audit log (timestamp +
 * actor minimal). Both keep dense logs scannable by giving every
 * row exactly one strong signal.
 */
function AuditRow({ row }: { row: TrustAuditRow }) {
  const meta = DECISION_META[row.decision];
  const isV2 = row.schema_version >= AUDIT_SCHEMA_VERSION_V2;
  const utterance = row.original_utterance?.trim();
  const provenance = row.retrieval_provenance;
  const showUserHeadline = isV2 && utterance && utterance.length > 0;

  return (
    <div
      data-testid={`audit-row-${row.audit_id}`}
      data-schema-version={row.schema_version}
      className="rounded-md border border-aether-border bg-aether-bg/50 px-3 py-2"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span
          className={`text-[11px] font-mono uppercase tracking-wider ${meta.color}`}
        >
          {meta.label}
        </span>
        <div className="flex items-center gap-2">
          {!isV2 && (
            <span
              data-testid="schema-v1-badge"
              title="Pre-2026-04-25 audit schema. The user's exact phrasing is not recorded for this row; the row may include retrieval context that was prepended to the model input."
              className="rounded-full border border-aether-warn/40 bg-aether-warn/5 px-1.5 py-0.5 text-[10px] text-aether-warn"
            >
              pre-ADR-0009
            </span>
          )}
          <span className="text-[10px] font-mono text-aether-dim">
            {row.audit_id}
          </span>
        </div>
      </div>

      {showUserHeadline ? (
        <>
          <div
            data-testid="audit-user-utterance"
            className="mt-1.5 text-[12.5px] text-aether-text break-words"
          >
            <span className="text-aether-dim mr-1.5">&ldquo;</span>
            {utterance}
            <span className="text-aether-dim ml-1">&rdquo;</span>
          </div>
          <div className="mt-1 text-[11px] font-mono text-aether-muted break-all">
            {row.capability}
            {row.scope ? <span className="text-aether-dim"> · {row.scope}</span> : null}
          </div>
        </>
      ) : (
        <>
          <div className="mt-1 font-mono text-[12px] text-aether-text break-all">
            {row.capability}
          </div>
          <div className="text-[11.5px] font-mono text-aether-muted break-all">
            {row.scope}
          </div>
        </>
      )}

      {isV2 && provenance && (
        provenance.block_present && provenance.hits.length > 0 ? (
          <details
            data-testid="audit-model-saw"
            className="mt-1.5 group"
          >
            <summary className="cursor-pointer text-[11px] text-aether-muted hover:text-aether-text select-none">
              {`Companion also saw ${provenance.hits.length} memor${
                provenance.hits.length === 1 ? "y" : "ies"
              } from ${formatDomains(provenance.hits)}`}
            </summary>
            <ul className="mt-1.5 ml-4 space-y-0.5 text-[10.5px] font-mono text-aether-muted">
              {provenance.hits.map((h) => (
                <li key={h.memory_id}>
                  <span className="text-aether-dim">{h.domain}</span>
                  {" · "}
                  <span title={h.memory_id}>
                    {truncateMiddleForDisplay(h.memory_id, 24)}
                  </span>
                  {" · "}
                  <span className="text-aether-dim">
                    score {h.score.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        ) : (
          // Phase 6 UX audit Bug 5.3 / AUDIT_ROW_UI_RESEARCH §2.3:
          // when retrieval ran but matched nothing, do NOT render the
          // <details>/<summary> chevron. The chevron suggests "click
          // to expand" but there is nothing to expand, so the click
          // is wasted and the affordance lies. Render the same
          // sentence inline as plain text instead.
          <div
            data-testid="audit-model-saw-empty"
            className="mt-1.5 text-[11px] text-aether-muted select-none"
          >
            Companion ran retrieval; nothing matched
          </div>
        )
      )}
    </div>
  );
}

/** Compact "(2 domains: durable, facts)" rendering for the
 * provenance summary. Deduplicates and sorts so the line is stable
 * across renders. */
function formatDomains(hits: { domain: string }[]): string {
  const uniq = Array.from(new Set(hits.map((h) => h.domain))).sort();
  if (uniq.length === 0) return "no domain";
  if (uniq.length === 1) return uniq[0];
  return uniq.join(", ");
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
      {rows.map((r) => (
        <AuditRow key={r.audit_id} row={r} />
      ))}
    </div>
  );
}

// Exported for the vitest in TrustDrawer.test.tsx — keep the
// component itself private to this module and only widen the test
// surface intentionally.
export { AuditRow };

function HistoryView({
  entries,
  presence,
  filter,
  onFilterChange,
  presenceHidden,
}: {
  entries: TelemetryEntry[];
  presence: PresenceHistoryEntry[];
  filter: HistoryFilter;
  onFilterChange: (f: HistoryFilter) => void;
  presenceHidden: boolean;
}) {
  // Coalesce adjacent presence transitions through a bucket the user
  // probably doesn't care about individually — see `coalescePresence`
  // below. Trust-drawer history should read as "what happened",
  // not a debug log.
  const coalescedPresence = coalescePresence(presence);

  // Build the interleaved list. Sort by timestamp descending so the
  // newest row is at the top, matching the existing turn-history
  // ordering.
  const telemetryRows: HistoryRow[] = entries.map((e) => ({
    kind: "telemetry" as const,
    entry: e,
    at_ms: e.timestamp_ms,
  }));
  const presenceRows: HistoryRow[] = coalescedPresence.map((p) => ({
    kind: "presence" as const,
    entry: p,
    at_ms: p.at_ms,
  }));
  const allRows: HistoryRow[] = [...telemetryRows, ...presenceRows].sort(
    (a, b) => b.at_ms - a.at_ms,
  );

  const filteredRows: HistoryRow[] =
    filter === "media"
      ? allRows.filter(
          (r) => r.kind === "telemetry" && isMediaTurn(r.entry.kind),
        )
      : filter === "voice"
        ? allRows.filter(
            (r) => r.kind === "telemetry" && isVoiceTurn(r.entry.kind),
          )
        : filter === "presence"
          ? allRows.filter((r) => r.kind === "presence")
          : allRows;

  const mediaCount = entries.filter((e) => isMediaTurn(e.kind)).length;
  const voiceCount = entries.filter((e) => isVoiceTurn(e.kind)).length;
  const presenceCount = coalescedPresence.length;

  return (
    <div className="flex flex-col gap-3">
      <div
        role="radiogroup"
        aria-label="History filter"
        className="flex flex-wrap gap-2"
      >
        <FilterPill
          active={filter === "all"}
          onClick={() => onFilterChange("all")}
          label={`All (${allRows.length})`}
        />
        <FilterPill
          active={filter === "media"}
          onClick={() => onFilterChange("media")}
          label={`Media only (${mediaCount})`}
        />
        <FilterPill
          active={filter === "voice"}
          onClick={() => onFilterChange("voice")}
          label={`Voice only (${voiceCount})`}
        />
        <FilterPill
          active={filter === "presence"}
          onClick={() => onFilterChange("presence")}
          label={`Presence (${presenceCount})`}
        />
      </div>
      {presenceHidden && (
        <p className="text-[11px] text-aether-dim">
          Presence rows are hidden by the &ldquo;Show presence in Trust
          history&rdquo; toggle in Settings.
        </p>
      )}
      <HistoryList rows={filteredRows} filterApplied={filter} />
    </div>
  );
}

/**
 * Coalesce a rapid sequence of presence transitions into the single
 * net move. A user tapping the mouse in an Idle state might briefly
 * flip Idle → Active → Idle inside the same second; surfacing the
 * three-row noise drowns out more interesting rows. Rule: a pair of
 * transitions A → B → A within `COALESCE_WINDOW_MS` of each other
 * collapses to nothing. Longer-lived transitions survive.
 *
 * Input is newest-first (from the backend's `presence_recent_history`
 * command), so we reverse, pass forward, then reverse again.
 *
 * Presence V1 step 3.
 */
const COALESCE_WINDOW_MS = 5_000;
export function coalescePresence(
  rows: PresenceHistoryEntry[],
): PresenceHistoryEntry[] {
  if (rows.length < 2) return rows;
  // Process oldest-first so `to` matches the next row's `from`.
  const oldestFirst = [...rows].reverse();
  const out: PresenceHistoryEntry[] = [];
  for (const ev of oldestFirst) {
    const prev = out[out.length - 1];
    // A → B → A within window → drop both prev and ev.
    if (
      prev &&
      prev.to === ev.from &&
      prev.from === ev.to &&
      ev.at_ms - prev.at_ms < COALESCE_WINDOW_MS
    ) {
      out.pop();
      continue;
    }
    out.push(ev);
  }
  return out.reverse();
}

function FilterPill({
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
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-[11px] transition-colors ${
        active
          ? "border border-aether-borderHi bg-aether-elevated text-aether-text"
          : "border border-aether-border bg-transparent text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
      }`}
    >
      {label}
    </button>
  );
}

function HistoryList({
  rows,
  filterApplied,
}: {
  rows: HistoryRow[];
  filterApplied?: HistoryFilter | false;
}) {
  if (rows.length === 0) {
    const empty =
      filterApplied === "media"
        ? "No media turns yet. Open the Camera or Screen panel and analyze a frame."
        : filterApplied === "voice"
          ? "No voice turns yet. Open the Voice panel and record an utterance."
          : filterApplied === "presence"
            ? "No presence transitions yet. Step away for a moment and come back."
            : "No turns logged yet. Send a message and timing will appear here.";
    return <div className="mt-6 text-center text-aether-muted">{empty}</div>;
  }
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r) => {
        if (r.kind === "presence") {
          return (
            <PresenceHistoryRow key={`presence-${r.entry.at_ms}`} entry={r.entry} />
          );
        }
        const e = r.entry;
        // Voice route summary takes priority when the provider is a
        // known speech adapter; otherwise fall back to vision. The
        // two routes are disjoint because their provider id sets are.
        const speechBadge = speechRouteSummary(e.provider, e.model);
        const visionBadge = speechBadge
          ? null
          : visionRouteSummary(e.provider, e.model);
        const routeTitle = speechBadge
          ? speechRouteTitle(e.provider, e.model)
          : visionBadge
            ? visionRouteTitle(e.provider, e.model)
            : null;
        const routeLabel = speechBadge ?? visionBadge;
        return (
          <div
            key={e.turn_id}
            className="rounded-md border border-aether-border bg-aether-bg/50 px-3 py-2"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span
                className={`text-[11px] font-mono uppercase tracking-wider ${kindClass(e.kind)}`}
              >
                {e.kind.replace(/_/g, " ")}
              </span>
              <div className="flex items-center gap-2">
                {routeLabel && (
                  <span
                    className="rounded-full border border-aether-ok/40 bg-aether-ok/5 px-1.5 py-0.5 text-[10px] text-aether-ok"
                    title={routeTitle ?? undefined}
                  >
                    {routeLabel}
                  </span>
                )}
                <span className="text-[10px] font-mono text-aether-dim">
                  {formatLatencyMs(e.latency_ms)}
                </span>
              </div>
            </div>
            <div className="mt-1 font-mono text-[12px] text-aether-text break-all">
              {e.persona_id}
              {e.provider ? ` · ${e.provider}` : ""}
              {e.model ? (
                <>
                  {" · "}
                  <span title={e.model}>
                    {truncateMiddleForDisplay(e.model, MODEL_ID_DISPLAY_MAX)}
                  </span>
                </>
              ) : null}
              {!e.model && e.tier ? ` · ${e.tier}` : ""}
            </div>
            <div className="text-[11.5px] font-mono text-aether-muted">
              {formatTokens(e.prompt_tokens, e.completion_tokens)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Single presence-transition row. Deliberately muted — presence is
 * context, not action. "You became Idle" doesn't need the same
 * visual weight as "Companion routed a turn to a model that took 3.2 s".
 *
 * Presence V1 step 3.
 */
function PresenceHistoryRow({ entry }: { entry: PresenceHistoryEntry }) {
  const arrow = `${labelForAttention(entry.from)} → ${labelForAttention(entry.to)}`;
  const glyph = entry.to === "away" ? "◦" : entry.to === "idle" ? "·" : "●";
  return (
    <div
      className="rounded-md border border-aether-border/60 bg-aether-bg/30 px-3 py-2"
      title={`Idle ${entry.idle_seconds}s at transition`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-mono uppercase tracking-wider text-aether-dim">
          <span aria-hidden className="mr-1.5 text-aether-muted">
            {glyph}
          </span>
          presence
        </span>
        <span className="text-[10px] font-mono text-aether-dim">
          {formatIdleSeconds(entry.idle_seconds)}
        </span>
      </div>
      <div className="mt-0.5 font-mono text-[12px] text-aether-muted">
        {arrow}
      </div>
    </div>
  );
}

function labelForAttention(s: UserAttentionLabel): string {
  switch (s) {
    case "active":
      return "Active";
    case "idle":
      return "Idle";
    case "away":
      return "Away";
  }
}

function formatIdleSeconds(s: number): string {
  if (s < 60) return `${s}s idle`;
  if (s < 3600) return `${Math.floor(s / 60)}m idle`;
  return `${Math.floor(s / 3600)}h idle`;
}

/**
 * Tooltip copy for the speech-route badge. Mirrors `visionRouteTitle`.
 */
function speechRouteTitle(
  provider: string | null | undefined,
  model: string | null | undefined,
): string {
  const p = provider ?? "speech provider";
  const trimmed = typeof model === "string" ? model.trim() : "";
  return trimmed.length > 0
    ? `Served by ${p} (${trimmed})`
    : `Served by ${p}`;
}

function kindClass(kind: string): string {
  switch (kind) {
    case "completed":
    case "frame_analyzed":
    case "utterance_transcribed":
      return "text-aether-ok";
    case "denied":
    case "provider_error":
    case "frame_blocked":
    case "frame_invalid":
    case "permission_denied":
    case "utterance_blocked":
    case "utterance_invalid":
    case "mic_permission_denied":
      return "text-aether-err";
    case "needs_upgrade":
    case "draft_only":
    case "permission_ask":
    case "mic_permission_ask":
      return "text-aether-warn";
    default:
      return "text-aether-muted";
  }
}

/**
 * Tooltip copy for the vision-route badge. Mentions the model when
 * we know it, the provider id either way. Plain English so the
 * Trust drawer's hover surface still reads coherently when the
 * adapter doesn't expose a model.
 */
function visionRouteTitle(
  provider: string | null | undefined,
  model: string | null | undefined,
): string {
  const p = provider ?? "vision provider";
  const trimmed = typeof model === "string" ? model.trim() : "";
  return trimmed.length > 0
    ? `Served by ${p} (${trimmed})`
    : `Served by ${p}`;
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
