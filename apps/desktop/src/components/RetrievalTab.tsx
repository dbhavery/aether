import { useEffect, useState } from "react";
import {
  backfillCount,
  backfillStatus,
  cancelBackfill,
  embeddingsReadiness,
  getTier,
  onBackfillDone,
  onBackfillProgress,
  startBackfill,
  type BackfillProgress,
} from "../lib/api";
import type { ReadinessState, NotReadyReason, TierConfig } from "../lib/types";

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

const SPARK_MODEL = { name: "nomic-embed-text", size_gb: 0.3 };
const FLAME_MODEL = { name: "bge-m3", size_gb: 1.2 };
const FORGE_MODEL = { name: "bge-m3", size_gb: 1.2 };

function tierModel(tier: TierConfig | null) {
  if (!tier) return FLAME_MODEL;
  switch (tier.selected_tier) {
    case "spark":
      return SPARK_MODEL;
    case "flame":
      return FLAME_MODEL;
    case "forge":
      return FORGE_MODEL;
  }
}

function reasonCopy(reason: NotReadyReason, modelName: string): string {
  switch (reason.kind) {
    case "provider_unreachable":
      return `Embedding provider unreachable. Is Ollama running? (${reason.detail})`;
    case "model_not_installed":
      return `Embedding model ${reason.model || modelName} is not installed. Run \`ollama pull ${reason.model || modelName}\` in a terminal and Aether will activate retrieval automatically.`;
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
      });
      unsubs.push(offProgress, offDone);
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
      const finalProgress = await startBackfill();
      setBackfill(finalProgress);
      setBackfillRunning(false);
      // Refresh count so the "~N items" copy reflects post-backfill reality.
      try {
        const n = await backfillCount();
        setUnembeddedCount(n);
      } catch {
        // best-effort
      }
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

  const model = tierModel(tier);

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
        {!backfillRunning && backfill && backfill.finished && backfill.completed > 0 && (
          <div className="text-aether-muted text-xs">
            Last backfill: {backfill.completed} indexed
            {backfill.failures > 0 ? `, ${backfill.failures} failed` : ""}
            {backfill.cancelled ? " (cancelled)" : ""}.
          </div>
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
  const pct =
    backfill.total > 0
      ? Math.round((backfill.completed / backfill.total) * 100)
      : 0;
  return (
    <div className="space-y-1">
      <div className="text-aether-muted text-sm">
        Indexing with <code>{modelName}</code>: {backfill.completed} of{" "}
        {backfill.total}
        {backfill.current_domain ? ` (${backfill.current_domain})` : ""}.
      </div>
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
