#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-T01: LLM-based Smart Chunking Prompt Design
==============================================

This module contains the prompt template and testing logic for
intelligent document chunking using Kimi K2 API.

The goal is to create semantically complete chunks with high-quality
keywords that improve RAG retrieval accuracy.

Problem Statement:
- Current rule-based chunking produces 800+ meaningless chunks
- 40% of extracted keywords are connective words (在於, 所以)
- Need semantic merging (title+content, case+analysis)

Solution:
- Use LLM to understand ancient Chinese semantics
- Extract truly meaningful core concepts
- Merge related content into coherent chunks

Usage:
    python scripts/rag/chunking/p2_t01_llm_chunking.py [--test]

Author: ML Engineer
Date: 2026-02-01
Task: P2-T01 (Phase 2 - LLM-based Chunking)
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field

# Setup logging
logger = logging.getLogger(__name__)

# Rich imports for beautiful console output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import print as rprint
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    Console = None
    rprint = print

# Project setup
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.rag.chunking.config import (
    MOONSHOT_API_KEY,
    MOONSHOT_API_BASE,
    MODEL_NAME,
    API_TEMPERATURE,
    API_MAX_TOKENS,
    API_MAX_RETRIES,
    API_RETRY_DELAY,
    API_RATE_LIMIT_DELAY,
    SOURCE_DIR,
    CHUNKS_DIR,
    MIN_CHUNK_LENGTH,
    MAX_CHUNK_LENGTH,
    TARGET_CHUNK_LENGTH,
    MIN_KEYWORDS_PER_CHUNK,
    MAX_KEYWORDS_PER_CHUNK,
)

# Import API client module (consistent with p2_t12_qa_generator pattern)
try:
    from scripts.rag.chunking.api_client import APIClient, api_client
    HAS_API_CLIENT = True
except ImportError:
    HAS_API_CLIENT = False
    api_client = None

# ============================================================================
# Prompt Templates (v1)
# ============================================================================

SMART_CHUNKING_PROMPT_V1 = """你是一位專精古籍文獻處理的 NLP 專家，負責為 RAG（檢索增強生成）系統準備高品質的文本塊。

## 任務說明
請分析以下古文文章，將其切分為語義完整的文本塊（chunks），並為每個塊提取關鍵詞。

## 切分原則
1. **語義完整性**：每個 chunk 必須是一個完整的意義單元
   - 標題與其說明內容應合併
   - 案例與其分析應合併
   - 引言與其解釋應合併
   
2. **長度控制**：每個 chunk 應在 {min_len}-{max_len} 字之間
   - 太短（<{min_len}字）：可能缺乏語義完整性，嘗試與前後合併
   - 太長（>{max_len}字）：可能涵蓋多個概念，嘗試拆分
   
3. **關鍵詞提取**：每個 chunk 提取 {min_kw}-{max_kw} 個關鍵詞
   - ✅ 人名、地名、書名、典故名、專有名詞
   - ✅ 核心概念詞、主題詞
   - ❌ 避免：連接詞（在於、所以、因此）、代名詞（他、她、這）、泛稱詞（東西、事物）

## 輸入文章
【標題】{title}
【類型】{doc_type}
【內容】
{content}

## 輸出格式（JSON Array）
請嚴格按照以下 JSON 格式輸出，不要添加任何額外說明：

**重要**：JSON 字串中的特殊字符必須正確轉義：
- 換行符使用 `\\n`（不是直接換行）
- 引號使用 `\\"`
- 反斜線使用 `\\\\`

```json
[
  {{
    "chunk_id": "c001",
    "text": "切分後的文本內容（單行，使用\\\\n表示換行）",
    "keywords": ["關鍵詞1", "關鍵詞2", "關鍵詞3"],
    "summary": "一句話概述此塊主題"
  }},
  ...
]
```

請開始處理："""


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ChunkResult:
    """Result of chunking a single document."""
    chunk_id: str
    text: str
    keywords: List[str]
    summary: str
    
    def to_dict(self) -> Dict:
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "keywords": self.keywords,
            "summary": self.summary
        }


@dataclass
class DocumentChunkingResult:
    """Result of chunking an entire document."""
    doc_id: str
    doc_title: str
    doc_type: str
    chunks: List[ChunkResult]
    processing_time: float
    success: bool
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "doc_type": self.doc_type,
            "chunks": [c.to_dict() for c in self.chunks],
            "processing_time": self.processing_time,
            "success": self.success,
            "error_message": self.error_message
        }


