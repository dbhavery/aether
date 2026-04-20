//! Aether L1 community demo.
//!
//! Reads a line from stdin, builds a `TurnRequest`, drives the L1 turn FSM
//! through L5 policy evaluation and into an L4 router adapter, and prints a
//! structured summary. Honest demo: nothing leaves the process, no model is
//! called, no tool executes — only the engine path is real.
//!
//! Commands:
//!   read <path>     → FilesRead   (Auto in wave3 preset — allowed)
//!   write <path>    → FilesCreate (Ask → blocked on approval)
//!   edit <path>     → FilesEdit   (Ask → blocked on approval)
//!   delete <path>   → FilesDelete (Ask → blocked on approval)
//!   shell <cmd>     → ShellExec   (Deny)
//!   browse <url>    → BrowserOpen (NeedsUpgrade — outside preset)
//!   <anything else> → FilesRead with ResourceScope::None (allowed)
//!
//! Each shape exercises a different branch of the FSM so a reader can see
//! how L1 / L5 / L4 interlock without editing the code.

mod adapter;
mod persona;

use std::io::{self, BufRead, Write};
use std::sync::Arc;

use aether_l1_interaction::{BlockReason, TurnEngine, TurnRequest, TurnResult, TurnRouter};
use aether_l5_policy::{
    policy_engine::PolicyEngine, Capability, Decision, DefaultPolicyEngine, EngineConfig,
    InMemoryAuditStore, InMemoryGrantLedger, InMemorySink, MonotonicTimestamp, PersonaId,
    ResourceScope, SessionId,
};
use aether_l6_persona::CompiledPersona;

use adapter::{ModelRouterAdapter, ReflexModelRouter};
use persona::{compile_demo_persona, output_detail_from_persona, tier_from_rules, OutputDetail};

const PROVIDER_LABEL: &str = "reflex-stub";
const SESSION: &str = "demo-session";

fn main() {
    let compiled = match compile_demo_persona() {
        Ok(c) => c,
        Err(e) => {
            eprintln!("failed to compile demo persona: {e}");
            std::process::exit(1);
        }
    };
    let detail = output_detail_from_persona(&compiled);

    let engine = build_engine(&compiled);

    print_banner(&compiled, detail);

    let stdin = io::stdin();
    let mut stdout = io::stdout();
    let mut ts: u64 = 1_000;

    loop {
        print!("aether> ");
        stdout.flush().ok();

        let mut line = String::new();
        match stdin.lock().read_line(&mut line) {
            Ok(0) => {
                println!();
                break;
            }
            Ok(_) => {}
            Err(e) => {
                eprintln!("stdin error: {e}");
                break;
            }
        }

        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if matches!(trimmed, "quit" | "exit" | ":q") {
            break;
        }

        let (capability, resource) = parse_command(trimmed);
        let request = TurnRequest {
            session_id: SessionId(SESSION.to_string()),
            persona: persona_id_from(&compiled),
            task_id: None,
            utterance: trimmed.to_string(),
            capability,
            resource,
            emitted_at: MonotonicTimestamp(ts),
        };
        ts += 1;

        match engine.handle_turn(request) {
            Ok(result) => print_turn_result(&result, detail),
            Err(err) => eprintln!("[error] {err}"),
        }
    }
}

fn persona_id_from(compiled: &CompiledPersona) -> PersonaId {
    PersonaId(compiled.persona_id.0.clone())
}

fn build_engine(compiled: &CompiledPersona) -> TurnEngine {
    let persona = persona_id_from(compiled);
    let cfg = EngineConfig::wave3_default(persona);
    let policy: Arc<dyn PolicyEngine> = Arc::new(DefaultPolicyEngine::new(
        cfg,
        Arc::new(InMemoryGrantLedger::new()),
        Arc::new(InMemoryAuditStore::new()),
        Arc::new(InMemorySink::new()),
    ));

    let model_router = ReflexModelRouter::new();
    // Persona-derived tier: the compiled CompiledRoutingRules.preferred_tier
    // drives the adapter's tier choice. Cautious personas sit at local-*,
    // Bold personas at remote-*.
    let tier = tier_from_rules(&compiled.routing.preferred_tier);
    let adapter = ModelRouterAdapter::new(model_router, PROVIDER_LABEL, tier);
    let router: Arc<dyn TurnRouter> = Arc::new(adapter);

    TurnEngine::new(policy, router)
}

