"""Typed dataclasses for the reference-gen batch lifecycle.

Schema is intentionally simple and JSON-round-trippable: a batch run writes
`manifest.json` containing every input that determines the output. A separate
`curation.jsonl` records Don's keep / reject / reprompt verdicts per candidate.

Reproducibility contract (ADR-0015 §"Architecture", ADR-0014 Step 1):
- Identical inputs (persona slug, prompt-matrix axes, seed list, model id)
  must produce an identical prompt set and identical fal.ai request payloads.
- Manifest is canonical; round-tripping it through JSON must preserve every
  field exactly.

Doctrine §5: full-body photoreal framing is enforced upstream in
prompt_matrix.py (see DEFAULT_FRAMINGS). Schema does not enforce framing
strings; the validator in runner.py does.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


CurationVerdict = Literal["pending", "keep", "reject", "reprompt"]
"""Don's per-candidate verdict. Default `pending` until Don curates."""


@dataclass
class PromptSpec:
    """A single fully-expanded prompt with all axis values that produced it."""

    prompt_id: str
    """Stable identifier; deterministic from (persona, framing, lighting, seed)."""

    persona_slug: str
    framing: str
    """Doctrine §5: must be a full-body framing string. Headshot/bust framings
    are rejected by the validator."""

    lighting: str
    seed: int
    prompt_text: str
    """The fully-expanded text payload sent to the backend."""

    negative_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Candidate:
    """One generated image candidate, plus its provenance."""

    prompt_id: str
    candidate_index: int
    """0-based; allows num_images>1 per prompt without colliding."""

    image_path: str
    """Path relative to the batch directory, e.g. `images/<prompt_id>__0.png`."""

    backend: str
    """Backend name, e.g. `fal.ai/flux-pro/v1.1-ultra` or `stub`."""

    backend_request_id: str | None = None
    backend_source_url: str | None = None
    sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatchManifest:
    """Top-level manifest for one reference-gen batch run.

    Written to `personas/<slug>/_pipeline/step1_references/<batch_id>/manifest.json`.
    """

    schema_version: int
    batch_id: str
    persona_slug: str
    created_at: str
    """ISO-8601 UTC timestamp."""

    backend: str
    backend_model_id: str
    aspect_ratio: str
    num_images_per_prompt: int

    framings: list[str]
    lightings: list[str]
    seeds: list[int]
    """Axes used to expand the prompt matrix. Together with the persona's
    yaml prompt anchors these fully determine the prompt set."""

    prompts: list[PromptSpec]
    candidates: list[Candidate] = field(default_factory=list)

    persona_yaml_sha256: str | None = None
    """SHA-256 of the persona.yaml at run time, so we can detect drift if
    the same batch_id is replayed against a mutated persona spec."""

    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # asdict already recurses; ensure list ordering is preserved.
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BatchManifest:
        prompts = [PromptSpec(**p) for p in d.get("prompts", [])]
        candidates = [Candidate(**c) for c in d.get("candidates", [])]
        kwargs = {k: v for k, v in d.items() if k not in {"prompts", "candidates"}}
        return cls(prompts=prompts, candidates=candidates, **kwargs)

    @classmethod
    def from_json(cls, text: str) -> BatchManifest:
        return cls.from_dict(json.loads(text))


SCHEMA_VERSION = 1
"""Bump on any breaking change to BatchManifest / PromptSpec / Candidate."""


@dataclass
class CurationEntry:
    """One line in `curation.jsonl`. Append-only, latest-wins per prompt_id."""

    prompt_id: str
    candidate_index: int
    verdict: CurationVerdict
    timestamp: str
    """ISO-8601 UTC timestamp."""

    note: str = ""
    """Don's freeform comment, e.g. why a candidate was rejected or what to
    re-prompt with."""

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), sort_keys=False)

    @classmethod
    def from_jsonl(cls, line: str) -> CurationEntry:
        return cls(**json.loads(line))


def write_manifest(manifest: BatchManifest, out_dir: Path) -> Path:
    """Write `manifest.json` to `out_dir`. Returns the path written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(manifest.to_json(), encoding="utf-8")
    return path


def read_manifest(path: Path) -> BatchManifest:
    return BatchManifest.from_json(path.read_text(encoding="utf-8"))
