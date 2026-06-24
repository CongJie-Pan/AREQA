import sqlite3
import sqlite_vec
import struct
import os
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "memories")
DB_PATH = os.path.join(MEMORY_DIR, "episodic_memory.db")

class VectorStore:
    def __init__(self):
        self.db_path = DB_PATH
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("WARNING: OPENROUTER_API_KEY not set. VectorStore will fail to embed.")
            
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
        self.model = "qwen/qwen3-embedding-8b"
        self._init_db()

    def _init_db(self):
        os.makedirs(MEMORY_DIR, exist_ok=True)
        self.db = sqlite3.connect(self.db_path)
        self.db.enable_load_extension(True)
        try:
            sqlite_vec.load(self.db)
        except Exception as e:
            print(f"[VectorStore] Failed to load sqlite_vec extension: {e}")
        self.db.enable_load_extension(False)
        
        # Create text table to store the actual strings
        self.db.execute("CREATE TABLE IF NOT EXISTS memory_text (rowid INTEGER PRIMARY KEY, target TEXT, content TEXT UNIQUE)")
        self.db.commit()

    def get_embedding(self, text: str) -> List[float]:
        """Call OpenRouter API to get the vector representation of the text."""
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding

    def serialize_f32(self, vector: List[float]) -> bytes:
        """Convert a list of Python floats into sqlite-vec's binary format."""
        return struct.pack("%sf" % len(vector), *vector)

    def _ensure_vector_table(self, dimension: int):
        """Dynamically create the virtual vector table based on the embedding dimension."""
        cursor = self.db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vec_memories'")
        if not cursor.fetchone():
            print(f"[VectorStore] Initializing vec_memories with dimension {dimension}...")
            cursor.execute(f"CREATE VIRTUAL TABLE vec_memories USING vec0(embedding float[{dimension}])")
            self.db.commit()

    def demote_to_cold_memory(self, target: str, content: str):
        """Demote an overflowing memory into the cold storage SQLite DB."""
        try:
            cursor = self.db.cursor()
            # Try inserting first. If it's a duplicate, we skip embedding to save money and time!
            cursor.execute("INSERT OR IGNORE INTO memory_text (target, content) VALUES (?, ?)", (target, content))
            if cursor.rowcount == 0:
                # Duplicate entry, skip
                return
                
            print(f"[VectorStore] Demoting to cold memory ({target}): {content[:30]}...")
            rowid = cursor.lastrowid
            
            vector = self.get_embedding(content)
            dimension = len(vector)
            self._ensure_vector_table(dimension)
            
            cursor.execute("INSERT INTO vec_memories (rowid, embedding) VALUES (?, ?)", 
                           (rowid, self.serialize_f32(vector)))
            self.db.commit()
        except Exception as e:
            print(f"[VectorStore] Failed to demote memory: {e}")

    def search_cold_memory(self, query: str, top_k: int = 3) -> List[str]:
        """Search the SQLite DB for semantically similar memories."""
        cursor = self.db.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vec_memories'")
        if not cursor.fetchone():
            # Vector table hasn't been created yet, meaning no demoted memories exist
            return []

        try:
            query_vector = self.get_embedding(query)
            
            results = self.db.execute(
                """
                SELECT mt.content 
                FROM vec_memories v
                JOIN memory_text mt ON v.rowid = mt.rowid
                WHERE embedding MATCH ? AND k = ?
                """,
                (self.serialize_f32(query_vector), top_k)
            ).fetchall()
            
            return [row[0] for row in results]
        except Exception as e:
            print(f"[VectorStore] Search failed: {e}")
            return []
