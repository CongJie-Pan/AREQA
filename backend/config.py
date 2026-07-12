from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LLM Model Names
    model_policy_classifier: str = "google/gemini-3.1-flash-lite"
    model_hyde_decomposer: str = "google/gemini-3.1-flash-lite"
    model_main_instruct: str = "google/gemini-3.1-flash-lite"
    model_main_thinking: str = "google/gemini-3.1-flash-lite"
    model_gum: str = "google/gemini-3.1-flash-lite"
    model_zpd_query: str = "google/gemini-3.1-flash-lite"

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
