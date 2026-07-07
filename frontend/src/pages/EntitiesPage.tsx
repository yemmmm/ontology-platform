/**
 * Stage 2 §5 — graph-derived EntitiesPage.
 *
 * MVP slice: lists entities from the entity-list read model and the edges
 * from entity-relations. Exposes a "New entity" button that creates an
 * entity via canonical-write (create_entity). Clicking an entity expands
 * the class-shape guidance from the entity-shape composer (read-only
 * display; inline editing lands in a later iteration).
 *
 * React Flow topology canvas (spec §5.2 mode=topology) is deferred per
 * task brief; the data layer is fully wired so the canvas is a pure
 * rendering concern when it lands.
 *
 * The legacy inline EntitiesPage remains in App.tsx as the fallback when
 * no ?graphSet= URL parameter is set.
 */

import { Alert, Button, Card, Input, Modal, Skeleton, Tag } from "antd";
import {
  ChevronRight,
  Database,
  Edit3,
  Link2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  ForceGraphCanvas,
  type ForceGraphEdge,
  type ForceGraphNode,
} from "../components/ForceGraphCanvas";
import { useT } from "../i18n";
import {
  compileAndApplyProductCommand,
  getClassShapeGuidance,
  readModel,
  type SemanticShaclFormGuidance,
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
  items: EntityListRow[];
};

type EntityRelationRow = {
  iri: string;
  label: string | null;
  source_graph_iri: string;
  assertion_kind: string;
  /** Source/target/relation IRIs come from the read-model envelope. They
   * are projected onto the same shape as entity-list items for symmetry. */
  source?: string;
  target?: string;
  relation?: string;
};

