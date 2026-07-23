from pelican_mvp.domain_skill import DomainSkill
from pelican_mvp.models import LearnerIntakeProfile, LearningIntent
from pelican_mvp.skill_compiler import compile_learning_plan
from pelican_mvp.skill_loader import load_catalog_skill


def test_compile_uncalibrated_deep_learning_starts_with_foundation() -> None:
    skill = load_catalog_skill("深度學習")
    profile = LearnerIntakeProfile(topic="深度學習")

    plan = compile_learning_plan(skill, profile)

    assert [node.node_id for node in plan.nodes] == [
        "math_intuition",
        "vectors_tensors",
        "functions_transformations",
    ]
    assert "MLP" not in plan.nodes[0].label
    assert all(node.prerequisites == () for node in plan.nodes)
    assert plan.diagnostics[0].node_id == "math_intuition"
    assert plan.diagnostics[0].expected_answer not in plan.diagnostics[0].prompt


def test_compile_same_profile_is_deterministic() -> None:
    skill = load_catalog_skill("deep learning")
    profile = LearnerIntakeProfile(
        topic="deep learning",
        intent=LearningIntent.IMPLEMENTATION,
        level_hint="beginner",
        intake_turns=1,
    )

    first = compile_learning_plan(skill, profile)
    second = compile_learning_plan(skill, profile)

    assert first.plan_id == second.plan_id
    assert [node.node_id for node in first.nodes] == [node.node_id for node in second.nodes]
    assert first.to_dict()["nodes"] == second.to_dict()["nodes"]


def test_compile_implementation_route_keeps_mlp_downstream() -> None:
    skill = load_catalog_skill("深度學習")
    profile = LearnerIntakeProfile(
        topic="深度學習",
        intent=LearningIntent.IMPLEMENTATION,
        level_hint="beginner",
        intake_turns=1,
    )

    plan = compile_learning_plan(skill, profile)
    node_ids = [node.node_id for node in plan.nodes]
    mlp = next(node for node in plan.nodes if node.node_id == "mlp_implementation")

    assert node_ids.index("math_intuition") < node_ids.index("mlp_implementation")
    assert "optimization" in mlp.prerequisites


def test_compile_project_and_assessment_routes_differ() -> None:
    skill = load_catalog_skill("深度學習")
    project = compile_learning_plan(
        skill,
        LearnerIntakeProfile(
            topic="深度學習",
            intent=LearningIntent.PROJECT,
            level_hint="beginner",
            intake_turns=1,
        ),
    )
    assessment = compile_learning_plan(
        skill,
        LearnerIntakeProfile(
            topic="深度學習",
            intent=LearningIntent.ASSESSMENT,
            level_hint="beginner",
            intake_turns=1,
        ),
    )

    assert "project_workflow" in {node.node_id for node in project.nodes}
    assert "assessment_review" in {node.node_id for node in assessment.nodes}
    assert [node.node_id for node in project.nodes] != [node.node_id for node in assessment.nodes]


def test_compile_does_not_infer_mastery_from_goal_statement() -> None:
    skill = load_catalog_skill("深度學習")
    profile = LearnerIntakeProfile(
        topic="深度學習",
        goal_summary="我已經很強，只想快速看 MLP",
        intent=LearningIntent.IMPLEMENTATION,
        level_hint="beginner",
        intake_turns=1,
    )

    plan = compile_learning_plan(skill, profile)

    assert plan.nodes[0].node_id == "math_intuition"
    assert all(node.node_id != "mlp_implementation" or node.prerequisites for node in plan.nodes)
