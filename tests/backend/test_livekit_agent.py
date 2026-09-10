"""Regression tests for the AREQA LiveKit avatar worker."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import livekit_agent.agent as agent_module


class FakeAvatarStartError(Exception):
    status_code = 429


class FakeAgentSession:
    last_started_room_options = None

    def __init__(self, *, llm):
        self.llm = llm

    async def start(self, *, room, agent, room_options):
        FakeAgentSession.last_started_room_options = room_options


class FakeRoomOptions:
    def __init__(self, *, audio_output):
        self.audio_output = audio_output


class FailingAvatarSession:
    def __init__(self, *, persona_config):
        self.persona_config = persona_config

    async def start(self, session, *, room):
        raise FakeAvatarStartError("Concurrent session limit reached")


class JoiningAvatarSession:
    def __init__(self, *, persona_config):
        self.persona_config = persona_config

    async def start(self, session, *, room):
        return None

    async def wait_for_join(self):
        return None


def fake_job_context() -> SimpleNamespace:
    return SimpleNamespace(
        room=SimpleNamespace(name="areqa-live-test-room"),
        job=SimpleNamespace(metadata='{"conversation_id": "conv_test"}'),
    )


def test_livekit_agent_instructions_use_task_adaptive_depth():
    instructions = agent_module._instructions("zh-TW")

    assert "Choose spoken depth from the learner's intent: BRIEF, EXPLAIN, or DEEP" in instructions
    assert "BRIEF is for greetings" in instructions
    assert "DEEP is for detailed paper walkthroughs" in instructions
    assert "do not apply the one-to-three-sentence limit" in instructions
    assert "Do not ask a follow-up question until the learner's current request has been substantively answered" in instructions
    assert "asks whether you remember something" in instructions
    assert "call get_areqa_context before answering" in instructions
    assert "Never say you cannot remember" in instructions


@pytest.mark.asyncio
async def test_livekit_agent_context_guidance_preserves_deep_explanations():
    tutor = agent_module.AreqaLiveTutor(
        interface_language="zh-TW",
        recent_messages=[],
        memory_items=[],
        parts_context={},
    )

    context = await tutor.get_areqa_context("paper_explanation")

    assert "answer the requested content before asking a follow-up" in context["guidance"]
    assert "do not omit key ideas merely to be brief" in context["guidance"]


@pytest.mark.asyncio
async def test_livekit_agent_falls_back_to_voice_only_when_anam_start_fails(monkeypatch):
    monkeypatch.setattr(agent_module, "ANAM_AVATAR_ID", "avatar_test")
    monkeypatch.setattr(agent_module, "AgentSession", FakeAgentSession)
    monkeypatch.setattr(
        agent_module.openai,
        "realtime",
        SimpleNamespace(RealtimeModel=lambda **kwargs: {"kwargs": kwargs}),
    )
    monkeypatch.setattr(
        agent_module.anam,
        "PersonaConfig",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(agent_module.anam, "AvatarSession", FailingAvatarSession)
    monkeypatch.setattr(agent_module.room_io, "RoomOptions", FakeRoomOptions)

    await agent_module.areqa_live_tutor(fake_job_context())

    assert FakeAgentSession.last_started_room_options.audio_output is True


@pytest.mark.asyncio
async def test_livekit_agent_disables_direct_audio_when_anam_joins(monkeypatch):
    monkeypatch.setattr(agent_module, "ANAM_AVATAR_ID", "avatar_test")
    monkeypatch.setattr(agent_module, "AgentSession", FakeAgentSession)
    monkeypatch.setattr(
        agent_module.openai,
        "realtime",
        SimpleNamespace(RealtimeModel=lambda **kwargs: {"kwargs": kwargs}),
    )
    monkeypatch.setattr(
        agent_module.anam,
        "PersonaConfig",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(agent_module.anam, "AvatarSession", JoiningAvatarSession)
    monkeypatch.setattr(agent_module.room_io, "RoomOptions", FakeRoomOptions)

    await agent_module.areqa_live_tutor(fake_job_context())

    assert FakeAgentSession.last_started_room_options.audio_output is False
