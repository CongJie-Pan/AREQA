"""
BM25 Search Service (P1-T03, Enhanced for P2-T10)

This module provides a rank-bm25 based BM25 search implementation
that is API-compatible with Elasticsearch for easy migration to Tier 2.

Enhanced Features (P2-T10):
    - Support for custom BM25 parameters (k1, b)
    - Integration with AncientChineseTokenizer for classical Chinese
    - Optimized default parameters for short classical Chinese texts
    - Keyword enhancement support

Reference: 
    - docs/RA_DIT-ancient-chinese-qa-spec/04-data.md §4.3.4.2
    - docs/RA_DIT-ancient-chinese-qa-spec/07-system-architecture.md
"""

import json
import jieba
from rank_bm25 import BM25Okapi
from typing import List, Tuple, Optional, Dict, Any, Callable, Union
from dataclasses import dataclass, field
from pathlib import Path
import pickle
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# BM25 Configuration for Ancient Chinese (based on IR research)
# ============================================================================

@dataclass
class BM25Config:
    """
    Configuration for BM25 parameters optimized for ancient Chinese.
    
    Research-backed defaults for short classical Chinese texts:
    - k1=1.5: Higher than default (1.2) because repeated terms in short 
              texts are more significant
    - b=0.4:  Lower than default (0.75) because document lengths are 
              uniform and content density is high in classical Chinese
    
    Reference: Perplexity research on BM25 for classical Chinese IR
    """
    k1: float = 1.5   # Term frequency saturation parameter
    b: float = 0.4    # Document length normalization parameter
    
    # Standard BM25 defaults for comparison
    STANDARD_K1: float = 1.2
    STANDARD_B: float = 0.75


@dataclass
class BM25Result:
    """
    Represents a single BM25 search result.

    Attributes:
        id: Document/chunk ID.
        score: BM25 score (higher is better).
        text: Original text content.
        metadata: Optional metadata associated with the document.
    """
    id: int
    score: float
    text: str
    metadata: Optional[Dict[str, Any]] = None


