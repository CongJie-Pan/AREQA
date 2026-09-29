import pytest
import json
import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.services.conversation_context_service import ConversationContext
from backend.services.conversation_stream_service import ConversationStreamService, ImageRequestMarkerFilter
from backend.services.orchestration_service import OrchestrationService
from backend.services.paper_visual_planner_service import PaperVisualPlanItem
from backend.services.parts_context_service import PartsContext
from backend.services.visual_answer_service import ImageBlock
from backend.services.query_policy_service import (
    AnswerDepth,
    AttachmentReason,
    AttachmentTask,
    FollowupMode,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
    VisualReason,
    VisualSupport,
)
from unittest.mock import patch


def test_attaches_multimodal_parts_only_to_latest_user_turn():
    messages = [
        {"role": "user", "content": "先前問題"},
        {"role": "assistant", "content": "先前回答"},
        {"role": "user", "content": "請分析附件"},
    ]
    attachments = [{"type": "file", "file": {"filename": "lesson.pdf", "file_data": "data:application/pdf;base64,AA=="}}]

    result = OrchestrationService._attach_to_latest_user_message(messages, attachments)

    assert result[0]["content"] == "先前問題"
    assert result[-1]["content"] == [
        {"type": "text", "text": "請分析附件"},
        attachments[0],
    ]


def test_attachment_grounding_instruction_forbids_metadata_guessing():
    messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "請分析附件"},
    ]

    result = OrchestrationService._add_attachment_grounding_instruction(messages)

    assert "只能根據實際可讀取的附件內容回答" in result[0]["content"]
    assert "不得根據檔名" in result[0]["content"]
    assert "解析失敗" in result[0]["content"]


def test_missing_visual_attachment_instruction_blocks_image_guessing():
    """Text-only image references should not invite visual hallucination."""

    messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "請說明這兩張圖是什麼意思"},
    ]

    result, applied = OrchestrationService._add_missing_visual_attachment_instruction(
        messages,
        "請說明這兩張圖是什麼意思",
    )

    assert applied is True
    system_prompt = result[0]["content"]
    assert "後端沒有收到任何可讀取的圖片" in system_prompt
    assert "不得假裝看過圖片" in system_prompt
    assert "不得推測左圖、右圖" in system_prompt


def test_missing_visual_attachment_instruction_ignores_plain_text_questions():
    """Ordinary text-only turns should keep the prompt unchanged."""

    messages = [{"role": "system", "content": "base prompt"}]

    result, applied = OrchestrationService._add_missing_visual_attachment_instruction(
        messages,
        "請用資訊工程語言解釋中介與調節",
    )

    assert applied is False
    assert result[0]["content"] == "base prompt"


def test_paper_auto_explain_instruction_adds_default_paper_structure():
    """Automatic PDF paper overview should be appended as a system constraint."""

    messages = [
        {"role": "system", "content": "base prompt"},
        {"role": "user", "content": "這篇論文在講什麼"},
    ]

    result = OrchestrationService._add_paper_auto_explain_instruction(messages)

    system_prompt = result[0]["content"]
    assert "PDF 論文自動解說任務" in system_prompt
    assert "profile: AREQA_TEACHING_V1" in system_prompt
    assert "首段先貼合本回合學習模式" in system_prompt
    assert "研究動機與目的" in system_prompt
    assert "研究方法與模型架構" in system_prompt
    assert "實驗設計與資料集" in system_prompt
    assert "實驗結果與消融分析" in system_prompt
    assert "一般回答模式的白話教學感" in system_prompt
    assert "不要寫成正式審稿報告" in system_prompt
    assert "段落文字為主" in system_prompt
    assert "研究結論" in system_prompt
    assert "局限與可延伸方向" in system_prompt
    assert "不得根據檔名" in system_prompt


@pytest.mark.asyncio
async def test_attachment_visual_extraction_uses_paper_visual_planner_for_auto_explain():
    """Paper auto-explain visual extraction should honor planner-selected pages."""

    fitz = pytest.importorskip("fitz")
    document = fitz.open()
    document.new_page(width=320, height=220).insert_text(
        (32, 40),
        "Figure 1. Architecture overview",
        fontsize=12,
    )
    page_2 = document.new_page(width=320, height=220)
    page_2.insert_text((32, 40), "Results BLEU evaluation", fontsize=10)
    page_2.draw_rect(fitz.Rect(40, 70, 280, 150), color=(0, 0, 0), width=1)
    page_2.insert_text((42, 180), "Table 2. BLEU results", fontsize=12)
    pdf_bytes = document.tobytes()
    document.close()

    planned = (
        PaperVisualPlanItem(
            page_number=2,
            answer_section="實驗結果與關鍵數據",
            visual_type="results_table",
            target_caption="Table 2. BLEU results",
            teaching_caption="這張表呈現 BLEU 結果，是理解論文實驗主張的關鍵。",
            rationale="results_table_carries_main_evidence",
        ),
    )

    with patch(
        "services.paper_visual_planner_service.PaperVisualPlannerService.plan_visuals",
        new_callable=AsyncMock,
        return_value=planned,
    ) as mock_plan:
        candidates = await OrchestrationService._extract_attachment_visual_candidates(
            [{"filename": "paper.pdf", "pdf_bytes": pdf_bytes}],
            "planner-integration",
            model_client=object(),
            use_paper_visual_planner=True,
        )

    mock_plan.assert_awaited_once()
    assert len(candidates) == 1
    assert candidates[0].page_number == 2
    assert candidates[0].selection_source == "planner"
    assert candidates[0].to_image_block().purpose == "results_table"
    assert "BLEU" in candidates[0].to_image_block().caption
    assert candidates[0].to_image_block().explanatory_caption == ""


def test_verified_visual_instruction_injects_inventory():
    """Verified image inventory should be available before main generation."""

    messages = [{"role": "system", "content": "base prompt"}]
    image = ImageBlock(
        slot_id="img_1",
        topic="Pacific War map",
        purpose="diagram",
        image_url="https://upload.wikimedia.org/map.png",
        thumbnail_url="https://upload.wikimedia.org/map-thumb.png",
        source_url="https://commons.wikimedia.org/wiki/File:Pacific_War_Map.png",
        source_domain="commons.wikimedia.org",
        caption="Pacific War map",
        license="CC BY-SA 4.0",
        safety_status="pass",
        match_confidence=0.8,
        vision_summary="A map showing Pacific War expansion and retreat.",
        visible_elements=("island chains", "movement arrows"),
        how_to_read=("Compare arrows across years.",),
        vision_confidence="high",
        vision_source="vision_model",
    )

    result = OrchestrationService._add_verified_visual_instruction(
        messages,
        {"img_1": image},
    )

    system_prompt = result[0]["content"]
    assert "已驗證圖片清單" in system_prompt
    assert "[[AREQA_VERIFIED_IMAGE id=\"img_1\"]]" in system_prompt
    assert "Pacific War map" in system_prompt
    assert "vision_summary" in system_prompt
    assert "movement arrows" in system_prompt
    assert "how_to_read" in system_prompt
    assert "purpose" in system_prompt
    assert "主回答素材的一部分" in system_prompt
    assert "不是回答後的附件" in system_prompt
    assert "必須把最相關的已驗證圖片整合進教學流程" in system_prompt
    assert "1 至 2 句" in system_prompt
    assert "下圖是一張" in system_prompt
    assert "你可以先看圖中的" in system_prompt
    assert "再依照" in system_prompt
    assert "理解 {這張圖如何幫助回答使用者問題}" in system_prompt
    assert "不要照抄英文欄位" in system_prompt
    assert "導圖段落後必須緊接著輸出標記" in system_prompt
    assert "圖片後的文字必須接續引用或延伸圖片內容" in system_prompt
    assert "不得輸出 <AREQA_IMAGE_SLOT .../>" in system_prompt
    assert "https://upload.wikimedia.org" not in system_prompt


