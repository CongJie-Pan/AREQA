from pathlib import Path

from pelican_mvp.agents import SkillAgent
from pelican_mvp.engine import PelicanEngine
from pelican_mvp.models import BoundedTutorProposal, DiagnosticQuestion
from pelican_mvp.planner import LearningPlanner
from pelican_mvp.skill_generator import DomainSkillGenerator
from test_skill_agent import FakeSpringAutumnLlm


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


class FakeTutorProposalLlm:
    @property
    def available(self) -> bool:
        return True

    def tutor_proposal(self, **kwargs) -> BoundedTutorProposal:
        signal = kwargs["evidence_signal"]
        node_id = kwargs["node_id"]
        strategy = kwargs["strategy"].value
        if signal == "too_detailed":
            return BoundedTutorProposal(
                response="我們先退回高層直覺：圖片先變成數字，模型才有東西可以比較。你覺得第一步像不像翻譯？",
                pedagogical_move="scope_recalibration",
                summary="Recalibrate abstraction level for the current node.",
                node_id=node_id,
                strategy=strategy,
                evidence_signal=signal,
            )
        return BoundedTutorProposal(
            response="先直接講重點：圖片可以被拆成一格格數字，每格代表局部亮度或顏色。你先確認這是在說資料表示嗎？",
            pedagogical_move="scaffold",
            summary="Scaffold the active node after an unknown signal.",
            node_id=node_id,
            strategy=strategy,
            evidence_signal=signal,
        )


def calibrated_deep_learning_engine(tmp_path: Path) -> PelicanEngine:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")
    engine.respond("想理解原理")
    engine.respond("完全沒有基礎")
    return engine


def spring_autumn_engine(tmp_path: Path) -> PelicanEngine:
    engine = PelicanEngine(tmp_path)
    fake_llm = FakeSpringAutumnLlm()
    engine.llm = fake_llm
    engine.planner = LearningPlanner(engine.llm)
    engine.skill_agent = SkillAgent(DomainSkillGenerator(engine.llm, artifact_root=tmp_path / "artifacts"))
    engine.start()
    engine.respond("中國春秋時期歷史")
    engine.respond("想理解春秋時期的政治秩序和諸侯爭霸脈絡")
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
    assert [node.node_id for node in engine.state.learning_plan.nodes] == [
        "math_intuition",
        "vectors_tensors",
        "functions_transformations",
    ]
    assert "MLP" not in diagnostic.message


def test_spring_autumn_skill_agent_flow_uses_history_diagnostic(tmp_path: Path) -> None:
    engine = spring_autumn_engine(tmp_path)

    diagnostic = engine.respond("只有大概聽過春秋五霸，沒有系統學過")

    labels = " ".join(node.label for node in engine.state.learning_plan.nodes)
    skill_proposals = [item for item in engine.state.agent_proposals if item.role.value == "skill_agent"]
    assert diagnostic.node_id == "zhou_authority"
    assert "春秋" in diagnostic.message
    assert "周王室" in diagnostic.message
    assert "周王室權威" in labels
    assert "諸侯爭霸" in labels
    assert "深度學習" not in diagnostic.message
    assert "模型" not in diagnostic.message
    assert skill_proposals
    assert skill_proposals[-1].validation_status.value == "accepted"


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
    assert "先直接講" in outcome.message
    assert "重點是" in outcome.message
    assert "不跳到下一個診斷題" in outcome.next_reason
    assert engine.state.phase == "tutoring"
    assert engine.state.direct_evidence[-1].signal == "unknown"


