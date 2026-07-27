from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from app.services.modeling_handlers import ALLOWED_FIELDS


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

import m4_clarification_responder as responder  # noqa: E402
import m4_api_file_spool_gateway as api_gateway  # noqa: E402
import m4_semantic_audit as semantic  # noqa: E402
import run_m4_clarification as launcher  # noqa: E402
import run_m4_readonly_consumer as consumer  # noqa: E402


def request(request_id: str, terms: list[str], question: str, impact: str) -> bytes:
    return responder.canonical_json(
        {
            "affected_terms": terms,
            "business_impact": impact,
            "id": request_id,
            "question": question,
        }
    )


def make_responder(root: Path, variant: str = "baseline") -> tuple[responder.ClarificationResponder, Path, Path, Path]:
    requests = root / "requests"
    responses = root / "responses"
    audit = root / "audit.jsonl"
    instance = responder.ClarificationResponder(
        requests=requests,
        responses=responses,
        audit_path=audit,
        hidden_contract=responder.default_hidden_contract(variant),
    )
    return instance, requests, responses, audit


def test_eligible_request_is_answered_without_disclosing_hidden_protocol_shape(tmp_path: Path) -> None:
    instance, requests, responses, audit = make_responder(tmp_path)
    request_id = "lifecycle-001"
    (requests / f"{request_id}.json").write_bytes(
        request(
            request_id,
            ["B", "C", "version", "invocation"],
            "Which published C version does B invoke?",
            "The current target determines B's visible output contract.",
        )
    )

    assert instance.process_once() == 1
    raw_response = (responses / f"{request_id}.json").read_bytes()
    response_value = json.loads(raw_response)
    assert response_value == {
        "answer": "B invokes C through C's Latest published Version.",
        "id": request_id,
        "status": "answered",
    }
    assert oct((responses / f"{request_id}.json").stat().st_mode & 0o777) == "0o400"
    audit_value = json.loads(audit.read_text(encoding="utf-8").strip())
    assert audit_value["status"] == "answered"
    assert audit_value["response_sha256"] == hashlib.sha256(raw_response).hexdigest()
    assert "answer" not in audit_value
    assert "category" not in raw_response.decode("utf-8")

    # The completed first request stays in the spool but does not block the next serial request.
    second_id = "missing-0001"
    (requests / f"{second_id}.json").write_bytes(
        request(
            second_id,
            ["score", "missing", "fallback"],
            "Can the owner confirm missing-score handling?",
            "A fallback would change the consumer conclusion.",
        )
    )
    assert instance.process_once() == 1
    assert json.loads((responses / f"{second_id}.json").read_bytes())["status"] == "uncertain"


