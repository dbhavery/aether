use aether_l3_presence::*;

#[test]
fn nine_behavior_classes_named() {
    let _all = [
        BehaviorClass::Idle,
        BehaviorClass::Listening,
        BehaviorClass::Thinking,
        BehaviorClass::Speaking,
        BehaviorClass::BargingIn,
        BehaviorClass::Emphasizing,
        BehaviorClass::Deflecting,
        BehaviorClass::Repairing,
        BehaviorClass::SigningOff,
    ];
    assert_eq!(_all.len(), 9);
}

#[test]
fn three_tiers_named() {
    let _all = [PresenceTier::Lite, PresenceTier::Balanced, PresenceTier::Pro];
    assert_eq!(_all.len(), 3);
}