type EntityRelationsEnvelope = {
  graph_set_id: string;
  items: EntityRelationRow[];
};

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
  const [selectedIri, setSelectedIri] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [newClassIri, setNewClassIri] = useState("");
  const [newLabel, setNewLabel] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [entityList, relationList] = await Promise.all([
        readModel<EntityListEnvelope>(request, graphSetId, "entity-list"),
        readModel<EntityRelationsEnvelope>(request, graphSetId, "entity-relations"),
      ]);
      setEntities(entityList);
      setRelations(relationList);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [graphSetId, request]);

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

  const { graphNodes, graphEdges, classLabels } = useMemo(() => {
    const nodes: ForceGraphNode[] = (entities?.items ?? []).map((row) => ({
      id: row.iri,
      label: row.label ?? compactIri(row.iri),
      group: row.class_label ?? (row.class_iri ? compactIri(row.class_iri) : t("Unclassified")),
    }));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges: ForceGraphEdge[] = (relations?.items ?? [])
      .filter((row) => row.source && row.target)
      .map((row, index) => ({
        id: `entity-relation:${row.iri}:${row.source}:${row.target}:${index}`,
        source: row.source ?? "",
        target: row.target ?? "",
        label: row.label ?? (row.relation ? compactIri(row.relation) : t("relationship")),
      }))
      .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target));
    const groups = Array.from(new Set(nodes.map((node) => node.group || t("Unclassified")))).sort();
    return { graphNodes: nodes, graphEdges: edges, classLabels: groups };
  }, [entities, relations, t]);

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
          <div className="semanticGraphLegend">
            {classLabels.slice(0, 8).map((label) => (
              <Tag key={label}>{label}</Tag>
            ))}
          </div>
          {selectedIri && (
            <Tag closable onClose={() => setSelectedIri(null)}>
              {entityLabelByIri.get(selectedIri) ?? compactIri(selectedIri)}
            </Tag>
          )}
        </div>
        <div className="semanticGraphSurface">
          {loading ? (
            <Skeleton active paragraph={{ rows: 7 }} />
          ) : (
            <ForceGraphCanvas
              nodes={graphNodes}
              edges={graphEdges}
              selectedNodeId={selectedIri}
              onSelectNode={setSelectedIri}
              searchQuery={searchQuery}
              groupLabels={classLabels}
              emptyTitle={t("No entities in this workspace yet.")}
              emptyHint={t("Create an entity to populate the force graph.")}
            />
          )}
        </div>
      </Card>

      <Card
        title={t("Entities · {n}", { n: entities?.items.length ?? 0 })}
        size="small"
        style={{ marginTop: 12 }}
      >
        {loading ? (
          <Skeleton active />
        ) : entities && entities.items.length > 0 ? (
          <ul className="entityList">
            {entities.items.map((row) => (
              <EntityListEntry
                key={row.iri}
                row={row}
                selected={selectedIri === row.iri}
                onSelect={() => setSelectedIri(selectedIri === row.iri ? null : row.iri)}
                request={request}
                graphSetId={graphSetId}
                readOnly={readOnly}
              />
            ))}
          </ul>
        ) : (
          <div>{t("No entities in this workspace yet.")}</div>
        )}
      </Card>

      <Card
        title={t("Relations · {n}", { n: relations?.items.length ?? 0 })}
        size="small"
        style={{ marginTop: 12 }}
      >
        {loading ? (
          <Skeleton active />
        ) : relations && relations.items.length > 0 ? (
          <ul className="relationList">
            {relations.items.map((row, idx) => (
              <li key={`${row.source ?? row.iri}-${idx}`} className="relationListItem">
                <ChevronRight size={16} />
                <div>
                  <span>{entityLabelByIri.get(row.source ?? "") ?? t("Unknown source")}</span>
                  <span style={{ margin: "0 6px" }}>-{row.label ?? t("relationship")}-</span>
                  <span>{entityLabelByIri.get(row.target ?? "") ?? t("Unknown target")}</span>
                </div>
                <Tag>{t(row.assertion_kind)}</Tag>
                <div className="rowActions">
                  <Button
                    size="small"
                    icon={<Edit3 size={13} />}
                    disabled
                    title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Relationship editing is not available from the current API yet.")}
                  >
                    {t("Edit")}
                  </Button>
                  <Button
                    size="small"
                    danger
                    icon={<Trash2 size={13} />}
                    disabled
                    title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Relationship deletion is not available from the current API yet.")}
                  >
                    {t("Delete")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div>{t("No relationships in this workspace yet.")}</div>
        )}
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

type EntityListEntryProps = {
  row: EntityListRow;
  selected: boolean;
  onSelect: () => void;
  request: WorkbenchRequest;
  graphSetId: string;
  readOnly: boolean;
};

function EntityListEntry({ row, selected, onSelect, request, graphSetId, readOnly }: EntityListEntryProps) {
  const t = useT();
  const [guidance, setGuidance] = useState<SemanticShaclFormGuidance | null>(null);
  const [guidanceError, setGuidanceError] = useState("");
  const [loadingGuidance, setLoadingGuidance] = useState(false);

  // Lazily fetch shape guidance when the row is expanded. The composer
  // (entity-shape) delegates to the existing class-shape merge endpoint.
  useEffect(() => {
    if (!selected || guidance || loadingGuidance) return;
    const classIri = row.class_iri;
    if (!classIri) {
      setGuidanceError(t("Entity is missing its class IRI in the read model."));
      return;
    }
    setLoadingGuidance(true);
    getClassShapeGuidance(request, graphSetId, classIri)
      .then((data) => setGuidance(data))
      .catch((cause) => setGuidanceError(cause instanceof Error ? cause.message : String(cause)))
      .finally(() => setLoadingGuidance(false));
  }, [selected, guidance, loadingGuidance, row.class_iri, request, graphSetId, t]);

  return (
    <li className={`entityListItem${selected ? " selected" : ""}`}>
      <div className="entityListItemHeader" onClick={onSelect} role="button" tabIndex={0}>
        <Database size={16} />
        <div>
          <strong>{row.label ?? row.iri}</strong>
          {row.class_label && <Tag color="blue">{row.class_label}</Tag>}
          {row.evidence_status === "missing_evidence" && (
            <Tag color="warning">⚠ {t("missing evidence")}</Tag>
          )}
        </div>
        <Tag>{t(row.assertion_kind)}</Tag>
        <div className="rowActions">
          <Button
            size="small"
            icon={<Edit3 size={13} />}
            disabled
            title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Entity editing is not available from the current API yet.")}
          >
            {t("Edit")}
          </Button>
          <Button
            size="small"
            danger
            icon={<Trash2 size={13} />}
            disabled
            title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Entity deletion is not available from the current API yet.")}
          >
            {t("Delete")}
          </Button>
        </div>
      </div>
      {selected && (
        <div className="entityShapePanel">
          {loadingGuidance ? (
            <Skeleton active paragraph={{ rows: 2 }} />
          ) : guidanceError ? (
            <Alert type="warning" showIcon message={guidanceError} />
          ) : guidance ? (
            <EntityShapeReadOnly guidance={guidance} />
          ) : null}
        </div>
      )}
    </li>
  );
}

function EntityShapeReadOnly({ guidance }: { guidance: SemanticShaclFormGuidance }) {
  const t = useT();
  const fields = useMemo(() => guidance.fields ?? [], [guidance]);
  return (
    <div>
      <div style={{ marginBottom: 6, fontWeight: 600 }}>
        {t("Class shape · {n} fields", { n: fields.length })}
      </div>
      {fields.length === 0 ? (
        <div>{t("No shape fields derived for this entity's class yet.")}</div>
      ) : (
        <ul className="shapeFieldList">
          {fields.map((field, idx) => (
            <li key={field.path ?? idx} className="shapeFieldItem">
              <code>{field.path ?? "(unknown path)"}</code>
              {field.label && <span style={{ marginLeft: 8 }}>{field.label}</span>}
              {field.provenance && (
                <Tag style={{ marginLeft: 8 }}>{field.provenance}</Tag>
              )}
              {field.required && <Tag color="red">{t("required")}</Tag>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export type { EntitiesPageProps };

function compactIri(value: string) {
  const hash = value.lastIndexOf("#");
  const slash = value.lastIndexOf("/");
  const idx = Math.max(hash, slash);
  return idx >= 0 ? value.slice(idx + 1) : value;
}
