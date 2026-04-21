//! Small per-provider TTL cache for vision model lists.
//!
//! `list_vision_models` hits the daemon on every call, which is fine
//! on local Ollama but expensive on a remote llama-server. The cache
//! sits in front of the adapter's `list_models` result and hands out
//! the last-known list when it's still fresh, forcing a refetch when
//! the entry ages out. A manual refresh command invalidates an entry
//! on demand.
//!
//! Pure: the cache takes `Instant` values from the caller so tests
//! can drive the clock deterministically.

use std::collections::HashMap;
use std::env;
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// Default cache lifetime. 60s is long enough to absorb the burst of
/// calls that happens when the user opens the camera/screen panel and
/// the VisionBadge + ModelListSection both render, but short enough
/// that a new model pulled via `ollama pull` shows up quickly.
pub const DEFAULT_TTL: Duration = Duration::from_secs(60);

/// Hard floor on operator-supplied TTLs. Anything below this would
/// thrash the daemon enough that the cache becomes a net negative.
pub const TTL_FLOOR_SECS: u64 = 5;

/// Hard ceiling on operator-supplied TTLs. One hour is well past any
/// reasonable freshness budget; rejecting anything higher protects
/// against typo'd values like 60000 (meant ms, not s).
pub const TTL_CEILING_SECS: u64 = 3_600;

/// Env var read by [`ModelListCache::from_env`] to override the default
/// TTL. Documented as an advanced operator knob — there's no UI for it.
pub const TTL_ENV_VAR: &str = "AETHER_VISION_MODEL_TTL_SECS";

/// Where the effective TTL came from. Surfaced in the boot log line
/// so operators can tell at a glance whether the cache is running on
/// the default value, an env override, or a fallback after an invalid
/// env value. Pure data; exposed for tests.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TtlSource {
    /// No `AETHER_VISION_MODEL_TTL_SECS` set — using `DEFAULT_TTL`.
    Default,
    /// `AETHER_VISION_MODEL_TTL_SECS` parsed cleanly and is being used.
    EnvOverride,
    /// `AETHER_VISION_MODEL_TTL_SECS` was set but invalid; fell back
    /// to `DEFAULT_TTL` and logged a WARN.
    DefaultAfterInvalidEnv,
}

impl TtlSource {
    /// Short, log-friendly label for the variant.
    pub fn label(self) -> &'static str {
        match self {
            TtlSource::Default => "default",
            TtlSource::EnvOverride => "env override",
            TtlSource::DefaultAfterInvalidEnv => "default after invalid env",
        }
    }
}

/// Resolve the effective TTL from the environment without constructing
/// a cache. Pure helper exposed for unit tests so the source-resolution
/// rules can be locked without sniffing log output.
pub fn resolve_ttl_from_env() -> (Duration, TtlSource) {
    match env::var(TTL_ENV_VAR) {
        Ok(raw) => match parse_ttl_secs(&raw) {
            Some(ttl) => (ttl, TtlSource::EnvOverride),
            None => (DEFAULT_TTL, TtlSource::DefaultAfterInvalidEnv),
        },
        Err(_) => (DEFAULT_TTL, TtlSource::Default),
    }
}

/// Pure parser for the TTL env var value. Returns `Some(Duration)` when
/// the input parses as a `u64` of seconds within
/// `[TTL_FLOOR_SECS, TTL_CEILING_SECS]`. Returns `None` for missing,
/// non-numeric, or out-of-range values — caller falls back to
/// [`DEFAULT_TTL`] in that case.
pub fn parse_ttl_secs(raw: &str) -> Option<Duration> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return None;
    }
    let secs: u64 = trimmed.parse().ok()?;
    if !(TTL_FLOOR_SECS..=TTL_CEILING_SECS).contains(&secs) {
        return None;
    }
    Some(Duration::from_secs(secs))
}

#[derive(Debug, Clone)]
struct CacheEntry {
    stamped_at: Instant,
    models: Vec<String>,
}

/// Per-provider TTL cache. Thread-safe via an internal `Mutex`; entries
/// are cheap `Vec<String>` clones so contention is not a concern.
pub struct ModelListCache {
    ttl: Duration,
    entries: Mutex<HashMap<String, CacheEntry>>,
}

impl ModelListCache {
    /// Build a cache with the default 60-second TTL.
    pub fn new() -> Self {
        Self::with_ttl(DEFAULT_TTL)
    }

    /// Build a cache with a custom TTL. Mostly for tests.
    pub fn with_ttl(ttl: Duration) -> Self {
        Self {
            ttl,
            entries: Mutex::new(HashMap::new()),
        }
    }

