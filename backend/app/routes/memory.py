"""Memory API routes for the AREQA backend.

This module owns user-visible memory routes and explicit memory correction
helpers. `backend.main` re-exports the public functions and request models for
legacy tests and callers while the FastAPI router owns endpoint registration.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel

from auth import get_current_user

router = APIRouter()
logger = logging.getLogger("backend.main")
_local_summary_cache: dict[str, dict[str, Any]] = {}


def _main_module():
    return (
        sys.modules.get("backend.main")
        or sys.modules.get("main")
        or importlib.import_module("main")
    )

async def push_observation(user_id: str, text: str):
    from services.memory.gum.runtime import push_observation as _push_observation

    return await _push_observation(user_id, text)

async def get_all_memory(user_id: str = "default_user"):
    from services.memory.gum.runtime import get_all_memory

    return await get_all_memory(user_id)


def _memory_source_id(category: str, text: str) -> str:
    digest = hashlib.sha256(f"{category}|{text}".encode("utf-8")).hexdigest()[:24]
    return f"{category}:{digest}"


async def build_memory_view(user_id: str) -> list[dict]:
    """Return only user-visible, durable Cold Memory records."""
    memory_loader = getattr(_main_module(), "get_all_memory", get_all_memory)
    props = [item for item in await memory_loader(user_id) if item.get("memory_type") == "cold_memory"]
    store = None
    try:
        from services.memory.store.service import get_global_store
        store = get_global_store()
    except Exception as exc:
        logger.warning("[MemoryView] Store unavailable for %s: %s", user_id, exc)

    merged = list(props)
    existing_text = {str(item.get("text", "")).strip() for item in merged}
    if store:
        try:
            profile = await store.get_user_profile(user_id)
            for text_value in profile.get("explicit_memories", []):
                text_value = str(text_value).strip()
                if not text_value or text_value in existing_text:
                    continue
                merged.append({
                    "id": _memory_source_id("profile:explicit", text_value),
                    "text": text_value,
                    "confidence": 9.0,
                    "updated_at": None,
                    "context_scope": "user_profile",
                    "event_types": ["explicit_memory"],
                    "target": "user",
                    "functional_type_seeds": ["profile"],
                    "memory_type": "profile",
                })
                existing_text.add(text_value)

        except Exception as exc:
            logger.warning("[MemoryView] Redis layers unavailable for %s: %s", user_id, exc)

    return [
        item for item in merged
        if not str(item.get("id", "")).startswith("hot:")
        and "Type: scroll" not in item.get("text", "")
        and "User Action: scroll" not in item.get("text", "")
    ]

@router.get("/api/v1/memory")
async def fetch_memory(current_user_id: str = Depends(get_current_user)):
    propositions = await build_memory_view(current_user_id)
    return {
        "propositions": propositions,
        "profile_memories": [item for item in propositions if item.get("memory_type") == "profile"],
        "cold_memories": [item for item in propositions if item.get("memory_type") == "cold_memory"],
        "candidates": [],
        "learning_state": [],
    }

@router.get("/api/v1/memory/summary")
async def get_memory_summary(current_user_id: str = Depends(get_current_user)):
    long_term_props = await build_memory_view(current_user_id)
    long_term_props = sorted(long_term_props, key=lambda x: str(x.get("id", "")))

    memory_text = "\n".join([f"- {p['text']}" for p in long_term_props])
    memory_hash = hashlib.md5(memory_text.encode('utf-8')).hexdigest()

    # 1. Try Redis cache
    redis_client = None
    try:
        rag_cache = getattr(_main_module(), "rag_cache", None)
        if rag_cache is not None:
            redis_client = rag_cache.redis

            cached_summary = await redis_client.get(f"memory_summary_json:{current_user_id}")
            cached_hash = await redis_client.get(f"memory_summary_hash:{current_user_id}")

            if cached_summary:
                cached_summary = cached_summary.decode('utf-8') if isinstance(cached_summary, bytes) else cached_summary
            if cached_hash:
                cached_hash = cached_hash.decode('utf-8') if isinstance(cached_hash, bytes) else cached_hash

            if cached_summary and cached_hash == memory_hash:
                return {"summary": json.loads(cached_summary)}
    except Exception as e:
        print(f"Redis cache error: {e}")

    # 2. Try in-memory fallback cache (useful for Render deployments without Redis)
    user_local_cache = _local_summary_cache.get(current_user_id, {})
    if user_local_cache.get("hash") == memory_hash:
        print("[MemorySummary] Hit in-memory fallback cache")
        return {"summary": user_local_cache.get("summary")}

    prompt = f"""請根據以下長期記憶內容，對這個使用者進行綜整：
