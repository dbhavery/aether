//! Memory-aware router wrapper. Mirrors `apps/l1-cli/src/memory.rs` — kept
//! per-app so the shell stays standalone. On each dispatch it loads the
//! recent window from L2 and prepends a rendered transcript before
//! forwarding to the inner router. L1 itself stays memory-agnostic.

use std::sync::Arc;

#[cfg(feature = "ollama-provider")]
use aether_l1_interaction::TokenUsage;
use aether_l1_interaction::{L1Error, RouteOutcome, TurnId, TurnResult, TurnRouter};
use aether_l2_memory::{
    render_transcript, MemoryRole, RecentMemoryWindow, SessionMemoryStore, TurnMemoryRecord,
};
use aether_l5_policy::Decision;

pub struct MemoryAwareRouter<R: TurnRouter> {
    inner: R,
    store: Arc<dyn SessionMemoryStore>,
    session_id: String,
}

impl<R: TurnRouter> MemoryAwareRouter<R> {
    pub fn new(
        inner: R,
        store: Arc<dyn SessionMemoryStore>,
        session_id: impl Into<String>,
    ) -> Self {
        Self {
            inner,
            store,
            session_id: session_id.into(),
        }
    }

    pub fn build_prompt(window: &RecentMemoryWindow, utterance: &str) -> String {
        let head = render_transcript(window);
        if head.is_empty() {
            utterance.to_string()
        } else {
            let mut out = String::with_capacity(head.len() + utterance.len() + 16);
            out.push_str(&head);
            out.push_str("User: ");
            out.push_str(utterance);
            out
        }
    }
}

impl<R: TurnRouter> TurnRouter for MemoryAwareRouter<R> {
    fn dispatch(
        &self,
        turn_id: &TurnId,
        prompt: &str,
        decision: &Decision,
    ) -> Result<RouteOutcome, L1Error> {
        let window = self
            .store
            .recent(&self.session_id)
            .map_err(|e| L1Error::Router(format!("memory recall failed: {e}")))?;
        let combined = Self::build_prompt(&window, prompt);
        self.inner.dispatch(turn_id, &combined, decision)
    }
}

/// Append the user side of a turn to memory with an explicit utterance
/// string. Shell callers use the raw variant (rather than reading
/// directly off `TurnRequest::utterance`) because ADR-0005 introduced a
/// retrieval-wiring path where the router sees a retrieval-augmented
/// utterance that memory must NOT record. Caller supplies the raw
/// utterance and the emission timestamp from `TurnRequest::emitted_at`.
pub fn user_record_raw(session_id: &str, utterance: &str, ts_ms: u64) -> TurnMemoryRecord {
    TurnMemoryRecord {
        session_id: session_id.to_string(),
        sequence: 0,
        role: MemoryRole::User,
        content: utterance.to_string(),
        timestamp_ms: ts_ms,
    }
}

/// Append the assistant or system side of a turn to memory. On Allow the
/// assistant text is the route response; on any block the content is a
/// short system note so transcript continuity survives refusals.
pub fn assistant_record(session_id: &str, result: &TurnResult, ts_ms: u64) -> TurnMemoryRecord {
    let (role, content) = summarise_turn_for_memory(result);
    TurnMemoryRecord {
        session_id: session_id.to_string(),
        sequence: 0,
        role,
        content,
        timestamp_ms: ts_ms,
    }
}

/// Role-tagged Ollama router (feature-gated).
///
/// Implements [`TurnRouter`] directly on top of [`OllamaProvider`], so the
/// shell can send Ollama the real role-tagged message history instead of
/// a single concatenated prompt string. Preferred over wrapping
/// [`ModelRouterAdapter`] + [`MemoryAwareRouter`] when the provider
/// supports `/api/chat`'s messages array, because instruction-tuned
/// models respond better to their own chat template than to a
/// pre-rendered transcript.
///
/// On each dispatch:
///   1. Pull the recent memory window for the session.
///   2. Emit a `system` message with the persona's system prompt (if
///      non-empty).
///   3. Emit one message per recorded turn, mapped 1:1 from
///      [`MemoryRole`] to [`aether_l4_router::MessageRole`].
///   4. Append the incoming utterance as the final `user` message.
///   5. Call [`OllamaProvider::chat_with_messages`] and wrap the reply in
///      a [`RouteOutcome`] carrying the configured tier label and
///      provider display string.
#[cfg(feature = "ollama-provider")]
pub struct RoleTaggedOllamaRouter {
    provider: aether_l4_router::OllamaProvider,
    store: Arc<dyn SessionMemoryStore>,
    session_id: String,
    system_prompt: String,
    tier_label: String,
    provider_label: String,
}

