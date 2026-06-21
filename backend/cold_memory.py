import os
import json
import pysqlite3 as sqlite3
import sqlite_vec
import httpx
from typing import List, Dict, Any, Tuple

class ColdMemoryRetriever:
    def __init__(self, db_path: str, openrouter_api_key: str):
        self.db_path = db_path
        self.api_key = openrouter_api_key
        self.embedding_model = "qwen/qwen3-embedding-8b" # as specified in the plan
        self.embedding_url = "https://openrouter.ai/api/v1/embeddings" # Assume standard endpoint
        
        # Initialize sqlite-vec if the tables don't exist
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            # We assume propositions table exists from GUM, but we need a vector table
            # sqlite-vec uses virtual tables
            conn.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_memory USING vec0(
                    id INTEGER PRIMARY KEY,
                    embedding float[4096] -- Qwen3 usually 4096, adjust if needed
                )
            ''')
            # Let's also create a fallback BM25 table if we want to do hybrid
            # or rely on GUM's existing propositions_fts
            conn.commit()

    async def get_embedding(self, text: str) -> List[float]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.embedding_model,
                "input": text
            }
            try:
                response = await client.post(self.embedding_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["data"][0]["embedding"]
            except Exception as e:
                print(f"[ColdMemory] Embedding API failed: {e}")
                return []

    async def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # Hybrid Search: Vector KNN + BM25 + RRF
        query_embedding = await self.get_embedding(query)
        
        with self._get_conn() as conn:
            vec_results = []
            if query_embedding:
                # Vector Search
                # Wait, sqlite-vec syntax:
                # SELECT id, distance FROM vec_memory WHERE embedding MATCH ? ORDER BY distance LIMIT ?
                try:
                    import struct
                    # Pack floats to bytes
                    embed_bytes = struct.pack(f'{len(query_embedding)}f', *query_embedding)
                    
                    cursor = conn.execute(
                        "SELECT id, distance FROM vec_memory WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                        (embed_bytes, top_k * 2)
                    )
                    vec_results = cursor.fetchall() # [(id, distance)]
                except Exception as e:
                    print(f"[ColdMemory] Vector search failed: {e}")
            
            # BM25 Search
            # Assuming GUM's existing `propositions_fts` exists
            bm25_results = []
            try:
                safe_query = '"' + query.replace('"', '""') + '"'
                cursor = conn.execute(
                    "SELECT rowid, bm25(propositions_fts) FROM propositions_fts WHERE propositions_fts MATCH ? ORDER BY bm25(propositions_fts) LIMIT ?",
                    (safe_query, top_k * 2)
                )
                bm25_results = cursor.fetchall() # [(id, score)]
            except Exception as e:
                print(f"[ColdMemory] BM25 search failed: {e}")
                
            # RRF Fusion
            rrf_scores = {}
            k_const = 60
            
            # Distance smaller is better, convert to rank
            for rank, (doc_id, dist) in enumerate(vec_results):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + (1.0 / (k_const + rank + 1))
                
            # BM25 larger/smaller is better? Usually smaller in sqlite bm25()
            for rank, (doc_id, score) in enumerate(bm25_results):
                rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + (1.0 / (k_const + rank + 1))
                
            sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
            
            final_results = []
            for doc_id, score in sorted_docs:
                try:
                    # Fetch text from propositions, filtering by active status
                    cursor = conn.execute("SELECT text FROM propositions WHERE id = ? AND status = 'active'", (doc_id,))
                    row = cursor.fetchone()
                    if row:
                        final_results.append({"id": doc_id, "text": row[0], "rrf_score": score})
                except Exception:
                    pass
                    
            return final_results
