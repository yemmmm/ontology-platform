from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from m7_contract import canonical_json  # noqa: E402
import m7_l0  # noqa: E402


def test_prepare_l0_uses_the_exact_clean_shell_command_and_creates_only_l0_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = SCENARIO_ROOT / "attempts.jsonl"
    before = attempts.read_bytes()
    real_run = m7_l0.subprocess.run
    calls: list[tuple[object, object]] = []

    def tracked(*args: object, **kwargs: object) -> object:
        calls.append((args[0], kwargs.get("env")))
        return real_run(*args, **kwargs)

    monkeypatch.setattr(m7_l0.subprocess, "run", tracked)
    result = m7_l0.prepare_l0("m7-l0-run-1", tmp_path)
    visible = Path(result["agent_visible_dir"])
    assert len(calls) == 2
    assert all(command == ["./seal_semantic_package.py", "--runtime-check", "--agent-visible", "."] for command, _env in calls)
    assert all(env == m7_l0.CLEAN_ENV for _command, env in calls)
    assert m7_l0.verify_l0(Path(result["run_dir"]))["contract_version"] == "m7-l0-runtime-v1"
    assert {path.name for path in visible.iterdir()} == m7_l0.EXPECTED_MEMBERS
    assert not (visible / "semantic-package.json").exists()
    assert attempts.read_bytes() == before
    text = (SCENARIO_ROOT / "m7_l0.py").read_text(encoding="utf-8").lower()
    assert "import urllib" not in text and "import requests" not in text


def test_l0_missing_python3_fails_before_formal_staging_or_ledger_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = SCENARIO_ROOT / "attempts.jsonl"
    before = attempts.read_bytes()
    monkeypatch.setattr(m7_l0, "CLEAN_ENV", {"PATH": "/missing", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})
    with pytest.raises(m7_l0.L0Error, match="clean-shell helper command failed"):
        m7_l0.prepare_l0("m7-l0-run-1", tmp_path)
    assert not (tmp_path / "l0" / "m7-l0-run-1").exists()
    assert attempts.read_bytes() == before


@pytest.mark.parametrize("target", ["receipt", "run-manifest", "l0-contract", "extra-file", "wrong-interpreter", "helper-mode"])
def test_verify_l0_rejects_tampered_receipt_or_staging_inputs(tmp_path: Path, target: str) -> None:
    result = m7_l0.prepare_l0(f"m7-l0-{target}", tmp_path)
    visible = Path(result["agent_visible_dir"])
    if target == "receipt":
        receipt = json.loads((visible / "l0-runtime-receipt.json").read_text())
        receipt["nonce"] = "tampered"
        (visible / "l0-runtime-receipt.json").write_bytes(canonical_json(receipt))
    elif target == "run-manifest":
        manifest = json.loads((visible / "run-manifest.json").read_text())
        manifest["nonce"] = "tampered"
        (visible / "run-manifest.json").write_bytes(canonical_json(manifest))
    elif target == "l0-contract":
        contract = json.loads((visible / "l0-contract.json").read_text())
        contract["nonce"] = "tampered"
        (visible / "l0-contract.json").write_bytes(canonical_json(contract))
    elif target == "extra-file":
        (visible / "unexpected.txt").write_text("no", encoding="utf-8")
    elif target == "wrong-interpreter":
        receipt = json.loads((visible / "l0-runtime-receipt.json").read_text())
        receipt["interpreter"] = "/usr/bin/python-not-allowed"
        unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        receipt["receipt_sha256"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()
        (visible / "l0-runtime-receipt.json").write_bytes(canonical_json(receipt))
    else:
        (visible / "seal_semantic_package.py").chmod(0o644)
    with pytest.raises(m7_l0.L0Error):
        m7_l0.verify_l0(Path(result["run_dir"]))
