"""Leaving a tutor profile mid-conversation tells the model its rules ended, once."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.conversation import profile_history
from services.conversation.context import ConversationContextService
from services.conversation.tutor_profile import render_tutor_profile_leave_note
from services.teaching.engine import TeachingMaterials, TeachingRequest, render_system_prompt


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.ttls[key] = ex

    async def expire(self, key, seconds):
        self.ttls[key] = seconds


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError("down")


def test_leave_note_only_when_leaving_a_profile_with_rules():
    note = render_tutor_profile_leave_note("english", "general")
    assert "English Tutor" in note and "仍然有效" in note
    assert render_tutor_profile_leave_note("general", "english") == ""
    assert render_tutor_profile_leave_note("english", "english") == ""
    assert render_tutor_profile_leave_note(None, "general") == ""


@pytest.mark.asyncio
async def test_swap_returns_previous_profile_per_learner_and_conversation(monkeypatch, caplog):
    redis = FakeRedis()
    monkeypatch.setattr(profile_history, "get_redis", lambda: redis)

    assert await profile_history.swap_previous_profile("u1", "c1", "english") is None
    assert await profile_history.swap_previous_profile("u1", "c1", "english") == "english"
    assert await profile_history.swap_previous_profile("u2", "c1", "general") is None
    caplog.set_level("INFO")
    assert await profile_history.swap_previous_profile("u1", "c1", "general") == "english"
    assert "from=english to=general" in caplog.text
    assert set(redis.ttls.values()) == {profile_history.PROFILE_TTL_SECONDS}


@pytest.mark.asyncio
async def test_swap_fails_soft_without_redis(monkeypatch, caplog):
    monkeypatch.setattr(profile_history, "get_redis", lambda: BrokenRedis())
    assert await profile_history.swap_previous_profile("u1", "c1", "general") is None
    assert "tutor_profile.history_unavailable reason=ConnectionError" in caplog.text
    assert await profile_history.swap_previous_profile("u1", "", "general") is None


class _Store:
    async def get_hot_memory(self, user_id):
        return {}


async def _build(service, tutor_profile, **kwargs):
    memory_policy = SimpleNamespace(evaluate=lambda _: SimpleNamespace(allow_long_term_query=False, reason_code="X"))
    service.memory_policy = memory_policy
    result = await service.build_conversation_context(
        user_id="u1", conversation_id="c1", messages=[{"role": "user", "content": "幫我寫一段結論"}],
        use_rag=False, use_web_search=False, force_think=False, context_results_obj=None,
        last_user_msg="幫我寫一段結論", context_prompt="", client=None,
        snapshot_loader=AsyncMock(return_value=""), store=_Store(), chat_avatar_key="chat_avatar:c1",
        tutor_profile=tutor_profile, **kwargs,
    )
    return result.messages[0]["content"]


@pytest.mark.asyncio
async def test_switch_from_english_adds_note_for_one_turn_only(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(profile_history, "get_redis", lambda: redis)
    service = ConversationContextService(None, AsyncMock(), profile_history=profile_history.swap_previous_profile)

    assert "已切換" not in await _build(service, "english")
    switched = await _build(service, "general")
    assert "【Tutor Profile 已切換】" in switched
    assert switched == render_system_prompt(
        TeachingRequest(last_user_msg="幫我寫一段結論", previous_tutor_profile="english"), TeachingMaterials())
    assert "已切換" not in await _build(service, "general")


@pytest.mark.asyncio
async def test_isolated_context_and_unwired_service_skip_profile_history():
    swap = AsyncMock(return_value="english")
    service = ConversationContextService(None, AsyncMock(), profile_history=swap)
    assert "已切換" not in await _build(service, "general", isolated_context=True)
    swap.assert_not_awaited()
    assert "已切換" not in await _build(ConversationContextService(None, AsyncMock()), "general")
