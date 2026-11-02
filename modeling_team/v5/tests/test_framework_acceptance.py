"""Report mechanics may reject a false PASS, but never assign the semantic verdict."""

import hashlib
import json

import pytest

from ontoweave_modeling.acceptance import validate_report
from ontoweave_modeling.contracts import FrameworkError


@pytest.fixture
def frozen_report(tmp_path):
    handoff = {
        "target": {"model_revisions": {"ontology": 3}},
        "evaluation": {"freeze_id": "freeze", "sha256": "a" * 64, "case_count": 1},
        "source_revisions": {"source": "b" * 64},
    }
    report = {
        "verdict": "PASS",
        "freeze_id": "freeze",
        "model_revisions": {"ontology": 3},
        "cases": [
            {
                "index": 1,
                "passed": True,
                "actual_answer": "Actual governed answer",
                "reason": "Independently assessed",
                "evidence_iris": ["urn:actual:resource"],
            }
        ],
    }
    events = []
    for material_id, sha in [("frozen-questions", "a" * 64), ("source", "b" * 64)]:
        events.append(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "tool": "read_material",
                        "status": "completed",
                        "arguments": {"material_id": material_id},
                        "result": {
                            "structuredContent": {
                                "text": "authorized content",
                                "sha256": sha,
                                "offset": 0,
                                "next_offset": None,
                                "total_characters": 18,
                            }
                        },
                    }
                },
            }
        )
    events.append(
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "tool": "query_semantic_context",
                    "status": "completed",
                    "result": {
                        "structuredContent": {
                            "ok": True,
                            "scope": {
                                "ontologies": [{"ontology_id": "ontology", "model_revision": 3}]
                            },
                        }
                    },
                }
            },
        }
    )
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(map(json.dumps, events)))
    return report, handoff, path, events


def test_valid_report_public_projection_contains_no_hidden_answers(frozen_report):
    report, handoff, path, _ = frozen_report
    public = validate_report(report, handoff, path)
    assert public["verdict"] == "PASS" and public["total"] == 1
    assert "actual_answer" not in json.dumps(public) and "reason" not in json.dumps(public)


def test_pass_does_not_accept_a_hash_matching_source_with_an_unread_tail(frozen_report):
    report, handoff, path, events = frozen_report
    data = events[1]["params"]["item"]["result"]["structuredContent"]
    data.update(text="auth", next_offset=4)
    path.write_text("\n".join(map(json.dumps, events)))
    with pytest.raises(FrameworkError, match="evaluation_read_coverage_incomplete") as caught:
        validate_report(report, handoff, path)
    assert caught.value.detail["coverage"]["materials"][0]["material_id"] == "source"
    assert caught.value.detail["coverage"]["materials"][0]["missing_ranges"] == [[4, 18]]


def test_read_ranges_can_overlap_and_arrive_out_of_order_without_losing_coverage(frozen_report):
    report, handoff, path, events = frozen_report
    first = events[1]["params"]["item"]["result"]["structuredContent"]
    first.update(text="authorized", next_offset=10)
    later = json.loads(json.dumps(events[1]))
    later["params"]["item"]["result"]["structuredContent"].update(
        offset=8, text="ed content", next_offset=None
    )
    events.insert(1, later)
    path.write_text("\n".join(map(json.dumps, events)))
    public = validate_report(report, handoff, path)
    assert public["read_coverage"]["complete"] is True


def test_partial_report_keeps_unread_source_visible_instead_of_killing_the_run(frozen_report):
    report, handoff, path, events = frozen_report
    report["verdict"] = "PARTIAL"
    report["cases"][0]["passed"] = False
    events[1]["params"]["item"]["result"]["structuredContent"].update(text="auth", next_offset=4)
    path.write_text("\n".join(map(json.dumps, events)))
    public = validate_report(report, handoff, path)
    assert public["verdict"] == "PARTIAL"
    assert public["read_coverage"]["complete"] is False
    assert public["read_coverage"]["unread_materials"] == 1


