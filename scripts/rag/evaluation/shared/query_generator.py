#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared Query Generator for RAG Evaluation

This module provides a unified query generation strategy for both
BM25+Reranker and FAISS evaluation scripts.

Query Type Design (aligned with qwen3_retrieval_evaluation.py):
===============================================================
- keyword: Direct keyword from chunk (highest precision expected)
- summary: Natural language from summary
- semantic: Question format using keywords
- keyword_question: Fallback for medium difficulty

Difficulty Mapping:
===================
- easy → keyword query
- medium → summary query  
- hard → semantic/LLM-rewritten query

Author: ML Engineer
Date: 2026-02-02
"""

import os
import random
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")

# OpenRouter API Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "qwen/qwen-2.5-72b-instruct"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Default random seed for reproducibility
DEFAULT_RANDOM_SEED = 42

logger = logging.getLogger(__name__)


@dataclass
class QuerySample:
    """A single evaluation query sample."""
    query_id: str
    query_text: str
    query_type: str
    difficulty: str
    source_type: str
    ground_truth_chunk_ids: List[str]
    ground_truth_texts: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Result of a single retrieval."""
    query_id: str
    strategy: str
    retrieved_chunk_ids: List[str]
    retrieved_scores: List[float]
    latency_ms: float
    latency_breakdown: Dict[str, float] = field(default_factory=dict)


class SimpleQueryGenerator:
    """
    Generate test queries from chunks with stratified sampling.
    
    This generator creates queries of varying difficulty levels:
    - easy: keyword-based queries (direct match expected)
    - medium: summary-based queries (natural language)
    - hard: semantic/question-based queries (requires understanding)
    
    The design ensures consistent query generation across different
    evaluation pipelines for fair comparison.
    """
    
    def __init__(
        self,
        chunks: List[Dict],
        samples_per_type: int = 5,
        random_seed: int = DEFAULT_RANDOM_SEED,
        enable_llm_rewrite: bool = True
    ):
        """
        Initialize query generator.
        
        Args:
            chunks: List of chunk dictionaries with 'chunk_id', 'text', 
                   'keywords', 'summary', 'source_type' fields
            samples_per_type: Number of samples per source type
            random_seed: Random seed for reproducibility
            enable_llm_rewrite: Whether to use LLM for hard queries
        """
        self.chunks = chunks
        self.samples_per_type = samples_per_type
        self.random_seed = random_seed
        self.enable_llm_rewrite = enable_llm_rewrite
        self.llm_client = None
        
        random.seed(random_seed)
        
        if enable_llm_rewrite and OPENROUTER_API_KEY:
            self._init_llm_client()
    
    def _init_llm_client(self):
        """Initialize LLM client for query rewriting."""
        try:
            from openai import OpenAI
            self.llm_client = OpenAI(
                base_url=OPENROUTER_BASE_URL,
                api_key=OPENROUTER_API_KEY
            )
            logger.info("LLM client initialized for query generation")
        except Exception as e:
            logger.warning(f"LLM client init failed: {e}")
    
    def generate_queries(self) -> List[QuerySample]:
        """
        Generate stratified queries across source types and difficulties.
        
        Returns:
            List of QuerySample objects for evaluation
        """
        # Group chunks by source_type
        by_type = defaultdict(list)
        for chunk in self.chunks:
            by_type[chunk.get('source_type', 'unknown')].append(chunk)
        
        all_queries = []
        difficulties = ["easy", "medium", "hard"]
        
        for source_type, type_chunks in by_type.items():
            sample_size = min(self.samples_per_type, len(type_chunks))
            sampled = random.sample(type_chunks, sample_size)
            
            logger.info(f"Generating queries for {source_type} ({sample_size} samples)")
            
            for chunk in sampled:
                for difficulty in difficulties:
                    query = self._generate_query(chunk, source_type, difficulty)
                    if query:
                        all_queries.append(query)
        
        logger.info(f"Total queries generated: {len(all_queries)}")
        return all_queries
    
    def _generate_query(
        self,
        chunk: Dict,
        source_type: str,
        difficulty: str
    ) -> Optional[QuerySample]:
        """
        Generate a single query matching qwen3_retrieval_evaluation.py design.
        
        Query Types (from qwen3 design):
        - keyword: Direct keyword from chunk (highest precision)
        - summary: Natural language from summary
        - semantic: Question format using keywords
        - keyword_question: Fallback when summary unavailable
        
        Args:
            chunk: Chunk dictionary
            source_type: Type of source (e.g., 'classical_literature')
            difficulty: 'easy', 'medium', or 'hard'
            
        Returns:
            QuerySample or None if generation fails
        """
        chunk_id = chunk['chunk_id']
        keywords = chunk.get('keywords', [])
        summary = chunk.get('summary', '')
        text = chunk.get('text', '')
        
        query_text = None
        query_type = None
        
        if difficulty == "easy":
            # Query Type 1: Keyword Query (highest precision expected)
            if keywords:
                query_text = ' '.join(keywords[:2]) if len(keywords) >= 2 else keywords[0]
                query_type = "keyword"
        
        elif difficulty == "medium":
            # Query Type 2: Summary Query (natural language)
            if summary and len(summary) > 10:
                query_text = summary
                query_type = "summary"
            elif keywords:
                # Fallback: keyword-based question
                query_text = f"關於{keywords[0]}的內容"
                query_type = "keyword_question"
        
        elif difficulty == "hard":
            # Query Type 3: Semantic Query (question format) or LLM rewritten
            if self.llm_client and self.enable_llm_rewrite and (keywords or summary):
                query_text = self._rewrite_with_llm(chunk)
                query_type = "semantic"
            elif keywords and len(keywords) >= 2:
                # Semantic patterns matching qwen3 design
                patterns = [
                    f"什麼是{keywords[0]}",
                    f"{keywords[0]}的含義",
                    f"關於{keywords[0]}和{keywords[1]}",
                    f"{keywords[0]}{keywords[1]}的關係",
                ]
                query_text = random.choice(patterns)
                query_type = "semantic"
            elif keywords:
                query_text = f"什麼是{keywords[0]}"
                query_type = "semantic"
        
        if not query_text:
            return None
        
        return QuerySample(
            query_id=f"{chunk_id}_{difficulty}",
            query_text=query_text,
            query_type=query_type,
            difficulty=difficulty,
            source_type=source_type,
            ground_truth_chunk_ids=[chunk_id],
            ground_truth_texts=[text],
            metadata={"keywords": keywords}
        )
    
    def _rewrite_with_llm(self, chunk: Dict) -> Optional[str]:
        """
        Use LLM to generate a natural research question.
        
        Args:
            chunk: Chunk dictionary with keywords and summary
            
        Returns:
            Generated question or None if failed
        """
        if not self.llm_client:
            return None
        
        keywords = chunk.get('keywords', [])
        summary = chunk.get('summary', '')
        
        prompt = f"""根據以下內容，生成一個自然的研究問題。

摘要：{summary}
關鍵詞：{', '.join(keywords[:5])}

要求：像真實學者會提出的問題，用現代中文。只輸出問題本身。

問題："""

        try:
            response = self.llm_client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"LLM rewrite failed: {e}")
            return None
