import { useEffect, useState } from "react";

import {
  getMediaPermissions,
  getMicPermission,
  getPresenceConfig,
  setMediaPermission,
  setMicPermission,
  setPresenceConfig,
} from "../lib/api";
import type {
  MediaKind,
  MediaPermissions,
  MediaPermissionState,
  MicPermission,
  PresenceConfig,
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
  const [mic, setMic] = useState<MicPermission | null>(null);
  const [presence, setPresence] = useState<PresenceConfig | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busyKind, setBusyKind] = useState<MediaKind | null>(null);
  const [busyMic, setBusyMic] = useState(false);
  const [busyPresence, setBusyPresence] = useState(false);

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
    getMicPermission()
      .then((m) => {
        if (!cancelled) setMic(m);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    getPresenceConfig()
      .then((p) => {
        if (!cancelled) setPresence(p);
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

  const handleMicChange = async (next: MediaPermissionState) => {
    setBusyMic(true);
    setErr(null);
    try {
      const updated = await setMicPermission(next);
      setMic(updated);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyMic(false);
    }
  };

  const updatePresence = async (patch: Partial<PresenceConfig>) => {
    if (!presence) return;
    const next: PresenceConfig = { ...presence, ...patch };
    setBusyPresence(true);
    setErr(null);
    try {
      const updated = await setPresenceConfig(next);
      setPresence(updated);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyPresence(false);
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

        <section
          aria-labelledby="settings-mic-heading"
          className="mt-6 border-t border-aether-border pt-4"
        >
          <h2
            id="settings-mic-heading"
            className="text-[11px] uppercase tracking-[0.18em] text-aether-dim"
          >
            Microphone
          </h2>
          <p className="mt-1 text-[12px] text-aether-muted">
            Mic consent is tracked separately from camera and screen.
            Voice capture is push-to-talk only; Aether never listens
            continuously.
          </p>

          <div className="mt-4">
            <PermissionRow
              title="Microphone"
              body="Short push-to-talk utterances Aether may transcribe for voice input. Capture happens only while you hold the Record button on the Voice panel."
              value={mic?.state ?? "ask"}
              busy={busyMic}
              onChange={(next) => handleMicChange(next)}
            />
          </div>
        </section>

        <section
          aria-labelledby="settings-presence-heading"
          className="mt-6 border-t border-aether-border pt-4"
        >
          <h2
            id="settings-presence-heading"
            className="text-[11px] uppercase tracking-[0.18em] text-aether-dim"
          >
            Presence
          </h2>
          <p className="mt-1 text-[12px] text-aether-muted">
            Aether tracks presence (Active / Idle / Away) to pace its
            responses. Presence signals are observational only — they
            do not trigger a capability gate or an audit row.
          </p>

          <div className="mt-4 flex flex-col gap-3">
            <ToggleRow
              title="Track presence"
              body="When off, Aether pauses the presence controller entirely. No state is emitted until you flip it back."
              checked={presence?.enabled ?? true}
              busy={busyPresence || presence === null}
              onChange={(v) => updatePresence({ enabled: v })}
            />
            <ToggleRow
              title="Show presence in Trust history"
              body="Include presence transitions in the Trust drawer's History tab. Off hides them from the list but does not disable tracking."
              checked={presence?.history_in_trust_drawer ?? true}
              busy={busyPresence || presence === null}
              onChange={(v) => updatePresence({ history_in_trust_drawer: v })}
            />
            {presence && (
              <p className="text-[11px] text-aether-dim">
                Thresholds: Active → Idle after{" "}
                <span className="font-mono">{presence.idle_after_s}s</span>, Idle → Away after{" "}
                <span className="font-mono">{presence.away_after_s}s</span>.
                Threshold editing is deferred to Presence V1 step 2.
              </p>
            )}
          </div>
        </section>
      </div>

      <div className="border-t border-aether-border px-5 py-3 text-[11px] text-aether-muted">
        Stored locally at{" "}
        <code className="font-mono text-aether-dim">
          %APPDATA%/Aether/media_permissions.json
        </code>
        ,{" "}
        <code className="font-mono text-aether-dim">
          %APPDATA%/Aether/mic_permissions.json
        </code>
        , and{" "}
        <code className="font-mono text-aether-dim">
          %APPDATA%/Aether/presence.json
        </code>
      </div>
    </div>
  );
}

/**
 * Compact two-state toggle row for observational settings (e.g.
 * Presence). Visually lighter than `PermissionRow` because there is
 * no tri-state / approval semantic — a simple yes/no.
 */
function ToggleRow({
  title,
  body,
  checked,
  busy,
  onChange,
}: {
  title: string;
  body: string;
  checked: boolean;
  busy: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[13px] font-medium text-aether-text">{title}</div>
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          aria-label={title}
          disabled={busy}
          onClick={() => onChange(!checked)}
          className={`rounded-md border px-2.5 py-1 text-[11px] transition-colors ${
            checked
              ? "border-aether-ok/60 bg-aether-ok/10 text-aether-ok"
              : "border-aether-border bg-transparent text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
          } ${busy ? "opacity-60" : ""}`}
        >
          {checked ? "On" : "Off"}
        </button>
      </div>
      <p className="mt-1 text-[11.5px] text-aether-muted">{body}</p>
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
