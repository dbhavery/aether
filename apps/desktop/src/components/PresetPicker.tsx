import { useState } from "react";

import { setAutonomyPreset } from "../lib/api";

const PRESET_STORAGE_KEY = "aether.onboarding.autonomy-preset";
const PRESET_VERSION_KEY = "aether.onboarding.autonomy-preset.version";
const PRESET_VERSION = "v0-2026-04-21";
// Kept in sync with Disclosure.tsx. The picker only auto-shows once the
// user has acknowledged the welcome disclosure, so we don't stack two
// first-run modals on the same frame.
const DISCLOSURE_STORAGE_KEY = "aether.disclosure.acknowledged";
const DISCLOSURE_VERSION = "v0-2026-04-19";

export type AutonomyPreset = "observer" | "assistant" | "operator";

interface Preset {
  id: AutonomyPreset;
  name: string;
  tagline: string;
  can: string[];
  asks: string[];
  never: string[];
}

const PRESETS: Preset[] = [
  {
    id: "observer",
    name: "Observer",
    tagline: "Read-only — watches and answers, never acts.",
    can: ["Read files you point it at", "Answer questions", "Summarise content"],
    asks: ["Nothing — Observer never takes action"],
    never: ["Write, edit, delete files", "Run shell commands", "Open URLs"],
  },
  {
    id: "assistant",
    name: "Assistant",
    tagline: "Helps with files, asks before anything risky. Recommended.",
    can: ["Read files", "Draft responses and plans"],
    asks: ["Writing, editing, or deleting files", "Opening URLs in a browser"],
    never: ["Run arbitrary shell commands without asking"],
  },
  {
    id: "operator",
    name: "Operator",
    tagline: "Can act within pre-approved folders after explicit grants.",
    can: ["Read files", "Write/edit within approved folders after you grant it"],
    asks: ["First-time file writes", "Browser opens", "Shell commands"],
    never: ["Run shell outside approved scope", "Touch system files"],
  },
];

/**
 * Step-5 autonomy preset picker.
 *
 * Shown on first launch after the welcome disclosure closes. The choice
 * persists in `window.localStorage` alongside the existing disclosure
 * acknowledgement. A versioned key re-shows this card if the preset
 * surface ever changes shape.
 *
 * The backend consumes the selected preset via the
 * `set_autonomy_preset` Tauri command: `EngineConfig::with_preset_overlay`
 * runs after the persona overlay so the user's chosen posture is the
 * final word on which capabilities are Auto / Ask / Deny.
 *
 * "I'll decide later" persists a sentinel so the card doesn't keep
 * re-showing every launch, per onboarding spec §"No dead ends".
 */
