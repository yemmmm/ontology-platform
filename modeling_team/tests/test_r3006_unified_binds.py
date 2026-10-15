"""R3.0-006 unified staged binds (v3 execution-gap closure, design §3.G2).

Covers test plan T-G2-1…T-G2-4.  T-G2-1 exercises the **real** bubblewrap
namespace built from the adapter's own mount list (equivalent minimal bwrap
plus the exact staged bind sequence) and asserts actual filesystem outcomes
for slot, candidates and materialization-plans writes plus rename/unlink/chmod
of the mounted plans directory — not parameter strings.  The slot bytes the
Modeling namespace writes are a valid ``r3-0-009-stage3-slot/v1`` body (the
existing 009 fixture shape), and the same host-side file is then accepted by
the Runner gate ``staged_stage3_issue`` — the agreed H1 cross-boundary proof.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from modeling_team.runtimes.codex import CodexRuntimeAdapter
from modeling_team.staged_decisions import (
    load_materialization_plan_ref,
    load_stage3_slot,
    load_unified_candidate,
    staged_decision_directories,
    staged_stage3_issue,
    validate_stage3_slot,
    validate_unified_candidate,
)
from modeling_team.tests.test_r30002_runner_wiring import _role_agent
from modeling_team.tests.test_r30009_runner_wiring import _candidate

REPO_ROOT = Path(__file__).resolve().parents[2]

PARENT = "/agent/work/stage3-neutral-graph"
PLANS = f"{PARENT}/materialization-plans"
CANDIDATES = f"{PARENT}/candidates"
SLOT = f"{PARENT}/neutral-candidate.json"

LEGACY_MODELING_BINDS = [
    "--ro-bind",
    "<run>/value-semantics",
    "/agent/work/value-semantics",
    "--bind",
    "<run>/value-semantics/conclusions",
    "/agent/work/value-semantics/conclusions",
    "--bind",
    "<run>/value-semantics/conclusions-archive",
    "/agent/work/value-semantics/conclusions-archive",
    "--bind",
    "<run>/stage3-neutral-graph",
    "/agent/work/stage3-neutral-graph",
]


def _run_root(base: Path) -> Path:
    root = base / "run"
    for directory in staged_decision_directories(root, unified=True):
        directory.mkdir(parents=True, exist_ok=True)
    (root / "scenario-map").mkdir(exist_ok=True)
    for relative in (
        "competency-questions/public",
        "competency-questions/private",
        "competency-questions/reviews",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    return root


def _adapter(root: Path, *, unified: bool) -> CodexRuntimeAdapter:
    adapter = CodexRuntimeAdapter(repository_root=REPO_ROOT)
    adapter._run_root = root
    adapter._staged_decisions_enabled = True
    adapter._multi_slice_scenario_map_enabled = True
    adapter._unified_graph = unified
    # Bind construction reads the active-run CQ selector; point it at a run
    # double that declares the 011 selector so production roles get the public
    # projection bind in the same command.
    adapter._active_run = SimpleNamespace(
        root=root,
        run_id="r30006-binds",
        configuration=SimpleNamespace(
            profile=SimpleNamespace(profile_id="r3-0-011-competency-question"),
            task=SimpleNamespace(
                schema_version=2,
                task_id="r3-0-006-real-full",
                parameters={
                    "multi_slice_workflow": True,
                    "staged_modeling_decisions": True,
                    "unified_semantic_graph": unified,
                    "competency_question_acceptance": True,
                },
            ),
        ),
    )
    return adapter


def _binds(command: list[str]) -> list[tuple[str, str, str]]:
    triples = []
    for index, item in enumerate(command):
        if item in {"--ro-bind", "--bind"}:
            triples.append((item, command[index + 1], command[index + 2]))
    return triples


def test_t_g2_2_unified_mount_sequences_match_the_design(tmp_path):
    root = _run_root(tmp_path)
    adapter = _adapter(root, unified=True)
    try:
        agents = {}
        sequences = {}
        for role in ("modeling", "protocol", "coordinator", "competency-question"):
            agent = _role_agent(root / "agents", role)
            agents[role] = agent
            sequences[role] = adapter._staged_decision_binds(agent)

        modeling = sequences["modeling"]
        triples = _binds(["x"] + modeling)
        assert ("--bind", str(root / "stage3-neutral-graph"), PARENT) in triples
        assert ("--ro-bind", str(root / "stage3-neutral-graph/materialization-plans"), PLANS) in triples
        # Order matters: the read-only overlay must be mounted after the
        # writable parent bind it carves out of.
        assert modeling.index("--bind") < modeling.index(
            "--ro-bind", modeling.index(PLANS) - 2
        )
        # The value-semantics and candidates ownership is unchanged.
        assert ("--bind", str(root / "value-semantics/conclusions"), "/agent/work/value-semantics/conclusions") in triples

        protocol = sequences["protocol"]
        protocol_triples = _binds(["x"] + protocol)
        assert ("--ro-bind", str(root / "stage3-neutral-graph"), PARENT) in protocol_triples
        assert ("--bind", str(root / "stage3-neutral-graph/materialization-plans"), PLANS) in protocol_triples
        assert protocol.index(PARENT) < protocol.index(PLANS)

        coordinator = sequences["coordinator"]
        coordinator_triples = _binds(["x"] + coordinator)
        assert ("--ro-bind", str(root / "stage3-neutral-graph"), PARENT) in coordinator_triples
        assert PLANS not in coordinator
        assert CANDIDATES not in coordinator

        # The competency-question role sees no stage3 mount at all (its only
        # staged view is the pre-existing read-only value-semantics tree), and
        # the production roles keep their read-only public projection bind.
        assert PARENT not in sequences["competency-question"]
        assert PLANS not in sequences["competency-question"]
        # The active unified Modeling role also receives the scoped read
        # surface.  Namespace construction requires the socket to exist, so
        # provide the same small host-side endpoint that a prepared run owns.
        modeling_read_socket = root / "modeling-read.sock"
        modeling_read_socket.touch()
        adapter._active_run.modeling_read_proxy = SimpleNamespace(
            socket_path=modeling_read_socket
        )
        for role in ("coordinator", "modeling", "protocol"):
            command = adapter.namespace_command(agents[role])
            assert (
                "--ro-bind",
                str(root / "competency-questions/public"),
                "/agent/work/competency-questions/public",
            ) in _binds(command)
    finally:
        adapter.stop()


def test_t_g2_cq_role_reads_the_restored_public_projection_and_never_frozen(tmp_path):
    """R3.0-011 isolation contract for the CQ role's own namespace.

    The competency-question role keeps its ``private/`` and ``reviews/`` binds
    and additionally reads the restored ``public/`` projection read-only (the
    same legal input the production roles get); the host-only ``frozen/`` tree
    is never bound into any Agent namespace.
    """

    root = _run_root(tmp_path)
    adapter = _adapter(root, unified=True)
    try:
        command = adapter.namespace_command(_role_agent(root / "agents", "competency-question"))
        triples = _binds(command)
        for relative in ("public", "private", "reviews"):
            assert (
                "--ro-bind",
                str(root / "competency-questions" / relative),
                f"/agent/work/competency-questions/{relative}",
            ) in triples
        assert not any("competency-questions/frozen" in target for _, _, target in triples)
    finally:
        adapter.stop()


def test_t_g2_3_non_unified_staged_sequence_is_byte_identical(tmp_path):
    root = _run_root(tmp_path)
    adapter = _adapter(root, unified=False)
    try:
        modeling = _role_agent(root / "agents", "modeling")
        expected = [part.replace("<run>", str(root)) for part in LEGACY_MODELING_BINDS]
        assert adapter._staged_decision_binds(modeling) == expected
        command = adapter.namespace_command(modeling)
        assert PLANS not in command
        assert CANDIDATES not in command
        # The other roles keep the legacy absence of any stage3 mount.
        for role in ("protocol", "coordinator", "competency-question"):
            agent = _role_agent(root / "agents", role)
            assert PARENT not in adapter._staged_decision_binds(agent)
    finally:
        adapter.stop()


def test_t_g2_4_missing_unified_directory_fails_closed_before_start(tmp_path):
    root = _run_root(tmp_path)
    shutil.rmtree(root / "stage3-neutral-graph/materialization-plans")
    adapter = _adapter(root, unified=True)
    try:
        for role in ("modeling", "protocol", "coordinator"):
            agent = _role_agent(root / "agents", role)
            with pytest.raises(Exception, match="not prepared"):
                adapter.namespace_command(agent)
                break
    finally:
        adapter.stop()


def test_t_g2_5_plan_ref_still_rejects_outside_paths_and_symlinks(tmp_path):
    root = _run_root(tmp_path)
    outside = root / "outside-plan.json"
    outside.write_text("{}", encoding="utf-8")
    (root / "stage3-neutral-graph/materialization-plans/link-r1.json").symlink_to(outside)
    for plan_ref in ("../outside-plan.json", "value-semantics/ledger/x.json", "stage3-neutral-graph/other/r1.json"):
        plan, issue = load_materialization_plan_ref(root, plan_ref)
        assert plan is None and issue is not None
    plan, issue = load_materialization_plan_ref(
        root, "stage3-neutral-graph/materialization-plans/link-r1.json"
    )
    assert plan is None and issue is not None


def _bwrap_command(adapter: CodexRuntimeAdapter, agent, script: str) -> list[str]:
    """Equivalent minimal bubblewrap invocation carrying the adapter's mounts."""

    bwrap = shutil.which("bwrap")
    assert bwrap is not None, "bubblewrap is required for the T-G2-1 proof"
    command = [
        bwrap,
        "--die-with-parent",
        "--unshare-pid",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
    ]
    for source in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(source).exists():
            command.extend(["--ro-bind", source, source])
    command.extend(
        [
            "--dir",
            "/agent",
            "--bind",
            str(agent.home),
            "/agent/home",
            "--bind",
            str(agent.work),
            "/agent/work",
            *adapter._staged_decision_binds(agent),
            "--chdir",
            "/agent/work",
            "--",
            "/bin/sh",
            "-c",
            script,
        ]
    )
    return command


