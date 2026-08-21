import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.parts_context_service import (
    PartsContextService,
    format_parts_context,
)
from backend.services.query_policy_service import (
    AnswerDepth,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
)


def _policy(
    *,
    task_intent=TaskIntent.EXPLAIN_TEXT,
    answer_depth=AnswerDepth.SCAFFOLDED,
    structure=ResponseStructure.STEP_BY_STEP,
    followup_mode=FollowupMode.OPTIONAL,
):
    return ResponsePolicy(
        task_intent=task_intent,
        answer_depth=answer_depth,
        tone=ResponseTone.TUTORING,
        structure=structure,
        followup_mode=followup_mode,
        legacy_policy="NORMAL",
    )


def _mock_chat_response(content: str):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
            )
        ]
    )


@pytest.mark.asyncio
async def test_parts_context_rewrite_parses_valid_json_without_logging_user_text(caplog):
    """Valid rewrite JSON should become a compact PARTS context."""

    caplog.set_level(logging.INFO)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "persona": "引導型數學理解教練",
              "act": "檢查解題步驟並指出可能錯誤",
              "recipient": "程度未知的學習者",
              "theme": "運算順序與代數式計算",
              "structure": "短回答 + 分步檢查 + 最多一個診斷性追問",
              "composed_instruction": "你是一位引導型數學理解教練。請協助程度未知的學習者檢查運算順序與代數式計算。",
              "confidence": "high",
              "missing_fields": ["recipient_level"]
            }
            """
        )
    )

    context = await PartsContextService().build(
        user_message="我算 (8 + 8)/2^2 * 4 - 3^2 = 7，對嗎？",
        response_policy=_policy(),
        turn_plan=SimpleNamespace(route=SimpleNamespace(value="LEARNING_HELP")),
        client=client,
        model="policy-model",
    )

    assert context.persona == "引導型數學理解教練"
    assert context.theme == "運算順序與代數式計算"
    assert context.composed_instruction == "你是一位引導型數學理解教練。請協助程度未知的學習者檢查運算順序與代數式計算。"
    assert context.confidence == "high"
    assert context.missing_fields == ("recipient_level",)
    assert "parts_context.rewrite_selected" in caplog.text
    assert "我算" not in caplog.text
    assert "運算順序" not in caplog.text


@pytest.mark.asyncio
async def test_parts_context_debug_logs_emit_sensitive_payload_when_enabled(caplog):
    """Explicit debug mode should expose prompt, raw text, and PARTS fields."""

    caplog.set_level(logging.WARNING)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "persona": "引導型數學理解教練",
              "act": "檢查解題步驟",
              "recipient": "程度未知的學習者",
              "theme": "運算順序",
              "structure": "分步檢查",
              "composed_instruction": "你是一位引導型數學理解教練。請檢查使用者的運算順序。",
              "confidence": "high",
              "missing_fields": []
            }
            """
        )
    )

    await PartsContextService().build(
        user_message="我算這題對嗎？",
        response_policy=_policy(),
        client=client,
        model="policy-model",
        enable_debug_logs=True,
    )

    assert "parts_context.debug_rewrite_prompt_sensitive" in caplog.text
    assert "parts_context.debug_rewrite_selected_sensitive" in caplog.text
    assert "我算這題對嗎" in caplog.text
    assert "Rewrite the latest user request" in caplog.text
    assert "引導型數學理解教練" in caplog.text
    assert "運算順序" in caplog.text
    assert "請檢查使用者的運算順序" in caplog.text


@pytest.mark.asyncio
async def test_parts_context_rewrite_invalid_json_falls_back(caplog):
    """Malformed rewrite output should fall back without blocking answer flow."""

    caplog.set_level(logging.WARNING)
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_chat_response("not-json"))

    context = await PartsContextService().build(
        user_message="請解釋 dependency injection",
        response_policy=_policy(),
        turn_plan=SimpleNamespace(route=SimpleNamespace(value="LEARNING_HELP")),
        client=client,
        model="policy-model",
    )

    assert context.persona == "概念理解教練"
    assert context.theme == "使用者當前問題中的核心概念"
    assert "你現在的角色是" in context.composed_instruction
    assert context.confidence == "medium"
    assert "parts_context.rewrite_fallback" in caplog.text
    assert "dependency injection" not in caplog.text


