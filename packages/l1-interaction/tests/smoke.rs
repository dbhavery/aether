//! L1 Wave 4 smoke — shape-only assertions. Logic lives in a later wave.

use aether_l1_interaction::*;

#[test]
fn turn_state_machine_has_nineteen_variants_named() {
    // If any of these evaporates during refactor, the compile breaks here.
    let _all = [
        TurnState::Idle,
        TurnState::Listening,
        TurnState::EndOfUserSpeech,
        TurnState::ReflexClassifying,
        TurnState::ReflexAck,
        TurnState::DeliberativeThinking,
        TurnState::RouterDispatched,
        TurnState::AwaitingPolicyApproval,
        TurnState::PolicyDenied,
        TurnState::ToolExecuting,
        TurnState::ToolCompleted,
        TurnState::Drafting,
        TurnState::Speaking,
        TurnState::BargeIn,
        TurnState::Repairing,
        TurnState::Deflected,
        TurnState::Completed,
        TurnState::TimedOut,
        TurnState::Errored,
    ];
    assert_eq!(_all.len(), 19);
}

#[test]
fn l1_error_is_serializable_as_display() {
    let e = L1Error::ReflexBudget { ms: 150 };
    assert!(format!("{e}").contains("150"));
}
