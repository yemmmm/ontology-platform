"""Refresh recoverable role feedback against current team input state."""

from ontoweave_modeling.role_work import _prompt_feedback


class _Team:
    def __init__(self, pending):
        self._pending = pending

    def pending(self, owner):
        return self._pending.get(owner, [])


class _Flow:
    def __init__(self, pending):
        self.team = _Team(pending)


def test_consumed_model_input_pending_feedback_is_cleared():
    state = {
        "issue": {
            "code": "model_input_pending",
            "owner_work_ids": ["modeler"],
            "historical_detail": "preserve the original state outside the prompt",
        }
    }

    assert _prompt_feedback(_Flow({"modeler": []}), state) is None
    assert state["issue"]["owner_work_ids"] == ["modeler"]


def test_model_input_pending_feedback_keeps_only_current_pending_owners():
    state = {
        "issue": {
            "code": "model_input_pending",
            "owner_work_ids": ["modeler", "other-modeler"],
            "historical_detail": "retain unrelated historical fields",
        }
    }

    assert _prompt_feedback(_Flow({"modeler": [{"id": "answer"}]}), state) == {
        "code": "model_input_pending",
        "owner_work_ids": ["modeler"],
        "historical_detail": "retain unrelated historical fields",
    }

