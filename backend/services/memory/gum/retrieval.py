"""GUM workflow with an explicit runtime owner for state and dependencies."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime

logger = logging.getLogger("gum_integration")

async def query_memory_for_context(runtime, user_query: str, limit: int = 8, user_id: str = "default_user") -> str:
    """
    Query GUM memory and return a formatted string for System Prompt injection.

    This is the critical bridge between STITCH-filtered memory and the LLM prompt.
    Without this, the STITCH subsystem correctly retrieves memories but never passes
    them to the main LLM, making memory invisible to the AI.

    Args:
        user_query: The user's current message to use as the search query.
        limit: Maximum number of memory propositions to inject.

    Returns:
        A formatted <memory> block string for system prompt injection, or "" if no memory.
    """
    gum_instance, _ = await runtime.get_gum_instance(user_id)
    if not gum_instance:
        return ""
    try:
        results = await gum_instance.query(user_query, user_id=user_id, limit=limit)
        memory_lines = []
        from services.memory.store.service import get_global_store
        store = get_global_store()
        if store:
            profile = await store.get_user_profile(user_id)
            prefs = profile.get("explicit_memories", [])
            if prefs:
                memory_lines.append("【USER PROFILE (長期)】\n  - " + "\n  - ".join(prefs))
            
            hot = await store.get_hot_memory(user_id)
            hot_memories = hot.get("explicit_memories", [])
            if hot_memories:
                memory_lines.append("【MEMORY (目前脈絡)】\n  - " + "\n  - ".join(hot_memories))
        
        if results:
            memory_lines.extend([p.text for p, _ in results])
            
        if not memory_lines:
            return ""
            
        memory_block = "\n".join(f"- {line}" for line in memory_lines)
        return f"\n<memory>\n以下是關於使用者的已知記憶，請根據這些記憶來個人化你的回答：\n{memory_block}\n</memory>"
    except Exception as e:
        logger.warning("gum.retrieval_failed reason=%s", type(e).__name__)
        return ""


async def get_pending_observation_count(runtime, user_id: str) -> int:
    """Return the durable GUM queue size for diagnostics."""
    gum_instance, _ = await runtime.get_gum_instance(user_id)
    batcher = getattr(gum_instance, "batcher", None) if gum_instance else None
    return int(batcher.size()) if batcher and hasattr(batcher, "size") else 0
