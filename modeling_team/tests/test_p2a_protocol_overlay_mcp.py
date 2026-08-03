from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from modeling_team import p2a_protocol_overlay_mcp as overlay
from modeling_team.p2a_batch_plan import (
    ASSERTION_CLIENT_ITEM_IDS,
    canonical_digest,
    materialize_overlay_contract,
    validate_overlay_contract,
)
from modeling_team.proof_v2 import build_candidate_item_evidence_map
from modeling_team.tests.test_p2a_batch_plan import (
    candidate,
    candidate_receipt,
    dry_run_detail,
    dry_run_receipt,
)


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "modeling_team/references/p2a-overlay-contract.json"


def _template() -> dict[str, object]:
    return json.loads(TEMPLATE.read_text())


def _authorized(monkeypatch: pytest.MonkeyPatch, run_id: str = "p2a-run-1") -> dict[str, object]:
    contract = materialize_overlay_contract(_template(), run_id)
    payloads = {
        overlay.CONTRACT_PATH: json.dumps(
            contract,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    }
    for asset in contract["assets"]:
        payloads[Path(asset["mount_path"])] = (ROOT / asset["source_path"]).read_bytes()
    monkeypatch.setenv(overlay.RUN_ID_ENV, run_id)
    monkeypatch.setenv(overlay.TASK_ID_ENV, overlay.P2A_TASK_ID)
    monkeypatch.setenv(overlay.CONTRACT_DIGEST_ENV, contract["contract_digest"])
    monkeypatch.setattr(overlay, "_read_immutable", lambda path, *_args: payloads[path])
    return contract


def test_template_self_digest_and_exact_asset_digests_are_current():
    template = _template()
    validate_overlay_contract(
        template,
        expected_run_id="$P2A_RUNTIME_RUN_ID",
    )
    for asset in template["assets"]:
        assert hashlib.sha256((ROOT / asset["source_path"]).read_bytes()).hexdigest() == asset[
            "sha256"
        ]


def test_overlay_lists_only_two_p2a_tools(monkeypatch):
    _authorized(monkeypatch)
    response = overlay.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert response is not None
    tools = response["result"]["tools"]
    assert [tool["name"] for tool in tools] == [overlay.BUILD_TOOL, overlay.VERIFY_TOOL]


def test_overlay_builds_exact_plan_under_host_bound_run(monkeypatch):
    _authorized(monkeypatch)
    value = candidate()
    retained_map = build_candidate_item_evidence_map(
        value,
        ASSERTION_CLIENT_ITEM_IDS,
        run_id="p2a-run-1",
    )
    response = overlay.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": overlay.BUILD_TOOL,
                "arguments": {
                    "candidate": value,
                    "candidate_item_evidence_map": retained_map,
                    "candidate_receipt": candidate_receipt(value),
                },
            },
        }
    )

    assert response is not None and "error" not in response
    plan = response["result"]["structuredContent"]
    assert plan["run_id"] == "p2a-run-1"
    assert len(plan["items"]) == 4


def test_overlay_verifies_formal_submit_receipt_and_two_detail_reads(monkeypatch):
    _authorized(monkeypatch)
    value = candidate()
    retained_map = build_candidate_item_evidence_map(
        value,
        ASSERTION_CLIENT_ITEM_IDS,
        run_id="p2a-run-1",
    )
    detail = dry_run_detail(retained_map)
    response = overlay.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": overlay.VERIFY_TOOL,
                "arguments": {
                    "candidate": value,
                    "candidate_item_evidence_map": retained_map,
                    "dry_run_receipt": dry_run_receipt(detail),
                    "detail_read_1": detail,
                    "detail_read_2": detail,
                },
            },
        }
    )

    assert response is not None and "error" not in response
    verified = response["result"]["structuredContent"]
    assert verified["batch_id"] == "batch-1"
    assert verified["client_item_ids"] == sorted(ASSERTION_CLIENT_ITEM_IDS.values())


@pytest.mark.parametrize(
    "drift",
    ["missing", "non-p2a", "cross-run", "self-digest", "asset"],
)
def test_missing_tampered_cross_run_and_non_p2a_context_fail_closed(monkeypatch, drift):
    contract = _authorized(monkeypatch)
    if drift == "missing":
        monkeypatch.delenv(overlay.CONTRACT_DIGEST_ENV)
    elif drift == "non-p2a":
        monkeypatch.setenv(overlay.TASK_ID_ENV, "ordinary-task")
    elif drift == "cross-run":
        monkeypatch.setenv(overlay.RUN_ID_ENV, "other-run")
    elif drift == "self-digest":
        contract["server_name"] = "tampered"
        raw = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
        original = overlay._read_immutable
        monkeypatch.setattr(
            overlay,
            "_read_immutable",
            lambda path, *args: raw if path == overlay.CONTRACT_PATH else original(path, *args),
        )
    else:
        original = overlay._read_immutable
        monkeypatch.setattr(
            overlay,
            "_read_immutable",
            lambda path, *args: b"tampered" if path.name == "p2a_batch_plan.py" else original(
                path, *args
            ),
        )

    response = overlay.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    assert response is not None
    assert response["error"]["code"] == -32020


def test_materialized_contract_digest_excludes_only_digest_field():
    contract = materialize_overlay_contract(_template(), "p2a-run-2")
    retained = contract.pop("contract_digest")
    assert retained == canonical_digest(contract)
