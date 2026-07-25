import { useEffect, useState } from "react";
import {
  backfillCount,
  backfillStatus,
  cancelBackfill,
  embeddingsReadiness,
  getMemoryConfig,
  getTier,
  onBackfillDone,
  onBackfillProgress,
  onTierChanged,
  startBackfill,
  type BackfillProgress,
} from "../lib/api";
import type {
  MemoryConfig,
  ReadinessState,
  NotReadyReason,
  TierConfig,
} from "../lib/types";

/**
 * ADR-0007 Session B scaffold: Trust drawer Retrieval tab.
 *
 * STATUS: Typecheck-only stub shipped during 2026-04-24 autonomous
 * validation run. Wires the data flow (api.ts → state → render) but
 * does NOT make visual styling decisions per CLAUDE.md / Don feedback
 * — those are explicitly parked for Don's review on return.
 *
 * What this component delivers today:
 *   - Polls `embeddingsReadiness()` every 2 seconds.
 *   - Renders the structured ReadinessState (kind + reason variant).
 *   - Surfaces the tier-aware model name + size from the active tier.
 *   - Provides a hook point for the [Backfill now] button when the
 *     backend ships that command (ADR-0007 D5 backend lands later in
 *     Session B).
 *
 * What this component DOES NOT do (Don's call on return):
 *   - Final visual layout (currently uses existing aether-* classes
 *     where they exist; some placeholder div nesting where they don't).
 *   - Toast styling / duration (ADR-0007 D6 transient toast is a Don
 *     visual decision).
 *   - Indicator placement in the chrome (drawer icon attention badge
 *     per ADR-0007 D6 — placement is a Don visual decision).
 *   - Pull-instruction copy tone (the strings here are functional
 *     placeholders; final copy is a Don decision).
 *   - "Backfill now" button placement / progress UI (depends on
 *     backend command surface that hasn't shipped yet).
 *
 * Imports the same patterns as MemoryTab / TrustDrawer so the
 * structural integration is correct even though the visual is
 * deliberately minimal.
 */

const POLL_INTERVAL_MS = 2_000;

// Per-tier defaults from ADR-0007 D7 (validated 2026-04-24): the
// model that ships when the user has not explicitly configured a
// `memory.embeddings.provider`. The active model surfaced in the UI
// reflects either the explicit configuration OR this default,
// whichever wins (configuration always takes precedence).
const SPARK_DEFAULT = { name: "nomic-embed-text", size_gb: 0.3 };
const FLAME_DEFAULT = { name: "bge-m3", size_gb: 1.2 };
const FORGE_DEFAULT = { name: "bge-m3", size_gb: 1.2 };

/** Approximate disk size for known embedding models. Mirrors the
 * Rust `required_disk_gb_for_provider` heuristic in retrieval.rs.
 * Returned as a soft estimate; the actual UI should not crash on
 * unknown models — falls back to the tier default size. */
function knownModelSize(modelName: string, fallback: number): number {
  if (modelName.includes("bge-m3")) return 1.2;
  if (modelName.includes("bge-small") || modelName.includes("bge-mini"))
    return 0.13;
  if (modelName.includes("nomic-embed")) return 0.3;
  return fallback;
}

/** Strip provider prefixes ("ollama:", "hf:org:repo:") to get the bare
 * model name. Mirrors `parse_model_name` in retrieval.rs. */
function bareModelName(provider: string): string {
  const parts = provider.split(":");
  return parts[parts.length - 1] || provider;
}

function tierDefaultModel(tier: TierConfig | null) {
  if (!tier) return FLAME_DEFAULT;
  switch (tier.selected_tier) {
    case "spark":
      return SPARK_DEFAULT;
    case "flame":
      return FLAME_DEFAULT;
    case "forge":
      return FORGE_DEFAULT;
  }
}

/** Resolve the active embedding model for display: the user's
 * explicit `memory.embeddings.provider` if set, otherwise the
 * tier default. Mirrors the resolution logic that the Rust readiness
 * probe uses, so the UI shows what the backend will actually use. */
