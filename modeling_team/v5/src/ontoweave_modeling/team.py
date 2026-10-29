"""Small task-scoped peer channel; work summaries do not replace model evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from .contracts import FrameworkError, digest

TEAM_TOOLS = (
    "send_team_message",
    "update_work_card",
    "get_work_board",
    "resolve_work_request",
    "publish_handoff_material",
    "read_handoff_material",
)


class MaterialReference(BaseModel):
    object_id: str
    revision: int
    digest: str | None = None


class TeamChannel:
    def __init__(self, task, repository, control, actor="modeling", materials=None):
        self.task, self.repository, self.control, self.actor = task, repository, control, actor
        self.materials = Path(materials) if materials is not None else None
        self.peers = {p["agent_id"]: p for p in task.get("collaboration", {}).get("peers", [])}
        self.work_units = {unit["unit_id"] for unit in task.get("work_units", [])}
        self.members = {"modeling", *self.peers, *self.work_units}
        if actor not in self.members:
            raise FrameworkError("team_actor_forbidden")
        self.prefix = f"run:{task['run_id']}:team:"

    def unit(self, actor):
        if actor in self.work_units:
            return actor
        return (
            self.task.get("_parent_work_unit_id", self.task["work_unit_id"])
            if actor == "modeling"
            else "peer:" + actor
        )

    def messages(self):
        return [
            m
            for m in self.control.view()["messages"]
            if m.get("metadata", {}).get("source") == "agent"
            and m["metadata"].get("run_id") == self.task["run_id"]
        ]

    def pending(self, actor):
        return [
            m
            for m in self.control.view()["messages"]
            if m["kind"] == "input"
            and m["target"] == self.unit(actor)
            and m["status"] in {"queued", "delivered"}
            and m.get("metadata", {}).get("run_id") == self.task["run_id"]
            and m.get("metadata", {}).get("phase") in {None, "model"}
        ]

    def _material(self, reference):
        if not {"object_id", "revision"}.issubset(reference):
            raise FrameworkError(
                "handoff_material_reference_invalid", required_fields=["object_id", "revision"]
            )
        row = self.repository.get(reference["object_id"], reference["revision"])
        if (
            not row
            or row["kind"] != "team_material"
            or not row["object_id"].startswith(self.prefix)
            or (
                reference.get("digest") is not None
                and digest(row["content"]) != reference["digest"]
            )
        ):
            raise FrameworkError("handoff_material_changed_or_missing")
        allowed = row["content"]["author"] == self.actor or any(
            m["target"] == self.unit(self.actor)
            and any(
                r.get("object_id") == reference["object_id"]
                and r.get("revision") == reference["revision"]
                for r in m["metadata"].get("material_refs", [])
            )
            for m in self.messages()
        )
        if not allowed:
            raise FrameworkError("handoff_material_forbidden")
        return row

    def publish(self, material_id, *, text=None, source_material_id=None, expected_revision=0):
        if not material_id.strip():
            raise FrameworkError("material_id_required")
        if (text is None) == (source_material_id is None):
            raise FrameworkError("supply_text_or_source_material_id")
        source = None
        if source_material_id is not None:
            manifest = self.task["source_manifest"]
            if source_material_id not in manifest or self.materials is None:
                raise FrameworkError("material_not_found")
            entry = manifest[source_material_id]
            path = (self.materials / entry["path"]).resolve()
            if not path.is_relative_to(self.materials.resolve()):
                raise FrameworkError("material_forbidden")
            payload = path.read_bytes()
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise FrameworkError("source_revision_changed")
            text, source = payload.decode(), {"material_id": source_material_id, **entry}
        content = {"author": self.actor, "text": text, "source": source}
        identity = self.prefix + "material:" + self.actor + ":" + material_id
        result = self.repository.put(identity, "team_material", content, expected_revision)
        if result.get("status") != "recorded":
            return result
        return {
            "object_id": identity,
            "revision": result["object"]["revision"],
            "digest": digest(content),
        }

    def read(self, reference, offset=0, limit=12000):
        row = self._material(reference)
        if offset < 0 or limit <= 0:
            raise FrameworkError("invalid_range")
        text = row["content"]["text"]
        end = min(len(text), offset + limit)
        return {
            "reference": {
                "object_id": row["object_id"],
                "revision": row["revision"],
                "digest": digest(row["content"]),
            },
            "author": row["content"]["author"],
            "source": row["content"]["source"],
            "offset": offset,
            "next_offset": end if end < len(text) else None,
            "total_characters": len(text),
            "text": text[offset:end],
        }

    def send(
        self, recipient_id, text, message_id, material_refs=None, work_request=None, reply_to=None
    ):
        if not message_id.strip():
            raise FrameworkError("message_id_required")
        if recipient_id not in self.members:
            raise FrameworkError(
                "team_recipient_not_found", allowed_recipients=sorted(self.members)
            )
        refs = []
        for reference in material_refs or []:
            row = self._material(reference)
            refs.append(
                {
                    "object_id": row["object_id"],
                    "revision": row["revision"],
                    "digest": digest(row["content"]),
                }
            )
        if work_request is not None and (
            set(work_request) - {"summary", "blocking"} or not work_request.get("summary")
        ):
            raise FrameworkError("invalid_work_request")
        if reply_to is not None and not any(
            m["id"] == reply_to
            and m["target"] == self.unit(self.actor)
            and m["metadata"]["author"] == recipient_id
            for m in self.messages()
        ):
            raise FrameworkError("team_reply_not_found")
        work = self.repository.get(f"run:{self.task['run_id']}:work")
        identity = self.prefix + self.actor + ":" + message_id
        prior = next((m for m in self.messages() if m["id"] == identity), None)
        if not prior and (
            self.control.view()["mode"] == "stopped"
            or (work and work["content"]["status"] == "handoff_ready")
        ):
            raise FrameworkError("team_task_closed")
        try:
            return self.control.enqueue(
                identity,
                "input",
                text,
                self.unit(recipient_id),
                metadata={
                    "source": "agent",
                    "author": self.actor,
                    "recipient": recipient_id,
                    "run_id": self.task["run_id"],
                    "material_refs": refs,
                    "work_request": work_request,
                    "reply_to": reply_to,
                },
            )
        except ValueError as error:
            raise FrameworkError("team_message_identity_conflict") from error

    def update_card(self, card, expected_revision=0):
        card = dict(card)
        if "expected_revision" in card:
            nested = card.pop("expected_revision")
            if expected_revision not in {0, nested}:
                raise FrameworkError("work_card_revision_conflict")
            expected_revision = nested
        if card.get("author") == self.actor:
            card.pop("author")
        allowed = {"current_work", "scope", "next_steps", "waiting_note", "result_refs"}
        if set(card) - allowed:
            raise FrameworkError(
                "invalid_work_card",
                allowed_fields=sorted(allowed),
                invalid_fields=sorted(set(card) - allowed),
                hint="author is bound by the tool; omit identity fields",
            )
        identity = self.prefix + "card:" + self.actor
        prior = self.repository.get(identity)
        content = {"author": self.actor, **card}
        if prior and {k: v for k, v in prior["content"].items() if k != "reported_at"} == content:
            return {"status": "recorded", "replayed": True, "object": prior}
        return self.repository.put(
            identity,
            "work_card",
            {**content, "reported_at": datetime.now(UTC).isoformat()},
            expected_revision,
        )

    def resolve_request(self, message_id, status):
        if status not in {"satisfied", "withdrawn"} or not any(
            m["id"] == message_id
            and m["metadata"]["author"] == self.actor
            and m["metadata"].get("work_request")
            for m in self.messages()
        ):
            raise FrameworkError(
                "work_request_resolution_forbidden",
                hint="only the originator resolves; recipient sends a reply_to instead",
            )
        return self.repository.put(
            self.prefix + "resolution:" + message_id,
            "work_resolution",
            {"author": self.actor, "status": status},
            0,
        )

    def board(self, agent_id=None, revision=None):
        actors = [agent_id] if agent_id is not None else sorted(self.members)
        if not set(actors).issubset(self.members):
            raise FrameworkError("team_recipient_not_found")
        result = []
        for actor in actors:
            card = self.repository.get(self.prefix + "card:" + actor, revision)
            requests = []
            for m in self.messages():
                if not m["metadata"].get("work_request") or actor not in {
                    m["metadata"]["author"],
                    m["metadata"]["recipient"],
                }:
                    continue
                resolution = self.repository.get(self.prefix + "resolution:" + m["id"])
                requests.append(
                    {
                        "message_id": m["id"],
                        **m["metadata"],
                        "delivery_status": m["status"],
                        "resolution": resolution["content"] if resolution else None,
                    }
                )
            result.append(
                {
                    "agent_id": actor,
                    "card": card,
                    "requests": requests,
                    "active_execution": self.control.view()["active"].get(self.unit(actor)),
                }
            )
        return {"agents": result, "complete": True}


def register_team_tools(server, channel):
    from mcp.server.fastmcp.exceptions import ToolError

    def call(method, *args, **kwargs):
        try:
            return method(*args, **kwargs)
        except FrameworkError as error:
            raise ToolError(json.dumps({**error.as_dict(), "recoverable": True})) from error

    @server.tool()
    def send_team_message(
        recipient_id: str,
        text: str,
        message_id: str,
        material_refs: list[MaterialReference] | None = None,
        work_request: dict | None = None,
        reply_to: str | None = None,
    ) -> dict:
        """Queue exact text and optional frozen materials/signed work request. Queued is not read."""
        refs = [r.model_dump(exclude_none=True) for r in material_refs or []]
        return call(channel.send, recipient_id, text, message_id, refs, work_request, reply_to)

    @server.tool()
    def publish_handoff_material(
        material_id: str,
        text: str | None = None,
        source_material_id: str | None = None,
        expected_revision: int = 0,
    ) -> dict:
        """Freeze own text OR an approved source without retranscribing it; return a versioned ref."""
        return call(
            channel.publish,
            material_id,
            text=text,
            source_material_id=source_material_id,
            expected_revision=expected_revision,
        )

    @server.tool()
    def read_handoff_material(
        reference: MaterialReference, offset: int = 0, limit: int = 12000
    ) -> dict:
        """Read own/received frozen material by character range, following next_offset as needed."""
        return call(channel.read, reference.model_dump(exclude_none=True), offset, limit)

    @server.tool()
    def update_work_card(card: dict, expected_revision: int = 0) -> dict:
        """Update ONLY own current_work, scope, next_steps, waiting_note and result_refs."""
        return call(channel.update_card, card, expected_revision)

    @server.tool()
    def get_work_board(agent_id: str | None = None, revision: int | None = None) -> dict:
        """Read member cards, exact historical version, signed requests and actual activity."""
        return call(channel.board, agent_id, revision)

    @server.tool()
    def resolve_work_request(message_id: str, status: str) -> dict:
        """Originator marks its own request satisfied or withdrawn; a reply alone does not resolve."""
        return call(channel.resolve_request, message_id, status)
