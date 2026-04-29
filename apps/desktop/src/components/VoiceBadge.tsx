import { useCallback, useEffect, useState } from "react";

import {
  listSpeechModels,
  refreshSpeechModels,
  setActiveSpeechModel,
  setActiveSpeechProvider,
  voiceStatus,
} from "../lib/api";
import type { SpeechModelList, VoiceStatus } from "../lib/types";

interface Props {
  /** Bumping this number forces the badge to refetch its status —
   * lets the parent panel coordinate the badge with the
   * ActiveVoiceRoute hint. */
  refreshKey?: number;
  /** Fires after a successful provider swap, model swap, or refresh
   * so siblings can invalidate. */
  onRouteChanged?: () => void;
}

const DISABLED_VALUE = "__none__";

/**
 * Status badge + runtime-swap dropdown for the VoicePanel. Mirrors
 * `VisionBadge`, but with one important difference: voice has NO
 * text-only fallback, so the "disabled" option means the next
 * `transcribe_utterance` will error loudly.
 *
 * Selection is persisted server-side (`voice_provider.json`) so the
 * choice survives the next launch.
 */
export function VoiceBadge({ refreshKey, onRouteChanged }: Props) {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [models, setModels] = useState<SpeechModelList | null>(null);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    voiceStatus()
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

  const activeId = status?.active_id ?? null;
  useEffect(() => {
    if (!activeId) {
      setModels(null);
      return;
    }
    let cancelled = false;
    setModelsLoading(true);
    listSpeechModels()
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
        const id = next === DISABLED_VALUE ? null : next;
        const updated = await setActiveSpeechProvider(id);
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
  const selectValue = status.active_id ?? DISABLED_VALUE;

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
          {status.enabled ? "Voice route" : "Voice disabled"}
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
            <label
              className="text-[11px] text-aether-muted"
              htmlFor="voice-route"
            >
              Active
            </label>
            <select
              id="voice-route"
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
              <option value={DISABLED_VALUE}>Disabled (no fallback)</option>
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
                  const updated = await setActiveSpeechModel(modelId);
                  setStatus(updated);
                  const fresh = await listSpeechModels();
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
                  const fresh = await refreshSpeechModels();
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
          No speech provider is registered. Set{" "}
          <code className="font-mono">AETHER_WHISPERCPP_SPEECH_MODEL</code>{" "}
          (and optionally <code className="font-mono">…_BASE_URL</code>)
          and restart Companion to enable push-to-talk.
        </div>
      )}

      {err && <div className="mt-2 text-aether-err">{err}</div>}
    </div>
  );
}

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
  models: SpeechModelList | null;
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
          Models on {activeProviderId ?? models.provider_id ?? "this provider"}
        </div>
        <RefreshButton busy={busy || loading} onClick={onRefresh} />
      </div>
      <div
        className="mt-1 flex flex-wrap gap-1"
        role="list"
        aria-label="Available speech models"
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
