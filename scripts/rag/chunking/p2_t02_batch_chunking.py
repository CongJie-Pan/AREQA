#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2-T02: Batch LLM-based Chunking Script

This script processes all source documents through the SmartChunker to create
semantically meaningful chunks using Kimi K2 API.

Features:
- Batch processing with progress tracking
- Checkpoint mechanism (saves every N documents)
- Error recovery and retry logic
- Detailed logging and statistics
- Dry-run mode for testing

Usage:
    # Full run
    python scripts/rag/chunking/p2_t02_batch_chunking.py
    
    # Dry run (no API calls)
    python scripts/rag/chunking/p2_t02_batch_chunking.py --dry-run
    
    # Resume from checkpoint
    python scripts/rag/chunking/p2_t02_batch_chunking.py --resume
    
    # Process specific source
    python scripts/rag/chunking/p2_t02_batch_chunking.py --source wiki

Author: GitHub Copilot
Date: 2026-02-01
"""

# ===== MUST BE BEFORE ANY OTHER IMPORTS =====
# Suppress LiteLLM stdout "Provider List" messages
import os
import sys
os.environ["LITELLM_LOG"] = "ERROR"
os.environ["LITELLM_PRINT_VERBOSE"] = "False"

# Monkey-patch to suppress litellm print statements (including empty lines)
class _SuppressLiteLLMPrint:
    """Suppress 'Provider List:' messages and empty lines from litellm."""
    _patched = False
    
    @classmethod
    def suppress_provider_list(cls):
        if cls._patched:
            return
        import builtins
        _original_print = builtins.print
        def _filtered_print(*args, **kwargs):
            # Suppress empty prints or prints with only whitespace
            if not args or (len(args) == 1 and (args[0] == "" or (isinstance(args[0], str) and args[0].strip() == ""))):
                return
            # Suppress Provider List messages
            if args and isinstance(args[0], str) and "Provider List:" in args[0]:
                return
            return _original_print(*args, **kwargs)
        builtins.print = _filtered_print
        cls._patched = True

_SuppressLiteLLMPrint.suppress_provider_list()
# =============================================

import argparse
import json
import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from threading import Lock

# Rich imports for beautiful console output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
    from rich.live import Live
    from rich import print as rprint
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    Console = None
    rprint = print

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# Suppress verbose third-party library logs
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("litellm").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

from scripts.rag.chunking.config import (
    RAG_SOURCE_DIR,
    RAG_CHUNKS_DIR,
    API_RATE_LIMIT_DELAY,
    CHECKPOINT_INTERVAL,
)
from scripts.rag.chunking.p2_t01_llm_chunking import SmartChunker

# Import API client module (consistent with p2_t12_qa_generator pattern)
try:
    from scripts.rag.chunking.api_client import api_client
    HAS_API_CLIENT = True
except ImportError:
    HAS_API_CLIENT = False
    api_client = None

# Configure logging
def setup_logging():
    """Configure logging with lazy directory creation."""
    handlers = [logging.StreamHandler()]
    
    # Only add file handler if we can create the directory
    log_dir = PROJECT_ROOT / "output" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"batch_chunking_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except (OSError, PermissionError):
        pass  # Skip file logging if directory cannot be created
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=handlers
    )
    return logging.getLogger(__name__)

logger = setup_logging()


# ==============================================================================
# Failed Chunks Detection and Cleanup
# ==============================================================================

def detect_and_clean_failed_chunks(console=None) -> list[str]:
    """
    偵測有問題的 chunks（空 keywords、空 summary、被截斷的 text）
    並自動清理，準備重新處理。
    
    Args:
        console: Rich console for output (optional)
    
    Returns:
        List of problematic document IDs that need reprocessing
    """
    output_file = RAG_CHUNKS_DIR / "kimik2_0905_chunking.json"
    checkpoint_file = RAG_CHUNKS_DIR / "checkpoints" / "chunks_checkpoint.json"
    progress_file = RAG_CHUNKS_DIR / "checkpoints" / "batch_progress.json"
    
    # 檢查文件是否存在
    if not output_file.exists():
        if console and HAS_RICH:
            console.print(f"[yellow]⚠️ 輸出文件不存在：{output_file}[/yellow]")
        else:
            logger.warning(f"輸出文件不存在：{output_file}")
        return []
    
    # 載入 chunks
    try:
        with open(output_file, encoding='utf-8') as f:
            all_chunks = json.load(f)
    except Exception as e:
        if console and HAS_RICH:
            console.print(f"[red]❌ 無法讀取輸出文件：{e}[/red]")
        else:
            logger.error(f"無法讀取輸出文件：{e}")
        return []
    
    if not all_chunks:
        if console and HAS_RICH:
            console.print("[yellow]輸出文件是空的[/yellow]")
        else:
            logger.warning("輸出文件是空的")
        return []
    
    # 偵測有問題的 chunks
    problem_chunks = []
    
    for chunk in all_chunks:
        is_problematic = False
        reasons = []
        
        # 檢查 1: keywords 為空
        if not chunk.get('keywords'):
            is_problematic = True
            reasons.append("空 keywords")
        
        # 檢查 2: summary 為空
        if not chunk.get('summary'):
            is_problematic = True
            reasons.append("空 summary")
        
        # 檢查 3: text 太短（可能被截斷）
        text = chunk.get('text', '')
        if len(text) < 10:
            is_problematic = True
            reasons.append(f"text 太短 ({len(text)} 字)")
        
        # 檢查 4: text 結尾異常（引號未閉合，可能被截斷）
        if text and text[-1] in '「『':
            is_problematic = True
            reasons.append("text 結尾為開引號")
        
        if is_problematic:
            problem_chunks.append({
                'chunk': chunk,
                'reasons': reasons
            })
    
    if not problem_chunks:
        return []
    
    # 提取問題文檔 ID
    problem_doc_ids = sorted(set(pc['chunk']['doc_id'] for pc in problem_chunks))
    
    # 顯示偵測結果
    if console and HAS_RICH:
        console.print(f"[bold red]🔍 偵測到 {len(problem_chunks)} 個有問題的 chunk[/bold red]")
        console.print(f"[yellow]涉及 {len(problem_doc_ids)} 個文檔[/yellow]\n")
        
        # 顯示前 10 個問題
        problem_table = Table(title="問題分塊清單（前 10 個）", show_header=True, header_style="bold yellow")
        problem_table.add_column("Chunk ID", style="cyan")
        problem_table.add_column("問題", style="red")
        problem_table.add_column("Text 長度", justify="right", style="yellow")
        
        for pc in problem_chunks[:10]:
            chunk = pc['chunk']
            reasons_str = ", ".join(pc['reasons'])
            problem_table.add_row(
                chunk['chunk_id'],
                reasons_str,
                str(len(chunk.get('text', '')))
            )
        
        console.print(problem_table)
        
        if len(problem_chunks) > 10:
            console.print(f"\n[dim]... 還有 {len(problem_chunks) - 10} 個問題未顯示[/dim]")
    else:
        logger.info(f"偵測到 {len(problem_chunks)} 個有問題的 chunk")
        logger.info(f"涉及 {len(problem_doc_ids)} 個文檔")
    
    # 詢問是否清理
    if console and HAS_RICH:
        from rich.prompt import Confirm
        should_clean = Confirm.ask(
            f"\n[bold yellow]是否要清理這些文檔並準備重新處理？[/bold yellow]",
            default=True
        )
    else:
        # 非互動模式，自動清理
        should_clean = True
    
    if not should_clean:
        if console and HAS_RICH:
            console.print("[yellow]取消清理操作[/yellow]")
        return []
    
    # 執行清理
    if console and HAS_RICH:
        console.print(f"\n[cyan]🧹 清理中...[/cyan]")
    else:
        logger.info("開始清理問題文檔...")
    
    # 1. 從 chunks 中移除這些文檔的所有 chunk
    original_chunk_count = len(all_chunks)
    cleaned_chunks = [c for c in all_chunks if c['doc_id'] not in problem_doc_ids]
    removed_chunk_count = original_chunk_count - len(cleaned_chunks)
    
    # 保存清理後的 chunks
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cleaned_chunks, f, ensure_ascii=False, indent=2)
    
    if console and HAS_RICH:
        console.print(f"[green]✅ 從主文件移除 {removed_chunk_count} 個 chunk[/green]")
    else:
        logger.info(f"從主文件移除 {removed_chunk_count} 個 chunk")
    
    # 2. 同步更新 checkpoint
    if checkpoint_file.exists():
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(cleaned_chunks, f, ensure_ascii=False, indent=2)
        
        if console and HAS_RICH:
            console.print(f"[green]✅ 已同步更新 checkpoint[/green]")
    
    # 3. 從 progress 中移除這些文檔 ID
    if progress_file.exists():
        with open(progress_file, encoding='utf-8') as f:
            progress = json.load(f)
        
        original_count = len(progress['processed_ids'])
        progress['processed_ids'] = [
            id for id in progress['processed_ids'] 
            if id not in problem_doc_ids
        ]
        removed_id_count = original_count - len(progress['processed_ids'])
        
        # 更新統計數據
        progress['processed_documents'] -= removed_id_count
        progress['successful_documents'] = max(0, progress['successful_documents'] - removed_id_count)
        progress['total_chunks_generated'] = len(cleaned_chunks)
        
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        
        if console and HAS_RICH:
            console.print(f"[green]✅ 從 progress 移除 {removed_id_count} 個文檔 ID[/green]")
        else:
            logger.info(f"從 progress 移除 {removed_id_count} 個文檔 ID")
    
    # 顯示待處理文檔清單
    if console and HAS_RICH:
        console.print(f"\n[bold cyan]📄 待重新處理的文檔 ({len(problem_doc_ids)}):[/bold cyan]")
        for idx, doc_id in enumerate(problem_doc_ids[:20], 1):
            affected_count = len([pc for pc in problem_chunks if pc['chunk']['doc_id'] == doc_id])
            console.print(f"  {idx:2d}. {doc_id:30s} ({affected_count} 個問題 chunk)")
        
        if len(problem_doc_ids) > 20:
            console.print(f"\n[dim]... 還有 {len(problem_doc_ids) - 20} 個文檔未顯示[/dim]")
    else:
        logger.info(f"待重新處理的文檔：{problem_doc_ids[:10]}")
    
    return problem_doc_ids


# ==============================================================================
# Signal Handler for Graceful Shutdown
# ==============================================================================

class GracefulShutdown:
    """處理 Ctrl+C 信號，確保資料保存後才退出"""
    shutdown_requested = False
    
    @classmethod
    def signal_handler(cls, signum, frame):
        """信號處理函數"""
        if cls.shutdown_requested:
            # 第二次 Ctrl+C：強制退出
            logger.warning("\n\n⚠️ 強制終止！資料可能未保存。")
            sys.exit(1)
        else:
            # 第一次 Ctrl+C：標記優雅退出
            cls.shutdown_requested = True
            logger.warning("\n\n🛑 收到中斷信號 (Ctrl+C)，正在保存資料...")
            logger.warning("   💡 再按一次 Ctrl+C 可強制終止（不建議）\n")
    
    @classmethod
    def setup(cls):
        """註冊信號處理器"""
        signal.signal(signal.SIGINT, cls.signal_handler)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, cls.signal_handler)


# ==============================================================================
# Data Classes
# ==============================================================================

@dataclass
class DocumentInfo:
    """Information about a source document."""
    file_path: Path
    source_type: str
    doc_id: str
    title: str
    content: str
    metadata: dict = field(default_factory=dict)


@dataclass
class ProcessingResult:
    """Result of processing a single document."""
    doc_id: str
    source_type: str
    success: bool = False  # Default to False, set to True on success
    chunks: list = field(default_factory=list)
    error_message: str = ""
    processing_time: float = 0.0
    api_calls: int = 0
    quality_score: float = 0.0
    used_fallback: bool = False


@dataclass
class BatchProgress:
    """Progress tracking for batch processing."""
    total_documents: int = 0
    processed_documents: int = 0
    successful_documents: int = 0
    failed_documents: int = 0
    total_chunks_generated: int = 0
    total_api_calls: int = 0
    total_processing_time: float = 0.0
    start_time: str = ""
    last_checkpoint: str = ""
    processed_ids: list = field(default_factory=list)
    failed_ids: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "BatchProgress":
        """Create from dictionary."""
        return cls(**data)


# ==============================================================================
# Source Document Loader
# ==============================================================================

class SourceDocumentLoader:
    """
    Loads source documents from various file formats.
    
    Supported formats:
    - JSON (list of documents)
    - JSONL (one document per line)
    """
    
    def __init__(self, source_dir: Path):
        """
        Initialize the loader.
        
        Args:
            source_dir: Path to the source directory
        """
        self.source_dir = Path(source_dir)
        
        # Source type mapping based on directory structure
        self.source_type_mapping = {
            "classical_texts": "經典",
            "exam_materials": "考試",
            "redChamber_text": "紅樓夢",
            "scholarly_analysis": "學術分析",
            "structured_contents": "結構化內容",
            "wiki": "維基",
        }
    
    def validate_source_files(self, console=None) -> tuple[bool, list[dict]]:
        """
        驗證所有來源文件的 JSON 格式。
        
        Returns:
            (is_valid, error_list): 是否全部通過驗證，以及錯誤清單
        """
        source_files = self.discover_source_files()
        errors = []
        
        if console and HAS_RICH:
            console.print(f"\n[bold cyan]🔍 驗證 {len(source_files)} 個來源文件的 JSON 格式...[/bold cyan]")
        else:
            logger.info(f"驗證 {len(source_files)} 個來源文件的 JSON 格式...")
        
        for file_path in source_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    if file_path.suffix == ".jsonl":
                        # Validate JSONL
                        for line_num, line in enumerate(f, 1):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                json.loads(line)
                            except json.JSONDecodeError as e:
                                errors.append({
                                    "file": str(file_path.relative_to(self.source_dir)),
                                    "line": line_num,
                                    "error": str(e),
                                    "content": line[:100] + "..." if len(line) > 100 else line
                                })
                    elif file_path.suffix == ".json":
                        # Validate JSON
                        try:
                            json.load(f)
                        except json.JSONDecodeError as e:
                            errors.append({
                                "file": str(file_path.relative_to(self.source_dir)),
                                "line": e.lineno if hasattr(e, 'lineno') else 0,
                                "error": str(e),
                                "content": ""
                            })
            except Exception as e:
                errors.append({
                    "file": str(file_path.relative_to(self.source_dir)),
                    "line": 0,
                    "error": f"無法讀取檔案: {e}",
                    "content": ""
                })
        
        if errors:
            if console and HAS_RICH:
                console.print(f"\n[bold red]❌ 發現 {len(errors)} 個 JSON 格式錯誤：[/bold red]\n")
                
                error_table = Table(title="JSON 格式錯誤清單", show_header=True, header_style="bold red")
                error_table.add_column("檔案", style="cyan")
                error_table.add_column("行號", justify="right", style="yellow")
                error_table.add_column("錯誤訊息", style="red")
                
                for err in errors[:20]:  # Show first 20 errors
                    error_table.add_row(
                        err["file"],
                        str(err["line"]) if err["line"] > 0 else "N/A",
                        err["error"][:80]
                    )
                
                console.print(error_table)
                
                if len(errors) > 20:
                    console.print(f"\n[yellow]... 還有 {len(errors) - 20} 個錯誤未顯示[/yellow]")
            else:
                logger.error(f"發現 {len(errors)} 個 JSON 格式錯誤")
                for err in errors[:10]:
                    logger.error(f"{err['file']}:{err['line']} - {err['error']}")
            
            return False, errors
        
        if console and HAS_RICH:
            console.print(f"[bold green]✅ 所有來源文件 JSON 格式驗證通過[/bold green]")
        else:
            logger.info("所有來源文件 JSON 格式驗證通過")
        
        return True, []
    
    def discover_source_files(self) -> list[Path]:
        """
        Discover all source files in the source directory.
        
        Returns:
            List of source file paths
        """
        source_files = []
        
        for subdir in self.source_dir.iterdir():
            if subdir.is_dir():
                # Find JSON and JSONL files
                source_files.extend(subdir.glob("*.json"))
                source_files.extend(subdir.glob("*.jsonl"))
        
        return sorted(source_files)
    
    def load_documents_from_file(self, file_path: Path) -> list[DocumentInfo]:
        """
        Load documents from a single file.
        
        Args:
            file_path: Path to the source file
            
        Returns:
            List of DocumentInfo objects
        """
        documents = []
        
        # Determine source type from parent directory
        parent_dir = file_path.parent.name
        source_type = self.source_type_mapping.get(parent_dir, "未知")
        
        try:
            if file_path.suffix == ".jsonl":
                documents = self._load_jsonl(file_path, source_type)
            elif file_path.suffix == ".json":
                documents = self._load_json(file_path, source_type)
            else:
                logger.warning(f"Unsupported file format: {file_path}")
        except Exception as e:
            logger.error(f"Error loading {file_path}: {e}")
        
        return documents
    
    def _load_jsonl(self, file_path: Path, source_type: str) -> list[DocumentInfo]:
        """Load documents from JSONL file."""
        documents = []
        
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    data = json.loads(line)
                    doc = self._parse_document(data, file_path, source_type, line_num)
                    if doc:
                        documents.append(doc)
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON decode error in {file_path} line {line_num}: {e}")
        
        return documents
    
    def _load_json(self, file_path: Path, source_type: str) -> list[DocumentInfo]:
        """Load documents from JSON file."""
        documents = []
        
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle both list and dict formats
        if isinstance(data, list):
            for idx, item in enumerate(data, 1):
                doc = self._parse_document(item, file_path, source_type, idx)
                if doc:
                    documents.append(doc)
        elif isinstance(data, dict):
            # Single document or nested structure
            if "content" in data or "text" in data:
                doc = self._parse_document(data, file_path, source_type, 1)
                if doc:
                    documents.append(doc)
            else:
                # Try to extract documents from nested structure
                for key, value in data.items():
                    if isinstance(value, dict):
                        doc = self._parse_document(value, file_path, source_type, key)
                        if doc:
                            documents.append(doc)
        
        return documents
    
    def _parse_document(
        self,
        data: dict,
        file_path: Path,
        source_type: str,
        index: Any
    ) -> Optional[DocumentInfo]:
        """
        Parse a single document from raw data.
        
        Args:
            data: Raw document data
            file_path: Source file path
            source_type: Type of source
            index: Document index or key
            
        Returns:
            DocumentInfo object or None if invalid
        """
        # Handle nested structure with "nodes" array (JSONL format)
        if "nodes" in data and isinstance(data["nodes"], list) and len(data["nodes"]) > 0:
            # Extract content from first node's content.text
            first_node = data["nodes"][0]
            if "content" in first_node and isinstance(first_node["content"], dict):
                content = first_node["content"].get("text", "")
            else:
                content = ""
            
            # If content is too short, try to get from indexing_augmentation
            if len(content) < 50 and "indexing_augmentation" in first_node:
                aug = first_node["indexing_augmentation"]
                if isinstance(aug, dict):
                    # Try modern_translation or suggested_queries
                    alt_content = aug.get("modern_translation", "")
                    if not alt_content and "suggested_queries" in aug:
                        alt_content = "\n".join(aug["suggested_queries"])
                    if len(alt_content) >= 20:  # Lower threshold for augmentation content
                        content = alt_content
            
            # Extract title from metadata or hierarchy
            if "metadata" in data and isinstance(data["metadata"], dict):
                title = data["metadata"].get("title", "")
            elif "hierarchy" in first_node and isinstance(first_node["hierarchy"], dict):
                title = first_node["hierarchy"].get("volume", "") or first_node["hierarchy"].get("chapter_title", "")
            else:
                title = ""
            
            # Fallback: use doc_id or file name if title is generic/empty
            if not title or title in ["Unknown Classic", "Unknown", ""]:
                # Try to get chapter_title from hierarchy
                if "hierarchy" in first_node:
                    chapter = first_node["hierarchy"].get("chapter_title", "")
                    if chapter and chapter not in ["Unknown", ""]:
                        title = chapter
                    else:
                        # Use doc_id as last resort
                        title = data.get("doc_id", f"{file_path.stem}_{index}")
            
            # Use original doc_id if available
            doc_id = data.get("doc_id", f"{file_path.stem}_{index}")
            
            # Extract metadata
            metadata = {
                "source_file": str(file_path.relative_to(self.source_dir)),
                "original_id": data.get("doc_id"),
                "doc_type": data.get("doc_type"),
            }
            if "metadata" in data:
                meta = data["metadata"]
                if isinstance(meta, dict):
                    metadata.update({
                        "author": meta.get("author"),
                        "dynasty": meta.get("dynasty"),
                        "category": meta.get("category"),
                    })
        else:
            # Standard flat structure
            content = (
                data.get("content") or 
                data.get("text") or 
                data.get("body") or
                data.get("full_text") or
                ""
            )
            
            # Extract title
            title = (
                data.get("title") or
                data.get("name") or
                data.get("heading") or
                f"Document {index}"
            )
            
            # Generate document ID
            file_stem = file_path.stem
            doc_id = f"{file_stem}_{index}"
            
            # Extract metadata
            metadata = {
                "source_file": str(file_path.relative_to(self.source_dir)),
                "original_id": data.get("id") or data.get("doc_id"),
                "author": data.get("author"),
                "dynasty": data.get("dynasty"),
                "category": data.get("category"),
            }
        
        # Validate content length (minimum 20 characters to include commentary)
        if not content or len(content) < 20:
            return None
        
        # Remove None values from metadata
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        return DocumentInfo(
            file_path=file_path,
            source_type=source_type,
            doc_id=doc_id,
            title=title,
            content=content,
            metadata=metadata
        )
    
    def load_all_documents(
        self,
        source_filter: Optional[str] = None
    ) -> list[DocumentInfo]:
        """
        Load all documents from the source directory.
        
        Args:
            source_filter: Optional filter for specific source type
            
        Returns:
            List of all DocumentInfo objects
        """
        all_documents = []
        source_files = self.discover_source_files()
        
        logger.info(f"Found {len(source_files)} source files")
        
        for file_path in source_files:
            # Apply source filter if specified
            if source_filter:
                parent_dir = file_path.parent.name
                if source_filter.lower() not in parent_dir.lower():
                    continue
            
            documents = self.load_documents_from_file(file_path)
            all_documents.extend(documents)
            logger.info(f"Loaded {len(documents)} documents from {file_path.name}")
        
        logger.info(f"Total documents loaded: {len(all_documents)}")
        return all_documents


# ==============================================================================
# Batch Processor
# ==============================================================================

class BatchChunkingProcessor:
    """
    Batch processor for LLM-based chunking.
    
    Features:
    - Progress tracking
    - Checkpoint mechanism
    - Error recovery
    - Statistics collection
    """
    
    def __init__(
        self,
        chunker: SmartChunker,
        output_dir: Path,
        checkpoint_dir: Optional[Path] = None,
        checkpoint_interval: int = CHECKPOINT_INTERVAL,
        dry_run: bool = False,
        max_workers: int = 3
    ):
        """
        Initialize the batch processor.
        
        Args:
            chunker: SmartChunker instance
            output_dir: Directory for output files
            checkpoint_dir: Directory for checkpoint files
            checkpoint_interval: Save checkpoint every N documents
            dry_run: If True, don't make actual API calls
            max_workers: Number of parallel workers (default: 3)
        """
        self.chunker = chunker
        self.output_dir = Path(output_dir)
        self.checkpoint_dir = checkpoint_dir or (self.output_dir / "checkpoints")
        self.checkpoint_interval = checkpoint_interval
        self.dry_run = dry_run
        self.max_workers = max_workers
        
        # Thread safety
        self.lock = Lock()
        self.checkpoint_interval = checkpoint_interval
        self.dry_run = dry_run
        
        # Ensure directories exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize progress
        self.progress = BatchProgress()
        self.results: list[ProcessingResult] = []
        self.all_chunks: list[dict] = []
    
    def process_document(self, doc: DocumentInfo) -> ProcessingResult:
        """
        Process a single document.
        
        Args:
            doc: Document to process
            
        Returns:
            ProcessingResult object
        """
        start_time = time.time()
        result = ProcessingResult(
            doc_id=doc.doc_id,
            source_type=doc.source_type
        )
        
        try:
            if self.dry_run:
                # Dry run: use fallback chunking
                chunk_results = self.chunker._fallback_chunking(
                    doc.doc_id,
                    doc.title,
                    doc.content
                )
                # Convert ChunkResult objects to dicts
                chunks = [asdict(chunk) for chunk in chunk_results]
                result.used_fallback = True
            else:
                # Real run: use LLM chunking
                doc_result = self.chunker.chunk_document(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    doc_type=doc.source_type,
                    content=doc.content
                )
                # Extract chunks from DocumentChunkingResult
                chunks = [asdict(chunk) for chunk in doc_result.chunks]
                result.used_fallback = not doc_result.success
            
            # Add metadata to chunks
            for idx, chunk in enumerate(chunks):
                chunk["doc_id"] = doc.doc_id
                chunk["source_type"] = doc.source_type
                chunk["source_file"] = doc.metadata.get("source_file", "")
                chunk["chunk_id"] = f"{doc.doc_id}_chunk_{idx + 1:03d}"
            
            # Calculate simple quality score based on chunk lengths
            if chunks:
                avg_len = sum(len(c.get("text", "")) for c in chunks) / len(chunks)
                # Quality score: closer to target length (400) is better
                quality_score = max(0, 1 - abs(avg_len - 400) / 400)
            else:
                quality_score = 0.0
            
            result.success = True
            result.chunks = chunks
            result.quality_score = quality_score
            result.api_calls = 0 if self.dry_run else 1
            
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            logger.error(f"Error processing {doc.doc_id}: {e}")
        
        result.processing_time = time.time() - start_time
        return result
    
    def process_batch(
        self,
        documents: list[DocumentInfo],
        resume_from_checkpoint: bool = False
    ) -> BatchProgress:
        """
        Process a batch of documents.
        
        Args:
            documents: List of documents to process
            resume_from_checkpoint: Whether to resume from checkpoint
            
        Returns:
            BatchProgress object
        """
        # Initialize or load progress
        if resume_from_checkpoint:
            self._load_checkpoint()
        else:
            self.progress = BatchProgress(
                total_documents=len(documents),
                start_time=datetime.now().isoformat()
            )
        
        logger.info(f"Starting batch processing of {len(documents)} documents")
        logger.info(f"Dry run: {self.dry_run}")
        logger.info(f"Checkpoint interval: {self.checkpoint_interval}")
        
        # Filter out already processed documents
        processed_ids = set(self.progress.processed_ids)
        documents_to_process = [
            doc for doc in documents
            if doc.doc_id not in processed_ids
        ]
        
        logger.info(f"Documents to process: {len(documents_to_process)}")
        logger.info(f"Parallel workers: {self.max_workers}")
        
        # Use rich progress bar with parallel processing if available
        if HAS_RICH:
            console = Console()
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TextColumn("({task.completed}/{task.total})"),
                TimeRemainingColumn(),
                console=console,
                transient=False
            ) as progress:
                task = progress.add_task(
                    "[cyan]處理文件中...", 
                    total=len(documents_to_process)
                )
                
                # Parallel processing with ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    # Submit all tasks
                    future_to_doc = {
                        executor.submit(self.process_document, doc): (idx, doc)
                        for idx, doc in enumerate(documents_to_process, 1)
                    }
                    
                    # Process results as they complete
                    for future in as_completed(future_to_doc):
                        # 檢查是否收到中斷信號
                        if GracefulShutdown.shutdown_requested:
                            logger.warning("⏸️ 偵測到中斷信號，正在取消剩餘任務...")
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        
                        idx, doc = future_to_doc[future]
                        
                        try:
                            result = future.result()
                            
                            # Thread-safe update
                            with self.lock:
                                self.results.append(result)
                                self.progress.processed_documents += 1
                                self.progress.processed_ids.append(doc.doc_id)
                                
                                if result.success:
                                    self.progress.successful_documents += 1
                                    self.progress.total_chunks_generated += len(result.chunks)
                                    self.all_chunks.extend(result.chunks)
                                else:
                                    self.progress.failed_documents += 1
                                    self.progress.failed_ids.append(doc.doc_id)
                                
                                self.progress.total_api_calls += result.api_calls
                                self.progress.total_processing_time += result.processing_time
                                
                                # Save checkpoint periodically
                                if self.progress.processed_documents % self.checkpoint_interval == 0:
                                    self._save_checkpoint()
                            
                            # Update progress bar
                            progress.update(task, advance=1)
                            
                        except Exception as e:
                            logger.error(f"Error processing {doc.doc_id}: {e}")
                            with self.lock:
                                self.progress.processed_documents += 1
                                self.progress.failed_documents += 1
                                self.progress.failed_ids.append(doc.doc_id)
                            progress.update(task, advance=1)
        else:
            # Fallback to simple logging without rich
            for idx, doc in enumerate(documents_to_process, 1):
                # 檢查是否收到中斷信號
                if GracefulShutdown.shutdown_requested:
                    logger.warning("⏸️ 偵測到中斷信號，停止處理新文檔...")
                    break
                
                logger.info(f"Processing [{idx}/{len(documents_to_process)}] {doc.doc_id}")
                result = self.process_document(doc)
                
                self.results.append(result)
                self.progress.processed_documents += 1
                self.progress.processed_ids.append(doc.doc_id)
                
                if result.success:
                    self.progress.successful_documents += 1
                    self.progress.total_chunks_generated += len(result.chunks)
                    self.all_chunks.extend(result.chunks)
                    logger.info(f"  ✓ Generated {len(result.chunks)} chunks")
                else:
                    self.progress.failed_documents += 1
                    self.progress.failed_ids.append(doc.doc_id)
                    logger.warning(f"  ✗ Failed: {result.error_message}")
                
                self.progress.total_api_calls += result.api_calls
                self.progress.total_processing_time += result.processing_time
                
                if idx % self.checkpoint_interval == 0:
                    self._save_checkpoint()
                
                if not self.dry_run:
                    time.sleep(API_RATE_LIMIT_DELAY)
        
        # 如果被中斷，顯示提示訊息
        if GracefulShutdown.shutdown_requested:
            logger.warning("\n🛑 處理已中斷，已保存當前進度")
            logger.warning("💡 使用 --resume 參數可繼續處理剩餘文檔\n")
        
        # Final checkpoint and output
        self._save_checkpoint()
        self._save_final_output()
        
        return self.progress
    
    def _save_checkpoint(self) -> None:
        """Save current progress to checkpoint file and incremental output."""
        self.progress.last_checkpoint = datetime.now().isoformat()
        
        checkpoint_file = self.checkpoint_dir / "batch_progress.json"
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(self.progress.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Also save current chunks to checkpoint
        chunks_checkpoint = self.checkpoint_dir / "chunks_checkpoint.json"
        with open(chunks_checkpoint, "w", encoding="utf-8") as f:
            json.dump(self.all_chunks, f, ensure_ascii=False, indent=2)
        
        # 🔄 持續更新最終輸出文件（每次 checkpoint 都寫入）
        # 這樣即使中途中斷，也能保有已處理的結果
        incremental_output = RAG_CHUNKS_DIR / "kimik2_0905_chunking.json"
        with open(incremental_output, "w", encoding="utf-8") as f:
            json.dump(self.all_chunks, f, ensure_ascii=False, indent=2)
        
        logger.info(
            f"Checkpoint saved at document {self.progress.processed_documents} "
            f"({len(self.all_chunks)} chunks)"
        )
    
    def _load_checkpoint(self) -> None:
        """Load progress from checkpoint file."""
        checkpoint_file = self.checkpoint_dir / "batch_progress.json"
        chunks_checkpoint = self.checkpoint_dir / "chunks_checkpoint.json"
        
        if checkpoint_file.exists():
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.progress = BatchProgress.from_dict(data)
            logger.info(f"Loaded checkpoint: {self.progress.processed_documents} documents processed")
        
        if chunks_checkpoint.exists():
            with open(chunks_checkpoint, "r", encoding="utf-8") as f:
                self.all_chunks = json.load(f)
            logger.info(f"Loaded {len(self.all_chunks)} chunks from checkpoint")
    
    def _save_final_output(self) -> None:
        """Save final output files."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save smart chunks with timestamp
        output_file = self.output_dir / f"kimik2_0905_chunking_{timestamp}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(self.all_chunks, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(self.all_chunks)} chunks to {output_file}")
        
        # Also save to standard location (without timestamp)
        standard_output = RAG_CHUNKS_DIR / "kimik2_0905_chunking.json"
        with open(standard_output, "w", encoding="utf-8") as f:
            json.dump(self.all_chunks, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved chunks to {standard_output}")
        
        # Save processing report
        report = self._generate_report()
        report_file = self.output_dir / f"chunking_report_{timestamp}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved report to {report_file}")
        
        # Save statistics
        stats = self._generate_statistics()
        stats_file = RAG_CHUNKS_DIR / "kimik2_0905_chunking_stats.json"
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved statistics to {stats_file}")
    
    def _generate_report(self) -> dict:
        """Generate processing report."""
        return {
            "summary": {
                "total_documents": self.progress.total_documents,
                "processed_documents": self.progress.processed_documents,
                "successful_documents": self.progress.successful_documents,
                "failed_documents": self.progress.failed_documents,
                "success_rate": (
                    self.progress.successful_documents / self.progress.processed_documents
                    if self.progress.processed_documents > 0 else 0
                ),
                "total_chunks_generated": self.progress.total_chunks_generated,
                "total_api_calls": self.progress.total_api_calls,
                "total_processing_time_seconds": self.progress.total_processing_time,
                "average_time_per_document": (
                    self.progress.total_processing_time / self.progress.processed_documents
                    if self.progress.processed_documents > 0 else 0
                ),
            },
            "processing_details": {
                "start_time": self.progress.start_time,
                "end_time": datetime.now().isoformat(),
                "dry_run": self.dry_run,
            },
            "failed_documents": self.progress.failed_ids,
            "results_by_source": self._aggregate_by_source(),
        }
    
    def _aggregate_by_source(self) -> dict:
        """Aggregate results by source type."""
        by_source = {}
        
        for result in self.results:
            source = result.source_type
            if source not in by_source:
                by_source[source] = {
                    "total": 0,
                    "successful": 0,
                    "failed": 0,
                    "chunks_generated": 0,
                    "avg_quality_score": 0.0,
                    "quality_scores": [],
                }
            
            by_source[source]["total"] += 1
            if result.success:
                by_source[source]["successful"] += 1
                by_source[source]["chunks_generated"] += len(result.chunks)
                by_source[source]["quality_scores"].append(result.quality_score)
            else:
                by_source[source]["failed"] += 1
        
        # Calculate averages
        for source in by_source:
            scores = by_source[source]["quality_scores"]
            by_source[source]["avg_quality_score"] = (
                sum(scores) / len(scores) if scores else 0.0
            )
            del by_source[source]["quality_scores"]
        
        return by_source
    
    def _generate_statistics(self) -> dict:
        """Generate chunking statistics."""
        if not self.all_chunks:
            return {"error": "No chunks generated"}
        
        lengths = [len(chunk.get("text", "")) for chunk in self.all_chunks]
        sources = {}
        
        for chunk in self.all_chunks:
            source = chunk.get("source_type", "unknown")
            sources[source] = sources.get(source, 0) + 1
        
        return {
            "generated_at": datetime.now().isoformat(),
            "total_chunks": len(self.all_chunks),
            "sources": sources,
            "length_stats": {
                "min": min(lengths) if lengths else 0,
                "max": max(lengths) if lengths else 0,
                "avg": sum(lengths) / len(lengths) if lengths else 0,
            },
            "processing_info": {
                "dry_run": self.dry_run,
                "total_documents_processed": self.progress.processed_documents,
                "api_calls": self.progress.total_api_calls,
            }
        }