def test_a_complete_relation_graph_cannot_replace_the_definition_body(frozen_report):
    report, handoff, path, events = frozen_report
    handoff["target"]["resource_bindings"] = {
        "resource": {"ontology_id": "ontology", "resource_iri": "urn:actual:resource"}
    }
    events.append(
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "tool": "read_model_resource",
                    "status": "completed",
                    "arguments": {"ontology_id": "ontology", "family": "resource-relations"},
                    "result": {
                        "structuredContent": {
                            "ontology_id": "ontology",
                            "model_revision": 3,
                            "paging": {"complete": True},
                            "items": [
                                {
                                    "source": "urn:actual:resource",
                                    "relation": "urn:predicate",
                                    "target": "urn:other",
                                }
                            ],
                        }
                    },
                }
            },
        }
    )
    path.write_text("\n".join(map(json.dumps, events)))
    with pytest.raises(FrameworkError, match="evaluation_read_coverage_incomplete") as caught:
        validate_report(report, handoff, path)
    assert caught.value.detail["coverage"]["models"][0]["unread_resources"] == [
        "urn:actual:resource"
    ]


@pytest.mark.parametrize("projection", ["detail", "query-resource", "query-fact"])
def test_cited_definition_can_come_from_each_actual_governed_projection(frozen_report, projection):
    report, handoff, path, events = frozen_report
    handoff["target"]["resource_bindings"] = {
        "resource": {"ontology_id": "ontology", "resource_iri": "urn:actual:resource"}
    }
    meaning = {"business_meaning": "Actually returned definition"}
    query = events[-1]["params"]["item"]["result"]["structuredContent"]
    if projection == "detail":
        events.append(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "tool": "read_model_resource",
                        "status": "completed",
                        "arguments": {"ontology_id": "ontology", "family": "entity-detail"},
                        "result": {
                            "structuredContent": {
                                "ontology_id": "ontology",
                                "model_revision": 3,
                                "items": [
                                    {
                                        "iri": "urn:actual:resource",
                                        "detail_fields": {
                                            "semantic_definition": meaning,
                                        },
                                    }
                                ],
                            }
                        },
                    }
                },
            }
        )
    elif projection == "query-resource":
        query["related_context"] = [
            {
                "iri": "urn:actual:resource",
                "ontology_id": "ontology",
                "data": {"semantic_definition": meaning},
            }
        ]
    else:
        query["primary_matches"] = [
            {
                "ontology_id": "ontology",
                "data": {
                    "subject": "urn:actual:resource",
                    "predicate": "http://ontology-platform.local/semantic/vocab/semanticDefinition",
                    "object": json.dumps(meaning),
                },
            }
        ]
    path.write_text("\n".join(map(json.dumps, events)))
    assert validate_report(report, handoff, path)["read_coverage"]["complete"] is True


def test_whole_model_checks_unfiltered_inventory_and_all_returned_definitions(frozen_report):
    report, handoff, path, events = frozen_report
    handoff["evaluation"]["model_read_scope"] = "whole_model"
    inventory = {
        "method": "item/completed",
        "params": {
            "item": {
                "tool": "read_model_resource",
                "status": "completed",
                "arguments": {"ontology_id": "ontology", "family": "resource-list"},
                "result": {
                    "structuredContent": {
                        "ontology_id": "ontology",
                        "model_revision": 3,
                        "paging": {"complete": True},
                        "items": [
                            {"iri": "urn:actual:resource", "detail_fields": {}},
                            {"iri": "urn:other"},
                        ],
                    }
                },
            }
        },
    }
    graph = json.loads(json.dumps(inventory))
    graph["params"]["item"]["arguments"]["family"] = "resource-relations"
    graph["params"]["item"]["result"]["structuredContent"]["items"] = []
    events.extend([inventory, graph])
    path.write_text("\n".join(map(json.dumps, events)))
    with pytest.raises(FrameworkError, match="evaluation_read_coverage_incomplete") as caught:
        validate_report(report, handoff, path)
    assert caught.value.detail["coverage"]["models"][0]["unread_resources"] == ["urn:other"]

    inventory["params"]["item"]["result"]["structuredContent"]["items"][1]["detail_fields"] = {}
    path.write_text("\n".join(map(json.dumps, events)))
    assert validate_report(report, handoff, path)["read_coverage"]["complete"]

    inventory["params"]["item"]["arguments"]["resource_iri"] = "urn:actual:resource"
    path.write_text("\n".join(map(json.dumps, events)))
    with pytest.raises(FrameworkError, match="evaluation_read_coverage_incomplete") as caught:
        validate_report(report, handoff, path)
    assert caught.value.detail["coverage"]["models"][0]["missing_inventory"] is True


