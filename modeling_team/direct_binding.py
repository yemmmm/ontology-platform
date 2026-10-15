"""Runner-side binding for the R4.3-025 direct execution boundary.

DirectModelExecutor deliberately receives already bound platform items.  This
module is the small capability-layer coordinator that runs the compiler's
dependency ordered phases, binds cross-batch item_ref values from observed
outputs, and leaves same-batch references for the platform Batch service.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from .direct_execution import RESULT_SCHEMA


_OUTPUT_KEYS = ("resource_id", "resource_iri", "statement", "fact")


class _BindingError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        item_id: str | None = None,
        path: str = "",
        target: str | None = None,
        output: str | None = None,
        target_batch: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.item_id = item_id
        self.path = path
        self.target = target
        self.output = output
        self.target_batch = target_batch


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _pointer_segment(value: Any) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _batch_index(batch: Any, position: int) -> int:
    if isinstance(batch, Mapping) and type(batch.get("batch_index", position)) is int:
        return int(batch.get("batch_index", position))
    return position


def _source_entries(source_map: Mapping[str, Any], batch_index: int) -> Mapping[str, Any]:
    nested = source_map.get(str(batch_index))
    if nested is None:
        nested = source_map.get(batch_index)
    return nested if isinstance(nested, Mapping) else {}


def _source_entry(source_map: Mapping[str, Any], batch_index: int, item_id: str) -> Mapping[str, Any]:
    value = _source_entries(source_map, batch_index).get(item_id)
    return value if isinstance(value, Mapping) else {}


def _dependency_indexes(
    batch: Mapping[str, Any],
    batch_index: int,
    source_map: Mapping[str, Any],
) -> set[int]:
    dependencies: set[int] = set()
    values = batch.get("depends_on_batches")
    if isinstance(values, list):
        dependencies.update(value for value in values if type(value) is int and value >= 0)
    for entry in _source_entries(source_map, batch_index).values():
        if not isinstance(entry, Mapping):
            continue
        edges = entry.get("cross_batch_dependencies")
        if not isinstance(edges, list):
            continue
        for edge in edges:
            if isinstance(edge, Mapping) and type(edge.get("depends_on_batch")) is int:
                dependency = int(edge["depends_on_batch"])
                if dependency >= 0:
                    dependencies.add(dependency)
    return dependencies


def _phase_source_map(source_map: Mapping[str, Any], batch_index: int) -> dict[str, dict[str, Any]]:
    """Keep field mapping while preventing the Executor from re-attaching edges.

    The original source_map remains the coordinator's source of truth.  The
    Executor sees only the current phase because prior phases are already
    represented by their durable receipt and the dependency coordinator.
    """

    entries = _source_entries(source_map, batch_index)
    phase: dict[str, Any] = {}
    for item_id, value in entries.items():
        if not isinstance(value, Mapping):
            phase[str(item_id)] = value
            continue
        entry = deepcopy(dict(value))
        entry.pop("cross_batch_dependencies", None)
        phase[str(item_id)] = entry
    return {str(batch_index): phase}


def _edge_batch(
    source_map: Mapping[str, Any],
    batch_index: int,
    item_id: str,
    target: str,
) -> int | None:
    entry = _source_entry(source_map, batch_index, item_id)
    edges = entry.get("cross_batch_dependencies")
    if not isinstance(edges, list):
        return None
    values = {
        int(edge["depends_on_batch"])
        for edge in edges
        if isinstance(edge, Mapping)
        and edge.get("depends_on") == target
        and type(edge.get("depends_on_batch")) is int
    }
    return next(iter(values)) if len(values) == 1 else None


def _declared_reference(
    source_map: Mapping[str, Any],
    batch_index: int,
    item_id: str,
    path: str,
    target: str | None,
    output: str | None,
) -> bool:
    """Return whether this exact payload pointer is a compiler reference slot.

    New compiler output may carry reference_slots as JSON Pointer keys.
    Until that metadata is present, the existing cross dependency edge is the
    narrow declaration available: only an item_ref whose target is an edge for
    this item is eligible for binding.  An unrelated literal item_ref is kept
    as literal data.
    """

    entry = _source_entry(source_map, batch_index, item_id)
    slots = entry.get("reference_slots")
    if isinstance(slots, Mapping):
        value = slots.get(path)
        if value is None:
            value = slots.get(path.lstrip("/"))
        if value is None:
            return False
        if isinstance(value, Mapping):
            declared_target = value.get("depends_on") or value.get("client_item_id")
            declared_output = value.get("output")
            if declared_target is not None and declared_target != target:
                return False
            if declared_output is not None and declared_output != output:
                return False
        elif isinstance(value, str) and value != target:
            return False
        return True
    if isinstance(slots, list):
        for slot in slots:
            if isinstance(slot, str) and slot == path:
                return True
            if not isinstance(slot, Mapping):
                continue
            slot_path = slot.get("path") or slot.get("payload_path")
            if slot_path != path and slot_path != path.lstrip("/"):
                continue
            declared_target = slot.get("depends_on") or slot.get("client_item_id")
            declared_output = slot.get("output")
            return (
                (declared_target is None or declared_target == target)
                and (declared_output is None or declared_output == output)
            )
        return False

    edges = entry.get("cross_batch_dependencies")
    if not isinstance(edges, list):
        return False
    return any(
        isinstance(edge, Mapping)
        and edge.get("depends_on") == target
        and (edge.get("output") is None or edge.get("output") == output)
        for edge in edges
    )


def _bind_batch(
    batch: Mapping[str, Any],
    batch_index: int,
    source_map: Mapping[str, Any],
    outputs: Mapping[tuple[int, str], Mapping[str, Any]],
) -> dict[str, Any]:
    items = batch.get("items")
    if not isinstance(items, list):
        raise _BindingError("batch_items_required", "each binding phase needs an items list")
    current_ids = {
        str(item.get("client_item_id"))
        for item in items
        if isinstance(item, Mapping) and isinstance(item.get("client_item_id"), str)
    }
    candidate_outputs: dict[str, list[Mapping[str, Any]]] = {}
    for (prior_batch, client_item_id), value in outputs.items():
        if prior_batch < batch_index:
            candidate_outputs.setdefault(client_item_id, []).append(value)

    def resolve(value: Any, item_id: str, path: str) -> Any:
        if isinstance(value, Mapping):
            if set(value) == {"item_ref"} and isinstance(value.get("item_ref"), Mapping):
                ref = value["item_ref"]
                target_value = ref.get("client_item_id")
                output_value = ref.get("output")
                target = str(target_value) if isinstance(target_value, str) else None
                output = str(output_value) if isinstance(output_value, str) else None
                if not _declared_reference(
                    source_map,
                    batch_index,
                    item_id,
                    path,
                    target,
                    output,
                ):
                    return deepcopy(dict(value))
                if target is None or output is None:
                    raise _BindingError(
                        "item_ref_invalid",
                        "item_ref requires client_item_id and output",
                        item_id=item_id,
                        path=path,
                    )
                # The platform owns same-batch item_ref resolution.
                if target in current_ids:
                    return deepcopy(dict(value))
                target_batch = _edge_batch(source_map, batch_index, item_id, target)
                if target_batch is not None:
                    observed = outputs.get((target_batch, target))
                else:
                    matches = candidate_outputs.get(target, [])
                    observed = matches[0] if len(matches) == 1 else None
                    if len(matches) > 1:
                        raise _BindingError(
                            "cross_batch_output_ambiguous",
                            "a cross-batch item reference has multiple observed outputs",
                            item_id=item_id,
                            path=path,
                            target=target,
                            output=output,
                        )
                if not isinstance(observed, Mapping) or observed.get(output) is None:
                    raise _BindingError(
                        "cross_batch_output_unavailable",
                        "a cross-batch item reference has no successful observed output",
                        item_id=item_id,
                        path=path,
                        target=target,
                        output=output,
                        target_batch=target_batch,
                    )
                return deepcopy(observed[output])
            return {
                str(key): resolve(child, item_id, f"{path}/{_pointer_segment(key)}")
                for key, child in value.items()
            }
        if isinstance(value, list):
            return [resolve(child, item_id, f"{path}/{index}") for index, child in enumerate(value)]
        return value

    bound_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise _BindingError("item_invalid", "compiled item is not an object")
        item_id = str(item.get("client_item_id"))
        bound = deepcopy(dict(item))
        bound["payload"] = resolve(item.get("payload"), item_id, "/payload")
        source = _source_entry(source_map, batch_index, item_id)
        for deferred in source.get("deferred_property_keys", []):
            ref = deferred["property_ref"]["item_ref"]
            target = ref["client_item_id"]
            prior_batch = _edge_batch(source_map, batch_index, item_id, target)
            observed = outputs.get((prior_batch, target))
            iri = observed.get("resource_iri") if isinstance(observed, Mapping) else None
            if not isinstance(iri, str) or not iri:
                raise _BindingError(
                    "cross_batch_output_unavailable", "The property key needs its successful prior resource output",
                    item_id=item_id, path=deferred["property_ref_source"], target=target,
                    output="resource_iri", target_batch=prior_batch,
                )
            properties = bound["payload"]["properties"]
            if iri in properties:
                raise _BindingError(
                    "duplicate_entity_property", "Two declared property keys resolve to the same property",
                    item_id=item_id, path=deferred["property_ref_source"], target=target,
                )
            properties[iri] = deepcopy(deferred["value"])
            # The final key exists only after the real output is known. Keep
            # platform findings tied to the original property/value inputs.
            source["field_map"][f"/payload/properties/{_pointer_segment(iri)}"] = [
                deferred["property_ref_source"], deferred["value_source"],
            ]
        bound_items.append(bound)
    result = deepcopy(dict(batch))
    result["items"] = bound_items
    return result


def _capture_outputs(
    batch: Mapping[str, Any],
    batch_index: int,
    row: Mapping[str, Any],
    outputs: dict[tuple[int, str], Mapping[str, Any]],
) -> None:
    bindings = row.get("resource_bindings")
    if not isinstance(bindings, list):
        bindings = []
    by_client_id = {
        str(binding.get("client_item_id")): binding
        for binding in bindings
        if isinstance(binding, Mapping) and isinstance(binding.get("client_item_id"), str)
    }
    items = batch.get("items")
    if not isinstance(items, list):
        return
    for position, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        client_item_id = item.get("client_item_id")
        if not isinstance(client_item_id, str):
            continue
        binding = by_client_id.get(client_item_id)
        if binding is None and position < len(bindings) and isinstance(bindings[position], Mapping):
            binding = bindings[position]
        if not isinstance(binding, Mapping):
            continue
        observed: dict[str, Any] = {}
        nested = binding.get("resource_outputs")
        if isinstance(nested, Mapping):
            observed.update({key: nested[key] for key in _OUTPUT_KEYS if nested.get(key) is not None})
        observed.update({key: binding[key] for key in _OUTPUT_KEYS if binding.get(key) is not None})
        if observed:
            outputs[(batch_index, client_item_id)] = observed


def _mapped_path(entry: Mapping[str, Any], path: str) -> str:
    if path.startswith(("/items/", "/changes/")):
        return path
    field_map = entry.get("field_map")
    if isinstance(field_map, Mapping):
        for payload_pointer, candidate_paths in field_map.items():
            candidates = {
                str(payload_pointer),
                str(payload_pointer).lstrip("/"),
            }
            if path in candidates or path.lstrip("/") in candidates:
                if isinstance(candidate_paths, list) and candidate_paths:
                    first = candidate_paths[0]
                    if isinstance(first, str) and first:
                        return first
    base = entry.get("candidate_path") or entry.get("json_pointer") or entry.get("path")
    if isinstance(base, str) and base:
        return base.rstrip("/") + (path if path.startswith("/") else f"/{path}" if path else "")
    return path


def _binding_error(
    error: _BindingError,
    *,
    source_map: Mapping[str, Any],
    batch_index: int,
    ontology_id: Any,
) -> dict[str, Any]:
    entry = _source_entry(source_map, batch_index, error.item_id or "")
    change_id = entry.get("change_id") or error.item_id
    source_item_id = entry.get("item_id") or error.item_id
    actual: dict[str, Any] = {}
    if error.target is not None:
        actual["depends_on"] = error.target
    if error.output is not None:
        actual["output"] = error.output
    if error.target_batch is not None:
        actual["depends_on_batch"] = error.target_batch
    return {
        "code": error.code,
        "change_id": change_id,
        "item_id": source_item_id,
        "path": _mapped_path(entry, error.path),
        "message": error.message,
        "expected": None,
        "actual": actual or None,
        "platform_ref": None,
        "retryable": True,
        "ontology_id": ontology_id,
    }


def _pending(
    batch: Mapping[str, Any],
    batch_index: int,
    *,
    reason: str,
    dependencies: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    items = batch.get("items")
    if not isinstance(items, list):
        return []
    return [
        {
            "batch_index": batch_index,
            "ontology_id": batch.get("ontology_id"),
            "client_item_id": item.get("client_item_id"),
            "reason": reason,
            **({"dependencies": list(dependencies)} if dependencies else {}),
        }
        for item in items
        if isinstance(item, Mapping)
    ]


def _usable(row: Mapping[str, Any], phase_status: Any) -> bool:
    return (
        row.get("write_state") == "applied"
        and row.get("attempt_status") != "partially_applied"
        and phase_status == "completed"
    )


def _aggregate(
    *,
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    state_by_index: Mapping[int, Mapping[str, Any]],
    first_phase: Mapping[str, Any] | None,
    batches: Sequence[Mapping[str, Any]],
    source_map: Mapping[str, Any],
) -> dict[str, Any]:
    states = [row.get("write_state") for row in rows]
    row_errors = [error for row in rows for error in row.get("errors", [])]
    has_errors = bool(errors or row_errors)
    has_uncertain = any(
        state.get("write_state") == "uncertain" or state.get("phase_status") == "uncertain"
        for state in state_by_index.values()
    ) or any(state == "uncertain" for state in states)
    has_partial_applied = any(row.get("attempt_status") == "partially_applied" for row in rows)
    if has_uncertain:
        status = "uncertain"
    elif any(state == "applied" for state in states) and (
        any(state == "not_written" for state in states)
        or pending
        or has_errors
        or has_partial_applied
        or any(state.get("write_state") == "not_written" for state in state_by_index.values())
    ):
        status = "partial"
    elif rows and all(state == "applied" for state in states) and not pending and not has_errors:
        status = "completed"
    elif rows or errors or pending:
        status = "not_written"
    else:
        status = "completed"
    digest = _digest(
        {
            "batch_indexes": [_batch_index(batch, position) for position, batch in enumerate(batches)],
            "source_map": source_map,
        }
    )
    return {
        "schema_version": RESULT_SCHEMA,
        "submission_ref": (
            first_phase.get("submission_ref")
            if isinstance(first_phase, Mapping) and first_phase.get("submission_ref")
            else f"bound:{digest[:16]}"
        ),
        "submission_digest": (
            first_phase.get("submission_digest")
            if isinstance(first_phase, Mapping) and first_phase.get("submission_digest")
            else f"sha256:{digest}"
        ),
        "status": status,
        "batches": rows,
        "errors": errors + row_errors,
        "pending_changes": pending,
    }


def execute_bound_model_changes(
    executor: Any,
    batches: Sequence[Mapping[str, Any]],
    source_map: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute dependency phases after binding cross-batch outputs.

    The function deliberately calls executor.execute once per phase.  A
    completed phase is represented by its original batch_index and actual
    resource bindings; a later phase is never submitted while any of its
    dependency batches are failed, partial, or uncertain.
    """

    source_map = source_map if isinstance(source_map, Mapping) else {}
    if not isinstance(batches, Sequence) or isinstance(batches, (str, bytes)):
        return executor.execute(batches, source_map)
    ordered = sorted(
        enumerate(batches),
        key=lambda pair: (_batch_index(pair[1], pair[0]), pair[0]),
    )
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    outputs: dict[tuple[int, str], Mapping[str, Any]] = {}
    state_by_index: dict[int, dict[str, Any]] = {}
    first_phase: Mapping[str, Any] | None = None

    for position, batch in ordered:
        batch_index = _batch_index(batch, position)
        if not isinstance(batch, Mapping):
            phase = executor.execute([batch], _phase_source_map(source_map, batch_index))
            if first_phase is None:
                first_phase = phase
            errors.extend(phase.get("errors", []) if isinstance(phase, Mapping) else [])
            pending.extend(phase.get("pending_changes", []) if isinstance(phase, Mapping) else [])
            state_by_index[batch_index] = {
                "write_state": "uncertain" if phase.get("status") == "uncertain" else "not_written",
                "phase_status": phase.get("status"),
            }
            continue

        dependencies = _dependency_indexes(batch, batch_index, source_map)
        blocked = [
            dependency
            for dependency in sorted(dependencies)
            if not _usable(
                state_by_index.get(
                    dependency,
                    {"write_state": "not_written", "attempt_status": None},
                ),
                state_by_index.get(dependency, {}).get("phase_status"),
            )
        ]
        if blocked:
            names = [f"batch:{dependency}" for dependency in blocked]
            pending.extend(
                _pending(
                    batch,
                    batch_index,
                    reason="dependency_not_applied",
                    dependencies=names,
                )
            )
            state_by_index[batch_index] = {"write_state": "not_written", "phase_status": "not_written"}
            continue

        try:
            bound = _bind_batch(batch, batch_index, source_map, outputs)
        except _BindingError as exc:
            errors.append(
                _binding_error(
                    exc,
                    source_map=source_map,
                    batch_index=batch_index,
                    ontology_id=batch.get("ontology_id"),
                )
            )
            pending.extend(_pending(batch, batch_index, reason=exc.code))
            state_by_index[batch_index] = {"write_state": "not_written", "phase_status": "not_written"}
            continue

        # The coordinator has already checked predecessor phases.  The
        # Executor receives only this executable phase, so its local dependency
        # check must not look for predecessor rows that are intentionally
        # outside this call.
        bound["depends_on_batches"] = []
        phase = executor.execute([bound], _phase_source_map(source_map, batch_index))
        if first_phase is None:
            first_phase = phase
        phase_rows = phase.get("batches") if isinstance(phase, Mapping) else []
        phase_status = phase.get("status") if isinstance(phase, Mapping) else "uncertain"
        errors.extend(phase.get("errors", []) if isinstance(phase, Mapping) else [])
        pending.extend(phase.get("pending_changes", []) if isinstance(phase, Mapping) else [])
        if isinstance(phase_rows, list) and phase_rows:
            selected: Mapping[str, Any] | None = None
            for raw_row in phase_rows:
                if not isinstance(raw_row, Mapping):
                    continue
                row = dict(raw_row)
                row.setdefault("batch_index", batch_index)
                rows.append(row)
                if selected is None:
                    selected = row
            if selected is not None:
                state_by_index[batch_index] = {
                    "write_state": selected.get("write_state"),
                    "attempt_status": selected.get("attempt_status"),
                    "phase_status": phase_status,
                }
                if _usable(selected, phase_status):
                    _capture_outputs(batch, batch_index, selected, outputs)
        else:
            state_by_index[batch_index] = {
                "write_state": "uncertain" if phase_status == "uncertain" else "not_written",
                "phase_status": phase_status,
            }

    return _aggregate(
        rows=rows,
        errors=errors,
        pending=pending,
        state_by_index=state_by_index,
        first_phase=first_phase,
        batches=batches,
        source_map=source_map,
    )


__all__ = ["execute_bound_model_changes"]
