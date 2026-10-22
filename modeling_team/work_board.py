"""Run-local work reports and shared request history (R4.4-001).

The Broker is the only production writer. Readers never repair, dispatch, collect
usage, or infer semantic progress. This module also runs beside the isolated
transport script, so its import-time dependencies are standard-library only.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from uuid import UUID
from uuid import uuid4

SCHEMA = "team-work-board/v1"
EVENT_PATH = "evidence/work-board-events.jsonl"
ARCHIVE_POINTER = "evidence/work-board-retrospective.json"
PRODUCTION_ROLES = {"coordinator", "modeling", "protocol", "source-specialist"}
TOOL_NAMES = {"update_work_card", "resolve_work_request", "get_work_board"}
SAFE_ERRORS = {
    "invalid_work_card": "supply documented own-card fields; use artifact references for full content",
    "invalid_work_request": "use the original request UUID, stable update UUID and documented action fields",
    "work_board_forbidden": "use your own card or an authorized request with its original participants",
    "work_request_conflict": "this identity binds different content; inspect the original before correcting",
    "work_request_closed": "retain the original decision; new work needs a new request",
    "work_board_unavailable": "inspect the history source; ordinary messaging remains available",
    "work_message_unknown": "inspect the original request and message receipts; do not blindly resend",
    "invalid_work_board_query": "reuse the documented selection; times need a timezone; versions need agent_id and record_seq",
    "invalid_work_board_cursor": "reuse the same run, viewer and selection",
    "invalid_source_ref": "use the exact run-local source_ref returned by this service",
    "source_changed": "the original prefix changed; begin a new query and retain the limitation",
    "source_unavailable": "the original history source is missing",
    "work_version_not_found": "choose a retained card sequence for this agent",
}
CARD_FIELDS = {
    "current_work",
    "work_scope",
    "near_term_goals",
    "waiting_note",
    "latest_result_refs",
}
READ_PROPERTIES = {
    "agent_id": {"type": "string"},
    "request_id": {"type": "string"},
    "view": {"type": "string", "enum": ["current", "history", "version"]},
    "from_time": {"type": "string"},
    "to_time": {"type": "string"},
    "record_seq": {"type": "integer", "minimum": 1},
    "after_record_seq": {"type": "integer", "minimum": 0},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    "cursor": {"type": "string"},
    "source_ref": {"type": "object"},
}
TOOL_SPECS = [
    {
        "name": "update_work_card",
        "description": "Replace your own shared work summary only on meaningful work changes; identical content is a no-op.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "card": {
                    "type": "object",
                    "properties": {
                        "current_work": {"type": "string"},
                        "work_scope": {"type": "string"},
                        "near_term_goals": {"type": "array", "items": {"type": "string"}},
                        "waiting_note": {"type": "string"},
                        "latest_result_refs": {
                            "type": "array",
                            "items": {"type": ["string", "object"]},
                        },
                    },
                    "required": ["current_work"],
                    "additionalProperties": False,
                }
            },
            "required": ["card"],
            "additionalProperties": False,
        },
    },
    {
        "name": "resolve_work_request",
        "description": "Requester only: record resolved locally, or withdraw with one notification. Reuse update_id on retry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "request_id": {"type": "string"},
                "update_id": {"type": "string"},
                "resolution": {"type": "string", "enum": ["resolved", "withdrawn"]},
                "note": {"type": "string"},
            },
            "required": ["request_id", "update_id", "resolution", "note"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_work_board",
        "description": "Read permitted work reports/requests or fixed-prefix history; history may filter records after a non-negative sequence. Reports and message receipts are separate facts.",
        "inputSchema": {
            "type": "object",
            "properties": READ_PROPERTIES,
            "additionalProperties": False,
        },
    },
]
WORK_REQUEST_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["request", "feedback"]},
        "request_id": {
            "type": "string",
            "description": "UUID generated once before the first request",
        },
        "summary": {"type": "string"},
        "related_work": {"type": "string"},
        "blocking": {"type": "boolean"},
        "update_id": {"type": "string"},
        "assignee_report": {
            "type": "string",
            "enum": ["in_progress", "needs_input", "responded", "unable"],
        },
        "result_refs": {"type": "array", "items": {"type": ["string", "object"]}},
    },
    "required": ["action", "request_id"],
    "additionalProperties": False,
}


class WorkBoardError(ValueError):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(f"{code}: {detail}")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uuid(value, field):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise WorkBoardError("invalid_work_request", f"{field} must be a canonical UUID") from None


def _text(value, field):
    if not isinstance(value, str):
        raise WorkBoardError("invalid_work_card", f"{field} must be text")
    return value


def normalize_card(card):
    if not isinstance(card, dict) or set(card) - CARD_FIELDS or "current_work" not in card:
        raise WorkBoardError("invalid_work_card", "supply only the documented own-card fields")
    value = {
        key: _text(card.get(key, ""), key) for key in ("current_work", "work_scope", "waiting_note")
    }
    for key in ("near_term_goals", "latest_result_refs"):
        rows = card.get(key, [])
        types = (str,) if key == "near_term_goals" else (str, dict)
        if not isinstance(rows, list) or any(not isinstance(row, types) for row in rows):
            raise WorkBoardError("invalid_work_card", f"{key} has invalid items")
        value[key] = deepcopy(rows)
    if len(_json(value).encode()) > 16000:
        raise WorkBoardError(
            "invalid_work_card",
            "keep the shared summary within 16000 bytes; reference full artifacts",
        )
    return value


def _time(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise WorkBoardError("invalid_work_board_query", "times must include a timezone") from None


def _local_path(root, relative):
    if (
        not isinstance(relative, str)
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
    ):
        raise WorkBoardError("invalid_source_ref", "use a returned run-local source")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise WorkBoardError("invalid_source_ref", "source must belong to this run")
    return path


def _event_source(root, source_ref=None):
    if source_ref is not None and not isinstance(source_ref, dict):
        raise WorkBoardError("invalid_source_ref", "use the returned source_ref object")
    relative = EVENT_PATH if source_ref is None else source_ref.get("path")
    if relative != EVENT_PATH:
        # Only immutable snapshots published by this service are valid alternatives.
        path = _local_path(root, relative)
        if (
            path.name != "work-board-events.jsonl"
            or path.parent.parent != root / "evidence/work-board-retrospectives"
        ):
            raise WorkBoardError("invalid_source_ref", "not a work-board history source")
        index = path.parent / "index.json"
        try:
            registered = _archive_index(root, index)["history_source"]
        except WorkBoardError:
            raise
        except (OSError, ValueError, KeyError):
            raise WorkBoardError("invalid_source_ref", "archive index unavailable") from None
        if {k: v for k, v in source_ref.items() if k != "statistics"} != registered:
            raise WorkBoardError("invalid_source_ref", "archive prefix does not match its index")
    else:
        path = _local_path(root, relative)
    try:
        with path.open("rb") as stream:
            length = source_ref.get("byte_length") if source_ref else None
            if length is not None and (type(length) is not int or length < 0):
                raise WorkBoardError("invalid_source_ref", "invalid byte_length")
            raw = stream.read(length) if length is not None else stream.read()
    except FileNotFoundError:
        if source_ref:
            raise WorkBoardError(
                "source_unavailable", "the original history prefix is missing"
            ) from None
        return b"", None, ["work_board_not_recorded"]
    if source_ref and (
        len(raw) != source_ref.get("byte_length")
        or sha256(raw).hexdigest() != source_ref.get("sha256")
    ):
        raise WorkBoardError("source_changed", "original history prefix changed; start a new query")
    limits = []
    end = raw.rfind(b"\n") + 1
    if end != len(raw):
        limits.append("history_truncated:incomplete_final_line")
        raw = raw[:end]
    return (
        raw,
        {"path": relative, "byte_length": len(raw), "sha256": sha256(raw).hexdigest()},
        limits,
    )


def _events(raw, run_id):
    events, limits, last, requests = [], [], 0, set()
    for number, line in enumerate(raw.splitlines(), 1):
        try:
            value = json.loads(line)
            if (
                not isinstance(value, dict)
                or value.get("schema_version") != SCHEMA
                or value.get("run_id") != run_id
                or type(value.get("record_seq")) is not int
                or value["record_seq"] <= last
                or not isinstance(value.get("actor_id"), str)
                or not isinstance(value.get("kind"), str)
                or _time(value.get("recorded_at")) is None
            ):
                raise ValueError
            kind = value["kind"]
            required = {
                "card": {"card", "previous_record_seq", "changed_fields"},
                "request": {
                    "request_id",
                    "operation_id",
                    "fingerprint",
                    "assignee_id",
                    "summary",
                    "related_work",
                    "blocking",
                },
                "feedback": {
                    "request_id",
                    "operation_id",
                    "fingerprint",
                    "assignee_report",
                    "result_refs",
                },
                "resolution": {"request_id", "operation_id", "fingerprint", "resolution", "note"},
                "transport": {"request_id", "delivery_id", "message_status"},
            }
            if kind not in required or not required[kind] <= value.keys():
                raise ValueError
            if value.get("member_ref") is not None and not isinstance(value["member_ref"], dict):
                raise ValueError
            if kind == "card":
                if (
                    normalize_card(value["card"]) != value["card"]
                    or value["previous_record_seq"] is not None
                    and type(value["previous_record_seq"]) is not int
                    or not isinstance(value["changed_fields"], list)
                ):
                    raise ValueError
            if kind != "card":
                _uuid(value["request_id"], "request_id")
                if kind in {"request", "feedback", "resolution"}:
                    _uuid(value["operation_id"], "operation_id")
                if kind == "request":
                    if (
                        not all(
                            isinstance(value[k], str)
                            for k in ("assignee_id", "summary", "related_work")
                        )
                        or type(value["blocking"]) is not bool
                    ):
                        raise ValueError
                    requests.add(value["request_id"])
                elif value["request_id"] not in requests:
                    limits.append(f"history_orphan_event:{number}")
                    continue
                if kind == "feedback" and (
                    not isinstance(value["result_refs"], list)
                    or value["assignee_report"]
                    not in {"in_progress", "needs_input", "responded", "unable"}
                ):
                    raise ValueError
                if kind == "resolution" and (
                    value["resolution"] not in {"resolved", "withdrawn"}
                    or not isinstance(value["note"], str)
                ):
                    raise ValueError
            last = value["record_seq"]
            events.append(value)
        except (ValueError, TypeError, KeyError):
            limits.append(f"history_bad_line:{number}")
    return events, limits


def _state(events):
    cards, requests, operations = {}, {}, {}
    for event in events:
        kind = event["kind"]
        if kind == "card":
            cards[event["actor_id"]] = event
        elif kind == "request":
            rid = event["request_id"]
            requests[rid] = {
                "request_id": rid,
                "requester_id": event["actor_id"],
                "assignee_id": event["assignee_id"],
                "summary": event["summary"],
                "related_work": event["related_work"],
                "blocking": event["blocking"],
                "requester_state": "open",
                "assignee_report": "pending",
                "feedback_refs": [],
                "message_bindings": [],
                "created_at": event["recorded_at"],
                "updated_at": event["recorded_at"],
            }
        if kind in {"request", "feedback", "resolution"}:
            rid = event["request_id"]
            operations[(rid, event["operation_id"])] = event
            if rid not in requests:
                continue
            current = requests[rid]
            current["updated_at"] = event["recorded_at"]
            if kind == "feedback":
                current["assignee_report"] = event["assignee_report"]
                current["feedback_refs"].append(
                    {
                        "record_seq": event["record_seq"],
                        "update_id": event["operation_id"],
                        "result_refs": event["result_refs"],
                        "late": current["requester_state"] != "open",
                    }
                )
            elif kind == "resolution":
                current["requester_state"] = event["resolution"]
                current["resolution_note"] = event["note"]
            if event.get("delivery_id"):
                current["message_bindings"].append(
                    {
                        "delivery_id": event["delivery_id"],
                        "record_seq": event["record_seq"],
                        "action": kind,
                        "message_status": event.get("message_status", "unknown"),
                    }
                )
        elif kind == "transport":
            for current in requests.values():
                for binding in current["message_bindings"]:
                    if binding["delivery_id"] == event["delivery_id"]:
                        binding.update(
                            message_status=event["message_status"],
                            receipt_record_seq=event["record_seq"],
                            receipt_ref=event.get("receipt_ref"),
                        )
    return cards, requests, operations


def _card_view(card, viewer, projection, ref_reader):
    if card is None:
        return None, True
    value = deepcopy(card)
    refs = value["latest_result_refs"]
    value["latest_result_refs"] = [
        ref
        for ref in refs
        if isinstance(ref, str)
        or projection == "host"
        or ref_reader is not None
        and ref_reader(viewer, ref)
    ]
    return value, len(value["latest_result_refs"]) == len(refs)


class WorkBoard:
    def __init__(self, root, run_id, agent_roles, permissions, *, member_reader=None):
        self.root, self.run_id = Path(root), run_id
        self.path = self.root / EVENT_PATH
        self.agents = {agent for agent, role in agent_roles.items() if role in PRODUCTION_ROLES}
        self.permissions = permissions
        self.member_reader = member_reader

    def require_actor(self, actor):
        if actor not in self.agents:
            raise WorkBoardError(
                "work_board_forbidden", "only bound production participants may use this board"
            )

    def load(self):
        raw, source, limits = _event_source(self.root)
        events, errors = _events(raw, self.run_id)
        return events, source, [*limits, *errors]

    def append(self, actor, kind, **data):
        events, _, limits = self.load()
        if any(item != "work_board_not_recorded" for item in limits):
            raise WorkBoardError(
                "work_board_unavailable", "repair the reported history source before appending"
            )
        member = self.member_reader(actor) if self.member_reader else None
        event = {
            "schema_version": SCHEMA,
            "run_id": self.run_id,
            "record_seq": events[-1]["record_seq"] + 1 if events else 1,
            "actor_id": actor,
            "recorded_at": _now(),
            "member_ref": member,
            "kind": kind,
            **data,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.path.open("ab") as stream:
            os.chmod(self.path, 0o600)
            stream.write((_json(event) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        return event

    def update(self, actor, card):
        self.require_actor(actor)
        card = normalize_card(card)
        previous = _state(self.load()[0])[0].get(actor)
        if previous and previous["card"] == card:
            return {
                "changed": False,
                "record_seq": previous["record_seq"],
                "reported_at": previous["recorded_at"],
            }
        event = self.append(
            actor,
            "card",
            card=card,
            previous_record_seq=previous["record_seq"] if previous else None,
            changed_fields=sorted(
                key for key in CARD_FIELDS if not previous or previous["card"][key] != card[key]
            ),
        )
        return {
            "changed": True,
            "record_seq": event["record_seq"],
            "reported_at": event["recorded_at"],
        }

    def prepare(self, actor, recipient, metadata, message):
        self.require_actor(actor)
        self.require_actor(recipient)
        if not isinstance(metadata, dict):
            raise WorkBoardError("invalid_work_request", "work_request must be an object")
        action, rid = metadata.get("action"), metadata.get("request_id")
        _uuid(rid, "request_id")
        _, requests, operations = _state(self.load()[0])
        current = requests.get(rid)
        if action == "request":
            if set(metadata) - {"action", "request_id", "summary", "related_work", "blocking"}:
                raise WorkBoardError("invalid_work_request", "unexpected request fields")
            if current and (
                current["requester_id"] != actor or current["assignee_id"] != recipient
            ):
                raise WorkBoardError(
                    "work_board_forbidden", "request belongs to different participants"
                )
            summary = _text(metadata.get("summary"), "summary")
            related = _text(metadata.get("related_work", ""), "related_work")
            blocking = metadata.get("blocking", False)
            if not isinstance(blocking, bool):
                raise WorkBoardError("invalid_work_request", "blocking must be boolean")
            fields = dict(
                summary=summary, related_work=related, blocking=blocking, assignee_id=recipient
            )
            operation_id = rid
        elif action == "feedback":
            if (
                not current
                or current["assignee_id"] != actor
                or current["requester_id"] != recipient
            ):
                raise WorkBoardError(
                    "work_board_forbidden", "feedback requires the original reversed participants"
                )
            if set(metadata) - {
                "action",
                "request_id",
                "update_id",
                "assignee_report",
                "result_refs",
            }:
                raise WorkBoardError("invalid_work_request", "unexpected feedback fields")
            operation_id = metadata.get("update_id")
            _uuid(operation_id, "update_id")
            report = metadata.get("assignee_report")
            refs = metadata.get("result_refs", [])
            if (
                report not in {"in_progress", "needs_input", "responded", "unable"}
                or not isinstance(refs, list)
                or any(not isinstance(ref, (str, dict)) for ref in refs)
            ):
                raise WorkBoardError(
                    "invalid_work_request", "invalid assignee_report or result_refs"
                )
            fields = dict(assignee_report=report, result_refs=refs)
        elif action == "resolution":
            if not current or current["requester_id"] != actor:
                raise WorkBoardError(
                    "work_board_forbidden", "only the requester may resolve or withdraw"
                )
            operation_id = metadata.get("update_id")
            _uuid(operation_id, "update_id")
            if set(metadata) != {
                "action",
                "request_id",
                "update_id",
                "resolution",
                "note",
            } or metadata.get("resolution") not in {"resolved", "withdrawn"}:
                raise WorkBoardError("invalid_work_request", "invalid resolution fields")
            fields = dict(resolution=metadata["resolution"], note=_text(metadata["note"], "note"))
        else:
            raise WorkBoardError("invalid_work_request", "use request or feedback")
        fingerprint = sha256(
            _json(
                {
                    "actor": actor,
                    "recipient": recipient,
                    "action": action,
                    "fields": fields,
                    "message": message,
                }
            ).encode()
        ).hexdigest()
        prior = operations.get((rid, operation_id))
        if prior and (prior["actor_id"] != actor or prior.get("fingerprint") != fingerprint):
            raise WorkBoardError(
                "work_request_conflict",
                "identity already binds different content; retain the original",
            )
        if action == "resolution" and not prior and current["requester_state"] != "open":
            raise WorkBoardError(
                "work_request_closed",
                "retain the existing decision; use a new request for new work",
            )
        if len(_json(fields).encode()) > 16000:
            raise WorkBoardError(
                "invalid_work_request",
                "keep the summary within 16000 bytes; reference full artifacts",
            )
        return prior, dict(
            kind=action,
            request_id=rid,
            operation_id=operation_id,
            fingerprint=fingerprint,
            **fields,
        )

    def read(
        self,
        viewer=None,
        *,
        projection="agent",
        agent_id=None,
        request_id=None,
        view="current",
        from_time=None,
        to_time=None,
        record_seq=None,
        after_record_seq=None,
        cursor=None,
        source_ref=None,
        limit=25,
        live_status=None,
        _statistics=None,
        _ref_reader=None,
    ):
        if projection == "agent":
            self.require_actor(viewer)
            visible = {
                agent
                for agent in self.agents
                if agent == viewer or (agent, viewer) in self.permissions
            }
        else:
            visible = set(self.agents)
        if agent_id is not None and agent_id not in visible:
            raise WorkBoardError("work_board_forbidden", "selected card is not readable")
        if (
            view not in {"current", "history", "version"}
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise WorkBoardError(
                "invalid_work_board_query", "use a valid view and limit from 1 to 100"
            )
        start, end = _time(from_time), _time(to_time)
        if (start or end) and view != "history" or start and end and start >= end:
            raise WorkBoardError(
                "invalid_work_board_query", "time range must be a history half-open interval"
            )
        if record_seq is not None and (
            view != "version" or not agent_id or type(record_seq) is not int
        ):
            raise WorkBoardError(
                "invalid_work_board_query", "record_seq requires version view and agent_id"
            )
        if view == "version" and (not agent_id or record_seq is None):
            raise WorkBoardError(
                "invalid_work_board_query", "version requires agent_id and record_seq"
            )
        if after_record_seq is not None and (
            view != "history" or type(after_record_seq) is not int or after_record_seq < 0
        ):
            raise WorkBoardError(
                "invalid_work_board_query",
                "after_record_seq requires history view and a non-negative integer",
            )
        selection = dict(
            agent_id=agent_id,
            request_id=request_id,
            view=view,
            from_time=from_time,
            to_time=to_time,
            record_seq=record_seq,
            after_record_seq=after_record_seq,
            include_statistics=_statistics is not None,
        )
        offset = 0
        if cursor:
            try:
                state = json.loads(base64.urlsafe_b64decode(cursor))
                if (
                    state["run_id"] != self.run_id
                    or state["selection"] != selection
                    or state["viewer"] != [projection, viewer]
                ):
                    raise ValueError
                if source_ref and {k: v for k, v in source_ref.items() if k != "statistics"} != {
                    k: v for k, v in state["source_ref"].items() if k != "statistics"
                }:
                    raise ValueError
                if (
                    _statistics is not None
                    and state.get("statistics_source") != _statistics["source"]
                ):
                    raise WorkBoardError(
                        "source_changed",
                        "retain the selected statistics publication on continuation",
                    )
                source_ref, offset = state["source_ref"], state["offset"]
                if type(offset) is not int or offset < 0:
                    raise ValueError
            except WorkBoardError:
                raise
            except (ValueError, KeyError, TypeError):
                raise WorkBoardError(
                    "invalid_work_board_cursor", "reuse the same run, viewer and selection"
                ) from None
        raw, source, limits = _event_source(self.root, source_ref)
        events, errors = _events(raw, self.run_id)
        limits.extend(errors)
        if source:
            source["max_record_seq"] = events[-1]["record_seq"] if events else 0
            if source_ref and source_ref.get("max_record_seq") != source["max_record_seq"]:
                raise WorkBoardError("source_changed", "history sequence does not match its source")
            if _statistics is not None:
                source["statistics"] = _statistics["source"]
        cards, requests, _ = _state(events)
        permitted = {
            rid: row
            for rid, row in requests.items()
            if row["requester_id"] in self.agents
            and row["assignee_id"] in self.agents
            and (projection != "agent" or viewer in {row["requester_id"], row["assignee_id"]})
        }
        if request_id is not None and request_id not in permitted:
            raise WorkBoardError("work_board_forbidden", "selected request is not readable")
        selected = {
            rid: row
            for rid, row in permitted.items()
            if (not request_id or rid == request_id)
            and (not agent_id or agent_id in {row["requester_id"], row["assignee_id"]})
        }
        rows = []
        if view == "current":
            for actor in sorted(visible if not agent_id else {agent_id}):
                if request_id and actor not in {
                    permitted[request_id]["requester_id"],
                    permitted[request_id]["assignee_id"],
                }:
                    continue
                event = cards.get(actor)
                card, refs_complete = _card_view(
                    event["card"] if event else None, viewer, projection, _ref_reader
                )
                rows.append(
                    (
                        "cards",
                        {
                            "agent_id": actor,
                            "report_status": "reported" if event else "not_reported",
                            "card": card,
                            "references_complete": refs_complete,
                            "reported_at": event["recorded_at"] if event else None,
                            "record_seq": event["record_seq"] if event else None,
                            "observed_runtime": observed_runtime(self.root, actor),
                            "outgoing_requests_total": sum(
                                r["requester_id"] == actor for r in selected.values()
                            ),
                            "incoming_requests_total": sum(
                                r["assignee_id"] == actor for r in selected.values()
                            ),
                        },
                    )
                )
            for row in selected.values():
                row = deepcopy(row)
                for binding in row["message_bindings"]:
                    if live_status and binding["delivery_id"] in live_status:
                        binding.update(live_status[binding["delivery_id"]])
                row.pop("resolution_note", None)
                for feedback in row["feedback_refs"]:
                    feedback.pop("result_refs", None)  # exact history event retains result locators
                for key in ("feedback_refs", "message_bindings"):
                    row[key + "_coverage"] = {
                        "total": len(row[key]),
                        "returned": min(5, len(row[key])),
                        "complete": len(row[key]) <= 5,
                        "detail": {
                            "view": "history",
                            "request_id": row["request_id"],
                            "source_ref": source,
                        },
                    }
                    row[key] = row[key][-5:]
                rows.append(("requests", row))
        else:
            by_seq = {event["record_seq"]: event for event in events}
            for event in events:
                if after_record_seq is not None and event["record_seq"] <= after_record_seq:
                    continue
                kind = event["kind"]
                if kind == "card":
                    if (
                        event["actor_id"] not in visible
                        or agent_id
                        and event["actor_id"] != agent_id
                        or request_id
                    ):
                        continue
                elif event.get("request_id") not in selected:
                    continue
                if view == "version" and (kind != "card" or event["record_seq"] != record_seq):
                    continue
                stamp = _time(event["recorded_at"])
                if start and stamp < start or end and stamp >= end:
                    continue
                item = deepcopy(event)
                item.pop("fingerprint", None)
                if kind == "card":
                    item["card"], item["references_complete"] = _card_view(
                        item["card"], viewer, projection, _ref_reader
                    )
                    if not item["references_complete"]:
                        item["changed_fields"] = [
                            key for key in item["changed_fields"] if key != "latest_result_refs"
                        ]
                    previous = by_seq.get(event.get("previous_record_seq"))
                    item["previous_version"] = (
                        {
                            "agent_id": event["actor_id"],
                            "record_seq": previous["record_seq"],
                            "source_ref": source,
                        }
                        if previous
                        else None
                    )
                    item["previous_status"] = (
                        "available"
                        if previous
                        else "unknown"
                        if event.get("previous_record_seq")
                        else "initial"
                    )
                    if not previous and event.get("previous_record_seq"):
                        item["changed_fields"] = None
                        limits.append("previous_version_unavailable")
                if projection == "delivery":
                    for key in ("note", "result_refs"):
                        item.pop(key, None)
                rows.append(("history", item))
            if view == "version" and not rows:
                raise WorkBoardError(
                    "work_version_not_found",
                    "sequence is not a retained version of the selected card",
                )
        if _statistics is not None:
            groups = [
                g for g in _statistics["groups"] if not agent_id or g.get("agent_id") == agent_id
            ]
            for kind, row in rows:
                if kind == "history":
                    row["statistics_binding"] = _member_binding(row, groups, self.run_id)
            rows.extend(("statistics_groups", g) for g in groups)
        page, size = [], 0
        for item in rows[offset : offset + limit]:
            item_size = len(_json(item).encode())
            if page and size + item_size > 24000:
                break
            page.append(item)
            size += item_size
        next_offset = offset + len(page)
        continuation = None
        if next_offset < len(rows):
            continuation = base64.urlsafe_b64encode(
                _json(
                    {
                        "run_id": self.run_id,
                        "selection": selection,
                        "viewer": [projection, viewer],
                        "source_ref": source,
                        "offset": next_offset,
                        "statistics_source": _statistics["source"]
                        if _statistics is not None
                        else None,
                    }
                ).encode()
            ).decode()
        result = {
            "schema_version": SCHEMA,
            "run_id": self.run_id,
            "view": view,
            "status": "available" if source else "unavailable",
            "source_ref": source,
            "history_window": {"from_time": from_time, "to_time": to_time, "interval": "[from,to)"},
            "observed_at": _now(),
            "continuation": continuation,
            "limitations": sorted(set(limits)),
            "coverage": {
                key: {
                    "total": sum(k == key for k, _ in rows),
                    "returned": sum(k == key for k, _ in page),
                    "complete": (
                        sum(k == key for k, _ in page) == sum(k == key for k, _ in rows)
                        and not limits
                    ),
                }
                for key in ("cards", "requests", "history", "statistics_groups")
            },
        }
        for key in ("cards", "requests", "history", "statistics_groups"):
            result[key] = [value for kind, value in page if kind == key]
        if _statistics is not None:
            result["statistics"] = {
                key: value for key, value in _statistics.items() if key != "groups"
            }
            result["bindings"] = [
                dict(record_seq=row["record_seq"], **row["statistics_binding"])
                for row in result["history"]
            ]
        return result


def observed_runtime(root, agent):
    """Only retained numeric activity facts, never a card-derived liveness verdict."""
    path = root / "evidence/close-statistics-capture/activity.jsonl"
    latest = None
    try:
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("agent_id") == agent:
                latest = {
                    key: row[key]
                    for key in (
                        "event",
                        "recorded_at",
                        "process_instance",
                        "runtime_session_id",
                        "status",
                    )
                    if key in row
                }
    except OSError:
        pass
    return {
        "status": "observed" if latest else "unknown",
        "last_activity": latest,
        "source": "evidence/close-statistics-capture/activity.jsonl" if latest else None,
        "observed_at": _now(),
        "meaning": "runtime activity only; no inferred business progress",
    }


def board_from_run(root, run_id):
    import yaml

    try:
        profile = yaml.safe_load((root / "profile.snapshot.yaml").read_text()) or {}
    except (OSError, ValueError, yaml.YAMLError):
        profile = {}
    try:
        baseline = json.loads((root / "baseline-manifest.json").read_text())
        recorded_roles = (
            baseline.get("work_board_roster", {}) if baseline.get("run_id") == run_id else {}
        )
    except (OSError, ValueError):
        recorded_roles = {}
    roles = {
        row["agent_id"]: recorded_roles.get(row["agent_id"], row.get("package"))
        for row in profile.get("agents", [])
    }
    permissions = {
        (row["from"], target) for row in profile.get("communication", []) for target in row["to"]
    }
    return WorkBoard(root, run_id, roles, permissions)


def _file_ref(root, relative):
    raw = _local_path(root, relative).read_bytes()
    return {"path": relative, "byte_length": len(raw), "sha256": sha256(raw).hexdigest()}


def _frozen_json(root, reference):
    path = _local_path(root, reference["path"])
    raw = path.read_bytes()
    if len(raw) != reference["byte_length"] or sha256(raw).hexdigest() != reference["sha256"]:
        raise WorkBoardError("source_changed", "frozen statistics original changed")
    return json.loads(raw)


def _statistics_source(root, pointer):
    if pointer.get("report_status") != "ready":
        return {"status": "unavailable", "limitations": ["close_statistics_not_published"]}
    report, scope = pointer.get("report_ref"), pointer.get("scope_ref")
    if (
        not isinstance(report, str)
        or not report.startswith("evidence/close-statistics/report-")
        or Path(report).name != "report.json"
        or scope != str(Path(report).with_name("scope.json"))
    ):
        raise WorkBoardError("invalid_source_ref", "not a published close statistics version")
    return {
        "status": "available",
        "snapshot_sha256": pointer.get("snapshot_sha256"),
        "report": _file_ref(root, report),
        "scope": _file_ref(root, scope),
    }


def _archive_index(root, path):
    value = json.loads(path.read_text())
    fingerprint = sha256(
        _json(
            {
                "run_id": value["run_id"],
                "history": value["original_source"],
                "statistics": value["statistics_source"],
            }
        ).encode()
    ).hexdigest()
    if (
        value.get("schema_version") != "team-work-board-retrospective/v1"
        or value["fingerprint"] != fingerprint
        or path.parent.name != "snapshot-" + fingerprint
        or value["original_source"]["path"] != EVENT_PATH
        or value["history_source"]
        != {
            **value["original_source"],
            "path": str((path.parent / "work-board-events.jsonl").relative_to(root)),
        }
    ):
        raise WorkBoardError(
            "source_changed", "retained archive index no longer matches its original binding"
        )
    return value


def _member_key(row):
    return row.get("runtime"), row.get("process_instance"), row.get("agent_id")


def _statistics_view(root, run_id, agents, source):
    result = {
        "source": source,
        "status": "unavailable",
        "coverage": "unknown",
        "groups": [],
        "statistics_window": None,
        "limitations": ["close_statistics_not_published"],
        "meaning": "original member/session report scope; no exact per-card token attribution",
    }
    if source.get("status") != "available":
        return result
    try:
        # A cursor may select an earlier publication, but never an arbitrary file.
        report_path, scope_path = source["report"]["path"], source["scope"]["path"]
        if (
            not report_path.startswith("evidence/close-statistics/report-")
            or Path(report_path).name != "report.json"
            or scope_path != str(Path(report_path).with_name("scope.json"))
        ):
            raise WorkBoardError("invalid_source_ref", "not a close statistics version")
        report = _frozen_json(root, source["report"])
        scope = _frozen_json(root, source["scope"])
        close = report["close_statistics"]
        declared = scope["close_statistics"]["members"]
        numeric_fields = {
            "usage",
            "lifecycle_seconds",
            "elapsed_to_cutoff_seconds",
            "llm_request_seconds",
            "tool_execution_seconds",
            "active_seconds",
            "llm",
            "tools",
            "pause_seconds",
            "wait_seconds",
            "closure_status",
            "exit_status",
            "exit_returncode",
            "other_or_uncovered_seconds",
            "activity_coverage",
            "active_observed_subtotal_seconds",
            "limitations",
        }
        identity_fields = {
            "run_id",
            "agent_id",
            "runtime",
            "runtime_session_id",
            "runtime_session_ids",
            "process_instance",
            "role",
            "provider",
            "requested_model",
            "actual_model",
            "requested_effort",
            "effective_effort",
        }
        groups = []
        for member in close.get("members", []):
            matches = [row for row in declared if _member_key(row) == _member_key(member)]
            if (
                len(matches) != 1
                or matches[0].get("run_id") != run_id
                or member.get("agent_id") not in agents
                or not matches[0].get("scope_member", True)
                or matches[0].get("role") not in PRODUCTION_ROLES
            ):
                continue
            value = {
                k: deepcopy(v) for k, v in member.items() if k in numeric_fields | identity_fields
            }
            value["run_id"] = run_id
            value["group_id"] = (
                "member-"
                + sha256(_json({k: value.get(k) for k in identity_fields}).encode()).hexdigest()[
                    :24
                ]
            )
            value["group_type"] = "registered_member"
            groups.append(value)
        # Reuse 019's published session/model groups. No new token aggregation;
        # in particular, never copy a session cumulative total into each process.
        for index, published in enumerate(report.get("task_usage", {}).get("groups", [])):
            unit = published["identity"]
            if unit.get("run_id") != run_id or unit.get("role") not in PRODUCTION_ROLES:
                continue
            session = unit.get("runtime_session_id") or unit.get("thread_id")
            runtime = unit.get("runtime", "codex")
            matches = [
                row
                for row in declared
                if row.get("runtime") == runtime
                and session
                and session
                in (
                    row.get("runtime_session_ids")
                    or [row.get("runtime_session_id"), row.get("thread_id")]
                )
            ]
            if len(matches) < 2 or any(
                row.get("run_id") != run_id
                or row.get("agent_id") not in agents
                or row.get("role") not in PRODUCTION_ROLES
                or not row.get("scope_member", True)
                for row in matches
            ):
                continue
            agent_ids = {row["agent_id"] for row in matches}
            if len(agent_ids) != 1:
                continue
            value = {k: deepcopy(v) for k, v in unit.items() if k in identity_fields}
            value["usage"] = {
                k: deepcopy(v)
                for k, v in published.items()
                if k in {"tokens", "field_coverage", "cache_rate_input_coverage", "cost_units"}
            }
            value.update(
                group_type="session_usage",
                agent_id=next(iter(agent_ids)),
                run_id=run_id,
                attribution_status="session_only_not_process_or_card",
                additive_to_member_usage=False,
                report_group_index=index,
            )
            value["group_id"] = (
                "session-" + sha256(_json([source, index]).encode()).hexdigest()[:24]
            )
            groups.append(value)
        result.update(
            status="available",
            coverage="partial" if groups else "unknown",
            groups=groups,
            statistics_window={
                "task_window": scope.get("task_window"),
                "cutoff_at": close.get("cutoff_at"),
                "basis": "selected_original_report_member_or_session_scope",
            },
            limitations=[
                "no_per_card_token_allocation",
                "task_totals_and_global_shares_omitted",
                *([] if groups else ["member_binding_unavailable"]),
            ],
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result["limitations"] = [getattr(exc, "code", "statistics_original_unavailable")]
    return result


def _member_binding(event, groups, run_id):
    member = event.get("member_ref")
    candidates = [
        g
        for g in groups
        if g["group_type"] == "registered_member"
        and g.get("run_id") == run_id
        and g.get("agent_id") == event["actor_id"]
    ]
    scope = "agent_not_subdivided"
    if member and (member.get("process_instance") or member.get("runtime_session_id")):
        candidates = [
            g
            for g in candidates
            if all(
                not member.get(k) or g.get(k) == member[k]
                for k in ("runtime", "process_instance", "run_id", "agent_id")
            )
            and (
                not member.get("runtime_session_id")
                or member["runtime_session_id"]
                in (g.get("runtime_session_ids") or [g.get("runtime_session_id")])
            )
        ]
        scope = (
            "member_scope_not_card_usage"
            if member.get("process_instance")
            else "session_not_subdivided"
        )
    return {
        "group_ids": [g["group_id"] for g in candidates],
        "status": "partial" if candidates else "unknown",
        "scope": scope,
        "card_tokens": None,
    }


def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(".work-board-" + uuid4().hex)
    try:
        temporary.write_text(_json(value))
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def archive_work_board(root, run_id, statistics):
    """Advisory close attachment. Never modifies the numeric report or its pointer."""
    root = Path(root)
    temporary = None
    try:
        raw, source, limits = _event_source(root)
        if source is None:
            return {"status": "unavailable", "limitations": limits}
        events, errors = _events(raw, run_id)
        source["max_record_seq"] = events[-1]["record_seq"] if events else 0
        try:
            stats_source = _statistics_source(root, statistics)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            stats_source = {
                "status": "unavailable",
                "limitations": [getattr(exc, "code", "statistics_original_unavailable")],
            }
        fingerprint = sha256(
            _json({"run_id": run_id, "history": source, "statistics": stats_source}).encode()
        ).hexdigest()
        parent = root / "evidence/work-board-retrospectives"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = parent / ("snapshot-" + fingerprint)
        history_source = {
            **source,
            "path": str((target / "work-board-events.jsonl").relative_to(root)),
        }
        index = {
            "schema_version": "team-work-board-retrospective/v1",
            "run_id": run_id,
            "history_source": history_source,
            "original_source": source,
            "history_cutoff_at": events[-1]["recorded_at"] if events else None,
            "statistics_source": stats_source,
            "member_bindings_source": stats_source.get("scope"),
            "coverage": "partial"
            if limits or errors or stats_source["status"] != "available"
            else "retained",
            "limitations": [*limits, *errors],
            "fingerprint": fingerprint,
        }
        if not target.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".publishing-", dir=parent))
            history = temporary / "work-board-events.jsonl"
            history.write_bytes(raw)
            history.chmod(0o600)
            _atomic_json(temporary / "index.json", index)
            temporary.rename(target)
            temporary = None
        else:
            if json.loads((target / "index.json").read_text()) != index:
                raise WorkBoardError("source_changed", "retained archive index changed")
            _event_source(root, history_source)
        value = {
            "status": "available",
            "archive_ref": str((target / "index.json").relative_to(root)),
            "fingerprint": fingerprint,
            "coverage": index["coverage"],
        }
        _atomic_json(root / ARCHIVE_POINTER, value)
        return value
    except (OSError, ValueError, KeyError, TypeError):
        value = {"status": "archive_unavailable", "limitations": ["work_board_archive_failed"]}
        try:
            _atomic_json(root / ARCHIVE_POINTER, value)
        except OSError:
            pass
        return value
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def read_team_work_board(root, run_id, *, projection="host", include_statistics=False, **arguments):
    from .close_statistics import read_close_statistics

    root = Path(root)
    board = board_from_run(root, run_id)
    source_ref = arguments.get("source_ref")
    if source_ref is not None and not isinstance(source_ref, dict):
        raise WorkBoardError("invalid_source_ref", "use the returned source_ref object")
    cursor_statistics = None
    if arguments.get("cursor") and not source_ref:
        try:
            cursor_state = json.loads(base64.urlsafe_b64decode(arguments["cursor"]))
            source_ref = cursor_state["source_ref"]
            cursor_statistics = cursor_state.get("statistics_source")
        except (ValueError, TypeError, KeyError):
            raise WorkBoardError("invalid_work_board_cursor", "reuse a returned cursor") from None
    archive = None
    if source_ref and "archive_ref" in source_ref:
        relative = source_ref["archive_ref"]
        path = _local_path(root, relative)
        if (
            path.name != "index.json"
            or path.parent.parent != root / "evidence/work-board-retrospectives"
        ):
            raise WorkBoardError("invalid_source_ref", "choose a returned archive index")
        try:
            archive = _archive_index(root, path)
        except WorkBoardError:
            raise
        except (OSError, ValueError):
            raise WorkBoardError("source_unavailable", "archive index unavailable") from None
        if (
            archive.get("schema_version") != "team-work-board-retrospective/v1"
            or archive.get("run_id") != run_id
        ):
            raise WorkBoardError("invalid_source_ref", "archive does not belong to this run")
        arguments["source_ref"] = archive["history_source"]
        source_ref = arguments["source_ref"]
    if source_ref and source_ref.get("path") != EVENT_PATH and source_ref.get("path"):
        # Pinned history cursors also retain their original numeric publication.
        path = _local_path(root, source_ref["path"]).parent / "index.json"
        try:
            archive = _archive_index(root, path)
        except WorkBoardError:
            raise
        except (OSError, ValueError):
            raise WorkBoardError("source_unavailable", "archive index unavailable") from None
    stats = None
    if include_statistics:
        try:
            selected_source = (
                archive["statistics_source"]
                if archive
                else cursor_statistics
                if cursor_statistics is not None
                else source_ref.get("statistics")
                if source_ref and "statistics" in source_ref
                else _statistics_source(root, read_close_statistics(root))
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            selected_source = {
                "status": "unavailable",
                "limitations": [getattr(exc, "code", "statistics_original_unavailable")],
            }
        stats = _statistics_view(root, run_id, board.agents, selected_source)
    result = board.read(projection=projection, _statistics=stats, **arguments)
    if projection == "host":
        try:
            result["retrospective"] = json.loads((root / ARCHIVE_POINTER).read_text())
        except (OSError, ValueError):
            result["retrospective"] = {"status": "unavailable"}
        # Existing Host context stays outside the production evidence file.
        result["host_context"] = _host_context(root)
    return result


def _host_context(root):
    try:
        supervisor = json.loads((root / "control/host-supervisor.json").read_text())
        session_ref = supervisor.get("session_ref")
        if not session_ref:
            return {"status": "unavailable", "limitations": ["delivery_session_binding_missing"]}
        session_root = Path(session_ref).parent
        # Read existing bytes directly: a query must not create a journal lock.
        raw = (session_root / "session-events.jsonl").read_bytes()
        latest, pending, results, limits = None, {}, {}, []
        for number, line in enumerate(raw.splitlines(keepends=True), 1):
            try:
                if not line.endswith(b"\n"):
                    raise ValueError
                row = json.loads(line)
                if row.get("event") == "delivery_yield":
                    latest = {
                        k: row[k]
                        for k in (
                            "session_id",
                            "recorded_at",
                            "phase",
                            "waiting_for",
                            "next_action",
                            "reason",
                        )
                        if k in row
                    }
                elif row.get("event") == "host_action_request" and row.get("run_id") == root.name:
                    pending[row["request_id"]] = {
                        k: row[k]
                        for k in (
                            "session_id",
                            "request_id",
                            "run_id",
                            "kind",
                            "recorded_at",
                            "bindings",
                        )
                        if k in row
                    }
                elif row.get("event") == "host_action_result" and row.get("run_id") == root.name:
                    results[row["request_id"]] = {
                        k: row[k]
                        for k in (
                            "session_id",
                            "request_id",
                            "run_id",
                            "status",
                            "recorded_at",
                            "result_ref",
                        )
                        if k in row
                    }
            except (ValueError, KeyError, TypeError):
                limits.append(f"host_context_bad_line:{number}")
        pending = [row for rid, row in pending.items() if rid not in results]
        unresolved = [row for row in results.values() if row.get("status") in {"blocked", "failed"}]
        return {
            "status": "available",
            "session_ref": session_ref,
            "delivery_yield": latest,
            "pending_host_actions": pending[:25],
            "unresolved_host_actions": unresolved[:25],
            "unresolved_total": len(unresolved),
            "pending_total": len(pending),
            "complete": len(pending) <= 25 and not limits,
            "source": str(session_root / "session-events.jsonl"),
            "limitations": limits,
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unavailable", "limitations": ["host_context_unreadable"]}


def render_board(board):
    lines = [f"Team work board: {board['run_id']} ({board['view']}; {board['status']})"]
    for row in board["cards"]:
        lines.append(f"\n{row['agent_id']} — {row['reported_at'] or '尚未报告'}")
        if row["card"]:
            card = row["card"]
            lines.extend(
                [
                    card["current_work"],
                    "近期：" + "；".join(card["near_term_goals"]),
                    "等待：" + card["waiting_note"],
                    "成果：" + _json(card["latest_result_refs"]),
                ]
            )
        lines.append("运行事实：" + _json(row["observed_runtime"]))
        for request in board["requests"]:
            if row["agent_id"] in {request["requester_id"], request["assignee_id"]}:
                lines.append(
                    f"{request['requester_id']} → {request['assignee_id']} [{request['request_id']}] "
                    f"{request['summary']} ({request['requester_state']}/{request['assignee_report']}) "
                    + _json(request["message_bindings"])
                )
    if not board["cards"]:
        lines.extend(_json(row) for row in board["requests"])
    lines.extend(_json(row) for row in board["history"])
    if "statistics_groups" in board:
        lines.append("统计（原报告窗口，不按卡片时间分摊）：" + _json(board["statistics_groups"]))
    lines.append("覆盖：" + _json(board["coverage"]))
    if board["limitations"]:
        lines.append("限制：" + "; ".join(board["limitations"]))
    if board["continuation"]:
        lines.append("续页：--cursor " + board["continuation"])
    return "\n".join(lines)
