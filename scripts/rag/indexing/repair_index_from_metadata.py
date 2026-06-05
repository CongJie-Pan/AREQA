import os
import json
import numpy as np
import faiss
import time
from tqdm import tqdm
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/embeddings"
MODEL_ID = "qwen/qwen3-embedding-8b"
METADATA_PATH = "data/rag/faiss_index/index_metadata.json"
OUTPUT_INDEX_PATH = "data/rag/faiss_index/chunks.index"

def get_embeddings(texts, retries=3):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_ID,
        "input": texts
    }
    
    for attempt in range(retries):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                sorted_embs = sorted(data["data"], key=lambda x: x["index"])
                embs_array = np.array([item["embedding"] for item in sorted_embs], dtype="float32")
                # L2 normalize
                norms = np.linalg.norm(embs_array, axis=1, keepdims=True)
                return embs_array / np.maximum(norms, 1e-10)
            else:
                print(f"API Error {resp.status_code}: {resp.text}")
                time.sleep(2)
        except Exception as e:
            print(f"Exception: {e}")
            time.sleep(2)
    raise Exception("Failed to get embeddings after retries.")

def rebuild_index():
    print(f"Loading metadata from {METADATA_PATH}...")
    with open(METADATA_PATH, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
        
    print(f"Loaded {len(metadata)} chunks. Starting embedding generation...")
    
    all_embeddings = []
    batch_size = 50
    
    for i in tqdm(range(0, len(metadata), batch_size)):
        batch = metadata[i:i+batch_size]
        texts = [item.get("page_content", item.get("text", "")) for item in batch]
        
        embs = get_embeddings(texts)
        all_embeddings.append(embs)
        
    final_embeddings = np.vstack(all_embeddings)
    dim = final_embeddings.shape[1]
    
    print(f"\nBuilding FAISS IndexFlatIP (dim={dim}, count={len(final_embeddings)})...")
    index = faiss.IndexFlatIP(dim)
    index.add(final_embeddings)
    
    faiss.write_index(index, OUTPUT_INDEX_PATH)
    print(f"Successfully saved clean FAISS index to {OUTPUT_INDEX_PATH}!")

if __name__ == "__main__":
    rebuild_index()
