"""Tests for approval gate."""

from src.tools.approval_gate import (
    HIGH_IMPACT_ACTIONS,
    ActionRisk,
    get_pending_approval_ids,
    is_approval_response,
)


def test_high_impact_actions_are_explicit():
    assert HIGH_IMPACT_ACTIONS["send_email"] == ActionRisk.EXPLICIT
    assert HIGH_IMPACT_ACTIONS["delete_file"] == ActionRisk.EXPLICIT
    assert HIGH_IMPACT_ACTIONS["purchase"] == ActionRisk.EXPLICIT


def test_confirm_actions():
    assert HIGH_IMPACT_ACTIONS["send_message"] == ActionRisk.CONFIRM
    assert HIGH_IMPACT_ACTIONS["create_calendar_event"] == ActionRisk.CONFIRM


def test_approval_response_detection():
    assert is_approval_response("yes") is True
    assert is_approval_response("go ahead") is True
    assert is_approval_response("no") is False
    assert is_approval_response("cancel") is False
    assert is_approval_response("maybe later") is None


def test_no_pending_approvals_initially():
    assert get_pending_approval_ids() == []