function activeModel(
  tier: TierConfig | null,
  cfg: MemoryConfig | null,
): { name: string; size_gb: number; configured: boolean } {
  const provider = cfg?.embeddings.provider;
  if (provider && provider.length > 0) {
    const name = bareModelName(provider);
    const tierDefault = tierDefaultModel(tier);
    return {
      name,
      size_gb: knownModelSize(name, tierDefault.size_gb),
      configured: true,
    };
  }
  const d = tierDefaultModel(tier);
  return { ...d, configured: false };
}

function reasonCopy(reason: NotReadyReason, modelName: string): string {
  switch (reason.kind) {
    case "provider_unreachable":
      return `Embedding provider unreachable. Is Ollama running? (${reason.detail})`;
    case "model_not_installed":
      return `Embedding model ${reason.model || modelName} is not installed. Run \`ollama pull ${reason.model || modelName}\` in a terminal and Companion will activate retrieval automatically.`;
    case "policy_denied":
      return `Retrieval is currently blocked by your policy settings. Check the Trust drawer's policy section.`;
    case "embed_failed":
      return `The embedding call failed: ${reason.detail}. Check the logs and retry.`;
    case "bailout":
      return `Retrieval exceeded the 5-second wall-clock deadline. Provider may be slow or under load.`;
    case "low_disk":
      return `Disk space too low for embedding model. Need ~${reason.needed_gb} GB free; have ~${reason.available_gb} GB.`;
  }
}

interface Props {
  /** Trust drawer signals to its tabs when it opens so they refresh.
   * Mirrored from MemoryTab/TrustDrawer pattern. */
  refreshKey: number;
}

