//! Wave L6.1 — `DefaultPersonaCompiler` tests.

use aether_l6_persona::{DefaultPersonaCompiler, Humor, PersonaProfile, Stance, Tone, Verbosity};

fn warm_bold() -> PersonaProfile {
    let mut p = PersonaProfile::simple("aurora", "Aurora");
    p.tone = Tone::Warm;
    p.verbosity = Verbosity::Verbose;
    p.stance = Stance::Bold;
    p.humor = Humor::Playful;
    p
}

fn formal_cautious() -> PersonaProfile {
    let mut p = PersonaProfile::simple("praxis", "Praxis");
    p.tone = Tone::Formal;
    p.verbosity = Verbosity::Terse;
    p.stance = Stance::Cautious;
    p.humor = Humor::Dry;
    p
}

#[test]
fn compilation_is_deterministic() {
    let c = DefaultPersonaCompiler::new();
    let p = warm_bold();
    let a = c.compile(&p).expect("compile ok");
    let b = c.compile(&p).expect("compile ok");

    // Compare every ordered artifact field directly. The one HashMap —
    // `policy_defaults.per_capability_defaults` — is order-nondeterministic
    // in JSON output but set-equal across runs, so we compare it as a set.
    assert_eq!(a.persona_id, b.persona_id);
    assert_eq!(a.version, b.version);
    assert_eq!(
        serde_json::to_string(&a.prompts).unwrap(),
        serde_json::to_string(&b.prompts).unwrap()
    );
    assert_eq!(
        serde_json::to_string(&a.routing).unwrap(),
        serde_json::to_string(&b.routing).unwrap()
    );
    assert_eq!(
        serde_json::to_string(&a.behavior).unwrap(),
        serde_json::to_string(&b.behavior).unwrap()
    );
    assert_eq!(
        serde_json::to_string(&a.memory).unwrap(),
        serde_json::to_string(&b.memory).unwrap()
    );
    assert_eq!(a.tools.tools, b.tools.tools);
    assert_eq!(
        serde_json::to_string(&a.voice).unwrap(),
        serde_json::to_string(&b.voice).unwrap()
    );
    assert_eq!(
        a.policy_defaults.per_capability_defaults,
        b.policy_defaults.per_capability_defaults
    );
    assert_eq!(
        a.policy_defaults.privacy_posture,
        b.policy_defaults.privacy_posture
    );
}

#[test]
fn different_profiles_produce_different_outputs() {
    let c = DefaultPersonaCompiler::new();
    let a = c.compile(&warm_bold()).unwrap();
    let b = c.compile(&formal_cautious()).unwrap();

    assert_ne!(a.prompts.system, b.prompts.system);
    assert_ne!(a.routing.preferred_tier, b.routing.preferred_tier);
    assert_ne!(a.voice.voice_id, b.voice.voice_id);
    assert_ne!(a.tools.tools, b.tools.tools);
}

#[test]
fn empty_name_is_rejected() {
    let c = DefaultPersonaCompiler::new();
    let mut p = PersonaProfile::simple("x", "   ");
    p.tone = Tone::Neutral;
    let err = c.compile(&p).expect_err("empty name must be rejected");
    match err {
        aether_l6_persona::L6Error::Schema(msg) => {
            assert!(msg.to_lowercase().contains("name"))
        }
        other => panic!("unexpected error: {other:?}"),
    }
}

#[test]
fn stance_shifts_routing_tier_up() {
    let c = DefaultPersonaCompiler::new();
    let cautious = c.compile(&formal_cautious()).unwrap();
    let bold = c.compile(&warm_bold()).unwrap();

    assert_eq!(cautious.routing.preferred_tier, "local-small");
    assert_eq!(bold.routing.preferred_tier, "remote-standard");
    assert_eq!(cautious.routing.max_tier, "local-full");
    assert_eq!(bold.routing.max_tier, "remote-premium");
}

#[test]
fn system_prompt_includes_name_description_and_policy_guardrail() {
    let c = DefaultPersonaCompiler::new();
    let out = c.compile(&warm_bold()).unwrap();
    assert!(out.prompts.system.contains("Aurora"));
    assert!(out.prompts.system.contains("attentive"));
    // The guardrail line must always appear — L5 is the policy gate and
    // the system prompt is not a route around it.
    assert!(out
        .prompts
        .system
        .to_lowercase()
        .contains("l5 authorization"));
}

#[test]
fn cautious_persona_has_narrower_tool_allow_list() {
    let c = DefaultPersonaCompiler::new();
    let cautious = c.compile(&formal_cautious()).unwrap();
    let bold = c.compile(&warm_bold()).unwrap();
    assert!(cautious.tools.tools.len() < bold.tools.tools.len());
    assert!(!cautious.tools.tools.contains(&"shell.exec".into()));
    assert!(bold.tools.tools.contains(&"shell.exec".into()));
}

#[test]
fn reflex_templates_are_sorted_and_non_empty() {
    let c = DefaultPersonaCompiler::new();
    let out = c.compile(&warm_bold()).unwrap();
    let keys: Vec<&str> = out
        .prompts
        .reflex_templates
        .iter()
        .map(|(k, _)| k.as_str())
        .collect();
    let mut sorted = keys.clone();
    sorted.sort();
    assert_eq!(keys, sorted, "templates must be sorted for determinism");
    for (_, tmpl) in &out.prompts.reflex_templates {
        assert!(!tmpl.trim().is_empty());
    }
}

#[test]
fn policy_defaults_never_auto_approve_shell_exec() {
    let c = DefaultPersonaCompiler::new();
    for profile in [warm_bold(), formal_cautious()] {
        let out = c.compile(&profile).unwrap();
        let shell = out
            .policy_defaults
            .per_capability_defaults
            .get(&aether_l5_policy::Capability::ShellExec)
            .copied();
        assert_eq!(
            shell,
            Some(aether_l5_policy::ApprovalMode::Deny),
            "shell.exec must default to Deny across personas"
        );
    }
}
