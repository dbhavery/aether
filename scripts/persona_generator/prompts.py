"""Per-persona prompt templates for portrait + state generation.

Keeping prompts in one module lets all generator scripts share the same
source of truth and makes regeneration reproducible — the exact prompt
used for a given asset is captured in the pack's `avatar/README.md`.

Every prompt deliberately excludes AI-slop signals (indigo/purple gradient
background, magenta rim light, over-smooth plastic skin, extra fingers,
floating text, logos) because early generations hit those consistently.
"""

from __future__ import annotations

from dataclasses import dataclass


# Shared constraints appended to every portrait prompt. These are the
# AI-slop exclusions — if you remove any of these, expect gradients and
# plastic skin to return.
SHARED_NEGATIVES = (
    "Photorealistic editorial portrait. Natural skin texture with visible "
    "pores and subtle skin variation — NOT airbrushed, NOT porcelain, NOT "
    "plastic. No magenta or purple rim light. No indigo gradient background. "
    "No cyberpunk neon. No text, no watermark, no logo, no jewelry with "
    "text. Realistic eye reflections, correct eye anatomy (no extra "
    "catchlights, no over-saturated iris). Centered composition, head and "
    "upper shoulders visible, relaxed natural expression, looking directly "
    "at camera. Shot on 85mm lens, f/2.0, shallow depth of field, sharp "
    "focus on the eyes. Square 1:1 framing, portrait-oriented subject "
    "centered in frame."
)


@dataclass(frozen=True)
class PersonaPromptSpec:
    """Prompt scaffolding for one persona.

    Attributes:
        id: Persona id (matches folder name).
        archetype: Personality archetype (matches persona.yaml).
        base_description: Core identity + appearance sentence. Used for
            portrait.png and as the anchor for every state image prompt.
        background: Short phrase describing the background / environment.
            Separate so state images can hold it constant while expression
            changes.
        lighting: Short phrase describing the lighting setup.
        state_modifiers: Map of state name -> expression modifier sentence.
            Inserted into the state prompt template to produce the four
            required variants.
    """

    id: str
    archetype: str
    base_description: str
    background: str
    lighting: str
    state_modifiers: dict[str, str]


# ---------------------------------------------------------------------------
# Aurora — warm_supportive
# ---------------------------------------------------------------------------

AURORA = PersonaPromptSpec(
    id="aurora",
    archetype="warm_supportive",
    base_description=(
        "Portrait of a woman in her early 30s with warm hazel-brown eyes, "
        "natural wavy shoulder-length auburn hair with subtle highlights, "
        "light natural makeup, gentle genuine smile suggesting warmth and "
        "calm intelligence. Wearing a soft cream-colored knit sweater with "
        "a wide neckline. Skin has natural warm undertones with light "
        "freckles across the bridge of the nose."
    ),
    background=(
        "Out-of-focus neutral warm beige interior wall, hint of a soft "
        "terracotta-toned textured fabric in the blur."
    ),
    lighting=(
        "Soft diffused golden-hour window light from the left at a 45-degree "
        "angle, producing gentle warm highlights on the cheekbone and a "
        "soft catchlight in the eyes. No harsh shadows."
    ),
    state_modifiers={
        "idle": (
            "Neutral relaxed expression, lips softly closed with the very "
            "faintest hint of a smile at the corners, eyes looking directly "
            "at the camera, calm and present."
        ),
        "listening": (
            "Attentive expression, slightly wider eyes, head tilted perhaps "
            "two degrees to the right, eyebrows raised a millimeter in "
            "genuine curiosity, mouth closed, engaged and open."
        ),
        "thinking": (
            "Concentration expression, gaze angled slightly off-camera to "
            "the upper-left as if reflecting on a question, eyebrows "
            "gently drawn, mouth neutral and closed."
        ),
        "speaking": (
            "Speaking-ready expression, mouth open in a neutral 'mid-word' "
            "position with teeth barely visible, warm smile in the eyes, "
            "looking directly at camera."
        ),
    },
)


# ---------------------------------------------------------------------------
# Caelum — analytical_precise
# ---------------------------------------------------------------------------

