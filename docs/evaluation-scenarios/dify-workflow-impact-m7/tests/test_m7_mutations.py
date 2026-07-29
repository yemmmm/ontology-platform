from __future__ import annotations

from pathlib import Path
import sys


SCENARIO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCENARIO_ROOT))

from m7_evaluation import evaluate_projection  # noqa: E402
from m7_host import mutate_projection  # noqa: E402


def projection() -> dict[str, object]:
    return {
        "bindings": [{"id": "c-to-b-score"}, {"id": "template-to-output"}],
        "variables": {"quality_rating": {"datatype": "xsd:number"}},
        "output_uses": [{"branch": "passing", "variable": "approved_content"}],
        "nodes": [{"id": "template", "name": "Template", "bound": True}],
    }


def test_three_semantic_mutations_change_validation_or_cq_proof() -> None:
    baseline = projection()
    accepted = evaluate_projection(baseline)
    assert accepted["validation"]["conforms"] is True and accepted["cq1"]["complete"] is True
    missing_binding = evaluate_projection(mutate_projection(baseline, "remove_score_binding"))
    assert missing_binding["validation"]["conforms"] is False
    assert missing_binding["cq1"] == {"complete": False, "proof": []}
    wrong_type = evaluate_projection(mutate_projection(baseline, "incompatible_quality_type"))
    assert wrong_type["validation"]["conforms"] is False
    assert wrong_type["cq1"]["complete"] is False
    unavailable = evaluate_projection(mutate_projection(baseline, "unavailable_branch_output"))
    assert unavailable["validation"]["conforms"] is False
    assert unavailable["cq2"]["complete"] is False
    assert baseline["variables"]["quality_rating"]["datatype"] == "xsd:number"


def test_same_name_decoy_has_no_binding_path() -> None:
    result = mutate_projection(projection(), "same_name_decoy")
    decoy = next(node for node in result["nodes"] if node["id"] == "decoy-template")
    assert decoy["name"] == "Template" and decoy["bound"] is False
    assert "decoy-template" not in evaluate_projection(result)["cq3"]["affected_nodes"]
