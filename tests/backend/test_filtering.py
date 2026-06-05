import pytest
from dataclasses import dataclass

# 我們需要匯入 backend/main.py 裡的函數
# 由於 FastAPI 專案架構，我們可以用相對路徑或直接 import
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.main import reorder_for_attention

@dataclass
class MockRetrievalResult:
    text: str
    chunk_id: str
    source: str
    score: float

def test_reorder_for_attention_basic():
    """
    驗證 Best-First & Second-Last 排序邏輯：
    最高分放第一位，次高分放最後一位，其餘放中間。
    """
    docs = [
        MockRetrievalResult(text="Doc1", chunk_id="1", source="s1", score=0.95),
        MockRetrievalResult(text="Doc2", chunk_id="2", source="s2", score=0.85),
        MockRetrievalResult(text="Doc3", chunk_id="3", source="s3", score=0.75),
        MockRetrievalResult(text="Doc4", chunk_id="4", source="s4", score=0.65),
        MockRetrievalResult(text="Doc5", chunk_id="5", source="s5", score=0.55),
    ]
    
    reordered = reorder_for_attention(docs)
    
    assert len(reordered) == 5
    assert reordered[0].chunk_id == "1"  # 最高分第一位
    assert reordered[-1].chunk_id == "2" # 次高分最後一位
    assert reordered[1].chunk_id == "3"  # 其餘順序不變
    assert reordered[2].chunk_id == "4"
    assert reordered[3].chunk_id == "5"

def test_reorder_for_attention_edge_cases():
    """
    驗證邊界條件：1 篇、2 篇文獻時的表現。
    """
    # 只有 1 篇
    docs_1 = [MockRetrievalResult(text="Doc1", chunk_id="1", source="s1", score=0.95)]
    assert reorder_for_attention(docs_1)[0].chunk_id == "1"
    
    # 只有 2 篇
    docs_2 = [
        MockRetrievalResult(text="Doc1", chunk_id="1", source="s1", score=0.95),
        MockRetrievalResult(text="Doc2", chunk_id="2", source="s2", score=0.85)
    ]
    reordered_2 = reorder_for_attention(docs_2)
    assert reordered_2[0].chunk_id == "1"
    assert reordered_2[-1].chunk_id == "2"
