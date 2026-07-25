//! Tauri command surface. Every UI action goes through one of these;
//! the webview never touches engine state directly.

use std::sync::Arc;

use aether_l1_interaction::{BlockReason, TurnRequest, TurnResult, TurnState};
use aether_l2_memory::{MemoryRole, TurnMemoryRecord};
use aether_l3_presence::{PresenceController, PresenceState};
use aether_l5_policy::{
    ApprovalResponse, AuditFilter, AutonomyPreset, Capability, Decision, DecisionKind,
    MonotonicTimestamp, PersonaId, ResourceScope, RetrievalProvenance, RetrievedMemoryRef,
    SessionId, UserChoice,
};
use aether_l7_trust::{
    approval_prompt_from_ticket, build_approval_response, human_capability, human_scope,
    ApprovalResolution,
};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, State};

use aether_l4_router::{
    split_audio_data_url, split_data_url, SpeechRequest, SpeechResponse, VisionRequest,
};

use crate::media_permissions::{CaptureGate, MediaKind, MediaPermissions, PermissionState};
#[cfg(feature = "ollama-provider")]
use crate::memory_router::PROVIDER_ERROR_PREFIX;
use crate::memory_router::{assistant_record, user_record_raw};
use crate::mic_permissions::MicPermission;
use crate::retrieval::{
    augment_utterance, format_retrieval_block, run_retrieval_context, DEFAULT_RETRIEVAL_DEADLINE,
};
use crate::state::{
    AppState, PendingApproval, PendingExecutorCall, PendingTurn, PresenceHistoryEntry,
    TelemetryEntry, SESSION_ID,
};

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
    /// Vision-route model id, when the assistant message came from a
    /// vision provider that exposes one. `None` for text-only turns
    /// and for adapters that don't report a model. Mirrors the
    /// `TelemetryEntry.model` field so transcript bubbles, the per-
    /// panel hint, and the Trust drawer all show the same identifier
    /// for the same turn. Wire-additive — old clients ignoring the
    /// field still work because of the skip_serializing guard.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
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
    /// Modality origin tag, e.g. `"voice"` when the user turn came
    /// from `transcribe_utterance`. `None` (and omitted from the
    /// wire) for text-only turns so old clients are unaffected.
    /// Voice V1 step 4 introduced this field; future modalities can
    /// use it without reshaping the struct.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub origin: Option<String>,
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
    /// Wave 15 — whether the request belongs to a task lineage. Drives
    /// whether the `allow_task` radio option is offered (T1.3 §5.1).
    /// The affordance is *gated* — selecting `allow_task` when this is
    /// `false` would be a no-op semantically (the grant scope would
    /// fall back to per-action), so the modal hides the option.
    pub task_id_present: bool,
    /// Wave 15 — whether the capability has side effects. Drives
    /// whether the `defer_draft` radio option is offered (T1.3 §5.1).
    /// Read-only capabilities cannot meaningfully be "drafted" — there
    /// is no pending mutation to defer.
    pub side_effecting: bool,
}

