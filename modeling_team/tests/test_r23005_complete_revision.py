from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace
from typing import Any

from modeling_team.contracts import load_formal_team_configuration, repository_root
from modeling_team.protocol_mechanics import build_candidate_receipt
from modeling_team.runner import TeamRunner


_START5_ITEM_IDS = (
    "class:UnknownAffectedSubject",
    "class:Workflow",
    "class:ToolInvocation",
    "class:WorkflowVersion",
    "class:OutputContract",
    "class:ExplicitUnknown",
    "property:workflowIdentity",
    "property:versionLabel",
    "property:publicationStatus",
    "property:outputFieldName",
    "property:outputDatatype",
    "property:kind",
    "property:unknownQuestion",
    "property:affectedSubject",
    "property:rationale",
    "property:mayCompleteSuccessfullyWithoutNumericScore",
    "property:returnsDiagnosticCodeWhenScoreAbsent",
    "relation:hasOutputContract",
    "relation:invokesAsPublishedTool",
    "relation:passesResultTo",
    "relation:configuredByWorkflowIdentity",
    "shape:WorkflowVersion",
    "shape:ExplicitUnknown",
    "entity:workflow:C",
    "entity:workflow:B",
    "entity:workflow:A",
    "entity:C:draft",
    "entity:output:C:draft",
    "entity:C:v1",
    "entity:output:C:v1",
    "entity:C:v2",
    "entity:output:C:v2",
    "entity:invocation:B-C",
    "entity:unknown:B-concrete-C-version",
    "entity:unknown:C-v1-v2-continuity",
    "entity:unknown:B-no-score-behavior",
    "assertion:B-invokes-C",
    "assertion:B-passes-A",
)

_START5_CONSTRAINTS = [
    "Workflow and ToolInvocation are subclasses of UnknownAffectedSubject so affectedSubject has one formal object range.",
    "Each WorkflowVersion has exactly one versionLabel, publicationStatus, and OutputContract.",
    "Each ExplicitUnknown has kind explicit_unknown, one affectedSubject, unknownQuestion, and rationale, and no answer value.",
    "Reject and do not apply a WorkflowVersion missing its OutputContract.",
    "Do not infer B's concrete C version, semantic continuity, or absent-score behavior.",
]

_START5_QUERIES = [
    "Return B's concrete consumed C version if asserted; otherwise its explicit unknown.",
    "Return C v1/v2 semantic continuity if asserted; otherwise its explicit unknown.",
    "Return B's no-score behavior if asserted; otherwise its explicit unknown.",
]


class CandidateRevisionContractError(ValueError):
    """Offline contract failure used by the retained revision regression."""


def _citation(name: str, *, owner_answer_id: str | None = None) -> dict[str, Any]:
    digest = (name.encode("utf-8").hex() * 64)[:64]
    return {
        "document_name": f"{name}.md",
        "excerpt": f"retained start5 source excerpt for {name}",
        "source_artifact_sha256": digest,
        "source_locator": f"sources/{name}.md",
        "excerpt_sha256": digest,
        "owner_answer_id": owner_answer_id,
    }


def _item_kind(item_id: str) -> str:
    return item_id.split(":", 1)[0]


def _start5_item(item_id: str) -> dict[str, Any]:
    kind = _item_kind(item_id)
    semantic: dict[str, Any] = {"label": item_id}
    if kind == "property":
        semantic.update({"domain": "Workflow", "range": "string", "cardinality": "exactly 1"})
    elif kind == "relation":
        semantic.update({"from": "Workflow", "to": "Workflow"})
    elif kind == "shape":
        semantic.update(
            {
                "target": "WorkflowVersion" if item_id.endswith("WorkflowVersion") else "ExplicitUnknown",
                "rules": ["kind exactly explicit_unknown", "exactly one affectedSubject", "no answer value"],
            }
        )
    elif kind == "entity":
        semantic.update({"types": ["Workflow"], "values": {"label": item_id}})
    elif kind == "assertion":
        semantic.update({"subject": "workflow:B", "predicate": "invokesAsPublishedTool", "object": "workflow:C"})
    return {"item_id": item_id, "item_kind": kind, "semantic": semantic}


