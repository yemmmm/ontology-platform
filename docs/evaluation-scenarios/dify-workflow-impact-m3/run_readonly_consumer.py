#!/usr/bin/env python3
"""Launch a fresh, isolated, read-only M3 consumer Agent for one tester-supplied question."""

from __future__ import annotations

import re
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Final

import run_autonomous_modeling as producer


SCENARIO_ROOT: Final = Path(__file__).resolve().parent
INPUT_ROOT: Final = SCENARIO_ROOT / "consumer-input-pack"
GATEWAY_SCRIPT: Final = SCENARIO_ROOT / "readonly_consumer_gateway.py"
RUN_TAG_RE: Final = producer.RUN_TAG_RE
CONSUMER_MOUNT_ROOT: Final = "/opt"
CONSUMER_PROMPT_PATH: Final = f"{CONSUMER_MOUNT_ROOT}/consumer-prompt.md"
CONSUMER_CONTRACT_PATH: Final = f"{CONSUMER_MOUNT_ROOT}/consumer-read-query-contract.md"
CONSUMER_REQUEST_PATH: Final = f"{CONSUMER_MOUNT_ROOT}/consumer-request.json"
CONSUMER_RPC_CLIENT_PATH: Final = f"{CONSUMER_MOUNT_ROOT}/m3_readonly_rpc.py"
CONSUMER_RESULT_RE: Final = re.compile(r"(?m)^CONSUMER_RESULT (CONSUMER_READY|BLOCKED|INCONCLUSIVE)$")


class ConsumerInputError(ValueError):
    """The independent consumer received an unsafe or ambiguous input pack."""


def consumer_agent_result(transcript: Path) -> str | None:
    """Read an exact terminal marker only from completed Codex agent-message events."""
    values: list[str] = []
    try:
        lines = transcript.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(event, dict):
            return None
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if not isinstance(text, str):
            return None
        values.extend(CONSUMER_RESULT_RE.findall(text))
    return values[0] if len(set(values)) == 1 and values else None


