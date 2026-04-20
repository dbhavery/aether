import { useEffect, useState } from "react";

import { getMediaPermissions, setMediaPermission } from "../lib/api";
import type {
  MediaKind,
  MediaPermissions,
  MediaPermissionState,
} from "../lib/types";

interface Props {
  open: boolean;
  onClose: () => void;
}

const STATES: MediaPermissionState[] = ["allow", "ask", "deny"];

const STATE_COPY: Record<
  MediaPermissionState,
  { label: string; hint: string; color: string }
> = {
  allow: {
    label: "Allow",
    hint: "Capture may proceed without an in-app prompt.",
    color: "text-aether-ok",
  },
  ask: {
    label: "Ask",
    hint: "Aether will request approval before each capture.",
    color: "text-aether-warn",
  },
  deny: {
    label: "Never",
    hint: "Capture is hard-disabled in this build.",
    color: "text-aether-err",
  },
};

const DEVICE_COPY: Record<MediaKind, { title: string; body: string }> = {
  camera: {
    title: "Camera",
    body: "Webcam frames Aether may sample for visual context. Capture only happens after you press the capture control on the camera panel.",
  },
  screen: {
    title: "Screen",
    body: "On-screen content Aether may sample for visual context. Screen capture is currently scaffolded but not wired to a capture surface.",
  },
};

/**
 * Settings drawer (P1 surface). Today it owns one section — local-only
 * media permissions for camera + screen capture. Other settings will
 * land here as the surface grows. Mirrors the visual language of the
 * existing trust drawer so the two drawers feel like siblings.
 */
export function SettingsDrawer({ open, onClose }: Props) {
  const [perms, setPerms] = useState<MediaPermissions | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busyKind, setBusyKind] = useState<MediaKind | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setErr(null);
    getMediaPermissions()
      .then((p) => {
        if (!cancelled) setPerms(p);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  if (!open) return null;

  const handleChange = async (kind: MediaKind, next: MediaPermissionState) => {
    setBusyKind(kind);
    setErr(null);
    try {
      const updated = await setMediaPermission(kind, next);
      setPerms(updated);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyKind(null);
    }
  };

  return (
    <div
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-md flex-col border-l border-aether-border bg-aether-surface shadow-neuRaised animate-fadeIn"
      role="complementary"
      aria-label="Settings"
    >
      <div className="flex items-center justify-between border-b border-aether-border px-5 py-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
            Settings
          </div>
          <div className="text-[13px] text-aether-text">
            Local controls for what Aether may see
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

      <div className="allow-select flex-1 overflow-y-auto px-5 py-4 text-[12.5px]">
        {err && (
          <div className="mb-3 rounded-md border border-aether-err/40 bg-aether-err/5 px-3 py-2 text-aether-err">
            {err}
          </div>
        )}

        <section aria-labelledby="settings-media-heading">
          <h2
            id="settings-media-heading"
            className="text-[11px] uppercase tracking-[0.18em] text-aether-dim"
          >
            Media
          </h2>
          <p className="mt-1 text-[12px] text-aether-muted">
            These choices live only on this machine. Aether never sends
            them anywhere. The OS-level permission prompt is still the
            final say.
          </p>

          <div className="mt-4 flex flex-col gap-4">
            {(["camera", "screen"] as MediaKind[]).map((kind) => {
              const meta = DEVICE_COPY[kind];
              const value = perms?.[kind] ?? "ask";
              return (
                <PermissionRow
                  key={kind}
                  title={meta.title}
                  body={meta.body}
                  value={value}
                  busy={busyKind === kind}
                  onChange={(next) => handleChange(kind, next)}
                />
              );
            })}
          </div>
        </section>
      </div>

      <div className="border-t border-aether-border px-5 py-3 text-[11px] text-aether-muted">
        Stored locally at{" "}
        <code className="font-mono text-aether-dim">
          %APPDATA%/Aether/media_permissions.json
        </code>
      </div>
    </div>
  );
}

function PermissionRow({
  title,
  body,
  value,
  busy,
  onChange,
}: {
  title: string;
  body: string;
  value: MediaPermissionState;
  busy: boolean;
  onChange: (next: MediaPermissionState) => void;
}) {
  return (
    <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[13px] font-medium text-aether-text">{title}</div>
        <div className={`text-[11px] ${STATE_COPY[value].color}`}>
          {STATE_COPY[value].label}
        </div>
      </div>
      <p className="mt-1 text-[11.5px] text-aether-muted">{body}</p>

      <div
        role="radiogroup"
        aria-label={`${title} permission`}
        className="mt-3 flex gap-2"
      >
        {STATES.map((s) => {
          const active = s === value;
          return (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(s)}
              disabled={busy}
              title={STATE_COPY[s].hint}
              className={`flex-1 rounded-md px-2 py-1.5 text-[11.5px] transition-colors ${
                active
                  ? "border border-aether-borderHi bg-aether-elevated text-aether-text"
                  : "border border-aether-border bg-transparent text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
              } ${busy ? "opacity-60" : ""}`}
            >
              {STATE_COPY[s].label}
            </button>
          );
        })}
      </div>

      <p className="mt-2 text-[11px] text-aether-dim">{STATE_COPY[value].hint}</p>
    </div>
  );
}