def test_tutoring_control_signals_after_mastery_do_not_overwrite_progress(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)
    mastered_node = engine.state.current_node_id

    correct = engine.respond("用來衡量預測與目標之間的差距")

    assert correct.node_id == "vectors_tensors"
    assert engine.state.phase == "diagnosis"
    assert engine.state.nodes[mastered_node].status.value == "mastered"
    assert "圖片、文字或表格資料" in correct.message

    unknown = engine.respond("我不知道")

    assert unknown.node_id == "vectors_tensors"
    assert "先直接講" in unknown.message
    assert "不跳到下一個診斷題" in unknown.next_reason
    assert engine.state.direct_evidence[-1].signal == "unknown"
    assert engine.state.nodes[mastered_node].status.value == "mastered"
    assert engine.state.nodes["vectors_tensors"].status.value == "not_mastered"

    too_detailed = engine.respond("這太細了，我完全沒有基礎")

    assert too_detailed.node_id == "vectors_tensors"
    assert "太細" in too_detailed.message
    assert "只懂數字的機器" in too_detailed.message
    assert "數學直覺與誤差觀念" not in too_detailed.message
    assert "重新校準抽象層級" in too_detailed.next_reason
    assert engine.state.direct_evidence[-1].signal == "too_detailed"
    assert engine.state.nodes[mastered_node].status.value == "mastered"


def test_llm_mode_records_distinct_bounded_tutor_proposals_for_control_signals(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)
    engine.state.mode = "llm"
    engine.llm = FakeTutorProposalLlm()
    engine.respond("用來衡量預測與目標之間的差距")

    unknown = engine.respond("我不知道")
    unknown_proposal = engine.state.agent_proposals[-1]

    too_detailed = engine.respond("這太細了，我完全沒有基礎")
    too_detailed_proposal = engine.state.agent_proposals[-1]

    assert unknown.message != too_detailed.message
    assert unknown_proposal.artifact_type == "tutor_proposal"
    assert unknown_proposal.pedagogical_move == "scaffold"
    assert unknown_proposal.validation_status.value == "accepted"
    assert "unknown signal" in unknown_proposal.display_summary
    assert too_detailed_proposal.artifact_type == "tutor_proposal"
    assert too_detailed_proposal.pedagogical_move == "scope_recalibration"
    assert too_detailed_proposal.validation_status.value == "accepted"
    assert "Recalibrate" in too_detailed_proposal.display_summary


def test_repeated_tutoring_failures_render_from_base_prompt(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)
    engine.respond("用來衡量預測與目標之間的差距")
    first = engine.respond("載入數據")

    second = engine.respond("還是不對")

    assert first.message.count("請只聚焦") <= 1
    assert second.message.count("請只聚焦") <= 1


def test_generated_skill_missed_diagnostic_records_tutor_proposal(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)
    current_node = engine.state.current_node_id

    outcome = engine.respond("載入數據")

    proposal = engine.state.agent_proposals[-1]
    assert outcome.node_id == current_node
    assert proposal.artifact_type == "tutor_proposal"
    assert proposal.node_id == current_node
    assert proposal.validation_status.value == "fallback_used"
    assert proposal.final_message_preview
    assert engine.state.phase == "tutoring"


def test_too_easy_accelerates_to_next_concept(tmp_path: Path) -> None:
    engine = calibrated_deep_learning_engine(tmp_path)

    outcome = engine.respond("太簡單了")

    assert "加快節奏" in outcome.message
    assert outcome.next_reason.startswith("too_easy")
    assert engine.state.direct_evidence[-1].signal == "too_easy"


def test_generated_plan_correct_leaf_infers_prerequisites_as_metadata(tmp_path: Path) -> None:
    engine = PelicanEngine(tmp_path)
    engine.start()
    engine.respond("深度學習")
    engine.respond("程式實作")
    engine.respond("已經有實作經驗")

    assert engine.state.current_node_id == "mlp_implementation"
    outcome = engine.respond("讓模型能表示非線性關係")

    assert any("由子節點推定" in change for change in outcome.state_changes)
    assert engine.state.nodes["mlp_implementation"].status.value == "mastered"
    assert engine.state.nodes["math_intuition"].status.value == "inferred_mastered"
    assert engine.state.phase == "tutoring"
    assert engine.state.current_node_id == "math_intuition"


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