# ============================================================================
# API Client Wrapper (uses api_client module for consistency)
# ============================================================================

class KimiAPIClient:
    """LiteLLM-based API client for Kimi K2.
    
    This is a thin wrapper around the shared api_client module for backward
    compatibility. New code should use api_client directly.
    
    Usage:
        # Direct module usage (preferred)
        from scripts.rag.chunking.api_client import api_client
        content, elapsed = api_client.generate(prompt)
        
        # Or via wrapper (for backward compatibility)
        client = KimiAPIClient()
        content, elapsed = client.generate(prompt)
    """
    
    def __init__(self):
        """Initialize using the shared API client."""
        if not HAS_API_CLIENT:
            raise ImportError(
                "API client module not available. Check api_client.py exists."
            )
        self._client = api_client
        
    def test_connection(self) -> Tuple[bool, str]:
        """Test API connection."""
        return self._client.test_connection()
    
    def generate(self, prompt: str) -> Tuple[str, float]:
        """
        Call API to generate content.
        
        Returns:
            Tuple of (content, elapsed_time)
        """
        return self._client.generate(prompt)


# ============================================================================
# Smart Chunking Logic
# ============================================================================

class SmartChunker:
    """LLM-based intelligent document chunker."""
    
    def __init__(self, api_client: Optional[KimiAPIClient] = None):
        """
        Initialize the chunker.
        
        Args:
            api_client: Optional pre-configured API client
        """
        self.client = api_client or KimiAPIClient()
        
    def build_prompt(self, title: str, doc_type: str, content: str) -> str:
        """
        Build the chunking prompt for a document.
        
        Args:
            title: Document title
            doc_type: Document type (e.g., 人物, 回目, 詩詞)
            content: Document content
            
        Returns:
            Formatted prompt string
        """
        return SMART_CHUNKING_PROMPT_V1.format(
            min_len=MIN_CHUNK_LENGTH,
            max_len=MAX_CHUNK_LENGTH,
            min_kw=MIN_KEYWORDS_PER_CHUNK,
            max_kw=MAX_KEYWORDS_PER_CHUNK,
            title=title,
            doc_type=doc_type,
            content=content
        )
    
    def _fix_json_string(self, json_str: str) -> str:
        """
        修復 LLM 輸出中常見的 JSON 格式錯誤。
        
        關鍵問題：LLM 在 JSON 字串值內嵌入了實際的換行符（literal newline），
        而非轉義序列（\\n），這導致 JSON 解析失敗。
        
        安全策略：先驗證原始 JSON 是否有效，有效則不修改。
        
        Args:
            json_str: 原始 JSON 字串
            
        Returns:
            修復後的 JSON 字串（如果原始有效則返回原始）
        """
        import re
        
        # 0. 先嘗試直接解析 - 如果成功就不修改
        try:
            json.loads(json_str)
            return json_str  # 原始 JSON 有效，不做任何修改
        except json.JSONDecodeError:
            pass  # 需要修復
        
        # 1. 移除 BOM 和其他不可見字符
        fixed = json_str.strip('\ufeff\u200b\u200c\u200d')
        
        # 2. 核心修復：替換 JSON 字串值內的實際換行符
        # 策略：逐字符解析，只在雙引號內部替換換行符
        result = []
        in_string = False
        escape_next = False
        
        for char in fixed:
            if escape_next:
                result.append(char)
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                result.append(char)
                continue
            
            if char == '"':
                in_string = not in_string
                result.append(char)
                continue
            
            if in_string:
                # 在字串值內部，替換控制字符
                if char == '\n':
                    result.append('\\n')
                elif char == '\r':
                    result.append('\\r')
                elif char == '\t':
                    result.append('\\t')
                elif char == '\b':
                    result.append('\\b')
                elif char == '\f':
                    result.append('\\f')
                else:
                    result.append(char)
            else:
                result.append(char)
        
        fixed = ''.join(result)
        
        # 3. 移除註釋（LLM 有時會添加）
        fixed = re.sub(r'//.*?\n', '\n', fixed)
        fixed = re.sub(r'/\*.*?\*/', '', fixed, flags=re.DOTALL)
        
        # 4. 修復尾部逗號
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        
        # 5. 驗證修復後的 JSON 是否有效
        try:
            json.loads(fixed)
            return fixed  # 規則修復成功
        except json.JSONDecodeError:
            # 規則修復失敗，返回修復後的版本讓上層處理
            return fixed
    
    def _llm_fix_json(self, broken_json: str, doc_id: str) -> Optional[str]:
        """
        使用 LLM 修復無法解析的 JSON。
        
        這是最後的防線，當規則修復失敗時使用。
        
        Args:
            broken_json: 無法解析的 JSON 字串
            doc_id: 文件 ID（用於日誌）
            
        Returns:
            修復後的 JSON 字串，如果修復失敗返回 None
        """
        FIX_JSON_PROMPT = """你是一個 JSON 修復專家。以下 JSON 有格式錯誤，請修復並返回正確的 JSON。

要求：
1. 只返回修復後的 JSON，不要任何解釋
2. 不要使用 markdown code block
3. 確保所有字串內的換行符正確轉義為 \\n
4. 確保所有引號正確配對
5. 保持原始數據內容不變

錯誤的 JSON：
{broken_json}

修復後的 JSON："""
        
        try:
            logger.info(f"🔧 嘗試使用 LLM 修復 {doc_id} 的 JSON...")
            print(f"  🔧 嘗試 LLM 修復 JSON...")
            
            prompt = FIX_JSON_PROMPT.format(broken_json=broken_json[:4000])  # 限制長度
            response, _ = self.client.generate(prompt)
            
            # 清理回應
            fixed_json = response.strip()
            if fixed_json.startswith("```"):
                fixed_json = fixed_json.split("```")[1]
                if fixed_json.startswith("json"):
                    fixed_json = fixed_json[4:]
                fixed_json = fixed_json.split("```")[0].strip()
            
            # 驗證修復結果
            json.loads(fixed_json)
            logger.info(f"✅ LLM 修復 {doc_id} 成功")
            print(f"  ✅ LLM 修復成功")
            return fixed_json
            
        except json.JSONDecodeError as e:
            logger.warning(f"❌ LLM 修復 {doc_id} 失敗: {e}")
            print(f"  ❌ LLM 修復失敗: {e}")
            return None
        except Exception as e:
            logger.warning(f"❌ LLM 修復 {doc_id} 異常: {e}")
            return None
    
    def parse_response(self, response: str, doc_id: str, use_llm_fix: bool = True) -> List[ChunkResult]:
        """
        Parse LLM response into ChunkResult objects.
        使用多重策略確保 JSON 解析成功：
        1. 直接解析原始 JSON
        2. 規則修復後解析
        3. LLM 修復後解析（可選）
        
        Args:
            response: Raw LLM response
            doc_id: Document ID for chunk ID prefix
            use_llm_fix: 是否在規則修復失敗後使用 LLM 修復（default: True）
            
        Returns:
            List of ChunkResult objects
        """
        json_str = None
        
        # Step 1: 提取 JSON 部分
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()
        except Exception:
            json_str = response.strip()
        
        # Step 2: 嘗試直接解析（最安全，不修改任何內容）
        try:
            chunks_data = json.loads(json_str)
            return self._parse_chunks_data(chunks_data, doc_id)
        except json.JSONDecodeError:
            pass  # 繼續嘗試修復
        
        # Step 3: 規則修復後解析
        try:
            fixed_json = self._fix_json_string(json_str)
            chunks_data = json.loads(fixed_json)
            logger.debug(f"規則修復 {doc_id} 成功")
            return self._parse_chunks_data(chunks_data, doc_id)
        except json.JSONDecodeError as e:
            rule_fix_error = e
        
        # Step 4: LLM 修復（可選）
        if use_llm_fix:
            llm_fixed_json = self._llm_fix_json(json_str, doc_id)
            if llm_fixed_json:
                try:
                    chunks_data = json.loads(llm_fixed_json)
                    return self._parse_chunks_data(chunks_data, doc_id)
                except json.JSONDecodeError as e:
                    logger.warning(f"LLM 修復後仍解析失敗 {doc_id}: {e}")
        
        # 所有修復都失敗，記錄錯誤
        print(f"  ⚠️ JSON解析失敗: {rule_fix_error}")
        print(f"  📝 LLM回應長度: {len(response)} 字元")
        print(f"  📝 錯誤位置: 第 {rule_fix_error.lineno} 行，第 {rule_fix_error.colno} 列")
        logger.warning(f"JSON parse error for {doc_id}: {rule_fix_error}")
        
        # 保存失敗的回應供後續分析
        error_log_dir = Path("output/chunking_errors")
        error_log_dir.mkdir(parents=True, exist_ok=True)
        error_file = error_log_dir / f"{doc_id}_error.txt"
        with open(error_file, "w", encoding="utf-8") as f:
            f.write(f"Error: {rule_fix_error}\n\n")
            f.write(f"Original Response:\n{response}\n\n")
            f.write(f"Rule-fixed JSON:\n{fixed_json if 'fixed_json' in locals() else 'N/A'}\n")
        logger.info(f"Error details saved to {error_file}")
        
        return []
    
    def _parse_chunks_data(self, chunks_data: Any, doc_id: str) -> List[ChunkResult]:
        """
        將解析後的 JSON 數據轉換為 ChunkResult 對象。
        
        Args:
            chunks_data: 解析後的 JSON 數據
            doc_id: 文件 ID
            
        Returns:
            List of ChunkResult objects
        """
        if not isinstance(chunks_data, list):
            chunks_data = [chunks_data]
        
        results = []
        for i, chunk_data in enumerate(chunks_data):
            # 必須有 text 欄位
            if not chunk_data.get("text"):
                logger.warning(f"Chunk {i+1} missing text field, skipping")
                continue
            
            # Generate proper chunk_id with doc prefix
            chunk_id = f"{doc_id}_c{i+1:03d}"
            
            results.append(ChunkResult(
                chunk_id=chunk_id,
                text=chunk_data.get("text", ""),
                keywords=chunk_data.get("keywords", []),
                summary=chunk_data.get("summary", "")
            ))
        
        if results:
            logger.debug(f"Successfully parsed {len(results)} chunks for {doc_id}")
        else:
            logger.warning(f"No valid chunks found for {doc_id}")
        
        return results
    
    def chunk_document(
        self,
        doc_id: str,
        title: str,
        doc_type: str,
        content: str,
        max_retries: int = 2
    ) -> DocumentChunkingResult:
        """
        Chunk a single document using LLM with automatic retry on JSON parse errors.
        
        Args:
            doc_id: Unique document identifier
            title: Document title
            doc_type: Document type
            content: Document content
            max_retries: Maximum retry attempts for JSON parse errors (default: 2)
            
        Returns:
            DocumentChunkingResult with chunks or error
        """
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                # Build prompt
                prompt = self.build_prompt(title, doc_type, content)
                
                # Call API
                response, elapsed = self.client.generate(prompt)
                
                # Parse response
                chunks = self.parse_response(response, doc_id)
                
                if chunks:
                    # 成功解析
                    if attempt > 0:
                        logger.info(f"✅ Retry {attempt} succeeded for {doc_id}")
                    return DocumentChunkingResult(
                        doc_id=doc_id,
                        doc_title=title,
                        doc_type=doc_type,
                        chunks=chunks,
                        processing_time=elapsed,
                        success=True
                    )
                else:
                    # JSON 解析失敗，記錄錯誤
                    last_error = f"JSON parse failed (attempt {attempt + 1}/{max_retries + 1})"
                    if attempt < max_retries:
                        logger.warning(f"🔄 Retrying {doc_id} (attempt {attempt + 2}/{max_retries + 1})...")
                        time.sleep(2)  # 短暫延遲再重試
                        continue
            
            except Exception as e:
                last_error = str(e)
                logger.error(f"Error processing {doc_id}: {e}")
                if attempt < max_retries:
                    logger.warning(f"🔄 Retrying {doc_id} (attempt {attempt + 2}/{max_retries + 1})...")
                    time.sleep(2)
                    continue
        
        # 所有重試都失敗，使用 fallback
        logger.warning(f"⚠️ All retries failed for {doc_id}, using fallback chunking")
        print(f"  ⚠️ {doc_id}: 已重試 {max_retries} 次仍失敗，使用規則分塊")
        
        fallback_chunks = self._fallback_chunking(doc_id, title, content)
        
        return DocumentChunkingResult(
            doc_id=doc_id,
            doc_title=title,
            doc_type=doc_type,
            chunks=fallback_chunks,
            processing_time=0,
            success=False,
            error_message=last_error
        )
    
    def _fallback_chunking(
        self,
        doc_id: str,
        title: str,
        content: str
    ) -> List[ChunkResult]:
        """
        Fallback rule-based chunking when LLM fails.
        
        Args:
            doc_id: Document ID
            title: Document title
            content: Document content
            
        Returns:
            List of ChunkResult from simple rule-based splitting
        """
        # Simple paragraph-based splitting
        paragraphs = content.split('\n\n')
        chunks = []
        
        current_text = ""
        chunk_num = 1
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            if len(current_text) + len(para) > MAX_CHUNK_LENGTH and current_text:
                # Save current chunk
                chunks.append(ChunkResult(
                    chunk_id=f"{doc_id}_c{chunk_num:03d}",
                    text=current_text.strip(),
                    keywords=self._extract_simple_keywords(current_text),
                    summary=f"[LLM Kimi K2-0905 切分塊] {title}"
                ))
                chunk_num += 1
                current_text = para
            else:
                current_text += "\n\n" + para if current_text else para
        
        # Add final chunk
        if current_text.strip():
            chunks.append(ChunkResult(
                chunk_id=f"{doc_id}_c{chunk_num:03d}",
                text=current_text.strip(),
                keywords=self._extract_simple_keywords(current_text),
                summary=f"[LLM Kimi K2-0905 切分塊] {title}"
            ))
        
        return chunks
    
    def _extract_simple_keywords(self, text: str) -> List[str]:
        """Extract keywords using simple heuristics (fallback)."""
        # Very basic: extract quoted terms and proper nouns
        keywords = []
        
        # Extract 「」quoted terms
        import re
        quoted = re.findall(r'「([^」]+)」', text)
        keywords.extend(quoted[:5])
        
        # Extract 《》book names
        books = re.findall(r'《([^》]+)》', text)
        keywords.extend(books[:3])
        
        return list(set(keywords))[:MAX_KEYWORDS_PER_CHUNK]


