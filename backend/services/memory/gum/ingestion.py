"""GUM workflow with an explicit runtime owner for state and dependencies."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime

logger = logging.getLogger("gum_integration")

async def batch_process_observations(
    runtime,
    user_id: str,
    items: list[str],
    *,
    sync_to_working_memory: bool = True,
    conversation_id: str = "",
):
    runtime.last_interaction_times[user_id] = datetime.now()
    
    gum_instance, text_observer = await runtime.get_gum_instance(user_id)
    
    if gum_instance and text_observer:
        combined_text = " | ".join(items)
        try:
            neighbors = await gum_instance.query(combined_text, user_id=user_id, limit=20)
            if not neighbors:
                recent_props = await gum_instance.recent(user_id=user_id, limit=20)
                neighbors = [(p, 1.0) for p in recent_props]
    
            if neighbors:
                neighbor_ctx = "\\n".join([f"ID: {p.id}, Text: {p.text}" for p, _ in neighbors])
                prompt = f"""Analyze the new observation against existing memories.
    New observation (user-originated input; not proof of a stable user fact): {combined_text}
    Existing memories:
    {neighbor_ctx}
    
    Task: 
    1. Determine if the new observation logically CONTRADICTS, UPDATES, or is highly REDUNDANT with any existing memories.
    2. If it is redundant or updates old memories, set should_evolve=true, add 'prune' to actions, and put the old memory IDs to be pruned in target_ids. 
    3. Provide a 'revised_proposition' that merges the new observation and the pruned memories into a single concise, updated statement.
    4. Generate a 'decay_score' (1-10) for this proposition. Transient or temporary actions (e.g. debugging a specific bug) decay fast (score=8-10). Stable facts (e.g. user is a PhD student) decay slowly (score=1-3).
    5. Rate importance 1-10.
    6. Never turn a teaching conclusion, an answer supplied by the assistant,
       or a temporary learning result into a durable user preference or identity."""
                
                from typing import Optional

                from gum.schemas import get_schema
                from pydantic import BaseModel, Field
                class EvolutionSchema(BaseModel):
                    should_evolve: bool
                    actions: list[str]
                    target_ids: list[int]
                    importance_score: int
                    revised_proposition: Optional[str] = Field(None, description="The merged and updated proposition")
                    decay_score: int = Field(5, description="1-10 score of how fast this memory should decay")
                    
                rsp = await gum_instance.client.chat.completions.create(
                    model=gum_instance.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=get_schema(EvolutionSchema.model_json_schema()),
                    max_tokens=500,
                )
                import json
                import re
                content = rsp.choices[0].message.content.strip()
                match = re.search(r'\{.*\}', content, re.DOTALL)
                if match:
                    content = match.group(0)
                decision = json.loads(content)
                
                logger.debug("gum.evolution_decision_received should_evolve=%s", bool(decision.get("should_evolve")))
                
                runtime.importance_sums[user_id] = runtime.importance_sums.get(user_id, 0) + decision.get("importance_score", 5)
                
                if decision.get("should_evolve") and "prune" in decision.get("actions", []):
                    target_ids = decision.get("target_ids", [])
                    for t_id in target_ids:
                        await gum_instance.update_status(t_id, "superseded")
                
                final_text = decision.get("revised_proposition") if decision.get("should_evolve") and decision.get("revised_proposition") else combined_text
                final_decay = decision.get("decay_score", 5.0)
            else:
                runtime.importance_sums[user_id] = runtime.importance_sums.get(user_id, 0) + 5
                final_text = combined_text
                final_decay = 5.0
        except Exception as e:
            logger.warning("gum.ingestion_failed reason=%s", type(e).__name__)
            runtime.importance_sums[user_id] = runtime.importance_sums.get(user_id, 0) + 5
            final_text = combined_text
            final_decay = 5.0
    
        if runtime.is_real_gum_batcher(gum_instance):
            for item in items:
                await runtime.push_text_to_gum(gum_instance, text_observer, item, user_id)
        else:
            await runtime.push_text_to_gum(gum_instance, text_observer, combined_text, user_id)
        runtime.interaction_counts[user_id] = runtime.interaction_counts.get(user_id, 0) + len(items)
    else:
        combined_text = " | ".join(items)
        
    # Sync only semantic learning observations into prompt-visible working memory.
    # Raw UI telemetry is routed by /log_action into behavior_signals instead.
    try:
        from services.memory.gate import classify_learning_observation
        from services.memory.store.service import get_global_store
        store = get_global_store()
        gate = classify_learning_observation(final_text)
        if store and gate.should_prompt and sync_to_working_memory:
            await store.append_learning_observation(
                user_id,
                gate.proposition,
                confidence=8.0,
                decay=float(final_decay),
                conversation_id=conversation_id,
                source="user_message",
            )
    except Exception as e:
        # Expected if budget exceeded, handled below
        pass
        
    await runtime.schedule_compaction(user_id)
    
    if runtime.importance_sums.get(user_id, 0) >= 100 or runtime.interaction_counts.get(user_id, 0) >= 20:
        await runtime.schedule_session_reflection(user_id, conversation_id=conversation_id)


async def push_observation(
    runtime,
    user_id: str,
    text: str,
    *,
    sync_to_working_memory: bool = True,
    conversation_id: str = "",
):
    gum_instance, _ = await runtime.get_gum_instance(user_id)
    if not gum_instance:
        return
    if runtime.obs_worker:
        await runtime.obs_worker.push(
            user_id,
            text,
            sync_to_working_memory=sync_to_working_memory,
            conversation_id=conversation_id,
        )
    else:
        await runtime.batch_process_observations(
            user_id,
            [text],
            sync_to_working_memory=sync_to_working_memory,
            conversation_id=conversation_id,
        )


async def push_reflection_observation(runtime, user_id: str, text: str, *, conversation_id: str = ""):
    return await runtime.push_observation(
        user_id,
        text,
        sync_to_working_memory=False,
        conversation_id=conversation_id,
    )
