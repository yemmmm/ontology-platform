"""Start73 report/watchdog terminal arbitration regressions.

These tests stay below the semantic boundary: a deterministic child resource and
the Host-owned report/failure callbacks are enough to prove ordering, rollback,
and cleanup without starting a model or provider process.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

from modeling_team.acceptance import (
    AcceptanceContractError,
    RunnerAcceptanceCarrier,
    ticket_digest,
)
from modeling_team.runtimes.codex import _CodexChildResource
from modeling_team.tests.test_r23005_contracts import _report, _ticket


class _ProbeProcess:
    def __init__(self) -> None:
        self.terminate_count = 0
        self.kill_count = 0

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        self.terminate_count += 1

    def kill(self) -> None:
        self.kill_count += 1

    def wait(self, timeout: float | None = None) -> int:
        return 0


def _start(
    carrier: RunnerAcceptanceCarrier,
    ticket: dict[str, Any],
    *,
    request_id: str,
) -> Any:
    projection, digest = carrier.project_child_input(
        round_id=ticket["acceptance_round_id"], kind="source"
    )
    return carrier.start_child(
        acceptance_id="acceptance",
        round_id=ticket["acceptance_round_id"],
        kind="source",
        input_ref=projection,
        input_digest=digest,
        ticket_digest_value=ticket["ticket_digest"],
        request_id=request_id,
        attempt=0,
    )


class Start73ReportWatchdogRaceTests(unittest.TestCase):
    def _carrier(
        self,
        directory: str,
        ticket: dict[str, Any],
        resources: list[_CodexChildResource],
    ) -> RunnerAcceptanceCarrier:
        def factory(spec: dict[str, Any]) -> _CodexChildResource:
            process = _ProbeProcess()
            # Keep the watchdog bounded for the report-first assertion.  The
            # report callback must win before this deadline without killing the
            # process or creating a failure record.
            spec["timeout_seconds"] = 0.03
            resource = _CodexChildResource(spec, process)
            resources.append(resource)
            return resource

        carrier = RunnerAcceptanceCarrier(
            Path(directory),
            task_id=ticket["task_id"],
            acceptance_id="acceptance",
            child_factory=factory,
        )
        carrier.publish_ticket(
            ticket,
            coordinator_id="coordinator",
            owner_revision=ticket["quality_standard_ref"],
        )
        carrier.ack_ticket(
            acceptance_id="acceptance",
            round_id=ticket["acceptance_round_id"],
            ticket_digest_value=ticket["ticket_digest"],
        )
        return carrier

    def test_report_first_late_watchdog_is_ignored_and_child_recycles(self) -> None:
        ticket = _ticket("start73-report-first")
        resources: list[_CodexChildResource] = []
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(directory, ticket, resources)
            handle = _start(carrier, ticket, request_id="report-first")
            resource = resources[0]
            self.assertNotIn("defer_output_pump", resource.spec)
            report = resource.spec["report_submit"](_report(ticket, handle, kind="source"))
            # Let the watchdog deadline expire.  The report terminal claim must
            # make its callback return false and must not terminate the process.
            time.sleep(0.08)
            self.assertEqual(carrier._failures, {})
            self.assertEqual(resource.failure_evidence(), None)
            process = resource.process
            self.assertIsNotNone(process)
            self.assertEqual(process.terminate_count, 0)
            self.assertEqual(process.kill_count, 0)
            cleanup = carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle,
                completion_ref={"terminal_report_digest": report["report_digest"]},
                request_id="report-first-recycle",
            )
            self.assertEqual(cleanup.completion_kind, "terminal_report")
            self.assertNotIn(handle.token, carrier._handles)
            carrier.cleanup()

    def test_failure_first_rejects_late_report_and_late_recycle_callbacks(self) -> None:
        ticket = _ticket("start73-failure-first")
        resources: list[_CodexChildResource] = []
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(directory, ticket, resources)
            handle = _start(carrier, ticket, request_id="failure-first")
            resource = resources[0]
            self.assertTrue(resource._record_failure("runtime", "child-timeout"))
            failure = next(iter(carrier._failures.values()))
            submit_report = resource.spec["report_submit"]
            submit_failure = resource.spec["record_infrastructure_failure"]
            with self.assertRaisesRegex(AcceptanceContractError, "conflicts with infrastructure failure"):
                submit_report(_report(ticket, handle, kind="source"))
            cleanup = carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle,
                completion_ref={"infrastructure_failure_digest": failure.failure_digest},
                request_id="failure-first-recycle",
            )
            self.assertEqual(cleanup.completion_kind, "infrastructure_failure")
            with self.assertRaises(AcceptanceContractError):
                submit_report(_report(ticket, handle, kind="source"))
            with self.assertRaises(AcceptanceContractError):
                submit_failure("runtime", "late-watchdog")
            carrier.cleanup()

    def test_two_thread_report_failure_race_has_one_terminal_winner(self) -> None:
        ticket = _ticket("start73-two-thread")
        resources: list[_CodexChildResource] = []
        with tempfile.TemporaryDirectory() as directory:
            carrier = self._carrier(directory, ticket, resources)
            handle = _start(carrier, ticket, request_id="two-thread")
            resource = resources[0]
            barrier = threading.Barrier(3)
            outcomes: list[tuple[str, str]] = []

            def submit_report() -> None:
                barrier.wait()
                try:
                    result = resource.spec["report_submit"](_report(ticket, handle, kind="source"))
                    outcomes.append(("report", str(result.get("report_digest"))))
                except Exception as exc:  # expected only when failure wins
                    outcomes.append(("report-error", type(exc).__name__))

            def submit_failure() -> None:
                barrier.wait()
                try:
                    result = resource.spec["record_infrastructure_failure"]("runtime", "child-crash")
                    outcomes.append(("failure", "none" if result is None else "recorded"))
                except Exception as exc:
                    outcomes.append(("failure-error", type(exc).__name__))

            report_thread = threading.Thread(target=submit_report)
            failure_thread = threading.Thread(target=submit_failure)
            report_thread.start()
            failure_thread.start()
            barrier.wait()
            report_thread.join(timeout=2)
            failure_thread.join(timeout=2)
            self.assertFalse(report_thread.is_alive())
            self.assertFalse(failure_thread.is_alive())
            self.assertEqual(len(outcomes), 2)
            self.assertLessEqual(len(carrier._reports) + len(carrier._failures), 1)
            if carrier._reports:
                report = next(iter(carrier._reports.values()))
                completion_ref = {"terminal_report_digest": report["report_digest"]}
            else:
                failure = next(iter(carrier._failures.values()))
                completion_ref = {"infrastructure_failure_digest": failure.failure_digest}
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle,
                completion_ref=completion_ref,
                request_id="two-thread-recycle",
            )
            carrier.cleanup()

    def test_report_append_failure_rolls_back_candidate_state(self) -> None:
        ticket = _ticket("start73-append-failure")
        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory),
                task_id=ticket["task_id"],
                acceptance_id="acceptance",
            )
            carrier.publish_ticket(
                ticket,
                coordinator_id="coordinator",
                owner_revision=ticket["quality_standard_ref"],
            )
            carrier.ack_ticket(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                ticket_digest_value=ticket["ticket_digest"],
            )
            handle = _start(carrier, ticket, request_id="append-failure")
            report = _report(ticket, handle, kind="source")
            original_append = carrier._append

            def fail_report_append(round_id: str, name: str, value: Any) -> None:
                if name == "source-report.json":
                    raise OSError("injected append failure")
                original_append(round_id, name, value)

            carrier._append = fail_report_append  # type: ignore[method-assign]
            try:
                with self.assertRaises(OSError):
                    carrier.ingest_report(
                        acceptance_id="acceptance",
                        round_id=ticket["acceptance_round_id"],
                        handle=handle,
                        report=report,
                    )
            finally:
                carrier._append = original_append  # type: ignore[method-assign]
            self.assertNotIn(handle.token, carrier._reports)
            self.assertNotIn("source", carrier._rounds[ticket["acceptance_round_id"]]["reports"])
            self.assertFalse(
                (carrier.acceptance_root / ticket["acceptance_round_id"] / "source-report.json").exists()
            )
            carrier.cleanup()

    def test_cleanup_marker_rejects_callback_while_stop_joins(self) -> None:
        ticket = _ticket("start73-cleanup-marker")
        late_errors: list[str] = []
        resource_ref: list[Any] = []

        class CleanupResource:
            def __init__(self, spec: dict[str, Any]) -> None:
                self.spec = spec
                self.stopped = False
                self.destroyed = False
                resource_ref.append(self)

            def stop(self) -> None:
                def late_callback() -> None:
                    try:
                        self.spec["report_submit"]({})
                    except Exception as exc:
                        late_errors.append(type(exc).__name__)

                callback_thread = threading.Thread(target=late_callback)
                callback_thread.start()
                callback_thread.join(timeout=1)
                self.stopped = True

            def destroy(self) -> None:
                self.destroyed = True

        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory),
                task_id=ticket["task_id"],
                acceptance_id="acceptance",
                child_factory=CleanupResource,
            )
            carrier.publish_ticket(
                ticket,
                coordinator_id="coordinator",
                owner_revision=ticket["quality_standard_ref"],
            )
            carrier.ack_ticket(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                ticket_digest_value=ticket["ticket_digest"],
            )
            _start(carrier, ticket, request_id="cleanup-marker")
            result = carrier.cleanup()
            self.assertIn(result["status"], {"cleaned", "aborted"})
            self.assertTrue(resource_ref[0].stopped)
            self.assertTrue(resource_ref[0].destroyed)
            self.assertEqual(late_errors, ["AcceptanceContractError"])

    def test_formal_pump_activation_happens_after_resource_registration(self) -> None:
        ticket = _ticket("start73-formal-pump")
        ticket["task_id"] = "r2-3-005-formal-acceptance"
        ticket["ticket_digest"] = ticket_digest(ticket)
        for receipt in ticket["modeling_receipts"]:
            receipt["evidence_ref"]["ticket_digest"] = ticket["ticket_digest"]
        carrier_ref: list[RunnerAcceptanceCarrier] = []
        resources: list[Any] = []

        class ActivationResource:
            def __init__(self, spec: dict[str, Any]) -> None:
                self.spec = spec
                self.stopped = False
                self.destroyed = False
                self.activation_count = 0
                self.registered_at_activation = False
                resources.append(self)

            def activate_output_pump(self) -> None:
                self.activation_count += 1
                self.registered_at_activation = (
                    bool(carrier_ref)
                    and any(
                        receipt.child_handle_digest == self.spec["child_handle_digest"]
                        for receipt, _resource in carrier_ref[0]._resources.values()
                    )
                )

            def stop(self) -> None:
                self.stopped = True

            def destroy(self) -> None:
                self.destroyed = True

        with tempfile.TemporaryDirectory() as directory:
            carrier = RunnerAcceptanceCarrier(
                Path(directory),
                task_id=ticket["task_id"],
                acceptance_id="acceptance",
                child_factory=ActivationResource,
            )
            carrier_ref.append(carrier)
            carrier.publish_ticket(
                ticket,
                coordinator_id="coordinator",
                owner_revision=ticket["quality_standard_ref"],
            )
            carrier.ack_ticket(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                ticket_digest_value=ticket["ticket_digest"],
            )
            handle = _start(carrier, ticket, request_id="formal-pump")
            resource = resources[0]
            self.assertTrue(resource.spec["defer_output_pump"])
            self.assertEqual(resource.activation_count, 1)
            self.assertTrue(resource.registered_at_activation)
            failure = carrier.record_infrastructure_failure(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle,
                failure_category="runtime",
                reason_code="activation-test",
            )
            assert failure is not None
            carrier.recycle_child(
                acceptance_id="acceptance",
                round_id=ticket["acceptance_round_id"],
                handle=handle,
                completion_ref={"infrastructure_failure_digest": failure.failure_digest},
                request_id="formal-pump-recycle",
            )



if __name__ == "__main__":
    unittest.main()
