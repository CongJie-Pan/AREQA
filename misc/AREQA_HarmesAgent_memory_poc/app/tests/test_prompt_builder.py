import pytest
from app.prompt_builder import build_system_prompt

def test_empty_memory_assembly():
    base_prompt = "You are a helpful assistant."
    
    # Test with entirely empty snapshots
    result = build_system_prompt(base_prompt, "", "")
    assert result == base_prompt
    
    # Test with only one snapshot
    result_user = build_system_prompt(base_prompt, "# USER PROFILE\n- Name is Bob", "")
    assert result_user == "You are a helpful assistant.\n\n# USER PROFILE\n- Name is Bob"
    
    result_memory = build_system_prompt(base_prompt, "", "# MEMORY\n- Has a dog")
    assert result_memory == "You are a helpful assistant.\n\n# MEMORY\n- Has a dog"

def test_combination_order():
    base_prompt = "[Identity]\nYou are Hermes."
    user_snapshot = "[Stable Tools]\n# USER PROFILE\n- Developer"
    memory_snapshot = "[Volatile Memory]\n# MEMORY\n- Likes Python"
    
    result = build_system_prompt(base_prompt, user_snapshot, memory_snapshot)
    
    expected = (
        "[Identity]\nYou are Hermes.\n\n"
        "[Stable Tools]\n# USER PROFILE\n- Developer\n\n"
        "[Volatile Memory]\n# MEMORY\n- Likes Python"
    )
    
    assert result == expected
    
    # Verify exact block indices to ensure order
    assert result.find("[Identity]") < result.find("[Stable Tools]")
    assert result.find("[Stable Tools]") < result.find("[Volatile Memory]")
