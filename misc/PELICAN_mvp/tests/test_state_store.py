from pathlib import Path

import pytest

from pelican_mvp.models import Evidence, KnowledgeStatus
from pelican_mvp.state_store import StateStore


def test_state_persists_and_loads(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    state = store.new_state("student-1")
    state.nodes["cnn_relu"].update(KnowledgeStatus.MASTERED, Evidence("不會", "correct", True))
    store.save(state)

    loaded = store.load_or_create("student-1")

    assert loaded.nodes["cnn_relu"].status is KnowledgeStatus.MASTERED
    assert loaded.nodes["cnn_relu"].evidence[0].response == "不會"


def test_reset_creates_clean_state(tmp_path: Path) -> None:
    store = StateStore(tmp_path)
    state = store.new_state("student")
    state.nodes["nn_basics"].status = KnowledgeStatus.MASTERED
    store.save(state)

    reset = store.reset("student")

    assert all(item.status is KnowledgeStatus.UNDIAGNOSED for item in reset.nodes.values())


@pytest.mark.parametrize("learner_id", ["", "../escape", "bad id", "a" * 65])
def test_invalid_learner_id_is_rejected(tmp_path: Path, learner_id: str) -> None:
    with pytest.raises(ValueError):
        StateStore(tmp_path).new_state(learner_id)

