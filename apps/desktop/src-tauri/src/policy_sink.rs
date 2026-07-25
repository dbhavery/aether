//! Wave 13b — L5 event sink that mirrors File-capability grants into
//! the live `StdFsExecutor` allowlist.
//!
//! The L5 policy engine emits a [`L5Event::GrantIssued`] when the user
//! approves an `Ask` decision and a [`L5Event::GrantRevoked`] when a
//! grant expires, is user-revoked, or is cascaded by a persona/preset
//! change. The shell needs the file backend's
//! [`ScopeAllowlist`](aether_l5_files::ScopeAllowlist) to track those
//! transitions in real time — otherwise an Approve fires but the next
//! `files_*` invocation still hits `FilesExecError::NotInScope`.
//!
//! [`ExecutorAllowlistSink`] wraps an inner `L5EventSink` (so the test
//! infra's `InMemorySink` collection still works), watches for the two
//! grant variants, and on each one it re-snapshots the ledger and
//! rebuilds the executor's allowlist from the union of currently-active
//! File-capability grants. Path canonicalization is best-effort per
//! path (a single bad path drops out of the new allowlist instead of
//! aborting the whole rebuild) — the L5 ledger may carry grants whose
//! paths were canonicalized at issuance time and have since become
//! unmountable.
//!
//! Per CLAUDE.md §1.5 the sink does NOT enforce policy — the L5 engine
//! has already issued the grant by the time we see the event. The sink
//! merely propagates the resulting scope into the executor's
//! defence-in-depth allowlist.

use std::path::PathBuf;
use std::sync::Arc;

use aether_l5_files::std_fs_stub::StdFsExecutor;
use aether_l5_files::ScopeAllowlist;
use aether_l5_policy::{
    Capability, GrantFilter, GrantLedger, L5Event, L5EventSink, ResourceScope,
};

/// L5 event sink that keeps the live `StdFsExecutor` allowlist in sync
/// with the user-approved File-capability grants.
///
/// `inner` is forwarded to for every event so existing collection
/// consumers (e.g. `InMemorySink` in tests) keep working. Only
/// `GrantIssued` / `GrantRevoked` trigger the allowlist rebuild — every
/// other variant short-circuits to the inner forward.
pub struct ExecutorAllowlistSink {
    inner: Arc<dyn L5EventSink>,
    ledger: Arc<dyn GrantLedger>,
    executor: Arc<StdFsExecutor>,
}

impl ExecutorAllowlistSink {
    /// Build a new wrapping sink. `inner` receives every event the
    /// engine emits; `ledger` is re-snapshotted on each grant
    /// transition; `executor` is the file backend whose allowlist will
    /// be replaced atomically.
    pub fn new(
        inner: Arc<dyn L5EventSink>,
        ledger: Arc<dyn GrantLedger>,
        executor: Arc<StdFsExecutor>,
    ) -> Self {
        Self {
            inner,
            ledger,
            executor,
        }
    }

    /// Re-snapshot the ledger, extract every active File-capability
    /// grant's resource path, canonicalize each path (per-path
    /// best-effort — a path that fails canonicalize is dropped, not
    /// fatal), and atomically swap the executor's allowlist to the
    /// resulting set.
    ///
    /// Empty ledger / no File grants ⇒ empty allowlist (every
    /// subsequent `files_*` call falls through to
    /// `FilesExecError::NotInScope`, which is the desired post-revoke
    /// behaviour).
    fn rebuild_allowlist(&self) {
        let active = self.ledger.snapshot(&GrantFilter {
            active_only: true,
            ..Default::default()
        });
        let mut canonical: Vec<PathBuf> = Vec::new();
        for grant in active.iter() {
            if !is_files_capability(&grant.capability) {
                continue;
            }
            let raw = match &grant.resource_pattern {
                ResourceScope::Path(s) => PathBuf::from(s),
                _ => continue,
            };
            // Best-effort canonicalize. A path that fails resolve
            // (volume unmounted, dir deleted out from under the grant)
            // simply drops out of the new allowlist; the corresponding
            // grant will then fail its next L5 evaluate and surface a
            // clearer error to the user.
            match std::fs::canonicalize(&raw) {
                Ok(c) => canonical.push(c),
                Err(e) => {
                    tracing::warn!(
                        "ExecutorAllowlistSink: dropping un-canonicalizable grant path {}: {}",
                        raw.display(),
                        e
                    );
                }
            }
        }
        self.executor
            .set_allowlist(ScopeAllowlist::new(canonical));
    }
}