def test_verified_visual_instruction_lists_multiple_verified_markers():
    """Multiple preverified images should each have an allowed marker."""

    messages = [{"role": "system", "content": "base prompt"}]
    sections = {
        1: "研究方法",
        2: "實驗設計與過程",
        3: "實驗結果",
        4: "實驗結果",
    }
    purposes = {
        1: "architecture",
        2: "results_chart",
        3: "main_results_table",
        4: "ablation_table",
    }
    images = {
        f"pdf_img_{index}": ImageBlock(
            slot_id=f"pdf_img_{index}",
            topic=f"Paper figure {index}",
            purpose=purposes[index],
            image_url=f"data:image/png;base64,{index}",
            thumbnail_url=f"data:image/png;base64,{index}",
            source_url=f"#pdf-attachment-page-{index}",
            source_domain="uploaded PDF",
            caption=f"Figure {index}",
            explanatory_caption="這張圖適合用來說明研究方法。",
            placement_section=sections[index],
            planner_hint="internal planner hint",
            safety_status="pass",
            match_confidence=0.8,
        )
        for index in range(1, 5)
    }

    result = OrchestrationService._add_verified_visual_instruction(messages, images)

    system_prompt = result[0]["content"]
    for index in range(1, 5):
        assert f'[[AREQA_VERIFIED_IMAGE id="pdf_img_{index}"]]' in system_prompt
    assert "依照圖片清單中的章節提示分散到對應段落" in system_prompt
    assert "不要只滿足總張數，每個核心節都要有圖" in system_prompt
    assert "先主要結果、再消融分析" in system_prompt
    assert '"placement_section": "研究方法"' in system_prompt
    assert '"purpose": "main_results_table"' in system_prompt
    assert "不得逐字複製系統提供的圖片用途或教學提示句" in system_prompt
    assert "data:image/png" not in system_prompt


def test_verified_visual_instruction_forbids_all_image_markers_when_empty():
    """Missing preverified images should not let any visual marker leak."""

    messages = [{"role": "system", "content": "base prompt"}]

    result = OrchestrationService._add_verified_visual_instruction(messages, {})

    system_prompt = result[0]["content"]
    assert "本回合沒有可用的已驗證圖片" in system_prompt
    assert "不得輸出 <AREQA_IMAGE_SLOT .../>" in system_prompt
    assert "[[AREQA_IMAGE_REQUEST ...]]" in system_prompt
    assert "[[AREQA_VERIFIED_IMAGE ...]]" in system_prompt


def test_required_visual_instruction_discloses_unavailable_verified_image():
    """Explicit visual requests should not be silently ignored when no image survived."""

    messages = [{"role": "system", "content": "base prompt"}]
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        visual_support=VisualSupport.REQUIRED,
        visual_reason=VisualReason.EXPLICIT_VISUAL_REQUEST,
    )

    result = OrchestrationService._add_verified_visual_instruction(
        messages,
        {},
        response_policy=response_policy,
    )

    system_prompt = result[0]["content"]
    assert "使用者明確要求圖片/圖解" in system_prompt
    assert "目前無法提供可靠圖片" in system_prompt
    assert "不要冗長道歉" in system_prompt


def test_optional_visual_instruction_does_not_mention_image_failure_to_user():
    """Optional visual enrichment failures should stay silent in normal answers."""

    messages = [{"role": "system", "content": "base prompt"}]
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        visual_support=VisualSupport.OPTIONAL,
        visual_reason=VisualReason.KNOWLEDGE_EXPLANATION,
    )

    result = OrchestrationService._add_verified_visual_instruction(
        messages,
        {},
        response_policy=response_policy,
    )

    system_prompt = result[0]["content"]
    assert "本回合沒有可用的已驗證圖片" in system_prompt
    assert "使用者明確要求圖片/圖解" not in system_prompt
    assert "目前無法提供可靠圖片" not in system_prompt


@pytest.mark.asyncio
async def test_llm_stream_strips_image_request_markers(mock_client, caplog):
    """Planned visual markers should be captured but never streamed publicly."""

    caplog.set_level(logging.INFO)
    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    service = ConversationStreamService(mock_client, MagicMock())

    async def chunks():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = (
            '第一段\n\n[[AREQA_IMAGE_REQUEST id="img_1" '
            'query="forest plot meta analysis example" caption_hint="森林圖輔助理解"]]'
            "\n\n第二段"
        )
        chunk.choices[0].delta.tool_calls = None
        yield chunk

    mock_client.chat.completions.create = AsyncMock(return_value=chunks())

    events = [event async for event in service.stream(
        user_id="u1",
        conversation_id="visual-conv",
        last_user_msg="什麼是統合分析",
        messages=[{"role": "user", "content": "什麼是統合分析"}],
        force_think=False,
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.0,
        request=request,
    )]

    streamed = "".join(events)
    assert "AREQA_IMAGE_REQUEST" not in streamed
    accumulator_event = next(event for event in events if event.startswith("event: accumulator"))
    data_line = next(line for line in accumulator_event.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[6:])
    assert payload["accumulator"] == "第一段\n\n\n\n第二段"
    assert payload["image_slots"][0]["slot_id"] == "img_1"
    assert payload["image_slots"][0]["anchor_after_paragraph"] == 0
    assert "visual.slot_marker_detected" in caplog.text
    assert "forest plot" not in caplog.text


