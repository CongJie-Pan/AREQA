from backend.core import PublicAnswerFilter


def test_filter_removes_reasoning_and_preserves_public_answer():
    output_filter = PublicAnswerFilter()
    result = output_filter.feed("before<think>private reasoning</think>after")
    assert result == "beforeafter"


def test_filter_handles_spaced_tags_split_across_chunks():
    output_filter = PublicAnswerFilter()
    chunks = ["public< th", "ink >secret", "< /think", " >answer"]
    assert "".join(output_filter.feed(chunk) for chunk in chunks) == "publicanswer"


def test_filter_preserves_non_reasoning_tags():
    output_filter = PublicAnswerFilter()
    assert output_filter.feed("Use <code>value</code>") == "Use <code>value</code>"


def test_filter_drops_unclosed_reasoning_at_end():
    output_filter = PublicAnswerFilter()
    assert output_filter.feed("answer<think>secret") == "answer"
    assert output_filter.finish() == ""
