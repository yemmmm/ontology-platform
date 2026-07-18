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
  evidence_status?: string;
  /** Optional class IRI / label that the read-model service decorates onto
   * each row. May be absent for entities whose class lives outside the
   * current graph set. */
  class_iri?: string;
  class_label?: string;
};

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

type EntityGraphLayer = "facts" | "reasoning" | "rules" | "full";
type EntityGraphFocus = "context" | "reasoning" | "rules";
type SemanticReadModelInclude =
  | "asserted"
  | "asserted-plus-reasoning"
  | "asserted-plus-rules"
  | "full-working-view";

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
    value: "rules",
    label: "Rule graph",
    include: "asserted-plus-rules",
    description: "Facts plus currently available rule results.",
  },
  {
    value: "full",
    label: "Complete view",
    include: "full-working-view",
    description: "Facts, reasoning results, and rule results together.",
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
  {
    value: "rules",
    label: "Rules",
    description: "Highlight rule-derived edges and fade the surrounding context.",
  },
];

type EntitiesPageProps = {
  graphSetId: string;
  ontologyId: string;
  readOnly: boolean;
  request: WorkbenchRequest;
};

export function EntitiesPage({ graphSetId, ontologyId, readOnly, request }: EntitiesPageProps) {
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
  const [newClassIri, setNewClassIri] = useState("");
  const [newLabel, setNewLabel] = useState("");

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
    if (selectedLayer === "rules") return "rules";
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
    const nodes: ForceGraphNode[] = (entities?.items ?? []).map((row) => ({
      id: row.iri,
      label: row.label ?? compactIri(row.iri),
      group: row.class_label ?? (row.class_iri ? compactIri(row.class_iri) : t("Unclassified")),
      kind: normalizeAssertionKind(row.assertion_kind),
    }));
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
    setEditing(false);
  }, [selectedEntity, selectedRelation]);

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
    if (!newLabel.trim() || !newClassIri.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await compileAndApplyProductCommand(request, {
        command_kind: "create_entity",
        payload: {
          ontology_id: ontologyId,
          class_iri_or_legacy_id: newClassIri.trim(),
          label: newLabel.trim(),
          aliases: [],
          properties: {},
        },
        graph_set_id: graphSetId,
        actor: "user:stage2-entities-page",
        reason: "create via Stage 2 EntitiesPage MVP",
      });
      setNewLabel("");
      setNewClassIri("");
      setCreating(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  async function applyDetailUpdate() {
    if (!selectedEntity && !selectedRelation) return;
    setSubmitting(true);
    setError("");
    try {
      if (selectedEntity) {
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
            onChangeLabel={setDetailLabel}
            onChangeRelationSource={setRelationSourceIri}
            onChangeRelationType={setRelationTypeIri}
            onChangeRelationTarget={setRelationTargetIri}
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
          setNewClassIri("");
          setNewLabel("");
        }}
        onOk={() => void submitNewEntity()}
        confirmLoading={submitting}
        okText={t("Create entity")}
        okButtonProps={{ disabled: !newLabel.trim() || !newClassIri.trim() }}
      >
        <Input
          placeholder={t("Class identifier from class diagram")}
          value={newClassIri}
          onChange={(event) => setNewClassIri(event.target.value)}
          autoFocus
        />
        <Input
          placeholder={t("Entity label")}
          value={newLabel}
          onChange={(event) => setNewLabel(event.target.value)}
          style={{ marginTop: 12 }}
        />
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
  onChangeLabel: (value: string) => void;
  onChangeRelationSource: (value: string) => void;
  onChangeRelationType: (value: string) => void;
  onChangeRelationTarget: (value: string) => void;
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
  onChangeLabel,
  onChangeRelationSource,
  onChangeRelationType,
  onChangeRelationTarget,
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
            <label>
              <span>{t("Label")}</span>
              <Input value={detailLabel} onChange={(event) => onChangeLabel(event.target.value)} />
            </label>
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
                <div><dt>{t("Class")}</dt><dd>{selectedEntity.class_label ?? compactIri(selectedEntity.class_iri ?? "")}</dd></div>
                <div><dt>{t("Assertion")}</dt><dd>{assertionKindLabel(selectedEntity.assertion_kind, t)}</dd></div>
                <div><dt>{t("Evidence")}</dt><dd>{selectedEntity.evidence_status ?? t("Not available")}</dd></div>
              </>
            )}
            {selectedRelation && (
              <>
                <div><dt>{t("Source")}</dt><dd>{entityLabelByIri.get(selectedRelation.source ?? "") ?? compactIri(selectedRelation.source ?? "")}</dd></div>
                <div><dt>{t("Relation type")}</dt><dd><code>{selectedRelation.relation ?? selectedRelation.iri}</code></dd></div>
                <div><dt>{t("Target")}</dt><dd>{entityLabelByIri.get(selectedRelation.target ?? "") ?? compactIri(selectedRelation.target ?? "")}</dd></div>
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
  if (normalized === "rule_derived") return t("Rule");
  return t("Fact");
}

function normalizeAssertionKind(kind: string | null | undefined) {
  return (kind || "asserted").toLowerCase().replace(/[-\s]/g, "_");
}

function friendlyGraphLayerWarning(code: string, t: ReturnType<typeof useT>) {
  switch (code) {
    case "missing_reasoning_result":
      return t("No reasoning result is available yet.");
    case "missing_rule_result":
      return t("No rule result is available yet.");
    case "stale_reasoning_result":
      return t("Reasoning results may be out of date.");
    case "stale_rule_result":
      return t("Rule results may be out of date.");
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
