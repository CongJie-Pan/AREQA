#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chunking Module Configuration
=============================

Configuration for LLM-based chunking using Kimi K2 API.
Reuses patterns from scripts/training/p2_t12_qa_generator/config.py

Author: ML Engineer
Date: 2026-02-01
Task: P2-T01 (Phase 2 - LLM-based Chunking Design)
"""

import os
from pathlib import Path

# ============================================================================
# Project Paths
# ============================================================================
# Path: scripts/rag/chunking/config.py
# Need to go up 4 levels to reach project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# Load .env file
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# Data directories
DATA_DIR = PROJECT_ROOT / "data"
RAG_DIR = DATA_DIR / "rag"
SOURCE_DIR = RAG_DIR / "source"
CHUNKS_DIR = RAG_DIR / "chunks"

# Aliases for compatibility
RAG_SOURCE_DIR = SOURCE_DIR
RAG_CHUNKS_DIR = CHUNKS_DIR

# ============================================================================
# API Configuration (OpenRouter)
# ============================================================================
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Model selection - using OpenRouter format
# Kimi K2-0905 via OpenRouter: openrouter/moonshotai/kimi-k2-0905
MODEL_NAME = "openrouter/moonshotai/kimi-k2-0905"

# Legacy Moonshot config (kept for backwards compatibility)
MOONSHOT_API_KEY = os.environ.get("MOONSHOT_API_KEY", "")
MOONSHOT_API_BASE = "https://api.moonshot.cn/v1"

# API parameters (conservative for chunking task)
API_TEMPERATURE = 0.3  # Lower for more consistent output
API_MAX_TOKENS = 13000  # 提升至 13K，應對最長章節 + JSON 結構開銷 (Kimi K2 max: 16384)
API_MAX_RETRIES = 3
API_RETRY_DELAY = 5     # seconds
API_RATE_LIMIT_DELAY = 2  # seconds between requests

# ============================================================================
# Chunking Configuration
# ============================================================================
# Ideal chunk length range
MIN_CHUNK_LENGTH = 200   # Minimum meaningful chunk
MAX_CHUNK_LENGTH = 800   # Maximum for embedding efficiency
TARGET_CHUNK_LENGTH = 400  # Optimal target

# Batch processing
BATCH_SIZE = 10  # Number of articles per batch
CHECKPOINT_INTERVAL = 1  # Save checkpoint every N articles

# Output files
OUTPUT_CHUNKS_FILE = CHUNKS_DIR / "smart_chunks.json"
CHECKPOINT_DIR = CHUNKS_DIR / "checkpoints"
PROGRESS_FILE = CHUNKS_DIR / "llm_chunking_progress.json"

# ============================================================================
# Quality Thresholds
# ============================================================================
MIN_KEYWORDS_PER_CHUNK = 2
MAX_KEYWORDS_PER_CHUNK = 8
KEYWORD_QUALITY_THRESHOLD = 0.85  # 85% of keywords should be meaningful
