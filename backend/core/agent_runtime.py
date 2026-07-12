from __future__ import annotations

import uuid
from dataclasses import dataclass

from .run_context import RunContext, SearchMode
from .run_state import ConversationRunState
from .sse_adapter import SSEAdapter


@dataclass(slots=True)
class RuntimeSession:
    context: RunContext
    state: ConversationRunState
    transport: SSEAdapter


class ConversationRuntime:
    """Creates isolated execution sessions for the compatibility facade."""

    def start_session(
        self,
        *,
        user_id: str,
        conversation_id: str,
        request_id: str | None,
        search_mode: SearchMode,
    ) -> RuntimeSession:
        run_id = uuid.uuid4().hex
        normalized_request_id = request_id.strip() if isinstance(request_id, str) else ""
        context = RunContext(
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id or f"ephemeral:{run_id}",
            request_id=normalized_request_id or run_id,
            search_mode=search_mode,
        )
        return RuntimeSession(
            context=context,
            state=ConversationRunState(),
            transport=SSEAdapter(),
        )
