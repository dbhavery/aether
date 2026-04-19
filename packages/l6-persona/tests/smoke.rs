use aether_l6_persona::*;

#[test]
fn swap_state_six_variants() {
    let _all = [
        SwapState::Idle,
        SwapState::Compiling,
        SwapState::Validating,
        SwapState::ReadyToCommit,
        SwapState::Committing,
        SwapState::RolledBack,
    ];
    assert_eq!(_all.len(), 6);
}
