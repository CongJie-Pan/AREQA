#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-T01: BGE Reranker Module
===========================
整合 BAAI/bge-reranker-v2-m3 進行檢索結果的重排序 (Reranking)。
包含自動 GPU VRAM 檢測與 Rich UI 顯示。

Features:
- Cross-Encoder 架構，精確度高於 Bi-Encoder
- GPU 記憶體安全檢測 (VRAM < 4GB 自動切換 CPU)
- 支援 Top-K 篩選
"""

import os
import torch
import logging
from typing import List, Tuple, Dict, Any
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.status import Status

# 配置日誌
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

console = Console()

# Cache Configuration
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
MODEL_CACHE_DIR = PROJECT_ROOT / "models" / "huggingface"
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

os.environ['HF_HOME'] = str(MODEL_CACHE_DIR)
os.environ['TRANSFORMERS_CACHE'] = str(MODEL_CACHE_DIR)

class BGEReranker:
    """
    BGE Reranker (Cross-Encoder) wrapper with memory safety.
    """
    
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self.model_name = model_name
        self.device = self._get_optimal_device()
        self.tokenizer = None
        self.model = None
        
        self._load_model()
        
    def _get_optimal_device(self) -> str:
        """
        Check GPU memory availability and determine best device.
        Requires at least 4GB VRAM for safe operation.
        """
        if not torch.cuda.is_available():
            console.print("[dim]No GPU detected. Using CPU.[/dim]")
            return "cpu"
            
        try:
            # Get free memory in GB
            free_mem, total_mem = torch.cuda.mem_get_info()
            free_gb = free_mem / (1024**3)
            total_gb = total_mem / (1024**3)
            
            console.print(f"[dim]GPU Status: {torch.cuda.get_device_name(0)} | Free: {free_gb:.1f}GB / {total_gb:.1f}GB[/dim]")
            
            if free_gb < 4.0:
                console.print(Panel(
                    f"[yellow]⚠️  GPU VRAM Insufficient ({free_gb:.1f}GB < 4.0GB)[/yellow]\n"
                    "Switched to [bold]CPU[/bold] to prevent Out-Of-Memory error.\n"
                    "[dim]Inference will be slower but stable.[/dim]",
                    title="Resource Safety Guard",
                    border_style="yellow"
                ))
                return "cpu"
            else:
                return "cuda"
                
        except Exception as e:
            logger.warning(f"Failed to check GPU memory: {e}. Defaulting to CPU.")
            return "cpu"

    def _load_model(self):
        """Load tokenizer and model."""
        with console.status(f"[bold cyan]Loading Reranker Model ({self.device})...[/bold cyan]") as status:
            try:
                from transformers import AutoTokenizer, AutoModelForSequenceClassification
                
                status.update(f"[cyan]Loading tokenizer: {self.model_name}[/cyan]")
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                
                status.update(f"[cyan]Loading model weights to {self.device.upper()}...[/cyan]")
                self.model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_name
                ).to(self.device).eval() # Set to eval mode
                
                # Enable FP16 for CUDA to save memory
                if self.device == "cuda":
                    self.model.half()
                    
                console.print(f"  ✅ Reranker Loaded: [green]{self.model_name}[/green]")
                
            except Exception as e:
                console.print(f"[red]❌ Failed to load model: {e}[/red]")
                raise e

    def rerank(self, query: str, documents: List[str], top_k: int = 5) -> List[Tuple[int, float]]:
        """
        Rerank a list of documents based on query relevance.
        
        Args:
            query: The search query
            documents: List of document texts
            top_k: Number of top results to return
            
        Returns:
            List of (original_index, score) tuples, sorted by score descending.
        """
        if not documents:
            return []
            
        # Prepare pairs
        pairs = [[query, doc] for doc in documents]
        
        try:
            with torch.no_grad():
                inputs = self.tokenizer(
                    pairs, 
                    padding=True, 
                    truncation=True, 
                    return_tensors='pt', 
                    max_length=512
                ).to(self.device)
                
                scores = self.model(**inputs, return_dict=True).logits.view(-1,).float()
                
                # Sigmoid to get 0-1 range (optional, but good for interpretation)
                scores = torch.sigmoid(scores)
                
                scores = scores.cpu().numpy()
                
            # Create (index, score) pairs
            ranked_results = [
                (i, float(score)) for i, score in enumerate(scores)
            ]
            
            # Sort by score desc
            ranked_results.sort(key=lambda x: x[1], reverse=True)
            
            return ranked_results[:top_k]
            
        except RuntimeError as e:
            if "out of memory" in str(e).lower() and self.device == "cuda":
                console.print("[red]❌ GPU OOM during reranking! Suggest restarting with CPU.[/red]")
                torch.cuda.empty_cache()
            raise e

def main():
    """Test the reranker."""
    console.print(Panel.fit("[bold blue]BGE Reranker Test[/bold blue]"))
    
    reranker = BGEReranker()
    
    query = "賈寶玉的性格特徵是什麼？"
    docs = [
        "賈寶玉是《紅樓夢》的主角，性格叛逆，不愛讀書，喜歡在脂粉堆裡混。", # Relevant
        "林黛玉是金陵十二釵之首，多愁善感。", # Slightly relevant (same book)
        "三國演義講述了東漢末年的群雄逐鹿。", # Irrelevant
        "Python 是一種程式語言。", # Irrelevant
        "寶玉道：『女兒是水做的骨肉，男人是泥做的骨肉。』" # Highly relevant
    ]
    
    console.print(f"\n[bold]Query:[/bold] {query}")
    console.print("[bold]Documents:[/bold]")
    for i, doc in enumerate(docs):
        console.print(f"  [{i}] {doc}")
        
    results = reranker.rerank(query, docs, top_k=3)
    
    console.print("\n[bold green]Top 3 Results:[/bold green]")
    for rank, (idx, score) in enumerate(results, 1):
        console.print(f"  {rank}. Doc [{idx}] (Score: {score:.4f}): {docs[idx]}")

if __name__ == "__main__":
    main()