_SCRIPT = r"""
write() {
  label="$2"
  if printf '%s' "$label" > "$1" 2>/dev/null; then echo "OK $label"; else echo "DENIED $label"; fi
}
writeb64() {
  path="$1"; label="$2"; data="$3"
  if printf '%s' "$data" | base64 -d > "$path" 2>/dev/null; then echo "OK $label"; else echo "DENIED $label"; fi
}
readf() {
  label="$2"
  if cat "$1" >/dev/null 2>&1; then echo "OK $label"; else echo "DENIED $label"; fi
}
run() {
  label="$1"
  shift
  if "$@" >/dev/null 2>&1; then echo "OK $label"; else echo "DENIED $label"; fi
}
"""


def _valid_modeling_bytes() -> tuple[str, str]:
    """(slot, candidate) as base64 JSON in the existing 009 fixture shape."""

    candidate = _candidate()
    slot = {
        "schema_version": "r3-0-009-stage3-slot/v1",
        "scenario_id": candidate["scenario_id"],
        "produced_by": "modeling",
        "approved_by": "coordinator",
        "candidate_artifacts": ["stage3-neutral-graph/candidates/cand-1-r2.json"],
        "candidate_contract": "r3-0-009-unified-graph/v2",
        "slot_note": "neutral slot",
    }
    encode = lambda value: base64.b64encode(  # noqa: E731
        json.dumps(value).encode("utf-8")
    ).decode("ascii")
    return encode(slot), encode(candidate)


