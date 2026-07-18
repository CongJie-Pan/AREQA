"""Dispatch non-critical background work after a conversation turn.

This service owns durable reflection/EDF job dispatch and suggestion creation.
It intentionally has no profile-memory persistence dependency; user evidence
must enter durable memory through ``MemoryIngestionService`` before this stage.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List


logger = logging.getLogger(__name__)


class PostTurnService:
    """Schedule post-turn jobs and format optional suggestion SSE events."""

    def __init__(self, suggestion_service: Any = None):
        self.suggestion_service = suggestion_service
        self._background_tasks: set[asyncio.Task] = set()

    def queue_post_turn_work(
        self,
        *,
        timeout_seconds: float = 2.0,
        **dispatch_kwargs: Any,
    ) -> asyncio.Task:
        """Queue bounded post-turn dispatch without delaying stream completion."""

        async def runner() -> None:
            try:
                await asyncio.wait_for(
                    self.dispatch_post_turn_work(**dispatch_kwargs),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                logger.warning(
                    "orchestration.post_turn_timeout run_id=%s conversation_id=%s timeout_seconds=%s",
                    dispatch_kwargs.get("run_id", ""),
                    dispatch_kwargs.get("conversation_id", ""),
                    timeout_seconds,
                )
            except Exception as exc:
                logger.exception(
                    "orchestration.post_turn_failed run_id=%s conversation_id=%s reason=%s",
                    dispatch_kwargs.get("run_id", ""),
                    dispatch_kwargs.get("conversation_id", ""),
                    type(exc).__name__,
                )

        task = asyncio.create_task(runner())
        # Keep a strong reference until completion; the event loop only retains
        # weak task references and post-turn work must not disappear mid-dispatch.
        self._background_tasks.add(task)

        def finalize(completed: asyncio.Task) -> None:
            self._background_tasks.discard(completed)
            if not completed.cancelled():
                completed.exception()

        task.add_done_callback(finalize)
        return task

    async def dispatch_post_turn_work(
        self,
        *,
        user_id: str,
        conversation_id: str,
        run_id: str,
        messages: List[Dict[str, str]],
        model: str,
        client: Any,
        reflection_fallback: Callable[..., Awaitable[Any]],
        evaluation_fallback: Callable[..., Awaitable[Any]],
    ) -> None:
        """Persist reflection and learner-state jobs with in-process fallback.

        Background failures are logged and contained because they must not
        invalidate an otherwise completed response stream.
        """
        from job_store import get_agent_job_store

        latest_user_text = next(
            (str(item.get("content", "")) for item in reversed(messages) if item.get("role") == "user"),
            "",
        )
        if not latest_user_text:
            return

        job_store = get_agent_job_store()
        reflection_job = None
        evaluation_job = None
        try:
            reflection_job = await job_store.schedule(
                job_type="reflection_observation",
                user_id=user_id,
                payload={
                    "text": f"User asked: {latest_user_text}",
                    "conversation_id": conversation_id,
                },
                idempotency_key=f"{run_id}:reflection_observation",
            )
        except Exception as exc:
            logger.exception(
                "orchestration.reflection_dispatch_failed run_id=%s conversation_id=%s reason=%s",
                run_id,
                conversation_id,
                type(exc).__name__,
            )
        if reflection_job is None:
            asyncio.create_task(
                reflection_fallback(
                    user_id,
                    f"User asked: {latest_user_text}",
                    conversation_id=conversation_id,
                )
            )

        recent_messages = messages[-10:]
        try:
            evaluation_job = await job_store.schedule(
                job_type="edf_evaluation",
                user_id=user_id,
                payload={
                    "messages": recent_messages,
                    "model": model,
                    "conversation_id": conversation_id,
                    "ingest_memory": False,
                },
                idempotency_key=f"{run_id}:edf_evaluation",
            )
        except Exception as exc:
            logger.exception(
                "orchestration.evaluation_dispatch_failed run_id=%s conversation_id=%s reason=%s",
                run_id,
                conversation_id,
                type(exc).__name__,
            )
        if evaluation_job is None and client is not None:
            asyncio.create_task(
                evaluation_fallback(
                    client,
                    model,
                    recent_messages,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    ingest_memory=False,
                )
            )
        logger.info(
            "orchestration.post_turn_dispatched run_id=%s conversation_id=%s reflection_durable=%s evaluation_durable=%s",
            run_id,
            conversation_id,
            reflection_job is not None,
            evaluation_job is not None,
        )

    async def suggestion_events(
        self,
        *,
        last_user_msg: str,
        answer_text: str,
        context_results_obj: Any,
        use_rag: bool,
        use_web_search: bool,
    ) -> List[str]:
        """Generate legacy-compatible suggestion and completion events."""
        if not self.suggestion_service:
            return []
        try:
            reranked_results = (
                context_results_obj.final_results
                if use_rag and not use_web_search and context_results_obj
                else []
            )
            suggestions = await self.suggestion_service.generate_suggestions(
                user_query=last_user_msg,
                answer_text=answer_text,
                reranked_results=reranked_results,
            )
            events = []
            if suggestions:
                events.append(
                    f"event: suggestions\ndata: {json.dumps(suggestions, ensure_ascii=False)}\n\n"
                )
            events.append(
                f"event: done\ndata: {json.dumps({'suggestions': suggestions or []}, ensure_ascii=False)}\n\n"
            )
            return events
        except Exception as exc:
            logger.warning("orchestration.suggestions_failed reason=%s", type(exc).__name__)
            return [
                f"event: done\ndata: {json.dumps({'suggestions': []}, ensure_ascii=False)}\n\n"
            ]
