// Post-onboarding persona switcher — T2.4.
//
// Lives inside `SettingsDrawer` as a sibling section to Autonomy,
// Media, Microphone, Presence, and Memory. The onboarding picker
// (`PersonaWizard`) is unchanged; this surface owns the swap path
// users take after first run.
//
// Design notes:
//
// * **Catalog source.** The backend `list_personas` returns every
//   *fully installed* persona (Tier-1 bundled previews that ship with
//   the app + any Tier-2 packs the user has installed via ADR-0012).
//   The bundled preview catalog (`loadPersonaPreviews`) is the
//   superset — it lists every persona the wizard could *show*, even
//   ones whose full pack hasn't been installed yet. The union, with
//   each entry tagged installed/preview-only, is what we render.
// * **Active marker.** The currently active persona id comes from
//   `companion_banner` (the same struct the header uses). On switch
//   we re-fetch the banner so the section's active marker stays
//   consistent with the rest of the UI.
// * **Tier-2 install affordance.** Preview-only entries surface an
//   "Install full pack (~10–13 MB)" button. We resolve the manifest
//   URL with `personaManifestUrl(slug)`; when the registry isn't
//   configured we explain the gap rather than firing a doomed
//   request. After install we auto-switch to the freshly installed
//   slug so the user lands on the persona they asked for.
// * **Memory continuity (ADR-0001).** Memory is user-keyed, not
//   persona-keyed. The backend's `switch_persona` clears only the
//   *session* lane — durable / facts / projects / preferences /
//   artifacts survive. We surface this with a small explainer
//   caption so the user isn't left guessing.
// * **Doctrine §8.** This file is the surface a user-flow vitest
//   exercises end to end; SettingsDrawer.test.tsx pulls the section
//   in via the parent. A live used-as-user click-through against a
//   real Tauri build is still owed before T2.4 ships — the mock
//   covers the contract but not the visual / latency feel.

import { useEffect, useMemo, useState } from "react";

import {
  companionBanner,
  installPersona,
  listPersonas,
  personaManifestUrl,
  switchPersona,
} from "../lib/api";
import {
  loadPersonaPreviews,
  previewAssetUrl,
  type PersonaPreview,
} from "../lib/personaPreviews";
import type { PersonaCatalogEntry } from "../lib/types";

/** One row in the rendered list. */
interface PersonaRow {
  slug: string;
  display_name: string;
  tagline: string | null;
  preview_webp: string | null;
  /** True when the backend `list_personas` carries this slug — i.e.
   * the full pack is on disk and `switch_persona` will accept it. */
  installed: boolean;
}

/** Merge backend catalog + bundled previews into a single render list. */
function buildRows(
  catalog: PersonaCatalogEntry[],
  previews: PersonaPreview[],
): PersonaRow[] {
  const previewBySlug = new Map(previews.map((p) => [p.slug, p]));
  const catalogSlugs = new Set(catalog.map((c) => c.id));
  const rows: PersonaRow[] = [];

  // Installed first, in catalog order.
  for (const c of catalog) {
    const prev = previewBySlug.get(c.id);
    rows.push({
      slug: c.id,
      display_name: c.name,
      tagline: c.tagline || prev?.tagline || null,
      preview_webp: prev?.preview_webp ?? null,
      installed: true,
    });
  }

  // Then preview-only, in preview-index order.
  for (const p of previews) {
    if (catalogSlugs.has(p.slug)) continue;
    rows.push({
      slug: p.slug,
      display_name: p.display_name,
      tagline: p.tagline,
      preview_webp: p.preview_webp,
      installed: false,
    });
  }
  return rows;
}

interface Props {
  /** When true, the parent drawer is open — we (re)load the catalog
   * + active persona id. Mirrors how the other sections gate their
   * fetches on the drawer's `open` prop. */
  open: boolean;
}