@pytest.mark.asyncio
async def test_llm_stream_strips_areqa_image_slot_markers(mock_client, caplog):
    """Gemini-like AREQA image slot tags should be captured but never streamed."""

    caplog.set_level(logging.INFO)
    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    service = ConversationStreamService(mock_client, MagicMock())

    async def chunks():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = (
            '第一段\n\n<AREQA_IMAGE_SLOT id="img_1" alt="中國東北地圖" '
            'caption="中國東北（滿洲）地理位置" query="中國東北 滿洲 地圖"/>\n\n第二段'
        )
        chunk.choices[0].delta.tool_calls = None
        yield chunk

    mock_client.chat.completions.create = AsyncMock(return_value=chunks())

    events = [event async for event in service.stream(
        user_id="u1",
        conversation_id="visual-conv",
        last_user_msg="請圖解滿洲位置",
        messages=[{"role": "user", "content": "請圖解滿洲位置"}],
        force_think=False,
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.0,
        request=request,
    )]

    public_stream = "".join(event for event in events if not event.startswith("event: accumulator"))
    assert "AREQA_IMAGE_SLOT" not in public_stream
    assert "中國東北 滿洲 地圖" not in public_stream
    accumulator_event = next(event for event in events if event.startswith("event: accumulator"))
    data_line = next(line for line in accumulator_event.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[6:])
    assert payload["accumulator"] == "第一段\n\n\n\n第二段"
    assert payload["image_slots"][0]["slot_id"] == "img_1"
    assert payload["image_slots"][0]["query"] == "中國東北 滿洲 地圖"
    assert payload["image_slots"][0]["caption_hint"] == "中國東北（滿洲）地理位置"
    assert payload["image_slots"][0]["anchor_after_paragraph"] == 0
    image_slot_event = next(event for event in events if event.startswith("event: image_slot"))
    image_slot_data = json.loads(next(
        line[6:] for line in image_slot_event.splitlines() if line.startswith("data: ")
    ))
    assert image_slot_data == {
        "slotId": "img_1",
        "anchorAfterParagraph": 0,
        "contentOffset": len("第一段\n\n"),
    }
    assert "query" not in image_slot_event
    assert "caption" not in image_slot_event
    assert "visual.slot_marker_detected" in caplog.text


def test_image_marker_filter_positions_marker_inside_one_chunk_with_utf16_offset():
    """One provider packet may contain paragraphs, emoji, and an image marker."""

    marker_filter = ImageRequestMarkerFilter(max_slots=2)
    prefix = "😀第一段\n\n下圖的左右箭頭展示了戰線如何隨年份移動。"
    public = marker_filter.feed(
        f'{prefix}[[AREQA_VERIFIED_IMAGE id="img_1"]]\n\n第三段'
    )

    slot = marker_filter.drain_new_slots()[0]
    assert public == f"{prefix}\n\n第三段"
    assert slot.anchor_after_paragraph == 1
    assert slot.content_offset == len(prefix.encode("utf-16-le")) // 2
    assert marker_filter.drain_new_slots() == []


def test_image_marker_filter_accepts_four_verified_markers_for_paper_mode():
    """Paper overview streaming can accept four preverified PDF image markers."""

    marker_filter = ImageRequestMarkerFilter(max_slots=4)

    public = marker_filter.feed(
        "下圖說明研究方法的主要流程與角色分工。[[AREQA_VERIFIED_IMAGE id=\"pdf_img_1\"]]\n\n"
        "下圖說明資料集組成與實驗設計的範圍。[[AREQA_VERIFIED_IMAGE id=\"pdf_img_2\"]]\n\n"
        "下圖說明實驗結果中模型表現的比較。[[AREQA_VERIFIED_IMAGE id=\"pdf_img_3\"]]\n\n"
        "下圖補充泛化實驗與後續分析的關係。[[AREQA_VERIFIED_IMAGE id=\"pdf_img_4\"]]"
    )

    assert "AREQA_VERIFIED_IMAGE" not in public
    assert [slot.slot_id for slot in marker_filter.slots] == [
        "pdf_img_1",
        "pdf_img_2",
        "pdf_img_3",
        "pdf_img_4",
    ]


@pytest.mark.parametrize(
    "prefix",
    [
        "貝氏統計與頻率統計的根本差異在於機率定義。",
        "### 下圖說明",
    ],
)
def test_image_marker_filter_rejects_verified_marker_without_visual_lead_in(prefix):
    """A verified marker must not create a slot without explanatory prose."""

    marker_filter = ImageRequestMarkerFilter(max_slots=2)

    public = marker_filter.feed(
        f'{prefix}\n\n[[AREQA_VERIFIED_IMAGE id="img_1"]]\n\n後續說明'
    )

    assert "AREQA_VERIFIED_IMAGE" not in public
    assert marker_filter.slots == []
    assert marker_filter.rejected_verified_marker_count == 1


@pytest.mark.asyncio
async def test_llm_stream_buffers_split_image_request_marker(mock_client):
    """Split marker starts should not leak partial marker text to the client."""

    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    service = ConversationStreamService(mock_client, MagicMock())

    async def chunks():
        for content in (
            "第一段\n\n[[AREQA_",
            'IMAGE_REQUEST id="img_1" query="forest plot" caption_hint="圖解"]]',
            "\n\n第二段",
        ):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = content
            chunk.choices[0].delta.tool_calls = None
            yield chunk

    mock_client.chat.completions.create = AsyncMock(return_value=chunks())

    events = [event async for event in service.stream(
        user_id="u1",
        conversation_id="visual-conv",
        last_user_msg="什麼是統合分析",
        messages=[{"role": "user", "content": "什麼是統合分析"}],
        force_think=False,
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.0,
        request=request,
    )]

    streamed = "".join(events)
    assert "AREQA_" not in streamed
    accumulator_event = next(event for event in events if event.startswith("event: accumulator"))
    data_line = next(line for line in accumulator_event.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[6:])
    assert payload["image_slots"][0]["slot_id"] == "img_1"


@pytest.mark.asyncio
async def test_llm_stream_buffers_split_areqa_image_slot_marker(mock_client):
    """Split AREQA image slot tags should not leak partial tag text."""

    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    service = ConversationStreamService(mock_client, MagicMock())

    async def chunks():
        for content in (
            "第一段\n\n<AREQA_",
            'IMAGE_SLOT id="img_1" alt="滿洲地圖" ',
            'caption="中國東北位置" query="中國東北 滿洲 地圖"/>',
            "\n\n第二段",
        ):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = content
            chunk.choices[0].delta.tool_calls = None
            yield chunk

    mock_client.chat.completions.create = AsyncMock(return_value=chunks())

    events = [event async for event in service.stream(
        user_id="u1",
        conversation_id="visual-conv",
        last_user_msg="請圖解滿洲位置",
        messages=[{"role": "user", "content": "請圖解滿洲位置"}],
        force_think=False,
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.0,
        request=request,
    )]

    public_stream = "".join(event for event in events if not event.startswith("event: accumulator"))
    assert "AREQA_" not in public_stream
    assert "IMAGE_SLOT" not in public_stream
    accumulator_event = next(event for event in events if event.startswith("event: accumulator"))
    data_line = next(line for line in accumulator_event.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[6:])
    assert payload["image_slots"][0]["slot_id"] == "img_1"
    assert payload["image_slots"][0]["query"] == "中國東北 滿洲 地圖"


@pytest.mark.asyncio
async def test_llm_stream_strips_verified_image_markers(mock_client):
    """Verified image markers should be captured without requiring a query."""

    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    service = ConversationStreamService(mock_client, MagicMock())

    async def chunks():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = (
            '下圖的左側是日本擴張路線，右側則是隨年份後退的戰線。'
            '\n\n[[AREQA_VERIFIED_IMAGE id="img_1"]]\n\n第二段'
        )
        chunk.choices[0].delta.tool_calls = None
        yield chunk

    mock_client.chat.completions.create = AsyncMock(return_value=chunks())

    events = [event async for event in service.stream(
        user_id="u1",
        conversation_id="visual-conv",
        last_user_msg="二戰日本戰況",
        messages=[{"role": "user", "content": "二戰日本戰況"}],
        force_think=False,
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.0,
        request=request,
    )]

    streamed = "".join(events)
    assert "AREQA_VERIFIED_IMAGE" not in streamed
    accumulator_event = next(event for event in events if event.startswith("event: accumulator"))
    data_line = next(line for line in accumulator_event.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line[6:])
    assert payload["image_slots"][0]["slot_id"] == "img_1"
    assert payload["image_slots"][0]["query"] == ""


