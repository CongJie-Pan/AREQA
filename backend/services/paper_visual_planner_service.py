"""Plan semantically useful visuals for automatic PDF paper explanations.

The planner reads a bounded structural map of an uploaded PDF and decides which
pages should be rendered as answer visuals. It may use a model for semantic
selection, but rendering and cropping remain owned by ``PdfVisualExtractionService``
so untrusted model output cannot directly control pixels or file system writes.
"""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
import logging
import re
from typing import Any

from config import settings


logger = logging.getLogger(__name__)

_FIGURE_CAPTION_PATTERN = re.compile(
    r"\b(?:fig(?:ure)?\.?|table)\s*\d+[A-Za-z]?\b[^\n]{0,220}|(?:圖|表)\s*\d+[^\n]{0,220}",
    re.IGNORECASE,
)
_SECTION_PATTERN = re.compile(
    r"\b(?:abstract|introduction|related work|background|method|methodology|model|architecture|"
    r"experiments?|evaluation|results?|discussion|conclusion|limitations?)\b",
    re.IGNORECASE,
)
_RESULT_TERMS = (
    "result",
    "results",
    "experiment",
    "experiments",
    "evaluation",
    "bleu",
    "accuracy",
    "benchmark",
    "table",
    "ablation",
    "performance",
    "結果",
    "實驗",
    "实验",
    "評估",
    "评估",
)
_METHOD_TERMS = (
    "method",
    "model",
    "architecture",
    "attention",
    "algorithm",
    "framework",
    "diagram",
    "figure",
    "方法",
    "模型",
    "架構",
    "架构",
    "注意力",
)


@dataclass(frozen=True, slots=True)
class PaperVisualPlanItem:
    """One model- or fallback-selected visual target for a PDF paper answer.

    Args:
        page_number: One-based page number to render.
        answer_section: Paper-explanation section where the visual should be
            introduced by the main answer model.
        visual_type: Bounded purpose label such as ``architecture`` or
            ``results_table``.
        teaching_caption: Short user-facing explanation of why this visual helps
            understand the paper.
        rationale: Internal bounded reason for logs/tests and prompt inventory.
        source: ``model`` or ``fallback``.

    Side Effects:
        None.
    """

    page_number: int
    answer_section: str
    visual_type: str
    teaching_caption: str
    rationale: str
    source: str = "model"


@dataclass(frozen=True, slots=True)
class _PaperPageContext:
    """Bounded text metadata for one PDF page used by the planner."""

    page_number: int
    text_excerpt: str
    captions: tuple[str, ...]
    section_hint: str


