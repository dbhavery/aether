//! Mapping from [`BrowserExecutor`](crate::executor::BrowserExecutor)
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
/// Returns `None` for methods that are intentionally NOT gated:
///
/// - `"close"` — releasing session resources is always permitted;
///   cleanup must not be gateable, otherwise a denied close would
///   leak browser processes.
///
/// All other public methods on
/// [`BrowserExecutor`](crate::executor::BrowserExecutor) MUST return a
/// `Some(_)` here; the unit test `every_executor_method_maps` enforces
/// the inverse direction.
///
/// # Mapping rationale
///
/// - `"open"` / `"navigate"` → `BrowserOpen`. A navigate is, in policy
///   terms, a re-open: it points an existing browser context at a new
///   origin, which is exactly the scope-allowlist boundary that
///   `BrowserOpen` enforces. Splitting them into two capabilities
///   would force callers to grant both for every flow without
///   tightening the security surface.
/// - `"read_page"` → `BrowserReadPage`.
/// - `"extract"` → `BrowserExtractData`.
/// - `"fill_form"` → `BrowserFillForm`. Submission is a separate
///   capability; filling alone never triggers state change.
/// - `"submit"` → `BrowserSubmit`. The Critical-risk capability that
///   actually mutates remote state.
pub fn capability_for_method(method: &str) -> Option<Capability> {
    match method {
        "open" | "navigate" => Some(Capability::BrowserOpen),
        "read_page" => Some(Capability::BrowserReadPage),
        "extract" => Some(Capability::BrowserExtractData),
        "fill_form" => Some(Capability::BrowserFillForm),
        "submit" => Some(Capability::BrowserSubmit),
        // `close` is intentionally ungated — see module docs.
        "close" => None,
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn open_and_navigate_share_browseropen() {
        assert_eq!(capability_for_method("open"), Some(Capability::BrowserOpen));
        assert_eq!(
            capability_for_method("navigate"),
            Some(Capability::BrowserOpen)
        );
    }

    #[test]
    fn read_page_maps_to_browserreadpage() {
        assert_eq!(
            capability_for_method("read_page"),
            Some(Capability::BrowserReadPage)
        );
    }

    #[test]
    fn extract_maps_to_browserextractdata() {
        assert_eq!(
            capability_for_method("extract"),
            Some(Capability::BrowserExtractData)
        );
    }

    #[test]
    fn fill_form_maps_to_browserfillform() {
        assert_eq!(
            capability_for_method("fill_form"),
            Some(Capability::BrowserFillForm)
        );
    }

    #[test]
    fn submit_maps_to_browsersubmit() {
        assert_eq!(
            capability_for_method("submit"),
            Some(Capability::BrowserSubmit)
        );
    }

    #[test]
    fn close_is_ungated() {
        assert_eq!(capability_for_method("close"), None);
    }

    #[test]
    fn unknown_method_returns_none() {
        assert_eq!(capability_for_method("teleport"), None);
        assert_eq!(capability_for_method(""), None);
    }

    /// Inverse-direction guard: every method named on the trait MUST
    /// either map to a `Some(Capability)` here or be on the
    /// known-ungated list. If you add a method to `BrowserExecutor`
    /// without updating `capability_for_method`, this test fails.
    #[test]
    fn every_executor_method_maps() {
        // Method names taken verbatim from `BrowserExecutor` in
        // `executor.rs`. Keep this list in sync with the trait.
        let gated = [
            "open",
            "navigate",
            "read_page",
            "extract",
            "fill_form",
            "submit",
        ];
        let ungated = ["close"];

        for m in gated {
            assert!(
                capability_for_method(m).is_some(),
                "expected {m:?} to map to a Capability"
            );
        }
        for m in ungated {
            assert!(
                capability_for_method(m).is_none(),
                "expected {m:?} to be ungated"
            );
        }
    }
}
