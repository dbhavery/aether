"""Manifest schema round-trip + curation jsonl round-trip."""

from __future__ import annotations

from output_schema import (  # type: ignore[import-not-found]
    SCHEMA_VERSION,
    BatchManifest,
    Candidate,
    CurationEntry,
    PromptSpec,
    read_manifest,
    write_manifest,
)


def _sample_manifest() -> BatchManifest:
    p = PromptSpec(
        prompt_id="abc123def4567890",
        persona_slug="aurora",
        framing="full-body shot, head to feet visible, standing, neutral pose",
        lighting="soft natural daylight from a north-facing window",
        seed=101,
        prompt_text="anchor. Framing: ... Lighting: ...",
        negative_prompt="headshot, bust crop, ...",
    )
    c = Candidate(
        prompt_id=p.prompt_id,
        candidate_index=0,
        image_path="images/abc123def4567890__0.png",
        backend="stub",
        backend_request_id="stub-101",
        backend_source_url=None,
        sha256="deadbeef",
    )
    return BatchManifest(
        schema_version=SCHEMA_VERSION,
        batch_id="2026-05-18a",
        persona_slug="aurora",
        created_at="2026-05-18T00:00:00+00:00",
        backend="stub",
        backend_model_id="fal-ai/flux-pro/v1.1-ultra",
        aspect_ratio="9:16",
        num_images_per_prompt=1,
        framings=["full-body shot, head to feet visible, standing, neutral pose"],
        lightings=["soft natural daylight from a north-facing window"],
        seeds=[101],
        prompts=[p],
        candidates=[c],
        persona_yaml_sha256="cafef00d",
        notes="smoke",
    )


def test_manifest_json_roundtrip(tmp_path):
    m = _sample_manifest()
    text = m.to_json()
    m2 = BatchManifest.from_json(text)
    assert m2.to_dict() == m.to_dict()


def test_write_and_read_manifest(tmp_path):
    m = _sample_manifest()
    out_dir = tmp_path / "batch"
    path = write_manifest(m, out_dir)
    assert path.exists()
    m2 = read_manifest(path)
    assert m2.to_dict() == m.to_dict()


def test_curation_entry_roundtrip():
    e = CurationEntry(
        prompt_id="abc123def4567890",
        candidate_index=0,
        verdict="keep",
        timestamp="2026-05-18T01:02:03+00:00",
        note="locked-in look",
    )
    line = e.to_jsonl()
    e2 = CurationEntry.from_jsonl(line)
    assert e2 == e
