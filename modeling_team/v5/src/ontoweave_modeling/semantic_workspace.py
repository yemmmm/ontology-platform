"""Persistent propositions, decisions and derived navigation, separate from applied models."""

from datetime import UTC, datetime

from .contracts import FrameworkError, bound_project_ref, digest

WORKSPACE_TOOLS = (
    "write_semantic_record",
    "read_semantic_record",
    "search_semantic_records",
    "get_modeling_context",
)


class SemanticWorkspace:
    def __init__(self, repository, task, actor="modeling", *, view="production"):
        from .workspace import WorkspaceRepository

        self.repository, self.task, self.actor, self.view = repository, task, actor, view
        self.model_revisions = {}
        self.project_ref = bound_project_ref(task, repository)
        self.project = (
            WorkspaceRepository(
                repository.connection, repository.schema, "project:" + self.project_ref
            )
            if self.project_ref
            else None
        )

    def observe_models(self, model_revisions):
        """Host snapshots or successful governed reads supply these, never note arguments."""
        self.model_revisions = dict(model_revisions)
        repository = self.project or self.repository
        for ontology_id, revision in model_revisions.items():
            repository.put_reference(
                f"model-observation:{ontology_id}:{revision}",
                "model_observation",
                {"ontology_id": ontology_id, "model_revision": revision},
                0,
            )

    def observed_models(self):
        revisions = {}
        for row in (self.project or self.repository).list_kind("model_observation"):
            content = row["content"]
            ontology_id = content["ontology_id"]
            revisions[ontology_id] = max(revisions.get(ontology_id, -1), content["model_revision"])
        return revisions

    def scoped(self, scope):
        if scope == "task":
            return self.repository
        if scope == "project" and self.project is not None:
            return self.project
        raise FrameworkError("workspace_scope_unavailable", scope=scope)

    @staticmethod
    def _valid_dependency(ref):
        return (
            isinstance(ref, dict)
            and isinstance(ref.get("record_id"), str)
            and bool(ref["record_id"])
            and type(ref.get("revision")) is int
            and ref["revision"] > 0
            and ref.get("scope", "task") in {"task", "project"}
        )

    def write(
        self,
        record_id,
        kind,
        title,
        body,
        source_refs=None,
        depends_on=None,
        states=None,
        expected_revision=0,
        scope="task",
        unit_id=None,
    ):
        states = states or {}
        for index, ref in enumerate(depends_on or []):
            if not self._valid_dependency(ref):
                raise FrameworkError(
                    "invalid_dependency_reference",
                    path=f"/depends_on/{index}",
                    instruction="Use the exact returned semantic record reference with record_id, "
                    "revision and scope directly; do not wrap it in reference. "
                    "Material IDs/SHA256 belong in source_refs, not depends_on. "
                    "Read the semantic record first to obtain its actual revision.",
                )
        if {"application", "acceptance"} & states.keys():
            raise FrameworkError(
                "host_observation_required",
                instruction="Reference actual application or independent reports; do not assign their state from notes.",
            )
        sources = []
        for ref in source_refs or []:
            entry = self.task["source_manifest"].get(ref["material_id"])
            if entry is None or ref.get("sha256", entry["sha256"]) != entry["sha256"]:
                raise FrameworkError(
                    "source_reference_mismatch",
                    material_id=ref["material_id"],
                    expected_sha256=entry["sha256"] if entry else None,
                    actual_sha256=ref.get("sha256"),
                )
            sources.append({**entry, **ref, "sha256": entry["sha256"]})
        repository = self.scoped(scope)
        identity = "semantic:" + record_id
        content = {
            "kind": kind,
            "title": title,
            "body": body,
            "source_refs": sources,
            "depends_on": depends_on or [],
            "states": {"applicability": "current", **states},
            "unit_id": unit_id or self.actor,
            "view": self.view,
            "origin_task_ref": self.task["task_ref"],
            "origin_run_id": self.task["run_id"],
            "author": self.actor,
        }
        if self.model_revisions and (
            kind in {"summary", "coverage", "definition"} or self.view != "production"
        ):
            content["model_basis"] = dict(self.model_revisions)
        prior = repository.get(identity)
        if prior and all(prior["content"].get(k) == v for k, v in content.items()):
            return {
                "status": "recorded",
                "replayed": True,
                "record": self.read(record_id, scope=scope),
            }
        result = repository.put(
            identity,
            "semantic_record",
            {**content, "updated_at": datetime.now(UTC).isoformat()},
            expected_revision,
        )
        if result.get("status") == "recorded":
            return {
                "status": "recorded",
                "replayed": result["replayed"],
                "record": self.read(record_id, scope=scope),
            }
        if result.get("actual"):
            result["actual"] = self.read(record_id, scope=scope)
        return result

    def freshness(self, row, seen=None, scope="task"):
        content = row["content"]
        if content.get("states", {}).get("applicability") != "current":
            return {"state": "needs_review", "reason": content.get("invalidation")}
        seen = set() if seen is None else seen
        identity = (scope, row["object_id"])
        if identity in seen:
            return {"state": "needs_review", "reason": "dependency_cycle"}
        changed, invalid = [], []
        model_basis = content.get("model_basis", {})
        observed = self.observed_models() if model_basis else {}
        changed_models = {
            key: {"basis": revision, "observed": observed.get(key)}
            for key, revision in model_basis.items()
            if observed.get(key) != revision
        }
        for ref in content.get("depends_on", []):
            if not self._valid_dependency(ref):
                invalid.append(ref)
                continue
            dependency = self.scoped(ref.get("scope", "task")).get("semantic:" + ref["record_id"])
            if (
                not dependency
                or dependency["content"].get("view") != self.view
                or dependency["revision"] != ref.get("revision")
                or self.freshness(dependency, seen | {identity}, ref.get("scope", "task"))["state"]
                != "current"
            ):
                changed.append(ref)
        return {
            "state": "needs_review" if changed or changed_models or invalid else "current",
            "changed_dependencies": changed,
            "invalid_dependencies": invalid,
            "changed_models": changed_models,
            "model_state": "changed"
            if changed_models
            else "observed"
            if model_basis
            else "not_checked",
            "basis": "source/dependency versions and last observed actual model revisions; exact judgments require governed reads",
        }

    def read(self, record_id, revision=None, scope="task"):
        row = self.scoped(scope).get("semantic:" + record_id, revision)
        if (
            row is None
            or row["kind"] != "semantic_record"
            or row["content"].get("view") != self.view
        ):
            return {"state": "not_found", "record_id": record_id}
        current = self.scoped(scope).get(row["object_id"])
        freshness = (
            self.freshness(row, scope=scope)
            if current["revision"] == row["revision"]
            else {"state": "historical", "current_revision": current["revision"]}
        )
        return {
            "record_id": record_id,
            "revision": row["revision"],
            "scope": scope,
            "reference": {
                "record_id": record_id,
                "scope": scope,
                "revision": row["revision"],
                "digest": digest(row["content"]),
            },
            "authority": "model_navigation"
            if self.view in {"consumer", "user"}
            else "candidate_workspace",
            **row["content"],
            "freshness": freshness,
        }

    def search(
        self,
        query="",
        kind=None,
        unit_id=None,
        scope="task",
        limit=20,
        offset=0,
        include_authored=False,
    ):
        rows = [
            r
            for r in self.scoped(scope).list_kind("semantic_record")
            if r["content"].get("view") == self.view
            and (kind is None or r["content"]["kind"] == kind)
            and (
                unit_id is None
                or r["content"]["unit_id"] == unit_id
                or (include_authored and r["content"].get("author") == unit_id)
            )
            and query.casefold() in (r["content"]["title"] + " " + r["content"]["body"]).casefold()
        ]
        return {
            "records": [
                {
                    "record_id": r["object_id"].removeprefix("semantic:"),
                    "revision": r["revision"],
                    "kind": r["content"]["kind"],
                    "title": r["content"]["title"],
                    "preview": r["content"]["body"][:400],
                    "states": r["content"].get("states", {}),
                    "model_basis": r["content"].get("model_basis", {}),
                    "freshness": self.freshness(r, scope=scope),
                }
                for r in rows[offset : offset + limit]
            ],
            "total": len(rows),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "scope": scope,
            "unit_id": unit_id,
            "include_authored": include_authored,
            "authority": "candidate_workspace",
        }

    def context(self):
        return {
            "objective": self.task["objective"],
            "unit_id": self.actor,
            "source_manifest": self.task["source_manifest"],
            "assigned_material_ids": self.task.get("assigned_material_ids", []),
            "project_ref": self.project_ref,
            "local": self.search(unit_id=self.actor, limit=10, include_authored=True),
            "project_local": self.search(
                unit_id=self.actor, scope="project", limit=10, include_authored=True
            )
            if self.project
            else None,
            "open_items": self.search(kind="open_item", limit=10),
            "project_navigation": self.search(kind="summary", scope="project", limit=10)
            if self.project
            else None,
            "instruction": "Read relevant existing records in both scopes before creating new notes. "
            "Local pages include notes assigned to or authored by this unit; continue them with "
            "search_semantic_records using unit_id, include_authored=true, scope and next_offset. "
            "Use stable IDs and exact revisions to refresh coverage after actual reads, or explicitly "
            "supersede obsolete records. States, body and model basis must describe the same scope; "
            "a current model does not close old workspace gaps. Follow next_offset where needed. "
            "Navigate to approved originals and actual models; notes are not application or acceptance proof.",
        }

    def invalidate_sources(
        self, previous_manifest, changed_ids, change_id, affected_units=None, affected_records=()
    ):
        old = {
            key: previous_manifest[key]["sha256"] for key in changed_ids if key in previous_manifest
        }
        changed = []
        for scope, repository in [
            ("task", self.repository),
            *([("project", self.project)] if self.project else []),
        ]:
            for kind in ("semantic_record", "shared_memory"):
                for row in repository.list_kind(kind):
                    content = row["content"]
                    if content.get("invalidation", {}).get("change_id") == change_id:
                        continue
                    local_impact = (
                        scope == "task" or content.get("origin_task_ref") == self.task["task_ref"]
                    ) and content.get("unit_id", content.get("author")) in (
                        set(affected_units or []) | {"modeling"}
                    )
                    explicit = {
                        "scope": scope,
                        "record_id": row["object_id"].removeprefix("semantic:"),
                    }
                    if (
                        explicit not in affected_records
                        and not local_impact
                        and not any(
                            ref.get("material_id") in old
                            and ref.get("sha256") == old[ref["material_id"]]
                            for ref in content.get("source_refs", [])
                        )
                    ):
                        continue
                    updated = {
                        **content,
                        "invalidation": {
                            "change_id": change_id,
                            "reason": "source revised or withdrawn; semantic impact requires review",
                        },
                    }
                    if kind == "semantic_record":
                        updated["states"] = {
                            **content.get("states", {}),
                            "applicability": "needs_review",
                        }
                    else:
                        updated["applicability"] = "needs_review"
                    repository.put_reference(row["object_id"], kind, updated, row["revision"])
                    changed.append({"scope": scope, "object_id": row["object_id"]})
        return changed


