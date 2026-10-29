"""Attach v5 numeric sources to the existing Host task budget, without new accounting."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from modeling_team.task_budget import BudgetError, TaskBudget

from ontoweave_modeling.contracts import FrameworkError, digest


def amount_state(binding, addition: dict | None = None, role: str | None = None) -> dict:
    try:
        return _amount_state(binding, addition, role)
    except BudgetError as error:
        raise FrameworkError(error.code, budget_detail=error.details) from error


def _amount_state(binding, addition, role) -> dict:
    budget = TaskBudget(binding.data["authorization"]["budget_ref"])
    state = budget.show("host")
    if state["task_ref"] != binding.data["task_ref"]:
        raise FrameworkError("budget_task_mismatch")
    for root in sorted((binding.root / "executions").glob("*")):
        provider_path = root / "provider-usage.jsonl"
        if not provider_path.exists() or not provider_path.stat().st_size:
            continue
        # The provider writes a complete numeric line before the native usage stream.
        with provider_path.open() as stream:
            first = json.loads(stream.readline())
        context = {
            key: first[key]
            for key in (
                "task_ref",
                "run_id",
                "agent_id",
                "role",
                "phase",
                "provider",
                "key_ref",
                "runtime",
            )
        }
        context["actual_model"] = first["requested_model"]
        # Each v5 execution starts a new Codex thread; its first counter has a proven zero baseline.
        context["cumulative_segment"] = {
            "id": root.name,
            "start": first["start"],
            "fresh_zero_baseline": True,
            "end": datetime.now(UTC).isoformat(),
            "evidence_ref": str(root / "agent/events.jsonl") + "#thread/start",
        }
        capture = first["proxy_session_id"]
        source_prefix = "v5-" + digest(str(root))[:24]
        sources = [
            (
                source_prefix + "-upstream",
                provider_path,
                # A cumulative observation window must never filter later transport attempts.
                {**context, "session_id": capture, "cumulative_segment": None},
                {"shared": True, "runtime": "codex"},
            ),
            (
                source_prefix + "-native",
                root / "budget-native-usage.jsonl",
                context,
                {"runtime": "codex", "native_capture_session_id": capture},
            ),
        ]
        for source_id, path, source_binding, metadata in sources:
            budget.register_source(source_id, path, "capture", source_binding, **metadata)
    budget.tick()
    if addition is not None:
        budget.add(addition)
    state = budget.show("delivery")
    if role is not None and state["admission_open"]:
        model = binding.data["models"][role]
        budget.require_available(
            operation="evaluation" if role == "acceptance" else "production",
            binding={"provider": model["provider"], "actual_model": model["model"]},
        )
    return state