def test_noncanonical_or_malformed_requests_fail_closed(tmp_path: Path) -> None:
    instance, requests, responses, audit = make_responder(tmp_path)
    request_id = "malformed-001"
    # Valid JSON but deliberately non-canonical order/whitespace must not become a semantic answer.
    (requests / f"{request_id}.json").write_text(
        json.dumps(
            {
                "id": request_id,
                "affected_terms": ["B"],
                "question": "x",
                "business_impact": "x",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    assert instance.process_once() == 0
    assert not list(responses.iterdir())
    event = json.loads(audit.read_text(encoding="utf-8").strip())
    assert event["policy"] == "rejected"
    assert event["reason"] == "request is not canonical JSON"


@pytest.mark.parametrize("terminator", [b"\n", b"\r\n"])
def test_clarification_spool_accepts_only_one_final_transport_line_ending(terminator: bytes) -> None:
    request_id = "clarify-001"
    canonical = request(
        request_id,
        ["B", "C"],
        "Does B follow C's latest release or an earlier published release?",
        "The selected target changes B's current output.",
    )
    parsed, normalized = responder.parse_request(canonical + terminator, f"{request_id}.json")
    assert parsed["id"] == request_id
    assert normalized == canonical


def test_clarification_parser_normalizes_direct_utf8_and_ascii_escaped_unicode(tmp_path: Path) -> None:
    request_id = "unicode-001"
    value = {
        "affected_terms": ["B", "C", "version", "invocation"],
        "business_impact": "C’s published target changes B’s visible output contract.",
        "id": request_id,
        "question": "Which published C version does B invoke?",
    }
    direct_utf8 = responder.canonical_json(value)
    escaped_ascii = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")

    direct_value, direct_canonical = responder.parse_request(direct_utf8, f"{request_id}.json")
    escaped_value, escaped_canonical = responder.parse_request(escaped_ascii, f"{request_id}.json")

    assert direct_utf8 != escaped_ascii
    assert hashlib.sha256(direct_utf8).hexdigest() != hashlib.sha256(escaped_ascii).hexdigest()
    assert direct_value == escaped_value == value
    assert direct_canonical == escaped_canonical == direct_utf8
    assert hashlib.sha256(direct_canonical).hexdigest() == hashlib.sha256(escaped_canonical).hexdigest()

    direct_instance, direct_requests, _direct_responses, direct_audit_path = make_responder(
        tmp_path / "direct"
    )
    escaped_instance, escaped_requests, _escaped_responses, escaped_audit_path = make_responder(
        tmp_path / "escaped"
    )
    (direct_requests / f"{request_id}.json").write_bytes(direct_utf8)
    (escaped_requests / f"{request_id}.json").write_bytes(escaped_ascii)
    assert direct_instance.process_once() == 1
    assert escaped_instance.process_once() == 1
    direct_audit = json.loads(direct_audit_path.read_text(encoding="utf-8"))
    escaped_audit = json.loads(escaped_audit_path.read_text(encoding="utf-8"))
    assert direct_audit["raw_request_sha256"] != escaped_audit["raw_request_sha256"]
    assert direct_audit["canonical_request_sha256"] == escaped_audit["canonical_request_sha256"]


@pytest.mark.parametrize(
    "raw",
    [
        b'{"affected_terms":["B"],"business_impact":"x","id":"duplicate-1","id":"duplicate-1","question":"x"}',
        b'{"affected_terms":["B"],"business_impact":"x","id":"malformed-1",',
        b'{"affected_terms":["B"],"business_impact":"x","id":"surrogate-1","question":"\\ud800"}',
    ],
)
def test_clarification_parser_rejects_duplicate_malformed_and_unpaired_surrogate(raw: bytes) -> None:
    with pytest.raises(responder.PolicyError):
        responder.parse_request(raw, "surrogate-1.json")


@pytest.mark.parametrize("suffix", [b"\r", b"\n\n", b"\r\n\n", b" \n", b"\t\n"])
def test_clarification_spool_rejects_other_trailing_or_internal_whitespace(suffix: bytes) -> None:
    request_id = "clarify-002"
    canonical = request(
        request_id,
        ["B", "C"],
        "Does B follow C's latest release or an earlier published release?",
        "The selected target changes B's current output.",
    )
    with pytest.raises(responder.PolicyError, match="canonical JSON"):
        responder.parse_request(canonical + suffix, f"{request_id}.json")
    with pytest.raises(responder.PolicyError, match="canonical JSON"):
        responder.parse_request(
            canonical.replace(b'"affected_terms":[', b'"affected_terms": ['), f"{request_id}.json"
        )


def test_clarification_audit_keeps_raw_and_canonical_request_hashes(tmp_path: Path) -> None:
    instance, requests, _responses, audit_path = make_responder(tmp_path)
    request_id = "clarify-003"
    canonical = request(
        request_id,
        ["B", "C"],
        "Does B follow C's latest release or an earlier published release?",
        "The selected target changes B's current output.",
    )
    raw = canonical + b"\n"
    (requests / f"{request_id}.json").write_bytes(raw)
    assert instance.process_once() == 1
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["raw_request_sha256"] == hashlib.sha256(raw).hexdigest()
    assert audit["canonical_request_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert "question" not in audit


def test_api_spool_rejects_authorization_and_forwards_only_safe_envelope(tmp_path: Path) -> None:
    request_id = "platform-001"
    raw = responder.canonical_json(
        {
            "body": None,
            "headers": {"authorization": "Bearer must-not-pass"},
            "id": request_id,
            "method": "GET",
            "path": "/api/health",
        }
    )
    with pytest.raises(api_gateway.PolicyError, match="allowlist"):
        api_gateway.parse_request(raw, f"{request_id}.json")

    requests = tmp_path / "api-requests"
    responses = tmp_path / "api-responses"
    requests.mkdir()
    canonical_request = responder.canonical_json(
        {"body": None, "headers": {"accept": "application/json"}, "id": request_id, "method": "GET", "path": "/api/health"}
    )
    safe_raw = canonical_request + b"\n"
    (requests / f"{request_id}.json").write_bytes(safe_raw)
    gateway = api_gateway.ApiFileSpoolGateway(
        requests=requests,
        responses=responses,
        audit_path=tmp_path / "api-audit.jsonl",
        api_key="host-only-key",
        upstream=lambda request_value: (200, {"content-type": "application/json", "x-secret": "no"}, {"ok": request_value["path"]}),
    )
    assert gateway.process_once() == 1
    assert json.loads((responses / f"{request_id}.json").read_bytes()) == {
        "body": {"ok": "/api/health"},
        "headers": {"content-type": "application/json"},
        "id": request_id,
        "status": 200,
    }
    audit = json.loads((tmp_path / "api-audit.jsonl").read_text(encoding="utf-8"))
    assert audit["raw_request_sha256"] == hashlib.sha256(safe_raw).hexdigest()
    assert audit["canonical_request_sha256"] == hashlib.sha256(canonical_request).hexdigest()


CONSUMER_SCOPE = {"project_id": "project-1", "ontology_id": "ontology-1", "graph_set_id": "graph-set-1"}


def _consumer_request(request_id: str, path: str) -> bytes:
    return responder.canonical_json(
        {"body": None, "headers": {}, "id": request_id, "method": "GET", "path": path}
    )


def _write_consumer_record_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    record_path = tmp_path / "consumer-record.json"
    audit_path = tmp_path / "api-audit.jsonl"
    receipts: dict[str, object] = {}
    audit_entries: list[dict[str, object]] = []
    for index, slot in enumerate(consumer.CONSUMER_SLOTS, start=1):
        request_id = f"consumer-{index}"
        request_hash = f"{index:064x}"
        response_hash = f"{index + 10:064x}"
        receipts[slot] = {
            "request_id": request_id,
            "canonical_request_sha256": request_hash,
            "response_sha256": response_hash,
        }
        audit_entries.append(
            {
                "policy": "forwarded",
                "method": "GET",
                "path": "/api/ontologies/ontology-1/semantic-read-models/facts",
                "request_id": request_id,
                "canonical_request_sha256": request_hash,
                "response_sha256": response_hash,
                "status": 200,
            }
        )
    record: dict[str, object] = {
        "terminal_status": "CONSUMER_READY",
        "scope": CONSUMER_SCOPE,
        "receipts": receipts,
        "observations": {
            "current_target_contract": {
                "current_target": "C latest published target",
                "target_version": "2.0",
                "b_contract": "B emits the C v2 contract",
            },
            "output_continuity": {
                "old_contract_change": "C v1 exposed one output",
                "new_contract_change": "C v2 changes the output contract",
                "continuity": "B requires a compatibility review",
            },
            "missing_score": {
                "state": "unknown",
                "explicit_gap_observed": True,
                "gap": "No modeled missing-score policy exists",
            },
        },
        "claim_classifications": {
            "current_target_contract": "source",
            "output_continuity": "source",
            "missing_score": "source",
        },
    }
    record_path.write_text(json.dumps(record), encoding="utf-8")
    audit_path.write_text("\n".join(json.dumps(entry) for entry in audit_entries) + "\n", encoding="utf-8")
    return record_path, audit_path, record


def test_consumer_scope_is_verified_and_staged_without_extra_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def backend_get(_key: str, _port: int, path: str) -> object:
        return {
            "/api/projects/project-1": {"id": "project-1"},
            "/api/ontologies/ontology-1": {"id": "ontology-1", "project_id": "project-1"},
            "/api/ontologies/ontology-1/workspace-context": {
                "ontology_id": "ontology-1",
                "default_graph_set_id": "graph-set-1",
            },
        }[path]

    monkeypatch.setattr(consumer, "_backend_get_json", backend_get)
    scope = consumer.verify_consumer_scope("key", 8012, **CONSUMER_SCOPE)
    paths = consumer.consumer_paths(tmp_path / "consumer", scope)

    assert scope == CONSUMER_SCOPE
    assert json.loads((paths["staging"] / "consumer-scope.json").read_text(encoding="utf-8")) == scope
    assert {path.name for path in paths["staging"].iterdir()} == {
        "consumer-prompt.md",
        "consumer-scope.json",
    }
    with pytest.raises(launcher.IsolationError, match="does not match backend"):
        monkeypatch.setattr(
            consumer,
            "_backend_get_json",
            lambda _key, _port, path: {"id": "ontology-1", "project_id": "foreign"}
            if path == "/api/ontologies/ontology-1"
            else backend_get(_key, _port, path),
        )
        consumer.verify_consumer_scope("key", 8012, **CONSUMER_SCOPE)
    with pytest.raises(launcher.IsolationError, match="does not match backend"):
        monkeypatch.setattr(
            consumer,
            "_backend_get_json",
            lambda _key, _port, path: {
                "ontology_id": "ontology-1",
                "default_graph_set_id": "foreign-graph-set",
            }
            if path == "/api/ontologies/ontology-1/workspace-context"
            else backend_get(_key, _port, path),
        )
        consumer.verify_consumer_scope("key", 8012, **CONSUMER_SCOPE)


@pytest.mark.parametrize(
    ("filename", "path"),
    [
        ("Consumer-1.json", "/api/projects/project-1"),
        ("consumer-2.json", "/api/projects"),
        ("consumer-3.json", "/api/ontologies/foreign/semantic-read-models/classes"),
        ("consumer-4.json", "/api/semantic/graph-sets/foreign/read-models/class-topology"),
    ],
)
def test_readonly_consumer_gateway_rejects_invalid_or_out_of_scope_requests_without_forwarding(
    tmp_path: Path, filename: str, path: str
) -> None:
    calls: list[dict[str, object]] = []
    requests = tmp_path / "requests"
    request_id = filename.removesuffix(".json").lower()
    (requests / filename).parent.mkdir()
    (requests / filename).write_bytes(_consumer_request(request_id, path))
    gateway = api_gateway.ApiFileSpoolGateway(
        requests=requests,
        responses=tmp_path / "responses",
        audit_path=tmp_path / "audit.jsonl",
        api_key="host-only-key",
        read_only=True,
        consumer_scope=api_gateway.ConsumerScope(**CONSUMER_SCOPE),
        upstream=lambda request_value: (calls.append(request_value) or (200, {}, {})),
    )

    assert gateway.process_once() == 0
    assert calls == []
    assert json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8"))["policy"] == "rejected"


def test_readonly_consumer_gateway_allows_only_verified_scope_and_normal_gateway_stays_writable(
    tmp_path: Path,
) -> None:
    readonly_calls: list[dict[str, object]] = []
    readonly_requests = tmp_path / "readonly-requests"
    readonly_requests.mkdir()
    (readonly_requests / "consumer-ok.json").write_bytes(
        _consumer_request("consumer-ok", "/api/semantic/graph-sets/graph-set-1/read-models/class-topology")
    )
    readonly_gateway = api_gateway.ApiFileSpoolGateway(
        requests=readonly_requests,
        responses=tmp_path / "readonly-responses",
        audit_path=tmp_path / "readonly-audit.jsonl",
        api_key="host-only-key",
        read_only=True,
        consumer_scope=api_gateway.ConsumerScope(**CONSUMER_SCOPE),
        upstream=lambda request_value: (readonly_calls.append(request_value) or (200, {}, {"ok": True})),
    )
    assert readonly_gateway.process_once() == 1
    assert readonly_calls[0]["path"].endswith("class-topology")

    modeling_calls: list[dict[str, object]] = []
    modeling_requests = tmp_path / "modeling-requests"
    modeling_requests.mkdir()
    modeling_request = responder.canonical_json(
        {"body": {}, "headers": {}, "id": "modeling-ok", "method": "POST", "path": "/api/semantic/sparql:query"}
    )
    (modeling_requests / "modeling-ok.json").write_bytes(modeling_request)
    modeling_gateway = api_gateway.ApiFileSpoolGateway(
        requests=modeling_requests,
        responses=tmp_path / "modeling-responses",
        audit_path=tmp_path / "modeling-audit.jsonl",
        api_key="host-only-key",
        upstream=lambda request_value: (modeling_calls.append(request_value) or (200, {}, {"ok": True})),
    )
    assert modeling_gateway.process_once() == 1
    assert modeling_calls[0]["method"] == "POST"


def test_consumer_record_requires_exact_bound_semantic_observations(tmp_path: Path) -> None:
    record_path, audit_path, record = _write_consumer_record_fixture(tmp_path)
    validated, errors = consumer.validate_consumer_record(record_path, audit_path, CONSUMER_SCOPE)
    assert validated == record
    assert errors == []
    assert consumer.consumer_final_status(0, validated, errors) == "COMPLETED"
    assert consumer.consumer_final_status(0, {"terminal_status": "BLOCKED"}, ["invalid"]) == "BLOCKED"


@pytest.mark.parametrize(
    "mutator",
    [
        lambda record: record["receipts"].pop("output_continuity"),
        lambda record: record["receipts"].update({"irrelevant": {}}),
        lambda record: record["receipts"]["current_target_contract"].update({"response_sha256": "0" * 64}),
        lambda record: record["observations"].pop("output_continuity"),
        lambda record: record["observations"]["current_target_contract"].update({"b_contract": ""}),
        lambda record: record["observations"]["missing_score"].update(
            {"state": "present", "explicit_gap_observed": False}
        ),
        lambda record: record["claim_classifications"].update({"missing_score": "invalid"}),
        lambda record: record.pop("claim_classifications"),
    ],
)
def test_consumer_record_rejects_missing_empty_unbound_or_wrong_classification(
    tmp_path: Path, mutator
) -> None:
    record_path, audit_path, record = _write_consumer_record_fixture(tmp_path)
    mutator(record)
    record_path.write_text(json.dumps(record), encoding="utf-8")

    _validated, errors = consumer.validate_consumer_record(record_path, audit_path, CONSUMER_SCOPE)

    assert errors
    assert consumer.consumer_final_status(0, record, errors) == "INCONCLUSIVE"


def test_consumer_record_rejects_receipts_only_record(tmp_path: Path) -> None:
    record_path, audit_path, record = _write_consumer_record_fixture(tmp_path)
    record.pop("observations")
    record_path.write_text(json.dumps(record), encoding="utf-8")

    _validated, errors = consumer.validate_consumer_record(record_path, audit_path, CONSUMER_SCOPE)

    assert "consumer_record:shape_invalid" in errors
    assert "consumer_record:observation_slots_mismatch" in errors


def test_consumer_record_rejects_extra_receipt_key(tmp_path: Path) -> None:
    record_path, audit_path, record = _write_consumer_record_fixture(tmp_path)
    record["receipts"]["current_target_contract"]["extra"] = "not allowed"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    _validated, errors = consumer.validate_consumer_record(record_path, audit_path, CONSUMER_SCOPE)

    assert "consumer_record:current_target_contract_receipt_invalid" in errors


def test_consumer_record_rejects_extra_observation_key(tmp_path: Path) -> None:
    record_path, audit_path, record = _write_consumer_record_fixture(tmp_path)
    record["observations"]["output_continuity"]["extra"] = "not allowed"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    _validated, errors = consumer.validate_consumer_record(record_path, audit_path, CONSUMER_SCOPE)

    assert "consumer_record:output_continuity_observation_invalid" in errors


def test_consumer_record_rejects_metadata_bound_receipts(tmp_path: Path) -> None:
    record_path, audit_path, _record = _write_consumer_record_fixture(tmp_path)
    entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    for entry in entries:
        entry["path"] = "/api/ontologies/ontology-1/modeling-context"
    audit_path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")

    _validated, errors = consumer.validate_consumer_record(record_path, audit_path, CONSUMER_SCOPE)

    assert {
        "consumer_record:current_target_contract_receipt_unbound",
        "consumer_record:output_continuity_receipt_unbound",
        "consumer_record:missing_score_receipt_unbound",
    }.issubset(errors)


def test_consumer_prompt_freezes_discovery_and_exact_readonly_record_without_answer_leakage() -> None:
    prompt = (SCENARIO_ROOT / "consumer-input-pack" / "consumer-prompt.md").read_text(encoding="utf-8")

    assert '{"body":null,"headers":{},"id":"<lowercase-id>","method":"GET","path":"/api/..."}' in prompt
    for slot in consumer.CONSUMER_SLOTS:
        assert f"`{slot}`" in prompt
    assert "/api/ontologies/<ontology_id>/modeling-context" in prompt
    assert "`query_entries.entities.rest`" in prompt
    assert "`query_entries.facts.rest`" in prompt
    assert "exactly these five top-level keys" in prompt
    assert "Latest published Version" not in prompt


@pytest.mark.parametrize("request_id", ["a", "lease01"])
def test_one_and_seven_character_request_ids_are_valid_for_both_spools(request_id: str) -> None:
    clarification = request(
        request_id,
        ["B", "C"],
        "Does B follow C's latest release or an earlier published release?",
        "The selected target changes B's current output.",
    )
    clarification_request, _ = responder.parse_request(clarification, f"{request_id}.json")
    assert clarification_request["id"] == request_id
    api = responder.canonical_json(
        {"body": None, "headers": {}, "id": request_id, "method": "GET", "path": "/api/health"}
    )
    api_request, _ = api_gateway.parse_request(api, f"{request_id}.json")
    assert api_request["id"] == request_id


@pytest.mark.parametrize("request_id", ["", "1lease", "Lease", "lease/01", "lease!01", "a" * 65])
def test_invalid_request_ids_and_filenames_remain_rejected_for_both_spools(request_id: str) -> None:
    filename = f"{request_id}.json"
    clarification = responder.canonical_json(
        {
            "affected_terms": ["B"],
            "business_impact": "target changes output",
            "id": request_id,
            "question": "Which target?",
        }
    )
    api = responder.canonical_json(
        {"body": None, "headers": {}, "id": request_id, "method": "GET", "path": "/api/health"}
    )
    with pytest.raises(responder.PolicyError):
        responder.parse_request(clarification, filename)
    with pytest.raises(api_gateway.PolicyError):
        api_gateway.parse_request(api, filename)


@pytest.mark.parametrize("terminator", [b"\n", b"\r\n"])
def test_api_spool_accepts_only_one_final_transport_line_ending(terminator: bytes) -> None:
    request_id = "newline-0001"
    canonical = responder.canonical_json(
        {"body": None, "headers": {}, "id": request_id, "method": "GET", "path": "/api/health"}
    )
    parsed, normalized = api_gateway.parse_request(canonical + terminator, f"{request_id}.json")
    assert parsed["id"] == request_id
    assert normalized == canonical


@pytest.mark.parametrize(
    "suffix_or_mutation",
    [b"\r", b"\n\n", b"\r\n\n", b" \n"],
)
def test_api_spool_rejects_internal_or_other_trailing_whitespace(suffix_or_mutation: bytes) -> None:
    request_id = "whitespace-1"
    canonical = responder.canonical_json(
        {"body": None, "headers": {}, "id": request_id, "method": "GET", "path": "/api/health"}
    )
    raw = canonical + suffix_or_mutation
    with pytest.raises(api_gateway.PolicyError, match="canonical JSON"):
        api_gateway.parse_request(raw, f"{request_id}.json")
    with pytest.raises(api_gateway.PolicyError, match="canonical JSON"):
        api_gateway.parse_request(canonical.replace(b'"headers":{}', b'"headers": {}'), f"{request_id}.json")


def test_ineligible_and_simultaneous_requests_cannot_substitute_for_a_gap(tmp_path: Path) -> None:
    instance, requests, responses, audit = make_responder(tmp_path)
    first = "decoy-0001"
    (requests / f"{first}.json").write_bytes(
        request(first, ["Current Draft"], "What is C's current draft?", "I want a documented fact.")
    )
    assert instance.process_once() == 1
    assert json.loads((responses / f"{first}.json").read_bytes())["status"] == "not_eligible"

    # New responder state represents a new run with two outstanding questions at once.
    simultaneous, requests, responses, audit = make_responder(tmp_path / "simultaneous")
    for request_id in ("serial-0001", "serial-0002"):
        (requests / f"{request_id}.json").write_bytes(
            request(request_id, ["B", "C", "version", "invocation"], "Which version?", "Current target changes.")
        )
    assert simultaneous.process_once() == 0
    assert not list(responses.iterdir())
    events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert {event["reason"] for event in events} == {"simultaneous_open_questions"}


def test_equivalent_business_questions_are_eligible_but_documented_decoy_is_not(tmp_path: Path) -> None:
    instance, requests, responses, _audit = make_responder(tmp_path)
    examples = [
        ("paraphrase-01", ["B", "C"], "Does B follow C's latest release or an earlier published release?", "The selected target changes B's current output."),
        ("paraphrase-02", ["quality rating", "quality score"], "Is quality rating the successor to quality score, or a separate change?", "Continuity changes the consumer explanation."),
        ("paraphrase-03", ["scoring data"], "What should B do if scoring data is unavailable?", "A confirmed behavior would change the result."),
    ]
    for request_id, terms, question, impact in examples:
        (requests / f"{request_id}.json").write_bytes(request(request_id, terms, question, impact))
        assert instance.process_once() == 1
    assert json.loads((responses / "paraphrase-01.json").read_bytes())["status"] == "answered"
    assert json.loads((responses / "paraphrase-02.json").read_bytes())["status"] == "answered"
    assert json.loads((responses / "paraphrase-03.json").read_bytes())["status"] == "uncertain"

    decoy_id = "paraphrase-04"
    (requests / f"{decoy_id}.json").write_bytes(
        request(decoy_id, ["Current Draft"], "What is C's current draft?", "I want the documented state.")
    )
    assert instance.process_once() == 1
    assert json.loads((responses / f"{decoy_id}.json").read_bytes())["status"] == "not_eligible"


def test_round14_continuity_question_is_answered_but_combined_decisions_fail_closed(tmp_path: Path) -> None:
    instance, requests, responses, _audit = make_responder(tmp_path)
    continuity_id = "continuity-001"
    (requests / f"{continuity_id}.json").write_bytes(
        request(
            continuity_id,
            ["quality_score", "quality_rating", "output continuity"],
            "Is quality_rating the successor of quality_score, or is it a separate contract change?",
            (
                "The acceptance consumer must report either output continuity or a positive discontinuity "
                "fact for C's published contract used by B."
            ),
        )
    )
    assert instance.process_once() == 1
    assert json.loads((responses / f"{continuity_id}.json").read_bytes())["status"] == "answered"

    combined_id = "combined-001"
    (requests / f"{combined_id}.json").write_bytes(
        request(
            combined_id,
            ["B", "C", "latest version", "quality rating", "quality score"],
            "Does B invoke C's latest version and is quality_rating the successor of quality_score?",
            "Both the current target and output continuity change the consumer conclusion.",
        )
    )
    assert instance.process_once() == 1
    assert json.loads((responses / f"{combined_id}.json").read_bytes())["status"] == "not_eligible"


def test_precreated_response_and_duplicate_id_are_rejected(tmp_path: Path) -> None:
    instance, requests, responses, audit = make_responder(tmp_path)
    request_id = "duplicate-001"
    (requests / f"{request_id}.json").write_bytes(
        request(request_id, ["score", "missing", "fallback"], "What if score is missing?", "Fallback changes behavior.")
    )
    (responses / f"{request_id}.json").write_bytes(b"tampered")
    assert instance.process_once() == 0
    assert "precreated" in audit.read_text(encoding="utf-8")

    instance, requests, responses, audit = make_responder(tmp_path / "duplicate")
    (requests / f"{request_id}.json").write_bytes(
        request(request_id, ["score", "missing", "fallback"], "What if score is missing?", "Fallback changes behavior.")
    )
    assert instance.process_once() == 1
    (requests / f"{request_id}.json").unlink()
    (requests / f"{request_id}.json").write_bytes(
        request(request_id, ["score", "missing", "fallback"], "What if score is missing?", "Fallback changes behavior.")
    )
    assert instance.process_once() == 0
    assert "duplicate request ID" in audit.read_text(encoding="utf-8")


def test_agent_visible_contract_has_no_category_or_expected_count(tmp_path: Path) -> None:
    manifest = launcher.read_manifest()
    run = launcher.prepare_run(tmp_path / "run", "baseline", "m4-protocol-test")
    staged = tmp_path / "run" / "agent-input"
    staged_text = "\n".join(path.read_text(encoding="utf-8") for path in staged.rglob("*") if path.is_file())
    assert "hidden-decision" not in staged_text
    assert "category" not in staged_text
    assert "expected question count" not in staged_text
    assert "category enum" not in staged_text
    assert "B invokes C through C's Latest published Version." not in staged_text
    assert manifest["files"]
    mount_audit = run["mount_audit"]
    assert all("hidden-contract" not in path for path in mount_audit["agent_visible_mounts"])
    assert any("hidden-contract" in path for path in mount_audit["host_only_paths"])
    command = " ".join(run["responder_command"])
    assert "hidden-contract.json" in command  # Host process needs the contract.
    assert "hidden-contract.json" not in " ".join(
        launcher.bwrap_command(
            {key: Path(value) for key, value in {
                "staging": tmp_path / "run" / "agent-input",
                "workspace": tmp_path / "run" / "workspace",
                "codex_home": tmp_path / "run" / "host" / "codex-home",
                "clarification_responses": tmp_path / "run" / "host" / "clarification-responses",
                "api_responses": tmp_path / "run" / "host" / "api-responses",
            }.items()},
            "m4-protocol-test",
            Path(sys.executable),
        )
    )


def test_positive_baseline_variant_and_unknown_semantics() -> None:
    semantic.assert_variant_pair(
        {
            "current_c_target": "C Latest Version",
            "current_target_contract": "quality_rating:number",
            "continuity": "quality_score:number -> quality_rating:number",
        },
        {
            "current_c_target": "C published Version 1",
            "current_target_contract": "quality_score:number",
            "old_contract_status": "quality_score:number removed",
            "new_contract_status": "quality_rating:number distinct addition",
            "discontinuity": "continuity not confirmed",
        },
        {
            "missing_score_status": "unknown",
            "missing_score_reason": "The business owner cannot confirm missing-score handling.",
        },
    )


def test_formal_launcher_commands_start_watch_services_and_fresh_codex_namespace(tmp_path: Path) -> None:
    paths = launcher.prepare_layout(tmp_path / "formal", "baseline", "m4-formal-test")
    modeling_command = launcher.agent_command(paths, "m4-formal-test")
    responder_command = launcher.responder_command(paths, watch=True)
    api_command = launcher.api_gateway_command(paths, 8012, watch=True)
    assert "--watch" in responder_command
    assert "--watch" in api_command
    assert "--api-key-env" in api_command
    assert "M4_HOST_API_KEY" in api_command
    assert "/codex" in modeling_command
    assert "exec" in modeling_command
    assert "--json" in modeling_command
    assert "hidden-contract.json" not in " ".join(modeling_command)
    assert "M4_HOST_API_KEY" not in " ".join(modeling_command)


def test_bwrap_forwards_only_proxy_allowlist_and_audit_redacts_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("https_proxy", "http://proxy.example:8443")
    monkeypatch.setenv("UNRELATED_HOST_TOKEN", "must-not-enter-bwrap")
    paths = launcher.prepare_layout(tmp_path / "proxy", "baseline", "m4-proxy-test")
    command = launcher.bwrap_command(paths, "m4-proxy-test", Path(sys.executable))
    command_text = " ".join(command)
    assert "HTTPS_PROXY" in command_text
    assert "https_proxy" in command_text
    assert "HTTP_PROXY" not in command_text
    assert "UNRELATED_HOST_TOKEN" not in command_text
    audit = launcher.write_mount_audit(paths, {"declared_mount_set": []}, "m4-proxy-test")
    assert audit["proxy_environment"] == [
        {"name": "HTTPS_PROXY", "value_sha256": launcher.sha256_bytes(b"http://proxy.example:8443")},
        {"name": "https_proxy", "value_sha256": launcher.sha256_bytes(b"http://proxy.example:8443")},
    ]
    assert "proxy.example" not in (tmp_path / "proxy" / "host" / "mount-audit.json").read_text(encoding="utf-8")


def test_negative_only_variant_proof_is_rejected() -> None:
    with pytest.raises(semantic.SemanticAuditError, match="missing positive"):
        semantic.assert_lifecycle_observation(
            "pinned-non-successor", {"current_c_target": "", "current_target_contract": ""}
        )
    with pytest.raises(semantic.SemanticAuditError, match="old-contract removal"):
        semantic.assert_output_identity_observation("pinned-non-successor", {"discontinuity": "continuity not confirmed"})


def _write_clarification_fixture(paths: dict[str, Path], run_tag: str) -> None:
    audit_entries: list[dict[str, object]] = []
    consumption: list[bytes] = []
    for index, decision in enumerate(responder.default_hidden_contract("baseline"), start=1):
        request_id = f"clarification-{index}"
        request_raw = responder.canonical_json(
            {
                "affected_terms": ["term"],
                "business_impact": "A visible business conclusion changes.",
                "id": request_id,
                "question": "A visible business ambiguity needs confirmation.",
            }
        )
        response_value = (
            {"answer": decision.answer, "id": request_id, "status": "answered"}
            if decision.answer is not None
            else {"id": request_id, "reason": decision.uncertain_reason, "status": "uncertain"}
        )
        response_raw = responder.canonical_json(response_value)
        (paths["clarification_requests"] / f"{request_id}.json").write_bytes(request_raw)
        (paths["clarification_responses"] / f"{request_id}.json").write_bytes(response_raw)
        response_sha256 = hashlib.sha256(response_raw).hexdigest()
        audit_entries.append(
            {
                "at": f"2026-07-27T00:00:00.{index}00000+00:00",
                "canonical_request_sha256": hashlib.sha256(request_raw).hexdigest(),
                "decision_fingerprint": responder.decision_fingerprint(decision),
                "filename": f"{request_id}.json",
                "policy": "responded",
                "raw_request_sha256": hashlib.sha256(request_raw).hexdigest(),
                "request_id": request_id,
                "response_sha256": response_sha256,
                "status": response_value["status"],
            }
        )
        consumption.append(
            responder.canonical_json(
                {
                    "request_id": request_id,
                    "response_id": request_id,
                    "response_read_confirmed": True,
                    "response_sha256": response_sha256,
                    "run_tag": run_tag,
                    "status": response_value["status"],
                }
            )
        )
    paths["host_audit"].write_text(
        "\n".join(json.dumps(entry) for entry in audit_entries) + "\n", encoding="utf-8"
    )
    paths["workspace"].joinpath("clarification-consumption-receipts.jsonl").write_bytes(
        b"\n".join(consumption) + b"\n"
    )


def _write_final_audit_fixture(
    tmp_path: Path, terminal_status: str = "DEVELOPMENT_READY", omit: str | None = None
) -> tuple[dict[str, Path], dict[str, object]]:
    paths = launcher.prepare_layout(tmp_path / "final-audit", "baseline", "m4-final-audit")
    bodies: dict[str, dict[str, object]] = {
        "principal_schema_dry_run": {"attempt_status": "validated", "mode": "dry_run", "target": {"graph_set_id": "graph-set-1", "source_signature_before": "sig-1"}},
        "shape_apply": {"attempt_status": "applied", "batch_status": "applied", "mode": "apply_atomic", "target": {"graph_set_id": "graph-set-1", "source_signature_after": "sig-2", "source_signature_before": "sig-1"}},
        "invalid_shape_dry_run": {
            "attempt_status": "validation_failed",
            "batch_status": "validated",
            "findings": [{"blocking": True, "code": "shacl_violation"}],
            "mode": "dry_run",
            "target": {"graph_set_id": "graph-set-1", "source_signature_before": "sig-2"},
        },
        "valid_instance_dry_run": {"attempt_status": "validated", "mode": "dry_run", "target": {"graph_set_id": "graph-set-1", "source_signature_before": "sig-2"}},
        "valid_instance_apply": {
            "attempt_status": "applied",
            "batch_status": "applied",
            "mode": "apply_atomic",
            "target": {"graph_set_id": "graph-set-1", "source_signature_before": "sig-2"},
        },
        "validation": {"conforms": True, "status": "succeeded"},
        "reasoning": {
            "consistent": True,
            "derived_pointer": {"graph_set_id": "graph-set-1", "status": "current"},
            "run_id": "reasoning-run-1",
            "status": "succeeded",
        },
        "governed_query": {
            "result": {"results": {"bindings": [{"answer": {"value": "yes"}}]}},
            "scope": {
                "excluded_ontologies": [],
                "ontologies": [{"derived_state": {"reasoning": {"run_id": "reasoning-run-1", "status": "current"}, "rule": {"status": "missing"}}, "ontology_id": "ontology-1"}],
                "status": "complete",
            },
            "truncated": False,
            "warnings": [{"code": "derived_result_missing", "message": "No current rule result pointer."}],
        },
        "pre_checkpoint_get": {"session": {"id": "session-1", "revision": 9}},
        "checkpoint": {
            "checkpoint": {"id": "checkpoint-1"},
            "session": {"revision": 9},
        },
        "complete": {"completed_at": "2026-07-27T00:00:00Z", "revision": 10, "status": "completed"},
        "final_get": {
            "latest_checkpoint": {"id": "checkpoint-1"},
            "session": {"completed_at": "2026-07-27T00:00:00Z", "status": "completed"},
        },
    }
    paths_by_receipt = {
        "principal_schema_dry_run": "/api/build-sessions/session-1/modeling-batches",
        "shape_apply": "/api/build-sessions/session-1/modeling-batches",
        "invalid_shape_dry_run": "/api/build-sessions/session-1/modeling-batches",
        "valid_instance_dry_run": "/api/build-sessions/session-1/modeling-batches",
        "valid_instance_apply": "/api/build-sessions/session-1/modeling-batches",
        "validation": "/api/semantic/validation-runs",
        "reasoning": "/api/semantic/graph-sets/graph-set-1/reasoning-runs",
        "governed_query": "/api/semantic/sparql:query",
        "pre_checkpoint_get": "/api/build-sessions/session-1",
        "checkpoint": "/api/build-sessions/session-1/checkpoints",
        "complete": "/api/build-sessions/session-1:complete",
        "final_get": "/api/build-sessions/session-1",
    }
    receipts: dict[str, dict[str, object]] = {}
    entries: list[dict[str, object]] = []
    times = {
        "principal_schema_dry_run": 1,
        "shape_apply": 2,
        "invalid_shape_dry_run": 3,
        "valid_instance_dry_run": 4,
        "valid_instance_apply": 5,
        "validation": 6,
        "reasoning": 7,
        "governed_query": 8,
        "pre_checkpoint_get": 9,
        "checkpoint": 10,
        "complete": 11,
        "final_get": 12,
    }
    for index, name in enumerate(launcher.RECEIPT_ORDER, start=1):
        if name == omit:
            continue
        request_id = f"receipt-{index}"
        status = 200
        canonical_request_sha256 = f"{index + 100:064x}"
        response = responder.canonical_json(
            {"body": bodies[name], "headers": {"content-type": "application/json"}, "id": request_id, "status": status}
        )
        response_sha256 = hashlib.sha256(response).hexdigest()
        (paths["api_responses"] / f"{request_id}.json").write_bytes(response)
        receipts[name] = {
            "request_id": request_id,
            "status": status,
            "canonical_request_sha256": canonical_request_sha256,
            "raw_response_sha256": response_sha256,
        }
        request_summary = (
            {
                "client_batch_id": "schema-1",
                "command_kinds": ["create_class", "create_shape"],
                "contains_create_shape": True,
                "items_sha256": "s" * 64,
                "mode": "dry_run",
            }
            if name == "principal_schema_dry_run"
            else
            {
                "client_batch_id": "schema-1",
                "command_kinds": ["create_class", "create_shape"],
                "contains_create_shape": True,
                "items_sha256": "s" * 64,
                "mode": "apply_atomic",
            }
            if name == "shape_apply"
            else {
                "client_batch_id": "invalid-1",
                "command_kinds": ["create_entity"],
                "contains_create_shape": False,
                "expected_workspace_version": "workspace-1",
                "items_sha256": "i" * 64,
                "mode": "dry_run",
                "ontology_id": "ontology-1",
            }
            if name == "invalid_shape_dry_run"
            else {
                "client_batch_id": "instance-1",
                "command_kinds": ["create_entity"],
                "contains_create_shape": False,
                "expected_workspace_version": "workspace-1",
                "idempotency_key_sha256": "a" * 64,
                "items_sha256": "v" * 64,
                "mode": "dry_run",
                "ontology_id": "ontology-1",
            }
            if name == "valid_instance_dry_run"
            else {
                "client_batch_id": "instance-1",
                "command_kinds": ["create_entity"],
                "contains_create_shape": False,
                "expected_workspace_version": "workspace-1",
                "idempotency_key_sha256": "b" * 64,
                "items_sha256": "v" * 64,
                "mode": "apply_atomic",
                "ontology_id": "ontology-1",
            }
            if name == "valid_instance_apply"
            else {"ontology_ids": ["ontology-1"], "project_id": "project-1", "scope_mode": "ontologies"}
            if name == "governed_query"
            else {"expected_revision": 9}
            if name in {"checkpoint", "complete"}
            else {}
        )
        entries.append(
            {
                "at": f"2026-07-27T00:00:{times[name]:02d}+00:00",
                "policy": "forwarded",
                "canonical_request_sha256": canonical_request_sha256,
                "method": "GET" if name in {"pre_checkpoint_get", "final_get"} else "POST",
                "path": paths_by_receipt[name],
                "request_id": request_id,
                "request_summary": request_summary,
                "response_filename": f"{request_id}.json",
                "response_sha256": response_sha256,
                "status": status,
            }
        )
    entries.sort(key=lambda entry: entry["at"])
    paths["api_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    _write_clarification_fixture(paths, "m4-final-audit")
    paths["workspace"].joinpath("decision-log.jsonl").write_text('{"event":"terminal"}\n', encoding="utf-8")
    runtime: dict[str, object] = {
        "run_tag": "m4-final-audit",
        "terminal_status": terminal_status,
        "receipts": receipts,
        "optional_rule_absent": {
            "request_id": receipts.get("governed_query", {}).get("request_id"),
            "response_sha256": receipts.get("governed_query", {}).get("raw_response_sha256"),
            "code": "derived_result_missing",
            "message": "No current rule result pointer.",
        },
        "checkpoint": {"id": "checkpoint-1", "session_revision": 9},
        "build_session_completion": {
            "status": "completed",
            "completed_at": "2026-07-27T00:00:00Z",
            "latest_checkpoint_id": "checkpoint-1",
            "complete_request_id": receipts.get("complete", {}).get("request_id"),
            "final_get_request_id": receipts.get("final_get", {}).get("request_id"),
        },
    }
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    return paths, runtime


def _replace_host_response(paths: dict[str, Path], runtime: dict[str, object], name: str, body: dict[str, object]) -> None:
    receipts = runtime["receipts"]
    assert isinstance(receipts, dict) and isinstance(receipts[name], dict)
    receipt = receipts[name]
    request_id = receipt["request_id"]
    assert isinstance(request_id, str)
    response = responder.canonical_json(
        {"body": body, "headers": {"content-type": "application/json"}, "id": request_id, "status": receipt["status"]}
    )
    (paths["api_responses"] / f"{request_id}.json").write_bytes(response)
    receipt["raw_response_sha256"] = hashlib.sha256(response).hexdigest()
    entries = [json.loads(line) for line in paths["api_audit"].read_text(encoding="utf-8").splitlines()]
    for entry in entries:
        if entry.get("request_id") == request_id:
            entry["response_sha256"] = receipt["raw_response_sha256"]
            entry["status"] = receipt["status"]
    paths["api_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def _write_correction_audit_fixture(tmp_path: Path) -> tuple[dict[str, Path], dict[str, object]]:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    _replace_host_response(
        paths,
        runtime,
        "valid_instance_dry_run",
        {
            "attempt_status": "validation_failed",
            "mode": "dry_run",
            "target": {"graph_set_id": "graph-set-1", "source_signature_before": "sig-2"},
            "findings": [
                {
                    "blocking": True,
                    "code": "shacl_violation",
                    "finding_fingerprint": "finding-1",
                    "client_item_ids": ["item-1"],
                }
            ],
        },
    )
    receipts = runtime["receipts"]
    assert isinstance(receipts, dict)
    old_apply = receipts.pop("valid_instance_apply")
    assert isinstance(old_apply, dict)
    old_id = old_apply["request_id"]
    assert isinstance(old_id, str)
    (paths["api_responses"] / f"{old_id}.json").unlink()
    entries = [
        json.loads(line)
        for line in paths["api_audit"].read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("request_id") != old_id
    ]
    original_entry = next(
        entry for entry in entries if entry.get("request_id") == receipts["valid_instance_dry_run"]["request_id"]
    )
    original_summary = original_entry["request_summary"]
    assert isinstance(original_summary, dict)
    original_summary["item_summaries"] = [
        {
            "canonical_item_sha256": "1" * 64,
            "client_item_id": "item-1",
            "command_kind": "create_entity",
            "depends_on": [],
        },
        {
            "canonical_item_sha256": "2" * 64,
            "client_item_id": "unchanged-1",
            "command_kind": "create_relation",
            "depends_on": ["item-1"],
        },
    ]
    original_receipt = receipts["valid_instance_dry_run"]
    assert isinstance(original_receipt, dict)
    correction_evidence = {
        "changed_items": [
            {
                "after_sha256": "3" * 64,
                "before_sha256": "1" * 64,
                "client_item_id": "item-1",
                "reason_finding_fingerprint": "finding-1",
            }
        ],
        "correction_batch_id": "correction-1",
        "correction_dry_run_request_id": "correction_instance_dry_run",
        "correction_dry_run_request_sha256": f"{205:064x}",
        "correction_dry_run_response_sha256": None,
        "original_batch_id": "instance-1",
        "original_finding_fingerprints": ["finding-1"],
        "original_request_id": original_receipt["request_id"],
        "original_request_sha256": original_receipt["canonical_request_sha256"],
        "original_response_sha256": original_receipt["raw_response_sha256"],
    }
    for name, second, mode, status in (
        ("correction_instance_dry_run", 5, "dry_run", "validated"),
        ("correction_instance_apply", 6, "apply_atomic", "applied"),
    ):
        request_id = name
        body = {
            "attempt_status": status,
            "mode": mode,
            "target": {"graph_set_id": "graph-set-1", "source_signature_before": "sig-2"},
        }
        if mode == "apply_atomic":
            body["batch_status"] = "applied"
        raw = responder.canonical_json({"body": body, "headers": {"content-type": "application/json"}, "id": request_id, "status": 200})
        response_sha256 = hashlib.sha256(raw).hexdigest()
        if name == "correction_instance_dry_run":
            correction_evidence["correction_dry_run_response_sha256"] = response_sha256
        (paths["api_responses"] / f"{request_id}.json").write_bytes(raw)
        receipts[name] = {"request_id": request_id, "status": 200, "canonical_request_sha256": f"{second + 200:064x}", "raw_response_sha256": response_sha256}
        entries.append(
            {
                "at": f"2026-07-27T00:00:{second:02d}+00:00",
                "canonical_request_sha256": f"{second + 200:064x}",
                "method": "POST",
                "path": "/api/build-sessions/session-1/modeling-batches",
                "policy": "forwarded",
                "request_id": request_id,
                "request_summary": {
                    "client_batch_id": "correction-1",
                    "command_kinds": ["create_entity", "create_relation"],
                    "contains_create_shape": False,
                    "expected_workspace_version": "workspace-1",
                    "idempotency_key_sha256": ("c" if mode == "dry_run" else "d") * 64,
                    "item_summaries": [
                        {
                            "canonical_item_sha256": "3" * 64,
                            "client_item_id": "item-1",
                            "command_kind": "create_entity",
                            "depends_on": [],
                        },
                        {
                            "canonical_item_sha256": "2" * 64,
                            "client_item_id": "unchanged-1",
                            "command_kind": "create_relation",
                            "depends_on": ["item-1"],
                        },
                    ],
                    "items_sha256": "c" * 64,
                    "mode": mode,
                    "ontology_id": "ontology-1",
                },
                "response_filename": f"{request_id}.json",
                "response_sha256": response_sha256,
                "status": 200,
            }
        )
    for entry in entries:
        second = int(str(entry["at"])[17:19])
        if second >= 5 and entry["request_id"] not in {"correction_instance_dry_run", "correction_instance_apply"}:
            entry["at"] = f"2026-07-27T00:00:{second + 1:02d}+00:00"
    entries.sort(key=lambda entry: entry["at"])
    paths["api_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    runtime["instance_correction"] = correction_evidence
    paths["workspace"].joinpath("decision-log.jsonl").write_bytes(
        responder.canonical_json({"event": "instance_correction", "evidence": correction_evidence}) + b"\n"
    )
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    return paths, runtime


def _rewrite_audit_entry(
    paths: dict[str, Path], name: str, *, path: str | None = None, request_summary: dict[str, object] | None = None
) -> None:
    entries = [json.loads(line) for line in paths["api_audit"].read_text(encoding="utf-8").splitlines()]
    request_id = f"receipt-{launcher.RECEIPT_ORDER.index(name) + 1}"
    for entry in entries:
        if entry.get("request_id") == request_id:
            if path is not None:
                entry["path"] = path
            if request_summary is not None:
                entry["request_summary"] = request_summary
    paths["api_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


def _append_audit_event(paths: dict[str, Path], event: dict[str, object]) -> None:
    with paths["api_audit"].open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event) + "\n")


def _prepend_audit_event(paths: dict[str, Path], event: dict[str, object]) -> None:
    existing = paths["api_audit"].read_text(encoding="utf-8")
    paths["api_audit"].write_text(json.dumps(event) + "\n" + existing, encoding="utf-8")


def test_final_audit_propagates_agent_blocked_state(tmp_path: Path) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path, terminal_status="BLOCKED")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "BLOCKED"
    assert audit["runtime_terminal_status"] == "BLOCKED"


def test_final_audit_refuses_ready_without_every_required_receipt(tmp_path: Path) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path, omit="reasoning")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "reasoning:missing_or_invalid_receipt" in audit["completion_gate_errors"]


def test_final_audit_requires_matching_completed_final_get_evidence(tmp_path: Path) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    runtime["build_session_completion"] = {"status": "active", "latest_checkpoint_id": "different"}
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "checkpoint_id_mismatch" in audit["completion_gate_errors"]
    assert "build_session_not_completed" in audit["completion_gate_errors"]
    assert "final_get_request_id_mismatch" in audit["completion_gate_errors"]


def test_final_audit_does_not_trust_agent_semantic_claims_over_host_responses(tmp_path: Path) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    receipts = runtime["receipts"]
    assert isinstance(receipts, dict)
    receipts["validation"]["conforms"] = False
    receipts["reasoning"]["current"] = False
    receipts["governed_query"]["warnings"] = ["scope warning"]
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "COMPLETED"


def test_final_audit_refuses_lying_runtime_when_host_response_fails(tmp_path: Path) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    _replace_host_response(paths, runtime, "validation", {"conforms": False, "status": "succeeded"})
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "validation:not_conformant" in audit["completion_gate_errors"]


@pytest.mark.parametrize(
    ("receipt_name", "body", "expected_error"),
    [
        (
            "invalid_shape_dry_run",
            {
                "attempt_status": "validation_failed",
                "batch_status": "validated",
                "findings": [{"blocking": True, "code": "shacl_violation"}],
                "mode": "dry_run",
                "target": {"graph_set_id": "graph-set-1", "source_signature_before": "spliced"},
            },
            "modeling_target:post_schema_signature_mismatch",
        ),
        (
            "valid_instance_dry_run",
            {
                "attempt_status": "validated",
                "mode": "dry_run",
                "target": {"graph_set_id": "graph-set-2", "source_signature_before": "sig-2"},
            },
            "modeling_target:graph_set_id_mismatch",
        ),
    ],
)
def test_final_audit_rejects_cross_phase_target_splices(
    tmp_path: Path, receipt_name: str, body: dict[str, object], expected_error: str
) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    _replace_host_response(paths, runtime, receipt_name, body)

    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})

    assert audit["status"] == "INCONCLUSIVE"
    assert expected_error in audit["completion_gate_errors"]


def test_final_audit_requires_2xx_shacl_validation_failure_not_fake_http_rejection(tmp_path: Path) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    receipts = runtime["receipts"]
    assert isinstance(receipts, dict) and isinstance(receipts["invalid_shape_dry_run"], dict)
    receipts["invalid_shape_dry_run"]["status"] = 422
    _replace_host_response(
        paths,
        runtime,
        "invalid_shape_dry_run",
        {"attempt_status": "validation_failed", "findings": [{"blocking": True, "code": "shacl_violation"}]},
    )
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "invalid_shape_dry_run:unexpected_receipt_status" in audit["completion_gate_errors"]


def test_final_audit_completes_only_with_gateway_bound_runtime_evidence(tmp_path: Path) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path)
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "COMPLETED"
    assert audit["completion_gate_errors"] == []