def _run_probe(adapter: CodexRuntimeAdapter, root: Path, role: str, body: str) -> dict[str, str]:
    agent = _role_agent(root / "agents", role)
    command = _bwrap_command(adapter, agent, _SCRIPT + body)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    assert completed.returncode == 0, completed.stderr[-2000:]
    results = {}
    for line in completed.stdout.splitlines():
        if line.startswith(("OK ", "DENIED ")):
            status, _, probe = line.partition(" ")
            results[probe] = status
    return results


def test_t_g2_1_real_bwrap_filesystem_outcomes(tmp_path):
    root = _run_root(tmp_path)
    (root / "stage3-neutral-graph/materialization-plans/plan-1-r1.json").write_text(
        '{"schema_version":"r3-0-009-materialization-plan/v1"}', encoding="utf-8"
    )
    slot_b64, candidate_b64 = _valid_modeling_bytes()
    adapter = _adapter(root, unified=True)
    try:
        modeling = _run_probe(
            adapter,
            root,
            "modeling",
            "\n".join(
                [
                    f'writeb64 "{SLOT}" modeling-slot-write {slot_b64}',
                    f'writeb64 "{CANDIDATES}/cand-1-r2.json" modeling-candidate-write {candidate_b64}',
                    f'write "{PLANS}/plan-9-r1.json" modeling-plans-file-write',
                    f'run modeling-plans-rename mv "{PLANS}" "{PARENT}/plans-moved"',
                    f'run modeling-plans-unlink rm -rf "{PLANS}"',
                    f'run modeling-plans-chmod chmod 0777 "{PLANS}"',
                    'echo DONE',
                ]
            ),
        )
        assert modeling["modeling-slot-write"] == "OK", modeling
        assert modeling["modeling-candidate-write"] == "OK", modeling
        assert modeling["modeling-plans-file-write"] == "DENIED", modeling
        assert modeling["modeling-plans-rename"] == "DENIED", modeling
        assert modeling["modeling-plans-unlink"] == "DENIED", modeling
        assert modeling["modeling-plans-chmod"] == "DENIED", modeling

        # H1 cross-boundary proof: the bytes Modeling's namespace actually
        # wrote are read back by the host and accepted by the same Runner gate
        # the staged submit path uses (runner.py: staged_stage3_issue with
        # unified=True), not just an in-memory slot.
        slot_path = root / "stage3-neutral-graph" / "neutral-candidate.json"
        slot = load_stage3_slot(slot_path)
        assert slot["schema_version"] == "r3-0-009-stage3-slot/v1"
        assert slot["produced_by"] == "modeling"
        assert validate_stage3_slot(slot, unified=True) == ()
        candidate = load_unified_candidate(
            root / "stage3-neutral-graph" / "candidates" / "cand-1-r2.json"
        )
        assert validate_unified_candidate(candidate) == ()
        assert staged_stage3_issue(root, None, unified=True) is None

        protocol = _run_probe(
            adapter,
            root,
            "protocol",
            "\n".join(
                [
                    f'write "{PLANS}/plan-2-r1.json" protocol-plans-file-write',
                    f'write "{SLOT}" protocol-slot-write',
                    f'write "{CANDIDATES}/cand-2-r1.json" protocol-candidate-write',
                    f'readf "{SLOT}" protocol-slot-read',
                    f'readf "{CANDIDATES}/cand-1-r2.json" protocol-candidate-read',
                    f'readf "{PLANS}/plan-1-r1.json" protocol-plans-read',
                    'echo DONE',
                ]
            ),
        )
        assert protocol["protocol-plans-file-write"] == "OK", protocol
        assert protocol["protocol-slot-write"] == "DENIED", protocol
        assert protocol["protocol-candidate-write"] == "DENIED", protocol
        assert protocol["protocol-slot-read"] == "OK", protocol
        assert protocol["protocol-candidate-read"] == "OK", protocol
        assert protocol["protocol-plans-read"] == "OK", protocol

        coordinator = _run_probe(
            adapter,
            root,
            "coordinator",
            "\n".join(
                [
                    f'readf "{SLOT}" coordinator-slot-read',
                    f'readf "{PLANS}/plan-1-r1.json" coordinator-plans-read',
                    f'write "{PARENT}/coordinator.json" coordinator-parent-write',
                    f'write "{PLANS}/plan-3-r1.json" coordinator-plans-write',
                    'echo DONE',
                ]
            ),
        )
        assert coordinator["coordinator-slot-read"] == "OK", coordinator
        assert coordinator["coordinator-plans-read"] == "OK", coordinator
        assert coordinator["coordinator-parent-write"] == "DENIED", coordinator
        assert coordinator["coordinator-plans-write"] == "DENIED", coordinator
    finally:
        adapter.stop()
