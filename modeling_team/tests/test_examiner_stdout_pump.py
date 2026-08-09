"""Focused tests for the Examiner child stdout pump and elicitation repair.

These tests build a scripted App Server on real ``os.pipe()`` file descriptors
because ``CodexRuntimeAdapter._read_output_line`` drives ``select`` plus
``os.read`` and a ``StringIO`` stdout is insufficient.  The scripted server
answers ``initialize``/``thread-start``/``mcpServerStatus/list``/``turn-start``
and then writes post-``turn/start`` notifications that only the new
lifecycle-owned pump can drain.
"""

from __future__ import annotations

import json
import os
import select
import socket
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

from modeling_team.acceptance_runtime import PLATFORM_PROXY_READ_TOOLS
from modeling_team.contracts import repository_root
from modeling_team.runtimes.codex import CodexRuntimeAdapter


def _source_report_payload() -> dict[str, Any]:
    return {
        "answerability": "answerable",
        "conclusion": "matched",
        "evidence": [],
        "coverage": {"queries_or_sections": [], "complete": True},
        "gaps": [],
        "evidence_refs": [{"location": "source.md"}],
    }


def _platform_report_payload() -> dict[str, Any]:
    return {
        "answerability": "answerable",
        "conclusion": "matched",
        "evidence": [],
        "coverage": {"queries_or_sections": [], "complete": True},
        "gaps": [],
        "evidence_refs": [
            {
                "ref_id": "ref-1",
                "tool": "get_ontology_read_model",
                "request_digest": "a" * 64,
                "response_digest": "b" * 64,
                "artifact_path": "artifact.json",
                "page": {
                    "ordinal": 0,
                    "input_cursor": None,
                    "output_cursor": None,
                    "has_more": False,
                    "sequence_complete": True,
                },
            }
        ],
    }


