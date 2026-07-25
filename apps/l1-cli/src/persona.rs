//! Demo-side persona wiring.
//!
//! Compiles a hard-coded `PersonaProfile` at startup and exposes small
//! helpers the rest of the CLI uses to pick a router tier and a banner
//! prompt. Persona logic stays inside this crate — L1 and L4 remain
//! persona-agnostic.

use aether_l4_router::RouterTier;
use aether_l6_persona::{
    CompiledPersona, DefaultPersonaCompiler, Humor, L6Error, PersonaProfile, Stance, Tone,
    Verbosity,
};

/// Build the demo's default profile. Hard-coded — a future wave could
/// read this from a config file or env var.
pub fn demo_profile() -> PersonaProfile {
    let mut p = PersonaProfile::simple("aurora", "Aurora");
    p.description =
        String::from("Local-first companion preview that narrates what the layers decide.");
    p.tone = Tone::Warm;
    p.verbosity = Verbosity::Balanced;
    p.stance = Stance::Balanced;
    p.humor = Humor::Occasional;
    p
}

/// Compile the demo persona. Fails only on schema errors; the default
/// profile above is always valid.
pub fn compile_demo_persona() -> Result<CompiledPersona, L6Error> {
    DefaultPersonaCompiler::new().compile(&demo_profile())
}

/// Map the string tier id produced by `DefaultPersonaCompiler` into the
/// strongly-typed `RouterTier` consumed by L4. Unknown labels fall back
/// to `RouterTier::Reflex` so a profile expansion never bricks the demo.
pub fn tier_from_rules(preferred: &str) -> RouterTier {
    match preferred {
        "reflex" => RouterTier::Reflex,
        "local-tiny" => RouterTier::LocalTiny,
        "local-small" => RouterTier::LocalSmall,
        "local-full" => RouterTier::LocalFull,
        "remote-standard" => RouterTier::RemoteStandard,
        "remote-premium" => RouterTier::RemotePremium,
        "remote-deep-research" => RouterTier::RemoteDeepResearch,
        _ => RouterTier::Reflex,
    }
}

/// Decide how much turn detail to print, based on the compiled persona.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OutputDetail {
    /// Terse — one-line summary per turn, no state trace.
    Terse,
    /// Balanced — state trace + decision + route.
    Balanced,
    /// Verbose — adds audit ids and raw block reason.
    Verbose,
}

/// Infer [`OutputDetail`] from the compiled persona's voice rate. Rate is
/// the one field that already surfaces the `Verbosity` dial through the
/// existing stub types without requiring us to extend `CompiledPersona`.
pub fn output_detail_from_persona(compiled: &CompiledPersona) -> OutputDetail {
    // compile_voice: Terse → 1.05, Balanced → 1.00, Verbose → 0.95
    let r = compiled.voice.rate;
    if r > 1.02 {
        OutputDetail::Terse
    } else if r < 0.98 {
        OutputDetail::Verbose
    } else {
        OutputDetail::Balanced
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tier_mapping_covers_all_seven_tiers() {
        assert_eq!(tier_from_rules("reflex"), RouterTier::Reflex);
        assert_eq!(tier_from_rules("local-tiny"), RouterTier::LocalTiny);
        assert_eq!(tier_from_rules("local-small"), RouterTier::LocalSmall);
        assert_eq!(tier_from_rules("local-full"), RouterTier::LocalFull);
        assert_eq!(
            tier_from_rules("remote-standard"),
            RouterTier::RemoteStandard
        );
        assert_eq!(tier_from_rules("remote-premium"), RouterTier::RemotePremium);
        assert_eq!(
            tier_from_rules("remote-deep-research"),
            RouterTier::RemoteDeepResearch
        );
        assert_eq!(tier_from_rules("unknown-label"), RouterTier::Reflex);
    }

    #[test]
    fn balanced_persona_compiles_to_a_usable_local_full_tier() {
        let c = compile_demo_persona().expect("compile demo persona");
        // Balanced stance → local-full preferred per the L6.1 rule table.
        assert_eq!(c.routing.preferred_tier, "local-full");
        assert_eq!(
            tier_from_rules(&c.routing.preferred_tier),
            RouterTier::LocalFull
        );
    }

    #[test]
    fn balanced_persona_yields_balanced_output_detail() {
        let c = compile_demo_persona().unwrap();
        assert_eq!(output_detail_from_persona(&c), OutputDetail::Balanced);
    }

    #[test]
    fn verbose_persona_yields_verbose_output_detail() {
        let mut p = demo_profile();
        p.verbosity = Verbosity::Verbose;
        let c = DefaultPersonaCompiler::new().compile(&p).unwrap();
        assert_eq!(output_detail_from_persona(&c), OutputDetail::Verbose);
    }

    #[test]
    fn terse_persona_yields_terse_output_detail() {
        let mut p = demo_profile();
        p.verbosity = Verbosity::Terse;
        let c = DefaultPersonaCompiler::new().compile(&p).unwrap();
        assert_eq!(output_detail_from_persona(&c), OutputDetail::Terse);
    }
}