# ============================================================================
# Quality Evaluation
# ============================================================================

def evaluate_chunk_quality(chunk: ChunkResult) -> Dict:
    """
    Evaluate the quality of a single chunk.
    
    Returns:
        Dict with quality metrics
    """
    metrics = {
        "length": len(chunk.text),
        "length_ok": MIN_CHUNK_LENGTH <= len(chunk.text) <= MAX_CHUNK_LENGTH,
        "keyword_count": len(chunk.keywords),
        "keyword_count_ok": MIN_KEYWORDS_PER_CHUNK <= len(chunk.keywords) <= MAX_KEYWORDS_PER_CHUNK,
        "has_summary": bool(chunk.summary),
    }
    
    # Check keyword quality (not connective words)
    bad_keywords = ['在於', '所以', '因此', '然後', '這個', '那個', '東西', '事物', '他們', '她們']
    good_keywords = [kw for kw in chunk.keywords if kw not in bad_keywords and len(kw) >= 2]
    
    metrics["good_keyword_ratio"] = len(good_keywords) / len(chunk.keywords) if chunk.keywords else 0
    metrics["keyword_quality_ok"] = metrics["good_keyword_ratio"] >= 0.8
    
    # Overall score
    metrics["quality_score"] = sum([
        metrics["length_ok"] * 30,
        metrics["keyword_count_ok"] * 25,
        metrics["keyword_quality_ok"] * 30,
        metrics["has_summary"] * 15,
    ]) / 100
    
    return metrics


