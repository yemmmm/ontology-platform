from __future__ import annotations

import json
import copy
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from modeling_team.acceptance import (
    AcceptanceContractError,
    RunnerAcceptanceCarrier,
    model_state_digest,
    modeling_receipt_digest,
    ticket_digest,
    validate_model_state,
)
from modeling_team.transport_mcp import RoutingError, TeamTransportBroker
from modeling_team.runner import TeamRunner
from modeling_team.acceptance_runtime import ScopedReadProxy
from modeling_team.tests.test_r23005_contracts import _pass_verdict, _report, _ticket


def _two_cq_ticket(suffix: str, question_id: str) -> dict:
    value = _ticket(suffix)
    questions = [
        {"id": "cq1", "question": "Which output is consumed?"},
        {"id": "cq2", "question": "What happens when the score is unknown?"},
    ]
    value["competency_questions"] = questions
    value["question_id"] = question_id
    value["question"] = next(item["question"] for item in questions if item["id"] == question_id)
    value["ticket_digest"] = ticket_digest(value)
    for receipt in value["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = value["ticket_digest"]
    value["ticket_digest"] = ticket_digest(value)
    for receipt in value["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = value["ticket_digest"]
    return value


def _run_round(
    carrier: RunnerAcceptanceCarrier,
    ticket: dict,
    prefix: str,
    *,
    published: bool = False,
) -> dict:
    if carrier.model_state_snapshot is None:
        # Offline doubles must provide an explicit passive reader; this is the
        # mutable fake equivalent of the formal authenticated platform reader.
        carrier.bind_model_state(
            ticket["model_state"],
            state_reader=lambda: ticket["model_state"],
        )
    if not published:
        carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
    carrier.ack_ticket(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        ticket_digest_value=ticket["ticket_digest"],
    )
    reports = []
    for kind in ("source", "platform"):
        projection, digest = carrier.project_child_input(
            round_id=ticket["acceptance_round_id"], kind=kind
        )
        handle = carrier.start_child(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            kind=kind,
            input_ref=projection,
            input_digest=digest,
            ticket_digest_value=ticket["ticket_digest"],
            request_id=f"{prefix}-start-{kind}",
            attempt=0,
        )
        report = carrier.ingest_report(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            handle=handle,
            report=_report(ticket, handle, kind=kind),
        )
        carrier.recycle_child(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            handle=handle,
            completion_ref={"terminal_report_digest": report["report_digest"]},
            request_id=f"{prefix}-recycle-{kind}",
        )
        reports.append(report)
    verdict = _pass_verdict(ticket, reports[0], reports[1])
    carrier.submit_verdict(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        verdict=verdict,
        request_id=f"{prefix}-verdict",
    )
    return verdict


def _fresh_ticket(base: dict, *, suffix: str, question_id: str, state: dict) -> dict:
    ticket = copy.deepcopy(base)
    ticket["ticket_id"] = f"ticket-r23005-{suffix}"
    ticket["acceptance_round_id"] = f"round-r23005-{suffix}"
    ticket["producer_run_id"] = "producer-r23005-fresh"
    ticket["ticket_revision"] = 1
    ticket["question_id"] = question_id
    ticket["question"] = next(item["question"] for item in ticket["competency_questions"] if item["id"] == question_id)
    ticket["model_state"] = copy.deepcopy(state)
    ticket["model_state_digest"] = state["state_digest"]
    for receipt in ticket["modeling_receipts"]:
        receipt["run_id"] = ticket["producer_run_id"]
        receipt["model_state_digest"] = state["state_digest"]
        receipt["receipt_digest"] = None
        receipt["evidence_ref"]["model_state_digest"] = state["state_digest"]
        receipt["evidence_ref"]["ticket_digest"] = None
        receipt["receipt_digest"] = modeling_receipt_digest(receipt)
    ticket["ticket_digest"] = ticket_digest(ticket)
    for receipt in ticket["modeling_receipts"]:
        receipt["evidence_ref"]["ticket_digest"] = ticket["ticket_digest"]
    return ticket


class R23005CSettlementTests(unittest.TestCase):
    def test_c29_c34_c50_c52_c55_i09_i10_two_pass_same_state_cas_and_abort_split(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            first = _two_cq_ticket("1", "cq1")
            second = _two_cq_ticket("2", "cq2")
            _run_round(carrier, first, "cq1")
            _run_round(carrier, second, "cq2")
            self.assertTrue(carrier.settlement_ready())
            settled = carrier.settle()
            self.assertEqual(settled["status"], "settled")
            self.assertIn("settlement_cas", settled)
            self.assertTrue(carrier.is_settled)
            cleanup = carrier.cleanup()
            self.assertEqual(cleanup["status"], "cleaned")
            self.assertTrue(cleanup["settled"])
            self.assertEqual(carrier.cleanup(), cleanup)

        with tempfile.TemporaryDirectory() as directory:
            aborted = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            self.assertFalse(aborted.is_settled)
            result = aborted.cleanup()
            self.assertEqual(result["status"], "aborted")
            self.assertFalse(result["settled"])

    def test_c30_c40_i08_state_drift_invalidates_pass_without_partial_verdict_and_requires_fresh_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            first = _two_cq_ticket("1", "cq1")
            _run_round(carrier, first, "cq1")
            old_receipt = carrier._verdicts[first["acceptance_round_id"]]
            changed_state = dict(first["model_state"])
            changed_state["model_revision"] = 2
            changed_state["state_digest"] = model_state_digest(changed_state)
            invalidation = carrier.revalidate_model_state(
                boundary="after-pass-before-next-cq", observed=changed_state
            )
            self.assertEqual(invalidation["status"], "state_invalidated")
            with self.assertRaises(AcceptanceContractError):
                carrier.get_verdict(
                    acceptance_id="acceptance",
                    round_id=first["acceptance_round_id"],
                )
            self.assertEqual(carrier._verdicts[first["acceptance_round_id"]], old_receipt)
            self.assertFalse(carrier._rounds[first["acceptance_round_id"]]["verdict_usable"])
            # Reissuing with the old five receipts is rejected; C1/C55 evidence cannot
            # be relabelled mechanically after a state drift.
            stale = json.loads(json.dumps(first))
            stale["ticket_id"] = "ticket-r23005-stale"
            stale["acceptance_round_id"] = "round-r23005-stale"
            with self.assertRaises(AcceptanceContractError):
                carrier.issue_ticket_revision(
                    stale,
                    owner_revision=stale["quality_standard_ref"],
                    model_state=changed_state,
                )

    def test_c_recovery_retains_old_evidence_and_settles_only_fresh_epoch_pair(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            first = _two_cq_ticket("1", "cq1")
            second = _two_cq_ticket("2", "cq2")
            _run_round(carrier, first, "old-cq1")
            _run_round(carrier, second, "old-cq2")
            old_rounds = set(carrier._rounds)
            changed_state = dict(first["model_state"])
            changed_state["model_revision"] = 3
            changed_state["state_digest"] = model_state_digest(changed_state)
            invalidation = carrier.revalidate_model_state(
                boundary="post-cleanup", observed=changed_state
            )
            self.assertEqual(invalidation["status"], "state_invalidated")
            self.assertEqual(set(carrier._rounds), old_rounds)
            self.assertTrue(all(item["status"] == "state_invalidated" for item in carrier._rounds.values()))
            self.assertEqual(len(carrier.state_invalidations), 1)

            fresh_first = _fresh_ticket(first, suffix="fresh-1", question_id="cq1", state=changed_state)
            carrier.issue_ticket_revision(
                fresh_first,
                owner_revision=fresh_first["quality_standard_ref"],
                model_state=changed_state,
            )
            fresh_first = carrier.get_ticket(
                acceptance_id="acceptance",
                round_id=fresh_first["acceptance_round_id"],
            )
            # Update the offline reader to the new immutable epoch after the
            # revision is published; this is the fake analogue of a live platform
            # context reader returning the recovered state.
            carrier.bind_model_state(changed_state, state_reader=lambda: changed_state)
            _run_round(carrier, fresh_first, "fresh-cq1", published=True)
            fresh_second = _fresh_ticket(second, suffix="fresh-2", question_id="cq2", state=changed_state)
            _run_round(carrier, fresh_second, "fresh-cq2")
            self.assertFalse(carrier.is_settled)
            current_epoch = carrier._state_epoch
            events = carrier._state_revalidation_boundaries
            removed = next(
                index
                for index, event in enumerate(events)
                if event["epoch"] == current_epoch and event["boundary"] == "after-pass-before-next-cq"
            )
            saved = events.pop(removed)
            self.assertFalse(carrier.settlement_ready())
            events.insert(removed, saved)
            self.assertTrue(carrier.settlement_ready())
            self.assertEqual(carrier.settle()["status"], "settled")

    def test_c_formal_platform_reader_binds_ticket_and_detects_workspace_drift(self) -> None:
        class Scope:
            project_id = "project-r23005"
            ontology_id = "ontology-r23005"
            completed_session_id = None

            def __init__(self) -> None:
                self.model_revision = 1

            def _modeling_context(self):
                return {
                    "project": {"id": self.project_id},
                    "ontology": {"id": self.ontology_id},
                    "workspace": {"model_revision": self.model_revision},
                    "recent_batches": [{"build_session_id": "session-r23005"}],
                }

            def _workspace_context(self):
                return {
                    "ontology_id": self.ontology_id,
                    "model_revision": self.model_revision,
                }

        with tempfile.TemporaryDirectory() as directory:
            scope = Scope()
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            carrier.bind_platform_scope(scope, repository_root=Path(directory))
            ticket = _two_cq_ticket("formal", "cq1")
            carrier.publish_ticket(
                ticket,
                coordinator_id="coordinator",
                owner_revision=ticket["quality_standard_ref"],
            )
            self.assertEqual(carrier.model_state_snapshot["state_digest"], ticket["model_state_digest"])
            scope.model_revision = 2
            changed = carrier.revalidate_model_state(boundary="before-pair")
            self.assertEqual(changed["status"], "state_invalidated")
            self.assertEqual(changed["new_model_state_digest"], model_state_digest({
                **ticket["model_state"],
                "model_revision": 2,
                "state_digest": None,
            }))

    def test_c49_proxy_and_source_artifacts_must_be_real_retained_receipts(self) -> None:
        class Resource:
            def __init__(self, spec: dict) -> None:
                self.spec = spec
                self.proxy = None
                if spec["kind"] == "platform":
                    self.proxy = ScopedReadProxy(
                        socket_path=Path(spec["private_root"]) / "proxy.sock",
                        token="proxy-token",
                        read_key=str(spec.get("read_key_plaintext") or "offline-read-key"),
                        project_id=spec["platform_read_scope"]["project_id"],
                        ontology_id=spec["platform_read_scope"]["ontology_id"],

                        ticket_digest=spec["ticket_digest"],
                        model_state_digest=spec["model_state_digest"],
                        allowed_tools=spec["allowed_read_tools"],
                        forward=lambda _tool, _arguments, _key: {"state": "ready"},
                        acceptance_round_id=spec["acceptance_round_id"],
                        child_handle_digest=spec["child_handle_digest"],
                    )

            def stop(self) -> None:
                if self.proxy is not None:
                    self.proxy.destroy()

            def destroy(self) -> None:
                self.stop()

        def report_with_proxy_receipt(ticket: dict, handle, resource: Resource) -> dict:
            response = resource.proxy.handle(
                {
                    "token": "proxy-token",
                    "operation": "tools/call",
                    "tool": "get_modeling_context",
                    "arguments": {
                        "project_id": ticket["platform_read_scope"]["project_id"],
                        "ontology_id": ticket["platform_read_scope"]["ontology_id"],

                        "ticket_digest": ticket["ticket_digest"],
                        "model_state_digest": ticket["model_state_digest"],
                    },
                }
            )
            self.assertTrue(response["ok"])
            receipt = resource.proxy.receipt_snapshot[0]
            report = _report(ticket, handle, kind="platform")
            ref = report["evidence_refs"][0]
            ref.update(
                {
                    "tool": receipt.tool,
                    "request_digest": receipt.request_digest,
                    "response_digest": receipt.response_digest,
                    "artifact_path": receipt.artifact_path,
                }
            )
            return report

        with tempfile.TemporaryDirectory() as directory:
            ticket = _two_cq_ticket("proxy", "cq1")
            carrier = RunnerAcceptanceCarrier(
                Path(directory) / "carrier",
                task_id="task-r23005",
                acceptance_id="acceptance",
                child_factory=Resource,
            )
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="platform")
            handle = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="platform", input_ref=projection, input_digest=digest, ticket_digest_value=ticket["ticket_digest"], request_id="proxy-start", attempt=0)
            resource = carrier._resources[handle.token][1]
            valid = report_with_proxy_receipt(ticket, handle, resource)
            accepted = carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, report=valid)
            self.assertEqual(accepted["evidence_refs"][0]["artifact_path"], resource.proxy.receipt_snapshot[0].artifact_path)

            # A receipt from a different scoped proxy is not interchangeable with
            # the current child receipt, even when it carries the same ticket and
            # model-state digests.  This prevents a child from laundering a read
            # performed under a foreign project/ontology/graph scope.
            foreign_proxy = ScopedReadProxy(
                socket_path=Path(directory) / "foreign-proxy.sock",
                token="foreign-token",
                read_key="foreign-read-key",
                project_id="project-foreign",
                ontology_id="ontology-foreign",

                ticket_digest=ticket["ticket_digest"],
                model_state_digest=ticket["model_state_digest"],
                allowed_tools=ticket["allowed_read_tools"],
                forward=lambda _tool, _arguments, _key: {"state": "foreign"},
                acceptance_round_id=ticket["acceptance_round_id"],
                child_handle_digest=handle.digest,
            )
            foreign_response = foreign_proxy.handle(
                {
                    "token": "foreign-token",
                    "operation": "tools/call",
                    "tool": "get_modeling_context",
                    "arguments": {
                        "project_id": "project-foreign",
                        "ontology_id": "ontology-foreign",

                        "ticket_digest": ticket["ticket_digest"],
                        "model_state_digest": ticket["model_state_digest"],
                    },
                }
            )
            self.assertTrue(foreign_response["ok"])
            foreign_receipt = foreign_proxy.receipt_snapshot[0]
            foreign_report = copy.deepcopy(valid)
            foreign_report["evidence_refs"][0].update(
                {
                    "request_digest": foreign_receipt.request_digest,
                    "response_digest": foreign_receipt.response_digest,
                    "artifact_path": foreign_receipt.artifact_path,
                }
            )
            with self.assertRaisesRegex(AcceptanceContractError, "does not match"):
                carrier.ingest_report(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    handle=handle,
                    report=foreign_report,
                )

            # The same successful scoped call cannot satisfy two report pages.
            duplicate_report = copy.deepcopy(valid)
            duplicate_report["evidence_refs"][0]["page"].update(
                {"output_cursor": "cursor-1", "sequence_complete": False, "has_more": True}
            )
            duplicate_page = copy.deepcopy(duplicate_report["evidence_refs"][0])
            duplicate_page["page"].update(
                {
                    "ordinal": 1,
                    "input_cursor": "cursor-1",
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                }
            )
            duplicate_report["evidence_refs"].append(duplicate_page)
            with self.assertRaisesRegex(AcceptanceContractError, "repeats"):
                carrier.ingest_report(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    handle=handle,
                    report=duplicate_report,
                )
            carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, completion_ref={"terminal_report_digest": accepted["report_digest"]}, request_id="proxy-recycle")
            carrier.abort_cleanup("proxy-test-cleanup")

        with tempfile.TemporaryDirectory() as directory:
            ticket = _two_cq_ticket("proxy-fail", "cq1")
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance", child_factory=Resource)
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="platform")
            handle = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="platform", input_ref=projection, input_digest=digest, ticket_digest_value=ticket["ticket_digest"], request_id="proxy-fail-start", attempt=0)
            resource = carrier._resources[handle.token][1]
            forged = _report(ticket, handle, kind="platform")
            forged["evidence_refs"][0]["artifact_path"] = "evidence/virtual.json"
            with self.assertRaisesRegex(AcceptanceContractError, "scoped proxy receipt"):
                carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, report=forged)
            self.assertFalse((carrier.acceptance_root / ticket["acceptance_round_id"] / "platform-report.json").exists())
            forged = report_with_proxy_receipt(ticket, handle, resource)
            forged["evidence_refs"][0]["response_digest"] = "f" * 64
            with self.assertRaisesRegex(AcceptanceContractError, "does not match"):
                carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, report=forged)
            self.assertFalse((carrier.acceptance_root / ticket["acceptance_round_id"] / "platform-report.json").exists())
            carrier.abort_cleanup("proxy-fail-cleanup")

        with tempfile.TemporaryDirectory() as directory:
            ticket = _two_cq_ticket("proxy-early", "cq1")

            class EarlyResource(Resource):
                def __init__(self, spec: dict) -> None:
                    super().__init__(spec)
                    if spec["kind"] == "platform":
                        response = self.proxy.handle(
                            {
                                "token": "proxy-token",
                                "operation": "tools/call",
                                "tool": "get_modeling_context",
                                "arguments": {
                                    "project_id": ticket["platform_read_scope"]["project_id"],
                                    "ontology_id": ticket["platform_read_scope"]["ontology_id"],

                                    "ticket_digest": ticket["ticket_digest"],
                                    "model_state_digest": ticket["model_state_digest"],
                                },
                            }
                        )
                        if not response["ok"]:
                            raise AssertionError("proxy call did not succeed")
                        receipt = self.proxy.receipt_snapshot[0]
                        pseudo_handle = SimpleNamespace(
                            digest=spec["child_handle_digest"],
                            session_id=spec["session_id"],
                            input_digest=spec["input_digest"],
                        )
                        report = _report(ticket, pseudo_handle, kind="platform")
                        report["evidence_refs"][0].update(
                            {
                                "tool": receipt.tool,
                                "request_digest": receipt.request_digest,
                                "response_digest": receipt.response_digest,
                                "artifact_path": receipt.artifact_path,
                            }
                        )
                        queued = spec["report_submit"](report)
                        if queued.get("status") != "queued":
                            raise AssertionError("early report was not queued")

            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance", child_factory=EarlyResource)
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="platform")
            handle = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="platform", input_ref=projection, input_digest=digest, ticket_digest_value=ticket["ticket_digest"], request_id="proxy-early-start", attempt=0)
            self.assertEqual(carrier.get_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, request_id="proxy-early-get")["examiner_kind"], "platform")
            carrier.abort_cleanup("proxy-early-cleanup")

        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.md"
            source_bytes = b"approved source\n"
            source_path.write_bytes(source_bytes)
            source_digest = hashlib.sha256(source_bytes).hexdigest()
            ticket = _ticket("source-artifact")
            ticket["approved_sources"] = [{"path": "source.md", "sha256": source_digest}]
            ticket["source_bundle_digest"] = hashlib.sha256(json.dumps(ticket["approved_sources"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            ticket["ticket_digest"] = ticket_digest(ticket)
            for receipt in ticket["modeling_receipts"]:
                receipt["evidence_ref"]["ticket_digest"] = ticket["ticket_digest"]
            ticket["ticket_digest"] = ticket_digest(ticket)
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance", source_materials={"source.md": source_path})
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            handle = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=projection, input_digest=digest, ticket_digest_value=ticket["ticket_digest"], request_id="source-artifact-start", attempt=0)
            source_report = _report(ticket, handle, kind="source")
            source_ref = source_report["evidence_refs"][0]
            source_ref["artifact_path"] = f"acceptance/{ticket['acceptance_round_id']}/approved-source/source.md.json"
            source_ref["artifact_digest"] = "f" * 64
            with self.assertRaisesRegex(AcceptanceContractError, "approved manifest"):
                carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, report=source_report)
            self.assertFalse((carrier.acceptance_root / ticket["acceptance_round_id"] / "source-report.json").exists())

            # A correct digest is still insufficient when the report points at a
            # virtual or otherwise non-canonical retained artifact path.
            source_ref["artifact_digest"] = source_digest
            source_ref["artifact_path"] = "evidence/source.md"
            with self.assertRaisesRegex(AcceptanceContractError, "artifact path"):
                carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, report=source_report)
            self.assertFalse((carrier.acceptance_root / ticket["acceptance_round_id"] / "source-report.json").exists())

            # The exact approved path and manifest digest bind a retained source
            # metadata artifact, after which the report is durable.
            source_ref["artifact_path"] = f"acceptance/{ticket['acceptance_round_id']}/approved-source/source.md.json"
            accepted_source = carrier.ingest_report(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, report=source_report)
            retained = carrier.root / accepted_source["evidence_refs"][0]["artifact_path"]
            self.assertEqual(json.loads(retained.read_text(encoding="utf-8")), {"path": "source.md", "sha256": source_digest})
            carrier.abort_cleanup("source-artifact-cleanup")

        with tempfile.TemporaryDirectory() as directory:
            # If a child submits an invalid report before its factory returns, the
            # queued report must fail the start transaction and leave no ghost
            # handle/resource/attempt or retained report artifact behind.
            ticket = _two_cq_ticket("proxy-early-invalid", "cq1")

            class InvalidEarlyResource(Resource):
                def __init__(self, spec: dict) -> None:
                    super().__init__(spec)
                    if spec["kind"] == "platform":
                        pseudo_handle = SimpleNamespace(
                            digest=spec["child_handle_digest"],
                            session_id=spec["session_id"],
                            input_digest=spec["input_digest"],
                        )
                        invalid = _report(ticket, pseudo_handle, kind="platform")
                        invalid["evidence_refs"][0]["artifact_path"] = "evidence/never-retained.json"
                        queued = spec["report_submit"](invalid)
                        if queued.get("status") != "queued":
                            raise AssertionError("invalid early report was not queued")

            carrier = RunnerAcceptanceCarrier(
                Path(directory) / "carrier",
                task_id="task-r23005",
                acceptance_id="acceptance",
                child_factory=InvalidEarlyResource,
            )
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="platform")
            with self.assertRaisesRegex(AcceptanceContractError, "scoped proxy receipt"):
                carrier.start_child(
                    acceptance_id="acceptance",
                    round_id=ticket["acceptance_round_id"],
                    kind="platform",
                    input_ref=projection,
                    input_digest=digest,
                    ticket_digest_value=ticket["ticket_digest"],
                    request_id="proxy-early-invalid-start",
                    attempt=0,
                )
            self.assertFalse(carrier._handles)
            self.assertFalse(carrier._resources)
            self.assertFalse(carrier._pending_reports)
            self.assertNotIn("platform", carrier._rounds[ticket["acceptance_round_id"]]["children"])
            self.assertNotIn("platform", carrier._rounds[ticket["acceptance_round_id"]]["attempts"])
            self.assertFalse((carrier.acceptance_root / ticket["acceptance_round_id"] / "platform-report.json").exists())
            carrier.abort_cleanup("proxy-early-invalid-cleanup")

    def test_c_settlement_fails_closed_without_explicit_reader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            first = _two_cq_ticket("reader-1", "cq1")
            second = _two_cq_ticket("reader-2", "cq2")
            # Child-boundary revalidation is intentionally exercised with an
            # explicit reader, then remove it to prove settlement cannot silently
            # compare the frozen snapshot to itself.
            _run_round(carrier, first, "reader-cq1")
            _run_round(carrier, second, "reader-cq2")
            carrier._model_state_reader = None
            with self.assertRaisesRegex(AcceptanceContractError, "explicit model-state reader"):
                carrier.settle()

    def test_c_settlement_readiness_with_zero_rounds_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            ticket = _two_cq_ticket("zero-rounds", "cq1")
            carrier.bind_model_state(
                ticket["model_state"],
                state_reader=lambda: ticket["model_state"],
            )
            # R2.3-009 start7 crash (2026-08-20): settlement readiness ran
            # after the acceptance-stage handoff but before the first round
            # existed; empty rounds must report not-ready instead of raising
            # IndexError and tearing the whole run down.
            self.assertFalse(carrier.settlement_ready())

    def test_c_model_state_digest_rejects_arbitrary_hex_placeholder(self) -> None:
        ticket = _two_cq_ticket("digest", "cq1")
        forged = dict(ticket["model_state"])
        forged["state_digest"] = "f" * 64
        with self.assertRaisesRegex(AcceptanceContractError, "canonical state"):
            validate_model_state(forged)

    def test_c_acceptance_terminal_is_guarded_until_settlement_and_coordinator_is_last(self) -> None:
        class AcceptanceState:
            is_settled = False

        roles = [
            SimpleNamespace(agent_id=name, package=SimpleNamespace(role=name))
            for name in ("coordinator", "modeling", "protocol", "acceptance")
        ]
        runner = TeamRunner(repository_root=Path.cwd(), adapter=SimpleNamespace(terminal_report_blocked=lambda *_args: False))
        runner.run = SimpleNamespace(
            configuration=SimpleNamespace(
                task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
                profile=SimpleNamespace(profile_id="r2-3-005-modeling-team", agents=roles),
            )
        )
        acceptance = AcceptanceState()
        runner.acceptance = acceptance
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "transport",
                {(sender, recipient) for sender in ("coordinator", "modeling", "protocol", "acceptance") for recipient in ("coordinator", "modeling", "protocol", "acceptance") if sender != recipient},
                terminal_dependencies={
                    "modeling": {"acceptance"},
                    "protocol": {"modeling"},
                    "coordinator": {"modeling", "protocol", "acceptance"},
                },
                modeling_agent_id="modeling",
                terminal_report_guard=runner._terminal_report_guard,
            )
            with self.assertRaisesRegex(RoutingError, "Acceptance settlement"):
                broker.report("acceptance", "completed", "premature")
            self.assertNotIn("acceptance", broker.results)
            # R2.3-009 follow-up (user 2026-08-20): ``blocked`` is a
            # self-declaration and no longer waits for the settled-Acceptance
            # handoff; ``completed`` still cannot cross it.
            with self.assertRaises(RoutingError):
                broker.report("modeling", "completed", "modeling must await settled Acceptance")
            broker.report("modeling", "blocked", "modeling self-declared stuck")
            acceptance.is_settled = True
            broker.report("acceptance", "completed", "acceptance settled")
            broker.ack_terminal_handoff("modeling", "acceptance")
            broker.ack_terminal_handoff("protocol", "modeling")
            broker.report("protocol", "completed", "protocol")
            broker.ack_terminal_handoff("coordinator", "modeling")
            broker.ack_terminal_handoff("coordinator", "protocol")
            broker.ack_terminal_handoff("coordinator", "acceptance")
            coordinator = broker.report("coordinator", "completed", "coordinator")
            self.assertEqual(coordinator.agent_id, "coordinator")
            with self.assertRaisesRegex(RoutingError, "already reported"):
                broker.report("acceptance", "completed", "acceptance-again")
            broker.stop()

    def test_terminal_guard_status_only_bypasses_protocol_retrieval_gate(self) -> None:
        class RetrievalGuard:
            def terminal_report_blocked(
                self,
                agent_id: str,
                _already_synchronized: bool = False,
                status: str = "completed",
            ) -> bool:
                return agent_id == "protocol" and status == "completed"

        class AcceptanceState:
            is_settled = False

        roles = [
            SimpleNamespace(agent_id=name, package=SimpleNamespace(role=name))
            for name in ("coordinator", "modeling", "protocol", "acceptance")
        ]
        runner = TeamRunner(repository_root=Path.cwd(), adapter=RetrievalGuard())
        runner.run = SimpleNamespace(
            configuration=SimpleNamespace(
                task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
                profile=SimpleNamespace(profile_id="r2-3-005-modeling-team", agents=roles),
            )
        )
        runner.acceptance = AcceptanceState()
        self.assertFalse(runner._terminal_report_guard("protocol", True, "blocked"))
        # T0 defense review (user 2026-08-20): acceptance/coordinator
        # ``blocked`` self-declares too -- gating it on verdict settlement
        # left an unrepairable run no exit but the 90-minute T3 timeout.
        self.assertFalse(runner._terminal_report_guard("acceptance", True, "blocked"))
        self.assertFalse(runner._terminal_report_guard("coordinator", True, "blocked"))
        with tempfile.TemporaryDirectory() as directory:
            broker = TeamTransportBroker(
                Path(directory) / "transport",
                set(),
                terminal_dependencies={
                    "modeling": {"acceptance"},
                    "protocol": {"modeling"},
                    "coordinator": {"modeling", "protocol", "acceptance"},
                },
                modeling_agent_id="modeling",
                terminal_report_guard=runner._terminal_report_guard,
            )
            with self.assertRaisesRegex(RoutingError, "Protocol retrieval evidence is incomplete"):
                broker.report("protocol", "completed", "retrieval incomplete")
            # R2.3-009 follow-up (user 2026-08-20): ``blocked`` self-declares
            # and bypasses both the retrieval guard and the handoff
            # dependency.  T0 defense review (same day): acceptance and
            # coordinator ``blocked`` self-declare as well; settlement
            # machinery gates only ``completed``.
            broker.report("protocol", "blocked", "bounded recovery")
            broker.report("modeling", "blocked", "modeling awaits Acceptance")
            self.assertEqual(broker.results["protocol"].status, "blocked")
            self.assertEqual(broker.results["modeling"].status, "blocked")

            broker.report("acceptance", "blocked", "acceptance is not settled")
            broker.report("coordinator", "blocked", "coordinator is not settled")
            self.assertEqual(broker.results["acceptance"].status, "blocked")
            self.assertEqual(broker.results["coordinator"].status, "blocked")

    def test_c_acceptance_finalization_serializes_drain_and_completed_guard(self) -> None:
        """Two concurrent settlement observers produce one CAS, evidence row, and handoff."""

        class GuardAdapter:
            def __init__(self) -> None:
                self.sent: list[tuple[str, object]] = []

            def terminal_report_blocked(self, *_args: object) -> bool:
                return False

            def send_message(self, recipient_id: str, delivery: object) -> None:
                self.sent.append((recipient_id, delivery))

            def receive_messages(self) -> list[object]:
                return []

            def stop(self) -> None:
                return None

            def cleanup_identifiers(self) -> dict[str, object]:
                return {}

            def wait_settled(self, _agent_ids: list[str], _timeout: float) -> bool:
                return False

        roles = [
            SimpleNamespace(agent_id=name, package=SimpleNamespace(role=name))
            for name in ("coordinator", "modeling", "protocol", "acceptance")
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_root = root / "run"
            (run_root / "evidence").mkdir(parents=True)
            carrier = RunnerAcceptanceCarrier(
                root / "carrier", task_id="task-r23005", acceptance_id="acceptance"
            )
            first = _two_cq_ticket("race-1", "cq1")
            second = _two_cq_ticket("race-2", "cq2")
            _run_round(carrier, first, "race-cq1")
            _run_round(carrier, second, "race-cq2")
            self.assertTrue(carrier.settlement_ready())

            adapter = GuardAdapter()
            runner = TeamRunner(repository_root=root, adapter=adapter)
            runner.run = SimpleNamespace(
                root=run_root,
                run_id="run-r23005-race",
                configuration=SimpleNamespace(
                    task=SimpleNamespace(schema_version=2, task_id="r2-3-005-formal-acceptance"),
                    profile=SimpleNamespace(
                        profile_id="r2-3-005-modeling-team", agents=roles
                    ),
                ),
            )
            runner.acceptance = carrier
            permissions = {
                (sender, recipient)
                for sender in ("coordinator", "modeling", "protocol", "acceptance")
                for recipient in ("coordinator", "modeling", "protocol", "acceptance")
                if sender != recipient
            }
            broker = TeamTransportBroker(
                root / "transport",
                permissions,
                terminal_dependencies={
                    "modeling": {"acceptance"},
                    "protocol": {"modeling"},
                    "coordinator": {"modeling", "protocol", "acceptance"},
                },
                modeling_agent_id="modeling",
                terminal_report_guard=runner._terminal_report_guard,
            )
            runner.transport = broker

            entered = threading.Event()
            release = threading.Event()
            settle_calls = 0
            original_settle = carrier.settle

            def synchronized_settle() -> dict:
                nonlocal settle_calls
                settle_calls += 1
                entered.set()
                if not release.wait(timeout=5):
                    raise AssertionError("settlement release timed out")
                return original_settle()

            carrier.settle = synchronized_settle  # type: ignore[method-assign]
            foreground = threading.Thread(target=runner._finalize_acceptance_if_ready)
            foreground.start()
            self.assertTrue(entered.wait(timeout=5))
            guard_result: list[bool] = []
            guarded = threading.Thread(
                target=lambda: guard_result.append(
                    runner._terminal_report_guard("acceptance", True, "completed")
                )
            )
            guarded.start()
            release.set()
            foreground.join(timeout=5)
            guarded.join(timeout=5)
            self.assertFalse(foreground.is_alive())
            self.assertFalse(guarded.is_alive())
            self.assertEqual(settle_calls, 1)
            self.assertEqual(guard_result, [False])
            self.assertTrue(carrier.is_settled)
            self.assertEqual(
                len((runner.run.root / "evidence" / "acceptance-settlement.jsonl").read_text().splitlines()),
                1,
            )
            self.assertEqual(len(list((root / "carrier").rglob("settlement-cas.json"))), 1)
            self.assertEqual(len(list((root / "carrier").rglob("settlement.json"))), 1)

            # T0 defense review (user 2026-08-20): a settled carrier no longer
            # rejects ``blocked`` (covered in the guard test above; one
            # terminal result per agent prevents exercising both here).
            # ``completed`` remains the verdict-bearing path and still
            # requires settlement.
            completed = broker.report("acceptance", "completed", "acceptance settled")
            self.assertEqual(completed.status, "completed")

            # The real Runner drain emits the Acceptance -> Modeling handoff once;
            # a second drain observes the acknowledgement and emits no duplicate.
            runner.drain()
            runner.drain()
            modeling_handoffs = [
                delivery
                for recipient, delivery in adapter.sent
                if recipient == "modeling" and getattr(delivery, "kind", None) == "terminal-handoff"
            ]
            self.assertEqual(len(modeling_handoffs), 1)
            broker.stop()
            carrier.cleanup()

    def test_c31_c47_infrastructure_abort_keeps_acceptance_live_until_explicit_abort_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            ticket = _ticket("1")
            carrier.publish_ticket(ticket, coordinator_id="coordinator", owner_revision=ticket["quality_standard_ref"])
            carrier.ack_ticket(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], ticket_digest_value=ticket["ticket_digest"])
            projection, digest = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            handle = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=projection, input_digest=digest, ticket_digest_value=ticket["ticket_digest"], request_id="infra-start-0", attempt=0)
            failure0 = carrier.record_infrastructure_failure(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, failure_category="runtime.child-crash", reason_code="runtime.child-crash")
            carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle, completion_ref={"infrastructure_failure_digest": failure0.failure_digest}, request_id="infra-recycle-0")
            projection1, digest1 = carrier.project_child_input(round_id=ticket["acceptance_round_id"], kind="source")
            handle1 = carrier.start_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], kind="source", input_ref=projection1, input_digest=digest1, ticket_digest_value=ticket["ticket_digest"], request_id="infra-start-1", attempt=1)
            failure1 = carrier.record_infrastructure_failure(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle1, failure_category="runtime.child-crash", reason_code="runtime.child-crash")
            receipt = carrier.recycle_child(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], handle=handle1, completion_ref={"infrastructure_failure_digest": failure1.failure_digest}, request_id="infra-recycle-1")
            self.assertTrue(carrier.is_live)
            self.assertEqual(carrier.round_summary(ticket["acceptance_round_id"])["status"], "blocked")
            ref = carrier.failure_evidence_ref(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], failure_digest=failure1.failure_digest, cleanup_receipt_digest=receipt.receipt_digest)
            self.assertEqual(ref["type"], "infrastructure_failure")
            cleanup = carrier.abort_cleanup("runtime-infrastructure")
            self.assertEqual(cleanup["status"], "aborted")

    def test_c57_verdict_submission_replays_only_the_same_request_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(Path(directory) / "carrier", task_id="task-r23005", acceptance_id="acceptance")
            ticket = _two_cq_ticket("1", "cq1")
            verdict = _run_round(carrier, ticket, "idempotent")
            receipt = carrier.submit_verdict(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], verdict=verdict, request_id="idempotent-verdict")
            self.assertEqual(receipt.verdict_digest, verdict["verdict_digest"])
            with self.assertRaises(AcceptanceContractError):
                changed = dict(verdict)
                changed["summary"] = "conflicting retry"
                carrier.submit_verdict(acceptance_id="acceptance", round_id=ticket["acceptance_round_id"], verdict=changed, request_id="different-request")
            carrier.abort_cleanup("test-cleanup")


if __name__ == "__main__":
    unittest.main()
