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
    assert s.model_memory_semantic_analyzer == "google/gemini-2.5-flash-lite"
    assert s.memory_semantic_analysis_enabled is False
    assert s.memory_semantic_shadow_mode is True
    assert s.memory_semantic_match_min_confidence == 0.85
    assert s.memory_semantic_external_processing_acknowledged is False

def test_settings_can_be_overridden_by_env():
    """Settings 應能透過環境變數覆寫，確保不 Hardcoding。"""
    with patch.dict('os.environ', {
        'RAG_MAX_DOCS': '10',
        'RAG_SCORE_DROP_TOLERANCE': '0.5',
        'MODEL_POLICY_CLASSIFIER': 'openai/gpt-4o',
        'MODEL_ZPD_QUERY': 'google/gemini-3.1-flash-lite',
        'MODEL_MEMORY_SEMANTIC_ANALYZER': 'google/gemini-2.5-flash-lite',
        'MEMORY_SEMANTIC_ANALYSIS_ENABLED': 'true',
    }):
        from backend.config import Settings
        s = Settings()
        assert s.rag_max_docs == 10
        assert s.rag_score_drop_tolerance == 0.5
        assert s.model_policy_classifier == 'openai/gpt-4o'
        assert s.model_zpd_query == 'google/gemini-3.1-flash-lite'
        assert s.model_memory_semantic_analyzer == 'google/gemini-2.5-flash-lite'
        assert s.memory_semantic_analysis_enabled is True
