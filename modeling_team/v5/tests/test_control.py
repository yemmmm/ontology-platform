"""Control uses the same real PostgreSQL fixture as workspace recovery tests."""

from ontoweave_modeling.control import TaskControl


def test_pause_waits_for_all_active_turns_and_delivers_queued_input_once(workspace):
    control = TaskControl(workspace)
    assert control.begin_turn("A", "a1")["admitted"]
    assert control.begin_turn("B", "b1")["admitted"]
    control.enqueue("input", "input", "Additional source reference", "A")
    control.enqueue("pause", "pause")
    assert all(m["status"] == "queued" for m in control.view()["messages"])
    first = control.finish_turn("A", "a1")
    assert first["status"] == "waiting_for_turn_end" and first["active"] == {"B": "b1"}
    assert not control.begin_turn("A", "a2")["admitted"]
    assert control.finish_turn("B", "b1")["status"] == "settled"
    control.enqueue("resume", "resume")
    delivery = TaskControl(workspace).begin_turn("A", "a3")
    assert [m["id"] for m in delivery["inputs"]] == ["input"]
    control.finish_turn("A", "a3", consumed_ids=("input",))
    assert control.begin_turn("A", "a4")["inputs"] == []


def test_budget_pause_and_stop_use_boundaries_without_replaying_inputs(workspace):
    control = TaskControl(workspace)
    control.begin_turn("A", "a1")
    control.enqueue("budget", "budget_pause")
    assert control.view()["budget_open"]
    control.finish_turn("A", "a1")
    assert not control.begin_turn("B", "b1")["admitted"]
    control.enqueue("budget-restored", "budget_resume")
    assert control.begin_turn("B", "b2")["admitted"]
    control.enqueue("stop", "stop")
    assert control.finish_turn("B", "b2")["mode"] == "stopped"
    assert not control.begin_turn("A", "a2")["admitted"]


def test_unknown_original_execution_cannot_be_started_again(workspace):
    control = TaskControl(workspace)
    control.begin_turn("A", "a1")
    rebuilt = TaskControl(workspace)
    result = rebuilt.begin_turn("A", "a2")
    assert not result["admitted"] and result["execution_id"] == "a1"


def test_unconfirmed_consumption_retains_identity_and_delivery_history(workspace):
    control = TaskControl(workspace)
    control.enqueue("m1", "input", "Additional constraint", "A")
    first = control.begin_turn("A", "a1")["inputs"][0]
    assert not first["previous_delivery_unconfirmed"]
    control.finish_turn("A", "a1")
    resumed = TaskControl(workspace).begin_turn("A", "a2")["inputs"][0]
    assert resumed["id"] == "m1" and resumed["previous_delivery_unconfirmed"]
    assert [item["execution_id"] for item in resumed["deliveries"]] == ["a1", "a2"]
    control.finish_turn("A", "a2", consumed_ids=("m1",))
    assert control.begin_turn("A", "a3")["inputs"] == []