def _start5_revision_five() -> dict[str, Any]:
    items = [_start5_item(item_id) for item_id in _START5_ITEM_IDS]
    for item in items:
        if item["item_id"] == "shape:WorkflowVersion":
            item["semantic"]["rules"] = [
                "exactly one versionLabel",
                "exactly one publicationStatus",
                "exactly one hasOutputContract",
            ]
        elif item["item_id"] == "shape:ExplicitUnknown":
            item["semantic"]["rules"] = [
                "kind exactly explicit_unknown",
                "affectedSubject exactly one UnknownAffectedSubject",
                "exactly one unknownQuestion",
                "exactly one rationale",
                "no answer value",
            ]
    return {
        "candidate_kind": "platform-neutral-candidate-v3",
        "candidate_revision": "start5-r5",
        "scope": "single bounded C -> B -> A modeling slice",
        "constraints": copy.deepcopy(_START5_CONSTRAINTS),
        "items": items,
    }


def _start5_partial_revision() -> dict[str, Any]:
    full = _start5_revision_five()
    shape = copy.deepcopy(next(item for item in full["items"] if item["item_id"] == "shape:ExplicitUnknown"))
    shape["semantic"]["rules"].remove("no answer value")
    return {
        "candidate_kind": full["candidate_kind"],
        "candidate_revision": "start5-r6",
        "scope": full["scope"],
        "constraints": copy.deepcopy(full["constraints"]),
        "items": [shape],
    }


def _assert_complete_candidate(candidate: dict[str, Any]) -> None:
    required = {
        "candidate_kind",
        "candidate_revision",
        "scope",
        "constraints",
        "items",
    }
    patch_fields = {"revision_basis", "revision_operation", "replace_item_id"}
    missing = required - set(candidate)
    if missing or patch_fields.intersection(candidate):
        detail = f"missing={sorted(missing)}" if missing else "patch-only metadata"
        raise CandidateRevisionContractError(
            f"candidate revision is not a complete, self-contained candidate ({detail})"
        )
    items = candidate["items"]
    if not isinstance(items, list) or len(items) != len(_START5_ITEM_IDS):
        raise CandidateRevisionContractError("complete candidate must carry all retained items")
    item_ids = [item.get("item_id") for item in items if isinstance(item, dict)]
    if item_ids != list(_START5_ITEM_IDS):
        raise CandidateRevisionContractError("complete candidate item inventory drifted")
    if not isinstance(candidate["constraints"], list) or not candidate["constraints"]:
        raise CandidateRevisionContractError("complete candidate constraints are missing")
    for item in items:
        if set(item) != {"item_id", "item_kind", "semantic"}:
            raise CandidateRevisionContractError("candidate item fields are not exact")
        if "evidence_citations" in item["semantic"]:
            raise CandidateRevisionContractError("candidate source-tracing fields are not accepted")


