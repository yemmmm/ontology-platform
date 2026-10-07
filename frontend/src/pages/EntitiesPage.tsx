/**
 * Stage 2 §5 — graph-derived EntitiesPage.
 *
 * MVP slice: renders entities from the entity-list read model and edges
 * from entity-relations as a topology graph. Exposes a "New entity" button
 * that creates an entity via canonical-write (create_entity). Inline
 * editing lands in a later iteration.
 *
 * The legacy inline EntitiesPage remains in App.tsx as the fallback when
 * no ?graphSet= URL parameter is set.
 */

import { Alert, Button, Card, Input, Modal, Segmented, Skeleton, Tag } from "antd";
import { Edit3, Link2, Plus, RefreshCw, Save, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ForceGraphCanvas,
  type ForceGraphEdge,
  type ForceGraphNode,
} from "../components/ForceGraphCanvas";
import { useT } from "../i18n";
import {
  compileAndApplyProductCommand,
  readModel,
} from "../semanticApi";
import type { WorkbenchRequest } from "./workbenchTypes";

type EntityListRow = {
  iri: string;
  label: string | null;
  source_graph_iri: string;
  assertion_kind: string;
  /** R3.0-009 §6.2/§9.3: the full visible formal Class set, deduplicated and
   * IRI-sorted. An empty array is the legal zero-class state, never a
   * truncation. */
  class_iris?: string[];
  /** Formal Classes whose `/vocab/id` identity anchor is not visible. */
  incomplete_class_identity_iris?: string[];
  /** Legacy single-value projection (lexicographically first visible Class).
   * Never multi-class truth; kept so older payloads still render. */
  class_iri?: string | null;
  class_label?: string;
};

/** Full formal Class set of a row, with the legacy scalar fallback. */
function entityClassIris(row: EntityListRow): string[] {
  if (Array.isArray(row.class_iris)) {
    return row.class_iris.filter((iri) => typeof iri === "string" && iri);
  }
  return typeof row.class_iri === "string" && row.class_iri ? [row.class_iri] : [];
}

type EntityListEnvelope = {
  graph_set_id: string;
  warnings?: Array<{ code: string; message?: string }>;
  items: EntityListRow[];
};

type EntityRelationRow = {
  iri: string;
  label: string | null;
  source_graph_iri: string;
  assertion_kind: string;
  stale?: boolean;
  /** Source/target/relation IRIs come from the read-model envelope. They
   * are projected onto the same shape as entity-list items for symmetry. */
  source?: string;
  target?: string;
  relation?: string;
};

type EntityRelationsEnvelope = {
  graph_set_id: string;
  warnings?: Array<{ code: string; message?: string }>;
  items: EntityRelationRow[];
};

type EntityGraphRelationPayload = EntityRelationRow & { id: string };

type EntityLiteralFactRow = {
  id: string;
  subject_iri: string;
  predicate_iri: string;
  predicate_label: string | null;
  object_value: unknown;
  object_label?: string | null;
  assertion_kind: string;
  stale?: boolean;
};

type EntityLiteralFactsEnvelope = {
  graph_set_id: string;
  warnings?: Array<{ code: string; message?: string }>;
  items: EntityLiteralFactRow[];
};

type EntityGraphLayer = "facts" | "reasoning" | "full";
type EntityGraphFocus = "context" | "reasoning";
type SemanticReadModelInclude =
  | "asserted"
  | "asserted-plus-reasoning"
  | "full-working-view";

/** R3.0-009 §4.3: formal Class membership is the rdf:type relation, so the
 * member add/remove path is identical for the UI and for the agent. */
const RDF_TYPE_IRI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";

const GRAPH_LAYER_OPTIONS: Array<{
  value: EntityGraphLayer;
  label: string;
  include: SemanticReadModelInclude;
  description: string;
}> = [
  {
    value: "facts",
    label: "Fact graph",
    include: "asserted",
    description: "Only manually asserted entities and relations.",
  },
  {
    value: "reasoning",
    label: "Reasoning graph",
    include: "asserted-plus-reasoning",
    description: "Facts plus currently available reasoning results.",
  },
  {
    value: "full",
    label: "Complete view",
    include: "full-working-view",
    description: "Facts and reasoning results together.",
  },
];

const GRAPH_FOCUS_OPTIONS: Array<{
  value: EntityGraphFocus;
  label: string;
  description: string;
}> = [
  {
    value: "context",
    label: "Context",
    description: "Show all edge kinds with their normal styling.",
  },
  {
    value: "reasoning",
    label: "Reasoning",
    description: "Highlight reasoning edges and fade the surrounding context.",
  },
];

