from backend.cold_memory import ColdMemoryRetriever


def test_cold_memory_retriever_uses_configured_embedding_model():
    retriever = ColdMemoryRetriever(db_path="", openrouter_api_key="test-key")

    assert retriever.embedding_model == "openai/text-embedding-3-small"


def test_cold_memory_retriever_allows_embedding_model_override():
    retriever = ColdMemoryRetriever(
        db_path="",
        openrouter_api_key="test-key",
        embedding_model="test/embedding-model",
    )

    assert retriever.embedding_model == "test/embedding-model"
