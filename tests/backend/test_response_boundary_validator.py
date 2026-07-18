from backend.services.response_boundary_validator import (
    ResponseBoundaryValidator,
    StreamingResponseBoundaryFilter,
)


def test_blocks_unsupported_understanding_claim():
    result = ResponseBoundaryValidator().validate("既然你已經理解了慣性，我們繼續。")
    assert not result.allowed
    assert result.reason == "unsupported_understanding"


def test_blocks_unsupported_ability_claim():
    result = ResponseBoundaryValidator().validate("你的國中理化基礎較弱，所以從例子開始。")
    assert not result.allowed
    assert result.reason == "unsupported_ability"


def test_allows_neutral_teaching():
    assert ResponseBoundaryValidator().validate("我們從一個生活例子開始說明慣性。").allowed


def test_stream_filter_blocks_claim_split_across_chunks():
    stream_filter = StreamingResponseBoundaryFilter()

    first, first_reasons = stream_filter.feed("既然你已經理")
    second, second_reasons = stream_filter.feed("解了慣性，我們繼續。")

    assert first == ""
    assert first_reasons == []
    assert second == "讓我們從目前的問題與具體例子開始。"
    assert second_reasons == ["unsupported_understanding"]


def test_stream_filter_releases_safe_unterminated_text():
    stream_filter = StreamingResponseBoundaryFilter()
    emitted, reasons = stream_filter.feed("我們從例子開始")
    trailing, trailing_reasons = stream_filter.finish()

    assert emitted == ""
    assert reasons == []
    assert trailing == "我們從例子開始"
    assert trailing_reasons == []
