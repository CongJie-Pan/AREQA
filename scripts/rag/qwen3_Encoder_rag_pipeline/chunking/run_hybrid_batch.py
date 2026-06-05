#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch Runner for Hybrid Chunking Pipeline (Async + Checkpoint + Rate Limit)
========================================================================
"""

import os
import sys
import json
import logging
import argparse
import asyncio
import aiohttp
import aiofiles
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
from scripts.rag.qwen3_Encoder_rag_pipeline.chunking.hybrid_chunking_core import run_hybrid_chunking_pipeline, LeakyBucketLimiter

# ============== 新增 Rich 終端顯示 ==============
from rich.logging import RichHandler
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from dotenv import load_dotenv

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("hybrid_batch")

# 確保讀取本地 .env
ENV_PATH = PROJECT_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=True)
# ==============================================

# Get context-generating model name from config for dynamic naming
try:
    from scripts.rag.qwen3_Encoder_rag_pipeline.chunking.hybrid_chunking_core import MODEL_NAME
except ImportError:
    MODEL_NAME = "qwen_chunk_agent"

# Generate dynamic suffix once at module load
_safe_model_name = MODEL_NAME.replace("/", "_").replace("-", "_")
_timestamp = datetime.now().strftime("%Y%m%d")
CHUNK_FILE_SUFFIX = f"{_safe_model_name}_{_timestamp}"

SOURCE_DIR = PROJECT_ROOT / "data" / "rag" / "source"
OUTPUT_DIR = PROJECT_ROOT / "data" / "rag" / "chunks"
CHECKPOINT_FILE = OUTPUT_DIR / ".checkpoint_manifest.json"
OUTPUT_JSONL = OUTPUT_DIR / f"hybrid_smart_chunks_{CHUNK_FILE_SUFFIX}.jsonl"
FINAL_OUTPUT_JSON = OUTPUT_DIR / f"hybrid_smart_chunks_{CHUNK_FILE_SUFFIX}.json"

class CheckpointManager:
    def __init__(self):
        self.processed = self._load_manifest()

    def _load_manifest(self) -> set:
        if CHECKPOINT_FILE.exists():
            try:
                with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                    return set(json.load(f).get("completed_files", []))
            except Exception:
                pass
        return set()

    def is_processed(self, file_name: str) -> bool:
        return file_name in self.processed

    async def save_chunks(self, chunks: list, file_name: str):
        # 逐筆追加至 JSONL（不是覆寫整個 JSON）
        async with aiofiles.open(OUTPUT_JSONL, mode='a', encoding='utf-8') as f:
            for chunk in chunks:
                await f.write(json.dumps(chunk, ensure_ascii=False) + '\n')

        # 更新 manifest
        self.processed.add(file_name)
        with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "completed_files": list(self.processed),
                "last_updated": datetime.now().isoformat(),
                "total_processed": len(self.processed)
            }, f, indent=2, ensure_ascii=False)


async def process_single_file(file_path: Path, session: aiohttp.ClientSession, rate_limiter: LeakyBucketLimiter, use_llm_context: bool = False) -> List[Dict[str, Any]]:
    # logger.info(f"Processing file: {file_path.name}")
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 針對 .txt 直接作處理，若是 .jsonl / .json 需先 parser 再進行處裡
    all_chunks = []
    
    if file_path.suffix == '.jsonl':
        lines = content.strip().split('\n')
        for i, line in enumerate(lines):
            if not line.strip(): continue
            try:
                data = json.loads(line)
                nodes = data.get("nodes", [{}])
                for node in nodes:
                    text = node.get("content", {}).get("text", "") or data.get("content", {}).get("text", "")
                    if not text:
                        continue
                    
                    meta = node.get("hierarchy", {}) or data.get("hierarchy", {})
                    meta["source"] = file_path.name
                    meta["line_idx"] = i
                    meta["doc_id"] = data.get("id") or data.get("doc_id") or f"{file_path.stem}_line_{i}"
                    
                    chunks = await run_hybrid_chunking_pipeline(text, session, rate_limiter, external_metadata=meta, use_llm_context=use_llm_context)
                    all_chunks.extend(chunks)
                    
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSONL in {file_path} at line {i}")
                continue
                
    elif file_path.suffix == '.json':
        try:
            data_list = json.loads(content)
            if isinstance(data_list, dict):
                data_list = [data_list]
            for i, item in enumerate(data_list):
                # 格式 B 檢測 - qaSynthesisArticle.json 結構 (沒有 nodes, 直屬 content 字串)
                if "nodes" not in item and "content" in item and isinstance(item["content"], str):
                    text = item["content"]
                    meta = {
                        "source": file_path.name,
                        "title": item.get("title", ""),
                        "category": item.get("category", ""),
                        "item_idx": i,
                        "doc_id": item.get("id") or item.get("doc_id") or f"{file_path.stem}_item_{i}"
                    }
                    chunks = await run_hybrid_chunking_pipeline(text, session, rate_limiter, external_metadata=meta, use_llm_context=use_llm_context)
                    all_chunks.extend(chunks)
                    continue

                nodes = item.get("nodes", [{}])
                for node in nodes:
                    text = node.get("content", {}).get("text", "") or item.get("content", {}).get("text", "")
                    if not text:
                        continue
                    
                    meta = node.get("hierarchy", {}) or item.get("hierarchy", {})
                    meta["source"] = file_path.name
                    meta["item_idx"] = i
                    meta["doc_id"] = item.get("id") or item.get("doc_id") or f"{file_path.stem}_item_{i}"
                    
                    chunks = await run_hybrid_chunking_pipeline(text, session, rate_limiter, external_metadata=meta, use_llm_context=use_llm_context)
                    all_chunks.extend(chunks)
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON in {file_path}")

    else: # txt
        chunks = await run_hybrid_chunking_pipeline(content, session, rate_limiter, external_metadata={"source": file_path.name, "doc_id": file_path.stem}, use_llm_context=use_llm_context)
        all_chunks.extend(chunks)
        
    return all_chunks


async def process_with_checkpoint(tf: Path, session: aiohttp.ClientSession, rate_limiter: LeakyBucketLimiter, semaphore: asyncio.Semaphore, ckpt: CheckpointManager, progress, task_id, use_llm_context: bool):
    async with semaphore:
        try:
            chunks = await process_single_file(tf, session, rate_limiter, use_llm_context)
            await ckpt.save_chunks(chunks, tf.name)
            progress.advance(task_id)
        except Exception as e:
            logger.error(f"❌ Failed {tf.name}: {e}")
            progress.advance(task_id) # Still advance to avoid blocking progress bar

async def main_async():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Limit number of files to process")
    parser.add_argument("--retry", action="store_true", help="Force restart (clear checkpoints and outputs)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    if args.retry:
        logger.info("Retry flag detected: Clearing previous checkpoints and output JSONL.")
        if CHECKPOINT_FILE.exists():
            CHECKPOINT_FILE.unlink()
        if OUTPUT_JSONL.exists():
            OUTPUT_JSONL.unlink()
        if FINAL_OUTPUT_JSON.exists():
            FINAL_OUTPUT_JSON.unlink()

    target_files = []
    target_files.extend(list(SOURCE_DIR.rglob("*.txt")))
    target_files.extend(list(SOURCE_DIR.rglob("*.jsonl")))
    target_files.extend(list(SOURCE_DIR.rglob("*.json")))

    if args.limit:
        target_files = target_files[:args.limit]
        logger.info(f"Limiting to {args.limit} files for testing.")

    if not target_files:
        logger.warning(f"No source files found in {SOURCE_DIR}")
        return

    logger.info(f"Found {len(target_files)} files to process.")
    
    ckpt = CheckpointManager()
    rate_limiter = LeakyBucketLimiter(rate=0.3)  # OpenRouter: ~18 RPM safe limit
    semaphore = asyncio.Semaphore(5)  # 最多 5 個文件同時處理
    
    # 可設定為 True 啟用 LLM Contextual Prefixing (注意 API 成本與速率)
    use_llm_context_mode = False

    tasks = []
    
    # Filter files that are already completed
    pending_files = []
    for tf in target_files:
        if "quarantine" in str(tf):
            logger.info(f"Skipping quarantined file: {tf.name}")
            continue
        if ckpt.is_processed(tf.name):
            # logger.info(f"⏭️ Skipping already processed: {tf.name}")
            continue
        pending_files.append(tf)
        
    logger.info(f"Files already processed (skipped): {len(target_files) - len(pending_files)}")
    logger.info(f"Files to process in this run: {len(pending_files)}")

    if pending_files:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task_id = progress.add_task("[cyan]Processing pending documents...", total=len(pending_files))
            
            async with aiohttp.ClientSession() as session:
                for tf in pending_files:
                    tasks.append(
                        asyncio.create_task(
                            process_with_checkpoint(tf, session, rate_limiter, semaphore, ckpt, progress, task_id, use_llm_context_mode)
                        )
                    )
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

    # 最終階段：從 JSONL 讀取所有資料，建構出完整的 json 供後續腳本使用
    logger.info("Building final JSON from JSONL chunks...")
    all_final_chunks = []
    if OUTPUT_JSONL.exists():
        with open(OUTPUT_JSONL, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.strip():
                    try:
                        all_final_chunks.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to decode a line in JSONL: {e}")
                    
    # 儲存完整的 json (確保相容性)
    with open(FINAL_OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_final_chunks, f, ensure_ascii=False, indent=2)
        
    logger.info(f"Finished. Total chunks ready for downstream: {len(all_final_chunks)}")
    logger.info(f"Saved unified chunks to: {FINAL_OUTPUT_JSON}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_async())