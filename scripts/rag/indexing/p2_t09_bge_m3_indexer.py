#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-T09: FAISS Vector Index Builder (BGE-M3 Version)

This script builds a FAISS vector index using BGE-M3 embeddings.
BGE-M3 is optimized for retrieval tasks with hybrid dense+sparse support.

Usage:
    python scripts/rag/p2_t09_bge_m3_indexer.py

Features:
    - 1024-dim dense embeddings using BAAI/bge-m3
    - L2 normalized vectors for cosine similarity (Inner Product)
    - Supports up to 8192 token context
    - FP16 for reduced memory usage

Author: ML Engineer
Date: 2026-01-14
Task: P2-T09 Upgrade (WorkList_71Days.md)
"""

import os
# [Fix OOM] Optimize memory allocation for 4GB VRAM
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

import numpy as np
import warnings

# Suppress tokenizer warnings
warnings.filterwarnings("ignore", message=".*XLMRobertaTokenizerFast.*")
warnings.filterwarnings("ignore", message=".*TRANSFORMERS_CACHE.*")

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.table import Table

# Configure logging - quieter for Rich UI
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format='%(levelname)s - %(message)s'.replace('[', '\\[').replace(']', '\\]') 
)
logger = logging.getLogger(__name__)

console = Console()

# ============================================================================
# Configuration
# ============================================================================

# Paths - use parent.parent because script is in scripts/rag/
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CHUNKS_DIR = PROJECT_ROOT / "data" / "rag" / "chunks"
FAISS_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index"
MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "huggingface"

# BGE-M3 Configuration
MODEL_NAME = "BAAI/bge-m3"
EMBEDDING_DIM = 1024  # BGE-M3 outputs 1024-dim vectors
MAX_LENGTH = 1024     # [Modified] Reduced from 8192 for 4GB VRAM
BATCH_SIZE = 1        # [Modified] Reduced from 8 for 4GB VRAM
USE_FP16 = True       # Use FP16 to reduce memory
ENHANCE_WITH_KEYWORDS = True  # Prepend keywords to text for better embedding

# Output file names (separate from SikuBERT version)
INDEX_FILENAME = "chunks_bge_m3.index"
MAPPING_FILENAME = "chunk_mapping_bge_m3.json"
CHUNKS_FILENAME = "indexed_chunks_bge_m3.json"

# ============================================================================
# BGE-M3 Embedder
# ============================================================================

class BGEM3Embedder:
    """Generates embeddings using BGE-M3 model optimized for retrieval."""
    
    def __init__(self, cache_dir: Path = MODEL_CACHE_DIR):
        """
        Initialize the BGE-M3 embedder.
        
        Args:
            cache_dir: Directory to cache the model
        """
        import torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        logger.info(f"Using device: {self.device}")
        logger.info(f"Loading model: {MODEL_NAME}")
        logger.info(f"Model cache directory: {cache_dir}")
        
        # Ensure cache directory exists and set ALL cache environment variables
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ['HF_HOME'] = str(cache_dir)
        os.environ['TRANSFORMERS_CACHE'] = str(cache_dir)
        os.environ['HF_HUB_CACHE'] = str(cache_dir)  # Critical for FlagEmbedding
        
        # Load BGE-M3 model
        try:
            from FlagEmbedding import BGEM3FlagModel
            self.model = BGEM3FlagModel(
                MODEL_NAME,
                use_fp16=USE_FP16,
                device=self.device
            )
            logger.info("BGE-M3 model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load BGE-M3: {e}")
            raise
    
    def generate_embeddings_batch(self, texts: List[str]) -> np.ndarray:
        """
        Generate normalized embeddings for a batch of texts.
        
        Args:
            texts: List of input texts
            
        Returns:
            Array of shape (len(texts), 1024) with normalized embeddings
        """
        # BGE-M3 encode returns dict with 'dense_vecs', 'lexical_weights', etc.
        result = self.model.encode(
            texts,
            batch_size=BATCH_SIZE,
            max_length=MAX_LENGTH,
            return_dense=True,
            return_sparse=False,  # We'll use FAISS for dense retrieval
            return_colbert_vecs=False
        )
        
        embeddings = result['dense_vecs']
        
        # Ensure numpy array and float32
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.array(embeddings)
        
        return embeddings.astype(np.float32)
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        return self.generate_embeddings_batch([text])[0]

# ============================================================================
# Chunk Loader (same as original)
# ============================================================================

def load_all_chunks(chunks_dir: Path, enhance_with_keywords: bool = ENHANCE_WITH_KEYWORDS) -> Tuple[List[Dict], List[str], List[str]]:
    """
    Load all chunks from standardized JSON files in the chunks directory.
    
    Args:
        chunks_dir: Directory containing processed *_chunks.json files
        enhance_with_keywords: If True, prepend keywords/breadcrumbs to text
        
    Returns:
        Tuple of (chunks list, texts list, chunk_ids list)
    """
    all_chunks = []
    texts = []
    chunk_ids = []
    
    if not chunks_dir.exists():
        logger.error(f"Chunks directory not found: {chunks_dir}")
        return [], [], []
        
    # Find all *_chunks.json files
    chunk_files = list(chunks_dir.glob("*_chunks.json"))
    logger.info(f"Found {len(chunk_files)} chunk files in {chunks_dir}")
    
    for json_file in chunk_files:
        try:
            logger.info(f"Loading {json_file.name}...")
            with open(json_file, 'r', encoding='utf-8') as f:
                file_chunks = json.load(f)
            
            if not file_chunks:
                continue
            
            valid_nodes_count = 0
            
            for chunk in file_chunks:
                # Extract core fields
                chunk_id = chunk.get("chunk_id")
                text_content = chunk.get("text", "")
                
                # Support both flat chunks and nested nodes (legacy support)
                if not chunk_id and "node_id" in chunk:
                    chunk_id = chunk["node_id"]
                
                if not chunk_id or not text_content:
                    continue
                    
                # Get formatting fields
                metadata = chunk.get("metadata", {})
                keywords = chunk.get("keywords", [])
                # If keywords not at top level, check metadata
                if not keywords:
                    keywords = metadata.get("keywords", [])
                
                # Prepare embedding text (Text Strategy V3)
                embedding_text = text_content
                
                if enhance_with_keywords:
                    context_parts = []
                    
                    # 1. Breadcrumbs / Title
                    breadcrumbs = metadata.get("breadcrumbs", "")
                    doc_title = metadata.get("doc_title") or metadata.get("title", "")
                    
                    if breadcrumbs:
                        context_parts.append(f"[{breadcrumbs}]")
                    elif doc_title:
                        context_parts.append(f"[{doc_title}]")
                        
                    # 2. Keywords
                    if keywords:
                        context_parts.append(f"Tags: {', '.join(keywords)}")
                    
                    # 3. Modern Translation
                    modern_translation = metadata.get("modern_translation", "")
                    if modern_translation:
                        context_parts.append(f"Translation: {modern_translation}")
                        
                    # 4. Suggested Queries (if available)
                    suggested_queries = metadata.get("suggested_queries", [])
                    if suggested_queries:
                        context_parts.append(f"Queries: {', '.join(suggested_queries)}")
                        
                    if context_parts:
                        embedding_text = f"{' '.join(context_parts)}\n{text_content}"
                
                # Check for existing embedding_text in chunk if we didn't construct one
                # (Some pre-processed chunks might already have it)
                if "embedding_text" in chunk and not enhance_with_keywords:
                    embedding_text = chunk["embedding_text"]
                
                # Store processed chunk
                # Ensure we strictly follow the structure needed for retrieval
                processed_chunk = chunk.copy()
                processed_chunk["embedding_text"] = embedding_text
                
                all_chunks.append(processed_chunk)
                texts.append(embedding_text)
                chunk_ids.append(chunk_id)
                valid_nodes_count += 1
            
            logger.info(f"  Loaded {json_file.name}: {valid_nodes_count} chunks")
            
        except Exception as e:
            logger.warning(f"Failed to load {json_file.name}: {e}")
            
    logger.info(f"Total chunks loaded: {len(all_chunks)}")
    return all_chunks, texts, chunk_ids

# ============================================================================
# FAISS Index Builder
# ============================================================================

def build_faiss_index(embeddings: np.ndarray) -> "faiss.IndexFlatIP":
    """
    Build FAISS IndexFlatIP index.
    
    Args:
        embeddings: Normalized embeddings array of shape (n, dim)
        
    Returns:
        FAISS index
    """
    import faiss
    
    n, dim = embeddings.shape
    logger.info(f"Building FAISS IndexFlatIP index: {n} vectors, {dim} dimensions")
    
    # Create index for Inner Product (cosine similarity with normalized vectors)
    index = faiss.IndexFlatIP(dim)
    
    # Add vectors
    index.add(embeddings)
    
    logger.info(f"Index built successfully. Total vectors: {index.ntotal}")
    return index


def save_index_and_mapping(
    index: "faiss.IndexFlatIP",
    chunk_ids: List[str],
    chunks: List[Dict],
    output_dir: Path
) -> None:
    """
    Save FAISS index and chunk mapping.
    
    Args:
        index: FAISS index
        chunk_ids: List of chunk IDs
        chunks: List of chunk data
        output_dir: Output directory
    """
    import faiss
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save FAISS index
    index_path = output_dir / INDEX_FILENAME
    faiss.write_index(index, str(index_path))
    logger.info(f"Saved FAISS index to: {index_path}")
    
    # Save chunk ID mapping (index position -> chunk_id)
    mapping = {
        "created_at": datetime.now().isoformat(),
        "model": MODEL_NAME,
        "embedding_dim": EMBEDDING_DIM,
        "keyword_enhanced": ENHANCE_WITH_KEYWORDS,
        "total_chunks": len(chunk_ids),
        "chunk_ids": chunk_ids
    }
    
    mapping_path = output_dir / MAPPING_FILENAME
    with open(mapping_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved chunk mapping to: {mapping_path}")
    
    # Save full chunk data for retrieval
    chunks_path = output_dir / CHUNKS_FILENAME
    indexed_data = {
        "created_at": datetime.now().isoformat(),
        "model": MODEL_NAME,
        "chunks": chunks
    }
    with open(chunks_path, 'w', encoding='utf-8') as f:
        json.dump(indexed_data, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved indexed chunks data to: {chunks_path}")

# ============================================================================
# Verification
# ============================================================================

def verify_index(index: "faiss.IndexFlatIP", embedder: BGEM3Embedder, 
                 chunk_ids: List[str], chunks: List[Dict], k: int = 5) -> None:
    """
    Verify index with test queries.
    
    Args:
        index: FAISS index
        embedder: Embedding generator
        chunk_ids: List of chunk IDs
        chunks: List of chunk data
        k: Number of results to retrieve
    """
    test_queries = [
        "林黛玉葬花吟",
        "金陵十二釵",
        "賈寶玉通靈寶玉",
        "王熙鳳協理寧國府",
        "劉姥姥進大觀園"
    ]
    
    logger.info("\n" + "="*60)
    logger.info("Index Verification - Test Queries (BGE-M3)")
    logger.info("="*60)
    
    for query in test_queries:
        query_embedding = embedder.generate_embedding(query)
        query_embedding = query_embedding.reshape(1, -1)
        
        distances, indices = index.search(query_embedding, k)
        
        logger.info(f"\nQuery: '{query}'")
        logger.info(f"Top-{k} results:")
        
        for rank, (dist, idx) in enumerate(zip(distances[0], indices[0]), 1):
            chunk_id = chunk_ids[idx]
            chunk_text = chunks[idx]['text'][:50] + "..." if len(chunks[idx]['text']) > 50 else chunks[idx]['text']
            logger.info(f"  {rank}. [{chunk_id}] (score: {dist:.4f})")
            logger.info(f"     {chunk_text}")

# ============================================================================
# Main
# ============================================================================

def main():
    """Main entry point with Rich UI."""
    console.print(Panel.fit(
        "[bold blue]P2-T09: FAISS Vector Index Builder[/bold blue]\n"
        "[dim]使用 BGE-M3 建立 1024 維向量索引[/dim]",
        title="🔍 RAG Indexer"
    ))
    
    # Check for faiss
    try:
        import faiss
        console.print(f"[dim]FAISS version: {faiss.__version__ if hasattr(faiss, '__version__') else 'unknown'}[/dim]")
    except ImportError:
        console.print("[red]❌ FAISS not installed. Please install with: pip install faiss-cpu[/red]")
        return
    
    # Step 1: Load chunks
    console.print("\n[bold cyan]Step 1/4: 載入分塊資料[/bold cyan]")
    chunks, texts, chunk_ids = load_all_chunks(CHUNKS_DIR)
    
    if not chunks:
        console.print("[red]❌ No chunks found![/red]")
        return
    
    console.print(f"  ✅ 載入 [green]{len(chunks):,}[/green] 個分塊")
    
    # Step 2: Initialize embedder and generate embeddings
    # Step 2: Initialize embedder and generate embeddings
    console.print("\n[bold cyan]Step 2/4: 初始化 BGE-M3 並生成嵌入向量[/bold cyan]")
    
    checkpoint_path = FAISS_INDEX_DIR / "checkpoint_embeddings.npy"
    all_embeddings = []
    start_index = 0
    
    # [Resume Logic] Check for existing checkpoint
    if checkpoint_path.exists():
        try:
            console.print(f"[yellow]⚠ 發現檢查點: {checkpoint_path}[/yellow]")
            saved_data = np.load(checkpoint_path)
            if saved_data.shape[1] == EMBEDDING_DIM:
                all_embeddings.append(saved_data)
                start_index = len(saved_data)
                console.print(f"  ↪ 從第 [bold green]{start_index}[/bold green] 筆資料由檢查點恢復 (共 {len(texts)} 筆)")
            else:
                console.print("[red]⚠ 檢查點維度不符，將重新開始[/red]")
        except Exception as e:
            from rich.markup import escape
            console.print(f"[red]⚠讀取檢查點失敗: {escape(str(e))}，將重新開始[/red]")
    
    if start_index >= len(texts):
        console.print("[green]✔ 所有資料已在檢查點中完成，跳過生成步驟。[/green]")
    else:
        embedder = BGEM3Embedder()
        
        # Calculate remaining batches
        remaining_texts = texts[start_index:]
        total_batches = (len(remaining_texts) + BATCH_SIZE - 1) // BATCH_SIZE
        
        console.print(f"  尚需處理: {len(remaining_texts)} 筆")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]生成嵌入向量...", total=total_batches)
            
            # Loop through remaining texts
            # Use 'i' relative to start_index for batching
            for i in range(0, len(remaining_texts), BATCH_SIZE):
                batch_texts = remaining_texts[i:i+BATCH_SIZE]
                
                try:
                    batch_embeddings = embedder.generate_embeddings_batch(batch_texts)
                    all_embeddings.append(batch_embeddings)
                    
                    # [Checkpoint Logic] Save every 50 batches (or roughly every 50-400 items depending on batch size)
                    # For Batch=1, every 50 items. For Batch=8, every 400 items.
                    if (i // BATCH_SIZE) % 50 == 0:
                        try:
                            # Stack valid embeddings so far and save
                            current_data = np.vstack(all_embeddings)
                            np.save(checkpoint_path, current_data)
                        except Exception as e:
                            logger.warning(f"Failed to save checkpoint: {e}")
                            
                except Exception as e:
                    console.print(f"[red]❌ Batch processing failed at index {start_index + i}: {e}[/red]")
                    # Try to save what we have
                    try:
                        if all_embeddings:
                            np.save(checkpoint_path, np.vstack(all_embeddings))
                            console.print("[yellow]已保存目前進度至檢查點[/yellow]")
                    except:
                        pass
                    raise e
                    
                progress.update(task, advance=1)
    
    # Final cleanup of checkpoint if successful (optional, or keep it until verify)
    # Merging all data
    if len(all_embeddings) > 1:
        embeddings = np.vstack(all_embeddings)
    elif len(all_embeddings) == 1:
        embeddings = all_embeddings[0]
    else:
        embeddings = np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

    # Save final complete checkpoint just in case
    np.save(checkpoint_path, embeddings)
    console.print(f"  ✅ 生成嵌入向量: {embeddings.shape}")
    
    # Step 3: Build FAISS index
    console.print("\n[bold cyan]Step 3/4: 建立 FAISS 索引[/bold cyan]")
    index = build_faiss_index(embeddings)
    console.print(f"  ✅ 索引包含 [green]{index.ntotal:,}[/green] 個向量")
    
    # Step 4: Save index and mapping
    console.print("\n[bold cyan]Step 4/4: 儲存索引與映射[/bold cyan]")
    save_index_and_mapping(index, chunk_ids, chunks, FAISS_INDEX_DIR)
    console.print(f"  ✅ 已儲存到 {FAISS_INDEX_DIR}")
    
    # Verification
    console.print("\n[bold cyan]驗證索引...[/bold cyan]")
    verify_index(index, embedder, chunk_ids, chunks)
    
    # Summary table
    console.print("\n")
    table = Table(title="📊 索引建立完成")
    table.add_column("項目", style="cyan")
    table.add_column("數值", justify="right", style="green")
    
    table.add_row("總分塊數", f"{len(chunks):,}")
    table.add_row("嵌入維度", str(EMBEDDING_DIM))
    table.add_row("模型", MODEL_NAME)
    table.add_row("索引檔案", INDEX_FILENAME)
    
    console.print(table)
    console.print("\n[bold green]✅ BGE-M3 FAISS 索引建立成功！[/bold green]")


if __name__ == "__main__":
    main()
