#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-T02: Qwen3-Embedding Indexer Builder

This script builds a FAISS index using Qwen3-Embedding-8B model via OpenRouter API.
It supports:
1. API usage for memory efficiency and speed
2. Dynamic batch processing
3. Checkpointing for failure recovery
4. FAISS IndexFlatIP for maximum accuracy
5. Comprehensive error handling and logging

Usage:
    python scripts/rag/qwen3_Encoder_rag_pipeline/rebuild_index_qwen3.py
"""

import os
import sys
import json
import time
import logging
import argparse
import pickle
import traceback
import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from tqdm import tqdm
from datetime import datetime
from openai import OpenAI

# ============================================================================
# Configuration
# ============================================================================

class IndexerConfig:
    # Paths
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    MODELS_DIR = PROJECT_ROOT / "models" / "huggingface"
    
    # Dynamically find the latest chunks JSON file if multiple exist
    _chunks_dir = PROJECT_ROOT / "data" / "rag" / "chunks"
    _chunk_files = list(_chunks_dir.glob("hybrid_smart_chunks_*.json"))
    # Fallback to the default name if no dynamic ones found
    if not _chunk_files:
        INPUT_CHUNKS_PATH = _chunks_dir / "hybrid_smart_chunks.json"
    else:
        # Sort by modification time to get the newest
        INPUT_CHUNKS_PATH = sorted(_chunk_files, key=lambda f: f.stat().st_mtime)[-1]
        
    OUTPUT_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index"
    CHECKPOINT_DIR = OUTPUT_INDEX_DIR / "checkpoints_qwen3"
    
    # Model
    MODEL_NAME = "qwen/qwen3-embedding-8b"
    
    # Indexing Settings
    BATCH_SIZE = 32  # API batch size
    MAX_LENGTH = 32000 # Using OpenRouter limits roughly
    EMBEDDING_DIM = 3584  # Qwen3-Embedding-8B uses 3584 dimensions normally
    
    # Checkpoint Settings
    CHECKPOINT_INTERVAL = 500  # Save every N chunks

# Logging Setup
log_dir = IndexerConfig.PROJECT_ROOT / "output" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / f"qwen3_indexer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# Core Components
# ============================================================================

class Qwen3Encoder:
    """Handles text encoding using Qwen3-Embedding via OpenRouter API."""
    
    def __init__(self, config: IndexerConfig):
        self.config = config
        
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is not set. Please set it before running.")
            
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        logger.info(f"Initialized OpenRouter client for model {self.config.MODEL_NAME}")

    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """Encode a batch of texts into embeddings via API."""
        if not texts:
            return np.zeros((0, self.config.EMBEDDING_DIM), dtype=np.float32)

        try:
            # We can use the batch embeddings support from API
            response = self.client.embeddings.create(
                model=self.config.MODEL_NAME,
                input=texts,
                encoding_format="float"
            )
            
            # The response contains 'data', which is a list of objects with 'embedding'
            # Sort by index just in case API returns them out of order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            embeddings_list = [item.embedding for item in sorted_data]
            
            # Update embedding dim if not matched
            if len(embeddings_list) > 0 and len(embeddings_list[0]) != self.config.EMBEDDING_DIM:
                logger.debug(f"Updating EMBEDDING_DIM to {len(embeddings_list[0])}")
                self.config.EMBEDDING_DIM = len(embeddings_list[0])
            
            embeddings = np.array(embeddings_list, dtype=np.float32)
            
            # L2 normalize for cosine similarity with IndexFlatIP
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            # Avoid division by zero
            norms[norms == 0] = 1e-10
            embeddings = embeddings / norms
                
            return embeddings
            
        except Exception as e:
            logger.error(f"Error encoding batch via API: {str(e)}")
            # Return zeros in case of failure to maintain shape matching
            return np.zeros((len(texts), self.config.EMBEDDING_DIM), dtype=np.float32)

class CheckpointManager:
    """Manages index checkpoints."""
    
    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
    def save_checkpoint(self, state_data: Dict[str, Any], faiss_index: faiss.Index, batch_num: int):
        """Save checkpoint data using FAISS I/O and JSON state."""
        # Clean older checkpoints periodically to save space
        
        index_path = self.checkpoint_dir / f"checkpoint_batch_{batch_num}.index"
        faiss.write_index(faiss_index, str(index_path))
        
        state_path = self.checkpoint_dir / f"checkpoint_batch_{batch_num}.json"
        with open(state_path, 'w', encoding='utf-8') as f:
            json.dump(state_data, f, ensure_ascii=False)
            
        logger.debug(f"Saved checkpoint: {batch_num}")
        
    def get_latest_checkpoint(self) -> Tuple[Optional[int], Optional[Dict[str, Any]], Optional[faiss.Index]]:
        """Find and load the latest checkpoint."""
        files = list(self.checkpoint_dir.glob("checkpoint_batch_*.json"))
        if not files:
            return None, None, None
            
        # Sort by batch number
        try:
            files.sort(key=lambda x: int(x.stem.split('_')[-1]))
            latest_file = files[-1]
            batch_num = int(latest_file.stem.split('_')[-1])
            
            logger.info(f"Loading latest checkpoint metadata: {latest_file.name}")
            with open(latest_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
                
            index_path = self.checkpoint_dir / f"checkpoint_batch_{batch_num}.index"
            faiss_index = faiss.read_index(str(index_path))
            
            return batch_num, state_data, faiss_index
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {str(e)}")
            return None, None, None

class IndexBuilder:
    """Main class for building the FAISS index."""
    
    def __init__(self, config: IndexerConfig):
        self.config = config
        self.encoder = Qwen3Encoder(config)
        self.checkpoint_manager = CheckpointManager(config.CHECKPOINT_DIR)
        
        # Output directory
        self.config.OUTPUT_INDEX_DIR.mkdir(parents=True, exist_ok=True)
        
    def load_chunks(self) -> List[Dict]:
        """Load chunks from JSON file."""
        logger.info(f"Loading chunks from {self.config.INPUT_CHUNKS_PATH}...")
        if not self.config.INPUT_CHUNKS_PATH.exists():
            raise FileNotFoundError(f"Chunk file not found: {self.config.INPUT_CHUNKS_PATH}")
            
        with open(self.config.INPUT_CHUNKS_PATH, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
            # normalize "page_content" to "text" if needed
            for c in chunks:
                if "page_content" in c and "text" not in c:
                    c["text"] = c["page_content"]

        logger.info(f"Loaded {len(chunks)} chunks.")
        # Filter empty chunks if any
        valid_chunks = [c for c in chunks if c.get('text') and len(c.get('text', "").strip()) > 0]
        
        return valid_chunks

    def _probe_optimal_batch_size(self, sample_text: str, current_config_batch: int) -> int:
        """For API based encoder, probing is not needed, just return configured batch size."""
        return current_config_batch

    def build_index(self, limit: Optional[int] = None):
        """Main indexing process."""
        chunks = self.load_chunks()
        
        if limit:
            logger.info(f"Limiting to {limit} chunks for testing.")
            chunks = chunks[:limit]
            
        total_chunks = len(chunks)
        
        # Check for checkpoint
        start_idx = 0
        metadata_list = []
        
        # Checking initial embedding dimension using first text to ensure FAISS matches
        logger.info("Initializing FAISS index and confirming exact embedding dimension...")
        if len(chunks) > 0 and start_idx == 0:
            sample_emb = self.encoder.encode_batch([chunks[0].get('text', "test")])
            actual_dim = sample_emb.shape[1]
            self.config.EMBEDDING_DIM = actual_dim
            logger.info(f"API confirmed embedding dimension is {actual_dim}")
            faiss_index = faiss.IndexFlatIP(self.config.EMBEDDING_DIM)
        elif start_idx == 0:
             faiss_index = faiss.IndexFlatIP(self.config.EMBEDDING_DIM)
             
        latest_batch, checkpoint_data, cached_index = self.checkpoint_manager.get_latest_checkpoint()
        if latest_batch is not None and checkpoint_data and cached_index:
            start_idx = checkpoint_data['next_start_idx']
            metadata_list = checkpoint_data['metadata']
            faiss_index = cached_index
            logger.info(f"Resuming from index {start_idx} ({faiss_index.ntotal} items indexed)")
        
        # Probing Batch Size (Not applicable for API, but kept for signature)
        if len(chunks) > 0 and start_idx == 0:
            self.config.BATCH_SIZE = self._probe_optimal_batch_size("", self.config.BATCH_SIZE)
            
        # Processing loop
        batch_size = self.config.BATCH_SIZE
        
        # Progress bar
        pbar = tqdm(total=total_chunks, initial=start_idx, desc="Indexing")
        
        current_batch_count = latest_batch + 1 if latest_batch else 0
        
        try:
            for i in range(start_idx, total_chunks, batch_size):
                batch_chunks = chunks[i : i + batch_size]
                batch_texts = [c['text'] for c in batch_chunks]
                
                # Encode
                batch_embs = self.encoder.encode_batch(batch_texts)
                
                # Validations
                if np.isnan(batch_embs).any() or np.isinf(batch_embs).any():
                    logger.warning(f"NaN/Inf detected in batch starting at {i}. Replacing with zeros.")
                    batch_embs = np.nan_to_num(batch_embs)
                
                # Accumulate results (streaming directly to FAISS)
                faiss_index.add(batch_embs)
                metadata_list.extend(batch_chunks)
                
                pbar.update(len(batch_chunks))
                current_batch_count += 1
                
                # Checkpoint every CHECKPOINT_INTERVAL chunks
                checkpoint_steps = max(1, self.config.CHECKPOINT_INTERVAL // batch_size)
                if current_batch_count % checkpoint_steps == 0:
                    self.checkpoint_manager.save_checkpoint({
                        'next_start_idx': i + len(batch_chunks),
                        'metadata': metadata_list
                    }, faiss_index, current_batch_count)
                    
        except KeyboardInterrupt:
            logger.info("Interrupted by user. Saving emergency checkpoint...")
            self.checkpoint_manager.save_checkpoint({
                'next_start_idx': pbar.n,
                'metadata': metadata_list
            }, faiss_index, current_batch_count)
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            traceback.print_exc()
            sys.exit(1)
            
        pbar.close()
        
        # Finalize Index
        self._finalize_index(faiss_index, metadata_list)

    def _finalize_index(self, index: faiss.Index, metadata_list: List[Dict]):
        """Save final FAISS index and metadata files."""
        logger.info("Finalizing index...")
        
        logger.info(f"Index built with {index.ntotal} vectors.")
        
        # Generate timestamp and model suffix
        timestamp = datetime.now().strftime("%Y%m%d")
        safe_model_name = self.config.MODEL_NAME.replace("/", "_").replace("-", "_")
        run_suffix = f"{safe_model_name}_{timestamp}"
        
        # Save FAISS Index
        index_path = self.config.OUTPUT_INDEX_DIR / f"chunks_{run_suffix}.index"
        faiss.write_index(index, str(index_path))
        logger.info(f"Saved FAISS index to {index_path}")
        
        # Save Metadata and Mapping
        mapping = {}
        processed_metadata = []
        
        for idx, meta in enumerate(metadata_list):
            # Mapping: int_id -> original_chunk_id
            chunk_id = meta.get('chunk_id')
            if not chunk_id and 'metadata' in meta:
                chunk_id = meta['metadata'].get('chunk_id')
            if not chunk_id:
                chunk_id = f"chunk_{idx}"
                
            mapping[str(idx)] = chunk_id
            processed_metadata.append(meta)
            
        mapping_path = self.config.OUTPUT_INDEX_DIR / f"chunk_mapping_{run_suffix}.json"
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
            
        # Also save the ordered metadata list for easier retrieval
        meta_path = self.config.OUTPUT_INDEX_DIR / f"index_metadata_{run_suffix}.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(processed_metadata, f, indent=2, ensure_ascii=False)
            
        logger.info("All files saved successfully.")

def main():
    parser = argparse.ArgumentParser(description="Build Qwen3 Index")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of chunks to index for testing")
    parser.add_argument("--retry", action="store_true", help="Force restart from scratch (clear checkpoints)")
    args = parser.parse_args()
    
    config = IndexerConfig()
    config.BATCH_SIZE = args.batch_size
    
    if args.retry:
        logger.info("Retry flag set. Clearing previous checkpoints and indices...")
        import shutil
        if config.CHECKPOINT_DIR.exists():
            try:
                # Windows might have issues deleting non-empty directories or files currently in use.
                # Just delete the files inside the directory instead.
                for file_path in config.CHECKPOINT_DIR.glob("*"):
                    try:
                        if file_path.is_file():
                            file_path.unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete {file_path}: {e}")
            except Exception as e:
                logger.warning(f"Could not clear checkpoint dir: {e}")
        config.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        # Clear previous index files
        for f in config.OUTPUT_INDEX_DIR.glob("chunks_*.index"):
            try: f.unlink()
            except Exception as e: logger.warning(f"Could not delete {f}: {e}")
        for f in config.OUTPUT_INDEX_DIR.glob("chunk_mapping_*.json"):
            try: f.unlink()
            except Exception as e: logger.warning(f"Could not delete {f}: {e}")
        for f in config.OUTPUT_INDEX_DIR.glob("index_metadata_*.json"):
            try: f.unlink()
            except Exception as e: logger.warning(f"Could not delete {f}: {e}")
    
    builder = IndexBuilder(config)
    builder.build_index(limit=args.limit)

if __name__ == "__main__":
    main()