【長期記憶】
{memory_text}

【輸出要求】
必須以嚴格的 JSON 格式輸出，不要有任何 Markdown 標記，不要輸出其他多餘的說明。格式如下：
{{
  "sentence1": "一句話表示對這個人的認識",
  "sentence2": "兩句話解釋",
  "hashtags": ["標籤1", "標籤2", "標籤3"]
}}"""

    client_factory = getattr(_main_module(), "AsyncOpenAI", AsyncOpenAI)
    client = client_factory(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ.get("OPENROUTER_API_KEY", "")
    )

    try:
        completion = await client.chat.completions.create(
            model="qwen/qwen3-235b-a22b-2507",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.7
        )
        summary_raw = completion.choices[0].message.content.strip()
        if summary_raw.startswith("```json"):
            summary_raw = summary_raw[7:]
        elif summary_raw.startswith("```"):
            summary_raw = summary_raw[3:]
        if summary_raw.endswith("```"):
            summary_raw = summary_raw[:-3]

        summary_json = json.loads(summary_raw.strip())

        # Cache it (Redis)
        if redis_client:
            try:
                await redis_client.set(f"memory_summary_json:{current_user_id}", json.dumps(summary_json, ensure_ascii=False))
                await redis_client.set(f"memory_summary_hash:{current_user_id}", memory_hash)
            except Exception as e:
                print(f"Redis cache set error: {e}")

        # Cache it (Local fallback)
        if current_user_id not in _local_summary_cache:
            _local_summary_cache[current_user_id] = {}
        _local_summary_cache[current_user_id]["summary"] = summary_json
        _local_summary_cache[current_user_id]["hash"] = memory_hash

        return {"summary": summary_json}
    except Exception as e:
        print(f"Error calling Qwen for memory summary: {e}")
        return {"summary": {"sentence1": "無法生成總結，請確認網路連線與 API Key 設定。", "sentence2": "", "hashtags": []}}

@router.get("/api/v1/memory/debug")
async def memory_debug_endpoint(current_user_id: str = Depends(get_current_user)):
    from services.memory.gum.runtime import get_hot_memory_snapshot, get_pending_observation_count
    from services.memory.store.service import get_global_store

    store = get_global_store()
    if not store:
        return {"status": "unavailable"}

    profile = await store.get_user_profile(current_user_id)
    hot_memory = await store.get_hot_memory(current_user_id)
    working_memory = await store.get_working_memory(current_user_id)
    behavior_signals = await store.get_behavior_signals(current_user_id)
    cold_candidates = await store.get_cold_candidates(current_user_id)
    memory_loader = getattr(_main_module(), "get_all_memory", get_all_memory)
    gum_props = await memory_loader(current_user_id)
    prompt_snapshot = await get_hot_memory_snapshot(current_user_id)

    return {
        "status": "ok",
        "user_id": current_user_id,
        "profile": profile,
        "hot_memory": hot_memory,
        "working_memory": working_memory,
        "behavior_signals": behavior_signals,
        "cold_candidates": cold_candidates,
        "prompt_snapshot": prompt_snapshot,
        "pending_observation_count": await get_pending_observation_count(current_user_id),
        "profile_memory_count": len(profile.get("explicit_memories", [])),
        "cold_candidate_count": len([
            item for item in cold_candidates if item.get("status") in (None, "candidate")
        ]),
        "gum_proposition_count": len(gum_props),
    }

from mailbox_store import get_mailbox_store

class EditMemoryRequest(BaseModel):
    text: str


def _find_profile_memory(profile: dict, memory_id: str) -> int | None:
    for index, value in enumerate(profile.get("explicit_memories", [])):
        if _memory_source_id("profile:explicit", str(value)) == memory_id:
            return index
    return None


def _find_candidate_memory(candidates: list[dict], memory_id: str) -> int | None:
    for index, candidate in enumerate(candidates):
        if _memory_source_id("candidate", str(candidate.get("text", ""))) == memory_id:
            return index
    return None


async def _delete_explicit_profile_memory(store: Any, user_id: str, memory_id: str) -> bool:
    profile = await store.get_user_profile(user_id)
    index = _find_profile_memory(profile, memory_id)
    if index is None:
        return False

    profile["explicit_memories"].pop(index)
    await store.redis.set(
        f"areqa:user_profile:{user_id}",
        json.dumps(profile, ensure_ascii=False),
    )
    try:
        await store.update_working_memory(
            user_id=user_id,
            updates={"explicit_memories": profile["explicit_memories"]},
        )
    except Exception as exc:
        # Profile is the durable source of truth. Working memory is a prompt
        # cache and must not turn a successful profile deletion into HTTP 500.
        logger.warning("[MemoryDelete] Working memory sync failed for %s: %s", user_id, exc)
    return True


async def _update_explicit_profile_memory(
    store: Any,
    user_id: str,
    memory_id: str,
    text: str,
) -> bool:
    """Persist an explicit profile-memory correction before syncing its cache.

    The Redis profile record is the durable source of truth.  The working-memory
    mirror only improves prompt assembly, so a mirror failure is observable but
    must not invalidate a correction that has already been persisted.
    """
    profile = await store.get_user_profile(user_id)
    index = _find_profile_memory(profile, memory_id)
    if index is None:
        return False

    explicit_memories = profile.setdefault("explicit_memories", [])
    explicit_memories[index] = text
    await store.redis.set(
        f"areqa:user_profile:{user_id}",
        json.dumps(profile, ensure_ascii=False),
    )
    logger.info(
        "memory.correction_applied user_id=%s memory_id=%s operation=edit result=persisted",
        user_id,
        memory_id,
    )
    try:
        await store.update_working_memory(
            user_id=user_id,
            updates={"explicit_memories": explicit_memories},
        )
    except Exception as exc:
        logger.warning(
            "memory.correction_sync_failed user_id=%s memory_id=%s operation=edit reason=%s",
            user_id,
            memory_id,
            type(exc).__name__,
        )
    return True


async def _get_candidate_by_memory_id(store: Any, user_id: str, memory_id: str) -> dict | None:
    candidates = await store.get_cold_candidates(user_id)
    return next(
        (
            candidate for candidate in candidates
            if _memory_source_id("candidate", str(candidate.get("text", ""))) == memory_id
        ),
        None,
    )


@router.post("/api/v1/memory/candidates/{memory_id}/confirm")
async def confirm_candidate_memory_endpoint(memory_id: str, current_user_id: str = Depends(get_current_user)):
    from services.memory.store.service import get_global_store

    store = get_global_store()
    if not store:
        raise HTTPException(status_code=503, detail="Memory store unavailable")
    candidate = await _get_candidate_by_memory_id(store, current_user_id, memory_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    promoted = await store.promote_cold_candidate(
        current_user_id,
        candidate["hash"],
        source="user_confirmation",
    )
    if not promoted:
        raise HTTPException(status_code=409, detail="Candidate cannot be confirmed")
    return {"status": "success", "candidate": promoted}


@router.post("/api/v1/memory/candidates/{memory_id}/reject")
async def reject_candidate_memory_endpoint(memory_id: str, current_user_id: str = Depends(get_current_user)):
    from services.memory.store.service import get_global_store

    store = get_global_store()
    if not store:
        raise HTTPException(status_code=503, detail="Memory store unavailable")
    candidate = await _get_candidate_by_memory_id(store, current_user_id, memory_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    rejected = await store.reject_cold_candidate(current_user_id, candidate["hash"])
    return {"status": "success", "candidate": rejected}

@router.delete("/api/v1/memory/working")
async def clear_working_memory_endpoint(current_user_id: str = Depends(get_current_user)):
    from services.memory.store.service import get_global_store

    store = get_global_store()
    if not store:
        raise HTTPException(status_code=500, detail="Memory store not initialized")

    await store.clear_working_memory(current_user_id)
    return {"status": "success", "cleared": "working_memory"}


@router.post("/api/v1/memory/flush")
async def flush_memory_endpoint(current_user_id: str = Depends(get_current_user)):
    """Flush a partial observation batch and reflect it into durable propositions."""
    from services.memory.gum.runtime import get_pending_observation_count, run_reflection

    pending_before = await get_pending_observation_count(current_user_id)
    insights = await run_reflection(current_user_id)
    pending_after = await get_pending_observation_count(current_user_id)
    return {
        "status": "success",
        "processed_observations": max(0, pending_before - pending_after),
        "generated_insights": len(insights),
    }

@router.delete("/api/v1/memory/{mem_id}")
async def delete_memory_endpoint(mem_id: str, current_user_id: str = Depends(get_current_user)):
    from services.memory.gum.runtime import get_gum_instance
    from services.memory.store.service import get_global_store

    if mem_id.startswith("profile:explicit:"):
        store = get_global_store()
        if not store:
            raise HTTPException(status_code=503, detail="Memory store unavailable")
        if not await _delete_explicit_profile_memory(store, current_user_id, mem_id):
            raise HTTPException(status_code=404, detail="Memory not found")
    elif mem_id.startswith("candidate:"):
        store = get_global_store()
        candidates = await store.get_cold_candidates(current_user_id)
        index = _find_candidate_memory(candidates, mem_id)
        if index is not None:
            candidates.pop(index)
            await store.redis.set(f"areqa:cold_candidates:{current_user_id}", json.dumps(candidates, ensure_ascii=False))
    elif mem_id.startswith("profile:"):
        store = get_global_store()
        key = mem_id.split("profile:")[1]
        profile = await store.get_user_profile(current_user_id)
        if key in profile:
            del profile[key]
            import json
            await store.redis.set(f"areqa:user_profile:{current_user_id}", json.dumps(profile, ensure_ascii=False))
    elif mem_id.startswith("hot:"):
        store = get_global_store()
        key = mem_id.split("hot:")[1]
        hot_mem = await store.get_hot_memory(current_user_id)
        if key in hot_mem:
            del hot_mem[key]
            import json
            await store.redis.set(f"areqa:hot_memory:{current_user_id}", json.dumps(hot_mem, ensure_ascii=False))
    else:
        gum_instance, _ = await get_gum_instance(current_user_id)
        if gum_instance:
            await gum_instance.update_status(int(mem_id), "deleted")
    return {"status": "success"}

class DeleteBatchRequest(BaseModel):
    ids: List[str]

@router.post("/api/v1/memory/batch-delete")
async def batch_delete_memory_endpoint(req: DeleteBatchRequest, current_user_id: str = Depends(get_current_user)):
    for mem_id in req.ids:
        await delete_memory_endpoint(mem_id, current_user_id)
    return {"status": "success", "deleted_count": len(req.ids)}

@router.put("/api/v1/memory/{mem_id}")
async def edit_memory_endpoint(mem_id: str, req: EditMemoryRequest, current_user_id: str = Depends(get_current_user)):
    from services.memory.gum.runtime import get_gum_instance
    from services.memory.store.service import get_global_store

    if mem_id.startswith("profile:explicit:"):
        store = get_global_store()
        if not store:
            raise HTTPException(status_code=503, detail="Memory store unavailable")
        if not await _update_explicit_profile_memory(
            store,
            current_user_id,
            mem_id,
            req.text.strip(),
        ):
            raise HTTPException(status_code=404, detail="Memory not found")
    elif mem_id.startswith("candidate:"):
        store = get_global_store()
        candidates = await store.get_cold_candidates(current_user_id)
        index = _find_candidate_memory(candidates, mem_id)
        if index is not None:
            candidates[index]["text"] = req.text.strip()
            candidates[index]["hash"] = hashlib.sha256(
                f"{candidates[index].get('category', '')}|{req.text.strip()}".encode("utf-8")
            ).hexdigest()[:24]
            candidates[index]["last_seen_at"] = datetime.now(timezone.utc).isoformat()
            await store.redis.set(f"areqa:cold_candidates:{current_user_id}", json.dumps(candidates, ensure_ascii=False))
    elif mem_id.startswith("profile:"):
        store = get_global_store()
        key = mem_id.split("profile:")[1]
        profile = await store.get_user_profile(current_user_id)
        if key in profile:
            profile[key] = req.text
            import json
            await store.redis.set(f"areqa:user_profile:{current_user_id}", json.dumps(profile, ensure_ascii=False))
    elif mem_id.startswith("hot:"):
        store = get_global_store()
        key = mem_id.split("hot:")[1]
        hot_mem = await store.get_hot_memory(current_user_id)
        if key in hot_mem:
            if isinstance(hot_mem[key], dict):
                hot_mem[key]["text"] = req.text
            else:
                hot_mem[key] = req.text
            import json
            await store.redis.set(f"areqa:hot_memory:{current_user_id}", json.dumps(hot_mem, ensure_ascii=False))
    else:
        gum_instance, _ = await get_gum_instance(current_user_id)
        if gum_instance:
            await gum_instance.update_text(int(mem_id), req.text)

            # Update cold memory search indexes (FTS & Vector)
            try:
                from cold_memory import ColdMemoryRetriever
                import os
                from pathlib import Path
                db_path = str(Path(__file__).resolve().parent.parent / "data" / "gum_data" / "gum.db")
                api_key = os.environ.get("OPENROUTER_API_KEY", "")
                if api_key:
                    cold_retriever = ColdMemoryRetriever(db_path, api_key)
                    embed = await cold_retriever.get_embedding(req.text)
                    if embed:
                        from cold_memory import get_engine
                        from sqlalchemy import text
                        from sqlalchemy.ext.asyncio import AsyncSession
                        engine = get_engine()
                        async with AsyncSession(engine) as session:
                            async with session.begin():
                                await session.execute(text(
                                    "SELECT set_config('request.jwt.claims', "
                                    "jsonb_build_object('role', 'authenticated', 'sub', CAST(:uid AS text))::text, TRUE)"
                                ), {"uid": current_user_id})
                                await session.execute(text("SET LOCAL ROLE authenticated;"))

                                await session.execute(text("UPDATE propositions SET text = :text WHERE id = :id"), {"text": req.text, "id": int(mem_id)})
                                await session.execute(text("UPDATE vec_memory SET embedding = CAST(:emb AS vector) WHERE id = :id"), {"emb": str(embed), "id": int(mem_id)})
            except Exception as e:
                print(f"Failed to update cold memory indexes for edit: {e}")

    return {"status": "success"}


@router.delete("/api/v1/memory")
async def clear_memory_endpoint(current_user_id: str = Depends(get_current_user)):
    """Clear all hot memory and cold GUM memory"""
    from services.memory.gum.runtime import clear_gum_memory

    from services.memory.store.service import get_global_store
    store = get_global_store()
    if store:
        await store.clear_all_memory(current_user_id)

    await clear_gum_memory(current_user_id)
    return {"status": "ok", "message": "Memory cleared successfully"}

from services.connection_manager import ws_manager
