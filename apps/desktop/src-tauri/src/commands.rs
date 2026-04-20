//! Tauri command surface. Every UI action goes through one of these;
//! the webview never touches engine state directly.

use std::sync::Arc;

use aether_l1_interaction::{BlockReason, TurnRequest, TurnResult, TurnState};
use aether_l2_memory::{MemoryRole, TurnMemoryRecord};
use aether_l3_presence::{PresenceController, PresenceState};
use aether_l5_policy::{
    AuditFilter, AutonomyPreset, Capability, Decision, DecisionKind, MonotonicTimestamp, PersonaId,
    ResourceScope, SessionId,
};
use aether_l7_trust::{
    approval_prompt_from_ticket, build_approval_response, human_capability, human_scope,
    ApprovalResolution,
};
use serde::Serialize;
use tauri::{AppHandle, Emitter, State};

#[cfg(feature = "ollama-provider")]
use crate::memory_router::PROVIDER_ERROR_PREFIX;
use crate::memory_router::{assistant_record, user_record};
use crate::state::{AppState, PendingTurn, TelemetryEntry, SESSION_ID};

/// Banner payload sent to the UI on startup.
#[derive(Debug, Clone, Serialize)]
pub struct CompanionBanner {
    pub persona_id: String,
    pub persona_name: String,
    pub persona_version: String,
    pub preferred_tier: String,
    pub provider_mode: String,
    pub provider_label: String,
    pub output_detail: String,
    pub tagline: String,
    pub system_prompt: String,
}

/// Message payload shown in the transcript. `kind` distinguishes user
/// lines from assistant/system lines so the UI can style them differently.
#[derive(Debug, Clone, Serialize)]
pub struct TranscriptMessage {
    pub id: String,
    pub role: String,
    pub content: String,
    pub sequence: u64,
    pub timestamp_ms: u64,
    pub meta: Option<MessageMeta>,
}

#[derive(Debug, Clone, Serialize)]
pub struct MessageMeta {
    pub tier: Option<String>,
    pub provider: Option<String>,
    /// Wall-clock ms measured by [`TurnEngine::handle_turn`] around the
    /// router dispatch call.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub latency_ms: Option<u64>,
    /// Prompt-side tokens (system + history + user) reported by the
    /// provider. `None` for the reflex stub and for provider responses
    /// that omit the counts.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub prompt_tokens: Option<u32>,
    /// Completion-side tokens the model produced.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completion_tokens: Option<u32>,
}

