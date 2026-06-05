#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3-Tier Hybrid Chunking Pipeline (Qwen3)
=====================================
依據 docs/implementationPlan/Hybrid_Chunking_Pipeline_Plan.md 所設計之模組。
包含：
1. 第一層：Markdown / 結構感知初切 (Structure-Aware Pre-chunking)
2. 第二層：LLM 語義邊際識別 (LLM Boundary Detection - Split Points Only)
3. 第三層：Anthropic/Metadata 上下文強化 (Contextual Prefixing)

Model: qwen/qwen3-30b-a3b-instruct-2507 via OpenRouter (Non-thinking mode)
"""

import os
import re
import json
import time
import logging
import asyncio
import aiohttp
import random
from typing import List, Dict, Any, Optional
from pathlib import Path
import requests

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from dotenv import load_dotenv

# ============== 新增 Rich 終端顯示 ==============
from rich.logging import RichHandler
from rich.console import Console

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("hybrid_chunking")
# ==============================================

# Project setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
else:
    logger.warning(f"[bold yellow]無法找到本地 .env 檔案[/bold yellow]: {ENV_PATH}")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# 依據企劃書要求使用 OpenRouter Qwen3
MODEL_NAME = "qwen/qwen3-30b-a3b-instruct-2507"

# 追蹤 fallback 發生次數
FALLBACK_COUNT = 0

class LeakyBucketLimiter:
    """嚴格 Rate Limiter，確保請求速率不超過 rate RPS"""
    def __init__(self, rate: float, epsilon: float = 0.01):
        self.rate = rate
        self.interval = 1.0 / rate
        self.lock = asyncio.Lock()
        self.epsilon = epsilon
        self.next_available = time.monotonic()

    async def acquire(self):
        async with self.lock:
            now = time.monotonic()
            wait_time = self.next_available - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.next_available = time.monotonic() + self.interval + self.epsilon


async def call_llm_async(
    session: aiohttp.ClientSession,
    rate_limiter: LeakyBucketLimiter,
    payload: dict,
    headers: dict,
    max_retries: int = 5,
    base_delay: float = 2.0
) -> str:
    for attempt in range(max_retries):
        if rate_limiter:
            await rate_limiter.acquire()
        try:
            async with session.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 429:
                    retry_after = float(response.headers.get('Retry-After', base_delay))
                    logger.warning(f"429 Too Many Requests. Retrying in {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                data = await response.json()
                return data['choices'][0]['message']['content']
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            delay = base_delay * (2 ** attempt) + random.random()
            logger.error(f"Error calling LLM (Attempt {attempt+1}/{max_retries}): {e}. Retrying in {delay:.2f}s...")
            await asyncio.sleep(delay)
    raise RuntimeError("Max retries exceeded")


async def call_llm_boundary_detection(text_blocks: List[str], session: aiohttp.ClientSession, rate_limiter: LeakyBucketLimiter = None) -> List[int]:
    """
    呼叫 LLM 進行邊界辨識。
    嚴格遵循「關閉思考模式」、「限制 System Prompt」及「Regex 容錯」。
    """
    global FALLBACK_COUNT
    if not OPENROUTER_API_KEY:
        logger.warning("No OPENROUTER_API_KEY found, fallback to empty split.")
        return []

    # 將微型片段加上標籤化處理
    tagged_text = ""
    for i, block in enumerate(text_blocks):
        tagged_text += f"<chunk_{i}>\n{block}\n</chunk_{i}>\n\n"

    system_prompt = """你是一個只會輸出數字序列的 API 伺服器，不具備對話能力。