export function RetrievalTab({ refreshKey }: Props) {
  const [readiness, setReadiness] = useState<ReadinessState | null>(null);
  const [tier, setTier] = useState<TierConfig | null>(null);
  const [memoryCfg, setMemoryCfg] = useState<MemoryConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unembeddedCount, setUnembeddedCount] = useState<number | null>(null);
  const [backfill, setBackfill] = useState<BackfillProgress | null>(null);
  const [backfillRunning, setBackfillRunning] = useState(false);

  useEffect(() => {
    let mounted = true;
    let interval: ReturnType<typeof setInterval> | null = null;
    const unsubs: Array<() => void> = [];

    async function refresh() {
      try {
        const r = await embeddingsReadiness();
        if (mounted) setReadiness(r);
      } catch (e) {
        if (mounted) setError(`readiness probe error: ${String(e)}`);
      }
      try {
        const n = await backfillCount();
        if (mounted) setUnembeddedCount(n);
      } catch {
        // backfill_count is best-effort; quietly ignore
      }
      try {
        const p = await backfillStatus();
        if (mounted) {
          setBackfill(p);
          // Sync running flag with worker state — covers the case where
          // a backfill is in progress when the tab first opens.
          if (!p.finished && p.total > 0) setBackfillRunning(true);
          if (p.finished) setBackfillRunning(false);
        }
      } catch {
        // backfill_status is best-effort
      }
    }

    async function init() {
      try {
        const t = await getTier();
        if (mounted) setTier(t);
      } catch (e) {
        if (mounted) setError(`tier load error: ${String(e)}`);
      }
      try {
        const cfg = await getMemoryConfig();
        if (mounted) setMemoryCfg(cfg);
      } catch {
        // Memory config is best-effort here; UI falls back to tier defaults.
      }
      await refresh();
      interval = setInterval(refresh, POLL_INTERVAL_MS);

      // Live event subscriptions for sub-second progress updates.
      const offProgress = await onBackfillProgress((payload) => {
        if (!mounted) return;
        setBackfill(payload);
      });
      const offDone = await onBackfillDone((payload) => {
        if (!mounted) return;
        setBackfill(payload);
        setBackfillRunning(false);
        // Phase 4D — refresh the un-embedded count so the
        // "Backfill ~N items" copy reflects post-backfill reality.
        // Best-effort; the next periodic refresh will pick it up
        // anyway if this throws.
        backfillCount()
          .then((n) => {
            if (mounted) setUnembeddedCount(n);
          })
          .catch(() => {});
      });
      // ADR-0006 D5: re-read tier on tier:changed without polling.
      const offTier = await onTierChanged((next) => {
        if (!mounted) return;
        setTier(next);
      });
      unsubs.push(offProgress, offDone, offTier);
    }

    void init();
    return () => {
      mounted = false;
      if (interval) clearInterval(interval);
      unsubs.forEach((fn) => fn());
    };
  }, [refreshKey]);

  async function handleBackfill() {
    setError(null);
    setBackfillRunning(true);
    try {
      // Phase 4D — `start_backfill` now returns immediately with the
      // initial progress snapshot once the worker is spawned. The
      // running flag is cleared by the `onBackfillDone` listener and
      // the post-run count refresh is triggered there too. Treating
      // the return value as the final progress would clobber the
      // live event stream with a zeroed snapshot.
      const initialProgress = await startBackfill();
      setBackfill(initialProgress);
    } catch (e) {
      setError(`backfill error: ${String(e)}`);
      setBackfillRunning(false);
    }
  }

  async function handleCancel() {
    try {
      await cancelBackfill();
    } catch (e) {
      setError(`cancel error: ${String(e)}`);
    }
  }

  if (error) {
    return <div className="text-aether-err text-sm">{error}</div>;
  }

  if (!readiness) {
    return <div className="text-aether-muted text-sm">Loading retrieval status…</div>;
  }

  const model = activeModel(tier, memoryCfg);

  if (readiness.kind === "disabled") {
    return (
      <div className="space-y-2">
        <div className="text-aether-muted text-sm">
          Retrieval is off. Toggle <code>embeddings.enabled = true</code> in
          memory settings to activate.
        </div>
        <div className="text-aether-muted text-xs">
          Active tier: <strong>{tier?.selected_tier ?? "unknown"}</strong>.
          Embedding model would be <code>{model.name}</code> (~{model.size_gb} GB).
        </div>
      </div>
    );
  }

  if (readiness.kind === "unknown") {
    return <div className="text-aether-muted text-sm">Probing retrieval readiness…</div>;
  }

  if (readiness.kind === "ready") {
    const showBackfillOffer =
      unembeddedCount !== null && unembeddedCount > 0 && !backfillRunning;
    return (
      <div className="space-y-2">
        <div className="text-aether-ok text-sm">Retrieval is active.</div>
        <div className="text-aether-muted text-xs">
          Tier: <strong>{tier?.selected_tier ?? "unknown"}</strong>. Embedding
          model: <code>{model.name}</code>.
        </div>
        {showBackfillOffer && (
          <div className="space-y-1">
            <div className="text-aether-muted text-sm">
              {unembeddedCount} memor{unembeddedCount === 1 ? "y" : "ies"} not
              indexed for retrieval.
            </div>
            <button
              type="button"
              onClick={handleBackfill}
              className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11.5px] text-aether-text hover:border-aether-text"
              title={`Re-index ${unembeddedCount} memories using ${model.name}`}
            >
              Backfill now
            </button>
          </div>
        )}
        {backfillRunning && backfill && (
          <BackfillProgressView
            backfill={backfill}
            onCancel={handleCancel}
            modelName={model.name}
          />
        )}
        {!backfillRunning &&
          backfill &&
          backfill.finished &&
          (backfill.completed > 0 || backfill.skipped_already_embedded > 0) && (
            <BackfillSummaryLine backfill={backfill} />
          )}
      </div>
    );
  }

  // not_ready — render the structured reason
  return (
    <div className="space-y-2">
      <div className="text-aether-warn text-sm">
        Retrieval is not active.
      </div>
      <div className="text-aether-muted text-sm">
        {reasonCopy(readiness.reason, model.name)}
      </div>
      <div className="text-aether-muted text-xs">
        Tier: <strong>{tier?.selected_tier ?? "unknown"}</strong>. Target
        model: <code>{model.name}</code> (~{model.size_gb} GB).
      </div>
    </div>
  );
}

