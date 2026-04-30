import { useCallback, useEffect, useState } from "react";

import {
  listVisionModels,
  refreshVisionModels,
  setActiveVisionModel,
  setActiveVisionProvider,
  visionStatus,
} from "../lib/api";
import type { VisionModelList, VisionStatus } from "../lib/types";

interface Props {
  /** Bumping this number forces the badge to refetch its status —
   * lets a parent panel coordinate the badge with sibling surfaces
   * (the per-panel ActiveVisionRoute hint, primarily). */
  refreshKey?: number;
  /** Fires after a successful provider swap, model swap, or refresh.
   * Parents use it to invalidate sibling views that depend on the
   * vision route (e.g. the active-route hint above the Analyze
   * button). Failures don't fire — the user-visible error line stays
   * inside the badge. */
  onRouteChanged?: () => void;
}

const TEXT_ONLY_VALUE = "__text_only__";

/**
 * Status badge + runtime-swap dropdown for the camera/screen panels.
 *
 * Tells the user which vision route the next "Analyze" call will
 * take — Ollama vision, llama.cpp vision, or text-only fallback —
 * and lets them swap among the registered providers without
 * restarting Companion. Selection is persisted server-side
 * (`vision_provider.json`) so the choice survives the next launch.
 *
 * When no vision provider is registered (no env opt-in), the
 * dropdown is hidden and the badge explains how to enable one.
 */
