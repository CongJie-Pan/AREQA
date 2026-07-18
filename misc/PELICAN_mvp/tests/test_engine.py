import pytest
from pathlib import Path

from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import KnowledgeStatus, ResponseCategory, TutoringStrategy


def test_unknown_student_is_diagnosed_before_original_problem(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    outcome = engine.start()

    assert engine.state.phase == "diagnosis"
    assert outcome.node_id == "cnn_conv"
    assert "診斷題" in outcome.message


def test_rule_mode_completes_problem_and_persists(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("8")
    engine.respond("不會")
    diagnosis_done = engine.respond("5")

    assert engine.state.phase == "tutoring"
    assert diagnosis_done.node_id == "cnn_conv"
    engine.respond("26")
    engine.respond("26")
    complete = engine.respond("13")

    assert complete.category is ResponseCategory.CORRECT
    assert engine.state.completed is True
    assert "原題完成" in complete.message
    restored = PelicanEngine(tmp_path)
    assert restored.state.completed is True


def test_show_answer_does_not_change_mastery(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("8")
    engine.respond("不會")
    engine.respond("5")
    before = engine.state.nodes["cnn_conv"].status
    outcome = engine.respond("show answer")

    assert "不會更新 mastery" in outcome.message
    assert engine.state.nodes["cnn_conv"].status is before


def test_persistent_failure_activates_slow_thinking(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("8")
    engine.respond("不會")
    engine.respond("5")
    engine.respond("我不會")
    second = engine.respond("我不會")

    assert second.strategy is TutoringStrategy.DECOMPOSITION
    assert "slow-thinking" in second.next_reason
    assert engine.state.nodes["cnn_conv"].status is KnowledgeStatus.NOT_MASTERED


def test_llm_mode_without_key_uses_reviewed_rule_question(tmp_path: Path, monkeypatch) -> None:
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    engine = PelicanEngine(tmp_path, mode="llm")

    outcome = engine.start()

    assert engine.state.current_prompt_source == "rule"
    assert "診斷題" in outcome.message

def test_start_when_completed(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.state.completed = True
    outcome = engine.start()
    
    assert "已完成" in outcome.message

def test_llm_mode_fallback_on_respond(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    
    engine = PelicanEngine(tmp_path, mode="llm")
    engine.start()
    outcome = engine.respond("100")
    
    assert outcome is not None