def _protocol_candidate_reply(candidate: dict[str, Any], calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Model the Protocol order: receipt builder first, complete-candidate gate second."""

    calls.append(copy.deepcopy(candidate))
    receipt = build_candidate_receipt(candidate)
    try:
        _assert_complete_candidate(candidate)
    except CandidateRevisionContractError as exc:
        return {"status": "conflict", "reason": str(exc), "receipt_probe": receipt}
    return receipt


class R23005CompleteRevisionTests(unittest.TestCase):
    def test_c94_complete_revision_contract_is_projected_to_modeling_and_task(self) -> None:
        root = repository_root()
        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)
        modeling_text = runner._task_text("modeling")
        task_objective = configuration.task.objective
        for text in (modeling_text, task_objective):
            self.assertIn("complete, self-contained", text)
            self.assertIn("unchanged items", text)
            self.assertIn("constraints", text)
            self.assertIn("patch-only", text)
        self.assertIn("revision_basis", modeling_text)
        self.assertIn("revision_operation", task_objective)
        self.assertIn("replace_item_id", task_objective)
        self.assertNotIn("expected_matrix_binding", task_objective)

    def test_c95_protocol_never_merges_history_and_builds_each_current_receipt(self) -> None:
        root = repository_root()
        protocol_instructions = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "Candidate history is not Protocol state",
            "Never merge, reconstruct, or mutate a candidate across",
            "Before every receipt or conflict response",
            "entire current candidate as its sole argument",
            "Complete the full platform-translation decision before any",
            "send exactly one of `receipt_json` or `conflict_json`, never both",
            "revision_basis",
            "replace_item_id",
            "Every explicit semantic resource/entity ID supplied by the candidate",
            "Copy each",
            "byte-for-byte into the corresponding platform item translation",
            "never shorten, normalize, replace, or alias it",
            "c-version-1",
            "quality-score-field",
            "unknown-cross-release-output-meaning",
            "return a concrete",
            "candidate-to-Batch translation conflict through the typed or native conflict builder",
            "Before the first query, use only the exact `resource_types` values advertised by the",
            "`query_semantic_context` contract: `concept`, `instance`, `relation`, `fact`, `rule`, `operation`,",
            "`mapping`, and `metric`",
            "Never probe unsupported aliases such as `entity`, `entities`, or `individual`",
            "Read the entire consumer question and its required",
            "response before freezing the first request",
            "relation topology together with literal facts requires the single tuple `relation` plus `fact`",
            "choose one complete, immutable tuple containing every required supported kind",
            "relation-only tuple",
            "return a concrete pre-query",
            "do not issue a probe or a partial query",
        ):
            self.assertIn(phrase, protocol_instructions)
        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        task_objective = configuration.task.objective
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)
        protocol_text = runner._task_text("protocol")
        self.assertIn("Protocol never merges prior deliveries", protocol_text)
        self.assertIn("build_candidate_receipt", protocol_text)
        self.assertIn("before every receipt or conflict response", protocol_text)
        self.assertIn("Complete the full platform-translation decision before any response", protocol_text)
        self.assertIn("exactly one of those two responses", protocol_text)
        for phrase in (
            "`consumer_query.semantic.required_paths`",
            "one independent `query_semantic_context` chain",
            "`query` is exactly the required-path string",
            "typed ordinary retrieval receipt",
        ):
            self.assertIn(phrase, task_objective)
        self.assertIn("accepted candidate's consumer_query", protocol_text)
        self.assertIn("query exactly equal to that path", protocol_text)
        self.assertIn("host artifact gate validates", protocol_text)

    def test_protocol_smoke_shortcut_requires_explicit_declaration_and_formal_full_run(self) -> None:
        root = repository_root()
        protocol_instructions = (
            root / "modeling_team/agent-packages/protocol/instructions.md"
        ).read_text(encoding="utf-8")
        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        protocol_words = " ".join(protocol_instructions.split())

        self.assertEqual(configuration.task.task_id, "r2-3-005-formal-acceptance")
        self.assertNotIn("capability smoke", configuration.task.objective.lower())
        for phrase in (
            "only when the loaded Task/Profile explicitly declares a capability smoke run",
            "Never infer that designation",
            "from a candidate receipt",
            "For formal R2.3-005 (`task_id=r2-3-005-formal-acceptance`)",
            "the capability smoke shortcut is forbidden",
            "a candidate receipt or a health/read-only result is intermediate execution state, never",
            "Execute all three current-run stages (dry-run, apply, readback)",
            "complete governed retrieval",
            "publish the acceptance-stage handoff to Coordinator",
            "send the bound gate-complete notice to Modeling",
            "then send `silent_for_acceptance`",
            "do not call `mcp__team_transport__report_task_result` until the Runner delivers the explicit Protocol `terminal-handoff`",
            "This smoke-only path never applies to formal R2.3-005",
        ):
            self.assertIn(phrase, protocol_words)

    def test_c95_modeling_waits_for_bound_protocol_gates_and_coordinator_uses_exact_pause_shape(self) -> None:
        root = repository_root()
        modeling_instructions = (
            root / "modeling_team/agent-packages/modeling/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "elapsed time, repeated wait/poll",
            "absence of a final result alone is not `runtime_recovery`",
            "explicit tool/Runtime error",
            "Never resend or rebuild the retained",
        ):
            self.assertIn(phrase, modeling_instructions)
        coordinator_instructions = (
            root / "modeling_team/agent-packages/coordinator/instructions.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "argument object must contain exactly",
            "`action`, `issue_id`, `reporter_id`, and `control_epoch`",
            "do not include `reason`",
            "retry that same pause once",
            "do not claim that the Runner resolved the issue",
            "Preserve the exact resolution guidance or repair fields",
            "Runner's `self_resumed` path records the bound control as dispatched",
            "without sending you a second Runtime message",
            "the Runner sends the control to that reporter's thread",
        ):
            self.assertIn(phrase, coordinator_instructions)

    def test_coordinator_task_text_injects_requirement_owned_frozen_question_ids(self) -> None:
        root = repository_root()
        configuration = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        runner = TeamRunner(repository_root=root, adapter=SimpleNamespace())
        runner.run = SimpleNamespace(configuration=configuration, protocol_context=None)
        coordinator = runner._task_text("coordinator")
        self.assertIn("the exact two IDs are `cq-001`, `cq-002`", coordinator)
        self.assertIn("Never guess an abbreviated ID such as `cq-1`", coordinator)
        self.assertIn("derive an ID from Protocol", coordinator)

    def test_c96_retained_partial_revision_is_rejected_without_cross_delivery_merge(self) -> None:
        partial = _start5_partial_revision()
        before = copy.deepcopy(partial)
        calls: list[dict[str, Any]] = []
        response = _protocol_candidate_reply(partial, calls)
        self.assertEqual(response["status"], "conflict")
        self.assertIn("complete candidate", response["reason"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], before)
        self.assertEqual(partial, before)
        self.assertEqual([item["item_id"] for item in partial["items"]], ["shape:ExplicitUnknown"])
        self.assertNotIn("class:Workflow", {item["item_id"] for item in partial["items"]})
        self.assertEqual(response["receipt_probe"]["candidate_revision"], "start5-r6")

    def test_c97_retained_complete_correction_reaches_ordinary_neutral_receipt(self) -> None:
        revision_five = _start5_revision_five()
        corrected = copy.deepcopy(revision_five)
        corrected["candidate_revision"] = "start5-r6"
        shape = next(item for item in corrected["items"] if item["item_id"] == "shape:ExplicitUnknown")
        shape["semantic"]["rules"].remove("no answer value")
        calls: list[dict[str, Any]] = []
        response = _protocol_candidate_reply(corrected, calls)
        self.assertEqual(response["status"], "accepted")
        self.assertEqual(response["candidate_revision"], "start5-r6")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0]["items"]), 38)
        self.assertEqual(calls[0]["constraints"], revision_five["constraints"])
        self.assertTrue(all("evidence_citations" not in item for item in calls[0]["items"]))
        self.assertEqual(response, build_candidate_receipt(corrected))

    def test_c98_proof_bound_002_and_neutral_005_boundaries_remain_distinct(self) -> None:
        root = repository_root()
        proof = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-002-t.yaml",
            root / "modeling_team/tasks/r2-3-002-t.yaml",
            root=root,
        )
        neutral = load_formal_team_configuration(
            root / "modeling_team/profiles/r2-3-005-modeling-team.yaml",
            root / "modeling_team/tasks/r2-3-005-formal-acceptance.yaml",
            root=root,
        )
        self.assertIsNotNone(proof.profile.expected_matrix_binding)
        self.assertIsNotNone(proof.task.expected_matrix_binding)
        self.assertIsNone(neutral.profile.expected_matrix_binding)
        self.assertIsNone(neutral.task.expected_matrix_binding)
        self.assertIn("native v2 retrieval verifier", proof.task.objective)
        self.assertIn("frozen 48-row assertion matrix IDs", proof.task.objective)
        self.assertNotIn("native v2 retrieval verifier", neutral.task.objective)
        self.assertNotIn("assertion matrix", neutral.task.objective)

        retained = json.loads(
            (root / "modeling_team/references/r2-3-002-retained-rev7-handoff.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(retained["candidate_revision"], "7")
        self.assertEqual(len(retained["required_semantic_items"]), 48)
        self.assertNotIn("revision_basis", retained)
        self.assertNotIn("revision_operation", retained)
        self.assertNotIn("replace_item_id", retained)


if __name__ == "__main__":
    unittest.main()