#[cfg(feature = "ollama-provider")]
impl RoleTaggedOllamaRouter {
    pub fn new(
        provider: aether_l4_router::OllamaProvider,
        store: Arc<dyn SessionMemoryStore>,
        session_id: impl Into<String>,
        system_prompt: impl Into<String>,
        tier_label: impl Into<String>,
        provider_label: impl Into<String>,
    ) -> Self {
        Self {
            provider,
            store,
            session_id: session_id.into(),
            system_prompt: system_prompt.into(),
            tier_label: tier_label.into(),
            provider_label: provider_label.into(),
        }
    }

    /// Build the role-tagged message array the provider will send.
    /// Exposed for tests.
    pub fn build_messages(
        window: &aether_l2_memory::RecentMemoryWindow,
        system_prompt: &str,
        utterance: &str,
    ) -> Vec<aether_l4_router::ChatMessage> {
        use aether_l4_router::{ChatMessage, MessageRole};
        let mut msgs: Vec<ChatMessage> = Vec::with_capacity(window.records.len() + 2);
        if !system_prompt.trim().is_empty() {
            msgs.push(ChatMessage::system(system_prompt.to_string()));
        }
        for r in &window.records {
            let role = match r.role {
                MemoryRole::User => MessageRole::User,
                MemoryRole::Assistant => MessageRole::Assistant,
                MemoryRole::System => MessageRole::System,
            };
            msgs.push(ChatMessage {
                role,
                content: r.content.clone(),
            });
        }
        msgs.push(ChatMessage {
            role: MessageRole::User,
            content: utterance.to_string(),
        });
        msgs
    }
}

#[cfg(feature = "ollama-provider")]
impl TurnRouter for RoleTaggedOllamaRouter {
    fn dispatch(
        &self,
        _turn_id: &TurnId,
        prompt: &str,
        _decision: &Decision,
    ) -> Result<RouteOutcome, L1Error> {
        let window = self
            .store
            .recent(&self.session_id)
            .map_err(|e| L1Error::Router(format!("memory recall failed: {e}")))?;
        let messages = Self::build_messages(&window, &self.system_prompt, prompt);
        let completion = self
            .provider
            .chat_with_messages_detailed(&messages)
            .map_err(|e| L1Error::Router(friendly_provider_error(&e)))?;
        // Only surface a TokenUsage when both sides of the count are
        // present. Mixed-presence (one side reported, the other missing)
        // would be harder for the UI to render truthfully than simply
        // omitting the meta.
        let tokens = match (completion.prompt_tokens, completion.completion_tokens) {
            (Some(prompt), Some(completion)) => Some(TokenUsage { prompt, completion }),
            _ => None,
        };
        Ok(RouteOutcome {
            tier: self.tier_label.clone(),
            provider: self.provider_label.clone(),
            response_text: completion.text,
            latency_ms: None, // TurnEngine::handle_turn stamps this.
            tokens,
        })
    }
}

/// Prefix attached to provider-error strings as they pass through
/// [`L1Error::Router`]. The shell's `submit_turn` command detects this
/// prefix and promotes the error into a transcript system message
/// (`kind = "provider_error"`) instead of surfacing it as a Tauri
/// command failure. Keep the prefix stable — `commands.rs` depends on
/// its exact spelling.
#[cfg(feature = "ollama-provider")]
pub const PROVIDER_ERROR_PREFIX: &str = "PROVIDER_ERROR: ";

/// Map a typed [`aether_l4_router::L4Error`] into a user-facing sentence.
/// Called on every provider failure inside
/// [`RoleTaggedOllamaRouter::dispatch`]; the result is prefixed with
/// [`PROVIDER_ERROR_PREFIX`] and routed through the existing
/// [`L1Error::Router`] channel so we don't need to widen
/// `aether_l1_interaction::L1Error` to carry typed provider errors yet.
///
/// Guidance per variant:
/// - `ProviderNotRunning` — point the user at `ollama serve`.
/// - `ProviderTimeout` — suggest a lighter model or a longer timeout.
/// - `ProviderModelNotFound` — name the model, suggest `ollama pull`.
/// - `ProviderBadResponse` — degraded provider; suggest retry.
/// - `ProviderUnknown` / catch-all — surface the detail verbatim so we
///   can diagnose later without losing information.
#[cfg(feature = "ollama-provider")]
pub fn friendly_provider_error(err: &aether_l4_router::L4Error) -> String {
    use aether_l4_router::L4Error;
    let body = match err {
        L4Error::ProviderNotRunning { .. } => String::from(
            "Companion can't reach the local model daemon. Start it with `ollama serve` and try again.",
        ),
        L4Error::ProviderTimeout { .. } => String::from(
            "The local model took too long to respond. Try a smaller model, or raise AETHER_OLLAMA_TIMEOUT_MS.",
        ),
        L4Error::ProviderModelNotFound { model, .. } => format!(
            "Model `{model}` isn't installed. Pull it with `ollama pull {model}` and try again.",
        ),
        L4Error::ProviderBadResponse { detail } => format!(
            "The model returned something Companion couldn't parse. Retry, and if it persists the model may be degraded. ({detail})",
        ),
        L4Error::ProviderUnknown { detail } => format!(
            "The provider failed with an unrecognised error. ({detail})",
        ),
        other => format!("Provider error: {other}"),
    };
    format!("{PROVIDER_ERROR_PREFIX}{body}")
}

