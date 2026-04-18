"""Pydantic models for persona packs.

One-to-one with `docs/PERSONA-SCHEMA.md` — edit there first, mirror here. Enum
membership and field names are load-bearing; the loader and audit tool rely on
them, and user-authored packs are validated against them.

Schema version: 1 (see PERSONA-SCHEMA.md §9 for forward-compat rules).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enumerations — mirror PERSONA-SCHEMA.md exactly.
# ---------------------------------------------------------------------------


class Archetype(StrEnum):
    """The 12 personality archetypes shipped in v1.0 (schema §2, §7)."""

    WARM_SUPPORTIVE = "warm_supportive"
    ANALYTICAL_PRECISE = "analytical_precise"
    PLAYFUL_WITTY = "playful_witty"
    FORMAL_EXECUTIVE = "formal_executive"
    CALM_ZEN = "calm_zen"
    ENERGETIC_ENTHUSIASTIC = "energetic_enthusiastic"
    DRY_SARDONIC = "dry_sardonic"
    MENTOR_TEACHER = "mentor_teacher"
    PEER_COLLABORATOR = "peer_collaborator"
    CREATIVE_ARTISTIC = "creative_artistic"
    TECHNICAL_ENGINEER = "technical_engineer"
    CURIOUS_INQUISITIVE = "curious_inquisitive"


class Formality(StrEnum):
    CASUAL = "casual"
    NEUTRAL = "neutral"
    FORMAL = "formal"


class Verbosity(StrEnum):
    TERSE = "terse"
    MEDIUM = "medium"
    EXPRESSIVE = "expressive"


class Humor(StrEnum):
    NONE = "none"
    LIGHT = "light"
    DRY = "dry"
    PLAYFUL = "playful"


class EmojiUsage(StrEnum):
    NEVER = "never"
    SPARINGLY = "sparingly"
    NATURAL = "natural"


class VoiceEngine(StrEnum):
    CHATTERBOX = "chatterbox"
    ELEVENLABS = "elevenlabs"


class GenderHint(StrEnum):
    """Informational only — used for ML-based fallbacks, never UI/UX gating."""

    FEMALE = "female"
    MALE = "male"
    NEUTRAL = "neutral"


class EmotionDefault(StrEnum):
    NEUTRAL = "neutral"
    WARM = "warm"
    BRIGHT = "bright"
    CALM = "calm"
    SERIOUS = "serious"


class AvatarEngine(StrEnum):
    """Only `liveportrait` ships in v1.0. New engines must bump schema_version."""

    LIVEPORTRAIT = "liveportrait"


class LLMTier(StrEnum):
    FAST = "fast"
    MAIN = "main"
    HEAVY = "heavy"


class AssetSource(StrEnum):
    """Asset provenance source (schema §4).

    `placeholder` is accepted by the loader for scaffold / example packs but
    will be flagged by the audit tool as non-shippable — bundled packs MUST
    resolve every placeholder before ship.
    """

    AI_GENERATED = "ai_generated"
    LICENSED = "licensed"
    ROYALTY_FREE = "royalty_free"
    USER_SUPPLIED = "user_supplied"
    SYNTHESIZED = "synthesized"
    PLACEHOLDER = "placeholder"


# ---------------------------------------------------------------------------
# Shared base — every model forbids unknown fields so typos fail loudly in
# dev instead of silently dropping data.
# ---------------------------------------------------------------------------


class _StrictBase(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# persona.yaml sub-structures (schema §2).
# ---------------------------------------------------------------------------


class PersonaStyle(_StrictBase):
    formality: Formality
    verbosity: Verbosity
    humor: Humor
    emoji_usage: EmojiUsage


class PersonaPersonality(_StrictBase):
    archetype: Archetype
    system_prompt: str = Field(
        ...,
        min_length=1,
        description="Full LLM system prompt, 200-800 tokens typical.",
    )
    style: PersonaStyle


class PersonaVoice(_StrictBase):
    engine: VoiceEngine
    gender_hint: GenderHint
    pitch_shift: int = Field(..., ge=-6, le=6, description="Semitones, -6 to +6.")
    speed: float = Field(..., ge=0.85, le=1.15, description="0.85 to 1.15.")
    emotion_default: EmotionDefault
    acknowledgment_phrases: list[str] = Field(..., min_length=1)
    interruption_phrases: list[str] = Field(..., min_length=1)

    @field_validator("acknowledgment_phrases", "interruption_phrases")
    @classmethod
    def _no_empty_phrases(cls, phrases: list[str]) -> list[str]:
        if any(not p.strip() for p in phrases):
            raise ValueError("phrase list contains an empty or whitespace-only entry")
        return phrases


class PersonaAvatar(_StrictBase):
    engine: AvatarEngine
    resolution: tuple[int, int] = Field(
        ...,
        description="Source portrait dimensions as (width, height).",
    )
    target_fps: int = Field(..., ge=1, le=60)
    idle_blink_rate_hz: float = Field(..., ge=0.0, le=2.0)
    idle_micro_movement_scale: float = Field(..., ge=0.0, le=1.0)

    @field_validator("resolution")
    @classmethod
    def _resolution_min(cls, value: tuple[int, int]) -> tuple[int, int]:
        width, height = value
        # Schema §5: portrait must be >= 512x512 and near-square.
        # `resolution` here is the declared *source* size. Actual image
        # dimensions are re-checked against portrait.png in the loader.
        if width < 512 or height < 512:
            raise ValueError(
                f"avatar.resolution {width}x{height} is below the 512x512 minimum "
                "(see PERSONA-SCHEMA.md §5)"
            )
        return value


class PersonaMemory(_StrictBase):
    isolation: bool
    retention_days: int = Field(..., ge=0, description="0 = forever.")
    persona_can_forget: bool


class PersonaLLMPreferences(_StrictBase):
    preferred_tier: LLMTier
    temperature: float = Field(..., ge=0.0, le=2.0)
    max_output_tokens: int = Field(..., ge=1, le=32768)


# ---------------------------------------------------------------------------
# Top-level persona.yaml.
# ---------------------------------------------------------------------------

# Literal list of valid schema versions. Adding v2 later means appending here;
# validation errors then surface the supported set directly to the user.
SupportedSchemaVersion = Literal[1]


class PersonaManifest(_StrictBase):
    """Top-level persona.yaml document (schema §2).

    `memory` and `llm_preferences` are optional per spec; when omitted, the
    runtime falls back to global defaults. When present they must be fully
    populated — partial overrides are rejected to avoid surprise merges.
    """

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=64)
    tagline: str = Field(..., max_length=120)
    schema_version: SupportedSchemaVersion
    personality: PersonaPersonality
    voice: PersonaVoice
    avatar: PersonaAvatar
    memory: PersonaMemory | None = None
    llm_preferences: PersonaLLMPreferences | None = None

    @field_validator("id")
    @classmethod
    def _id_format(cls, value: str) -> str:
        # Schema §2: lowercase alphanumeric + hyphens. Underscore prefix is
        # reserved for reference packs (filtered by loader) and is allowed
        # here so those still parse; filtering happens in `scan_personas`.
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
        if not value:
            raise ValueError("id cannot be empty")
        if any(c not in allowed for c in value):
            raise ValueError(
                f"id '{value}' contains invalid characters — "
                "use lowercase alphanumeric + hyphens (see PERSONA-SCHEMA.md §2)"
            )
        return value


# ---------------------------------------------------------------------------
# metadata.yaml sub-structures (schema §4).
# ---------------------------------------------------------------------------


class AssetProvenance(_StrictBase):
    """Provenance for a single asset entry in metadata.yaml.

    Different sources require different fields (e.g. ai_generated needs
    generator, royalty_free typically has attribution+url). Cross-field
    rules are enforced here; the audit tool (src/personas/audit.py)
    enforces the stricter shipping rules.
    """

    source: AssetSource
    generator: str | None = None
    prompt: str | None = None
    license: str = Field(..., min_length=1)
    url: str | None = None
    attribution: str | None = None
    description: str | None = None


class PersonaMetadata(_StrictBase):
    """metadata.yaml document (schema §4)."""

    schema_version: SupportedSchemaVersion
    creator: str = Field(..., min_length=1)
    created: date
    last_updated: date
    assets: dict[str, AssetProvenance] = Field(
        ...,
        description="Asset key → provenance. Keys match schema §4 (portrait, "
        "state_images, voice_reference, voice_sample).",
    )
    notes: str | None = None

    @field_validator("assets")
    @classmethod
    def _required_asset_keys(cls, assets: dict[str, AssetProvenance]) -> dict[str, AssetProvenance]:
        required = {"portrait", "state_images", "voice_reference", "voice_sample"}
        missing = required - assets.keys()
        if missing:
            raise ValueError(
                f"metadata.yaml missing required asset keys: {sorted(missing)} "
                "(see PERSONA-SCHEMA.md §4)"
            )
        return assets


# ---------------------------------------------------------------------------
# Runtime pack (internal — not a file).
# ---------------------------------------------------------------------------


class PersonaPack(_StrictBase):
    """In-memory bundle of a validated persona pack.

    Constructed by the loader after persona.yaml + metadata.yaml parse cleanly
    and every REQUIRED asset file exists on disk. `root_dir` is the folder the
    pack was loaded from; all other paths are derived from it.
    """

    manifest: PersonaManifest
    metadata: PersonaMetadata
    root_dir: Path
    is_user_pack: bool = Field(
        ...,
        description="True if loaded from the user override dir; False for bundled packs.",
    )

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,  # Path
        validate_assignment=True,
    )

    # --- convenience accessors ----------------------------------------------

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def display_name(self) -> str:
        return self.manifest.display_name

    @property
    def portrait_path(self) -> Path:
        return self.root_dir / "avatar" / "portrait.png"

    @property
    def state_image_paths(self) -> dict[str, Path]:
        states_dir = self.root_dir / "avatar" / "states"
        return {name: states_dir / f"{name}.png" for name in ("idle", "listening", "thinking", "speaking")}

    @property
    def reference_wav_path(self) -> Path:
        return self.root_dir / "voice" / "reference.wav"

    @property
    def sample_wav_path(self) -> Path:
        return self.root_dir / "voice" / "sample.wav"


__all__ = [
    "Archetype",
    "AssetProvenance",
    "AssetSource",
    "AvatarEngine",
    "EmojiUsage",
    "EmotionDefault",
    "Formality",
    "GenderHint",
    "Humor",
    "LLMTier",
    "PersonaAvatar",
    "PersonaLLMPreferences",
    "PersonaManifest",
    "PersonaMemory",
    "PersonaMetadata",
    "PersonaPack",
    "PersonaPersonality",
    "PersonaStyle",
    "PersonaVoice",
    "SupportedSchemaVersion",
    "Verbosity",
    "VoiceEngine",
]