class BM25Search:
    """
    BM25 search service using rank-bm25 with configurable tokenization.

    This class provides an Elasticsearch-compatible API for BM25 search
    using rank-bm25 as the backend. Designed for Tier 1 (research) deployment.
    
    Enhanced for P2-T10 with:
    - Configurable BM25 parameters (k1, b) optimized for ancient Chinese
    - Support for AncientChineseTokenizer
    - Keyword enhancement for improved recall

    Attributes:
        tokenizer: Tokenization function.
        config: BM25Config with k1 and b parameters.

    Example:
        >>> # With default ancient Chinese optimization
        >>> search = BM25Search()
        >>> search.add_documents(texts, ids)
        >>> results = search.search("林黛玉葬花", top_k=10)
        
        >>> # With custom tokenizer
        >>> from core.tokenizers import AncientChineseTokenizer
        >>> tokenizer = AncientChineseTokenizer()
        >>> search = BM25Search(tokenizer=tokenizer.tokenize, k1=1.5, b=0.4)
    """

    def __init__(
        self,
        tokenizer: Optional[Callable[[str], List[str]]] = None,
        stopwords: Optional[List[str]] = None,
        k1: float = 1.5,
        b: float = 0.4,
    ):
        """
        Initialize BM25 search.

        Args:
            tokenizer: Custom tokenizer function. Default uses jieba.lcut.
            stopwords: List of stopwords to filter out.
            k1: BM25 term frequency saturation parameter (default: 1.5 for short texts).
            b: BM25 document length normalization parameter (default: 0.4 for uniform lengths).
        """
        self.tokenizer = tokenizer or self._default_tokenizer
        self.stopwords = set(stopwords) if stopwords else self._default_stopwords()
        
        # BM25 parameters (optimized for ancient Chinese)
        self.k1 = k1
        self.b = b
        self.config = BM25Config(k1=k1, b=b)

        # BM25 index (will be created when documents are added)
        self.bm25: Optional[BM25Okapi] = None

        # Document storage
        self.documents: List[str] = []
        self.tokenized_docs: List[List[str]] = []
        self.doc_ids: List[int] = []
        self.metadata: Dict[int, Dict[str, Any]] = {}
        
        # Chunk ID mapping (for string IDs like "chapter_001")
        self.chunk_id_mapping: Dict[int, str] = {}

        logger.info(f"Initialized BM25Search with k1={k1}, b={b}")

    def _default_tokenizer(self, text: str) -> List[str]:
        """
        Default tokenizer using jieba for Chinese text.

        Args:
            text: Input text to tokenize.

        Returns:
            List of tokens.
        """
        tokens = jieba.lcut(text)
        # Filter stopwords and single characters (optional)
        tokens = [t for t in tokens if t not in self.stopwords and len(t.strip()) > 0]
        return tokens

    def _default_stopwords(self) -> set:
        """
        Return default Chinese stopwords.

        Returns:
            Set of stopwords.
        """
        # Common Chinese stopwords
        return {
            "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
            "都", "一", "一個", "上", "也", "很", "到", "說", "要", "去",
            "你", "會", "著", "沒有", "看", "好", "自己", "這", "那", "他",
            "她", "它", "們", "這個", "那個", "什麼", "怎麼", "為什麼",
            "可以", "因為", "所以", "但是", "如果", "或者", "而且", "之",
            "其", "以", "於", "為", "與", "則", "乃", "亦", "而", "且",
            "若", "故", "然", "者", "也", "矣", "焉", "哉", "乎", "耳",
        }

    def add_documents(
        self,
        texts: List[str],
        ids: Optional[List[int]] = None,
        metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Add documents to the BM25 index.

        Args:
            texts: List of document texts.
            ids: Optional list of document IDs.
            metadata: Optional list of metadata dicts.
        """
        # Generate IDs if not provided
        if ids is None:
            start_id = len(self.doc_ids)
            ids = list(range(start_id, start_id + len(texts)))

        # Tokenize documents
        new_tokenized = [self.tokenizer(text) for text in texts]

        # Store documents
        self.documents.extend(texts)
        self.tokenized_docs.extend(new_tokenized)
        self.doc_ids.extend(ids)

        # Store metadata
        if metadata:
            for doc_id, meta in zip(ids, metadata):
                self.metadata[doc_id] = meta

        # Rebuild BM25 index with custom parameters
        self.bm25 = BM25Okapi(self.tokenized_docs, k1=self.k1, b=self.b)

        logger.info(f"Added {len(texts)} documents. Total: {len(self.documents)}")

    def search(
        self,
        query: str,
        top_k: int = 10,
    ) -> List[BM25Result]:
        """
        Search for documents matching the query.

        Args:
            query: Search query string.
            top_k: Number of results to return.

        Returns:
            List of BM25Result objects sorted by score (descending).
        """
        if self.bm25 is None or len(self.documents) == 0:
            logger.warning("No documents indexed. Returning empty results.")
            return []

        # Tokenize query
        query_tokens = self.tokenizer(query)

        # Get BM25 scores for all documents
        scores = self.bm25.get_scores(query_tokens)

        # Get top-k indices
        top_indices = scores.argsort()[-top_k:][::-1]

        # Build results
        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score <= 0:  # Skip zero-score results
                continue

            doc_id = self.doc_ids[idx]
            text = self.documents[idx]
            meta = self.metadata.get(doc_id)

            results.append(BM25Result(
                id=doc_id,
                score=score,
                text=text,
                metadata=meta,
            ))

        return results

    def batch_search(
        self,
        queries: List[str],
        top_k: int = 10,
    ) -> List[List[BM25Result]]:
        """
        Batch search for multiple queries.

        Args:
            queries: List of query strings.
            top_k: Number of results per query.

        Returns:
            List of result lists, one per query.
        """
        return [self.search(query, top_k) for query in queries]

    def save(self, path: str) -> None:
        """
        Save index and documents to disk.

        Args:
            path: Directory path to save files.
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        data = {
            "documents": self.documents,
            "tokenized_docs": self.tokenized_docs,
            "doc_ids": self.doc_ids,
            "metadata": self.metadata,
            "chunk_id_mapping": self.chunk_id_mapping,
            "config": {
                "k1": self.k1,
                "b": self.b,
            }
        }

        with open(path / "bm25_index.pkl", "wb") as f:
            pickle.dump(data, f)
        
        # Also save metadata as JSON for inspection
        metadata_json = {
            "total_documents": len(self.documents),
            "k1": self.k1,
            "b": self.b,
            "vocab_size": len(set(token for doc in self.tokenized_docs for token in doc)),
            "avg_doc_length": sum(len(doc) for doc in self.tokenized_docs) / len(self.tokenized_docs) if self.tokenized_docs else 0,
        }
        with open(path / "index_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata_json, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved BM25 index to {path}")

    def load(self, path: str) -> None:
        """
        Load index and documents from disk.

        Args:
            path: Directory path containing saved files.
        """
        path = Path(path)

        with open(path / "bm25_index.pkl", "rb") as f:
            data = pickle.load(f)

        if isinstance(data, dict):
            self.documents = data.get("documents", [])
            self.tokenized_docs = data.get("tokenized_docs", [])
            self.doc_ids = data.get("doc_ids", [])
            self.metadata = data.get("metadata", {})
            self.chunk_id_mapping = data.get("chunk_id_mapping", {})
            
            # Load config if available
            if "config" in data:
                self.k1 = data["config"]["k1"]
                self.b = data["config"]["b"]
                self.config = BM25Config(k1=self.k1, b=self.b)

            # Rebuild BM25 index with saved parameters
            self.bm25 = BM25Okapi(self.tokenized_docs, k1=self.k1, b=self.b)
        else:
            # Assume it's a direct BM25Okapi object (legacy or alternative format)
            self.bm25 = data
            
            # Try to load metadata to reconstruct IDs
            metadata_path = path / "bm25_metadata.json"
            if metadata_path.exists():
                try:
                    import json
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        if "chunk_ids" in meta:
                            chunk_ids = meta["chunk_ids"]
                            self.doc_ids = list(range(len(chunk_ids)))
                            self.chunk_id_mapping = {str(i): cid for i, cid in enumerate(chunk_ids)}
                            # Mock documents to avoid index out of bounds during search
                            self.documents = [""] * len(chunk_ids)
                            self.metadata = {i: {"chunk_id": cid} for i, cid in enumerate(chunk_ids)}
                except Exception as e:
                    logger.warning(f"Could not load metadata from {metadata_path}: {e}")
                    
            if not getattr(self, "documents", None):
                # Fallback to empty values if no metadata
                size = getattr(self.bm25, "corpus_size", 0)
                self.documents = [""] * size
                self.doc_ids = list(range(size))
                self.chunk_id_mapping = {}

        logger.info(f"Loaded BM25 index from {path}. Total: {len(self.documents)}, k1={self.k1}, b={self.b}")

    @property
    def total_documents(self) -> int:
        """Return total number of indexed documents."""
        return len(self.documents)

    # =========================================================================
    # Elasticsearch-compatible API (for future migration to Tier 2)
    # =========================================================================

    def index(
        self,
        documents: List[Dict[str, Any]],
        text_field: str = "text",
        id_field: str = "id",
    ) -> None:
        """
        Elasticsearch-compatible index API.

        Args:
            documents: List of document dicts.
            text_field: Field name containing text.
            id_field: Field name containing ID.
        """
        texts = [doc[text_field] for doc in documents]
        ids = [doc.get(id_field, i) for i, doc in enumerate(documents)]
        metadata = [
            {k: v for k, v in doc.items() if k not in [text_field, id_field]}
            for doc in documents
        ]

        self.add_documents(texts, ids, metadata)

    def query_string(
        self,
        query: str,
        size: int = 10,
    ) -> Dict[str, Any]:
        """
        Elasticsearch-compatible query API.

        Args:
            query: Query string.
            size: Max results.

        Returns:
            Dict with 'hits' containing results.
        """
        results = self.search(query, top_k=size)

        return {
            "hits": {
                "total": {"value": len(results)},
                "hits": [
                    {
                        "_id": r.id,
                        "_score": r.score,
                        "_source": {
                            "text": r.text,
                            **(r.metadata or {}),
                        },
                    }
                    for r in results
                ],
            }
        }
