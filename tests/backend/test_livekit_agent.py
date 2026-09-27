"""Regression tests for the AREQA LiveKit avatar worker."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import livekit_agent.agent as agent_module


class FakeAvatarStartError(Exception):
    status_code = 429


class FakeAgentSession:
    last_started_room_options = None
    last_instance = None

    def __init__(self, *, llm):
        self.llm = llm
        self.spoken = []
        self.reply_count = 0
        FakeAgentSession.last_instance = self

    async def start(self, *, room, agent, room_options):
        FakeAgentSession.last_started_room_options = room_options

    async def interrupt(self):
        return None

    def say(self, text, *, allow_interruptions):
        self.spoken.append(text)

    def generate_reply(self):
        self.reply_count += 1


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
    room = SimpleNamespace(name="areqa-live-test-room", handlers={})
    room.register_text_stream_handler = lambda topic, handler: room.handlers.update({topic: handler})
    return SimpleNamespace(
        room=room,
        job=SimpleNamespace(metadata='{"conversation_id": "conv_test"}'),
    )


def test_livekit_agent_instructions_use_task_adaptive_depth():
    instructions = agent_module._instructions("zh-TW")

    assert "Choose spoken learning mode from the learner's intent: REFERENCE, LEARN, or PRACTICE" in instructions
    assert "REFERENCE is for definitions" in instructions
    assert "PRACTICE is for homework" in instructions
    assert "does not by itself switch PRACTICE to REFERENCE" in instructions
    assert "Choose spoken depth within that mode: BRIEF, EXPLAIN, or DEEP" in instructions
    assert "BRIEF is for greetings" in instructions
    assert "DEEP is for detailed paper walkthroughs" in instructions
    assert "do not apply the one-to-three-sentence limit" in instructions
    assert "substantively answered" not in instructions
    assert "asks whether you remember something" in instructions
    assert "call get_areqa_context before answering" in instructions
    assert "Never say you cannot remember" in instructions
    assert "Choose response language by priority" in instructions
    assert "language the learner is speaking now" in instructions
    assert "Do not switch to English merely because the interface" in instructions


def test_livekit_agent_applies_dispatched_tutor_rules_without_changing_default():
    profile_prompt = " English Tutor speaking practice rule: use three English anchors."
    metadata = agent_module._dispatch_metadata(SimpleNamespace(
        job=SimpleNamespace(metadata=json.dumps({
            "tutor_profile": "english",
            "tutor_profile_prompt": profile_prompt.strip(),
        })),
    ))
    tutor = agent_module.AreqaLiveTutor(
        interface_language="zh-TW",
        recent_messages=[],
        memory_items=[],
        parts_context={},
        tutor_profile_prompt=metadata["tutor_profile_prompt"],
    )

    assert profile_prompt.strip() in tutor.instructions
    assert profile_prompt.strip() not in agent_module._instructions("zh-TW")
    assert agent_module._dispatch_metadata(SimpleNamespace(job=SimpleNamespace(metadata='{}')))["tutor_profile_prompt"] == ""


def test_livekit_agent_rejects_oversized_tutor_rules_instead_of_truncating():
    metadata = json.dumps({"tutor_profile": "english", "tutor_profile_prompt": "x" * 6001})

    with pytest.raises(ValueError, match="exceeds"):
        agent_module._dispatch_metadata(SimpleNamespace(job=SimpleNamespace(metadata=metadata)))


@pytest.mark.asyncio
async def test_livekit_agent_context_guidance_preserves_deep_explanations():
    tutor = agent_module.AreqaLiveTutor(
        interface_language="zh-TW",
        recent_messages=[],
        memory_items=[],
        parts_context={},
    )

    context = await tutor.get_areqa_context("paper_explanation")

    assert "preserve the learner-owned core step" in context["guidance"]
    assert "do not omit key ideas merely to be brief" in context["guidance"]
    assert "Use the current spoken language first" in context["guidance"]


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


@pytest.mark.asyncio
async def test_livekit_worker_reads_backend_answer_through_avatar_audio(monkeypatch):
    monkeypatch.setattr(agent_module, "ANAM_AVATAR_ID", "")
    monkeypatch.setattr(agent_module, "AgentSession", FakeAgentSession)
    monkeypatch.setattr(agent_module.openai, "realtime", SimpleNamespace(
        RealtimeModel=lambda **kwargs: {"kwargs": kwargs},
    ))
    monkeypatch.setattr(agent_module.room_io, "RoomOptions", FakeRoomOptions)
    ctx = fake_job_context()
    ctx.job.metadata = json.dumps({
        "conversation_id": "conv_test", "tutor_profile": "english", "participant_identity": "learner",
    })
    await agent_module.areqa_live_tutor(ctx)

    assert FakeAgentSession.last_instance.llm["kwargs"]["turn_detection"].create_response is False
    assert FakeAgentSession.last_instance.llm["kwargs"]["turn_detection"].type == "semantic_vad"
    assert FakeAgentSession.last_instance.llm["kwargs"]["turn_detection"].eagerness == "low"
    handler = ctx.room.handlers[agent_module.BACKEND_SPEECH_TOPIC]

    class Reader:
        async def read_all(self):
            return json.dumps({"action": "speak", "text": "Try the same idea once more."})

    task = handler(Reader(), "learner")
    await task
    assert FakeAgentSession.last_instance.spoken == ["Try the same idea once more."]

    await handler(Reader(), "another-participant")
    assert FakeAgentSession.last_instance.spoken == ["Try the same idea once more."]


@pytest.mark.asyncio
async def test_livekit_general_voice_uses_patient_turn_detection(monkeypatch):
    monkeypatch.setattr(agent_module, "ANAM_AVATAR_ID", "")
    monkeypatch.setattr(agent_module, "AgentSession", FakeAgentSession)
    monkeypatch.setattr(agent_module.openai, "realtime", SimpleNamespace(
        RealtimeModel=lambda **kwargs: {"kwargs": kwargs},
    ))
    monkeypatch.setattr(agent_module.room_io, "RoomOptions", FakeRoomOptions)

    await agent_module.areqa_live_tutor(fake_job_context())

    turn_detection = FakeAgentSession.last_instance.llm["kwargs"]["turn_detection"]
    assert turn_detection.type == "semantic_vad"
    assert turn_detection.eagerness == "low"
    assert turn_detection.create_response is True
    assert turn_detection.interrupt_response is True


@pytest.mark.asyncio
async def test_livekit_worker_adds_uploaded_file_context_before_reply(monkeypatch):
    monkeypatch.setattr(agent_module, "ANAM_AVATAR_ID", "")
    monkeypatch.setattr(agent_module, "AgentSession", FakeAgentSession)
    monkeypatch.setattr(agent_module.openai, "realtime", SimpleNamespace(
        RealtimeModel=lambda **kwargs: {"kwargs": kwargs},
    ))
    monkeypatch.setattr(agent_module.room_io, "RoomOptions", FakeRoomOptions)
    captured = []

    async def update_chat_ctx(self, chat_ctx):
        captured.append(chat_ctx.messages()[-1].text_content)

    monkeypatch.setattr(agent_module.AreqaLiveTutor, "update_chat_ctx", update_chat_ctx)
    ctx = fake_job_context()
    ctx.job.metadata = json.dumps({"participant_identity": "learner"})
    await agent_module.areqa_live_tutor(ctx)
    handler = ctx.room.handlers[agent_module.BACKEND_SPEECH_TOPIC]

    class Reader:
        def __init__(self, action="context"):
            self.action = action

        async def read_all(self):
            return json.dumps({
                "action": self.action,
                "text": "File: notes.txt. Cobalt is the answer." if self.action == "context" else "Please continue",
                "reply": True,
            })

    await handler(Reader(), "learner")
    await handler(Reader("user_text"), "learner")

    assert captured == ["File: notes.txt. Cobalt is the answer.", "Please continue"]
    assert FakeAgentSession.last_instance.reply_count == 2
