from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "m4_batch_exchange", ROOT / "input-pack" / "m4-batch-exchange.py"
)
assert SPEC is not None and SPEC.loader is not None
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


def _write_runtime(root: Path) -> tuple[Path, Path, Path]:
    runtime_path = root / "runtime-record.json"
    request_dir = root / "requests"
    response_dir = root / "responses"
    request_dir.mkdir()
    response_dir.mkdir()
    context_id = "initial-context"
    runtime_path.write_text(
        json.dumps(
            {
                "batch_exchange": {},
                "lease": {"token": "lease-1"},
                "receipts": {"modeling_context": {"request_id": context_id}},
                "resource_ids": {"build_session_id": "session-1", "ontology_id": "ontology-1"},
                "run_tag": "m5-p1-full-host-tag-20260729-a",
                "terminal_status": "INCONCLUSIVE",
            }
        ),
        encoding="utf-8",
    )
    (response_dir / f"{context_id}.json").write_text(
        json.dumps(
            {
                "body": {"workspace": {"workspace_version": "version-1"}},
                "id": context_id,
                "status": 200,
            }
        ),
        encoding="utf-8",
    )
    return runtime_path, request_dir, response_dir


def _candidate(path: Path, batch_id: str, item_id: str) -> Path:
    path.write_text(
        json.dumps(
            {
                "client_batch_id": batch_id,
                "items": [
                    {
                        "client_item_id": item_id,
                        "command_kind": "create_entity",
                        "depends_on": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_closed_batch_exchange_replay_freezes_only_projection_and_preserves_m4_timeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    scripted = iter(
        [
            {"attempt_status": "validated", "mode": "dry_run", "workspace": {"before_version": "version-1", "expected_version": "version-1"}},
            {"attempt_status": "applied", "mode": "apply_atomic", "workspace": {"before_version": "version-1", "after_version": "version-2"}},
            {"attempt_status": "validation_failed", "mode": "dry_run", "workspace": {"before_version": "version-2", "expected_version": "version-2"}},
            {"attempt_status": "validated", "mode": "dry_run", "workspace": {"before_version": "version-2", "expected_version": "version-2"}},
            {"attempt_status": "applied", "mode": "apply_atomic", "workspace": {"before_version": "version-2", "after_version": "version-3"}},
        ]
    )
    published: list[dict[str, object]] = []

    def publish(request: dict[str, object]) -> dict[str, object]:
        published.append(request)
        return {"body": next(scripted), "id": request["id"], "status": 200}

    monkeypatch.setattr(exchange, "_publish", publish)
    principal = _candidate(tmp_path / "principal.json", "principal", "schema-item")
    invalid = _candidate(tmp_path / "invalid.json", "invalid", "invalid-item")
    valid = _candidate(tmp_path / "valid.json", "valid", "valid-item")

    assert exchange.seed() == {"workspace_version": "version-1"}
    exchange.dry_run(principal, "validated")
    exchange.apply(principal)
    exchange.dry_run(invalid, "validation_failed")
    exchange.dry_run(valid, "validated")
    exchange.apply(valid)

    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    state = runtime["batch_exchange"]
    assert runtime["run_tag"] == "m5-p1-full-host-tag-20260729-a"
    assert runtime["terminal_status"] == "INCONCLUSIVE"
    assert state["workspace_version"] == "version-3"
    assert state["frozen"]["projection"] == json.loads(valid.read_text(encoding="utf-8"))
    assert state["frozen"]["sha256"] == hashlib.sha256(
        batch.canonical_json(state["frozen"]["projection"])
    ).hexdigest()
    assert [request["path"] for request in published] == [
        "/api/build-sessions/session-1/modeling-batches"
    ] * 5
    assert all("modeling-context" not in str(request["path"]) for request in published)

    principal_dry = published[0]["body"]
    principal_apply = published[1]["body"]
    assert isinstance(principal_dry, dict) and isinstance(principal_apply, dict)
    frozen_keys = {"client_batch_id", "items", "ontology_id"}
    assert {key: principal_dry[key] for key in frozen_keys} == {
        key: principal_apply[key] for key in frozen_keys
    }
    assert principal_dry["mode"] == "dry_run"
    assert principal_apply["mode"] == "apply_atomic"
    assert principal_dry["idempotency_key"] != principal_apply["idempotency_key"]
    assert "lease_token" not in principal_dry and principal_apply["lease_token"] == "lease-1"


def test_changed_or_unfrozen_apply_fails_closed_without_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    monkeypatch.setattr(
        exchange,
        "_publish",
        lambda request: {
            "body": {
                "attempt_status": "validated",
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
            "id": request["id"],
            "status": 200,
        },
    )
    original = _candidate(tmp_path / "original.json", "batch-1", "item-1")
    changed = _candidate(tmp_path / "changed.json", "batch-1", "item-2")
    exchange.seed()
    exchange.dry_run(original, "validated")
    with pytest.raises(batch.BatchExchangeError, match="does not match"):
        exchange.apply(changed)
    assert not list(request_dir.iterdir())
    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"


@pytest.mark.parametrize(
    ("response_body", "expected_branch", "frozen"),
    [
        (
            {
                "attempt_status": "validated",
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
            "validated",
            True,
        ),
        (
            {
                "attempt_status": "validation_failed",
                "findings": [
                    {"blocking": False, "code": "advisory"},
                    {
                        "blocking": True,
                        "client_item_ids": ["entity-1"],
                        "code": "shacl_violation",
                        "finding_fingerprint": "fingerprint-1",
                    },
                ],
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
            "shacl_correction_required",
            False,
        ),
    ],
)
def test_first_valid_instance_expected_mode_returns_branch_and_freezes_only_validated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response_body: dict[str, object],
    expected_branch: str,
    frozen: bool,
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    monkeypatch.setattr(
        exchange,
        "_publish",
        lambda request: {"body": response_body, "id": request["id"], "status": 200},
    )
    candidate = _candidate(tmp_path / "candidate.json", "valid", "entity-1")

    exchange.seed()
    result = exchange.dry_run(candidate, batch.FIRST_VALID_INSTANCE_EXPECTED)

    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert result["branch"] == expected_branch
    assert ("frozen" in runtime["batch_exchange"]) is frozen
    assert runtime["terminal_status"] == "INCONCLUSIVE"


@pytest.mark.parametrize(
    "response_body",
    [
        {
            "attempt_status": "validation_failed",
            "findings": [
                {
                    "blocking": True,
                    "client_item_ids": ["entity-1"],
                    "code": "shacl_violation",
                }
            ],
            "mode": "dry_run",
            "workspace": {"before_version": "version-1", "expected_version": "version-1"},
        },
        {
            "attempt_status": "validation_failed",
            "findings": [
                {
                    "blocking": True,
                    "code": "shacl_violation",
                    "finding_fingerprint": "fingerprint-1",
                }
            ],
            "mode": "dry_run",
            "workspace": {"before_version": "version-1", "expected_version": "version-1"},
        },
        {
            "attempt_status": "validation_failed",
            "findings": [
                {
                    "blocking": True,
                    "client_item_ids": ["entity-1"],
                    "code": "invalid_command_payload",
                    "finding_fingerprint": "fingerprint-1",
                }
            ],
            "mode": "dry_run",
            "workspace": {"before_version": "version-1", "expected_version": "version-1"},
        },
        {
            "attempt_status": "failed",
            "mode": "dry_run",
            "workspace": {"before_version": "version-1", "expected_version": "version-1"},
        },
    ],
)
def test_first_valid_instance_expected_mode_locks_invalid_correction_responses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    response_body: dict[str, object],
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    monkeypatch.setattr(
        exchange,
        "_publish",
        lambda request: {"body": response_body, "id": request["id"], "status": 200},
    )
    exchange.seed()

    with pytest.raises(batch.BatchExchangeError, match="differs"):
        exchange.dry_run(
            _candidate(tmp_path / "candidate.json", "valid", "entity-1"),
            batch.FIRST_VALID_INSTANCE_EXPECTED,
        )

    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert runtime["terminal_status"] == "BLOCKED"
    assert "frozen" not in runtime["batch_exchange"]


def test_first_valid_instance_expected_mode_locks_non_2xx_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    monkeypatch.setattr(
        exchange,
        "_publish",
        lambda request: {"body": {"detail": "failure"}, "id": request["id"], "status": 409},
    )
    exchange.seed()

    with pytest.raises(batch.BatchExchangeError, match="unexpected HTTP"):
        exchange.dry_run(
            _candidate(tmp_path / "candidate.json", "valid", "entity-1"),
            batch.FIRST_VALID_INSTANCE_EXPECTED,
        )

    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"


def test_validated_freeze_requires_exact_apply_before_another_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    published: list[dict[str, object]] = []

    def publish(request: dict[str, object]) -> dict[str, object]:
        published.append(request)
        return {
            "body": {
                "attempt_status": "validated",
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
            "id": request["id"],
            "status": 200,
        }

    monkeypatch.setattr(exchange, "_publish", publish)
    exchange.seed()
    exchange.dry_run(_candidate(tmp_path / "first.json", "first", "item-1"), "validated")

    with pytest.raises(batch.BatchExchangeError, match="freeze requires apply"):
        exchange.dry_run(
            _candidate(tmp_path / "extra.json", "extra", "item-2"), "validation_failed"
        )

    assert len(published) == 1
    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"


def test_shacl_correction_branch_admits_one_validated_correction_then_requires_apply(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    responses = iter(
        [
            {
                "attempt_status": "validation_failed",
                "findings": [
                    {
                        "blocking": True,
                        "client_item_ids": ["item-1"],
                        "code": "shacl_violation",
                        "finding_fingerprint": "fingerprint-1",
                    }
                ],
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
            {
                "attempt_status": "validated",
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
        ]
    )
    published: list[dict[str, object]] = []

    def publish(request: dict[str, object]) -> dict[str, object]:
        published.append(request)
        return {"body": next(responses), "id": request["id"], "status": 200}

    monkeypatch.setattr(exchange, "_publish", publish)
    original = _candidate(tmp_path / "original.json", "original", "item-1")
    correction = _candidate(tmp_path / "correction.json", "correction", "item-1")
    exchange.seed()

    result = exchange.dry_run(original, batch.FIRST_VALID_INSTANCE_EXPECTED)
    assert result["branch"] == "shacl_correction_required"
    exchange.dry_run(correction, "validated")

    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert runtime["batch_exchange"]["frozen"]["projection"] == json.loads(
        correction.read_text(encoding="utf-8")
    )
    assert "correction_pending" not in runtime["batch_exchange"]
    with pytest.raises(batch.BatchExchangeError, match="freeze requires apply"):
        exchange.dry_run(_candidate(tmp_path / "extra.json", "extra", "item-2"), "validated")
    assert len(published) == 2
    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"


def test_shacl_correction_branch_rejects_non_validated_next_dry_run_without_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    published: list[dict[str, object]] = []

    def publish(request: dict[str, object]) -> dict[str, object]:
        published.append(request)
        return {
            "body": {
                "attempt_status": "validation_failed",
                "findings": [
                    {
                        "blocking": True,
                        "client_item_ids": ["item-1"],
                        "code": "shacl_violation",
                        "finding_fingerprint": "fingerprint-1",
                    }
                ],
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
            "id": request["id"],
            "status": 200,
        }

    monkeypatch.setattr(exchange, "_publish", publish)
    exchange.seed()
    exchange.dry_run(
        _candidate(tmp_path / "original.json", "original", "item-1"),
        batch.FIRST_VALID_INSTANCE_EXPECTED,
    )

    with pytest.raises(batch.BatchExchangeError, match="must expect validated"):
        exchange.dry_run(
            _candidate(tmp_path / "correction.json", "correction", "item-1"), "validation_failed"
        )

    assert len(published) == 1
    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"


def test_shacl_correction_branch_locks_when_its_one_validated_dry_run_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    responses = iter(
        [
            {
                "attempt_status": "validation_failed",
                "findings": [
                    {
                        "blocking": True,
                        "client_item_ids": ["item-1"],
                        "code": "shacl_violation",
                        "finding_fingerprint": "fingerprint-1",
                    }
                ],
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
            {
                "attempt_status": "validation_failed",
                "findings": [
                    {
                        "blocking": True,
                        "client_item_ids": ["item-1"],
                        "code": "shacl_violation",
                        "finding_fingerprint": "fingerprint-2",
                    }
                ],
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
        ]
    )
    published: list[dict[str, object]] = []

    def publish(request: dict[str, object]) -> dict[str, object]:
        published.append(request)
        return {"body": next(responses), "id": request["id"], "status": 200}

    monkeypatch.setattr(exchange, "_publish", publish)
    exchange.seed()
    exchange.dry_run(
        _candidate(tmp_path / "original.json", "original", "item-1"),
        batch.FIRST_VALID_INSTANCE_EXPECTED,
    )
    with pytest.raises(batch.BatchExchangeError, match="differs"):
        exchange.dry_run(
            _candidate(tmp_path / "correction.json", "correction", "item-1"), "validated"
        )
    with pytest.raises(batch.BatchExchangeError, match="blocked"):
        exchange.dry_run(_candidate(tmp_path / "extra.json", "extra", "item-2"), "validated")

    assert len(published) == 2
    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"


def test_persisted_blocked_state_rejects_later_dry_run_and_apply_without_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    responses = iter(
        [
            {
                "attempt_status": "validated",
                "mode": "dry_run",
                "workspace": {"before_version": "version-1", "expected_version": "version-1"},
            },
            {
                "attempt_status": "unexpected",
                "mode": "apply_atomic",
                "workspace": {"after_version": "version-2", "before_version": "version-1"},
            },
        ]
    )
    published: list[dict[str, object]] = []

    def publish(request: dict[str, object]) -> dict[str, object]:
        published.append(request)
        return {"body": next(responses), "id": request["id"], "status": 200}

    monkeypatch.setattr(exchange, "_publish", publish)
    candidate = _candidate(tmp_path / "candidate.json", "batch", "item")
    exchange.seed()
    exchange.dry_run(candidate, "validated")
    with pytest.raises(batch.BatchExchangeError, match="differs"):
        exchange.apply(candidate)
    assert len(published) == 2
    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"

    with pytest.raises(batch.BatchExchangeError, match="blocked"):
        exchange.dry_run(candidate, "validated")
    with pytest.raises(batch.BatchExchangeError, match="blocked"):
        exchange.apply(candidate)
    assert len(published) == 2


@pytest.mark.parametrize(
    "workspace",
    [
        {"before_version": "wrong", "expected_version": "version-1"},
        {"before_version": "version-1", "expected_version": "wrong"},
    ],
)
def test_inconsistent_dry_run_transition_locks_without_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, workspace: dict[str, str]
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    calls: list[dict[str, object]] = []

    def publish(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "body": {"attempt_status": "validated", "mode": "dry_run", "workspace": workspace},
            "id": request["id"],
            "status": 200,
        }

    monkeypatch.setattr(exchange, "_publish", publish)
    exchange.seed()
    with pytest.raises(batch.BatchExchangeError, match="transition"):
        exchange.dry_run(_candidate(tmp_path / "candidate.json", "batch", "item"), "validated")
    assert len(calls) == 1
    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"


def test_check_rejects_round_33_depends_on_object_without_publication_or_state_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    published: list[dict[str, object]] = []
    monkeypatch.setattr(exchange, "_publish", lambda request: published.append(request))
    malformed = tmp_path / "malformed-depends-on.json"
    malformed.write_text(
        json.dumps(
            {
                "client_batch_id": "batch-1",
                "items": [
                    {
                        "client_item_id": "item-1",
                        "depends_on": [{"client_item_id": "other-item"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    before = runtime_path.read_bytes()

    with pytest.raises(batch.BatchExchangeError, match="depends_on"):
        exchange.check(malformed)

    assert runtime_path.read_bytes() == before
    assert not published
    assert not list(request_dir.iterdir())
    assert not [path for path in response_dir.iterdir() if path.name != "initial-context.json"]


def test_check_cli_accepts_generic_prior_dependency_and_payload_item_ref(tmp_path: Path) -> None:
    candidate = tmp_path / "generic-candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "client_batch_id": "generic-batch",
                "items": [
                    {"client_item_id": "make-resource", "depends_on": []},
                    {
                        "client_item_id": "use-resource",
                        "depends_on": ["make-resource"],
                        "payload": {
                            "target": {
                                "item_ref": {
                                    "client_item_id": "make-resource",
                                    "output": "resource_id",
                                }
                            }
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(ROOT / "input-pack" / "m4-batch-exchange.py"), "check", "--candidate", str(candidate)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "candidate_sha256": hashlib.sha256(
            batch.canonical_json(json.loads(candidate.read_text(encoding="utf-8")))
        ).hexdigest(),
        "status": "valid",
    }


@pytest.mark.parametrize(
    ("items", "error"),
    [
        (
            [
                {"client_item_id": "first", "depends_on": []},
                {
                    "client_item_id": "second",
                    "depends_on": ["first"],
                    "payload": {
                        "target": {
                            "item_ref": {"client_item_id": "first", "output": "not-an-output"}
                        }
                    },
                },
            ],
            "payload item_ref is malformed",
        ),
        (
            [
                {
                    "client_item_id": "first",
                    "depends_on": ["second"],
                    "payload": {
                        "target": {
                            "item_ref": {"client_item_id": "second", "output": "resource_id"}
                        }
                    },
                },
                {"client_item_id": "second", "depends_on": []},
            ],
            "depends_on",
        ),
        (
            [
                {"client_item_id": "first", "depends_on": []},
                {
                    "client_item_id": "second",
                    "depends_on": [],
                    "payload": {
                        "target": {
                            "item_ref": {"client_item_id": "first", "output": "resource_iri"}
                        }
                    },
                },
            ],
            "must be listed",
        ),
        (
            [
                {"client_item_id": "same", "depends_on": []},
                {"client_item_id": "same", "depends_on": []},
            ],
            "unique non-empty",
        ),
        (
            [
                {
                    "client_item_id": "first",
                    "depends_on": [],
                    "item_ref": {"client_item_id": "first", "output": "resource_id"},
                }
            ],
            "allowed only inside payload",
        ),
    ],
    ids=(
        "malformed-payload-output",
        "unordered-item-ref",
        "missing-dependency",
        "duplicate-ids",
        "item-ref-outside-payload",
    ),
)
def test_check_rejects_malformed_candidate_reference_topology(
    tmp_path: Path, items: list[dict[str, object]], error: str
) -> None:
    candidate = tmp_path / "malformed-candidate.json"
    candidate.write_text(
        json.dumps({"client_batch_id": "batch-1", "items": items}), encoding="utf-8"
    )

    with pytest.raises(batch.BatchExchangeError, match=error):
        batch.check_candidate(candidate)


def test_dry_run_revalidates_candidate_drift_before_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_path, request_dir, response_dir = _write_runtime(tmp_path)
    exchange = batch.BatchExchange(
        runtime_path=runtime_path, request_dir=request_dir, response_dir=response_dir
    )
    published: list[dict[str, object]] = []
    monkeypatch.setattr(exchange, "_publish", lambda request: published.append(request))
    candidate = _candidate(tmp_path / "candidate.json", "batch-1", "item-1")

    exchange.seed()
    assert exchange.check(candidate)["status"] == "valid"
    candidate.write_text(
        json.dumps(
            {
                "client_batch_id": "batch-1",
                "items": [{"client_item_id": "item-1", "depends_on": {}}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(batch.BatchExchangeError, match="depends_on"):
        exchange.dry_run(candidate, "validated")

    assert not published
    assert not list(request_dir.iterdir())
    assert json.loads(runtime_path.read_text(encoding="utf-8"))["terminal_status"] == "BLOCKED"
