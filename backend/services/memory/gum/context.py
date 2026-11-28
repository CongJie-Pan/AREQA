"""Build prompt-safe memory context and bounded learner-state or scaffolding requests."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def get_hot_memory_snapshot(
    user_id: str = "default_user",
    *,
    conversation_id: str = "",
    include_cross_conversation_focus: bool = True,
) -> str:
    import json

    from services.memory.store.service import get_global_store
    store = get_global_store()
    if not store:
        return ""

    # Combine durable profile facts and prompt-safe working memory.
    profile = await store.get_user_profile(user_id)
    import inspect
    get_working_memory = getattr(store, "get_working_memory", None)
    if inspect.iscoroutinefunction(get_working_memory):
        working_memory = await get_working_memory(user_id)
    else:
        working_memory = {}

    parts = []
    if profile:
        parts.append("【使用者畫像 (User Profile)】\n" + json.dumps(profile, ensure_ascii=False, indent=2))

    if working_memory:
        focus = working_memory.get("current_focus")
        focus_conversation_id = working_memory.get("current_focus_conversation_id")
        session_summary = working_memory.get("session_summary")
        summary_conversation_id = working_memory.get("session_summary_conversation_id")
        explicit_memories = working_memory.get("explicit_memories") or []
        recent_points = working_memory.get("recent_learning_points") or []
        if not include_cross_conversation_focus and conversation_id:
            is_same_conversation = bool(focus_conversation_id and focus_conversation_id == conversation_id)
            if not is_same_conversation:
                focus = ""
                explicit_memories = []
                recent_points = []
            if summary_conversation_id != conversation_id:
                session_summary = ""

        if not include_cross_conversation_focus and conversation_id:
            recent_points = [
                point for point in recent_points
                if isinstance(point, dict) and point.get("conversation_id") == conversation_id
            ]

        working_parts = []
        if session_summary:
            working_parts.append(f"Session summary: {session_summary}")
        if focus:
            working_parts.append(f"Current focus: {focus}")
        for memory in explicit_memories[-8:]:
            if memory:
                working_parts.append(f"Explicit memory: {memory}")
        for point in recent_points[-8:]:
            if isinstance(point, dict) and point.get("prompt_safe") is False:
                # logger.info(
                logger.debug(
                    "hot_memory.snapshot_excluded user_id=%s reason=not_prompt_safe",
                    user_id,
                )
                continue
            if isinstance(point, dict) and point.get("text"):
                working_parts.append(point["text"])
            elif isinstance(point, str):
                working_parts.append(point)

        if working_parts:
            parts.append("【工作記憶 (Working Memory)】\n- " + "\n- ".join(working_parts))

    return "\n\n".join(parts)


async def generate_zpd_query_via_llm(client, model, original_query, learner_state):
    prompt = f"""You are an educational AI converting a student's question into a ZPD-aligned search query.
Student's current learning state: {learner_state}
Original query: {original_query}

If the state is "TINKERING" or "RUN_REPEAT", focus on underlying concepts rather than the exact syntax.
If the state is "STARTING", focus on fundamental definitions.
Otherwise, refine the query to be pedagogical.
Return ONLY the refined query string without any quotes or explanations."""
    try:
        rsp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.3
        )
        return rsp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("gum.context_failed reason=%s", type(e).__name__)
        return original_query


async def query_cold_memory_for_context(
    user_id: str,
    query: str,
    top_k: int = 5,
    client=None,
    model=None,
    memory_trace=None,
) -> str:
    """Return prompt-safe cold memory context with optional safe trace metadata."""

    import os
    from pathlib import Path

    from services.memory.cold import ColdMemoryRetriever
    from services.memory.store.service import get_global_store

    db_path = str(Path(__file__).resolve().parents[3] / "data" / "gum_data" / "gum.db")
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return ""

    try:
        store = get_global_store()
        if memory_trace:
            async with memory_trace.measure("cold_memory_learner_state"):
                learner_state = await store.get_learner_state(user_id) if store else "STARTING"
        else:
            learner_state = await store.get_learner_state(user_id) if store else "STARTING"

        c = client
        from config import settings
        m = model if model else settings.model_zpd_query
        if not c:
            from openai import AsyncOpenAI
            c = AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

        if memory_trace:
            async with memory_trace.measure("cold_memory_zpd_query"):
                zpd_query = await generate_zpd_query_via_llm(c, m, query, learner_state)
        else:
            zpd_query = await generate_zpd_query_via_llm(c, m, query, learner_state)

        cold_retriever = ColdMemoryRetriever(db_path, api_key)
        if memory_trace:
            async with memory_trace.measure("cold_memory_search"):
                results = await cold_retriever.search(
                    zpd_query,
                    user_id=user_id,
                    top_k=top_k,
                    memory_trace=memory_trace,
                )
        else:
            results = await cold_retriever.search(zpd_query, user_id=user_id, top_k=top_k)
        if not results:
            return ""

        if memory_trace:
            memory_trace.record_step("cold_memory_results", 0, outcome=f"count_{min(len(results), 6)}")
        parts = ["【檢索到的長尾記憶 (Cold Memory)】"]
        for r in results:
            parts.append(f"- {r['text']}")

        return "\n".join(parts)
    except Exception as e:
        logger.warning("gum.context_failed reason=%s", type(e).__name__)
        return ""


async def async_evaluate_and_update_state(
    client,
    model,
    chat_history,
    user_id: str = "default_user",
    conversation_id: str = "",
    ingest_memory: bool = False,
):
    """Evaluate EDF state without creating profile-memory evidence.

    ``ingest_memory`` remains temporarily for worker compatibility, but is
    intentionally ignored. Exact user evidence enters memory only through
    ``TurnIntakeService`` and ``MemoryIngestionService``.
    """
    from services.memory.scoring import evaluate_student_state
    from services.memory.store.service import get_global_store

    state_res = await evaluate_student_state(client, model, chat_history)
    store = get_global_store()
    if store:
        await store.update_learner_state_snapshot(
            user_id,
            learner_state=state_res.get("learner_state", "STARTING"),
            strategy=state_res.get("pedagogical_strategy", "NORMAL"),
            trigger_proactive=bool(state_res.get("trigger_proactive")),
        )
        # State evaluation must not summon avatars or affect chat persona.
        # Conversation-scoped roleplay is handled only by explicit chat commands in OrchestrationService.
        if state_res.get("trigger_proactive"):
            # No proactive consumer remains; keep the EDF signal observable in logs only.
            logger.info("gum.proactive_trigger_requested")

        # EDF evaluates the learner state only. It must never promote an
        # assistant-generated inference into durable user memory.
        if state_res.get("memory_operations"):
            logger.info("gum.derived_memory_operations_ignored")

        if ingest_memory:
            logger.warning(
                "memory.ingestion_skipped user_id=%s conversation_id=%s reason=edf_boundary",
                user_id,
                conversation_id,
            )
