/**
 * Stage 2 §4 — graph-derived ClassesPage.
 *
 * MVP slice: renders classes and relation types from read models as a
 * topology graph, and exposes a "New class" button that creates a class
 * via canonical-write. Full property/relation CRUD and shape sub-mode land
 * in later iterations. The legacy implementation remains at
 * ClassesPage.legacy.tsx and is wired as the fallback when no graph set is
 * selected.
 */

import { Alert, Button, Card, Input, Modal, Skeleton, Tag } from "antd";
import { Edit3, Plus, RefreshCw, Save, Search, Trash2, X } from "lucide-react";
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
  type SemanticShaclFormGuidance,
} from "../semanticApi";
import type { WorkbenchRequest } from "./workbenchTypes";

type ClassTopologyRow = {
  iri: string;
  label: string | null;
  source_graph_iri: string;
  assertion_kind: string;
  parent?: string | null;
};

type ClassTopologyEnvelope = {
  graph_set_id: string;
  items: ClassTopologyRow[];
};

type RelationTypeRow = {
  iri: string;
  label: string | null;
  source_graph_iri: string;
  assertion_kind: string;
  source?: string | null;
  target?: string | null;
};

type ClassGraphEdgePayload =
  | { kind: "subclass"; child: ClassTopologyRow; parentIri: string; id: string }
  | { kind: "relation_type"; row: RelationTypeRow; id: string };

type RelationTypeEnvelope = {
  graph_set_id: string;
  items: RelationTypeRow[];
};

type ClassesPageProps = {
  graphSetId: string;
  ontologyId: string;
  readOnly: boolean;
  request: WorkbenchRequest;
};

