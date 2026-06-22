export type JsonObject = Record<string, unknown>;

export type Notice = { kind: "ok" | "error" | "info"; message: string } | null;

export type Project = {
  id: string;
  name: string;
  description: string | null;
  created_at?: string;
  updated_at?: string;
};

export type Ontology = {
  id: string;
  project_id: string;
  current_version_id: string | null;
  name: string;
  description: string | null;
  status: string;
  external_mappings?: JsonObject;
  created_at?: string;
  updated_at?: string;
};

export type ClassDef = {
  id: string;
  ontology_id: string;
  name: string;
  normalized_label?: string;
  description: string | null;
  aliases: string[];
  parent_class_ids: string[];
  external_mappings?: JsonObject;
};

export type PropertyDef = {
  id: string;
  class_id: string;
  name: string;
  type: string;
  description: string | null;
  required: boolean;
  multi_valued: boolean;
  enum_values: string[];
  constraints?: JsonObject;
  external_mappings?: JsonObject;
};

export type RelationType = {
  id: string;
  ontology_id: string;
  name: string;
  description: string | null;
  aliases: string[];
  parent_relation_type_id: string | null;
  source_class_id: string;
  target_class_id: string;
  inverse_name: string | null;
  normalized_type?: string;
  external_mappings?: JsonObject;
};

export type Entity = {
  id: string;
  project_id: string;
  ontology_id: string;
  ontology_version_id: string | null;
  class_id: string;
  class_label: string;
  name: string;
  aliases: string[];
  properties: JsonObject;
};

export type Relation = {
  id: string;
  project_id: string;
  ontology_id: string;
  ontology_version_id: string | null;
  relation_type_id: string;
  relation_type: string;
  source_entity_id: string;
  target_entity_id: string;
  properties: JsonObject;
};

export type EntitySearchResult = {
  results: Array<Entity & {
    score: number;
    match_source: "text" | "vector" | "hybrid";
  }>;
  count: number;
};

export type EntityWithRelations = Entity & {
  outgoing: Relation[];
  incoming: Relation[];
};

export type RelatedEntity = {
  entity: Entity;
  relations: Relation[];
};

export type EntityExplain = {
  entity: Entity;
  class_schema: (ClassDef & { properties: PropertyDef[] }) | null;
  direct_relations: Relation[];
  related_entities: RelatedEntity[];
  explain_text: string;
};

export type OntologyExport = {
  ontology: Ontology;
  classes: Array<ClassDef & { properties: PropertyDef[] }>;
  relation_types: RelationType[];
  entities: Entity[];
  relations: Relation[];
};

export type AgentTestResponse = {
  answer: string;
  tool_calls: JsonObject[];
  graph_context: JsonObject;
  prompt_preview: string;
  warnings: string[];
  errors: string[];
};

export type Health = Record<string, unknown>;
