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

@pytest.fixture
def memory_store():
    from backend.memory_store import MemoryStore
    from unittest.mock import AsyncMock, patch, MagicMock
    redis = AsyncMock()
    _store = {}
    async def fake_get(key): return _store.get(key)
    async def fake_set(key, val): _store[key] = val
    def fake_set_sync(key, val): _store[key] = val
    redis.get = AsyncMock(side_effect=fake_get)
    redis.set = AsyncMock(side_effect=fake_set)
    pipe_mock = AsyncMock()
    pipe_mock.get = AsyncMock(side_effect=fake_get)
    pipe_mock.set = MagicMock(side_effect=fake_set_sync)
    pipe_mock.watch = AsyncMock()
    pipe_mock.multi = MagicMock()
    pipe_mock.execute = AsyncMock()
    class PipelineContext:
        def __init__(self, **kwargs): self.pipe = pipe_mock
        async def __aenter__(self): return self.pipe
        async def __aexit__(self, exc_type, exc_val, exc_tb): pass
    redis.pipeline = PipelineContext
    redis._store = _store
    with patch("backend.memory_store.get_redis", return_value=redis):
        yield MemoryStore()

class TestGetHotMemorySnapshot:
    """
    Target: gum_integration.get_hot_memory_snapshot()
    Regression: If the function is absent or returns "" always, these FAIL.
    """

    @pytest.mark.asyncio
    async def test_snapshot_returns_empty_when_no_store(self):
        """When no global store is initialized, snapshot must return ''."""
        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=None):
            result = await gi.get_hot_memory_snapshot("default_user")
        assert result == ""

    @pytest.mark.asyncio
    async def test_snapshot_includes_user_profile_section(self, memory_store):
        """Snapshot must include user profile section when profile has data."""
        await memory_store.update_user_profile("default_user", "school", "國立臺灣大學中文系三年級")

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot("default_user")

        assert "使用者畫像" in result
        assert "國立臺灣大學中文系三年級" in result

    @pytest.mark.asyncio
    async def test_snapshot_includes_working_memory_section(self, memory_store):
        """Snapshot must include prompt-safe working memory items."""
        await memory_store.append_learning_observation("default_user", "林黛玉的老師是賈雨村", confidence=9)

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot("default_user")

        assert "工作記憶" in result
        assert "賈雨村" in result

    @pytest.mark.asyncio
    async def test_snapshot_ignores_hot_memory_plain_string_value(self, memory_store):
        """Arbitrary hot-memory strings must not leak into prompt-visible working memory."""
        await memory_store.update_hot_memory("default_user", "怡紅院住戶", "賈寶玉")

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot("default_user")

        assert "賈寶玉" not in result

    @pytest.mark.asyncio
    async def test_snapshot_reflects_overwrite_immediately(self, memory_store):
        """After a=b → a=c override, snapshot must show new value only."""
        await memory_store.update_working_memory("default_user", {"current_focus": "雪雁"})
        await memory_store.update_working_memory("default_user", {"current_focus": "紫鵑"})

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot("default_user")

        assert "紫鵑" in result
        assert "雪雁" not in result

    @pytest.mark.asyncio
    async def test_snapshot_excludes_cross_conversation_current_focus_when_requested(self, memory_store):
        """A new conversation greeting must not inherit the previous conversation's task focus."""
        await memory_store.update_working_memory(
            "default_user",
            {
                "session_summary": "使用者正在用 Codex 更新 AREQA 專案的 README.md",
                "current_focus": "我正在用 Codex 更新 AREQA 專案的 README.md",
                "current_focus_conversation_id": "conv-readme",
                "recent_learning_points": [{"text": "README 測試殘留"}],
            },
        )

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot(
                "default_user",
                conversation_id="conv-greeting",
                include_cross_conversation_focus=False,
            )

        assert "README.md" not in result
        assert "Codex" not in result
        assert "README 測試殘留" not in result

    @pytest.mark.asyncio
    async def test_snapshot_includes_same_conversation_current_focus(self, memory_store):
        """The active conversation should still retain its own recent task focus."""
        await memory_store.update_working_memory(
            "default_user",
            {
                "session_summary": "React useEffect dependency array 卡住",
                "session_summary_conversation_id": "conv-react",
                "current_focus": "React useEffect dependency array 卡住",
                "current_focus_conversation_id": "conv-react",
                "recent_learning_points": [{
                    "text": "cleanup function 何時執行",
                    "conversation_id": "conv-react",
                }],
            },
        )

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot(
                "default_user",
                conversation_id="conv-react",
                include_cross_conversation_focus=False,
            )

        assert "React useEffect" in result
        assert "dependency array" in result
        assert "cleanup function" in result

    @pytest.mark.asyncio
    async def test_snapshot_excludes_legacy_summary_after_focus_moves_to_new_conversation(
        self, memory_store
    ):
        await memory_store.update_working_memory(
            "default_user",
            {
                "session_summary": "家庭壓力與跑步回憶",
                "current_focus": "血壓 118/77 正常嗎？",
                "current_focus_conversation_id": "conv-health",
            },
        )

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot(
                "default_user",
                conversation_id="conv-health",
                include_cross_conversation_focus=False,
            )

        assert "血壓 118/77" in result
        assert "家庭壓力" not in result

    @pytest.mark.asyncio
    async def test_snapshot_filters_individual_points_from_other_conversations(self, memory_store):
        await memory_store.update_working_memory(
            "default_user",
            {
                "current_focus": "血壓 118/77 正常嗎？",
                "current_focus_conversation_id": "conv-health",
                "recent_learning_points": [
                    {"text": "家庭壓力與跑步", "conversation_id": "conv-diary"},
                    {"text": "血壓量測", "conversation_id": "conv-health"},
                ],
            },
        )

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot(
                "default_user",
                conversation_id="conv-health",
                include_cross_conversation_focus=False,
            )

        assert "血壓量測" in result
        assert "家庭壓力" not in result

    @pytest.mark.asyncio
    async def test_snapshot_excludes_ui_behavior_signals(self, memory_store):
        """UI telemetry belongs to behavior_signals and must stay out of the LLM prompt."""
        await memory_store.append_behavior_signal("default_user", "scroll", {"duration_seconds": 3.0})
        await memory_store.update_hot_memory("default_user", "obs_legacy_scroll", "[User Action] Type: scroll, Context: {}")

        import backend.gum_integration as gi
        with patch("memory_store.get_global_store", return_value=memory_store):
            result = await gi.get_hot_memory_snapshot("default_user")

        assert "scroll" not in result
        assert "User Action" not in result

    @pytest.mark.asyncio
    async def test_cold_candidates_are_deduplicated_by_hash(self, memory_store):
        """Reflection-first cold candidates should keep source metadata and dedupe repeats."""
        first = await memory_store.append_cold_candidate(
            "default_user",
            "學生昨天文言文卡很久，但願意反覆重讀。",
            category="session_reflection",
            source="reflection",
            reason="test",
        )
        second = await memory_store.append_cold_candidate(
            "default_user",
            "學生昨天文言文卡很久，但願意反覆重讀。",
            category="session_reflection",
            source="reflection",
            reason="test",
        )

        candidates = await memory_store.get_cold_candidates("default_user")

        assert first["hash"] == second["hash"]
        assert len(candidates) == 1
        assert candidates[0]["seen_count"] == 2
        assert candidates[0]["source"] == "reflection"


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
        result = await query_cold_memory_for_context("default_user", "王熙鳳的判詞是什麼？")
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_formatted_results_when_cold_memory_hit(self, monkeypatch):
        """When ColdMemoryRetriever.search() returns results, output contains header and text."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-dummy")

        mock_results = [
            {"text": "王熙鳳的判詞是：凡鳥偏從末世來，都知愛慕此生才。", "score": 0.95},
        ]

        import backend.gum_integration as gi
        gi.gum_instance = MagicMock()
        with patch("cold_memory.ColdMemoryRetriever") as MockCRM, \
               patch("memory_store.get_global_store", return_value=None), \
             patch("backend.gum_integration.generate_zpd_query_via_llm", new_callable=AsyncMock, return_value="王熙鳳的判詞是什麼？"):
            mock_instance = MockCRM.return_value
            mock_instance.search = AsyncMock(return_value=mock_results)
            result = await gi.query_cold_memory_for_context("default_user", "王熙鳳的判詞是什麼？", top_k=3)

        assert "長尾記憶" in result
        assert "王熙鳳" in result
        assert "凡鳥偏從末世來" in result
        gi.gum_instance = None

    @pytest.mark.asyncio
    async def test_returns_empty_when_cold_memory_miss(self, monkeypatch):
        """Returns empty string when no search results found."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-dummy")

        import backend.gum_integration as gi
        gi.gum_instance = MagicMock()
        with patch("cold_memory.ColdMemoryRetriever") as MockCRM, \
               patch("memory_store.get_global_store", return_value=None), \
             patch("backend.gum_integration.generate_zpd_query_via_llm", new_callable=AsyncMock, return_value="林黛玉"):
            mock_instance = MockCRM.return_value
            mock_instance.search = AsyncMock(return_value=[])
            result = await gi.query_cold_memory_for_context("default_user", "林黛玉是誰", top_k=3)

        assert result == ""
        gi.gum_instance = None

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_retriever_error(self, monkeypatch):
        """If ColdMemoryRetriever throws an exception, system degrades gracefully."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-dummy")

        import backend.gum_integration as gi
        gi.gum_instance = MagicMock()
        with patch("cold_memory.ColdMemoryRetriever") as MockCRM, \
               patch("memory_store.get_global_store", return_value=None), \
             patch("backend.gum_integration.generate_zpd_query_via_llm", new_callable=AsyncMock, return_value="Error query"):
            mock_instance = MockCRM.return_value
            mock_instance.search = AsyncMock(side_effect=Exception("Database locked"))
            result = await gi.query_cold_memory_for_context("default_user", "引發錯誤的查詢")

        assert result == ""
        gi.gum_instance = None


class TestColdMemoryTransactionIsolation:
    @pytest.mark.asyncio
    async def test_vector_failure_does_not_abort_bm25_search(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-dummy")

        import backend.cold_memory as cm

        class FakeCursor:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

            def fetchone(self):
                return self._rows[0] if self._rows else None

        class FakeSession:
            def __init__(self, name):
                self.name = name
                self.aborted = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def begin(self):
                return self

            async def execute(self, statement, params=None):
                sql = str(statement)
                if "vec_memory" in sql:
                    self.aborted = True
                    raise Exception("relation \"vec_memory\" does not exist")
                if self.aborted:
                    raise Exception("current transaction is aborted")
                if "ts_rank" in sql:
                    return FakeCursor([(42, 0.9)])
                if "SELECT text FROM propositions" in sql:
                    return FakeCursor([("BM25 survives vector failure",)])
                return FakeCursor([])

        class FakeSessionFactory:
            def __init__(self):
                self.calls = 0

            def __call__(self, engine):
                self.calls += 1
                return FakeSession(f"session-{self.calls}")

        fake_session_factory = FakeSessionFactory()

        async def fake_embedding(self, text_str):
            return [0.1, 0.2, 0.3]

        with patch.object(cm, "AsyncSession", fake_session_factory), \
             patch.object(cm.ColdMemoryRetriever, "get_embedding", fake_embedding):
            retriever = cm.ColdMemoryRetriever("/tmp/gum.db", "dummy-key")
            results = await retriever.search("村上春樹短篇小說的象徵手法與魔幻寫實風格解析", user_id="u1", top_k=3)

        assert results == [{"id": 42, "text": "BM25 survives vector failure", "rrf_score": pytest.approx(results[0]["rrf_score"])}]


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
