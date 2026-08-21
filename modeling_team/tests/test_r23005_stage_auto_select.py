"""R2.3-005 step 2: deterministic acceptance-stage auto-select coverage.

``protocol_build_acceptance_stage_handoff`` now accepts an omitted
``stage_calls`` argument: the carrier auto-selects the five canonical
final-state observed calls instead of asking the Protocol role to hand-pick
them.  These tests cover:

* a golden reconstruction from the retained start53 run evidence, asserting
  the auto-selected five stages equal start53's actually-succeeded handoff
  (delivery-7); and
* focused synthetic tests that encode the observed ambiguities (a stale earlier
  ``apply_atomic``, a later unsuccessful dry-run over the live workspace
  version, and repeated readbacks whose responses changed) plus the structured
  ``stage_auto_select_missing`` / ``stage_auto_select_ambiguous`` failures.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from modeling_team.acceptance import (
    AcceptanceContractError,
    MODELING_STAGES,
    RunnerAcceptanceCarrier,
    model_state_digest,
)


ROOT = Path(__file__).resolve().parents[2]
START53_RUN_DIR = (
    ROOT
    / "workspaces"
    / "modeling-runs"
    / "r23005-real-20260807-deepseek-start53"
)
RUN_ID = "r23005-real-20260807-deepseek-start53"

# start53's actually-succeeded handoff (delivery-7) live model state and
# candidate identity.  These are read directly from the retained delivery
# evidence so the golden assertion tracks the real run, not a hand-typed copy.
START53_LIVE_STATE = {
    "build_session_id": "40cbe906-6478-4b79-aaf8-e99232de66ad",
    "graph_set_id": "5a9094fd-0f7f-5799-ab05-10e813354819",
    "ontology_id": "ef6706df-9411-4a0b-afbc-85f7af27b840",
    "project_id": "b5dc5ade-b274-480d-aad6-b1b59c60e637",
    "source_signature": "a8c5cfa4bee7504c77f94d0b7b5f77d5",
    "workspace_version": "3a97f9d5b6733d068690529bb6bf4488089f5c11255f7084104620ae50ed61c0",
}
START53_LIVE_STATE["state_digest"] = model_state_digest(START53_LIVE_STATE)
START53_CANDIDATE_DIGEST = (
    "7a131d3b3c65619e2126c17b0e2d11e04dc85abdc8ef13b2eff60a70ca854998"
)
START53_CANDIDATE_REVISION = "dify-cba-slice-r3"


def _start53_golden_stages() -> dict[str, dict[str, str]] | None:
    """Return start53 delivery-7's five stage evidence bindings, or None."""

    deliveries = START53_RUN_DIR / "evidence" / "deliveries.jsonl"
    if not deliveries.is_file():
        return None
    for line in deliveries.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        if entry.get("delivery_id") != "delivery-7":
            continue
        payload = json.loads(entry["text"])
        stages: dict[str, dict[str, str]] = {}
        for receipt in payload["modeling_receipts"]:
            evidence = receipt["evidence_ref"]
            stages[receipt["stage"]] = {
                "tool": evidence["tool"],
                "artifact_path": evidence["artifact_path"],
                "request_digest": evidence["request_digest"],
                "response_digest": evidence["response_digest"],
            }
        return stages
    return None


def _reconstruct_records(run_root: Path) -> dict[str, dict[str, Any]]:
    """Reconstruct ``_platform_read_artifacts`` records from start53's catalog.

    The catalog carries each observed call's ``tool``/digests/``artifact_path``;
    the request arguments are not retained on disk, so the per-record
    ``request_arguments`` are synthesized with exactly the fields the selector
    and ``_validate_observed_stage_evidence`` read (``mode`` from the real
    artifact ``structuredContent.data``, plus the live scope fields).  The
    selection itself depends only on the real artifact bytes, so this is a
    faithful golden verification of which observed call each stage resolves to.
    """

    catalog_path = run_root / "evidence" / "platform-response-artifacts.jsonl"
    records: dict[str, dict[str, Any]] = {}
    sequence = 0
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        artifact_path = entry["artifact_path"]
        tool = entry["tool"]
        target = run_root / artifact_path
        data: dict[str, Any] | None = None
        successful = True
        try:
            result = json.loads(target.read_text(encoding="utf-8"))
        except OSError:
            continue
        structured = result.get("structuredContent") if isinstance(result, dict) else None
        if isinstance(structured, dict):
            data = structured.get("data")
            successful = structured.get("ok") is not False
        if not isinstance(data, dict):
            data = None
        arguments: dict[str, Any]
        if tool == "submit_modeling_batch":
            arguments = {
                "mode": data.get("mode") if data else None,
                "ontology_id": START53_LIVE_STATE["ontology_id"],
                "session_id": START53_LIVE_STATE["build_session_id"],
            }
        elif tool == "get_modeling_context":
            arguments = {"ontology_id": START53_LIVE_STATE["ontology_id"]}
        elif tool in {"run_semantic_validation", "run_semantic_reasoning"}:
            arguments = {"graph_set_id": START53_LIVE_STATE["graph_set_id"]}
        else:
            arguments = {}
        sequence += 1
        records[artifact_path] = {
            "tool": tool,
            "request_digest": entry["request_digest"],
            "response_digest": entry["response_digest"],
            "artifact_path": artifact_path,
            "request_arguments": arguments,
            "successful": successful,
            "observation_sequence": sequence,
        }
    return records


