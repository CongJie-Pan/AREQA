import pytest
import os
from unittest.mock import patch

def test_settings_loads_defaults():
    """Settings 應在未設定環境變數時回傳所有預設值。"""
    from backend.config import Settings
    s = Settings()
    assert s.rag_max_docs == 7
    assert s.rag_score_drop_tolerance == 0.60
    assert s.rag_absolute_min_score == 0.005
    assert s.rag_reranker_threshold == 0.35
    assert s.model_policy_classifier == "google/gemini-3.1-flash-lite"
    assert s.model_zpd_query == "google/gemini-3.1-flash-lite"
    assert s.model_suggestion == "google/gemini-2.5-flash-lite"
    assert s.model_cold_memory_embedding == "openai/text-embedding-3-small"
    assert s.model_memory_semantic_analyzer == "google/gemini-2.5-flash-lite"
    assert s.memory_semantic_analysis_enabled is False
    assert s.memory_semantic_shadow_mode is True
    assert s.memory_semantic_match_min_confidence == 0.85
    assert s.memory_semantic_external_processing_acknowledged is False
    assert s.enable_turn_plan_runtime is False
    assert s.foreground_model_call_budget_general == 2
    assert s.foreground_model_call_budget_learning == 3
    assert s.enable_policy_classifier_for_general_chat is False
    assert s.enable_sync_long_term_memory_for_general_chat is False
    assert s.enable_production_turn_trace_summary is True
    assert s.turn_trace_slow_total_threshold_ms == 8000
    assert s.turn_trace_slow_first_token_threshold_ms == 5000
    assert s.turn_trace_top_phase_count == 5
    assert s.explicit_recall_memory_timeout_ms == 2000
    assert s.enable_explicit_recall_memory_cache is True
    assert s.explicit_recall_memory_cache_ttl_seconds == 120
    assert s.cold_memory_embedding_timeout_ms == 1500
    assert s.suggestion_generation_timeout_ms == 1000

def test_settings_can_be_overridden_by_env():
    """Settings 應能透過環境變數覆寫，確保不 Hardcoding。"""
    with patch.dict('os.environ', {
        'RAG_MAX_DOCS': '10',
        'RAG_SCORE_DROP_TOLERANCE': '0.5',
        'MODEL_POLICY_CLASSIFIER': 'openai/gpt-4o',
        'MODEL_ZPD_QUERY': 'google/gemini-3.1-flash-lite',
        'MODEL_SUGGESTION': 'google/gemini-2.5-flash-lite',
        'MODEL_COLD_MEMORY_EMBEDDING': 'openai/text-embedding-3-small',
        'MODEL_MEMORY_SEMANTIC_ANALYZER': 'google/gemini-2.5-flash-lite',
        'MEMORY_SEMANTIC_ANALYSIS_ENABLED': 'true',
        'ENABLE_TURN_PLAN_RUNTIME': 'true',
        'FOREGROUND_MODEL_CALL_BUDGET_GENERAL': '4',
        'TURN_TRACE_SLOW_TOTAL_THRESHOLD_MS': '9000',
        'EXPLICIT_RECALL_MEMORY_TIMEOUT_MS': '1500',
        'ENABLE_EXPLICIT_RECALL_MEMORY_CACHE': 'false',
        'COLD_MEMORY_EMBEDDING_TIMEOUT_MS': '900',
        'SUGGESTION_GENERATION_TIMEOUT_MS': '750',
    }):
        from backend.config import Settings
        s = Settings()
        assert s.rag_max_docs == 10
        assert s.rag_score_drop_tolerance == 0.5
        assert s.model_policy_classifier == 'openai/gpt-4o'
        assert s.model_zpd_query == 'google/gemini-3.1-flash-lite'
        assert s.model_suggestion == 'google/gemini-2.5-flash-lite'
        assert s.model_cold_memory_embedding == 'openai/text-embedding-3-small'
        assert s.model_memory_semantic_analyzer == 'google/gemini-2.5-flash-lite'
        assert s.memory_semantic_analysis_enabled is True
        assert s.enable_turn_plan_runtime is True
        assert s.foreground_model_call_budget_general == 4
        assert s.turn_trace_slow_total_threshold_ms == 9000
        assert s.explicit_recall_memory_timeout_ms == 1500
        assert s.enable_explicit_recall_memory_cache is False
        assert s.cold_memory_embedding_timeout_ms == 900
        assert s.suggestion_generation_timeout_ms == 750