任務：找出古文與評注的最佳語義段落切分點。
請閱讀傳入的標籤化文本（如 <chunk_0>），決定在哪幾個 chunk 之後切斷最適合語義完整性。
規則：
1. 絕對不要解釋你的理由。
2. 絕對不要輸出任何開場白或結語（如「好的」、「以下是」）。
3. 你的輸出必須且只能是 "split_after: 數字, 數字" 的格式。"""

    user_prompt = f"請提供切分點，文本如下：\n\n{tagged_text}"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        # Custom header to ensure thinking mode isn't accidentally enforced
        "X-Title": "Hybrid-Chunking-Pipeline"
    }

    # 使用極端的 low temperature，並確保沒啟用思維鏈 (No max_thinking_tokens or similar)
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 100,  # 極度限制 token 數量，防堵模型作怪
        "top_p": 0.1,
        # 防禦性禁用 reasoning，避免 OpenRouter 意外啟動思維鏈
        "reasoning": {"effort": "none"}
    }

    try:
        response_text = await call_llm_async(session, rate_limiter, payload, headers)
        logger.debug(f"LLM Raw Output: {response_text}")

        # 使用 Regex 取出數字，支援多種常見變體
        patterns = [
            r'split_after[：:]\s*([\d,、\s]+)',
            r'\[([\d,\s]+)\]',
            r'^([\d,\s]+)$',
        ]
        
        match = None
        for pattern in patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                break

        if match:
            # 替換頓號為逗號，並完美萃取成 Python List
            cleaned_numbers = match.group(1).replace('、', ',')
            split_indices = [int(idx.strip()) for idx in cleaned_numbers.split(',') if idx.strip().isdigit()]
            return split_indices
        else:
            logger.warning(f"LLM output unparseable, falling back to rule-based: {response_text}")
            FALLBACK_COUNT += 1
            return []

    except Exception as e:
        logger.error(f"Unexpected error in call_llm_boundary_detection: {e}")
        FALLBACK_COUNT += 1
        return []


def tier_1_markdown_split(markdown_text: str) -> List[Dict[str, Any]]:
    """第一層：以 Markdown 標頭進行物理切塊"""
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False  # 保留標題在 chunk 內文中
    )
    md_header_splits = markdown_splitter.split_text(markdown_text)
    
    results = []
    for split in md_header_splits:
        results.append({
            "content": split.page_content,
            "metadata": split.metadata
        })
    return results


async def tier_2_llm_boundary_split(tier1_chunk: str, session: aiohttp.ClientSession, rate_limiter: LeakyBucketLimiter = None, max_chunk_size: int = 800) -> List[str]:
    """第二層：如果段落仍過長，則發動 LLM 定位切分點"""
    # 如果段落長度已經符合要求，則直接放行
    if len(tier1_chunk) <= max_chunk_size:
        return [tier1_chunk]

    # 使用 Rule-based 將長文分割為 ~100 字微型片段
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=100,
        chunk_overlap=20,  # 提升重疊字數，給予LLM更好的上下文判斷空間
        separators=["\n\n", "\n", "。", "！", "？", " ", ""]
    )
    
    micro_chunks = text_splitter.split_text(tier1_chunk)
    
    # 避免切太細導致 API 大爆炸
    if len(micro_chunks) < 2:
        return micro_chunks

    # 向 LLM 查詢切分點
    split_indices = await call_llm_boundary_detection(micro_chunks, session, rate_limiter)
    
    if not split_indices:
        # Fallback：直接均分或按照原始微型片段每 4 個合併
        fallback_chunks = []
        temp_str = ""
        for i, micro in enumerate(micro_chunks):
            temp_str += micro + "\n"
            if len(temp_str) > max_chunk_size * 0.8:
                fallback_chunks.append(temp_str.strip())
                temp_str = ""
        if temp_str:
            fallback_chunks.append(temp_str.strip())
        return fallback_chunks

    # 依據 LLM 建議的 Index 進行合併
    final_chunks = []
    current_chunk = ""
    for i, micro in enumerate(micro_chunks):
        current_chunk += micro + "\n"
        if i in split_indices:
            final_chunks.append(current_chunk.strip())
            current_chunk = ""
            
    if current_chunk.strip():
        final_chunks.append(current_chunk.strip())

    return final_chunks


async def call_llm_contextual_prefixing(chunk_text: str, document_text: str, session: aiohttp.ClientSession, rate_limiter: LeakyBucketLimiter = None) -> str:
    """呼叫 LLM 進行 Contextual Retrieval 的前綴生成"""
    if not OPENROUTER_API_KEY:
        return ""

    system_prompt = """你是一個精準的文本摘要助手。你的任務是閱讀整篇文件，並為其中一個特定的段落提供簡短、精準的「定位描述」，用於提升搜尋引擎的檢索準確度。
請用繁體中文回覆，長度請盡量保持在 30-50 字以內，不要輸出任何開場白。"""

    user_prompt = f"""<document>
{document_text[:3000]}... (截斷) 
</document>

<chunk>
{chunk_text}
</chunk>

請為上述 <chunk> 寫一段簡短的上下文敘述，說明它在整份文件中的位置與作用。"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "X-Title": "Hybrid-Chunking-Pipeline"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 150,
        "top_p": 0.1,
        "reasoning": {"effort": "none"}
    }

    try:
        response_text = await call_llm_async(session, rate_limiter, payload, headers)
        return response_text.strip()
    except Exception as e:
        logger.error(f"Error calling contextual prefixing LLM: {e}")
            
    return ""