export function PresetPicker({
  forceOpen,
  onClose,
}: {
  forceOpen?: boolean;
  onClose?: () => void;
}) {
  const stored =
    typeof window !== "undefined"
      ? window.localStorage.getItem(PRESET_STORAGE_KEY)
      : null;
  const storedVersion =
    typeof window !== "undefined"
      ? window.localStorage.getItem(PRESET_VERSION_KEY)
      : null;
  const disclosureAcked =
    typeof window !== "undefined" &&
    window.localStorage.getItem(DISCLOSURE_STORAGE_KEY) === DISCLOSURE_VERSION;
  const needsPrompt = !stored || storedVersion !== PRESET_VERSION;
  const [open, setOpen] = useState(
    forceOpen ?? (disclosureAcked && needsPrompt),
  );
  const [selected, setSelected] = useState<AutonomyPreset>("assistant");

  if (!open) return null;

  const persist = (value: string) => {
    try {
      window.localStorage.setItem(PRESET_STORAGE_KEY, value);
      window.localStorage.setItem(PRESET_VERSION_KEY, PRESET_VERSION);
    } catch {
      // ignore — worst case we re-prompt next launch
    }
  };

  const choose = () => {
    persist(selected);
    // Push the user's choice to the backend so EngineConfig overlays it
    // on top of the persona-adjusted preset. Fire-and-forget — the
    // overlay is idempotent and the frontend is not blocked on success.
    void setAutonomyPreset(selected).catch((e) => {
      console.warn("set_autonomy_preset failed:", e);
    });
    setOpen(false);
    onClose?.();
  };

  const decideLater = () => {
    persist("later");
    // "Decide later" == no overlay. Clear any prior overlay the backend
    // may still be carrying from an earlier session.
    void setAutonomyPreset(null).catch((e) => {
      console.warn("set_autonomy_preset(null) failed:", e);
    });
    setOpen(false);
    onClose?.();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="preset-picker-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fadeIn"
    >
      <div className="neu-raised mx-6 max-w-xl rounded-xl p-7">
        <h2
          id="preset-picker-title"
          className="text-base font-medium tracking-tight text-aether-text"
        >
          How much autonomy should Companion have?
        </h2>
        <p className="mt-2 text-[12.5px] text-aether-muted">
          Pick a starting posture. You can change it any time in Settings.
        </p>
        <div className="mt-5 flex flex-col gap-2">
          {PRESETS.map((p) => (
            <PresetOption
              key={p.id}
              preset={p}
              selected={selected === p.id}
              onSelect={() => setSelected(p.id)}
            />
          ))}
        </div>
        <PresetDetail preset={PRESETS.find((p) => p.id === selected)!} />
        <div className="mt-6 flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={decideLater}
            className="rounded-md border border-aether-border bg-transparent px-3 py-2 text-[12px] text-aether-muted hover:text-aether-text hover:border-aether-borderHi transition-colors"
          >
            I'll decide later
          </button>
          <button
            type="button"
            onClick={choose}
            className="rounded-md border border-aether-borderHi bg-aether-elevated px-4 py-2 text-[13px] text-aether-text hover:border-aether-text transition-colors"
          >
            Use {PRESETS.find((p) => p.id === selected)!.name}
          </button>
        </div>
      </div>
    </div>
  );
}

function PresetOption({
  preset,
  selected,
  onSelect,
}: {
  preset: Preset;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`flex flex-col items-start rounded-md border px-3 py-2 text-left transition-colors ${
        selected
          ? "border-aether-text bg-aether-elevated"
          : "border-aether-border bg-aether-bg/40 hover:border-aether-borderHi"
      }`}
    >
      <span className="text-[13px] font-medium text-aether-text">
        {preset.name}
      </span>
      <span className="text-[11.5px] text-aether-muted">{preset.tagline}</span>
    </button>
  );
}

function PresetDetail({ preset }: { preset: Preset }) {
  return (
    <div className="mt-4 rounded-md border border-aether-border bg-aether-bg/40 px-3 py-2.5 text-[11.5px] text-aether-muted">
      <DetailLine label="Can" items={preset.can} tone="ok" />
      <DetailLine label="Asks" items={preset.asks} tone="warn" />
      <DetailLine label="Never" items={preset.never} tone="err" />
    </div>
  );
}

function DetailLine({
  label,
  items,
  tone,
}: {
  label: string;
  items: string[];
  tone: "ok" | "warn" | "err";
}) {
  const toneClass =
    tone === "ok"
      ? "text-aether-ok"
      : tone === "warn"
        ? "text-aether-warn"
        : "text-aether-err";
  return (
    <div className="flex gap-2 py-0.5">
      <span className={`w-14 shrink-0 font-mono text-[10.5px] uppercase tracking-wide ${toneClass}`}>
        {label}
      </span>
      <span className="flex-1">{items.join(" · ")}</span>
    </div>
  );
}

/**
 * Read the current persisted autonomy preset. Returns `null` if the user
 * hasn't chosen yet (or chose "decide later") so the caller can decide
 * whether to prompt.
 */
export function readStoredPreset(): AutonomyPreset | "later" | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(PRESET_STORAGE_KEY);
  if (!v) return null;
  if (v === "observer" || v === "assistant" || v === "operator") return v;
  if (v === "later") return "later";
  return null;
}
