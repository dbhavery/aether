"""Multimodal-vision self-test pass for reference-image candidates.

Implements **Doctrine §8** + **ADR-0014 §"Visual self-test gate"**: every
candidate gets vision-model-scored against three explicit acceptance
criteria *before* Don sees it. Failures are flagged so the curation walk
hides them by default — Don's time is the scarce resource and the agent
absorbs the QA pass.

Three axes scored:

1. **photoreal_score** (0–10) — how plausibly photographic the image
   reads. <6 typically means visible AI artefacts (smooth skin, six
   fingers, glassy eyes, magenta gradient backgrounds).
2. **framing_match** (yes/no) — whether the candidate actually achieved
   the full-body framing the prompt asked for. AI generators routinely
   crop tighter than requested; doctrine §5 makes this a hard gate.
3. **identity_match** (yes/no/maybe) — whether the face/body identity is
   consistent with the persona's anchor reference image.

Backend: OpenAI `gpt-4o-mini`. Cheap (~$0.0003/image at low resolution),
fast, and accurate enough at the categorical questions we ask. The
backend identifier is captured on each `SelfTestRow` so a future swap is
detectable from the JSONL alone.

Gate: stub mode (default `PERSONA_REFGEN_SELFTEST_LIVE` env var unset)
returns a deterministic `pass` row keyed off the candidate's seed.
Live mode requires `OPENAI_API_KEY` and burns the (very cheap) per-image
cost. Stub keeps the default `pytest` run free.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import os
from pathlib import Path

from output_schema import SelfTestRow  # type: ignore[import-not-found]

DEFAULT_VISION_MODEL = "gpt-4o-mini"
LIVE_ENV_VAR = "PERSONA_REFGEN_SELFTEST_LIVE"


# Photoreal threshold below which a candidate is auto-flagged. 6/10 is
# the empirical break point where AI defects become obvious to the
# trained eye (locked here, not parameterized, so the gate threshold is
# a single audited value across the codebase).
PHOTOREAL_FLAG_THRESHOLD = 6


_SYSTEM_PROMPT = (
    "You are an image-quality auditor for an AI image generation pipeline. "
    "You will be shown two images: an ANCHOR identity reference and a CANDIDATE. "
    "Your job is to score the CANDIDATE on three axes against the ANCHOR's identity. "
    "Be a tough but fair judge. Score photorealism strictly: AI defects (smooth "
    "skin, glassy eyes, six fingers, distorted hands, magenta gradient backgrounds, "
    "indigo digital halos, plastic texture) drop the score significantly. "
    "Reply with strict JSON only — no prose, no markdown fences."
)

_USER_PROMPT_TEMPLATE = (
    "Persona slug: {persona_slug}. "
    "Generation prompt asked for: {prompt_text}\n\n"
    "Score the CANDIDATE (second image) against the ANCHOR (first image).\n\n"
    "Reply as strict JSON with these exact keys:\n"
    "  photoreal_score: integer 0..10 (how plausibly photographic — 0 obviously "
    "AI, 10 indistinguishable from a real photograph)\n"
    '  framing_match: "yes" or "no" (did the CANDIDATE actually achieve full-body '
    "head-to-feet framing as requested? if it cropped tighter, answer no)\n"
    '  identity_match: "yes" | "no" | "maybe" (does the CANDIDATE'"'"'s face and body '
    "identity match the ANCHOR's? maybe = uncertain or partially)\n"
    "  notes: a short string explaining the strongest signal that drove the scores\n"
    "JSON only. No prose."
)


def is_live_mode() -> bool:
    """True if the env var gate is set to a truthy value."""
    val = os.environ.get(LIVE_ENV_VAR, "").strip().lower()
    return val in {"1", "true", "yes", "on"}


def _utc_now() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


def _roll_up_verdict(
    photoreal_score: int,
    framing_match: str,
    identity_match: str,
) -> str:
    """Roll the three axes into the binary `pass` | `flag` gate.

    Flagging rules (locked):
      - photoreal_score < PHOTOREAL_FLAG_THRESHOLD → flag
      - framing_match == "no" → flag (doctrine §5: full-body is a hard
        gate, not a soft preference)
      - identity_match == "no" → flag

    `identity_match == "maybe"` does NOT flag — Don sees these but the
    notes carry the uncertainty so he can judge.
    """
    if photoreal_score < PHOTOREAL_FLAG_THRESHOLD:
        return "flag"
    if framing_match == "no":
        return "flag"
    if identity_match == "no":
        return "flag"
    return "pass"


def _stub_score(seed_basis: int) -> tuple[int, str, str, str]:
    """Deterministic stub: every candidate passes with score 8 / yes / yes.

    Keyed off `seed_basis` so future tests can assert determinism. We
    deliberately don't introduce stub flagging — that's a behaviour
    test, not a smoke test, and would couple stub/live shapes.
    """
    _ = seed_basis  # acknowledged; kept so signature stays parallel
    return 8, "yes", "yes", "stub: no live OPENAI_API_KEY in this run"


def _live_score(
    candidate_path: Path,
    anchor_path: Path,
    *,
    prompt_text: str,
    persona_slug: str,
    model: str,
) -> tuple[int, str, str, str]:
    """Live OpenAI gpt-4o-mini call. Imported lazily so stub runs don't
    require `openai`."""
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover — environment-specific
        raise RuntimeError(
            f"{LIVE_ENV_VAR} is set but `openai` is not installed. "
            "Install per pyproject.toml dev-deps."
        ) from exc

    client = OpenAI()

    candidate_b64 = base64.b64encode(candidate_path.read_bytes()).decode("ascii")
    anchor_b64 = base64.b64encode(anchor_path.read_bytes()).decode("ascii")

    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": _USER_PROMPT_TEMPLATE.format(
                            persona_slug=persona_slug,
                            prompt_text=prompt_text,
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{anchor_b64}",
                            "detail": "low",
                        },
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{candidate_b64}",
                            "detail": "low",
                        },
                    },
                ],
            },
        ],
    )

    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(raw)

    # Defensive coercion — the model is JSON-mode but the field shapes
    # are still trust-boundary. Clamp + normalize.
    photoreal = int(parsed.get("photoreal_score", 0))
    photoreal = max(0, min(10, photoreal))
    framing = str(parsed.get("framing_match", "no")).strip().lower()
    if framing not in {"yes", "no"}:
        framing = "no"
    identity = str(parsed.get("identity_match", "no")).strip().lower()
    if identity not in {"yes", "no", "maybe"}:
        identity = "no"
    notes = str(parsed.get("notes", "")).strip()
    return photoreal, framing, identity, notes


def score_candidate(
    candidate_path: Path,
    anchor_path: Path,
    *,
    prompt_id: str,
    candidate_index: int,
    prompt_text: str,
    persona_slug: str,
    model: str = DEFAULT_VISION_MODEL,
) -> SelfTestRow:
    """Score one candidate and return a `SelfTestRow`.

    Live or stub depending on `PERSONA_REFGEN_SELFTEST_LIVE`. The stub
    path is deterministic and free; the live path requires
    `OPENAI_API_KEY` and burns the per-image cost (~$0.0003 at low
    resolution).
    """
    if is_live_mode():
        photoreal, framing, identity, notes = _live_score(
            candidate_path,
            anchor_path,
            prompt_text=prompt_text,
            persona_slug=persona_slug,
            model=model,
        )
        backend = f"openai/{model}"
    else:
        # Seed basis: the candidate's own bytes hash isn't necessary
        # for v0 stub; just keep it parallel-shaped so a future
        # determinism test can swap the basis.
        photoreal, framing, identity, notes = _stub_score(seed_basis=candidate_index)
        backend = "stub"

    verdict = _roll_up_verdict(photoreal, framing, identity)
    return SelfTestRow(
        prompt_id=prompt_id,
        candidate_index=candidate_index,
        timestamp=_utc_now(),
        photoreal_score=photoreal,
        framing_match=framing,  # type: ignore[arg-type]
        identity_match=identity,  # type: ignore[arg-type]
        verdict=verdict,  # type: ignore[arg-type]
        notes=notes,
        backend=backend,
    )


def write_selftest_jsonl(rows: list[SelfTestRow], out_dir: Path) -> Path:
    """Write `selftest.jsonl` to `out_dir`. Returns the path written.

    Append-only on disk semantics are preserved by the consumer; this
    helper is for the batch-time bulk write.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "selftest.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(row.to_jsonl())
            f.write("\n")
    return path