    /// Build a cache whose TTL is read from [`TTL_ENV_VAR`]. Falls
    /// back to [`DEFAULT_TTL`] when the var is unset, empty,
    /// non-numeric, or out of range. Always emits an INFO log line
    /// stating the effective TTL plus its source so operators can
    /// confirm at boot which value the cache is using; emits a
    /// WARN line first when an invalid value forced a fallback.
    pub fn from_env() -> Self {
        let (ttl, source) = resolve_ttl_from_env();
        if matches!(source, TtlSource::DefaultAfterInvalidEnv) {
            // Be specific about what the operator passed so they can
            // fix it. The pure helper hides the raw value, so re-read
            // here purely for the warning message.
            let raw = env::var(TTL_ENV_VAR).unwrap_or_default();
            tracing::warn!(
                "{}={:?} is not in [{},{}] seconds; using default {}s",
                TTL_ENV_VAR,
                raw,
                TTL_FLOOR_SECS,
                TTL_CEILING_SECS,
                DEFAULT_TTL.as_secs()
            );
        }
        tracing::info!(
            "vision model-list cache TTL: {}s ({})",
            ttl.as_secs(),
            source.label()
        );
        Self::with_ttl(ttl)
    }

    /// Effective TTL of this cache. Used by tests + diagnostics.
    #[allow(dead_code)]
    pub fn ttl(&self) -> Duration {
        self.ttl
    }

    /// Fresh lookup. Returns the cached list when it's inside the TTL,
    /// `None` otherwise (caller refetches from the daemon).
    pub fn get(&self, provider_id: &str) -> Option<Vec<String>> {
        self.get_with_now(provider_id, Instant::now())
    }

    /// Same as [`get`] but with an explicit `now` — lets tests drive
    /// the clock without sleeping.
    pub fn get_with_now(&self, provider_id: &str, now: Instant) -> Option<Vec<String>> {
        let guard = self.entries.lock().ok()?;
        let entry = guard.get(provider_id)?;
        if now.duration_since(entry.stamped_at) < self.ttl {
            Some(entry.models.clone())
        } else {
            None
        }
    }

    /// Record a fresh list for `provider_id`. Overwrites any prior
    /// entry so a manual refresh replaces a stale list cleanly.
    pub fn put(&self, provider_id: &str, models: Vec<String>) {
        self.put_with_now(provider_id, models, Instant::now());
    }

    /// Same as [`put`] but with an explicit `now`.
    pub fn put_with_now(&self, provider_id: &str, models: Vec<String>, now: Instant) {
        let Ok(mut guard) = self.entries.lock() else {
            return;
        };
        guard.insert(
            provider_id.to_string(),
            CacheEntry {
                stamped_at: now,
                models,
            },
        );
    }

    /// Drop the cached entry for `provider_id`. The next lookup will
    /// force a refetch. Called on model swap so the user immediately
    /// sees their pick reflected in a subsequent list.
    pub fn invalidate(&self, provider_id: &str) {
        if let Ok(mut guard) = self.entries.lock() {
            guard.remove(provider_id);
        }
    }

    /// Wipe every cached entry. Used by the manual `refresh_vision_models`
    /// surface when the UI wants to guarantee a fresh fetch across
    /// every provider in the registry.
    pub fn clear(&self) {
        if let Ok(mut guard) = self.entries.lock() {
            guard.clear();
        }
    }
}

impl Default for ModelListCache {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn miss_on_empty_cache() {
        let c = ModelListCache::new();
        assert!(c.get("ollama-vision").is_none());
    }

    #[test]
    fn hit_within_ttl_returns_cached_list() {
        let c = ModelListCache::with_ttl(Duration::from_secs(10));
        let now = Instant::now();
        c.put_with_now("ollama-vision", vec!["llava".into()], now);
        let still_fresh = now + Duration::from_secs(5);
        assert_eq!(
            c.get_with_now("ollama-vision", still_fresh),
            Some(vec!["llava".into()])
        );
    }

    #[test]
    fn miss_after_ttl_expires() {
        let c = ModelListCache::with_ttl(Duration::from_secs(10));
        let now = Instant::now();
        c.put_with_now("ollama-vision", vec!["llava".into()], now);
        let stale = now + Duration::from_secs(20);
        assert!(c.get_with_now("ollama-vision", stale).is_none());
    }

    #[test]
    fn put_overwrites_prior_entry() {
        let c = ModelListCache::with_ttl(Duration::from_secs(10));
        let now = Instant::now();
        c.put_with_now("ollama-vision", vec!["old".into()], now);
        c.put_with_now(
            "ollama-vision",
            vec!["new-1".into(), "new-2".into()],
            now + Duration::from_secs(1),
        );
        assert_eq!(
            c.get_with_now("ollama-vision", now + Duration::from_secs(2)),
            Some(vec!["new-1".into(), "new-2".into()])
        );
    }

    #[test]
    fn invalidate_forces_next_lookup_to_miss() {
        let c = ModelListCache::with_ttl(Duration::from_secs(10));
        let now = Instant::now();
        c.put_with_now("ollama-vision", vec!["llava".into()], now);
        c.invalidate("ollama-vision");
        assert!(c
            .get_with_now("ollama-vision", now + Duration::from_secs(1))
            .is_none());
        // Other providers untouched.
        c.put_with_now("llamacpp-vision", vec!["minicpm".into()], now);
        assert_eq!(
            c.get_with_now("llamacpp-vision", now + Duration::from_secs(1)),
            Some(vec!["minicpm".into()])
        );
    }

