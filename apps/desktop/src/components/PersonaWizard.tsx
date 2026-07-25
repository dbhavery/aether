import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import {
  loadPersonaPreviews,
  previewAssetUrl,
  type PersonaPreview,
} from "../lib/personaPreviews";

/**
 * Onboarding wizard — picks one of the 9 v0 cast personas before the
 * conversation UI is reachable. Reads the bundled Tier-1 previews
 * (preview.webp + preview_voice.opus + tagline/archetype yaml fields)
 * via `/personas-previews/index.json`. No network round-trip required.
 *
 * Per ADR-0012 §7, this is the first step in the onboarding flow:
 *   - Show 9 cards (thumb + name + tagline + archetype tag)
 *   - Hover/click a card → play that persona's 3-second voice clip
 *   - Click "Choose" on a card → move to confirmation step
 *   - Confirmation step → mocks the Tier-2 download until the L6
 *     install backend lands (coordinator-gated work)
 *
 * The "commit" handler is provided by the parent so this component
 * stays decoupled from the App's persistence + state machine.
 */
export interface PersonaWizardProps {
  /** Called when the user confirms a persona pick. */
  onCommit: (slug: string) => void;
  /**
   * Restrict the rendered cast to slugs the backend persona catalog
   * can actually deliver. When omitted, every preview from the bundled
   * index renders — useful for standalone tests. When provided, only
   * the intersection is shown so the user can never pick a persona
   * that `switchPersona` would reject. The cast preview catalog is
   * frozen at 9 today; the backend's live catalog grows as
   * Tier-2 packs install (ADR-0012).
   */
  availableSlugs?: readonly string[];
}

type Step = "pick" | "confirm";

