"""Shared imports for orchestration service mixins."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import Request

from config import settings
from services.memory.gate import classify_user_message
from core import AgentEvent, ConversationRunState, EventType, SearchMode
from policies import CapabilityPolicy, SearchDecision, SearchReason
from services.query_policy.classifier import (
    AttachmentTask,
    apply_pdf_auto_explain_guardrail,
    count_pdf_attachments,
    default_response_policy,
    paper_auto_explain_instruction,
    response_policy_from_legacy,
)
from services.orchestration.trace import TurnLatencyTrace
from services.orchestration.turn_plan import TurnPlan
from services.orchestration.intake import chat_avatar_key as _chat_avatar_key
from services.orchestration.utils import (
    _build_valid_web_sources,
    _localized_greeting_reply,
    classify_dialogue_policy,
    parse_and_decompose_query,
    reorder_for_attention,
)

logger = logging.getLogger(__name__)
InterfaceLanguage = str

class OrchestrationVisualMixin:
    _MISSING_VISUAL_ATTACHMENT_PATTERN = re.compile(
        r"(?:"
        r"這(?:張|兩張|幾張)?圖|"
        r"这些?图|這個圖片|这个图片|"
        r"附(?:上|的).{0,8}(?:圖|图片|image)|"
        r"貼(?:上|的).{0,8}(?:圖|图片|image)|"
        r"uploaded image|attached image|this image|these images|the image above"
        r")",
        re.IGNORECASE,
    )

    @classmethod
    def _mentions_missing_visual_attachment(cls, user_msg: str) -> bool:
        """Return whether a text-only turn appears to ask about an attached image.

        Args:
            user_msg: Latest user text. The caller must not log this value.

        Returns:
            True when the wording references user-provided images strongly
            enough that answering without attachments would invite visual
            hallucination.

        Side Effects:
            None.
        """

        return bool(cls._MISSING_VISUAL_ATTACHMENT_PATTERN.search(user_msg or ""))

    @classmethod
    def _add_missing_visual_attachment_instruction(
        cls,
        messages: List[Dict[str, Any]],
        user_msg: str,
    ) -> tuple[List[Dict[str, Any]], bool]:
        """Prevent visual guessing when the turn references absent attachments.

        Args:
            messages: Prompt messages prepared for the main answer model.
            user_msg: Latest user text used only for bounded intent detection.

        Returns:
            A tuple of updated messages and whether the guard was applied.

        Side Effects:
            Mutates the first system message in ``messages`` or inserts one if
            none exists. The instruction contains no raw user text, prompts,
            model output, credentials, or file metadata.
        """

        if not cls._mentions_missing_visual_attachment(user_msg):
            return messages, False

        instruction = (
            "【缺少圖片附件邊界】使用者的文字似乎要求解讀已貼上或附上的圖片，"
            "但本回合後端沒有收到任何可讀取的圖片、PDF 或附件內容。"
            "不得假裝看過圖片，不得推測左圖、右圖、上圖、下圖或圖片細節。"
            "請先用一句簡短文字說明目前沒有收到可查看的圖片，"
            "再請使用者重新上傳或貼上圖片；若仍可根據純文字問題提供一般概念說明，"
            "必須明確標示那只是一般說明，不是對圖片內容的解讀。"
        )
        for message in messages:
            if message.get("role") == "system" and isinstance(message.get("content"), str):
                message["content"] = f'{message["content"]}\n\n{instruction}'
                return messages, True
        messages.insert(0, {"role": "system", "content": instruction})
        return messages, True

    async def _node_intent_routing(self, query: str) -> AsyncGenerator[str, None]:
        """
        Perform fast intent checking to reject harmful or out-of-scope queries (Currently Disabled).

        Args:
            query (str): The user query to evaluate.

        Yields:
            str: SSE formatted events if rejection occurs.
        """
        if not query or not self.client:
            return

        # Fast intent check to quickly reject truly harmful or out-of-scope queries
        # Router LLM is currently DISABLED. All queries pass through.
        # If re-enabled in the future, the prompt should be updated to reflect
        # the new universal learning scope of AREQA.
        pass

    @staticmethod
    def _attach_to_latest_user_message(
        messages: List[Dict[str, Any]], attachments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Attach request-scoped multimodal content only to the latest user turn.

        Args:
            messages (List[Dict[str, Any]]): The list of conversation messages.
            attachments (List[Dict[str, Any]]): The list of attachment data dictionaries.

        Returns:
            List[Dict[str, Any]]: The updated list of messages with attachments embedded.
        """
        if not attachments:
            return messages

        for message in reversed(messages):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            text = content if isinstance(content, str) and content.strip() else "請分析我附加的檔案。"
            message["content"] = [{"type": "text", "text": text}, *attachments]
            break
        return messages

    @staticmethod
    def _add_attachment_grounding_instruction(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Require answers to be grounded in content actually read from attachments.

        Args:
            messages (List[Dict[str, Any]]): The list of conversation messages.

        Returns:
            List[Dict[str, Any]]: The updated list of messages with grounding instructions added to the system prompt.
        """
        instruction = (
            "【附件事實邊界】本回合包含使用者附件。只能根據實際可讀取的附件內容回答；"
            "不得根據檔名、作者、建立時間、metadata 或常識猜測文件正文。"
            "若附件內容為空、解析失敗或只有 metadata，必須明確告知目前無法讀取文件內容，"
            "並請使用者改傳可讀版本。"
        )
        for message in messages:
            if message.get("role") == "system" and isinstance(message.get("content"), str):
                message["content"] = f'{message["content"]}\n\n{instruction}'
                return messages
        messages.insert(0, {"role": "system", "content": instruction})
        return messages

    @staticmethod
    def _add_paper_auto_explain_instruction(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Append the automatic PDF paper overview task to the system prompt.

        Args:
            messages: Prompt messages after the attachment grounding boundary
                has been applied.

        Returns:
            Messages with a system-level paper overview instruction.

        Side Effects:
            None. The caller logs ``paper.auto_explain_policy_selected`` with
            safe decision metadata before this instruction is applied.
        """

        instruction = paper_auto_explain_instruction()
        for message in messages:
            if message.get("role") == "system" and isinstance(message.get("content"), str):
                message["content"] = f'{message["content"]}\n\n{instruction}'
                return messages
        messages.insert(0, {"role": "system", "content": instruction})
        return messages

    @staticmethod
    async def _extract_attachment_visual_candidates(
        attachment_visual_sources: List[Dict[str, Any]],
        conversation_id: str,
        model_client: Any = None,
        use_paper_visual_planner: bool = False,
    ) -> List[Any]:
        """Render PDF visual candidates after the visual policy gate passes.

        Args:
            attachment_visual_sources: Request-scoped dictionaries containing a
                sanitized filename and PDF bytes from attachment validation.
            conversation_id: Correlation id for safe structured logs.
            model_client: Optional chat-completions compatible client used by
                the paper visual planner for automatic paper explanations.
            use_paper_visual_planner: Whether to read the PDF page map and let
                the planner select semantically important visuals before local
                rendering. Targeted attachment tasks keep deterministic
                extraction only.

        Returns:
            A flat list of PDF visual candidates accepted by
            ``OutputImageService``.

        Side Effects:
            Runs local PDF rendering in worker threads. Logs only counts,
            filenames, correlation ids, and reason codes; never logs raw PDF
            text, prompts, rendered data URIs, or credentials.
        """

        if not getattr(settings, "enable_pdf_attachment_visuals", True):
            logger.info(
                "visual.attachment_pdf_extraction_skipped conversation_id=%s reason=disabled source_count=%s",
                conversation_id,
                len(attachment_visual_sources),
            )
            return []

        from services.paper_visual.planner import PaperVisualPlannerService
        from services.pdf_visual.extraction import PdfVisualExtractionService

        async def extract_one(source: Dict[str, Any]) -> List[Any]:
            filename = str(source.get("filename") or "attachment.pdf")
            pdf_bytes = source.get("pdf_bytes")
            if not isinstance(pdf_bytes, bytes) or not pdf_bytes:
                return []
            service = PdfVisualExtractionService()
            visual_plan = ()
            if use_paper_visual_planner:
                planner = PaperVisualPlannerService()
                visual_plan = await planner.plan_visuals(
                    pdf_bytes=pdf_bytes,
                    filename=filename,
                    conversation_id=conversation_id,
                    client=model_client,
                    max_visuals=service.max_candidates,
                )
            try:
                candidates = await asyncio.to_thread(
                    service.extract_candidates,
                    pdf_bytes=pdf_bytes,
                    filename=filename,
                    conversation_id=conversation_id,
                    visual_plan=visual_plan,
                )
            except Exception as exc:
                logger.info(
                    "visual.attachment_pdf_extraction_failed conversation_id=%s filename=%s reason=%s",
                    conversation_id,
                    filename,
                    type(exc).__name__,
                )
                return []
            return list(candidates)

        nested_candidates = await asyncio.gather(
            *(extract_one(source) for source in attachment_visual_sources[:3])
        )
        candidates = [candidate for group in nested_candidates for candidate in group]
        logger.info(
            "visual.attachment_pdf_candidates_ready conversation_id=%s source_count=%s candidate_count=%s planner_enabled=%s",
            conversation_id,
            len(attachment_visual_sources),
            len(candidates),
            use_paper_visual_planner,
        )
        return candidates

    @staticmethod
    def _add_verified_visual_instruction(
        messages: List[Dict[str, Any]],
        image_blocks: dict[str, Any],
        response_policy: Any = None,
    ) -> List[Dict[str, Any]]:
        """Add verified image inventory and integrated-answer marker rules.

        The main answer model owns the semantic placement of verified images.
        This instruction therefore treats image evidence as part of the answer
        material instead of a post-response attachment. The stable internal
        marker is stripped before public streaming and later converted into
        structured answer blocks; the prompt must not expose raw image URLs or
        ask the model to invent image metadata.

        Args:
            messages: Prompt messages assembled for the main answer model.
            image_blocks: Verified image inventory keyed by image slot id.
            response_policy: Optional structured response policy. When the user
                explicitly required visual support and no verified image is
                available, the prompt asks the model to briefly disclose that no
                reliable image can be provided instead of silently ignoring the
                explicit visual request.

        Returns:
            Prompt messages with visual inventory or no-image instructions.

        Side Effects:
            Mutates the first system message in ``messages`` or inserts one if
            none exists. The instruction contains no image URLs, raw user text,
            prompts, model output, or secrets.
        """

        instruction: str
        if not image_blocks:
            visual_support = getattr(
                getattr(response_policy, "visual_support", None),
                "value",
                getattr(response_policy, "visual_support", None),
            )
            required_image_notice = (
                "因為使用者明確要求圖片/圖解，但本回合沒有找到可驗證且可讀取的合適圖片，"
                "請在回答開頭或第一個自然段落中用一句簡短文字說明目前無法提供可靠圖片，"
                "然後改用文字、步驟、表格或 ASCII 示意來解釋；語氣保持中性，不要冗長道歉。"
                if visual_support == "REQUIRED"
                else ""
            )
            instruction = (
                "【已驗證圖片狀態】本回合沒有可用的已驗證圖片。"
                "不得輸出 <AREQA_IMAGE_SLOT .../>、[[AREQA_IMAGE_REQUEST ...]] 或 [[AREQA_VERIFIED_IMAGE ...]]；"
                "若需要視覺輔助，請只用文字描述，不要假裝已插入圖片。"
                f"{required_image_notice}"
            )
        else:
            inventory = [
                {
                    "id": slot_id,
                    "topic": block.topic,
                    "purpose": block.purpose,
                    "placement_section": getattr(block, "placement_section", ""),
                    "planner_hint": getattr(block, "planner_hint", ""),
                    "caption": block.caption,
                    "explanatory_caption": block.explanatory_caption,
                    "vision_summary": block.vision_summary,
                    "visible_elements": list(block.visible_elements),
                    "how_to_read": list(block.how_to_read),
                    "vision_confidence": block.vision_confidence,
                    "vision_limitations": list(block.vision_limitations),
                    "source_domain": block.source_domain,
                    "license": block.license,
                    "width": block.width,
                    "height": block.height,
                }
                for slot_id, block in image_blocks.items()
            ]
            verified_markers = [
                f'[[AREQA_VERIFIED_IMAGE id="{slot_id}"]]'
                for slot_id in image_blocks.keys()
            ]
            verified_marker_examples = "、".join(verified_markers)
            available_image_count = len(image_blocks)
            paper_section_instruction = (
                "如果這是論文總覽回答，且圖片清單可用 placement_section、purpose、caption "
                "對應「研究方法」、「實驗設計與過程」、「實驗結果」，"
                "這三個核心節各必須緊接一張已驗證 PDF 圖片；"
                "不要只滿足總張數，每個核心節都要有圖。"
                "如果「實驗結果」同時有主要結果與消融分析圖片，且回答包含「實驗結果與消融分析」，"
                "請在該節使用兩張結果圖片，先主要結果、再消融分析；"
                if available_image_count >= 3
                else ""
            )
            instruction = (
                "【已驗證圖片清單】以下圖片已由系統搜尋、驗證並讀圖；"
                "它們是本回合主回答素材的一部分，不是回答後的附件。"
                "你只能使用清單中的 id，不能自行編造圖片、URL 或來源。"
                "你必須把最相關的已驗證圖片整合進教學流程；"
                f"{paper_section_instruction}"
                "若有多張圖片，請依照圖片清單中的章節提示分散到對應段落，"
                "特別是論文總覽回答應優先覆蓋研究動機與目的、研究方法、實驗設計與過程、實驗結果。"
                "在最適合的位置先寫 1 至 2 句完整導圖文字，"
                "明確使用「下圖」、「圖中」或對應語言的圖片引用。"
                "導圖文字必須至少引用 caption、vision_summary、visible_elements 或 how_to_read 中一項可見特徵，"
                "不得逐字複製系統提供的圖片用途或教學提示句；"
                "並且導圖段落後必須緊接著輸出標記，也就是對應圖片的標記；可用標記為："
                f"{verified_marker_examples}。"
                "圖片後的文字必須接續引用或延伸圖片內容，不能像圖片不存在一樣繼續純文字回答。"
                "請優先使用這個自然教學結構："
                "「下圖是一張 {topic 或 vision_summary 所描述的圖}，呈現 {與使用者問題最相關的核心過程或關係}。"
                "你可以先看圖中的 {visible_elements 中 2 至 3 個具體元素}，"
                "再依照 {how_to_read 中前 2 至 3 個讀圖步驟} 讀圖，"
                "理解 {這張圖如何幫助回答使用者問題}。」"
                "請用使用者回答語言重寫這段導讀，不要照抄英文欄位；"
                "不得把標記直接放在開場摘要、標題、清單或表格後。"
                "若 vision_summary 為空，才退回依據圖片 caption/source 做有限解釋；"
                "不得輸出 <AREQA_IMAGE_SLOT .../> 或 [[AREQA_IMAGE_REQUEST ...]]。"
                f"\n<verified_images>{json.dumps(inventory, ensure_ascii=False)}</verified_images>"
            )

        for message in messages:
            if message.get("role") == "system" and isinstance(message.get("content"), str):
                message["content"] = f'{message["content"]}\n\n{instruction}'
                return messages
        messages.insert(0, {"role": "system", "content": instruction})
        return messages
