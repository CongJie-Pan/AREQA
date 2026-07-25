from pathlib import Path

from pelican_mvp.agents import SkillAgent, SkillAgentInput
from pelican_mvp.domain_skill import DomainCategory
from pelican_mvp.llm import LlmHealth
from pelican_mvp.models import LearnerIntakeProfile, LearningIntent, ProposalValidationStatus
from pelican_mvp.skill_generator import DomainSkillGenerator


class FakeSpringAutumnLlm:
    @property
    def available(self) -> bool:
        return True

    def model_route_for_category(self, category: DomainCategory) -> str:
        return f"fake/{category.value}"

    def check_route_health(self, model_route: str) -> LlmHealth:
        return LlmHealth(True, ("ok",))

    def generate_domain_skill_payload(
        self,
        topic: str,
        category: DomainCategory,
        *,
        model_route: str | None = None,
        repair_issues: tuple[str, ...] = (),
        goal_context: str = "",
    ) -> dict:
        return spring_autumn_payload()


class OfflineHumanitiesLlm(FakeSpringAutumnLlm):
    @property
    def available(self) -> bool:
        return False


def spring_autumn_payload() -> dict:
    return {
        "skill_id": "spring_autumn_history",
        "version": "0.1.0",
        "title": "中國春秋時期歷史脈絡",
        "domain_category": "humanities",
        "lifecycle": "runtime_generated",
        "supported_topics": ["中國春秋時期歷史", "春秋五霸", "諸侯爭霸"],
        "intent_types": ["conceptual"],
        "prerequisites": [
            {
                "concept_id": "zhou_authority",
                "label": "周王室權威下降",
                "prerequisites": [],
                "description": "理解春秋時期名義共主和實際控制力的落差。",
            },
            {
                "concept_id": "fengjian_order",
                "label": "分封秩序與諸侯互動",
                "prerequisites": ["zhou_authority"],
                "description": "理解封建秩序如何約束又放大諸侯競爭。",
            },
            {
                "concept_id": "hegemon_politics",
                "label": "諸侯爭霸與霸主秩序",
                "prerequisites": ["fengjian_order"],
                "description": "理解霸主如何在尊王名義下重組秩序。",
            },
            {
                "concept_id": "ritual_breakdown",
                "label": "禮樂秩序鬆動",
                "prerequisites": ["zhou_authority"],
                "description": "理解禮樂規範弱化後，政治衝突如何更頻繁出現。",
            },
            {
                "concept_id": "state_reform",
                "label": "諸侯國改革與軍事競爭",
                "prerequisites": ["fengjian_order"],
                "description": "理解各國如何透過內政與軍事改革提升競爭力。",
            },
            {
                "concept_id": "transition_to_warring_states",
                "label": "春秋到戰國的轉變",
                "prerequisites": ["hegemon_politics", "state_reform"],
                "description": "理解爭霸政治如何逐步轉向更激烈的兼併戰爭。",
            },
        ],
        "calibration_questions": [
            {
                "question_id": "goal",
                "prompt": "你想從政治秩序、人物事件，還是制度變遷理解春秋？",
                "intent_targets": ["conceptual"],
                "level_targets": ["beginner", "intermediate"],
            }
        ],
        "canonical_path": {
            "conceptual": [
                "zhou_authority",
                "fengjian_order",
                "ritual_breakdown",
                "hegemon_politics",
                "state_reform",
                "transition_to_warring_states",
            ],
        },
        "diagnostic_rules": [
            {
                "rule_id": "diag_zhou",
                "concept_id": "zhou_authority",
                "prompt": "春秋時期為什麼周王室權威下降會讓諸侯更容易爭霸？",
                "expected_answer": "周王室控制力下降，諸侯在名義秩序下競爭主導權",
            },
            {
                "rule_id": "diag_fengjian",
                "concept_id": "fengjian_order",
                "prompt": "分封秩序如何影響諸侯之間的互動？",
                "expected_answer": "分封提供名分和義務，也形成諸侯競爭的框架",
            },
            {
                "rule_id": "diag_hegemon",
                "concept_id": "hegemon_politics",
                "prompt": "春秋霸主通常如何取得政治正當性？",
                "expected_answer": "以尊王或維護秩序名義號召諸侯",
            },
            {
                "rule_id": "diag_ritual_breakdown",
                "concept_id": "ritual_breakdown",
                "prompt": "禮樂秩序鬆動為什麼會讓諸侯衝突增加？",
                "expected_answer": "共同規範弱化後，諸侯更容易用實力解決爭端",
            },
            {
                "rule_id": "diag_state_reform",
                "concept_id": "state_reform",
                "prompt": "諸侯國改革和軍事競爭有什麼關係？",
                "expected_answer": "改革能提高動員、財政或軍事能力，使諸侯競爭更激烈",
            },
            {
                "rule_id": "diag_transition",
                "concept_id": "transition_to_warring_states",
                "prompt": "春秋政治如何逐漸走向戰國式兼併？",
                "expected_answer": "霸主協調秩序減弱，國家改革和軍事競爭推動兼併戰爭",
            },
        ],
        "teaching_moves": [
            {
                "move_id": "context_first",
                "strategy": "explanation",
                "description": "先建立周王室和諸侯關係，再進入事件細節。",
            }
        ],
        "remediation_paths": [
            {"signal": "unknown", "action": "scaffold_prerequisite", "target": "zhou_authority"},
            {"signal": "too_detailed", "action": "recalibrate_level", "target": "goal"},
            {"signal": "too_easy", "action": "accelerate", "target": "fengjian_order"},
            {"signal": "project_goal", "action": "switch_path", "target": "conceptual"},
            {"signal": "assessment_goal", "action": "switch_path", "target": "conceptual"},
        ],
        "teaching_methodology": {
            "context_first": "先講周王室權威與分封秩序，再連到諸侯爭霸。",
        },
        "assessment_policy": {
            "mode": "formative",
            "education_only": True,
            "notes": "Humanities education only.",
        },
        "safety_notes": ["Avoid overconfident claims about disputed historical interpretations."],
    }


