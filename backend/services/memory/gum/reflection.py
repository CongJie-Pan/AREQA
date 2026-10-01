"""GUM workflow with an explicit runtime owner for state and dependencies."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime

logger = logging.getLogger("gum_integration")

async def run_reflection(runtime, user_id: str, conversation_id: str = "") -> list[str]:
    """Serialize reflection and flush operations for one user."""
    lock = runtime.reflection_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        return await runtime._run_reflection_unlocked(user_id, conversation_id)


async def _run_reflection_unlocked(runtime, user_id: str, conversation_id: str = "") -> list[str]:
    gum_instance, text_observer = await runtime.get_gum_instance(user_id)
    if not gum_instance:
        return []
    
    try:
        flush_pending = getattr(gum_instance, "flush_pending_observations", None)
        if flush_pending and inspect.iscoroutinefunction(flush_pending):
            await flush_pending()
        obs = await gum_instance.recent_observations(limit=20, user_id=user_id)
        if not obs:
            return []
            
        context = "\n".join([o.content for o in obs])
        prompt = f"請將以下最近的互動紀錄總結為高層次的學習洞察（insights）：\n{context}\n請只根據使用者明確說出的內容產生洞察。AI 回答、教學解釋與模型推論不是使用者事實；不要把模型推論寫成 user profile。請輸出這些學習洞察。"
        
        from gum.schemas import get_schema
        from pydantic import BaseModel
        class ReflectionSchema(BaseModel):
            insights: list[str]
            
        rsp = await gum_instance.client.chat.completions.create(
            model=gum_instance.model,
            messages=[{"role": "user", "content": prompt}],
            response_format=get_schema(ReflectionSchema.model_json_schema()),
            max_tokens=700,
        )
        import json
        data = json.loads(rsp.choices[0].message.content)
        
        insights = data.get("insights", [])
        logger.info("gum.reflection_generated insight_count=%s", len(insights))
        from services.memory.gate import apply_reflection_gate
        from services.memory.store.service import get_global_store
        store = get_global_store()
        for insight in insights:
            if store:
                await apply_reflection_gate(
                    store,
                    user_id,
                    insight,
                    conversation_id=conversation_id,
                )
            # Reflection output is derived model text. Do not feed it back into
            # the observation stream, otherwise an inference becomes a new fact.
                
        # Archive old observations
        for o in obs:
            await gum_instance.update_observation_status(o.id, "archived")
            
        logger.info("gum.reflection_archived observation_count=%s", len(obs))
        runtime.importance_sums[user_id] = 0
        runtime.interaction_counts[user_id] = 0
        return insights
    except Exception as e:
        logger.warning("gum.reflection_failed reason=%s", type(e).__name__)
        return []


async def schedule_session_reflection(runtime, user_id: str, *, conversation_id: str = "") -> str | None:
    from job_store import get_agent_job_store

    idempotency_key = (
        f"{user_id}:session_reflection:"
        f"{runtime.interaction_counts.get(user_id, 0)}:{int(runtime.importance_sums.get(user_id, 0))}"
    )
    job_id = await get_agent_job_store().schedule(
        job_type="session_reflection",
        user_id=user_id,
        payload={"conversation_id": conversation_id},
        idempotency_key=idempotency_key,
    )
    if job_id is None:
        asyncio.create_task(runtime.run_reflection(user_id, conversation_id=conversation_id))
    return job_id
