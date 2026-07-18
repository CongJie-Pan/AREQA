import pytest
import tempfile
from pelican_mvp.curriculum import CURRICULUMS
from pelican_mvp.engine import PelicanEngine

def test_chinese_history_curriculum_loads() -> None:
    assert "chinese_history" in CURRICULUMS
    curriculum = CURRICULUMS["chinese_history"]
    
    assert len(curriculum.nodes) == 6
    assert "hist_basics" in curriculum.nodes
    assert curriculum.nodes["ming_fall"].prerequisites == ("ming_decline",)

def test_chinese_history_engine_flow() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = PelicanEngine(tmpdir, learner_id="test_history", mode="rule", curriculum_id="chinese_history")
        
        # Diagnosis phase starts with the deepest leaf node according to successor-first
        # Leaves: ming_fall (priority 50), so it should start there.
        outcome = engine.start()
        assert outcome.node_id == "ming_fall"
        
        # We answer correctly
        outcome = engine.respond("吳三桂")
        assert outcome.category.value == "correct"
        # It should complete diagnosis phase immediately since ming_fall correctness 
        # infers all prerequisites mastered.
        assert engine.state.phase == "tutoring"
        
        # First task step
        assert engine.state.current_node_id == "ming_founding"
        assert "明朝建立" in engine.state.current_prompt

        # We answer incorrectly
        outcome = engine.respond("李自成")
        assert outcome.category.value == "incorrect"
        assert outcome.strategy == "correction"
        assert "明朝建立" in outcome.message
