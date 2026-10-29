"""Exercise one real v5 application/checkpoint gap, then resume with the normal CLI.

Requires an explicitly authorized prepared task. Never edits model content or native receipts.
"""

import argparse
import fcntl
import json
from pathlib import Path

from ontoweave_modeling.cli import repository
from ontoweave_modeling.contracts import FrameworkError, TaskBinding, write_json
from ontoweave_modeling.execution import CodexInvocation
from ontoweave_modeling.flow import WorkUnitFlow
from ontoweave_modeling.host_bridge import HostBridge


class AfterApplication:
    def __init__(self, bridge, root):
        self.bridge, self.root = bridge, root

    def call(self, action, payload=None):
        result = self.bridge.call(action, payload)
        if action == "apply" and result.get("status") == "completed":
            write_json(
                self.root / "injected-checkpoint-gap.json",
                {
                    "fault": "successful_host_application_before_workflow_checkpoint",
                    "operation_id": payload["operation_id"],
                    "actual_host_result": result,
                    "next_action": "Normal CLI resume must reuse this original operation and result",
                },
            )
            raise FrameworkError("injected_checkpoint_gap", layer="runtime/infrastructure")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    binding = TaskBinding.load(args.run_dir)
    repo, config = repository(binding)
    bridge = HostBridge(binding.root)
    with (binding.root / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with repo.checkpointer(config["checkpoint_schema"]) as saver:
            flow = WorkUnitFlow(
                binding,
                repo,
                AfterApplication(bridge, binding.root),
                CodexInvocation(binding, bridge),
            )
            result = flow.advance(saver)
            print(
                json.dumps(
                    {
                        "fault_injected": result.get("issue", {}).get("code")
                        == "injected_checkpoint_gap",
                        "work": result,
                    }
                )
            )


if __name__ == "__main__":
    main()
