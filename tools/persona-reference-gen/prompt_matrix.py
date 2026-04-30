"""Structured prompt-matrix expansion for reference-image generation.

Expands a persona's prompt anchors across three reproducible axes:

    framing × lighting × seed → list[PromptSpec]

Determinism contract: given identical inputs (persona anchors + axes lists)
the output PromptSpec list is byte-identical, including `prompt_id`s. This is
what makes batches re-runnable and manifests reproducible.

Doctrine §5 enforcement (photoreal full-body, no headshot intermediate):
- DEFAULT_FRAMINGS contains only full-body / 3/4-body framings.
- `validate_framings` rejects any framing string containing forbidden
  headshot/bust keywords. The default set passes; custom sets are checked.

Persona prompt anchors come from `personas/<slug>/persona.yaml`. The current
schema (see docs/PERSONA-SCHEMA.md and personas/aurora/persona.yaml) does NOT
yet have a structured `reference_prompt_anchor` field — for v0 we use a
small per-persona anchor dict here, and surface a TODO to migrate the
canonical anchor into persona.yaml in a follow-up. See README.md §"What's
stubbed".
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from output_schema import PromptSpec  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# Doctrine §5 — full-body framing axis. NO headshot / bust / portrait-crop.
# ---------------------------------------------------------------------------

DEFAULT_FRAMINGS: tuple[str, ...] = (
    "full-body shot, head to feet visible, standing, neutral pose",
    "full-body shot, head to feet visible, three-quarter angle, relaxed pose",
    "wide full-body shot, environmental context, head to feet visible",
    "3/4 body shot from knees up, head clearly visible, natural posture",
)


# Forbidden substrings (case-insensitive). Any framing string containing one
# of these is rejected — they imply headshot/bust crop, which doctrine §5
# bans as the source asset for the full-body pipeline.
_FORBIDDEN_FRAMING_TOKENS: tuple[str, ...] = (
    "headshot",
    "head shot",
    "head and shoulders",
    "shoulders up",
    "bust shot",
    "bust crop",
    "face only",
    "close-up portrait",
    "tight portrait crop",
)


DEFAULT_LIGHTINGS: tuple[str, ...] = (
    "soft natural daylight from a north-facing window",
    "warm golden hour, low sun, slight backlight",
    "neutral overhead studio softbox, even fill",
    "cool overcast outdoor light, diffused",
)


DEFAULT_SEEDS: tuple[int, ...] = (101, 202, 303, 404)


# v0 anchor table — per-persona core identity prompt. Each is a single
# self-contained sentence with the persona's identity-fixing details. These
# are the prompts we KNOW survive FLUX/RealVisXL well from prior anchor-set
# runs. TODO: migrate to a `reference_prompt_anchor` field in persona.yaml.
PERSONA_ANCHORS: dict[str, str] = {
    "aurora": (
        "Aurora Nash, a warm grounded thinking companion in her early thirties, "
        "auburn shoulder-length wavy hair, hazel eyes, calm steady expression, "
        "wearing a soft cream sweater and dark slim jeans, photorealistic, "
        "85mm lens, natural skin texture, no airbrushing"
    ),
}


DEFAULT_NEGATIVE_PROMPT = (
    "headshot, bust crop, close-up of face only, cartoon, anime, 3d render, "
    "cgi, plastic skin, airbrushed, beauty filter, magenta lighting, "
    "indigo gradient background, deformed hands, extra fingers, low resolution"
)


@dataclass(frozen=True)
class MatrixAxes:
    """Bundle of the three axes used to expand a persona's anchor.

    Frozen + immutable so a prompt_matrix run cannot mutate state mid-flight.
    """

    framings: tuple[str, ...]
    lightings: tuple[str, ...]
    seeds: tuple[int, ...]

    @classmethod
    def default(cls) -> MatrixAxes:
        return cls(
            framings=DEFAULT_FRAMINGS,
            lightings=DEFAULT_LIGHTINGS,
            seeds=DEFAULT_SEEDS,
        )

    def cardinality(self) -> int:
        return len(self.framings) * len(self.lightings) * len(self.seeds)


def validate_framings(framings: tuple[str, ...] | list[str]) -> None:
    """Raise ValueError on any framing that contains a forbidden headshot
    keyword. Doctrine §5 is enforced here, not at the schema layer."""
    bad: list[tuple[str, str]] = []
    for f in framings:
        low = f.lower()
        for tok in _FORBIDDEN_FRAMING_TOKENS:
            if tok in low:
                bad.append((f, tok))
                break
    if bad:
        details = "; ".join(f"{f!r} contains {tok!r}" for f, tok in bad)
        raise ValueError(
            f"doctrine §5 violation — headshot/bust framing rejected: {details}. "
            f"Use full-body framings (see DEFAULT_FRAMINGS in prompt_matrix.py)."
        )


def _make_prompt_id(persona_slug: str, framing: str, lighting: str, seed: int) -> str:
    """Stable hash-based id; deterministic given the same inputs."""
    h = hashlib.sha256()
    h.update(persona_slug.encode("utf-8"))
    h.update(b"\x00")
    h.update(framing.encode("utf-8"))
    h.update(b"\x00")
    h.update(lighting.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(seed).encode("utf-8"))
    return h.hexdigest()[:16]


def _compose_prompt(anchor: str, framing: str, lighting: str) -> str:
    """Concatenate anchor + framing + lighting with stable separators."""
    return f"{anchor}. Framing: {framing}. Lighting: {lighting}."


def expand_matrix(
    persona_slug: str,
    anchor: str,
    axes: MatrixAxes,
    negative_prompt: str = DEFAULT_NEGATIVE_PROMPT,
) -> list[PromptSpec]:
    """Expand the prompt matrix deterministically.

    Args:
        persona_slug: persona id (e.g. "aurora").
        anchor: the persona's identity-fixing core sentence.
        axes: framing × lighting × seed axes.
        negative_prompt: applied to every prompt.

    Returns:
        list[PromptSpec] of cardinality `len(framings) * len(lightings) *
        len(seeds)`. Iteration order is (framing, lighting, seed) — same
        order every call.
    """
    validate_framings(axes.framings)
    out: list[PromptSpec] = []
    for framing in axes.framings:
        for lighting in axes.lightings:
            for seed in axes.seeds:
                pid = _make_prompt_id(persona_slug, framing, lighting, seed)
                out.append(
                    PromptSpec(
                        prompt_id=pid,
                        persona_slug=persona_slug,
                        framing=framing,
                        lighting=lighting,
                        seed=seed,
                        prompt_text=_compose_prompt(anchor, framing, lighting),
                        negative_prompt=negative_prompt,
                    )
                )
    return out


def lookup_anchor(persona_slug: str) -> str:
    """Return the v0 hardcoded anchor for a persona, or raise.

    TODO (ADR-0014 follow-up): migrate to reading persona.yaml's
    `reference_prompt_anchor` field once the schema is extended.
    """
    if persona_slug not in PERSONA_ANCHORS:
        raise KeyError(
            f"no anchor registered for persona {persona_slug!r}. "
            f"Add to PERSONA_ANCHORS in prompt_matrix.py "
            f"(or migrate to persona.yaml field — see README §TODO)."
        )
    return PERSONA_ANCHORS[persona_slug]
