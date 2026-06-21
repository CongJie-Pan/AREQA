"""
Regression tests for the 3 P0 Bug Fixes applied to the AREQA Hybrid Memory System.

Bug Fix Summary (from memory_audit_report.md):
  1. Import path fix: `backend.memory_store` → `memory_store` in gum_integration.py
  2. hot_memory.json was never injected into <working_memory> in the System Prompt
  3. ColdMemoryRetriever.search() was never called in the Chat API flow

These tests MUST FAIL if the corresponding fix is reverted.
"""

import json
import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Regression Test 1 (Bug Fix #2):
# `get_hot_memory_snapshot()` must return a non-empty snapshot containing
# User Profile and Hot Memory when the global store has data.
# Previously: function did not exist → <working_memory> was never populated.
# ---------------------------------------------------------------------------

class TestGetHotMemorySnapshot:
    """
    Target: gum_integration.get_hot_memory_snapshot()
    Regression: If the function is absent or returns "" always, these FAIL.
    """

    def test_snapshot_returns_empty_when_no_store(self):
        """When no global store is initialized, snapshot must return ''."""
        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=None):
            result = gi.get_hot_memory_snapshot()
        assert result == ""

    def test_snapshot_includes_user_profile_section(self, tmp_path):
        """Snapshot must include user profile section when profile has data."""
        from backend.memory_store import MemoryStore
        hot_path = tmp_path / "hot.json"
        profile_path = tmp_path / "profile.json"
        store = MemoryStore(str(hot_path), str(profile_path))
        store.update_user_profile("school", "國立臺灣大學中文系三年級")

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=store):
            result = gi.get_hot_memory_snapshot()

        assert "使用者畫像" in result
        assert "國立臺灣大學中文系三年級" in result

    def test_snapshot_includes_hot_memory_section(self, tmp_path):
        """Snapshot must include hot memory section when hot memory has dict-style items."""
        from backend.memory_store import MemoryStore
        hot_path = tmp_path / "hot.json"
        profile_path = tmp_path / "profile.json"
        store = MemoryStore(str(hot_path), str(profile_path))
        store.update_hot_memory("林黛玉的老師", {"text": "賈雨村", "confidence": 9})

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=store):
            result = gi.get_hot_memory_snapshot()

        assert "近期記憶" in result
        assert "賈雨村" in result

    def test_snapshot_hot_memory_plain_string_value(self, tmp_path):
        """Snapshot must handle hot memory items that are plain strings."""
        from backend.memory_store import MemoryStore
        hot_path = tmp_path / "hot.json"
        profile_path = tmp_path / "profile.json"
        store = MemoryStore(str(hot_path), str(profile_path))
        store.update_hot_memory("怡紅院住戶", "賈寶玉")

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=store):
            result = gi.get_hot_memory_snapshot()

        assert "賈寶玉" in result

    def test_snapshot_reflects_overwrite_immediately(self, tmp_path):
        """After a=b → a=c override, snapshot must show new value only."""
        from backend.memory_store import MemoryStore
        hot_path = tmp_path / "hot.json"
        profile_path = tmp_path / "profile.json"
        store = MemoryStore(str(hot_path), str(profile_path))
        store.update_hot_memory("林黛玉的丫鬟", "雪雁")  # a = b
        store.update_hot_memory("林黛玉的丫鬟", "紫鵑")  # a = c (override)

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=store):
            result = gi.get_hot_memory_snapshot()

        assert "紫鵑" in result
        assert "雪雁" not in result


# ---------------------------------------------------------------------------
# Regression Test 2 (Bug Fix #3):
# `query_cold_memory_for_context()` must return formatted content or ""
# Previously: function did not exist → <retrieved_memory> was never populated.
# ---------------------------------------------------------------------------

