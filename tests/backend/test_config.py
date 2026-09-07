import pytest
import os
from unittest.mock import patch

def test_settings_loads_defaults():
    """Settings 應在未設定環境變數時回傳所有預設值。"""
    from backend.config import Settings
    with patch.dict(os.environ, {}, clear=True):
        s = Settings(_env_file=None)
    assert s.rag_max_docs == 7
    assert s.rag_score_drop_tolerance == 0.60
    assert s.rag_absolute_min_score == 0.005
    assert s.rag_reranker_threshold == 0.35
    assert s.model_policy_classifier == "google/gemini-3.1-flash-lite"
    assert s.model_zpd_query == "google/gemini-3.1-flash-lite"
    assert s.model_suggestion == "google/gemini-2.5-flash-lite"
    assert s.model_cold_memory_embedding == "openai/text-embedding-3-small"
    assert s.model_memory_semantic_analyzer == "google/gemini-2.5-flash-lite"
    assert s.model_visual_understanding == "google/gemini-3.1-flash-lite"
    assert s.model_web_search == "google/gemini-3.8-flash"
    assert s.memory_semantic_analysis_enabled is False
    assert s.memory_semantic_shadow_mode is True
    assert s.memory_semantic_match_min_confidence == 0.85
    assert s.memory_semantic_external_processing_acknowledged is False
    assert s.enable_turn_plan_runtime is True
    assert s.foreground_model_call_budget_general == 2
    assert s.foreground_model_call_budget_learning == 3
    assert s.enable_policy_classifier_for_general_chat is True
    assert s.policy_classifier_timeout_ms == 700
    assert s.enable_sync_long_term_memory_for_general_chat is False
    assert s.enable_parts_prompt_context is True
    assert s.enable_parts_llm_rewrite is True
    assert s.enable_parts_llm_rewrite_for_ungrounded_turns is False
    assert s.parts_rewrite_timeout_ms == 2500
    assert s.enable_parts_prompt_debug_logs is False
    assert s.enable_live_tutor_debug_logs is True
    assert s.enable_realtime_debug_logs is True
    assert s.enable_livekit_avatar_mode is True
    assert s.livekit_url == ""
    assert s.livekit_api_key == ""
    assert s.livekit_api_secret == ""
    assert s.livekit_agent_name == "areqa-live-tutor"
    assert s.livekit_avatar_token_ttl_seconds == 900
    assert s.enable_production_turn_trace_summary is True
    assert s.turn_trace_slow_total_threshold_ms == 8000
    assert s.turn_trace_slow_first_token_threshold_ms == 5000
    assert s.turn_trace_top_phase_count == 5
    assert s.enable_openrouter_main_session_id is True
    assert s.enable_openrouter_main_latency_routing is True
    assert s.openrouter_main_preferred_latency_p90_seconds == 2.5
    assert s.explicit_recall_memory_timeout_ms == 2000
    assert s.enable_explicit_recall_memory_cache is True
    assert s.explicit_recall_memory_cache_ttl_seconds == 120
    assert s.cold_memory_embedding_timeout_ms == 1500
    assert s.suggestion_generation_timeout_ms == 1000
    assert s.web_search_provider == "openrouter"
    assert s.openrouter_web_search_engine == "auto"
    assert s.openrouter_web_search_max_tool_calls == 2
    assert s.openrouter_web_search_api_url == "https://openrouter.ai/api/v1/chat/completions"
    assert s.compeer_delivery_delay_seconds == 120
    assert s.compeer_cooldown_override_seconds == 120
    assert s.compeer_proactive_mail_min_interval_seconds == 21600
    assert s.compeer_daily_proactive_limit == 2
    assert s.enable_mailbox_feature is False
    assert s.enable_compeer_feature is False
    assert s.enable_compeer_telemetry is False
    assert s.enable_compeer_auto_proactive is False
    assert s.enable_mailbox_sending is False
    assert s.enable_share_link_debug_logs is True

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
        'MODEL_VISUAL_UNDERSTANDING': 'google/gemini-3.1-flash-lite',
        'MODEL_WEB_SEARCH': 'google/gemini-3.1-flash-lite',
        'MEMORY_SEMANTIC_ANALYSIS_ENABLED': 'true',
        'ENABLE_TURN_PLAN_RUNTIME': 'true',
        'FOREGROUND_MODEL_CALL_BUDGET_GENERAL': '4',
        'POLICY_CLASSIFIER_TIMEOUT_MS': '450',
        'ENABLE_PARTS_PROMPT_CONTEXT': 'false',
        'ENABLE_PARTS_LLM_REWRITE': 'false',
        'ENABLE_PARTS_LLM_REWRITE_FOR_UNGROUNDED_TURNS': 'true',
        'PARTS_REWRITE_TIMEOUT_MS': '250',
        'ENABLE_PARTS_PROMPT_DEBUG_LOGS': 'true',
        'ENABLE_LIVE_TUTOR_DEBUG_LOGS': 'false',
        'ENABLE_REALTIME_DEBUG_LOGS': 'false',
        'ENABLE_LIVEKIT_AVATAR_MODE': 'false',
        'LIVEKIT_URL': 'wss://example.livekit.cloud',
        'LIVEKIT_API_KEY': 'lk_api_key',
        'LIVEKIT_API_SECRET': 'lk_api_secret',
        'LIVEKIT_AGENT_NAME': 'custom-agent',
        'LIVEKIT_AVATAR_TOKEN_TTL_SECONDS': '120',
        'TURN_TRACE_SLOW_TOTAL_THRESHOLD_MS': '9000',
        'ENABLE_OPENROUTER_MAIN_SESSION_ID': 'false',
        'ENABLE_OPENROUTER_MAIN_LATENCY_ROUTING': 'false',
        'OPENROUTER_MAIN_PREFERRED_LATENCY_P90_SECONDS': '1.2',
        'EXPLICIT_RECALL_MEMORY_TIMEOUT_MS': '1500',
        'ENABLE_EXPLICIT_RECALL_MEMORY_CACHE': 'false',
        'COLD_MEMORY_EMBEDDING_TIMEOUT_MS': '900',
        'SUGGESTION_GENERATION_TIMEOUT_MS': '750',
        'WEB_SEARCH_PROVIDER': 'perplexity',
        'OPENROUTER_WEB_SEARCH_ENGINE': 'native',
        'OPENROUTER_WEB_SEARCH_MAX_TOOL_CALLS': '1',
        'OPENROUTER_WEB_SEARCH_API_URL': 'https://openrouter.example.test/chat/completions',
        'COMPEER_COOLDOWN_OVERRIDE_SECONDS': '30',
        'COMPEER_PROACTIVE_MAIL_MIN_INTERVAL_SECONDS': '3600',
        'ENABLE_MAILBOX_FEATURE': 'true',
        'ENABLE_COMPEER_FEATURE': 'true',
        'ENABLE_COMPEER_TELEMETRY': 'true',
        'ENABLE_COMPEER_AUTO_PROACTIVE': 'true',
        'ENABLE_MAILBOX_SENDING': 'true',
        'ENABLE_SHARE_LINK_DEBUG_LOGS': 'false',
    }, clear=True):
        from backend.config import Settings
        s = Settings(_env_file=None)
        assert s.rag_max_docs == 10
        assert s.rag_score_drop_tolerance == 0.5
        assert s.model_policy_classifier == 'openai/gpt-4o'
        assert s.model_zpd_query == 'google/gemini-3.1-flash-lite'
        assert s.model_suggestion == 'google/gemini-2.5-flash-lite'
        assert s.model_cold_memory_embedding == 'openai/text-embedding-3-small'
        assert s.model_memory_semantic_analyzer == 'google/gemini-2.5-flash-lite'
        assert s.model_visual_understanding == 'google/gemini-3.1-flash-lite'
        assert s.model_web_search == 'google/gemini-3.1-flash-lite'
        assert s.memory_semantic_analysis_enabled is True
        assert s.enable_turn_plan_runtime is True
        assert s.foreground_model_call_budget_general == 4
        assert s.policy_classifier_timeout_ms == 450
        assert s.enable_parts_prompt_context is False
        assert s.enable_parts_llm_rewrite is False
        assert s.enable_parts_llm_rewrite_for_ungrounded_turns is True
        assert s.parts_rewrite_timeout_ms == 250
        assert s.enable_parts_prompt_debug_logs is True
        assert s.enable_live_tutor_debug_logs is False
        assert s.enable_realtime_debug_logs is False
        assert s.enable_livekit_avatar_mode is False
        assert s.livekit_url == 'wss://example.livekit.cloud'
        assert s.livekit_api_key == 'lk_api_key'
        assert s.livekit_api_secret == 'lk_api_secret'
        assert s.livekit_agent_name == 'custom-agent'
        assert s.livekit_avatar_token_ttl_seconds == 120
        assert s.turn_trace_slow_total_threshold_ms == 9000
        assert s.enable_openrouter_main_session_id is False
        assert s.enable_openrouter_main_latency_routing is False
        assert s.openrouter_main_preferred_latency_p90_seconds == 1.2
        assert s.explicit_recall_memory_timeout_ms == 1500
        assert s.enable_explicit_recall_memory_cache is False
        assert s.cold_memory_embedding_timeout_ms == 900
        assert s.suggestion_generation_timeout_ms == 750
        assert s.web_search_provider == 'perplexity'
        assert s.openrouter_web_search_engine == 'native'
        assert s.openrouter_web_search_max_tool_calls == 1
        assert s.openrouter_web_search_api_url == 'https://openrouter.example.test/chat/completions'
        assert s.compeer_cooldown_override_seconds == 30
        assert s.compeer_proactive_mail_min_interval_seconds == 3600
        assert s.enable_mailbox_feature is True
        assert s.enable_compeer_feature is True
        assert s.enable_compeer_telemetry is True
        assert s.enable_compeer_auto_proactive is True
        assert s.enable_mailbox_sending is True
        assert s.enable_share_link_debug_logs is False
