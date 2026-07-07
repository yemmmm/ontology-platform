/**
 * Stage 2 §4 — graph-derived ClassesPage.
 *
 * MVP slice: lists classes from the class-topology read model, exposes a
 * "New class" button that creates a class via canonical-write. Full editor
 * (topology canvas, property/relation CRUD, shape sub-mode) lands in later
 * iterations. The legacy implementation remains at ClassesPage.legacy.tsx
 * and is wired as the fallback when no graph set is selected.
 */

import { Alert, Button, Card, Input, Modal, Skeleton, Tag } from "antd";
import { Box, Edit3, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

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
};

type ClassTopologyEnvelope = {
  graph_set_id: string;
  items: ClassTopologyRow[];
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
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await readModel<ClassTopologyEnvelope>(request, graphSetId, "class-topology");
      setEnvelope(data);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [graphSetId, request]);

  useEffect(() => {
    void load();
  }, [load]);

  async function submitNewClass() {
    if (!newName.trim()) return;
    setCreating(true);
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
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setCreating(false);
    }
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
        title={t("Class diagram · {n}", { n: envelope?.items.length ?? 0 })}
      >
        {loading ? (
          <Skeleton active />
        ) : envelope && envelope.items.length > 0 ? (
          <ul className="classList">
            {envelope.items.map((row) => (
              <li key={row.iri} className="classListItem">
                <Box size={16} />
                <div>
                  <strong>{row.label ?? row.iri}</strong>
                </div>
                <Tag>{t(row.assertion_kind)}</Tag>
                <div className="rowActions">
                  <Button
                    size="small"
                    icon={<Edit3 size={13} />}
                    disabled
                    title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Class editing is not available from the current API yet.")}
                  >
                    {t("Edit")}
                  </Button>
                  <Button
                    size="small"
                    danger
                    icon={<Trash2 size={13} />}
                    disabled
                    title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Class deletion is not available from the current API yet.")}
                  >
                    {t("Delete")}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div>{t("No classes in this workspace yet.")}</div>
        )}
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
        confirmLoading={creating}
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
