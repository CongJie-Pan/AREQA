"""Image candidate selection mixin for visual answer enrichment.

This mixin converts provider candidates into verified image blocks and keeps the
selection path fail-soft. Structured logs emitted here use safe provider/domain,
slot, count, and reason metadata only.
"""

from __future__ import annotations

import httpx

import logging
from typing import Any
from urllib.parse import urljoin, urlparse

from config import settings
from services.visual_answer.constants import _IMAGE_META_PATTERN, _NEGATIVE_CACHE_TTL_SECONDS
from services.visual_answer.models import ImageBlock, ImageCandidate
from services.visual_grounding_agent import VisualBrief

logger = logging.getLogger(__name__)


class VisualAnswerSelectionMixin:
    """Select and convert normalized visual candidates into image blocks."""

    async def _select_image_block(
        self,
        candidates: list[ImageCandidate],
        query: str,
        provider: str,
        conversation_id: str,
        visual_intent_text: str = "",
        model_client: Any = None,
        visual_brief: VisualBrief | None = None,
    ) -> ImageBlock | None:
        """Select the strongest grounded candidate using metadata and an agent."""

        blocks = await self._select_image_blocks(
            candidates,
            query,
            provider,
            conversation_id,
            visual_intent_text,
            model_client,
            visual_brief,
            limit=1,
        )
        return blocks[0] if blocks else None

    async def _select_image_blocks(
        self,
        candidates: list[ImageCandidate],
        query: str,
        provider: str,
        conversation_id: str,
        visual_intent_text: str = "",
        model_client: Any = None,
        visual_brief: VisualBrief | None = None,
        *,
        limit: int = 1,
    ) -> list[ImageBlock]:
        """Select grounded candidates for downstream understanding retries.

        Args:
            candidates: Provider-normalized image metadata.
            query: Search query used for metadata scoring.
            provider: Stable provider identifier for logs.
            conversation_id: Correlation id for safe structured logs.
            visual_intent_text: Bounded visual intent used by the grounding
                agent. This is not logged.
            model_client: Optional OpenAI-compatible model client.
            visual_brief: Optional preflight brief for stricter grounding.
            limit: Maximum accepted image blocks to return.

        Returns:
            Ordered image blocks accepted by cheap scoring and visual grounding.

        Side Effects:
            May call the visual grounding agent. Logs only safe provider,
            count, score, and reason metadata.
        """

        scored = [
            (self._heuristic_score(candidate, query), candidate)
            for candidate in candidates
            if self._is_safe_candidate(candidate)
        ]
        if not scored:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=no_safe_candidates provider=%s candidate_count=%s threshold=0.40",
                conversation_id,
                provider,
                len(candidates),
            )
            return []
        scored.sort(key=lambda item: item[0], reverse=True)
        score, candidate = scored[0]
        self._log_candidate_decision(
            conversation_id=conversation_id,
            provider=provider,
            candidate=candidate,
            candidate_count=len(candidates),
            safe_candidate_count=len(scored),
            top_score=score,
            threshold=0.4,
        )
        if score < 0.4:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=low_score provider=%s top_score=%.2f threshold=0.40",
                conversation_id,
                provider,
                score,
            )
            return []

        selected_blocks: list[ImageBlock] = []
        max_grounding_candidates = (
            max(
                limit + 1,
                int(getattr(settings, "visual_preflight_grounding_max_candidates", 1)),
            )
            if visual_brief is not None
            else max(1, int(getattr(settings, "visual_grounding_max_candidates", 3)))
        )
        for candidate_score, candidate in scored[:max_grounding_candidates]:
            if candidate_score < 0.4:
                continue
            decision = await self._visual_grounding_agent.evaluate(
                client=model_client,
                model=settings.model_policy_classifier,
                visual_intent=visual_intent_text or query,
                candidate=candidate,
                conversation_id=conversation_id,
                visual_brief=visual_brief,
            )
            if decision.accepted and not (visual_brief is not None and decision.reason == "model_unavailable"):
                selected_blocks.append(
                    self._candidate_to_block(candidate, candidate_score, len(selected_blocks) + 1)
                )
                if len(selected_blocks) >= max(1, limit):
                    break
                continue
            logger.info(
                "visual.candidate_rejected conversation_id=%s provider=%s reason=grounding_%s expected_type=%s candidate_type=%s",
                conversation_id,
                provider,
                decision.reason,
                decision.expected_visual_type,
                decision.candidate_visual_type,
            )

        if not selected_blocks:
            logger.info(
                "visual.image_omitted conversation_id=%s reason=grounding_rejected provider=%s checked_candidate_count=%s threshold=0.40",
                conversation_id,
                provider,
                min(max_grounding_candidates, len(scored)),
            )
            return []

        block = selected_blocks[0]
        logger.info(
            "visual.image_selected conversation_id=%s source_domain=%s provider=%s confidence_bucket=%s",
            conversation_id,
            block.source_domain,
            block.provider,
            "high" if block.match_confidence >= 0.65 else "medium",
        )
        return selected_blocks

    @staticmethod
    def _log_candidate_decision(
        *,
        conversation_id: str,
        provider: str,
        candidate: ImageCandidate,
        candidate_count: int,
        safe_candidate_count: int,
        top_score: float,
        threshold: float,
    ) -> None:
        """Log safe candidate-ranking metadata for image retrieval debugging.

        The event intentionally excludes raw search queries, user prompts,
        model output, and full image/source URLs. It records only the provider,
        source domain, license label, dimension bucket, candidate counts, and
        score threshold needed to explain selection or low-score omission.
        """

        domain = urlparse(candidate.source_url).netloc.replace("www.", "") or "unknown"
        if candidate.width and candidate.height:
            if candidate.width >= 800 and candidate.height >= 400:
                dimension_bucket = "large"
            elif candidate.width >= 400 and candidate.height >= 250:
                dimension_bucket = "medium"
            else:
                dimension_bucket = "small"
        else:
            dimension_bucket = "unknown"
        logger.info(
            "visual.candidate_top_scored conversation_id=%s provider=%s candidate_count=%s safe_candidate_count=%s top_score=%.2f threshold=%.2f source_domain=%s license=%s dimension_bucket=%s",
            conversation_id,
            provider,
            candidate_count,
            safe_candidate_count,
            top_score,
            threshold,
            domain,
            candidate.license or "unknown",
            dimension_bucket,
        )

    async def _block_from_result(
        self,
        client: httpx.AsyncClient,
        result: dict[str, Any],
        index: int,
    ) -> ImageBlock | None:
        """Extract one OpenGraph/Twitter image from a search result page."""

        source_url = str(result.get("url") or "").strip()
        parsed_source = urlparse(source_url)
        if parsed_source.scheme not in {"http", "https"} or not parsed_source.netloc:
            return None

        response = await client.get(source_url)
        if response.status_code >= 400:
            return None

        html = response.text[:80_000]
        match = _IMAGE_META_PATTERN.search(html)
        if not match:
            return None

        image_url = urljoin(source_url, match.group(1).strip())
        parsed_image = urlparse(image_url)
        if parsed_image.scheme not in {"http", "https"} or not parsed_image.netloc:
            return None

        title = self._clean_text(str(result.get("title") or "") or self._extract_title(html))
        domain = parsed_source.netloc.replace("www.", "")
        caption = title or f"Illustration from {domain}"
        return ImageBlock(
            slot_id=f"visual-{index}",
            topic=caption[:80],
            purpose="diagram",
            image_url=image_url,
            thumbnail_url=image_url,
            source_url=source_url,
            source_domain=domain,
            caption=caption[:140],
            provider="og_image",
            license="unknown",
            attribution_caption=caption[:140],
            safety_status="pass",
            match_confidence=0.6,
            heuristic_score=0.45,
            pedagogical_score=0.0,
        )

    @staticmethod
    def _log_image_block_selected(conversation_id: str, block: ImageBlock, stage: str) -> None:
        """Emit opt-in visual diagnostics without logging image URLs or prompts."""

        if not settings.enable_visual_answer_debug_logs:
            return
        logger.info(
            "visual.image_block_ready conversation_id=%s stage=%s provider=%s source_domain=%s has_explanatory_caption=%s pedagogical_score=%.2f",
            conversation_id,
            stage,
            block.provider,
            block.source_domain or "unknown",
            bool(block.explanatory_caption),
            block.pedagogical_score,
        )

    def _candidate_to_block(self, candidate: ImageCandidate, score: float, index: int) -> ImageBlock:
        """Convert a provider candidate into the frontend image block model."""

        parsed = urlparse(candidate.source_url)
        domain = parsed.netloc.replace("www.", "")
        caption = candidate.caption or candidate.title or f"Illustration from {domain}"
        pedagogical_score = self._pedagogical_score(candidate)
        display_image_url = self._display_image_url(candidate)
        return ImageBlock(
            slot_id=f"visual-{index}",
            topic=(candidate.title or caption)[:80],
            purpose="diagram",
            image_url=candidate.image_url,
            thumbnail_url=display_image_url,
            source_url=candidate.source_url,
            source_domain=domain,
            caption=caption[:140],
            provider=candidate.provider,
            license=candidate.license or "unknown",
            license_url=candidate.license_url,
            creator=candidate.creator,
            attribution_string=candidate.attribution_string,
            attribution_caption=caption[:140],
            width=candidate.width,
            height=candidate.height,
            safety_status="pass",
            match_confidence=score,
            heuristic_score=score,
            pedagogical_score=pedagogical_score,
        )
