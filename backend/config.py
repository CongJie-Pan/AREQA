from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LLM Model Names
    model_policy_classifier: str = "google/gemini-3.1-flash-lite"
    model_hyde_decomposer: str = "google/gemini-3.1-flash-lite"
    model_main_instruct: str = "google/gemini-3.8-flash"
    model_main_thinking: str = "google/gemini-3.8-flash"
    model_conversation_summary: str = "google/gemini-3.1-flash-lite"
    model_gum: str = "google/gemini-3.1-flash-lite"
    model_zpd_query: str = "google/gemini-3.1-flash-lite"
    model_suggestion: str = "google/gemini-2.5-flash-lite"
    model_cold_memory_embedding: str = "openai/text-embedding-3-small"
    model_memory_semantic_analyzer: str = "google/gemini-2.5-flash-lite"
    model_visual_understanding: str = "google/gemini-3.1-flash-lite"
    model_web_search: str = "google/gemini-3.8-flash"

    # Chat history uses its own allowance; providers enforce actual media capacity.
    conversation_context_tokens: int = 32_768
    # Legacy deployment settings retained for compatibility; not admission limits.
    conversation_attachment_tokens: int = 131_072
    conversation_provider_context_tokens: int = 262_144
    conversation_attachment_timeout_seconds: float = 10.0
    conversation_summary_tokens: int = 1_536
    conversation_summary_timeout_seconds: float = 20.0
    conversation_summary_cold_timeout_seconds: float = 45.0
    conversation_summary_context_tokens: int = 524_288
    enable_conversation_compaction: bool = True
    # Summarize older history in the background as the context nears its budget,
    # so long chats stop waiting on a summary call before answering. Off by default.
    enable_conversation_summary_precompute: bool = False
    conversation_summary_precompute_ratio: float = 0.75
    conversation_summary_precompute_tail_share: float = 0.5
    conversation_summary_precompute_wait_seconds: float = 3.0

    # RAG Parameters
    rag_max_docs: int = 7
    rag_score_drop_tolerance: float = 0.60
    rag_absolute_min_score: float = 0.005
    rag_reranker_threshold: float = 0.35
    rag_rrf_threshold: float = 0.005
    rag_cache_size: int = 200

    # Infrastructure
    redis_url: str = "redis://localhost:6379"
    database_url: str = ""

    # Agent rollout flags
    enable_tutor_shadow_routing: bool = False
    enable_agent_search_routing: bool = True
    enable_auto_web_search: bool = False
    agent_search_rollout_percentage: float = 100.0
    enable_turn_plan_runtime: bool = True
    foreground_model_call_budget_general: int = 2
    foreground_model_call_budget_learning: int = 3
    enable_policy_classifier_for_general_chat: bool = True
    # The EDF classifier takes about 1.0-1.3 s; a 700 ms budget discarded every
    # PRACTICE/HINT decision and silently served the default LEARN policy.
    policy_classifier_timeout_ms: int = 1500
    # "gemini" (chat classifier), "jev" (Decisions API), "shadow" (serve Gemini,
    # compare Jev) or "jev_shadow" (serve Jev, compare Gemini). Unknown values
    # behave as "gemini".
    policy_classifier_backend: str = "gemini"
    # Last Asia/Taipei date (inclusive, YYYY-MM-DD) that shadow mode runs; empty means no end.
    policy_shadow_until: str = ""
    # Comma-separated user ids who opted in to text review records during shadow mode.
    shadow_review_user_ids: str = ""
    pdf_intent_classifier_timeout_ms: int = 1500
    enable_sync_long_term_memory_for_general_chat: bool = False
    enable_parts_prompt_context: bool = True
    enable_parts_llm_rewrite: bool = True
    enable_parts_llm_rewrite_for_ungrounded_turns: bool = False
    # Start grounded-turn PARTS rewrites alongside the policy classifier instead of after it.
    enable_parts_rewrite_prefetch: bool = True
    parts_rewrite_timeout_ms: int = 2500
    enable_parts_prompt_debug_logs: bool = False
    enable_live_tutor_debug_logs: bool = True
    enable_realtime_debug_logs: bool = True
    enable_livekit_avatar_mode: bool = True
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "areqa-live-tutor"
    livekit_avatar_token_ttl_seconds: int = 900
    enable_production_turn_trace_summary: bool = True
    turn_trace_slow_total_threshold_ms: int = 8000
    turn_trace_slow_first_token_threshold_ms: int = 5000
    turn_trace_top_phase_count: int = 5
    enable_openrouter_main_session_id: bool = True
    enable_openrouter_main_latency_routing: bool = True
    openrouter_main_preferred_latency_p90_seconds: float = 2.5
    explicit_recall_memory_timeout_ms: int = 2000
    enable_explicit_recall_memory_cache: bool = True
    explicit_recall_memory_cache_ttl_seconds: int = 120
    cold_memory_embedding_timeout_ms: int = 1500
    # Follow-up upload context: re-send stored original PDFs up to this many bytes,
    # otherwise give each document a fair share of this many extracted characters.
    chat_upload_native_followup_bytes: int = 10 * 1024 * 1024
    chat_upload_context_text_chars: int = 120_000
    chat_upload_store_originals: bool = True
    # Put stable re-sent documents before per-turn instructions so the provider can cache them.
    chat_upload_prompt_cache: bool = True
    # Production calls return in about 1.0-1.2 s, so a 1 s cap discarded nearly all suggestions.
    suggestion_generation_timeout_ms: int = 2500
    web_search_provider: str = "tavily"
    tavily_web_search_depth: str = "basic"
    openrouter_web_search_engine: str = "exa"
    openrouter_web_search_max_tool_calls: int = 2
    openrouter_web_search_api_url: str = "https://openrouter.ai/api/v1/chat/completions"

    # Visual answer retrieval. Keep provider debug logs off by default because
    # they are only needed while diagnosing third-party API failures.
    areqa_visual_user_agent: str = "AREQA/0.1 (https://congjie-pan.github.io/; contact: smartjay1206@gmail.com)"
    wikimedia_image_debug_logs: bool = True
    enable_visual_answer_debug_logs: bool = True
    enable_visual_preflight: bool = True
    visual_preflight_timeout_seconds: float = 6.0
    enable_visual_preflight_parallel_providers: bool = True
    enable_visual_preflight_open_provider_fallback: bool = True
    enable_perplexity_visual_search: bool = True
    perplexity_visual_search_model: str = "sonar"
    perplexity_visual_search_timeout_seconds: float = 4.5
    perplexity_sonar_api_url: str = "https://api.perplexity.ai/v1/sonar"
    enable_tavily_visual_search: bool = True
    tavily_visual_search_timeout_seconds: float = 3.0
    tavily_search_api_url: str = "https://api.tavily.com/search"
    enable_serpapi_visual_search: bool = True
    serpapi_visual_search_timeout_seconds: float = 3.0
    serpapi_google_images_api_url: str = "https://serpapi.com/search"
    visual_grounding_timeout_seconds: float = 1.5
    visual_grounding_max_candidates: int = 3
    visual_preflight_grounding_max_candidates: int = 2
    enable_visual_understanding: bool = True
    # Safe stage diagnostics for image generation; provider failures stay visible when disabled.
    enable_generated_image_debug_logs: bool = False
    generated_image_tool_timeout_seconds: float = 180.0
    visual_understanding_timeout_seconds: float = 4.0
    enable_pdf_attachment_visuals: bool = True
    pdf_attachment_visual_max_candidates: int = 4
    pdf_attachment_visual_max_pages_scanned: int = 8
    # Attachment visuals block the first answer token; vision calls still running
    # this long after preflight starts are dropped (images keep planner captions).
    pdf_attachment_visual_preflight_budget_seconds: float = 6.0
    enable_pdf_attachment_image_storage: bool = True
    pdf_attachment_image_storage_bucket: str = "areqa-pdf-visuals"
    pdf_attachment_image_signed_url_ttl_seconds: int = 2592000
    enable_pdf_paper_auto_explain: bool = True
    enable_pdf_paper_visual_planner: bool = True
    pdf_paper_visual_planner_timeout_seconds: float = 2.5
    pdf_paper_visual_planner_max_pages_scanned: int = 20
    pdf_paper_visual_planner_context_chars: int = 16000

    # Backend-only Supabase Storage credentials for persisted PDF visuals.
    # The service role key must never be exposed to browser code.
    supabase_url: str = ""
    next_public_supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Candidate memory promotion policy. Values are intentionally configurable
    # so the policy remains domain-neutral and can be tuned without code edits.
    memory_candidate_auto_promote_conversations: int = 2
    memory_candidate_max_evidence: int = 8
    memory_semantic_analysis_enabled: bool = False
    memory_semantic_shadow_mode: bool = True
    memory_semantic_timeout_seconds: float = 3.0
    memory_semantic_candidate_limit: int = 20
    memory_semantic_match_min_confidence: float = 0.85
    memory_semantic_external_processing_acknowledged: bool = False
    memory_extraction_agent_enabled: bool = True
    memory_extraction_timeout_seconds: float = 3.0
    memory_extraction_min_confidence: float = 0.85

    # Share-link creation runs in the Next.js API route. Keep the matching
    # backend setting enabled by default so deployments can use one environment
    # flag name while debugging share failures.
    enable_share_link_debug_logs: bool = True
    enable_conversation_history_debug_logs: bool = True
    # Owner-only topic-card event timeline API (GET /research-coach/{id}/card/log) for debugging.
    enable_topic_card_event_log_api: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

settings = Settings()
