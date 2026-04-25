import { useEffect, useState } from "react";

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
 * session generated. Answers "what did Aether just decide, and why do I
 * trust that?" per planning/05_ux_principles §Information architecture
 * ("Action history is always reviewable").
 */
export function TrustDrawer({ open, refreshKey, onClose, initialTab }: Props) {
  const [tab, setTab] = useState<Tab>(initialTab ?? "audit");

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
              : tab === "memory"
                ? "What Aether remembers, by domain"
                : tab === "retrieval"
                  ? "Whether Aether can find what it remembers"
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
 * visual weight as "Aether routed a turn to a model that took 3.2 s".
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
