"""Merge generated and custom SHACL shape guidance (Stage 2 §3.4.2).

Both inputs are ``ShaclFormGuidance`` dicts of the shape consumed by the
frontend ``ShaclFormRenderer``. The merged output adds a ``provenance``
marker (``"generated"`` / ``"custom"`` / ``"merged"``) to each field so
the UI can badge user-authored constraints distinctly from generator
output.
"""

from __future__ import annotations

from typing import Any


def merge_shape_guidance(
    generated: dict[str, Any] | None,
    custom: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge two shape-guidance dicts, marking each field's provenance.

    - Field present only in ``generated`` → ``provenance="generated"``.
    - Field present only in ``custom`` → ``provenance="custom"``.
    - Field present in both → ``provenance="merged"``; ``custom`` wins
      on conflicting keys, ``generated`` fills in keys ``custom`` lacks.
    - ``target_class`` / ``target_class_label`` come from ``generated``
      unless ``custom`` overrides them.
    """
    generated = generated or {}
    custom = custom or {}

    merged_fields: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}

    for field in generated.get("fields") or []:
        path = field.get("path") or field.get("name")
        if path is None:
            continue
        merged = {**field, "provenance": "generated"}
        by_path[path] = merged
        merged_fields.append(merged)

    for field in custom.get("fields") or []:
        path = field.get("path") or field.get("name")
        if path is None:
            continue
        existing = by_path.get(path)
        if existing is None:
            merged = {**field, "provenance": "custom"}
            by_path[path] = merged
            merged_fields.append(merged)
        else:
            existing.update(field)
            existing["provenance"] = "merged"

    target_class = custom.get("target_class") or generated.get("target_class")
    target_class_label = (
        custom.get("target_class_label") or generated.get("target_class_label")
    )
    shape_iri = custom.get("shape_iri") or generated.get("shape_iri")

    result: dict[str, Any] = {"fields": merged_fields}
    if target_class is not None:
        result["target_class"] = target_class
    if target_class_label is not None:
        result["target_class_label"] = target_class_label
    if shape_iri is not None:
        result["shape_iri"] = shape_iri
    return result