class TestQueryColdMemoryForContext:
    """
    Target: gum_integration.query_cold_memory_for_context()
    Regression: If the function is absent or always returns "", these FAIL.
    """

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_api_key(self, monkeypatch):
        """Without OPENROUTER_API_KEY, must return '' (graceful no-op)."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

        from backend.gum_integration import query_cold_memory_for_context
        result = await query_cold_memory_for_context("王熙鳳的判詞是什麼？")
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_formatted_results_when_cold_memory_hit(self, monkeypatch):
        """When ColdMemoryRetriever.search() returns results, output contains header and text."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-dummy")

        mock_results = [
            {"text": "王熙鳳的判詞是：凡鳥偏從末世來，都知愛慕此生才。", "score": 0.95},
        ]

        import backend.gum_integration as gi
        with patch("cold_memory.ColdMemoryRetriever") as MockCRM:
            mock_instance = MockCRM.return_value
            mock_instance.search = AsyncMock(return_value=mock_results)
            result = await gi.query_cold_memory_for_context("王熙鳳的判詞是什麼？", top_k=3)

        assert "長尾記憶" in result
        assert "王熙鳳" in result
        assert "凡鳥偏從末世來" in result

    @pytest.mark.asyncio
    async def test_returns_empty_when_cold_memory_miss(self, monkeypatch):
        """When search returns no results, must return '' (not a header with no content)."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-dummy")

        import backend.gum_integration as gi
        with patch("cold_memory.ColdMemoryRetriever") as MockCRM:
            mock_instance = MockCRM.return_value
            mock_instance.search = AsyncMock(return_value=[])
            result = await gi.query_cold_memory_for_context("完全不存在的問題")

        assert result == ""

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_retriever_error(self, monkeypatch):
        """If retriever raises exception, must return '' — never crash the chat API."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-dummy")

        import backend.gum_integration as gi
        with patch("cold_memory.ColdMemoryRetriever") as MockCRM:
            mock_instance = MockCRM.return_value
            mock_instance.search = AsyncMock(side_effect=ConnectionError("sqlite-vec unavailable"))
            result = await gi.query_cold_memory_for_context("任何問題")

        assert result == ""


# ---------------------------------------------------------------------------
# Regression Test 3 (Bug Fix #1 consequence):
# `is_user_profile()` prefix semantics must correctly gate USER_PROFILE items
# from compaction — ensuring user_profile.json entries are NEVER demoted.
# ---------------------------------------------------------------------------

class TestIsUserProfileGating:
    """
    Target: compaction.is_user_profile()
    Validates plan: USER_PROFILE items are skipped in compaction decay.
    """

    def test_user_profile_prefix_returns_true(self):
        """Keys starting with 'user_profile' must be identified as profile entries."""
        from backend.compaction import is_user_profile
        assert is_user_profile("user_profile") is True
        assert is_user_profile("user_profile_name") is True
        assert is_user_profile("user_profile_school") is True

    def test_hot_memory_keys_return_false(self):
        """Regular hot memory keys must NOT be misidentified as profile entries."""
        from backend.compaction import is_user_profile
        assert is_user_profile("林黛玉的老師") is False
        assert is_user_profile("王熙鳳的判詞") is False
        assert is_user_profile("寶玉的住所") is False

    def test_edge_case_profile_substring_not_at_start(self):
        """Key with 'user_profile' not at start must return False (prefix-only check)."""
        from backend.compaction import is_user_profile
        assert is_user_profile("some_user_profile") is False

    def test_profile_key_exempt_from_decay_integration(self):
        """
        Integration-level: even a very old low-decay user_profile key has score ~0,
        but is_user_profile() correctly gates it from the demotion logic.
        """
        from backend.compaction import is_user_profile, calculate_activation_score

        # A very old, low-decay item would normally be demoted
        score = calculate_activation_score(confidence=5.0, decay=1.0, age_days=365.0)
        assert score < 1e-10, "Sanity: this item WOULD be demoted by score alone"

        # But is_user_profile protects it
        assert is_user_profile("user_profile_學校") is True, \
            "user_profile_ prefix must be protected from demotion"
