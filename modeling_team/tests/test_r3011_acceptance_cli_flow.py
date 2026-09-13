"""T-G4-1/G4-4/G4-6/G4-7: the real ``cq-acceptance`` CLI end-to-end flow.

These tests prove the ACTUAL default acceptance child factory chain: the CLI is
invoked as a real process, ``CodexRuntimeAdapter`` resolves a controlled
``codex`` App Server executable first on the fixture PATH (no launcher, factory
or runtime symbol is replaced), the private Examiner namespace is built by the
product launcher, the real staged ``report_sink_mcp.py`` / ``read_proxy_mcp.py``
bridges are spawned by the controlled App Server exactly as the mounted child
``config.toml`` declares, and the real ``ReportSinkServer`` / ``ScopedReadProxy``
AF_UNIX sockets plus the local canonical ``McpReadForwarder`` carry every read
and every report.

The controlled App Server opens no network socket (socket creation raises), so
the chain can never fall through to a real model.  All fixture credentials are
synthetic and are asserted absent from every output surface.

Fixture owned files: this test module plus the three tracked executables in
``modeling_team/tests/fixtures/r3011_acceptance_cli/`` next to it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from modeling_team.competency_questions import CQ_FREEZE_SCHEMA, freeze_question_pool
from modeling_team.contracts import repository_root

REPO_ROOT = repository_root()
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "r3011_acceptance_cli"
APP_SERVER = FIXTURE_DIR / "codex_app_server.py"
CANONICAL_SERVER = FIXTURE_DIR / "canonical_mcp_server.py"
CLI_ENTRY = FIXTURE_DIR / "cli_entry.py"

FREEZE_ID = "freeze-0001"
RUN_ID = "r3011-cli-run"
READ_KEY = "fixture-acceptance-read-key-" + "0f" * 16
READ_TOOLS = ("get_ontology_workspace_context", "query_semantic_context")
PROJECT_ID = "project-1"
ONTOLOGY_A = "ontology-1"
ONTOLOGY_B = "ontology-2"
ONTOLOGY_C = "ontology-3"
GRAPH_A = "gs-ontology-1"
GRAPH_B = "gs-ontology-2"
GRAPH_C = "gs-ontology-3"
SOURCE_NAME = "scenario-brief.md"
INTERVIEW_REF = "competency-questions/private/interview-0001.json"
SOURCE_BYTES = (
    "Scenario brief (approved source bytes).\n"
    "Entitlement ACL-1 grants read on dataset D1.\n"
    "Judge basis:cccccccc0001\n"
)
INTERVIEW_BYTES = {
    "schema_version": "r3-0-011-cq-interview/v1",
    "interview_id": "interview-0001",
    "text": (
        "Stakeholder interview record. The stakeholder confirmed that entitlement "
        "ACL-2 grants read on dataset D2. Judge basis:cccccccc0002"
    ),
}
FACT_A = "entitlement ACL-1 grants read on dataset D1"
FACT_B = "entitlement ACL-2 grants read on dataset D2"
FACT_C = "entitlement ACL-3 grants read on dataset D3"
# Provider/credential variables that must never reach the CLI under test.
_DROP_ENV_PREFIXES = ("OPENAI_", "ANTHROPIC_", "DEEPSEEK", "LLM_API_KEY", "R3011_")
_DROP_ENV_NAMES = {
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "CODEX_HOME",
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _question(question_id: str, *, kind: str, text: str, points: list[str], source: str) -> dict:
    return {
        "question_id": question_id,
        "scope": {"kind": kind, "slice_ids": [] if kind == "panorama" else ["slice-1"]},
        "question": text,
        "answer_points": points,
        "evidence_refs": [{"source": source, "locator": "approved bytes"}],
        "unknown": [],
        "proposed_visibility": "hidden",
        "content_version": 1,
    }


def _canonical_state() -> dict:
    return {
        "project_id": PROJECT_ID,
        "ontologies": {
            ONTOLOGY_A: {
                "default_graph_set_id": GRAPH_A,
                "source_signature": "sig-ontology-1",
                "graph_set_status": "ready",
                "revision": 3,
                "members": [{"role": "asserted", "revision": 3, "content_hash": "sha256:" + "1" * 64}],
                "facts": [f"fact: {FACT_A}"],
            },
            ONTOLOGY_B: {
                "default_graph_set_id": GRAPH_B,
                "source_signature": "sig-ontology-2",
                "graph_set_status": "ready",
                "revision": 5,
                "members": [{"role": "asserted", "revision": 5, "content_hash": "sha256:" + "2" * 64}],
                "facts": [f"fact: {FACT_B}"],
            },
            ONTOLOGY_C: {
                "default_graph_set_id": GRAPH_C,
                "source_signature": "sig-ontology-3",
                "graph_set_status": "ready",
                "revision": 7,
                "members": [{"role": "asserted", "revision": 7, "content_hash": "sha256:" + "3" * 64}],
                "facts": [f"fact: {FACT_C}"],
            },
        },
    }


def _handoff_binding(frozen: dict) -> dict:
    """Handoff binding whose pre-handoff state entries are opaque markers.

    A handoff is written before the batch and cannot own the batch's live
    platform state: the executed CLI binds the actual pre-session state itself
    (D5).  The markers below are valid (non-empty) state digests that are
    deliberately no platform state, so the CLI has to replace them with its own
    batch-start observation instead of trusting or re-deriving a private digest
    recipe from this fixture.
    """

    return {
        "schema_version": "r3-0-011-model-binding/v1",
        "batch_id": frozen["batch_id"],
        "freeze_digest": frozen["snapshot_digest"],
        "bound_at": "2026-09-09T00:00:00+00:00",
        "ontologies": [
            {
                "project_id": PROJECT_ID,
                "ontology_id": ontology,
                "workspace_state": {"state_digest": f"handoff-marker:{ontology}:workspace"},
                "graph_state": {"state_digest": f"handoff-marker:{ontology}:graph"},
                "authorized_read_tools": list(READ_TOOLS),
            }
            for ontology in (ONTOLOGY_A, ONTOLOGY_B, ONTOLOGY_C)
        ],
    }


def _freeze() -> dict:
    items = [
        _question(
            "cq-9",
            kind="panorama",
            text=f"Which dataset does ACL-1 grant read on? [[needs:{ONTOLOGY_A}]]",
            points=[FACT_A],
            source=SOURCE_NAME,
        ),
        _question(
            "cq-7",
            kind="slice",
            text=f"Which dataset does ACL-2 grant read on? [[needs:{ONTOLOGY_B}]]",
            points=[FACT_B],
            source=INTERVIEW_REF,
        ),
    ]
    return freeze_question_pool(
        {
            "schema_version": CQ_FREEZE_SCHEMA,
            "batch_id": "batch-cli-r3011",
            "material_digest": "material-cli-r3011",
            "panorama_question_ids": ["cq-9"],
            "slice_question_ids": ["cq-7"],
            "ordering": ["cq-9", "cq-7"],
            "review_binding": {
                "review_id": "cq-review-cli-0001",
                "review_content_version": 1,
                "decision_digest": "sha256:" + "0" * 64,
            },
            "questions": items,
        }
    )


def _build_scenario(tmp: Path, *, drift_after: int = 0, fail_read_after: int = 0) -> dict:
    """Write a legal run root, handoff, fixture ``codex`` and canonical state."""

    run_root = tmp / "run"
    frozen = _freeze()
    (run_root / "competency-questions" / "frozen").mkdir(parents=True)
    (run_root / "acceptance-v3").mkdir(parents=True)
    (run_root / "competency-questions" / "private").mkdir(parents=True)
    (run_root / "acceptance-v3" / "run-contract.json").write_text(
        json.dumps(
            {
                "schema_version": "r3-0-011-run-contract/v1",
                "run_id": RUN_ID,
                "profile_id": "r3-0-011-competency-question",
                "task_id": "r3-0-008b-staged-real",
                "parameters": {"competency_question_acceptance": True},
            }
        ),
        encoding="utf-8",
    )
    (run_root / "competency-questions" / "frozen" / f"{FREEZE_ID}.json").write_text(
        json.dumps(frozen), encoding="utf-8"
    )
    (run_root / "competency-questions" / "private" / "interview-0001.json").write_text(
        json.dumps(INTERVIEW_BYTES), encoding="utf-8"
    )
    source_payload = SOURCE_BYTES.encode("utf-8")
    (run_root / "source-manifest.json").write_text(
        json.dumps({"sources": [{"path": SOURCE_NAME, "sha256": _sha256(source_payload)}]}),
        encoding="utf-8",
    )
    # Multi-role staging: one identical approved copy per authorized role.
    for role in ("coordinator", "modeling", "competency-question"):
        role_dir = run_root / "sources" / role
        role_dir.mkdir(parents=True)
        (role_dir / SOURCE_NAME).write_bytes(source_payload)

    state_path = tmp / "platform-state.json"
    state_path.write_text(json.dumps(_canonical_state()), encoding="utf-8")
    binding = _handoff_binding(frozen)
    handoff = tmp / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "authorized_ontology_ids": [ONTOLOGY_A, ONTOLOGY_B, ONTOLOGY_C],
                "production_delivery": {"ready": True, "pending_writes": False},
                "model_binding": binding,
            }
        ),
        encoding="utf-8",
    )

    codex_home = tmp / "codex-home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text(
        json.dumps({"synthetic_fixture_credential": True, "OPENAI_API_KEY": None}), encoding="utf-8"
    )
    os.chmod(codex_home / "auth.json", 0o600)
    fixture_bin = tmp / "bin"
    fixture_bin.mkdir()
    fixture_codex = fixture_bin / "codex"
    shutil.copyfile(APP_SERVER, fixture_codex)
    os.chmod(fixture_codex, 0o755)

    env = {
        key: value
        for key, value in os.environ.items()
        if not any(key.startswith(prefix) for prefix in _DROP_ENV_PREFIXES) and key not in _DROP_ENV_NAMES
    }
    env.update(
        {
            "PATH": f"{fixture_bin}:{os.environ.get('PATH', '')}",
            "CODEX_HOME": str(codex_home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            # Synthetic only: no provider credential and a black-hole proxy so no
            # process in this chain can reach a real model endpoint.
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "R3011_ACCEPTANCE_PLATFORM_READ_KEY": READ_KEY,
            "R3011_FIXTURE_REPO": str(REPO_ROOT),
            "R3011_FIXTURE_CANONICAL": str(CANONICAL_SERVER),
            "R3011_FIXTURE_STATE": str(state_path),
            "R3011_FIXTURE_CODEX": str(fixture_codex),
            "R3011_FIXTURE_EVIDENCE": str(tmp / "host-evidence.json"),
            "R3011_FIXTURE_DRIFT": str(drift_after or ""),
            "R3011_FIXTURE_FAIL_READ": str(fail_read_after or ""),
        }
    )
    return {
        "tmp": tmp,
        "run_root": run_root,
        "handoff": handoff,
        "env": env,
        "fixture_codex": fixture_codex,
        "state_path": state_path,
        "batch_id": frozen["batch_id"],
        "question_ids": ["cq-9", "cq-7"],
    }


def _run_cli(scenario: dict, *extra: str, timeout: float = 45.0) -> dict:
    preexisting = {item.name for item in Path("/tmp").glob("r3011-acceptance-*")}
    completed = subprocess.run(
        [
            sys.executable,
            str(CLI_ENTRY),
            "cq-acceptance",
            "--run-root",
            str(scenario["run_root"]),
            "--freeze-id",
            FREEZE_ID,
            "--model-handoff",
            str(scenario["handoff"]),
            # The controlled App Server answers in milliseconds; a short session
            # deadline keeps a fake-protocol defect from stalling the run.
            "--session-timeout",
            "10",
            *extra,
        ],
        env=scenario["env"],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(scenario["tmp"]),
    )
    scenario["preexisting_roots"] = preexisting
    scenario["proc"] = completed
    scenario["stdout_json"] = None
    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and '"batch_id"' in line:
            try:
                scenario["stdout_json"] = json.loads(line)
            except json.JSONDecodeError:
                scenario["stdout_json"] = None
    report_dir = scenario["run_root"] / "acceptance-v3" / "reports" / scenario["batch_id"]
    scenario["report_dir"] = report_dir
    report_path = report_dir / "batch-report.json"
    scenario["report"] = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else None
    scenario["new_private_roots"] = sorted(
        item.name
        for item in Path("/tmp").glob("r3011-acceptance-*")
        if item.name not in preexisting
    )
    return scenario


def _markers(text: str) -> dict[str, str]:
    return dict(part.split("=", 1) for part in text.split(";") if "=" in part)


def _evidence_of(report: dict, question_id: str) -> dict[str, str]:
    for entry in report["examiner_reports"]:
        if entry["question_id"] == question_id:
            return _markers(entry["reason"])
    raise AssertionError(f"no examiner report for {question_id} in {json.dumps(report)[:800]}")


def _verdict_note(report: dict, question_id: str) -> dict[str, str]:
    for entry in report["verdicts"]:
        if entry["question_id"] == question_id:
            return _markers(entry["note"])
    raise AssertionError(f"no verdict for {question_id} in {json.dumps(report)[:800]}")


def _assert_handoff_markers_replaced(scenario: dict, report: dict) -> None:
    """The handoff markers were replaced by the actual batch-start state everywhere.

    The handoff cannot own live state, so no handoff marker may survive into any
    executed surface: the reported batch binding must be the CLI's own pre-session
    observation and the packet/proxy/report must not carry the stale input.
    """

    assert report["sessions"]["pre_batch_model_state_drift"] == [], report["sessions"].get(
        "pre_batch_model_state_drift"
    )
    binding = report["sessions"]["batch_model_binding"]
    assert binding is not None, "the executed batch never bound actual pre-session state"
    for entry in binding["ontologies"]:
        for field in ("workspace_state", "graph_state"):
            digest = str(entry[field]["state_digest"])
            assert not digest.startswith("handoff-marker:"), (
                f"{entry['ontology_id']}.{field} still carries the handoff marker: {digest}"
            )
            assert len(digest) >= 32, digest
    surfaces = [json.dumps(report, sort_keys=True)]
    packet_path = scenario["report_dir"] / "batch-packet.json"
    if packet_path.is_file():
        surfaces.append(packet_path.read_text(encoding="utf-8"))
    for surface in surfaces:
        assert "handoff-marker:" not in surface, "a handoff state marker reached an executed surface"


def _assert_mounted_v3_prompts(markers: dict[str, str], *, platform: bool) -> None:
    """The mounted child prompt/skill bytes really are the v3 batch contract.

    The controlled App Server reads the actual ``instructions.md``/``SKILL.md``
    bytes inside the namespace, so a legacy one-question/Source-Examiner mount
    shows up here instead of being ignored while the fixture emits v3 reports.
    """

    assert markers["skill_names"] == "v3-acceptance-batch", markers
    assert markers["prompt_legacy_markers"] == "", markers
    assert len(markers["instructions"]) == 16 and len(markers["skill"]) == 16, markers
    assert "batch_id" in markers["prompt_markers"], markers
    assert "submit_examiner_report" in markers["prompt_markers"], markers
    if platform:
        assert "question_content_version" in markers["prompt_markers"], markers
    # The mounted v3 read surface was really advertised to the child.
    if platform:
        assert markers["schemas"] == (
            "get_ontology_workspace_context:1,query_semantic_context:1"
        ), markers


def _assert_batch_cleanup(report: dict, expected_children: int = 2) -> None:
    """The batch's own teardown outcome: forwarder stopped, every child gone.

    The evidence is the per-child teardown the runtime boundary observed after
    ``destroy`` -- never a global scan -- so a concurrently running batch can
    never be reported as this batch's cleanup.  ``expected_children`` is 2 for
    the happy batch (one Platform Examiner batch child + one judge) and 1 when
    the batch failed before the judge session was started at all.
    """

    cleanup = report["sessions"]["cleanup"]
    assert cleanup["forwarder_stopped"] is True, cleanup
    assert cleanup["forwarder_still_active"] is False
    assert cleanup["children_destroyed"] is True, cleanup
    children = cleanup["children"]
    assert len(children) == expected_children, children
    for child in children:
        assert child["child_stopped"] is True and child["child_destroyed"] is True, child
        assert child["proxy_stopped"] is True, child
        assert child["report_sink_stopped"] is True, child
        assert child["private_root_removed"] is True and child["socket_root_removed"] is True, child


def _assert_no_key_leak(scenario: dict) -> None:
    surfaces = [scenario["proc"].stdout, scenario["proc"].stderr]
    for name in ("batch-report.json", "attribution.json", "batch-packet.json"):
        path = scenario["report_dir"] / name
        if path.is_file():
            surfaces.append(path.read_text(encoding="utf-8"))
    evidence = scenario["tmp"] / "host-evidence.json"
    if evidence.is_file():
        surfaces.append(evidence.read_text(encoding="utf-8"))
    for surface in surfaces:
        assert READ_KEY not in surface, "the synthetic platform read key leaked into an output surface"


@pytest.fixture(scope="module")
def happy_run(tmp_path_factory) -> dict:
    tmp = tmp_path_factory.mktemp("cli-happy")
    return _run_cli(_build_scenario(tmp))


# --- T-G4-1: two real v3 sessions complete the two-question batch -------------


def test_tg41_two_v3_sessions_complete_the_batch_through_real_sockets(happy_run: dict) -> None:
    scenario, proc = happy_run, happy_run["proc"]
    evidence = json.loads((scenario["tmp"] / "host-evidence.json").read_text(encoding="utf-8"))
    # The process boundary is the controlled executable, resolved by the real
    # adapter through PATH; no launcher/factory symbol was replaced.
    assert evidence["codex_resolved"] == str(scenario["fixture_codex"]), evidence
    assert evidence["canonical_is_controlled"] is True
    assert evidence["expected_tools"] == list(READ_TOOLS)

    assert proc.returncode == 0, (
        "expected full batch PASS from the real CLI flow\n"
        f"stdout={proc.stdout[-3000:]}\nstderr={proc.stderr[-3000:]}\n"
        f"report={json.dumps(scenario['report'], sort_keys=True)[:3000]}"
    )
    assert scenario["stdout_json"]["full_pass"] is True
    assert scenario["stdout_json"]["executed_question_ids"] == scenario["question_ids"]
    assert scenario["stdout_json"]["consumes_semantic_start"] is False
    assert scenario["stdout_json"]["start_ledger_write"] is False

    report = scenario["report"]
    assert report["full_pass"] is True
    assert sorted(report["executed_question_ids"]) == sorted(scenario["question_ids"])
    assert report["unexecuted_question_ids"] == []
    assert report["blind_status"]["blind_status"] == "blind"
    # Two sessions: one platform Examiner batch session and one judge session.
    assert report["sessions"]["platform_examiner"]["reports"] == 2
    assert report["sessions"]["platform_examiner"]["missing_question_ids"] == []
    assert report["sessions"]["platform_examiner"]["failure_reason"] is None
    assert report["sessions"]["acceptance_judge"]["verdicts"] == 2
    assert report["sessions"]["lifecycle_errors"] == []
    assert [entry["verdict"] for entry in report["verdicts"]] == ["pass", "pass"]
    # The per-scope summary counts every canonical v3 verdict state.
    assert report["summary_by_scope"] == {
        "panorama": {
            "pass": 1,
            "model-recall-insufficient": 0,
            "question-answer-review": 0,
            "platform-runtime-incomplete": 0,
        },
        "slice": {
            "pass": 1,
            "model-recall-insufficient": 0,
            "question-answer-review": 0,
            "platform-runtime-incomplete": 0,
        },
    }
    # D5: the batch binding came from the real pre-session read and the real
    # post-session read is recorded with no drift.
    assert report["sessions"]["batch_model_binding"]["ontologies"][0]["ontology_id"] == ONTOLOGY_A
    assert report["sessions"]["post_batch_model_state_drift"] == []
    assert report["coverage_gaps"]["model_state_drift"] == []
    _assert_handoff_markers_replaced(scenario, report)

    # The platform session answered from real authorized platform reads and the
    # judge session judged the same answers against the real evidence bytes.
    platform_a = _evidence_of(report, "cq-9")
    platform_b = _evidence_of(report, "cq-7")
    for markers in (platform_a, platform_b):
        assert markers["fixture:appserver"] == "controlled-codex", markers
        assert markers["role"] == "platform"
        assert markers["packet_blind"] == "1"
        assert markers["reads"].startswith("multi:")
        assert markers["spawned"] == "examiner_report+platform_read_proxy"
        _assert_mounted_v3_prompts(markers, platform=True)
    assert ONTOLOGY_A in platform_a["reads"] and ONTOLOGY_B in platform_a["reads"]
    assert ONTOLOGY_C in platform_a["reads"]
    judge_a = _verdict_note(report, "cq-9")
    judge_b = _verdict_note(report, "cq-7")
    for markers in (judge_a, judge_b):
        assert markers["fixture:appserver"] == "controlled-codex", markers
        assert markers["role"] == "acceptance"
        assert markers["examiner_reports"] == "2"
        assert markers["spawned"] == "examiner_report"
        _assert_mounted_v3_prompts(markers, platform=False)
    # Each verdict basis digest is the actual approved material bytes.
    assert judge_a["basis"] == "cccccccc0001", judge_a
    assert judge_b["basis"] == "cccccccc0002", judge_b
    assert SOURCE_NAME in judge_a["evidence"] and INTERVIEW_REF.split("/")[-1] in judge_b["evidence"]

    # Evidence refs are the real ScopedReadProxy receipt digests, forwarded by
    # the real staged read bridge (request/response digests are 64 hex chars).
    for entry in report["examiner_reports"]:
        assert entry["status"] == "completed", entry
        assert entry["evidence_refs"], entry
        tool, request_digest, response_digest = entry["evidence_refs"][0].split("|")
        assert tool == "query_semantic_context"
        assert len(request_digest) == 64 and len(response_digest) == 64

    # Actual cleanup of this batch: no owned private root or socket survived.
    assert scenario["new_private_roots"] == []
    _assert_batch_cleanup(report)
    _assert_no_key_leak(scenario)


def test_tg41_platform_packet_stays_blind_and_multi_ontology_scope(happy_run: dict) -> None:
    scenario = happy_run
    packet = json.loads((scenario["report_dir"] / "batch-packet.json").read_text(encoding="utf-8"))
    assert sorted(packet) == ["canonical_digest", "schema_version"]
    attribution = json.loads((scenario["report_dir"] / "attribution.json").read_text(encoding="utf-8"))
    assert attribution["platform_read_path"] == "local-canonical-mcp-forwarder"
    assert attribution["blind_status"] == "blind"
    report = scenario["report"]
    platform_a = _evidence_of(report, "cq-9")
    platform_b = _evidence_of(report, "cq-7")
    # One authorized multi-Ontology read covered the whole batch scope in a
    # single call; the blind packet carried neither answer points nor evidence.
    assert (
        platform_a["reads"].split(",")[0]
        == f"multi:{ONTOLOGY_A}+{ONTOLOGY_B}+{ONTOLOGY_C}:1"
    ), platform_a["reads"]
    assert "evidence_bundle" not in json.dumps(report["sessions"]["batch_model_binding"])
    # The second-only selection and the subset that excludes the primary entry
    # are separate real proxy/forwarder round trips against the same scope.
    assert platform_b["reads"].split(",")[1] == f"second:{ONTOLOGY_C}:1", platform_b["reads"]
    assert (
        platform_b["reads"].split(",")[2] == f"subset:{ONTOLOGY_B}+{ONTOLOGY_C}:1"
    ), platform_b["reads"]


# --- T-G4-4: credentials ------------------------------------------------------


def test_tg44_missing_platform_read_key_fails_typed_without_sessions(tmp_path) -> None:
    scenario = _build_scenario(tmp_path)
    env = dict(scenario["env"])
    env.pop("R3011_ACCEPTANCE_PLATFORM_READ_KEY")
    scenario["env"] = env
    result = _run_cli(scenario)
    assert result["proc"].returncode == 2, (
        f"stdout={result['proc'].stdout[-1500:]}\nstderr={result['proc'].stderr[-1500:]}"
    )
    assert "cq_acceptance_credentials_missing" in result["proc"].stderr
    assert "R3011_ACCEPTANCE_PLATFORM_READ_KEY" in result["proc"].stderr
    # No session was started and no report was fabricated.
    assert result["report"] is None
    assert not (result["report_dir"] / "batch-report.json").exists()
    assert not (result["tmp"] / "host-evidence.json").exists()
    assert result["new_private_roots"] == []


def test_tg44_synthetic_key_is_absent_from_child_visible_surfaces(happy_run: dict) -> None:
    scenario = happy_run
    evidence = json.loads((scenario["tmp"] / "host-evidence.json").read_text(encoding="utf-8"))
    # The forwarder is the only key holder and records no key value.
    assert evidence["read_key_present"] is True
    assert evidence["read_key_value"] == ""
    for entry in evidence["forwarder_command"]:
        assert READ_KEY not in entry
    _assert_no_key_leak(scenario)


# --- T-G4-6: post-batch state read outcomes ----------------------------------


def test_tg46_post_read_drift_keeps_reports_and_fails_the_batch(tmp_path) -> None:
    # Reads 1-3 are the CLI's own pre-batch binding reads; every later read
    # observes one graph revision further, so only the post-batch read drifts.
    scenario = _run_cli(_build_scenario(tmp_path, drift_after=3))
    proc = scenario["proc"]
    assert proc.returncode == 1, (
        f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}\n"
        f"report={json.dumps(scenario['report'], sort_keys=True)[:2000]}"
    )
    report = scenario["report"]
    assert report is not None
    # The examiner batch itself was received and is retained in the report.
    assert len(report["examiner_reports"]) == 2
    assert sorted(report["executed_question_ids"]) == sorted(scenario["question_ids"])
    # The real post-session read detected the drift and blocked the judge.
    drift = report["sessions"]["post_batch_model_state_drift"]
    assert drift, "post-read drift was not detected"
    assert report["coverage_gaps"]["model_state_drift"] == drift
    assert report["full_pass"] is False
    assert "drift" in report["sessions"]["acceptance_judge"]["reason"]
    assert "verdicts" not in report["sessions"]["acceptance_judge"]
    assert report["sessions"]["lifecycle_errors"] == []
    # Cleanup still happened for real; the judge was skipped, so one child.
    assert scenario["new_private_roots"] == []
    _assert_batch_cleanup(report, expected_children=1)
    _assert_no_key_leak(scenario)


def test_tg46_post_read_failure_is_runtime_incomplete_and_retained(tmp_path) -> None:
    scenario = _run_cli(_build_scenario(tmp_path, fail_read_after=5))
    proc = scenario["proc"]
    assert proc.returncode == 1, (
        f"stdout={proc.stdout[-2500:]}\nstderr={proc.stderr[-2500:]}"
    )
    report = scenario["report"]
    assert report is not None
    assert len(report["examiner_reports"]) == 2
    assert sorted(report["executed_question_ids"]) == sorted(scenario["question_ids"])
    stages = [entry["stage"] for entry in report["sessions"]["lifecycle_errors"]]
    assert "post-batch-model-state-read" in stages
    assert report["full_pass"] is False
    assert "verdicts" not in report["sessions"]["acceptance_judge"]
    assert scenario["new_private_roots"] == []
    _assert_batch_cleanup(report, expected_children=1)
    _assert_no_key_leak(scenario)


# --- T-G4-7: child dies mid-batch --------------------------------------------


def test_tg47_mid_batch_child_exit_retains_executed_report(tmp_path) -> None:
    scenario = _build_scenario(tmp_path)
    state = json.loads(scenario["state_path"].read_text(encoding="utf-8"))
    # Fixture directive: the controlled child answers the first question, then
    # exits, exactly like a crashed examiner process.
    first = state["ontologies"]
    assert first  # state sanity before the directive is bound below
    _patch_first_question_directive(scenario, "exit-after-first-report")
    result = _run_cli(scenario)
    proc = result["proc"]
    assert proc.returncode == 1, f"stdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
    report = result["report"]
    assert report is not None
    # The accepted first report is retained after real cleanup; the rest is
    # recorded as unexecuted with the typed failure layer/reason.
    assert report["executed_question_ids"] == ["cq-9"], report["executed_question_ids"]
    assert report["unexecuted_question_ids"] == ["cq-7"]
    sessions = report["sessions"]
    failure_reason = str(sessions["platform_examiner"]["failure_reason"])
    assert failure_reason
    assert "runtime-infrastructure" in failure_reason, failure_reason
    # The stdout pump can observe the child output closing before the process
    # poll observes the exit, so either typed runtime code is the real reason;
    # both are the same runtime-infrastructure stop and neither is remapped.
    assert "child-exited" in failure_reason or "child-output-closed" in failure_reason, (
        failure_reason
    )
    assert sessions["platform_examiner"]["first_failure"]
    # R3.0-012 §4.3 (T3-2): the landed report is judgeable even though the
    # examiner child died mid-batch -- the judge runs for that question, the
    # unreported one stays unexecuted, and the whole batch still cannot pass.
    assert sessions["acceptance_judge"]["verdicts"] == 1
    assert sessions["acceptance_judge"]["judged_question_ids"] == ["cq-9"]
    stages = [entry["stage"] for entry in sessions["lifecycle_errors"]]
    assert "platform-examiner-session" in stages
    # Real teardown of this batch's own resources, observed after the CLI exited;
    # the examiner and judge children were both started and both cleaned up.
    assert result["new_private_roots"] == []
    _assert_batch_cleanup(report, expected_children=2)
    _assert_no_key_leak(result)


def _patch_first_question_directive(scenario: dict, directive: str) -> None:
    """Bind a fixture directive into the frozen first question's text.

    A stored freeze is append-only: ``reload_frozen_pool`` re-derives the
    digest and rejects any edited file.  The directive therefore has to be
    frozen into a fresh pool (new ``snapshot_digest``) that the CLI accepts as
    the frozen input, and the handoff is re-bound to that digest.
    """

    from modeling_team.competency_questions import freeze_question_pool

    freeze_path = scenario["run_root"] / "competency-questions" / "frozen" / f"{FREEZE_ID}.json"
    frozen = json.loads(freeze_path.read_text(encoding="utf-8"))
    frozen["questions"][0]["question"] += f" [[fixture:{directive}]]"
    rebuilt_input = {key: value for key, value in frozen.items() if key != "snapshot_digest"}
    rebuilt_input["questions"] = [
        {
            **{key: value for key, value in question.items() if key != "visibility"},
            "proposed_visibility": question.get("visibility"),
        }
        for question in frozen["questions"]
    ]
    reloaded = freeze_question_pool(rebuilt_input)
    freeze_path.write_text(json.dumps(reloaded), encoding="utf-8")
    handoff = json.loads(scenario["handoff"].read_text(encoding="utf-8"))
    handoff["model_binding"]["freeze_digest"] = reloaded["snapshot_digest"]
    handoff_path = scenario["tmp"] / "handoff.json"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    scenario["handoff"] = handoff_path
    scenario["batch_id"] = reloaded["batch_id"]
