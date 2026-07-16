"""Extensible command handlers for immutable R-004 Modeling Items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.core.config import Settings
from app.repositories.rdf_store import RdfGraphDelta
from app.services.semantic_command_compiler import (
    CompiledCommand,
    InvalidCommandPayload,
    compile_command,
)
from app.services.semantic_export import namespace_from_settings
from app.services.semantic_rule_definition import (
    ALLOWED_INPUT_ROLES,
    ALLOWED_OUTPUT_KINDS,
    RuleDefinitionError,
    validate_construct_template,
    validate_platform_dsl,
    validate_workflow_state_machine,
)


FORBIDDEN_TARGET_FIELDS = {
    "ontology_id",
    "graph_set_id",
    "graph_iri",
    "target_graph_iri",
    "shape_graph_iris",
    "actor",
}

CREATE_RESOURCES: dict[str, tuple[str, str]] = {
    "create_class": ("class_id", "class"),
    "create_property": ("property_id", "property"),
    "create_relation_type": ("relation_type_id", "relation-type"),
    "create_shape": ("shape_id", "shape"),
    "create_entity": ("entity_id", "entity"),
    "create_mapping": ("mapping_id", "mapping"),
    "create_rule_definition": ("rule_id", "rule"),
    "create_operation": ("operation_id", "operation"),
}

RDF_COMMANDS = {
    "create_class",
    "update_class",
    "delete_class",
    "create_property",
    "update_property",
    "delete_property",
    "create_relation_type",
    "update_relation_type",
    "delete_relation_type",
    "create_shape",
    "update_shape",
    "delete_shape",
    "create_entity",
    "update_entity",
    "delete_entity",
    "create_relation",
    "delete_relation",
    "update_fact",
    "delete_fact",
    "create_mapping",
    "update_mapping",
    "delete_mapping",
    "create_operation",
    "update_operation",
    "delete_operation",
}
RULE_COMMANDS = {"create_rule_definition", "update_rule_definition", "delete_rule_definition"}

# The canonical compiler owns semantic validation. This table makes its accepted
# protocol explicit and rejects accidental/privileged fields before compilation.
ALLOWED_FIELDS: dict[str, set[str]] = {
    "create_class": {
        "class_id",
        "name",
        "description",
        "aliases",
        "parent_class_ids",
        "external_mappings",
    },
    "update_class": {"class_id", "class_iri", "name", "description", "aliases", "parent_class_ids"},
    "delete_class": {"class_id", "class_iri"},
    "create_property": {
        "property_id",
        "class_id",
        "name",
        "description",
        "datatype",
        "object_class_id",
    },
    "update_property": {
        "property_id",
        "property_iri",
        "name",
        "description",
        "datatype",
        "object_class_id",
    },
    "delete_property": {"property_id", "property_iri"},
    "create_relation_type": {
        "relation_type_id",
        "name",
        "source_class_id",
        "target_class_id",
        "description",
        "symmetric",
        "transitive",
        "scope_policy",
        "status",
    },
    "update_relation_type": {
        "relation_type_id",
        "relation_type_iri",
        "name",
        "description",
        "source_class_id",
        "target_class_id",
        "inverse_name",
    },
    "delete_relation_type": {"relation_type_id", "relation_type_iri"},
    "create_shape": {"shape_id", "target_class_id", "constraints"},
    "update_shape": {"shape_id", "shape_iri", "target_class_id", "constraints"},
    "delete_shape": {"shape_id", "shape_iri"},
    "create_entity": {"entity_id", "class_iri_or_legacy_id", "label", "aliases", "properties"},
    "update_entity": {"entity_id", "entity_iri", "label", "aliases", "properties"},
    "delete_entity": {"entity_id", "entity_iri"},
    "create_relation": {"source_entity_iri", "relation_type_iri", "target_entity_iri"},
    "delete_relation": {"source_entity_iri", "relation_type_iri", "target_entity_iri"},
    "update_fact": {
        "subject_iri",
        "predicate_iri",
        "old_object_value",
        "new_object_value",
        "old_object_is_iri",
        "new_object_is_iri",
    },
    "delete_fact": {"subject_iri", "predicate_iri", "object_value", "object_is_iri"},
    "create_mapping": {
        "mapping_id",
        "external_field_iri",
        "target_type",
        "target_iri",
        "join_key",
        "confidence",
        "owner",
        "source_id",
        "run_id",
        "import_run_iri",
    },
    "update_mapping": {
        "mapping_id",
        "mapping_iri",
        "join_key",
        "confidence",
        "owner",
        "target_type",
        "target_iri",
        "source_id",
        "run_id",
    },
    "delete_mapping": {"mapping_id", "mapping_iri", "source_id", "run_id"},
    "create_rule_definition": {
        "rule_id",
        "rule_iri",
        "name",
        "language",
        "body",
        "input_roles",
        "output_kind",
        "uses_inferred_facts",
        "requires_review",
        "priority",
        "safety_profile",
        "metadata",
    },
    "update_rule_definition": {
        "rule_id",
        "rule_iri",
        "name",
        "language",
        "body",
        "input_roles",
        "output_kind",
        "uses_inferred_facts",
        "requires_review",
        "priority",
        "safety_profile",
        "metadata",
    },
    "delete_rule_definition": {"rule_id", "rule_iri"},
    "create_operation": {
        "operation_id",
        "name",
        "aliases",
        "description",
        "target_resource_type_iri",
        "parameters",
        "preconditions",
        "effects",
        "possible_failures",
        "idempotency",
        "risk_level",
        "tool_bindings",
        "credential_requirements",
        "status",
        "schema_version",
    },
    "update_operation": {
        "operation_id",
        "operation_iri",
        "name",
        "aliases",
        "description",
        "target_resource_type_iri",
        "parameters",
        "preconditions",
        "effects",
        "possible_failures",
        "idempotency",
        "risk_level",
        "tool_bindings",
        "credential_requirements",
        "status",
        "schema_version",
    },
    "delete_operation": {"operation_id", "operation_iri"},
}


@dataclass(frozen=True)
class ModelingWriteEffect:
    item_id: str
    resource_key: str
    slot_key: str
    operation: str
    cardinality: str
    value_hash: str
    object_key: str = ""
    match_pattern: str | None = None
    cascade_footprint: tuple[str, ...] = ()


@dataclass
class PreparedModelingCommand:
    command_kind: str
    payload: dict[str, Any]
    outputs: dict[str, str]
    compiled: CompiledCommand | None
    storage: str


class ModelingCommandHandlerRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def command_kinds(self) -> list[str]:
        return sorted(RDF_COMMANDS | RULE_COMMANDS)

    def prepare(
        self,
        *,
        batch_id: str,
        ontology_id: str,
        client_item_id: str,
        command_kind: str,
        payload: dict[str, Any],
    ) -> PreparedModelingCommand:
        self.validate_payload_shape(command_kind, payload)
        normalized = dict(payload)
        outputs = self.outputs_for(
            batch_id=batch_id,
            ontology_id=ontology_id,
            client_item_id=client_item_id,
            command_kind=command_kind,
            payload=payload,
        )
        resource = CREATE_RESOURCES.get(command_kind)
        if resource:
            normalized[resource[0]] = outputs["resource_id"]
        if command_kind == "create_rule_definition":
            required = {"name", "language", "body", "input_roles"}
            if not required.issubset(normalized):
                raise InvalidCommandPayload(
                    f"Missing required Rule field(s): {', '.join(sorted(required - set(normalized)))}"
                )
            definition_data = {
                "name": normalized["name"],
                "language": normalized["language"],
                "body": normalized["body"],
                "input_roles": normalized["input_roles"],
                "output_kind": normalized.get("output_kind", "assertion"),
                "uses_inferred_facts": normalized.get("uses_inferred_facts", False),
                "requires_review": normalized.get("requires_review", False),
                "priority": normalized.get("priority", 0),
                "safety_profile": normalized.get("safety_profile", {}),
                "metadata": normalized.get("metadata", {}),
            }
            if definition_data["language"] not in {
                "sparql_construct",
                "platform_dsl",
                "workflow_state_machine",
            }:
                raise InvalidCommandPayload("Unsupported Rule language")
            if not definition_data["input_roles"]:
                raise InvalidCommandPayload("Rule must declare at least one input role")
            if set(definition_data["input_roles"]) - ALLOWED_INPUT_ROLES:
                raise InvalidCommandPayload("Rule declares an unsupported input role")
            if definition_data["output_kind"] not in ALLOWED_OUTPUT_KINDS:
                raise InvalidCommandPayload("Rule declares an unsupported output kind")
            _validate_rule_body(definition_data["language"], definition_data["body"])
            version = "sha256:" + _stable_value(definition_data)[:16]
            outputs["definition_id"] = str(
                uuid5(NAMESPACE_URL, f"modeling-rule:{outputs['resource_id']}:{version}")
            )
        if command_kind in RDF_COMMANDS:
            compiled = compile_command(
                command_kind, {"ontology_id": ontology_id, **normalized}, self.settings
            )
            if command_kind in {"create_shape", "update_shape", "delete_shape"}:
                workspace_shape_graph = (
                    f"{self.settings.semantic_graph_iri_prefix.rstrip('/')}/shapes/{ontology_id}"
                )
                delta = RdfGraphDelta(
                    inserts=[(*quad[:3], workspace_shape_graph) for quad in compiled.delta.inserts],
                    deletes=[(*quad[:3], workspace_shape_graph) for quad in compiled.delta.deletes],
                    clear_graphs=[workspace_shape_graph for _graph in compiled.delta.clear_graphs],
                    drop_graphs=[workspace_shape_graph for _graph in compiled.delta.drop_graphs],
                )
                compiled = CompiledCommand(
                    command_kind=compiled.command_kind,
                    delta=delta,
                    object_kind=compiled.object_kind,
                    source_ids=compiled.source_ids,
                    target_graph_iris=[workspace_shape_graph],
                    metadata={**compiled.metadata, "graph_iri": workspace_shape_graph},
                )
            return PreparedModelingCommand(command_kind, normalized, outputs, compiled, "rdf")
        return PreparedModelingCommand(command_kind, normalized, outputs, None, "postgres")

    @staticmethod
    def validate_payload_shape(command_kind: str, payload: dict[str, Any]) -> None:
        if command_kind not in ALLOWED_FIELDS:
            raise InvalidCommandPayload(f"Unsupported Modeling command: {command_kind}")
        forbidden = sorted(FORBIDDEN_TARGET_FIELDS.intersection(payload))
        if forbidden:
            raise InvalidCommandPayload(f"Forbidden target override: {', '.join(forbidden)}")
        unknown = sorted(set(payload) - ALLOWED_FIELDS[command_kind])
        if unknown:
            raise InvalidCommandPayload(f"Unknown payload field(s): {', '.join(unknown)}")
        if command_kind.endswith("mapping") and ({"source_id", "run_id"} & set(payload)):
            raise InvalidCommandPayload(
                "unsupported_batch_variant: import-run Mapping commands are not accepted"
            )

    def outputs_for(
        self,
        *,
        batch_id: str,
        ontology_id: str,
        client_item_id: str,
        command_kind: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        resource = CREATE_RESOURCES.get(command_kind)
        if resource is None:
            return {}
        id_field, resource_kind = resource
        resource_id = str(
            payload.get(id_field)
            or uuid5(
                NAMESPACE_URL,
                f"ontology-platform:modeling:{batch_id}:{ontology_id}:"
                f"{client_item_id}:{command_kind}",
            )
        )
        resource_iri = (
            str(payload["rule_iri"])
            if command_kind == "create_rule_definition" and payload.get("rule_iri")
            else str(namespace_from_settings(self.settings).resource(resource_kind, resource_id))
        )
        return {
            "resource_id": resource_id,
            "resource_iri": resource_iri,
        }

    @staticmethod
    def effects(item_id: str, prepared: PreparedModelingCommand) -> list[ModelingWriteEffect]:
        if prepared.compiled is None:
            rule_key = str(
                prepared.payload.get("rule_id") or prepared.payload.get("rule_iri") or item_id
            )
            return [
                ModelingWriteEffect(
                    item_id,
                    f"rule:{rule_key}",
                    "*",
                    "delete" if prepared.command_kind.startswith("delete_") else "write",
                    "single",
                    _stable_value(prepared.payload),
                    cascade_footprint=(f"rule:{rule_key}:*",),
                )
            ]
        effects: list[ModelingWriteEffect] = []
        for operation, quads in (
            ("delete", prepared.compiled.delta.deletes),
            ("insert", prepared.compiled.delta.inserts),
        ):
            for subject, predicate, obj, graph_iri in quads:
                wildcard = "?" in subject or "?" in predicate or "?" in obj
                effects.append(
                    ModelingWriteEffect(
                        item_id=item_id,
                        resource_key=f"{graph_iri}:{subject}",
                        slot_key=predicate,
                        operation=operation,
                        cardinality="multi" if _is_multi_value_predicate(predicate) else "single",
                        value_hash=_stable_value(obj),
                        object_key=obj,
                        match_pattern=f"{subject} {predicate} {obj}" if wildcard else None,
                        cascade_footprint=(f"{graph_iri}:{subject}:*",) if wildcard else (),
                    )
                )
        if prepared.command_kind == "delete_class":
            class_iri = prepared.compiled.metadata.get("class_iri")
            graph_iri = prepared.compiled.target_graph_iris[0]
            if class_iri:
                class_term = f"<{class_iri}>"
                effects.append(
                    ModelingWriteEffect(
                        item_id=item_id,
                        resource_key=f"{graph_iri}:{class_term}",
                        slot_key="*",
                        operation="delete",
                        cardinality="single",
                        value_hash=_stable_value(class_term),
                        object_key=class_term,
                        match_pattern=f"?s ?p {class_term}",
                        cascade_footprint=(f"{graph_iri}:class-dependent:{class_term}:*",),
                    )
                )
        return effects


def union_delta(commands: list[PreparedModelingCommand]) -> RdfGraphDelta:
    inserts: set[tuple[str, str, str, str]] = set()
    deletes: set[tuple[str, str, str, str]] = set()
    clear_graphs: set[str] = set()
    drop_graphs: set[str] = set()
    for command in commands:
        if command.compiled is None:
            continue
        inserts.update(command.compiled.delta.inserts)
        deletes.update(command.compiled.delta.deletes)
        clear_graphs.update(command.compiled.delta.clear_graphs)
        drop_graphs.update(command.compiled.delta.drop_graphs)
    return RdfGraphDelta(
        inserts=sorted(inserts),
        deletes=sorted(deletes),
        clear_graphs=sorted(clear_graphs),
        drop_graphs=sorted(drop_graphs),
    )


def _stable_value(value: Any) -> str:
    import hashlib
    import json

    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _validate_rule_body(language: str, body: dict[str, Any]) -> None:
    try:
        if language == "sparql_construct":
            validate_construct_template(body)
        elif language == "platform_dsl":
            validate_platform_dsl(body)
        elif language == "workflow_state_machine":
            validate_workflow_state_machine(body)
    except RuleDefinitionError as exc:
        raise InvalidCommandPayload(str(exc)) from exc


def _is_multi_value_predicate(predicate: str) -> bool:
    return predicate in {
        "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type>",
        "<http://www.w3.org/2000/01/rdf-schema#subClassOf>",
        "<http://www.w3.org/2004/02/skos/core#altLabel>",
        "<http://www.w3.org/ns/shacl#property>",
        "<http://www.w3.org/ns/shacl#in>",
    }