    #[test]
    fn clear_empties_every_entry() {
        let c = ModelListCache::with_ttl(Duration::from_secs(10));
        let now = Instant::now();
        c.put_with_now("a", vec!["x".into()], now);
        c.put_with_now("b", vec!["y".into()], now);
        c.clear();
        assert!(c.get_with_now("a", now).is_none());
        assert!(c.get_with_now("b", now).is_none());
    }

    // ---------------------------------------------------------------
    // TTL env-override parsing.
    // ---------------------------------------------------------------

    #[test]
    fn parse_ttl_secs_accepts_in_range_values() {
        assert_eq!(parse_ttl_secs("5"), Some(Duration::from_secs(5)));
        assert_eq!(parse_ttl_secs("60"), Some(Duration::from_secs(60)));
        assert_eq!(parse_ttl_secs("3600"), Some(Duration::from_secs(3600)));
        // Whitespace tolerated.
        assert_eq!(parse_ttl_secs("  120  "), Some(Duration::from_secs(120)));
    }

    #[test]
    fn parse_ttl_secs_rejects_out_of_range() {
        // Below the floor: thrashes the daemon, useless cache.
        assert!(parse_ttl_secs("0").is_none());
        assert!(parse_ttl_secs("4").is_none());
        // Above the ceiling: typo guard (60000 was likely meant ms).
        assert!(parse_ttl_secs("3601").is_none());
        assert!(parse_ttl_secs("60000").is_none());
    }

    #[test]
    fn parse_ttl_secs_rejects_non_numeric_and_empty() {
        assert!(parse_ttl_secs("").is_none());
        assert!(parse_ttl_secs("   ").is_none());
        assert!(parse_ttl_secs("abc").is_none());
        assert!(parse_ttl_secs("60s").is_none());
        assert!(parse_ttl_secs("-1").is_none());
        assert!(parse_ttl_secs("1.5").is_none());
    }

    /// Env-set tests share process state, so they're serialised
    /// through this mutex (same pattern as ollama provider tests).
    static ENV_MUTEX: std::sync::Mutex<()> = std::sync::Mutex::new(());

    fn unset_ttl_env() {
        env::remove_var(TTL_ENV_VAR);
    }

    #[test]
    fn from_env_uses_default_when_var_unset() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_ttl_env();
        let c = ModelListCache::from_env();
        assert_eq!(c.ttl(), DEFAULT_TTL);
    }

    #[test]
    fn from_env_picks_up_valid_override() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_ttl_env();
        env::set_var(TTL_ENV_VAR, "30");
        let c = ModelListCache::from_env();
        assert_eq!(c.ttl(), Duration::from_secs(30));
        unset_ttl_env();
    }

    #[test]
    fn resolve_ttl_from_env_reports_default_when_unset() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_ttl_env();
        let (ttl, source) = resolve_ttl_from_env();
        assert_eq!(ttl, DEFAULT_TTL);
        assert_eq!(source, TtlSource::Default);
    }

    #[test]
    fn resolve_ttl_from_env_reports_env_override() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_ttl_env();
        env::set_var(TTL_ENV_VAR, "45");
        let (ttl, source) = resolve_ttl_from_env();
        assert_eq!(ttl, Duration::from_secs(45));
        assert_eq!(source, TtlSource::EnvOverride);
        unset_ttl_env();
    }

    #[test]
    fn resolve_ttl_from_env_reports_invalid_env_fallback() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_ttl_env();
        env::set_var(TTL_ENV_VAR, "garbage");
        let (ttl, source) = resolve_ttl_from_env();
        assert_eq!(ttl, DEFAULT_TTL);
        assert_eq!(source, TtlSource::DefaultAfterInvalidEnv);
        env::set_var(TTL_ENV_VAR, "0");
        let (ttl2, source2) = resolve_ttl_from_env();
        assert_eq!(ttl2, DEFAULT_TTL);
        assert_eq!(source2, TtlSource::DefaultAfterInvalidEnv);
        unset_ttl_env();
    }

    #[test]
    fn ttl_source_label_is_stable() {
        assert_eq!(TtlSource::Default.label(), "default");
        assert_eq!(TtlSource::EnvOverride.label(), "env override");
        assert_eq!(
            TtlSource::DefaultAfterInvalidEnv.label(),
            "default after invalid env"
        );
    }

    #[test]
    fn from_env_falls_back_to_default_on_invalid_value() {
        let _g = ENV_MUTEX.lock().unwrap_or_else(|p| p.into_inner());
        unset_ttl_env();
        env::set_var(TTL_ENV_VAR, "garbage");
        let c = ModelListCache::from_env();
        assert_eq!(c.ttl(), DEFAULT_TTL);
        env::set_var(TTL_ENV_VAR, "0");
        let c2 = ModelListCache::from_env();
        assert_eq!(c2.ttl(), DEFAULT_TTL);
        unset_ttl_env();
    }
}
