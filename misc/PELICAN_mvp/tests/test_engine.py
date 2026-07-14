from pathlib import Path

from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import KnowledgeStatus, ResponseCategory, TutoringStrategy


def test_unknown_student_is_diagnosed_before_original_problem(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    outcome = engine.start()

    assert engine.state.phase == "diagnosis"
    assert outcome.node_id == "set_intersection"
    assert "診斷題" in outcome.message


def test_rule_mode_completes_problem_and_persists(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("{3,4}")
    engine.respond("[-1,3]")
    diagnosis_done = engine.respond("{0,1,...,16}")

    assert engine.state.phase == "tutoring"
    assert diagnosis_done.node_id == "absolute_value"
    engine.respond("[-1,3]")
    engine.respond("{0,1,...,16}")
    complete = engine.respond("{0,1,2,3}")

    assert complete.category is ResponseCategory.CORRECT
    assert engine.state.completed is True
    assert "原題完成" in complete.message
    restored = PelicanEngine(tmp_path)
    assert restored.state.completed is True


def test_show_answer_does_not_change_mastery(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("{3,4}")
    engine.respond("[-1,3]")
    engine.respond("{0,1,...,16}")
    before = engine.state.nodes["absolute_value"].status
    outcome = engine.respond("show answer")

    assert "不會更新 mastery" in outcome.message
    assert engine.state.nodes["absolute_value"].status is before


def test_persistent_failure_activates_slow_thinking(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("{3,4}")
    engine.respond("[-1,3]")
    engine.respond("{0,1,...,16}")
    engine.respond("我不會")
    second = engine.respond("我不會")

    assert second.strategy is TutoringStrategy.DECOMPOSITION
    assert "slow-thinking" in second.next_reason
    assert engine.state.nodes["absolute_value"].status is KnowledgeStatus.NOT_MASTERED


def test_llm_mode_without_key_uses_reviewed_rule_question(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    engine = PelicanEngine(tmp_path, mode="llm")

    outcome = engine.start()

    assert engine.state.current_prompt_source == "rule"
    assert "診斷題" in outcome.message