def test_final_audit_requires_one_hash_bound_eligible_response_for_every_visible_gap(
    tmp_path: Path,
) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path)
    entries = [json.loads(line) for line in paths["host_audit"].read_text(encoding="utf-8").splitlines()]
    paths["host_audit"].write_text(
        "\n".join(json.dumps(entry) for entry in entries[1:]) + "\n", encoding="utf-8"
    )

    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})

    assert audit["status"] == "INCONCLUSIVE"
    assert "clarification:missing_or_duplicate_visible_gap" in audit["completion_gate_errors"]


def test_final_audit_rejects_duplicate_eligible_response_for_one_visible_gap(tmp_path: Path) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path)
    entries = [json.loads(line) for line in paths["host_audit"].read_text(encoding="utf-8").splitlines()]
    original = entries[0]
    duplicate_id = "clarification-duplicate"
    duplicate_request = responder.canonical_json(
        {
            "affected_terms": ["B", "C", "version", "invocation"],
            "business_impact": "The current target changes B's visible output contract.",
            "id": duplicate_id,
            "question": "Which published C version does B invoke?",
        }
    )
    duplicate_response = responder.canonical_json(
        {
            "answer": "B invokes C through C's Latest published Version.",
            "id": duplicate_id,
            "status": "answered",
        }
    )
    (paths["clarification_requests"] / f"{duplicate_id}.json").write_bytes(duplicate_request)
    (paths["clarification_responses"] / f"{duplicate_id}.json").write_bytes(duplicate_response)
    duplicate_hash = hashlib.sha256(duplicate_response).hexdigest()
    entries.insert(
        1,
        {
            "at": "2026-07-27T00:00:00.150000+00:00",
            "decision_fingerprint": original["decision_fingerprint"],
            "policy": "responded",
            "raw_request_sha256": hashlib.sha256(duplicate_request).hexdigest(),
            "request_id": duplicate_id,
            "response_sha256": duplicate_hash,
            "status": "answered",
        },
    )
    paths["host_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    receipts_path = paths["workspace"] / "clarification-consumption-receipts.jsonl"
    with receipts_path.open("ab") as stream:
        stream.write(
            responder.canonical_json(
                {
                    "request_id": duplicate_id,
                    "response_id": duplicate_id,
                    "response_read_confirmed": True,
                    "response_sha256": duplicate_hash,
                    "run_tag": "m4-final-audit",
                    "status": "answered",
                }
            )
            + b"\n"
        )

    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})

    assert audit["status"] == "INCONCLUSIVE"
    assert "clarification:missing_or_duplicate_visible_gap" in audit["completion_gate_errors"]


