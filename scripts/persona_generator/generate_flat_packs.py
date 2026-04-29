"""Generate v0 flat-schema persona pack YAMLs from the rich cast yaml files.

The runtime pack loader (`packages/l6-persona/src/pack_loader.rs`) accepts
flat YAML files with the v0 schema (id/version/name/description + tone/
verbosity/stance/humor dials) and rejects unknown fields. The 9-persona
cast under `personas/<slug>/persona.yaml` uses a richer schema
(display_name/tagline/personality.archetype/personality.system_prompt/
voice_descriptors/etc.) which the loader can't read.

This script bridges the gap by emitting a v0-compatible flat YAML per
cast member, baking the hand-authored system_prompt into the
`description` field so the persona's voice survives the compiler. The
`tone`/`verbosity`/`stance`/`humor` dials are creator-locked per
archetype below — see PERSONA_DIAL_PICKS for the rationale.

Output goes to `apps/desktop/src-tauri/resources/personas/<slug>.yaml`,
which the desktop installer bundles as a Tauri resource. The shell
seeds `<app_data>/personas/` from these on first boot so the live
persona catalog grows from 3 (built-in) to 12 (built-in + 9 cast,
minus aurora collision).

Aurora is intentionally skipped — the built-in `default_catalog()`
hard-codes aurora's profile and the loader rejects YAML collisions
(see `merge_yaml_personas` in state.rs). The cast aurora's prompt
fidelity is already approximated by the built-in.

Usage: `python scripts/persona_generator/generate_flat_packs.py`
       (run from the repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CAST_DIR = REPO_ROOT / "personas"
OUT_DIR = REPO_ROOT / "apps" / "desktop" / "src-tauri" / "resources" / "personas"

# Creator-locked dials per cast member.
#
# Tone:      Formal | Neutral | Warm
# Verbosity: Terse  | Balanced | Verbose
# Stance:    Cautious | Balanced | Bold
# Humor:     Dry | Occasional | Playful
#
# Picks are guided by the persona's archetype + the voice register the
# hand-authored system_prompt establishes. Loose mapping:
#   - "warm uncle / kitchen-table" → Warm tone
#   - "constraint-first engineer / skeptic" → Neutral tone, Bold stance
#   - "executive at altitude" → Formal tone
#   - "field commander / Brooklyn PM" → Neutral tone, Terse, Bold
#   - "depth researcher with PhD" → Formal, Verbose, Cautious
#
# These compose with the LLM-side system_prompt rather than fighting
# it: the auto-appended "Voice: <tone> <verbosity> <humor>" line lands
# after the hand-authored prompt and reinforces register without
# replacing it.
PERSONA_DIAL_PICKS = {
    "marcus_chen":     ("neutral", "balanced", "bold",     "dry"),
    "sara_reyes":      ("warm",    "balanced", "bold",     "playful"),
    "james_whitfield": ("warm",    "balanced", "balanced", "dry"),
    "nadia_volkov":    ("neutral", "balanced", "bold",     "dry"),
    "priya_iyer":      ("formal",  "balanced", "balanced", "occasional"),
    "ray_castellano":  ("neutral", "terse",    "bold",     "dry"),
    "hannah_park":     ("formal",  "verbose",  "cautious", "dry"),
    "tomas_andrade":   ("warm",    "balanced", "bold",     "occasional"),
}


def parse_persona_yaml(path: Path) -> dict[str, str]:
    """Pull the four fields we need from a cast persona.yaml.

    Returns id, display_name, tagline, system_prompt. We avoid pyyaml so
    the script has zero deps — the schema is small and well-formed
    enough to hand-parse.
    """
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}

    for line in text.splitlines():
        s = line.lstrip()
        for key in ("id:", "display_name:", "tagline:"):
            if s.startswith(key) and key not in out:
                value = s[len(key):].strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                out[key.rstrip(":")] = value

    # Block scalar `system_prompt: |` — collect indented lines until
    # the next sibling key or end of block.
    lines = text.splitlines()
    sp_lines: list[str] = []
    in_block = False
    block_indent = None
    for line in lines:
        if not in_block:
            if line.lstrip().startswith("system_prompt:") and line.rstrip().endswith("|"):
                in_block = True
                continue
            continue
        if line.strip() == "":
            sp_lines.append("")
            continue
        # Indent = whitespace count
        indent = len(line) - len(line.lstrip())
        if block_indent is None:
            block_indent = indent
        if indent < block_indent:
            break
        sp_lines.append(line[block_indent:])
    if sp_lines:
        out["system_prompt"] = "\n".join(sp_lines).rstrip() + "\n"

    return out


def emit_flat_yaml(slug: str, parsed: dict[str, str]) -> str:
    """Render a v0-compatible flat YAML for the pack loader."""
    tone, verbosity, stance, humor = PERSONA_DIAL_PICKS[slug]
    name = parsed.get("display_name", slug)
    description = parsed.get("system_prompt", parsed.get("tagline", ""))
    description = description.replace("\\", "\\\\").replace('"', '\\"')

    # Use a YAML block scalar (`|`) for description so multi-line
    # prompts survive. Indent body by 2 spaces — pack_loader uses
    # serde_yaml which honours the `|` scalar.
    indented = "\n".join("  " + line for line in description.splitlines()) or "  "

    return (
        f"# Auto-generated from personas/{slug}/persona.yaml.\n"
        f"# Edit the canonical rich yaml + re-run scripts/persona_generator/generate_flat_packs.py\n"
        f"# rather than editing this file by hand.\n"
        f"\n"
        f'id: "{parsed["id"]}"\n'
        f"version: 1\n"
        f'name: "{name}"\n'
        f"description: |\n"
        f"{indented}\n"
        f'tone: "{tone}"\n'
        f'verbosity: "{verbosity}"\n'
        f'stance: "{stance}"\n'
        f'humor: "{humor}"\n'
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = []
    for slug in PERSONA_DIAL_PICKS:
        src = CAST_DIR / slug / "persona.yaml"
        if not src.exists():
            skipped.append((slug, "missing persona.yaml"))
            continue
        parsed = parse_persona_yaml(src)
        if "id" not in parsed or "system_prompt" not in parsed:
            skipped.append((slug, f"parse incomplete: keys={sorted(parsed)}"))
            continue
        out_path = OUT_DIR / f"{slug}.yaml"
        out_path.write_text(emit_flat_yaml(slug, parsed), encoding="utf-8")
        written += 1
        print(f"[ok] {slug} -> {out_path.relative_to(REPO_ROOT)}")

    if skipped:
        print(f"\nSkipped {len(skipped)}:")
        for slug, why in skipped:
            print(f"  - {slug}: {why}")

    print(f"\nWrote {written} flat persona packs to {OUT_DIR.relative_to(REPO_ROOT)}/")
    return 0 if written > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