@pytest.mark.asyncio
async def test_llm_stream_uses_openrouter_latency_routing_and_session_id(
    mock_client, caplog
):
    """Main answer requests should opt into OpenRouter low-latency routing."""

    caplog.set_level(logging.INFO)
    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)
    service = ConversationStreamService(mock_client, MagicMock())

    async def chunks():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = "answer"
        chunk.choices[0].delta.tool_calls = None
        yield chunk

    mock_client.chat.completions.create = AsyncMock(return_value=chunks())

    _ = [event async for event in service.stream(
        user_id="u1",
        conversation_id="conversation with spaces",
        last_user_msg="請簡短回答",
        messages=[{"role": "user", "content": "請簡短回答"}],
        force_think=False,
        max_tokens=100,
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.0,
        request=request,
    )]

    kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert kwargs["extra_body"]["session_id"] == "conversation_with_spaces"
    assert kwargs["extra_body"]["provider"] == {
        "preferred_max_latency": {"p90": 2.5}
    }
    assert "openrouter_session=True" in caplog.text
    assert "latency_routing=True" in caplog.text


@pytest.mark.asyncio
async def test_pdf_stream_uses_openrouter_native_parser(
    mock_router, mock_rag, mock_suggestion, mock_client, caplog
):
    caplog.set_level(logging.INFO)
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()
    request.is_disconnected = AsyncMock(return_value=False)

    async def chunks():
        if False:
            yield None

    mock_client.chat.completions.create = AsyncMock(return_value=chunks())
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "請分析"},
            {"type": "file", "file": {"filename": "lesson.pdf", "file_data": "data:application/pdf;base64,AA=="}},
        ],
    }]

    _ = [event async for event in service._node_llm_stream(
        "u1", "conv", "請分析", messages, False, 100, 0.7, 0.9, 1.0, request
    )]

    kwargs = mock_client.chat.completions.create.await_args.kwargs
    assert kwargs["extra_body"]["plugins"] == [
        {"id": "file-parser", "pdf": {"engine": "native"}}
    ]
    assert kwargs["extra_body"]["session_id"] == "conv"
    assert kwargs["extra_body"]["provider"] == {
        "preferred_max_latency": {"p90": 2.5}
    }
    assert "orchestration.stream_started" in caplog.text
    assert "image_slot_cap=2" in caplog.text

@pytest.fixture
def mock_router():
    router = AsyncMock()
    return router

@pytest.fixture
def mock_rag():
    rag = AsyncMock()
    return rag

@pytest.fixture
def mock_suggestion():
    suggestion = AsyncMock()
    return suggestion

@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_prompt_assembly_skips_long_term_memory_for_low_information_greeting(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
    ) as mock_cold, patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
    ) as mock_gum:
        messages = await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="new-conv",
            messages=[{"role": "user", "content": "你好"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="你好",
        )

    system_prompt = messages[0]["content"]
    assert "<retrieved_memory>" not in system_prompt
    assert "<memory>" not in system_prompt
    mock_cold.assert_not_awaited()
    mock_gum.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_assembly_keeps_long_term_memory_for_substantive_query(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
        return_value="cold context",
    ) as mock_cold, patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
        return_value="<memory>gum context</memory>",
    ) as mock_gum:
        messages = await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="react-conv",
            messages=[{"role": "user", "content": "React useEffect dependency array 是什麼？"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="React useEffect dependency array 是什麼？",
        )

    system_prompt = messages[0]["content"]
    assert "<retrieved_memory>" in system_prompt
    assert "<memory>gum context</memory>" in system_prompt
    mock_cold.assert_awaited_once()
    mock_gum.assert_awaited_once()


@pytest.mark.asyncio
async def test_first_newton_question_does_not_claim_verified_understanding(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ):
        messages = await service._node_prompt_assembly(
            user_id="new-user",
            conversation_id="newton-conversation",
            messages=[{"role": "user", "content": "請教我牛頓第一運動定律。"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="請教我牛頓第一運動定律。",
        )

    system_prompt = messages[0]["content"]
    assert "理解程度視為 unknown" in system_prompt
    assert "使用者目前已理解牛頓第一運動定律" not in system_prompt
    assert "使用者已掌握慣性" not in system_prompt


@pytest.mark.asyncio
async def test_prompt_assembly_skips_cross_conversation_memory_for_health_query(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
    ) as mock_cold, patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
    ) as mock_gum:
        messages = await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="health-conv",
            messages=[{"role": "user", "content": "血壓 118/77，脈搏 91 正常嗎？"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="血壓 118/77，脈搏 91 正常嗎？",
        )

    assert "<retrieved_memory>" not in messages[0]["content"]
    mock_cold.assert_not_awaited()
    mock_gum.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_assembly_allows_sensitive_recall_when_user_explicitly_requests_it(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
        return_value="family context",
    ) as mock_cold, patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ) as mock_gum:
        await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="health-conv",
            messages=[{"role": "user", "content": "請結合昨天家庭壓力的情況回答"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="請結合昨天家庭壓力的情況回答",
        )

    mock_cold.assert_awaited_once()
    mock_gum.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_short_circuits_low_information_greeting_without_llm(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock):
        events = []
        async for event in service.execute(
            [{"role": "user", "content": "你好"}],
            "greeting-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        ):
            events.append(event)

    joined = "".join(events)
    assert "你好，我在。你可以直接告訴我現在想處理什麼。" in joined
    assert "React" not in joined
    assert "useEffect" not in joined
    assert joined.endswith("data: [DONE]\n\n")


@pytest.mark.asyncio
async def test_execute_emits_visible_status_before_memory_work(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()

    store = MagicMock()
    with patch("memory_store.get_global_store", return_value=store), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock):
        stream = service.execute(
            [{"role": "user", "content": "請解釋 dependency injection"}],
            "latency-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )
        first = await anext(stream)
        second = await anext(stream)
        third = await anext(stream)
        fourth = await anext(stream)
        await stream.aclose()

    assert first.startswith("event: metadata")
    assert second.startswith("event: status")
    assert '"status": "routing"' in second
    assert third.startswith("event: status")
    assert "正在判斷是否需要外部搜尋" in third
    assert fourth.startswith("event: action")
    assert "請解釋 dependency injection" not in fourth
    assert '"reason_code": "USER_DISABLED"' in fourth


@pytest.mark.asyncio
async def test_execute_passes_structured_response_policy_to_prompt_assembly(
    mock_router, mock_rag, mock_suggestion, mock_client, caplog, monkeypatch
):
    import config as runtime_config

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", False)
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.ANSWER_EXAM,
        answer_depth=AnswerDepth.DIRECT,
        tone=ResponseTone.PLAIN,
        structure=ResponseStructure.SHORT,
        followup_mode=FollowupMode.NONE,
        legacy_policy="NORMAL",
    )

    async def llm_stream(*args, **kwargs):
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value=response_policy), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]) as prompt_assembly:
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "但是只能選一個"}],
            "response-policy-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    assert prompt_assembly.await_args.kwargs["response_policy"] == response_policy
    assert "orchestration.response_policy_applied" in caplog.text
    assert "source=classifier" in caplog.text
    assert "但是只能選一個" not in caplog.text