class _ScriptedAppServer:
    """Process double backed by real pipes; a thread answers JSON-RPC traffic.

    The adapter writes requests and server-request responses to ``stdin`` and
    reads App Server output from ``stdout`` via ``os.read`` on the fileno.  The
    server thread reads adapter requests (lines carrying ``method``) and writes
    scripted results; after the ``turn/start`` response it writes the configured
    post-start notification lines, which only the lifecycle-owned pump drains.
    The server thread starts in ``__init__`` so it can answer startup RPCs.
    """

    def __init__(
        self,
        *,
        kind: str,
        post_lines: tuple[dict[str, Any], ...] = (),
        close_stdout_after_post: bool = False,
        malformed_after_post: bool = False,
        nonzero_exit_after_post: bool = False,
        report_payload: dict[str, Any] | None = None,
        report_socket: Path | None = None,
        report_token_path: Path | None = None,
        thread_start_error: bool = False,
    ) -> None:
        self._kind = kind
        self._post_lines = post_lines
        self._close_stdout_after_post = close_stdout_after_post
        self._malformed_after_post = malformed_after_post
        self._nonzero_exit_after_post = nonzero_exit_after_post
        self._report_payload = report_payload
        self._report_socket = report_socket
        self._report_token_path = report_token_path
        self._thread_start_error = thread_start_error

        req_read_fd, req_write_fd = os.pipe()
        resp_read_fd, resp_write_fd = os.pipe()
        # The adapter writes requests and server-request responses to stdin and
        # reads App Server output from stdout via os.read on the fileno.
        self.stdin = os.fdopen(req_write_fd, "w", encoding="utf-8")
        self.stdout = os.fdopen(resp_read_fd, "rb", buffering=0)
        self.stderr = None
        # The server reads requests directly from the raw fd so its loop can
        # poll ``_stop`` between lines and shutdown never blocks on readline.
        self._req_read_fd = req_read_fd
        self._resp_write = os.fdopen(resp_write_fd, "w", encoding="utf-8")

        self._stop = threading.Event()
        self._terminated = threading.Event()
        self._exit_code: int | None = None
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self.captured_responses: list[dict[str, Any]] = []
        self.report_response: Any = None
        self.report_error: str | None = None
        self._report_submitted = False
        self._thread.start()

    @property
    def pid(self) -> Any:  # None avoids os.killpg touching the test process.
        return None

    def _result_for(self, method: str) -> dict[str, Any] | None:
        if method == "initialize":
            return {}
        if method == "thread/start":
            if self._thread_start_error:
                return None
            return {"thread": {"id": "child-thread"}}
        if method == "mcpServerStatus/list":
            servers = [{"name": "examiner_report", "tools": [{"name": "submit_examiner_report"}]}]
            if self._kind == "platform":
                servers.append(
                    {
                        "name": "platform_read_proxy",
                        "tools": [{"name": name} for name in PLATFORM_PROXY_READ_TOOLS],
                    }
                )
            return {"data": servers}
        if method == "turn/start":
            return {"turn": {"id": "child-turn"}}
        return {}

    def _write_line(self, payload: dict[str, Any]) -> None:
        writer = self._resp_write
        if writer is None:
            return
        writer.write(json.dumps(payload) + "\n")
        writer.flush()

    def _submit_report(self) -> None:
        socket_path = self._report_socket
        token_path = self._report_token_path
        if socket_path is None or token_path is None or self._report_payload is None:
            return
        try:
            token = token_path.read_text(encoding="utf-8")
        except OSError as exc:
            self.report_error = type(exc).__name__
            return
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(5)
                conn.connect(str(socket_path))
                conn.sendall(
                    json.dumps(
                        {"token": token, "report": self._report_payload}
                    ).encode("utf-8")
                )
                data = conn.recv(4096)
                self.report_response = json.loads(data.decode("utf-8")) if data else None
        except (OSError, ValueError) as exc:
            self.report_error = type(exc).__name__

    def _serve(self) -> None:
        buffer = ""
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([self._req_read_fd], [], [], 0.1)
            except (OSError, ValueError):
                break
            if not ready:
                continue
            try:
                chunk = os.read(self._req_read_fd, 65536)
            except (OSError, ValueError):
                break
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, _, buffer = buffer.partition("\n")
                if not self._handle_line(line):
                    return

    def _handle_line(self, raw: str) -> bool:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return True
        if "method" in value and "id" in value:
            method = value["method"]
            if method == "thread/start" and self._thread_start_error:
                self._write_line(
                    {"jsonrpc": "2.0", "id": value["id"], "error": {"code": -32000}}
                )
                return False
            result = self._result_for(method)
            if result is not None:
                self._write_line({"jsonrpc": "2.0", "id": value["id"], "result": result})
            if method == "turn/start":
                for post in self._post_lines:
                    self._write_line(post)
                if self._malformed_after_post and self._resp_write is not None:
                    self._resp_write.write("not-json-at-all\n")
                    self._resp_write.flush()
                if self._close_stdout_after_post:
                    try:
                        self._resp_write.close()
                    except (OSError, ValueError):
                        pass
                    self._resp_write = None
                if self._nonzero_exit_after_post:
                    self._exit_code = -9
        elif "result" in value:
            # A server-request response written by the pump (e.g. elicitation accept).
            self.captured_responses.append(value)
            if (
                self._report_payload is not None
                and not self._report_submitted
                and isinstance(value.get("result"), dict)
                and value["result"].get("action") == "accept"
            ):
                self._submit_report()
                self._report_submitted = True
        return True

    def poll(self) -> int | None:
        if self._exit_code is not None:
            return self._exit_code
        if self._terminated.is_set():
            return 0
        return None

    def terminate(self) -> None:
        self.close()

    def kill(self) -> None:
        self.close()

    def wait(self, timeout: float | None = None) -> int:
        self._thread.join(timeout=timeout)
        return self._exit_code if self._exit_code is not None else 0

    def close(self) -> None:
        self._terminated.set()
        self._stop.set()
        try:
            if self._resp_write is not None:
                self._resp_write.close()
        except (OSError, ValueError):
            pass
        self._resp_write = None
        for stream in (self.stdin, self.stdout):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
        try:
            os.close(self._req_read_fd)
        except (OSError, ValueError):
            pass

    def join(self, timeout: float = 5.0) -> None:
        self._thread.join(timeout=timeout)


