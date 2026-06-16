from typing import Any

from pydantic import BaseModel, Field


class Entity(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    ontology_version_id: str | None = None
    class_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    id: str
    project_id: str
    ontology_id: str
    ontology_version_id: str | None = None
    relation_type_id: str
    source_entity_id: str
    target_entity_id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphQuerySpec(BaseModel):
    start_entity_id: str
    relation_type_ids: list[str] = Field(default_factory=list)
    direction: str = "outgoing"
    depth: int = 1
    target_class_ids: list[str] = Field(default_factory=list)
    limit: int = 50