interface BackfillProgressViewProps {
  backfill: BackfillProgress;
  onCancel: () => void;
  modelName: string;
}

function BackfillProgressView({
  backfill,
  onCancel,
  modelName,
}: BackfillProgressViewProps) {
  // Both newly-embedded rows and already-embedded skips count as
  // "processed" for the progress bar — skipping is the cheap path,
  // not unfinished work. Hard failures count as "advanced past" too;
  // we don't re-attempt within a job.
  const processed =
    backfill.completed +
    backfill.skipped_already_embedded +
    backfill.failures;
  const pct =
    backfill.total > 0
      ? Math.round((processed / backfill.total) * 100)
      : 0;
  return (
    <div className="space-y-1">
      <div className="text-aether-muted text-sm">
        Indexing with <code>{modelName}</code>: {processed} of {backfill.total}
        {backfill.current_domain ? ` — ${backfill.current_domain}` : ""}.
      </div>
      <BackfillCounters backfill={backfill} />
      <div className="h-1 w-full overflow-hidden rounded bg-aether-bg/40">
        <div
          className="h-full bg-aether-ok transition-all"
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <button
        type="button"
        onClick={onCancel}
        className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11.5px] text-aether-muted hover:border-aether-text hover:text-aether-text"
      >
        Cancel
      </button>
    </div>
  );
}

/**
 * Stable always-visible counters for in-progress and post-run views.
 *
 * Per AUDIT_ROW_UI_RESEARCH.md (Linear / Stripe / Carbon discipline):
 * critical state lives in a stable affordance, not a hover-only
 * tooltip. The user must be able to see "did anything fail?" without
 * interacting with the row.
 *
 * Tier of attention:
 *   - failures (J): red badge — user attention warranted; lost data.
 *   - recovered_failures (K): small grey text — informational; the
 *     system self-healed. Reassures rather than alarms.
 *   - skipped_already_embedded (M): small grey text — explains why
 *     "indexed" might be lower than "total".
 *
 * Each counter is omitted when zero so the happy-path UI stays clean.
 */
function BackfillCounters({ backfill }: { backfill: BackfillProgress }) {
  const { failures, recovered_failures, skipped_already_embedded } = backfill;
  if (
    failures === 0 &&
    recovered_failures === 0 &&
    skipped_already_embedded === 0
  ) {
    return null;
  }
  return (
    <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px]">
      {failures > 0 && (
        <span
          data-testid="backfill-failures"
          className="rounded border border-aether-err/50 bg-aether-err/10 px-1.5 py-0.5 font-medium text-aether-err"
        >
          {failures} failed
        </span>
      )}
      {recovered_failures > 0 && (
        <span
          data-testid="backfill-recovered"
          className="text-aether-muted"
        >
          {recovered_failures} recovered after retry
        </span>
      )}
      {skipped_already_embedded > 0 && (
        <span
          data-testid="backfill-skipped"
          className="text-aether-muted"
        >
          {skipped_already_embedded} already embedded
        </span>
      )}
    </div>
  );
}

/**
 * Post-run summary line for completed backfills. Stable affordance:
 * the headline "N indexed" is always visible; the parenthetical
 * counter strip uses BackfillCounters to surface non-zero failures /
 * recovered / skipped with appropriate visual weight (failures get a
 * red badge, the rest stay informational).
 *
 * Per quality standard #3 — don't lie to the user. Embedding losses
 * (`failures`) get the highest visual weight because the user has to
 * decide whether to re-run. Recovered transient blips get
 * acknowledged so the user understands that "self-healed" is a
 * deliberate behaviour, not a missed alert.
 */
function BackfillSummaryLine({ backfill }: { backfill: BackfillProgress }) {
  return (
    <div className="space-y-1">
      <div className="text-aether-muted text-xs">
        Last backfill: {backfill.completed} indexed
        {backfill.cancelled ? " (cancelled)" : ""}.
      </div>
      <BackfillCounters backfill={backfill} />
    </div>
  );
}