type EntitiesPageProps = {
  graphSetId: string;
  ontologyId: string;
  readOnly: boolean;
  request: WorkbenchRequest;
  /** App-level tab navigation; enables the R3.0-009 §7.1 cross-page links. */
  navigateWorkspace?: (tab: string, params?: Record<string, string>) => void;
  /** Entity IRI carried in the URL (`category`) when another page links here. */
  focusIri?: string | null;
};

export function EntitiesPage({
  graphSetId,
  ontologyId,
  readOnly,
  request,
  navigateWorkspace,
  focusIri,
}: EntitiesPageProps) {
  const t = useT();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [entities, setEntities] = useState<EntityListEnvelope | null>(null);
  const [relations, setRelations] = useState<EntityRelationsEnvelope | null>(null);
  const [selectedLayer, setSelectedLayer] = useState<EntityGraphLayer>("facts");
  const [selectedFocus, setSelectedFocus] = useState<EntityGraphFocus>("context");
  const [literalFacts, setLiteralFacts] = useState<EntityLiteralFactRow[]>([]);
  const [literalFactsLoading, setLiteralFactsLoading] = useState(false);
  const [literalFactsError, setLiteralFactsError] = useState("");
  const [selectedIri, setSelectedIri] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [detailLabel, setDetailLabel] = useState("");
  const [relationSourceIri, setRelationSourceIri] = useState("");
  const [relationTypeIri, setRelationTypeIri] = useState("");
  const [relationTargetIri, setRelationTargetIri] = useState("");
  // R3.0-009 §7.1: Class is optional and multi-valued in the create form.
  const [newClassIris, setNewClassIris] = useState<string[]>([]);
  const [newClassDraft, setNewClassDraft] = useState("");
  const [newLabel, setNewLabel] = useState("");
  // R3.0-009 §4.3/D12: the edited formal Class set of the selected entity.
  // Saving diffs it against the entity's current set and issues
  // create_relation / delete_relation commands with the rdf:type predicate.
  const [editClassIris, setEditClassIris] = useState<string[]>([]);
  const [editClassDraft, setEditClassDraft] = useState("");

  const selectedLayerConfig = useMemo(
    () => GRAPH_LAYER_OPTIONS.find((option) => option.value === selectedLayer) ?? GRAPH_LAYER_OPTIONS[0],
    [selectedLayer],
  );
  const selectedFocusConfig = useMemo(
    () => GRAPH_FOCUS_OPTIONS.find((option) => option.value === selectedFocus) ?? GRAPH_FOCUS_OPTIONS[0],
    [selectedFocus],
  );
  const derivedFocus = useMemo(() => {
    if (selectedLayer === "reasoning") return "reasoning";
    if (selectedLayer === "full" && selectedFocus !== "context") return selectedFocus;
    return null;
  }, [selectedFocus, selectedLayer]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [entityList, relationList] = await Promise.all([
        readModel<EntityListEnvelope>(request, graphSetId, "entity-list", {
          include: selectedLayerConfig.include,
        }),
        readModel<EntityRelationsEnvelope>(request, graphSetId, "entity-relations", {
          include: selectedLayerConfig.include,
        }),
      ]);
      setEntities(entityList);
      setRelations(relationList);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [graphSetId, request, selectedLayerConfig.include]);

  useEffect(() => {
    void load();
  }, [load]);

  const entityLabelByIri = useMemo(() => {
    const labels = new Map<string, string>();
    for (const row of entities?.items ?? []) {
      labels.set(row.iri, row.label ?? row.iri);
    }
    return labels;
  }, [entities]);

  const { graphNodes, graphEdges, classLabels, entityByIri, relationByEdgeId } = useMemo(() => {
    const entityMap = new Map<string, EntityListRow>();
    const nodes: ForceGraphNode[] = (entities?.items ?? []).map((row) => {
      const classIris = entityClassIris(row);
      return {
        id: row.iri,
        label: row.label ?? compactIri(row.iri),
        group: row.class_label ?? (classIris[0] ? compactIri(classIris[0]) : t("Unclassified")),
        kind: normalizeAssertionKind(row.assertion_kind),
      };
    });
    for (const row of entities?.items ?? []) entityMap.set(row.iri, row);
    const nodeIds = new Set(nodes.map((node) => node.id));
    const relationMap = new Map<string, EntityGraphRelationPayload>();
    const edges: ForceGraphEdge[] = (relations?.items ?? [])
      .filter((row) => row.source && row.target)
      .map((row, index) => ({
        id: `entity-relation:${row.iri}:${row.source}:${row.target}:${index}`,
        source: row.source ?? "",
        target: row.target ?? "",
        label: row.label ?? (row.relation ? compactIri(row.relation) : t("relationship")),
        kind: normalizeAssertionKind(row.assertion_kind),
        stale: Boolean(row.stale),
      }))
      .filter((edge) => {
        const visible = nodeIds.has(edge.source) && nodeIds.has(edge.target);
        if (!visible) return false;
        const row = (relations?.items ?? []).find((item, index) => (
          edge.id === `entity-relation:${item.iri}:${item.source}:${item.target}:${index}`
        ));
        if (row) relationMap.set(edge.id, { ...row, id: edge.id });
        return true;
      });
    const groups = Array.from(new Set(nodes.map((node) => node.group || t("Unclassified")))).sort();
    return {
      graphNodes: nodes,
      graphEdges: edges,
      classLabels: groups,
      entityByIri: entityMap,
      relationByEdgeId: relationMap,
    };
  }, [entities, relations, t]);

  const selectedEntity = selectedIri ? entityByIri.get(selectedIri) ?? null : null;
  const selectedRelation = selectedEdgeId ? relationByEdgeId.get(selectedEdgeId) ?? null : null;
  const hasGraphSelection = Boolean(selectedEntity || selectedRelation);
  const visibleWarnings = useMemo(() => {
    const warnings = [...(entities?.warnings ?? []), ...(relations?.warnings ?? [])];
    const messages = new Map<string, string>();
    for (const warning of warnings) {
      const message = friendlyGraphLayerWarning(warning.code, t);
      if (message) messages.set(warning.code, message);
    }
    return Array.from(messages, ([code, message]) => ({ code, message }));
  }, [entities, relations, t]);

  useEffect(() => {
    setDetailLabel(selectedEntity?.label ?? "");
    setRelationSourceIri(selectedRelation?.source ?? "");
    setRelationTypeIri(selectedRelation?.relation ?? selectedRelation?.iri ?? "");
    setRelationTargetIri(selectedRelation?.target ?? "");
    setEditClassIris(selectedEntity ? entityClassIris(selectedEntity) : []);
    setEditClassDraft("");
    setEditing(false);
  }, [selectedEntity, selectedRelation]);

  // R3.0-009 §7.2: a Class page can link straight to one of its members.
  useEffect(() => {
    if (!focusIri) return;
    if (entityByIri.has(focusIri)) setSelectedIri(focusIri);
  }, [focusIri, entityByIri]);

  useEffect(() => {
    if (!selectedEntity) {
      setLiteralFacts([]);
      setLiteralFactsError("");
      setLiteralFactsLoading(false);
      return;
    }

    let cancelled = false;
    setLiteralFactsLoading(true);
    setLiteralFactsError("");
    void readModel<EntityLiteralFactsEnvelope>(request, graphSetId, "entity-literal-facts", {
      include: selectedLayerConfig.include,
      entity: selectedEntity.iri,
      limit: 50,
    })
      .then((envelope) => {
        if (!cancelled) setLiteralFacts(envelope.items ?? []);
      })
      .catch((cause) => {
        if (!cancelled) {
          setLiteralFacts([]);
          setLiteralFactsError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!cancelled) setLiteralFactsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [graphSetId, request, selectedEntity, selectedLayerConfig.include]);

  async function submitNewEntity() {
    if (!newLabel.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const classIris = Array.from(
        new Set(newClassIris.map((iri) => iri.trim()).filter(Boolean)),
      );
      await compileAndApplyProductCommand(request, {
        command_kind: "create_entity",
        payload: {
          ontology_id: ontologyId,
          // R3.0-009 §4.1/§6.2: zero or more explicit formal Classes; the
          // legacy scalar rides along only for the single-Class case so the
          // old single-input submission stays compatible.
          ...(classIris.length === 1 ? { class_iri_or_legacy_id: classIris[0] } : {}),
          class_iris: classIris,
          label: newLabel.trim(),
          aliases: [],
          properties: {},
        },
        graph_set_id: graphSetId,
        actor: "user:stage2-entities-page",
        reason: "create via Stage 2 EntitiesPage MVP",
      });
      setNewLabel("");
      setNewClassIris([]);
      setNewClassDraft("");
      setCreating(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  function addNewClass() {
    const value = newClassDraft.trim();
    if (!value) return;
    setNewClassIris((current) => (current.includes(value) ? current : [...current, value]));
    setNewClassDraft("");
  }

  function removeNewClass(value: string) {
    setNewClassIris((current) => current.filter((iri) => iri !== value));
  }

  function addEditClass() {
    const value = editClassDraft.trim();
    if (!value) return;
    setEditClassIris((current) => (current.includes(value) ? current : [...current, value]));
    setEditClassDraft("");
  }

  function removeEditClass(value: string) {
    setEditClassIris((current) => current.filter((iri) => iri !== value));
  }

  async function applyDetailUpdate() {
    if (!selectedEntity && !selectedRelation) return;
    setSubmitting(true);
    setError("");
    try {
      if (selectedEntity) {
        // R3.0-009 §4.3/D12: formal Class membership of an existing entity is
        // written back as relation commands with the rdf:type predicate, so
        // the read model, the digest, and the agent path stay identical.
        const currentClasses = entityClassIris(selectedEntity);
        const targetClasses = Array.from(
          new Set(editClassIris.map((iri) => iri.trim()).filter(Boolean)),
        );
        for (const classIri of currentClasses) {
          if (!targetClasses.includes(classIri)) {
            await compileAndApplyProductCommand(request, {
              command_kind: "delete_relation",
              payload: {
                ontology_id: ontologyId,
                source_entity_iri: selectedEntity.iri,
                relation_type_iri: RDF_TYPE_IRI,
                target_entity_iri: classIri,
              },
              graph_set_id: graphSetId,
              actor: "user:stage2-entities-page",
              reason: "remove formal class membership from graph detail panel",
            });
          }
        }
        for (const classIri of targetClasses) {
          if (!currentClasses.includes(classIri)) {
            await compileAndApplyProductCommand(request, {
              command_kind: "create_relation",
              payload: {
                ontology_id: ontologyId,
                source_entity_iri: selectedEntity.iri,
                relation_type_iri: RDF_TYPE_IRI,
                target_entity_iri: classIri,
              },
              graph_set_id: graphSetId,
              actor: "user:stage2-entities-page",
              reason: "add formal class membership from graph detail panel",
            });
          }
        }
        await compileAndApplyProductCommand(request, {
          command_kind: "update_entity",
          payload: {
            ontology_id: ontologyId,
            entity_iri: selectedEntity.iri,
            label: detailLabel.trim() || selectedEntity.label || compactIri(selectedEntity.iri),
          },
          graph_set_id: graphSetId,
          actor: "user:stage2-entities-page",
          reason: "update entity from graph detail panel",
        });
      } else if (selectedRelation?.source && selectedRelation.target) {
        await compileAndApplyProductCommand(request, {
          command_kind: "delete_relation",
          payload: {
            ontology_id: ontologyId,
            source_entity_iri: selectedRelation.source,
            relation_type_iri: selectedRelation.relation ?? selectedRelation.iri,
            target_entity_iri: selectedRelation.target,
          },
          graph_set_id: graphSetId,
          actor: "user:stage2-entities-page",
          reason: "replace relation from graph detail panel",
        });
        await compileAndApplyProductCommand(request, {
          command_kind: "create_relation",
          payload: {
            ontology_id: ontologyId,
            source_entity_iri: relationSourceIri.trim(),
            relation_type_iri: relationTypeIri.trim(),
            target_entity_iri: relationTargetIri.trim(),
          },
          graph_set_id: graphSetId,
          actor: "user:stage2-entities-page",
          reason: "replace relation from graph detail panel",
        });
      }
      setEditing(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteSelectedDetail() {
    if (!selectedEntity && !selectedRelation) return;
    setSubmitting(true);
    setError("");
    try {
      if (selectedEntity) {
        await compileAndApplyProductCommand(request, {
          command_kind: "delete_entity",
          payload: { ontology_id: ontologyId, entity_iri: selectedEntity.iri },
          graph_set_id: graphSetId,
          actor: "user:stage2-entities-page",
          reason: "delete entity from graph detail panel",
        });
        setSelectedIri(null);
      } else if (selectedRelation?.source && selectedRelation.target) {
        await compileAndApplyProductCommand(request, {
          command_kind: "delete_relation",
          payload: {
            ontology_id: ontologyId,
            source_entity_iri: selectedRelation.source,
            relation_type_iri: selectedRelation.relation ?? selectedRelation.iri,
            target_entity_iri: selectedRelation.target,
          },
          graph_set_id: graphSetId,
          actor: "user:stage2-entities-page",
          reason: "delete relation from graph detail panel",
        });
        setSelectedEdgeId(null);
      }
      setEditing(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  function clearSelection() {
    setSelectedIri(null);
    setSelectedEdgeId(null);
    setEditing(false);
  }

  function changeLayer(value: EntityGraphLayer) {
    setSelectedLayer(value);
    if (value !== "full") setSelectedFocus("context");
    clearSelection();
  }

  return (
    <section className="entitiesPage stage2">
      <header className="topBar">
        <div>
          <span className="eyebrow">{t("Business modeling")}</span>
          <h1>{t("Entities")}</h1>
          <div className="crumbTrail">
            <span>{t("Entity diagram")}</span>
          </div>
        </div>
        <div className="topActions">
          <Button icon={<RefreshCw size={15} />} onClick={() => void load()} disabled={loading}>
            {t("Refresh")}
          </Button>
          <Button
            type="primary"
            icon={<Plus size={15} />}
            disabled={readOnly || creating}
            title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : undefined}
            onClick={() => setCreating(true)}
          >
            {t("New entity")}
          </Button>
          <Button
            icon={<Link2 size={15} />}
            disabled
            title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Relationship creation is not available from the current API yet.")}
          >
            {t("New relationship")}
          </Button>
        </div>
      </header>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}
      {readOnly && (
        <Alert
          type="info"
          showIcon
          message={t("Workspace is locked. Unlock in Settings to edit modeling data.")}
        />
      )}
      {visibleWarnings.map((warning) => (
        <Alert
          key={warning.code}
          type="warning"
          showIcon
          message={warning.message}
        />
      ))}

      <Card
        title={t("Entity force graph · {nodes} nodes · {edges} edges", {
          nodes: graphNodes.length,
          edges: graphEdges.length,
        })}
        size="small"
      >
        <div className="semanticGraphToolbar">
          <Input
            prefix={<Search size={14} />}
            placeholder={t("Search entities by name or class")}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            allowClear
          />
          <div className="semanticGraphLayerControl" aria-label={t("Graph layer")}>
            <span>{t("Graph layer")}</span>
            <Segmented
              value={selectedLayer}
              onChange={(value) => changeLayer(value as EntityGraphLayer)}
              options={GRAPH_LAYER_OPTIONS.map((option) => ({
                label: t(option.label),
                value: option.value,
              }))}
            />
            <small>{t(selectedLayerConfig.description)}</small>
          </div>
          {selectedLayer === "full" && (
            <div className="semanticGraphLayerControl" aria-label={t("Graph focus")}>
              <span>{t("Focus")}</span>
              <Segmented
                value={selectedFocus}
                onChange={(value) => {
                  setSelectedFocus(value as EntityGraphFocus);
                  clearSelection();
                }}
                options={GRAPH_FOCUS_OPTIONS.map((option) => ({
                  label: t(option.label),
                  value: option.value,
                }))}
              />
              <small>{t(selectedFocusConfig.description)}</small>
            </div>
          )}
          {selectedIri && (
            <Tag closable onClose={() => setSelectedIri(null)}>
              {entityLabelByIri.get(selectedIri) ?? compactIri(selectedIri)}
            </Tag>
          )}
          {selectedRelation && (
            <Tag closable onClose={() => setSelectedEdgeId(null)}>
              {selectedRelation.label ?? compactIri(selectedRelation.relation ?? selectedRelation.iri)}
            </Tag>
          )}
        </div>
        <div className={`semanticGraphLayout${hasGraphSelection ? " hasDetails" : ""}`}>
          <div className="semanticGraphSurface">
            {loading ? (
              <Skeleton active paragraph={{ rows: 7 }} />
            ) : (
              <ForceGraphCanvas
                nodes={graphNodes}
                edges={graphEdges}
                cacheKey={`${graphSetId}:${selectedLayer}`}
                derivedFocus={derivedFocus}
                selectedNodeId={selectedIri}
                selectedEdgeId={selectedEdgeId}
                onSelectNode={(id) => {
                  setSelectedIri(id);
                  if (id) setSelectedEdgeId(null);
                }}
                onSelectEdge={(id) => {
                  setSelectedEdgeId(id);
                  if (id) setSelectedIri(null);
                }}
                searchQuery={searchQuery}
                groupLabels={classLabels}
                emptyTitle={t("No entities in this workspace yet.")}
                emptyHint={t("Create an entity to populate the force graph.")}
              />
            )}
          </div>
          <EntityGraphDetailPanel
            selectedEntity={selectedEntity}
            selectedRelation={selectedRelation}
            entityLabelByIri={entityLabelByIri}
            readOnly={readOnly}
            busy={submitting}
            editing={editing}
            literalFacts={literalFacts}
            literalFactsLoading={literalFactsLoading}
            literalFactsError={literalFactsError}
            detailLabel={detailLabel}
            relationSourceIri={relationSourceIri}
            relationTypeIri={relationTypeIri}
            relationTargetIri={relationTargetIri}
            editClassIris={editClassIris}
            editClassDraft={editClassDraft}
            onChangeEditClassDraft={setEditClassDraft}
            onAddEditClass={addEditClass}
            onRemoveEditClass={removeEditClass}
            onChangeLabel={setDetailLabel}
            onChangeRelationSource={setRelationSourceIri}
            onChangeRelationType={setRelationTypeIri}
            onChangeRelationTarget={setRelationTargetIri}
            onNavigateToClass={(classIri) =>
              navigateWorkspace?.("classes", { category: classIri })
            }
            onSelectEntityIri={(entityIri) => {
              setSelectedEdgeId(null);
              setSelectedIri(entityIri);
            }}
            onEdit={() => setEditing(true)}
            onCancelEdit={() => setEditing(false)}
            onSave={() => void applyDetailUpdate()}
            onDelete={() => void deleteSelectedDetail()}
            onClose={clearSelection}
          />
        </div>
      </Card>

      <Modal
        title={t("Create entity")}
        open={creating}
        onCancel={() => {
          setCreating(false);
          setNewClassIris([]);
          setNewClassDraft("");
          setNewLabel("");
        }}
        onOk={() => void submitNewEntity()}
        confirmLoading={submitting}
        okText={t("Create entity")}
        okButtonProps={{ disabled: !newLabel.trim() }}
      >
        <Input
          placeholder={t("Entity label")}
          value={newLabel}
          onChange={(event) => setNewLabel(event.target.value)}
          autoFocus
        />
        <div className="entityClassInput">
          <span className="entityClassInputHint">
            {t("Formal classes (optional, one or more)")}
          </span>
          <div className="entityClassInputRow">
            <Input
              placeholder={t("Class identifier from class diagram")}
              value={newClassDraft}
              onChange={(event) => setNewClassDraft(event.target.value)}
              onPressEnter={addNewClass}
            />
            <Button onClick={addNewClass} disabled={!newClassDraft.trim()}>
              {t("Add class")}
            </Button>
          </div>
          {newClassIris.length === 0 ? (
            <p className="entityClassInputEmpty">
              {t("No formal class selected; the entity stays unclassified.")}
            </p>
          ) : (
            <div className="entityClassTags">
              {newClassIris.map((iri) => (
                <Tag key={iri} closable onClose={() => removeNewClass(iri)}>
                  {compactIri(iri)}
                </Tag>
              ))}
            </div>
          )}
        </div>
      </Modal>
    </section>
  );
}

export type { EntitiesPageProps };

type EntityGraphDetailPanelProps = {
  selectedEntity: EntityListRow | null;
  selectedRelation: EntityGraphRelationPayload | null;
  entityLabelByIri: Map<string, string>;
  readOnly: boolean;
  busy: boolean;
  editing: boolean;
  literalFacts: EntityLiteralFactRow[];
  literalFactsLoading: boolean;
  literalFactsError: string;
  detailLabel: string;
  relationSourceIri: string;
  relationTypeIri: string;
  relationTargetIri: string;
  /** R3.0-009 §4.3/D12: editable formal Class set of the selected entity. */
  editClassIris: string[];
  editClassDraft: string;
  onChangeEditClassDraft: (value: string) => void;
  onAddEditClass: () => void;
  onRemoveEditClass: (classIri: string) => void;
  onChangeLabel: (value: string) => void;
  onChangeRelationSource: (value: string) => void;
  onChangeRelationType: (value: string) => void;
  onChangeRelationTarget: (value: string) => void;
  /** R3.0-009 §7.1: navigate from an entity to one of its formal Classes. */
  onNavigateToClass: (classIri: string) => void;
  /** R3.0-009 §7.1: follow a relation endpoint to the related node. */
  onSelectEntityIri: (entityIri: string) => void;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  onDelete: () => void;
  onClose: () => void;
};

function EntityGraphDetailPanel({
  selectedEntity,
  selectedRelation,
  entityLabelByIri,
  readOnly,
  busy,
  editing,
  literalFacts,
  literalFactsLoading,
  literalFactsError,
  detailLabel,
  relationSourceIri,
  relationTypeIri,
  relationTargetIri,
  editClassIris,
  editClassDraft,
  onChangeEditClassDraft,
  onAddEditClass,
  onRemoveEditClass,
  onChangeLabel,
  onChangeRelationSource,
  onChangeRelationType,
  onChangeRelationTarget,
  onNavigateToClass,
  onSelectEntityIri,
  onEdit,
  onCancelEdit,
  onSave,
  onDelete,
  onClose,
}: EntityGraphDetailPanelProps) {
  const t = useT();
  const selected = selectedEntity || selectedRelation;
  const title = selectedEntity
    ? selectedEntity.label ?? compactIri(selectedEntity.iri)
    : selectedRelation
      ? selectedRelation.label ?? compactIri(selectedRelation.relation ?? selectedRelation.iri)
      : t("Select an item");
  const relationComplete = Boolean(
    relationSourceIri.trim() && relationTypeIri.trim() && relationTargetIri.trim(),
  );

  if (!selected) return null;

  return (
    <aside className="semanticGraphDetail" aria-label={t("Graph item details")}>
      <header className="semanticGraphDetailHeader">
        <div>
          <Tag>{selectedEntity ? t("Entity") : t("Relation")}</Tag>
          <h2>{title}</h2>
        </div>
        <Button size="small" icon={<X size={14} />} onClick={onClose} aria-label={t("Close details")} />
      </header>

      {editing ? (
        <div className="semanticGraphDetailForm">
          {selectedEntity ? (
            <>
              <label>
                <span>{t("Label")}</span>
                <Input value={detailLabel} onChange={(event) => onChangeLabel(event.target.value)} />
              </label>
              <div className="entityClassInput">
                <span className="entityClassInputHint">
                  {t("Formal classes (optional, one or more)")}
                </span>
                <div className="entityClassInputRow">
                  <Input
                    placeholder={t("Class identifier from class diagram")}
                    value={editClassDraft}
                    onChange={(event) => onChangeEditClassDraft(event.target.value)}
                    onPressEnter={onAddEditClass}
                  />
                  <Button onClick={onAddEditClass} disabled={!editClassDraft.trim()}>
                    {t("Add class")}
                  </Button>
                </div>
                {editClassIris.length === 0 ? (
                  <p className="entityClassInputEmpty">
                    {t("No formal class selected; the entity stays unclassified.")}
                  </p>
                ) : (
                  <div className="entityClassTags">
                    {editClassIris.map((classIri) => (
                      <Tag key={classIri} closable onClose={() => onRemoveEditClass(classIri)}>
                        {compactIri(classIri)}
                      </Tag>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <label>
                <span>{t("Source entity IRI")}</span>
                <Input value={relationSourceIri} onChange={(event) => onChangeRelationSource(event.target.value)} />
              </label>
              <label>
                <span>{t("Relation type IRI")}</span>
                <Input value={relationTypeIri} onChange={(event) => onChangeRelationType(event.target.value)} />
              </label>
              <label>
                <span>{t("Target entity IRI")}</span>
                <Input value={relationTargetIri} onChange={(event) => onChangeRelationTarget(event.target.value)} />
              </label>
            </>
          )}
          <div className="semanticGraphDetailActions">
            <Button onClick={onCancelEdit} disabled={busy}>{t("Cancel")}</Button>
            <Button
              type="primary"
              icon={<Save size={14} />}
              onClick={onSave}
              loading={busy}
              disabled={!selectedEntity && !relationComplete}
            >
              {t("Save")}
            </Button>
          </div>
        </div>
      ) : (
        <>
          <dl className="semanticGraphDetailList">
            {selectedEntity && (
              <>
                <div><dt>{t("IRI")}</dt><dd><code>{selectedEntity.iri}</code></dd></div>
                <div>
                  <dt>{t("Classes")}</dt>
                  <dd>
                    {entityClassIris(selectedEntity).length === 0 ? (
                      <span className="entityClassEmpty">
                        {t("Unclassified · no formal class")}
                      </span>
                    ) : (
                      <span className="entityClassLinks">
                        {entityClassIris(selectedEntity).map((classIri, index) => (
                          <button
                            key={classIri}
                            type="button"
                            className="entityClassLink"
                            title={classIri}
                            onClick={() => onNavigateToClass(classIri)}
                          >
                            {index === 0 && selectedEntity.class_label
                              ? selectedEntity.class_label
                              : compactIri(classIri)}
                          </button>
                        ))}
                      </span>
                    )}
                  </dd>
                </div>
                {(selectedEntity.incomplete_class_identity_iris?.length ?? 0) > 0 && (
                  <div>
                    <dt>{t("Incomplete class identity")}</dt>
                    <dd>
                      <span className="entityClassIncomplete">
                        {selectedEntity.incomplete_class_identity_iris
                          ?.map((iri) => compactIri(iri))
                          .join(", ")}
                      </span>
                    </dd>
                  </div>
                )}
                <div><dt>{t("Assertion")}</dt><dd>{assertionKindLabel(selectedEntity.assertion_kind, t)}</dd></div>
              </>
            )}
            {selectedRelation && (
              <>
                <div>
                  <dt>{t("Source")}</dt>
                  <dd>
                    <button
                      type="button"
                      className="entityClassLink"
                      onClick={() => onSelectEntityIri(selectedRelation.source ?? "")}
                    >
                      {entityLabelByIri.get(selectedRelation.source ?? "") ?? compactIri(selectedRelation.source ?? "")}
                    </button>
                  </dd>
                </div>
                <div><dt>{t("Relation type")}</dt><dd><code>{selectedRelation.relation ?? selectedRelation.iri}</code></dd></div>
                <div>
                  <dt>{t("Target")}</dt>
                  <dd>
                    <button
                      type="button"
                      className="entityClassLink"
                      onClick={() => onSelectEntityIri(selectedRelation.target ?? "")}
                    >
                      {entityLabelByIri.get(selectedRelation.target ?? "") ?? compactIri(selectedRelation.target ?? "")}
                    </button>
                  </dd>
                </div>
                <div><dt>{t("Assertion")}</dt><dd>{assertionKindLabel(selectedRelation.assertion_kind, t)}</dd></div>
              </>
            )}
          </dl>
          {selectedEntity && (
            <section className="entityLiteralFacts" aria-label={t("Literal facts")}>
              <header>
                <strong>{t("Literal facts")}</strong>
              </header>
              {literalFactsLoading ? (
                <Skeleton active paragraph={{ rows: 3 }} title={false} />
              ) : literalFactsError ? (
                <Alert type="warning" showIcon message={literalFactsError} />
              ) : literalFacts.length === 0 ? (
                <p className="entityLiteralFactsEmpty">{t("No literal facts for this entity in the current layer.")}</p>
              ) : (
                <div className="entityLiteralFactList">
                  {literalFacts.map((fact) => (
                    <article key={fact.id} className="entityLiteralFact">
                      <div>
                        <span>{fact.predicate_label ?? compactIri(fact.predicate_iri)}</span>
                        <Tag>{assertionKindLabel(fact.assertion_kind, t)}{fact.stale ? ` · ${t("Stale")}` : ""}</Tag>
                      </div>
                      <p>{literalFactValue(fact)}</p>
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
          <div className="semanticGraphDetailActions">
            <Button icon={<Edit3 size={14} />} onClick={onEdit} disabled={readOnly || busy}>
              {t("Edit")}
            </Button>
            <Button danger icon={<Trash2 size={14} />} onClick={onDelete} disabled={readOnly || busy} loading={busy}>
              {t("Delete")}
            </Button>
          </div>
        </>
      )}
    </aside>
  );
}

function compactIri(value: string) {
  const hash = value.lastIndexOf("#");
  const slash = value.lastIndexOf("/");
  const idx = Math.max(hash, slash);
  return idx >= 0 ? value.slice(idx + 1) : value;
}

function assertionKindLabel(kind: string, t: ReturnType<typeof useT>) {
  const normalized = normalizeAssertionKind(kind);
  if (normalized === "asserted") return t("Fact");
  if (normalized === "owl_inferred" || normalized === "inferred") return t("Reasoning");
  return t("Fact");
}

function normalizeAssertionKind(kind: string | null | undefined) {
  return (kind || "asserted").toLowerCase().replace(/[-\s]/g, "_");
}

function friendlyGraphLayerWarning(code: string, t: ReturnType<typeof useT>) {
  switch (code) {
    case "missing_reasoning_result":
      return t("No reasoning result is available yet.");
    case "stale_reasoning_result":
      return t("Reasoning results may be out of date.");
    default:
      return "";
  }
}

function literalFactValue(fact: EntityLiteralFactRow) {
  if (fact.object_label != null && fact.object_label !== "") return String(fact.object_label);
  if (fact.object_value == null) return "";
  if (typeof fact.object_value === "string") return fact.object_value;
  return JSON.stringify(fact.object_value);
}