def test_final_audit_allows_revised_eligible_id_after_initial_not_eligible(tmp_path: Path) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path)
    entries = [json.loads(line) for line in paths["host_audit"].read_text(encoding="utf-8").splitlines()]
    rejected_id = "clarification-revision-needed"
    rejected_request = responder.canonical_json(
        {
            "affected_terms": ["quality rating"],
            "business_impact": "A visible business conclusion changes.",
            "id": rejected_id,
            "question": "Can this be confirmed?",
        }
    )
    rejected_response = responder.canonical_json(
        {
            "id": rejected_id,
            "reason": "The request does not reach an answerable visible-input gap.",
            "status": "not_eligible",
        }
    )
    (paths["clarification_requests"] / f"{rejected_id}.json").write_bytes(rejected_request)
    (paths["clarification_responses"] / f"{rejected_id}.json").write_bytes(rejected_response)
    entries.insert(
        0,
        {
            "at": "2026-07-27T00:00:00.010000+00:00",
            "decision_fingerprint": entries[1]["decision_fingerprint"],
            "policy": "responded",
            "raw_request_sha256": hashlib.sha256(rejected_request).hexdigest(),
            "request_id": rejected_id,
            "response_sha256": hashlib.sha256(rejected_response).hexdigest(),
            "status": "not_eligible",
        },
    )
    paths["host_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")

    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})

    assert audit["status"] == "COMPLETED"
    assert audit["completion_gate_errors"] == []


