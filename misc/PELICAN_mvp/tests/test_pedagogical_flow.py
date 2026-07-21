from pathlib import Path

from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import DiagnosticQuestion


class FakeDiagnosticLlm:
    @property
    def available(self) -> bool:
        return True

    def verified_diagnostic(self, node_label: str) -> DiagnosticQuestion:
        return DiagnosticQuestion(
            node_id="",
            prompt="LLM BAD QUESTION",
            expected_answer="LLM BAD ANSWER",
            source="llm",
        )

    def intake_question(self, **kwargs) -> None:
        return None


class FakeIntakeLlm:
    @property
    def available(self) -> bool:
        return True

    def intake_question(self, **kwargs) -> str:
        return "LLM 產生的中國歷史前置問題"


def calibrated_deep_learning_engine(tmp_path: Path) -> PelicanEngine:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")
    engine.respond("想理解原理")
    engine.respond("完全沒有基礎")
    return engine


def test_deep_learning_collects_goal_and_level_before_diagnosis(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    first = engine.start()
    second = engine.respond("深度學習")
    third = engine.respond("想理解原理")
    diagnostic = engine.respond("完全沒有基礎")

    assert "你想學什麼" in first.message
    assert "怎麼學" in second.message
    assert "基礎" in third.message
    assert engine.state.phase == "diagnosis"
    assert engine.state.intake_profile.intake_turns == 3
    assert engine.state.intake_profile.intent.value == "conceptual"
    assert engine.state.intake_profile.level_hint == "beginner"
    assert diagnostic.node_id == "math_intuition"
    assert "MLP" not in diagnostic.message


def test_scope_mismatch_recalibrates_without_advancing_node(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)
    current_node = engine.state.current_node_id

    outcome = engine.respond("這太細了吧，我不知道")

    assert outcome.node_id == current_node
    assert "太細" in outcome.message
    assert "不前進" in outcome.next_reason
    assert engine.state.current_node_id == current_node
    assert engine.state.direct_evidence[-1].signal == "too_detailed"
    assert engine.state.nodes[current_node].status.value == "undiagnosed"


def test_unknown_scaffolds_current_prerequisite_not_unrelated_node(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)
    current_node = engine.state.current_node_id

    outcome = engine.respond("不知道")

    assert outcome.node_id == current_node
    assert "先補" in outcome.message
    assert "不跳到下一個診斷題" in outcome.next_reason
    assert engine.state.phase == "tutoring"
    assert engine.state.direct_evidence[-1].signal == "unknown"


def test_too_easy_accelerates_to_next_concept(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)

    outcome = engine.respond("太簡單了")

    assert "加快節奏" in outcome.message
    assert outcome.next_reason.startswith("too_easy")
    assert engine.state.direct_evidence[-1].signal == "too_easy"


def test_generated_plan_correct_leaf_does_not_infer_all_prerequisites(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")
    engine.respond("程式實作")
    engine.respond("已經有實作經驗")

    assert engine.state.current_node_id == "mlp_implementation"
    outcome = engine.respond("讓模型能表示非線性關係")

    assert all("由子節點推定" not in change for change in outcome.state_changes)
    assert engine.state.nodes["mlp_implementation"].status.value == "mastered"
    assert engine.state.nodes["math_intuition"].status.value == "undiagnosed"
    assert engine.state.current_node_id == "optimization"


def test_skill_diagnostic_is_not_overridden_by_llm_mode(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, mode="llm")
    engine.llm = FakeDiagnosticLlm()
    engine.start()
    engine.respond("深度學習")
    engine.respond("理解概念")
    outcome = engine.respond("已經有實作經驗")

    assert outcome.node_id == "math_intuition"
    assert "LLM BAD QUESTION" not in outcome.message
    assert "為什麼需要一個錯誤衡量" in outcome.message
    assert engine.state.current_prompt_source == "skill"
    assert engine.state.activity_log[-1].detail == "skill:math_intuition"


def test_generated_skill_incorrect_stays_on_current_concept(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)
    current_node = engine.state.current_node_id

    outcome = engine.respond("載入數據")

    assert outcome.node_id == current_node
    assert "先停在" in outcome.message
    assert "不跳下一題" in outcome.next_reason
    assert engine.state.phase == "tutoring"
    assert engine.state.nodes[current_node].status.value == "not_mastered"


def test_project_and_assessment_routes_compile_different_paths(tmp_path: Path) -> None:
    project = PelicanEngine(tmp_path / "project")
    project.start()
    project.respond("深度學習")
    project.respond("想做小專案")
    project.respond("學過一點")

    assessment = PelicanEngine(tmp_path / "assessment")
    assessment.start()
    assessment.respond("深度學習")
    assessment.respond("準備考試")
    assessment.respond("學過一點")

    assert "project_workflow" in {node.node_id for node in project.state.learning_plan.nodes}
    assert "assessment_review" in {node.node_id for node in assessment.state.learning_plan.nodes}


def test_legal_knowledge_stays_educational_during_intake(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()

    outcome = engine.respond("法律知識，我想問個案怎麼判")

    assert "不能提供個案法律諮詢" in outcome.message
    assert engine.state.intake_profile.domain_category == "humanities"


def test_humanities_onboarding_uses_domain_specific_questions(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()

    outcome = engine.respond("中國歷史")

    assert "時代脈絡" in outcome.message
    assert "程式實作" not in outcome.message
    assert engine.state.activity_log[-1].detail == "rule:humanities:goal"


def test_llm_mode_can_generate_domain_intake_question(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path, mode="llm")
    engine.llm = FakeIntakeLlm()
    engine.start()

    outcome = engine.respond("中國歷史")

    assert outcome.message == "LLM 產生的中國歷史前置問題"
    assert engine.state.activity_log[-1].detail == "llm:goal"