@pytest.mark.asyncio
async def test_execute_injects_missing_visual_attachment_guard_before_main_model(
    mock_router, mock_rag, mock_suggestion, mock_client, caplog
):
    """The live execute path should not let text-only image references be guessed."""

    caplog.set_level(logging.INFO, logger="backend.services.orchestration_service")
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()
    captured_messages = []
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.GENERAL_QA,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
    )

    async def llm_stream(*args, **kwargs):
        captured_messages.extend(args[3])
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value=response_policy), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[
             {"role": "system", "content": "base prompt"},
             {"role": "user", "content": "所以這兩張圖是什麼意思"},
         ]):
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "所以這兩張圖是什麼意思"}],
            "missing-visual-attachment-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    assert "不得假裝看過圖片" in captured_messages[0]["content"]
    assert "不得推測左圖、右圖" in captured_messages[0]["content"]
    assert "orchestration.missing_visual_attachment_guard_applied" in caplog.text
    assert "這兩張圖" not in caplog.text


@pytest.mark.asyncio
async def test_execute_passes_accumulated_answer_to_suggestions(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()
    mock_suggestion.generate_suggestions.return_value = []

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋 dependency injection"}],
            "accumulator-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    assert not any(event.startswith("event: accumulator") for event in events)
    assert mock_suggestion.generate_suggestions.await_args.kwargs["answer_text"] == "answer"


@pytest.mark.asyncio
async def test_execute_passes_planned_image_slots_to_visual_service(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()
    mock_suggestion.generate_suggestions.return_value = []
    service.visual_answer_service.build_answer_blocks = AsyncMock(return_value=[])
    planned_slots = [{
        "slot_id": "img_1",
        "query": "forest plot meta analysis example",
        "caption_hint": "森林圖輔助理解",
        "anchor_after_paragraph": 0,
    }]

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
        yield f"event: accumulator\ndata: {json.dumps({'accumulator': 'answer', 'image_slots': planned_slots}, ensure_ascii=False)}\n\n"

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "什麼是統合分析"}],
            "planned-slot-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    assert not any(event.startswith("event: accumulator") for event in events)
    assert service.visual_answer_service.build_answer_blocks.await_args.kwargs["planned_image_slots"] == planned_slots


@pytest.mark.asyncio
async def test_execute_logs_safe_turn_latency_trace(
    mock_router, mock_rag, mock_suggestion, caplog
):
    caplog.set_level(logging.INFO)
    service = OrchestrationService(mock_router, mock_rag, None, None)
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋 dependency injection"}],
            "trace-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    assert events[-1] == "data: [DONE]\n\n"
    assert "orchestration.turn_trace_completed" in caplog.text
    assert "orchestration.turn_trace_summary" in caplog.text
    assert "time_to_first_answer_ms" in caplog.text
    assert "phase_durations_ms" in caplog.text
    assert "prompt_assembly_started" in caplog.text
    assert "terminal_sent" in caplog.text
    assert "請解釋 dependency injection" not in caplog.text


@pytest.mark.asyncio
async def test_turn_plan_enabled_can_skip_general_policy_classifier_when_disabled(
    mock_router, mock_rag, mock_client, monkeypatch
):
    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", True)
    monkeypatch.setattr(runtime_config.settings, "enable_policy_classifier_for_general_chat", False)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock) as mock_policy, \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]) as prompt_assembly:
        events = [event async for event in service.execute(
            [{"role": "user", "content": "這部電影的節奏很奇怪"}],
            "turn-plan-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    mock_policy.assert_not_awaited()
    assert prompt_assembly.await_args.kwargs["turn_plan"].route.value == "GENERAL_CHAT"
    assert "data: [DONE]" in events[-1]


@pytest.mark.asyncio
async def test_turn_plan_enabled_runs_general_policy_classifier_by_default(
    mock_router, mock_rag, mock_client, monkeypatch, caplog
):
    import config as runtime_config

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", True)
    monkeypatch.setattr(runtime_config.settings, "enable_policy_classifier_for_general_chat", True)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.DISCUSS_IDEA,
        answer_depth=AnswerDepth.REFLECTIVE,
        tone=ResponseTone.ANALYTICAL,
        structure=ResponseStructure.ARGUMENT,
        followup_mode=FollowupMode.OPTIONAL,
        legacy_policy="PUSH_LIMIT",
    )

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value=response_policy) as mock_policy, \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]) as prompt_assembly:
        events = [event async for event in service.execute(
            [{"role": "user", "content": "這部電影的節奏很奇怪"}],
            "turn-plan-general-policy-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    mock_policy.assert_awaited_once()
    assert prompt_assembly.await_args.kwargs["turn_plan"].route.value == "GENERAL_CHAT"
    assert prompt_assembly.await_args.kwargs["response_policy"] == response_policy
    assert "orchestration.response_policy_applied" in caplog.text
    assert "source=classifier" in caplog.text
    assert "data: [DONE]" in events[-1]


@pytest.mark.asyncio
async def test_visual_preflight_skips_blocking_work_after_policy_timeout(
    mock_router, mock_rag, mock_client, monkeypatch, caplog
):
    """Policy fallback should not spend optional visual work before first text."""

    import config as runtime_config

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", True)
    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight", True)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    service.visual_answer_service.prepare_preflight_image_blocks = AsyncMock(return_value={})
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, side_effect=asyncio.TimeoutError), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋第二次世界大戰歐洲戰場"}],
            "learning-visual-timeout-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    service.visual_answer_service.prepare_preflight_image_blocks.assert_not_awaited()
    assert "visual.preflight_blocking_skipped" in caplog.text


@pytest.mark.asyncio
async def test_optional_visual_policy_does_not_block_before_first_text(
    mock_router, mock_rag, mock_client, monkeypatch, caplog
):
    """OPTIONAL visual enrichment should not trigger blocking preflight."""

    import config as runtime_config

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", True)
    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight", True)
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        visual_support=VisualSupport.OPTIONAL,
        visual_reason=VisualReason.KNOWLEDGE_EXPLANATION,
        legacy_policy="PROBE_UNDERSTANDING",
    )
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    service.visual_answer_service.prepare_preflight_image_blocks = AsyncMock(return_value={})
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value=response_policy), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋第二次世界大戰歐洲戰場"}],
            "optional-visual-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    service.visual_answer_service.prepare_preflight_image_blocks.assert_not_awaited()
    assert "blocking_allowed=False" in caplog.text
    assert "trigger=response_policy_optional" in caplog.text


