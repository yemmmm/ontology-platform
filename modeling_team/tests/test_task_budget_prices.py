"""Configured prices freeze into new, explicitly scoped task budgets."""

import json

import pytest

from modeling_team import task_budget
from modeling_team.task_budget import BudgetError, TaskBudget


BINDINGS = [
    {"provider": "glm-direct", "actual_model": "glm-5.3-flash"},
    {"provider": "glm-messages", "actual_model": "glm-5.3-flash"},
    {"provider": "deepseek-direct", "actual_model": "deepseek-flash"},
    {"provider": "deepseek-official", "actual_model": "deepseek-flash"},
]
RATES = {"cached_input_tokens": "0.02", "uncached_input_tokens": "1", "output_tokens": "4"}


def config(binding):
    return {"task_ref": "price-fixture", "authorization_reference": "fixture-user",
            "amount": "1", "allowed_bindings": [binding]}


@pytest.mark.parametrize("binding", BINDINGS)
def test_user_prices_apply_to_each_authorized_route_without_expanding_scope(tmp_path, binding):
    budget = TaskBudget.create(tmp_path / "budget", config(binding))
    state = budget.show()
    assert state["allowed_bindings"] == [binding]
    assert len(state["price_versions"]) == 1
    assert state["price_versions"][0]["rates"] == RATES
    assert state["price_versions"][0]["currency"] == "CNY"
    assert state["price_versions"][0]["unit_tokens"] == "1000000"
    source = tmp_path / "usage.jsonl"
    source.write_text(json.dumps({
        **binding, "key_ref": "fixture-key", "response_id": "fixture-response",
        "status": "completed", "usage": {"input_tokens": 1_100_000,
        "cached_input_tokens": 1_000_000, "output_tokens": 10_000},
    }) + "\n")
    budget.register_source("fixture", source, "receipts")
    assert budget.tick()["charged_estimate"] == "0.16"


def test_shared_price_edits_preserve_existing_snapshot_and_create_retry(tmp_path, monkeypatch):
    prices = json.loads(task_budget.DEFAULT_PRICES_PATH.read_text())
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(prices))
    monkeypatch.setattr(task_budget, "DEFAULT_PRICES_PATH", path)
    authorization = config(BINDINGS[0])
    budget = TaskBudget.create(tmp_path / "original", authorization)
    prices[0]["output_per_million"] = "99"
    path.write_text(json.dumps(prices))
    assert TaskBudget.create(budget.ref, authorization).show()["price_versions"][0]["rates"] == RATES
    fresh = TaskBudget.create(tmp_path / "new", {**authorization, "task_ref": "new-fixture"})
    assert fresh.show()["price_versions"][0]["rates"]["output_tokens"] == "99"
    budget.add({"authorization_reference": "fixture-add", "delta_amount": "1"})
    assert budget.show()["price_versions"][0]["rates"] == RATES


def test_explicit_task_prices_override_shared_defaults(tmp_path):
    budget = TaskBudget.create(tmp_path / "budget", {
        **config(BINDINGS[0]), "prices": [{**BINDINGS[0], "cached_input_per_million": "0",
        "uncached_input_per_million": "2", "output_per_million": "8"}],
    })
    assert budget.show()["price_versions"][0]["rates"]["output_tokens"] == "8"


@pytest.mark.parametrize("changes", [
    {"prices": []}, {"price_snapshot": []}, {"currency": "USD"},
    {"allowed_bindings": [{"provider": "glm-direct", "actual_model": "glm-5.3-flashx"}]},
    {"allowed_bindings": [{**BINDINGS[0], "route": "another-route"}]},
])
def test_defaults_do_not_fill_explicit_empty_unknown_or_other_currency_prices(tmp_path, changes):
    authorization = {**config(BINDINGS[0]), **changes}
    budget = TaskBudget.create(tmp_path / "budget", authorization)
    assert budget.show()["price_versions"] == []
    with pytest.raises(BudgetError) as error:
        budget.require_available(binding=authorization["allowed_bindings"][0])
    assert error.value.code == "budget_price_missing"


def test_price_catalog_does_not_authorize_models(tmp_path):
    authorization = config(BINDINGS[0])
    authorization.pop("allowed_bindings")
    budget = TaskBudget.create(tmp_path / "budget", authorization)
    assert budget.show()["allowed_bindings"] == []
    assert budget.show()["price_versions"] == []
    with pytest.raises(BudgetError) as error:
        budget.require_available(binding=BINDINGS[0])
    assert error.value.code == "budget_binding_not_allowed"
