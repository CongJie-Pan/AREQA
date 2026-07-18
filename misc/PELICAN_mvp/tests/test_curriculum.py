import pytest
from pelican_mvp.curriculum import CURRICULUMS

def test_next_task_step_valid() -> None:
    curriculum = CURRICULUMS["cnn"]
    first = curriculum.first_task_step()
    assert first["step_id"] == "solve_conv"
    
    second = curriculum.next_task_step("solve_conv")
    assert second is not None
    assert second["step_id"] == "solve_relu"
    
def test_next_task_step_invalid_raises_value_error() -> None:
    curriculum = CURRICULUMS["cnn"]
    with pytest.raises(ValueError, match="Unknown task step: invalid_step"):
        curriculum.next_task_step("invalid_step")