def _golden_carrier(run_root: Path) -> RunnerAcceptanceCarrier:
    carrier = RunnerAcceptanceCarrier(
        run_root / "acceptance-carrier",
        task_id="r2-3-005-formal-acceptance",
        acceptance_id="acceptance",
    )
    carrier.bind_model_state(START53_LIVE_STATE)
    carrier.register_accepted_candidate(
        candidate_revision=START53_CANDIDATE_REVISION,
        candidate_digest=START53_CANDIDATE_DIGEST,
    )
    records = _reconstruct_records(run_root)
    carrier._platform_read_artifacts.update(records)
    carrier._platform_artifact_sequence = len(records)
    return carrier


@unittest.skipUnless(
    (START53_RUN_DIR / "evidence" / "platform-response-artifacts.jsonl").is_file()
    and _start53_golden_stages() is not None,
    "start53 retained evidence is not available; golden reconstruction skipped",
)
class Start53GoldenAutoSelectTests(unittest.TestCase):
    """Auto-select (no ``stage_calls``) must reproduce start53's golden handoff."""

    def test_auto_select_matches_start53_golden_stages(self) -> None:
        golden = _start53_golden_stages()
        assert golden is not None
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / RUN_ID
            evidence_dst = run_root / "evidence"
            evidence_dst.mkdir(parents=True)
            shutil.copy2(
                START53_RUN_DIR / "evidence" / "platform-response-artifacts.jsonl",
                evidence_dst / "platform-response-artifacts.jsonl",
            )
            shutil.copytree(
                START53_RUN_DIR / "evidence" / "platform-responses",
                evidence_dst / "platform-responses",
            )
            carrier = _golden_carrier(run_root)
            try:
                built = carrier.protocol_build_acceptance_stage_handoff(
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
            finally:
                carrier.cleanup()

        handoff = built["handoff_json"]
        self.assertEqual(handoff["producer_run_id"], RUN_ID)
        self.assertEqual(handoff["candidate_digest"], START53_CANDIDATE_DIGEST)
        self.assertEqual(handoff["slice_revision"], START53_CANDIDATE_REVISION)
        self.assertEqual(len(handoff["modeling_receipts"]), len(MODELING_STAGES))
        by_stage = {r["stage"]: r for r in handoff["modeling_receipts"]}
        self.assertEqual(set(by_stage), set(MODELING_STAGES))
        for stage, expected in golden.items():
            evidence = by_stage[stage]["evidence_ref"]
            self.assertEqual(evidence["tool"], expected["tool"], msg=f"stage={stage}")
            self.assertEqual(
                evidence["artifact_path"], expected["artifact_path"], msg=f"stage={stage}"
            )
            self.assertEqual(
                evidence["request_digest"], expected["request_digest"], msg=f"stage={stage}"
            )
            self.assertEqual(
                evidence["response_digest"], expected["response_digest"], msg=f"stage={stage}"
            )

    def test_auto_select_dry_run_is_not_the_stale_live_version_dry_run(self) -> None:
        """The stale later dry_run over the live workspace version must NOT win.

        start53 observed ``e0d4b85b…`` (mode=dry_run, attempt_status=
        validation_failed, before_version==live workspace_version) AFTER the
        final apply.  The golden dry-run is the validated ``0555e917…`` paired
        with the final apply.  Auto-select must pick the latter.
        """

        golden = _start53_golden_stages()
        assert golden is not None
        stale_dry_run_path = (
            "evidence/platform-responses/"
            "e0d4b85b318734b3e38e18cd6672ac471a0017c0427a19e54b27b02f366e41d0-"
            "29f77a72060d11d3ea8ae256ec706decf81c5d428cf96e756c1baae27a4d54d2.json"
        )
        self.assertNotEqual(golden["dry-run"]["artifact_path"], stale_dry_run_path)
        with tempfile.TemporaryDirectory() as directory:
            run_root = Path(directory) / "modeling-runs" / RUN_ID
            evidence_dst = run_root / "evidence"
            evidence_dst.mkdir(parents=True)
            shutil.copy2(
                START53_RUN_DIR / "evidence" / "platform-response-artifacts.jsonl",
                evidence_dst / "platform-response-artifacts.jsonl",
            )
            shutil.copytree(
                START53_RUN_DIR / "evidence" / "platform-responses",
                evidence_dst / "platform-responses",
            )
            carrier = _golden_carrier(run_root)
            try:
                state = carrier._observed_model_state(None)
                selected = carrier._auto_select_stage_calls(state)
            finally:
                carrier.cleanup()
        self.assertEqual(
            selected["dry-run"]["artifact_path"], golden["dry-run"]["artifact_path"]
        )
        self.assertNotEqual(selected["dry-run"]["artifact_path"], stale_dry_run_path)


def _submit_result(*, mode: str, attempt_status: str, before: str, after: str | None) -> dict:
    return {
        "structuredContent": {
            "ok": True,
            "data": {
                "mode": mode,
                "attempt_status": attempt_status,
                "workspace": {"before_version": before, "after_version": after},
            },
        }
    }


def _readback_result(workspace_version: str, *, lease_active: bool | None = None) -> dict:
    data: dict[str, Any] = {
        "ontology": {"id": "ontology-syn"},
        "workspace": {"workspace_version": workspace_version},
    }
    if lease_active is not None:
        data["lease"] = {"active": lease_active}
    return {"structuredContent": {"ok": True, "data": data}}


def _graph_result(status: str, graph_set_id: str, *, kind: str) -> dict:
    return {
        "structuredContent": {
            "ok": True,
            "data": {"status": status, "graph_set_id": graph_set_id, "kind": kind},
        }
    }


def _synthetic_carrier(tmp: Path) -> RunnerAcceptanceCarrier:
    run_root = tmp / "modeling-runs" / "run-syn"
    carrier = RunnerAcceptanceCarrier(
        run_root / "acceptance-carrier",
        task_id="task-syn",
        acceptance_id="acceptance",
    )
    state = {
        "project_id": "project-syn",
        "ontology_id": "ontology-syn",
        "workspace_version": "ws-live",
        "source_signature": "source-syn",
        "build_session_id": "session-syn",
        "graph_set_id": "graph-syn",
    }
    state["state_digest"] = model_state_digest(state)
    carrier.bind_model_state(state)
    carrier.register_accepted_candidate(
        candidate_revision="revision-syn", candidate_digest="a" * 64
    )
    return carrier


def _submit_args(*, mode: str) -> dict[str, Any]:
    return {
        "session_id": "session-syn",
        "ontology_id": "ontology-syn",
        "mode": mode,
        "items": [],
        "client_batch_id": f"batch-{mode}",
        "idempotency_key": f"idem-{mode}",
    }


class StageAutoSelectSyntheticTests(unittest.TestCase):
    """Encode the observed ambiguities and assert deterministic resolution."""

    def test_auto_select_picks_final_apply_paired_dry_run_and_live_readback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = _synthetic_carrier(Path(directory))
            try:
                # Earlier apply whose after_version is NOT the live version.
                carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="apply_atomic") | {"client_batch_id": "old-apply"},
                    result=_submit_result(
                        mode="apply_atomic", attempt_status="applied", before="ws-0", after="ws-stale"
                    ),
                )
                # Final apply that produced the live workspace_version.
                final_apply = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="apply_atomic") | {"client_batch_id": "final-apply"},
                    result=_submit_result(
                        mode="apply_atomic", attempt_status="applied", before="ws-prev", after="ws-live"
                    ),
                )
                # Paired validated dry-run before that final apply.
                paired_dry = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="dry_run") | {"client_batch_id": "paired-dry"},
                    result=_submit_result(
                        mode="dry_run", attempt_status="validated", before="ws-prev", after=None
                    ),
                )
                # Later stale dry-run over the live version that failed validation.
                stale_dry = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="dry_run") | {"client_batch_id": "stale-dry"},
                    result=_submit_result(
                        mode="dry_run", attempt_status="validation_failed", before="ws-live", after=None
                    ),
                )
                # Two readbacks; only the second reflects the live workspace.
                carrier.register_platform_tool_result(
                    tool="get_modeling_context",
                    arguments={"ontology_id": "ontology-syn"},
                    result=_readback_result("ws-stale"),
                )
                live_readback = carrier.register_platform_tool_result(
                    tool="get_modeling_context",
                    arguments={"ontology_id": "ontology-syn"},
                    result=_readback_result("ws-live"),
                )
                validation = carrier.register_platform_tool_result(
                    tool="run_semantic_validation",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="validation"),
                )
                reasoning = carrier.register_platform_tool_result(
                    tool="run_semantic_reasoning",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="reasoning"),
                )

                built = carrier.protocol_build_acceptance_stage_handoff(
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                by_stage = {r["stage"]: r for r in built["handoff_json"]["modeling_receipts"]}
                evidence = {stage: by_stage[stage]["evidence_ref"] for stage in MODELING_STAGES}

                self.assertEqual(evidence["apply"]["artifact_path"], final_apply["artifact_path"])
                self.assertEqual(evidence["dry-run"]["artifact_path"], paired_dry["artifact_path"])
                self.assertNotEqual(evidence["dry-run"]["artifact_path"], stale_dry["artifact_path"])
                self.assertEqual(evidence["readback"]["artifact_path"], live_readback["artifact_path"])
                self.assertEqual(evidence["validation"]["artifact_path"], validation["artifact_path"])
                self.assertEqual(evidence["reasoning"]["artifact_path"], reasoning["artifact_path"])
            finally:
                carrier.cleanup()

    def test_auto_select_matches_supplied_path_output(self) -> None:
        """Auto-select and a correct supplied mapping produce the same handoff."""

        with tempfile.TemporaryDirectory() as directory:
            carrier = _synthetic_carrier(Path(directory))
            try:
                final_apply = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="apply_atomic"),
                    result=_submit_result(
                        mode="apply_atomic", attempt_status="applied", before="ws-prev", after="ws-live"
                    ),
                )
                paired_dry = carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="dry_run"),
                    result=_submit_result(
                        mode="dry_run", attempt_status="validated", before="ws-prev", after=None
                    ),
                )
                readback = carrier.register_platform_tool_result(
                    tool="get_modeling_context",
                    arguments={"ontology_id": "ontology-syn"},
                    result=_readback_result("ws-live"),
                )
                validation = carrier.register_platform_tool_result(
                    tool="run_semantic_validation",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="validation"),
                )
                reasoning = carrier.register_platform_tool_result(
                    tool="run_semantic_reasoning",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="reasoning"),
                )
                catalog = carrier.protocol_list_platform_artifacts(
                    protocol_id="protocol", capability=carrier.capability_token("protocol")
                )
                by_path = {item["artifact_path"]: item for item in catalog["artifacts"]}
                supplied = {
                    "dry-run": by_path[paired_dry["artifact_path"]],
                    "apply": by_path[final_apply["artifact_path"]],
                    "readback": by_path[readback["artifact_path"]],
                    "validation": by_path[validation["artifact_path"]],
                    "reasoning": by_path[reasoning["artifact_path"]],
                }
                supplied_calls = {
                    stage: {
                        "tool": item["tool"],
                        "arguments": item["request_arguments"],
                        "artifact_path": item["artifact_path"],
                    }
                    for stage, item in supplied.items()
                }

                auto = carrier.protocol_build_acceptance_stage_handoff(
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                manual = carrier.protocol_build_acceptance_stage_handoff(
                    supplied_calls,
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                self.assertEqual(auto["handoff_digest"], manual["handoff_digest"])
            finally:
                carrier.cleanup()

    def test_auto_select_prefers_settled_readback_when_two_live_reads_observed(self) -> None:
        """R2.3-009 start17: mid-lease and settled reads can both show live.

        Two ``get_modeling_context`` observations may both report the live
        workspace_version and differ only in the transient ``lease.active``
        field (the first read happened while the mutation lease was still
        active).  The settled read — no active lease — is the final-state
        readback and auto-select must resolve to it instead of raising
        ``stage_auto_select_ambiguous``.
        """

        with tempfile.TemporaryDirectory() as directory:
            carrier = _synthetic_carrier(Path(directory))
            try:
                carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="apply_atomic"),
                    result=_submit_result(
                        mode="apply_atomic", attempt_status="applied", before="ws-prev", after="ws-live"
                    ),
                )
                carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="dry_run"),
                    result=_submit_result(
                        mode="dry_run", attempt_status="validated", before="ws-prev", after=None
                    ),
                )
                # Mid-lease read: live workspace version but lease still active.
                carrier.register_platform_tool_result(
                    tool="get_modeling_context",
                    arguments={"ontology_id": "ontology-syn"},
                    result=_readback_result("ws-live", lease_active=True),
                )
                settled_readback = carrier.register_platform_tool_result(
                    tool="get_modeling_context",
                    arguments={"ontology_id": "ontology-syn"},
                    result=_readback_result("ws-live", lease_active=False),
                )
                carrier.register_platform_tool_result(
                    tool="run_semantic_validation",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="validation"),
                )
                carrier.register_platform_tool_result(
                    tool="run_semantic_reasoning",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="reasoning"),
                )

                built = carrier.protocol_build_acceptance_stage_handoff(
                    protocol_id="protocol",
                    capability=carrier.capability_token("protocol"),
                )
                by_stage = {r["stage"]: r for r in built["handoff_json"]["modeling_receipts"]}
                self.assertEqual(
                    by_stage["readback"]["evidence_ref"]["artifact_path"],
                    settled_readback["artifact_path"],
                )
            finally:
                carrier.cleanup()

    def test_auto_select_raises_structured_ambiguous_when_two_applies_match_live(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = _synthetic_carrier(Path(directory))
            try:
                for batch in ("dup-a", "dup-b"):
                    carrier.register_platform_tool_result(
                        tool="submit_modeling_batch",
                        arguments=_submit_args(mode="apply_atomic") | {"client_batch_id": batch},
                        result=_submit_result(
                            mode="apply_atomic",
                            attempt_status="applied",
                            before="ws-prev",
                            after="ws-live",
                        ),
                    )
                with self.assertRaises(AcceptanceContractError) as ctx:
                    carrier.protocol_build_acceptance_stage_handoff(
                        protocol_id="protocol",
                        capability=carrier.capability_token("protocol"),
                    )
                self.assertEqual(ctx.exception.data["reason"], "stage_auto_select_ambiguous")
                self.assertEqual(ctx.exception.data["stage"], "apply")
                self.assertEqual(len(ctx.exception.data["matches"]), 2)
            finally:
                carrier.cleanup()

    def test_auto_select_raises_structured_missing_when_no_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = _synthetic_carrier(Path(directory))
            try:
                carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="apply_atomic"),
                    result=_submit_result(
                        mode="apply_atomic", attempt_status="applied", before="ws-prev", after="ws-live"
                    ),
                )
                carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="dry_run"),
                    result=_submit_result(
                        mode="dry_run", attempt_status="validated", before="ws-prev", after=None
                    ),
                )
                carrier.register_platform_tool_result(
                    tool="get_modeling_context",
                    arguments={"ontology_id": "ontology-syn"},
                    result=_readback_result("ws-live"),
                )
                carrier.register_platform_tool_result(
                    tool="run_semantic_reasoning",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="reasoning"),
                )
                with self.assertRaises(AcceptanceContractError) as ctx:
                    carrier.protocol_build_acceptance_stage_handoff(
                        protocol_id="protocol",
                        capability=carrier.capability_token("protocol"),
                    )
                self.assertEqual(ctx.exception.data["reason"], "stage_auto_select_missing")
                self.assertEqual(ctx.exception.data["stage"], "validation")
            finally:
                carrier.cleanup()

    def test_auto_select_raises_structured_missing_when_no_paired_dry_run(self) -> None:
        """A validated dry_run at a different before_version does not satisfy."""

        with tempfile.TemporaryDirectory() as directory:
            carrier = _synthetic_carrier(Path(directory))
            try:
                carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="apply_atomic"),
                    result=_submit_result(
                        mode="apply_atomic", attempt_status="applied", before="ws-prev", after="ws-live"
                    ),
                )
                # Dry-run paired with an EARLIER apply, not the final one.
                carrier.register_platform_tool_result(
                    tool="submit_modeling_batch",
                    arguments=_submit_args(mode="dry_run"),
                    result=_submit_result(
                        mode="dry_run", attempt_status="validated", before="ws-older", after=None
                    ),
                )
                carrier.register_platform_tool_result(
                    tool="get_modeling_context",
                    arguments={"ontology_id": "ontology-syn"},
                    result=_readback_result("ws-live"),
                )
                carrier.register_platform_tool_result(
                    tool="run_semantic_validation",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="validation"),
                )
                carrier.register_platform_tool_result(
                    tool="run_semantic_reasoning",
                    arguments={"graph_set_id": "graph-syn"},
                    result=_graph_result("succeeded", "graph-syn", kind="reasoning"),
                )
                with self.assertRaises(AcceptanceContractError) as ctx:
                    carrier.protocol_build_acceptance_stage_handoff(
                        protocol_id="protocol",
                        capability=carrier.capability_token("protocol"),
                    )
                self.assertEqual(ctx.exception.data["reason"], "stage_auto_select_missing")
                self.assertEqual(ctx.exception.data["stage"], "dry-run")
            finally:
                carrier.cleanup()


if __name__ == "__main__":
    unittest.main()