/// True iff the capability is one of the file-workflow variants whose
/// `ResourceScope::Path(_)` should be reflected into the executor's
/// allowlist.
fn is_files_capability(cap: &Capability) -> bool {
    matches!(
        cap,
        Capability::FilesRead
            | Capability::FilesCreate
            | Capability::FilesEdit
            | Capability::FilesRenameMove
            | Capability::FilesDelete
            | Capability::FilesBulkOp
    )
}

impl L5EventSink for ExecutorAllowlistSink {
    fn emit(&self, event: L5Event) {
        // Inspect-then-forward. Cloning the event is cheap (small enums
        // with `Arc`-friendly innards) and lets the inner sink see every
        // event regardless of what we do with it.
        match &event {
            L5Event::GrantIssued(_) | L5Event::GrantRevoked(_) => {
                self.rebuild_allowlist();
            }
            _ => {}
        }
        self.inner.emit(event);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    // Bring `FilesExecutor::read` into scope for the assertions below.
    use aether_l5_files::FilesExecutor;
    use aether_l5_policy::{
        events::{GrantIssuedEvent, GrantRevokedEvent, RevokeReason},
        ApprovalMode, ApprovalScope, Grant, GrantDuration, GrantId, InMemoryGrantLedger,
        InMemorySink, MonotonicTimestamp, PersonaId,
    };
    use std::sync::Arc;
    use tempfile::TempDir;

    fn make_grant(id: &str, capability: Capability, path: &std::path::Path) -> Grant {
        Grant {
            grant_id: GrantId(id.to_string()),
            capability,
            resource_pattern: ResourceScope::Path(path.display().to_string()),
            persona_id: PersonaId("test-persona".to_string()),
            approval_mode: ApprovalMode::Ask,
            duration: GrantDuration::Session,
            issued_at: MonotonicTimestamp(0),
            expires_at: None,
            preset_version_issued_under: 0,
            approval_scope: Some(ApprovalScope::PerAction),
        }
    }

    fn make_grant_issued_event(id: &str) -> L5Event {
        L5Event::GrantIssued(GrantIssuedEvent {
            grant_id: GrantId(id.to_string()),
            capability: Capability::FilesRead,
            resource_scope: ResourceScope::Path("ignored-by-sink".to_string()),
            approval_mode: ApprovalMode::Ask,
            duration: GrantDuration::Session,
            issued_at: MonotonicTimestamp(0),
            issued_by: aether_l5_policy::ActorRef::User,
            audit_ref: aether_l5_policy::AuditId(String::new()),
            change_id: aether_l5_policy::ChangeId(String::new()),
            seq: 0,
            preset_version_issued_under: 0,
            approval_scope: Some(ApprovalScope::PerAction),
        })
    }

    fn make_grant_revoked_event(id: &str) -> L5Event {
        L5Event::GrantRevoked(GrantRevokedEvent {
            grant_id: GrantId(id.to_string()),
            revoked_at: MonotonicTimestamp(0),
            revoked_reason: RevokeReason::UserRevoked,
            audit_ref: aether_l5_policy::AuditId(String::new()),
            change_id: aether_l5_policy::ChangeId(String::new()),
            seq: 0,
        })
    }

    /// Issuing a `FilesRead` grant for a tempdir, then firing the
    /// matching `GrantIssued` event, must widen the executor allowlist
    /// to that tempdir. Reads inside it succeed; reads outside continue
    /// to fail.
    #[tokio::test]
    async fn grant_issued_event_widens_allowlist() {
        let dir = TempDir::new().unwrap();
        let canonical = std::fs::canonicalize(dir.path()).unwrap();
        let file = dir.path().join("hello.txt");
        std::fs::write(&file, b"hi").unwrap();

        let executor = Arc::new(StdFsExecutor::default());
        let ledger: Arc<dyn GrantLedger> = Arc::new(InMemoryGrantLedger::new());
        let inner: Arc<dyn L5EventSink> = Arc::new(InMemorySink::new());
        let sink = ExecutorAllowlistSink::new(inner.clone(), ledger.clone(), executor.clone());

        // Pre-condition: empty allowlist rejects.
        let err = executor.read(&file).await.unwrap_err();
        assert!(
            matches!(err, aether_l5_files::FilesExecError::NotInScope(_)),
            "got {err:?}"
        );

        // Issue the grant in the ledger, then fire the matching event.
        ledger
            .issue(make_grant("g1", Capability::FilesRead, &canonical))
            .expect("issue grant");
        sink.emit(make_grant_issued_event("g1"));

        // Allowlist now covers the tempdir.
        let bytes = executor.read(&file).await.unwrap();
        assert_eq!(bytes, b"hi");
    }

    /// Inverse: with a grant active and the allowlist seeded, revoking
    /// the grant + firing `GrantRevoked` narrows the allowlist back to
    /// empty. Subsequent reads return `NotInScope`.
    #[tokio::test]
    async fn grant_revoked_event_narrows_allowlist() {
        let dir = TempDir::new().unwrap();
        let canonical = std::fs::canonicalize(dir.path()).unwrap();
        let file = dir.path().join("h.txt");
        std::fs::write(&file, b"x").unwrap();

        let executor = Arc::new(StdFsExecutor::default());
        let ledger: Arc<dyn GrantLedger> = Arc::new(InMemoryGrantLedger::new());
        let inner: Arc<dyn L5EventSink> = Arc::new(InMemorySink::new());
        let sink = ExecutorAllowlistSink::new(inner.clone(), ledger.clone(), executor.clone());

        let grant_id = ledger
            .issue(make_grant("g2", Capability::FilesRead, &canonical))
            .expect("issue grant");
        sink.emit(make_grant_issued_event("g2"));
        // Sanity: read works.
        assert_eq!(executor.read(&file).await.unwrap(), b"x");

        // Revoke + fire event.
        ledger.revoke(&grant_id, RevokeReason::UserRevoked);
        sink.emit(make_grant_revoked_event("g2"));

        // Allowlist now empty.
        let err = executor.read(&file).await.unwrap_err();
        assert!(
            matches!(err, aether_l5_files::FilesExecError::NotInScope(_)),
            "got {err:?}"
        );
    }

    /// A non-File grant (e.g. `BrowserOpen` with `ResourceScope::Url`)
    /// must NOT widen the file allowlist. The sink's filter on
    /// `is_files_capability` is the protection.
    #[tokio::test]
    async fn non_file_grant_does_not_widen_allowlist() {
        let dir = TempDir::new().unwrap();
        let file = dir.path().join("h.txt");
        std::fs::write(&file, b"x").unwrap();

        let executor = Arc::new(StdFsExecutor::default());
        let ledger: Arc<dyn GrantLedger> = Arc::new(InMemoryGrantLedger::new());
        let inner: Arc<dyn L5EventSink> = Arc::new(InMemorySink::new());
        let sink = ExecutorAllowlistSink::new(inner.clone(), ledger.clone(), executor.clone());

        // Issue a non-File capability grant (BrowserOpen w/ Url scope).
        ledger
            .issue(Grant {
                grant_id: GrantId("g3".to_string()),
                capability: Capability::BrowserOpen,
                resource_pattern: ResourceScope::Url("https://example.com".to_string()),
                persona_id: PersonaId("test-persona".to_string()),
                approval_mode: ApprovalMode::Ask,
                duration: GrantDuration::Session,
                issued_at: MonotonicTimestamp(0),
                expires_at: None,
                preset_version_issued_under: 0,
                approval_scope: Some(ApprovalScope::PerAction),
            })
            .expect("issue grant");
        sink.emit(make_grant_issued_event("g3"));

        // Allowlist still empty — file read still rejects.
        let err = executor.read(&file).await.unwrap_err();
        assert!(
            matches!(err, aether_l5_files::FilesExecError::NotInScope(_)),
            "got {err:?}"
        );
    }

    /// Every event variant — including the two we react to — must be
    /// forwarded to the inner sink. Tests downstream of `InMemorySink`
    /// rely on collection completeness.
    #[tokio::test]
    async fn forwards_every_event_to_inner_sink() {
        let executor = Arc::new(StdFsExecutor::default());
        let ledger: Arc<dyn GrantLedger> = Arc::new(InMemoryGrantLedger::new());
        let inner = Arc::new(InMemorySink::new());
        let inner_dyn: Arc<dyn L5EventSink> = inner.clone();
        let sink = ExecutorAllowlistSink::new(inner_dyn, ledger.clone(), executor.clone());

        sink.emit(make_grant_issued_event("g4"));
        sink.emit(make_grant_revoked_event("g4"));
        // Pick any non-grant variant — `EmergencyRevokeAll` is cheap.
        sink.emit(L5Event::EmergencyRevokeAll(
            aether_l5_policy::events::EmergencyRevokeAllEvent {
                initiated_by: aether_l5_policy::ActorRef::User,
                scope: aether_l5_policy::events::EmergencyScope::All,
                initiated_at: MonotonicTimestamp(0),
                completed_at: None,
                revoked_count: None,
                audit_ref: aether_l5_policy::AuditId(String::new()),
                change_id: aether_l5_policy::ChangeId(String::new()),
                seq: 0,
            },
        ));

        let snap = inner.snapshot();
        assert_eq!(snap.len(), 3, "every event should reach the inner sink");
    }
}
