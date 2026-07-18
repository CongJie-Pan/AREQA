from backend.services.response_boundary_validator import ResponseBoundaryValidator


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
