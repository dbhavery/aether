"""Smoke + determinism tests for prompt_matrix expansion."""

from __future__ import annotations

import pytest
from prompt_matrix import (  # type: ignore[import-not-found]
    DEFAULT_FRAMINGS,
    DEFAULT_LIGHTINGS,
    DEFAULT_SEEDS,
    MatrixAxes,
    expand_matrix,
    lookup_anchor,
    validate_framings,
)


def test_default_axes_cardinality():
    axes = MatrixAxes.default()
    assert axes.cardinality() == len(DEFAULT_FRAMINGS) * len(DEFAULT_LIGHTINGS) * len(DEFAULT_SEEDS)


def test_expand_matrix_is_deterministic():
    axes = MatrixAxes.default()
    a = expand_matrix("aurora", lookup_anchor("aurora"), axes)
    b = expand_matrix("aurora", lookup_anchor("aurora"), axes)
    assert [p.to_dict() for p in a] == [p.to_dict() for p in b]


def test_expand_matrix_iteration_order():
    """Order is (framing outer, lighting middle, seed inner)."""
    axes = MatrixAxes(
        framings=("full-body shot, A",),
        lightings=("light X", "light Y"),
        seeds=(1, 2),
    )
    out = expand_matrix("aurora", "anchor stub", axes)
    assert [(p.lighting, p.seed) for p in out] == [
        ("light X", 1),
        ("light X", 2),
        ("light Y", 1),
        ("light Y", 2),
    ]


def test_prompt_id_stable_across_runs():
    axes = MatrixAxes.default()
    a = expand_matrix("aurora", "fixed anchor", axes)
    # Re-run with a fresh axes instance carrying same values.
    axes2 = MatrixAxes(
        framings=DEFAULT_FRAMINGS,
        lightings=DEFAULT_LIGHTINGS,
        seeds=DEFAULT_SEEDS,
    )
    b = expand_matrix("aurora", "fixed anchor", axes2)
    assert [p.prompt_id for p in a] == [p.prompt_id for p in b]


def test_validate_framings_accepts_default():
    validate_framings(DEFAULT_FRAMINGS)


@pytest.mark.parametrize(
    "bad_framing",
    [
        "headshot, studio backdrop",
        "head and shoulders crop, soft light",
        "Bust shot from chest up",
        "close-up portrait of the face",
        "tight portrait crop centered on eyes",
    ],
)
def test_validate_framings_rejects_headshot_variants(bad_framing: str):
    with pytest.raises(ValueError, match="doctrine §5"):
        validate_framings((bad_framing,))


def test_lookup_anchor_unknown_raises():
    with pytest.raises(KeyError):
        lookup_anchor("not_a_persona")


def test_lookup_anchor_aurora_present():
    assert "Aurora" in lookup_anchor("aurora")