def test_standard_report_does_not_accept_invented_custom_cq_metadata(frozen_report):
    report, handoff, path, _ = frozen_report
    report["cases"][0].update(cq_id="invented-id", answerability="supported")
    with pytest.raises(FrameworkError):
        validate_report(report, handoff, path)


def test_actual_rest_governed_response_needs_no_synthetic_ok_field(frozen_report):
    report, handoff, path, events = frozen_report
    data = events[-1]["params"]["item"]["result"]["structuredContent"]
    data.pop("ok")
    data["result_status"] = "complete"
    path.write_text("\n".join(map(json.dumps, events)))
    assert validate_report(report, handoff, path)["verdict"] == "PASS"


@pytest.mark.parametrize("read_all", [False, True])
def test_exact_governed_reads_cover_each_frozen_ontology(frozen_report, read_all):
    report, handoff, path, events = frozen_report
    handoff["target"]["model_revisions"]["other"] = 7
    report["model_revisions"] = dict(handoff["target"]["model_revisions"])
    events.pop()
    for ontology, revision in [("ontology", 3), *([("other", 7)] if read_all else [])]:
        events.append(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "tool": "read_model_resource",
                        "status": "completed",
                        "arguments": {
                            "ontology_id": ontology,
                            "resource_iri": "urn:actual:resource",
                        },
                        "result": {"structuredContent": {"model_revision": revision, "items": []}},
                    }
                },
            }
        )
    path.write_text("\n".join(map(json.dumps, events)))
    if read_all:
        assert validate_report(report, handoff, path)["verdict"] == "PASS"
    else:
        with pytest.raises(FrameworkError, match="actual_governed_read_missing"):
            validate_report(report, handoff, path)


def test_required_human_dialogue_must_be_actually_read(frozen_report):
    report, handoff, path, events = frozen_report
    with pytest.raises(FrameworkError, match="evaluation_human_source_not_read"):
        validate_report(report, handoff, path, required_materials={"human-inputs": "c" * 64})
    events.append(
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "tool": "read_material",
                    "status": "completed",
                    "arguments": {"material_id": "human-inputs"},
                    "result": {
                        "structuredContent": {
                            "text": "Attributed approved reply",
                            "sha256": "c" * 64,
                            "offset": 0,
                            "next_offset": None,
                            "total_characters": len("Attributed approved reply"),
                        }
                    },
                }
            },
        }
    )
    path.write_text("\n".join(map(json.dumps, events)))
    assert (
        validate_report(report, handoff, path, required_materials={"human-inputs": "c" * 64})[
            "verdict"
        ]
        == "PASS"
    )


@pytest.mark.parametrize(
    "defect", ["missing_case", "wrong_revision", "failed_case", "wrong_freeze"]
)
def test_false_binding_or_coverage_does_not_publish_pass(frozen_report, defect):
    report, handoff, path, _ = frozen_report
    if defect == "missing_case":
        report["cases"] = []
    elif defect == "wrong_revision":
        report["model_revisions"] = {"ontology": 4}
    elif defect == "failed_case":
        report["cases"][0]["passed"] = False
    else:
        report["freeze_id"] = "different-freeze"
    with pytest.raises(FrameworkError):
        validate_report(report, handoff, path)


@pytest.mark.parametrize(
    "defect", ["tool_error", "wrong_revision", "failed_envelope", "missing_source"]
)
def test_tool_completion_is_not_successful_governed_or_source_read(frozen_report, defect):
    report, handoff, path, events = frozen_report
    item = events[-1]["params"]["item"]
    if defect == "tool_error":
        item["error"] = {"message": "Forbidden"}
    elif defect == "wrong_revision":
        item["result"]["structuredContent"]["scope"]["ontologies"][0]["model_revision"] = 4
    elif defect == "failed_envelope":
        item["result"]["structuredContent"]["ok"] = False
    else:
        events.pop(1)
    path.write_text("\n".join(map(json.dumps, events)))
    with pytest.raises(FrameworkError):
        validate_report(report, handoff, path)


