"""Tests for the SHACL shape guidance merge function (Stage 2 §3.4.2).

The merge takes two ``ShaclFormGuidance`` dicts — one derived from the
``generated`` sub-graph and one from the ``custom`` sub-graph — and
produces a merged dict where each field carries a ``provenance`` marker.
"""

from __future__ import annotations

from app.services.semantic_shape_merge import merge_shape_guidance


def _field(path: str, **kwargs):
    base = {"path": path, "name": path, "label": path}
    base.update(kwargs)
    return base


def test_generated_only_field_keeps_generated_provenance():
    generated = {
        "target_class": "http://example.org/Student",
        "fields": [_field("http://example.org/name", datatype="xsd:string")],
    }
    custom = {"target_class": "http://example.org/Student", "fields": []}

    merged = merge_shape_guidance(generated, custom)

    fields_by_path = {f["path"]: f for f in merged["fields"]}
    assert fields_by_path["http://example.org/name"]["provenance"] == "generated"
    assert fields_by_path["http://example.org/name"]["datatype"] == "xsd:string"


def test_custom_only_field_gets_custom_provenance():
    generated = {"target_class": "http://example.org/Student", "fields": []}
    custom = {
        "target_class": "http://example.org/Student",
        "fields": [_field("http://example.org/email", datatype="xsd:string", min_count=1)],
    }

    merged = merge_shape_guidance(generated, custom)

    fields_by_path = {f["path"]: f for f in merged["fields"]}
    assert fields_by_path["http://example.org/email"]["provenance"] == "custom"
    assert fields_by_path["http://example.org/email"]["min_count"] == 1


def test_field_in_both_gets_merged_provenance_with_custom_winning():
    generated = {
        "target_class": "http://example.org/Student",
        "fields": [_field("http://example.org/name", datatype="xsd:string")],
    }
    custom = {
        "target_class": "http://example.org/Student",
        "fields": [_field("http://example.org/name", datatype="xsd:string", min_count=1)],
    }

    merged = merge_shape_guidance(generated, custom)

    fields_by_path = {f["path"]: f for f in merged["fields"]}
    field = fields_by_path["http://example.org/name"]
    assert field["provenance"] == "merged"
    # Custom wins on overlapping fields.
    assert field["min_count"] == 1
    # Generated contributes the datatype since custom does not set it.
    assert field["datatype"] == "xsd:string"


def test_merge_preserves_target_class_and_label_from_generated_when_custom_lacks_them():
    generated = {
        "target_class": "http://example.org/Student",
        "target_class_label": "Student",
        "fields": [],
    }
    custom = {"fields": []}

    merged = merge_shape_guidance(generated, custom)

    assert merged["target_class"] == "http://example.org/Student"
    assert merged["target_class_label"] == "Student"


def test_custom_target_class_overrides_generated():
    generated = {"target_class": "http://example.org/Student", "fields": []}
    custom = {"target_class": "http://example.org/Learner", "fields": []}

    merged = merge_shape_guidance(generated, custom)

    assert merged["target_class"] == "http://example.org/Learner"
