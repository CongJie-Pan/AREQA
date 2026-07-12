from backend.policies import CapabilityPolicy


def test_rollout_is_disabled_when_feature_flag_is_off():
    assert CapabilityPolicy.rollout_enabled(
        feature_enabled=False,
        rollout_percentage=100,
        user_id="user-1",
        conversation_id="conversation-1",
    ) is False


def test_rollout_percentage_boundaries_are_deterministic():
    kwargs = {"user_id": "user-1", "conversation_id": "conversation-1"}
    assert CapabilityPolicy.rollout_enabled(
        feature_enabled=True, rollout_percentage=0, **kwargs
    ) is False
    assert CapabilityPolicy.rollout_enabled(
        feature_enabled=True, rollout_percentage=100, **kwargs
    ) is True


def test_partial_rollout_is_stable_for_same_conversation():
    values = {
        CapabilityPolicy.rollout_enabled(
            feature_enabled=True,
            rollout_percentage=25,
            user_id="user-1",
            conversation_id="conversation-1",
        )
        for _ in range(20)
    }
    assert len(values) == 1