@pytest.mark.asyncio
async def test_required_visual_policy_allows_blocking_preflight(
    mock_router, mock_rag, mock_client, monkeypatch
):
    """REQUIRED visual policy may block so explicit semantic visual requests work."""

    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", True)
    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight", True)
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        visual_support=VisualSupport.REQUIRED,
        visual_reason=VisualReason.EXPLICIT_VISUAL_REQUEST,
        legacy_policy="PROBE_UNDERSTANDING",
    )
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    service.visual_answer_service.prepare_preflight_image_blocks = AsyncMock(return_value={})
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value=response_policy), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "請把這個概念轉成更容易看的形式"}],
            "required-visual-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    kwargs = service.visual_answer_service.prepare_preflight_image_blocks.await_args.kwargs
    assert kwargs["response_policy"].visual_support == VisualSupport.REQUIRED
    assert kwargs["turn_plan"].route.value == "LEARNING_HELP"


@pytest.mark.asyncio
async def test_turn_plan_disabled_keeps_legacy_policy_classifier(
    mock_router, mock_rag, mock_client, monkeypatch
):
    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_turn_plan_runtime", False)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL") as mock_policy, \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]) as prompt_assembly:
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "這部電影的節奏很奇怪"}],
            "legacy-turn-plan-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
        )]

    mock_policy.assert_awaited_once()
    assert prompt_assembly.await_args.kwargs["turn_plan"] is None


@pytest.mark.asyncio
async def test_prompt_assembly_passes_explicit_recall_memory_runtime_settings(
    mock_router, mock_rag, mock_client, monkeypatch
):
    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "explicit_recall_memory_timeout_ms", 1234)
    monkeypatch.setattr(runtime_config.settings, "enable_explicit_recall_memory_cache", True)
    monkeypatch.setattr(runtime_config.settings, "explicit_recall_memory_cache_ttl_seconds", 77)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    service.context_service.build_conversation_context = AsyncMock(
        return_value=ConversationContext(
            messages=[{"role": "user", "content": "answer"}],
            learner_understanding="unknown",
            retrieved_memory=False,
        )
    )
    turn_plan = SimpleNamespace(
        allow_long_term_memory_query=True,
        reason_code="EXPLICIT_RECALL_REQUEST",
    )

    with patch("memory_store.get_global_store", return_value=None):
        await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="explicit-conv",
            messages=[{"role": "user", "content": "你還記得我的偏好嗎？"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="你還記得我的偏好嗎？",
            turn_plan=turn_plan,
        )

    kwargs = service.context_service.build_conversation_context.await_args.kwargs
    assert kwargs["explicit_recall_memory_timeout_ms"] == 1234
    assert kwargs["enable_explicit_recall_memory_cache"] is True
    assert kwargs["explicit_recall_memory_cache_ttl_seconds"] == 77
    assert kwargs["memory_skip_reason"] == "EXPLICIT_RECALL_REQUEST"


@pytest.mark.asyncio
async def test_prompt_assembly_builds_and_passes_parts_context(
    mock_router, mock_rag, mock_client, monkeypatch
):
    """Prompt assembly should add PARTS context without changing public APIs."""

    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_parts_prompt_context", True)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_llm_rewrite", True)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_llm_rewrite_for_ungrounded_turns", True)
    monkeypatch.setattr(runtime_config.settings, "parts_rewrite_timeout_ms", 321)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_prompt_debug_logs", True)
    monkeypatch.setattr(runtime_config.settings, "model_policy_classifier", "policy-model")
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    parts_context = PartsContext(
        persona="引導型數學理解教練",
        act="檢查解題步驟",
        recipient="程度未知的學習者",
        theme="運算順序",
        structure="分步檢查",
        composed_instruction="你現在的角色是「引導型數學理解教練」。請檢查解題步驟。",
        confidence="high",
        missing_fields=(),
    )
    service.parts_context_service.build = AsyncMock(return_value=parts_context)
    service.context_service.build_conversation_context = AsyncMock(
        return_value=ConversationContext(
            messages=[{"role": "user", "content": "answer"}],
            learner_understanding="unknown",
            retrieved_memory=False,
        )
    )
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        legacy_policy="NORMAL",
    )

    with patch("memory_store.get_global_store", return_value=None):
        await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="parts-conv",
            messages=[
                {"role": "user", "content": "日本二戰歷史過程"},
                {
                    "role": "assistant",
                    "content": (
                        "先看**第一階段：戰爭的開端與背景**。\n"
                        "1. **擴張初期與國際孤立**\n"
                        "2. **結盟與戰事擴大**\n\n"
                        "#### 文獻來源\n1. 測試來源"
                    ),
                },
                {"role": "user", "content": "請先教我運算順序"},
                {"role": "assistant", "content": "先從括號與次方開始檢查。"},
                {"role": "user", "content": "我算這題對嗎？"},
            ],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="我算這題對嗎？",
            response_policy=response_policy,
        )

    service.parts_context_service.build.assert_awaited_once()
    parts_kwargs = service.parts_context_service.build.await_args.kwargs
    assert parts_kwargs["response_policy"] == response_policy
    assert "recent_conversation_context" in parts_kwargs
    assert "User:\n日本二戰歷史過程" in parts_kwargs["recent_conversation_context"]
    assert "Assistant:\n先看**第一階段：戰爭的開端與背景**" in parts_kwargs["recent_conversation_context"]
    assert "2. **結盟與戰事擴大**" in parts_kwargs["recent_conversation_context"]
    assert "Assistant:\n先從括號與次方開始檢查。" in parts_kwargs["recent_conversation_context"]
    assert "我算這題對嗎？" not in parts_kwargs["recent_conversation_context"]
    assert parts_kwargs["client"] is mock_client
    assert parts_kwargs["model"] == "policy-model"
    assert parts_kwargs["enable_llm_rewrite"] is True
    assert parts_kwargs["timeout_ms"] == 321
    assert parts_kwargs["enable_debug_logs"] is True
    context_kwargs = service.context_service.build_conversation_context.await_args.kwargs
    assert context_kwargs["parts_context"] == parts_context