def test_skill_agent_accepts_spring_autumn_runtime_skill(tmp_path: Path) -> None:
    agent = SkillAgent(DomainSkillGenerator(FakeSpringAutumnLlm(), artifact_root=tmp_path))
    profile = LearnerIntakeProfile(
        topic="中國春秋時期歷史",
        goal_summary="想理解春秋時期的政治秩序和諸侯爭霸脈絡",
        intent=LearningIntent.CONCEPTUAL,
        level_hint="beginner",
        domain_category="humanities",
        model_route="fake/humanities",
        intake_turns=3,
    )

    proposal = agent.propose_skill(SkillAgentInput(profile, force_regenerate=True))

    labels = " ".join(item.label for item in proposal.skill.prerequisites)
    assert proposal.route == "fake/humanities"
    assert proposal.used_fallback is False
    assert proposal.attempts[-1].validation_status is ProposalValidationStatus.ACCEPTED
    assert "周王室權威" in labels
    assert "諸侯爭霸" in labels
    assert "深度學習" not in labels


def test_skill_agent_marks_known_domain_offline_fallback(tmp_path: Path) -> None:
    agent = SkillAgent(DomainSkillGenerator(OfflineHumanitiesLlm(), artifact_root=tmp_path))
    profile = LearnerIntakeProfile(
        topic="中國春秋時期歷史",
        goal_summary="想理解歷史脈絡",
        intent=LearningIntent.CONCEPTUAL,
        level_hint="beginner",
        domain_category="humanities",
        intake_turns=3,
    )

    proposal = agent.propose_skill(SkillAgentInput(profile, force_regenerate=True))

    assert proposal.route == "generic:humanities"
    assert proposal.used_fallback is True
    assert proposal.attempts[-1].validation_status is ProposalValidationStatus.FALLBACK_USED
