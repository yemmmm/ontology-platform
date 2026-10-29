"""Small task-shared business notes on the existing versioned workspace."""

from datetime import UTC, datetime

from .contracts import bound_project_ref

MEMORY_TOOLS = ("write_memory", "read_memory", "search_memory")


class SharedMemory:
    def __init__(self, repository, actor, project_ref=None, task=None):
        self.repository, self.actor = repository, actor
        self.task = task
        from .workspace import WorkspaceRepository

        project_ref = project_ref or (bound_project_ref(task, repository) if task else None)

        self.project = (
            WorkspaceRepository(repository.connection, repository.schema, "project:" + project_ref)
            if project_ref
            else None
        )

    def scoped(self, scope):
        if scope == "task":
            return self
        if scope == "project" and self.project:
            return SharedMemory(self.project, self.actor, task=self.task)
        from .contracts import FrameworkError

        raise FrameworkError("workspace_scope_unavailable", scope=scope)

    @staticmethod
    def entry(row):
        return {
            "entry_id": row["object_id"].removeprefix("memory:"),
            "revision": row["revision"],
            "authority": "business_memory",
            **row["content"],
        }

    def read(self, entry_id, revision=None):
        row = self.repository.get("memory:" + entry_id, revision)
        return self.entry(row) if row else {"state": "not_found", "entry_id": entry_id}

    def write(
        self,
        entry_id,
        kind,
        title,
        body,
        source_refs=None,
        expected_revision=0,
        applicability="current",
    ):
        identity = "memory:" + entry_id
        content = {
            "kind": kind,
            "title": title,
            "body": body,
            "source_refs": source_refs or [],
            "applicability": applicability,
        }
        if self.task:
            content.update(
                origin_task_ref=self.task["task_ref"],
                origin_run_id=self.task["run_id"],
                unit_id=self.actor,
            )
        prior = self.repository.get(identity)
        if prior and all(prior["content"].get(k) == v for k, v in content.items()):
            return {"status": "recorded", "replayed": True, "entry": self.entry(prior)}
        result = self.repository.put(
            identity,
            "shared_memory",
            {**content, "author": self.actor, "updated_at": datetime.now(UTC).isoformat()},
            expected_revision,
        )
        if result.get("status") == "recorded":
            return {
                "status": "recorded",
                "replayed": result["replayed"],
                "entry": self.entry(result["object"]),
            }
        if result.get("code") == "version_conflict" and result.get("actual"):
            result["actual"] = self.entry(result["actual"])
        return result

    def search(self, query="", kind=None, limit=10, offset=0):
        rows = self.repository.list_kind("shared_memory")
        matches = [
            row
            for row in rows
            if (kind is None or row["content"]["kind"] == kind)
            and query.casefold()
            in " ".join(
                str(row["content"].get(k, "")) for k in ["title", "body", "kind"]
            ).casefold()
        ]
        limit, offset = max(1, limit), max(0, offset)
        selected = matches[offset : offset + limit]
        return {
            "entries": [
                {
                    "entry_id": row["object_id"].removeprefix("memory:"),
                    "revision": row["revision"],
                    "kind": row["content"]["kind"],
                    "title": row["content"]["title"],
                    "preview": row["content"]["body"][:400],
                    "applicability": row["content"].get("applicability", "current"),
                }
                for row in selected
            ],
            "total": len(matches),
            "next_offset": offset + limit if offset + limit < len(matches) else None,
        }


def register_memory_tools(server, memory):
    @server.tool()
    def write_memory(
        entry_id: str,
        kind: str,
        title: str,
        body: str,
        source_refs: list[dict] | None = None,
        expected_revision: int = 0,
        scope: str = "task",
        applicability: str = "current",
    ) -> dict:
        """Save a shared judgment/decision/open item. On updates use read entry's revision as
        top-level expected_revision; a version conflict returns current content for your merge.
        This records business understanding, not an applied model or human confirmation."""
        return memory.scoped(scope).write(
            entry_id, kind, title, body, source_refs, expected_revision, applicability
        )

    @server.tool()
    def read_memory(entry_id: str, revision: int | None = None, scope: str = "task") -> dict:
        """Read full current business note, or an exact older revision, by entry_id."""
        return memory.scoped(scope).read(entry_id, revision)

    @server.tool()
    def search_memory(
        query: str = "",
        kind: str | None = None,
        limit: int = 10,
        offset: int = 0,
        scope: str = "task",
    ) -> dict:
        """Find unknown note IDs by case-insensitive text and optional kind. Previews navigate;
        use read_memory to obtain full conditions, exceptions, source refs and current revision."""
        return memory.scoped(scope).search(query, kind, limit, offset)
