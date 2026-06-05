#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-T02: Qwen3-Embedding Indexer Builder

This script builds a FAISS index using Qwen3-Embedding-0.6B model.
It supports:
1. FP16 precision for memory efficiency
2. Dynamic batch processing
3. Checkpointing for failure recovery
4. FAISS IndexFlatIP for maximum accuracy
5. Comprehensive error handling and logging

Usage:
    python scripts/rag/indexing/rebuild_index_qwen3.py
"""

import os
import sys
import json
import time
import torch
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
from transformers import AutoModel, AutoTokenizer

# ============================================================================
# Configuration
# ============================================================================

class IndexerConfig:
    # Paths
    PROJECT_ROOT = Path(__file__).resolve().parents[3]
    MODELS_DIR = PROJECT_ROOT / "models" / "huggingface"
    INPUT_CHUNKS_PATH = PROJECT_ROOT / "data" / "rag" / "chunks" / "kimik2_0905_chunking.json"
    OUTPUT_INDEX_DIR = PROJECT_ROOT / "data" / "rag" / "faiss_index"
    CHECKPOINT_DIR = OUTPUT_INDEX_DIR / "checkpoints_qwen3"
    
    # Model
    MODEL_NAME = "Qwen3-Embedding-0.6B"
    MODEL_PATH = MODELS_DIR / MODEL_NAME
    
    # Indexing Settings
    BATCH_SIZE = 16  # Optimized based on P3-T01 validation
    MAX_LENGTH = 512
    EMBEDDING_DIM = 1024
    DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
    PRECISION = torch.float16 if torch.cuda.is_available() else torch.float32
    
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
    """Handles text encoding using Qwen3-Embedding model."""
    
    def __init__(self, config: IndexerConfig):
        self.config = config
        self.tokenizer = None
        self.model = None
        self._load_model()
        
    def _load_model(self):
        """Load model and tokenizer."""
        logger.info(f"Loading model from {self.config.MODEL_PATH}...")
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.MODEL_PATH, 
                trust_remote_code=True
            )
            self.model = AutoModel.from_pretrained(
                self.config.MODEL_PATH, 
                trust_remote_code=True,
                torch_dtype=self.config.PRECISION
            ).to(self.config.DEVICE)
            
            self.model.eval()
            logger.info(f"Model loaded successfully on {self.config.DEVICE} ({self.config.PRECISION})")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            raise

    def encode_batch(self, texts: List[str]) -> np.ndarray:
        """Encode a batch of texts into embeddings."""
        try:
            # Tokenize
            batch_dict = self.tokenizer(
                texts, 
                max_length=self.config.MAX_LENGTH, 
                padding=True, 
                truncation=True, 
                return_tensors="pt"
            ).to(self.config.DEVICE)
            
            # Inference
            with torch.no_grad():
                outputs = self.model(**batch_dict)
                # Mean pooling - take attention mask into account
                last_hidden = outputs.last_hidden_state
                attention_mask = batch_dict['attention_mask']
                
                # Mask out padding tokens and convert to FP32 for stability
                input_mask_expanded = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
                sum_embeddings = torch.sum(last_hidden * input_mask_expanded, 1).float()
                sum_mask = torch.clamp(input_mask_expanded.sum(1), min=1e-9).float()
                embeddings = sum_embeddings / sum_mask
                
                # Normalize embeddings
                embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                
            return embeddings.cpu().numpy().astype('float32')
            
        except Exception as e:
            logger.error(f"Error encoding batch: {str(e)}")
            # Return zeros in case of failure to maintain shape matching
            return np.zeros((len(texts), self.config.EMBEDDING_DIM), dtype=np.float32)

class CheckpointManager:
    """Manages index checkpoints."""
    
    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
    def save_checkpoint(self, data: Dict[str, Any], batch_num: int):
        """Save checkpoint data."""
        filepath = self.checkpoint_dir / f"checkpoint_batch_{batch_num}.pkl"
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)
        logger.debug(f"Saved checkpoint: {filepath.name}")
        
    def get_latest_checkpoint(self) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
        """Find and load the latest checkpoint."""
        files = list(self.checkpoint_dir.glob("checkpoint_batch_*.pkl"))
        if not files:
            return None, None
            
        # Sort by batch number
        try:
            files.sort(key=lambda x: int(x.stem.split('_')[-1]))
            latest_file = files[-1]
            batch_num = int(latest_file.stem.split('_')[-1])
            
            logger.info(f"Loading latest checkpoint: {latest_file.name}")
            with open(latest_file, 'rb') as f:
                data = pickle.load(f)
            return batch_num, data
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {str(e)}")
            return None, None

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
            
        logger.info(f"Loaded {len(chunks)} chunks.")
        # Filter empty chunks if any
        valid_chunks = [c for c in chunks if c.get('text') and len(c.get('text').strip()) > 0]
        if len(valid_chunks) < len(chunks):
            logger.warning(f"Filtered {len(chunks) - len(valid_chunks)} empty chunks.")
        
        return valid_chunks

    def build_index(self):
        """Main indexing process."""
        chunks = self.load_chunks()
        total_chunks = len(chunks)
        
        # Check for checkpoint
        start_idx = 0
        embeddings_list = []
        metadata_list = []
        processed_chunks_count = 0
        
        latest_batch, checkpoint_data = self.checkpoint_manager.get_latest_checkpoint()
        if latest_batch is not None and checkpoint_data:
            start_idx = checkpoint_data['next_start_idx']
            embeddings_list = checkpoint_data['embeddings']
            metadata_list = checkpoint_data['metadata']
            logger.info(f"Resuming from index {start_idx} ({len(embeddings_list)} embeddings loaded)")
        
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
                
                # Accumulate results (append each embedding individually)
                for emb in batch_embs:
                    embeddings_list.append(emb)
                metadata_list.extend(batch_chunks)
                
                pbar.update(len(batch_chunks))
                current_batch_count += 1
                
                # CUDA memory cleanup every 10 batches
                if current_batch_count % 10 == 0 and self.config.DEVICE != "cpu":
                    torch.cuda.empty_cache()
                
                # Checkpoint every CHECKPOINT_INTERVAL chunks
                if len(embeddings_list) >= (current_batch_count // (self.config.CHECKPOINT_INTERVAL // batch_size)) * self.config.CHECKPOINT_INTERVAL:
                    self.checkpoint_manager.save_checkpoint({
                        'next_start_idx': i + len(batch_chunks),
                        'embeddings': embeddings_list, # Note: This grows large in memory. 
                                                       # For huge datasets, we should append to disk (memmap). 
                                                       # For 2600 chunks, memory is fine.
                        'metadata': metadata_list
                    }, current_batch_count)
                    
        except KeyboardInterrupt:
            logger.info("Interrupted by user. Saving emergency checkpoint...")
            self.checkpoint_manager.save_checkpoint({
                'next_start_idx': pbar.n,
                'embeddings': embeddings_list,
                'metadata': metadata_list
            }, current_batch_count)
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            traceback.print_exc()
            sys.exit(1)
            
        pbar.close()
        
        # Finalize Index
        self._finalize_index(embeddings_list, metadata_list)

    def _finalize_index(self, embeddings_list: List[np.ndarray], metadata_list: List[Dict]):
        """Create FAISS index and save files."""
        logger.info("Finalizing index...")
        
        # Convert to single numpy array (vstack for 1D arrays)
        if isinstance(embeddings_list, list):
            if len(embeddings_list) > 0 and embeddings_list[0].ndim == 1:
                # List of 1D arrays -> stack vertically
                embeddings = np.vstack(embeddings_list).astype('float32')
            else:
                # List of 2D arrays or other -> fallback
                embeddings = np.array(embeddings_list).astype('float32')
        else:
            embeddings = embeddings_list.astype('float32')
             
        logger.info(f"Final embedding shape: {embeddings.shape}")
        
        # Validate shape
        if embeddings.ndim != 2 or embeddings.shape[1] != self.config.EMBEDDING_DIM:
            raise ValueError(f"Invalid embedding shape: {embeddings.shape}, expected (N, {self.config.EMBEDDING_DIM})")
        
        # Build FAISS Index (FlatIP = Cosine Similarity since vectors are normalized)
        index = faiss.IndexFlatIP(self.config.EMBEDDING_DIM)
        index.add(embeddings)
        
        logger.info(f"Index built with {index.ntotal} vectors.")
        
        # Save FAISS Index
        index_path = self.config.OUTPUT_INDEX_DIR / "chunks_qwen3.index"
        faiss.write_index(index, str(index_path))
        logger.info(f"Saved FAISS index to {index_path}")
        
        # Save Metadata and Mapping
        mapping = {}
        processed_metadata = []
        
        for idx, meta in enumerate(metadata_list):
            # Mapping: int_id -> original_chunk_id
            mapping[str(idx)] = meta['chunk_id']
            processed_metadata.append(meta)
            
        mapping_path = self.config.OUTPUT_INDEX_DIR / "chunk_mapping_qwen3.json"
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
            
        # Also save the ordered metadata list for easier retrieval
        meta_path = self.config.OUTPUT_INDEX_DIR / "index_metadata_qwen3.json"
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(processed_metadata, f, indent=2, ensure_ascii=False)
            
        logger.info("All files saved successfully.")

def main():
    parser = argparse.ArgumentParser(description="Build Qwen3 Index")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size")
    args = parser.parse_args()
    
    config = IndexerConfig()
    config.BATCH_SIZE = args.batch_size
    
    if config.DEVICE == "cpu":
        logger.warning("CUDA not available! Indexing will be very slow.")
        
    builder = IndexBuilder(config)
    builder.build_index()

if __name__ == "__main__":
    main()
