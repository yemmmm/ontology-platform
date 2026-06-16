from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PropertyType(StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    ENUM = "enum"
    REFERENCE = "reference"
    JSON = "json"


class PropertyDef(BaseModel):
    id: str
    name: str
    type: PropertyType
    description: str | None = None
    required: bool = False
    multi_valued: bool = False
    enum_values: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ClassDef(BaseModel):
    id: str
    name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    parent_class_ids: list[str] = Field(default_factory=list)
    properties: list[PropertyDef] = Field(default_factory=list)


class RelationTypeDef(BaseModel):
    id: str
    name: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    parent_relation_type_id: str | None = None
    source_class_id: str
    target_class_id: str
    inverse_name: str | None = None


class ConstraintDef(BaseModel):
    id: str
    scope: str
    kind: str
    severity: str = "error"
    expression: str | None = None


class OntologySchema(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None = None
    classes: list[ClassDef] = Field(default_factory=list)
    relation_types: list[RelationTypeDef] = Field(default_factory=list)
    constraints: list[ConstraintDef] = Field(default_factory=list)

