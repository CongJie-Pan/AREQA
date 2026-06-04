import pytest
from backend.main import reorder_for_attention

class MockChunk:
    def __init__(self, score, id):
        self.score = score
        self.id = id
        
    def __repr__(self):
        return f"MockChunk(id={self.id}, score={self.score})"

def test_reorder_for_attention_normal_case():
    """
    Test that the top 1 is placed at the front, top 2 is placed at the back,
    and the rest are in the middle.
    """
    results = [
        MockChunk(0.9, 1),
        MockChunk(0.8, 2),
        MockChunk(0.7, 3),
        MockChunk(0.6, 4),
        MockChunk(0.5, 5)
    ]
    
    reordered = reorder_for_attention(results)
    
    # Assert Best-First & Second-Last ordering
    assert len(reordered) == 5
    assert reordered[0].id == 1  # 1st best (score 0.9)
    assert reordered[-1].id == 2 # 2nd best (score 0.8)
    
    # Assert Middle items are present
    assert reordered[1].id == 3
    assert reordered[2].id == 4
    assert reordered[3].id == 5

def test_reorder_for_attention_two_items():
    """
    Test that ordering handles edge case of exactly 2 items.
    It should return them as is without modifying or failing.
    """
    results = [
        MockChunk(0.9, 1),
        MockChunk(0.8, 2)
    ]
    
    reordered = reorder_for_attention(results)
    
    assert len(reordered) == 2
    assert reordered[0].id == 1
    assert reordered[1].id == 2

def test_reorder_for_attention_one_item():
    """
    Test that ordering handles edge case of 1 item.
    """
    results = [MockChunk(0.9, 1)]
    
    reordered = reorder_for_attention(results)
    
    assert len(reordered) == 1
    assert reordered[0].id == 1

def test_reorder_for_attention_empty():
    """
    Test empty input.
    """
    results = []
    reordered = reorder_for_attention(results)
    assert len(reordered) == 0