fn parse_command(line: &str) -> (Capability, ResourceScope) {
    let mut parts = line.splitn(2, char::is_whitespace);
    let verb = parts.next().unwrap_or("").to_ascii_lowercase();
    let arg = parts.next().unwrap_or("").trim();

    match verb.as_str() {
        "read" => (Capability::FilesRead, path_scope_or_none(arg)),
        "write" => (Capability::FilesCreate, path_scope_or_none(arg)),
        "edit" => (Capability::FilesEdit, path_scope_or_none(arg)),
        "delete" => (Capability::FilesDelete, path_scope_or_none(arg)),
        "shell" => (
            Capability::ShellExec,
            if arg.is_empty() {
                ResourceScope::None
            } else {
                ResourceScope::Path(arg.to_string())
            },
        ),
        "browse" => (
            Capability::BrowserOpen,
            if arg.is_empty() {
                ResourceScope::None
            } else {
                ResourceScope::Path(arg.to_string())
            },
        ),
        _ => (Capability::FilesRead, ResourceScope::None),
    }
}

fn path_scope_or_none(arg: &str) -> ResourceScope {
    if arg.is_empty() {
        ResourceScope::None
    } else {
        ResourceScope::Path(arg.to_string())
    }
}

fn print_banner(compiled: &CompiledPersona, detail: OutputDetail) {
    println!("Aether L1 demo — community preview.");
    println!(
        "persona     : {} (v{}, preferred tier {})",
        compiled.persona_id.0, compiled.version, compiled.routing.preferred_tier,
    );
    println!("output mode : {detail:?}");
    if !matches!(detail, OutputDetail::Terse) {
        println!();
        println!("--- system prompt (from L6) ---");
        println!("{}", compiled.prompts.system);
        println!("-------------------------------");
    }
    println!();
    println!(
        "Type a message, or try: 'read /tmp/x', 'delete /tmp/x', 'shell ls', 'browse https://…'."
    );
    println!("Ctrl+D / Ctrl+C / 'quit' to exit.");
    println!();
}

fn print_turn_result(result: &TurnResult, detail: OutputDetail) {
    match detail {
        OutputDetail::Terse => {
            let route_summary = match (&result.route, &result.block) {
                (Some(r), _) => format!("→ {}", r.response_text),
                (_, Some(b)) => format!("blocked: {}", format_block(b)),
                _ => String::from("(no route, no block)"),
            };
            println!(
                "  {} [{:?}] {route_summary}",
                result.turn_id.0, result.final_state
            );
        }
        OutputDetail::Balanced => {
            println!("  turn-id      : {}", result.turn_id.0);
            println!("  final-state  : {:?}", result.final_state);
            println!("  state-trace  : {}", format_trace(&result.state_trace));
            println!(
                "  policy       : {}",
                decision_short(&result.policy_decision)
            );
            if let Some(r) = &result.route {
                println!("  route        : tier={} provider={}", r.tier, r.provider);
                println!("  response     : {}", r.response_text);
            }
            if let Some(b) = &result.block {
                println!("  blocked      : {}", format_block(b));
            }
        }
        OutputDetail::Verbose => {
            println!("  turn-id      : {}", result.turn_id.0);
            println!("  final-state  : {:?}", result.final_state);
            println!("  state-trace  : {}", format_trace(&result.state_trace));
            println!(
                "  policy       : {}",
                format_decision(&result.policy_decision)
            );
            if let Some(r) = &result.route {
                println!("  route        : tier={} provider={}", r.tier, r.provider);
                println!("  response     : {}", r.response_text);
            }
            if let Some(b) = &result.block {
                println!("  blocked      : {}", format_block(b));
            }
        }
    }
    println!();
}

fn format_trace(trace: &[aether_l1_interaction::TurnState]) -> String {
    let parts: Vec<String> = trace.iter().map(|s| format!("{s:?}")).collect();
    parts.join(" -> ")
}

