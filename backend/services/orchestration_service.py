"""
Orchestration Service Module.

This module provides the streaming controller for incoming chat requests. It
owns execution order and the established SSE compatibility boundary while
delegating memory ingestion, context construction, and post-turn work to
domain services.
"""

from __future__ import annotations

import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from config import settings

try:
    from gum_integration import (
        async_evaluate_and_update_state,
        get_hot_memory_snapshot,
        push_observation,
        query_cold_memory_for_context,
        query_memory_for_context,
    )
except ModuleNotFoundError:
    from backend.gum_integration import (
        async_evaluate_and_update_state,
        get_hot_memory_snapshot,
        push_observation,
        query_cold_memory_for_context,
        query_memory_for_context,
    )
from core import ConversationRuntime
from agents import TutorAgent
from policies import MemoryPolicy
from tools import DelayedMailTool, MemoryQueryTool, ToolDefinition, ToolRegistry, WebSearchTool
from services.conversation_context_service import ConversationContextService
from services.conversation_stream_service import ConversationStreamService
from services.orchestration import (
    OrchestrationExecutionMixin,
    OrchestrationPromptingMixin,
    OrchestrationRetrievalMixin,
    OrchestrationStreamingMixin,
    OrchestrationVisualMixin,
)
from services.orchestration.utils import (
    _build_valid_web_sources,
    _localized_greeting_reply,
    classify_dialogue_policy,
    parse_and_decompose_query,
    reorder_for_attention,
)
from services.output_image_service import OutputImageService
from services.parts_context_service import PartsContextService
from services.post_turn_service import PostTurnService
from services.turn_intake_service import TurnIntakeService
from services.turn_intake_service import (
    chat_avatar_key as _chat_avatar_key,
    extract_explicit_chat_avatar as _extract_explicit_chat_avatar,
    is_stop_roleplay_request as _is_stop_roleplay_request,
    normalize_avatar_name as _normalize_avatar_name,
)
from services.turn_plan_service import TurnPlanService
from services.visual_answer_service import VisualAnswerService

InterfaceLanguage = str


class OrchestrationService(
    OrchestrationExecutionMixin,
    OrchestrationVisualMixin,
    OrchestrationRetrievalMixin,
    OrchestrationPromptingMixin,
    OrchestrationStreamingMixin,
):
    """The main orchestration service managing conversation flow and tools."""

    def __init__(self, router_service, rag_service, suggestion_service, client):
        """Initialize the OrchestrationService with required sub-services."""

        self.router = router_service
        self.rag = rag_service
        self.suggestion = suggestion_service
        self.client = client
        self.runtime = ConversationRuntime()
        self.tutor_agent = TutorAgent()
        self.memory_policy = MemoryPolicy()
        self.memory_query_tool = MemoryQueryTool(
            lambda *args, **kwargs: query_cold_memory_for_context(*args, **kwargs),
            lambda *args, **kwargs: query_memory_for_context(*args, **kwargs),
        )
        self.context_service = ConversationContextService(
            self.memory_policy,
            self.memory_query_tool,
        )
        self.post_turn_service = PostTurnService(suggestion_service)
        self.visual_answer_service = VisualAnswerService()
        self.output_image_service = OutputImageService()
        self.parts_context_service = PartsContextService()
        self.turn_intake_service = TurnIntakeService(client)
        self.turn_plan_service = TurnPlanService(self.memory_policy)
        self.web_search_tool = WebSearchTool(
            provider=settings.web_search_provider,
            tavily_endpoint=settings.tavily_search_api_url,
            openrouter_endpoint=settings.openrouter_web_search_api_url,
            openrouter_model=settings.model_web_search,
            openrouter_engine=settings.openrouter_web_search_engine,
            openrouter_max_tool_calls=settings.openrouter_web_search_max_tool_calls,
        )
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(ToolDefinition(
            name="web_search",
            external=True,
            handler=self.web_search_tool.execute,
        ))
        self.delayed_mail_tool = DelayedMailTool(
            lambda: __import__("mailbox_store").get_mailbox_store()
        )
        self.tool_registry.register(ToolDefinition(
            name="schedule_letter",
            external=False,
            handler=self.delayed_mail_tool.execute,
        ))
        from services.conversation.image_generation import image_tool_definition
        self.tool_registry.register(image_tool_definition())
        self.stream_service = ConversationStreamService(client, self.tool_registry)