def _build_spec(kind: str, base: Path) -> dict[str, Any]:
    private_root = base / "private-child"
    private_root.mkdir(mode=0o700, parents=True)
    (private_root / "input.json").write_text("{}", encoding="utf-8")
    spec: dict[str, Any] = {
        "task_id": "task-one",
        "acceptance_round_id": "round-one",
        "kind": kind,
        "attempt": 0,
        "session_id": "session-one",
        "child_handle_digest": "c" * 64,
        "ticket_digest": "a" * 64,
        "input_digest": "d" * 64,
        "private_root": str(private_root),
        "private_input": str(private_root / "input.json"),
        "descriptor": {"kind": f"{kind}_examiner", "package_digest": "f" * 64},
        "timeout_seconds": 30,
    }
    if kind == "platform":
        spec.update(
            {
                "read_key_id": "read-key-one",
                "read_key_digest": "e" * 64,
                "platform_read_scope": {
                    "project_id": "project-one",
                    "ontology_id": "ontology-one",
                    "graph_set_id": "graph-one",
                },
                "model_state_digest": "b" * 64,
                "allowed_read_tools": list(PLATFORM_PROXY_READ_TOOLS),
                "read_key_plaintext": "temporary-read-key",
                "read_key_revoke": lambda _key_id: None,
            }
        )
    return spec


def _child_home(base: Path) -> Path:
    return base / "private-child" / "home"


def _launch_with_script(
    *,
    kind: str,
    server: _ScriptedAppServer,
    base: Path,
) -> tuple[Any, CodexRuntimeAdapter]:
    auth_home = base / "codex-home"
    auth_home.mkdir(mode=0o700)
    (auth_home / "auth.json").write_text("{}", encoding="utf-8")
    (auth_home / "auth.json").chmod(0o600)
    root = repository_root()

    def process_factory(_command, **_kwargs):
        return server

    adapter = CodexRuntimeAdapter(
        repository_root=root,
        use_bwrap=False,
        process_factory=process_factory,
    )
    adapter._run_root = base
    spec = _build_spec(kind, base)
    with unittest.mock.patch.dict(os.environ, {"CODEX_HOME": str(auth_home)}, clear=False):
        resource = adapter.acceptance_child_factory(spec)
    return resource, adapter


