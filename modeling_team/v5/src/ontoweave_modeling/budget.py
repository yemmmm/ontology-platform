"""Project the Host amount ledger onto existing natural-turn task control."""

from __future__ import annotations

from .contracts import digest
from .host_bridge import HostBridge


def synchronize_budget(
    binding, control, *, addition: dict | None = None, role: str | None = None
) -> dict | None:
    if binding.data["authorization"]["mode"] != "amount":
        return None
    payload = {}
    if addition is not None:
        payload["addition"] = addition
    if role is not None:
        payload["role"] = role
    state = HostBridge(binding.root).call("budget", payload)
    opened = state["admission_open"]
    if control.synchronize()["budget_open"] != opened:
        control.enqueue(
            "budget-" + digest([state["budget_ref"], state["pause_epoch"], opened])[:24],
            "budget_resume" if opened else "budget_pause",
            metadata={"budget_ref": state["budget_ref"], "pause_epoch": state["pause_epoch"]},
        )
    control.synchronize()
    return state
