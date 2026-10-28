"""Natural-turn control with two real, busy Codex members and a persisted queue."""

from __future__ import annotations

import argparse
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from host_support import HostAgent, write_json
from integration_cases import json_turn, materials, source, workspace

from ontoweave_modeling.control import TaskControl
from ontoweave_modeling.results import MATERIAL_RESULT_SCHEMA


def run(root: Path) -> dict:
    repository, _ = workspace(root, [], [])
    control = TaskControl(repository, root.name + ":control")
    public = materials(root / "materials", {"scenario": source()})
    running = {unit: threading.Event() for unit in ("A", "B")}
    actors = {}
    try:
        for unit in ("A", "B"):

            def observed(method, params, unit=unit):
                if method == "turn/started":
                    running[unit].set()

            actors[unit] = HostAgent(
                root / unit,
                materials=public,
                instructions="Read the authorized source and preserve unknowns. "
                "Control messages are engineering input, not business facts.",
                on_event=observed,
            ).start()

        def initial(unit):
            execution = root.name + ":" + unit + ":initial"
            assert control.begin_turn(unit, execution)["admitted"]
            result = json_turn(
                actors[unit],
                "Read scenario and capture the supported definitions, distinctions and unknowns.",
                MATERIAL_RESULT_SCHEMA,
            )
            assert result["status"] == "completed" and "structured_result" in result
            return {"result": result["status"], "boundary": control.finish_turn(unit, execution)}

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {unit: pool.submit(initial, unit) for unit in ("A", "B")}
            assert all(event.wait(120) for event in running.values())
            marker = "input-" + uuid.uuid4().hex
            control.enqueue(marker, "input", marker, "A")
            control.enqueue("user-pause", "pause")
            control.enqueue("budget-test-pause", "budget_pause")
            queued = control.view()
            assert len(queued["active"]) == 2
            assert all(message["status"] == "queued" for message in queued["messages"])
            results = {unit: future.result() for unit, future in futures.items()}
        settled = control.view()
        assert settled["status"] == "settled" and not settled["active"]
        assert not control.begin_turn("A", "must-not-start")["admitted"]
        control.enqueue("user-resume", "resume")
        assert not control.begin_turn("A", "budget-still-closed")["admitted"]
        control.enqueue("budget-test-resume", "budget_resume")
        resumed = TaskControl(repository, control.object_id)
        delivery = resumed.begin_turn("A", root.name + ":A:resumed")
        assert delivery["admitted"]
        assert [m["id"] for m in delivery["inputs"]] == [marker]
        running["A"].clear()
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"received_input": {"type": "string"}, "source_ref": {"type": "string"}},
            "required": ["received_input", "source_ref"],
        }
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                json_turn,
                actors["A"],
                f"A queued engineering message is now delivered: {marker}. Return it exactly as "
                "received_input, and reference the source already read. Do not alter business facts.",
                schema,
            )
            assert running["A"].wait(120)
            resumed.enqueue("user-stop", "stop")
            result = future.result()
        assert result["structured_result"]["received_input"] == marker
        final = resumed.finish_turn("A", root.name + ":A:resumed", consumed_ids=(marker,))
        assert final["status"] == "settled" and final["mode"] == "stopped"
        assert not resumed.begin_turn("B", "after-stop")["admitted"]
        methods = []
        for actor in actors.values():
            methods.extend(
                json.loads(line)["method"]
                for line in (actor.agent.root / "events.jsonl").read_text().splitlines()
            )
        assert not {"turn/steer", "turn/interrupt"}.intersection(methods)
        write_json(root / "control-state.json", resumed.view())
        return {
            "case": "V4-natural-boundaries",
            "two_members_busy_at_enqueue": True,
            "initial_turns_completed": {unit: value["result"] for unit, value in results.items()},
            "all_members_settled": True,
            "no_native_steer_or_interrupt": True,
            "queued_input_delivered_and_consumed_once": True,
            "budget_control": "injected closed/open admission signal; actual task remains usage_only",
            "stop_effective_after_native_completion": True,
            "semantic_acceptance": "unverified",
        }
    finally:
        for actor in actors.values():
            actor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    result = run(root)
    write_json(root / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