def register_workspace_tools(server, workspace):
    import json

    from mcp.server.fastmcp.exceptions import ToolError

    def call(method, *args):
        try:
            return method(*args)
        except FrameworkError as error:
            raise ToolError(json.dumps(error.as_dict())) from error

    @server.tool()
    def write_semantic_record(
        record_id: str,
        kind: str,
        title: str,
        body: str,
        source_refs: list[dict] | None = None,
        depends_on: list[dict] | None = None,
        states: dict | None = None,
        expected_revision: int = 0,
        scope: str = "task",
        unit_id: str | None = None,
    ) -> dict:
        """Persist a material_review, proposition, interpretation, decision, definition, coverage,
        open_item or summary. Keep full conditions/exceptions/unknowns. states independently records
        review/cognition/expression/work/applicability, never application/acceptance. depends_on uses
        exact returned reference objects; source refs name approved material_id plus optional ranges.
        Project scope is available only for this Host-bound project. On conflict reread and merge."""
        return call(
            workspace.write,
            record_id,
            kind,
            title,
            body,
            source_refs,
            depends_on,
            states,
            expected_revision,
            scope,
            unit_id,
        )

    @server.tool()
    def read_semantic_record(
        record_id: str, revision: int | None = None, scope: str = "task"
    ) -> dict:
        """Read full authorized content and dependency/source freshness, or an exact historical revision."""
        return call(workspace.read, record_id, revision, scope)

    @server.tool()
    def search_semantic_records(
        query: str = "",
        kind: str | None = None,
        unit_id: str | None = None,
        scope: str = "task",
        limit: int = 20,
        offset: int = 0,
        include_authored: bool = False,
    ) -> dict:
        """Locate records by text, kind and unit. include_authored also matches that unit's author
        field, for paging local context. Preserve returned filters and read complete records."""
        return call(workspace.search, query, kind, unit_id, scope, limit, offset, include_authored)

    @server.tool()
    def get_modeling_context() -> dict:
        """Assemble a bounded restart/compression context: goal, sources, local/open-item refs and project navigation."""
        return workspace.context()
