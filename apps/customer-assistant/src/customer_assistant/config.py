"""Per-company profile schema + loader.

A ``company.yaml`` is to the Customer Assistant what a ``persona.yaml`` is to
the Aether Companion: a typed, inspectable description that compiles into an
LLM system prompt and runtime behaviour. Where a persona describes *a
character*, a company profile describes *a business's support surface* —
branding, support scope, escalation rules, allowed tools, knowledge-base
location, and LLM tier/temperature.

The full documented schema lives in ``apps/customer-assistant/COMPANY-SCHEMA.md``.
This module is the canonical, validated implementation of that schema.

Design notes
------------
* Pure data + validation. No I/O side effects beyond reading a YAML file.
* Validation is strict (``extra="forbid"``) so a typo in a company.yaml fails
  loudly at load time rather than being silently ignored.
* Every model carries defaults so a minimal company.yaml still loads.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Aether's tiers (see configs/default_config.yaml -> llm.tier_map). A company
# picks a tier; the deployment maps the tier to a concrete Ollama model.
Tier = Literal["fast", "main", "heavy"]

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class _Strict(BaseModel):
    """Base model: forbid unknown keys so typos fail loudly."""

    model_config = ConfigDict(extra="forbid")


class BrandColors(_Strict):
    """Brand palette. Consumed by the embeddable widget for theming."""

    primary: str = "#2563eb"
    accent: str = "#f59e0b"
    background: str = "#0f1115"
    surface: str = "#171a21"
    text: str = "#e8eaed"

    @field_validator("primary", "accent", "background", "surface", "text")
    @classmethod
    def _hex(cls, value: str) -> str:
        if not _HEX_COLOR.match(value):
            raise ValueError(f"color must be a hex string like #1f6f54, got {value!r}")
        return value


class Branding(_Strict):
    """Visual + voice identity for the assistant."""

    logo: str | None = None  # path relative to the company dir, or a URL
    colors: BrandColors = Field(default_factory=BrandColors)
    tone: str = "friendly, clear, and concise"
    greeting: str = "Hi! How can I help you today?"


class SupportScope(_Strict):
    """What the assistant is and is not allowed to help with."""

    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["en"])


class EscalationContact(_Strict):
    email: str | None = None
    phone: str | None = None
    hours: str | None = None


class Escalation(_Strict):
    """When and how to hand off to a human agent."""

    enabled: bool = True
    triggers: list[str] = Field(default_factory=list)
    contact: EscalationContact = Field(default_factory=EscalationContact)
    message: str = (
        "Let me connect you with a member of our support team who can help "
        "with that."
    )


class ToolSpec(_Strict):
    """A tool the assistant is allowed to call.

    Scaffold only in this demo: ``enabled`` defaults to ``False`` and the
    assistant core advertises allowed tools in the system prompt but does not
    execute them. Wiring real tool execution would route through Aether's L5
    policy layer in a production build (see README "Scaffolded vs production").
    """

    name: str
    description: str
    enabled: bool = False


class KnowledgeBase(_Strict):
    """RAG knowledge-base location + chunking parameters."""

    path: str = "knowledge"  # relative to the company dir
    collection: str | None = None  # defaults to "<company_id>_kb"
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)

    @model_validator(mode="after")
    def _overlap_lt_size(self) -> KnowledgeBase:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self


class LLMConfig(_Strict):
    """LLM dispatch settings.

    ``tier`` maps to Aether's ``llm.tier_map`` (fast/main/heavy). ``model``
    is an optional explicit Ollama model that overrides the tier mapping.
    ``fine_tuned_model`` is the fine-tuning hook (see FINETUNING.md): when set,
    it takes priority over both ``model`` and ``tier``.
    """

    tier: Tier = "fast"
    model: str | None = None
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=512, ge=16, le=8192)
    fine_tuned_model: str | None = None


class CompanyMeta(_Strict):
    """Top-level identity."""

    id: str
    display_name: str
    tagline: str | None = None
    website: str | None = None
    support_email: str | None = None

    @field_validator("id")
    @classmethod
    def _id_slug(cls, value: str) -> str:
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", value):
            raise ValueError(
                "company.id must be a lowercase slug (a-z, 0-9, hyphens), "
                f"got {value!r}"
            )
        return value


class CompanyProfile(_Strict):
    """The full compiled company profile (root of ``company.yaml``)."""

    schema_version: int = 1
    company: CompanyMeta
    branding: Branding = Field(default_factory=Branding)
    support: SupportScope = Field(default_factory=SupportScope)
    escalation: Escalation = Field(default_factory=Escalation)
    tools: list[ToolSpec] = Field(default_factory=list)
    knowledge_base: KnowledgeBase = Field(default_factory=KnowledgeBase)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    # Populated by ``load_company`` — absolute path to the company directory.
    # Excluded from validation of the YAML body.
    base_dir: Path | None = Field(default=None, exclude=True)

    @property
    def collection_name(self) -> str:
        """Effective ChromaDB collection name for this company's KB."""
        return self.knowledge_base.collection or f"{self.company.id}_kb"

    def knowledge_dir(self) -> Path:
        """Absolute path to the knowledge folder for this company."""
        if self.base_dir is None:
            raise ValueError("base_dir is not set; load via load_company()")
        return (self.base_dir / self.knowledge_base.path).resolve()

    def effective_model(self, tier_map: dict[str, str] | None = None) -> str:
        """Resolve the concrete Ollama model name to call.

        Priority: fine_tuned_model > explicit model > tier-mapped model.
        """
        if self.llm.fine_tuned_model:
            return self.llm.fine_tuned_model
        if self.llm.model:
            return self.llm.model
        mapping = tier_map or DEFAULT_TIER_MAP
        resolved = mapping.get(self.llm.tier, DEFAULT_TIER_MAP[self.llm.tier])
        # tier_map values look like "ollama/qwen2.5:7b"; strip the provider.
        return resolved.split("/", 1)[-1]


