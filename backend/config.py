from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LLM Model Names
    model_policy_classifier: str = "qwen/qwen3-30b-a3b-instruct-2507"
    model_hyde_decomposer: str = "qwen/qwen3-30b-a3b-instruct-2507"
    model_main_instruct: str = "qwen/qwen3-235b-a22b-2507"
    model_main_thinking: str = "qwen/qwen3-235b-a22b-thinking-2507"
    model_gum: str = "qwen/qwen3-235b-a22b-2507"

    # RAG Parameters
    rag_max_docs: int = 7
    rag_score_drop_tolerance: float = 0.60
    rag_absolute_min_score: float = 0.005
    rag_reranker_threshold: float = 0.35
    rag_rrf_threshold: float = 0.005
    rag_cache_size: int = 200

    # Infrastructure
    redis_url: str = "redis://localhost:6379"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
