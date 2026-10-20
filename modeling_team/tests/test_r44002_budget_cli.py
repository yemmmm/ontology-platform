from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from modeling_team import __main__ as team_main


def _invoke(*arguments: str) -> tuple[int, dict | None]:
    output = StringIO()
    with patch.object(sys, "argv", ["modeling-team", *arguments]), redirect_stdout(output):
        status = team_main.main()
    text = output.getvalue().strip()
    return status, json.loads(text) if text else None


def _config(reference: str = "user-auth-1") -> dict:
    return {
        "mode": "amount",
        "budget_id": "budget-cli",
        "task_ref": "task-cli",
        "authorization_reference": reference,
        "amount": "10",
        "prices": [
            {
                "provider": "route-a",
                "actual_model": "model-a",
                "cached_input_per_million": "0.2",
                "uncached_input_per_million": "2",
                "output_per_million": "8",
            }
        ],
    }


def _help(*arguments: str) -> tuple[int, str]:
    output = StringIO()
    with patch.object(sys, "argv", ["modeling-team", *arguments]), redirect_stdout(output):
        with pytest.raises(SystemExit) as raised:
            team_main.main()
    return raised.value.code, output.getvalue()


def test_task_budget_cli_create_add_show_uses_host_core_without_model_start(tmp_path: Path) -> None:
    ref = tmp_path / "cost-budget"
    create_config = tmp_path / "create.json"
    create_config.write_text(json.dumps(_config()), encoding="utf-8")

    status, created = _invoke(
        "task-budget", "create", "--ref", str(ref), "--config", str(create_config)
    )
    assert status == 0
    assert created["budget_ref"] == str(ref.resolve())
    assert created["authorized_amount"] == "10"
    assert (ref / "authorization.json").is_file()

    add_config = tmp_path / "add.json"
    add_config.write_text(
        json.dumps({"delta_amount": "2", "authorization_id": "user-auth-2"}),
        encoding="utf-8",
    )
    status, added = _invoke(
        "task-budget", "add", "--ref", str(ref), "--config", str(add_config)
    )
    assert status == 0
    assert added["authorized_amount"] == "12"

    status, delivery = _invoke(
        "task-budget", "show", "--ref", str(ref), "--audience", "delivery"
    )
    assert status == 0
    assert delivery["authorized_amount"] == "12"
    assert "owners" not in delivery
    assert "sources" not in delivery


def test_task_budget_cli_requires_real_host_authorization_reference(tmp_path: Path) -> None:
    ref = tmp_path / "cost-budget"
    config = tmp_path / "missing-reference.json"
    config.write_text(json.dumps({"mode": "amount", "amount": "1"}), encoding="utf-8")

    status, result = _invoke(
        "task-budget", "create", "--ref", str(ref), "--config", str(config)
    )
    assert status == 2
    assert result["error"] == "task_budget_failed"
    assert not (ref / "authorization.json").exists()


def test_task_budget_cli_can_supply_reference_as_host_flag(tmp_path: Path) -> None:
    ref = tmp_path / "cost-budget"
    config = tmp_path / "host-config.yaml"
    config.write_text("mode: amount\namount: '1'\n", encoding="utf-8")

    status, result = _invoke(
        "task-budget",
        "create",
        "--ref",
        str(ref),
        "--config",
        str(config),
        "--authorization-reference",
        "user-auth-flag",
    )
    assert status == 0
    assert result["authorized_amount"] == "1"
    persisted = json.loads((ref / "authorization.json").read_text(encoding="utf-8"))
    assert persisted["authorization_reference"] == "user-auth-flag"


def test_amount_budget_ref_passthrough_is_available_on_run_and_resume() -> None:
    run_status, run_help = _help("run", "--help")
    resume_status, resume_help = _help("checkpoint", "resume", "--help")

    assert run_status == 0
    assert resume_status == 0
    assert "--budget-ref BUDGET_REF" in run_help
    assert "--budget-ref BUDGET_REF" in resume_help


def test_task_budget_cli_snapshots_configured_model_prices(tmp_path: Path) -> None:
    config = _config()
    config.pop("prices")
    config["allowed_bindings"] = [
        {"provider": "glm-messages", "actual_model": "glm-5.3-flash"},
        {"provider": "deepseek-official", "actual_model": "deepseek-flash"},
    ]
    path = tmp_path / "create.json"
    path.write_text(json.dumps(config))
    status, result = _invoke("task-budget", "create", "--ref", str(tmp_path / "budget"),
                             "--config", str(path))
    assert status == 0
    assert len(result["price_versions"]) == 2
    assert all(row["rates"] == {"cached_input_tokens": "0.02", "uncached_input_tokens": "1",
                               "output_tokens": "4"} for row in result["price_versions"])
