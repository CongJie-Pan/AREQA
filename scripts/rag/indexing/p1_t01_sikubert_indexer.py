#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P1-T01: SikuBERT FAISS Vector Index Builder

This script builds a FAISS vector index using SikuBERT embeddings.
SikuBERT is pre-trained on ancient Chinese texts and excels at understanding
classical Chinese literature semantics.

Features:
    - 768-dim dense embeddings using SIKU-BERT/sikubert
    - L2 normalized vectors for cosine similarity (Inner Product)
    - Mean pooling for sentence embeddings
    - Checkpoint support for resumability
    - Uses local model cache (no download if exists)

Usage:
    python scripts/rag/indexing/p1_t01_sikubert_indexer.py

Performance Comparison (from eval_results):
    - BGE-M3:   MRR = 0.005 (disaster - correct answer ranks 200+)
    - SikuBERT: MRR = 0.410 (acceptable - 82x improvement)

Author: ML Engineer
Date: 2026-02-01
Task: P1-T01 (Phase 1 Emergency Fix - rag_system_20260201_report_and_plan.md)
"""

import os
# Memory optimization for limited VRAM
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

import json
import logging
import torch
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
from tqdm import tqdm

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
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHUNKS_DIR = PROJECT_ROOT / "data" / "rag" / "chunks"
FAISS_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index"
MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "huggingface"

# SikuBERT Configuration
MODEL_NAME = "SIKU-BERT/sikubert"
EMBEDDING_DIM = 768  # SikuBERT outputs 768-dim vectors
MAX_LENGTH = 512     # BERT max sequence length
ENHANCE_WITH_KEYWORDS = True  # Prepend keywords to text for better embedding

# GPU Optimization Configuration
GPU_BATCH_SIZE = 32       # Larger batch for GPU (SikuBERT is ~110MB)
CPU_BATCH_SIZE = 8        # Smaller batch for CPU to avoid memory issues
USE_FP16 = True           # Enable FP16 on GPU for 2x speedup
GPU_MEMORY_FRACTION = 0.8 # Max GPU memory fraction to use
ENABLE_CUDA_OPTIMIZATION = True  # Enable CUDA-specific optimizations

# Output file names (separate from BGE-M3 version)
INDEX_FILENAME = "chunks_sikubert.index"
MAPPING_FILENAME = "chunk_mapping_sikubert.json"
CHUNKS_FILENAME = "indexed_chunks_sikubert.json"

# Checkpoint configuration
CHECKPOINT_INTERVAL = 1000  # Save checkpoint every N chunks
CHECKPOINT_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index" / "checkpoints"

# ============================================================================
# SikuBERT Embedder
# ============================================================================

class SikuBERTEmbedder:
    """Generates embeddings using SikuBERT model optimized for ancient Chinese.
    
    GPU Optimization Features:
        - Automatic GPU detection with CPU fallback
        - Dynamic batch size based on device
        - FP16 inference on GPU for 2x speedup
        - CUDA memory management to prevent OOM
    """
    
    def __init__(self, cache_dir: Path = MODEL_CACHE_DIR, force_cpu: bool = False):
        """
        Initialize the SikuBERT embedder with GPU optimization.
        
        Args:
            cache_dir: Directory containing the cached model
            force_cpu: If True, force CPU usage even if GPU is available
        """
        # Detect and configure device
        self.device, self.device_info = self._setup_device(force_cpu)
        self.use_fp16 = USE_FP16 and self.device == "cuda"
        self.batch_size = GPU_BATCH_SIZE if self.device == "cuda" else CPU_BATCH_SIZE
        
        logger.info(f"Device: {self.device_info}")
        logger.info(f"Batch size: {self.batch_size}, FP16: {self.use_fp16}")
        
        # Set cache environment variables
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ['HF_HOME'] = str(cache_dir)
        os.environ['TRANSFORMERS_CACHE'] = str(cache_dir)
        os.environ['HF_HUB_CACHE'] = str(cache_dir)
        
        # Try to load from local cache first
        local_model_path = self._find_local_model(cache_dir)
        
        from transformers import AutoModel, AutoTokenizer
        
        if local_model_path:
            logger.info(f"Loading SikuBERT from local cache: {local_model_path}")
            self.tokenizer = AutoTokenizer.from_pretrained(str(local_model_path))
            self.model = AutoModel.from_pretrained(str(local_model_path))
        else:
            logger.info(f"Loading SikuBERT from HuggingFace: {MODEL_NAME}")
            self.tokenizer = AutoTokenizer.from_pretrained(
                MODEL_NAME, 
                cache_dir=str(cache_dir)
            )
            self.model = AutoModel.from_pretrained(
                MODEL_NAME, 
                cache_dir=str(cache_dir)
            )
        
        # Move model to device with optimization
        self.model.to(self.device)
        self.model.eval()
        
        # Enable FP16 for GPU inference
        if self.use_fp16:
            self.model = self.model.half()
            logger.info("Enabled FP16 inference for GPU")
        
        # Enable CUDA optimizations
        if self.device == "cuda" and ENABLE_CUDA_OPTIMIZATION:
            torch.backends.cudnn.benchmark = True
            logger.info("Enabled CUDA optimizations")
        
        logger.info(f"SikuBERT loaded successfully on {self.device}")
    
    def _setup_device(self, force_cpu: bool = False) -> tuple:
        """
        Setup compute device with GPU detection and fallback.
        
        Args:
            force_cpu: Force CPU usage
            
        Returns:
            Tuple of (device_string, device_info_string)
        """
        if force_cpu:
            return "cpu", "CPU (forced)"
        
        if not torch.cuda.is_available():
            return "cpu", "CPU (CUDA not available)"
        
        try:
            # Test CUDA availability
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            
            # Set memory fraction
            if GPU_MEMORY_FRACTION < 1.0:
                torch.cuda.set_per_process_memory_fraction(GPU_MEMORY_FRACTION)
            
            # Clear any existing cache
            torch.cuda.empty_cache()
            
            return "cuda", f"GPU: {gpu_name} ({gpu_memory:.1f} GB)"
            
        except Exception as e:
            logger.warning(f"GPU initialization failed: {e}")
            logger.warning("Falling back to CPU")
            return "cpu", f"CPU (GPU failed: {str(e)[:50]})"
    
    def _find_local_model(self, cache_dir: Path) -> Path:
        """
        Find local model cache path.
        
        Args:
            cache_dir: Base cache directory
            
        Returns:
            Path to local model or None if not found
        """
        # HuggingFace cache format: models--{org}--{model}/snapshots/{hash}
        model_dir = cache_dir / f"models--{MODEL_NAME.replace('/', '--')}"
        
        if model_dir.exists():
            snapshots_dir = model_dir / "snapshots"
            if snapshots_dir.exists():
                snapshots = list(snapshots_dir.iterdir())
                if snapshots:
                    # Use the first (usually latest) snapshot
                    snapshot_path = snapshots[0]
                    # Verify it has the necessary files
                    required_files = ["config.json", "pytorch_model.bin"]
                    alt_files = ["config.json", "model.safetensors"]
                    
                    has_required = all((snapshot_path / f).exists() for f in required_files)
                    has_alt = all((snapshot_path / f).exists() for f in alt_files)
                    
                    if has_required or has_alt:
                        return snapshot_path
        
        return None
    
    def _mean_pooling(self, model_output, attention_mask):
        """
        Apply mean pooling to get sentence embeddings.
        
        Args:
            model_output: BERT model output
            attention_mask: Attention mask from tokenizer
            
        Returns:
            Mean pooled embeddings
        """
        token_embeddings = model_output[0]  # First element is last_hidden_state
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, 1)
        sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9)
        return sum_embeddings / sum_mask
    
    def generate_embeddings_batch(self, texts: List[str]) -> np.ndarray:
        """
        Generate normalized embeddings for a batch of texts.
        
        Optimized for GPU with FP16 inference and memory management.
        
        Args:
            texts: List of input texts
            
        Returns:
            Array of shape (len(texts), 768) with normalized embeddings
        """
        # Tokenize
        encoded_input = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors='pt'
        ).to(self.device)
        
        # Generate embeddings with memory optimization
        with torch.no_grad():
            # Use autocast for FP16 inference on GPU
            if self.use_fp16 and self.device == "cuda":
                with torch.cuda.amp.autocast():
                    model_output = self.model(**encoded_input)
            else:
                model_output = self.model(**encoded_input)
        
        # Mean pooling
        embeddings = self._mean_pooling(model_output, encoded_input['attention_mask'])
        
        # L2 normalize for cosine similarity
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        
        # Convert to float32 for FAISS compatibility
        result = embeddings.cpu().float().numpy().astype(np.float32)
        
        # Clear GPU cache periodically
        if self.device == "cuda":
            del encoded_input, model_output, embeddings
            torch.cuda.empty_cache()
        
        return result
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        return self.generate_embeddings_batch([text])[0]


# ============================================================================
# Chunk Loader (adapted from p2_t09_bge_m3_indexer.py)
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
                if "embedding_text" in chunk and not enhance_with_keywords:
                    embedding_text = chunk["embedding_text"]
                
                # Store processed chunk
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
        "max_length": MAX_LENGTH,
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
# Checkpoint Management
# ============================================================================

def save_checkpoint(
    embeddings: np.ndarray,
    chunk_ids: List[str],
    batch_num: int,
    checkpoint_dir: Path
) -> None:
    """Save embedding checkpoint for resumability."""
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / f"sikubert_checkpoint_{batch_num}.npz"
    
    np.savez_compressed(
        checkpoint_path,
        embeddings=embeddings,
        chunk_ids=np.array(chunk_ids, dtype=object)
    )
    logger.info(f"Saved checkpoint: {checkpoint_path}")


def load_latest_checkpoint(checkpoint_dir: Path) -> Tuple[np.ndarray, List[str], int]:
    """
    Load the latest checkpoint if available.
    
    Returns:
        Tuple of (embeddings, chunk_ids, last_batch_num) or (None, None, 0) if no checkpoint
    """
    if not checkpoint_dir.exists():
        return None, None, 0
    
    checkpoints = sorted(checkpoint_dir.glob("sikubert_checkpoint_*.npz"))
    if not checkpoints:
        return None, None, 0
    
    latest = checkpoints[-1]
    batch_num = int(latest.stem.split("_")[-1])
    
    data = np.load(latest, allow_pickle=True)
    embeddings = data['embeddings']
    chunk_ids = data['chunk_ids'].tolist()
    
    logger.info(f"Loaded checkpoint: {latest} (batch {batch_num}, {len(chunk_ids)} chunks)")
    return embeddings, chunk_ids, batch_num


# ============================================================================
# Verification
# ============================================================================

def verify_index(
    index: "faiss.IndexFlatIP", 
    embedder: SikuBERTEmbedder,
    chunk_ids: List[str], 
    chunks: List[Dict], 
    k: int = 5
) -> None:
    """
    Verify index with test queries.
    
    Args:
        index: FAISS index
        embedder: SikuBERT embedder
        chunk_ids: List of chunk IDs
        chunks: List of chunk data
        k: Number of results to retrieve
    """
    test_queries = [
        "林黛玉葬花吟",
        "賈寶玉通靈寶玉",
        "好了歌",
        "金陵十二釵判詞",
        "大觀園",
    ]
    
    # Build chunk_id -> chunk mapping
    id_to_chunk = {c['chunk_id']: c for c in chunks if 'chunk_id' in c}
    
    print("\n" + "="*60)
    print("INDEX VERIFICATION (SikuBERT)")
    print("="*60)
    
    for query in test_queries:
        # Generate query embedding
        query_embedding = embedder.generate_embedding(query).reshape(1, -1)
        
        # Search
        distances, indices = index.search(query_embedding, k)
        
        print(f"\n🔍 Query: {query}")
        print("-" * 40)
        
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(chunk_ids):
                cid = chunk_ids[idx]
                chunk = id_to_chunk.get(cid, {})
                text_preview = chunk.get('text', '')[:80] + "..." if len(chunk.get('text', '')) > 80 else chunk.get('text', '')
                print(f"  [{i+1}] Score: {dist:.4f} | ID: {cid}")
                print(f"      {text_preview}")
    
    print("\n" + "="*60)


# ============================================================================
# Main
# ============================================================================

def main():
    """Main entry point for SikuBERT indexing."""
    import faiss
    import argparse
    
    parser = argparse.ArgumentParser(description="SikuBERT FAISS Index Builder")
    parser.add_argument("--cpu", action="store_true", help="Force CPU mode (disable GPU)")
    parser.add_argument("--batch-size", type=int, help="Override batch size")
    args = parser.parse_args()
    
    print("="*60)
    print("SikuBERT FAISS Index Builder")
    print("Phase 1 Emergency Fix - Replacing BGE-M3")
    print("="*60)
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Chunks Dir: {CHUNKS_DIR}")
    print(f"Output Dir: {FAISS_INDEX_DIR}")
    print(f"Model: {MODEL_NAME}")
    print(f"GPU Batch Size: {GPU_BATCH_SIZE}, CPU Batch Size: {CPU_BATCH_SIZE}")
    print(f"Force CPU: {args.cpu}")
    print("="*60 + "\n")
    
    # 1. Load chunks
    print("📚 Step 1: Loading chunks...")
    chunks, texts, chunk_ids = load_all_chunks(CHUNKS_DIR, ENHANCE_WITH_KEYWORDS)
    
    if not chunks:
        logger.error("No chunks found! Exiting.")
        return
    
    print(f"✅ Loaded {len(chunks)} chunks\n")
    
    # 2. Check for checkpoint
    print("🔍 Step 2: Checking for checkpoint...")
    cached_embeddings, cached_ids, last_batch = load_latest_checkpoint(CHECKPOINT_DIR)
    
    start_idx = 0
    all_embeddings = []
    
    if cached_embeddings is not None:
        # Resume from checkpoint
        start_idx = last_batch * BATCH_SIZE
        if start_idx < len(texts):
            print(f"📥 Resuming from batch {last_batch} (index {start_idx})")
            all_embeddings = [cached_embeddings]
        else:
            print(f"✅ Checkpoint covers all data, using cached embeddings")
            all_embeddings = [cached_embeddings]
            start_idx = len(texts)  # Skip encoding
    
    # 3. Initialize embedder with GPU optimization
    print("\n🤖 Step 3: Initializing SikuBERT embedder...")
    embedder = SikuBERTEmbedder(MODEL_CACHE_DIR, force_cpu=args.cpu)
    
    # Use dynamic batch size from embedder (or override from args)
    batch_size = args.batch_size if args.batch_size else embedder.batch_size
    print(f"Using batch size: {batch_size}")
    
    # 4. Generate embeddings
    if start_idx < len(texts):
        print(f"\n⚡ Step 4: Generating embeddings (from index {start_idx})...")
        
        remaining_texts = texts[start_idx:]
        num_batches = (len(remaining_texts) + batch_size - 1) // batch_size
        
        for batch_idx in tqdm(range(num_batches), desc="Encoding"):
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(remaining_texts))
            batch_texts = remaining_texts[batch_start:batch_end]
            
            # Generate embeddings for batch
            try:
                batch_embeddings = embedder.generate_embeddings_batch(batch_texts)
                all_embeddings.append(batch_embeddings)
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    logger.warning(f"GPU OOM at batch {batch_idx}, reducing batch size...")
                    torch.cuda.empty_cache()
                    # Process smaller sub-batches
                    sub_batch_size = max(1, batch_size // 4)
                    for sub_start in range(0, len(batch_texts), sub_batch_size):
                        sub_end = min(sub_start + sub_batch_size, len(batch_texts))
                        sub_batch = batch_texts[sub_start:sub_end]
                        sub_embeddings = embedder.generate_embeddings_batch(sub_batch)
                        all_embeddings.append(sub_embeddings)
                else:
                    raise
            
            # Save checkpoint periodically
            global_batch_num = last_batch + batch_idx + 1
            if (global_batch_num % (CHECKPOINT_INTERVAL // batch_size)) == 0:
                # Concatenate all embeddings so far
                current_embeddings = np.vstack(all_embeddings)
                current_chunk_ids = chunk_ids[:start_idx + batch_end]
                save_checkpoint(current_embeddings, current_chunk_ids, global_batch_num, CHECKPOINT_DIR)
    
    # 5. Concatenate all embeddings
    print("\n📊 Step 5: Building index...")
    embeddings = np.vstack(all_embeddings)
    print(f"Embeddings shape: {embeddings.shape}")
    
    # Verify embeddings are normalized
    norms = np.linalg.norm(embeddings, axis=1)
    print(f"Embedding norms - min: {norms.min():.4f}, max: {norms.max():.4f}, mean: {norms.mean():.4f}")
    
    # 6. Build FAISS index
    index = build_faiss_index(embeddings)
    
    # 7. Save index and mapping
    print("\n💾 Step 6: Saving index and mapping...")
    save_index_and_mapping(index, chunk_ids, chunks, FAISS_INDEX_DIR)
    
    # 8. Verify index
    print("\n🧪 Step 7: Verifying index...")
    verify_index(index, embedder, chunk_ids, chunks)
    
    # 9. Summary
    print("\n" + "="*60)
    print("✅ SikuBERT Index Build Complete!")
    print("="*60)
    print(f"Total chunks indexed: {len(chunk_ids)}")
    print(f"Index file: {FAISS_INDEX_DIR / INDEX_FILENAME}")
    print(f"Mapping file: {FAISS_INDEX_DIR / MAPPING_FILENAME}")
    print(f"Chunks file: {FAISS_INDEX_DIR / CHUNKS_FILENAME}")
    print("="*60)
    
    # Clean up checkpoints after successful completion
    if CHECKPOINT_DIR.exists():
        import shutil
        shutil.rmtree(CHECKPOINT_DIR)
        print("🧹 Cleaned up checkpoints")


if __name__ == "__main__":
    main()
