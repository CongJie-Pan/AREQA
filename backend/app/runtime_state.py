"""Runtime state and RAG initialization helpers for the backend app."""

from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
rag_cache = None
rag_service = None
_resolved_model_name = None
_thread_pool = ThreadPoolExecutor(max_workers=4)


def get_query_fingerprint(query: str) -> str:
    """Return a stable cache fingerprint for a normalized query string.

    Args:
        query: Raw user query to normalize for cache lookup.

    Returns:
        MD5 fingerprint matching the legacy `backend.main` cache key.
    """

    return hashlib.md5(query.strip().lower().encode()).hexdigest()


def _env_flag(name: str, default: str = "false") -> bool:
    """Read a boolean environment flag using the backend's legacy truthy set."""

    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def init_rag_service():
    """Initialize internal RAG only when explicitly enabled.

    Returns:
        The singleton RAG service, or `None` when the feature is disabled,
        indexes are missing, or initialization fails.

    Side Effects:
        Updates the module-level `rag_service` singleton. It prints the same
        operational messages as the legacy implementation and never emits
        credentials or query text.
    """

    global rag_service
    if rag_service is not None:
        return rag_service

    if not _env_flag("ENABLE_INTERNAL_RAG"):
        print("Internal RAG disabled. Set ENABLE_INTERNAL_RAG=true to enable local retrieval.")
        return None

    try:
        from services.rag_service import RAGService

        faiss_dir = PROJECT_ROOT / "data" / "rag" / "faiss_index"
        bm25_dir = PROJECT_ROOT / "data" / "rag" / "bm25_index"

        def get_latest_file(directory: Path, pattern: str) -> str:
            if not directory.exists():
                return ""
            files = list(directory.glob(pattern))
            if not files:
                return ""
            return str(sorted(files, key=lambda path: path.stat().st_mtime)[-1])

        latest_faiss_idx = get_latest_file(faiss_dir, "chunks*.index")
        latest_faiss_meta = get_latest_file(faiss_dir, "index_metadata*.json")
        if not latest_faiss_idx or not latest_faiss_meta:
            print("Internal RAG enabled but FAISS index/metadata is missing. RAG disabled.")
            return None

        rag_service = RAGService(
            faiss_index_path=latest_faiss_idx,
            faiss_metadata_path=latest_faiss_meta,
            bm25_index_dir=str(bm25_dir),
            embedding_model_path="api",
            reranker_model_path="api",
            top_k=5,
            rrf_k=60,
            score_threshold=0.0,
            max_context_tokens=4000,
        )
        print("RAG Service initialized successfully.")
        return rag_service
    except Exception as exc:
        rag_service = None
        print(f"Warning: Could not load RAGService. Details: {exc}")
        return None