@pytest.mark.asyncio
async def test_prompt_assembly_skips_ungrounded_parts_llm_rewrite_by_default(
    mock_router, mock_rag, mock_client, monkeypatch, caplog
):
    """Ungrounded turns should keep PARTS context without spending rewrite cost."""

    import config as runtime_config

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_prompt_context", True)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_llm_rewrite", True)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_llm_rewrite_for_ungrounded_turns", False)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    service.context_service.build_conversation_context = AsyncMock(
        return_value=ConversationContext(
            messages=[{"role": "user", "content": "answer"}],
            learner_understanding="unknown",
            retrieved_memory=False,
        )
    )
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        legacy_policy="NORMAL",
    )

    with patch("memory_store.get_global_store", return_value=None):
        await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="ungrounded-parts-conv",
            messages=[{"role": "user", "content": "請解釋第二次世界大戰主因"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="請解釋第二次世界大戰主因",
            response_policy=response_policy,
        )

    mock_client.chat.completions.create.assert_not_awaited()
    context_kwargs = service.context_service.build_conversation_context.await_args.kwargs
    assert context_kwargs["parts_context"] is not None
    assert "parts_context.rewrite_gate" in caplog.text
    assert "enabled=False" in caplog.text
    assert "route=UNKNOWN" in caplog.text


@pytest.mark.asyncio
async def test_prompt_assembly_allows_attachment_parts_llm_rewrite(
    mock_router, mock_rag, mock_client, monkeypatch
):
    """Attachment-grounded turns may spend rewrite cost before generation."""

    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_parts_prompt_context", True)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_llm_rewrite", True)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_llm_rewrite_for_ungrounded_turns", False)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    service.context_service.build_conversation_context = AsyncMock(
        return_value=ConversationContext(
            messages=[{"role": "user", "content": "answer"}],
            learner_understanding="unknown",
            retrieved_memory=False,
        )
    )
    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        attachment_task=AttachmentTask.PAPER_TARGETED_QA,
        attachment_reason=AttachmentReason.TARGETED_ATTACHMENT_TASK,
        legacy_policy="NORMAL",
    )

    with patch("memory_store.get_global_store", return_value=None):
        await service._node_prompt_assembly(
            user_id="u1",
            conversation_id="attachment-parts-conv",
            messages=[{"role": "user", "content": "請解釋這段 method"}],
            use_rag=False,
            use_web_search=False,
            force_think=False,
            context_results_obj=None,
            last_user_msg="請解釋這段 method",
            response_policy=response_policy,
            has_attachments=True,
        )

    assert mock_client.chat.completions.create.await_count == 1
    context_kwargs = service.context_service.build_conversation_context.await_args.kwargs
    assert context_kwargs["parts_context"] is not None


@pytest.mark.asyncio
async def test_prompt_assembly_keeps_concurrent_run_contexts_isolated(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)

    async def assemble(conversation_id, marker):
        return await service._node_prompt_assembly(
            user_id="u1",
            conversation_id=conversation_id,
            messages=[{"role": "user", "content": "同一個問題"}],
            use_rag=False,
            use_web_search=True,
            force_think=False,
            context_results_obj={"source": "web_search"},
            last_user_msg="同一個問題",
            context_prompt=f"<context>{marker}</context>\n",
        )

    with patch(
        "backend.services.orchestration_service.get_hot_memory_snapshot",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_cold_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ), patch(
        "backend.services.orchestration_service.query_memory_for_context",
        new_callable=AsyncMock,
        return_value="",
    ):
        first, second = await asyncio.gather(
            assemble("conversation-a", "SOURCE_A"),
            assemble("conversation-b", "SOURCE_B"),
        )

    first_user = next(message["content"] for message in first if message["role"] == "user")
    second_user = next(message["content"] for message in second if message["role"] == "user")
    assert "SOURCE_A" in first_user and "SOURCE_B" not in first_user
    assert "SOURCE_B" in second_user and "SOURCE_A" not in second_user


@pytest.mark.asyncio
async def test_explicit_never_search_mode_overrides_legacy_search_boolean(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()

    async def fail_if_searched(*args, **kwargs):
        raise AssertionError("web search must not run in never mode")
        yield

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"offline"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"offline"}\n\n'

    service._node_perplexity_search = fail_if_searched
    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "搜尋今天最新新聞"}],
            "privacy-conv",
            False,
            True,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
            search_mode="never",
        )]

    assert "offline" in "".join(events)


@pytest.mark.asyncio
async def test_legacy_auto_search_mode_is_disabled_by_default(
    mock_router, mock_rag, mock_suggestion, mock_client, monkeypatch, caplog
):
    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_auto_web_search", False)
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()
    caplog.set_level(logging.INFO, logger="backend.services.orchestration_service")

    async def fail_if_searched(*args, **kwargs):
        raise AssertionError("auto mode must not run web search by default")
        yield

    async def llm_stream(*args, **kwargs):
        yield 'data: {"choices":[{"delta":{"content":"offline"}}]}\n\n'
        yield 'event: accumulator\ndata: {"accumulator":"offline"}\n\n'

    service._node_perplexity_search = fail_if_searched
    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "今天最新新聞是什麼"}],
            "auto-disabled-conv",
            False,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
            search_mode="auto",
        )]

    assert "offline" in "".join(events)
    assert "orchestration.auto_web_search_disabled" in caplog.text


@pytest.mark.asyncio
async def test_auto_mode_with_attachment_skips_generic_search_and_rag(
    mock_router, mock_rag, mock_suggestion, mock_client, caplog
):
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()
    captured_messages = []
    captured_stream_kwargs = {}
    caplog.set_level(logging.INFO, logger="backend.services.orchestration_service")

    async def fail_if_searched(*args, **kwargs):
        raise AssertionError("attachment-first AUTO mode must not use generic retrieval")
        yield

    async def llm_stream(*args, **kwargs):
        captured_messages.extend(args[3])
        captured_stream_kwargs.update(kwargs)
        yield 'event: accumulator\ndata: {"accumulator":"attachment answer"}\n\n'

    service._node_perplexity_search = fail_if_searched
    service._node_rag_retrieval = fail_if_searched
    service._node_llm_stream = llm_stream
    attachment = {
        "type": "file",
        "file": {"filename": "lesson.pdf", "file_data": "data:application/pdf;base64,AA=="},
    }

    response_policy = ResponsePolicy(
        task_intent=TaskIntent.EXPLAIN_TEXT,
        answer_depth=AnswerDepth.SCAFFOLDED,
        tone=ResponseTone.TUTORING,
        structure=ResponseStructure.STEP_BY_STEP,
        followup_mode=FollowupMode.OPTIONAL,
        attachment_task=AttachmentTask.PAPER_AUTO_EXPLAIN,
        attachment_reason=AttachmentReason.GENERIC_PAPER_EXPLANATION,
    )

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value=response_policy), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[
             {"role": "system", "content": "base prompt"},
             {"role": "user", "content": "請解釋該 PDF"},
         ]):
        events = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋該 PDF"}],
            "attachment-conv",
            True,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
            search_mode="auto",
            attachments=[attachment],
        )]

    joined = "".join(events)
    assert "ATTACHMENT_CONTEXT_PRIORITY" in joined
    assert any(
        isinstance(message.get("content"), list) and attachment in message["content"]
        for message in captured_messages
    )
    assert "不得根據檔名" in captured_messages[0]["content"]
    assert "PDF 論文自動解說任務" in captured_messages[0]["content"]
    assert "profile: AREQA_TEACHING_V1" in captured_messages[0]["content"]
    assert "研究動機與目的" in captured_messages[0]["content"]
    assert "paper.auto_explain_policy_selected" in caplog.text
    assert "applied=True" in caplog.text
    assert "task=PAPER_AUTO_EXPLAIN" in caplog.text
    assert "pdf_count=1" in caplog.text
    assert captured_stream_kwargs["max_image_slots"] == 4


