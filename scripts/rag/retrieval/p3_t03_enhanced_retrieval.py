#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P3-T03: Enhanced Retrieval Pipeline (RAG V3)
============================================
整合所有 RAG 升級元件的完整檢索流程。

Pipeline:
1. Query Expansion (LiteLLM) -> 白話轉古文關鍵詞
2. Hybrid Search (BGE-M3 + BM25) -> 召回 Top 100
3. Reranking (BGE-Reranker) -> 精排 Top 5
4. Parent Context Retrieval -> 獲取完整上下文

Usage:
    python scripts/rag/p3_t03_enhanced_retrieval.py
"""

import sys
import os
import json
from pathlib import Path
from typing import List, Dict, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

# Add scripts/rag to path to import sibling modules
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "scripts" / "rag"))

# Import RAG V2 (test_hybrid_rag) components for loading indices
# We need to reuse load_chunks, load_bge_m3_model, load_faiss_index, load_bm25_index
# Note: We might need to copy/paste or import carefully if test_hybrid_rag isn't designed as a proper module.
# To avoid issues, we'll import functions if possible, or reimplement the loading logic cleanly here.
# For simplicity and stability, we reimplement clean loading logic here, reusing codes from test_hybrid_rag.py analysis.

from p3_t01_reranker import BGEReranker
from p3_t02_query_expander import QueryExpander

console = Console()

# ============================================================================
# Connectors to Existing RAG V2 Data
# ============================================================================

DATA_DIR = PROJECT_ROOT / "data" / "rag"
CHUNKS_DIR = DATA_DIR / "chunks"
FAISS_DIR = DATA_DIR / "faiss_index"
BM25_DIR = DATA_DIR / "bm25_index"

def load_all_data():
    """Load all necessary indices and chunks."""
    with console.status("[bold cyan]Loading System Components...[/bold cyan]") as status:
        # 1. Load Chunks
        status.update("Loading chunks...")
        chunks = {}
        for f in CHUNKS_DIR.glob("*_chunks.json"):
            if "stats" in f.name: continue
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                for c in data:
                    chunks[c['chunk_id']] = c
        console.print(f"  ✅ Loaded {len(chunks)} chunks")

        # 2. Load FAISS
        status.update("Loading FAISS index...")
        import faiss
        index_path = FAISS_DIR / "chunks_bge_m3.index"
        mapping_path = FAISS_DIR / "chunk_mapping_bge_m3.json"
        
        if not index_path.exists():
            console.print("[red]❌ FAISS index not found. Run P2-T09 first.[/red]")
            return None
            
        faiss_index = faiss.read_index(str(index_path))
        with open(mapping_path, 'r', encoding='utf-8') as f:
            faiss_mapping = json.load(f)['chunk_ids']
        console.print(f"  ✅ FAISS Index Loaded ({faiss_index.ntotal} vectors)")

        # 3. Load BM25
        status.update("Loading BM25 index...")
        import pickle
        from rank_bm25 import BM25Okapi
        bm25_path = BM25_DIR / "bm25_index.pkl"
        
        if not bm25_path.exists():
             console.print("[red]❌ BM25 index not found. Run P2-T10 first.[/red]")
             return None

        with open(bm25_path, 'rb') as f:
            bm25_data = pickle.load(f)
        
        bm25_index = BM25Okapi(bm25_data['tokenized_docs'], k1=bm25_data['config']['k1'], b=bm25_data['config']['b'])
        bm25_ids = [bm25_data['chunk_id_mapping'][i] for i in range(len(bm25_data['tokenized_docs']))]
        console.print(f"  ✅ BM25 Index Loaded")

        # 4. Load BGE-M3 Model (for query embedding)
        status.update("Loading BGE-M3 Model...")
        from FlagEmbedding import BGEM3FlagModel
        # Use existing cache
        os.environ['HF_HOME'] = str(PROJECT_ROOT / "models" / "huggingface")
        bge_model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, device="cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") != "-1" and __import__("torch").cuda.is_available() else "cpu")
        console.print(f"  ✅ BGE-M3 Model Loaded")
        
        return chunks, faiss_index, faiss_mapping, bm25_index, bm25_ids, bge_model

# ============================================================================
# Search Logic
# ============================================================================

def search_faiss(query, model, index, ids, k=50):
    import numpy as np
    emb = model.encode([query], return_dense=True, return_sparse=False)['dense_vecs'][0].astype(np.float32).reshape(1, -1)
    dists, idxs = index.search(emb, k)
    return [(ids[i], float(d)) for d, i in zip(dists[0], idxs[0]) if i < len(ids)]

def search_bm25(query, bm25, ids, k=50):
    # Simple N-gram tokenization
    tokens = list(query) + [query[i:i+2] for i in range(len(query)-1)]
    scores = bm25.get_scores(tokens)
    import numpy as np
    top_idxs = np.argsort(scores)[::-1][:k]
    return [(ids[i], float(scores[i])) for i in top_idxs]

def rrf_fusion(list1, list2, k=60, alpha=0.5):
    scores = {}
    for r, (id, s) in enumerate(list1):
        scores[id] = scores.get(id, 0) + alpha * (1 / (k + r + 1))
    for r, (id, s) in enumerate(list2):
        scores[id] = scores.get(id, 0) + (1 - alpha) * (1 / (k + r + 1))
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

# ============================================================================
# Generation Logic (Perplexity Reference Implementation)
# ============================================================================

def generate_answer(query: str, chunks_data: List[Dict], model_name: str = "openrouter/deepseek/deepseek-chat"):
    """
    Generate answer using Strict Citation Rules and Dynamic Re-indexing.
    
    Args:
        query: User's question
        chunks_data: List of dicts, each containing 'chunk_id', 'text', and optionally 'metadata'/'parent_context'
                     The order of this list determines the index [1], [2], etc.
    """
    # 1. Dynamic Re-indexing & Context Construction
    context_str = "<search_results>\n"
    available_ids = []
    
    for idx, chunk in enumerate(chunks_data, 1):
        available_ids.append(str(idx))
        # Fallback to chunk text if parent_context is missing
        content = chunk.get('parent_context', chunk.get('text', ''))
        
        # Try to extract metadata if available
        meta = chunk.get('metadata', {})
        source_type = chunk.get('source', '')
        
        # Metadata Extraction Logic (High Precision)
        meta = chunk.get('metadata', {})
        source_type = chunk.get('source', '')
        
        source_line = ""
        detail_line = ""
        
        # 1. Title/Entry Name
        title = meta.get('title', '')
        
        # 2. Authorship
        author = meta.get('authorship', '')
        
        # 3. Chapter/Section Info
        chapter_str = ""
        if 'chapter_id' in meta:
             chapter_str = f"第{meta['chapter_id']}回"
        elif 'section' in meta:
             chapter_str = meta['section']
             
        # Construct Source Info based on Type
        if source_type == '回目' or source_type == '原文':
            source_line = f"出處：紅樓夢" + (f" ({author})" if author else "")
            detail_line = f"章節：{chapter_str}" + (f" — {title}" if title else "")
            
        elif source_type == '詩詞':
            source_line = f"出處：紅樓夢詩詞" + (f" ({author})" if author else "")
            detail_line = f"標題：{title}" + (f" ({chapter_str})" if chapter_str else "")
            
        elif source_type == '維基':
            source_line = f"出處：維基百科"
            detail_line = f"條目：{title}" + (f" — {chapter_str}" if chapter_str else "")
            
        else:
            # Generic Fallback
            source_line = f"出處：{source_type if source_type else '未知來源'}"
            if title:
                detail_line = f"標題：{title}"
        
        # Combine valid lines
        source_info = ""
        if source_line: source_info += source_line + "\n"
        if detail_line: source_info += detail_line + "\n"

        # Check if content already has headers (skip if double header)
        if content.strip().startswith("出處") or content.strip().startswith("書名"):
             source_info = ""
            
        context_str += f"[{idx}]\n{source_info}內容：{content}\n\n"
        
    context_str += "</search_results>"
    
    # 2. System Prompt Construction
    system_prompt = f"""你是紅樓夢學術助手。請嚴格基於 `<search_results>` 中的資訊回答使用者的問題。

