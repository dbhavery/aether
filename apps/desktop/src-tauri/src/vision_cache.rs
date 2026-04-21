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
use std::sync::Mutex;
use std::time::{Duration, Instant};

/// Default cache lifetime. 60s is long enough to absorb the burst of
/// calls that happens when the user opens the camera/screen panel and
/// the VisionBadge + ModelListSection both render, but short enough
/// that a new model pulled via `ollama pull` shows up quickly.
pub const DEFAULT_TTL: Duration = Duration::from_secs(60);

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
}
