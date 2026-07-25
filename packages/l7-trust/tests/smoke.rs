use aether_l7_trust::*;

#[test]
fn eight_onboarding_screens_named() {
    let _all = [
        OnboardingScreen::Welcome,
        OnboardingScreen::PersonaPicker,
        OnboardingScreen::PresetPicker,
        OnboardingScreen::CapabilityPreview,
        OnboardingScreen::PrivacyPledge,
        OnboardingScreen::ByokSetup,
        OnboardingScreen::FirstTurn,
        OnboardingScreen::Done,
    ];
    assert_eq!(_all.len(), 8);
}
