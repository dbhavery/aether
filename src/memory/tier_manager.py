"""3-Tier Memory Manager — VRAM → RAM → I: drive archive.

Tier 1 (VRAM, 512MB): Most important/recent data, fast similarity search.
Tier 2 (RAM, 5GB): Broader cache, LRU eviction of oldest+least-important.
Tier 3 (I: drive): Full conversation archive, gzipped JSONL, never deleted.
"""

import contextlib
import gzip
import json
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.shared.config import get_yaml_config

# Memory item structure: {id, content, metadata, importance, last_accessed, access_count}


def calculate_importance(item: dict) -> float:
    """Multi-signal importance scoring. Returns 0.0-1.0.

    Signals:
    - Recency: newer = higher (exponential decay, half-life 7 days)
    - Frequency: access_count, log-scaled
    - Emotional weight: sentiment marker in metadata
    - Explicit flag: "remember this" → 1.0
    - Category weight: personal > factual > casual
    """
    score = 0.0

    # Recency (0-0.3): exponential decay with 7-day half-life
    stored_at = item.get("metadata", {}).get("timestamp", item.get("stored_at", 0))
    if stored_at:
        age_seconds = time.time() - stored_at
        age_days = age_seconds / 86400.0
        recency = 0.3 * (0.5 ** (age_days / 7.0))
        score += recency

    # Frequency (0-0.2): log-scaled access count
    access_count = item.get("access_count", 0)
    if access_count > 0:
        import math

        freq = 0.2 * min(1.0, math.log1p(access_count) / math.log1p(50))
        score += freq

    # Emotional weight (0-0.15): metadata flag
    metadata = item.get("metadata", {})
    raw_weight = metadata.get("emotional_weight")
    if raw_weight:
        with contextlib.suppress(ValueError, TypeError):
            score += 0.15 * min(1.0, float(raw_weight))

    # Explicit flag (0.35): "remember this" = max importance
    if metadata.get("explicit_flag"):
        score += 0.35

    # Category weight (0-0.1): personal > work > social > technical > casual
    category = metadata.get("category", "")
    category_weights = {
        "personal": 0.10,
        "work": 0.08,
        "social": 0.07,
        "technical": 0.05,
        "casual": 0.02,
    }
    for prefix, weight in category_weights.items():
        if category.startswith(prefix):
            score += weight
            break

    return min(1.0, max(0.0, score))


class MemoryTier:
    """Single tier: an ordered dict with size-based eviction."""

    def __init__(self, name: str, max_size_mb: float):
        self.name = name
        self.max_size_mb = max_size_mb
        self._items: OrderedDict[str, dict] = OrderedDict()
        self._current_size_bytes: int = 0

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def size_mb(self) -> float:
        return self._current_size_bytes / (1024 * 1024)

    @property
    def is_full(self) -> bool:
        return self.size_mb >= self.max_size_mb

    def _estimate_item_size(self, item: dict) -> int:
        """Rough size estimate of a memory item in bytes."""
        return sys.getsizeof(json.dumps(item, default=str))

    def get(self, item_id: str) -> dict | None:
        """Get item by ID. Updates access time and moves to end (most recent)."""
        item = self._items.get(item_id)
        if item is not None:
            old_size = self._estimate_item_size(item)
            item["last_accessed"] = time.time()
            item["access_count"] = item.get("access_count", 0) + 1
            new_size = self._estimate_item_size(item)
            self._current_size_bytes += new_size - old_size
            self._items.move_to_end(item_id)
        return item

    def put(self, item_id: str, item: dict) -> list[tuple[str, dict]]:
        """Insert item. Returns list of (id, item) evicted to make room."""
        evicted = []
        item_size = self._estimate_item_size(item)

        # Remove existing entry if updating
        if item_id in self._items:
            old = self._items.pop(item_id)
            self._current_size_bytes -= self._estimate_item_size(old)

        # Evict least important items until there's room
        while self.is_full and self._items:
            evict_id, evict_item = self._find_least_important()
            self._items.pop(evict_id)
            self._current_size_bytes -= self._estimate_item_size(evict_item)
            evicted.append((evict_id, evict_item))

        self._items[item_id] = item
        self._current_size_bytes += item_size
        return evicted

    def remove(self, item_id: str) -> dict | None:
        """Remove item by ID. Returns the item if found."""
        item = self._items.pop(item_id, None)
        if item is not None:
            self._current_size_bytes -= self._estimate_item_size(item)
        return item

    def _find_least_important(self) -> tuple[str, dict]:
        """Find the item with lowest importance score."""
        min_id = None
        min_score = float("inf")
        for item_id, item in self._items.items():
            score = calculate_importance(item)
            if score < min_score:
                min_score = score
                min_id = item_id
        return min_id, self._items[min_id]

    def get_all(self) -> list[tuple[str, dict]]:
        """Return all items as (id, item) pairs."""
        return list(self._items.items())

    def search(self, predicate: callable) -> list[dict]:
        """Filter items by predicate function."""
        return [item for item in self._items.values() if predicate(item)]