export function PersonaWizard({ onCommit, availableSlugs }: PersonaWizardProps) {
  const [step, setStep] = useState<Step>("pick");
  const [personas, setPersonas] = useState<PersonaPreview[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [playingSlug, setPlayingSlug] = useState<string | null>(null);
  // Roving-tabindex focus pointer — index into `visiblePersonas`. Only
  // the focused card has `tabIndex=0`; the rest are `-1` so Tab moves
  // through the wizard rather than each individual card.
  const [focusIdx, setFocusIdx] = useState(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cardRefs = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    let cancelled = false;
    loadPersonaPreviews()
      .then((data) => {
        if (!cancelled) setPersonas(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err.message ?? String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const visiblePersonas = useMemo(() => {
    if (!personas) return null;
    if (!availableSlugs) return personas;
    const allow = new Set(availableSlugs);
    return personas.filter((p) => allow.has(p.slug));
  }, [personas, availableSlugs]);

  const selected = useMemo(
    () =>
      selectedSlug && visiblePersonas
        ? visiblePersonas.find((p) => p.slug === selectedSlug) ?? null
        : null,
    [selectedSlug, visiblePersonas],
  );

  function playPreview(p: PersonaPreview) {
    // Stop the previous clip cleanly so two cards can't overlap.
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    const audio = new Audio(previewAssetUrl(p.preview_voice_opus));
    audio.onended = () => {
      setPlayingSlug((cur) => (cur === p.slug ? null : cur));
    };
    audioRef.current = audio;
    setPlayingSlug(p.slug);
    void audio.play().catch(() => {
      // Autoplay can fail if the user hasn't interacted yet. Reset
      // the playing indicator so the UI doesn't lie.
      setPlayingSlug((cur) => (cur === p.slug ? null : cur));
    });
  }

  function selectPersona(p: PersonaPreview) {
    setSelectedSlug(p.slug);
    playPreview(p);
  }

  // Roving-tabindex grid keyboard handler. Arrow keys move focus
  // linearly; Home/End jump to first/last; Enter picks the focused
  // card (browsers fire native click on the button so we don't need
  // a separate keydown→select branch). Vertical arrows alias to
  // horizontal — the grid reflows responsively (1/2/3 cols), so
  // computing a real "row above" requires layout introspection
  // jsdom can't do anyway. Linear traversal is the conservative
  // choice and matches how most users navigate small grids.
  const onGridKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      const list = cardRefs.current;
      const len = list.length;
      if (len === 0) return;
      let next: number | null = null;
      switch (e.key) {
        case "ArrowRight":
        case "ArrowDown":
          next = (focusIdx + 1) % len;
          break;
        case "ArrowLeft":
        case "ArrowUp":
          next = (focusIdx - 1 + len) % len;
          break;
        case "Home":
          next = 0;
          break;
        case "End":
          next = len - 1;
          break;
        default:
          return;
      }
      e.preventDefault();
      setFocusIdx(next);
      list[next]?.focus();
    },
    [focusIdx],
  );

  if (loadError) {
    return (
      <div
        role="alert"
        className="mx-auto mt-24 max-w-md rounded-lg border border-aether-border bg-aether-bg p-6 text-aether-text"
      >
        <h2 className="text-[15px] font-medium">Couldn't load companions</h2>
        <p className="mt-2 text-[13px] text-aether-muted">{loadError}</p>
        <p className="mt-4 text-[12px] text-aether-dim">
          The wizard expects a bundled persona preview index at
          /personas-previews/index.json. If this is a dev build, run:
          <code className="ml-1 font-mono text-aether-text">
            python tools/build-persona-previews/build.py
          </code>
        </p>
      </div>
    );
  }

  if (!personas || !visiblePersonas) {
    return (
      <div className="mx-auto mt-24 max-w-md text-center text-[13px] text-aether-muted">
        Loading companions…
      </div>
    );
  }

  if (visiblePersonas.length === 0) {
    // The bundled previews were filtered down to nothing — typically
    // means the backend persona catalog hasn't been populated yet
    // (e.g. ADR-0012 Tier-2 install hasn't run for any cast member).
    // Surface this honestly instead of rendering a ghost grid.
    return (
      <div
        role="alert"
        className="mx-auto mt-24 max-w-md rounded-lg border border-aether-border bg-aether-bg p-6 text-aether-text"
      >
        <h2 className="text-[15px] font-medium">No companions available yet</h2>
        <p className="mt-2 text-[13px] text-aether-muted">
          Your installation doesn't have any companion packs ready. Once
          a pack is installed, the wizard will list it here.
        </p>
      </div>
    );
  }

  if (step === "confirm" && selected) {
    return (
      <div className="mx-auto mt-16 max-w-lg px-6">
        <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
          Confirm
        </div>
        <h1 className="mt-1 text-[20px] font-medium text-aether-text">
          You picked {selected.display_name}
        </h1>
        <p className="mt-3 text-[13px] leading-relaxed text-aether-muted">
          {selected.tagline}
        </p>
        <div className="mt-6 rounded-lg border border-aether-border bg-aether-elevated p-4">
          <p className="text-[12px] text-aether-muted">
            {selected.display_name}'s full pack (~10–13 MB) will download.
            Subsequent conversations stay offline.
          </p>
          <p className="mt-2 text-[11px] text-aether-dim">
            You can change companions later in Settings. Your conversation
            history and memory are preserved across switches.
          </p>
        </div>
        <div className="mt-6 flex gap-3">
          <button
            type="button"
            className="rounded-md border border-aether-border px-3 py-1.5 text-[12px] text-aether-muted hover:border-aether-text hover:text-aether-text"
            onClick={() => setStep("pick")}
          >
            Back
          </button>
          <button
            type="button"
            className="rounded-md border border-aether-accent bg-aether-accent/10 px-4 py-1.5 text-[12px] font-medium text-aether-accent hover:bg-aether-accent/20"
            onClick={() => onCommit(selected.slug)}
          >
            Continue with {selected.display_name.split(" ")[0]}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="text-center">
        <div className="text-[11px] uppercase tracking-[0.18em] text-aether-dim">
          Pick your companion
        </div>
        <h1 className="mt-2 text-[22px] font-medium text-aether-text">
          {visiblePersonas.length === 1
            ? "Meet your companion"
            : "Distinct voices, distinct registers"}
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-[13px] leading-relaxed text-aether-muted">
          {visiblePersonas.length === 1
            ? "Your installation ships with one companion ready to talk. More arrive as their packs install."
            : "Each is a distinct character with their own voice, presence, and way of thinking. Tap a card to hear them speak. You'll stick with one — though you can switch later."}
        </p>
      </div>

      <div
        role="grid"
        aria-label="Companion picker"
        onKeyDown={onGridKeyDown}
        className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {visiblePersonas.map((p, i) => {
          const isSelected = selectedSlug === p.slug;
          const isPlaying = playingSlug === p.slug;
          return (
            <button
              key={p.slug}
              type="button"
              ref={(el) => {
                cardRefs.current[i] = el;
              }}
              tabIndex={i === focusIdx ? 0 : -1}
              onClick={() => {
                setFocusIdx(i);
                selectPersona(p);
              }}
              onFocus={() => setFocusIdx(i)}
              aria-pressed={isSelected}
              aria-label={`Pick ${p.display_name}`}
              className={[
                "group relative flex flex-col overflow-hidden rounded-lg border text-left motion-safe:transition-all",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-aether-accent focus-visible:ring-offset-2 focus-visible:ring-offset-aether-bg",
                isSelected
                  ? "border-aether-accent bg-aether-elevated shadow-lg"
                  : "border-aether-border bg-aether-bg hover:border-aether-text/40 hover:bg-aether-elevated",
              ].join(" ")}
            >
              <div className="aspect-square w-full overflow-hidden bg-aether-elevated">
                <img
                  src={previewAssetUrl(p.preview_webp)}
                  alt={`${p.display_name} portrait`}
                  className="h-full w-full object-cover"
                  loading="lazy"
                />
              </div>
              <div className="flex flex-col gap-1.5 p-4">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-[14px] font-medium text-aether-text">
                    {p.display_name}
                  </h2>
                  <span
                    className="font-mono text-[10px] uppercase tracking-wider text-aether-dim"
                    aria-label={`archetype ${p.archetype}`}
                  >
                    {p.archetype.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-[12px] leading-relaxed text-aether-muted">
                  {p.tagline}
                </p>
                {isPlaying && (
                  <span
                    className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-aether-accent"
                    aria-live="polite"
                    aria-label="Voice preview playing"
                  >
                    {/* Animated 3-bar VU indicator. Bars scale on the
                     * Y axis via Tailwind's `animate-[*]` arbitrary
                     * value; `motion-safe:` gates the keyframes so
                     * users with prefers-reduced-motion get a static
                     * trio of bars instead of a pulsing one. */}
                    <span
                      aria-hidden="true"
                      className="inline-flex h-3 items-end gap-[2px]"
                    >
                      <span className="block h-full w-[2px] origin-bottom rounded-sm bg-aether-accent motion-safe:animate-wizardBar" />
                      <span className="block h-full w-[2px] origin-bottom rounded-sm bg-aether-accent motion-safe:animate-wizardBar motion-safe:[animation-delay:0.15s]" />
                      <span className="block h-full w-[2px] origin-bottom rounded-sm bg-aether-accent motion-safe:animate-wizardBar motion-safe:[animation-delay:0.3s]" />
                    </span>
                    Playing
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      <div className="mt-8 flex justify-end">
        <button
          type="button"
          disabled={!selected}
          className={[
            "rounded-md px-4 py-2 text-[12px] font-medium transition-colors",
            selected
              ? "border border-aether-accent bg-aether-accent/10 text-aether-accent hover:bg-aether-accent/20"
              : "border border-aether-border text-aether-dim",
          ].join(" ")}
          onClick={() => selected && setStep("confirm")}
        >
          {selected ? `Continue with ${selected.display_name}` : "Pick a companion to continue"}
        </button>
      </div>
    </div>
  );
}
