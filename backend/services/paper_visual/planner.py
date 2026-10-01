"""Plan semantically useful visuals for automatic PDF paper explanations.

The planner reads a bounded structural map of an uploaded PDF and decides which
pages should be rendered as answer visuals. It may use a model for semantic
selection, but rendering and cropping remain owned by ``PdfVisualExtractionService``
so untrusted model output cannot directly control pixels or file system writes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from config import settings
from services.paper_visual import fallback, validation
from services.paper_visual.constants import (
    _ABLATION_CAPTION_TERMS,
    _DATASET_CAPTION_TERMS,
    _FALLBACK_SECTION_ORDER,
    _FIGURE_CAPTION_PATTERN,
    _MAIN_RESULT_CAPTION_TERMS,
    _METHOD_TERMS,
    _OVERVIEW_CAPTION_TERMS,
    _REQUIRED_FALLBACK_SECTIONS,
    _RESULT_CAPTION_TERMS,
    _RESULT_TERMS,
    _SECTION_KEYWORDS,
    _SECTION_LABELS,
    _SECTION_PATTERN,
)
from services.paper_visual.models import PaperVisualPlanItem, _PaperPageContext

logger = logging.getLogger(__name__)




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
            min(int(max_pages_scanned or settings.pdf_paper_visual_planner_max_pages_scanned), 40),
        )
        self.context_chars = max(1000, min(int(context_chars or settings.pdf_paper_visual_planner_context_chars), 30000))
        self.timeout_seconds = max(0.2, min(float(timeout_seconds or settings.pdf_paper_visual_planner_timeout_seconds), 8.0))

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

        bounded_max_visuals = max(0, min(int(max_visuals or 0), 4))
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
            "For broad paper explanations, cover research method, experiment design/process, and "
            "experimental results when possible. When both main results and ablations are available, "
            "select the main results first, then the ablation if visual capacity remains. "
            "Prefer a pipeline, method, or framework overview before example-only figures when both are available. "
            "Return strict JSON only: {\"selected_visuals\":[{\"page_number\":number,"
            "\"answer_section\":string,\"visual_type\":\"architecture|method_diagram|results_chart|"
            "results_table|main_results_table|ablation_table|mechanism|other\",\"target_caption\":string,"
            "\"teaching_caption\":string,\"rationale\":string}]}. "
            f"Select at most {max_visuals} visuals. Do not invent pages not present in the page map. "
            "When the page map has a relevant Figure/Table caption, copy that caption into target_caption "
            "so the renderer can crop the intended figure/table. Leave target_caption empty only if no caption fits. "
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


    @staticmethod
    def _log_completed(
        conversation_id: str,
        filename: str,
        items: tuple[PaperVisualPlanItem, ...],
        source: str,
    ) -> None:
        """Emit the stable planner completion log without raw PDF text."""

        logger.info(
            "paper_visual.planner_completed conversation_id=%s filename=%s source=%s selected_count=%s pages=%s sections=%s visual_types=%s",
            conversation_id,
            filename,
            source,
            len(items),
            ",".join(str(item.page_number) for item in items) or "none",
            ",".join(item.answer_section for item in items) or "none",
            ",".join(item.visual_type for item in items) or "none",
        )

    _sanitize_plan_items = staticmethod(validation._sanitize_plan_items)
    _bounded_text = staticmethod(validation._bounded_text)
    _normalize_answer_section = staticmethod(validation._normalize_answer_section)
    _bounded_visual_type = staticmethod(validation._bounded_visual_type)
    _bounded_target_caption = staticmethod(validation._bounded_target_caption)
    _normalize_caption_match_text = staticmethod(validation._normalize_caption_match_text)
    _fallback_plan = staticmethod(fallback._fallback_plan)
    _fallback_candidate_rank = staticmethod(fallback._fallback_candidate_rank)
    _fallback_fill_rank = staticmethod(fallback._fallback_fill_rank)
    _fallback_item_for_page = staticmethod(fallback._fallback_item_for_page)
    _best_fallback_visual = staticmethod(fallback._best_fallback_visual)
    _is_figure_caption = staticmethod(fallback._is_figure_caption)
    _is_table_caption = staticmethod(fallback._is_table_caption)
    _first_caption = staticmethod(fallback._first_caption)
    _fallback_teaching_caption = staticmethod(fallback._fallback_teaching_caption)
    _fallback_page_score = staticmethod(fallback._fallback_page_score)