class ArchiveTier:
    """Tier 3: I: drive archive. Gzipped JSONL. Never deleted."""

    def __init__(self, archive_path: str):
        self.archive_path = Path(archive_path)
        self.archive_path.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    def _get_month_file(self, timestamp: float | None = None) -> Path:
        """Get archive file path for the given timestamp's month."""
        dt = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
        month_dir = self.archive_path / dt.strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        return month_dir / "archive.jsonl.gz"

    def store(self, item_id: str, item: dict) -> None:
        """Append item to gzipped JSONL archive for current month (thread-safe)."""
        timestamp = item.get("metadata", {}).get("timestamp", time.time())
        archive_file = self._get_month_file(timestamp)
        record = {"id": item_id, **item, "archived_at": time.time()}
        line = json.dumps(record, default=str) + "\n"
        with self._write_lock, gzip.open(archive_file, "at", encoding="utf-8") as f:
            f.write(line)

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Simple text search across archive files. Slow — use only for deep queries."""
        results = []
        query_lower = query.lower()
        for month_dir in sorted(self.archive_path.iterdir(), reverse=True):
            if not month_dir.is_dir():
                continue
            archive_file = month_dir / "archive.jsonl.gz"
            if not archive_file.exists():
                continue
            try:
                with gzip.open(archive_file, "rt", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                        except (json.JSONDecodeError, ValueError):
                            continue  # Skip malformed lines, don't abort file
                        content = record.get("content", "")
                        if query_lower in content.lower():
                            results.append(record)
                            if len(results) >= max_results:
                                return results
            except Exception as e:
                logger.warning(f"Memory: archive search error in {archive_file}: {e}")
        return results

    def get_month_files(self) -> list[Path]:
        """List all month archive files."""
        files = []
        for month_dir in sorted(self.archive_path.iterdir()):
            if month_dir.is_dir():
                archive_file = month_dir / "archive.jsonl.gz"
                if archive_file.exists():
                    files.append(archive_file)
        return files


class MemoryTierManager:
    """Orchestrates data across 3 tiers with importance-based eviction."""

    def __init__(self):
        config = get_yaml_config()
        memory_config = config.get("memory", {})

        vram_mb = memory_config.get("vram_cache_mb", 512)
        ram_mb = memory_config.get("ram_cache_mb", 5120)
        archive_path = memory_config.get("archive_path", "./data/long_term")

        self.tier1 = MemoryTier("VRAM", vram_mb)
        self.tier2 = MemoryTier("RAM", ram_mb)
        self.tier3 = ArchiveTier(archive_path)

        logger.info(f"Memory: TierManager initialized — T1={vram_mb}MB, T2={ram_mb}MB, T3={archive_path}")

    def store(self, item_id: str, item: dict) -> None:
        """Store item into the appropriate tier based on importance.

        High importance → Tier 1 (VRAM). Evicted items cascade to Tier 2 → Tier 3.
        """
        # Shallow copy to avoid mutating the caller's dict
        item = {**item}
        importance = calculate_importance(item)
        item["importance"] = importance
        item.setdefault("last_accessed", time.time())
        item.setdefault("access_count", 0)

        if importance >= 0.5:
            # High importance → Tier 1
            evicted = self.tier1.put(item_id, item)
            for evict_id, evict_item in evicted:
                self._cascade_to_tier2(evict_id, evict_item)
        else:
            # Lower importance → Tier 2
            evicted = self.tier2.put(item_id, item)
            for evict_id, evict_item in evicted:
                self.tier3.store(evict_id, evict_item)

        # Always archive to Tier 3 for permanent storage
        self.tier3.store(item_id, item)

    def _cascade_to_tier2(self, item_id: str, item: dict) -> None:
        """Move item from Tier 1 to Tier 2, cascading evictions to Tier 3."""
        evicted = self.tier2.put(item_id, item)
        for evict_id, evict_item in evicted:
            self.tier3.store(evict_id, evict_item)

    def retrieve(self, item_id: str) -> dict | None:
        """Get item from fastest available tier. Promotes to higher tiers on access."""
        # Try Tier 1 first (fastest)
        item = self.tier1.get(item_id)
        if item is not None:
            return item

        # Try Tier 2
        item = self.tier2.get(item_id)
        if item is not None:
            # Promote to Tier 1 if importance warrants it
            importance = calculate_importance(item)
            if importance >= 0.5:
                self.tier2.remove(item_id)
                evicted = self.tier1.put(item_id, item)
                for evict_id, evict_item in evicted:
                    self._cascade_to_tier2(evict_id, evict_item)
            return item

        return None

    def search(self, query: str, deep: bool = False, category: str | None = None) -> list[dict]:
        """Search across tiers. Simple queries → Tier 1+2. Deep queries → all 3 tiers.

        Args:
            query: Search text
            deep: If True, also search Tier 3 (I: drive archive)
            category: Optional hierarchical category filter (e.g., "personal.preferences")
        """
        results = []
        query_lower = query.lower()

        def matches(item: dict) -> bool:
            """Check if item matches query and optional category."""
            content_match = query_lower in item.get("content", "").lower()
            if not content_match:
                return False
            if category:
                item_category = item.get("metadata", {}).get("category", "")
                return item_category.startswith(category)
            return True

        # Search Tier 1
        results.extend(self.tier1.search(matches))

        # Search Tier 2
        results.extend(self.tier2.search(matches))

        # Search Tier 3 (deep queries only)
        if deep:
            archive_results = self.tier3.search(query)
            for record in archive_results:
                if category:
                    item_category = record.get("metadata", {}).get("category", "")
                    if not item_category.startswith(category):
                        continue
                results.append(record)

        # Deduplicate by ID
        seen = set()
        unique = []
        for item in results:
            item_id = item.get("id", id(item))
            if item_id not in seen:
                seen.add(item_id)
                unique.append(item)

        # Sort by importance descending
        unique.sort(key=lambda x: x.get("importance", 0), reverse=True)
        return unique

    def soft_delete(self, item_id: str) -> bool:
        """Soft delete — mark as deleted (hidden from search) but retain in archive."""
        item = self.tier1.remove(item_id)
        if item is None:
            item = self.tier2.remove(item_id)
        if item is not None:
            item.setdefault("metadata", {})["deleted"] = True
            item["metadata"]["deleted_at"] = time.time()
            self.tier3.store(item_id, item)
            logger.info(f"Memory: soft-deleted '{item_id}'")
            return True
        return False

    def get_stats(self) -> dict:
        """Return tier statistics."""
        return {
            "tier1": {
                "name": self.tier1.name,
                "count": self.tier1.count,
                "size_mb": round(self.tier1.size_mb, 2),
                "max_mb": self.tier1.max_size_mb,
            },
            "tier2": {
                "name": self.tier2.name,
                "count": self.tier2.count,
                "size_mb": round(self.tier2.size_mb, 2),
                "max_mb": self.tier2.max_size_mb,
            },
            "tier3": {
                "archive_path": str(self.tier3.archive_path),
                "month_files": len(self.tier3.get_month_files()),
            },
        }


# Module-level singleton
_manager: MemoryTierManager | None = None


def get_tier_manager() -> MemoryTierManager:
    """Get or create the singleton MemoryTierManager."""
    global _manager
    if _manager is None:
        _manager = MemoryTierManager()
    return _manager