@pytest.mark.asyncio
async def test_pdf_auto_explain_guardrail_survives_policy_classifier_timeout(
    mock_router,
    mock_rag,
    mock_suggestion,
    mock_client,
    caplog,
):
    """Classifier timeout must not bypass deterministic PDF overview routing."""

    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()
    captured_messages = []
    caplog.set_level(logging.INFO, logger="backend.services.orchestration_service")

    async def slow_policy(*args, **kwargs):
        await asyncio.sleep(2)
        return ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
        )

    async def llm_stream(*args, **kwargs):
        captured_messages.extend(args[3])
        yield 'event: accumulator\ndata: {"accumulator":"attachment answer"}\n\n'

    async def fake_extract(*args, **kwargs):
        return []

    service._node_llm_stream = llm_stream
    attachment = {
        "type": "file",
        "file": {"filename": "paper.pdf", "file_data": "data:application/pdf;base64,AA=="},
    }
    attachment_visual_sources = [{"filename": "paper.pdf", "pdf_bytes": b"%PDF-1.4"}]

    with patch("memory_store.get_global_store", return_value=None), \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.classify_dialogue_policy", side_effect=slow_policy), \
         patch.object(service, "_extract_attachment_visual_candidates", new_callable=AsyncMock, side_effect=fake_extract) as mock_extract, \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[
             {"role": "system", "content": "base prompt"},
             {"role": "user", "content": "Please help me explain this paper."},
         ]):
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "Please help me explain this paper."}],
            "attachment-timeout-conv",
            True,
            False,
            False,
            100,
            0.7,
            0.9,
            1.0,
            request,
            "u1",
            search_mode="auto",
            attachments=[attachment],
            attachment_visual_sources=attachment_visual_sources,
        )]

    assert mock_extract.await_count == 1
    assert "PDF 論文自動解說任務" in captured_messages[0]["content"]
    assert "paper.auto_explain_policy_selected" in caplog.text
    assert "applied=True" in caplog.text
    assert "task=PAPER_AUTO_EXPLAIN" in caplog.text
    assert "visual.attachment_preflight_skipped" not in caplog.text


@pytest.mark.asyncio
async def test_durable_jobs_suppress_in_process_edf_and_reflection_tasks(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    service = OrchestrationService(mock_router, mock_rag, None, mock_client)
    request = MagicMock()
    durable_store = MagicMock()
    durable_store.schedule = AsyncMock(return_value="job-1")
    memory_store = MagicMock()

    async def llm_stream(*args, **kwargs):
        yield 'event: accumulator\ndata: {"accumulator":"answer"}\n\n'

    service._node_llm_stream = llm_stream

    with patch("memory_store.get_global_store", return_value=memory_store), \
         patch("job_store.get_agent_job_store", return_value=durable_store), \
         patch("gum_integration.push_reflection_observation", new_callable=AsyncMock) as reflection, \
         patch("services.compeer_scheduler.set_last_interaction_time", new_callable=AsyncMock), \
         patch("backend.services.orchestration_service.async_evaluate_and_update_state", new_callable=AsyncMock) as edf, \
         patch("backend.services.orchestration_service.classify_dialogue_policy", new_callable=AsyncMock, return_value="NORMAL"), \
         patch.object(service, "_node_prompt_assembly", new_callable=AsyncMock, return_value=[]):
        _ = [event async for event in service.execute(
            [{"role": "user", "content": "請解釋 dependency injection"}],
            "durable-conv", False, False, False, 100, 0.7, 0.9, 1.0,
            request, "u1",
        )]
        await asyncio.gather(*tuple(service.post_turn_service._background_tasks))

    assert durable_store.schedule.await_count == 2
    reflection.assert_not_awaited()
    edf.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.skip(reason="Router feature bypassed by user request")
async def test_orchestration_routing_deny(mock_router, mock_rag, mock_suggestion, mock_client):
    # Mock the router to DENY
    mock_router.check_query_intent.return_value = {
        "action": "DENY", 
        "refusal_message": "這是數學問題"
    }
    
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    messages = [{"role": "user", "content": "1+1=?"}]
    request = MagicMock()
    
    with patch('backend.services.orchestration_service.push_observation', new_callable=AsyncMock), \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock):
        
        events = []
        async for event in service.execute(messages, "test_conv_id", False, False, False, 100, 0.7, 0.9, 1.0, request):
            events.append(event)
            
        assert len(events) >= 2
        assert any("refused" in e for e in events)
        assert any("這是數學問題" in e for e in events)
        assert "data: [DONE]" in events[-1]

@pytest.mark.asyncio
@pytest.mark.skip(reason="Router feature bypassed by user request")
async def test_orchestration_routing_allow(mock_router, mock_rag, mock_suggestion, mock_client):
    # Mock the router to ALLOW
    mock_router.check_query_intent.return_value = {
        "action": "ALLOW"
    }
    
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    messages = [{"role": "user", "content": "紅樓夢"}]
    request = MagicMock()
    
    with patch('backend.services.orchestration_service.push_observation', new_callable=AsyncMock), \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock), \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock) as mock_policy:
         
        mock_policy.return_value = "NORMAL"
        
        events = []
        async for event in service.execute(messages, "test_conv_id", False, False, False, 100, 0.7, 0.9, 1.0, request):
            events.append(event)
            
        # Since we are in Gate 1A, it yields dummy processing and OK messages
        assert any("generating" in e for e in events) or any("status" in e for e in events)
        assert "data: [DONE]" in events[-1]


@pytest.mark.asyncio
async def test_generated_chat_tool_blocks_are_not_replaced_by_visual_search(
    mock_router, mock_rag, mock_suggestion, mock_client
):
    """Forward validated uploads to the tool and retain its final image in SSE."""
    service = OrchestrationService(mock_router, mock_rag, mock_suggestion, mock_client)
    request = MagicMock()
    attachments = [object()]
    block = {'type': 'image_block', 'provider': 'generated_image', 'imageUrl': 'https://example.com/private.png'}
    observed = {}
    async def llm_stream(*args, **kwargs):
        observed.update(kwargs)
        yield 'event: answer_blocks\ndata: ' + json.dumps([block]) + '\n\n'
        yield 'event: accumulator\ndata: ' + json.dumps({'accumulator': '', 'generated_blocks': [block]}) + '\n\n'
    service._node_llm_stream = llm_stream
    with patch('memory_store.get_global_store', return_value=None), \
         patch('services.compeer_scheduler.set_last_interaction_time', new_callable=AsyncMock), \
         patch('backend.services.orchestration_service.async_evaluate_and_update_state', new_callable=AsyncMock), \
         patch('backend.services.orchestration_service.classify_dialogue_policy', new_callable=AsyncMock, return_value=ResponsePolicy(task_intent=TaskIntent.ANSWER_EXAM, answer_depth=AnswerDepth.DIRECT, tone=ResponseTone.PLAIN, structure=ResponseStructure.SHORT, followup_mode=FollowupMode.NONE, legacy_policy='NORMAL')), \
         patch.object(service, '_node_prompt_assembly', new_callable=AsyncMock, return_value=[]), \
         patch.object(service.visual_answer_service, 'build_answer_blocks', new_callable=AsyncMock) as visual_search:
        events = [event async for event in service.execute(
            [{'role': 'user', 'content': '請幫我製作教學圖片'}], 'tool-integration', False, False, False,
            100, 0.7, 0.9, 1.0, request, 'u1', image_attachments=attachments, interface_language='zh-TW')]
    assert observed['image_attachments'] is attachments
    assert observed['interface_language'] == 'zh-TW'
    assert 'private.png' in ''.join(events)
    assert 'data: [DONE]' in ''.join(events)
    visual_search.assert_not_awaited()
