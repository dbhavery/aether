import { useCallback, useEffect, useState } from "react";

import { setActiveVisionProvider, visionStatus } from "../lib/api";
import type { VisionStatus } from "../lib/types";

interface Props {
  refreshKey?: number;
}

const TEXT_ONLY_VALUE = "__text_only__";

/**
 * Status badge + runtime-swap dropdown for the camera/screen panels.
 *
 * Tells the user which vision route the next "Analyze" call will
 * take — Ollama vision, llama.cpp vision, or text-only fallback —
 * and lets them swap among the registered providers without
 * restarting Aether. Selection is persisted server-side
 * (`vision_provider.json`) so the choice survives the next launch.
 *
 * When no vision provider is registered (no env opt-in), the
 * dropdown is hidden and the badge explains how to enable one.
 */
export function VisionBadge({ refreshKey }: Props) {
  const [status, setStatus] = useState<VisionStatus | null>(null);
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
            providers: [],
          });
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const handleChange = useCallback(
    async (next: string) => {
      setBusy(true);
      setErr(null);
      try {
        const id = next === TEXT_ONLY_VALUE ? null : next;
        const updated = await setActiveVisionProvider(id);
        setStatus(updated);
      } catch (e) {
        setErr(String(e));
      } finally {
        setBusy(false);
      }
    },
    [],
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
      ) : (
        <div className="mt-1 text-aether-muted">
          Analyze will run the active text model on your note only —
          the pixels are not sent. Set{" "}
          <code className="font-mono">AETHER_OLLAMA_VISION_MODEL</code>{" "}
          (Ollama) or{" "}
          <code className="font-mono">AETHER_LLAMACPP_VISION_MODEL</code>{" "}
          (llama-server) and restart Aether to enable.
        </div>
      )}

      {err && (
        <div className="mt-2 text-aether-err">{err}</div>
      )}
    </div>
  );
}