# ==============================================================================
# Main Function
# ==============================================================================

def main():
    """Main entry point."""
    # 設置信號處理器（Ctrl+C 優雅退出）
    GracefulShutdown.setup()
    
    parser = argparse.ArgumentParser(
        description="RAG 系統批次 LLM 分塊處理"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="不實際呼叫 API 執行（使用備用分塊方式）"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="從上次檢查點繼續執行"
    )
    parser.add_argument(
        "--source",
        type=str,
        help="僅處理特定來源類型（例如：'wiki'、'classical'）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="限制處理文件數量（測試用）"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="並行處理的執行緒數量（預設：3）"
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=CHECKPOINT_INTERVAL,
        help=f"每 N 個文件儲存檢查點（預設：{CHECKPOINT_INTERVAL}）"
    )
    parser.add_argument(
        "--reprocess-failed",
        action="store_true",
        help="自動偵測有問題的 chunk（空 keywords、被截斷）並重新處理這些文檔"
    )
    
    args = parser.parse_args()
    
    console = Console() if HAS_RICH else None
    
    # Display header
    if HAS_RICH:
        header_text = (
            "[bold cyan]P2-T02: 批次 LLM 分塊處理[/bold cyan]\n"
            f"[yellow]模式：[/yellow] {'模擬執行' if args.dry_run else '實際執行'}\n"
            f"[yellow]續傳：[/yellow] {'是' if args.resume else '否'}\n"
            f"[yellow]來源篩選：[/yellow] {args.source or '全部'}\n"
            f"[yellow]並行執行緒：[/yellow] {args.workers}"
        )
        if args.limit:
            header_text += f"\n[yellow]限制數量：[/yellow] {args.limit} 個文件"
        console.print(Panel.fit(header_text, border_style="cyan"))
    else:
        logger.info("=" * 60)
        logger.info("P2-T02: 批次 LLM 分塊處理")
        logger.info("=" * 60)
    
    # ========== PRE-FLIGHT CHECKS ==========
    
    # 0. Validate JSON format of all source files FIRST
    loader = SourceDocumentLoader(RAG_SOURCE_DIR)
    is_valid, errors = loader.validate_source_files(console)
    
    if not is_valid:
        if HAS_RICH:
            console.print("\n[bold red]💥 無法繼續：請先修正來源文件的 JSON 格式錯誤[/bold red]")
            console.print(f"[yellow]提示：總共發現 {len(errors)} 個錯誤[/yellow]")
        else:
            logger.error("無法繼續：請先修正來源文件的 JSON 格式錯誤")
            logger.error(f"總共發現 {len(errors)} 個錯誤")
        return 1
    
    # 1. Check source data directory
    if HAS_RICH:
        console.print("\n[bold cyan]執行前置檢查...[/bold cyan]")
        if not RAG_SOURCE_DIR.exists():
            console.print(f"[bold red]❌ 來源資料目錄不存在：{RAG_SOURCE_DIR}[/bold red]")
            return 1
        # Use recursive glob to find files in subdirectories
        source_files = list(RAG_SOURCE_DIR.rglob("*.json")) + list(RAG_SOURCE_DIR.rglob("*.jsonl"))
        console.print(f"[green]✅ 來源資料目錄：{len(source_files)} 個檔案[/green]")
    else:
        logger.info("檢查來源資料目錄...")
        if not RAG_SOURCE_DIR.exists():
            logger.error(f"來源資料目錄不存在：{RAG_SOURCE_DIR}")
            return 1
        # Use recursive glob to find files in subdirectories
        source_files = list(RAG_SOURCE_DIR.rglob("*.json")) + list(RAG_SOURCE_DIR.rglob("*.jsonl"))
        logger.info(f"來源資料目錄：{len(source_files)} 個檔案")
    
    # 2. Test API connection (unless dry-run)
    if not args.dry_run:
        if HAS_RICH:
            with console.status("[yellow]測試 API 連接..."):
                success, msg = api_client.test_connection()
                if not success:
                    console.print(f"[bold red]❌ API 連接失敗：{msg}[/bold red]")
                    console.print("[yellow]提示：請檢查 OPENROUTER_API_KEY 環境變數[/yellow]")
                    return 1
                console.print(f"[green]✅ API 連接成功[/green]")
        else:
            logger.info("測試 API 連接...")
            success, msg = api_client.test_connection()
            if not success:
                logger.error(f"API 連接失敗：{msg}")
                logger.info("請檢查 OPENROUTER_API_KEY 環境變數")
                return 1
            logger.info("API 連接成功")
    
    if HAS_RICH:
        console.print("[green]✅ 所有前置檢查通過[/green]\n")
    
    # ========== END PRE-FLIGHT CHECKS ==========
    
    # ========== REPROCESS FAILED CHUNKS MODE ==========
    if args.reprocess_failed:
        if HAS_RICH:
            console.print("\n[bold yellow]🔍 偵測有問題的分塊模式啟動[/bold yellow]\n")
        else:
            logger.info("偵測有問題的分塊模式啟動")
        
        problem_docs = detect_and_clean_failed_chunks(console)
        
        if not problem_docs:
            if HAS_RICH:
                console.print("[bold green]✅ 沒有發現問題分塊！所有文檔品質良好。[/bold green]")
            else:
                logger.info("沒有發現問題分塊")
            return 0
        
        if HAS_RICH:
            console.print(f"\n[yellow]📋 即將重新處理 {len(problem_docs)} 個文檔[/yellow]")
            console.print("[cyan]這些文檔的舊 chunks 已從輸出文件中移除[/cyan]\n")
        else:
            logger.info(f"即將重新處理 {len(problem_docs)} 個文檔")
        
        # 自動啟用 resume 模式繼續處理
        args.resume = True
    # ========== END REPROCESS FAILED MODE ==========
    
    # Ensure log directory exists
    log_dir = PROJECT_ROOT / "output" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Load source documents
    if HAS_RICH:
        with console.status("[bold green]載入來源文件中..."):
            documents = loader.load_all_documents(source_filter=args.source)
        
        # Apply limit if specified
        if args.limit and args.limit > 0:
            documents = documents[:args.limit]
            console.print(f"[yellow]已限制處理數量為 {args.limit} 份文件[/yellow]")
        
        console.print(f"[green]已載入 {len(documents)} 份文件[/green]")
    else:
        logger.info("載入來源文件中...")
        documents = loader.load_all_documents(source_filter=args.source)
        
        # Apply limit if specified
        if args.limit and args.limit > 0:
            documents = documents[:args.limit]
            logger.info(f"已限制處理數量為 {args.limit} 份文件")
    
    if not documents:
        if HAS_RICH:
            console.print("[red]找不到要處理的文件[/red]")
        else:
            logger.error("找不到要處理的文件")
        return 1
    
    # Initialize chunker
    if HAS_RICH:
        console.print("[cyan]初始化智能分塊器中...[/cyan]")
    else:
        logger.info("初始化智能分塊器中...")
    chunker = SmartChunker()
    
    # Initialize batch processor - use RAG_CHUNKS_DIR instead of output/batch_chunking
    output_dir = RAG_CHUNKS_DIR
    processor = BatchChunkingProcessor(
        chunker=chunker,
        output_dir=output_dir,
        checkpoint_interval=args.checkpoint_interval,
        dry_run=args.dry_run,
        max_workers=args.workers
    )
    
    # Process batch
    if HAS_RICH:
        console.print("[bold green]開始批次處理...[/bold green]\n")
    else:
        logger.info("開始批次處理...")
    
    progress = processor.process_batch(
        documents=documents,
        resume_from_checkpoint=args.resume
    )
    
    # Print summary
    if HAS_RICH:
        summary_table = Table(title="處理摘要", show_header=True, header_style="bold cyan")
        summary_table.add_column("指標", style="cyan")
        summary_table.add_column("數值", justify="right", style="green")
        
        summary_table.add_row("文件總數", str(progress.total_documents))
        summary_table.add_row("已處理", str(progress.processed_documents))
        summary_table.add_row("成功", str(progress.successful_documents))
        summary_table.add_row("失敗", str(progress.failed_documents))
        summary_table.add_row("分塊總數", str(progress.total_chunks_generated))
        summary_table.add_row("API 呼叫次數", str(progress.total_api_calls))
        summary_table.add_row("處理時間", f"{progress.total_processing_time:.2f} 秒")
        
        console.print("\n")
        console.print(summary_table)
        console.print("\n")
        console.print(Panel.fit(
            f"[bold green]處理完成！[/bold green]\n"
            f"輸出位置：{output_dir}",
            border_style="green"
        ))
    else:
        logger.info("=" * 60)
        logger.info("處理完成！")
        logger.info("=" * 60)
        logger.info(f"文件總數：{progress.total_documents}")
        logger.info(f"已處理：{progress.processed_documents}")
    logger.info(f"Successful: {progress.successful_documents}")
    logger.info(f"Failed: {progress.failed_documents}")
    logger.info(f"Total chunks generated: {progress.total_chunks_generated}")
    logger.info(f"Total processing time: {progress.total_processing_time:.2f}s")
    
    if progress.failed_ids:
        logger.warning(f"Failed document IDs: {progress.failed_ids}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