export function PersonaSection({ open }: Props) {
  const [catalog, setCatalog] = useState<PersonaCatalogEntry[] | null>(null);
  const [previews, setPreviews] = useState<PersonaPreview[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busySlug, setBusySlug] = useState<string | null>(null);
  /** Slug currently being downloaded + installed (Tier-2 path). */
  const [installingSlug, setInstallingSlug] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setErr(null);
    listPersonas()
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    loadPersonaPreviews()
      .then((p) => {
        if (!cancelled) setPreviews(p);
      })
      .catch((e) => {
        // Preview-load failure is non-fatal — the catalog still
        // renders the installed personas. Surface as a soft note.
        if (!cancelled) {
          setPreviews([]);
          // Don't overwrite a hard catalog error.
          setErr((cur) =>
            cur ?? `couldn't load preview index: ${e.message ?? e}`,
          );
        }
      });
    companionBanner()
      .then((b) => {
        if (!cancelled) setActiveId(b.persona_id);
      })
      .catch((e) => {
        if (!cancelled) setErr(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const rows = useMemo(() => {
    if (!catalog || !previews) return null;
    return buildRows(catalog, previews);
  }, [catalog, previews]);

  const handleSwitch = async (slug: string) => {
    if (slug === activeId) return;
    setBusySlug(slug);
    setErr(null);
    try {
      const banner = await switchPersona(slug);
      setActiveId(banner.persona_id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusySlug(null);
    }
  };

  const handleInstall = async (slug: string) => {
    const url = personaManifestUrl(slug);
    if (!url) {
      setErr(
        "Persona registry isn't configured for this build. Set " +
          "VITE_PERSONA_MANIFEST_BASE at build time to enable Tier-2 " +
          "downloads.",
      );
      return;
    }
    setInstallingSlug(slug);
    setErr(null);
    try {
      await installPersona(slug, url);
      // Refresh the catalog so the row flips installed=true.
      const updated = await listPersonas();
      setCatalog(updated);
      // Auto-switch — the user just asked for this persona.
      const banner = await switchPersona(slug);
      setActiveId(banner.persona_id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setInstallingSlug(null);
    }
  };

  return (
    <section
      aria-labelledby="settings-persona-heading"
      className="mt-6 border-t border-aether-border pt-4"
    >
      <h2
        id="settings-persona-heading"
        className="text-[11px] uppercase tracking-[0.18em] text-aether-dim"
      >
        Persona
      </h2>
      <p className="mt-1 text-[12px] text-aether-muted">
        Pick which companion you talk to. Your memory stays with you across
        personas — only the voice, name, and stance change.
      </p>

      {err && (
        <div
          role="alert"
          className="mt-3 rounded-md border border-aether-err/40 bg-aether-err/5 px-3 py-2 text-[11.5px] text-aether-err"
        >
          {err}
        </div>
      )}

      {/* Hide the "Loading…" line once an error has surfaced — otherwise
       * the catalog stays null forever and the user sees a perpetual
       * loading spinner above the error banner. Doctrine §8 used-as-user
       * verify caught this 2026-04-30. */}
      {!rows && !err && (
        <p className="mt-4 text-[11.5px] text-aether-dim">Loading personas…</p>
      )}

      {rows && rows.length === 0 && (
        <p className="mt-4 text-[11.5px] text-aether-dim">
          No personas available.
        </p>
      )}

      {rows && rows.length > 0 && (
        <ul
          role="radiogroup"
          aria-label="Active persona"
          className="mt-4 flex flex-col gap-2"
        >
          {rows.map((r) => {
            const active = r.slug === activeId;
            const busy = busySlug === r.slug;
            const installing = installingSlug === r.slug;
            return (
              <li
                key={r.slug}
                className={`rounded-md border bg-aether-elevated/40 px-3 py-3 ${
                  active
                    ? "border-aether-borderHi"
                    : "border-aether-border"
                }`}
              >
                <div className="flex items-start gap-3">
                  {r.preview_webp && (
                    <img
                      src={previewAssetUrl(r.preview_webp)}
                      alt=""
                      aria-hidden="true"
                      className="h-12 w-12 flex-none rounded-md object-cover"
                      loading="lazy"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-3">
                      <div className="text-[13px] font-medium text-aether-text">
                        {r.display_name}
                      </div>
                      {active && (
                        <span
                          className="text-[11px] text-aether-ok"
                          aria-label="active persona"
                        >
                          Active
                        </span>
                      )}
                      {!active && !r.installed && (
                        <span className="text-[11px] text-aether-dim">
                          Preview only
                        </span>
                      )}
                    </div>
                    {r.tagline && (
                      <p className="mt-1 text-[11.5px] text-aether-muted">
                        {r.tagline}
                      </p>
                    )}
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {r.installed ? (
                        <button
                          type="button"
                          role="radio"
                          aria-checked={active}
                          aria-label={
                            active
                              ? `${r.display_name} (active persona)`
                              : `Switch to ${r.display_name}`
                          }
                          onClick={() => handleSwitch(r.slug)}
                          disabled={active || busy}
                          className={`rounded-md border px-2.5 py-1 text-[11px] transition-colors ${
                            active
                              ? "border-aether-ok/60 bg-aether-ok/10 text-aether-ok"
                              : "border-aether-border bg-transparent text-aether-muted hover:border-aether-borderHi hover:text-aether-text"
                          } ${busy ? "opacity-60" : ""}`}
                        >
                          {active ? "Active" : busy ? "Switching…" : "Switch"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleInstall(r.slug)}
                          disabled={installing}
                          className={`rounded-md border border-aether-accent/60 bg-aether-accent/10 px-2.5 py-1 text-[11px] text-aether-accent hover:bg-aether-accent/20 ${
                            installing ? "opacity-60" : ""
                          }`}
                        >
                          {installing
                            ? "Installing…"
                            : "Install full pack (~10–13 MB)"}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <p className="mt-3 text-[11px] text-aether-dim">
        Your memory stays with you across personas.
      </p>
    </section>
  );
}
