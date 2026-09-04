"""Factory wiring for durable memory ingestion services.

This module owns feature-flag driven construction of optional extraction and
semantic-analysis agents. Logs use only mode, model name, timeout, confidence,
privacy-acknowledgement, and client-availability metadata; raw user evidence,
prompts, model output, credentials, and tokens must never be logged here.
"""

from __future__ import annotations

import logging
from typing import Any

from config import settings


logger = logging.getLogger(__name__)


def create_memory_ingestion_service_impl(
    service_cls: type,
    store: Any,
    *,
    client: Any = None,
) -> Any:
    """Create a configured memory ingestion service instance.

    Args:
        service_cls: Concrete ``MemoryIngestionService`` class supplied by the
            public facade to avoid a package-to-facade import cycle.
        store: Memory store dependency used by the service instance.
        client: Optional OpenAI-compatible client for external analysis agents.

    Returns:
        A configured memory ingestion service with optional extraction and
        semantic analyzers.

    Side Effects:
        Emits privacy-safe configuration logs and may instantiate local or
        OpenRouter-backed analyzer dependencies.
    """

    analyzer = None
    extraction_agent = None
    semantic_enabled = bool(
        settings.memory_semantic_analysis_enabled
        and settings.memory_semantic_external_processing_acknowledged
    )
    if (
        settings.memory_extraction_agent_enabled
        and settings.memory_semantic_external_processing_acknowledged
        and client is not None
    ):
        from services.memory_extraction_agent import OpenRouterMemoryExtractionAgent

        extraction_agent = OpenRouterMemoryExtractionAgent(
            client,
            settings.model_memory_semantic_analyzer,
            timeout_seconds=settings.memory_extraction_timeout_seconds,
        )
        logger.debug(
            "memory.extraction_agent_configured mode=external model=%s timeout_seconds=%s min_confidence=%s privacy_acknowledged=%s client_available=%s",
            settings.model_memory_semantic_analyzer,
            settings.memory_extraction_timeout_seconds,
            settings.memory_extraction_min_confidence,
            settings.memory_semantic_external_processing_acknowledged,
            client is not None,
        )
    elif settings.memory_extraction_agent_enabled:
        from services.memory_extraction_agent import LocalMemoryExtractionAgent

        extraction_agent = LocalMemoryExtractionAgent()
        logger.debug(
            "memory.extraction_agent_configured mode=local model=none timeout_seconds=%s min_confidence=%s privacy_acknowledged=%s client_available=%s",
            settings.memory_extraction_timeout_seconds,
            settings.memory_extraction_min_confidence,
            settings.memory_semantic_external_processing_acknowledged,
            client is not None,
        )
    else:
        logger.debug(
            "memory.extraction_agent_configured mode=disabled model=none timeout_seconds=%s min_confidence=%s privacy_acknowledged=%s client_available=%s",
            settings.memory_extraction_timeout_seconds,
            settings.memory_extraction_min_confidence,
            settings.memory_semantic_external_processing_acknowledged,
            client is not None,
        )

    if semantic_enabled and client is not None:
        from services.memory_semantic_analyzer import OpenRouterMemorySemanticAnalyzer

        analyzer = OpenRouterMemorySemanticAnalyzer(
            client,
            settings.model_memory_semantic_analyzer,
            timeout_seconds=settings.memory_semantic_timeout_seconds,
        )
    elif settings.memory_semantic_analysis_enabled:
        logger.warning(
            "memory.semantic_analysis_blocked reason=%s",
            "privacy_acknowledgement_missing"
            if not settings.memory_semantic_external_processing_acknowledged
            else "client_unavailable",
        )
    return service_cls(
        store,
        extraction_agent=extraction_agent,
        semantic_analyzer=analyzer,
        semantic_enabled=semantic_enabled,
    )
