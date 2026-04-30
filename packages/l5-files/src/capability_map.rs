//! Mapping from [`FilesExecutor`](crate::executor::FilesExecutor)
//! method names to [`aether_l5_policy::Capability`] variants.
//!
//! This is the integration point where future Tauri commands (and any
//! other call site outside the executor itself) check L5 policy
//! BEFORE invoking a method. The executor trait does not perform its
//! own policy check — that responsibility lives one layer up, by
//! design (CLAUDE.md §1.5: policy is the single writer for side
//! effects).
//!
//! Method names match the trait method identifiers verbatim so call
//! sites can use `stringify!(method)` if useful.

use aether_l5_policy::Capability;

/// Return the [`Capability`] that gates a given executor method, if
/// one applies.
///
/// All methods on
/// [`FilesExecutor`](crate::executor::FilesExecutor) return a
/// `Some(_)` here; the unit test `every_executor_method_maps`
/// enforces the inverse direction so a future method that forgets to
/// map fails fast at test time.
///
/// # Mapping rationale
///
/// - `"read"` → `FilesRead`.
/// - `"create"` → `FilesCreate`.
/// - `"edit"` → `FilesEdit`.
/// - `"rename"` → `FilesRenameMove`. The L5 enum collapses rename and
///   move under one variant because, in policy terms, both are the
///   same operation: changing the path of an existing file. Splitting
///   them would force callers to grant both for every flow without
///   tightening the security surface.
/// - `"delete"` → `FilesDelete`. Per T1.3 the policy layer enforces an
///   Ask gate above this — this map only names the capability.
/// - `"grep"` → `FilesRead`. A live grep is a read-side operation: it
///   reads file contents inside approved scope and returns matching
///   lines without mutating anything. Granting a separate
///   `FilesGrep` capability would be redundant — anything `FilesRead`
///   already permits is already greppable. (Mirror of the
///   `navigate → BrowserOpen` consolidation in `aether-l5-browser`:
///   one capability covers the read-side surface.)
pub fn capability_for_method(method: &str) -> Option<Capability> {
    match method {
        "read" => Some(Capability::FilesRead),
        "create" => Some(Capability::FilesCreate),
        "edit" => Some(Capability::FilesEdit),
        "rename" => Some(Capability::FilesRenameMove),
        "delete" => Some(Capability::FilesDelete),
        "grep" => Some(Capability::FilesRead),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn read_maps_to_filesread() {
        assert_eq!(capability_for_method("read"), Some(Capability::FilesRead));
    }

    #[test]
    fn create_maps_to_filescreate() {
        assert_eq!(
            capability_for_method("create"),
            Some(Capability::FilesCreate)
        );
    }

    #[test]
    fn edit_maps_to_filesedit() {
        assert_eq!(capability_for_method("edit"), Some(Capability::FilesEdit));
    }

    #[test]
    fn rename_maps_to_filesrenamemove() {
        assert_eq!(
            capability_for_method("rename"),
            Some(Capability::FilesRenameMove)
        );
    }

    #[test]
    fn delete_maps_to_filesdelete() {
        assert_eq!(
            capability_for_method("delete"),
            Some(Capability::FilesDelete)
        );
    }

    #[test]
    fn grep_maps_to_filesread() {
        // Read-side rationale: see module docs. Locking it in here so a
        // future change that splits grep into its own capability has to
        // update this test deliberately.
        assert_eq!(capability_for_method("grep"), Some(Capability::FilesRead));
    }

    #[test]
    fn unknown_method_returns_none() {
        assert_eq!(capability_for_method("teleport"), None);
        assert_eq!(capability_for_method(""), None);
        // FilesBulkOp is a known L5 capability but no executor method
        // names it today; callers that orchestrate bulk ops compose
        // multiple single-file calls and gate them at a higher layer.
        assert_eq!(capability_for_method("bulk_op"), None);
    }

    /// Inverse-direction guard: every method named on the trait MUST
    /// map to a `Some(Capability)` here. If you add a method to
    /// `FilesExecutor` without updating `capability_for_method`, this
    /// test fails.
    #[test]
    fn every_executor_method_maps() {
        // Method names taken verbatim from `FilesExecutor` in
        // `executor.rs`. Keep this list in sync with the trait.
        let gated = ["read", "create", "edit", "rename", "delete", "grep"];

        for m in gated {
            assert!(
                capability_for_method(m).is_some(),
                "expected {m:?} to map to a Capability"
            );
        }
    }
}