def evaluate_document_chunking(result: DocumentChunkingResult) -> Dict:
    """
    Evaluate chunking quality for entire document.
    
    Returns:
        Dict with aggregated quality metrics
    """
    if not result.success or not result.chunks:
        return {
            "success": False,
            "chunk_count": 0,
            "avg_quality_score": 0,
            "error": result.error_message
        }
    
    chunk_metrics = [evaluate_chunk_quality(c) for c in result.chunks]
    
    return {
        "success": True,
        "chunk_count": len(result.chunks),
        "avg_length": sum(m["length"] for m in chunk_metrics) / len(chunk_metrics),
        "length_compliance_rate": sum(1 for m in chunk_metrics if m["length_ok"]) / len(chunk_metrics),
        "keyword_compliance_rate": sum(1 for m in chunk_metrics if m["keyword_count_ok"]) / len(chunk_metrics),
        "keyword_quality_rate": sum(m["good_keyword_ratio"] for m in chunk_metrics) / len(chunk_metrics),
        "avg_quality_score": sum(m["quality_score"] for m in chunk_metrics) / len(chunk_metrics),
        "processing_time": result.processing_time
    }


# ============================================================================
# Test Function
# ============================================================================

def run_prompt_test():
    """Run test with sample documents to validate prompt design."""
    print("="*60)
    print("P2-T01: LLM-based Chunking Prompt Test")
    print("="*60)
    
    # Test documents (representative samples)
    test_docs = [
        {
            "id": "test_001",
            "title": "林黛玉",
            "type": "人物",
            "content": """林黛玉是《紅樓夢》的女主角之一，是賈母的外孫女、林如海與賈敏之女。

林黛玉初進賈府時年僅六歲，因母親去世，被賈母接入府中撫養。她聰慧絕頂，才華橫溢，善於詩詞歌賦，是大觀園中最有才情的女子。

林黛玉與賈寶玉青梅竹馬，兩人情投意合，但因黛玉體弱多病，加之賈府日漸衰敗，最終未能如願。黛玉性格敏感多疑，常因小事落淚，故有「淚人」之稱。

其著名詩作《葬花吟》、《桃花行》等，皆為紅樓詩詞經典。「質本潔來還潔去，強於污淖陷渠溝」更是其性格寫照。"""
        },
        {
            "id": "test_002",
            "title": "大觀園",
            "type": "地點",
            "content": """大觀園是《紅樓夢》中賈府為迎接元春省親而建造的園林。

建園緣由：賈元春被封為貴妃，皇帝准許宮妃回家省親。賈府為此大興土木，將寧國府後面的花園與榮國府東面的空地合併擴建。

園中景致：大觀園佔地廣闊，內有怡紅院、瀟湘館、蘅蕪苑、稻香村等處所。園中亭台樓閣，山水相依，是當時最精緻的私家園林之一。

後來，寶玉、黛玉、寶釵等人搬入園中居住，大觀園成為眾女兒的天地，也是紅樓故事的主要場景。"""
        }
    ]
    
    # Initialize
    print("\n🔌 Testing API connection...")
    client = KimiAPIClient()
    success, msg = client.test_connection()
    print(f"   {'✅' if success else '❌'} {msg}")
    
    if not success:
        print("\n⚠️ API connection failed. Running dry-run mode...")
        chunker = SmartChunker(client)
        
        # Just show what the prompt would look like
        for doc in test_docs[:1]:
            prompt = chunker.build_prompt(doc["title"], doc["type"], doc["content"])
            print(f"\n📋 Sample Prompt for '{doc['title']}':")
            print("-" * 40)
            print(prompt[:500] + "...")
        return
    
    # Run actual test
    chunker = SmartChunker(client)
    results = []
    
    for doc in test_docs:
        print(f"\n📄 Processing: {doc['title']}")
        result = chunker.chunk_document(
            doc["id"],
            doc["title"],
            doc["type"],
            doc["content"]
        )
        results.append(result)
        
        # Evaluate quality
        eval_result = evaluate_document_chunking(result)
        
        print(f"   {'✅' if result.success else '❌'} Chunks: {len(result.chunks)}")
        if result.success:
            print(f"   📊 Avg Quality Score: {eval_result['avg_quality_score']:.2f}")
            print(f"   ⏱️ Processing Time: {result.processing_time:.2f}s")
            
            for chunk in result.chunks:
                print(f"\n   Chunk {chunk.chunk_id}:")
                print(f"      Text: {chunk.text[:100]}...")
                print(f"      Keywords: {chunk.keywords}")
                print(f"      Summary: {chunk.summary}")
    
    # Save test results
    output_path = CHUNKS_DIR / "prompt_test_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump([r.to_dict() for r in results], f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Test results saved to: {output_path}")


# ============================================================================
# Main
# ============================================================================

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="基於 LLM 的智能分塊 (P2-T01)")
    parser.add_argument("--test", action="store_true", help="使用範例文件執行提示測試")
    parser.add_argument("--dry-run", action="store_true", help="預覽提示但不呼叫 API")
    args = parser.parse_args()
    
    if args.test or args.dry_run:
        run_prompt_test()
    else:
        console = Console() if HAS_RICH else None
        
        if HAS_RICH:
            console.print(Panel.fit(
                "[bold cyan]基於 LLM 的智能分塊 (P2-T01)[/bold cyan]\n\n"
                "[yellow]使用方式：[/yellow]\n"
                "  --test     使用範例文件執行提示測試\n"
                "  --dry-run  預覽提示但不呼叫 API",
                border_style="cyan",
                title="智能分塊器"
            ))
        else:
            print("使用 --test 執行提示測試")
            print("使用 --dry-run 預覽提示但不呼叫 API")


if __name__ == "__main__":
    main()