export function ClassesPage({ graphSetId, ontologyId, readOnly, request }: ClassesPageProps) {
  const t = useT();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [envelope, setEnvelope] = useState<ClassTopologyEnvelope | null>(null);
  const [relations, setRelations] = useState<RelationTypeEnvelope | null>(null);
  const [selectedIri, setSelectedIri] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [detailName, setDetailName] = useState("");
  const [detailDescription, setDetailDescription] = useState("");
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [classData, relationData] = await Promise.all([
        readModel<ClassTopologyEnvelope>(request, graphSetId, "class-topology"),
        readModel<RelationTypeEnvelope>(request, graphSetId, "relation-type-list"),
      ]);
      setEnvelope(classData);
      setRelations(relationData);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [graphSetId, request]);

  useEffect(() => {
    void load();
  }, [load]);

  const { graphNodes, graphEdges, classByIri, edgeById } = useMemo(() => {
    const byIri = new Map<string, ClassTopologyRow>();
    for (const row of envelope?.items ?? []) {
      if (!byIri.has(row.iri)) byIri.set(row.iri, row);
    }
    const nodes: ForceGraphNode[] = Array.from(byIri.values()).map((row) => ({
      id: row.iri,
      label: row.label ?? compactIri(row.iri),
      group: row.assertion_kind,
    }));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges: ForceGraphEdge[] = [];
    const edgePayloads = new Map<string, ClassGraphEdgePayload>();

    for (const row of envelope?.items ?? []) {
      if (row.parent && nodeIds.has(row.parent) && nodeIds.has(row.iri)) {
        const id = `subclass:${row.iri}:${row.parent}`;
        edges.push({
          id,
          source: row.iri,
          target: row.parent,
          label: t("subClassOf"),
        });
        edgePayloads.set(id, { kind: "subclass", child: row, parentIri: row.parent, id });
      }
    }
    for (const [index, row] of (relations?.items ?? []).entries()) {
      if (row.source && row.target && nodeIds.has(row.source) && nodeIds.has(row.target)) {
        const id = `relation:${row.iri}:${row.source}:${row.target}:${index}`;
        edges.push({
          id,
          source: row.source,
          target: row.target,
          label: row.label ?? compactIri(row.iri),
        });
        edgePayloads.set(id, { kind: "relation_type", row, id });
      }
    }
    return { graphNodes: nodes, graphEdges: edges, classByIri: byIri, edgeById: edgePayloads };
  }, [envelope, relations, t]);

  const selectedClass = selectedIri ? classByIri.get(selectedIri) ?? null : null;
  const selectedEdge = selectedEdgeId ? edgeById.get(selectedEdgeId) ?? null : null;
  const hasGraphSelection = Boolean(selectedClass || selectedEdge);

  useEffect(() => {
    const label =
      selectedClass?.label ??
      (selectedEdge?.kind === "relation_type" ? selectedEdge.row.label : null) ??
      "";
    setDetailName(label);
    setDetailDescription("");
    setEditing(false);
  }, [selectedClass, selectedEdge]);

  async function submitNewClass() {
    if (!newName.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      await compileAndApplyProductCommand(request, {
        command_kind: "create_class",
        payload: {
          ontology_id: ontologyId,
          name: newName.trim(),
          description: newDescription.trim() || null,
          aliases: [],
          parent_class_ids: [],
        },
        graph_set_id: graphSetId,
        actor: "user:stage2-classes-page",
        reason: "create via Stage 2 ClassesPage MVP",
      });
      setNewName("");
      setNewDescription("");
      setCreating(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  async function applyDetailUpdate() {
    if (!selectedClass && selectedEdge?.kind !== "relation_type") return;
    setSubmitting(true);
    setError("");
    try {
      if (selectedClass) {
        await compileAndApplyProductCommand(request, {
          command_kind: "update_class",
          payload: {
            ontology_id: ontologyId,
            class_iri: selectedClass.iri,
            name: detailName.trim() || selectedClass.label || compactIri(selectedClass.iri),
            description: detailDescription,
          },
          graph_set_id: graphSetId,
          actor: "user:stage2-classes-page",
          reason: "update class from graph detail panel",
        });
      } else if (selectedEdge?.kind === "relation_type") {
        await compileAndApplyProductCommand(request, {
          command_kind: "update_relation_type",
          payload: {
            ontology_id: ontologyId,
            relation_type_iri: selectedEdge.row.iri,
            name: detailName.trim() || selectedEdge.row.label || compactIri(selectedEdge.row.iri),
            description: detailDescription,
          },
          graph_set_id: graphSetId,
          actor: "user:stage2-classes-page",
          reason: "update relation type from graph detail panel",
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
    if (!selectedClass && selectedEdge?.kind !== "relation_type") return;
    setSubmitting(true);
    setError("");
    try {
      if (selectedClass) {
        await compileAndApplyProductCommand(request, {
          command_kind: "delete_class",
          payload: { ontology_id: ontologyId, class_iri: selectedClass.iri },
          graph_set_id: graphSetId,
          actor: "user:stage2-classes-page",
          reason: "delete class from graph detail panel",
        });
        setSelectedIri(null);
      } else if (selectedEdge?.kind === "relation_type") {
        await compileAndApplyProductCommand(request, {
          command_kind: "delete_relation_type",
          payload: { ontology_id: ontologyId, relation_type_iri: selectedEdge.row.iri },
          graph_set_id: graphSetId,
          actor: "user:stage2-classes-page",
          reason: "delete relation type from graph detail panel",
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

  return (
    <section className="classesPage stage2">
      <header className="topBar">
        <div>
          <span className="eyebrow">{t("Business modeling")}</span>
          <h1>{t("Classes")}</h1>
          <div className="crumbTrail">
            <span>{t("Class diagram")}</span>
          </div>
        </div>
        <div className="topActions">
          <Button
            icon={<RefreshCw size={15} />}
            onClick={() => void load()}
            disabled={loading}
          >
            {t("Refresh")}
          </Button>
          <Button
            type="primary"
            icon={<Plus size={15} />}
            disabled={readOnly || creating}
            title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : undefined}
            onClick={() => setCreating(true)}
          >
            {t("New class")}
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
        size="small"
        title={t("Class force graph · {nodes} nodes · {edges} edges", {
          nodes: graphNodes.length,
          edges: graphEdges.length,
        })}
      >
        <div className="semanticGraphToolbar">
          <Input
            prefix={<Search size={14} />}
            placeholder={t("Search classes")}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            allowClear
          />
          {selectedIri && (
            <Tag closable onClose={() => setSelectedIri(null)}>
              {graphNodes.find((node) => node.id === selectedIri)?.label ?? compactIri(selectedIri)}
            </Tag>
          )}
          {selectedEdge && (
            <Tag closable onClose={() => setSelectedEdgeId(null)}>
              {selectedEdge.kind === "relation_type"
                ? selectedEdge.row.label ?? compactIri(selectedEdge.row.iri)
                : t("subClassOf")}
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
                cacheKey={graphSetId}
                layoutMode="hierarchy"
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
                emptyTitle={t("No classes in this workspace yet.")}
                emptyHint={t("Create a class to populate the force graph.")}
              />
            )}
          </div>
          <ClassGraphDetailPanel
            selectedClass={selectedClass}
            selectedEdge={selectedEdge}
            classByIri={classByIri}
            readOnly={readOnly}
            busy={submitting}
            editing={editing}
            detailName={detailName}
            detailDescription={detailDescription}
            onChangeName={setDetailName}
            onChangeDescription={setDetailDescription}
            onEdit={() => setEditing(true)}
            onCancelEdit={() => setEditing(false)}
            onSave={() => void applyDetailUpdate()}
            onDelete={() => void deleteSelectedDetail()}
            onClose={clearSelection}
          />
        </div>
      </Card>

      <Modal
        title={t("Create class")}
        open={creating}
        onCancel={() => {
          setCreating(false);
          setNewName("");
          setNewDescription("");
        }}
        onOk={() => void submitNewClass()}
        confirmLoading={submitting}
        okText={t("Create class")}
      >
        <Input
          placeholder={t("Class name")}
          value={newName}
          onChange={(event) => setNewName(event.target.value)}
          autoFocus
        />
        <Input.TextArea
          placeholder={t("Description (optional)")}
          value={newDescription}
          onChange={(event) => setNewDescription(event.target.value)}
          rows={3}
          style={{ marginTop: 12 }}
        />
      </Modal>
    </section>
  );
}

export type { ClassesPageProps, SemanticShaclFormGuidance };

type ClassGraphDetailPanelProps = {
  selectedClass: ClassTopologyRow | null;
  selectedEdge: ClassGraphEdgePayload | null;
  classByIri: Map<string, ClassTopologyRow>;
  readOnly: boolean;
  busy: boolean;
  editing: boolean;
  detailName: string;
  detailDescription: string;
  onChangeName: (value: string) => void;
  onChangeDescription: (value: string) => void;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  onDelete: () => void;
  onClose: () => void;
};

function ClassGraphDetailPanel({
  selectedClass,
  selectedEdge,
  classByIri,
  readOnly,
  busy,
  editing,
  detailName,
  detailDescription,
  onChangeName,
  onChangeDescription,
  onEdit,
  onCancelEdit,
  onSave,
  onDelete,
  onClose,
}: ClassGraphDetailPanelProps) {
  const t = useT();
  const relationRow = selectedEdge?.kind === "relation_type" ? selectedEdge.row : null;
  const subclassEdge = selectedEdge?.kind === "subclass" ? selectedEdge : null;
  const selected = selectedClass || selectedEdge;
  const editable = Boolean(selectedClass || relationRow);
  const title = selectedClass
    ? selectedClass.label ?? compactIri(selectedClass.iri)
    : relationRow
      ? relationRow.label ?? compactIri(relationRow.iri)
      : subclassEdge
        ? t("subClassOf")
        : t("Select an item");

  if (!selected) return null;

  return (
    <aside className="semanticGraphDetail" aria-label={t("Graph item details")}>
      <header className="semanticGraphDetailHeader">
        <div>
          <Tag>{selectedClass ? t("Class") : relationRow ? t("Relation type") : t("Class relation")}</Tag>
          <h2>{title}</h2>
        </div>
        <Button size="small" icon={<X size={14} />} onClick={onClose} aria-label={t("Close details")} />
      </header>

      {editing && editable ? (
        <div className="semanticGraphDetailForm">
          <label>
            <span>{t("Name")}</span>
            <Input value={detailName} onChange={(event) => onChangeName(event.target.value)} />
          </label>
          <label>
            <span>{t("Description")}</span>
            <Input.TextArea
              value={detailDescription}
              onChange={(event) => onChangeDescription(event.target.value)}
              rows={3}
              placeholder={t("Optional description")}
            />
          </label>
          <div className="semanticGraphDetailActions">
            <Button onClick={onCancelEdit} disabled={busy}>{t("Cancel")}</Button>
            <Button type="primary" icon={<Save size={14} />} onClick={onSave} loading={busy}>
              {t("Save")}
            </Button>
          </div>
        </div>
      ) : (
        <>
          <dl className="semanticGraphDetailList">
            {selectedClass && (
              <>
                <div><dt>{t("IRI")}</dt><dd><code>{selectedClass.iri}</code></dd></div>
                <div><dt>{t("Source graph")}</dt><dd><code>{selectedClass.source_graph_iri}</code></dd></div>
                <div><dt>{t("Assertion")}</dt><dd>{selectedClass.assertion_kind}</dd></div>
                <div>
                  <dt>{t("Parents")}</dt>
                  <dd>
                    {(Array.from(classByIri.values()).filter((row) => row.iri === selectedClass.iri && row.parent).map((row) => row.parent) as string[]).length
                      ? Array.from(classByIri.values())
                          .filter((row) => row.iri === selectedClass.iri && row.parent)
                          .map((row) => compactIri(row.parent ?? ""))
                          .join(", ")
                      : t("None")}
                  </dd>
                </div>
              </>
            )}
            {relationRow && (
              <>
                <div><dt>{t("IRI")}</dt><dd><code>{relationRow.iri}</code></dd></div>
                <div><dt>{t("Source class")}</dt><dd>{classByIri.get(relationRow.source ?? "")?.label ?? compactIri(relationRow.source ?? "")}</dd></div>
                <div><dt>{t("Target class")}</dt><dd>{classByIri.get(relationRow.target ?? "")?.label ?? compactIri(relationRow.target ?? "")}</dd></div>
                <div><dt>{t("Source graph")}</dt><dd><code>{relationRow.source_graph_iri}</code></dd></div>
              </>
            )}
            {subclassEdge && (
              <>
                <div><dt>{t("Child class")}</dt><dd>{subclassEdge.child.label ?? compactIri(subclassEdge.child.iri)}</dd></div>
                <div><dt>{t("Parent class")}</dt><dd>{classByIri.get(subclassEdge.parentIri)?.label ?? compactIri(subclassEdge.parentIri)}</dd></div>
                <div><dt>{t("IRI")}</dt><dd><code>rdfs:subClassOf</code></dd></div>
              </>
            )}
          </dl>
          <div className="semanticGraphDetailActions">
            <Button
              icon={<Edit3 size={14} />}
              onClick={onEdit}
              disabled={readOnly || !editable || busy}
            >
              {t("Edit")}
            </Button>
            <Button
              danger
              icon={<Trash2 size={14} />}
              onClick={onDelete}
              disabled={readOnly || !editable || busy}
              loading={busy}
            >
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
