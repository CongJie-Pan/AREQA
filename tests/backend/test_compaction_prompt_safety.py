import inspect

from backend.compaction import generate_stitch_tags


def test_stitch_prompt_example_uses_domain_neutral_content():
    source = inspect.getsource(generate_stitch_tags)

    assert "判詞" not in source
    assert "金陵十二釵" not in source
    assert "妙玉" not in source
    assert "香菱" not in source
    assert "概念A" in source
