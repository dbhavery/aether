//! Wave L6.1 — `DefaultPersonaCompiler`.
//!
//! Deterministic, transparent profile → artifact compilation. No LLM calls,
//! no network. Same `PersonaProfile` in → byte-identical `CompiledPersona`
//! out (see `determinism` test).
//!
//! The rules in this module are intentionally small and readable. They
//! are not a replacement for the full persona pack compiler described in
//! `planning/plans/L6_persona_compiler_system_design.md`; they are the
//! thin slice that proves the pipeline works end-to-end for a later
//! demo wire-up.

use std::collections::HashMap;

use aether_l5_policy::{
    ApprovalMode, Capability, PersonaCompiledPolicyDefaults, PersonaId as PolicyPersonaId,
    PrivacyPosture,
};

use crate::compiler::{
    CompiledBehaviorMap, CompiledMemoryHints, CompiledPersona, CompiledPrompts,
    CompiledRoutingRules, CompiledToolAllowList, CompiledVoiceConfig,
};
use crate::error::L6Error;
use crate::profile::{Humor, PersonaProfile, Stance, Tone, Verbosity};

/// Default compiler. Stateless — every call to [`compile`](Self::compile)
/// produces output purely from the input profile.
#[derive(Debug, Default, Clone, Copy)]
pub struct DefaultPersonaCompiler;

impl DefaultPersonaCompiler {
    /// Build a new compiler.
    pub fn new() -> Self {
        Self
    }

    /// Compile a profile into the six artifacts + policy defaults.
    ///
    /// Deterministic: for a given `PersonaProfile`, the returned
    /// `CompiledPersona` is byte-identical across runs.
    pub fn compile(&self, profile: &PersonaProfile) -> Result<CompiledPersona, L6Error> {
        if profile.name.trim().is_empty() {
            return Err(L6Error::Schema(String::from("persona name is empty")));
        }

        let prompts = compile_prompts(profile);
        let routing = compile_routing(profile);
        let behavior = compile_behavior(profile);
        let memory = compile_memory(profile);
        let tools = compile_tools(profile);
        let voice = compile_voice(profile);
        let policy_defaults = compile_policy_defaults(profile);

        Ok(CompiledPersona {
            persona_id: profile.persona_id.clone(),
            version: profile.version,
            prompts,
            routing,
            behavior,
            memory,
            tools,
            voice,
            policy_defaults,
        })
    }
}

// ---------------------------------------------------------------------------
// Artifact builders — each is a small, deterministic function of the profile.
// ---------------------------------------------------------------------------

fn compile_prompts(p: &PersonaProfile) -> CompiledPrompts {
    let tone_line = match p.tone {
        Tone::Formal => "Speak formally and concisely. Avoid casual phrasing.",
        Tone::Neutral => "Speak plainly and professionally.",
        Tone::Warm => "Speak warmly and conversationally, like a trusted colleague.",
    };
    let verbosity_line = match p.verbosity {
        Verbosity::Terse => "Keep replies to one or two sentences unless detail is requested.",
        Verbosity::Balanced => "Answer in short paragraphs. Skip filler.",
        Verbosity::Verbose => "Explain context when it helps; prefer thorough answers.",
    };
    let humor_line = match p.humor {
        Humor::Dry => "Humor is dry and rare.",
        Humor::Occasional => "Occasional light humor is welcome when it fits.",
        Humor::Playful => "Playful banter and metaphors are welcome.",
    };
    let stance_line = match p.stance {
        Stance::Cautious => "Prefer drafting and confirmation over action.",
        Stance::Balanced => "Move promptly but check before high-impact actions.",
        Stance::Bold => "Lean toward action; surface risks explicitly rather than stalling.",
    };

    let system = format!(
        "You are {name}. {description}\n\n\
         Voice: {tone_line} {verbosity_line} {humor_line}\n\
         Stance: {stance_line}\n\
         Policy: all side-effectful actions require L5 authorization. You do not bypass that gate.",
        name = p.name,
        description = p.description,
        tone_line = tone_line,
        verbosity_line = verbosity_line,
        humor_line = humor_line,
        stance_line = stance_line,
    );

    // Reflex templates — one short canned reply per reflex class, colored
    // by tone so the top-of-funnel latency path still feels like the
    // persona. Kept as a sorted vector so compilation stays deterministic.
    let mut templates: Vec<(String, String)> = vec![
        (
            "AckOnly".into(),
            match p.tone {
                Tone::Formal => "Acknowledged.".into(),
                Tone::Neutral => "Got it.".into(),
                Tone::Warm => "Okay — on it.".into(),
            },
        ),
        (
            "ShortReply".into(),
            match p.tone {
                Tone::Formal => "Understood. One moment.".into(),
                Tone::Neutral => "Yep — checking now.".into(),
                Tone::Warm => "Sure thing — let me see.".into(),
            },
        ),
        ("Deflect".into(), "I'd rather not do that.".into()),
    ];
    templates.sort_by(|a: &(String, String), b| a.0.cmp(&b.0));

    CompiledPrompts {
        system,
        reflex_templates: templates,
    }
}