fn format_decision(d: &Decision) -> String {
    match d {
        Decision::Allow {
            grant_ref,
            audit_id,
        } => format!(
            "Allow  (grant={}, audit={})",
            grant_ref.as_ref().map(|g| g.0.as_str()).unwrap_or("-"),
            audit_id.0
        ),
        Decision::Ask { ticket, audit_id } => format!(
            "Ask    (ticket={}, audit={})",
            ticket.ticket_id.0, audit_id.0
        ),
        Decision::Deny { reason, audit_id } => {
            format!("Deny   ({reason:?}, audit={})", audit_id.0)
        }
        Decision::NeedsUpgrade {
            capability_path,
            audit_id,
            suggested_preset,
        } => format!(
            "NeedsUpgrade  (cap={}, preset={}, audit={})",
            capability_path.0,
            suggested_preset
                .as_ref()
                .map(|p| p.0.as_str())
                .unwrap_or("-"),
            audit_id.0
        ),
        Decision::DraftOnly {
            source, audit_id, ..
        } => format!("DraftOnly  ({source:?}, audit={})", audit_id.0),
    }
}

fn decision_short(d: &Decision) -> &'static str {
    match d {
        Decision::Allow { .. } => "Allow",
        Decision::Ask { .. } => "Ask",
        Decision::Deny { .. } => "Deny",
        Decision::NeedsUpgrade { .. } => "NeedsUpgrade",
        Decision::DraftOnly { .. } => "DraftOnly",
    }
}

fn format_block(b: &BlockReason) -> &'static str {
    match b {
        BlockReason::AwaitingApproval => "awaiting user approval (Ask ticket open)",
        BlockReason::Denied => "policy denied",
        BlockReason::NeedsUpgrade => "capability not in active preset (upgrade required)",
        BlockReason::DraftOnly => "draft-only (no side effects permitted)",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn req(
        compiled: &CompiledPersona,
        cap: Capability,
        resource: ResourceScope,
        text: &str,
    ) -> TurnRequest {
        TurnRequest {
            session_id: SessionId(SESSION.to_string()),
            persona: persona_id_from(compiled),
            task_id: None,
            utterance: text.to_string(),
            capability: cap,
            resource,
            emitted_at: MonotonicTimestamp(1),
        }
    }

    #[test]
    fn demo_engine_runs_allow_path_end_to_end() {
        let compiled = compile_demo_persona().unwrap();
        let engine = build_engine(&compiled);
        let r = engine
            .handle_turn(req(
                &compiled,
                Capability::FilesRead,
                ResourceScope::Path("/tmp/x".into()),
                "read /tmp/x",
            ))
            .unwrap();
        let route = r.route.expect("allow path reaches router");
        assert_eq!(route.provider, PROVIDER_LABEL);
        assert!(route.response_text.contains("read /tmp/x"));
        assert!(r.block.is_none());
        // Persona-derived tier surfaces through RouteOutcome.
        assert_eq!(route.tier, compiled.routing.preferred_tier);
    }

    #[test]
    fn demo_engine_blocks_shell_exec() {
        let compiled = compile_demo_persona().unwrap();
        let engine = build_engine(&compiled);
        let r = engine
            .handle_turn(req(
                &compiled,
                Capability::ShellExec,
                ResourceScope::None,
                "shell",
            ))
            .unwrap();
        assert_eq!(r.block, Some(BlockReason::Denied));
        assert!(r.route.is_none());
    }

    #[test]
    fn parse_command_routes_verbs_to_capabilities() {
        assert!(matches!(
            parse_command("read /tmp/x").0,
            Capability::FilesRead
        ));
        assert!(matches!(
            parse_command("delete /tmp/x").0,
            Capability::FilesDelete
        ));
        assert!(matches!(parse_command("shell ls").0, Capability::ShellExec));
        assert!(matches!(
            parse_command("browse https://example.com").0,
            Capability::BrowserOpen
        ));
        assert!(matches!(parse_command("hello").0, Capability::FilesRead));
    }
}