export function VisionBadge({ refreshKey, onRouteChanged }: Props) {
  const [status, setStatus] = useState<VisionStatus | null>(null);
  const [models, setModels] = useState<VisionModelList | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    visionStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled)
          setStatus({
            enabled: false,
            active_id: null,
            label: null,
            active_model: null,
            providers: [],
          });
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  // Refresh the model list whenever the active provider changes (or
  // the badge first renders with one). Failures collapse to a quiet
  // "models unavailable" hint — no toast, no console spam.
  const activeId = status?.active_id ?? null;
  useEffect(() => {
    if (!activeId) {
      setModels(null);
      return;
    }
    let cancelled = false;
    setModelsLoading(true);
    listVisionModels()
      .then((m) => {
        if (!cancelled) setModels(m);
      })
      .catch(() => {
        if (!cancelled)
          setModels({
            provider_id: activeId,
            models: [],
            error: "Models unavailable for this provider.",
          });
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const handleChange = useCallback(
    async (next: string) => {
      setBusy(true);
      setErr(null);
      try {
        const id = next === TEXT_ONLY_VALUE ? null : next;
        const updated = await setActiveVisionProvider(id);
        setStatus(updated);
        onRouteChanged?.();
      } catch (e) {
        setErr(String(e));
      } finally {
        setBusy(false);
      }
    },
    [onRouteChanged],
  );

  if (!status) return null;

  const hasProviders = status.providers.length > 0;
  const selectValue = status.active_id ?? TEXT_ONLY_VALUE;

  return (
    <div
      className={`rounded-md border px-3 py-2 text-[11.5px] ${
        status.enabled
          ? "border-aether-ok/40 bg-aether-ok/5"
          : "border-aether-border bg-aether-elevated/40"
      }`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span
          className={`font-medium ${
            status.enabled ? "text-aether-ok" : "text-aether-text"
          }`}
        >
          {status.enabled ? "Vision route" : "Text-only fallback"}
        </span>
        {status.enabled && status.label && (
          <span className="font-mono text-[10.5px] text-aether-muted">
            {status.label}
          </span>
        )}
      </div>

      {hasProviders ? (
        <>
          <div className="mt-2 flex items-center gap-2">
            <label className="text-[11px] text-aether-muted" htmlFor="vision-route">
              Active
            </label>
            <select
              id="vision-route"
              value={selectValue}
              disabled={busy}
              onChange={(e) => handleChange(e.target.value)}
              className="flex-1 rounded-md border border-aether-border bg-aether-elevated px-2 py-1 text-[11.5px] text-aether-text focus:outline-none focus:ring-1 focus:ring-aether-accent"
            >
              {status.providers.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
              <option value={TEXT_ONLY_VALUE}>Text-only fallback</option>
            </select>
          </div>
          {status.enabled && (
            <ModelListSection
              loading={modelsLoading}
              models={models}
              activeProviderId={activeId ?? null}
              activeModel={status.active_model ?? null}
              busy={busy}
              onPickModel={async (modelId) => {
                setBusy(true);
                setErr(null);
                try {
                  const updated = await setActiveVisionModel(modelId);
                  setStatus(updated);
                  // Cache was invalidated server-side on pick; refresh
                  // the UI's snapshot so the "Active" ring moves.
                  const fresh = await listVisionModels();
                  setModels(fresh);
                  onRouteChanged?.();
                } catch (e) {
                  setErr(String(e));
                } finally {
                  setBusy(false);
                }
              }}
              onRefresh={async () => {
                setModelsLoading(true);
                setErr(null);
                try {
                  const fresh = await refreshVisionModels();
                  setModels(fresh);
                  onRouteChanged?.();
                } catch (e) {
                  setErr(String(e));
                } finally {
                  setModelsLoading(false);
                }
              }}
            />
          )}
        </>
      ) : (
        <div className="mt-1 text-aether-muted">
          Analyze will run the active text model on your note only —
          the pixels are not sent. Set{" "}
          <code className="font-mono">AETHER_OLLAMA_VISION_MODEL</code>{" "}
          (Ollama) or{" "}
          <code className="font-mono">AETHER_LLAMACPP_VISION_MODEL</code>{" "}
          (llama-server) and restart Companion to enable.
        </div>
      )}

      {err && (
        <div className="mt-2 text-aether-err">{err}</div>
      )}
    </div>
  );
}

/**
 * Compact "models on this provider" panel under the dropdown.
 *
 * Failures collapse to a quiet "models unavailable" hint so the
 * dropdown UI never spams. Each chip is clickable — clicking swaps
 * the active provider's model via `set_active_vision_model`. The
 * currently-selected model gets an "Active" ring.
 */
function ModelListSection({
  loading,
  models,
  activeProviderId,
  activeModel,
  busy,
  onPickModel,
  onRefresh,
}: {
  loading: boolean;
  models: VisionModelList | null;
  activeProviderId: string | null;
  activeModel: string | null;
  busy: boolean;
  onPickModel: (modelId: string) => void | Promise<void>;
  onRefresh: () => void | Promise<void>;
}) {
  if (loading) {
    return (
      <div className="mt-2 text-[11px] text-aether-muted">
        Loading models on this provider…
      </div>
    );
  }
  if (!models) return null;
  // If discovery returned an error or an empty list, render the
  // plain-language hint alongside a retry affordance — a common
  // cause is the daemon briefly unreachable, and a manual refresh
  // is faster than waiting for the UI to remount.
  if (models.error || models.models.length === 0) {
    return (
      <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-aether-muted">
        <span>{models.error ?? "Models unavailable for this provider."}</span>
        <RefreshButton busy={busy || loading} onClick={onRefresh} />
      </div>
    );
  }
  return (
    <div className="mt-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[10.5px] uppercase tracking-[0.18em] text-aether-dim">
          Models on{" "}
          {activeProviderId ?? models.provider_id ?? "this provider"}
        </div>
        <RefreshButton busy={busy || loading} onClick={onRefresh} />
      </div>
      <div
        className="mt-1 flex flex-wrap gap-1"
        role="list"
        aria-label="Available models"
      >
        {models.models.map((m) => {
          const isActive = activeModel !== null && m === activeModel;
          const base =
            "max-w-[14rem] truncate rounded-full border px-2 py-0.5 font-mono text-[10.5px]";
          const activeStyle =
            "border-aether-ok/60 bg-aether-ok/10 text-aether-ok";
          const idleStyle =
            "border-aether-border bg-aether-elevated/60 text-aether-muted hover:border-aether-accent/60 hover:text-aether-text";
          return (
            <button
              key={m}
              type="button"
              role="listitem"
              title={isActive ? `${m} (active)` : `Switch to ${m}`}
              aria-pressed={isActive}
              disabled={busy || isActive}
              onClick={() => onPickModel(m)}
              className={`${base} ${isActive ? activeStyle : idleStyle} disabled:cursor-default disabled:opacity-70`}
            >
              {m}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Compact refresh affordance — a `↻` glyph that calls `onClick`.
 * Disabled while a swap or load is in flight so we never queue a
 * second refresh on top of an in-flight one.
 */
function RefreshButton({
  busy,
  onClick,
}: {
  busy: boolean;
  onClick: () => void | Promise<void>;
}) {
  return (
    <button
      type="button"
      title="Refresh model list"
      aria-label="Refresh model list"
      disabled={busy}
      onClick={() => onClick()}
      className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-aether-border bg-aether-elevated/60 text-[11px] text-aether-muted hover:border-aether-accent/60 hover:text-aether-text disabled:cursor-default disabled:opacity-50"
    >
      <span aria-hidden="true">↻</span>
    </button>
  );
}