fn compile_routing(p: &PersonaProfile) -> CompiledRoutingRules {
    let (preferred, max_tier) = match p.stance {
        Stance::Cautious => ("local-small", "local-full"),
        Stance::Balanced => ("local-full", "remote-standard"),
        Stance::Bold => ("remote-standard", "remote-premium"),
    };
    CompiledRoutingRules {
        preferred_tier: preferred.to_string(),
        max_tier: max_tier.to_string(),
    }
}

fn compile_behavior(p: &PersonaProfile) -> CompiledBehaviorMap {
    // Every persona emits the same 4 behavior classes so downstream L3
    // maps never have to learn a variable shape. Only intensities shift.
    let (focus, warmth, playful, caution) = match (p.tone, p.stance, p.humor) {
        (Tone::Formal, Stance::Cautious, _) => (1.0, 0.3, 0.1, 1.0),
        (Tone::Formal, _, _) => (1.0, 0.4, 0.2, 0.6),
        (Tone::Warm, _, Humor::Playful) => (0.7, 1.0, 1.0, 0.5),
        (Tone::Warm, _, _) => (0.8, 0.9, 0.6, 0.5),
        (Tone::Neutral, Stance::Bold, _) => (0.9, 0.6, 0.5, 0.3),
        (Tone::Neutral, Stance::Cautious, _) => (0.9, 0.5, 0.3, 0.9),
        _ => (0.9, 0.6, 0.4, 0.5),
    };
    let mut intensities = vec![
        ("focus".into(), focus),
        ("warmth".into(), warmth),
        ("playfulness".into(), playful),
        ("caution".into(), caution),
    ];
    intensities.sort_by(|a: &(String, f32), b| a.0.cmp(&b.0));
    CompiledBehaviorMap { intensities }
}

fn compile_memory(p: &PersonaProfile) -> CompiledMemoryHints {
    // Very small hint table — verbose personas keep longer recent context,
    // cautious personas weigh safety-adjacent memory higher. Sorted for
    // determinism.
    let recent_weight = match p.verbosity {
        Verbosity::Terse => 0.6,
        Verbosity::Balanced => 0.8,
        Verbosity::Verbose => 1.0,
    };
    let safety_weight = match p.stance {
        Stance::Cautious => 1.0,
        Stance::Balanced => 0.7,
        Stance::Bold => 0.4,
    };
    let mut salience = vec![
        ("recent_turns".into(), recent_weight),
        ("safety_notes".into(), safety_weight),
    ];
    salience.sort_by(|a: &(String, f32), b| a.0.cmp(&b.0));
    CompiledMemoryHints {
        domain_salience: salience,
    }
}

fn compile_tools(p: &PersonaProfile) -> CompiledToolAllowList {
    // L5 always has the final say on which capabilities are actually
    // allowed; this allow-list is a hint only. Bold personas advertise
    // a slightly wider toolset than cautious ones.
    let mut tools: Vec<String> = vec!["fs.read".into(), "memory.recall".into()];
    if !matches!(p.stance, Stance::Cautious) {
        tools.push("browser.open".into());
    }
    if matches!(p.stance, Stance::Bold) {
        tools.push("shell.exec".into());
    }
    tools.sort();
    CompiledToolAllowList { tools }
}

fn compile_voice(p: &PersonaProfile) -> CompiledVoiceConfig {
    // Keep voice_id derived from tone so a real TTS layer can pick a
    // matching preset later. Rate shifts slightly with verbosity.
    let voice_id = match p.tone {
        Tone::Formal => "preset.formal",
        Tone::Neutral => "preset.neutral",
        Tone::Warm => "preset.warm",
    };
    let rate = match p.verbosity {
        Verbosity::Terse => 1.05,
        Verbosity::Balanced => 1.00,
        Verbosity::Verbose => 0.95,
    };
    CompiledVoiceConfig {
        voice_id: voice_id.to_string(),
        rate,
    }
}

fn compile_policy_defaults(p: &PersonaProfile) -> PersonaCompiledPolicyDefaults {
    // L6 *proposes* per-capability approval-mode defaults; L5's preset +
    // user-approval layer always get the final say. This is a hint only.
    let mut defaults: HashMap<Capability, ApprovalMode> = HashMap::new();
    defaults.insert(Capability::FilesRead, ApprovalMode::Auto);
    defaults.insert(
        Capability::FilesCreate,
        match p.stance {
            Stance::Cautious => ApprovalMode::Ask,
            Stance::Balanced | Stance::Bold => ApprovalMode::Ask,
        },
    );
    defaults.insert(Capability::ShellExec, ApprovalMode::Deny);

    let posture = match p.stance {
        Stance::Cautious => PrivacyPosture::Strict,
        Stance::Balanced => PrivacyPosture::Balanced,
        Stance::Bold => PrivacyPosture::Balanced,
    };

    PersonaCompiledPolicyDefaults {
        persona_id: PolicyPersonaId(p.persona_id.0.clone()),
        persona_version: p.version,
        privacy_posture: posture,
        per_capability_defaults: defaults,
        privileged_profile: false,
        recommended_preset: None,
    }
}