def validate_request(path: Path) -> dict[str, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConsumerInputError("consumer request is not UTF-8 JSON") from error
    if not isinstance(value, dict) or set(value) != {"project_id", "ontology_id", "business_question"}:
        raise ConsumerInputError("consumer request keys must be project_id, ontology_id and business_question")
    if any(not isinstance(value[key], str) or not value[key].strip() for key in value):
        raise ConsumerInputError("consumer request values must be non-empty strings")
    for key in ("project_id", "ontology_id"):
        try:
            uuid.UUID(value[key])
        except ValueError as error:
            raise ConsumerInputError(f"consumer {key} must be a UUID") from error
    if len(value["business_question"]) > 20_000:
        raise ConsumerInputError("consumer question exceeds the input limit")
    return {key: value[key].strip() for key in value}


def stage_inputs(request_path: Path, staging: Path) -> dict[str, object]:
    request = validate_request(request_path)
    staging.mkdir(mode=0o700, parents=True, exist_ok=False)
    sources = {
        "consumer-prompt.md": INPUT_ROOT / "consumer-prompt.md",
        "consumer-read-query-contract.md": INPUT_ROOT / "consumer-read-query-contract.md",
        "m3_readonly_rpc.py": INPUT_ROOT / "m3_readonly_rpc.py",
    }
    for name, source in sources.items():
        if not source.is_file():
            raise ConsumerInputError(f"missing consumer input: {name}")
        shutil.copyfile(source, staging / name)
        os.chmod(staging / name, 0o444)
    (staging / "consumer-request.json").write_bytes(producer.canonical_json(request))
    os.chmod(staging / "consumer-request.json", 0o444)
    actual = {path.name for path in staging.iterdir() if path.is_file()}
    if actual != set(sources) | {"consumer-request.json"}:
        raise ConsumerInputError("consumer staging set differs from its allowlist")
    return {
        "request": request,
        "staged_files": sorted(actual),
        "source_hashes": {name: producer.sha256(source) for name, source in sources.items()},
        "request_sha256": producer.sha256(staging / "consumer-request.json"),
    }


def consumer_isolation_probe(command: list[str]) -> dict[str, object]:
    probe = command[: command.index("--")] + [
        "--",
        "/bin/sh",
        "-c",
        "test ! -e /home/yangxiang/projects/ontology-platform && "
        "test ! -e /home/yangxiang/.codex && "
        f"test -f {CONSUMER_PROMPT_PATH} && "
        f"test -f {CONSUMER_CONTRACT_PATH} && "
        f"test -f {CONSUMER_REQUEST_PATH} && "
        f"test -f {CONSUMER_RPC_CLIENT_PATH} && "
        f"test ! -e {CONSUMER_MOUNT_ROOT}/modeling-agent-prompt.md && "
        "test -w /mnt/rpc/requests && test ! -w /mnt/rpc/responses",
    ]
    result = subprocess.run(probe, check=False, capture_output=True, text=True, timeout=30)
    return {"exit_code": result.returncode, "passed": result.returncode == 0, "stderr": result.stderr.strip()}


def _gateway_entries(run_dir: Path) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    gateway_audit = run_dir / "gateway.jsonl"
    if not gateway_audit.is_file():
        return None, {
            "passed": False,
            "errors": ["consumer made zero RPC calls"],
            "forwarded_count": 0,
            "gateway_audit_present": False,
        }
    try:
        entries = [json.loads(line) for line in gateway_audit.read_text(encoding="utf-8").splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        return None, {"passed": False, "errors": [f"invalid consumer gateway audit: {type(error).__name__}"]}
    if not all(isinstance(entry, dict) for entry in entries):
        return None, {"passed": False, "errors": ["invalid consumer gateway audit: non-object entry"]}
    return entries, None


def consumer_receipt_audit(run_dir: Path, run_tag: str) -> dict[str, object]:
    entries, early_result = _gateway_entries(run_dir)
    if early_result is not None:
        return early_result
    assert entries is not None
    if not any(entry.get("policy") == "forwarded" for entry in entries):
        return {
            "passed": False,
            "errors": ["consumer made zero allowed RPC calls"],
            "forwarded_count": 0,
            "gateway_audit_present": True,
        }
    return producer.receipt_audit(run_dir, run_tag)


def consumer_operation_audit(run_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    entries, early_result = _gateway_entries(run_dir)
    if early_result is not None:
        return early_result
    assert entries is not None
    forwarded_count = 0
    for entry in entries:
        if entry.get("policy") != "forwarded":
            continue
        forwarded_count += 1
        if entry.get("method") == "POST" and entry.get("path") != "/api/semantic/sparql:query":
            errors.append("consumer forwarded a non-query POST")
        if entry.get("method") not in {"GET", "POST"}:
            errors.append("consumer forwarded a non-read method")
    if forwarded_count == 0:
        errors.append("consumer made zero allowed RPC calls")
    return {"passed": not errors, "errors": errors, "forwarded_count": forwarded_count, "gateway_audit_present": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-tag", default=f"m3-consumer-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if not RUN_TAG_RE.fullmatch(args.run_tag):
        raise SystemExit("run tag must contain lowercase letters, digits and hyphens only")
    run_dir = SCENARIO_ROOT / "runtime" / "consumer-runs" / args.run_tag
    if run_dir.exists() or not producer.CODEX_BINARY.exists() or not producer.HOST_CODEX_AUTH.exists():
        raise SystemExit("run target exists or Codex authentication is unavailable")
    run_dir.mkdir(mode=0o700, parents=True)
    staging, workspace = run_dir / "staging", run_dir / "work"
    workspace.mkdir(mode=0o700)
    requests, response_target = workspace / "rpc" / "requests", workspace / "rpc" / "responses"
    requests.mkdir(mode=0o700, parents=True)
    response_target.mkdir(mode=0o700)
    responses, archive = run_dir / "gateway-responses", run_dir / "gateway-request-archive"
    responses.mkdir(mode=0o700)
    archive.mkdir(mode=0o700)
    transcript, audit_path = run_dir / "agent-transcript.jsonl", run_dir / "audit.json"
    codex_home, gateway, api_key = run_dir / "temporary-codex-home", None, ""
    audit: dict[str, Any] = {"run_tag": args.run_tag, "status": "INCONCLUSIVE", "started_at": producer.utc_now()}
    try:
        audit["staging"] = stage_inputs(args.request, staging)
        request = audit["staging"]["request"]
        audit["fresh_codex_home_before"] = producer.create_codex_home(codex_home)
        api_key = producer.load_api_key()
        command = producer.bwrap_command(
            staging=staging,
            workspace=workspace,
            codex_home=codex_home,
            responses=responses,
            run_tag=args.run_tag,
        )
        audit["mount_command"] = [
            "<inherited-proxy>" if value in {os.environ.get("HTTP_PROXY"), os.environ.get("HTTPS_PROXY")} else value
            for value in command
        ]
        gateway = subprocess.Popen(
            [
                sys.executable,
                str(GATEWAY_SCRIPT),
                "--requests",
                str(requests),
                "--responses",
                str(responses),
                "--archive",
                str(archive),
                "--audit",
                str(run_dir / "gateway.jsonl"),
                "--project-id",
                request["project_id"],
                "--ontology-id",
                request["ontology_id"],
            ],
            env={"PATH": os.environ["PATH"], "M3_API_KEY": api_key},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.1)
        if gateway.poll() is not None:
            raise ConsumerInputError("read-only consumer gateway stopped during startup")
        audit["isolation_probe"] = consumer_isolation_probe(command)
        if not audit["isolation_probe"]["passed"]:
            raise ConsumerInputError("consumer bubblewrap isolation probe failed")
        if args.prepare_only:
            audit["status"] = "PREPARED"
            return 0
        with (staging / "consumer-prompt.md").open("rb") as prompt, transcript.open("wb") as output, (run_dir / "codex-stderr.log").open("wb") as errors:
            agent = subprocess.Popen(command, stdin=prompt, stdout=output, stderr=errors)
            time.sleep(0.5)
            audit["process_argv_audit"] = producer.argv_secret_audit(agent.pid, api_key)
            audit["codex_exit_code"] = agent.wait(timeout=args.timeout_seconds)
        audit["agent_declared_result"] = consumer_agent_result(transcript)
        audit["receipt_audit"] = consumer_receipt_audit(run_dir, args.run_tag)
        audit["operation_audit"] = consumer_operation_audit(run_dir)
        audit["artifact_audit"] = producer.scan_run_artifacts(run_dir, api_key)
        if (
            audit["codex_exit_code"] == 0
            and audit["agent_declared_result"] in {"CONSUMER_READY", "BLOCKED"}
            and audit["process_argv_audit"]["passed"]
            and audit["receipt_audit"]["passed"]
            and audit["operation_audit"]["passed"]
            and audit["artifact_audit"]["passed"]
        ):
            audit["status"] = audit["agent_declared_result"]
    except (ConsumerInputError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        audit["error"] = type(error).__name__
        audit["error_detail"] = str(error).replace(api_key, "<redacted>")
    finally:
        if gateway is not None:
            gateway.terminate()
            gateway.wait(timeout=10)
        shutil.rmtree(codex_home, ignore_errors=True)
        audit["temporary_codex_home_deleted"] = not codex_home.exists()
        audit["finished_at"] = producer.utc_now()
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"run_tag": args.run_tag, "status": audit["status"], "audit": str(audit_path)}))
    return 0 if audit["status"] in {"CONSUMER_READY", "BLOCKED", "PREPARED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