CAELUM = PersonaPromptSpec(
    id="caelum",
    archetype="analytical_precise",
    base_description=(
        "Portrait of a man in his mid 30s with sharp dark-grey eyes, short "
        "neatly-cut dark brown hair with a slight natural wave, clean shave "
        "or very light stubble, composed and intelligent expression with a "
        "slight intensity, calm but alert. Wearing a charcoal grey merino "
        "crew-neck sweater. Skin has neutral undertones, realistic texture, "
        "subtle natural lines at the eyes showing lived experience."
    ),
    background=(
        "Out-of-focus cool-neutral interior, soft grey-blue tones, a "
        "hint of bookshelf or framed geometric abstract in the blur."
    ),
    lighting=(
        "Even diffused overcast daylight from a large north-facing window "
        "in front-left, neutral white balance, gentle modeling on the "
        "cheekbones without warm tint. Soft shadow under the jaw giving "
        "the face subtle dimension. No drama, no color cast."
    ),
    state_modifiers={
        "idle": (
            "Composed neutral expression, mouth closed in a relaxed line "
            "neither smiling nor frowning, eyes steady and level, looking "
            "directly at the camera. Thoughtful and present."
        ),
        "listening": (
            "Attentive analytical expression, eyes fully engaged and "
            "slightly narrowed in focused listening, head perfectly "
            "upright, mouth closed in a neutral line, eyebrow lifted one "
            "millimeter in genuine interest."
        ),
        "thinking": (
            "Deep concentration expression, gaze angled slightly off-camera "
            "to the side mid-distance, eyebrows faintly drawn together, "
            "mouth closed. The look of working through a problem carefully."
        ),
        "speaking": (
            "Speaking-ready expression, mouth open in a neutral mid-word "
            "position, eyes direct to camera, controlled and clear — "
            "not theatrical, not dramatic."
        ),
    },
)


# ---------------------------------------------------------------------------
# Luma — playful_witty
# ---------------------------------------------------------------------------

LUMA = PersonaPromptSpec(
    id="luma",
    archetype="playful_witty",
    base_description=(
        "Androgynous portrait of a person in their late 20s with bright "
        "expressive light-green eyes, tousled short-to-medium chestnut-brown "
        "hair with a natural messy side part, a scattering of freckles "
        "across the nose and upper cheeks, quick intelligent expression. "
        "Wearing a soft mustard-yellow mock-neck sweater. Skin has warm "
        "undertones, realistic texture, a natural liveliness to the face."
    ),
    background=(
        "Out-of-focus bright warm interior with a hint of pale yellow or "
        "peach tones, maybe a soft-focus potted plant in the blur, airy "
        "and open-feeling."
    ),
    lighting=(
        "Bright soft daylight from a large window to the left and slightly "
        "above, giving a lively warm-neutral tone with bright catchlights "
        "in the eyes. Higher overall exposure than Aurora or Caelum — feels "
        "like a sunny morning indoors. No harsh shadows."
    ),
    state_modifiers={
        "idle": (
            "Relaxed expression with a subtle warm smile naturally lifting "
            "the corners of the mouth, eyes bright and present, one "
            "eyebrow raised one millimeter as if about to say something "
            "clever. Looking directly at camera."
        ),
        "listening": (
            "Engaged playful expression, eyes wide and curious, head "
            "tilted slightly to the left maybe two degrees, mouth in a "
            "gentle relaxed line with the hint of a 'tell me more' smile."
        ),
        "thinking": (
            "Thinking expression with a slightly amused quirk — gaze "
            "angled up and to the right as if chasing a good idea, one "
            "eyebrow lifted higher than the other, mouth in a small "
            "wry close-lipped smile."
        ),
        "speaking": (
            "Speaking-ready expression, mouth open in a neutral mid-word "
            "position with a natural smile at the edges, eyes bright and "
            "engaged, looking directly at camera."
        ),
    },
)


# ---------------------------------------------------------------------------
# Registry + template builders.
# ---------------------------------------------------------------------------

PERSONA_PROMPTS: dict[str, PersonaPromptSpec] = {
    "aurora": AURORA,
    "caelum": CAELUM,
    "luma": LUMA,
}


def build_portrait_prompt(spec: PersonaPromptSpec) -> str:
    """Compose the full portrait prompt for a persona spec."""
    return (
        f"{spec.base_description} "
        f"Background: {spec.background} "
        f"Lighting: {spec.lighting} "
        f"{SHARED_NEGATIVES}"
    )


def build_state_prompt(spec: PersonaPromptSpec, state: str) -> str:
    """Compose the full state-image prompt for a given state name."""
    if state not in spec.state_modifiers:
        raise KeyError(
            f"unknown state '{state}' for persona '{spec.id}' — "
            f"expected one of {sorted(spec.state_modifiers)}"
        )
    modifier = spec.state_modifiers[state]
    return (
        f"{spec.base_description} "
        f"Expression for this frame: {modifier} "
        f"Background: {spec.background} "
        f"Lighting: {spec.lighting} "
        f"{SHARED_NEGATIVES}"
    )


__all__ = [
    "AURORA",
    "CAELUM",
    "LUMA",
    "PERSONA_PROMPTS",
    "PersonaPromptSpec",
    "SHARED_NEGATIVES",
    "build_portrait_prompt",
    "build_state_prompt",
]