class PaperVisualPlannerService:
    """Select paper visuals before deterministic PDF rendering.

    The service scans pages for captions and section hints, then asks a bounded
    JSON-producing model to choose the visuals that best support an automatic
    paper explanation. If the model is unavailable, slow, or returns invalid
    JSON, the deterministic fallback prioritizes result tables/figures and core
    method diagrams. Logs contain only counts, reason codes, filenames, and page
    numbers; raw PDF text and model output are never logged.
    """

    def __init__(
        self,
        *,
        max_pages_scanned: int | None = None,
        context_chars: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        """Initialize planner limits from settings.

        Args:
            max_pages_scanned: Maximum pages to inspect from the PDF.
            context_chars: Maximum total page-map characters sent to the model.
            timeout_seconds: Foreground model timeout.

        Side Effects:
            None.
        """

        self.max_pages_scanned = max(
            1,
            min(
                int(max_pages_scanned or settings.pdf_paper_visual_planner_max_pages_scanned),
                40,
            ),
        )
        self.context_chars = max(
            1000,
            min(int(context_chars or settings.pdf_paper_visual_planner_context_chars), 30000),
        )
        self.timeout_seconds = max(
            0.2,
            min(float(timeout_seconds or settings.pdf_paper_visual_planner_timeout_seconds), 8.0),
        )

    async def plan_visuals(
        self,
        *,
        pdf_bytes: bytes,
        filename: str,
        conversation_id: str,
        client: Any = None,
        max_visuals: int = 2,
    ) -> tuple[PaperVisualPlanItem, ...]:
        """Return selected visual targets for an automatic paper explanation.

        Args:
            pdf_bytes: Validated upload bytes for the current request.
            filename: Sanitized display filename. Logged only as a filename.
            conversation_id: Correlation id for safe structured logs.
            client: Chat-completions compatible model client. When absent, the
                deterministic fallback is used.
            max_visuals: Maximum selected visuals returned.

        Returns:
            Bounded visual plan items. Empty means no suitable page map was
            available or visuals are disabled upstream.

        Side Effects:
            Reads PDF text/layout in memory and may call a planner model. Emits
            privacy-safe ``paper_visual.planner_*`` structured logs.
        """

        bounded_max_visuals = max(0, min(int(max_visuals or 0), 3))
        if bounded_max_visuals <= 0:
            return ()

        try:
            pages = await asyncio.to_thread(self._extract_page_contexts, pdf_bytes)
        except Exception as exc:
            logger.info(
                "paper_visual.planner_unavailable conversation_id=%s filename=%s reason=%s",
                conversation_id,
                filename,
                type(exc).__name__,
            )
            return ()

        logger.info(
            "paper_visual.planner_started conversation_id=%s filename=%s page_count=%s max_visuals=%s model_enabled=%s",
            conversation_id,
            filename,
            len(pages),
            bounded_max_visuals,
            bool(client and getattr(settings, "enable_pdf_paper_visual_planner", True)),
        )
        if not pages:
            return ()

        if client and getattr(settings, "enable_pdf_paper_visual_planner", True):
            try:
                model_items = await asyncio.wait_for(
                    self._plan_with_model(
                        pages=pages,
                        filename=filename,
                        client=client,
                        max_visuals=bounded_max_visuals,
                    ),
                    timeout=self.timeout_seconds,
                )
                sanitized = self._sanitize_plan_items(model_items, pages, bounded_max_visuals, source="model")
                if sanitized:
                    self._log_completed(conversation_id, filename, sanitized, "model")
                    return sanitized
            except Exception as exc:
                logger.info(
                    "paper_visual.planner_model_failed conversation_id=%s filename=%s reason=%s",
                    conversation_id,
                    filename,
                    type(exc).__name__,
                )

        fallback = self._fallback_plan(pages, bounded_max_visuals)
        self._log_completed(conversation_id, filename, fallback, "fallback")
        return fallback

    def _extract_page_contexts(self, pdf_bytes: bytes) -> tuple[_PaperPageContext, ...]:
        """Extract bounded page text, captions, and section hints."""

        import fitz  # type: ignore[import-not-found]

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            page_count = int(getattr(document, "page_count", 0) or len(document))
            contexts: list[_PaperPageContext] = []
            for page_index in range(min(page_count, self.max_pages_scanned)):
                page = document.load_page(page_index)
                text = re.sub(r"\s+", " ", page.get_text("text") or "").strip()
                excerpt = text[:1200]
                captions = tuple(match.group(0).strip()[:240] for match in _FIGURE_CAPTION_PATTERN.finditer(text))[:6]
                section_match = _SECTION_PATTERN.search(text)
                contexts.append(
                    _PaperPageContext(
                        page_number=page_index + 1,
                        text_excerpt=excerpt,
                        captions=captions,
                        section_hint=section_match.group(0).lower() if section_match else "",
                    )
                )
            return tuple(contexts)
        finally:
            document.close()

    async def _plan_with_model(
        self,
        *,
        pages: tuple[_PaperPageContext, ...],
        filename: str,
        client: Any,
        max_visuals: int,
    ) -> list[dict[str, Any]]:
        """Ask the model for strict JSON visual selections."""

        page_map = self._page_map_for_prompt(pages)
        prompt = (
            "You are AREQA's Paper Visual Planner. Select the most useful PDF pages/figures/tables "
            "for a teaching-style explanation of the uploaded paper. Prefer visuals that carry the "
            "paper's method, architecture, key mechanism, experimental results, or result tables. "
            "Return strict JSON only: {\"selected_visuals\":[{\"page_number\":number,"
            "\"answer_section\":string,\"visual_type\":\"architecture|method_diagram|results_chart|"
            "results_table|mechanism|other\",\"teaching_caption\":string,\"rationale\":string}]}. "
            f"Select at most {max_visuals} visuals. Do not invent pages not present in the page map. "
            "Keep teaching_caption under 180 characters and rationale under 160 characters.\n\n"
            f"Filename: {filename}\n"
            f"Page map:\n{page_map}"
        )
        response = await client.chat.completions.create(
            model=settings.model_policy_classifier,
            messages=[
                {"role": "system", "content": "Return valid JSON only. Never include markdown fences."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=700,
        )
        content = ""
        if getattr(response, "choices", None):
            content = str(response.choices[0].message.content or "").strip()
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            selected = parsed.get("selected_visuals", [])
        else:
            selected = parsed
        return selected if isinstance(selected, list) else []

    def _page_map_for_prompt(self, pages: tuple[_PaperPageContext, ...]) -> str:
        """Return bounded JSON lines for model planning."""

        lines: list[str] = []
        used_chars = 0
        for page in pages:
            payload = {
                "page_number": page.page_number,
                "section_hint": page.section_hint,
                "captions": list(page.captions),
                "text_excerpt": page.text_excerpt,
            }
            line = json.dumps(payload, ensure_ascii=False)
            if used_chars + len(line) > self.context_chars:
                break
            lines.append(line)
            used_chars += len(line)
        return "\n".join(lines)

    def _sanitize_plan_items(
        self,
        raw_items: list[dict[str, Any]],
        pages: tuple[_PaperPageContext, ...],
        max_visuals: int,
        *,
        source: str,
    ) -> tuple[PaperVisualPlanItem, ...]:
        """Validate model plan output against available pages and bounds."""

        available_pages = {page.page_number for page in pages}
        selected: list[PaperVisualPlanItem] = []
        seen_pages: set[int] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                page_number = int(item.get("page_number"))
            except (TypeError, ValueError):
                continue
            if page_number not in available_pages or page_number in seen_pages:
                continue
            seen_pages.add(page_number)
            selected.append(
                PaperVisualPlanItem(
                    page_number=page_number,
                    answer_section=self._bounded_text(item.get("answer_section"), "論文重點圖解", 80),
                    visual_type=self._bounded_visual_type(item.get("visual_type")),
                    teaching_caption=self._bounded_text(
                        item.get("teaching_caption"),
                        "這張圖是理解論文方法或結果的關鍵視覺線索。",
                        180,
                    ),
                    rationale=self._bounded_text(item.get("rationale"), "planner_selected", 160),
                    source=source,
                )
            )
            if len(selected) >= max_visuals:
                break
        return tuple(selected)

    def _fallback_plan(
        self,
        pages: tuple[_PaperPageContext, ...],
        max_visuals: int,
    ) -> tuple[PaperVisualPlanItem, ...]:
        """Select result-heavy and method-heavy pages without model support."""

        scored = sorted(
            ((self._fallback_page_score(page), page) for page in pages),
            key=lambda item: item[0],
            reverse=True,
        )
        raw_items: list[dict[str, Any]] = []
        for score, page in scored:
            if score <= 0:
                continue
            text = f"{page.section_hint} {' '.join(page.captions)} {page.text_excerpt}".lower()
            is_result = any(term in text for term in _RESULT_TERMS)
            visual_type = "results_table" if "table" in text or "表" in text else "results_chart" if is_result else "method_diagram"
            answer_section = "實驗結果與關鍵數據" if is_result else "方法與模型架構"
            teaching_caption = (
                "這張圖表承載論文的實驗結果或關鍵數據，適合用來說明模型表現與作者主張。"
                if is_result
                else "這張圖呈現論文的方法、模型架構或核心機制，適合先用來建立整體理解。"
            )
            raw_items.append(
                {
                    "page_number": page.page_number,
                    "answer_section": answer_section,
                    "visual_type": visual_type,
                    "teaching_caption": teaching_caption,
                    "rationale": "fallback_ranked_by_caption_and_section_terms",
                }
            )
        return self._sanitize_plan_items(raw_items, pages, max_visuals, source="fallback")

    @staticmethod
    def _fallback_page_score(page: _PaperPageContext) -> int:
        """Return deterministic semantic score for a candidate page."""

        text = f"{page.section_hint} {' '.join(page.captions)} {page.text_excerpt}".lower()
        score = 0
        score += sum(6 for term in _RESULT_TERMS if term in text)
        score += sum(4 for term in _METHOD_TERMS if term in text)
        score += len(page.captions) * 5
        return score

    @staticmethod
    def _bounded_text(value: Any, fallback: str, max_length: int) -> str:
        """Return normalized bounded text for planner-owned metadata."""

        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return (text or fallback)[:max_length]

    @staticmethod
    def _bounded_visual_type(value: Any) -> str:
        """Return allowlisted visual purpose label."""

        visual_type = str(value or "").strip().lower()
        allowed = {"architecture", "method_diagram", "results_chart", "results_table", "mechanism", "other"}
        return visual_type if visual_type in allowed else "other"

    @staticmethod
    def _log_completed(
        conversation_id: str,
        filename: str,
        items: tuple[PaperVisualPlanItem, ...],
        source: str,
    ) -> None:
        """Emit the stable planner completion log without raw PDF text."""

        logger.info(
            "paper_visual.planner_completed conversation_id=%s filename=%s source=%s selected_count=%s pages=%s",
            conversation_id,
            filename,
            source,
            len(items),
            ",".join(str(item.page_number) for item in items) or "none",
        )
