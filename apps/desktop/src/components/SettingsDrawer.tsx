import { useEffect, useState } from "react";

import {
  currentAutonomyPreset,
  getMediaPermissions,
  getMemoryConfig,
  getMicPermission,
  getPresenceConfig,
  setAutonomyPreset,
  setMediaPermission,
  setMemoryConfig,
  setMicPermission,
  setPresenceConfig,
} from "../lib/api";
import type {
  MediaKind,
  MediaPermissions,
  MediaPermissionState,
  MemoryConfig,
  MemoryDomain,
  MemoryRisk,
  MicPermission,
  PresenceConfig,
} from "../lib/types";
import {
  MEMORY_DOMAINS,
  PRESENCE_THRESHOLD_MAX_S,
  PRESENCE_THRESHOLD_MIN_S,
} from "../lib/types";
import { PersonaSection } from "./PersonaSection";

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
    hint: "Companion will request approval before each capture.",
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
    body: "Webcam frames Companion may sample for visual context. Capture only happens after you press the capture control on the camera panel.",
  },
  screen: {
    title: "Screen",
    body: "On-screen content Companion may sample for visual context. Screen capture is currently scaffolded but not wired to a capture surface.",
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
  const [memory, setMemory] = useState<MemoryConfig | null>(null);
  const [autonomy, setAutonomy] = useState<string | null>(null);
  const [autonomyLoaded, setAutonomyLoaded] = useState(false);
  // The shared `err` shows at the top of the drawer. Doctrine §8
  // used-as-user verify (2026-04-30) caught that an Autonomy-section
  // failure was rendering far above the section the user was looking
  // at. Section-scoped error states let each panel render its own
  // alert next to the controls that produced it.
  const [autonomyErr, setAutonomyErr] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busyKind, setBusyKind] = useState<MediaKind | null>(null);
  const [busyMic, setBusyMic] = useState(false);
  const [busyPresence, setBusyPresence] = useState(false);
  const [busyMemory, setBusyMemory] = useState(false);
  const [busyAutonomy, setBusyAutonomy] = useState(false);

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
    getMemoryConfig()
      .then((m) => {
        if (!cancelled) setMemory(m);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    currentAutonomyPreset()
      .then((p) => {
        if (!cancelled) {
          setAutonomy(p);
          setAutonomyLoaded(true);
        }
      })
      .catch((e) => {
        if (!cancelled) setAutonomyErr(String(e));
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

  const updateAutonomy = async (next: string | null) => {
    setBusyAutonomy(true);
    setAutonomyErr(null);
    try {
      await setAutonomyPreset(next);
      setAutonomy(next);
    } catch (e) {
      setAutonomyErr(String(e));
    } finally {
      setBusyAutonomy(false);
    }
  };

  const updateMemoryRisk = async (domain: MemoryDomain, risk: MemoryRisk) => {
    if (!memory) return;
    const next: MemoryConfig = {
      ...memory,
      default_risk: { ...memory.default_risk, [domain]: risk },
    };
    setBusyMemory(true);
    setErr(null);
    try {
      const updated = await setMemoryConfig(next);
      setMemory(updated);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusyMemory(false);
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
            Local controls for what Companion may see
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

        <PersonaSection open={open} />

        <section
          aria-labelledby="settings-media-heading"
          className="mt-6 border-t border-aether-border pt-4"
        >
          <h2
            id="settings-media-heading"
            className="text-[11px] uppercase tracking-[0.18em] text-aether-dim"
          >
            Media
          </h2>
          <p className="mt-1 text-[12px] text-aether-muted">
            These choices live only on this machine. Companion never sends
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
            Voice capture is push-to-talk only; Companion never listens
            continuously.
          </p>

          <div className="mt-4">
            <PermissionRow
              title="Microphone"
              body="Short push-to-talk utterances Companion may transcribe for voice input. Capture happens only while you hold the Record button on the Voice panel."
              value={mic?.state ?? "ask"}
              busy={busyMic}
              onChange={(next) => handleMicChange(next)}
            />
          </div>
        </section>

        <section
          aria-labelledby="settings-autonomy-heading"
          className="mt-6 border-t border-aether-border pt-4"
        >
          <h2
            id="settings-autonomy-heading"
            className="text-[11px] uppercase tracking-[0.18em] text-aether-dim"
          >
            Autonomy
          </h2>
          <p className="mt-1 text-[12px] text-aether-muted">
            How much Companion does on its own. Overrides the per-capability
            defaults set by the active persona. Picked once during onboarding
            and changeable here.
          </p>

          {autonomyErr && (
            <div
              role="alert"
              className="mt-3 rounded-md border border-aether-err/40 bg-aether-err/5 px-3 py-2 text-[11.5px] text-aether-err"
            >
              {autonomyErr}
            </div>
          )}

          <div className="mt-4">
            <AutonomyRow
              value={autonomy}
              busy={busyAutonomy || !autonomyLoaded}
              onChange={updateAutonomy}
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
            Companion tracks presence (Active / Idle / Away) to pace its
            responses. Presence signals are observational only — they
            do not trigger a capability gate or an audit row.
          </p>

          <div className="mt-4 flex flex-col gap-3">
            <ToggleRow
              title="Track presence"
              body="When off, Companion pauses the presence controller entirely. No state is emitted until you flip it back."
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
              <ThresholdEditor
                presence={presence}
                busy={busyPresence}
                onCommit={updatePresence}
                onError={setErr}
              />
            )}
          </div>
        </section>

        <section
          aria-labelledby="settings-memory-heading"
          className="mt-6 border-t border-aether-border pt-4"
        >
          <h2
            id="settings-memory-heading"
            className="text-[11px] uppercase tracking-[0.18em] text-aether-dim"
          >
            Memory
          </h2>
          <p className="mt-1 text-[12px] text-aether-muted">
            What Companion remembers, and whether each domain writes
            automatically or asks first. User-sensitive domains
            (Facts, Artifacts) default to Ask. See the Memory
            architecture doc for the full rules.
          </p>
          {memory && (
            <div className="mt-4 flex flex-col gap-2">
              {MEMORY_DOMAINS.map((d) => (
                <MemoryRiskRow
                  key={d}
                  domain={d}
                  risk={memory.default_risk[d] ?? MEMORY_RISK_DEFAULT[d]}
                  retention={
                    memory.retention_days[d] ??
                    MEMORY_RETENTION_DEFAULT[d] ??
                    null
                  }
                  busy={busyMemory}
                  onChange={(risk) => updateMemoryRisk(d, risk)}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      <div className="border-t border-aether-border px-5 py-3 text-[11px] text-aether-muted">
        Stored locally at{" "}
        <code className="font-mono text-aether-dim">
          %APPDATA%/Companion/media_permissions.json
        </code>
        ,{" "}
        <code className="font-mono text-aether-dim">
          %APPDATA%/Companion/mic_permissions.json
        </code>
        ,{" "}
        <code className="font-mono text-aether-dim">
          %APPDATA%/Companion/presence.json
        </code>
        , and{" "}
        <code className="font-mono text-aether-dim">
          %APPDATA%/Companion/memory.json
        </code>
      </div>
    </div>
  );
}

// Memory V2 step 2 — client-side copies of the design-doc defaults
// so the Settings UI renders sensible values even when a domain has
// been dropped from the persisted map.
const MEMORY_RISK_DEFAULT: Record<MemoryDomain, MemoryRisk> = {
  session: "auto",
  durable: "auto",
  facts: "ask",
  projects: "auto",
  preferences: "auto",
  artifacts: "ask",
};
const MEMORY_RETENTION_DEFAULT: Record<MemoryDomain, number | null> = {
  session: null,
  durable: 30,
  facts: null,
  projects: null,
  preferences: null,
  artifacts: null,
};
const MEMORY_DOMAIN_COPY: Record<
  MemoryDomain,
  { title: string; hint: string }
> = {
  session: {
    title: "Session",
    hint: "Turn-by-turn within one session. Cleared on session end.",
  },
  durable: {
    title: "Durable",
    hint: "Recent conversation across sessions. Rolling 30-day window by default.",
  },
  facts: {
    title: "Facts",
    hint: "User-provided facts (name, preferences, domain vocab). User-sensitive.",
  },
  projects: {
    title: "Projects",
    hint: "Named project scopes + notes the user pinned.",
  },
  preferences: {
    title: "Preferences",
    hint: "Per-user tuning (timezone, style, interaction defaults).",
  },
  artifacts: {
    title: "Artifacts",
    hint: "Files, URLs, and code snippets the user pinned. User-sensitive.",
  },
};

const MEMORY_RISKS: MemoryRisk[] = ["auto", "ask", "deny"];
const MEMORY_RISK_COPY: Record<
  MemoryRisk,
  { label: string; color: string }
> = {
  auto: { label: "Auto", color: "text-aether-ok" },
  ask: { label: "Ask", color: "text-aether-warn" },
  deny: { label: "Deny", color: "text-aether-err" },
};

/**
 * One row of the Memory domain policy list. Mirrors `PermissionRow`
 * visually so the two surfaces read as siblings. Retention appears
 * as a read-only hint in v1 — editing retention days lands in a
 * later Memory V2 slice along with the sweep.
 *
 * Memory V2 step 2.
 */
function MemoryRiskRow({
  domain,
  risk,
  retention,
  busy,
  onChange,
}: {
  domain: MemoryDomain;
  risk: MemoryRisk;
  retention: number | null;
  busy: boolean;
  onChange: (next: MemoryRisk) => void;
}) {
  const meta = MEMORY_DOMAIN_COPY[domain];
  const retentionLabel =
    retention === null || retention === 0
      ? "kept until forgotten"
      : `retained ${retention} day${retention === 1 ? "" : "s"}`;
  return (
    <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[13px] font-medium text-aether-text">
          {meta.title}
        </div>
        <div className={`text-[11px] ${MEMORY_RISK_COPY[risk].color}`}>
          {MEMORY_RISK_COPY[risk].label}
        </div>
      </div>
      <p className="mt-1 text-[11.5px] text-aether-muted">{meta.hint}</p>
      <div
        role="radiogroup"
        aria-label={`${meta.title} write policy`}
        className="mt-3 flex gap-2"
      >
        {MEMORY_RISKS.map((r) => {
          const active = r === risk;
          return (
            <button
              key={r}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(r)}
              disabled={busy}
              className={`flex-1 rounded-md px-2 py-1.5 text-[11.5px] transition-colors ${
                active
                  ? "border border-aether-borderHi bg-aether-elevated text-aether-text"
                  : "border border-aether-border bg-transparent text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
              } ${busy ? "opacity-60" : ""}`}
            >
              {MEMORY_RISK_COPY[r].label}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-aether-dim">{retentionLabel}</p>
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

/**
 * Editable threshold row — replaces the Presence V1 step 1 read-only
 * line. Two inputs with inline validation against the same bounds the
 * Rust `set_presence_config` enforces (10–86400 s, away > idle). Only
 * commits to the backend when Apply is pressed — avoids a round trip
 * per keystroke and lets the user type freely through transient
 * invalid states (e.g. typing "30" on the way to "300").
 *
 * Presence V1 step 2.
 */
function ThresholdEditor({
  presence,
  busy,
  onCommit,
  onError,
}: {
  presence: PresenceConfig;
  busy: boolean;
  onCommit: (patch: Partial<PresenceConfig>) => Promise<void>;
  onError: (msg: string | null) => void;
}) {
  const [idle, setIdle] = useState<string>(String(presence.idle_after_s));
  const [away, setAway] = useState<string>(String(presence.away_after_s));
  const [localErr, setLocalErr] = useState<string | null>(null);

  // Keep the text inputs in sync when presence comes back from the
  // backend (e.g. after a successful Apply the Rust side may have
  // sanitised our numbers). Only re-seed when the persisted values
  // actually changed so we don't trample mid-edit typing.
  useEffect(() => {
    setIdle(String(presence.idle_after_s));
    setAway(String(presence.away_after_s));
  }, [presence.idle_after_s, presence.away_after_s]);

  const idleNum = Number(idle);
  const awayNum = Number(away);
  const idleValid =
    Number.isInteger(idleNum) &&
    idleNum >= PRESENCE_THRESHOLD_MIN_S &&
    idleNum <= PRESENCE_THRESHOLD_MAX_S;
  const awayValid =
    Number.isInteger(awayNum) &&
    awayNum >= PRESENCE_THRESHOLD_MIN_S &&
    awayNum <= PRESENCE_THRESHOLD_MAX_S;
  const orderValid = awayNum > idleNum;
  const allValid = idleValid && awayValid && orderValid;
  const dirty =
    idleNum !== presence.idle_after_s || awayNum !== presence.away_after_s;

  const validationMessage = (() => {
    if (!idleValid)
      return `Active → Idle must be an integer between ${PRESENCE_THRESHOLD_MIN_S} and ${PRESENCE_THRESHOLD_MAX_S} seconds.`;
    if (!awayValid)
      return `Idle → Away must be an integer between ${PRESENCE_THRESHOLD_MIN_S} and ${PRESENCE_THRESHOLD_MAX_S} seconds.`;
    if (!orderValid)
      return "Idle → Away must be greater than Active → Idle.";
    return null;
  })();

  const apply = async () => {
    if (!allValid) {
      setLocalErr(validationMessage);
      return;
    }
    setLocalErr(null);
    onError(null);
    await onCommit({ idle_after_s: idleNum, away_after_s: awayNum });
  };

  const reset = () => {
    setIdle(String(presence.idle_after_s));
    setAway(String(presence.away_after_s));
    setLocalErr(null);
  };

  return (
    <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3">
      <div className="text-[12px] font-medium text-aether-text">
        Thresholds
      </div>
      <p className="mt-1 text-[11.5px] text-aether-muted">
        How long of no keyboard / mouse activity before Companion considers
        you Idle, then Away. Seconds; {PRESENCE_THRESHOLD_MIN_S}–
        {PRESENCE_THRESHOLD_MAX_S}.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1 text-[11.5px] text-aether-muted">
          <span>Active → Idle (s)</span>
          <input
            type="number"
            inputMode="numeric"
            min={PRESENCE_THRESHOLD_MIN_S}
            max={PRESENCE_THRESHOLD_MAX_S}
            step={1}
            value={idle}
            onChange={(e) => setIdle(e.target.value)}
            disabled={busy}
            aria-invalid={!idleValid}
            className={`rounded-md border bg-aether-surface px-2 py-1.5 font-mono text-[12px] text-aether-text focus:border-aether-borderHi focus:outline-none ${
              idleValid
                ? "border-aether-border"
                : "border-aether-err/60"
            }`}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11.5px] text-aether-muted">
          <span>Idle → Away (s)</span>
          <input
            type="number"
            inputMode="numeric"
            min={PRESENCE_THRESHOLD_MIN_S}
            max={PRESENCE_THRESHOLD_MAX_S}
            step={1}
            value={away}
            onChange={(e) => setAway(e.target.value)}
            disabled={busy}
            aria-invalid={!awayValid || !orderValid}
            className={`rounded-md border bg-aether-surface px-2 py-1.5 font-mono text-[12px] text-aether-text focus:border-aether-borderHi focus:outline-none ${
              awayValid && orderValid
                ? "border-aether-border"
                : "border-aether-err/60"
            }`}
          />
        </label>
      </div>
      {(validationMessage || localErr) && (
        <p className="mt-2 text-[11px] text-aether-err">
          {localErr ?? validationMessage}
        </p>
      )}
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={apply}
          disabled={!allValid || !dirty || busy}
          className={`rounded-md border px-2.5 py-1 text-[11px] transition-colors ${
            !allValid || !dirty || busy
              ? "border-aether-border bg-transparent text-aether-muted opacity-60"
              : "border-aether-ok/60 bg-aether-ok/10 text-aether-ok hover:border-aether-ok"
          }`}
        >
          Apply
        </button>
        <button
          type="button"
          onClick={reset}
          disabled={!dirty || busy}
          className="rounded-md border border-aether-border bg-transparent px-2.5 py-1 text-[11px] text-aether-muted hover:border-aether-borderHi hover:text-aether-text disabled:opacity-60"
        >
          Reset
        </button>
        <span className="ml-auto text-[11px] text-aether-dim">
          Saved: {presence.idle_after_s}s / {presence.away_after_s}s
        </span>
      </div>
    </div>
  );
}

type AutonomyChoice = "observer" | "assistant" | "operator" | "later";

const AUTONOMY_CHOICES: {
  id: AutonomyChoice;
  label: string;
  hint: string;
  color: string;
}[] = [
  {
    id: "observer",
    label: "Observer",
    hint: "Read-only — watches and answers, never acts.",
    color: "text-aether-ok",
  },
  {
    id: "assistant",
    label: "Assistant",
    hint: "Helps with files, asks before anything risky. Recommended.",
    color: "text-aether-text",
  },
  {
    id: "operator",
    label: "Operator",
    hint: "Acts within pre-approved folders after explicit grants.",
    color: "text-aether-warn",
  },
  {
    id: "later",
    label: "No override",
    hint: "Persona-adjusted defaults only — no extra overlay.",
    color: "text-aether-dim",
  },
];

function autonomyChoiceFromBackend(value: string | null): AutonomyChoice {
  // Backend reports the *active overlay* — null means no overlay (i.e.
  // baseline persona-adjusted Assistant). The frontend wire-string
  // contract from the onboarding picker (`later`) is *not* what the
  // backend round-trips, so we map null → "later" for UX consistency.
  if (value === "observer" || value === "assistant" || value === "operator")
    return value;
  return "later";
}

/**
 * Post-onboarding autonomy preset row — mirrors the onboarding
 * `PresetPicker` but inline in Settings so the user can change posture
 * after first run. The backend `set_autonomy_preset` is idempotent;
 * passing `null` clears the overlay (Assistant baseline).
 *
 * T2.3 — autonomy preset picker UI.
 */
function AutonomyRow({
  value,
  busy,
  onChange,
}: {
  value: string | null;
  busy: boolean;
  onChange: (next: string | null) => void;
}) {
  const active = autonomyChoiceFromBackend(value);
  const activeMeta = AUTONOMY_CHOICES.find((c) => c.id === active)!;
  return (
    <div className="rounded-md border border-aether-border bg-aether-elevated/40 px-3 py-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[13px] font-medium text-aether-text">
          Active preset
        </div>
        <div className={`text-[11px] ${activeMeta.color}`}>
          {activeMeta.label}
        </div>
      </div>
      <p className="mt-1 text-[11.5px] text-aether-muted">
        {activeMeta.hint}
      </p>
      <div
        role="radiogroup"
        aria-label="Autonomy preset"
        className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        {AUTONOMY_CHOICES.map((c) => {
          const selected = c.id === active;
          return (
            <button
              key={c.id}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(c.id === "later" ? null : c.id)}
              disabled={busy}
              title={c.hint}
              className={`rounded-md px-2 py-1.5 text-[11.5px] transition-colors ${
                selected
                  ? "border border-aether-borderHi bg-aether-elevated text-aether-text"
                  : "border border-aether-border bg-transparent text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
              } ${busy ? "opacity-60" : ""}`}
            >
              {c.label}
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-aether-dim">
        Power User and Custom presets are not yet available — they require
        capability-axis controls that land in a later slice.
      </p>
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