def _wait_for(predicate, *, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class ExaminerStdoutPumpTests(unittest.TestCase):
    def test_source_examiner_pump_drains_elicitation_and_publishes_report(self) -> None:
        elicitation = {
            "jsonrpc": "2.0",
            "id": 7001,
            "method": "mcpServer/elicitation/request",
            "params": {
                "serverName": "examiner_report",
                "mode": "form",
                "message": "private-elicitation-text",
                "requestedSchema": {"type": "object", "properties": {}},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report_socket = _child_home(base) / "report.sock"
            report_token_path = _child_home(base) / "report-sink.token"
            server = _ScriptedAppServer(
                kind="source",
                post_lines=(elicitation,),
                report_payload=_source_report_payload(),
                report_socket=report_socket,
                report_token_path=report_token_path,
            )
            self.addCleanup(server.close)
            resource, _adapter = _launch_with_script(kind="source", server=server, base=base)
            try:
                # The socket root is the child home for the short temp path.
                self.assertEqual(Path(str(resource.report_sink.socket_path)), report_socket)
                delivered = _wait_for(lambda: len(resource.submitted_reports) > 0)
                self.assertTrue(delivered, "six-field report was not published to report.sock")
                self.assertEqual(resource.submitted_reports[0], _source_report_payload())
                self.assertTrue(
                    _wait_for(
                        lambda: any(
                            r.get("result", {}).get("action") == "accept"
                            for r in server.captured_responses
                        )
                    )
                )
                self.assertIsNone(server.report_error)
                self.assertEqual(server.report_response, {"ok": True})
                evidence = (base / "evidence" / "mcp-elicitations.jsonl").read_text(encoding="utf-8")
                self.assertIn('"action": "accept"', evidence)
                self.assertNotIn("private-elicitation-text", evidence)
            finally:
                resource.destroy()
            server.join()
            self.assertFalse(server._thread.is_alive())

    def test_platform_examiner_pump_admits_platform_read_proxy(self) -> None:
        elicitation = {
            "jsonrpc": "2.0",
            "id": 7002,
            "method": "mcpServer/elicitation/request",
            "params": {
                "serverName": "platform_read_proxy",
                "mode": "form",
                "message": "private-platform-text",
                "requestedSchema": {"type": "object", "properties": {}},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report_socket = _child_home(base) / "report.sock"
            report_token_path = _child_home(base) / "report-sink.token"
            server = _ScriptedAppServer(
                kind="platform",
                post_lines=(elicitation,),
                report_payload=_platform_report_payload(),
                report_socket=report_socket,
                report_token_path=report_token_path,
            )
            self.addCleanup(server.close)
            resource, _adapter = _launch_with_script(kind="platform", server=server, base=base)
            try:
                self.assertTrue(
                    _wait_for(
                        lambda: any(
                            r.get("result", {}).get("action") == "accept"
                            for r in server.captured_responses
                        )
                    )
                )
                delivered = _wait_for(lambda: len(resource.submitted_reports) > 0)
                self.assertTrue(delivered, "platform six-field report was not published")
                self.assertEqual(resource.submitted_reports[0], _platform_report_payload())
            finally:
                resource.destroy()
            server.join()
            self.assertFalse(server._thread.is_alive())

    def test_pump_records_fixed_runtime_failure_on_stdout_close(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            server = _ScriptedAppServer(
                kind="source",
                post_lines=(),
                close_stdout_after_post=True,
            )
            self.addCleanup(server.close)
            resource, _adapter = _launch_with_script(kind="source", server=server, base=base)
            try:
                recorded = _wait_for(lambda: resource.failure_evidence() is not None)
                self.assertTrue(recorded, "pump did not record the EOF failure")
                evidence = resource.failure_evidence()
                self.assertEqual(evidence["failure_category"], "runtime")
                self.assertEqual(evidence["reason_code"], "child-output-closed")
                self.assertNotIn("Traceback", json.dumps(evidence))
            finally:
                resource.destroy()
            server.join()

    def test_pump_records_fixed_runtime_failure_on_malformed_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            server = _ScriptedAppServer(
                kind="source",
                post_lines=(),
                malformed_after_post=True,
            )
            self.addCleanup(server.close)
            resource, _adapter = _launch_with_script(kind="source", server=server, base=base)
            try:
                recorded = _wait_for(lambda: resource.failure_evidence() is not None)
                self.assertTrue(recorded, "pump did not record the malformed-line failure")
                evidence = resource.failure_evidence()
                self.assertEqual(evidence["failure_category"], "runtime")
                self.assertEqual(evidence["reason_code"], "child-output-malformed")
            finally:
                resource.destroy()
            server.join()

    def test_pump_failure_does_not_overwrite_delivered_report(self) -> None:
        elicitation = {
            "jsonrpc": "2.0",
            "id": 7003,
            "method": "mcpServer/elicitation/request",
            "params": {"serverName": "examiner_report", "mode": "form", "requestedSchema": {}},
        }
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report_socket = _child_home(base) / "report.sock"
            report_token_path = _child_home(base) / "report-sink.token"
            server = _ScriptedAppServer(
                kind="source",
                post_lines=(elicitation,),
                report_payload=_source_report_payload(),
                # After the report is delivered, the App Server dies (non-zero exit)
                # and closes stdout, so the pump observes a real failure.
                nonzero_exit_after_post=True,
                close_stdout_after_post=True,
                report_socket=report_socket,
                report_token_path=report_token_path,
            )
            self.addCleanup(server.close)
            resource, _adapter = _launch_with_script(kind="source", server=server, base=base)
            try:
                delivered = _wait_for(lambda: len(resource.submitted_reports) > 0)
                self.assertTrue(delivered)
                recorded = _wait_for(lambda: resource.failure_evidence() is not None)
                self.assertTrue(recorded)
                # The delivered six-field report is preserved, not erased.
                self.assertEqual(resource.submitted_reports, [_source_report_payload()])
                evidence = resource.failure_evidence()
                self.assertEqual(evidence["failure_category"], "runtime")
                # The _failure_recorded guard means a second failure cannot overwrite.
                before_reason = resource.failure_reason
                resource._record_failure("runtime", "late-second-failure")
                self.assertEqual(resource.failure_evidence(), evidence)
                self.assertEqual(resource.failure_reason, before_reason)
                self.assertNotIn("late-second-failure", json.dumps(resource.failure_evidence()))
            finally:
                resource.destroy()
            server.join()

    def test_stop_joins_pump_and_watchdog_before_descriptor_teardown(self) -> None:
        elicitation = {
            "jsonrpc": "2.0",
            "id": 7004,
            "method": "mcpServer/elicitation/request",
            "params": {"serverName": "examiner_report", "mode": "form", "requestedSchema": {}},
        }
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            server = _ScriptedAppServer(kind="source", post_lines=(elicitation,))
            self.addCleanup(server.close)
            resource, _adapter = _launch_with_script(kind="source", server=server, base=base)
            report_socket = Path(str(resource.report_sink.socket_path))
            socket_root = _child_home(base)
            self.assertTrue(report_socket.exists())
            # Ensure the pump has actually started and is draining.
            self.assertIsNotNone(resource._stdout_pump)
            self.assertTrue(resource._stdout_pump.is_alive())  # type: ignore[union-attr]
            resource.stop()
            # stop() joined both lifecycle threads before descriptor teardown.
            self.assertFalse(resource._stdout_pump.is_alive())  # type: ignore[union-attr]
            self.assertFalse(resource._watchdog_thread.is_alive())  # type: ignore[union-attr]
            # report.sock removed by stop()'s report_sink teardown.
            self.assertFalse(report_socket.exists())
            server.join()
            self.assertFalse(server._thread.is_alive())
            # destroy() removes the private tree; no socket root left behind.
            resource.destroy()
            self.assertTrue(resource.destroyed)
            self.assertFalse(socket_root.exists())

    def test_startup_failure_leaves_no_pump_residue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            auth_home = base / "codex-home"
            auth_home.mkdir(mode=0o700)
            (auth_home / "auth.json").write_text("{}", encoding="utf-8")
            (auth_home / "auth.json").chmod(0o600)
            root = repository_root()
            server = _ScriptedAppServer(kind="source", thread_start_error=True)
            self.addCleanup(server.close)

            def process_factory(_command, **_kwargs):
                return server

            adapter = CodexRuntimeAdapter(
                repository_root=root,
                use_bwrap=False,
                process_factory=process_factory,
            )
            adapter._run_root = base
            spec = _build_spec("source", base)
            with unittest.mock.patch.dict(
                os.environ, {"CODEX_HOME": str(auth_home)}, clear=False
            ):
                resource = adapter.acceptance_child_factory(spec)
            # Startup failure is converted to a typed placeholder: no pump thread
            # was started, no live child handle is registered, and the failing
            # process/thread is fully torn down by the impl's destroy().
            self.assertTrue(resource.destroyed)
            self.assertEqual(resource.failure_category, "runtime")
            self.assertEqual(resource.failure_reason, "child-start-failed")
            self.assertIsNone(resource._stdout_pump)
            self.assertEqual(adapter._acceptance_children, {})
            server.join()
            self.assertFalse(server._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