def test_final_audit_uses_host_observed_order_and_response_hashes_for_clarifications(
    tmp_path: Path,
) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path)
    entries = [json.loads(line) for line in paths["host_audit"].read_text(encoding="utf-8").splitlines()]
    entries[-1]["at"] = "2026-07-27T00:00:02+00:00"
    paths["host_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")

    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})

    assert audit["status"] == "INCONCLUSIVE"
    assert "clarification:host_observed_order_or_status_invalid" in audit["completion_gate_errors"]

    hash_paths, _runtime = _write_final_audit_fixture(tmp_path / "hash-case")
    hash_entries = [
        json.loads(line) for line in hash_paths["host_audit"].read_text(encoding="utf-8").splitlines()
    ]
    response_path = hash_paths["clarification_responses"] / f"{hash_entries[-1]['request_id']}.json"
    response_path.write_bytes(b'{"tampered":true}')
    audit = launcher._final_audit(
        hash_paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"}
    )
    assert "clarification:hash_bound_consumption_missing" in audit["completion_gate_errors"]


def test_prompt_requires_every_visible_brief_gap_before_principal_schema_batch() -> None:
    prompt = (SCENARIO_ROOT / "input-pack" / "modeling-agent-prompt.md").read_text(encoding="utf-8")

    assert "three consequential\nambiguities" in prompt
    assert "not_eligible" in prompt
    assert "atomically record `BLOCKED`" in prompt