可用來源 ID: {', '.join([f'[{i}]' for i in available_ids])}

引用規則 (Strict Citation Rules)：
1. **必須**在每個論點後加上來源編號 `[index]`。
2. **只能**使用上述列表中的 ID，絕對禁止使用其他數字 (如 [{len(available_ids)+1}])。
3. 如果 `<search_results>` 沒有相關資訊，請回答「資料庫中無相關資訊」，不要編造。
4. 優先引用最相關的段落。

回答格式範例：
xx觀點認為...[1]。而在另一版本中提到...[2]。
"""

    # 3. Call LLM
    try:
        from litellm import completion
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return "[red]Error: OPENROUTER_API_KEY not set.[/red]"
            
        console.print(Panel(context_str, title="Constructed Context (Dynamic Re-indexing)", border_style="dim", height=15))
        
        with console.status("[bold green]Generating Answer...[/bold green]"):
            response = completion(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                api_key=api_key,
                temperature=0.3
            )
            return response.choices[0].message.content
            
    except Exception as e:
        return f"[red]Generation failed: {e}[/red]"


# ============================================================================
# Main Pipeline
# ============================================================================

def main():
    console.print(Panel.fit("[bold blue]RAG V3: Enhanced Retrieval Pipeline[/bold blue]"))
    
    # 0. Initialize Reranker & Expander
    try:
        reranker = BGEReranker()
        expander = QueryExpander(model_name="openrouter/deepseek/deepseek-chat") # Or config.model
    except Exception as e:
        console.print(f"[red]Failed to init components: {e}[/red]")
        return

    # 1. Load Data
    data = load_all_data()
    if not data: return
    chunks, faiss_idx, faiss_map, bm25_idx, bm25_map, bge_model = data

    # Interactive Loop or Test Questions
    test_queries = [
        "賈寶玉最後跟誰結婚？",
        "林黛玉的性格有什麼特點？",
        "大觀園是為了誰蓋的？"
    ]

    for user_query in test_queries:
        console.print(f"\n[bold magenta]User Query:[/bold magenta] {user_query}")
        
        # Step 1: Query Expansion
        expanded_keywords = expander.expand(user_query)
        # Combine original query + keywords for search
        search_query = f"{user_query} {' '.join(expanded_keywords)}"
        
        # Step 2: Hybrid Retrieval (Recall Top 100)
        # We search using the ENHANCED query for better recall
        faiss_res = search_faiss(search_query, bge_model, faiss_idx, faiss_map, k=100)
        bm25_res = search_bm25(search_query, bm25_idx, bm25_map, k=100)
        
        # Fusion
        hybrid_res = rrf_fusion(faiss_res, bm25_res, k=60, alpha=0.6)[:100]
        
        # Get Doc Texts for Reranking
        candidate_docs = []
        candidate_ids = []
        for cid, score in hybrid_res:
            if cid in chunks:
                candidate_ids.append(cid)
                doc_text = chunks[cid]['text']
                # Add keywords prefix to help reranker context
                keywords_str = " ".join(chunks[cid].get('keywords', []))
                candidate_docs.append(f"{keywords_str} {doc_text}")
        
        # Step 3: Reranking (Refine to Top 5)
        # Rerank against the ORIGINAL user intent/query (or enhanced one? usually original is better for cross-encoder as it understands natural language)
        # But here we use 'user_query' directly.
        reranked = reranker.rerank(user_query, candidate_docs, top_k=5)
        
        # Step 4: Display Results & Prepare Context
        context_chunks = []
        table = Table(title="🏆 Final RAG Results", show_lines=True)
        table.add_column("Rank", style="cyan", width=5)
        table.add_column("Score", style="green", width=8)
        table.add_column("Chunk ID", style="dim", width=20)
        table.add_column("Content (Parent Context Preview)", style="white")
        
        for rank, (idx, score) in enumerate(reranked, 1):
            original_idx = idx # Index in candidate_ids
            cid = candidate_ids[original_idx]
            chunk = chunks[cid]
            
            # Check for parent context
            parent_ctx = chunk.get('parent_context', "")
            display_text = parent_ctx if parent_ctx else chunk['text']
            
            # Prepare data for generation
            context_chunks.append({
                'chunk_id': cid,
                'text': chunk['text'],
                'parent_context': parent_ctx,
                'metadata': chunk.get('metadata', {}) # Assuming metadata exists on chunk object
            })
            
            # Truncate for display
            display_preview = display_text[:150].replace("\n", " ") + "..."
            
            if parent_ctx:
                display_preview = f"[bold yellow][Parent Context][/bold yellow] {display_preview}"
            
            table.add_row(str(rank), f"{score:.4f}", cid, display_preview)
            
        console.print(table)
        
        # Step 5: Generation
        console.print("\n[bold]Step 5: Generation with Strict Citation[/bold]")
        answer = generate_answer(user_query, context_chunks)
        console.print(Panel(Markdown(answer), title=f"Answer: {user_query}", border_style="green"))

if __name__ == "__main__":
    main()
