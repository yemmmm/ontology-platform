"""Local-only L0 runtime preparer and verifier for the M7 visible sealing helper."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from m7_contract import SCENARIO_ROOT, canonical_json, sha256, verify_manifest


L0_VERSION = "m7-l0-runtime-v1"
L0_SOURCE = SCENARIO_ROOT / "l0-source"
HELPER_SOURCE = SCENARIO_ROOT / "agent-input" / "seal_semantic_package.py"
L0_COMMAND = "./seal_semantic_package.py --runtime-check --agent-visible ."
L0_NONCE = "m7-l0-runtime-nonce-v1"
EXPECTED_MEMBERS = {
    "l0-contract.json",
    "run-manifest.json",
    "seal_semantic_package.py",
    "staged-manifest.json",
    "l0-runtime-receipt.json",
}
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")
CLEAN_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


class L0Error(RuntimeError):
    """A local L0 runtime invariant failed before any modeling attempt can start."""


def prepare_l0(run_id: str, runtime_root: Path) -> dict[str, str]:
    """Preflight then stage a local-only L0 run; no HTTP, ledger or platform resource is involved."""
    if not RUN_ID.fullmatch(run_id):
        raise L0Error("unsafe L0 run_id")
    _verify_l0_source()
    run_dir = runtime_root / "l0" / run_id
    if run_dir.exists():
        raise L0Error("L0 run directory already exists")
    with tempfile.TemporaryDirectory(prefix="m7-l0-preflight-") as temporary:
        preflight = Path(temporary) / "agent-visible"
        _create_staging(preflight, run_id)
        _run_runtime_check(preflight)
        verify_l0(preflight.parent)
    try:
        _create_staging(run_dir / "agent-visible", run_id)
        _run_runtime_check(run_dir / "agent-visible")
        verify_l0(run_dir)
    except Exception:
        if run_dir.exists():
            shutil.rmtree(run_dir)
        raise
    return {
        "run_dir": str(run_dir),
        "agent_visible_dir": str(run_dir / "agent-visible"),
        "receipt_path": str(run_dir / "agent-visible" / "l0-runtime-receipt.json"),
    }


def verify_l0(run_dir: Path) -> dict[str, Any]:
    """Verify one L0 run contains only immutable input plus its canonical local receipt."""
    visible = run_dir / "agent-visible"
    if not visible.is_dir() or visible.is_symlink():
        raise L0Error("L0 Agent-visible directory is missing or unsafe")
    members = {path.name for path in visible.iterdir()}
    if members != EXPECTED_MEMBERS:
        raise L0Error("L0 staging membership drift")
    for name in members:
        path = visible / name
        if not path.is_file() or path.is_symlink() or visible.resolve() not in path.resolve().parents:
            raise L0Error("L0 staging contains an unsafe path")
    contract = _read_canonical_object(visible / "l0-contract.json")
    manifest = _read_canonical_object(visible / "run-manifest.json")
    staged = _read_canonical_object(visible / "staged-manifest.json")
    receipt = _read_canonical_object(visible / "l0-runtime-receipt.json")
    _verify_l0_contract(contract)
    _verify_run_manifest(manifest, contract, visible)
    _verify_staged_manifest(staged, manifest, visible)
    _verify_helper(visible / "seal_semantic_package.py", manifest, contract)
    _verify_receipt(receipt, manifest, contract, visible)
    return receipt


def _verify_l0_source() -> None:
    verify_manifest(L0_SOURCE)
    _verify_l0_contract(_read_object(L0_SOURCE / "l0-contract.json"))
    _verify_helper_source()


def _verify_l0_contract(contract: dict[str, Any]) -> None:
    expected = {
        "contract_version": L0_VERSION,
        "command": L0_COMMAND,
        "nonce": L0_NONCE,
        "required_interpreter": "/usr/bin/python3",
    }
    if contract != expected:
        raise L0Error("L0 contract drift")


def _verify_helper_source() -> None:
    if not HELPER_SOURCE.is_file() or not HELPER_SOURCE.stat().st_mode & 0o111:
        raise L0Error("L0 helper is not executable")
    if HELPER_SOURCE.read_text(encoding="utf-8").splitlines()[0] != "#!/usr/bin/env python3":
        raise L0Error("L0 helper has an invalid Python3 shebang")


def _create_staging(visible: Path, run_id: str) -> None:
    visible.mkdir(parents=True)
    _verify_helper_source()
    _write_canonical(visible / "l0-contract.json", _read_object(L0_SOURCE / "l0-contract.json"))
    shutil.copy2(HELPER_SOURCE, visible / "seal_semantic_package.py")
    (visible / "seal_semantic_package.py").chmod(0o755)
    contract_hash, helper_hash = sha256(visible / "l0-contract.json"), sha256(visible / "seal_semantic_package.py")
    staged = {
        "manifest_version": 1,
        "files": [
            {"path": "l0-contract.json", "sha256": contract_hash},
            {"path": "seal_semantic_package.py", "sha256": helper_hash},
        ],
    }
    _write_canonical(visible / "staged-manifest.json", staged)
    manifest = {
        "contract_version": L0_VERSION,
        "run_id": run_id,
        "nonce": L0_NONCE,
        "command": L0_COMMAND,
        "l0_contract_sha256": contract_hash,
        "helper_sha256": helper_hash,
        "staged_manifest_sha256": hashlib.sha256(canonical_json(staged)).hexdigest(),
    }
    _write_canonical(visible / "run-manifest.json", manifest)


def _run_runtime_check(visible: Path) -> None:
    result = subprocess.run(
        ["./seal_semantic_package.py", "--runtime-check", "--agent-visible", "."],
        cwd=visible,
        env=CLEAN_ENV,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\n", " ")[:300]
        raise L0Error(f"L0 clean-shell helper command failed: {detail or result.returncode}")


def _verify_run_manifest(manifest: dict[str, Any], contract: dict[str, Any], visible: Path) -> None:
    expected_keys = {
        "contract_version",
        "run_id",
        "nonce",
        "command",
        "l0_contract_sha256",
        "helper_sha256",
        "staged_manifest_sha256",
    }
    if set(manifest) != expected_keys or manifest.get("contract_version") != L0_VERSION:
        raise L0Error("L0 run manifest fields drift")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id) or manifest.get("nonce") != contract["nonce"]:
        raise L0Error("L0 run manifest nonce or run_id drift")
    if manifest.get("command") != contract["command"]:
        raise L0Error("L0 run command drift")
    if manifest.get("l0_contract_sha256") != sha256(visible / "l0-contract.json"):
        raise L0Error("L0 contract hash drift")
    if manifest.get("helper_sha256") != sha256(visible / "seal_semantic_package.py"):
        raise L0Error("L0 helper hash drift")


def _verify_staged_manifest(staged: dict[str, Any], manifest: dict[str, Any], visible: Path) -> None:
    expected = {
        "manifest_version": 1,
        "files": [
            {"path": "l0-contract.json", "sha256": sha256(visible / "l0-contract.json")},
            {"path": "seal_semantic_package.py", "sha256": sha256(visible / "seal_semantic_package.py")},
        ],
    }
    if staged != expected or manifest.get("staged_manifest_sha256") != hashlib.sha256(canonical_json(staged)).hexdigest():
        raise L0Error("L0 immutable staging manifest drift")


def _verify_helper(helper: Path, manifest: dict[str, Any], contract: dict[str, Any]) -> None:
    if not helper.stat().st_mode & 0o111:
        raise L0Error("L0 helper is not executable")
    if helper.read_text(encoding="utf-8").splitlines()[0] != "#!/usr/bin/env python3":
        raise L0Error("L0 helper has an invalid Python3 shebang")
    if manifest["helper_sha256"] != sha256(helper) or contract["required_interpreter"] != "/usr/bin/python3":
        raise L0Error("L0 helper identity or interpreter drift")


def _verify_receipt(receipt: dict[str, Any], manifest: dict[str, Any], contract: dict[str, Any], visible: Path) -> None:
    expected_keys = {
        "receipt_version",
        "contract_version",
        "run_id",
        "nonce",
        "command",
        "run_manifest_sha256",
        "helper_sha256",
        "interpreter",
        "python_version",
        "receipt_sha256",
    }
    if set(receipt) != expected_keys or receipt.get("receipt_version") != 1 or receipt.get("contract_version") != L0_VERSION:
        raise L0Error("L0 receipt fields drift")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt["receipt_sha256"] != hashlib.sha256(canonical_json(unsigned)).hexdigest():
        raise L0Error("L0 receipt canonical hash drift")
    if receipt.get("run_id") != manifest["run_id"] or receipt.get("nonce") != manifest["nonce"]:
        raise L0Error("L0 receipt nonce or run_id drift")
    if receipt.get("command") != L0_COMMAND or receipt.get("helper_sha256") != manifest["helper_sha256"]:
        raise L0Error("L0 receipt command or helper identity drift")
    if receipt.get("run_manifest_sha256") != hashlib.sha256(canonical_json(manifest)).hexdigest():
        raise L0Error("L0 receipt run manifest hash drift")
    if receipt.get("interpreter") != contract["required_interpreter"] or not isinstance(receipt.get("python_version"), str) or not receipt["python_version"].startswith("3."):
        raise L0Error("L0 receipt interpreter or Python version drift")
    if (visible / "semantic-package.json").exists():
        raise L0Error("L0 staging must not contain a semantic package")


def _read_canonical_object(path: Path) -> dict[str, Any]:
    value = _read_object(path)
    if path.read_bytes() != canonical_json(value):
        raise L0Error(f"L0 file is not canonical JSON: {path.name}")
    return value


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise L0Error(f"L0 file is missing or invalid: {path.name}") from exc
    if not isinstance(value, dict):
        raise L0Error(f"L0 file is not an object: {path.name}")
    return value


def _write_canonical(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(canonical_json(value))
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or verify the local-only M7 L0 runtime slice.")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--runtime-root", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "prepare":
        result: dict[str, Any] = prepare_l0(args.run_id, args.runtime_root)
    else:
        result = verify_l0(args.run_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