def test_final_audit_completes_after_one_qualified_correction_and_exact_apply(tmp_path: Path) -> None:
    paths, _runtime = _write_correction_audit_fixture(tmp_path)
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "COMPLETED"


def test_final_audit_rejects_correction_signature_splice(tmp_path: Path) -> None:
    paths, runtime = _write_correction_audit_fixture(tmp_path)
    _replace_host_response(
        paths,
        runtime,
        "correction_instance_apply",
        {
            "attempt_status": "applied",
            "batch_status": "applied",
            "mode": "apply_atomic",
            "target": {"graph_set_id": "graph-set-1", "source_signature_before": "spliced"},
        },
    )

    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})

    assert audit["status"] == "INCONCLUSIVE"
    assert "modeling_target:instance_signature_mismatch" in audit["completion_gate_errors"]


def _mutate_correction_dry_summary(paths: dict[str, Path], mutator) -> None:
    entries = [json.loads(line) for line in paths["api_audit"].read_text(encoding="utf-8").splitlines()]
    for request_id in ("correction_instance_dry_run", "correction_instance_apply"):
        summary = next(entry["request_summary"] for entry in entries if entry.get("request_id") == request_id)
        assert isinstance(summary, dict)
        mutator(summary)
    paths["api_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (
            lambda summary: summary["item_summaries"][1].update({"canonical_item_sha256": "4" * 64}),
            "correction_instance:changed_item_not_in_finding",
        ),
        (
            lambda summary: summary["item_summaries"].append(
                {
                    "canonical_item_sha256": "5" * 64,
                    "client_item_id": "added-1",
                    "command_kind": "create_entity",
                    "depends_on": [],
                }
            ),
            "correction_instance:item_id_set_changed",
        ),
        (
            lambda summary: summary["item_summaries"].pop(),
            "correction_instance:item_id_set_changed",
        ),
        (
            lambda summary: summary["item_summaries"][0].update({"client_item_id": "renamed-1"}),
            "correction_instance:item_id_set_changed",
        ),
        (
            lambda summary: summary["item_summaries"][0].update({"command_kind": "create_relation"}),
            "correction_instance:command_kind_changed",
        ),
        (
            lambda summary: summary["item_summaries"][0].update({"depends_on": ["unchanged-1"]}),
            "correction_instance:depends_on_changed",
        ),
        (
            lambda summary: summary["item_summaries"][0].update({"canonical_item_sha256": "1" * 64}),
            "correction_instance:no_changed_item",
        ),
    ],
)
def test_final_audit_rejects_correction_item_set_topology_and_finding_violations(
    tmp_path: Path, mutator, expected_error: str
) -> None:
    paths, _runtime = _write_correction_audit_fixture(tmp_path)
    _mutate_correction_dry_summary(paths, mutator)
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert expected_error in audit["completion_gate_errors"]


