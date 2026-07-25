"""Module 08 tests — verify memory meets done criteria."""

import gzip
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_store_and_retrieve(self):
        """Store a turn then retrieve it with a related query."""
        with patch("src.memory.store.embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 768
            from src.memory.store import search_memory, store_conversation_turn

            doc_id = await store_conversation_turn("user", "The user prefers dark mode", time.time())
            assert doc_id is not None
            results = await search_memory("dark mode preference")
            assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_empty_collection_returns_empty(self):
        with patch("src.memory.store.embed_text", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.0] * 768
            from src.memory.store import search_memory

            results = await search_memory("nothing here yet")
            assert isinstance(results, list)


# ── Tier Manager Tests ──────────────────────────────────────────


class TestImportanceScoring:
    def test_recent_item_scores_higher(self):
        from src.memory.tier_manager import calculate_importance

        recent = {"metadata": {"timestamp": time.time()}, "access_count": 0}
        old = {"metadata": {"timestamp": time.time() - 86400 * 30}, "access_count": 0}
        assert calculate_importance(recent) > calculate_importance(old)

    def test_explicit_flag_boosts_score(self):
        from src.memory.tier_manager import calculate_importance

        normal = {"metadata": {"timestamp": time.time()}, "access_count": 0}
        flagged = {"metadata": {"timestamp": time.time(), "explicit_flag": True}, "access_count": 0}
        assert calculate_importance(flagged) > calculate_importance(normal)

    def test_frequent_access_boosts_score(self):
        from src.memory.tier_manager import calculate_importance

        low_access = {"metadata": {"timestamp": time.time()}, "access_count": 1}
        high_access = {"metadata": {"timestamp": time.time()}, "access_count": 50}
        assert calculate_importance(high_access) > calculate_importance(low_access)

    def test_personal_category_weighs_more(self):
        from src.memory.tier_manager import calculate_importance

        personal = {"metadata": {"timestamp": time.time(), "category": "personal.preferences"}, "access_count": 0}
        casual = {"metadata": {"timestamp": time.time(), "category": "casual"}, "access_count": 0}
        assert calculate_importance(personal) > calculate_importance(casual)

    def test_score_clamped_0_to_1(self):
        from src.memory.tier_manager import calculate_importance

        extreme = {
            "metadata": {
                "timestamp": time.time(),
                "explicit_flag": True,
                "emotional_weight": 1.0,
                "category": "personal",
            },
            "access_count": 1000,
        }
        score = calculate_importance(extreme)
        assert 0.0 <= score <= 1.0


class TestMemoryTier:
    def test_put_and_get(self):
        from src.memory.tier_manager import MemoryTier

        tier = MemoryTier("test", max_size_mb=10)
        tier.put("item1", {"content": "hello", "metadata": {"timestamp": time.time()}})
        result = tier.get("item1")
        assert result is not None
        assert result["content"] == "hello"

    def test_get_updates_access_count(self):
        from src.memory.tier_manager import MemoryTier

        tier = MemoryTier("test", max_size_mb=10)
        tier.put("item1", {"content": "hello", "access_count": 0, "metadata": {}})
        tier.get("item1")
        item = tier.get("item1")
        assert item["access_count"] == 2

    def test_eviction_when_full(self):
        from src.memory.tier_manager import MemoryTier

        # Very small tier — 0.0001 MB ≈ 100 bytes, forces eviction on 2nd put
        tier = MemoryTier("test", max_size_mb=0.0001)
        tier.put("item1", {"content": "a" * 200, "metadata": {"timestamp": time.time() - 86400 * 30}})
        assert tier.count == 1
        # This should evict item1 because tier is over capacity
        evicted = tier.put("item2", {"content": "b" * 200, "metadata": {"timestamp": time.time()}})
        assert len(evicted) >= 1
        assert evicted[0][0] == "item1"

    def test_search_with_predicate(self):
        from src.memory.tier_manager import MemoryTier

        tier = MemoryTier("test", max_size_mb=10)
        tier.put("item1", {"content": "dark mode preference", "metadata": {}})
        tier.put("item2", {"content": "meeting notes", "metadata": {}})
        results = tier.search(lambda item: "dark" in item.get("content", ""))
        assert len(results) == 1
        assert "dark" in results[0]["content"]

    def test_remove(self):
        from src.memory.tier_manager import MemoryTier

        tier = MemoryTier("test", max_size_mb=10)
        tier.put("item1", {"content": "hello", "metadata": {}})
        removed = tier.remove("item1")
        assert removed is not None
        assert tier.get("item1") is None


class TestArchiveTier:
    def test_store_and_search(self, tmp_path):
        from src.memory.tier_manager import ArchiveTier

        archive = ArchiveTier(str(tmp_path / "archive"))
        archive.store("item1", {"content": "The user prefers dark mode", "metadata": {"timestamp": time.time()}})
        results = archive.search("dark mode")
        assert len(results) == 1
        assert "dark mode" in results[0]["content"]

    def test_archive_creates_month_folders(self, tmp_path):
        from src.memory.tier_manager import ArchiveTier

        archive = ArchiveTier(str(tmp_path / "archive"))
        archive.store("item1", {"content": "test", "metadata": {"timestamp": time.time()}})
        month_files = archive.get_month_files()
        assert len(month_files) == 1

    def test_archive_gzip_format(self, tmp_path):
        from src.memory.tier_manager import ArchiveTier

        archive = ArchiveTier(str(tmp_path / "archive"))
        archive.store("item1", {"content": "test data", "metadata": {"timestamp": time.time()}})
        month_files = archive.get_month_files()
        assert month_files[0].suffix == ".gz"
        # Verify it's valid gzip
        with gzip.open(month_files[0], "rt") as f:
            line = f.readline()
            record = json.loads(line)
            assert record["content"] == "test data"

    def test_search_no_match_returns_empty(self, tmp_path):
        from src.memory.tier_manager import ArchiveTier

        archive = ArchiveTier(str(tmp_path / "archive"))
        archive.store("item1", {"content": "hello world", "metadata": {"timestamp": time.time()}})
        results = archive.search("quantum physics")
        assert len(results) == 0


class TestTierManager:
    def test_store_high_importance_goes_to_tier1(self):
        with patch("src.memory.tier_manager.get_yaml_config") as mock_config:
            mock_config.return_value = {
                "memory": {"vram_cache_mb": 512, "ram_cache_mb": 5120, "archive_path": "./data/long_term"}
            }
            from src.memory.tier_manager import MemoryTierManager

            mgr = MemoryTierManager()
            mgr.tier3 = MagicMock()  # Mock archive to avoid I: drive writes
            # Explicit flag = high importance
            mgr.store(
                "fact1",
                {
                    "content": "Important fact",
                    "metadata": {"timestamp": time.time(), "explicit_flag": True, "category": "personal"},
                    "access_count": 10,
                },
            )
            assert mgr.tier1.get("fact1") is not None

    def test_store_low_importance_goes_to_tier2(self):
        with patch("src.memory.tier_manager.get_yaml_config") as mock_config:
            mock_config.return_value = {
                "memory": {"vram_cache_mb": 512, "ram_cache_mb": 5120, "archive_path": "./data/long_term"}
            }
            from src.memory.tier_manager import MemoryTierManager

            mgr = MemoryTierManager()
            mgr.tier3 = MagicMock()
            # Old item with no flags = low importance
            mgr.store(
                "old1",
                {
                    "content": "Old casual fact",
                    "metadata": {"timestamp": time.time() - 86400 * 60},
                    "access_count": 0,
                },
            )
            assert mgr.tier2.get("old1") is not None

    def test_retrieve_promotes_from_tier2(self):
        with patch("src.memory.tier_manager.get_yaml_config") as mock_config:
            mock_config.return_value = {
                "memory": {"vram_cache_mb": 512, "ram_cache_mb": 5120, "archive_path": "./data/long_term"}
            }
            from src.memory.tier_manager import MemoryTierManager

            mgr = MemoryTierManager()
            mgr.tier3 = MagicMock()
            # Manually place item in tier2
            mgr.tier2.put(
                "item1",
                {
                    "content": "test",
                    "metadata": {"timestamp": time.time(), "explicit_flag": True, "category": "personal"},
                    "access_count": 20,
                },
            )
            result = mgr.retrieve("item1")
            assert result is not None
            # Should be promoted to tier1 (high importance)
            assert mgr.tier1.get("item1") is not None

    def test_soft_delete(self):
        with patch("src.memory.tier_manager.get_yaml_config") as mock_config:
            mock_config.return_value = {
                "memory": {"vram_cache_mb": 512, "ram_cache_mb": 5120, "archive_path": "./data/long_term"}
            }
            from src.memory.tier_manager import MemoryTierManager

            mgr = MemoryTierManager()
            mgr.tier3 = MagicMock()
            mgr.tier1.put("item1", {"content": "secret", "metadata": {}})
            result = mgr.soft_delete("item1")
            assert result is True
            assert mgr.tier1.get("item1") is None
            # Verify archived with deleted flag
            mgr.tier3.store.assert_called()

    def test_get_stats(self):
        with patch("src.memory.tier_manager.get_yaml_config") as mock_config:
            mock_config.return_value = {
                "memory": {"vram_cache_mb": 512, "ram_cache_mb": 5120, "archive_path": "./data/long_term"}
            }
            from src.memory.tier_manager import MemoryTierManager

            mgr = MemoryTierManager()
            stats = mgr.get_stats()
            assert stats["tier1"]["name"] == "VRAM"
            assert stats["tier2"]["name"] == "RAM"
            assert "archive_path" in stats["tier3"]

    def test_search_with_category_filter(self):
        with patch("src.memory.tier_manager.get_yaml_config") as mock_config:
            mock_config.return_value = {
                "memory": {"vram_cache_mb": 512, "ram_cache_mb": 5120, "archive_path": "./data/long_term"}
            }
            from src.memory.tier_manager import MemoryTierManager

            mgr = MemoryTierManager()
            mgr.tier3 = MagicMock()
            mgr.tier1.put("pref1", {"content": "dark mode", "metadata": {"category": "personal.preferences"}})
            mgr.tier1.put("work1", {"content": "dark repo", "metadata": {"category": "work.projects"}})
            results = mgr.search("dark", category="personal")
            assert len(results) == 1
            assert results[0]["metadata"]["category"] == "personal.preferences"


# ── Fact Extractor Tests ────────────────────────────────────────


class TestFactExtractor:
    def test_detect_explicit_remember(self):
        from src.memory.fact_extractor import detect_explicit_memory

        is_explicit, text = detect_explicit_memory("remember that I hate mushrooms")
        assert is_explicit is True
        assert "hate mushrooms" in text

    def test_detect_dont_forget(self):
        from src.memory.fact_extractor import detect_explicit_memory

        is_explicit, text = detect_explicit_memory("don't forget my appointment Friday")
        assert is_explicit is True
        assert "appointment" in text

    def test_non_explicit_not_detected(self):
        from src.memory.fact_extractor import detect_explicit_memory

        is_explicit, _ = detect_explicit_memory("what's the weather like?")
        assert is_explicit is False

    def test_add_turn_returns_immediate_facts(self):
        from src.memory.fact_extractor import FactExtractor

        extractor = FactExtractor(batch_interval=10)
        facts = extractor.add_turn("user", "remember that I prefer sushi", time.time())
        assert len(facts) == 1
        assert facts[0]["metadata"]["explicit_flag"] is True
        assert facts[0]["metadata"]["importance"] == 1.0

    def test_batch_extraction_triggers_after_n_turns(self):
        from src.memory.fact_extractor import FactExtractor

        extractor = FactExtractor(batch_interval=3)
        for i in range(3):
            extractor.add_turn("user", f"message {i}", time.time())
        assert extractor.should_batch_extract() is True

    def test_parse_extraction_result(self):
        from src.memory.fact_extractor import FactExtractor

        extractor = FactExtractor()
        llm_response = """Here are the facts:
        [
            {"content": "The user prefers dark mode", "subject": "User", "category": "personal.preferences", "confidence": 0.9},
            {"content": "The user works on Aether project", "subject": "User", "category": "work.projects", "confidence": 0.8}
        ]"""
        facts = extractor.parse_extraction_result(llm_response)
        assert len(facts) == 2
        assert facts[0]["content"] == "The user prefers dark mode"
        assert facts[0]["metadata"]["confidence"] == 0.9

    def test_parse_invalid_json_returns_empty(self):
        from src.memory.fact_extractor import FactExtractor

        extractor = FactExtractor()
        facts = extractor.parse_extraction_result("not json at all")
        assert facts == []

    def test_clear_buffer(self):
        from src.memory.fact_extractor import FactExtractor

        extractor = FactExtractor(batch_interval=3)
        for i in range(5):
            extractor.add_turn("user", f"msg {i}", time.time())
        extractor.clear_buffer()
        assert extractor.should_batch_extract() is False


# ── Categorizer Tests ───────────────────────────────────────────


class TestCategorizer:
    def test_classify_preference(self):
        from src.memory.categorizer import classify_fast

        assert classify_fast("I prefer dark mode for everything") == "personal.preferences"

    def test_classify_health(self):
        from src.memory.categorizer import classify_fast

        assert classify_fast("I'm allergic to peanuts") == "personal.health"

    def test_classify_work_project(self):
        from src.memory.categorizer import classify_fast

        assert classify_fast("The Aether project needs a new feature") == "work.projects"

    def test_classify_technical_code(self):
        from src.memory.categorizer import classify_fast

        assert classify_fast("There's a bug in the Python function") == "technical.code"

    def test_classify_family(self):
        from src.memory.categorizer import classify_fast

        assert classify_fast("My sister is visiting this weekend") == "social.family"

    def test_classify_unknown_returns_general(self):
        from src.memory.categorizer import classify_fast

        assert classify_fast("the sky is particularly vivid today") == "general"

    @pytest.mark.asyncio
    async def test_classify_with_fast_match(self):
        from src.memory.categorizer import classify

        result = await classify("I love sushi as my favorite food", use_llm_fallback=False)
        assert result == "personal.preferences"

    @pytest.mark.asyncio
    async def test_classify_general_without_llm(self):
        from src.memory.categorizer import classify

        result = await classify("random abstract thought", use_llm_fallback=False)
        assert result == "general"


# ── Hybrid Search Tests ─────────────────────────────────────────


class TestBM25Rerank:
    def test_bm25_scores_relevant_higher(self):
        from src.memory.store import _bm25_rerank

        docs = ["I prefer dark mode in all apps", "The weather is sunny today", "Dark chocolate is my favorite"]
        ranked = _bm25_rerank("dark mode", docs)
        # First result should be the dark mode doc
        assert ranked[0][0] == 0

    def test_bm25_empty_docs(self):
        from src.memory.store import _bm25_rerank

        ranked = _bm25_rerank("test query", [])
        assert ranked == []


class TestFuseScores:
    def test_fusion_combines_scores(self):
        from src.memory.store import _fuse_scores

        dense_results = [
            {"content": "doc1", "relevance": 0.9},
            {"content": "doc2", "relevance": 0.5},
        ]
        bm25_ranked = [(1, 1.0), (0, 0.5)]  # doc2 wins BM25
        fused = _fuse_scores(dense_results, bm25_ranked)
        # Both scores contribute — results should be sorted by fused score
        assert len(fused) == 2
        assert all(0 <= r["relevance"] <= 1.0 for r in fused)

    def test_fusion_empty_results(self):
        from src.memory.store import _fuse_scores

        fused = _fuse_scores([], [])
        assert fused == []


# ── Pattern Learner Tests ───────────────────────────────────────


class TestPatternLearner:
    def test_analyze_wake_time(self):
        from datetime import datetime

        from src.memory.pattern_learner import analyze_activity_patterns

        # Use explicit datetimes to avoid timezone issues
        day1_8am = datetime(2026, 3, 1, 8, 0).timestamp()
        day1_10am = datetime(2026, 3, 1, 10, 0).timestamp()
        day2_830am = datetime(2026, 3, 2, 8, 30).timestamp()
        day3_730am = datetime(2026, 3, 3, 7, 30).timestamp()
        turns = [
            {"role": "user", "content": "good morning", "timestamp": day1_8am},
            {"role": "user", "content": "hello again", "timestamp": day1_10am},
            {"role": "user", "content": "good morning", "timestamp": day2_830am},
            {"role": "user", "content": "good morning", "timestamp": day3_730am},
        ]
        patterns = analyze_activity_patterns(turns)
        assert "typical_wake_hour" in patterns
        assert 7.0 <= patterns["typical_wake_hour"] <= 9.0

    def test_analyze_peak_hours(self):
        from datetime import datetime

        from src.memory.pattern_learner import analyze_activity_patterns

        turns = []
        # 10 messages at 2pm on March 1
        for i in range(10):
            ts = datetime(2026, 3, 1, 14, i).timestamp()
            turns.append({"role": "user", "content": f"msg {i}", "timestamp": ts})
        # 3 messages at 9am
        for i in range(3):
            ts = datetime(2026, 3, 1, 9, i).timestamp()
            turns.append({"role": "user", "content": f"morning {i}", "timestamp": ts})
        patterns = analyze_activity_patterns(turns)
        assert "peak_activity_hours" in patterns
        assert 14 in patterns["peak_activity_hours"]

    def test_analyze_empty_turns(self):
        from src.memory.pattern_learner import analyze_activity_patterns

        patterns = analyze_activity_patterns([])
        assert patterns == {}

    def test_format_patterns_as_facts(self):
        from src.memory.pattern_learner import format_patterns_as_facts

        patterns = {
            "typical_wake_hour": 8.5,
            "peak_activity_hours": [14, 20, 9],
            "prefers_brief": True,
            "avg_message_length": 35,
        }
        facts = format_patterns_as_facts(patterns)
        assert len(facts) >= 2
        assert any("8:30" in f["content"] for f in facts)
        assert all(f["metadata"]["source"] == "pattern_analysis" for f in facts)
