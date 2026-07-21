import pytest
from pathlib import Path

from pelican_mvp.engine import PelicanEngine
from pelican_mvp.domain_skill import DomainCategory
from pelican_mvp.llm import IntakeSemanticSignal
from pelican_mvp.models import KnowledgeStatus, ResponseCategory, TutoringStrategy


def test_unknown_student_is_diagnosed_before_original_problem(tmp_path: Path) -> None:
    # Fixture explicitly selected
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    outcome = engine.start()

    assert engine.state.phase == "diagnosis"
    assert outcome.node_id == "cnn_conv"
    assert "診斷題" in outcome.message


def test_default_intake_path(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    outcome = engine.start()

    assert engine.state.phase == "onboarding"
    assert "你想學什麼" in outcome.message

    outcome = engine.respond("深度學習")
    assert engine.state.phase == "onboarding"
    assert "怎麼學" in outcome.message

    outcome = engine.respond("想理解原理")
    assert engine.state.phase == "onboarding"
    assert "基礎" in outcome.message

    outcome = engine.respond("完全沒有基礎")
    assert engine.state.phase == "diagnosis"
    assert engine.state.learning_plan is not None
    assert engine.state.learning_plan.topic == "深度學習"
    assert engine.state.current_node_id == "math_intuition"


def test_llm_intake_topic_revision_resets_onboarding_topic(tmp_path: Path) -> None:
    class SemanticLlm:
        available = True

        def intake_question(self, *, topic: str, domain_category: DomainCategory, stage: str, model_route=None):
            return f"{topic} 的 {stage} 問題？"

        def classify_intake_semantics(
            self,
            *,
            current_topic: str,
            answer: str,
            stage: str,
            domain_category: DomainCategory,
            model_route=None,
        ):
            return IntakeSemanticSignal(
                intent="topic_revision",
                confidence=0.94,
                reason_code="explicit_correction",
                new_topic="春秋時期歷史",
            )

    engine = PelicanEngine(tmp_path, mode="llm")
    engine.llm = SemanticLlm()
    engine.start()
    engine.respond("明朝歷史")

    outcome = engine.respond("哦哦 我說錯了是春秋時期的歷史")

    assert "春秋時期歷史" in outcome.message
    assert engine.state.phase == "onboarding"
    assert engine.state.intake_profile.topic == "春秋時期歷史"
    assert engine.state.intake_profile.intake_turns == 1
    assert engine.state.intake_profile.intent.value == "unknown"
    assert engine.state.learning_plan is None


def test_rule_intake_topic_revision_fallback_when_llm_unavailable(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("明朝歷史")

    outcome = engine.respond("我說錯了是春秋時期歷史")

    assert "春秋時期歷史" in outcome.message
    assert engine.state.intake_profile.topic == "春秋時期歷史"
    assert engine.state.intake_profile.intake_turns == 1


def test_rule_mode_completes_problem_and_persists(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
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
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.start()
    engine.respond("8")
    engine.respond("不會")
    engine.respond("5")
    before = engine.state.nodes["cnn_conv"].status
    outcome = engine.respond("show answer")

    assert "不會更新 mastery" in outcome.message
    assert engine.state.nodes["cnn_conv"].status is before


def test_persistent_failure_activates_slow_thinking(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
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
    engine = PelicanEngine(tmp_path, mode="llm", curriculum_id="cnn")

    outcome = engine.start()

    assert engine.state.current_prompt_source == "rule"
    assert "診斷題" in outcome.message

def test_start_when_completed(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, curriculum_id="cnn")
    engine.state.completed = True
    outcome = engine.start()

    assert "已完成" in outcome.message

def test_llm_mode_fallback_on_respond(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    engine = PelicanEngine(tmp_path, mode="llm", curriculum_id="cnn")
    engine.start()
    outcome = engine.respond("100")

    assert outcome is not None
