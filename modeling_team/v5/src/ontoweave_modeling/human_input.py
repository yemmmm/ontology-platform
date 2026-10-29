"""Task-scoped human questions and replies; business interpretation stays with the Agent."""

from __future__ import annotations

from .contracts import FrameworkError, digest, safe_id


class HumanInput:
    def __init__(self, binding, repository, control):
        self.binding, self.repository, self.control = binding, repository, control
        self.unit = binding.data["work_unit_id"]

    def ask(self, phase, questions, basis_ref, execution_ref):
        identities = []
        for question in questions:
            content = {
                **question,
                "run_id": self.binding.data["run_id"],
                "work_unit_id": self.unit,
                "phase": phase,
                "basis_ref": basis_ref,
                "source_revisions": {
                    key: value["sha256"]
                    for key, value in self.binding.data["source_manifest"].items()
                },
            }
            identity = "human-request-" + digest(content)[:24]
            if self.repository.get(identity) is None:
                self.repository.put_reference(
                    identity, "human_request", {**content, "execution_ref": execution_ref}, 0
                )
            identities.append(identity)
        return identities

    def requests(self):
        messages = self.control.view()["messages"]
        result = []
        for row in self.repository.list_kind("human_request"):
            content = row["content"]
            if content["run_id"] != self.binding.data["run_id"]:
                continue
            if self.binding.is_child and content["work_unit_id"] != self.unit:
                continue
            identity = row["object_id"]
            replies = [m for m in messages if m.get("metadata", {}).get("request_id") == identity]
            resolved = self.repository.get("human-resolution:" + identity)
            state = "resolved" if resolved else "awaiting_answer"
            if replies and not resolved:
                state = "answer_" + replies[-1]["status"]
            result.append(
                {
                    "request_id": identity,
                    "request_ref": {
                        "object_id": identity,
                        "revision": row["revision"],
                        "digest": digest(content),
                    },
                    **content,
                    "status": state,
                    "reply_ids": [m["id"] for m in replies],
                    "replies": [
                        {
                            "message_id": m["id"],
                            "body": m["body"],
                            "metadata": m.get("metadata", {}),
                            "status": m["status"],
                        }
                        for m in replies
                    ],
                }
            )
        return result

    def submit(
        self,
        body,
        message_id,
        *,
        request_id=None,
        partial=False,
        author="user",
        request_revision=None,
    ):
        safe_id(message_id)
        if not body.strip() or not author.strip():
            raise FrameworkError("human_input_empty")
        answer_id = "human-answer:" + message_id
        prior = self.repository.get(answer_id)
        if prior:
            answer = prior["content"]
            metadata = answer["metadata"]
            if metadata.get("run_id") not in {None, self.binding.data["run_id"]}:
                raise FrameworkError("human_input_identity_conflict")
            if (
                request_revision is not None
                and (metadata.get("request_ref") or {}).get("revision") != request_revision
            ):
                raise FrameworkError(
                    "human_request_version_changed", actual=metadata.get("request_ref")
                )
            if (
                answer["body"],
                metadata["request_id"],
                metadata["partial"],
                metadata["author"],
            ) != (body, request_id, partial, author):
                raise FrameworkError("human_input_identity_conflict")
        else:
            work = self.repository.get(self.binding.identity + ":work")
            if self.control.view()["mode"] == "stopped" or (
                work and work["content"]["status"] in {"handoff_ready", "stopped"}
            ):
                raise FrameworkError("human_input_task_closed")
            question = None
            if request_id is not None:
                question = next((r for r in self.requests() if r["request_id"] == request_id), None)
                if question is None:
                    raise FrameworkError("human_request_not_found")
                if question["status"] == "resolved":
                    raise FrameworkError("human_request_already_resolved")
                if (
                    request_revision is not None
                    and question["request_ref"]["revision"] != request_revision
                ):
                    raise FrameworkError(
                        "human_request_version_changed", actual=question["request_ref"]
                    )
            metadata = {
                "source": "user",
                "run_id": self.binding.data["run_id"],
                "author": author,
                "request_id": request_id,
                "request_ref": question["request_ref"] if question else None,
                "phase": question["phase"] if question else None,
                "partial": partial,
                "basis_ref": question["basis_ref"]
                if question
                else (
                    work["content"].get("target_ref", work["content"].get("baseline_ref"))
                    if work
                    else None
                ),
            }
            answer = {
                "body": body,
                "metadata": metadata,
                "work_unit_id": question["work_unit_id"] if question else self.unit,
            }
            self.repository.put_reference(answer_id, "human_answer", answer, 0)
        queued = self.control.enqueue(
            message_id, "input", body, answer["work_unit_id"], metadata=answer["metadata"]
        )
        return {"message": queued, "request_id": request_id}

    def pending(self, phase):
        return [
            m
            for m in self.control.view()["messages"]
            if m["kind"] == "input"
            and m["target"] in {None, self.unit}
            and m["status"] in {"queued", "delivered"}
            and m.get("metadata", {}).get("phase") in {None, phase}
            and m.get("metadata", {}).get("run_id") in {None, self.binding.data["run_id"]}
        ]

    def context(self):
        return {
            "requests": [{k: v for k, v in r.items() if k != "replies"} for r in self.requests()],
            "answers": [
                {
                    "message_id": m["id"],
                    "body": m["body"],
                    "metadata": m.get("metadata", {}),
                    "status": m["status"],
                }
                for m in self.control.view()["messages"]
                if m["kind"] == "input"
                and m["target"]
                in {
                    None,
                    self.unit,
                    *(
                        u["unit_id"]
                        for u in self.binding.data.get("work_units", [])
                        if not self.binding.is_child
                    ),
                }
                and m.get("metadata", {}).get("source") == "user"
                and m.get("metadata", {}).get("run_id") in {None, self.binding.data["run_id"]}
            ],
        }

    def validate_resolutions(self, execution, consumed_ids, resolved_ids):
        inputs = self.repository.read_reference(execution)["inputs"]
        allowed = {
            m.get("metadata", {}).get("request_id")
            for m in inputs
            if m["id"] in consumed_ids
            and m.get("metadata", {}).get("source") == "user"
            and not m.get("metadata", {}).get("partial", False)
        }
        already_resolved = {r["request_id"] for r in self.requests() if r["status"] == "resolved"}
        if not set(resolved_ids).issubset((allowed - {None}) | already_resolved):
            raise FrameworkError(
                "human_resolution_unconfirmed",
                allowed_human_request_ids=sorted((allowed - {None}) | already_resolved),
                hint="team work requests use resolve_work_request, not resolved_request_ids",
            )

    def resolve(self, execution, consumed_ids, resolved_ids):
        for identity in resolved_ids:
            key = "human-resolution:" + identity
            if self.repository.get(key) is None:
                self.repository.put_reference(
                    key,
                    "human_resolution",
                    {
                        "request_id": identity,
                        "execution_ref": execution,
                        "consumed_ids": consumed_ids,
                    },
                    0,
                )