# Mirrors configs/default_config.yaml -> llm.tier_map (provider stripped at use).
DEFAULT_TIER_MAP: dict[str, str] = {
    "fast": "ollama/qwen2.5:7b",
    "main": "ollama/qwen2.5:14b",
    "heavy": "ollama/qwen2.5:32b",
}


class CompanyConfigError(RuntimeError):
    """Raised when a company.yaml is missing or fails schema validation."""


def load_company(company_dir: str | Path) -> CompanyProfile:
    """Load and validate ``<company_dir>/company.yaml``.

    Args:
        company_dir: Path to a company directory containing ``company.yaml``.

    Returns:
        A validated :class:`CompanyProfile` with ``base_dir`` populated.

    Raises:
        CompanyConfigError: if the directory or file is missing, the YAML is
            malformed, or validation fails.
    """
    base = Path(company_dir).resolve()
    yaml_path = base / "company.yaml"
    if not yaml_path.is_file():
        raise CompanyConfigError(f"no company.yaml found at {yaml_path}")

    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise CompanyConfigError(f"malformed YAML in {yaml_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise CompanyConfigError(f"{yaml_path} must contain a YAML mapping at the root")

    try:
        profile = CompanyProfile.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError — re-raise as our type
        raise CompanyConfigError(f"invalid company profile in {yaml_path}: {exc}") from exc

    profile.base_dir = base
    return profile


def discover_companies(companies_root: str | Path) -> dict[str, Path]:
    """Map company id -> directory for every company under ``companies_root``.

    A directory qualifies if it contains a ``company.yaml``. Directories whose
    name starts with ``_`` are skipped (reserved for examples/templates).
    """
    root = Path(companies_root).resolve()
    found: dict[str, Path] = {}
    if not root.is_dir():
        return found
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if (child / "company.yaml").is_file():
            found[child.name] = child
    return found