@pytest.mark.parametrize("missing", [True, False])
def test_final_audit_requires_correction_fingerprint_evidence_and_matching_decision_log(
    tmp_path: Path, missing: bool
) -> None:
    paths, runtime = _write_correction_audit_fixture(tmp_path)
    if missing:
        runtime.pop("instance_correction")
        expected_error = "correction_instance:missing_evidence"
    else:
        evidence = runtime["instance_correction"]
        assert isinstance(evidence, dict)
        changed_items = evidence["changed_items"]
        assert isinstance(changed_items, list) and isinstance(changed_items[0], dict)
        changed_items[0]["reason_finding_fingerprint"] = "wrong-fingerprint"
        expected_error = "correction_instance:changed_item_evidence_mismatch"
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert expected_error in audit["completion_gate_errors"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("client_batch_id", "instance-1"), ("idempotency_key_sha256", "a" * 64)],
)
def test_final_audit_requires_new_correction_batch_and_idempotency_identity(
    tmp_path: Path, field: str, value: str
) -> None:
    paths, _runtime = _write_correction_audit_fixture(tmp_path)
    entries = [json.loads(line) for line in paths["api_audit"].read_text(encoding="utf-8").splitlines()]
    summary = next(
        entry["request_summary"]
        for entry in entries
        if entry.get("request_id") == "correction_instance_dry_run"
    )
    assert isinstance(summary, dict)
    summary[field] = value
    paths["api_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "correction_instance:invalid_or_unapplied" in audit["completion_gate_errors"]


@pytest.mark.parametrize(
    "event",
    [
        {
            "method": "POST",
            "path": "/api/build-sessions/session-1/modeling-batches",
            "request_id": "original-instance-apply",
            "request_summary": {"command_kinds": ["create_entity"], "contains_create_shape": False, "mode": "apply_atomic"},
        },
        {
            "method": "POST",
            "path": "/api/build-sessions/session-1/modeling-batches",
            "request_id": "second-correction-dry-run",
            "request_summary": {"command_kinds": ["create_entity"], "contains_create_shape": False, "mode": "dry_run"},
        },
        {
            "method": "POST",
            "path": "/api/build-sessions/session-1/modeling-batches",
            "request_id": "post-correction-schema",
            "request_summary": {"command_kinds": ["create_shape"], "contains_create_shape": True, "mode": "dry_run"},
        },
    ],
)
def test_final_audit_rejects_original_apply_second_correction_and_schema_operation(
    tmp_path: Path, event: dict[str, object]
) -> None:
    paths, _runtime = _write_correction_audit_fixture(tmp_path)
    _append_audit_event(
        paths,
        {"at": "2026-07-27T00:00:06.500000+00:00", "policy": "forwarded", **event},
    )
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "timeline:closed_sequence_violation" in audit["completion_gate_errors"]


def test_final_audit_rejects_correction_after_direct_valid_candidate(tmp_path: Path) -> None:
    paths, runtime = _write_correction_audit_fixture(tmp_path)
    _replace_host_response(paths, runtime, "valid_instance_dry_run", {"attempt_status": "validated", "mode": "dry_run", "target": {"graph_set_id": "graph-set-1", "source_signature_before": "sig-2"}})
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (
            lambda paths, runtime: runtime["receipts"]["validation"].update(
                {"canonical_request_sha256": "f" * 64}
            ),
            "validation:gateway_receipt_mismatch",
        ),
        (
            lambda paths, runtime: _rewrite_audit_entry(paths, "governed_query", path="/api/test/query"),
            "governed_query:unexpected_endpoint",
        ),
        (
            lambda paths, runtime: _rewrite_audit_entry(
                paths, "shape_apply", request_summary={"contains_create_shape": False, "mode": "apply_atomic"}
            ),
            "principal_schema:not_matching_validated_shape_batch",
        ),
    ],
)
def test_final_audit_requires_host_bound_paths_hashes_and_shape_input(
    tmp_path: Path, mutator, expected_error: str
) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    mutator(paths, runtime)
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert expected_error in audit["completion_gate_errors"]


def test_final_audit_refuses_failed_shape_apply_response(tmp_path: Path) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    _replace_host_response(
        paths,
        runtime,
        "shape_apply",
        {"attempt_status": "validation_failed", "batch_status": "validated", "mode": "apply_atomic"},
    )
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "principal_schema:not_matching_validated_shape_batch" in audit["completion_gate_errors"]


@pytest.mark.parametrize(
    ("omitted_receipt", "expected_error"),
    [
        ("principal_schema_dry_run", "principal_schema_dry_run:missing_or_invalid_receipt"),
        ("valid_instance_dry_run", "valid_instance_dry_run:missing_or_invalid_receipt"),
        ("valid_instance_apply", "valid_instance_apply:missing_or_invalid_receipt"),
        ("pre_checkpoint_get", "pre_checkpoint_get:missing_or_invalid_receipt"),
    ],
)
def test_final_audit_requires_every_new_host_bound_receipt(
    tmp_path: Path, omitted_receipt: str, expected_error: str
) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path, omit=omitted_receipt)
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert expected_error in audit["completion_gate_errors"]


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        (
            lambda paths, _runtime: _rewrite_audit_entry(
                paths,
                "shape_apply",
                request_summary={
                    "client_batch_id": "different-schema",
                    "contains_create_shape": True,
                    "items_sha256": "s" * 64,
                    "mode": "apply_atomic",
                },
            ),
            "principal_schema:not_matching_validated_shape_batch",
        ),
        (
            lambda paths, runtime: _replace_host_response(
                paths, runtime, "principal_schema_dry_run", {"attempt_status": "validation_failed", "mode": "dry_run"}
            ),
            "principal_schema:not_matching_validated_shape_batch",
        ),
        (
            lambda paths, runtime: _replace_host_response(
                paths, runtime, "valid_instance_dry_run", {"attempt_status": "validation_failed", "mode": "dry_run"}
            ),
            "valid_instance:not_matching_validated_apply",
        ),
        (
            lambda paths, _runtime: _rewrite_audit_entry(
                paths,
                "valid_instance_apply",
                request_summary={
                    "client_batch_id": "different-instance",
                    "command_kinds": ["create_entity"],
                    "items_sha256": "v" * 64,
                    "mode": "apply_atomic",
                },
            ),
            "valid_instance:not_matching_validated_apply",
        ),
        (
            lambda paths, runtime: _replace_host_response(
                paths, runtime, "pre_checkpoint_get", {"session": {"id": "session-1", "revision": 8}}
            ),
            "pre_checkpoint_get:session_revision_mismatch",
        ),
    ],
)
def test_final_audit_rejects_host_bound_principal_instance_and_precheckpoint_mismatches(
    tmp_path: Path, mutator, expected_error: str
) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    mutator(paths, runtime)
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert expected_error in audit["completion_gate_errors"]


def test_final_audit_rejects_non_2xx_valid_instance_host_response(tmp_path: Path) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    receipts = runtime["receipts"]
    assert isinstance(receipts, dict) and isinstance(receipts["valid_instance_apply"], dict)
    receipts["valid_instance_apply"]["status"] = 422
    _replace_host_response(
        paths,
        runtime,
        "valid_instance_apply",
        {"attempt_status": "applied", "batch_status": "applied", "mode": "apply_atomic"},
    )
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "valid_instance_apply:unexpected_receipt_status" in audit["completion_gate_errors"]


@pytest.mark.parametrize(
    "event",
    [
        {
            "at": "2026-07-27T00:00:04.500000+00:00",
            "method": "POST",
            "path": "/api/build-sessions/session-1/modeling-batches",
            "policy": "forwarded",
            "request_id": "extra-schema",
            "request_summary": {"command_kinds": ["create_shape"], "mode": "dry_run"},
        },
        {
            "at": "2026-07-27T00:00:07.500000+00:00",
            "method": "POST",
            "path": "/api/semantic/graph-sets/graph-set-1/rule-runs",
            "policy": "forwarded",
            "request_id": "rule-run",
            "request_summary": {},
        },
        {
            "at": "2026-07-27T00:00:07.500000+00:00",
            "method": "POST",
            "path": "/api/semantic/sparql:query",
            "policy": "forwarded",
            "request_id": "second-query",
            "request_summary": {},
        },
    ],
)
def test_final_audit_rejects_closed_plan_extra_post_shape_operations(tmp_path: Path, event: dict[str, object]) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path)
    _append_audit_event(paths, event)
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "timeline:closed_sequence_violation" in audit["completion_gate_errors"]


def test_final_audit_rejects_modeling_batch_probe_before_principal_anchor(tmp_path: Path) -> None:
    paths, _runtime = _write_final_audit_fixture(tmp_path)
    _prepend_audit_event(
        paths,
        {
            "at": "2026-07-27T00:00:00+00:00",
            "method": "POST",
            "path": "/api/build-sessions/session-1/modeling-batches",
            "policy": "forwarded",
            "request_id": "pre-principal-schema-probe",
            "request_summary": {
                "command_kinds": ["create_shape"],
                "contains_create_shape": True,
                "mode": "dry_run",
            },
        },
    )
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "timeline:pre_principal_probe" in audit["completion_gate_errors"]


