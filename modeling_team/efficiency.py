"""R4.3 local round timing over retained Host records, never a semantic judge.

The supplied completion references must be independently checked by Delivery.
This utility measures their recorded time window; it cannot establish PASS.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

_IDENTITY_FIELDS = {"materials_digest", "question_set", "model_effort", "configuration", "code_commit", "scope"}


def _identity(value: dict) -> dict:
    if not isinstance(value, dict) or any(not value.get(key) for key in _IDENTITY_FIELDS):
        raise ValueError("identity needs materials, question version, scope, model/effort, configuration and code commit")
    return value


def _time(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timestamps require an explicit timezone")
    return stamp.astimezone(timezone.utc)


def begin_round(path: Path, *, identity: dict, start_reference: str, started_at: str) -> dict:
    """Create once when authorized inputs are ready, before launch preparation."""
    _time(started_at)
    _identity(identity)
    if not isinstance(start_reference, str) or not start_reference:
        raise ValueError("record the start authorization and comparison identity")
    record = {
        "schema_version": "r4-3-efficiency-round/v1", "started_at": started_at,
        "start_reference": start_reference, "identity": identity,
        "run_ids": [], "intervals": [], "completion": None,
    }
    with path.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
    return record


def _union_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return sum((end - start).total_seconds() for start, end in merged)


def summarize_round(record: dict, *, observed_at: str) -> dict:
    """Measure one unchanged start across retries, preserving unknown activities."""
    if record.get("schema_version") != "r4-3-efficiency-round/v1":
        raise ValueError("expected r4-3-efficiency-round/v1")
    _identity(record["identity"])
    start = _time(record["started_at"])
    completion = record.get("completion") or {}
    refs = completion.get("acceptance_references")
    complete = (completion.get("independent_full_pass") is True
                and isinstance(refs, list) and bool(refs)
                and all(isinstance(ref, str) and ref.strip() for ref in refs)
                and isinstance(completion.get("cleanup_reference"), str)
                and bool(completion["cleanup_reference"].strip())
                and bool(completion.get("completed_at")))
    end = _time(completion["completed_at"] if complete else observed_at)
    if end < start or end > _time(observed_at):
        raise ValueError("round window is negative or ends after observation")
    categories: dict[str, list[tuple[datetime, datetime]]] = {}
    faults: list[tuple[datetime, datetime]] = []
    missing: list[str] = []
    for index, interval in enumerate(record.get("intervals", [])):
        category = interval["category"]
        if not interval.get("ended_at") or not interval.get("evidence_reference"):
            missing.append(f"interval {index}: no end or evidence; duration remains unknown")
            continue
        a, b = _time(interval["started_at"]), _time(interval["ended_at"])
        if a < start or b > end or b < a:
            raise ValueError(f"interval {index} is outside the round window")
        categories.setdefault(category, []).append((a, b))
        if (category in {"platform-contract", "runtime/infrastructure"}
                and interval.get("blocks_critical_path") is True):
            faults.append((a, b))
    wall = (end - start).total_seconds()
    blocked = _union_seconds(faults)
    return {
        "started_at": record["started_at"], "measured_until": end.isoformat(),
        "completion_recorded": complete, "identity": record["identity"],
        "run_ids": record.get("run_ids", []), "total_wall_seconds": wall,
        "critical_path_fault_seconds": blocked,
        "fault_adjusted_wall_seconds": wall - blocked,
        "fault_adjusted_note": "estimate subtracts only evidence-backed blocking fault union; not a fault-free measurement",
        "category_wall_seconds": {key: _union_seconds(value) for key, value in categories.items()},
        "category_note": "category windows can overlap; do not sum them as total wall time or active Agent work",
        "active_work_seconds": record.get("active_work_seconds"),
        "counts": record.get("counts"),
        "limitations": missing or ["activity attribution is limited to supplied retained records"],
        "performance_acceptance": "not_judged_by_timing_tool",
        "target_seconds": 7200, "later_product_target_seconds": 3600,
        "completion_references": completion if complete else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    parser.add_argument("--observed-at", default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()
    print(json.dumps(summarize_round(json.loads(args.record.read_text()), observed_at=args.observed_at),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
