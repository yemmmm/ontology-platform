"""Real platform effects across PostgreSQL graph failure and process reconstruction."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import TypedDict

from host_support import ROOT, write_json
from integration_cases import workspace
from langgraph.graph import END, START, StateGraph


class State(TypedDict, total=False):
    case: str
    result_ref: str


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("initial", "resume"))
    parser.add_argument(
        "--case",
        choices=("checkpoint_loss", "response_loss", "not_written", "partial"),
        required=True,
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=args.phase == "resume", mode=0o700)
    repository, _ = workspace(root, [], [])
    initial = args.phase == "initial"

    def apply(state):
        fault = args.case if initial else "normal"
        command = [
            str(ROOT / "backend/.venv/bin/python"),
            str(ROOT / "modeling_team/v5/scripts/platform_case.py"),
            "apply",
            "--output-dir",
            str(root / "platform"),
            "--plan",
            str(args.plan.resolve()),
            "--fault",
            fault,
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=180, check=False
        )
        (root / f"platform-{args.phase}.log").write_text(completed.stdout + completed.stderr)
        assert completed.returncode == 0, completed.stderr
        result = json.loads((root / f"platform/summary-{fault}.json").read_text())
        if initial:
            expected = {
                "checkpoint_loss": "completed",
                "response_loss": "uncertain",
                "not_written": "uncertain",
                "partial": "partial",
            }[args.case]
            assert result["status"] == expected, result
            raise RuntimeError("P0 controlled node failure before checkpoint persistence")
        # A confirmed pre-dispatch rejection needs an explicit corrected
        # request, not a regrouped replay. This probe preserves that partial
        # outcome and verifies that the applied predecessor is not submitted.
        expected = "partial" if args.case == "partial" else "completed"
        assert result["status"] == expected, result
        return {"result_ref": str(root / "platform/summary-normal.json")}

    builder = StateGraph(State)
    builder.add_node("apply", apply)
    builder.add_edge(START, "apply")
    builder.add_edge("apply", END)
    config = {"configurable": {"thread_id": root.name}}
    with repository.checkpointer() as saver:
        graph = builder.compile(checkpointer=saver)
        before = list(graph.get_state(config).next)
        if not initial:
            assert before == ["apply"]
        try:
            graph.invoke({"case": args.case} if initial else None, config)
        except RuntimeError as error:
            if (
                not initial
                or str(error) != "P0 controlled node failure before checkpoint persistence"
            ):
                raise
        after = list(graph.get_state(config).next)
        assert after == (["apply"] if initial else [])
        summary = {
            "phase": args.phase,
            "case": args.case,
            "before": before,
            "after": after,
            "semantic_acceptance": "unverified",
        }
        write_json(root / f"summary-{args.phase}.json", summary)
        print(json.dumps(summary))


if __name__ == "__main__":
    main()
