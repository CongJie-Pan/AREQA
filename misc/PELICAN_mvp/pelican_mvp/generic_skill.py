"""Deterministic generic domain skills used when runtime generation fails.

This module owns the fail-closed bridge between the runtime skill generator and
the teaching engine. It deliberately creates a valid ``DomainSkill`` rather than
a legacy topic plan so downstream diagnosis, remediation templates, and EDF/GUM
metadata remain skill-backed even when the model cannot produce a valid expert
skill. The generated payload contains only bounded topic text and generic domain
teaching structure; it is not intended to become an approved catalog asset.
"""

from __future__ import annotations

import re

from .domain_skill import DomainCategory, DomainSkill


def build_generic_domain_skill(topic: str, category: DomainCategory) -> DomainSkill:
    """Build a validated skill-backed fallback for a resolved teaching domain.

    The generic skill is intentionally domain-level rather than topic-specific
    expert content. It prevents a failed runtime generation from silently falling
    back to the legacy one-node plan while keeping all later diagnosis and
    remediation behavior inside the DomainSkill contract.

    Args:
        topic: Learner-requested topic after upstream normalization.
        category: Resolved high-level teaching category. Unknown categories are
            treated as STEM by the private payload selector because unknown
            topics should normally be rejected before reaching this function.

    Returns:
        A strict ``DomainSkill`` instance that can pass the existing validator
        and compiler without LLM access.

    Raises:
        DomainSkillError: If the fallback payload accidentally violates the
            strict skill schema. This is intentionally not swallowed because a
            broken generic skill would make the recovery path unsafe.
    """
    topic_clean = re.sub(r"\s+", " ", topic).strip()[:100] or "預設主題"
    payload = _payload_for_category(topic_clean, category)
    return DomainSkill.from_dict(payload)


def _payload_for_category(topic: str, category: DomainCategory) -> dict:
    """Select the category-specific generic payload shape for a topic."""
    if category is DomainCategory.HUMANITIES:
        return _humanities_payload(topic)
    if category is DomainCategory.BUSINESS:
        return _business_payload(topic)
    if category is DomainCategory.LANGUAGE:
        return _language_payload(topic)
    return _stem_payload(topic)


def _base_payload(topic: str, category: DomainCategory, concepts: list[tuple[str, str, str]]) -> dict:
    """Build the common DomainSkill payload shared by generic domain fallbacks."""
    prerequisites = []
    diagnostics = []
    task_steps = []
    for index, (concept_id, label, description) in enumerate(concepts):
        prerequisites.append(
            {
                "concept_id": concept_id,
                "label": label,
                # Generic fallbacks avoid hard prerequisite edges so the
                # successor-first selector starts with the first low-load concept
                # instead of treating the final broad concept as the only leaf.
                "prerequisites": [],
                "description": description,
            }
        )
        diagnostics.append(
            {
                "rule_id": f"diag_{concept_id}",
                "concept_id": concept_id,
                "prompt": f"請用一句話說明「{label}」在學習「{topic}」時主要幫助你理解什麼？",
                "expected_answer": description,
                "tests_single_concept": True,
            }
        )
        task_steps.append(
            {
                "step_id": f"practice_{concept_id}",
                "node_id": concept_id,
                "label": label,
                "prompt": f"請整理「{label}」的核心重點，並舉一個和「{topic}」相關的例子。",
                "expected": description,
            }
        )

    path = [item[0] for item in concepts]
    first_id = path[0]
    last_id = path[-1]
    return {
        "skill_id": f"generic_{category.value}",
        "version": "0.1.0",
        "title": f"Generic {category.value.title()} Learning Skill",
        "domain_category": category.value,
        "lifecycle": "validated_generated",
        "supported_topics": [topic],
        "intent_types": ["conceptual", "explanatory", "assessment"],
        "prerequisites": prerequisites,
        "calibration_questions": [
            {
                "question_id": "goal",
                "prompt": f"你想從哪個角度理解「{topic}」？",
                "intent_targets": ["conceptual", "explanatory", "assessment"],
                "level_targets": ["beginner", "intermediate"],
            }
        ],
        "canonical_path": {
            "conceptual": path,
            "explanatory": path,
            "assessment": path,
        },
        "diagnostic_rules": diagnostics,
        "teaching_moves": [
            {
                "move_id": "reframe",
                "strategy": "simplification",
                "description": "把學生答錯的概念改寫成更高層的理解問題。",
            },
            {
                "move_id": "scaffold",
                "strategy": "decomposition",
                "description": "先補上前置脈絡，再回到當前概念。",
            },
        ],
        "remediation_paths": [
            {"signal": "unknown", "action": "scaffold_prerequisite", "target": first_id},
            {"signal": "too_detailed", "action": "recalibrate_level", "target": "goal"},
            {"signal": "too_easy", "action": "accelerate", "target": last_id},
            {"signal": "project_goal", "action": "switch_path", "target": "conceptual"},
            {"signal": "assessment_goal", "action": "switch_path", "target": "assessment"},
        ],
        "assessment_policy": {
            "mode": "formative",
            "education_only": True,
            "notes": "This generic fallback skill supports education and formative learning only.",
        },
        "teaching_methodology": {
            "calibration": "先確認學習角度，再用低負荷問題找出起點。",
            "remediation": "答錯時停在目前概念，改用更高層的脈絡問題補架。",
        },
        "remediation_templates": {
            concept_id: f"我們先停在「{{label}}」。先不要追求標準答案，也不用完整重述；你可以先選一個關鍵原因、轉折點，或影響，說說它如何幫你理解「{topic}」。"
            for concept_id, _label, _description in concepts
        },
        "safety_notes": ["Generic fallback skills must remain broad and formative."],
    }


def _humanities_payload(topic: str) -> dict:
    """Return a broad humanities fallback that starts from context and scope."""
    return _base_payload(
        topic,
        DomainCategory.HUMANITIES,
        [
            ("scope_context", "範圍與時代脈絡", "建立主題的時間範圍、背景與基本脈絡"),
            ("key_people_events", "關鍵人物與事件", "辨識推動變化的人物、事件與因果關係"),
            ("interpretation_perspective", "詮釋角度與意義", "從制度、文化或思想角度解釋歷史意義"),
        ],
    )


def _business_payload(topic: str) -> dict:
    """Return a broad business fallback centered on decision framing."""
    return _base_payload(
        topic,
        DomainCategory.BUSINESS,
        [
            ("problem_frame", "問題框架", "界定商業或金融問題的目標與限制"),
            ("metric_signal", "指標與訊號", "辨識可用來判斷情況的關鍵數字或訊號"),
            ("decision_tradeoff", "決策取捨", "比較方案、風險與行動後果"),
        ],
    )


def _language_payload(topic: str) -> dict:
    """Return a broad language-learning fallback centered on use cases."""
    return _base_payload(
        topic,
        DomainCategory.LANGUAGE,
        [
            ("usage_goal", "使用情境", "確認語言學習要服務的溝通場景"),
            ("input_pattern", "語言輸入模式", "辨識常見句型、語感或語料模式"),
            ("output_practice", "輸出練習", "把理解轉成口說、寫作或應答表達"),
        ],
    )


def _stem_payload(topic: str) -> dict:
    """Return a broad STEM fallback for unknown or technical categories."""
    return _base_payload(
        topic,
        DomainCategory.STEM,
        [
            ("core_concept", "核心概念", "理解主題解決的基本問題"),
            ("mechanism", "運作機制", "說明概念如何一步步產生結果"),
            ("application", "應用與檢查", "把概念用在簡單例子並檢查結果"),
        ],
    )
