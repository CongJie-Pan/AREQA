import pytest
import math
from backend.compaction import calculate_activation_score, is_user_profile

def test_high_decay_short_time():
    # Decay=9 (long lasting), Age=0.1 days, Confidence=8
    score = calculate_activation_score(confidence=8, decay=9, age_days=0.1)
    
    # 11 - 9 = 2. K=2.0
    # gamma = -2 * 2.0 * 0.1 = -0.4
    # score = 8 * exp(-0.4) = 8 * 0.67 = 5.36
    assert math.isclose(score, 8 * math.exp(-0.4), rel_tol=1e-5)

def test_low_decay_long_time():
    # Decay=2 (short lived), Age=5 days, Confidence=8
    score = calculate_activation_score(confidence=8, decay=2, age_days=5.0)
    
    # 11 - 2 = 9. K=2.0
    # gamma = -9 * 2.0 * 5.0 = -90
    # score = 8 * exp(-90) = essentially 0
    assert score < 1e-10

def test_user_profile_skip():
    # user profile should be skipped
    assert is_user_profile("user_profile") == True
    assert is_user_profile("hot_memory_key") == False
