import os
import json
import httpx
from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

global_engine = None
_table_availability = None

def get_engine():
    global global_engine
    if global_engine is None:
        db_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres")
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        global_engine = create_async_engine(
            db_url,
            pool_size=5,
            max_overflow=10,
            connect_args={"statement_cache_size": 0}
        )
    return global_engine

class ColdMemoryRetriever:
    def __init__(self, db_path: str, openrouter_api_key: str):
        self.api_key = openrouter_api_key
        self.embedding_model = "qwen/qwen3-embedding-8b"
        self.embedding_url = "https://openrouter.ai/api/v1/embeddings"

    async def get_embedding(self, text_str: str) -> List[float]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.embedding_model,
                "input": text_str
            }
            try:
                response = await client.post(self.embedding_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]
            except Exception as e:
                logger.error(f"[ColdMemory] Embedding API failed: {e}")
                return []

    async def search(self, query: str, user_id: str = "default_user", top_k: int = 5) -> List[Dict[str, Any]]:
        # Hybrid Search: Vector KNN + BM25 + RRF
        engine = get_engine()

        async def _get_table_availability() -> Dict[str, bool]:
            global _table_availability
            if _table_availability is not None:
                return _table_availability

            async def _table_exists(session: AsyncSession, table_name: str, *, required: bool) -> bool:
                try:
                    cursor = await session.execute(text(f"SELECT to_regclass('public.{table_name}')"))
                    if hasattr(cursor, "scalar"):
                        return cursor.scalar() is not None

                    # Some tests use lightweight fake cursors that do not implement
                    # scalar(). For the required table, stay optimistic and let the
                    # real query path decide; for optional tables, default disabled.
                    return required
                except Exception as e:
                    if required:
                        logger.error(f"[ColdMemory] Failed to inspect required PostgreSQL table {table_name}: {e}")
                        return True
                    logger.warning(f"[ColdMemory] PostgreSQL table {table_name} is unavailable; related search disabled: {e}")
                    return False

            async with AsyncSession(engine) as session:
                _table_availability = {
                    "propositions": await _table_exists(session, "propositions", required=True),
                    "vec_memory": await _table_exists(session, "vec_memory", required=False),
                }

            if not _table_availability["propositions"]:
                logger.warning("[ColdMemory] PostgreSQL table propositions is missing; cold memory search disabled.")
            elif not _table_availability["vec_memory"]:
                logger.warning("[ColdMemory] PostgreSQL table vec_memory is missing; vector cold memory search disabled.")
            return _table_availability

        tables = await _get_table_availability()
        if not tables["propositions"]:
            return []

        query_embedding = await self.get_embedding(query) if tables["vec_memory"] else []

        async def _fetch_vector_results() -> List[Tuple[int, float]]:
            if not tables["vec_memory"] or not query_embedding:
                return []

            try:
                async with AsyncSession(engine) as session:
                    async with session.begin():
                        await session.execute(text(
                            "SELECT set_config('request.jwt.claims', "
                            "jsonb_build_object('role', 'authenticated', 'sub', CAST(:uid AS text))::text, TRUE)"
                        ), {"uid": user_id})
                        await session.execute(text("SET LOCAL ROLE authenticated;"))
                        cursor = await session.execute(
                            text("SELECT v.id, v.embedding <-> CAST(:emb AS vector) AS distance FROM vec_memory v JOIN propositions p ON v.id = p.id WHERE p.user_id = :uid ORDER BY distance LIMIT :limit"),
                            {"emb": str(query_embedding), "limit": top_k * 2, "uid": user_id}
                        )
                        return [(row[0], row[1]) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"[ColdMemory] Vector search failed: {e}")
                return []

        async def _fetch_bm25_results() -> List[Tuple[int, float]]:
            try:
                async with AsyncSession(engine) as session:
                    async with session.begin():
                        await session.execute(text(
                            "SELECT set_config('request.jwt.claims', "
                            "jsonb_build_object('role', 'authenticated', 'sub', CAST(:uid AS text))::text, TRUE)"
                        ), {"uid": user_id})
                        await session.execute(text("SET LOCAL ROLE authenticated;"))
                        cursor = await session.execute(
                            text("""
                            SELECT id, ts_rank(to_tsvector('english', text), plainto_tsquery('english', :query)) as rank 
                            FROM propositions 
                            WHERE to_tsvector('english', text) @@ plainto_tsquery('english', :query) AND user_id = :uid
                            ORDER BY rank DESC LIMIT :limit
                            """),
                            {"query": query, "limit": top_k * 2, "uid": user_id}
                        )
                        return [(row[0], row[1]) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"[ColdMemory] BM25 search failed: {e}")
                return []

        vec_results = await _fetch_vector_results()
        bm25_results = await _fetch_bm25_results()

        # RRF Fusion
        rrf_scores = {}
        k_const = 60

        # Sort vector by distance (lower is better)
        for rank, (doc_id, dist) in enumerate(vec_results):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + (1.0 / (k_const + rank + 1))

        # Sort bm25 by rank (higher is better)
        for rank, (doc_id, score) in enumerate(bm25_results):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + (1.0 / (k_const + rank + 1))

        sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        final_results = []
        async with AsyncSession(engine) as session:
            async with session.begin():
                await session.execute(text(
                    "SELECT set_config('request.jwt.claims', "
                    "jsonb_build_object('role', 'authenticated', 'sub', CAST(:uid AS text))::text, TRUE)"
                ), {"uid": user_id})
                await session.execute(text("SET LOCAL ROLE authenticated;"))
                for doc_id, score in sorted_docs:
                    try:
                        cursor = await session.execute(
                            text("SELECT text FROM propositions WHERE id = :id AND status = 'active'"),
                            {"id": doc_id}
                        )
                        row = cursor.fetchone()
                        if row:
                            final_results.append({"id": doc_id, "text": row[0], "rrf_score": score})
                    except Exception:
                        pass

        return final_results