/// Outcome of a submitted turn. The UI branches on `kind`.
#[derive(Debug, Clone, Serialize)]
pub struct TurnOutcomePayload {
    pub turn_id: String,
    pub kind: String,
    pub message: Option<TranscriptMessage>,
    pub approval: Option<ApprovalPayload>,
    pub error_note: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ApprovalPayload {
    pub ticket_id: String,
    pub capability: String,
    pub scope: String,
    pub reason: String,
    pub risk_hint: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct PresencePayload {
    pub state: String,
    pub detail: Option<String>,
    pub updated_at_ms: u64,
}

#[tauri::command]
pub fn companion_banner(state: State<'_, AppState>) -> CompanionBanner {
    let a = state.active.read().expect("active read lock");
    CompanionBanner {
        persona_id: a.compiled.persona_id.0.clone(),
        persona_name: a.persona_display_name.clone(),
        persona_version: a.compiled.version.to_string(),
        preferred_tier: a.compiled.routing.preferred_tier.clone(),
        provider_mode: a.provider_mode.as_str().to_string(),
        provider_label: a.provider_label.clone(),
        output_detail: detail_label(a.compiled.voice.rate),
        tagline: a.persona_tagline.clone(),
        system_prompt: a.compiled.prompts.system.clone(),
    }
}

#[tauri::command]
pub fn list_personas(state: State<'_, AppState>) -> Vec<crate::state::PersonaCatalogEntry> {
    state.catalog_entries()
}

#[tauri::command]
pub fn switch_persona(
    id: String,
    state: State<'_, AppState>,
    app: AppHandle,
) -> Result<CompanionBanner, String> {
    // Capture the outgoing persona name before the swap so the banner
    // can reference *both* sides of the transition.
    let previous_name = {
        let a = state.active.read().expect("active read lock");
        a.persona_display_name.clone()
    };
    state.switch_persona(&id)?;

    // Record a system-role memory entry so the UI's transcript shows
    // an explicit "Session reset because you switched to X" line
    // instead of the session silently emptying. This runs after the
    // session clear so the banner is the first message the new
    // persona's conversation carries.
    let (new_name, ts) = {
        let a = state.active.read().expect("active read lock");
        (a.persona_display_name.clone(), state.next_ts())
    };
    let banner_text = persona_switch_banner_text(&previous_name, &new_name);
    if let Err(e) = state.memory.append(TurnMemoryRecord {
        session_id: SESSION_ID.to_string(),
        sequence: 0,
        role: MemoryRole::System,
        content: banner_text,
        timestamp_ms: ts,
    }) {
        tracing::warn!("failed to append persona-switch banner to memory: {e}");
    }

    transition_presence(
        &app,
        &state.presence,
        PresenceState::Quiet,
        state.next_ts(),
        None,
    );
    Ok(companion_banner(state))
}

/// Human-readable banner line inserted into the transcript when the
/// user switches persona. Format is "Session reset because you
/// switched to <new>. Previous context with <old> cleared." — the
/// previous name is included so the line is self-contained even if
/// the user looks at it weeks later. Kept as a free function so tests
/// can lock the copy.
pub(crate) fn persona_switch_banner_text(previous: &str, new: &str) -> String {
    format!(
        "Session reset because you switched to {new}. Previous context with {previous} cleared."
    )
}

/// Apply (or clear with `null`) the onboarding autonomy preset. Accepts
/// the same wire strings the PresetPicker writes to localStorage —
/// `"observer" | "assistant" | "operator"` — plus the picker's
/// "decide later" sentinel `"later"`, which is mapped to "no overlay"
/// on the backend. Unknown values are rejected so UI bugs surface
/// instead of silently accepting bad state.
#[tauri::command]
pub fn set_autonomy_preset(
    preset: Option<String>,
    state: State<'_, AppState>,
) -> Result<CompanionBanner, String> {
    let parsed = match preset.as_deref() {
        None | Some("") | Some("later") => None,
        Some(other) => match AutonomyPreset::from_wire(other) {
            Some(p) => Some(p),
            None => return Err(format!("unknown autonomy preset: {other}")),
        },
    };
    state.apply_preset(parsed)?;
    Ok(companion_banner(state))
}

/// Report the autonomy preset currently overlaid on the engine. `null`
/// means no overlay (baseline Assistant behaviour).
#[tauri::command]
pub fn current_autonomy_preset(state: State<'_, AppState>) -> Option<String> {
    state.current_preset().map(|p| p.wire_name().to_string())
}

/// Report of a retention-style "forget older than N days" run.
#[derive(Debug, Clone, Serialize)]
pub struct ForgetOlderReport {
    /// Rows actually removed from the conversation log.
    pub removed: u64,
    /// `true` if the command ran against a durable backend, `false`
    /// if the shell is currently on the in-memory store (no-op).
    pub applied: bool,
}

/// Explicit "forget everything older than `days` days" action for the
/// durable session memory store. Computes the wall-clock cutoff on the
/// backend so the UI cannot race the clock. Operates on the current
/// session only — cross-session forgetting would require a separate
/// "clear all history" path with a stronger confirmation.
///
/// Returns a structured report so the UI can show "Removed N entries"
/// affirmation. When the shell is running on the in-memory backend
/// (e.g. in a sandbox without a writable data dir), the command is a
/// no-op and `applied` is `false`.
#[tauri::command]
pub fn forget_older_than_days(
    days: u32,
    state: State<'_, AppState>,
) -> Result<ForgetOlderReport, String> {
    if days == 0 {
        return Err("days must be >= 1".into());
    }
    #[cfg(feature = "sqlite-backend")]
    {
        if let Some(store) = state.durable_store() {
            let now_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            let cutoff = now_ms.saturating_sub((days as u64) * 86_400 * 1_000);
            let removed = store
                .prune_older_than(SESSION_ID, cutoff)
                .map_err(|e| format!("prune: {e}"))?;
            return Ok(ForgetOlderReport {
                removed: removed as u64,
                applied: true,
            });
        }
    }
    Ok(ForgetOlderReport {
        removed: 0,
        applied: false,
    })
}

fn detail_label(rate: f32) -> String {
    if rate > 1.02 {
        "terse"
    } else if rate < 0.98 {
        "verbose"
    } else {
        "balanced"
    }
    .to_string()
}

#[tauri::command]
pub fn submit_turn(
    text: String,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<TurnOutcomePayload, String> {
    let text = text.trim().to_string();
    if text.is_empty() {
        return Err("empty input".into());
    }

    // Presence → Listening → Thinking
    transition_presence(
        &app,
        &state.presence,
        PresenceState::Listening,
        state.next_ts(),
        None,
    );
    let ts = state.next_ts();
    let (capability, resource) = parse_command(&text);
    let request = {
        let a = state.active.read().expect("active read lock");
        TurnRequest {
            session_id: SessionId(SESSION_ID.into()),
            persona: PersonaId(a.compiled.persona_id.0.clone()),
            task_id: None,
            utterance: text.clone(),
            capability,
            resource,
            emitted_at: MonotonicTimestamp(ts),
        }
    };
    transition_presence(
        &app,
        &state.presence,
        PresenceState::Thinking,
        state.next_ts(),
        None,
    );

    let first = {
        let a = state.active.read().expect("active read lock");
        match a.engine.handle_turn(request.clone()) {
            Ok(r) => r,
            Err(e) => {
                // Provider-side failures (Ollama daemon down, model not
                // installed, etc.) are surfaced as a transcript system
                // message so the UI can show actionable language instead
                // of a raw Tauri error. See memory_router.rs for the
                // mapping from typed L4Error → friendly copy.
                if let Some(msg) = extract_provider_error(&e.to_string()) {
                    drop(a);
                    return Ok(provider_error_payload(&app, &state, &request, msg));
                }
                return Err(format!("engine error: {e}"));
            }
        }
    };

    if let Decision::Ask { ticket, .. } = &first.policy_decision {
        let prompt = approval_prompt_from_ticket(ticket.clone(), None);
        let approval = ApprovalPayload {
            ticket_id: prompt.ticket.ticket_id.0.clone(),
            capability: human_capability(&prompt.capability).to_string(),
            scope: human_scope(&prompt.resource),
            reason: prompt.reason.0.clone(),
            risk_hint: "Session-only approval. This will not persist beyond this session.".into(),
        };
        transition_presence(
            &app,
            &state.presence,
            PresenceState::AwaitingApproval,
            state.next_ts(),
            Some(approval.ticket_id.clone()),
        );
        state.record_pending(
            approval.ticket_id.clone(),
            PendingTurn {
                request,
                ask_result: first.clone(),
            },
        );
        return Ok(TurnOutcomePayload {
            turn_id: first.turn_id.0,
            kind: "awaiting_approval".into(),
            message: None,
            approval: Some(approval),
            error_note: None,
        });
    }

    let payload = finalize_turn(&app, &state, &request, &first);
    Ok(payload)
}

#[tauri::command]
pub fn resolve_approval(
    ticket_id: String,
    approve: bool,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<TurnOutcomePayload, String> {
    let Some(pending) = state.take_pending(&ticket_id) else {
        return Err(format!("ticket not found: {ticket_id}"));
    };

    let ticket = match &pending.ask_result.policy_decision {
        Decision::Ask { ticket, .. } => ticket.clone(),
        _ => return Err("pending turn was not an Ask".into()),
    };
    let resolution = if approve {
        ApprovalResolution::Approve
    } else {
        ApprovalResolution::Reject
    };
    let response =
        build_approval_response(&ticket, resolution, MonotonicTimestamp(state.next_ts()));
    {
        let a = state.active.read().expect("active read lock");
        a.policy
            .respond_approval(response)
            .map_err(|e| format!("respond_approval: {e}"))?;
    }

    transition_presence(
        &app,
        &state.presence,
        PresenceState::Thinking,
        state.next_ts(),
        None,
    );

    let final_result: TurnResult = if approve {
        let a = state.active.read().expect("active read lock");
        a.engine
            .handle_turn(pending.request.clone())
            .map_err(|e| format!("post-approval engine: {e}"))?
    } else {
        // Reconstruct a denied view of the original turn.
        let audit = match &pending.ask_result.policy_decision {
            Decision::Ask { audit_id, .. } => audit_id.clone(),
            _ => unreachable!(),
        };
        let denied = Decision::Deny {
            reason: aether_l5_policy::DenyReason::ModeDeny,
            audit_id: audit,
        };
        let mut trace = pending.ask_result.state_trace.clone();
        trace.push(TurnState::PolicyDenied);
        TurnResult {
            turn_id: pending.ask_result.turn_id.clone(),
            final_state: TurnState::PolicyDenied,
            policy_decision: denied,
            route: None,
            block: Some(BlockReason::Denied),
            state_trace: trace,
        }
    };

    let payload = finalize_turn(&app, &state, &pending.request, &final_result);
    Ok(payload)
}

#[tauri::command]
pub fn presence_current(state: State<'_, AppState>) -> Result<PresencePayload, String> {
    let snap = state
        .presence
        .current(SESSION_ID)
        .map_err(|e| format!("presence: {e}"))?;
    Ok(PresencePayload {
        state: snap.state.label().to_string(),
        detail: snap.detail,
        updated_at_ms: snap.updated_at_ms,
    })
}

#[tauri::command]
pub fn memory_recent(state: State<'_, AppState>) -> Result<Vec<TranscriptMessage>, String> {
    let w = state
        .memory
        .recent(SESSION_ID)
        .map_err(|e| format!("memory: {e}"))?;
    Ok(w.records
        .into_iter()
        .map(|r| TranscriptMessage {
            id: format!("mem-{}", r.sequence),
            role: role_label(r.role).to_string(),
            content: r.content,
            sequence: r.sequence,
            timestamp_ms: r.timestamp_ms,
            meta: None,
        })
        .collect())
}

#[tauri::command]
pub fn clear_session(state: State<'_, AppState>, app: AppHandle) -> Result<(), String> {
    state.clear_session()?;
    transition_presence(
        &app,
        &state.presence,
        PresenceState::Quiet,
        state.next_ts(),
        None,
    );
    Ok(())
}

/// Audit row projected for the UI. Tiny subset of `AuditRecordEvent` —
/// enough for a trust panel showing "what did Aether decide, when, and
/// about what".
#[derive(Debug, Clone, Serialize)]
pub struct TrustAuditRow {
    pub audit_id: String,
    pub decision: String,
    pub capability: String,
    pub scope: String,
    pub change_id: String,
    pub at_mono_ns: u64,
    pub at_epoch_s: i64,
}

#[tauri::command]
pub fn audit_recent(
    limit: Option<u32>,
    state: State<'_, AppState>,
) -> Result<Vec<TrustAuditRow>, String> {
    let filter = AuditFilter::default();
    let cap = limit.unwrap_or(50).clamp(1, 500);
    let rows = {
        let a = state.active.read().expect("active read lock");
        a.audit.query(&filter, cap)
    };
    Ok(rows
        .into_iter()
        .map(|r| TrustAuditRow {
            audit_id: r.audit_id.0,
            decision: decision_kind_label(r.decision).to_string(),
            capability: aether_l7_trust::human_capability(&r.capability).to_string(),
            scope: aether_l7_trust::human_scope(&r.resource),
            change_id: r.change_id.0,
            at_mono_ns: r.timestamp_monotonic.0,
            at_epoch_s: r.timestamp_wall.epoch_s,
        })
        .collect())
}

fn decision_kind_label(k: DecisionKind) -> &'static str {
    match k {
        DecisionKind::Allow => "allow",
        DecisionKind::Ask => "ask",
        DecisionKind::Deny => "deny",
        DecisionKind::NeedsUpgrade => "needs_upgrade",
        DecisionKind::DraftOnlySystem => "draft_only_system",
        DecisionKind::DraftOnlyUserChoice => "draft_only_user_choice",
    }
}

fn role_label(r: MemoryRole) -> &'static str {
    match r {
        MemoryRole::User => "user",
        MemoryRole::Assistant => "assistant",
        MemoryRole::System => "system",
    }
}

/// Detect the provider-error marker inside the engine's `Display`
/// output. `L1Error::Router(inner)` renders as `"router: {inner}"`;
/// when `inner` starts with
/// [`crate::memory_router::PROVIDER_ERROR_PREFIX`] we strip both layers
/// and return the user-facing body. Returns `None` when the error is
/// not a provider error so the caller keeps the current fail-fast path.
fn extract_provider_error(msg: &str) -> Option<String> {
    #[cfg(feature = "ollama-provider")]
    {
        // `L1Error::Router` renders as `"router client: {payload}"`.
        // Strip the outer label if present; fall back to raw so we're
        // robust to future L1Error formatting tweaks or callers that
        // already passed us the inner payload.
        let stripped = msg.strip_prefix("router client: ").unwrap_or(msg);
        if let Some(body) = stripped.strip_prefix(PROVIDER_ERROR_PREFIX) {
            return Some(body.to_string());
        }
    }
    #[cfg(not(feature = "ollama-provider"))]
    {
        let _ = msg;
    }
    None
}

/// Synthesise a transcript payload when a provider fails before the
/// policy engine even sees the turn. The user's utterance is still
/// recorded so the transcript reads coherently; the assistant side is
/// a system-role note with the actionable copy.
fn provider_error_payload(
    app: &AppHandle,
    state: &State<'_, AppState>,
    request: &TurnRequest,
    friendly: String,
) -> TurnOutcomePayload {
    transition_presence(
        app,
        &state.presence,
        PresenceState::Responding,
        state.next_ts(),
        None,
    );
    let ts_ms = state.next_ts();
    let _ = state.memory.append(user_record(SESSION_ID, request));
    let _ = state.memory.append(aether_l2_memory::TurnMemoryRecord {
        session_id: SESSION_ID.to_string(),
        sequence: 0,
        role: MemoryRole::System,
        content: friendly.clone(),
        timestamp_ms: ts_ms,
    });
    let id = format!("provider-err-{ts_ms}");
    let persona_id = {
        let a = state.active.read().expect("active read lock");
        a.compiled.persona_id.0.clone()
    };
    state.record_telemetry(TelemetryEntry {
        turn_id: id.clone(),
        timestamp_ms: ts_ms,
        kind: "provider_error".into(),
        persona_id,
        provider: None,
        tier: None,
        latency_ms: None,
        prompt_tokens: None,
        completion_tokens: None,
    });
    transition_presence(
        app,
        &state.presence,
        PresenceState::Quiet,
        state.next_ts(),
        None,
    );
    TurnOutcomePayload {
        turn_id: id.clone(),
        kind: "provider_error".into(),
        message: Some(TranscriptMessage {
            id,
            role: "system".into(),
            content: friendly,
            sequence: 0,
            timestamp_ms: ts_ms,
            meta: None,
        }),
        approval: None,
        error_note: None,
    }
}

fn finalize_turn(
    app: &AppHandle,
    state: &State<'_, AppState>,
    request: &TurnRequest,
    result: &TurnResult,
) -> TurnOutcomePayload {
    transition_presence(
        app,
        &state.presence,
        PresenceState::Responding,
        state.next_ts(),
        None,
    );

    let ts_ms = state.next_ts();
    let _ = state.memory.append(user_record(SESSION_ID, request));
    let _ = state
        .memory
        .append(assistant_record(SESSION_ID, result, ts_ms));

    let (kind, message) = match (&result.route, &result.block) {
        (Some(r), _) => (
            "completed",
            Some(TranscriptMessage {
                id: format!("{}-response", result.turn_id.0),
                role: "assistant".into(),
                content: r.response_text.clone(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: Some(MessageMeta {
                    tier: Some(r.tier.clone()),
                    provider: Some(r.provider.clone()),
                    latency_ms: r.latency_ms,
                    prompt_tokens: r.tokens.map(|t| t.prompt),
                    completion_tokens: r.tokens.map(|t| t.completion),
                }),
            }),
        ),
        (None, Some(BlockReason::Denied)) => (
            "denied",
            Some(TranscriptMessage {
                id: format!("{}-denied", result.turn_id.0),
                role: "system".into(),
                content: "Declined — this action was not permitted.".into(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: None,
            }),
        ),
        (None, Some(BlockReason::NeedsUpgrade)) => (
            "needs_upgrade",
            Some(TranscriptMessage {
                id: format!("{}-upgrade", result.turn_id.0),
                role: "system".into(),
                content: "That capability isn't enabled in your current preset.".into(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: None,
            }),
        ),
        (None, Some(BlockReason::DraftOnly)) => (
            "draft_only",
            Some(TranscriptMessage {
                id: format!("{}-draft", result.turn_id.0),
                role: "system".into(),
                content: "Draft only — no side effects were produced.".into(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: None,
            }),
        ),
        _ => (
            "completed",
            Some(TranscriptMessage {
                id: format!("{}-empty", result.turn_id.0),
                role: "system".into(),
                content: "(no route, no block)".into(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: None,
            }),
        ),
    };

    // Record telemetry for the trust drawer's History tab. Derive
    // provider / tier / token fields from the route when present;
    // blocks produce a row too so the user can inspect denials.
    let persona_id = {
        let a = state.active.read().expect("active read lock");
        a.compiled.persona_id.0.clone()
    };
    let telemetry_entry = TelemetryEntry {
        turn_id: result.turn_id.0.clone(),
        timestamp_ms: ts_ms,
        kind: kind.to_string(),
        persona_id,
        provider: result.route.as_ref().map(|r| r.provider.clone()),
        tier: result.route.as_ref().map(|r| r.tier.clone()),
        latency_ms: result.route.as_ref().and_then(|r| r.latency_ms),
        prompt_tokens: result
            .route
            .as_ref()
            .and_then(|r| r.tokens.map(|t| t.prompt)),
        completion_tokens: result
            .route
            .as_ref()
            .and_then(|r| r.tokens.map(|t| t.completion)),
    };
    state.record_telemetry(telemetry_entry);

    transition_presence(
        app,
        &state.presence,
        PresenceState::Quiet,
        state.next_ts(),
        None,
    );

    TurnOutcomePayload {
        turn_id: result.turn_id.0.clone(),
        kind: kind.to_string(),
        message,
        approval: None,
        error_note: None,
    }
}

/// Return the newest-first telemetry entries for the Trust drawer
/// History tab. `limit` is clamped to the internal buffer capacity.
#[tauri::command]
pub fn telemetry_recent(
    limit: Option<usize>,
    state: State<'_, AppState>,
) -> Vec<TelemetryEntry> {
    let cap = crate::state::TELEMETRY_BUFFER_CAPACITY;
    let n = limit.unwrap_or(cap).min(cap);
    state.telemetry_recent(n)
}

/// Wipe the telemetry buffer. Does not affect the audit log.
#[tauri::command]
pub fn telemetry_clear(state: State<'_, AppState>) {
    state.clear_telemetry();
}

/// Parse the leading verb of a user utterance into a
/// (capability, resource) pair so approvals are reachable from the UI.
///
/// Mirrors `apps/l1-cli/src/main.rs::parse_command` — the CLI is the
/// canonical demo surface, and the desktop shell intentionally speaks
/// the same verb vocabulary so Don can exercise the same Ask/Deny/
/// NeedsUpgrade paths from either entry point. Keeping the two in sync
/// is a small cost next to having a single mental model for "what does
/// this verb trigger?".
///
/// Verbs (case-insensitive):
///   read <path>    → FilesRead      (Auto — allowed)
///   write <path>   → FilesCreate    (Ask)
///   edit <path>    → FilesEdit      (Ask)
///   delete <path>  → FilesDelete    (Ask)
///   shell <cmd>    → ShellExec      (Deny)
///   browse <url>   → BrowserOpen    (NeedsUpgrade)
///   anything else  → FilesRead with ResourceScope::None (allowed).
fn parse_command(line: &str) -> (Capability, ResourceScope) {
    let mut parts = line.splitn(2, char::is_whitespace);
    let verb = parts.next().unwrap_or("").to_ascii_lowercase();
    let arg = parts.next().unwrap_or("").trim();

    match verb.as_str() {
        "read" => (Capability::FilesRead, path_scope_or_none(arg)),
        "write" => (Capability::FilesCreate, path_scope_or_none(arg)),
        "edit" => (Capability::FilesEdit, path_scope_or_none(arg)),
        "delete" => (Capability::FilesDelete, path_scope_or_none(arg)),
        "shell" => (Capability::ShellExec, path_scope_or_none(arg)),
        "browse" => (Capability::BrowserOpen, path_scope_or_none(arg)),
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

fn transition_presence(
    app: &AppHandle,
    presence: &Arc<dyn PresenceController>,
    new_state: PresenceState,
    ts_ms: u64,
    detail: Option<String>,
) {
    if let Ok(snap) = presence.set_state(SESSION_ID, new_state, ts_ms, detail) {
        let payload = PresencePayload {
            state: snap.state.label().to_string(),
            detail: snap.detail,
            updated_at_ms: snap.updated_at_ms,
        };
        let _ = app.emit("presence:update", payload);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plain_chat_is_files_read_none() {
        let (cap, scope) = parse_command("hello there");
        assert!(matches!(cap, Capability::FilesRead));
        assert!(matches!(scope, ResourceScope::None));
    }

    #[test]
    fn read_verb_routes_to_files_read_with_path() {
        let (cap, scope) = parse_command("read /tmp/x");
        assert!(matches!(cap, Capability::FilesRead));
        match scope {
            ResourceScope::Path(p) => assert_eq!(p, "/tmp/x"),
            _ => panic!("expected path scope"),
        }
    }

    #[test]
    fn write_verb_routes_to_files_create() {
        assert!(matches!(
            parse_command("write /tmp/foo").0,
            Capability::FilesCreate
        ));
    }

    #[test]
    fn edit_verb_routes_to_files_edit() {
        assert!(matches!(
            parse_command("edit /tmp/foo").0,
            Capability::FilesEdit
        ));
    }

    #[test]
    fn delete_verb_routes_to_files_delete() {
        assert!(matches!(
            parse_command("delete /tmp/foo").0,
            Capability::FilesDelete
        ));
    }

    #[test]
    fn shell_verb_routes_to_shell_exec() {
        assert!(matches!(parse_command("shell ls").0, Capability::ShellExec));
    }

    #[test]
    fn browse_verb_routes_to_browser_open() {
        assert!(matches!(
            parse_command("browse https://example.com").0,
            Capability::BrowserOpen
        ));
    }

    #[test]
    fn verb_is_case_insensitive() {
        assert!(matches!(
            parse_command("DELETE /tmp/foo").0,
            Capability::FilesDelete
        ));
        assert!(matches!(
            parse_command("Write /tmp/foo").0,
            Capability::FilesCreate
        ));
    }

    #[cfg(feature = "ollama-provider")]
    #[test]
    fn extract_provider_error_matches_prefixed_router_message() {
        let wrapped = format!(
            "router client: {}Aether can't reach the local model daemon.",
            PROVIDER_ERROR_PREFIX
        );
        assert_eq!(
            extract_provider_error(&wrapped).as_deref(),
            Some("Aether can't reach the local model daemon."),
        );
    }

    #[cfg(feature = "ollama-provider")]
    #[test]
    fn extract_provider_error_none_for_unrelated_message() {
        assert!(extract_provider_error("router client: memory recall failed: oh no").is_none());
        assert!(extract_provider_error("policy: denied").is_none());
    }

    #[test]
    fn verb_without_arg_yields_none_scope() {
        let (cap, scope) = parse_command("delete");
        assert!(matches!(cap, Capability::FilesDelete));
        assert!(matches!(scope, ResourceScope::None));
    }

    #[test]
    fn persona_switch_banner_references_both_names() {
        let b = persona_switch_banner_text("Aurora", "Sable");
        assert!(b.contains("Aurora"), "banner should name outgoing persona");
        assert!(b.contains("Sable"), "banner should name incoming persona");
        assert!(b.to_lowercase().contains("reset"));
        assert!(b.to_lowercase().contains("cleared"));
    }

    /// Switching persona should wipe session memory (existing contract)
    /// AND leave exactly one system-role banner message so the user
    /// sees the transition instead of an empty transcript.
    #[test]
    fn switch_persona_records_system_banner_in_memory() {
        use crate::state::AppState;

        let state = AppState::new().expect("AppState::new");
        // Seed memory with a couple of turns to prove clear-and-banner
        // leaves the banner as the only record afterwards.
        state
            .memory
            .append(TurnMemoryRecord {
                session_id: SESSION_ID.to_string(),
                sequence: 0,
                role: MemoryRole::User,
                content: "first turn".into(),
                timestamp_ms: 10,
            })
            .unwrap();

        // Simulate the command body directly to avoid Tauri State plumbing.
        let previous_name = {
            let a = state.active.read().unwrap();
            a.persona_display_name.clone()
        };
        state.switch_persona("sable").unwrap();
        let (new_name, ts) = {
            let a = state.active.read().unwrap();
            (a.persona_display_name.clone(), state.next_ts())
        };
        let text = persona_switch_banner_text(&previous_name, &new_name);
        state
            .memory
            .append(TurnMemoryRecord {
                session_id: SESSION_ID.to_string(),
                sequence: 0,
                role: MemoryRole::System,
                content: text.clone(),
                timestamp_ms: ts,
            })
            .unwrap();

        let window = state.memory.recent(SESSION_ID).unwrap();
        assert_eq!(
            window.records.len(),
            1,
            "persona switch should leave exactly the banner behind",
        );
        assert_eq!(window.records[0].role, MemoryRole::System);
        assert_eq!(window.records[0].content, text);
        assert!(window.records[0].content.contains("Sable"));
    }
}
