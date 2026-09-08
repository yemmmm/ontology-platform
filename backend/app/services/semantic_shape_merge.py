"""Merge generated and custom SHACL shape guidance (Stage 2 §3.4.2).

Both inputs are ``ShaclFormGuidance`` dicts of the shape consumed by the
frontend ``ShaclFormRenderer``. The merged output adds a ``provenance``
marker (``"generated"`` / ``"custom"`` / ``"merged"``) to each field so
the UI can badge user-authored constraints distinctly from generator
output.

R3.0-009 §6.1 adds ``merge_shape_guidance_multi`` for the entity path: it
merges any number of sources, keeps every still-effective constraint and
raises a locatable ``shape_conflict`` instead of silently keeping the last
writer when two shapes constrain the same path differently.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

# Constraint keys compared across sources; two shapes that bind the same path
# with different values for any of these are a real conflict.
_CONFLICT_KEYS = (
    "datatype",
    "class_iri",
    "min_count",
    "max_count",
    "pattern",
    "enumeration",
)


class ShapeGuidanceConflict(RuntimeError):
    """Two still-effective shapes constrain the same path differently."""

    code = "shape_conflict"
    status_code = 409


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


def merge_shape_guidance_multi(
    sources: Iterable[tuple[str, dict[str, Any] | None]],
) -> dict[str, Any]:
    """Merge shape guidance from any number of sources without dropping constraints.

    Every source contributes ``(label, guidance)``; guidance fields are grouped
    by ``path`` and annotated with the source label and shape IRI they came
    from. Fields from different source shapes that bind the same path with
    conflicting constraint values raise :class:`ShapeGuidanceConflict` naming
    the path, the key, both values and both sources — the merge never guesses a
    priority and never drops a still-effective constraint.
    """
    merged_fields: list[dict[str, Any]] = []
    by_path: dict[str, dict[str, Any]] = {}
    all_targets: list[dict[str, Any]] = []
    shape_iris: list[str] = []

    for label, guidance in sources:
        for field in (guidance or {}).get("fields") or []:
            path = field.get("path") or field.get("name")
            if path is None:
                continue
            source_shape = field.get("source_shape_iri") or ""
            entry = by_path.get(path)
            if entry is None:
                entry = {**field, "sources": [label], "provenance": label}
                by_path[path] = entry
                merged_fields.append(entry)
                continue
            if entry.get("source_shape_iri") == source_shape and source_shape:
                # Same source shape restating the constraint: fill in keys it
                # does not already carry.
                for key, value in field.items():
                    entry.setdefault(key, value)
                continue
            _check_conflict(path, entry, field, entry.get("sources") or [], label)
            for key, value in field.items():
                if key not in entry or entry.get(key) is None:
                    entry[key] = value
            if label not in entry["sources"]:
                entry["sources"].append(label)
            entry["provenance"] = (
                "merged" if len(entry["sources"]) > 1 else entry["sources"][0]
            )
        all_targets.extend((guidance or {}).get("targets") or [])
        shape_iris.extend((guidance or {}).get("shape_iris") or [])

    result: dict[str, Any] = {
        "fields": merged_fields,
        "targets": all_targets,
        "shape_iris": sorted(set(shape_iris)),
    }
    return result


def _check_conflict(
    path: Any,
    existing: dict[str, Any],
    incoming: dict[str, Any],
    existing_sources: list[str],
    incoming_source: str,
) -> None:
    for key in _CONFLICT_KEYS:
        if key not in existing or key not in incoming:
            continue
        left = existing.get(key)
        right = incoming.get(key)
        if left == right:
            continue
        raise ShapeGuidanceConflict(
            "shape_conflict: path "
            f"{path} is constrained differently by "
            f"{', '.join(existing_sources)} ({key}={left!r}) and "
            f"{incoming_source} ({key}={right!r}); "
            "align the shapes or split the target"
        )

