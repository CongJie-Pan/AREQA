#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-T10: BM25 Index Builder for Ancient Chinese RAG

This script builds a high-quality BM25 index from RAG chunks using
the AncientChineseTokenizer with Unigram + Bigram strategy.

Usage:
    python scripts/p2_t10_bm25_indexer.py

Features:
    - Loads all *_chunks.json files from data/rag/chunks/
    - Uses Unigram + Bigram tokenization (optimized for classical Chinese)
    - Applies keyword enhancement from chunk metadata
    - Configures BM25 with k1=1.5, b=0.4 (optimized for short texts)
    - Saves index and metadata to data/rag/bm25_index/

Research Background:
    - Character-level (unigram) tokenization works better for classical Chinese
      where each character often carries independent meaning
    - Bigrams capture common collocations without dictionary dependency
    - k1=1.5 (higher than default) for short texts where repetition matters more
    - b=0.4 (lower than default) for uniform-length chunks with high content density

Output Files:
    - data/rag/bm25_index/bm25_index.pkl       - Serialized BM25 index
    - data/rag/bm25_index/tokenized_corpus.pkl - Tokenized corpus for inspection
    - data/rag/bm25_index/chunk_mapping.json   - Chunk ID to index mapping
    - data/rag/bm25_index/index_metadata.json  - Index statistics