fn summarise_turn_for_memory(result: &TurnResult) -> (MemoryRole, String) {
    if let Some(route) = &result.route {
        return (MemoryRole::Assistant, route.response_text.clone());
    }
    let note = match &result.block {
        Some(aether_l1_interaction::BlockReason::AwaitingApproval) => {
            "awaiting user approval for the last request".to_string()
        }
        Some(aether_l1_interaction::BlockReason::Denied) => {
            "policy denied that request".to_string()
        }
        Some(aether_l1_interaction::BlockReason::NeedsUpgrade) => {
            "capability not in active preset".to_string()
        }
        Some(aether_l1_interaction::BlockReason::DraftOnly) => {
            "draft-only — no side effects permitted".to_string()
        }
        None => format!("turn ended in state {:?}", result.final_state),
    };
    (MemoryRole::System, note)
}

#[cfg(all(test, feature = "ollama-provider"))]
mod tests {
    use super::*;
    use aether_l2_memory::{RecentMemoryWindow, TurnMemoryRecord};
    use aether_l4_router::MessageRole;

    fn rec(role: MemoryRole, content: &str, seq: u64) -> TurnMemoryRecord {
        TurnMemoryRecord {
            session_id: "s".into(),
            sequence: seq,
            role,
            content: content.into(),
            timestamp_ms: 1_000 + seq,
        }
    }

    #[test]
    fn build_messages_emits_system_then_history_then_current_user() {
        let window = RecentMemoryWindow {
            session_id: "s".into(),
            records: vec![
                rec(MemoryRole::User, "hello", 1),
                rec(MemoryRole::Assistant, "hi there", 2),
            ],
        };
        let msgs =
            RoleTaggedOllamaRouter::build_messages(&window, "You are Aurora.", "how are you");
        assert_eq!(msgs.len(), 4);
        assert_eq!(msgs[0].role, MessageRole::System);
        assert_eq!(msgs[0].content, "You are Aurora.");
        assert_eq!(msgs[1].role, MessageRole::User);
        assert_eq!(msgs[1].content, "hello");
        assert_eq!(msgs[2].role, MessageRole::Assistant);
        assert_eq!(msgs[2].content, "hi there");
        assert_eq!(msgs[3].role, MessageRole::User);
        assert_eq!(msgs[3].content, "how are you");
    }

    #[test]
    fn build_messages_skips_system_entry_when_prompt_is_blank() {
        let window = RecentMemoryWindow {
            session_id: "s".into(),
            records: vec![],
        };
        let msgs = RoleTaggedOllamaRouter::build_messages(&window, "   ", "hi");
        assert_eq!(msgs.len(), 1);
        assert_eq!(msgs[0].role, MessageRole::User);
        assert_eq!(msgs[0].content, "hi");
    }

    #[test]
    fn friendly_provider_error_covers_known_variants() {
        use aether_l4_router::L4Error;
        let not_running = friendly_provider_error(&L4Error::ProviderNotRunning {
            detail: "conn refused".into(),
        });
        assert!(not_running.starts_with(PROVIDER_ERROR_PREFIX));
        assert!(not_running.contains("ollama serve"));

        let timeout = friendly_provider_error(&L4Error::ProviderTimeout {
            detail: "read timeout".into(),
        });
        assert!(timeout.contains("took too long"));
        assert!(timeout.contains("AETHER_OLLAMA_TIMEOUT_MS"));

        let not_found = friendly_provider_error(&L4Error::ProviderModelNotFound {
            model: "phi3".into(),
            detail: "not found".into(),
        });
        assert!(not_found.contains("`phi3`"));
        assert!(not_found.contains("ollama pull phi3"));

        let bad = friendly_provider_error(&L4Error::ProviderBadResponse {
            detail: "junk".into(),
        });
        assert!(bad.contains("couldn't parse"));
        assert!(bad.contains("junk"));
    }

    #[test]
    fn build_messages_maps_system_role_records_through() {
        // Block / denial summaries are stored as MemoryRole::System —
        // ensure those pass through as `system` to the provider rather
        // than being swallowed.
        let window = RecentMemoryWindow {
            session_id: "s".into(),
            records: vec![rec(MemoryRole::System, "policy denied that request", 1)],
        };
        let msgs = RoleTaggedOllamaRouter::build_messages(&window, "", "retry");
        assert_eq!(msgs.len(), 2);
        assert_eq!(msgs[0].role, MessageRole::System);
        assert_eq!(msgs[0].content, "policy denied that request");
        assert_eq!(msgs[1].role, MessageRole::User);
    }
}