async def tier_3_contextual_prefixing(text: str, metadata: dict, document_text: str = "", use_llm_context: bool = False, session: aiohttp.ClientSession = None, rate_limiter: LeakyBucketLimiter = None) -> str:
    """第三層：為 Chunk 掛載 Metadata 以強化檢索精確度"""
    context_parts = []
    
    # 兼容 Markdown Headers
    headers = [v for k, v in metadata.items() if k.startswith("Header")]
    if headers:
        context_parts.extend(headers)
        
    # 兼容 JSONL schema 的 hierarchy
    if "breadcrumbs" in metadata:
        context_parts.append(metadata["breadcrumbs"])
    elif "volume" in metadata or "chapter_title" in metadata:
        vol = metadata.get("volume", "")
        chap = metadata.get("chapter_title", "")
        context_parts.append(f"{vol} {chap}".strip())
        
    prefix = ""
    # LLM 動態摘要模式
    if use_llm_context and document_text and session:
        llm_context = await call_llm_contextual_prefixing(text, document_text, session, rate_limiter)
        if llm_context:
            prefix += f"【AI 動態脈絡】：{llm_context}\n"
            
    if context_parts:
        context_str = " > ".join(dict.fromkeys(context_parts)) # deduplicate
        prefix += f"此段落的章節脈絡為：{context_str}。\n\n"
        
    return prefix + text if prefix else text


async def run_hybrid_chunking_pipeline(markdown_text: str, session: aiohttp.ClientSession, rate_limiter: LeakyBucketLimiter = None, external_metadata: dict = None, use_llm_context: bool = False) -> List[Dict[str, Any]]:
    """執行完整三層混合切塊流程"""
    if external_metadata is None:
        external_metadata = {}

    doc_id = external_metadata.get("doc_id", "unknown_doc")
    source_file = external_metadata.get("source", "unknown_source")

    final_processed_chunks = []
    
    # Tier 1
    tier1_results = tier_1_markdown_split(markdown_text)
    
    for t1 in tier1_results:
        # Tier 2
        tier2_chunks = await tier_2_llm_boundary_split(t1["content"], session, rate_limiter)
        
        # Tier 3 & Combine Metadata
        for t2_content in tier2_chunks:
            combined_meta = {**external_metadata, **t1["metadata"]}
            enriched_text = await tier_3_contextual_prefixing(t2_content, combined_meta, document_text=markdown_text, use_llm_context=use_llm_context, session=session, rate_limiter=rate_limiter)
            
            # char_offset_start rough calculation
            char_offset = markdown_text.find(t2_content[:50]) if len(t2_content) >= 50 else markdown_text.find(t2_content)
            if char_offset == -1:
                char_offset = 0
            
            final_processed_chunks.append({
                "page_content": enriched_text,
                "metadata": combined_meta,
                "raw_content_offset": char_offset,  # temporary to keep track
            })
            
    # Post-process indexing
    total_chunks = len(final_processed_chunks)
    for i, chunk in enumerate(final_processed_chunks):
        chunk["metadata"]["chunk_id"] = f"{doc_id}_chunk_{i}"
        chunk["metadata"]["doc_id"] = doc_id
        chunk["metadata"]["source_file"] = source_file
        chunk["metadata"]["chunk_index"] = i
        chunk["metadata"]["total_chunks"] = total_chunks
        chunk["metadata"]["char_offset_start"] = chunk.pop("raw_content_offset")
            
    return final_processed_chunks


if __name__ == "__main__":
    # 簡單的測試範例
    sample_text = """# 第一回 甄士隱夢幻識通靈 賈雨村風塵懷閨秀
## 蔡義江評注
此段為第一回重要之處。列位看官：你道此書從何而來？說起根由雖近荒唐，細按則深有趣味。
待在下將此來歷註明，方使閱者了然不惑。
原來女媧氏煉石補天之時，於大荒山無稽崖練成高經十二丈，方經二十四丈頑石三萬六千五百零一塊。
媧皇氏只用了三萬六千五百塊，只單單剩了一塊未用，便棄在此山青埂峰下。
誰知此石自經煅煉之後，靈性已通，因見眾石俱得補天，獨自己無材不堪入選，遂自怨自嘆，日夜悲號慚愧。
"""
    
    logger.info("Starting Hybrid Chunking Pipeline Test...")
    result_chunks = run_hybrid_chunking_pipeline(sample_text, external_metadata={"source": "hongloumeng.txt"})
    
    for idx, c in enumerate(result_chunks):
        logger.info(f"Chunk {idx}:")
        logger.info(f"Metadata: {c['metadata']}")
        logger.info(f"Content:\n{c['page_content']}")
        logger.info("-" * 40)