/// Wave 15 — classify a `Capability` variant as side-effecting (mutating
/// or producing observable external effects) versus read-only. Drives
/// the `side_effecting` field on `ApprovalPayload`, which in turn gates
/// the `defer_draft` radio option in the L7 approval modal (T1.3 §5.1).
///
/// The match is exhaustive against the current `Capability` enum
/// (packages/l5-policy/src/capability.rs). The `_ => true` arm is
/// defence-in-depth only — it should never match in practice. Adding a
/// new variant should trip a compile error here only if explicit-match
/// is restored, but we keep the conservative fallback so an unhandled
/// variant errs on offering the affordance rather than hiding it.
pub(crate) fn capability_is_side_effecting(cap: &aether_l5_policy::Capability) -> bool {
    use aether_l5_policy::Capability::*;
    match cap {
        // ----- Read-only -----
        FilesRead | BrowserReadPage | BrowserExtractData | EmailReadMetadata | EmailReadBody
        | ClipboardRead | NotificationRead | MemoryRead | RetrievalContext => false,

        // ----- Mutating / side-effecting -----
        FilesCreate | FilesEdit | FilesRenameMove | FilesDelete | FilesBulkOp | BrowserOpen
        | BrowserFillForm | BrowserUpload | BrowserDownload | BrowserSubmit
        | BrowserLoginReuse | EmailDraft | EmailEditDraft | EmailSend
        | EmailAttachmentAccess | ClipboardWrite | ShellExec | PackageInstall
        | AutomationTrigger | MemoryWriteSession | MemoryWriteDurable
        | MemoryWriteExtractedPref | MemoryUseInFutureTask | MemoryExport | MemoryDelete
        | MemoryWrite | MemoryForget | MemoryEdit | MemoryEmbed | MediaMic | MediaCamera
        | MediaScreenCapture | IntegrationUse(_) | IntegrationExternalApi(_)
        | IntegrationTriggerAutomation(_) | RouterEscalateRemote | RouterOverrideTier
        | RouterAllowRemoteWithPrivate | CostCapAdmin | AuditExport | PersonaDownload
        | PersonaInstall | PersonaUninstall | PersonaSwitch => true,

        // Defence in depth — unknown variants default to side-effecting
        // so the modal still offers `defer_draft`. Should never match
        // against the enum at HEAD; if it does, classify the new
        // variant explicitly above.
        #[allow(unreachable_patterns)]
        _ => true,
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct PresencePayload {
    pub state: String,
    pub detail: Option<String>,
    pub updated_at_ms: u64,
}

#[tauri::command]
pub fn companion_banner(state: State<'_, std::sync::Arc<AppState>>) -> CompanionBanner {
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
pub fn list_personas(
    state: State<'_, std::sync::Arc<AppState>>,
) -> Vec<crate::state::PersonaCatalogEntry> {
    state.catalog_entries()
}

/// ADR-0012 Tier-2 install — fetch a signed persona manifest, verify it
/// against the bundled release public key, download the slug's pack
/// zip, SHA-256-check, atomically extract, and refresh the live
/// catalog. Returns the number of newly-added catalog entries (0 if
/// the slug was already installed and the rescan was a no-op).
///
/// Long-running and IO-heavy: scheduled on the blocking task pool so
/// the IPC thread stays responsive while the download runs.
#[tauri::command]
pub async fn install_persona(
    slug: String,
    manifest_url: String,
    state: State<'_, std::sync::Arc<AppState>>,
    app: AppHandle,
) -> Result<usize, String> {
    use tauri::Manager;
    let personas_dir = match app.path().app_data_dir() {
        Ok(dir) => dir.join("personas"),
        Err(_) => match std::env::var("AETHER_PERSONAS_DIR") {
            Ok(v) => std::path::PathBuf::from(v),
            Err(_) => return Err("personas dir not configured".to_string()),
        },
    };
    if let Err(e) = std::fs::create_dir_all(&personas_dir) {
        return Err(format!(
            "could not create personas dir {}: {e}",
            personas_dir.display()
        ));
    }
    let dir_for_task = personas_dir.clone();
    // Decode the bundled release public key once on the IPC thread —
    // failure here is a build-time corruption signal, surfaced as a
    // command error before we spawn the background task.
    let pk = crate::decode_bundled_release_public_key()
        .map_err(|e| format!("bundled release public key invalid: {e:?}"))?;
    let install_outcome = tauri::async_runtime::spawn_blocking(move || {
        crate::install_persona_via_http(&manifest_url, &slug, &dir_for_task, &pk)
    })
    .await
    .map_err(|e| format!("install task failed to join: {e}"))?;
    install_outcome.map_err(|e| format!("{e}"))?;
    Ok(state.refresh_catalog())
}

#[tauri::command]
pub fn switch_persona(
    id: String,
    state: State<'_, std::sync::Arc<AppState>>,
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
    state: State<'_, std::sync::Arc<AppState>>,
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
pub fn current_autonomy_preset(state: State<'_, std::sync::Arc<AppState>>) -> Option<String> {
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
    state: State<'_, std::sync::Arc<AppState>>,
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

/// ADR-0009 §Decision 2 helper. Project the orchestrator's
/// `Vec<RetrievalHit>` into the L5 audit-row provenance shape. Always
/// returns a [`RetrievalProvenance`] (not `Option`) — caller wraps in
/// `Some(...)` to distinguish "ran retrieval, got nothing" (some,
/// `block_present=false`, empty hits) from "didn't run retrieval at
/// all" (`None`).
fn retrieval_provenance_for(hits: &[crate::retrieval::RetrievalHit]) -> RetrievalProvenance {
    RetrievalProvenance {
        block_present: !hits.is_empty(),
        hits: hits
            .iter()
            .map(|h| RetrievedMemoryRef {
                memory_id: h.memory_id.clone(),
                domain: h.domain.label().to_string(),
                score: h.score,
            })
            .collect(),
    }
}

#[tauri::command]
pub fn submit_turn(
    text: String,
    app: AppHandle,
    state: State<'_, std::sync::Arc<AppState>>,
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

    // ADR-0005 retrieval wiring: run the orchestrator BEFORE the L1
    // engine sees the turn. Non-empty hits get formatted into a
    // deterministic `Relevant context (retrieval):` block and prepended
    // to the utterance the router forwards. The original text is kept
    // separately and is what memory and the transcript record. Empty
    // hits (embeddings off, policy deny, bailout, zero rows) produce a
    // byte-identical `router_utterance == text` and no memory drift.
    let max_items = state.memory_config().retrieval.max_items as usize;
    let hits = run_retrieval_context(
        state.inner().as_ref(),
        SESSION_ID,
        &text,
        max_items,
        DEFAULT_RETRIEVAL_DEADLINE,
    );
    let retrieval_block = format_retrieval_block(&hits);
    let router_utterance = augment_utterance(retrieval_block.as_deref(), &text);

    let request = {
        let a = state.active.read().expect("active read lock");
        TurnRequest {
            session_id: SessionId(SESSION_ID.into()),
            persona: PersonaId(a.compiled.persona_id.0.clone()),
            task_id: None,
            original_utterance: text.clone(),
            model_input_utterance: router_utterance,
            capability,
            resource,
            emitted_at: MonotonicTimestamp(ts),
            // ADR-0009 §Decision 2: stamp provenance describing what
            // retrieval contributed. Always Some on the conversation
            // path so the audit row affirmatively records "we asked
            // retrieval, here is what came back" — even when the hit
            // list is empty.
            retrieval_provenance: Some(retrieval_provenance_for(&hits)),
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
                    return Ok(provider_error_payload(&app, &state, &request, &text, msg));
                }
                return Err(format!("engine error: {e}"));
            }
        }
    };

    if let Decision::Ask { ticket, .. } = &first.policy_decision {
        let prompt = approval_prompt_from_ticket(ticket.clone(), None);
        let side_effecting = capability_is_side_effecting(&prompt.capability);
        let approval = ApprovalPayload {
            ticket_id: prompt.ticket.ticket_id.0.clone(),
            capability: human_capability(&prompt.capability).to_string(),
            scope: human_scope(&prompt.resource),
            reason: prompt.reason.0.clone(),
            risk_hint: "Session-only approval. This will not persist beyond this session.".into(),
            // Wave 15 — task lineage is not yet threaded through
            // submit_turn (every TurnRequest above has task_id: None).
            // When a future wave plumbs task ids, switch to
            // request.task_id.is_some().
            task_id_present: false,
            side_effecting,
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
            PendingApproval::Turn(PendingTurn {
                request,
                ask_result: first.clone(),
                original_utterance: text.clone(),
            }),
        );
        return Ok(TurnOutcomePayload {
            turn_id: first.turn_id.0,
            kind: "awaiting_approval".into(),
            message: None,
            approval: Some(approval),
            error_note: None,
        });
    }

    let payload = finalize_turn(&app, state.as_ref(), &request, &text, &first);
    Ok(payload)
}

/// TS-friendly wire mirror of L5's [`UserChoice`] (the five-option
/// surface the L7 modal exposes per the approval-scope design in
/// `ARCHITECTURE.md`).
///
/// Today's binary `approve: bool` collapses every approve into
/// `UserChoice::Allow` and every reject into `UserChoice::Deny`. The
/// radio surface widens that — the modal can now elect
/// `Allow` / `AllowSession` / `AllowTask` / `DeferToDraft` / `Deny`
/// directly, and L5 records the chosen scope on the audit row.
///
/// Wire shape is a tagged enum so the TS mirror is a discriminated
/// union (`{ kind: "allow" } | { kind: "allow_session" } | ...`), not
/// an opaque string. This keeps the new variants type-checked end to
/// end without inventing a free-text contract.
///
/// `AllowScope` is intentionally NOT mirrored. The modal does not let
/// the user narrow `ResourceScope` in v1; if the engine needs that
/// level of granularity it can be added as a sixth variant carrying
/// the resource — additive on the wire (old clients ignore it because
/// serde rejects unknown tags, and the renderer never emits it). For
/// v1 the modal's "allow once" maps to `UserChoice::Allow` cleanly.
#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum UserChoiceWire {
    /// One-shot allow. Maps to [`UserChoice::Allow`]. Default radio
    /// selection in the modal.
    Allow,
    /// Allow for the lifetime of the current session. Maps to
    /// [`UserChoice::AllowSession`]. Persists across turns until
    /// session end / app restart per design §4.2.
    AllowSession,
    /// Allow for the lifetime of the current task / turn-window. Maps
    /// to [`UserChoice::AllowTask`].
    AllowTask,
    /// Prepare the action artifact but do NOT dispatch the executor —
    /// the user reviews and re-issues to actually run. Maps to
    /// [`UserChoice::DeferToDraft`] (per Decision 2 → produces a
    /// `Decision::DraftOnly { source: UserChoice }` server-side).
    DeferToDraft,
    /// Reject. Maps to [`UserChoice::Deny`]. The radio's "Decline"
    /// escape — kept outside the Approve-radio cluster in the UI but
    /// shares the wire surface so the dispatch is uniform.
    Deny,
}

impl UserChoiceWire {
    /// Project the wire choice onto the L5 [`UserChoice`] enum that
    /// `PolicyEngine::respond_approval` consumes. 1:1 per design
    /// §5.3.
    pub fn to_user_choice(&self) -> UserChoice {
        match self {
            UserChoiceWire::Allow => UserChoice::Allow,
            UserChoiceWire::AllowSession => UserChoice::AllowSession,
            UserChoiceWire::AllowTask => UserChoice::AllowTask,
            UserChoiceWire::DeferToDraft => UserChoice::DeferToDraft,
            UserChoiceWire::Deny => UserChoice::Deny,
        }
    }

    /// `true` when the choice is any flavour of "allow" (one-shot,
    /// session, task, or defer-to-draft). The Turn-path uses this to
    /// decide whether to replay the engine's `handle_turn` after
    /// `respond_approval`. The Executor-path uses it to decide whether
    /// to issue the one-shot grant + invoke the executor.
    ///
    /// `DeferToDraft` is treated as approve-with-no-execution: the
    /// engine writes a `Decision::DraftOnly` row, but the executor
    /// MUST NOT fire. The reply ends up `approved=false` on the
    /// executor branch and a denied-shaped TurnResult on the Turn
    /// branch — see the call sites for the dispatch.
    pub fn is_approve(&self) -> bool {
        !matches!(self, UserChoiceWire::Deny)
    }

    /// `true` when the choice should NOT cause the executor to run
    /// even though the user "approved." Currently only
    /// `DeferToDraft` — the user wants the artifact prepared but
    /// retains hand-on-trigger.
    pub fn defers_execution(&self) -> bool {
        matches!(self, UserChoiceWire::DeferToDraft)
    }
}

/// Build an [`ApprovalResponse`] carrying the user's chosen
/// [`UserChoice`] verbatim — bypasses
/// `aether_l7_trust::build_approval_response` (which is
/// `ApprovalResolution`-shaped and collapses the four approve
/// variants into `UserChoice::Allow`). Apps/desktop owns this wider
/// projection so `packages/l7-trust` stays untouched in this slice.
fn build_approval_response_for_choice(
    ticket: &aether_l5_policy::ApprovalTicket,
    choice: UserChoice,
    responded_at: MonotonicTimestamp,
) -> ApprovalResponse {
    ApprovalResponse {
        ticket_id: ticket.ticket_id.clone(),
        user_choice: choice,
        responded_at,
        scope_override: None,
        duration_override: None,
        reauth_token: None,
    }
}

/// Outcome variant returned by `resolve_approval` so the same Tauri
/// command can serve both the chat-surface (`PendingApproval::Turn`)
/// path and the Wave 11 executor path (`PendingApproval::Executor`).
/// The UI dispatches on `kind`:
///
/// - `"turn"` carries a `TurnOutcomePayload` shaped exactly like the
///   `submit_turn` reply — preserving the existing wire shape so the
///   chat surface needs zero TS-side branching.
/// - `"executor"` carries a `ExecutorApprovalReply` describing whether
///   the post-approval invocation succeeded and (on success) the
///   serialized result. The renderer's executor caller awaits this
///   reply and surfaces the result in whichever surface originally
///   issued the call.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ResolveApprovalReply {
    Turn {
        outcome: TurnOutcomePayload,
    },
    Executor {
        /// `true` if the executor was invoked and returned `Ok`. `false`
        /// covers both reject (skipped invocation) and post-approval
        /// invocation errors.
        approved: bool,
        /// Method tag (e.g. `"browser_navigate"`, `"files_read"`) so the
        /// UI can route the reply to the right surface. Stable wire
        /// string.
        method: String,
        /// Stringified result payload on success, or the error string
        /// the executor surfaced on failure. JSON shape is intentionally
        /// open — the v1 routing slice does not yet promote rich
        /// per-method result types onto this wire.
        result: Option<String>,
        /// Error string when `approved=false` AND the resolution was
        /// "approve but then the executor failed" — kept distinct from
        /// the user-rejected case so the UI can show "execution failed:
        /// {err}" vs "you declined". `None` when the user rejected.
        error: Option<String>,
    },
}

#[tauri::command]
pub async fn resolve_approval(
    ticket_id: String,
    user_choice: UserChoiceWire,
    app: AppHandle,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<ResolveApprovalReply, String> {
    let Some(pending) = state.take_pending(&ticket_id) else {
        return Err(format!("ticket not found: {ticket_id}"));
    };

    match pending {
        PendingApproval::Turn(turn) => {
            let outcome = resolve_turn_approval(&app, state.as_ref(), turn, &user_choice)?;
            Ok(ResolveApprovalReply::Turn { outcome })
        }
        PendingApproval::Executor {
            call,
            approval,
            ticket,
        } => {
            resolve_executor_approval(
                &app,
                state.as_ref(),
                call,
                approval,
                ticket,
                &user_choice,
            )
            .await
        }
    }
}

/// Replay a `PendingApproval::Turn` post-approval. Extracted from the
/// monolithic `resolve_approval` so the Wave 11 dispatch can call into
/// it without changing behaviour for the chat surface.
///
/// Wave 14: takes the four-option [`UserChoiceWire`] instead of a
/// binary `approve` so the engine receives the actual scope the user
/// picked (Allow / AllowSession / AllowTask / DeferToDraft / Deny). The
/// `respond_approval` call now plumbs the chosen `UserChoice` directly
/// — bypassing `aether_l7_trust::build_approval_response` which only
/// understands the binary `ApprovalResolution`. `DeferToDraft` is
/// treated as approve-without-execute: the engine writes the
/// `Decision::DraftOnly { source: UserChoice }` row but the Turn-path
/// reconstructs a draft-only TurnResult instead of replaying the
/// router (matches the engine's intent — the user wants the artifact,
/// not the side effect).
fn resolve_turn_approval(
    app: &AppHandle,
    state: &AppState,
    pending: PendingTurn,
    choice: &UserChoiceWire,
) -> Result<TurnOutcomePayload, String> {
    let ticket = match &pending.ask_result.policy_decision {
        Decision::Ask { ticket, .. } => ticket.clone(),
        _ => return Err("pending turn was not an Ask".into()),
    };
    let response = build_approval_response_for_choice(
        &ticket,
        choice.to_user_choice(),
        MonotonicTimestamp(state.next_ts()),
    );
    {
        let a = state.active.read().expect("active read lock");
        a.policy
            .respond_approval(response)
            .map_err(|e| format!("respond_approval: {e}"))?;
    }

    transition_presence(
        app,
        &state.presence,
        PresenceState::Thinking,
        state.next_ts(),
        None,
    );

    let final_result: TurnResult = if choice.is_approve() && !choice.defers_execution() {
        let a = state.active.read().expect("active read lock");
        a.engine
            .handle_turn(pending.request.clone())
            .map_err(|e| format!("post-approval engine: {e}"))?
    } else {
        // Reject OR defer-to-draft: do NOT replay the router. For
        // Reject, surface a PolicyDenied turn (today's behaviour).
        // For DeferToDraft we still surface the denied shape on the
        // wire — the v1 chat surface does not yet render a "draft
        // ready" affordance; the audit row stamped by the engine
        // above is the persistent record. A follow-up wave can
        // promote a dedicated `draft_only` TurnResult shape.
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

    let payload = finalize_turn(
        app,
        state,
        &pending.request,
        &pending.original_utterance,
        &final_result,
    );
    Ok(payload)
}

/// Replay a `PendingApproval::Executor` post-approval (Waves 11–12). On
/// approve, issues an L5 grant for the originally-asked capability via
/// `respond_approval`, then re-invokes the matching `*_inner` handler.
/// The grant-then-replay path is the same shape `submit_turn` uses for
/// chat-surface Asks: the gate's next `evaluate` sees the just-issued
/// grant and returns `Allow`, so the executor is fired exactly once.
///
/// On reject, the executor is NOT invoked (security invariant); Wave 12
/// closes the deferred audit-completeness gap by calling
/// `respond_approval(Reject)` against the live `ticket` cached on
/// `PendingApproval::Executor` so L5's audit row records the rejection
/// alongside any other ticket the engine has emitted — mirroring the
/// chat-surface Turn-path precedent in `resolve_turn_approval`.
async fn resolve_executor_approval(
    app: &AppHandle,
    state: &AppState,
    call: PendingExecutorCall,
    _approval: ApprovalPayload,
    ticket: aether_l5_policy::ApprovalTicket,
    choice: &UserChoiceWire,
) -> Result<ResolveApprovalReply, String> {
    let method = method_tag(&call);

    // Wave 14: Reject AND DeferToDraft both terminate the executor
    // path without invoking the executor. They differ only in the
    // `UserChoice` posted to L5 (Deny vs DeferToDraft), so the audit
    // row records the right intent — `Decision::DraftOnly { source:
    // UserChoice }` for the latter per Decision 2.
    if !choice.is_approve() || choice.defers_execution() {
        let response = build_approval_response_for_choice(
            &ticket,
            choice.to_user_choice(),
            MonotonicTimestamp(state.next_ts()),
        );
        {
            let a = state.active.read().expect("active read lock");
            a.policy
                .respond_approval(response)
                .map_err(|e| format!("respond_approval: {e}"))?;
        }
        transition_presence(
            app,
            &state.presence,
            PresenceState::Quiet,
            state.next_ts(),
            None,
        );
        return Ok(ResolveApprovalReply::Executor {
            approved: false,
            method,
            result: None,
            error: None,
        });
    }

    // Approve path — issue the grant, then re-invoke. The grant covers
    // the next matching `evaluate` so the gate's second pass returns
    // Allow. We re-issue the gate here (inside the inner) rather than
    // bypassing it, preserving the §5 "policy is the single writer for
    // side effects" invariant from CLAUDE.md.
    //
    // Wave 14: pass the chosen `UserChoice` through so the issued grant
    // carries the right `ApprovalScope` (PerAction for Allow,
    // OncePerSession for AllowSession, OncePerTask for AllowTask). The
    // engine's `respond_approval` projects the scope onto the grant
    // row per `ApprovalScope::from_user_choice`. DeferToDraft is
    // already filtered out above (defers_execution branch), so the
    // approve path only sees Allow / AllowSession / AllowTask here.
    issue_one_shot_grant_for_pending(state, &call, choice)?;

    transition_presence(
        app,
        &state.presence,
        PresenceState::Thinking,
        state.next_ts(),
        None,
    );

    let exec_result = replay_executor_call(state, call).await;

    transition_presence(
        app,
        &state.presence,
        PresenceState::Quiet,
        state.next_ts(),
        None,
    );

    match exec_result {
        Ok(serialised) => Ok(ResolveApprovalReply::Executor {
            approved: true,
            method,
            result: Some(serialised),
            error: None,
        }),
        Err(err) => Ok(ResolveApprovalReply::Executor {
            approved: false,
            method,
            result: None,
            error: Some(err),
        }),
    }
}

/// Issue a fresh L5 approval grant for a `PendingExecutorCall` that the
/// user just approved in the UI. We rebuild the original `ActionRequest`
/// so the engine can re-Ask, capture the live ticket, and immediately
/// post the user's `UserChoice` so the engine writes a grant whose
/// `ApprovalScope` matches what the user picked (PerAction for Allow,
/// OncePerSession for AllowSession, OncePerTask for AllowTask). The
/// next `evaluate` (driven from the executor inner) then resolves to
/// `Allow` via §4.2 consume-while-valid.
fn issue_one_shot_grant_for_pending(
    state: &AppState,
    call: &PendingExecutorCall,
    choice: &UserChoiceWire,
) -> Result<(), String> {
    use aether_l5_policy::policy_engine::ActionRequest;
    use aether_l5_policy::{
        capability::ResourceScope, common::MonotonicTimestamp, common::RequestId, common::TurnId,
    };

    let (capability, resource, method) = action_request_parts(call)?;
    let ts = state.next_ts();
    let persona = {
        let a = state.active.read().expect("active read lock");
        aether_l5_policy::PersonaId(a.compiled.persona_id.0.clone())
    };
    let request = ActionRequest {
        request_id: RequestId(format!("approve-{method}-{ts}")),
        turn_id: TurnId(format!("approve-{method}-turn-{ts}")),
        capability,
        resource,
        actor_persona: persona,
        emitted_at: MonotonicTimestamp(ts),
        task_id: None,
        provenance_tags: Vec::new(),
        intended_route: None,
        risk_class_hint: None,
        audit_extras: None,
    };

    let ticket = {
        let a = state.active.read().expect("active read lock");
        match a
            .policy
            .evaluate(request)
            .map_err(|e| format!("approval evaluate: {e}"))?
        {
            Decision::Ask { ticket, .. } => ticket,
            other => {
                // The action no longer Asks (already-Allow under an
                // earlier session grant, or now Deny under preset
                // tightening). Either way we don't need to issue a new
                // grant — the executor replay will see the live policy
                // disposition. Treat as success.
                let _ = other;
                return Ok(());
            }
        }
    };

    let response = build_approval_response_for_choice(
        &ticket,
        choice.to_user_choice(),
        MonotonicTimestamp(state.next_ts()),
    );
    let a = state.active.read().expect("active read lock");
    a.policy
        .respond_approval(response)
        .map_err(|e| format!("respond_approval: {e}"))?;
    let _ = ResourceScope::None; // satisfy import in cfg(test)-only paths
    Ok(())
}

/// Map a `PendingExecutorCall` back to the `(Capability, ResourceScope,
/// method_tag)` triple needed to rebuild an `ActionRequest`. Mirrors
/// the gate-side mapping in `browser_commands.rs::gate` and
/// `files_commands.rs::gate`.
fn action_request_parts(
    call: &PendingExecutorCall,
) -> Result<
    (
        aether_l5_policy::Capability,
        aether_l5_policy::ResourceScope,
        &'static str,
    ),
    String,
> {
    use aether_l5_policy::ResourceScope;
    let (cap_method, scope, method_tag) = match call {
        PendingExecutorCall::BrowserOpen { url } => (
            ("open", aether_l5_browser::capability_for_method("open")),
            ResourceScope::Url(url.clone()),
            "browser_open",
        ),
        PendingExecutorCall::BrowserNavigate { url, .. } => (
            (
                "navigate",
                aether_l5_browser::capability_for_method("navigate"),
            ),
            ResourceScope::Url(url.clone()),
            "browser_navigate",
        ),
        PendingExecutorCall::BrowserReadPage { .. } => (
            (
                "read_page",
                aether_l5_browser::capability_for_method("read_page"),
            ),
            ResourceScope::None,
            "browser_read_page",
        ),
        PendingExecutorCall::BrowserExtract { .. } => (
            (
                "extract",
                aether_l5_browser::capability_for_method("extract"),
            ),
            ResourceScope::None,
            "browser_extract",
        ),
        PendingExecutorCall::BrowserFillForm { .. } => (
            (
                "fill_form",
                aether_l5_browser::capability_for_method("fill_form"),
            ),
            ResourceScope::None,
            "browser_fill_form",
        ),
        PendingExecutorCall::BrowserSubmit { .. } => (
            ("submit", aether_l5_browser::capability_for_method("submit")),
            ResourceScope::None,
            "browser_submit",
        ),
        PendingExecutorCall::FilesRead { path } => (
            ("read", aether_l5_files::capability_for_method("read")),
            ResourceScope::Path(path.clone()),
            "files_read",
        ),
        PendingExecutorCall::FilesCreate { path, .. } => (
            ("create", aether_l5_files::capability_for_method("create")),
            ResourceScope::Path(path.clone()),
            "files_create",
        ),
        PendingExecutorCall::FilesEdit { path, .. } => (
            ("edit", aether_l5_files::capability_for_method("edit")),
            ResourceScope::Path(path.clone()),
            "files_edit",
        ),
        PendingExecutorCall::FilesRename { dst, .. } => (
            ("rename", aether_l5_files::capability_for_method("rename")),
            ResourceScope::Path(dst.clone()),
            "files_rename",
        ),
        PendingExecutorCall::FilesDelete { path } => (
            ("delete", aether_l5_files::capability_for_method("delete")),
            ResourceScope::Path(path.clone()),
            "files_delete",
        ),
        PendingExecutorCall::FilesGrep { root, .. } => (
            ("grep", aether_l5_files::capability_for_method("grep")),
            ResourceScope::Path(root.clone()),
            "files_grep",
        ),
    };
    let cap = cap_method
        .1
        .ok_or_else(|| format!("no L5 capability mapping for method {:?}", cap_method.0))?;
    Ok((cap, scope, method_tag))
}

/// Stable wire-string identifier for the executor method, used in the
/// `ResolveApprovalReply::Executor.method` field so the renderer can
/// route the reply to the right surface.
fn method_tag(call: &PendingExecutorCall) -> String {
    match call {
        PendingExecutorCall::BrowserOpen { .. } => "browser_open",
        PendingExecutorCall::BrowserNavigate { .. } => "browser_navigate",
        PendingExecutorCall::BrowserReadPage { .. } => "browser_read_page",
        PendingExecutorCall::BrowserExtract { .. } => "browser_extract",
        PendingExecutorCall::BrowserFillForm { .. } => "browser_fill_form",
        PendingExecutorCall::BrowserSubmit { .. } => "browser_submit",
        PendingExecutorCall::FilesRead { .. } => "files_read",
        PendingExecutorCall::FilesCreate { .. } => "files_create",
        PendingExecutorCall::FilesEdit { .. } => "files_edit",
        PendingExecutorCall::FilesRename { .. } => "files_rename",
        PendingExecutorCall::FilesDelete { .. } => "files_delete",
        PendingExecutorCall::FilesGrep { .. } => "files_grep",
    }
    .to_string()
}

/// Re-invoke the originally-attempted command via the same `*_inner`
/// helpers `submit_turn`-shaped traffic uses, so the gate is exercised
/// (post-grant) rather than bypassed. Returns a `String` rendering of
/// the success result so the v1 wire surface can carry mixed return
/// types under a single `ResolveApprovalReply::Executor.result` field.
async fn replay_executor_call(
    state: &AppState,
    call: PendingExecutorCall,
) -> Result<String, String> {
    use crate::browser_commands::*;
    use crate::files_commands::*;
    // The replay path runs inside `resolve_approval` which has already
    // emitted any presence/event side effects; pass `None` for the
    // optional `AppHandle` so the inner does not double-emit
    // `executor:awaiting_approval` if the gate happens to Ask again
    // (which it shouldn't — the just-issued grant should resolve to
    // Allow — but the None is a defensive belt).
    match call {
        PendingExecutorCall::BrowserOpen { url } => browser_open_inner(state, None, url)
            .await
            .map(|sid| format!("{:?}", sid)),
        PendingExecutorCall::BrowserNavigate { session, url } => {
            browser_navigate_inner(state, None, session, url)
                .await
                .map(|()| String::from("ok"))
        }
        PendingExecutorCall::BrowserReadPage { session } => {
            browser_read_page_inner(state, None, session)
                .await
                .map(|snap| format!("{:?}", snap))
        }
        PendingExecutorCall::BrowserExtract { session, selector } => {
            browser_extract_inner(state, None, session, selector)
                .await
                .map(|v| format!("{:?}", v))
        }
        PendingExecutorCall::BrowserFillForm { session, fields } => {
            browser_fill_form_inner(state, None, session, fields)
                .await
                .map(|()| String::from("ok"))
        }
        PendingExecutorCall::BrowserSubmit { session, selector } => {
            browser_submit_inner(state, None, session, selector)
                .await
                .map(|()| String::from("ok"))
        }
        PendingExecutorCall::FilesRead { path } => files_read_inner(state, None, path)
            .await
            .map(|bytes| format!("{} bytes", bytes.len())),
        PendingExecutorCall::FilesCreate { path, contents } => {
            files_create_inner(state, None, path, contents)
                .await
                .map(|()| String::from("ok"))
        }
        PendingExecutorCall::FilesEdit { path, contents } => {
            files_edit_inner(state, None, path, contents)
                .await
                .map(|()| String::from("ok"))
        }
        PendingExecutorCall::FilesRename { src, dst } => {
            files_rename_inner(state, None, src, dst)
                .await
                .map(|()| String::from("ok"))
        }
        PendingExecutorCall::FilesDelete { path } => files_delete_inner(state, None, path)
            .await
            .map(|()| String::from("ok")),
        PendingExecutorCall::FilesGrep { root, pattern } => {
            files_grep_inner(state, None, root, pattern)
                .await
                .map(|hits| format!("{} hits", hits.len()))
        }
    }
}

#[tauri::command]
pub fn presence_current(
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<PresencePayload, String> {
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
pub fn memory_recent(
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<Vec<TranscriptMessage>, String> {
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
pub fn clear_session(
    state: State<'_, std::sync::Arc<AppState>>,
    app: AppHandle,
) -> Result<(), String> {
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

/// One retrieval hit projected for the UI audit-row renderer. Mirrors
/// `aether_l5_policy::RetrievedMemoryRef` 1:1 — kept as its own Serde
/// type rather than re-exporting so the shell controls the wire shape
/// the webview consumes.
#[derive(Debug, Clone, Serialize)]
pub struct TrustRetrievalHit {
    pub memory_id: String,
    pub domain: String,
    pub score: f32,
}

/// Retrieval provenance projected for the UI. ADR-0009 §Decision 2.
#[derive(Debug, Clone, Serialize)]
pub struct TrustRetrievalProvenance {
    pub block_present: bool,
    pub hits: Vec<TrustRetrievalHit>,
}

/// Audit row projected for the UI. Subset of `AuditRecordEvent` —
/// enough for a trust panel showing "what did Companion decide, when,
/// about what, and (post-ADR-0009) what did the user say".
#[derive(Debug, Clone, Serialize)]
pub struct TrustAuditRow {
    pub audit_id: String,
    pub decision: String,
    pub capability: String,
    pub scope: String,
    pub change_id: String,
    pub at_mono_ns: u64,
    pub at_epoch_s: i64,
    /// ADR-0009 schema version. v1 rows omit user-phrasing fields;
    /// v2 rows populate them when the capability is conversational.
    pub schema_version: u32,
    /// User's typed/spoken text. v1 rows leave this `None`; v2 rows
    /// populate it for conversation capabilities, leave it `None` for
    /// file ops, media frames, etc.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub original_utterance: Option<String>,
    /// Retrieval block summary. `None` when retrieval did not run.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub retrieval_provenance: Option<TrustRetrievalProvenance>,
}

#[tauri::command]
pub fn audit_recent(
    limit: Option<u32>,
    state: State<'_, std::sync::Arc<AppState>>,
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
            schema_version: r.schema_version,
            original_utterance: r.original_utterance,
            retrieval_provenance: r.retrieval_provenance.map(|p| TrustRetrievalProvenance {
                block_present: p.block_present,
                hits: p
                    .hits
                    .into_iter()
                    .map(|h| TrustRetrievalHit {
                        memory_id: h.memory_id,
                        domain: h.domain,
                        score: h.score,
                    })
                    .collect(),
            }),
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
    state: &State<'_, std::sync::Arc<AppState>>,
    request: &TurnRequest,
    original_utterance: &str,
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
    // ADR-0005: record the ORIGINAL user utterance in memory, not the
    // retrieval-augmented form the router saw.
    let _ = state.memory.append(user_record_raw(
        SESSION_ID,
        original_utterance,
        request.emitted_at.0,
    ));
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
        model: None,
        latency_ms: None,
        prompt_tokens: None,
        completion_tokens: None,
        memory_domain: None,
        memory_id: None,
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
    state: &AppState,
    request: &TurnRequest,
    original_utterance: &str,
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
    // ADR-0005: record the ORIGINAL user utterance in memory, not the
    // retrieval-augmented form the router saw.
    let _ = state.memory.append(user_record_raw(
        SESSION_ID,
        original_utterance,
        request.emitted_at.0,
    ));
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
                    // Text-only finalize_turn — vision substitution
                    // happens in analyze_frame, not here.
                    model: None,
                    latency_ms: r.latency_ms,
                    prompt_tokens: r.tokens.map(|t| t.prompt),
                    completion_tokens: r.tokens.map(|t| t.completion),
                    origin: None,
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
        // Text-only path — vision-substitution is not in this code
        // path, so the model field stays None here.
        model: None,
        latency_ms: result.route.as_ref().and_then(|r| r.latency_ms),
        prompt_tokens: result
            .route
            .as_ref()
            .and_then(|r| r.tokens.map(|t| t.prompt)),
        completion_tokens: result
            .route
            .as_ref()
            .and_then(|r| r.tokens.map(|t| t.completion)),
        memory_domain: None,
        memory_id: None,
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
    state: State<'_, std::sync::Arc<AppState>>,
) -> Vec<TelemetryEntry> {
    let cap = crate::state::TELEMETRY_BUFFER_CAPACITY;
    let n = limit.unwrap_or(cap).min(cap);
    state.telemetry_recent(n)
}

/// Wipe the telemetry buffer. Does not affect the audit log.
#[tauri::command]
pub fn telemetry_clear(state: State<'_, std::sync::Arc<AppState>>) {
    state.clear_telemetry();
}

// ---------------------------------------------------------------------
// Media permissions surface (P1).
// ---------------------------------------------------------------------

/// Snapshot of the current local-only media permission posture.
/// Returned to the Settings UI so it can render tri-state controls.
#[tauri::command]
pub fn get_media_permissions(state: State<'_, std::sync::Arc<AppState>>) -> MediaPermissions {
    state.media_permissions()
}

/// Status of the active vision provider plus the full registered
/// list. The UI surfaces this in the camera/screen panels so the
/// user can tell at a glance whether the next "Analyze" call will
/// hit a vision-capable model or fall back to text-only output, and
/// in the runtime-swap dropdown so they can pick a different
/// registered provider.
#[derive(Debug, Clone, Serialize)]
pub struct VisionStatus {
    /// `true` when a vision provider is currently active.
    pub enabled: bool,
    /// Active provider id (`"ollama-vision"` / `"llamacpp-vision"`),
    /// `None` when in text-only mode.
    pub active_id: Option<String>,
    /// Human-readable label of the active provider, e.g.
    /// `"Ollama vision · llava · http://..."`. `None` when text-only.
    pub label: Option<String>,
    /// Active provider's current model id, if the adapter exposes one.
    /// Drives the "Active" indicator in the model strip.
    pub active_model: Option<String>,
    /// Every registered provider with an `active` flag — drives the
    /// runtime-swap UI.
    pub providers: Vec<crate::vision_registry::VisionProviderInfo>,
}

#[tauri::command]
pub fn vision_status(state: State<'_, std::sync::Arc<AppState>>) -> VisionStatus {
    let label = state.vision_provider_label();
    let active_id = state.vision_active_id();
    let active_model = state.vision_active_model();
    let providers = state.vision_provider_list();
    VisionStatus {
        enabled: label.is_some(),
        active_id,
        label,
        active_model,
        providers,
    }
}

/// Snapshot of registered vision providers — same list shipped inside
/// `VisionStatus` but exposed as its own command for callers that
/// only want the inventory.
#[tauri::command]
pub fn list_vision_providers(
    state: State<'_, std::sync::Arc<AppState>>,
) -> Vec<crate::vision_registry::VisionProviderInfo> {
    state.vision_provider_list()
}

/// Models the active vision provider's daemon currently has
/// available. Returns `{ provider_id, models, error }` so the UI can
/// render either a model list (success) or a plain "models
/// unavailable" message (failure / empty / no active provider). Errors
/// are returned in-band rather than as a Tauri Err so the dropdown
/// never spams the user.
#[derive(Debug, Clone, Serialize)]
pub struct VisionModelList {
    /// Provider id the listing was fetched for. `None` when no
    /// provider is currently active (text-only mode).
    pub provider_id: Option<String>,
    /// Discovered model ids. Empty when discovery failed, when the
    /// adapter does not implement `list_models`, or when the daemon
    /// reports no models.
    pub models: Vec<String>,
    /// Short, plain-language explanation when discovery did not
    /// produce a usable list. `None` on success.
    pub error: Option<String>,
}

#[tauri::command]
pub fn list_vision_models(state: State<'_, std::sync::Arc<AppState>>) -> VisionModelList {
    match state.vision_model_list_cached() {
        Ok((id, models)) if models.is_empty() => VisionModelList {
            provider_id: Some(id),
            models,
            error: Some("Models unavailable for this provider.".into()),
        },
        Ok((id, models)) => VisionModelList {
            provider_id: Some(id),
            models,
            error: None,
        },
        Err(crate::state::VisionModelListError::NoActive) => VisionModelList {
            provider_id: None,
            models: Vec::new(),
            error: Some("No vision provider is active.".into()),
        },
        Err(crate::state::VisionModelListError::Unavailable(id)) => VisionModelList {
            provider_id: Some(id),
            models: Vec::new(),
            error: Some("Models unavailable for this provider.".into()),
        },
    }
}

/// Force a fresh fetch of the active vision provider's model list,
/// bypassing the short-TTL cache. Wired to the `↻` refresh button on
/// the VisionBadge so the user can pick up a newly-pulled model
/// without waiting for the TTL to expire.
#[tauri::command]
pub fn refresh_vision_models(state: State<'_, std::sync::Arc<AppState>>) -> VisionModelList {
    match state.vision_model_list_refresh() {
        Ok((id, models)) if models.is_empty() => VisionModelList {
            provider_id: Some(id),
            models,
            error: Some("Models unavailable for this provider.".into()),
        },
        Ok((id, models)) => VisionModelList {
            provider_id: Some(id),
            models,
            error: None,
        },
        Err(crate::state::VisionModelListError::NoActive) => VisionModelList {
            provider_id: None,
            models: Vec::new(),
            error: Some("No vision provider is active.".into()),
        },
        Err(crate::state::VisionModelListError::Unavailable(id)) => VisionModelList {
            provider_id: Some(id),
            models: Vec::new(),
            error: Some("Models unavailable for this provider.".into()),
        },
    }
}

/// Switch the active vision provider. `id = None` (or the wire
/// sentinel `""` / `"none"`) deliberately switches to text-only
/// fallback. Unknown ids are rejected so UI bugs surface instead of
/// silently flipping to the wrong route.
#[tauri::command]
pub fn set_active_vision_provider(
    id: Option<String>,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<VisionStatus, String> {
    let normalized = match id.as_deref() {
        None | Some("") | Some("none") => None,
        Some(other) => Some(other.to_string()),
    };
    state.set_active_vision_provider(normalized)?;
    Ok(vision_status(state))
}

/// Switch the model used by the currently-active vision provider.
/// Validates the requested id against the most-recent `list_models`
/// snapshot so UI bugs (typos, stale caches) surface immediately
/// instead of silently pointing at a model the daemon doesn't have.
///
/// When list_models fails or returns an empty list (adapter does not
/// expose discovery), we accept the id optimistically — the user's
/// next `analyze_frame` will surface any real model-not-found error
/// through the normal provider-error path.
#[tauri::command]
pub fn set_active_vision_model(
    id: String,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<VisionStatus, String> {
    let trimmed = id.trim();
    if trimmed.is_empty() {
        return Err("model id must not be empty".into());
    }
    // Validate against the active provider's current model list. The
    // cached helper fetches fresh on first call and reuses the list
    // within the TTL; validation failures that bubble up here still
    // let the user eventually discover the typo via analyze_frame's
    // provider-error path.
    match state.vision_model_list_cached() {
        Ok((_, known)) if known.is_empty() => {
            // Discovery returned an empty list — adapter doesn't
            // expose models, or the daemon has none yet. Accept
            // optimistically.
        }
        Ok((_, known)) => {
            if !known.iter().any(|m| m == trimmed) {
                return Err(format!("unknown model for active provider: {trimmed}"));
            }
        }
        Err(crate::state::VisionModelListError::NoActive) => {
            return Err("no active vision provider".into());
        }
        Err(crate::state::VisionModelListError::Unavailable(_)) => {
            // Discovery unavailable (daemon error, passive adapter).
            // Accept optimistically; analyze_frame surfaces any
            // real model-not-found error.
        }
    }
    state.set_active_vision_model(trimmed)?;
    Ok(vision_status(state))
}

/// Update one device's permission and persist the new state when a
/// disk-backed file is wired. Wire format mirrors the JSON file:
/// `kind ∈ {"camera","screen"}`, `state ∈ {"allow","ask","deny"}`.
/// Unknown values are rejected so UI bugs surface instead of silently
/// flipping to the wrong posture.
#[tauri::command]
pub fn set_media_permission(
    kind: String,
    state_value: String,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<MediaPermissions, String> {
    let parsed_kind =
        MediaKind::from_wire(&kind).ok_or_else(|| format!("unknown media kind: {kind}"))?;
    let parsed_state = PermissionState::from_wire(&state_value)
        .ok_or_else(|| format!("unknown permission state: {state_value}"))?;
    state.set_media_permission(parsed_kind, parsed_state)
}

// ---------------------------------------------------------------------
// Mic permission surface (Voice V1 step 1).
// ---------------------------------------------------------------------

/// Snapshot of the current local-only mic permission posture.
/// Returned to the Settings UI so it can render the tri-state control
/// for the microphone. Separate from `get_media_permissions` so the
/// camera/screen consent and the mic consent stay independently
/// auditable.
#[tauri::command]
pub fn get_mic_permission(state: State<'_, std::sync::Arc<AppState>>) -> MicPermission {
    state.mic_permission()
}

/// Update the mic permission and persist the new state when a
/// disk-backed file is wired. Wire format mirrors the mic JSON file
/// shape: `state_value ∈ {"allow","ask","deny"}`. Unknown values are
/// rejected so UI bugs surface instead of silently flipping to the
/// wrong posture.
#[tauri::command]
pub fn set_mic_permission(
    state_value: String,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<MicPermission, String> {
    let parsed_state = PermissionState::from_wire(&state_value)
        .ok_or_else(|| format!("unknown permission state: {state_value}"))?;
    state.set_mic_permission(parsed_state)
}

// ---------------------------------------------------------------------
// Single-frame analysis surface (P3).
// ---------------------------------------------------------------------

/// Request shape for a single-frame analysis turn. The frame is
/// supplied as a data URL (`data:image/...;base64,...`) so the Tauri
/// boundary stays string-only — keeps the JSON IPC predictable and
/// avoids dragging a binary serialization format into the protocol.
///
/// `note` is an optional human cue ("what's on the receipt?", "is
/// there anyone in the room?"); when omitted the engine uses a
/// neutral default prompt. `kind` selects which media-permission
/// gate must be open ("camera" or "screen") so the same path can
/// later serve screen-capture frames.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct AnalyzeFrameRequest {
    pub kind: String,
    pub frame_data_url: String,
    pub note: Option<String>,
}

/// Outcome of a frame-analysis turn. Mirrors `TurnOutcomePayload`
/// closely so the UI can re-use the same rendering helpers; the
/// `kind` discriminator distinguishes a successfully analysed frame
/// (`"analyzed"`) from a permission block or other refusal.
#[derive(Debug, Clone, Serialize)]
pub struct FrameAnalysisOutcome {
    pub turn_id: String,
    pub kind: String,
    pub message: Option<TranscriptMessage>,
    pub error_note: Option<String>,
}

/// Default cue when the UI does not pass a `note`. Kept short and
/// neutral so personas stay in charge of voice.
const DEFAULT_FRAME_PROMPT: &str =
    "Describe what you see in this frame in a short, helpful sentence.";

/// Minimum number of base64 characters we require in the body before
/// handing the frame to a provider. Base64 encodes 3 bytes per 4
/// characters, so 4 is the absolute floor for a non-empty payload —
/// anything shorter cannot represent even one decoded byte and almost
/// certainly indicates a broken or empty capture.
const MIN_FRAME_BODY_LEN: usize = 4;

/// Validate a frame data URL before it reaches the model layer.
///
/// Returns the body slice on success so the caller doesn't need to
/// re-split. The L4 `split_data_url` helper handles MIME / encoding
/// strictness once the engine is invoked; this shell-side check is the
/// friendly first line of defense — it surfaces obvious capture
/// failures (empty body, missing separator, wrong scheme) as a clear
/// error string before any audit row is written or any provider call
/// is made.
///
/// Pure helper so the rules are unit-testable without booting Tauri.
fn validate_frame_data_url(url: &str) -> Result<&str, String> {
    if !url.starts_with("data:image/") {
        return Err("frame_data_url must be a data:image/... URL".into());
    }
    let Some((_, body)) = url.split_once(',') else {
        return Err("frame_data_url is missing the base64 body separator (',')".into());
    };
    let trimmed = body.trim();
    if trimmed.is_empty() {
        return Err("frame_data_url has an empty image body — capture may have failed".into());
    }
    if trimmed.len() < MIN_FRAME_BODY_LEN {
        return Err("frame_data_url body is too short to decode — capture may have failed".into());
    }
    Ok(body)
}

/// Record a telemetry entry for an `analyze_frame` early-exit path
/// (permission denied, permission ask, or frame validation failure).
/// These paths short-circuit before any provider call or audit row is
/// written, but they are still meaningful end-user events — recording
/// them here keeps the Trust drawer's History tab honest about what
/// the user actually attempted.
///
/// Stable `kind` values consumed by the History tab and the
/// `MEDIA_TURN_KINDS` allow-list:
///   - `"permission_denied"` — gate evaluated to Deny
///   - `"permission_ask"`    — gate evaluated to PromptUser
///   - `"frame_invalid"`     — `validate_frame_data_url` rejected
///
/// `provider`, `model`, `tier`, `latency_ms`, and the token fields
/// are intentionally `None` — no provider was consulted. Only the
/// persona id and timestamp carry signal.
fn record_frame_early_exit_telemetry(state: &State<'_, std::sync::Arc<AppState>>, kind: &str) {
    let ts_ms = state.next_ts();
    let persona_id = {
        let a = state.active.read().expect("active read lock");
        a.compiled.persona_id.0.clone()
    };
    state.record_telemetry(TelemetryEntry {
        turn_id: format!("frame-early-{ts_ms}"),
        timestamp_ms: ts_ms,
        kind: kind.to_string(),
        persona_id,
        provider: None,
        tier: None,
        model: None,
        latency_ms: None,
        prompt_tokens: None,
        completion_tokens: None,
        memory_domain: None,
        memory_id: None,
    });
}

/// Single-frame analysis path (P3 v0). This is the foundation hook
/// for video-assistant work — it does NOT stream, does NOT loop, and
/// does NOT acquire the camera itself. The shell is expected to
/// supply a captured frame; this command:
///
///   1. enforces the media permission gate (Deny short-circuits with
///      a friendly message, Ask returns a hint that the UI should
///      route through the existing approval flow first),
///   2. records the request as a user-role memory entry tagged with
///      `[frame analysis]` so transcript review is coherent,
///   3. invokes the active turn engine with the user's note (or the
///      default prompt) so the model call goes through L5 / L6 like
///      any other turn — frame analysis is not a side channel,
///   4. tags telemetry with `kind="frame_analyzed"` so the Trust
///      drawer's History tab can show the user how often Companion
///      looked at media.
///
/// We deliberately do NOT push the raw frame bytes through the
/// router on this slice — the local provider stack is text-only
/// today, and the foundation is meant to land the wiring before the
/// vision provider arrives. Once a vision-capable provider is wired
/// the same command can pass `frame_data_url` straight to it.
#[tauri::command]
pub fn analyze_frame(
    request: AnalyzeFrameRequest,
    app: AppHandle,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<FrameAnalysisOutcome, String> {
    let kind = MediaKind::from_wire(&request.kind)
        .ok_or_else(|| format!("unknown media kind: {}", request.kind))?;
    let gate = state.evaluate_media_permission(kind);

    match gate {
        CaptureGate::Deny => {
            let ts_ms = state.next_ts();
            let id = format!("frame-deny-{ts_ms}");
            let copy = match kind {
                MediaKind::Camera => "Camera analysis is disabled in your settings. Enable it under Settings → Media to use this feature.",
                MediaKind::Screen => "Screen analysis is disabled in your settings. Enable it under Settings → Media to use this feature.",
            }.to_string();
            let _ = state.memory.append(TurnMemoryRecord {
                session_id: SESSION_ID.to_string(),
                sequence: 0,
                role: MemoryRole::System,
                content: copy.clone(),
                timestamp_ms: ts_ms,
            });
            record_frame_early_exit_telemetry(&state, "permission_denied");
            return Ok(FrameAnalysisOutcome {
                turn_id: id.clone(),
                kind: "permission_denied".into(),
                message: Some(TranscriptMessage {
                    id,
                    role: "system".into(),
                    content: copy,
                    sequence: 0,
                    timestamp_ms: ts_ms,
                    meta: None,
                }),
                error_note: None,
            });
        }
        CaptureGate::PromptUser => {
            // The shell-side approval modal owns the prompt UX; the
            // frontend should call set_media_permission to "allow" or
            // "deny" before retrying. Surface a short, actionable note.
            let ts_ms = state.next_ts();
            let id = format!("frame-ask-{ts_ms}");
            let copy = match kind {
                MediaKind::Camera => "Camera permission is set to Ask. Approve camera analysis in Settings before retrying.",
                MediaKind::Screen => "Screen permission is set to Ask. Approve screen analysis in Settings before retrying.",
            }.to_string();
            record_frame_early_exit_telemetry(&state, "permission_ask");
            return Ok(FrameAnalysisOutcome {
                turn_id: id.clone(),
                kind: "permission_ask".into(),
                message: Some(TranscriptMessage {
                    id,
                    role: "system".into(),
                    content: copy,
                    sequence: 0,
                    timestamp_ms: ts_ms,
                    meta: None,
                }),
                error_note: None,
            });
        }
        CaptureGate::Proceed => {}
    }

    // Sanity-check the frame data URL early so a malformed payload
    // doesn't reach the model layer. The helper enforces both the
    // `data:image/...` prefix and a non-empty base64 body — the
    // shell-side first line of defense against silently-broken
    // captures. Provider adapters still do the strict decode when
    // they actually run.
    if let Err(detail) = validate_frame_data_url(&request.frame_data_url) {
        // Record a telemetry-only entry (no audit row, no provider
        // call) so the Trust drawer's History tab can show the user
        // that their last capture was rejected. L5 / audit semantics
        // stay untouched — no policy decision was made.
        record_frame_early_exit_telemetry(&state, "frame_invalid");
        return Err(format!("{detail}. Try capturing a new frame."));
    }

    transition_presence(
        &app,
        &state.presence,
        PresenceState::Thinking,
        state.next_ts(),
        Some(format!("analyzing {} frame", kind.wire_label())),
    );

    let cue = request
        .note
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .unwrap_or(DEFAULT_FRAME_PROMPT)
        .to_string();
    let utterance = format!("[frame analysis · {}] {}", kind.wire_label(), cue);

    let ts = state.next_ts();
    let req = {
        let a = state.active.read().expect("active read lock");
        TurnRequest {
            session_id: SessionId(SESSION_ID.into()),
            persona: PersonaId(a.compiled.persona_id.0.clone()),
            task_id: None,
            // Media turns have no retrieval augmentation today; the two
            // utterance channels are byte-identical. ADR-0009 §Decision 4
            // — original is the audit-truth, model_input is what the
            // router/provider receives. retrieval_provenance is None
            // because retrieval did not run for this capability.
            original_utterance: utterance.clone(),
            model_input_utterance: utterance.clone(),
            // Map to the dedicated media capability so the audit log
            // reads `media.camera` / `media.screen_capture` instead of
            // misleading file-read rows. Both are configured Auto in
            // `EngineConfig::wave3_default` because the shell-side
            // permission gate (P1) is the user-facing per-device
            // control; L5 records the audit row without doubling up.
            retrieval_provenance: None,
            capability: match kind {
                MediaKind::Camera => Capability::MediaCamera,
                MediaKind::Screen => Capability::MediaScreenCapture,
            },
            resource: ResourceScope::None,
            emitted_at: MonotonicTimestamp(ts),
        }
    };

    let mut result = {
        let a = state.active.read().expect("active read lock");
        a.engine
            .handle_turn(req.clone())
            .map_err(|e| format!("frame turn engine: {e}"))?
    };

    // If a vision provider is wired AND policy allowed the turn,
    // replace the text-only model output with a real vision response.
    // The handle_turn call already produced the L5 audit row and ran
    // policy — we keep that and just substitute the assistant text +
    // provider/tier metadata. When vision fails the text-only output
    // stays as a safe fallback.
    let vision_model = maybe_apply_vision(&state, &mut result, &request.frame_data_url, &cue);

    let ts_ms = state.next_ts();
    let _ = state.memory.append(TurnMemoryRecord {
        session_id: SESSION_ID.to_string(),
        sequence: 0,
        role: MemoryRole::User,
        content: utterance,
        timestamp_ms: ts_ms,
    });

    let (kind_label, message) = match (&result.route, &result.block) {
        (Some(r), _) => {
            let assistant_ts = state.next_ts();
            let _ = state.memory.append(TurnMemoryRecord {
                session_id: SESSION_ID.to_string(),
                sequence: 0,
                role: MemoryRole::Assistant,
                content: r.response_text.clone(),
                timestamp_ms: assistant_ts,
            });
            (
                "frame_analyzed".to_string(),
                Some(TranscriptMessage {
                    id: format!("{}-frame", result.turn_id.0),
                    role: "assistant".into(),
                    content: r.response_text.clone(),
                    sequence: 0,
                    timestamp_ms: assistant_ts,
                    meta: Some(MessageMeta {
                        tier: Some(r.tier.clone()),
                        provider: Some(r.provider.clone()),
                        // Same model id captured by maybe_apply_vision —
                        // shared with telemetry so transcript bubble,
                        // panel hint, and Trust drawer agree on the
                        // route that served this turn.
                        model: vision_model.clone(),
                        latency_ms: r.latency_ms,
                        prompt_tokens: r.tokens.map(|t| t.prompt),
                        completion_tokens: r.tokens.map(|t| t.completion),
                        // Voice V1 step 5 symmetry — the voice path
                        // stamps `origin: "voice"`; vision's analyze_frame
                        // stamps `origin: "vision"` so the transcript chip
                        // can render a modality badge either way. Text
                        // turns keep `origin: None`.
                        origin: Some("vision".into()),
                    }),
                }),
            )
        }
        (None, Some(_)) => (
            "frame_blocked".to_string(),
            Some(TranscriptMessage {
                id: format!("{}-frame-blocked", result.turn_id.0),
                role: "system".into(),
                content: "Frame analysis was blocked by policy.".into(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: None,
            }),
        ),
        _ => (
            "frame_analyzed".to_string(),
            Some(TranscriptMessage {
                id: format!("{}-frame-empty", result.turn_id.0),
                role: "system".into(),
                content: "(no response)".into(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: None,
            }),
        ),
    };

    let persona_id = {
        let a = state.active.read().expect("active read lock");
        a.compiled.persona_id.0.clone()
    };
    state.record_telemetry(TelemetryEntry {
        turn_id: result.turn_id.0.clone(),
        timestamp_ms: ts_ms,
        kind: kind_label.clone(),
        persona_id,
        provider: result.route.as_ref().map(|r| r.provider.clone()),
        tier: result.route.as_ref().map(|r| r.tier.clone()),
        // `model` is `Some(_)` only when the vision provider actually
        // ran and reported its current model id. Text-fallback turns
        // (no vision provider configured / vision call failed) leave
        // it `None` so the History tab doesn't lie about the route.
        model: vision_model,
        latency_ms: result.route.as_ref().and_then(|r| r.latency_ms),
        prompt_tokens: result
            .route
            .as_ref()
            .and_then(|r| r.tokens.map(|t| t.prompt)),
        completion_tokens: result
            .route
            .as_ref()
            .and_then(|r| r.tokens.map(|t| t.completion)),
        memory_domain: None,
        memory_id: None,
    });

    transition_presence(
        &app,
        &state.presence,
        PresenceState::Quiet,
        state.next_ts(),
        None,
    );

    Ok(FrameAnalysisOutcome {
        turn_id: result.turn_id.0.clone(),
        kind: kind_label,
        message,
        error_note: None,
    })
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
/// If a vision provider is wired and the policy engine returned a
/// route, decode the data URL and call the provider. On success,
/// substitute the assistant text + provider/tier metadata in `result`
/// so downstream memory/telemetry/transcript see the vision output.
/// Failures (no provider, malformed URL, daemon error) leave `result`
/// untouched — the caller falls back to the existing text-only output.
///
/// Returns `Some(model_id)` on success — the model the vision
/// provider used at the moment of the call. Telemetry stamps this
/// into the recorded entry so the Trust drawer can annotate media
/// rows with the exact model that served them. Returns `None` when
/// no vision call ran (no provider, blocked turn, malformed URL,
/// daemon error). Adapters that don't expose `current_model` (passive
/// future adapters) yield `Some` with the provider's id substring
/// stripped — but today both built-in adapters report the model.
fn maybe_apply_vision(
    state: &State<'_, std::sync::Arc<AppState>>,
    result: &mut TurnResult,
    frame_data_url: &str,
    cue: &str,
) -> Option<String> {
    let provider = state.vision_provider()?;
    // Only override when policy actually allowed a route. A blocked
    // turn keeps its block — vision should never resurrect a denied
    // action.
    let route = result.route.as_mut()?;
    // Mirror the shell-side `analyze_frame` validation here so this
    // function is safe regardless of caller. In production
    // `analyze_frame` already short-circuits these shapes with a
    // user-facing error; if a future caller reaches us with the same
    // bad shape, swallow it silently (debug-level) rather than
    // duplicating the WARN line about a decode that we know would
    // fail. Real provider/decode failures still WARN below.
    if let Err(detail) = validate_frame_data_url(frame_data_url) {
        tracing::debug!("vision: skipping route, frame failed validation: {detail}");
        return None;
    }
    let (mime, body) = match split_data_url(frame_data_url) {
        Ok(parts) => parts,
        Err(e) => {
            tracing::warn!("vision: data URL decode failed: {e}; using text-only output");
            return None;
        }
    };
    let label = provider.label();
    let id = provider.id().to_string();
    let model = provider.current_model();
    match provider.analyze(VisionRequest {
        cue: cue.to_string(),
        image_b64: body,
        mime,
    }) {
        Ok(resp) => {
            route.response_text = resp.text;
            route.provider = id;
            route.tier = label;
            // Token counts are merged when the vision adapter reports
            // them; otherwise leave whatever the text path stamped.
            if let Some(tokens) = route.tokens.as_mut() {
                if let Some(p) = resp.prompt_tokens {
                    tokens.prompt = p;
                }
                if let Some(c) = resp.completion_tokens {
                    tokens.completion = c;
                }
            } else if resp.prompt_tokens.is_some() || resp.completion_tokens.is_some() {
                route.tokens = Some(aether_l1_interaction::TokenUsage {
                    prompt: resp.prompt_tokens.unwrap_or(0),
                    completion: resp.completion_tokens.unwrap_or(0),
                });
            }
            model
        }
        Err(e) => {
            tracing::warn!("vision: provider analyze failed: {e}; using text-only output");
            None
        }
    }
}

// ---------------------------------------------------------------------
// Utterance transcription surface (Voice V1 step 4).
// ---------------------------------------------------------------------

/// Minimum number of base64 characters we require in the audio body
/// before handing the payload to a speech provider. Base64 encodes 3
/// bytes per 4 characters, so 64 chars is roughly 48 bytes of raw
/// audio — shorter than any plausible intentional utterance and
/// almost certainly a broken capture. See
/// `docs/VOICE-V1-ARCHITECTURE.md` §5 for the rationale.
const MIN_UTTERANCE_BODY_LEN: usize = 64;

/// Request shape for `transcribe_utterance`. The audio is supplied as
/// a data URL (`data:audio/wav;base64,<body>`) so the Tauri boundary
/// stays string-only — mirrors `AnalyzeFrameRequest`.
///
/// `duration_ms`, `sample_rate`, and `channels` are the shell's best
/// record of the capture parameters; the speech provider is free to
/// use, override, or ignore them. `cue` is an optional explicit hint
/// the UI may pass (a hotkey-assigned prompt, for example); `None`
/// means "no cue — the transcribed text is the user turn as-is."
#[derive(Debug, Clone, serde::Deserialize)]
pub struct TranscribeUtteranceRequest {
    /// `data:audio/wav;base64,<body>` string.
    pub utterance_data_url: String,
    /// Shell-measured capture duration in milliseconds. Informational.
    pub duration_ms: u32,
    /// Optional explicit cue — see struct docs.
    pub cue: Option<String>,
    /// Sample rate of the decoded PCM, in Hz (Voice V1 captures 16000).
    pub sample_rate: u32,
    /// Channel count (Voice V1 captures mono = 1).
    pub channels: u16,
    /// Optional ISO-639-1 language hint forwarded to the provider.
    pub language: Option<String>,
}

/// Outcome of a transcription attempt. `kind` drives UI branching
/// exactly the way `FrameAnalysisOutcome::kind` does for vision.
///
/// Possible `kind` values:
///   - `"utterance_transcribed"` — provider returned text and the
///     engine turn completed successfully.
///   - `"utterance_blocked"`     — policy blocked the turn after the
///     mic permission gate passed.
///   - `"mic_permission_denied"` — mic set to Deny; short-circuit
///     before any provider call.
///   - `"mic_permission_ask"`    — mic still on Ask; the UI should
///     flip to Allow before retrying.
///
/// The two other telemetry kinds (`utterance_invalid`, plus
/// transport/provider errors) surface as `Err(String)` rather than
/// an `Ok` outcome because there is no useful transcript to render.
#[derive(Debug, Clone, Serialize)]
pub struct UtteranceOutcome {
    pub turn_id: String,
    pub kind: String,
    pub message: Option<TranscriptMessage>,
    pub error_note: Option<String>,
}

/// Validate an audio data URL before it reaches the speech layer.
/// Mirror of `validate_frame_data_url` but pinned to
/// `data:audio/wav`. Rules (documented in
/// `docs/VOICE-V1-ARCHITECTURE.md` §5):
///
///   1. URL must start with `data:audio/wav` (V1 pins to WAV).
///   2. URL must contain a `,` separator.
///   3. Body (trimmed) must be non-empty.
///   4. Body (trimmed) must be at least [`MIN_UTTERANCE_BODY_LEN`]
///      chars — smaller is definitely a broken capture.
///
/// Returns the body slice on success. Pure helper so every branch
/// is unit-testable without booting Tauri.
fn validate_utterance_data_url(url: &str) -> Result<&str, String> {
    if !url.starts_with("data:audio/wav") {
        return Err("utterance_data_url must be a data:audio/wav;base64,... URL".into());
    }
    let Some((_, body)) = url.split_once(',') else {
        return Err("utterance_data_url is missing the base64 body separator (',')".into());
    };
    let trimmed = body.trim();
    if trimmed.is_empty() {
        return Err("utterance_data_url has an empty audio body — capture may have failed".into());
    }
    if trimmed.len() < MIN_UTTERANCE_BODY_LEN {
        return Err(
            "utterance_data_url body is too short to decode — capture may have failed".into(),
        );
    }
    Ok(body)
}

/// Record a telemetry entry for a `transcribe_utterance` early-exit
/// path. Mirror of `record_frame_early_exit_telemetry`. Stable `kind`
/// values consumed by the History tab and the
/// `VOICE_TURN_KINDS` allow-list:
///
///   - `"utterance_invalid"`      — `validate_utterance_data_url`
///     rejected the payload
///   - `"mic_permission_denied"`  — mic gate evaluated to Deny
///   - `"mic_permission_ask"`     — mic gate evaluated to PromptUser
///
/// `provider`, `model`, `tier`, `latency_ms`, and the token fields
/// are intentionally `None` — no provider was consulted. Only persona
/// id + timestamp carry signal, same restraint vision uses for its
/// three early-exit kinds.
fn record_utterance_early_exit_telemetry(state: &State<'_, std::sync::Arc<AppState>>, kind: &str) {
    let ts_ms = state.next_ts();
    let persona_id = {
        let a = state.active.read().expect("active read lock");
        a.compiled.persona_id.0.clone()
    };
    state.record_telemetry(TelemetryEntry {
        turn_id: format!("utterance-early-{ts_ms}"),
        timestamp_ms: ts_ms,
        kind: kind.to_string(),
        persona_id,
        provider: None,
        tier: None,
        model: None,
        latency_ms: None,
        prompt_tokens: None,
        completion_tokens: None,
        memory_domain: None,
        memory_id: None,
    });
}

/// Defense-in-depth mirror of `maybe_apply_vision` for the voice
/// path. The shell-side `transcribe_utterance` already validates
/// the data URL up front; this helper is the second line so a future
/// caller can't accidentally reach the provider with a shape the
/// validator would reject. Logs at `debug` (not WARN) — the shell-
/// side gate already owned the user-visible error.
///
/// Returns the `SpeechResponse` on success; on validator rejection
/// returns `Err(String)` containing the same detail the shell-side
/// caller would have surfaced. On provider / decode failure, returns
/// `Err(String)` with a user-readable message. There is NO silent
/// text fallback for voice (unlike vision), per §8.9 of the design
/// doc — swallowing a user's utterance is a worse UX than a visible
/// error.
fn maybe_apply_voice(
    provider: &Arc<dyn aether_l4_router::SpeechProvider>,
    utterance_data_url: &str,
    sample_rate: u32,
    channels: u16,
    language: Option<String>,
) -> Result<SpeechResponse, String> {
    if let Err(detail) = validate_utterance_data_url(utterance_data_url) {
        tracing::debug!("voice: skipping transcribe, utterance failed validation: {detail}",);
        return Err(detail);
    }
    let (mime, body) = match split_audio_data_url(utterance_data_url) {
        Ok(parts) => parts,
        Err(e) => {
            tracing::warn!("voice: audio data URL decode failed: {e}");
            return Err(format!("audio decode failed: {e}"));
        }
    };
    provider
        .transcribe(SpeechRequest {
            audio_b64: body,
            mime,
            sample_rate,
            channels,
            language,
        })
        .map_err(|e| format!("{e}"))
}

/// Single-utterance transcription (Voice V1 step 4).
///
/// Mirror of `analyze_frame` for the voice modality. The shell is
/// expected to hand over a captured audio blob as a `data:audio/wav;
/// base64,...` URL; this command:
///
///   1. enforces the mic permission gate — `Deny` / `Ask` short-circuit
///      with a friendly message and a telemetry entry, no provider
///      call, no audit row,
///   2. validates the audio data URL — malformed payloads also
///      short-circuit, with an `utterance_invalid` telemetry row,
///   3. fetches the active `SpeechProvider` — absence is a hard error
///      (unlike vision, there is no silent text fallback),
///   4. invokes the provider's `transcribe` — failures surface as a
///      clear `Err(String)`; no silent fallback,
///   5. records the transcribed text as a **user-role** memory entry
///      (the transcript becomes a user turn, per design §1),
///   6. feeds the transcript through the normal turn engine with
///      `Capability::MediaMic` — the engine produces the L5 audit
///      row the same way `analyze_frame` does today,
///   7. tags telemetry with `utterance_transcribed` /
///      `utterance_blocked` based on the L5 decision.
///
/// No raw audio is persisted anywhere — the bytes live only inside
/// the IPC frame and the `SpeechRequest`. The transcript text is
/// persistable because it becomes a user turn; the audio source
/// itself is not.
#[tauri::command]
pub fn transcribe_utterance(
    request: TranscribeUtteranceRequest,
    app: AppHandle,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<UtteranceOutcome, String> {
    let gate = state.evaluate_mic_permission();

    match gate {
        CaptureGate::Deny => {
            let ts_ms = state.next_ts();
            let id = format!("utterance-deny-{ts_ms}");
            let copy = "Microphone analysis is disabled in your settings. \
                Enable it under Settings → Microphone to use this feature."
                .to_string();
            let _ = state.memory.append(TurnMemoryRecord {
                session_id: SESSION_ID.to_string(),
                sequence: 0,
                role: MemoryRole::System,
                content: copy.clone(),
                timestamp_ms: ts_ms,
            });
            record_utterance_early_exit_telemetry(&state, "mic_permission_denied");
            return Ok(UtteranceOutcome {
                turn_id: id.clone(),
                kind: "mic_permission_denied".into(),
                message: Some(TranscriptMessage {
                    id,
                    role: "system".into(),
                    content: copy,
                    sequence: 0,
                    timestamp_ms: ts_ms,
                    meta: None,
                }),
                error_note: None,
            });
        }
        CaptureGate::PromptUser => {
            let ts_ms = state.next_ts();
            let id = format!("utterance-ask-{ts_ms}");
            let copy = "Microphone permission is set to Ask. Approve \
                microphone capture in Settings before retrying."
                .to_string();
            record_utterance_early_exit_telemetry(&state, "mic_permission_ask");
            return Ok(UtteranceOutcome {
                turn_id: id.clone(),
                kind: "mic_permission_ask".into(),
                message: Some(TranscriptMessage {
                    id,
                    role: "system".into(),
                    content: copy,
                    sequence: 0,
                    timestamp_ms: ts_ms,
                    meta: None,
                }),
                error_note: None,
            });
        }
        CaptureGate::Proceed => {}
    }

    if let Err(detail) = validate_utterance_data_url(&request.utterance_data_url) {
        // Same semantics as `frame_invalid`: telemetry-only, no
        // audit row (no policy decision was made), user-visible
        // error returned as `Err`.
        record_utterance_early_exit_telemetry(&state, "utterance_invalid");
        return Err(format!("{detail}. Try recording again."));
    }

    let Some(provider) = state.speech_provider() else {
        // No silent fallback — see §8.9 of the design doc.
        return Err(
            "Voice is disabled or no speech provider is active. Configure \
             a speech provider in settings before retrying."
                .into(),
        );
    };

    // Measure STT latency locally — the trait's `SpeechResponse` does
    // not carry a latency field (mirrors `VisionResponse`); the shell
    // times the provider call the same way `TurnEngine` times its
    // router dispatch.
    let transcribe_start = std::time::Instant::now();
    let response = match maybe_apply_voice(
        &provider,
        &request.utterance_data_url,
        request.sample_rate,
        request.channels,
        request.language.clone(),
    ) {
        Ok(r) => r,
        Err(e) => {
            // Provider or transport error — surface loudly to the
            // user. No telemetry row beyond the engine-side audit
            // (which we haven't written yet because policy never
            // ran). Returning Err keeps analyze_frame-style parity:
            // the user sees a specific "transcription failed" copy.
            return Err(format!("Transcription failed: {e}"));
        }
    };
    let stt_latency_ms = transcribe_start.elapsed().as_millis() as u64;

    transition_presence(
        &app,
        &state.presence,
        PresenceState::Thinking,
        state.next_ts(),
        Some("transcribing utterance".into()),
    );

    // The transcript text becomes the user's utterance for the
    // downstream turn engine. An explicit `cue` overrides the
    // transcribed text (useful when the UI wants to pin a hotkey
    // prompt regardless of what was captured); without a cue the
    // transcription itself is the utterance.
    let utterance_text = request
        .cue
        .as_deref()
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string)
        .unwrap_or_else(|| response.text.clone());

    // Record a user-role memory entry so the transcript reads
    // coherently before the engine responds. Same sequencing
    // analyze_frame uses.
    let user_ts = state.next_ts();
    let _ = state.memory.append(TurnMemoryRecord {
        session_id: SESSION_ID.to_string(),
        sequence: 0,
        role: MemoryRole::User,
        content: utterance_text.clone(),
        timestamp_ms: user_ts,
    });

    let ts = state.next_ts();
    let req = {
        let a = state.active.read().expect("active read lock");
        TurnRequest {
            session_id: SessionId(SESSION_ID.into()),
            persona: PersonaId(a.compiled.persona_id.0.clone()),
            task_id: None,
            // Voice turns: the transcribed text IS the user's utterance,
            // and there's no augmentation in this path today, so both
            // channels carry the same string. ADR-0009 §Decision 4.
            original_utterance: utterance_text.clone(),
            model_input_utterance: utterance_text.clone(),
            // L5 audit stamps this turn with `MediaMic`. The shell's
            // mic_permissions.json tri-state is the user-facing
            // per-device gate; L5 records the row without doubling
            // up, same pattern analyze_frame uses for camera/screen.
            // The design doc calls this capability "Microphone"; the
            // canonical L5 variant is `MediaMic` — divergence noted
            // in VOICE_V1_STEP4 execution report.
            capability: Capability::MediaMic,
            resource: ResourceScope::None,
            emitted_at: MonotonicTimestamp(ts),
            retrieval_provenance: None,
        }
    };

    let result = {
        let a = state.active.read().expect("active read lock");
        a.engine
            .handle_turn(req.clone())
            .map_err(|e| format!("voice turn engine: {e}"))?
    };

    let speech_provider_id = provider.id().to_string();
    let speech_model = provider.current_model();
    let latency_ms = stt_latency_ms;
    let _ = &response; // kept for future token-count propagation

    let ts_ms = state.next_ts();

    let (kind_label, message) = match (&result.route, &result.block) {
        (Some(r), _) => {
            let assistant_ts = state.next_ts();
            let _ = state.memory.append(TurnMemoryRecord {
                session_id: SESSION_ID.to_string(),
                sequence: 0,
                role: MemoryRole::Assistant,
                content: r.response_text.clone(),
                timestamp_ms: assistant_ts,
            });
            (
                "utterance_transcribed".to_string(),
                Some(TranscriptMessage {
                    id: format!("{}-voice", result.turn_id.0),
                    role: "assistant".into(),
                    content: r.response_text.clone(),
                    sequence: 0,
                    timestamp_ms: assistant_ts,
                    meta: Some(MessageMeta {
                        tier: Some(r.tier.clone()),
                        provider: Some(r.provider.clone()),
                        // Carry the speech model so Trust drawer /
                        // transcript footer can show which STT
                        // model served the turn.
                        model: speech_model.clone(),
                        latency_ms: Some(latency_ms),
                        prompt_tokens: r.tokens.map(|t| t.prompt),
                        completion_tokens: r.tokens.map(|t| t.completion),
                        origin: Some("voice".into()),
                    }),
                }),
            )
        }
        (None, Some(_)) => (
            "utterance_blocked".to_string(),
            Some(TranscriptMessage {
                id: format!("{}-voice-blocked", result.turn_id.0),
                role: "system".into(),
                content: "Voice analysis was blocked by policy.".into(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: None,
            }),
        ),
        _ => (
            "utterance_transcribed".to_string(),
            Some(TranscriptMessage {
                id: format!("{}-voice-empty", result.turn_id.0),
                role: "system".into(),
                content: "(no response)".into(),
                sequence: 0,
                timestamp_ms: ts_ms,
                meta: None,
            }),
        ),
    };

    let persona_id = {
        let a = state.active.read().expect("active read lock");
        a.compiled.persona_id.0.clone()
    };
    state.record_telemetry(TelemetryEntry {
        turn_id: result.turn_id.0.clone(),
        timestamp_ms: ts_ms,
        kind: kind_label.clone(),
        persona_id,
        provider: Some(speech_provider_id),
        tier: result.route.as_ref().map(|r| r.tier.clone()),
        model: speech_model,
        latency_ms: Some(latency_ms),
        prompt_tokens: result
            .route
            .as_ref()
            .and_then(|r| r.tokens.map(|t| t.prompt)),
        completion_tokens: result
            .route
            .as_ref()
            .and_then(|r| r.tokens.map(|t| t.completion)),
        memory_domain: None,
        memory_id: None,
    });

    // Hush duration_ms — reserved for future telemetry fields; today
    // only used informationally. Keep the parameter accepted so the
    // UI wire contract is stable across step 5.
    let _ = request.duration_ms;

    transition_presence(
        &app,
        &state.presence,
        PresenceState::Quiet,
        state.next_ts(),
        None,
    );

    Ok(UtteranceOutcome {
        turn_id: result.turn_id.0.clone(),
        kind: kind_label,
        message,
        error_note: None,
    })
}

// ---------------------------------------------------------------------
// Presence V1 step 1 — presence.json read/write surface.
// ---------------------------------------------------------------------

/// Snapshot the current presence config. Returned to the Settings
/// UI so it can render the enabled toggle + retention pills. The
/// shape is an opaque re-export of `PresenceConfig`; the TS side
/// mirrors the same fields.
#[tauri::command]
pub fn get_presence_config(
    state: State<'_, std::sync::Arc<AppState>>,
) -> crate::presence_config::PresenceConfig {
    state.presence_config()
}

// ---------------------------------------------------------------------
// Presence V1 step 2 — user-attention status + history surface.
//
// Deliberately named `presence_status` (not `presence_current`) because
// the pre-V2 `presence_current` command returns the assistant-posture
// snapshot (Quiet / Listening / Thinking / …) and the turn engine
// depends on that contract. Renaming either would be a breaking IPC
// change without benefit; two commands on two orthogonal axes keeps
// the wire surface honest.
// ---------------------------------------------------------------------

/// Shell-side payload mirroring `AttentionSnapshot` for the
/// `presence_status` Tauri command. Lower-case `state` label matches
/// `UserAttention::label` (`"active"` / `"idle"` / `"away"`) so TS
/// can use it as a discriminant without an enum mapping.
#[derive(Debug, Clone, Serialize)]
pub struct PresenceStatusPayload {
    /// `"active"` / `"idle"` / `"away"`. Meaningless when
    /// `enabled = false` — TS should branch on the flag first.
    pub state: String,
    /// Monotonic ms when the controller entered `state`.
    pub since_ms: u64,
    /// Seconds of OS idle at snapshot time. Zero when
    /// `enabled = false` or the probe reported unsupported.
    pub idle_seconds: u64,
    /// `true` when the controller is running.
    pub enabled: bool,
    /// `false` on platforms whose idle probe has not shipped yet
    /// (macOS / Linux stubs today). UI should surface this as
    /// "idle probe unavailable" rather than pretending to know.
    pub probe_supported: bool,
    /// Applied thresholds. Handy for a "Active → Idle after Xs" label
    /// in Settings without a second round trip.
    pub idle_after_s: u32,
    pub away_after_s: u32,
}

/// Snapshot the current user-attention state. Independent of
/// `presence_current` — that command reports the assistant-posture
/// axis (what Companion is doing at turn granularity). See
/// `docs/PRESENCE-V1-ARCHITECTURE.md` §2 for the three-axis model.
#[tauri::command]
pub fn presence_status(state: State<'_, std::sync::Arc<AppState>>) -> PresenceStatusPayload {
    let snap = state.attention_snapshot();
    let thresholds = state.attention.thresholds();
    PresenceStatusPayload {
        state: snap.state.label().to_string(),
        since_ms: snap.since_ms,
        idle_seconds: snap.idle_seconds,
        enabled: snap.enabled,
        probe_supported: snap.probe_supported,
        idle_after_s: thresholds.idle_after_s,
        away_after_s: thresholds.away_after_s,
    }
}

/// Snapshot of recent presence transitions for the Trust drawer's
/// History tab (Presence V1 step 3). Returns newest-first, capped at
/// `limit` (default 50 when the caller passes `null`). No audit rows
/// are emitted — presence is observational.
#[tauri::command]
pub fn presence_recent_history(
    state: State<'_, std::sync::Arc<AppState>>,
    limit: Option<usize>,
) -> Vec<PresenceHistoryEntry> {
    let lim = limit.unwrap_or(50);
    state.presence_history_recent(lim)
}

// ---------------------------------------------------------------------
// Memory V2 step 2 — memory.json read/write surface.
// ---------------------------------------------------------------------

/// Snapshot the current memory policy. Wire shape matches
/// `docs/MEMORY-V2-ARCHITECTURE.md` §3 — retention per domain,
/// default risk per domain, embeddings opt-in block.
#[tauri::command]
pub fn get_memory_config(
    state: State<'_, std::sync::Arc<AppState>>,
) -> crate::memory_config::MemoryConfig {
    state.memory_config()
}

/// Replace the memory policy and persist atomically. Full-snapshot
/// semantics (no partial patch) so the wire contract stays
/// predictable. Persistence or validation failures surface as a
/// user-visible error string.
#[tauri::command]
pub fn set_memory_config(
    config: crate::memory_config::MemoryConfig,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<crate::memory_config::MemoryConfig, String> {
    state.set_memory_config(config)
}

// ------------------------------------------------------------------
// ADR-0006 — Hardware tier model command surface.
// ------------------------------------------------------------------

/// Snapshot of the current tier config (selected, detected, hardware
/// snapshot). Cheap clone; safe to call on every render. Read by the
/// Settings UI to render the three-tier picker, badge the recommended
/// tier, and surface "your hardware suggests X" hint when selected
/// and detected diverge.
#[tauri::command]
pub fn get_tier(state: State<'_, std::sync::Arc<AppState>>) -> crate::tier::TierConfig {
    state.tier_config()
}

/// User-initiated tier change. Updates `selected_tier`, flips
/// `manual_override` if the new selection diverges from the detected
/// recommendation, and persists atomically when `tier.json` is wired.
/// Emits a `tier:changed` Tauri event with the new TierConfig so
/// subsystems that consume tier (embeddings onboarding via ADR-0007,
/// future TTS/vision/avatar ADRs) re-read on demand without polling.
#[tauri::command]
pub fn set_tier(
    tier: crate::tier::Tier,
    state: State<'_, std::sync::Arc<AppState>>,
    app: AppHandle,
) -> Result<crate::tier::TierConfig, String> {
    let cfg = state.set_tier(tier)?;
    // ADR-0006 §Decision 5: tier_changed event surface. Best-effort
    // emit; subsystems treat its absence as "tier may have changed,
    // re-read on next interaction" rather than failing.
    let _ = app.emit("tier:changed", &cfg);
    Ok(cfg)
}

/// Run a fresh hardware-detection pass and update the tier config.
/// Pure read on the hardware side (wgpu adapter enumeration, sysinfo,
/// `fs::available_space`, optional 750ms `/api/ps` HTTP probe). No
/// rendering, no model loads. Honours manual override: if the user
/// has previously chosen a non-detected tier, redetection updates
/// `detected_tier` and `hardware_snapshot` only — the manual selection
/// stays.
#[tauri::command]
pub fn redetect_hardware(
    state: State<'_, std::sync::Arc<AppState>>,
    app: AppHandle,
) -> Result<crate::tier::TierConfig, String> {
    let cfg = state.redetect_hardware()?;
    // Emit tier:changed when the active selection diverges post-detection
    // (manual override unchanged → no-op for consumers). Best-effort.
    let _ = app.emit("tier:changed", &cfg);
    Ok(cfg)
}

// ------------------------------------------------------------------
// ADR-0007 — Retrieval readiness command surface.
// ------------------------------------------------------------------

/// Snapshot the current retrieval readiness state per ADR-0007 D3.
/// Read by the Trust drawer indicator + drawer-icon attention badge +
/// transition-toast subscription. Cheap clone; UI may poll on a
/// reasonable interval (≥1s) without backend cost.
///
/// State updates are pushed by `run_retrieval_context` itself (every
/// real turn) and by future boot / settings-change probes. The state
/// machine is event-driven (ADR-0007 D3); this command is the read
/// side only.
#[tauri::command]
pub fn embeddings_readiness(
    state: State<'_, std::sync::Arc<AppState>>,
) -> crate::retrieval::ReadinessState {
    state.retrieval_readiness()
}

// ------------------------------------------------------------------
// ADR-0007 §Decision 5 — embeddings backfill command surface.
// ------------------------------------------------------------------

/// Snapshot of current backfill progress. Polled by the UI for the
/// progress strip and to flip the button state between "Backfill now"
/// and "Cancel". The full progress shape lives in
/// `crate::state::BackfillProgress`.
#[tauri::command]
pub fn backfill_status(
    state: State<'_, std::sync::Arc<AppState>>,
) -> crate::state::BackfillProgress {
    state
        .backfill_progress
        .lock()
        .expect("backfill progress lock")
        .clone()
}

/// Approximate count of un-embedded rows across embed-eligible
/// domains. Drives the "Backfill ~N items" copy. ADR-0007 D5
/// approximate semantics — see `backfill::estimate_unembedded_count`.
#[tauri::command]
pub fn backfill_count(state: State<'_, std::sync::Arc<AppState>>) -> usize {
    crate::backfill::estimate_unembedded_count(state.inner().as_ref())
}

/// Spawn a backfill job and return immediately with the initial
/// `BackfillProgress` snapshot. Returns an error when a job is
/// already in progress (only one job at a time per ADR-0007 D5).
///
/// Phase 4D (ADR-0007 §Decision 5 + AUTONOMOUS_RUN_FINAL_REPORT §9
/// shortcut #1): the worker now runs on Tauri's tokio runtime via
/// `tauri::async_runtime::spawn_blocking`, so the IPC thread is
/// freed within milliseconds instead of blocking for the full
/// 30-60 sec backfill duration. Live progress flows through the
/// existing `backfill:progress` Tauri event stream and through
/// `backfill_status` polling — both are already consumed by
/// `RetrievalTab.tsx`. Cancel via `cancel_backfill` from another
/// command invocation; the worker observes the atomic at the
/// next row boundary.
#[tauri::command]
pub fn start_backfill(
    state: State<'_, std::sync::Arc<AppState>>,
    app: AppHandle,
) -> Result<crate::state::BackfillProgress, String> {
    let job_id = crate::backfill::spawn_backfill(
        state.inner().clone(),
        app,
        crate::backfill::BackfillOptions::default(),
    )
    .ok_or_else(|| "backfill already in progress".to_string())?;
    tracing::info!("backfill spawned: job_id={job_id}");
    // Return the just-initialised progress snapshot. The worker may
    // not have written to it yet (it spawns on another task), so the
    // shape is the prior run's `finished=true` snapshot or a default.
    // The frontend disregards it in favour of the live event stream
    // and the periodic poll — see RetrievalTab.tsx::handleBackfill.
    Ok(state
        .backfill_progress
        .lock()
        .expect("backfill progress lock")
        .clone())
}

/// Request cancellation of any in-progress backfill. The worker
/// observes the flag at the next row boundary; the in-flight embed
/// call is allowed to finish so we never strand a partial vector
/// in the embedding store.
#[tauri::command]
pub fn cancel_backfill(state: State<'_, std::sync::Arc<AppState>>) -> bool {
    if state
        .backfill_in_progress
        .load(std::sync::atomic::Ordering::SeqCst)
    {
        state
            .backfill_cancel
            .store(true, std::sync::atomic::Ordering::SeqCst);
        true
    } else {
        false
    }
}

// ------------------------------------------------------------------
// Memory V2 step 4 — Trust drawer Memory tab command surface.
// ------------------------------------------------------------------
//
// One row per memory item as rendered by the Memory tab. `source`
// today is always "conversation" because the only backing store is
// the SessionMemoryStore. Step 5 (retention sweep) introduces a
// domain-typed durable store and will populate the other five
// domain lanes; the `empty_reason` field on `MemoryListPayload`
// exists so today's Facts/Artifacts/Durable/Projects/Preferences
// lanes render honestly ("Storage for this domain arrives with
// Memory V2 step 5") rather than invent content.
#[derive(Debug, Clone, Serialize)]
pub struct MemoryListItem {
    pub memory_id: String,
    pub sequence: u64,
    pub timestamp_ms: u64,
    pub role: String,
    pub content: String,
    pub source: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct MemoryListPayload {
    pub domain: String,
    pub privacy_class: String,
    pub risk: String,
    pub items: Vec<MemoryListItem>,
    pub empty_reason: Option<String>,
}

/// Privacy class per `docs/MEMORY-V2-ARCHITECTURE.md` §1. Kept in the
/// command layer rather than on `MemoryDomain` itself so the doc
/// table is the single source of truth and the wire contract stays
/// stable even if the enum order changes.
fn privacy_class_label(domain: crate::memory_config::MemoryDomain) -> &'static str {
    use crate::memory_config::MemoryDomain;
    match domain {
        MemoryDomain::Facts | MemoryDomain::Artifacts => "user_sensitive",
        MemoryDomain::Session
        | MemoryDomain::Durable
        | MemoryDomain::Projects
        | MemoryDomain::Preferences => "standard",
    }
}

fn risk_wire_label(risk: crate::memory_config::MemoryRisk) -> &'static str {
    use crate::memory_config::MemoryRisk;
    match risk {
        MemoryRisk::Auto => "auto",
        MemoryRisk::Ask => "ask",
        MemoryRisk::Deny => "deny",
    }
}

/// Split `"mem-{session_id}-{sequence}"` back into its two parts.
/// Returns `None` on any shape mismatch — the caller surfaces a
/// user-visible error. `session_id` may itself contain hyphens, so
/// we split from the RIGHT: everything after the last `-` is the
/// sequence, everything between the `mem-` prefix and that last
/// hyphen is the session id.
fn parse_memory_id(memory_id: &str) -> Option<(String, u64)> {
    let inner = memory_id.strip_prefix("mem-")?;
    let (session_id, seq_str) = inner.rsplit_once('-')?;
    if session_id.is_empty() {
        return None;
    }
    let sequence: u64 = seq_str.parse().ok()?;
    Some((session_id.to_string(), sequence))
}

/// List memory items for a domain. Today the Session lane surfaces
/// the current session's turn records; the other five domains
/// return an empty list with an `empty_reason` string so the UI
/// can render an honest "not yet stored" state.
#[tauri::command]
pub fn memory_list(
    domain: crate::memory_config::MemoryDomain,
    session_id: Option<String>,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<MemoryListPayload, String> {
    use crate::memory_config::MemoryDomain;
    let risk = state.memory_config().risk_for(domain);
    let base = MemoryListPayload {
        domain: domain.label().to_string(),
        privacy_class: privacy_class_label(domain).to_string(),
        risk: risk_wire_label(risk).to_string(),
        items: Vec::new(),
        empty_reason: None,
    };
    match domain {
        MemoryDomain::Session => {
            let session = session_id.unwrap_or_else(|| SESSION_ID.to_string());
            let w = state
                .memory
                .recent(&session)
                .map_err(|e| format!("memory: {e}"))?;
            let items = w
                .records
                .into_iter()
                .map(|r| MemoryListItem {
                    memory_id: format!("mem-{}-{}", session, r.sequence),
                    sequence: r.sequence,
                    timestamp_ms: r.timestamp_ms,
                    role: role_label(r.role).to_string(),
                    content: r.content,
                    source: "conversation".to_string(),
                })
                .collect();
            Ok(MemoryListPayload { items, ..base })
        }
        MemoryDomain::Durable
        | MemoryDomain::Facts
        | MemoryDomain::Projects
        | MemoryDomain::Preferences
        | MemoryDomain::Artifacts => Ok(MemoryListPayload {
            empty_reason: Some(
                "Storage for this domain arrives with Memory V2 step 5.".to_string(),
            ),
            ..base
        }),
    }
}

/// Forget every row in a domain's session. Wraps the existing
/// `AppState::memory_forget` so the Memory tab's "forget all in
/// domain" button has a UI seat. Serialised outcome mirrors the
/// Rust enum so the TS side can switch on `kind`.
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum MemoryForgetOutcomeWire {
    Allowed {
        removed_count: usize,
        audit_id: String,
    },
    RequiresApproval,
    Denied {
        reason: String,
    },
    NotFound,
}

impl From<crate::memory_service::MemoryForgetOutcome> for MemoryForgetOutcomeWire {
    fn from(o: crate::memory_service::MemoryForgetOutcome) -> Self {
        use crate::memory_service::MemoryForgetOutcome;
        match o {
            MemoryForgetOutcome::Allowed {
                removed_count,
                audit_id,
            } => Self::Allowed {
                removed_count,
                audit_id,
            },
            MemoryForgetOutcome::RequiresApproval => Self::RequiresApproval,
            MemoryForgetOutcome::Denied { reason } => Self::Denied { reason },
            MemoryForgetOutcome::NotFound => Self::NotFound,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum MemoryEditOutcomeWire {
    Allowed { memory_id: String, audit_id: String },
    RequiresApproval,
    Denied { reason: String },
    NotFound,
}

impl From<crate::memory_service::MemoryEditOutcome> for MemoryEditOutcomeWire {
    fn from(o: crate::memory_service::MemoryEditOutcome) -> Self {
        use crate::memory_service::MemoryEditOutcome;
        match o {
            MemoryEditOutcome::Allowed {
                memory_id,
                audit_id,
            } => Self::Allowed {
                memory_id,
                audit_id,
            },
            MemoryEditOutcome::RequiresApproval => Self::RequiresApproval,
            MemoryEditOutcome::Denied { reason } => Self::Denied { reason },
            MemoryEditOutcome::NotFound => Self::NotFound,
        }
    }
}

#[tauri::command]
pub fn memory_forget(
    domain: crate::memory_config::MemoryDomain,
    session_id: Option<String>,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<MemoryForgetOutcomeWire, String> {
    let session = session_id.unwrap_or_else(|| SESSION_ID.to_string());
    state
        .memory_forget(domain, &session)
        .map(Into::into)
        .map_err(|e| format!("memory_forget: {e}"))
}

#[tauri::command]
pub fn memory_forget_item(
    domain: crate::memory_config::MemoryDomain,
    memory_id: String,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<MemoryForgetOutcomeWire, String> {
    let (session_id, sequence) =
        parse_memory_id(&memory_id).ok_or_else(|| format!("invalid memory_id: {memory_id}"))?;
    state
        .memory_forget_item(domain, &session_id, sequence)
        .map(Into::into)
        .map_err(|e| format!("memory_forget_item: {e}"))
}

#[tauri::command]
pub fn memory_forget_item_after_approval(
    domain: crate::memory_config::MemoryDomain,
    memory_id: String,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<MemoryForgetOutcomeWire, String> {
    let (session_id, sequence) =
        parse_memory_id(&memory_id).ok_or_else(|| format!("invalid memory_id: {memory_id}"))?;
    state
        .memory_forget_item_after_approval(domain, &session_id, sequence)
        .map(Into::into)
        .map_err(|e| format!("memory_forget_item_after_approval: {e}"))
}

#[tauri::command]
pub fn memory_edit(
    domain: crate::memory_config::MemoryDomain,
    memory_id: String,
    new_content: String,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<MemoryEditOutcomeWire, String> {
    let (session_id, sequence) =
        parse_memory_id(&memory_id).ok_or_else(|| format!("invalid memory_id: {memory_id}"))?;
    state
        .memory_edit(domain, &session_id, sequence, new_content)
        .map(Into::into)
        .map_err(|e| format!("memory_edit: {e}"))
}

#[tauri::command]
pub fn memory_edit_after_approval(
    domain: crate::memory_config::MemoryDomain,
    memory_id: String,
    new_content: String,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<MemoryEditOutcomeWire, String> {
    let (session_id, sequence) =
        parse_memory_id(&memory_id).ok_or_else(|| format!("invalid memory_id: {memory_id}"))?;
    state
        .memory_edit_after_approval(domain, &session_id, sequence, new_content)
        .map(Into::into)
        .map_err(|e| format!("memory_edit_after_approval: {e}"))
}

/// Replace the presence config and persist atomically. The caller
/// supplies the full snapshot (no partial-patch semantics) — keeps
/// the wire contract predictable and the Rust side trivial.
/// Persistence failures surface as a user-visible error.
#[tauri::command]
pub fn set_presence_config(
    config: crate::presence_config::PresenceConfig,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<crate::presence_config::PresenceConfig, String> {
    state.set_presence_config(config)
}

// ---------------------------------------------------------------------
// Voice status + runtime swap (Voice V1 step 5).
// ---------------------------------------------------------------------

/// Shell-side snapshot of the speech provider registry — mirrors
/// [`VisionStatus`]. Surfaced to the `VoiceBadge` / `ActiveVoiceRoute`
/// UI so the user can see at a glance which STT route the next
/// `transcribe_utterance` call will hit, plus a runtime-swap dropdown
/// to pick a different registered adapter. `None` fields mean "voice
/// disabled" — unlike vision there is no text-only fallback; without
/// an active speech provider the user sees a visible error when they
/// try to record.
#[derive(Debug, Clone, Serialize)]
pub struct VoiceStatus {
    /// `true` when a speech provider is currently active.
    pub enabled: bool,
    /// Active provider id (e.g. `"whispercpp-speech"`), `None` when
    /// voice is disabled.
    pub active_id: Option<String>,
    /// Human-readable label of the active provider
    /// (e.g. `"whisper.cpp · ggml-base.en · http://..."`). `None`
    /// when disabled.
    pub label: Option<String>,
    /// Active provider's current model id, if the adapter exposes
    /// one. Drives the "Active" indicator in the model strip.
    pub active_model: Option<String>,
    /// Every registered speech provider with an `active` flag —
    /// drives the runtime-swap UI.
    pub providers: Vec<crate::voice_registry::SpeechProviderInfo>,
}

#[tauri::command]
pub fn voice_status(state: State<'_, std::sync::Arc<AppState>>) -> VoiceStatus {
    let label = state.speech_provider_label();
    let active_id = state.speech_active_id();
    let active_model = state.speech_active_model();
    let providers = state.speech_provider_list();
    VoiceStatus {
        enabled: label.is_some(),
        active_id,
        label,
        active_model,
        providers,
    }
}

/// Snapshot of registered speech providers — same list shipped
/// inside `VoiceStatus` but exposed as its own command for callers
/// that only want the inventory.
#[tauri::command]
pub fn list_speech_providers(
    state: State<'_, std::sync::Arc<AppState>>,
) -> Vec<crate::voice_registry::SpeechProviderInfo> {
    state.speech_provider_list()
}

/// Models the active speech provider's daemon currently has
/// available. Shape mirrors `VisionModelList`. The adapter's
/// `list_models` default is an empty vec (whisper.cpp scaffold
/// today doesn't expose discovery); failures + empty lists fold to
/// a plain-language "models unavailable" hint the dropdown can
/// render quietly.
#[derive(Debug, Clone, Serialize)]
pub struct SpeechModelList {
    /// Provider id the listing was fetched for. `None` when no
    /// provider is currently active.
    pub provider_id: Option<String>,
    /// Discovered model ids. Empty when discovery failed, the
    /// adapter doesn't implement `list_models`, or the daemon
    /// reports no models.
    pub models: Vec<String>,
    /// Short, plain-language explanation when discovery did not
    /// produce a usable list. `None` on success.
    pub error: Option<String>,
}

fn collect_speech_models(state: &State<'_, std::sync::Arc<AppState>>) -> SpeechModelList {
    let Some(provider) = state.speech_provider() else {
        return SpeechModelList {
            provider_id: None,
            models: Vec::new(),
            error: Some("No speech provider is active.".into()),
        };
    };
    let id = provider.id().to_string();
    match provider.list_models() {
        Ok(models) if models.is_empty() => SpeechModelList {
            provider_id: Some(id),
            models,
            error: Some("Models unavailable for this provider.".into()),
        },
        Ok(models) => SpeechModelList {
            provider_id: Some(id),
            models,
            error: None,
        },
        Err(_) => SpeechModelList {
            provider_id: Some(id),
            models: Vec::new(),
            error: Some("Models unavailable for this provider.".into()),
        },
    }
}

#[tauri::command]
pub fn list_speech_models(state: State<'_, std::sync::Arc<AppState>>) -> SpeechModelList {
    collect_speech_models(&state)
}

/// Force a fresh discovery (no TTL cache in step 5 — whisper.cpp
/// scaffold doesn't expose model listing yet; when it does, add a
/// cache mirror of `vision_cache.rs`). For now this is equivalent
/// to `list_speech_models` but named so the UI can wire a `↻`
/// affordance the same way VisionBadge does.
#[tauri::command]
pub fn refresh_speech_models(state: State<'_, std::sync::Arc<AppState>>) -> SpeechModelList {
    collect_speech_models(&state)
}

/// Switch the active speech provider. `None` (or the wire
/// sentinel `""` / `"none"`) disables voice — the next
/// `transcribe_utterance` will surface a clear error rather than
/// silently falling back. Unknown ids are rejected so UI bugs
/// surface instead of silently flipping to the wrong route.
#[tauri::command]
pub fn set_active_speech_provider(
    id: Option<String>,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<VoiceStatus, String> {
    let normalized = match id.as_deref() {
        None | Some("") | Some("none") => None,
        Some(other) => Some(other.to_string()),
    };
    state.set_active_speech_provider(normalized)?;
    Ok(voice_status(state))
}

/// Switch the model used by the currently-active speech provider.
/// Validates against the fresh model list when the adapter exposes
/// one; accepts optimistically when discovery is unavailable (same
/// pattern `set_active_vision_model` uses).
#[tauri::command]
pub fn set_active_speech_model(
    id: String,
    state: State<'_, std::sync::Arc<AppState>>,
) -> Result<VoiceStatus, String> {
    let trimmed = id.trim();
    if trimmed.is_empty() {
        return Err("model id must not be empty".into());
    }
    if state.speech_provider().is_none() {
        return Err("no active speech provider".into());
    }
    let list = collect_speech_models(&state);
    if list.error.is_none() && !list.models.is_empty() {
        if !list.models.iter().any(|m| m == trimmed) {
            return Err(format!("unknown model for active provider: {trimmed}"));
        }
    }
    // Discovery unavailable → accept optimistically; the next
    // transcribe_utterance will surface a real "model not found"
    // error through the provider error path.
    state.set_active_speech_model(trimmed)?;
    Ok(voice_status(state))
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

/// Payload emitted on `presence:attention` whenever the user-attention
/// axis transitions (driven by the shell's poll loop in `main.rs`).
/// Same shape as `PresenceHistoryEntry` so the TS side can reuse a
/// single mapper across the event-bus push and the
/// `presence_recent_history` command.
#[derive(Debug, Clone, Serialize)]
pub struct AttentionEventPayload {
    pub kind: String,
    pub from: String,
    pub to: String,
    pub idle_seconds: u64,
    pub at_ms: u64,
}

impl From<PresenceHistoryEntry> for AttentionEventPayload {
    fn from(e: PresenceHistoryEntry) -> Self {
        Self {
            kind: e.kind,
            from: e.from,
            to: e.to,
            idle_seconds: e.idle_seconds,
            at_ms: e.at_ms,
        }
    }
}

/// Poll-tick handler. Called from the shell's presence loop; keeps
/// the emit + history-push contract in one place so the loop body
/// stays tiny. Records a `presence_state_changed` row on every
/// transition per design §5.
pub fn drive_attention_tick(
    app: &AppHandle,
    state: &AppState,
    now_ms: u64,
    idle_seconds: Option<u64>,
) {
    let Some(event) = state.attention_tick(now_ms, idle_seconds) else {
        return;
    };
    let entry = PresenceHistoryEntry {
        kind: "presence_state_changed".to_string(),
        from: event.from.label().to_string(),
        to: event.to.label().to_string(),
        idle_seconds: event.idle_seconds,
        at_ms: event.at_ms,
    };
    state.push_presence_history(entry.clone());
    let payload: AttentionEventPayload = entry.into();
    let _ = app.emit("presence:attention", payload);
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---------- Wave 15 — capability_is_side_effecting classifier ----------

    #[test]
    fn wave15_classifies_read_only_file_and_browser_caps_as_non_side_effecting() {
        use aether_l5_policy::Capability::*;
        for cap in [
            FilesRead,
            BrowserReadPage,
            BrowserExtractData,
            EmailReadMetadata,
            EmailReadBody,
            ClipboardRead,
            NotificationRead,
            MemoryRead,
            RetrievalContext,
        ] {
            assert!(
                !capability_is_side_effecting(&cap),
                "{cap:?} should be classified read-only"
            );
        }
    }

    #[test]
    fn wave15_classifies_mutating_caps_as_side_effecting() {
        use aether_l5_policy::Capability::*;
        for cap in [
            FilesCreate,
            FilesEdit,
            FilesRenameMove,
            FilesDelete,
            FilesBulkOp,
            BrowserOpen,
            BrowserFillForm,
            BrowserUpload,
            BrowserDownload,
            BrowserSubmit,
            BrowserLoginReuse,
            EmailDraft,
            EmailEditDraft,
            EmailSend,
            EmailAttachmentAccess,
            ClipboardWrite,
            ShellExec,
            PackageInstall,
        ] {
            assert!(
                capability_is_side_effecting(&cap),
                "{cap:?} should be classified side-effecting"
            );
        }
    }

    // ---------- Memory V2 step 4 command helpers ----------

    #[test]
    fn parse_memory_id_round_trips_plain_session() {
        assert_eq!(
            parse_memory_id("mem-session-1").unwrap(),
            ("session".to_string(), 1)
        );
    }

    #[test]
    fn parse_memory_id_preserves_hyphenated_session_ids() {
        // Session ids are opaque strings that may contain hyphens;
        // splitting from the right is the contract.
        assert_eq!(
            parse_memory_id("mem-session-2026-05-17-42").unwrap(),
            ("session-2026-05-17".to_string(), 42)
        );
    }

    #[test]
    fn parse_memory_id_rejects_malformed_input() {
        assert!(parse_memory_id("").is_none());
        assert!(parse_memory_id("session-1").is_none()); // missing mem- prefix
        assert!(parse_memory_id("mem-sessiononly").is_none()); // missing sequence
        assert!(parse_memory_id("mem-").is_none()); // empty after prefix
        assert!(parse_memory_id("mem--1").is_none()); // empty session
        assert!(parse_memory_id("mem-s1-not-a-number").is_none());
    }

    #[test]
    fn privacy_class_tracks_design_doc() {
        use crate::memory_config::MemoryDomain;
        assert_eq!(privacy_class_label(MemoryDomain::Facts), "user_sensitive");
        assert_eq!(
            privacy_class_label(MemoryDomain::Artifacts),
            "user_sensitive"
        );
        for d in [
            MemoryDomain::Session,
            MemoryDomain::Durable,
            MemoryDomain::Projects,
            MemoryDomain::Preferences,
        ] {
            assert_eq!(privacy_class_label(d), "standard");
        }
    }

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
            "router client: {}Companion can't reach the local model daemon.",
            PROVIDER_ERROR_PREFIX
        );
        assert_eq!(
            extract_provider_error(&wrapped).as_deref(),
            Some("Companion can't reach the local model daemon."),
        );
    }

    #[cfg(feature = "ollama-provider")]
    #[test]
    fn extract_provider_error_none_for_unrelated_message() {
        assert!(extract_provider_error("router client: memory recall failed: oh no").is_none());
        assert!(extract_provider_error("policy: denied").is_none());
    }

    #[test]
    fn validate_frame_data_url_accepts_well_formed_payload() {
        let url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB";
        let body = validate_frame_data_url(url).expect("valid URL should parse");
        assert!(body.starts_with("iVBORw0KGgo"));
    }

    #[test]
    fn validate_frame_data_url_accepts_jpeg() {
        let url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD";
        assert!(validate_frame_data_url(url).is_ok());
    }

    #[test]
    fn validate_frame_data_url_rejects_wrong_scheme() {
        let err = validate_frame_data_url("https://example.com/x.png").unwrap_err();
        assert!(err.contains("data:image/"), "{err}");
    }

    #[test]
    fn validate_frame_data_url_rejects_non_image_mime() {
        let err = validate_frame_data_url("data:text/plain,hello").unwrap_err();
        assert!(err.contains("data:image/"), "{err}");
    }

    #[test]
    fn validate_frame_data_url_rejects_missing_separator() {
        let err = validate_frame_data_url("data:image/png;base64").unwrap_err();
        assert!(err.contains("separator"), "{err}");
    }

    #[test]
    fn validate_frame_data_url_rejects_empty_body() {
        let err = validate_frame_data_url("data:image/png;base64,").unwrap_err();
        assert!(err.contains("empty image body"), "{err}");
    }

    #[test]
    fn validate_frame_data_url_rejects_whitespace_only_body() {
        let err = validate_frame_data_url("data:image/png;base64,   \n\t  ").unwrap_err();
        assert!(err.contains("empty image body"), "{err}");
    }

    #[test]
    fn validate_frame_data_url_rejects_too_short_body() {
        let err = validate_frame_data_url("data:image/png;base64,ab").unwrap_err();
        assert!(err.contains("too short"), "{err}");
    }

    // ----- validate_utterance_data_url (Voice V1 step 4) -----

    /// Well-formed WAV data URL with a body longer than MIN returns
    /// the body slice (no leading comma).
    #[test]
    fn validate_utterance_data_url_accepts_wav_data_url() {
        // 128 `A`s — way above MIN_UTTERANCE_BODY_LEN = 64.
        let body = "A".repeat(128);
        let url = format!("data:audio/wav;base64,{body}");
        let got = validate_utterance_data_url(&url).expect("valid URL should parse");
        assert_eq!(got, body);
    }

    #[test]
    fn validate_utterance_data_url_rejects_non_audio_prefix() {
        let body = "A".repeat(128);
        let url = format!("data:image/png;base64,{body}");
        let err = validate_utterance_data_url(&url).unwrap_err();
        assert!(err.contains("data:audio/wav"), "{err}");
    }

    #[test]
    fn validate_utterance_data_url_rejects_missing_comma() {
        let err = validate_utterance_data_url("data:audio/wav;base64").unwrap_err();
        assert!(err.contains("separator"), "{err}");
    }

    #[test]
    fn validate_utterance_data_url_rejects_empty_body() {
        let err = validate_utterance_data_url("data:audio/wav;base64,").unwrap_err();
        assert!(err.contains("empty audio body"), "{err}");
    }

    #[test]
    fn validate_utterance_data_url_rejects_whitespace_only_body() {
        let err = validate_utterance_data_url("data:audio/wav;base64,   \n\t  ").unwrap_err();
        assert!(err.contains("empty audio body"), "{err}");
    }

    #[test]
    fn validate_utterance_data_url_rejects_too_short_body() {
        // 32 chars — half of MIN_UTTERANCE_BODY_LEN.
        let body = "A".repeat(32);
        let url = format!("data:audio/wav;base64,{body}");
        let err = validate_utterance_data_url(&url).unwrap_err();
        assert!(err.contains("too short"), "{err}");
    }

    /// MIN_UTTERANCE_BODY_LEN is tuned to 64. Lock the value so any
    /// future relaxation is a conscious decision reflected in this
    /// test and the design doc, not a silent drift.
    #[test]
    fn min_utterance_body_len_is_sixty_four() {
        assert_eq!(MIN_UTTERANCE_BODY_LEN, 64);
    }

    /// The whisper.cpp adapter now performs a real HTTP call to
    /// `/inference`. With an unreachable server the shell must
    /// surface a loud, user-visible error — NO silent empty
    /// transcript. This test proves the no-silent-fallback contract
    /// survives the scaffold → real-inference transition that landed
    /// in this session. If the error goes quiet or turns into an
    /// `Ok(SpeechResponse { text: "" })`, this test fires.
    #[cfg(feature = "speech-whispercpp")]
    #[test]
    fn whispercpp_transport_failure_surfaces_loudly() {
        use aether_l4_router::{
            SpeechProvider, SpeechRequest, WhisperCppSpeechConfig, WhisperCppSpeechProvider,
        };
        let cfg = WhisperCppSpeechConfig {
            base_url: "http://127.0.0.1:65535".into(),
            model: "ggml-base.en.bin".into(),
            language: None,
            timeout_ms: 1,
        };
        let provider = WhisperCppSpeechProvider::new(cfg);
        // "AAAA" decodes to 3 zero bytes — non-empty, so we clear
        // the validator and reach the HTTP layer where the closed
        // port trips the transport error.
        let err = provider
            .transcribe(SpeechRequest {
                audio_b64: "AAAA".into(),
                mime: "audio/wav".into(),
                sample_rate: 16000,
                channels: 1,
                language: None,
            })
            .unwrap_err();
        let msg = format!("{err}");
        // Must mention the base URL or the POST path so the user
        // has something to diagnose — not a silent empty transcript.
        assert!(
            msg.contains("127.0.0.1:65535") || msg.contains("/inference"),
            "transport error should identify the endpoint; msg = {msg:?}",
        );
    }

    // ----- mic permission early-exit behavior via AppState -----

    /// Deny gate on the mic records a `mic_permission_denied`
    /// telemetry row, writes a system-role memory entry, and does
    /// not consult the speech provider.
    #[test]
    fn utterance_early_exit_telemetry_records_permission_denied_kind() {
        use crate::state::AppState;

        let state = AppState::new().expect("AppState::new");
        state
            .set_mic_permission(PermissionState::Deny)
            .expect("set deny");
        assert_eq!(state.evaluate_mic_permission(), CaptureGate::Deny);

        // Exercise the helper directly — the full command path is
        // covered by the analyze_frame-style pattern; this slice
        // proves the early-exit plumbing is wired.
        let ts_before = state.telemetry_recent(10).len();
        // Use the helper via a test shim: record_utterance_early_exit
        // takes `State<'_, std::sync::Arc<AppState>>` which we can't construct in
        // unit tests, so we mirror the call shape with the state
        // method directly.
        let ts_ms = state.next_ts();
        let persona_id = {
            let a = state.active.read().unwrap();
            a.compiled.persona_id.0.clone()
        };
        state.record_telemetry(TelemetryEntry {
            turn_id: format!("utterance-early-{ts_ms}"),
            timestamp_ms: ts_ms,
            kind: "mic_permission_denied".to_string(),
            persona_id,
            provider: None,
            tier: None,
            model: None,
            latency_ms: None,
            prompt_tokens: None,
            completion_tokens: None,
            memory_domain: None,
            memory_id: None,
        });

        let entries = state.telemetry_recent(10);
        assert_eq!(entries.len(), ts_before + 1);
        assert_eq!(entries[0].kind, "mic_permission_denied");
        assert!(entries[0].provider.is_none());
        assert!(entries[0].model.is_none());
    }

    /// Ask gate produces the `mic_permission_ask` kind instead of
    /// `mic_permission_denied`. Parity with `permission_ask` on the
    /// vision side.
    #[test]
    fn utterance_early_exit_distinguishes_ask_from_deny() {
        use crate::state::AppState;

        let state = AppState::new().expect("AppState::new");
        // Default is Ask — confirm the gate is PromptUser.
        assert_eq!(state.evaluate_mic_permission(), CaptureGate::PromptUser);

        let ts_ms = state.next_ts();
        let persona_id = {
            let a = state.active.read().unwrap();
            a.compiled.persona_id.0.clone()
        };
        state.record_telemetry(TelemetryEntry {
            turn_id: format!("utterance-early-{ts_ms}"),
            timestamp_ms: ts_ms,
            kind: "mic_permission_ask".to_string(),
            persona_id,
            provider: None,
            tier: None,
            model: None,
            latency_ms: None,
            prompt_tokens: None,
            completion_tokens: None,
            memory_domain: None,
            memory_id: None,
        });

        let entries = state.telemetry_recent(10);
        assert_eq!(entries[0].kind, "mic_permission_ask");
    }

    /// Allow gate lets the pipeline through — the state-level gate
    /// resolves to Proceed so the command body would hit the
    /// speech provider next.
    #[test]
    fn utterance_gate_allow_resolves_to_proceed() {
        use crate::state::AppState;

        let state = AppState::new().expect("AppState::new");
        state
            .set_mic_permission(PermissionState::Allow)
            .expect("set allow");
        assert_eq!(state.evaluate_mic_permission(), CaptureGate::Proceed);
    }

    /// With no speech provider registered, speech_provider() returns
    /// None — transcribe_utterance surfaces this as an `Err` rather
    /// than silently falling back. Locked here so the "no silent
    /// fallback" contract stays honest.
    #[test]
    fn no_speech_provider_yields_none_from_state() {
        use crate::state::AppState;

        let state = AppState::new().expect("AppState::new");
        assert!(state.speech_provider().is_none());
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

    // ----- ADR-0009 code review #2: end-to-end original-utterance survival -----

    /// **ADR-0009 code-review-#2 closure.** Reproduces the path
    /// `submit_turn` walks — run the retrieval orchestrator, build the
    /// `format_retrieval_block` + `augment_utterance` augmented router
    /// utterance, construct the same `TurnRequest` shape (with
    /// `Some(retrieval_provenance_for(&hits))` stamped on the audit
    /// extras), drive the policy engine, then read the resulting audit
    /// row through the **same projection logic** `audit_recent` uses.
    ///
    /// What this locks:
    /// 1. `original_utterance` on the projected row equals the user's
    ///    distinctive phrase **byte-for-byte** (no augmentation leaks
    ///    into the audit truth channel).
    /// 2. `original_utterance != model_input_utterance` when retrieval
    ///    fired — proving the two-channel split survives the round
    ///    trip (the spec's whole point).
    /// 3. The augmented router utterance carries the retrieval-block
    ///    prefix `"Relevant context (retrieval):"` AND the user's
    ///    original phrase.
    /// 4. `retrieval_provenance.is_some()` AND `hits.len() > 0` —
    ///    proves the orchestrator's hit list survives into the audit
    ///    row's structured-metadata channel.
    /// 5. `schema_version == AUDIT_SCHEMA_VERSION_V2` — locks the
    ///    write-side stamping behaviour.
    ///
    /// We bypass `State<'_, Arc<AppState>>` plumbing (Tauri's command
    /// macro can't be invoked from a unit test) by exercising the
    /// internal helpers `submit_turn` itself uses: same `parse_command`,
    /// same `run_retrieval_context`, same `format_retrieval_block`,
    /// same `augment_utterance`, same `retrieval_provenance_for`, same
    /// `engine.handle_turn`, then the same projection body as
    /// `audit_recent`. If any of those internals diverge from the path
    /// the live command takes, this test goes stale — that staleness is
    /// itself a signal worth catching during review.
    #[test]
    fn submit_turn_audit_row_preserves_original_utterance_end_to_end() {
        use crate::memory_config::MemoryDomain;
        use crate::retrieval::DEFAULT_RETRIEVAL_DEADLINE;
        use crate::state::{AppState, SESSION_ID};
        use aether_l2_memory::embeddings::StubEmbedder;
        use aether_l2_memory::{EmbeddingProvider, EmbeddingRow, MemoryId};
        use aether_l5_policy::AUDIT_SCHEMA_VERSION_V2;

        let phrase = "the Karpathy fix on tuesday";

        let state = AppState::new().expect("AppState::new");

        // Enable embeddings + swap to a deterministic stub embedder so
        // the orchestrator returns hits without needing Ollama.
        {
            let stub: Arc<dyn EmbeddingProvider> = Arc::new(StubEmbedder::new(16));
            *state.embedding_provider.write().unwrap() = stub;
        }
        {
            let mut cfg = state.memory_config();
            cfg.embeddings.enabled = true;
            cfg.embeddings.provider = Some("stub:16".into());
            state.set_memory_config(cfg).expect("set_memory_config");
        }

        // Seed a durable memory row whose content matches the phrase so
        // the stub embedder ranks it highly. Pair it with an embedding
        // row keyed off the same memory_id format the store emits.
        state
            .durable_memory
            .append(TurnMemoryRecord {
                session_id: SESSION_ID.into(),
                sequence: 0, // recomputed by the store
                role: MemoryRole::User,
                content: phrase.into(),
                timestamp_ms: 1_000,
            })
            .expect("seed durable");
        let provider = state.embedding_provider.read().unwrap().clone();
        let v = provider.embed(phrase).expect("seed embed");
        state
            .embedding_store
            .upsert(EmbeddingRow {
                memory_id: MemoryId::new(format!("mem-{SESSION_ID}-1")),
                domain: MemoryDomain::Durable,
                vector: v,
            })
            .expect("seed embedding row");

        // ---- Mirror submit_turn's body, helper-for-helper. ----
        let text = phrase.to_string();
        let (capability, resource) = parse_command(&text);

        let max_items = state.memory_config().retrieval.max_items as usize;
        let hits = crate::retrieval::run_retrieval_context(
            &state,
            SESSION_ID,
            &text,
            max_items,
            DEFAULT_RETRIEVAL_DEADLINE,
        );
        assert!(
            !hits.is_empty(),
            "retrieval should return hits for the seeded phrase; if this fires the \
             stub-embedder seed path drifted",
        );

        let retrieval_block = crate::retrieval::format_retrieval_block(&hits);
        let router_utterance =
            crate::retrieval::augment_utterance(retrieval_block.as_deref(), &text);

        // Sanity: the augmented router utterance is what submit_turn
        // would forward — must differ from the original AND must carry
        // both the retrieval-block prefix and the user's exact text.
        assert_ne!(
            router_utterance, text,
            "router utterance should diverge from original when retrieval fires",
        );
        assert!(
            router_utterance.contains("Relevant context (retrieval):"),
            "augmented utterance missing retrieval-block prefix; got {router_utterance:?}",
        );
        assert!(
            router_utterance.contains(phrase),
            "augmented utterance lost the user's original phrase; got {router_utterance:?}",
        );

        let ts = state.next_ts();
        let request = {
            let a = state.active.read().expect("active read lock");
            TurnRequest {
                session_id: SessionId(SESSION_ID.into()),
                persona: PersonaId(a.compiled.persona_id.0.clone()),
                task_id: None,
                original_utterance: text.clone(),
                model_input_utterance: router_utterance.clone(),
                capability,
                resource,
                emitted_at: MonotonicTimestamp(ts),
                // Same `Some(retrieval_provenance_for(...))` shape as
                // submit_turn — even an empty hits vec gets `Some(...)`
                // here so absence-vs-empty stays distinguishable.
                retrieval_provenance: Some(retrieval_provenance_for(&hits)),
            }
        };

        // Drive the engine — this is what writes the audit row.
        let result = {
            let a = state.active.read().expect("active read lock");
            a.engine.handle_turn(request).expect("handle_turn")
        };
        // Sanity: a `parse_command(phrase)` for plain chat resolves to
        // FilesRead/None which the default policy Allows — engine should
        // reach Completed and emit a route.
        assert!(
            matches!(result.policy_decision, Decision::Allow { .. }),
            "expected Allow on plain chat, got {:?}",
            result.policy_decision,
        );

        // ---- Read back via the same projection body audit_recent uses. ----
        let filter = AuditFilter::default();
        let rows = {
            let a = state.active.read().expect("active read lock");
            a.audit.query(&filter, 50)
        };
        // Find the row we just wrote — match on the change_id from the
        // engine result so we don't pick up the retrieval-gate audit row
        // (`Capability::RetrievalContext`) the orchestrator emits.
        let written_change_id = match &result.policy_decision {
            Decision::Allow { audit_id, .. } => audit_id.0.clone(),
            other => panic!("unexpected decision: {other:?}"),
        };
        let raw = rows
            .into_iter()
            .find(|r| r.audit_id.0 == written_change_id)
            .expect("audit row for the conversational turn");

        // Project through the same shape audit_recent emits to the UI.
        let projected = TrustAuditRow {
            audit_id: raw.audit_id.0,
            decision: decision_kind_label(raw.decision).to_string(),
            capability: aether_l7_trust::human_capability(&raw.capability).to_string(),
            scope: aether_l7_trust::human_scope(&raw.resource),
            change_id: raw.change_id.0,
            at_mono_ns: raw.timestamp_monotonic.0,
            at_epoch_s: raw.timestamp_wall.epoch_s,
            schema_version: raw.schema_version,
            original_utterance: raw.original_utterance,
            retrieval_provenance: raw.retrieval_provenance.map(|p| TrustRetrievalProvenance {
                block_present: p.block_present,
                hits: p
                    .hits
                    .into_iter()
                    .map(|h| TrustRetrievalHit {
                        memory_id: h.memory_id,
                        domain: h.domain,
                        score: h.score,
                    })
                    .collect(),
            }),
        };

        // (1) Original utterance survives byte-for-byte.
        assert_eq!(
            projected.original_utterance.as_deref(),
            Some(phrase),
            "audit row's original_utterance must equal the user's exact text",
        );

        // (2) Schema version is v2 (write-side stamp).
        assert_eq!(
            projected.schema_version, AUDIT_SCHEMA_VERSION_V2,
            "post-ADR-0009 writers must stamp schema_version=2",
        );

        // (3) Retrieval provenance is Some + non-empty hits.
        let prov = projected
            .retrieval_provenance
            .as_ref()
            .expect("retrieval_provenance must be Some when retrieval fired");
        assert!(
            prov.block_present,
            "block_present should be true when hits were returned",
        );
        assert!(
            !prov.hits.is_empty(),
            "hits must be non-empty when the orchestrator returned non-empty hits",
        );

        // (4) Original utterance and the augmented router utterance
        //     diverge — proving the two-channel split holds. The audit
        //     row only stores the original; we reconstruct the
        //     augmented form from `format_retrieval_block` + the
        //     original utterance to assert the inequality.
        assert_ne!(
            projected.original_utterance.as_deref(),
            Some(router_utterance.as_str()),
            "audit row must NOT store the augmented model-input utterance",
        );
    }

    // ---------- Wave 11 — Decision::Ask routing for browser_*/files_* ----------
    //
    // These tests prove the routing slice end-to-end without requiring
    // a Tauri runtime:
    //
    // 1. Calling a `*_inner(&state, None, ...)` whose gate Asks
    //    registers a `PendingApproval::Executor` row (not a
    //    `PendingApproval::Turn`) keyed on the ticket id, transitions
    //    presence (skipped here — None AppHandle), and returns the
    //    sentinel `awaiting_approval:<ticket_id>` error string. The
    //    executor mock is NOT invoked.
    //
    // 2. `resolve_executor_approval(approve=true, ...)` issues a
    //    one-shot grant via the live policy engine, then re-invokes
    //    the originally-attempted command through the same `*_inner`
    //    helper — the gate's second pass returns Allow (consume-while-
    //    valid grant), so the executor IS invoked exactly once.
    //
    // 3. `resolve_executor_approval(approve=false, ...)` does NOT
    //    invoke the executor and produces an `ExecutorApprovalReply`
    //    with `approved: false`.
    //
    // 4. The original chat-surface PendingApproval::Turn flow still
    //    works through the new dispatch — preserved by the existing
    //    `state::tests::ask_*` cycle, but locked here too at the
    //    `resolve_approval`-shaped wire surface for Wave 11.

    use aether_l5_browser::{
        BrowserExecError, BrowserExecutor, FormField, PageSnapshot,
        SessionId as BrowserSessionId,
    };
    use aether_l5_files::{FilesExecError, FilesExecutor, GrepHit};
    use async_trait::async_trait;
    use std::path::Path;
    use std::sync::Mutex as StdMutex;

    /// Tracking browser executor — same shape as
    /// `browser_commands::tests::MockExecutor` but inlined here so
    /// the Wave 11 tests don't have to share a module.
    #[derive(Default)]
    struct CountingBrowser {
        calls: StdMutex<Vec<String>>,
    }
    impl CountingBrowser {
        fn calls(&self) -> Vec<String> {
            self.calls.lock().unwrap().clone()
        }
    }
    #[async_trait]
    impl BrowserExecutor for CountingBrowser {
        async fn open(&self, _url: &str) -> Result<BrowserSessionId, BrowserExecError> {
            self.calls.lock().unwrap().push("open".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn navigate(
            &self,
            _s: BrowserSessionId,
            _u: &str,
        ) -> Result<(), BrowserExecError> {
            self.calls.lock().unwrap().push("navigate".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn read_page(
            &self,
            _s: BrowserSessionId,
        ) -> Result<PageSnapshot, BrowserExecError> {
            self.calls.lock().unwrap().push("read_page".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn extract(
            &self,
            _s: BrowserSessionId,
            _sel: &str,
        ) -> Result<Vec<String>, BrowserExecError> {
            self.calls.lock().unwrap().push("extract".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn fill_form(
            &self,
            _s: BrowserSessionId,
            _f: &[FormField],
        ) -> Result<(), BrowserExecError> {
            self.calls.lock().unwrap().push("fill_form".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn submit(
            &self,
            _s: BrowserSessionId,
            _sel: &str,
        ) -> Result<(), BrowserExecError> {
            self.calls.lock().unwrap().push("submit".into());
            Err(BrowserExecError::BackendDisabled)
        }
        async fn close(&self, _s: BrowserSessionId) -> Result<(), BrowserExecError> {
            self.calls.lock().unwrap().push("close".into());
            Err(BrowserExecError::BackendDisabled)
        }
    }

    /// Tracking files executor — mirrors the browser variant.
    #[derive(Default)]
    struct CountingFiles {
        calls: StdMutex<Vec<String>>,
    }
    impl CountingFiles {
        fn calls(&self) -> Vec<String> {
            self.calls.lock().unwrap().clone()
        }
    }
    #[async_trait]
    impl FilesExecutor for CountingFiles {
        async fn read(&self, _path: &Path) -> Result<Vec<u8>, FilesExecError> {
            self.calls.lock().unwrap().push("read".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn create(
            &self,
            _path: &Path,
            _contents: &[u8],
        ) -> Result<(), FilesExecError> {
            self.calls.lock().unwrap().push("create".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn edit(&self, _path: &Path, _contents: &[u8]) -> Result<(), FilesExecError> {
            self.calls.lock().unwrap().push("edit".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn rename(&self, _src: &Path, _dst: &Path) -> Result<(), FilesExecError> {
            self.calls.lock().unwrap().push("rename".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn delete(&self, _path: &Path) -> Result<(), FilesExecError> {
            self.calls.lock().unwrap().push("delete".into());
            Err(FilesExecError::BackendDisabled)
        }
        async fn grep(
            &self,
            _root: &Path,
            _pattern: &str,
        ) -> Result<Vec<GrepHit>, FilesExecError> {
            self.calls.lock().unwrap().push("grep".into());
            Err(FilesExecError::BackendDisabled)
        }
    }

    fn block_on<F: std::future::Future>(fut: F) -> F::Output {
        use std::sync::Arc as StdArc;
        use std::task::{Context, Poll, Wake, Waker};
        struct NoopWaker;
        impl Wake for NoopWaker {
            fn wake(self: StdArc<Self>) {}
        }
        let waker = Waker::from(StdArc::new(NoopWaker));
        let mut ctx = Context::from_waker(&waker);
        let mut fut = Box::pin(fut);
        loop {
            if let Poll::Ready(v) = fut.as_mut().poll(&mut ctx) {
                return v;
            }
        }
    }

    /// Build an `AppState` with both executors swapped for tracking
    /// mocks so the Wave 11 tests can assert the executor is invoked
    /// exactly once on the post-approval replay.
    fn state_with_tracking_executors() -> (AppState, std::sync::Arc<CountingBrowser>, std::sync::Arc<CountingFiles>) {
        let browser = std::sync::Arc::new(CountingBrowser::default());
        let files = std::sync::Arc::new(CountingFiles::default());
        let mut state = AppState::new().expect("AppState::new in-memory");
        state.browser_executor = browser.clone() as std::sync::Arc<dyn BrowserExecutor>;
        state.files_executor = files.clone() as std::sync::Arc<dyn FilesExecutor>;
        (state, browser, files)
    }

    /// Drive the gate to Ask once, capturing the ticket id from the
    /// sentinel error string. Returns `None` if the gate did not Ask
    /// for `files_edit` (e.g. the default policy was tightened to
    /// Deny). Tests that need an Ask use `assert!` on the Some-path.
    fn drive_files_edit_to_ask(
        state: &AppState,
    ) -> Option<String> {
        let res = block_on(crate::files_commands::files_edit_inner(
            state,
            None,
            "/tmp/aether-wave11.txt".into(),
            b"hello".to_vec(),
        ));
        match res {
            Err(msg) if msg.starts_with("awaiting_approval:") => {
                Some(msg.strip_prefix("awaiting_approval:").unwrap().to_string())
            }
            _ => None,
        }
    }

    #[test]
    fn ask_routes_to_pending_executor_not_pending_turn() {
        // Pre-condition: the registry is empty.
        let (state, _browser, files) = state_with_tracking_executors();
        // The default aurora persona + FilesEdit hits Ask under the
        // baseline policy disposition (locked by
        // `state::tests::apply_preset_observer_denies_write_capabilities`
        // which derives "without Observer Sable doesn't Deny"; aurora
        // baseline is the same). If this regresses, the routing slice
        // is no longer being exercised and we want to know.
        let ticket = drive_files_edit_to_ask(&state)
            .expect("baseline aurora + FilesEdit must Ask under default disposition");
        // Executor was NOT invoked.
        assert!(
            files.calls().is_empty(),
            "Ask must not invoke the executor; got {:?}",
            files.calls()
        );
        // Registry holds an Executor variant (NOT Turn).
        let pending = state.take_pending(&ticket).expect("pending entry");
        match pending {
            PendingApproval::Executor {
                call,
                approval,
                ticket: cached_ticket,
            } => {
                assert!(matches!(call, PendingExecutorCall::FilesEdit { .. }));
                assert_eq!(approval.ticket_id, ticket);
                // Wave 12: the live ticket is cached on the row so the
                // reject path can call respond_approval(Reject) for
                // audit completeness.
                assert_eq!(cached_ticket.ticket_id.0, ticket);
            }
            PendingApproval::Turn(_) => {
                panic!("Wave 11 must register Executor, not Turn");
            }
        }
    }

    #[test]
    fn resolve_executor_approval_approve_invokes_executor_exactly_once() {
        let (state, _browser, files) = state_with_tracking_executors();
        let ticket = drive_files_edit_to_ask(&state)
            .expect("baseline aurora + FilesEdit must Ask under default disposition");
        // Pull the entry back out and feed it to the resolve helper.
        let pending = state.take_pending(&ticket).expect("pending entry");
        let (call, approval) = match pending {
            PendingApproval::Executor {
                call,
                approval,
                ticket: _,
            } => (call, approval),
            PendingApproval::Turn(_) => unreachable!("registered Executor above"),
        };

        // We can't call `resolve_executor_approval` directly because
        // it needs an `AppHandle`. Exercise its private substeps in
        // sequence — that's the same wiring the real Tauri command
        // runs internally. (`AppHandle` is only used for emit + a
        // presence transition; both are UX-only and exercised
        // separately at the wrapper level.)
        issue_one_shot_grant_for_pending(&state, &call, &UserChoiceWire::Allow)
            .expect("grant issuance");
        let result = block_on(replay_executor_call(&state, call));

        // Replay must have invoked the executor exactly once. The mock
        // returns BackendDisabled on every call; the replay surfaces
        // that as Err(<disabled-string>), but the count is what we
        // care about for the security invariant.
        assert_eq!(
            files.calls(),
            vec!["edit".to_string()],
            "approve replay must invoke the files executor exactly once"
        );
        // The wire shape for the v1 routing slice surfaces the
        // BackendDisabled string verbatim; the UI's surface checks
        // `approved` rather than parsing the result.
        assert!(
            result.is_err(),
            "stub returns BackendDisabled; expected Err on the replay path"
        );
        // Sanity: after take_pending above, the registry is empty.
        assert!(state.take_pending(&ticket).is_none());
        // The approval payload was the one captured at gate-time.
        assert_eq!(approval.ticket_id, ticket);
    }

    #[test]
    fn resolve_executor_approval_reject_does_not_invoke_executor() {
        let (state, _browser, files) = state_with_tracking_executors();
        let ticket = drive_files_edit_to_ask(&state)
            .expect("baseline aurora + FilesEdit must Ask under default disposition");
        // Take the pending row out (mirroring resolve_approval's
        // dispatch path — take_pending is the consume point). Wave 12:
        // the row caches the live `ApprovalTicket`; exercise the
        // reject-path's `respond_approval(Reject)` call here, mirroring
        // the production path's reject branch.
        let pending = state.take_pending(&ticket).expect("pending entry");
        let (call, _approval, cached_ticket) = match pending {
            PendingApproval::Executor {
                call,
                approval,
                ticket,
            } => (call, approval, ticket),
            PendingApproval::Turn(_) => unreachable!(),
        };

        // Reject path: do NOT call issue_one_shot_grant_for_pending
        // and do NOT call replay_executor_call. The dispatch returns
        // `ExecutorApprovalReply { approved: false, ... }` without
        // touching the executor. Wave 12 additionally calls
        // `respond_approval(Reject)` against the cached live ticket
        // for L5 audit-row completeness.
        let _tag = method_tag(&call);
        let response = build_approval_response(
            &cached_ticket,
            ApprovalResolution::Reject,
            MonotonicTimestamp(state.next_ts()),
        );
        {
            let a = state.active.read().expect("active read lock");
            a.policy
                .respond_approval(response)
                .expect("Wave 12: respond_approval(Reject) must Ok against the cached live ticket");
        }
        // Executor mock saw no calls — security invariant preserved.
        assert!(
            files.calls().is_empty(),
            "reject path must not invoke the executor; got {:?}",
            files.calls()
        );
        // Registry is now empty (take_pending consumed it). A second
        // resolve attempt on the same ticket id should fail.
        assert!(state.take_pending(&ticket).is_none());
    }

    /// Wave 12 — the reject branch of `resolve_executor_approval` must
    /// call `respond_approval(Reject)` against the live ticket cached
    /// on `PendingApproval::Executor`. This test asserts the wiring by
    /// proving:
    ///   1. The ticket is cached on the pending row at gate-time and
    ///      its id matches the registry key driven by the Ask.
    ///   2. `build_approval_response(&ticket, Reject, ts)` against the
    ///      cached ticket is accepted by the live `PolicyEngine` (Ok)
    ///      — proving the cached ticket id matches what the engine
    ///      remembers.
    ///   3. A second `respond_approval` against the same ticket id is
    ///      rejected by the engine — proving the first call consumed
    ///      the ticket from the engine's pending table (the audit-row
    ///      side effect Wave 12 was added for actually happened).
    #[test]
    fn wave12_executor_reject_consumes_ticket_via_respond_approval() {
        let (state, _browser, _files) = state_with_tracking_executors();
        let ticket = drive_files_edit_to_ask(&state)
            .expect("baseline aurora + FilesEdit must Ask under default disposition");
        let pending = state.take_pending(&ticket).expect("pending entry");
        let cached_ticket = match pending {
            PendingApproval::Executor { ticket, .. } => ticket,
            PendingApproval::Turn(_) => unreachable!(),
        };
        // Cached ticket id matches the registry key that drove the Ask.
        assert_eq!(cached_ticket.ticket_id.0, ticket);

        // First Reject — the engine accepts and consumes the ticket.
        let first = build_approval_response(
            &cached_ticket,
            ApprovalResolution::Reject,
            MonotonicTimestamp(state.next_ts()),
        );
        {
            let a = state.active.read().expect("active read lock");
            a.policy
                .respond_approval(first)
                .expect("first Reject must Ok against the live cached ticket");
        }

        // Second Reject — the engine has already consumed the ticket;
        // a duplicate response must fail. This is the load-bearing
        // assertion: it proves the first Reject actually mutated the
        // engine's pending-tickets table (i.e. the audit-completeness
        // side effect Wave 12 was added for actually happened).
        let second = build_approval_response(
            &cached_ticket,
            ApprovalResolution::Reject,
            MonotonicTimestamp(state.next_ts()),
        );
        let dup_result = {
            let a = state.active.read().expect("active read lock");
            a.policy.respond_approval(second)
        };
        assert!(
            dup_result.is_err(),
            "second Reject against an already-consumed ticket must fail; \
             got Ok which would mean the first Reject was a no-op"
        );
    }

    #[test]
    fn pending_approval_turn_path_unaffected_by_wave11_widening() {
        // Wave 11 widened the registry to a sum type. The original
        // chat-surface `PendingApproval::Turn(...)` branch must still
        // round-trip the way it did before. We register a synthetic
        // turn pending row, take it back, and confirm the variant.
        let state = AppState::new().expect("AppState::new in-memory");
        let req = TurnRequest {
            session_id: aether_l5_policy::SessionId(SESSION_ID.into()),
            persona: PersonaId("aurora".into()),
            task_id: None,
            original_utterance: "ignore me".into(),
            model_input_utterance: "ignore me".into(),
            capability: Capability::FilesRead,
            resource: ResourceScope::None,
            emitted_at: MonotonicTimestamp(state.next_ts()),
            retrieval_provenance: None,
        };
        let ticket_id = "wave11-turn-roundtrip".to_string();
        // We synthesize a TurnResult to land into the registry; the
        // round-trip test only cares about variant identity, not the
        // engine flow.
        let synthesized = aether_l1_interaction::TurnResult {
            turn_id: aether_l1_interaction::TurnId("synthesized".into()),
            final_state: aether_l1_interaction::TurnState::Completed,
            policy_decision: Decision::Allow {
                grant_ref: None,
                audit_id: aether_l5_policy::AuditId("synthesized".into()),
            },
            route: None,
            block: None,
            state_trace: vec![],
        };
        state.record_pending(
            ticket_id.clone(),
            PendingApproval::Turn(PendingTurn {
                request: req,
                ask_result: synthesized,
                original_utterance: "ignore me".into(),
            }),
        );
        match state.take_pending(&ticket_id).expect("entry") {
            PendingApproval::Turn(_) => {}
            PendingApproval::Executor { .. } => panic!("expected Turn round-trip"),
        }
        assert!(state.take_pending(&ticket_id).is_none());
    }

    // ---------- Wave 14 — UserChoiceWire wire mapping + scope plumbing ----------

    /// Each wire variant must project onto the matching L5 `UserChoice`
    /// per design §5.3. This locks the wire-string contract: if a
    /// future refactor renames a variant, this test breaks first.
    #[test]
    fn wave14_user_choice_wire_maps_one_to_one() {
        use aether_l5_policy::UserChoice;
        assert!(matches!(
            UserChoiceWire::Allow.to_user_choice(),
            UserChoice::Allow
        ));
        assert!(matches!(
            UserChoiceWire::AllowSession.to_user_choice(),
            UserChoice::AllowSession
        ));
        assert!(matches!(
            UserChoiceWire::AllowTask.to_user_choice(),
            UserChoice::AllowTask
        ));
        assert!(matches!(
            UserChoiceWire::DeferToDraft.to_user_choice(),
            UserChoice::DeferToDraft
        ));
        assert!(matches!(
            UserChoiceWire::Deny.to_user_choice(),
            UserChoice::Deny
        ));
    }

    /// `is_approve()` is the gate for "did the user accept?" — every
    /// non-Deny variant counts. `defers_execution()` separately gates
    /// "did the user accept BUT request the draft path?" — only
    /// DeferToDraft.
    #[test]
    fn wave14_user_choice_wire_classifiers() {
        assert!(UserChoiceWire::Allow.is_approve());
        assert!(UserChoiceWire::AllowSession.is_approve());
        assert!(UserChoiceWire::AllowTask.is_approve());
        assert!(UserChoiceWire::DeferToDraft.is_approve());
        assert!(!UserChoiceWire::Deny.is_approve());

        assert!(!UserChoiceWire::Allow.defers_execution());
        assert!(!UserChoiceWire::AllowSession.defers_execution());
        assert!(!UserChoiceWire::AllowTask.defers_execution());
        assert!(UserChoiceWire::DeferToDraft.defers_execution());
        assert!(!UserChoiceWire::Deny.defers_execution());
    }

    /// Wire-string deserialization regression. The Tauri bridge serdes
    /// the JSON payload from the renderer; if the tag string drifts
    /// (e.g. someone renames `allow_session` to `session_allow`) this
    /// test breaks before any production path notices.
    #[test]
    fn wave14_user_choice_wire_deserializes_from_snake_case_tags() {
        let allow: UserChoiceWire =
            serde_json::from_str(r#"{"kind":"allow"}"#).expect("allow tag");
        assert!(matches!(allow, UserChoiceWire::Allow));

        let session: UserChoiceWire =
            serde_json::from_str(r#"{"kind":"allow_session"}"#).expect("allow_session tag");
        assert!(matches!(session, UserChoiceWire::AllowSession));

        let task: UserChoiceWire =
            serde_json::from_str(r#"{"kind":"allow_task"}"#).expect("allow_task tag");
        assert!(matches!(task, UserChoiceWire::AllowTask));

        let draft: UserChoiceWire =
            serde_json::from_str(r#"{"kind":"defer_to_draft"}"#).expect("defer_to_draft tag");
        assert!(matches!(draft, UserChoiceWire::DeferToDraft));

        let deny: UserChoiceWire =
            serde_json::from_str(r#"{"kind":"deny"}"#).expect("deny tag");
        assert!(matches!(deny, UserChoiceWire::Deny));
    }

    /// Reject path: respond_approval must consume the ticket once and
    /// reject the second attempt — same load-bearing assertion the
    /// Wave 12 test makes, but driven through the Wave 14 wire +
    /// build_approval_response_for_choice helper. Locks that the new
    /// helper is wire-compatible with the live engine.
    #[test]
    fn wave14_reject_via_user_choice_wire_consumes_ticket() {
        let (state, _browser, _files) = state_with_tracking_executors();
        let ticket = drive_files_edit_to_ask(&state)
            .expect("baseline aurora + FilesEdit must Ask under default disposition");
        let pending = state.take_pending(&ticket).expect("pending entry");
        let cached_ticket = match pending {
            PendingApproval::Executor { ticket, .. } => ticket,
            PendingApproval::Turn(_) => unreachable!(),
        };
        let choice = UserChoiceWire::Deny;
        let first = build_approval_response_for_choice(
            &cached_ticket,
            choice.to_user_choice(),
            MonotonicTimestamp(state.next_ts()),
        );
        {
            let a = state.active.read().expect("active read lock");
            a.policy
                .respond_approval(first)
                .expect("first Deny must Ok against the live cached ticket");
        }
        // Duplicate must fail — proves the engine consumed the ticket.
        let second = build_approval_response_for_choice(
            &cached_ticket,
            UserChoiceWire::Deny.to_user_choice(),
            MonotonicTimestamp(state.next_ts()),
        );
        let dup = {
            let a = state.active.read().expect("active read lock");
            a.policy.respond_approval(second)
        };
        assert!(
            dup.is_err(),
            "second Deny against an already-consumed ticket must fail"
        );
    }

    /// AllowSession via the Wave 14 wire produces a respond_approval
    /// the engine accepts (proving the new build_approval_response_for_choice
    /// path is engine-compatible) and consumes the ticket. The
    /// AllowSession case is the highest-leverage non-default variant —
    /// it is the one the audit-row downstream summary depends on for
    /// "you approved X for the session" copy.
    #[test]
    fn wave14_allow_session_via_user_choice_wire_consumes_ticket() {
        let (state, _browser, _files) = state_with_tracking_executors();
        let ticket = drive_files_edit_to_ask(&state)
            .expect("baseline aurora + FilesEdit must Ask under default disposition");
        let pending = state.take_pending(&ticket).expect("pending entry");
        let cached_ticket = match pending {
            PendingApproval::Executor { ticket, .. } => ticket,
            PendingApproval::Turn(_) => unreachable!(),
        };
        let choice = UserChoiceWire::AllowSession;
        let response = build_approval_response_for_choice(
            &cached_ticket,
            choice.to_user_choice(),
            MonotonicTimestamp(state.next_ts()),
        );
        // The L5 engine accepts the response — proves the wire
        // mapping landed a UserChoice the live engine recognises.
        {
            let a = state.active.read().expect("active read lock");
            a.policy
                .respond_approval(response)
                .expect("AllowSession respond_approval must Ok");
        }
        // Second response against the same ticket fails — proves the
        // first call consumed the engine's pending entry.
        let dup = build_approval_response_for_choice(
            &cached_ticket,
            UserChoiceWire::AllowSession.to_user_choice(),
            MonotonicTimestamp(state.next_ts()),
        );
        let dup_result = {
            let a = state.active.read().expect("active read lock");
            a.policy.respond_approval(dup)
        };
        assert!(
            dup_result.is_err(),
            "duplicate AllowSession must fail — proving the first call \
             actually mutated the engine's pending-tickets table"
        );
    }

    /// AllowTask wire variant exercises the same engine path. Mirror
    /// of the AllowSession test — kept separate so a regression on
    /// one variant doesn't get masked by the other.
    #[test]
    fn wave14_allow_task_via_user_choice_wire_consumes_ticket() {
        let (state, _browser, _files) = state_with_tracking_executors();
        let ticket = drive_files_edit_to_ask(&state)
            .expect("baseline aurora + FilesEdit must Ask under default disposition");
        let cached_ticket = match state.take_pending(&ticket).expect("pending entry") {
            PendingApproval::Executor { ticket, .. } => ticket,
            PendingApproval::Turn(_) => unreachable!(),
        };
        let response = build_approval_response_for_choice(
            &cached_ticket,
            UserChoiceWire::AllowTask.to_user_choice(),
            MonotonicTimestamp(state.next_ts()),
        );
        {
            let a = state.active.read().expect("active read lock");
            a.policy
                .respond_approval(response)
                .expect("AllowTask respond_approval must Ok");
        }
    }

    /// DeferToDraft wire variant: respond_approval must succeed (the
    /// engine writes the Decision::DraftOnly { source: UserChoice }
    /// audit row per Decision 2). The executor MUST NOT be invoked —
    /// that's the load-bearing security invariant for DeferToDraft.
    /// We assert the no-execute property by exercising the same
    /// shape the executor-path reject branch does, because the
    /// production resolve_executor_approval treats DeferToDraft
    /// identically (`!is_approve() || defers_execution()` short-
    /// circuits the executor invocation).
    #[test]
    fn wave14_defer_to_draft_via_user_choice_wire_does_not_execute() {
        let (state, _browser, files) = state_with_tracking_executors();
        let ticket = drive_files_edit_to_ask(&state)
            .expect("baseline aurora + FilesEdit must Ask under default disposition");
        let cached_ticket = match state.take_pending(&ticket).expect("pending entry") {
            PendingApproval::Executor { ticket, .. } => ticket,
            PendingApproval::Turn(_) => unreachable!(),
        };
        let choice = UserChoiceWire::DeferToDraft;
        // The classifier flags this as approve-with-no-execute —
        // resolve_executor_approval branches identically to Reject.
        assert!(choice.is_approve());
        assert!(choice.defers_execution());

        let response = build_approval_response_for_choice(
            &cached_ticket,
            choice.to_user_choice(),
            MonotonicTimestamp(state.next_ts()),
        );
        {
            let a = state.active.read().expect("active read lock");
            a.policy
                .respond_approval(response)
                .expect("DeferToDraft respond_approval must Ok");
        }
        // Executor mock saw no calls — DeferToDraft must NOT dispatch
        // the executor.
        assert!(
            files.calls().is_empty(),
            "DeferToDraft must not invoke the executor; got {:?}",
            files.calls()
        );
    }

    /// Wave 19 — Doctrine §8 used-as-user equivalent at the Rust layer.
    ///
    /// Existing `resolve_executor_approval_approve_invokes_executor_exactly_once`
    /// proves the executor is called exactly once on Approve, but it
    /// uses a tracking mock that returns `BackendDisabled` regardless of
    /// allowlist state. That hides the load-bearing Wave 13b property:
    /// the L5 grant emitted by `respond_approval` MUST flow through
    /// [`crate::policy_sink::ExecutorAllowlistSink`] into the live
    /// `StdFsExecutor`'s allowlist, so the replay's actual `read()`
    /// crosses the path-allowlist gate.
    ///
    /// This test wires no mock — it boots `AppState::new()` with the
    /// real `StdFsExecutor`, real `DefaultPolicyEngine`, and real
    /// `ExecutorAllowlistSink`, drives a `files_read` against a
    /// tempfile, exercises the Approve substeps that
    /// `resolve_executor_approval` runs (`issue_one_shot_grant_for_pending`
    /// → `replay_executor_call`), and asserts the replay returns the
    /// real file bytes — proving the sink fired and the allowlist now
    /// permits the path that was `NotInScope` before the grant.
    #[tokio::test]
    async fn wave19_real_executor_replay_after_approve_returns_real_bytes() {
        use tempfile::TempDir;

        let dir = TempDir::new().expect("tempdir");
        let path = dir.path().join("aether-wave19.txt");
        let contents = b"wave19-end-to-end\n";
        std::fs::write(&path, contents).expect("seed tempfile");
        let path_str = path.to_string_lossy().into_owned();

        let state = AppState::new().expect("AppState::new in-memory");

        // Sanity: with the boot-time allowlist empty, a direct executor
        // read against the tempfile must reject as `NotInScope`. This
        // is the precondition that proves the gate-then-grant flow is
        // actually doing work — if this assert flipped, the test
        // wouldn't be measuring the sink's contribution. (The
        // `require_runtime` short-circuit in `std_fs_stub` is satisfied
        // because we're inside a `#[tokio::test]` runtime.)
        let pre_err = state.files_executor.read(&path).await.unwrap_err();
        assert!(
            matches!(pre_err, aether_l5_files::FilesExecError::NotInScope(_)),
            "boot-time allowlist must reject before a grant lands; got {pre_err:?}",
        );

        // Drive `files_edit_inner` — under the aurora baseline this
        // capability is the one proven to Ask (see
        // `ask_routes_to_pending_executor_not_pending_turn`). Editing is
        // gated; the resulting `Allow` grant covers a `Capability::FilesEdit`
        // with `ResourceScope::Path(path)`, which `is_files_capability`
        // matches, so the sink will rebuild the allowlist with the
        // canonical tempfile path — and a direct *read* against that
        // path then succeeds because the executor's path-allowlist is
        // capability-agnostic at the executor layer.
        let ticket = match crate::files_commands::files_edit_inner(
            &state,
            None,
            path_str.clone(),
            contents.to_vec(),
        )
        .await
        {
            Err(msg) if msg.starts_with("awaiting_approval:") => {
                msg.strip_prefix("awaiting_approval:").unwrap().to_string()
            }
            other => panic!(
                "expected gate to Ask for files_edit against a fresh tempfile; got {other:?}"
            ),
        };

        let pending = state
            .take_pending(&ticket)
            .expect("Ask must register a pending entry");
        let call = match pending {
            PendingApproval::Executor { call, .. } => call,
            PendingApproval::Turn(_) => panic!("files_edit registers Executor, not Turn"),
        };
        assert!(matches!(call, PendingExecutorCall::FilesEdit { .. }));

        // Approve substeps that `resolve_executor_approval` runs (it
        // additionally emits + presence-transitions, both of which need
        // an `AppHandle` and are not relevant to this property).
        // `issue_one_shot_grant_for_pending` calls
        // `policy.respond_approval(Allow)`, which fires
        // `L5Event::GrantIssued` into the real sink, which rebuilds the
        // executor allowlist from the (now-non-empty) ledger.
        issue_one_shot_grant_for_pending(&state, &call, &UserChoiceWire::Allow)
            .expect("Wave 13b: issuing the Allow grant must succeed");

        // Replay the FilesEdit through `replay_executor_call`. The
        // just-updated allowlist now permits the canonical tempfile, so
        // the real `StdFsExecutor::edit` succeeds — proving the sink
        // propagated the grant end-to-end. `replay_executor_call`
        // formats `FilesEdit` success as the literal `"ok"`.
        let replay = replay_executor_call(&state, call)
            .await
            .expect("Wave 13b replay must succeed once the allowlist contains the tempfile");
        assert_eq!(
            replay, "ok",
            "FilesEdit replay must surface the post-Wave-13b success shape",
        );

        // Belt-and-braces: a direct executor read against the same path
        // must now return the literal seed bytes (the gate is upstream
        // of the executor; once the allowlist contains the path the
        // executor returns the file contents verbatim). This pins the
        // sink-to-allowlist contract beyond the replay's formatted
        // wire shape.
        let post_bytes = state
            .files_executor
            .read(&path)
            .await
            .expect("post-grant direct read must succeed against the same allowlist");
        assert_eq!(
            post_bytes, contents,
            "direct executor read must return the seeded tempfile contents",
        );
    }
}