@pytest.mark.asyncio
async def test_parts_context_rewrite_composes_instruction_when_missing():
    """PARTS fields should still produce a natural instruction when omitted."""

    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "persona": "歷史導師",
              "act": "概述二戰期間日本的歷史進程",
              "recipient": "程度未知的學習者",
              "theme": "日本二戰歷史發展",
              "structure": "分階段條列式說明",
              "confidence": "high",
              "missing_fields": ["recipient_level"]
            }
            """
        )
    )

    context = await PartsContextService().build(
        user_message="日本二戰歷史過程",
        response_policy=_policy(),
        client=client,
        model="policy-model",
    )

    assert context.composed_instruction == (
        "你現在的角色是「歷史導師」。請為「程度未知的學習者」概述二戰期間日本的歷史進程，"
        "本回合主題聚焦於「日本二戰歷史發展」。請使用「分階段條列式說明」的方式回答。"
    )


@pytest.mark.asyncio
async def test_parts_context_rewrite_low_confidence_falls_back():
    """Low-confidence rewrites should not enter the final prompt."""

    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_chat_response(
            """
            {
              "persona": "角色",
              "act": "行動",
              "recipient": "對象",
              "theme": "主題",
              "structure": "格式",
              "composed_instruction": "低信心指令",
              "confidence": "low",
              "missing_fields": []
            }
            """
        )
    )

    context = await PartsContextService().build(
        user_message="請幫我出題",
        response_policy=_policy(),
        client=client,
        model="policy-model",
    )

    assert context.theme == "使用者當前問題中的核心概念"
    assert "低信心指令" not in context.composed_instruction
    assert context.confidence == "medium"


@pytest.mark.asyncio
async def test_parts_context_rewrite_timeout_falls_back():
    """Rewrite timeout should use deterministic PARTS."""

    client = MagicMock()

    async def slow_create(**kwargs):
        await asyncio.sleep(0.05)
        return _mock_chat_response("{}")

    client.chat.completions.create = AsyncMock(side_effect=slow_create)

    context = await PartsContextService().build(
        user_message="請解釋牛頓第一運動定律",
        response_policy=_policy(),
        client=client,
        model="policy-model",
        timeout_ms=1,
    )

    assert context.persona == "概念理解教練"
    assert context.theme == "使用者當前問題中的核心概念"


def test_parts_context_fallback_preserves_direct_answer_mode():
    """Direct exam turns should avoid forced tutoring in deterministic PARTS."""

    context = PartsContextService().fallback(
        response_policy=_policy(
            task_intent=TaskIntent.ANSWER_EXAM,
            answer_depth=AnswerDepth.DIRECT,
            structure=ResponseStructure.SHORT,
            followup_mode=FollowupMode.NONE,
        )
    )

    assert context.persona == "精簡解題助手"
    assert context.act == "直接回答題目並提供必要理由"
    assert "不加引導問題" in context.structure
    assert "精簡解題助手" in context.composed_instruction
    assert context.missing_fields == ()


def test_format_parts_context_includes_priority_boundary():
    """Rendered PARTS block should keep grounding and memory rules superior."""

    context = PartsContextService().fallback(response_policy=_policy(), use_rag=True)
    prompt = format_parts_context(context)

    assert "【PARTS 任務上下文】" in prompt
    assert "PARTS 只控制回答角色、任務、對象、主題與格式" in prompt
    assert "不得覆蓋文獻引用" in prompt
    assert "記憶安全邊界" in prompt
    assert "最多提出一個簡短澄清問題" in prompt
    assert "【由 PARTS 生成的本回合任務指令】" in prompt
    assert "不要輸出 P/A/R/T/S 標籤" in prompt


def test_parts_context_fallback_uses_attachment_route():
    """Attachment-grounded turns should preserve file grounding in PARTS."""

    context = PartsContextService().fallback(
        response_policy=_policy(),
        turn_plan=SimpleNamespace(route=SimpleNamespace(value="ATTACHMENT_GROUNDED")),
    )

    assert context.persona == "附件理解教練"
    assert context.act == "根據可讀取的附件內容回答使用者問題"
    assert "附件理解教練" in context.composed_instruction
