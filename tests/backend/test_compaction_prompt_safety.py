import inspect

from backend.compaction import generate_stitch_tags
from services.memory.gum.compaction import run_compaction


def test_stitch_prompt_example_uses_domain_neutral_content():
    source = inspect.getsource(generate_stitch_tags)

    assert "判詞" not in source
    assert "金陵十二釵" not in source
    assert "妙玉" not in source
    assert "香菱" not in source
    assert "概念A" in source


def test_hot_compaction_has_no_direct_cold_retriever_write():
    source = inspect.getsource(run_compaction)

    assert "ColdMemoryRetriever" not in source
    assert "insert_memory" not in source
    assert "create_memory_ingestion_service" in source
