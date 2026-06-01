"""
RAG Service — Unified Retrieval-Augmented Generation interface for Streamlit.

This service encapsulates the complete RAG retrieval pipeline:
  1. Query encoding with Qwen3-Embedding-0.6B (instruction-aware, asymmetric)
  2. Hybrid search: FAISS (dense) + BM25 (sparse) → RRF fusion
  3. Prompt injection sanitization
  4. Token-budget-aware context truncation

Why a separate service?
    - Hides FAISS/BM25/Embedding initialisation complexity from chat_app.py
    - Enables @st.cache_resource to load models once across Streamlit reruns
    - Co-located with chat_app.py under app/streamlit/

Reference:
    - Implementation Plan v2 (RAG Pipeline 整合至 Streamlit)
    - docs/miscellaneous/paper/RA-DIT_method_Mermaid流程圖.md
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import numpy as np
import opencc

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

# English instruction prefix for Qwen3-Embedding asymmetric encoding.
# Why English? Qwen3-Embedding was trained with English instructions,
# even for multilingual retrieval tasks. See official repo & HF docs.
QUERY_INSTRUCTION = (
    "Instruct: Given a question about classical Chinese literature, "
    "retrieve relevant passages that answer the question\n"
    "Query: "
)

# Patterns that may indicate indirect prompt injection attacks.
# Why filter these? RAG systems expose an attack surface where malicious
# content in the document corpus can hijack the LLM's system prompt.
SUSPICIOUS_PATTERNS = [
    "ignore previous",
    "system override",
    "disregard",
    "forget your instructions",
    "new instructions",
    "ignore all",
    "act as",
    "<|im_start|>",
    "<|im_end|>",
    "<|system|>",
]


@dataclass
class RetrievalResult:
    """A single retrieved chunk with metadata for display.

    Attributes:
        text: The chunk text content.
        chunk_id: Original chunk identifier (e.g. 'chapter_008').
        score: RRF fusion score.
        source: Source label for citation display.
    """
    text: str
    chunk_id: str = ""
    score: float = 0.0
    source: str = ""


@dataclass
class RetrievalDebugInfo:
    """Full retrieval trace for Streamlit debug rendering.

    Attributes:
        query: The user query that triggered retrieval.
        dense_results: Raw FAISS ranking before fusion.
        sparse_results: Raw BM25 ranking before fusion.
        fused_results: RRF-ranked items before sanitization/truncation.
        final_results: Final chunks that will be injected into the prompt.
        context: Prompt-ready context string built from ``final_results``.
        sanitized_count: Number of chunks whose text was replaced by the
            prompt-injection sanitizer.
        truncated_count: Number of top-k chunks dropped by token truncation.
    """

    query: str
    dense_results: Optional[List[Dict[str, Any]]] = None
    sparse_results: Optional[List[Dict[str, Any]]] = None
    fused_results: Optional[List[Dict[str, Any]]] = None
    final_results: Optional[List[RetrievalResult]] = None
    context: str = ""
    sanitized_count: int = 0
    truncated_count: int = 0
    highest_score: float = 0.0

    def __post_init__(self):
        """Normalise optional collections to empty lists."""
        if self.dense_results is None:
            self.dense_results = []
        if self.sparse_results is None:
            self.sparse_results = []
        if self.fused_results is None:
            self.fused_results = []
        if self.final_results is None:
            self.final_results = []


# ============================================================================
# Security Utilities
# ============================================================================

def sanitize_chunk(text: str) -> str:
    """Filter chunks containing suspicious prompt-injection patterns.

    Why: Retrieved chunks are injected into the LLM prompt as context.
    A compromised document could contain instructions that override the
    system prompt. This function replaces such chunks with a safe notice.

    Args:
        text: Raw chunk text to inspect.

    Returns:
        Original text if clean, or a safe replacement string.
    """
    text_lower = text.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern.lower() in text_lower:
            logger.warning(
                "Sanitized a chunk containing suspicious pattern: '%s'",
                pattern,
            )
            return "[此段落已被安全過濾]"
    return text


# ============================================================================
# Token Budget Utilities
# ============================================================================

def truncate_rag_context(
    chunks: List[str],
    max_tokens: int = 4000,
    tokenizer=None,
) -> List[str]:
    """Select chunks greedily until the token budget is exhausted.

    Why a hard truncation? The model context window (8192 tokens) must be
    shared among RAG context, chat history, system prompt, and generation
    headroom. Unbounded context causes silent overflow and degraded output.

    Args:
        chunks: Ordered list of chunk texts (best first).
        max_tokens: Maximum total tokens allowed for RAG context.
        tokenizer: A tokenizer with an ``encode`` method (e.g. from
            ``transformers.AutoTokenizer``). If None, a rough character-
            based estimate is used (1 token ≈ 1.5 Chinese characters).

    Returns:
        A prefix of *chunks* that fits within the token budget.
    """
    total = 0
    selected: List[str] = []
    for chunk in chunks:
        if tokenizer is not None:
            chunk_tokens = len(tokenizer.encode(chunk))
        else:
            # Rough heuristic for Chinese text when tokenizer unavailable
            chunk_tokens = max(len(chunk) * 2 // 3, 1)
        if total + chunk_tokens > max_tokens:
            break
        selected.append(chunk)
        total += chunk_tokens
    return selected


# ============================================================================
# RAG Service
# ============================================================================

class RAGService:
    """Unified RAG retrieval service for the Streamlit chat app.

    Encapsulates:
      - Qwen3-Embedding-0.6B for query encoding (instruction-aware)
      - FAISS index for dense retrieval
      - BM25 index for sparse retrieval
      - RRF hybrid fusion
      - Prompt-injection sanitization
      - Token-budget context truncation

    Example (inside Streamlit)::

        @st.cache_resource
        def get_rag_service():
            return RAGService(...)

        rag = get_rag_service()
        if rag.is_available:
            results = rag.retrieve("林黛玉住在哪裡？")
    """

    def __init__(
        self,
        faiss_index_path: str,
        faiss_metadata_path: str,
        bm25_index_dir: str,
        embedding_model_path: str,
        reranker_model_path: str = None,
        top_k: int = 3,
        rrf_k: int = 60,
        score_threshold: float = 0.0,
        max_context_tokens: int = 4000,
        device: str = "auto",
        use_reranker: bool = True,
        use_hyde: bool = True,
    ):
        """Initialise the RAG service by loading all required resources.

        Args:
            faiss_index_path: Path to the ``chunks_qwen3.index`` file.
            faiss_metadata_path: Path to ``index_metadata_qwen3.json``.
            bm25_index_dir: Directory containing ``bm25_index.pkl``.
            embedding_model_path: Local path to Qwen3-Embedding-0.6B.
            reranker_model_path: Local path to Qwen3-Reranker-0.6B limit.
            top_k: Number of chunks to return after fusion.
            rrf_k: RRF constant (default 60).
            score_threshold: Minimum FAISS cosine-sim to keep a result.
            max_context_tokens: Token budget for RAG context.
            device: PyTorch device ('auto', 'cuda', 'cpu').
            use_reranker: Whether to use ranking fusion.
            use_hyde: Whether to expand user query using OpenRouter HyDE.
        """
        self._faiss_index_path = Path(faiss_index_path)
        self._faiss_metadata_path = Path(faiss_metadata_path)
        self._bm25_index_dir = Path(bm25_index_dir)
        self._embedding_model_path = Path(embedding_model_path)
        self._reranker_model_path = Path(reranker_model_path) if reranker_model_path else None
        
        self.use_reranker = use_reranker
        self.use_hyde = use_hyde
        
        # s2twp: Simplified Chinese to Traditional Chinese (Taiwan Standard)
        self.converter = opencc.OpenCC('s2twp')

        self.top_k = top_k
        self.rrf_k = rrf_k
        self.score_threshold = score_threshold
        self.max_context_tokens = max_context_tokens

        # Lazy-loaded components (populated by _load_*)
        self._encoder = None
        self._tokenizer_emb = None
        self._reranker = None
        self._faiss_index = None
        self._faiss_metadata: List[Dict[str, Any]] = []
        self._bm25 = None
        self._available = False
        self._device = device

        # Load all components synchronously (can take a moment)
        try:
            self._load_embedding_model()
            if self.use_reranker and self._reranker_model_path:
                self._load_reranker_model()
            self._load_faiss_index()
            self._load_bm25_index()
            self._available = True
            logger.info(
                "RAGService initialised successfully — "
                "FAISS: %d vectors, BM25: %d docs, top_k=%d, rrf_k=%d",
                self._faiss_index.ntotal,
                self._bm25.total_documents if self._bm25 else 0,
                self.top_k,
                self.rrf_k,
            )
        except Exception as exc:
            logger.error("RAGService init failed (degraded mode): %s", exc)
            self._available = False

    # ------------------------------------------------------------------
    # Resource loading
    # ------------------------------------------------------------------

    def _load_embedding_model(self):
        """Load Qwen3-Embedding API or local model."""
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if "api" in str(self._embedding_model_path).lower() or api_key:
            from openai import OpenAI
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY env var missing for Embedding API mode")
            
            logger.info("Initializing OpenRouter Embedding API client...")
            self._embedding_api_client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
            )
            self._tokenizer_emb = None
            self._encoder = None
            logger.info("Embedding API client ready.")
            return

        import torch
        from transformers import AutoModel, AutoTokenizer

        if self._device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(
            "Loading Qwen3-Embedding-0.6B from %s on %s …",
            self._embedding_model_path,
            self._device,
        )

        self._tokenizer_emb = AutoTokenizer.from_pretrained(
            str(self._embedding_model_path),
            trust_remote_code=True,
            padding_side='left'  # Qwen3-Embedding 官方建議左側 padding 以獲得更穩定的最後 token 池化表現
        )

        precision = torch.float16 if "cuda" in self._device else torch.float32
        self._encoder = AutoModel.from_pretrained(
            str(self._embedding_model_path),
            trust_remote_code=True,
            torch_dtype=precision,
        ).to(self._device)
        self._encoder.eval()
        logger.info("Embedding model loaded (%s, %s).", self._device, precision)

    def _load_reranker_model(self):
        """Load Qwen3-Reranker cross-encoder model."""
        is_api_mode = "api" in str(self._reranker_model_path).lower() or os.environ.get("DEEPINFRA_API_KEY")
        if not getattr(self, '_reranker_api_client', None) and not is_api_mode and not self._reranker_model_path.exists():
            logger.warning(f"Reranker model not found at {self._reranker_model_path}")
            return
            
        try:
            from sentence_transformers import CrossEncoder
            import torch
            
            # check API key or load model
            deepinfra_api_key = os.environ.get("DEEPINFRA_API_KEY")
            if "api" in str(self._reranker_model_path).lower() or deepinfra_api_key:
                # API MODE
                from openai import OpenAI
                if not deepinfra_api_key:
                    raise ValueError("DEEPINFRA_API_KEY env var missing for DeepInfra Reranker API mode")
                
                logger.info("Initializing DeepInfra Reranker API client...")
                self._reranker_api_client = OpenAI(
                    base_url="https://api.deepinfra.com/v1/openai",
                    api_key=deepinfra_api_key,
                )
                
                class MockReranker:
                    def __init__(self, client):
                        self.client = client
                        self.model_id = "Qwen/Qwen3-Reranker-8B"
                        
                    def predict(self, pairs, batch_size=None):
                        # pairs: List of [query, chunk]
                        # deepinfra reranker API doesn't exist natively on standard OpenAI spec but deepinfra supports it
                        import requests
                        scores = []
                        
                        # Deepinfra specific reranker inference endpoint
                        key = os.environ.get("DEEPINFRA_API_KEY")
                        headers = {"Authorization": f"Bearer {key}"}
                        url = f"https://api.deepinfra.com/v1/inference/{self.model_id}"
                        
                        query = pairs[0][0] # All pairs share same query
                        documents = [p[1] for p in pairs]
                        
                        try:
                            # Send batch request
                            payload = {
                                "queries": [query] * len(documents),
                                "documents": documents
                            }
                            resp = requests.post(url, headers=headers, json=payload)
                            
                            if resp.status_code == 200:
                                data = resp.json()
                                # Sort original inputs with the returned scores 
                                # (usually returned as `scores` array parallel to `documents`)
                                if "scores" in data:
                                    scores = data["scores"]
                                    return scores
                                elif "results" in data:
                                     # Sometimes format like: { "results": [{"index":0, "document":{"text":...}, "relevance_score": 0.8}] }
                                     # Need to ensure ordering matches
                                     results_map = {r["index"]: r.get("relevance_score", 0.0) for r in data["results"]}
                                     for i in range(len(documents)):
                                        scores.append(results_map.get(i, 0.0))
                                     return scores
                            
                            logger.error(f"Reranker API Error: {resp.text}")
                        except Exception as e:
                            logger.error(f"Reranker Request Failed: {e}")
                        
                        # Fallback random/0 scores if failed
                        return [0.0] * len(pairs)
                        
                self._reranker = MockReranker(self._reranker_api_client)
                logger.info("Reranker API client ready.")
                
            else:
                logger.info("Initializing Reranker model...")
            if not getattr(self, '_reranker_api_client', None):
                precision = torch.float16 if self._device != "cpu" else torch.float32
                self._reranker = CrossEncoder(
                    str(self._reranker_model_path),
                    device=self._device,
                    default_activation_function=torch.nn.Identity(),
                    trust_remote_code=True,
                    model_kwargs={"torch_dtype": precision}
                )

                # Fix for Qwen3-Reranker padding token issue
                if self._reranker.tokenizer.pad_token_id is None:
                    self._reranker.tokenizer.pad_token = self._reranker.tokenizer.eos_token
                    self._reranker.tokenizer.pad_token_id = self._reranker.tokenizer.eos_token_id

                if self._reranker.model.config.pad_token_id is None:
                    self._reranker.model.config.pad_token_id = self._reranker.tokenizer.eos_token_id

                logger.info("Reranker loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load reranker from {self._reranker_model_path}: {e}")
            self._reranker = None

    def _load_faiss_index(self):
        """Load pre-built FAISS index and its chunk metadata.

        Why read metadata separately? The metadata JSON contains the
        original ``text`` field for each indexed chunk, which we need to
        display in the Streamlit sidebar and inject into the LLM prompt.
        """
        import faiss

        if not self._faiss_index_path.exists():
            raise FileNotFoundError(
                f"FAISS index not found: {self._faiss_index_path}"
            )

        self._faiss_index = faiss.read_index(str(self._faiss_index_path))
        logger.info(
            "Loaded FAISS index: %d vectors, dim=%d",
            self._faiss_index.ntotal,
            self._faiss_index.d,
        )

        # Load metadata (contains chunk text + chunk_id)
        if self._faiss_metadata_path.exists():
            with open(self._faiss_metadata_path, "r", encoding="utf-8") as f:
                self._faiss_metadata = json.load(f)
            logger.info("Loaded FAISS metadata: %d entries", len(self._faiss_metadata))
        else:
            logger.warning(
                "FAISS metadata file not found: %s — "
                "chunk text will not be available for dense results.",
                self._faiss_metadata_path,
            )

    def _load_bm25_index(self):
        """Load pre-built BM25 index from pickle.

        Why dynamic sys.path? BM25Search lives in src/main/python/services/,
        but this file is under app/streamlit/. We resolve the path at
        runtime from the project root.
        """
        import sys
        # In the new structure, both rag_service and bm25_search are in the same folder.
        # However, backend/main.py will add src/main/python to sys.path,
        # so we can just import it directly from services.bm25_search
        
        try:
            from services.bm25_search import BM25Search
        except ImportError:
            # Fallback for local testing or relative imports
            from bm25_search import BM25Search

        bm25_pkl = self._bm25_index_dir / "bm25_index.pkl"
        if not bm25_pkl.exists():
            raise FileNotFoundError(f"BM25 index not found: {bm25_pkl}")

        self._bm25 = BM25Search()
        self._bm25.load(str(self._bm25_index_dir))
        logger.info(
            "Loaded BM25 index: %d docs", self._bm25.total_documents
        )

    # ------------------------------------------------------------------
    # Encoding (asymmetric: query ≠ document)
    # ------------------------------------------------------------------

    def _last_token_pool(self, last_hidden_states, attention_mask):
        """Qwen3-Embedding 官方指定的 Last Token Pooling"""
        import torch
        left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
        if left_padding:
            return last_hidden_states[:, -1]
        else:
            sequence_lengths = attention_mask.sum(dim=1) - 1
            batch_size = last_hidden_states.shape[0]
            return last_hidden_states[
                torch.arange(batch_size, device=last_hidden_states.device),
                sequence_lengths
            ]

    def _encode_texts(self, texts: List[str]) -> np.ndarray:
        """Encode a batch of texts into normalised embeddings."""
        import torch
        import numpy as np
        
        # Check if using API mode
        if hasattr(self, '_embedding_api_client') and self._embedding_api_client:
            model_id = "qwen/qwen3-embedding-8b" # Adjust if your actual API model differs
            try:
                resp = self._embedding_api_client.embeddings.create(
                    model=model_id,
                    input=texts
                )
                
                # Sort embedding objects by their index just in case they're out of order
                sorted_embs = sorted(resp.data, key=lambda x: x.index)
                
                # L2 normalization (OpenRouter's output might be normalized already, but safety first)
                embs_array = np.array([item.embedding for item in sorted_embs], dtype="float32")
                norms = np.linalg.norm(embs_array, axis=1, keepdims=True)
                # Avoid division by zero
                norms[norms == 0] = 1e-10
                embs_array = embs_array / norms
                
                return embs_array
            except Exception as e:
                logger.error(f"Embedding API Request Failed: {e}")
                # Fallback to zeros (which breaks similarity but avoids full crash)
                # Ensure dim matches your FAISS index
                dim = self._faiss_index.d if self._faiss_index else 3584 
                return np.zeros((len(texts), dim), dtype="float32")

        batch_dict = self._tokenizer_emb(
            texts,
            max_length=512,
            padding=True,
            truncation=True,
            return_tensors="pt",
        ).to(self._device)

        with torch.no_grad():
            outputs = self._encoder(**batch_dict)
            # ★ 改用 Last Token Pool
            embeddings = self._last_token_pool(
                outputs.last_hidden_state, batch_dict["attention_mask"]
            )

            # L2 normalise for cosine similarity via inner product
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

        result = embeddings.cpu().numpy().astype("float32")
        del embeddings
        del batch_dict
        if "cuda" in self._device:
            torch.cuda.empty_cache()
            
        return result

    def encode_query(self, query: str) -> np.ndarray:
        """Encode a user query with the instruction prefix.

        Why asymmetric? Qwen3-Embedding is instruction-aware: adding a
        task-specific prefix to the query (but NOT to documents) yields
        1-5 % retrieval quality gains, as documented in the official repo.

        Args:
            query: Raw user query string.

        Returns:
            Normalised embedding of shape (dim,).
        """
        instructed = QUERY_INSTRUCTION + query
        return self._encode_texts([instructed])[0]

    def encode_document(self, text: str) -> np.ndarray:
        """Encode a document chunk WITHOUT instruction prefix.

        Args:
            text: Chunk text.

        Returns:
            Normalised embedding of shape (dim,).
        """
        return self._encode_texts([text])[0]

    # ------------------------------------------------------------------
    # Retrieval pipeline
    # ------------------------------------------------------------------

    def _faiss_search(
        self, query_embedding: np.ndarray, depth: int = 100
    ) -> List[Dict[str, Any]]:
        """Dense retrieval via FAISS inner-product search.

        Args:
            query_embedding: Normalised query vector of shape (dim,).
            depth: Number of candidates to retrieve.

        Returns:
            List of dicts with keys: id, score, text, chunk_id.
        """
        import faiss as _faiss  # noqa: F811

        qvec = query_embedding.reshape(1, -1).astype("float32")
        _faiss.normalize_L2(qvec)

        scores, indices = self._faiss_index.search(qvec, depth)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            # Apply minimum score threshold
            if score < self.score_threshold:
                continue

            meta = {}
            text = ""
            chunk_id = str(idx)
            if idx < len(self._faiss_metadata):
                meta = self._faiss_metadata[idx]
                text = meta.get("page_content", meta.get("text", ""))
                # Safely get chunk_id directly from root or from nested metadata
                chunk_id = meta.get("chunk_id")
                if not chunk_id and "metadata" in meta:
                    chunk_id = meta["metadata"].get("chunk_id", str(idx))
                elif not chunk_id:
                    chunk_id = str(idx)
                
                # Also try to resolve source
                source = meta.get("source", "")
                if not source and "metadata" in meta:
                    source = meta["metadata"].get("source", "")

            results.append({
                "id": idx,
                "score": float(score),
                "text": text,
                "chunk_id": chunk_id,
                "source": meta.get("source", ""),
            })
        return results

    def _bm25_search(
        self, query: str, depth: int = 100
    ) -> List[Dict[str, Any]]:
        """Sparse retrieval via BM25.

        Args:
            query: Raw query text.
            depth: Number of candidates.

        Returns:
            List of dicts with keys: id, score, text, chunk_id.
        """
        if self._bm25 is None:
            return []

        bm25_results = self._bm25.search(query, top_k=depth)
        results = []
        for r in bm25_results:
            chunk_id = str(r.id)
            # Resolve chunk_id from BM25's internal mapping if available
            if hasattr(self._bm25, "chunk_id_mapping") and self._bm25.chunk_id_mapping:
                chunk_id = self._bm25.chunk_id_mapping.get(str(r.id), str(r.id))
            
            source = ""
            if r.metadata:
                chunk_id = r.metadata.get("chunk_id", chunk_id)
                if ("metadata" in r.metadata and 
                    isinstance(r.metadata["metadata"], dict)):
                    chunk_id = r.metadata["metadata"].get("chunk_id", chunk_id)
                    source = r.metadata["metadata"].get("source", "")
                
                if not source:
                    source = r.metadata.get("source", "")

            results.append({
                "id": r.id,
                "score": float(r.score),
                "text": r.metadata.get("page_content", r.text) if r.metadata else r.text,
                "chunk_id": chunk_id,
                "source": source,
            })
        return results

    def _rrf_fusion(
        self,
        dense_results: List[Dict[str, Any]],
        sparse_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Reciprocal Rank Fusion of dense and sparse results.

        Formula: RRF(d) = α / (k + rank_dense) + β / (k + rank_sparse)
        Default weights: α=0.6 (dense), β=0.4 (sparse).

        Why RRF? It is the most robust zero-shot fusion method for
        combining heterogeneous retrieval signals (dense semantic vs.
        sparse keyword). The k parameter controls the emphasis on top
        ranks vs. lower ranks.

        Args:
            dense_results: FAISS results (ranked by cosine similarity).
            sparse_results: BM25 results (ranked by BM25 score).

        Returns:
            Fused results sorted by RRF score (descending).
        """
        k = self.rrf_k
        alpha, beta = 0.5, 0.5  # Equal weight works best with missing rank penalty

        scores: Dict[str, Dict[str, Any]] = {}
        
        dense_max_rank = len(dense_results) + 1
        sparse_max_rank = len(sparse_results) + 1

        # Pre-fill scores for all unique doc_ids to handle missing ranks
        all_ids = set([r["id"] for r in dense_results]) | set([r["id"] for r in sparse_results])
        
        for doc_id in all_ids:
            scores[doc_id] = {
                "rrf_score": 0.0,
                "text": "",
                "chunk_id": "",
                "source": "",
                "found_in_dense": False,
                "found_in_sparse": False
            }

        # Dense contributions
        for rank, item in enumerate(dense_results, start=1):
            doc_id = item["id"]
            scores[doc_id].update({
                "text": item.get("text", ""),
                "chunk_id": item.get("chunk_id", ""),
                "source": item.get("source", ""),
                "found_in_dense": True
            })
            scores[doc_id]["rrf_score"] += alpha / (k + rank)

        # Sparse contributions
        for rank, item in enumerate(sparse_results, start=1):
            doc_id = item["id"]
            if not scores[doc_id]["text"]:
                scores[doc_id].update({
                    "text": item.get("text", ""),
                    "chunk_id": item.get("chunk_id", ""),
                    "source": item.get("source", "")
                })
            scores[doc_id]["found_in_sparse"] = True
            scores[doc_id]["rrf_score"] += beta / (k + rank)
            
        # Add penalty ranks for missing ones
        for doc_id, meta in scores.items():
            if not meta["found_in_dense"]:
                meta["rrf_score"] += alpha / (k + dense_max_rank)
            if not meta["found_in_sparse"]:
                meta["rrf_score"] += beta / (k + sparse_max_rank)

        # Sort by RRF score descending
        fused = sorted(scores.values(), key=lambda x: x["rrf_score"], reverse=True)
        return fused
        
    def _expand_query_with_hyde(self, query: str) -> str:
        """Perform text expansion (HyDE) via OpenRouter to improve retrieval."""
        import requests
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("No OPENROUTER_API_KEY found. Skipping HyDE expansion.")
            return query

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Perform standard HyDE (Hypothetical Document Embeddings)
        prompt = f"""請針對以下關於古文或國學常識的問題，撰寫一段假想的「詳細解答文本」（約100字內）。
請盡量包含相關的原文關鍵字、專有名詞或主旨，這將用於作為語義檢索的文本擴寫特徵。

問題：{query}
直接輸出擴寫文本，不要任何解釋或多餘的開頭："""

        payload = {
            "model": "qwen/qwen3-30b-a3b-instruct-2507",
            "messages": [
                {"role": "system", "content": "你是一個優化語義檢索的國學領域專家。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 150,
        }

        try:
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers, timeout=15)
            if response.ok:
                data = response.json()
                expanded_text = data["choices"][0]["message"]["content"].strip()
                if expanded_text:
                    # Apply OpenCC conversion as a failsafe
                    expanded_text = self.converter.convert(expanded_text)
                    logger.info("HyDE Expansion successful.")
                    return f"{query}\n[擴寫特徵]: {expanded_text}"
        except Exception as e:
            logger.error(f"Failed to expand query '{query}': {e}")
            
        return query

    def retrieve(
        self,
        query: str,
        tokenizer=None,
    ) -> List[RetrievalResult]:
        """Execute the full RAG retrieval pipeline.

        Pipeline: encode → FAISS search → BM25 search → RRF fusion
                  → sanitize → truncate (token budget)

        Args:
            query: User query in natural language.
            tokenizer: Optional tokenizer for accurate token counting
                during truncation. Should have an ``encode()`` method.

        Returns:
            List of RetrievalResult with text ready for prompt injection.
        """
        return self.retrieve_with_debug(query, tokenizer=tokenizer).final_results

    def retrieve_with_debug(
        self,
        query: str,
        tokenizer=None,
    ) -> RetrievalDebugInfo:
        """Execute retrieval and return both final chunks and debug traces.

        Args:
            query: User query in natural language.
            tokenizer: Optional tokenizer for accurate token counting.

        Returns:
            RetrievalDebugInfo describing every major retrieval stage.
        """
        # Exhaust the generator to get the final results
        final_info = None
        for event in self.retrieve_with_events(query, tokenizer):
            if event["type"] == "results":
                final_info = event["data"]
        return final_info or RetrievalDebugInfo(query=query)

    def retrieve_with_events(
        self,
        query: str,
        tokenizer=None,
    ):
        """Execute retrieval and yield progress events before returning final results.

        Yields:
            Dict containing event type ('status' or 'results') and data.
        """
        debug_info = RetrievalDebugInfo(query=query)

        if not self._available:
            logger.warning("RAGService unavailable — returning empty results.")
            return debug_info

        if not query or not query.strip():
            yield {"type": "results", "data": debug_info}
            return

        yield {"type": "status", "status": "searching_dense", "message": "📖 翻閱古籍索引..."}
        
        # Step 0: HyDE Text Expansion (if enabled)
        search_query = query
        if getattr(self, 'use_hyde', False) and len(query) > 10:
            search_query = self._expand_query_with_hyde(query)

        # Step 1: Encode query (with instruction prefix)
        query_embedding = self.encode_query(search_query)

        # Step 2: Dense + Sparse retrieval
        dense_results = self._faiss_search(query_embedding, depth=100)
        debug_info.dense_results = dense_results
        
        yield {"type": "status", "status": "searching_sparse", "message": "🔤 查考字詞出處..."}
        sparse_results = self._bm25_search(search_query, depth=100)
        debug_info.sparse_results = sparse_results

        yield {"type": "status", "status": "reranking", "message": "⚖️ 比較文獻相關性..."}
        # Step 3: RRF Fusion
        fused = self._rrf_fusion(dense_results, sparse_results)
        
        # Step 3.5: Reranker (if enabled and available)
        if getattr(self, 'use_reranker', False) and hasattr(self, '_reranker') and self._reranker is not None:
            # Only rerank top 50 candidates to save time
            candidates = fused[:50]
            if candidates:
                pairs = [[query, item["text"]] for item in candidates]
                import torch
                # Process in smaller batches to avoid OOM
                # We check if it's the MockReranker (API) or the local model
                is_api = hasattr(self._reranker, 'model_id')
                
                if is_api:
                     scores = self._reranker.predict(pairs, batch_size=2)
                else:
                    with torch.no_grad():
                        scores = self._reranker.predict(pairs, batch_size=2)
                    
                # Store reranker scores and re-sort
                for item, score in zip(candidates, scores):
                    item["reranker_score"] = float(score)
                    
                candidates = sorted(candidates, key=lambda x: x["reranker_score"], reverse=True)
                fused = candidates + fused[50:]
                
        # Step 3.6: Diversity Filter (同源 Chunk 去重)
        seen_sources = set()
        diverse_fused = []
        for item in fused:
            chunk_id = item.get("chunk_id", "")
            source_prefix = chunk_id.split('_')[0] if chunk_id else ""
            if source_prefix and source_prefix in seen_sources:
                continue
            if source_prefix:
                seen_sources.add(source_prefix)
            diverse_fused.append(item)
        fused = diverse_fused
                
        debug_info.fused_results = fused

        # Step 4: Take top-k
        top_results = fused[: self.top_k]
        
        # Calculate highest score for Layer 2 Gatekeeper logic
        highest_score = 0.0
        if top_results:
            first_item = top_results[0]
            highest_score = first_item.get("reranker_score", first_item.get("rrf_score", 0.0))
        debug_info.highest_score = highest_score

        # Step 5: Sanitize (prompt injection defence)
        sanitized = []
        sanitized_count = 0
        for item in top_results:
            # Apply threshold filter for final injection
            # Adapt threshold based on whether we have reranker scores or raw RRF scores
            is_reranked = "reranker_score" in item
            effective_threshold = self.score_threshold if is_reranked else 0.005
            
            current_score = item.get("reranker_score", item.get("rrf_score", 0.0))
            if current_score < effective_threshold:
                continue
                
            clean_text = sanitize_chunk(item["text"])
            if clean_text != item["text"]:
                sanitized_count += 1
            sanitized.append(RetrievalResult(
                text=clean_text,
                chunk_id=item.get("chunk_id", ""),
                score=current_score,
                source=item.get("source", ""),
            ))

        # Step 6: Truncate to token budget
        texts = [r.text for r in sanitized]
        truncated_texts = truncate_rag_context(
            texts,
            max_tokens=self.max_context_tokens,
            tokenizer=tokenizer,
        )

        # Only keep results whose text survived truncation
        final = sanitized[: len(truncated_texts)]
        debug_info.final_results = final
        debug_info.context = self.format_context(final)
        debug_info.sanitized_count = sanitized_count
        debug_info.truncated_count = max(len(sanitized) - len(final), 0)
        yield {"type": "results", "data": debug_info}

    def format_context(self, results: List[RetrievalResult]) -> str:
        """Format retrieval results into the prompt context block.

        Uses XML-like <context> tags for clear separation between
        retrieved content and user instructions, reducing prompt
        injection confusion.

        Args:
            results: List of RetrievalResult from ``retrieve()``.

        Returns:
            Formatted context string ready for prompt insertion.
        """
        if not results:
            return ""

        # U-shape ordering: highest score first, second highest last, to mitigate Lost in the Middle
        if len(results) >= 3:
            sorted_results = sorted(results, key=lambda x: x.score, reverse=True)
            u_shaped = [sorted_results[0]] + sorted_results[2:] + [sorted_results[1]]
        else:
            u_shaped = results

        chunks_text = "\n\n".join(
            f"[參考資料 {i + 1}] {r.text}" for i, r in enumerate(u_shaped)
        )
        return f"<context>\n{chunks_text}\n</context>"

    @property
    def is_available(self) -> bool:
        """Whether the service loaded successfully and is ready to use.

        When False, the chat app should gracefully fall back to pure LM
        mode without RAG augmentation.
        """
        return self._available
