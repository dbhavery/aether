"""Tier 1B Aether → Companion rename for governing docs.

Walks the explicit IN-SCOPE file list, applies the rename rules from the
coordinator prompt, preserves codename `aether` (lowercase), Cargo crate names,
DB filenames, Tauri identifier, env vars, Tailwind class names, and historical
phrases. Skips content inside fenced code blocks.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ---------- IN-SCOPE FILE LIST ----------
IN_SCOPE_RELATIVE: list[str] = [
    # planning numbered specs (03–18) + index docs
    "planning/03_vision_and_thesis.md",
    "planning/04_user_modes.md",
    "planning/05_ux_principles.md",
    "planning/06_onboarding_spec.md",
    "planning/07_tutorial_help_system.md",
    "planning/08_system_architecture.md",
    "planning/09_realtime_interaction.md",
    "planning/10_memory_architecture.md",
    "planning/11_avatar_presence.md",
    "planning/12_permissions_autonomy.md",
    "planning/13_trust_security_redteam.md",
    "planning/14_performance_tiers_vram.md",
    "planning/15_updates_releases.md",
    "planning/16_tech_stack.md",
    "planning/17_persona_pack_schema.md",
    "planning/18_model_router_spec.md",
    "planning/MASTER_OUTLINE_TREE.md",
    "planning/NUMBERED_SPEC.md",
    "planning/COMPARISON_REPORT.md",
    "planning/sources_matrix.md",
    "planning/OPEN_QUESTIONS.md",
    "planning/README.md",
    # plans/
    "planning/plans/00_ORCHESTRATION_MAP.md",
    "planning/plans/01_pro_phase_crosswalk.md",
    "planning/plans/02_oss_preview_alignment_map.md",
    "planning/plans/03_content_lock_v1_port.md",
    "planning/plans/IMPLEMENTATION_PREP_INDEX.md",
    # L*_* in plans (excluding L3 — Session 3 owns it)
    "planning/plans/L1_interaction_timing.md",
    "planning/plans/L1_interaction_timing_system_design.md",
    "planning/plans/L1_L4_L5_L7_integration_notes.md",
    "planning/plans/L2_memory_kernel.md",
    "planning/plans/L2_memory_kernel_system_design.md",
    "planning/plans/L2_L3_L6_integration_notes.md",
    "planning/plans/L4_model_router.md",
    "planning/plans/L4_model_router_system_design.md",
    "planning/plans/L5_policy_engine.md",
    "planning/plans/L5_policy_engine_system_design.md",
    "planning/plans/L6_persona_compiler.md",
    "planning/plans/L6_persona_compiler_system_design.md",
    "planning/plans/L7_trust_ux_onboarding.md",
    "planning/plans/L7_trust_ux_onboarding_system_design.md",
    "planning/plans/X3_tauri_architecture.md",
    # implementation_prep (excluding L3_interface_pack — Session 3 owns L3)
    "planning/plans/implementation_prep/L1_interface_pack.md",
    "planning/plans/implementation_prep/L2_interface_pack.md",
    "planning/plans/implementation_prep/L4_interface_pack.md",
    "planning/plans/implementation_prep/L5_interface_pack.md",
    "planning/plans/implementation_prep/L6_interface_pack.md",
    "planning/plans/implementation_prep/L7_interface_pack.md",
    "planning/plans/implementation_prep/event_contracts_master.md",
    "planning/plans/implementation_prep/implementation_handoff_notes.md",
    "planning/plans/implementation_prep/sqlite_schema_pack.md",
    "planning/plans/implementation_prep/test_matrix_master.md",
    # planning/planning
    "planning/planning/monorepo_plan_draft.md",
    # prompts (excluding L3_presence_engine — Session 3 owns L3)
    "planning/prompts/L1_interaction_timing.md",
    "planning/prompts/L2_memory_kernel.md",
    "planning/prompts/L4_model_router.md",
    "planning/prompts/L5_policy_engine.md",
    "planning/prompts/L5_policy_engine_system_design.md",
    "planning/prompts/L6_persona_compiler.md",
    "planning/prompts/L7_trust_ux_onboarding.md",
    "planning/prompts/X1_repo_restructure.md",
    "planning/prompts/X3_tauri_architecture.md",
    "planning/prompts/X4_v1_content_port.md",
    # repo root governance
    "PERSONA_ROADMAP.md",
    "ROADMAP.md",
    "ARCHITECTURE.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "SUPPORT.md",
    # docs/ (excluding QUALITY-EVAL-V1-ARCHITECTURE.md — Session 2 owns it)
    "docs/ARCHITECTURE-V2.md",
    "docs/ARCHITECTURE_DIAGRAM.md",
    "docs/PRODUCT-PLAN.md",
    "docs/REPO_TOUR.md",
    "docs/GLOSSARY.md",
    "docs/DISTRIBUTION.md",
    "docs/ONBOARDING-SPEC.md",
    "docs/PERSONA-SCHEMA.md",
    "docs/LLM-PROVIDERS.md",
    "docs/MEDIA-PERMISSIONS.md",
    "docs/MEMORY-V2-ARCHITECTURE.md",
    "docs/PRESENCE-V1-ARCHITECTURE.md",
    "docs/VOICE-V1-ARCHITECTURE.md",
    "docs/VISION-V1-ARCHITECTURE.md",
    "docs/NFR.md",
    "docs/HF_EMBEDDER.md",
    "docs/posts/show-hn.md",
    "docs/posts/policy-as-load-bearing.md",
]


# ---------- PRESERVATION PATTERNS ----------
# Phrases that contain "Aether" but must be kept verbatim (historical / structural).
# Match BEFORE the rename rules, mask out matches with sentinel tokens, then restore.
PRESERVE_PHRASES = [
    "internal codename Aether",
    "internal codename `Aether`",
    "internal codename `aether`",
    "renamed from Aether",
    "Aether OSS Preview — RETIRED",
    'Aether OSS Preview" — RETIRED',
    '"Aether OSS Preview" — RETIRED',
]

# Tokens with "aether" or "Aether" embedded that must NOT be touched (compound IDs).
# We treat any of these as atomic — if the regex matches one of them, skip.
ATOMIC_PRESERVE_REGEX = re.compile(
    r"""(
        aether-l[0-9][a-z0-9-]* |          # Cargo crate slugs aether-l1-... etc.
        aether-storage |
        aether-event-bus |
        aether-[a-z][a-z0-9-]* |           # any other lowercase aether-foo slug
        aether\.db |
        aether_audit\.db |
        aether_oss_preview |
        aether_pro |
        aether_persona_pack[a-z_]* |
        dev\.aether\.desktop |
        AETHER_[A-Z0-9_]+ |                # env vars
        border-aether-[a-z0-9-]+ |
        text-aether-[a-z0-9-]+ |
        bg-aether-[a-z0-9-]+ |
        ring-aether-[a-z0-9-]+ |
        from-aether-[a-z0-9-]+ |
        to-aether-[a-z0-9-]+ |
        via-aether-[a-z0-9-]+ |
        Projects/aether/[A-Za-z0-9_/.-]* |
        /aether/ |
        `aether` |
        \baether\b                          # bare lowercase aether word
    )""",
    re.VERBOSE,
)

CODE_FENCE_RE = re.compile(r"(```.*?```|`[^`\n]+`)", re.DOTALL)


def mask_protected(text: str) -> tuple[str, list[str]]:
    """Replace code fences, inline code, atomic preserves, and preserve phrases
    with sentinel tokens before running the rename pass."""
    saved: list[str] = []

    def stash(match: re.Match[str]) -> str:
        saved.append(match.group(0))
        return f"\x00MASK{len(saved) - 1}\x00"

    # 1) Code fences and inline code
    text = CODE_FENCE_RE.sub(stash, text)
    # 2) Preserve phrases (case-sensitive, exact)
    for phrase in PRESERVE_PHRASES:
        text = text.replace(phrase, stash(re.match(r".*", phrase)) if False else f"\x00MASK{len(saved)}\x00")
        # The above one-shot approach is awkward; do it cleanly:
    # Redo phrase masking cleanly:
    return text, saved


def mask_clean(text: str) -> tuple[str, list[str]]:
    saved: list[str] = []

    def stash(s: str) -> str:
        saved.append(s)
        return f"\x00MASK{len(saved) - 1}\x00"

    # 1) Code fences + inline code
    def repl_code(m: re.Match[str]) -> str:
        return stash(m.group(0))

    text = CODE_FENCE_RE.sub(repl_code, text)

    # 2) Exact preserve phrases
    for phrase in PRESERVE_PHRASES:
        if phrase in text:
            text = text.replace(phrase, stash(phrase))

    # 3) Atomic preserves (compound identifiers) — done inline during the rename pass via lookahead
    return text, saved


def unmask(text: str, saved: list[str]) -> str:
    def restore(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        return saved[idx]

    return re.sub(r"\x00MASK(\d+)\x00", restore, text)


# ---------- RENAME RULES ----------
# Order matters: longer / more specific phrases first.
RENAME_RULES: list[tuple[re.Pattern[str], str]] = [
    # "Aether OSS Preview" — first occurrence handled per-file with marker
    # (handled separately in apply_rename_to_file)
    # "Aether Pro" → "Companion"
    (re.compile(r"\bAether Pro\b"), "Companion"),
    # "Aether OSS" (not followed by " Preview") → "Companion"
    (re.compile(r"\bAether OSS(?!\s+Preview)\b"), "Companion"),
    # "Aether platform" → "Companion product family"
    (re.compile(r"\bAether platform\b"), "Companion product family"),
    # "Aether product family" → "Companion product family"
    (re.compile(r"\bAether product family\b"), "Companion product family"),
    # "Aether's" → "Companion's"
    (re.compile(r"\bAether's\b"), "Companion's"),
    # Bare "Aether" referring to product → "Companion"
    # (atomic preserves like aether-l1, aether.db etc are lowercase so no match)
    (re.compile(r"\bAether\b"), "Companion"),
]

OSS_PREVIEW_FIRST = re.compile(r"\bAether OSS Preview\b")
OSS_PREVIEW_FIRST_REPLACEMENT = (
    "Companion (OSS Preview wedge thesis retired 2026-05-18 per doctrine §6)"
)


def apply_rename(text: str) -> tuple[str, dict[str, int]]:
    """Apply rename rules. Returns new_text and per-rule replacement counts."""
    counts: dict[str, int] = {}

    masked, saved = mask_clean(text)

    # Handle "Aether OSS Preview" — first match expands, rest become "Companion"
    matches = list(OSS_PREVIEW_FIRST.finditer(masked))
    if matches:
        # Replace from end so positions stay valid
        new_chars = list(masked)
        for i, m in enumerate(reversed(matches)):
            real_idx = len(matches) - 1 - i
            replacement = OSS_PREVIEW_FIRST_REPLACEMENT if real_idx == 0 else "Companion"
            new_chars[m.start() : m.end()] = list(replacement)
        masked = "".join(new_chars)
        counts["Aether OSS Preview (first→tombstoned, rest→Companion)"] = len(matches)

    for pattern, repl in RENAME_RULES:
        masked, n = pattern.subn(repl, masked)
        if n:
            counts[pattern.pattern] = counts.get(pattern.pattern, 0) + n

    text_out = unmask(masked, saved)
    return text_out, counts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--diff-log", default="tools/rename_companion_tier1b_diff.log")
    args = ap.parse_args()

    diff_log_path = REPO / args.diff_log
    diff_log_path.parent.mkdir(parents=True, exist_ok=True)

    total_files = 0
    changed_files = 0
    total_replacements = 0
    log_lines: list[str] = []
    log_lines.append(f"# rename_companion_tier1b — dry_run={args.dry_run}\n")

    for rel in IN_SCOPE_RELATIVE:
        path = REPO / rel
        if not path.exists():
            log_lines.append(f"MISSING: {rel}\n")
            continue
        total_files += 1
        original = path.read_text(encoding="utf-8")
        new_text, counts = apply_rename(original)

        if new_text != original:
            changed_files += 1
            file_total = sum(counts.values())
            total_replacements += file_total
            log_lines.append(f"\n## {rel} — {file_total} replacements\n")
            for k, v in counts.items():
                log_lines.append(f"  {v:4d}  {k}\n")
            if not args.dry_run:
                path.write_text(new_text, encoding="utf-8")

    log_lines.append(
        f"\n# SUMMARY: {changed_files}/{total_files} files changed, "
        f"{total_replacements} total replacements\n"
    )
    diff_log_path.write_text("".join(log_lines), encoding="utf-8")
    print(
        f"{'DRY-RUN ' if args.dry_run else ''}done: "
        f"{changed_files}/{total_files} files changed, "
        f"{total_replacements} replacements. Log: {diff_log_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