def test_final_audit_rejects_schema_command_in_valid_instance_receipt(tmp_path: Path) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    _rewrite_audit_entry(
        paths,
        "valid_instance_dry_run",
        request_summary={
            "client_batch_id": "instance-1",
            "command_kinds": ["create_entity", "create_shape"],
            "contains_create_shape": True,
            "items_sha256": "v" * 64,
            "mode": "dry_run",
        },
    )
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "valid_instance:not_matching_validated_apply" in audit["completion_gate_errors"]
    assert "timeline:closed_sequence_violation" in audit["completion_gate_errors"]


def test_final_audit_rejects_core_checkpoint_after_600_seconds(tmp_path: Path) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    _rewrite_audit_entry(paths, "checkpoint", path="/api/build-sessions/session-1/checkpoints")
    entries = [json.loads(line) for line in paths["api_audit"].read_text(encoding="utf-8").splitlines()]
    for entry in entries:
        if entry.get("request_id") == runtime["receipts"]["checkpoint"]["request_id"]:
            entry["at"] = "2026-07-27T00:10:01+00:00"
    paths["api_audit"].write_text("\n".join(json.dumps(entry) for entry in entries) + "\n", encoding="utf-8")
    audit = launcher._final_audit(
        paths,
        "m4-final-audit",
        0,
        {"product_write_mode": "rdf_primary"},
        launcher.datetime(2026, 7, 27, tzinfo=launcher.UTC),
    )
    assert audit["status"] == "INCONCLUSIVE"
    assert "timeline:checkpoint_outside_core_window" in audit["completion_gate_errors"]


@pytest.mark.parametrize(
    "body",
    [
        {"result": {"results": {"bindings": [{"ok": {"value": "yes"}}]}}, "scope": {"status": "partial", "excluded_ontologies": [], "ontologies": []}, "truncated": False, "warnings": [{"code": "derived_result_missing", "message": "No current rule result pointer."}]},
        {"result": {"results": {"bindings": [{"ok": {"value": "yes"}}]}}, "scope": {"status": "complete", "excluded_ontologies": [], "ontologies": [{"ontology_id": "ontology-1", "derived_state": {"reasoning": {"status": "stale", "run_id": "reasoning-run-1"}, "rule": {"status": "missing"}}}]}, "truncated": False, "warnings": [{"code": "derived_result_missing", "message": "different"}]},
    ],
)
def test_final_audit_rejects_non_exact_optional_rule_warning_or_scope(tmp_path: Path, body: dict[str, object]) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    _replace_host_response(paths, runtime, "governed_query", body)
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")
    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})
    assert audit["status"] == "INCONCLUSIVE"
    assert "governed_query:invalid_optional_rule_absent_scope" in audit["completion_gate_errors"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", "different_code"),
        ("message", "Different message."),
        ("request_id", "different-request"),
        ("response_sha256", "0" * 64),
    ],
)
def test_final_audit_rejects_optional_rule_absent_evidence_mismatch(
    tmp_path: Path, field: str, value: str
) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    optional_rule_absent = runtime["optional_rule_absent"]
    assert isinstance(optional_rule_absent, dict)
    optional_rule_absent[field] = value
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")

    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})

    assert audit["status"] == "INCONCLUSIVE"
    assert "governed_query:missing_optional_rule_absent_decision" in audit["completion_gate_errors"]


def test_final_audit_uses_checkpoint_session_revision_for_checkpoint_and_complete(
    tmp_path: Path,
) -> None:
    paths, runtime = _write_final_audit_fixture(tmp_path)
    checkpoint = runtime["checkpoint"]
    assert isinstance(checkpoint, dict)
    checkpoint["session_revision"] = 8
    paths["workspace"].joinpath("runtime-record.json").write_text(json.dumps(runtime), encoding="utf-8")

    audit = launcher._final_audit(paths, "m4-final-audit", 0, {"product_write_mode": "rdf_primary"})

    assert audit["status"] == "INCONCLUSIVE"
    assert "checkpoint_response_mismatch" in audit["completion_gate_errors"]
    assert "complete_expected_revision_mismatch" in audit["completion_gate_errors"]


def test_generic_command_contract_requires_fields_and_completion_first_milestones() -> None:
    contract = (SCENARIO_ROOT / "input-pack" / "platform-modeling-command-contract.md").read_text(encoding="utf-8")
    for field in (
        "client_batch_id",
        "expected_workspace_version",
        "lease_token",
        "create_shape",
        "target_class_id",
        "validation-runs",
        "reasoning-runs",
        "sparql:query",
        "expected_revision",
        "latest_checkpoint_id",
        "default_graph_set_id",
        "enum_values",
        "attempt_status: \"validation_failed\"",
        "blocking finding",
        "generic instance commands `create_entity` and `create_relation`",
    ):
        assert field in contract
    milestones = [
        "**Principal schema dry-run**",
        "**Shape apply**",
        "**Independent invalid-instance dry-run**",
        "**Valid instance dry-run**",
        "**Valid instance apply**",
        "**Validation**",
        "**Reasoning**",
        "**Governed positive query**",
        "**Pre-checkpoint GET, checkpoint, complete, final GET**",
    ]
    assert [contract.index(milestone) for milestone in milestones] == sorted(
        contract.index(milestone) for milestone in milestones
    )
    assert '"expected_workspace_version":"workspace-version"' in contract
    assert "`symmetric`, `transitive`, `scope_policy`, `status`" in contract
    assert "`inverse_name`, `is_symmetric`" not in contract
    assert "`relation_id`, `properties`" not in contract


def test_generic_command_contract_command_fields_match_handler_allowlist_exactly() -> None:
    expected = {
        "create_class": {"class_id", "name", "description", "aliases", "parent_class_ids", "external_mappings"},
        "create_property": {"property_id", "class_id", "name", "description", "datatype", "object_class_id"},
        "create_relation_type": {
            "relation_type_id", "name", "source_class_id", "target_class_id", "description", "symmetric", "transitive", "scope_policy", "status"
        },
        "create_shape": {"shape_id", "target_class_id", "constraints"},
        "create_entity": {"entity_id", "class_iri_or_legacy_id", "label", "aliases", "properties"},
        "create_relation": {"source_entity_iri", "relation_type_iri", "target_entity_iri"},
    }
    assert {name: ALLOWED_FIELDS[name] for name in expected} == expected
    contract = (SCENARIO_ROOT / "input-pack" / "platform-modeling-command-contract.md").read_text(encoding="utf-8")
    expected_rows = {
        "create_class": "| `create_class` | `name` | `class_id`, `description`, `aliases`, `parent_class_ids`, `external_mappings` |",
        "create_property": "| `create_property` | `class_id`, `name`, exactly one of `datatype` or `object_class_id` | `property_id`, `description` |",
        "create_relation_type": "| `create_relation_type` | `name`, `source_class_id`, `target_class_id` | `relation_type_id`, `description`, `symmetric`, `transitive`, `scope_policy`, `status` |",
        "create_shape": "| `create_shape` | `target_class_id`, `constraints` | `shape_id` |",
        "create_entity": "| `create_entity` | `class_iri_or_legacy_id`, `label` | `entity_id`, `aliases`, `properties` |",
        "create_relation": "| `create_relation` | `source_entity_iri`, `relation_type_iri`, `target_entity_iri` | none |",
    }
    for command_kind, row in expected_rows.items():
        assert f"`{command_kind}`" in row
        assert row in contract


def test_workspace_roles_are_exact_and_empty_ready_workspace_stages_for_first_batch(
    tmp_path: Path,
) -> None:
    contract_path = SCENARIO_ROOT / "input-pack" / "platform-modeling-command-contract.md"
    contract = contract_path.read_text(encoding="utf-8")
    required_rules = (
        "Workspace member `role` values returned by the platform are authoritative.",
        "`asserted_ontology`, `asserted_data`, `shapes`, and `policy`",
        "do not locally abbreviate, rename, translate, or infer any role",
        "A fresh workspace reported ready may\n   proceed to the first Modeling Batch even when its initial hashes are empty and every resource count is\n   zero.",
        "Block only when a required member is actually absent or the workspace is reported non-ready.",
    )
    for rule in required_rules:
        assert rule in contract

    prepared = launcher.prepare_run(tmp_path / "prepare-only", "baseline", "m4-role-prepare")
    staged_contract = (
        tmp_path / "prepare-only" / "agent-input" / "platform" / "modeling-command-contract.md"
    )
    manifest = launcher.read_manifest()
    manifest_item = next(
        item
        for item in manifest["files"]
        if item["mounted_path"] == "platform/modeling-command-contract.md"
    )

    assert prepared["status"] == "PREPARED"
    assert staged_contract.read_text(encoding="utf-8") == contract
    assert hashlib.sha256(staged_contract.read_bytes()).hexdigest() == manifest_item["sha256"]


def test_agent_visible_id_integrity_rules_cover_all_scoped_paths_and_fail_closed() -> None:
    documents = [
        (SCENARIO_ROOT / "input-pack" / "modeling-agent-prompt.md").read_text(encoding="utf-8"),
        (SCENARIO_ROOT / "input-pack" / "platform-modeling-command-contract.md").read_text(
            encoding="utf-8"
        ),
    ]
    required_rules = (
        "Immediately atomically persist every returned Project, Ontology, and Build Session ID",
        "`runtime-record.json.resource_ids.project_id`, `.ontology_id`, and `.build_session_id`",
        "For **every** Project-, Ontology-, or Build Session-scoped API path, just before publishing",
        "read the corresponding ID just-in-time from that persisted runtime record",
        "child-resource\ncreation, ontology context, lease, Modeling Batch, Build Session GET, checkpoint, complete, and final\nGET paths",
        "declare every\nsuch scratch variable `local`",
        "assert that every Project, Ontology, or Build Session ID embedded in the path equals the\nmatching persisted runtime-record ID",
        "rebuild the request locally from the\nruntime record or atomically record `BLOCKED`; never forward a mismatched path",
    )

    for document in documents:
        for rule in required_rules:
            assert rule in document


def test_input_manifest_hashes_every_agent_visible_source_after_id_integrity_update() -> None:
    manifest = launcher.read_manifest()

    for item in manifest["files"]:
        source = launcher.REPOSITORY_ROOT / item["source_path"]
        assert source.is_file()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == item["sha256"]
