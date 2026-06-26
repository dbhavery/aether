"""Smoke tests for the Customer Assistant — pure logic, no network/LLM.

Run from apps/customer-assistant:
    PYTHONPATH=src python -m pytest tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from customer_assistant.assistant import (  # noqa: E402
    _check_escalation,
    _stub_answer,
    build_system_prompt,
)
from customer_assistant.config import (  # noqa: E402
    CompanyConfigError,
    CompanyProfile,
    load_company,
)
from customer_assistant.knowledge_base import RetrievedChunk, _split_markdown  # noqa: E402

_APP_ROOT = Path(__file__).resolve().parents[1]
_SAMPLE = _APP_ROOT / "companies" / "northwind-outdoors"


def _sample_profile() -> CompanyProfile:
    return load_company(_SAMPLE)


# ── config / schema ──────────────────────────────────────────────────────────
def test_sample_company_loads_and_validates() -> None:
    p = _sample_profile()
    assert p.company.id == "northwind-outdoors"
    assert p.collection_name == "northwind_outdoors_kb"
    assert p.knowledge_dir().is_dir()


def test_effective_model_resolution_priority() -> None:
    p = _sample_profile()
    # tier "fast" -> qwen2.5:7b (provider stripped)
    assert p.effective_model() == "qwen2.5:7b"
    p.llm.model = "llama3.1:8b"
    assert p.effective_model() == "llama3.1:8b"
    p.llm.fine_tuned_model = "northwind-support:latest"
    assert p.effective_model() == "northwind-support:latest"


def test_bad_color_rejected() -> None:
    with pytest.raises(Exception):
        CompanyProfile.model_validate(
            {"company": {"id": "x", "display_name": "X"}, "branding": {"colors": {"primary": "green"}}}
        )


def test_unknown_key_rejected() -> None:
    with pytest.raises(Exception):
        CompanyProfile.model_validate(
            {"company": {"id": "x", "display_name": "X"}, "nope": 1}
        )


def test_bad_id_slug_rejected() -> None:
    with pytest.raises(Exception):
        CompanyProfile.model_validate({"company": {"id": "Bad ID", "display_name": "X"}})


def test_missing_company_yaml(tmp_path: Path) -> None:
    with pytest.raises(CompanyConfigError):
        load_company(tmp_path)


# ── chunking ─────────────────────────────────────────────────────────────────
def test_split_markdown_overlap_and_size() -> None:
    text = "\n\n".join(f"Paragraph number {i} with some words." for i in range(40))
    chunks = _split_markdown(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 200 + 40 for c in chunks)


def test_split_markdown_hard_splits_huge_paragraph() -> None:
    chunks = _split_markdown("x" * 1000, chunk_size=300, overlap=50)
    assert len(chunks) >= 4


# ── escalation ───────────────────────────────────────────────────────────────
def test_escalation_trigger_detected() -> None:
    p = _sample_profile()
    # case-insensitive substring match against configured trigger phrases
    assert _check_escalation(p, "Can I please speak to a HUMAN?") is True
    assert _check_escalation(p, "My LOST PACKAGE never arrived") is True
    assert _check_escalation(p, "I want an Agent") is True
    assert _check_escalation(p, "what colors do your jackets come in?") is False


# ── prompt build ─────────────────────────────────────────────────────────────
def test_system_prompt_includes_company_scope_and_context() -> None:
    p = _sample_profile()
    chunks = [RetrievedChunk(text="Return within 60 days.", source="returns-policy.md", chunk_index=0, distance=0.1)]
    prompt = build_system_prompt(p, chunks)
    assert "Northwind Outdoors" in prompt
    assert "returns-policy.md" in prompt
    assert "Return within 60 days." in prompt
    assert "Escalate to a human" in prompt


def test_stub_answer_grounds_in_chunks() -> None:
    p = _sample_profile()
    chunks = [RetrievedChunk(text="Return within 60 days.", source="returns-policy.md", chunk_index=0, distance=0.1)]
    answer = _stub_answer(p, chunks)
    assert "returns-policy.md" in answer
    assert "60 days" in answer
