from types import SimpleNamespace

from backend.core import SearchMode
from backend.policies import SearchPolicy
from backend.services.turn_plan_service import (
    BehaviorAnalysisLevel,
    TurnPlanService,
    TurnRoute,
)


def _settings(**overrides):
    values = {
        "foreground_model_call_budget_general": 2,
        "foreground_model_call_budget_learning": 3,
        "enable_policy_classifier_for_general_chat": False,
        "enable_sync_long_term_memory_for_general_chat": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _search_decision(query, mode=SearchMode.NEVER):
    return SearchPolicy().evaluate(query, mode)


def test_greeting_uses_static_route_without_foreground_model_work():
    query = "你好"

    plan = TurnPlanService().plan(
        user_message=query,
        use_rag=False,
        has_attachments=False,
        search_decision=_search_decision(query),
        settings=_settings(),
    )

    assert plan.route == TurnRoute.STATIC_GREETING
    assert plan.behavior_analysis_level == BehaviorAnalysisLevel.RULE_ONLY
    assert plan.requires_policy_classifier is False
    assert plan.allow_long_term_memory_query is False


def test_general_chat_does_not_require_policy_classifier_by_default():
    query = "今天心情有點普通"

    plan = TurnPlanService().plan(
        user_message=query,
        use_rag=False,
        has_attachments=False,
        search_decision=_search_decision(query),
        settings=_settings(),
    )

    assert plan.route == TurnRoute.GENERAL_CHAT
    assert plan.requires_policy_classifier is False
    assert plan.allow_long_term_memory_query is False
    assert plan.requires_suggestions is True


def test_learning_question_allows_policy_classifier_but_not_general_long_term_memory():
    query = "請解釋 dependency injection"

    plan = TurnPlanService().plan(
        user_message=query,
        use_rag=False,
        has_attachments=False,
        search_decision=_search_decision(query),
        settings=_settings(),
    )

    assert plan.route == TurnRoute.LEARNING_HELP
    assert plan.requires_policy_classifier is True
    assert plan.allow_long_term_memory_query is False


def test_explicit_recall_allows_foreground_long_term_memory():
    query = "你還記得我之前提過的學習偏好嗎？"

    plan = TurnPlanService().plan(
        user_message=query,
        use_rag=False,
        has_attachments=False,
        search_decision=_search_decision(query),
        settings=_settings(),
    )

    assert plan.route == TurnRoute.EXPLICIT_MEMORY_RECALL
    assert plan.allow_long_term_memory_query is True
    assert plan.requires_policy_classifier is True


def test_never_search_mode_keeps_external_search_forbidden():
    query = "今天最新新聞是什麼？"

    plan = TurnPlanService().plan(
        user_message=query,
        use_rag=False,
        has_attachments=False,
        search_decision=_search_decision(query, SearchMode.NEVER),
        settings=_settings(),
    )

    assert plan.route in {TurnRoute.GENERAL_CHAT, TurnRoute.LEARNING_HELP}
    assert plan.requires_web_query_rewrite is False


def test_auto_web_required_route_allows_query_rewrite():
    query = "今天最新新聞是什麼？"

    plan = TurnPlanService().plan(
        user_message=query,
        use_rag=False,
        has_attachments=False,
        search_decision=_search_decision(query, SearchMode.AUTO),
        settings=_settings(),
    )

    assert plan.route == TurnRoute.WEB_REQUIRED
    assert plan.requires_web_query_rewrite is True
    assert plan.allow_long_term_memory_query is False
