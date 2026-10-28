"""Fixed local Host worker boundary; no legacy imports in the v5 process."""

from __future__ import annotations

import json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

from .contracts import FrameworkError, safe_id

OPERATIONS = frozenset(
    {
        "inspect",
        "prepare_scope",
        "apply",
        "reconcile",
        "snapshot",
        "finalize",
        "read_config",
        "cleanup",
        "provider",
    }
)


class HostBridge:
    def __init__(self, run_root: Path):
        self.run_root = run_root.resolve()
        repository = Path(__file__).resolve().parents[4]
        self.command = [
            str(repository / "backend/.venv/bin/python"),
            str(repository / "modeling_team/v5/host/worker.py"),
            "--run-dir",
            str(self.run_root),
        ]
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "PYTHONPATH": os.pathsep.join(
                [
                    str(repository),
                    str(repository / "backend"),
                    str(repository / "modeling_team/v5/src"),
                ]
            ),
        }
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE"):
            if key in os.environ:
                self.env[key] = os.environ[key]

    @staticmethod
    def _decode(raw: str) -> dict:
        try:
            reply = json.loads(raw)
        except (ValueError, TypeError) as error:
            raise FrameworkError("host_response_unknown", layer="runtime/infrastructure") from error
        if not reply.get("ok"):
            error = reply.get("error", {})
            raise FrameworkError(
                error.get("code", "host_operation_failed"),
                layer=error.get("layer", "platform-contract"),
                host_detail=error.get("detail"),
            )
        return reply["result"]

    def call(self, operation: str, payload: dict | None = None) -> dict:
        if operation not in OPERATIONS - {"provider"}:
            raise FrameworkError("host_operation_not_allowed")
        try:
            completed = subprocess.run(
                [*self.command, operation],
                input=json.dumps(payload or {}),
                text=True,
                capture_output=True,
                env=self.env,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise FrameworkError(
                "host_response_unknown", layer="runtime/infrastructure", operation=operation
            ) from error
        return self._decode(completed.stdout)

    @contextmanager
    def provider(self, execution_id: str, role: str, tools: tuple[str, ...]):
        safe_id(execution_id)
        process = subprocess.Popen(
            [*self.command, "provider"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=self.env,
        )
        try:
            process.stdin.write(
                json.dumps({"execution_id": execution_id, "role": role, "tools": list(tools)})
                + "\n"
            )
            process.stdin.flush()
            result = self._decode(process.stdout.readline())
            yield result["base_url"]
        finally:
            if process.poll() is None:
                process.stdin.close()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=15)
            process.stdout.close()
