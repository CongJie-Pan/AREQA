from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LLM Model Names
    model_policy_classifier: str = "google/gemini-3.1-flash-lite"
    model_hyde_decomposer: str = "google/gemini-3.1-flash-lite"
    model_main_instruct: str = "google/gemini-3.1-flash-lite"
    model_main_thinking: str = "google/gemini-3.1-flash-lite"
    model_gum: str = "google/gemini-3.1-flash-lite"
    model_zpd_query: str = "google/gemini-3.1-flash-lite"
    model_memory_semantic_analyzer: str = "google/gemini-2.5-flash-lite"

    # RAG Parameters
    rag_max_docs: int = 7
    rag_score_drop_tolerance: float = 0.60
    rag_absolute_min_score: float = 0.005
    rag_reranker_threshold: float = 0.35
    rag_rrf_threshold: float = 0.005
    rag_cache_size: int = 200

    # Infrastructure
    redis_url: str = "redis://localhost:6379"

    # Agent rollout flags
    enable_tutor_shadow_routing: bool = False
    enable_agent_search_routing: bool = True
    agent_search_rollout_percentage: float = 100.0
    enable_turn_plan_runtime: bool = False
    foreground_model_call_budget_general: int = 2
    foreground_model_call_budget_learning: int = 3
    enable_policy_classifier_for_general_chat: bool = False
    enable_sync_long_term_memory_for_general_chat: bool = False

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
    compeer_delivery_delay_seconds: int = 120
    compeer_cooldown_override_seconds: int | None = None
    compeer_daily_proactive_limit: int = 2
    enable_compeer_dev_controls: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