@pytest.mark.parametrize("bounded_scope", [False, True])
@pytest.mark.parametrize("first_failure", ["format", "source_read"])
@pytest.mark.parametrize("same_native_context", [False, True])
def test_evaluation_format_retry_preserves_freeze_and_does_not_advance_production(
    task_file,
    tmp_path,
    workspace,
    monkeypatch,
    bounded_scope,
    first_failure,
    same_native_context,
):
    from ontoweave_modeling import cli
    from ontoweave_modeling.contracts import TaskBinding, write_json
    from ontoweave_modeling.control import TaskControl

    questions = b'{"cases":["first", "second"]}'
    question_sha = hashlib.sha256(questions).hexdigest()
    task = json.loads(task_file.read_text())
    task["evaluation"]["sha256"] = question_sha
    task_file.write_text(json.dumps(task))
    binding = TaskBinding.prepare(task_file, tmp_path / "run")
    scope = None
    selected_evaluation = binding.data["evaluation"]
    if bounded_scope:
        questions = b'{"cases":["bounded first", "bounded second"]}'
        question_sha = hashlib.sha256(questions).hexdigest()
        selected_evaluation = {
            **selected_evaluation,
            "freeze_id": "bounded-freeze",
            "sha256": question_sha,
        }
        scope = {
            "scope_id": "direct-child",
            "base_freeze_id": binding.data["evaluation"]["freeze_id"],
            "source_ids": ["source"],
            "evaluation": selected_evaluation,
        }
    source = binding.data["source_manifest"]["source"]
    handoff = {
        "target": {"model_revisions": {"ontology": 3}},
        "evaluation": binding.data["evaluation"],
        "source_revisions": {"source": source["sha256"]},
        "human_context": {
            "requests": [
                {"request_id": "question", "question": "Which meaning?", "basis_ref": None}
            ],
            "answers": [
                {
                    "message_id": "human-answer",
                    "body": "Approved meaning from a user",
                    "metadata": {"source": "user", "author": "test-user", "partial": False},
                },
                {
                    "message_id": "host-private",
                    "body": "Private technical input",
                    "metadata": {"source": "host"},
                },
            ],
        },
    }
    ref = workspace.put_reference(binding.identity + ":handoff", "handoff", handoff, 0)
    work = {"status": "handoff_ready", "handoff_ref": ref}
    workspace.put_reference(binding.identity + ":work", "work_unit", work, 0)
    package = tmp_path / "independent-inputs"
    package.mkdir()
    (package / "source.md").write_bytes((binding.root / "materials/source.md").read_bytes())
    (package / "questions.json").write_bytes(questions)
    write_json(
        package / "manifest.json",
        {
            "source": source,
            "frozen-questions": {
                "path": "questions.json",
                "source_ref": "independent-freeze",
                "sha256": question_sha,
            },
        },
    )
    calls = []

    class IndependentActor:
        def __init__(self, binding, bridge, **kwargs):
            assert kwargs["materials"] != binding.root / "materials"
            assert kwargs["model_revisions"] == {"ontology": 3}
            assert "endpoints" in kwargs["instructions"]
            assert "definition text" in kwargs["instructions"]
            assert "every required_artifacts entry" in kwargs["instructions"]
            assert "distinct resource IRIs" in kwargs["instructions"]
            assert "same incident" in kwargs["instructions"]
            assert "relation IRI" in kwargs["instructions"]
            assert "source, predicate and target" in kwargs["instructions"]
            assert "all relevant actual resources" in kwargs["instructions"]
            assert "only the required per-case fields" in kwargs["instructions"]
            self.materials = kwargs["materials"]
            self.resume_from = kwargs.get("resume_from")

        def __call__(self, root, purpose, prompt, inputs):
            calls.append(root.name)
            assert purpose == "acceptance" and not inputs
            assert json.loads(prompt)["source_ids"] == ["source", "human-inputs"]
            assert set(
                json.loads(prompt)["result_schema"]["properties"]["cases"]["items"]["properties"]
            ) == {"index", "passed", "actual_answer", "reason", "evidence_iris"}
            if len(calls) == 1:
                assert self.resume_from is None
            else:
                assert self.resume_from == binding.root / "executions" / calls[0] / "agent"
            if first_failure == "source_read" and len(calls) == 2:
                parsed = json.loads(prompt)
                assert parsed["source_ids"] == ["source", "human-inputs"]
                assert parsed["contract_feedback"]["material_id"] == "source"
            folder = root / "agent"
            folder.mkdir()
            events = []
            human_material = json.loads((self.materials / "human-inputs.json").read_text())
            assert len(human_material["answers"]) == 1
            assert human_material["answers"][0]["metadata"]["author"] == "test-user"
            human_sha = json.loads((self.materials / "manifest.json").read_text())["human-inputs"][
                "sha256"
            ]
            for material_id, sha in [
                ("source", source["sha256"]),
                ("frozen-questions", question_sha),
                ("human-inputs", human_sha),
            ]:
                if len(calls) == 2 and (first_failure == "format" or material_id != "source"):
                    continue
                if first_failure == "source_read" and len(calls) == 1 and material_id == "source":
                    continue
                manifest = json.loads((self.materials / "manifest.json").read_text())
                text = (self.materials / manifest[material_id]["path"]).read_text()
                events.append(
                    {
                        "method": "item/completed",
                        "params": {
                            "item": {
                                "tool": "read_material",
                                "status": "completed",
                                "arguments": {"material_id": material_id},
                                "result": {
                                    "structuredContent": {
                                        "text": text,
                                        "sha256": sha,
                                        "offset": 0,
                                        "next_offset": None,
                                        "total_characters": len(text),
                                    }
                                },
                            }
                        },
                    }
                )
            events.append(
                {
                    "method": "item/completed",
                    "params": {
                        "item": {
                            "tool": "query_semantic_context",
                            "status": "completed",
                            "result": {
                                "structuredContent": {
                                    "ok": True,
                                    "scope": {
                                        "ontologies": [
                                            {"ontology_id": "ontology", "model_revision": 3}
                                        ]
                                    },
                                }
                            },
                        }
                    },
                }
            )
            (folder / "events.jsonl").write_text("\n".join(map(json.dumps, events)))
            report = {
                "verdict": "PASS",
                "freeze_id": selected_evaluation["freeze_id"],
                "model_revisions": {"ontology": 3},
                "cases": [
                    {
                        "index": index,
                        "passed": True,
                        "actual_answer": "Test answer",
                        "reason": "Test-only judgment",
                        "evidence_iris": ["urn:test"],
                    }
                    for index in (1, 2)
                ],
            }
            return {
                "status": "completed",
                "thread_id": "independent-reader-thread"
                if len(calls) == 1 or same_native_context
                else "different-reader-thread",
                "turn_id": "turn-" + str(len(calls)),
                "final_response": "bad JSON"
                if len(calls) == 1 and first_failure == "format"
                else json.dumps(report),
            }

    class Platform:
        def call(self, action):
            assert action == "snapshot"
            return {"model_revisions": {"ontology": 3}}

    monkeypatch.setattr(cli, "CodexInvocation", IndependentActor)
    TaskControl(workspace).enqueue("production-input", "input", "Pending production correction")
    with pytest.raises(FrameworkError, match="evaluation_report_needs_correction"):
        cli.evaluate(binding, workspace, Platform(), package, "evaluation-1", scope=scope)
    if not same_native_context:
        with pytest.raises(FrameworkError, match="evaluation_correction_context_changed"):
            cli.evaluate(binding, workspace, Platform(), package, "evaluation-1", scope=scope)
        assert not (binding.root / "evaluations/evaluation-1/private-report.json").exists()
        assert workspace.get(binding.identity + ":work")["content"] == work
        assert not TaskControl(workspace).view()["active"]
        return
    assert (
        cli.evaluate(binding, workspace, Platform(), package, "evaluation-1", scope=scope)[
            "verdict"
        ]
        == "PASS"
    )
    public = cli.evaluate(binding, workspace, Platform(), package, "evaluation-1", scope=scope)
    if bounded_scope:
        assert public["evaluation_scope"]["scope_id"] == "direct-child"
        assert workspace.read_reference(ref)["evaluation"] == binding.data["evaluation"]
    assert len(calls) == 2 and calls[0] != calls[1]
    assert workspace.get(binding.identity + ":work")["content"] == work
    control = TaskControl(workspace).view()
    assert not control["active"] and control["messages"][0]["status"] == "queued"
