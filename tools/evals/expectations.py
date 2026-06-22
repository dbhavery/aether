"""Expectation DSL for the Aether eval runner (v1).

Open-ended: the runner skips unknown kinds silently, so adding new
ones is non-breaking. See `docs/QUALITY-EVAL-V1-ARCHITECTURE.md`
§2.1 for the design.

Kinds implemented:
  - `forbids`      — response must NOT contain any of `patterns`
                     (case-insensitive substring match).
  - `requires`     — response MUST contain every string in `patterns`
                     (case-insensitive substring match — ALL).
  - `requires_any` — response MUST match AT LEAST ONE of `patterns`
                     interpreted as case-insensitive regular
                     expressions. Added by the EVAL_SCENARIO_BROADENING
                     2026-04-25 work to encode "Aurora's product-correct
                     surface" as a union of acceptable phrasings
                     (paraphrase, clarifier, hedge) rather than a
                     single literal token. See the 2026-04-25 eval
                     scenario-broadening work.
  - `length`       — `{ max_words?, min_words? }` bounds on whitespace-
                     split word count.
  - `tone`         — accepts `matches: [<tag>, ...]`; v1 just records
                     the tags as informational. A future slice plugs a
                     tone classifier in.

Every evaluator is pure and side-effect-free so the runner stays
trivially unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


EVALUATED_KINDS = {"forbids", "requires", "requires_any", "length", "tone"}


@dataclass
class ExpectationResult:
    kind: str
    status: str                  # "pass" | "fail" | "skip"
    detail: str = ""


def evaluate_expectation(expectation: dict, response: str) -> ExpectationResult:
    kind = expectation.get("kind", "<missing>")
    if kind == "forbids":
        return _forbids(expectation, response)
    if kind == "requires":
        return _requires(expectation, response)
    if kind == "requires_any":
        return _requires_any(expectation, response)
    if kind == "length":
        return _length(expectation, response)
    if kind == "tone":
        return _tone(expectation)
    return ExpectationResult(
        kind=kind, status="skip", detail=f"unknown kind {kind!r}"
    )


def _forbids(expectation: dict, response: str) -> ExpectationResult:
    patterns = expectation.get("patterns") or []
    hay = response.lower()
    hits = [p for p in patterns if isinstance(p, str) and p.lower() in hay]
    if hits:
        return ExpectationResult(
            kind="forbids",
            status="fail",
            detail=f"response contained forbidden patterns: {hits!r}",
        )
    return ExpectationResult(kind="forbids", status="pass", detail="")


def _requires(expectation: dict, response: str) -> ExpectationResult:
    patterns = expectation.get("patterns") or []
    hay = response.lower()
    missing = [p for p in patterns if isinstance(p, str) and p.lower() not in hay]
    if missing:
        return ExpectationResult(
            kind="requires",
            status="fail",
            detail=f"response missed required patterns: {missing!r}",
        )
    return ExpectationResult(kind="requires", status="pass", detail="")


def _requires_any(expectation: dict, response: str) -> ExpectationResult:
    """Pass if AT LEAST ONE pattern (compiled as a case-insensitive
    regex) finds a match in the response. Invalid regexes surface as
    a `fail` with the pattern that failed to compile so a typo never
    silently passes the assertion.
    """
    patterns = expectation.get("patterns") or []
    valid: list[str] = [p for p in patterns if isinstance(p, str)]
    for pattern in valid:
        try:
            if re.search(pattern, response, re.IGNORECASE):
                return ExpectationResult(
                    kind="requires_any",
                    status="pass",
                    detail=f"matched pattern: {pattern!r}",
                )
        except re.error as exc:
            return ExpectationResult(
                kind="requires_any",
                status="fail",
                detail=f"pattern {pattern!r} failed to compile: {exc}",
            )
    return ExpectationResult(
        kind="requires_any",
        status="fail",
        detail=f"response matched none of the required patterns: {valid!r}",
    )


def _length(expectation: dict, response: str) -> ExpectationResult:
    words = len(response.split())
    max_w = expectation.get("max_words")
    min_w = expectation.get("min_words")
    if isinstance(max_w, int) and words > max_w:
        return ExpectationResult(
            kind="length",
            status="fail",
            detail=f"response is {words} words; max_words={max_w}",
        )
    if isinstance(min_w, int) and words < min_w:
        return ExpectationResult(
            kind="length",
            status="fail",
            detail=f"response is {words} words; min_words={min_w}",
        )
    return ExpectationResult(
        kind="length", status="pass", detail=f"{words} words"
    )


def _tone(expectation: dict) -> ExpectationResult:
    # v1: informational only. No classifier yet. Future slices can
    # flip this from `skip` to `pass`/`fail` once a real tone
    # signal is available.
    matches = expectation.get("matches") or []
    return ExpectationResult(
        kind="tone",
        status="skip",
        detail=f"tone classifier not yet implemented (tags: {matches!r})",
    )
