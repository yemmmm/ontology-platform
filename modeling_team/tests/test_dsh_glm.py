"""Exact GLM Messages routing, including the pinned isolated DSH process."""
import json
from pathlib import Path

import pytest

from modeling_team.deepseek_provider_proxy import preflight_glm_credential
from modeling_team.model_routing import (
    load_team_model_profile, resolve_delivery_model_binding, validate_runtime_model_profile,
)
from modeling_team.runtimes.acceptance import validate_acceptance_profile
from modeling_team.runtimes.dsh_delivery import DSHDeliveryRuntime, validate_delivery_runtime
from modeling_team.tests.test_dsh_runtime import (  # noqa: F401
    LocalMessagesProvider, local_roster, wait_until,
)

ROOT = Path(__file__).resolve().parents[2]


def test_glm_messages_exact_profile_and_runtime_selection():
    profile = load_team_model_profile(ROOT, "dsh-glm-flash-low")
    validate_runtime_model_profile("dsh", profile)
    validate_acceptance_profile("dsh", profile)
    binding, _ = resolve_delivery_model_binding(profile)
    assert validate_delivery_runtime({"runtime": "dsh"}, binding) == "dsh"
    assert all(b.provider_id == "glm-messages" and b.model == "glm-5.3-flash"
               and b.requested_effort == b.effective_effort == "low"
               for b in profile.bindings.values())
    with pytest.raises(ValueError, match="unsupported-runtime-provider"):
        validate_runtime_model_profile("codex", profile)


def test_glm_delivery_real_native_low_and_exact_model(tmp_path):
    profile = load_team_model_profile(ROOT, "dsh-glm-flash-low")
    binding, _ = resolve_delivery_model_binding(profile)
    runtime = DSHDeliveryRuntime(
        binding=binding, home=tmp_path / "native", instructions="Engineering fixture.",
        tools=[{"name": "probe", "description": "Probe", "inputSchema": {"type": "object"}}],
        tool_handler=lambda *a, **kw: {}, session_id="glm-test-delivery",
        provider_factory=LocalMessagesProvider,
    )
    try:
        runtime.start()
        runtime.provider.tool_calls = False
        runtime.send(json.dumps({"text": "Reply OK"}))
        wait_until(lambda: not runtime.busy)
        assert len(runtime.provider.requests) == 1
        request = runtime.provider.requests[0]
        assert request["model"] == "glm-5.3-flash"
        assert request["output_config"] == {"effort": "low"}
        assert runtime.identity["runtime"] == "dsh"
    finally:
        runtime.close()


def test_glm_production_real_isolated_roster(local_roster, tmp_path):
    adapter, run, broker = local_roster
    key = tmp_path / "glm.env"
    key.write_text("GLM_API_KEY=glm-engineering-secret\n")
    key.chmod(0o600)
    run.team_model_profile = load_team_model_profile(ROOT, "dsh-glm-flash-low")
    run.provider_credential_bindings = {"glm-messages": preflight_glm_credential(key)}
    adapter.provider_factory = LocalMessagesProvider
    assert len(adapter.start_roster(run, run.configuration.profile.agents)) == 3
    assert all(adapter.probe_role_visibility(run).values())
    baseline = (run.root / "evidence/dsh-baseline.jsonl").read_text()
    assert "glm-messages" in baseline and "glm-engineering-secret" not in baseline