Author: ML Engineer
Date: 2026-01-07
Task: P2-T10 (WorkList_71Days.md)
Reference: docs/RA_DIT-ancient-chinese-qa-spec/04-data.md §4.3.4.2
"""

import os
import sys
import json
import pickle
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
from collections import Counter

from tqdm import tqdm

# Add src to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # scripts/rag -> scripts -> project root
sys.path.insert(0, str(PROJECT_ROOT / "src" / "main" / "python"))

from core.tokenizers import (
    AncientChineseTokenizer, 
    TokenizerConfig, 
    TokenizationMethod
)
from rank_bm25 import BM25Okapi

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

# Paths
CHUNKS_DIR = PROJECT_ROOT / "data" / "rag" / "chunks"
BM25_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "bm25_index"

# BM25 Parameters (optimized for ancient Chinese short texts)
BM25_K1 = 1.5   # Term frequency saturation (higher for short texts)
BM25_B = 0.4    # Length normalization (lower for uniform lengths)

# Tokenization Configuration
TOKENIZATION_METHOD = TokenizationMethod.NGRAM  # Unigram + Bigram
KEYWORD_WEIGHT = 2  # Keywords appear 2x for enhanced recall


# ============================================================================
# Data Loading
# ============================================================================

def load_all_chunks(chunks_dir: Path) -> Tuple[List[Dict], Dict[str, str]]:
    """
    Load all chunks from JSON files in the chunks directory.
    
    Args:
        chunks_dir: Path to directory containing *_chunks.json files.
        
    Returns:
        Tuple of (chunks list, source file mapping).
    """
    all_chunks = []
    source_mapping = {}
    
    chunk_files = list(chunks_dir.glob("*_chunks.json"))
    logger.info(f"Found {len(chunk_files)} chunk files in {chunks_dir}")
    
    for json_file in chunk_files:
        logger.info(f"Loading {json_file.name}...")
        with open(json_file, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        
        for chunk in chunks:
            chunk_id = chunk.get('chunk_id', '')
            source_mapping[chunk_id] = json_file.stem
            all_chunks.append(chunk)
    
    logger.info(f"Loaded {len(all_chunks)} total chunks")
    return all_chunks, source_mapping


# ============================================================================
# Index Building
# ============================================================================

class BM25IndexBuilder:
    """
    Builds BM25 index with AncientChineseTokenizer.
    
    This class handles the complete index building pipeline:
    1. Initialize tokenizer with N-gram strategy
    2. Tokenize all chunks with keyword enhancement
    3. Build BM25Okapi index with custom parameters
    4. Save all artifacts for later loading
    """
    
    def __init__(
        self,
        k1: float = BM25_K1,
        b: float = BM25_B,
        method: TokenizationMethod = TOKENIZATION_METHOD,
        keyword_weight: int = KEYWORD_WEIGHT,
    ):
        """
        Initialize the index builder.
        
        Args:
            k1: BM25 term frequency saturation parameter.
            b: BM25 document length normalization parameter.
            method: Tokenization method to use.
            keyword_weight: Weight for keyword enhancement.
        """
        self.k1 = k1
        self.b = b
        
        # Initialize tokenizer
        config = TokenizerConfig(
            method=method,
            include_unigrams=True,
            include_bigrams=True,
            keyword_weight=keyword_weight,
        )
        self.tokenizer = AncientChineseTokenizer(config)
        
        logger.info(f"Initialized BM25IndexBuilder:")
        logger.info(f"  - k1={k1}, b={b}")
        logger.info(f"  - Tokenization: {method.value}")
        logger.info(f"  - Keyword weight: {keyword_weight}")
    
    def tokenize_chunks(
        self,
        chunks: List[Dict],
        show_progress: bool = True,
        output_dir: Path = BM25_INDEX_DIR
    ) -> Tuple[List[List[str]], List[str], List[Dict]]:
        """
        Tokenize all chunks with keyword enhancement and checkpointing.
        
        Args:
            chunks: List of chunk dictionaries.
            show_progress: Whether to show progress bar.
            output_dir: Directory to save checkpoint.
            
        Returns:
            Tuple of (tokenized_corpus, chunk_ids, metadata_list).
        """
        tokenized_corpus = []
        chunk_ids = []
        metadata_list = []
        
        checkpoint_path = output_dir / "tokenization_checkpoint.pkl"
        start_index = 0
        
        # [Resume Logic]
        if checkpoint_path.exists():
            try:
                logger.info(f"Adding resume capability... Found checkpoint: {checkpoint_path}")
                with open(checkpoint_path, "rb") as f:
                    data = pickle.load(f)
                    tokenized_corpus = data.get("tokenized_corpus", [])
                    chunk_ids = data.get("chunk_ids", [])
                    metadata_list = data.get("metadata_list", [])
                    start_index = len(tokenized_corpus)
                    logger.info(f"Resuming from index {start_index} ({len(chunks)} total)")
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}. Starting from scratch.")
        
        if start_index >= len(chunks):
            logger.info("All chunks already tokenized in checkpoint.")
            return tokenized_corpus, chunk_ids, metadata_list

        iterator = chunks[start_index:]
        if show_progress:
            iterator = tqdm(iterator, desc="Tokenizing", initial=start_index, total=len(chunks))
        
        for i, chunk in enumerate(iterator):
            text = chunk.get('text', '')
            keywords = chunk.get('keywords', [])
            chunk_id = chunk.get('chunk_id', '')
            
            # Tokenize with keyword enhancement
            tokens = self.tokenizer.tokenize(text, keywords=keywords)
            
            tokenized_corpus.append(tokens)
            chunk_ids.append(chunk_id)
            
            # Build metadata
            meta = {
                'chunk_id': chunk_id,
                'source': chunk.get('source', ''),
                'text_type': chunk.get('text_type', ''),
                'length': chunk.get('length', len(text)),
                'keywords': keywords,
                'metadata': chunk.get('metadata', {}),
            }
            metadata_list.append(meta)
            
            # [Checkpoint Logic] Save every 1000 items
            current_idx = start_index + i + 1
            if current_idx % 1000 == 0:
                try:
                    with open(checkpoint_path, "wb") as f:
                        pickle.dump({
                            "tokenized_corpus": tokenized_corpus,
                            "chunk_ids": chunk_ids,
                            "metadata_list": metadata_list
                        }, f)
                except Exception as e:
                    logger.warning(f"Failed to save checkpoint: {e}")
        
        # Final save/cleanup (optional, or keep checkpoint until explicitly cleared)
        return tokenized_corpus, chunk_ids, metadata_list
    
    def build_index(
        self,
        tokenized_corpus: List[List[str]],
    ) -> BM25Okapi:
        """
        Build BM25Okapi index from tokenized corpus.
        
        Args:
            tokenized_corpus: List of token lists.
            
        Returns:
            BM25Okapi index instance.
        """
        logger.info(f"Building BM25Okapi index with k1={self.k1}, b={self.b}...")
        bm25 = BM25Okapi(tokenized_corpus, k1=self.k1, b=self.b)
        logger.info("BM25 index built successfully")
        return bm25
    
    def compute_statistics(
        self,
        tokenized_corpus: List[List[str]],
        chunks: List[Dict],
    ) -> Dict[str, Any]:
        """
        Compute index statistics for metadata.
        
        Args:
            tokenized_corpus: Tokenized document list.
            chunks: Original chunk list.
            
        Returns:
            Dictionary of statistics.
        """
        # Token statistics
        all_tokens = [token for doc in tokenized_corpus for token in doc]
        unique_tokens = set(all_tokens)
        token_freq = Counter(all_tokens)
        
        # Document length statistics
        doc_lengths = [len(doc) for doc in tokenized_corpus]
        text_lengths = [chunk.get('length', len(chunk.get('text', ''))) for chunk in chunks]
        
        # Source distribution
        sources = Counter(chunk.get('source', 'unknown') for chunk in chunks)
        
        stats = {
            "created_at": datetime.now().isoformat(),
            "bm25_params": {
                "k1": self.k1,
                "b": self.b,
            },
            "tokenization": {
                "method": self.tokenizer.config.method.value,
                "keyword_weight": self.tokenizer.config.keyword_weight,
            },
            "corpus_stats": {
                "total_documents": len(tokenized_corpus),
                "total_tokens": len(all_tokens),
                "unique_tokens": len(unique_tokens),
                "avg_tokens_per_doc": len(all_tokens) / len(tokenized_corpus) if tokenized_corpus else 0,
                "min_tokens": min(doc_lengths) if doc_lengths else 0,
                "max_tokens": max(doc_lengths) if doc_lengths else 0,
            },
            "text_stats": {
                "avg_text_length": sum(text_lengths) / len(text_lengths) if text_lengths else 0,
                "min_text_length": min(text_lengths) if text_lengths else 0,
                "max_text_length": max(text_lengths) if text_lengths else 0,
            },
            "source_distribution": dict(sources),
            "top_20_tokens": token_freq.most_common(20),
        }
        
        return stats
    
    def save_index(
        self,
        output_dir: Path,
        bm25: BM25Okapi,
        tokenized_corpus: List[List[str]],
        chunk_ids: List[str],
        metadata_list: List[Dict],
        statistics: Dict[str, Any],
    ) -> None:
        """
        Save all index artifacts to disk.
        
        Args:
            output_dir: Directory to save files.
            bm25: BM25Okapi index instance.
            tokenized_corpus: Tokenized documents.
            chunk_ids: List of chunk IDs.
            metadata_list: List of metadata dictionaries.
            statistics: Index statistics.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Save main index pickle (compatible with BM25Search.load())
        index_data = {
            "documents": [],  # Will be populated separately
            "tokenized_docs": tokenized_corpus,
            "doc_ids": list(range(len(chunk_ids))),
            "metadata": {i: meta for i, meta in enumerate(metadata_list)},
            "chunk_id_mapping": {i: cid for i, cid in enumerate(chunk_ids)},
            "config": {
                "k1": self.k1,
                "b": self.b,
            }
        }
        
        # Add original texts for search result display
        index_data["documents"] = [meta.get('metadata', {}).get('title', '') or 
                                   f"Chunk {meta['chunk_id']}" 
                                   for meta in metadata_list]
        
        with open(output_dir / "bm25_index.pkl", "wb") as f:
            pickle.dump(index_data, f)
        logger.info(f"Saved bm25_index.pkl")
        
        # 2. Save tokenized corpus separately for inspection/debugging
        with open(output_dir / "tokenized_corpus.pkl", "wb") as f:
            pickle.dump({
                "tokenized_corpus": tokenized_corpus,
                "chunk_ids": chunk_ids,
            }, f)
        logger.info(f"Saved tokenized_corpus.pkl")
        
        # 3. Save chunk ID mapping as JSON
        chunk_mapping = {
            "created_at": statistics["created_at"],
            "total_chunks": len(chunk_ids),
            "chunk_ids": chunk_ids,
            "id_to_index": {cid: i for i, cid in enumerate(chunk_ids)},
        }
        with open(output_dir / "chunk_mapping.json", "w", encoding="utf-8") as f:
            json.dump(chunk_mapping, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved chunk_mapping.json")
        
        # 4. Save statistics as JSON
        with open(output_dir / "index_metadata.json", "w", encoding="utf-8") as f:
            json.dump(statistics, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved index_metadata.json")
        
        # Log summary
        logger.info(f"\n{'='*60}")
        logger.info(f"Index saved to: {output_dir}")
        logger.info(f"  - Total documents: {statistics['corpus_stats']['total_documents']}")
        logger.info(f"  - Total tokens: {statistics['corpus_stats']['total_tokens']}")
        logger.info(f"  - Unique tokens: {statistics['corpus_stats']['unique_tokens']}")
        logger.info(f"  - Avg tokens/doc: {statistics['corpus_stats']['avg_tokens_per_doc']:.1f}")
        logger.info(f"{'='*60}")


# ============================================================================
# Search Testing
# ============================================================================

def test_search(
    bm25: BM25Okapi,
    tokenized_corpus: List[List[str]],
    chunk_ids: List[str],
    tokenizer: AncientChineseTokenizer,
    chunks: List[Dict],
) -> None:
    """
    Run test searches to validate the index.
    
    Args:
        bm25: BM25Okapi index.
        tokenized_corpus: Tokenized corpus.
        chunk_ids: Chunk ID list.
        tokenizer: Tokenizer instance.
        chunks: Original chunks for text display.
    """
    test_queries = [
        "林黛玉葬花",
        "賈寶玉通靈寶玉",
        "好了歌",
        "金玉良緣",
        "紅樓夢",
    ]
    
    # Build chunk_id to text mapping
    id_to_text = {chunk['chunk_id']: chunk.get('text', '')[:50] for chunk in chunks}
    
    print("\n" + "="*60)
    print("  BM25 Search Test Results")
    print("="*60)
    
    for query in test_queries:
        query_tokens = tokenizer.tokenize(query)
        scores = bm25.get_scores(query_tokens)
        
        # Get top 5 results
        top_indices = scores.argsort()[-5:][::-1]
        
        print(f"\n📝 Query: '{query}'")
        print(f"   Tokens: {query_tokens[:10]}{'...' if len(query_tokens) > 10 else ''}")
        print(f"   Top 5 results:")
        
        for rank, idx in enumerate(top_indices, 1):
            cid = chunk_ids[idx]
            score = scores[idx]
            text_preview = id_to_text.get(cid, '')[:40]
            print(f"     {rank}. [{cid}] score={score:.4f}")
            print(f"        {text_preview}...")
    
    print("\n" + "="*60)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main function to build BM25 index."""
    logger.info("="*60)
    logger.info("P2-T10: BM25 Index Builder for Ancient Chinese RAG")
    logger.info("="*60)
    
    # Check chunks directory
    if not CHUNKS_DIR.exists():
        logger.error(f"Chunks directory not found: {CHUNKS_DIR}")
        logger.error("Please run P2-T07 (semantic chunker) first.")
        sys.exit(1)
    
    # Load chunks
    chunks, source_mapping = load_all_chunks(CHUNKS_DIR)
    
    if not chunks:
        logger.error("No chunks loaded. Check the chunks directory.")
        sys.exit(1)
    
    # Initialize builder
    builder = BM25IndexBuilder(
        k1=BM25_K1,
        b=BM25_B,
        method=TOKENIZATION_METHOD,
        keyword_weight=KEYWORD_WEIGHT,
    )
    
    # Tokenize chunks
    logger.info("\nTokenizing chunks...")
    tokenized_corpus, chunk_ids, metadata_list = builder.tokenize_chunks(chunks)
    
    # Build index
    bm25 = builder.build_index(tokenized_corpus)
    
    # Compute statistics
    logger.info("\nComputing statistics...")
    statistics = builder.compute_statistics(tokenized_corpus, chunks)
    
    # Save index
    logger.info("\nSaving index...")
    builder.save_index(
        output_dir=BM25_INDEX_DIR,
        bm25=bm25,
        tokenized_corpus=tokenized_corpus,
        chunk_ids=chunk_ids,
        metadata_list=metadata_list,
        statistics=statistics,
    )
    
    # Run test searches
    test_search(bm25, tokenized_corpus, chunk_ids, builder.tokenizer, chunks)
    
    logger.info("\n✅ BM25 index building completed successfully!")
    logger.info(f"   Index location: {BM25_INDEX_DIR}")


if __name__ == "__main__":
    main()
