from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "input-pack" / "m4-api-spool.py"
SPEC = importlib.util.spec_from_file_location("m4_api_spool", HELPER_PATH)
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def _candidate(request_id: str = "create-project") -> dict[str, object]:
    return {
        "id": request_id,
        "method": "POST",
        "path": "/api/projects",
        "headers": {"content-type": "application/json"},
        "body": {"name": "candidate-owned"},
    }


def _dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    requests, responses, candidate = tmp_path / "requests", tmp_path / "responses", tmp_path / "candidate.json"
    requests.mkdir()
    responses.mkdir()
    return requests, responses, candidate


def test_round36_trailing_newline_candidate_is_canonicalized_published_and_printed(tmp_path: Path) -> None:
    requests, responses, candidate = _dirs(tmp_path)
    request = _candidate()
    candidate.write_bytes(helper.canonical_json(request) + b"\n")
    environment = {
        **os.environ,
        "M4_API_REQUEST_DIR": str(requests),
        "M4_API_RESPONSE_DIR": str(responses),
    }
    process = subprocess.Popen(
        [sys.executable, str(HELPER_PATH), "--candidate", str(candidate), "--timeout-seconds", "2"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    request_path = requests / "create-project.json"
    deadline = time.monotonic() + 2
    while not request_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert request_path.is_file()
    assert request_path.read_bytes() == helper.canonical_json(request)
    response = {"id": "create-project", "status": 201, "headers": {}, "body": {"id": "p1"}}
    (responses / "create-project.json").write_bytes(helper.canonical_json(response))
    stdout, stderr = process.communicate(timeout=2)
    assert process.returncode == 0, stderr.decode()
    assert stdout == helper.canonical_json(response) + b"\n"


@pytest.mark.parametrize(
    "candidate",
    [
        b"not-json",
        b'{"id":"x","id":"y","method":"GET","path":"/api/x","headers":{},"body":null}',
        helper.canonical_json({**_candidate(), "Authorization": "forbidden"}),
        helper.canonical_json({**_candidate(), "headers": {"Authorization": "forbidden"}}),
    ],
)
def test_candidate_rejects_malformed_duplicate_keys_or_authorization(candidate: bytes) -> None:
    with pytest.raises(helper.SpoolError):
        helper.parse_candidate(candidate)


@pytest.mark.parametrize("preexisting", ("request", "response"))
def test_helper_rejects_duplicate_request_or_response(tmp_path: Path, preexisting: str) -> None:
    requests, responses, candidate = _dirs(tmp_path)
    candidate.write_bytes(helper.canonical_json(_candidate()))
    target = (requests if preexisting == "request" else responses) / "create-project.json"
    target.write_bytes(b"{}")
    with pytest.raises(helper.SpoolError, match="already exists"):
        helper.run(candidate, requests, responses, 0.1)


def test_helper_rejects_response_with_different_id(tmp_path: Path) -> None:
    requests, responses, candidate = _dirs(tmp_path)
    candidate.write_bytes(helper.canonical_json(_candidate()))

    def reply() -> None:
        deadline = time.monotonic() + 2
        while not (requests / "create-project.json").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        (responses / "create-project.json").write_bytes(
            helper.canonical_json({"id": "different", "status": 200})
        )

    worker = threading.Thread(target=reply)
    worker.start()
    with pytest.raises(helper.SpoolError, match="response ID differs"):
        helper.run(candidate, requests, responses, 2)
    worker.join(timeout=2)
