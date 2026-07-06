/**
 * Stage 2 §7 — Catalog Mappings step (RDF-derived).
 *
 * Replaces the original Postgres-backed MappingStep inside CatalogWizardPage
 * when a graph set is selected (URL ?graphSet=...). Renders SemanticMapping
 * rows from the `mapping-list` read model and lets the user add / delete
 * mappings via the canonical-write kinds `create_mapping` / `delete_mapping`.
 *
 * Connector / DataSource / DataResource / ExternalField / ConnectorTemplate
 * stay on Postgres per spec §7.1; only SemanticMapping is rebuilt as RDF.
 */

import { Alert, Button, Card, Modal, Select, Skeleton, Tag } from "antd";
import { ArrowLeft, ArrowRight, Plus, RefreshCw, Route, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import { compileAndApplyProductCommand, readModel } from "../semanticApi";
import type { ClassDef, Entity, ExternalField, PropertyDef, RelationType } from "../types";
import type { WorkbenchRequest } from "./workbenchTypes";

// Default base IRI; aligns with backend Settings.semantic_base_iri.
const SEMANTIC_BASE_IRI = "http://ontology-platform.local/semantic/";

type MappingTargetType = "class" | "property" | "relation_type";

type MappingListRow = {
  mapping: string;
  external_field: string | null;
  target: string | null;
  join_key: string | null;
  confidence: number | null;
  owner: string | null;
  graph: string;
};

type MappingListEnvelope = {
  graph_set_id: string;
  items: MappingListRow[];
};

type CatalogMappingsStepProps = {
  graphSetId: string;
  ontologyId: string;
  projectId: string;
  classes: ClassDef[];
  propertiesByClass: Record<string, PropertyDef[]>;
  relationTypes: RelationType[];
  entities: Entity[];
  fields: ExternalField[];
  request: WorkbenchRequest;
  readOnly: boolean;
  busy: boolean;
  onBack: () => void;
  onAdvance: () => void;
};

type NewMappingForm = {
  targetType: MappingTargetType;
  targetId: string;
  fieldId: string;
  joinKey: string;
  confidence: string;
  owner: string;
};

const defaultForm: NewMappingForm = {
  targetType: "class",
  targetId: "",
  fieldId: "",
  joinKey: '{\n  "entity_property": "student_number",\n  "external_field": "student_no"\n}',
  confidence: "1",
  owner: "",
};

function externalFieldIri(fieldId: string): string {
  return `${SEMANTIC_BASE_IRI}external-field/${fieldId}`;
}

function targetIri(targetType: MappingTargetType, targetId: string): string {
  const kind = targetType === "relation_type" ? "relation-type" : targetType;
  return `${SEMANTIC_BASE_IRI}${kind}/${targetId}`;
}

function parseObject(text: string): Record<string, unknown> {
  const value = JSON.parse(text) as unknown;
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Join key JSON must be an object");
  }
  return value as Record<string, unknown>;
}

export function CatalogMappingsStep(props: CatalogMappingsStepProps) {
  const t = useT();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [envelope, setEnvelope] = useState<MappingListEnvelope | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<NewMappingForm>(defaultForm);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await readModel<MappingListEnvelope>(
        props.request,
        props.graphSetId,
        "mapping-list",
      );
      setEnvelope(data);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [props.graphSetId, props.request]);

  useEffect(() => {
    void load();
  }, [load]);

  const targetOptions = useMemo(() => {
    if (form.targetType === "class") {
      return props.classes.map((item) => ({
        value: item.id,
        label: t("{name} · class", { name: item.name }),
      }));
    }
    if (form.targetType === "property") {
      return Object.values(props.propertiesByClass)
        .flat()
        .map((item) => ({
          value: item.id,
          label: t("{name} · property", { name: item.name }),
        }));
    }
    return props.relationTypes.map((item) => ({
      value: item.id,
      label: t("{name} · relation type", { name: item.name }),
    }));
  }, [form.targetType, props.classes, props.propertiesByClass, props.relationTypes, t]);

  async function submitNewMapping() {
    if (!form.targetId || !form.fieldId) return;
    setCreating(true);
    setError("");
    try {
      const joinKeyRaw = parseObject(form.joinKey);
      await compileAndApplyProductCommand(props.request, {
        command_kind: "create_mapping",
        payload: {
          ontology_id: props.ontologyId,
          external_field_iri: externalFieldIri(form.fieldId),
          target_type: form.targetType,
          target_iri: targetIri(form.targetType, form.targetId),
          join_key: JSON.stringify(joinKeyRaw),
          confidence: Number(form.confidence || 1),
          owner: form.owner || null,
        },
        graph_set_id: props.graphSetId,
        actor: "user:stage2-catalog-mappings",
        reason: "create via Stage 2 CatalogMappingsStep",
      });
      setForm((current) => ({ ...defaultForm, targetType: current.targetType }));
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setCreating(false);
    }
  }

  async function deleteMapping(mappingIri: string) {
    if (!mappingIri) return;
    setError("");
    try {
      await compileAndApplyProductCommand(props.request, {
        command_kind: "delete_mapping",
        payload: {
          ontology_id: props.ontologyId,
          mapping_iri: mappingIri,
        },
        graph_set_id: props.graphSetId,
        actor: "user:stage2-catalog-mappings",
        reason: "delete via Stage 2 CatalogMappingsStep",
      });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  return (
    <div className="wizardGrid">
      <div className="stackForm">
        <div className="wizardHelp">
          {t("将本体元素（类 / 属性 / 关系类型）映射到外部字段，写入 RDF 图。可循环添加多条。")}
        </div>
        <Select
          value={form.targetType}
          onChange={(value) =>
            setForm((current) => ({
              ...current,
              targetType: value as MappingTargetType,
              targetId: "",
            }))
          }
          disabled={props.readOnly}
          options={[
            { value: "class", label: "Class" },
            { value: "property", label: "Property" },
            { value: "relation_type", label: "RelationType" },
          ]}
        />
        <Select
          showSearch
          optionFilterProp="label"
          options={targetOptions}
          placeholder={t("Ontology target")}
          value={form.targetId || undefined}
          onChange={(value) => setForm((current) => ({ ...current, targetId: value }))}
          disabled={props.readOnly}
        />
        <Select
          showSearch
          optionFilterProp="label"
          options={props.fields.map((field) => ({
            value: field.id,
            label: `${field.name} · ${field.sensitivity}`,
          }))}
          placeholder={t("Select external field")}
          value={form.fieldId || undefined}
          onChange={(value) => setForm((current) => ({ ...current, fieldId: value }))}
          disabled={props.readOnly}
        />
        <textarea
          rows={5}
          value={form.joinKey}
          onChange={(event) => setForm((current) => ({ ...current, joinKey: event.target.value }))}
          disabled={props.readOnly}
        />
        <input
          placeholder={t("Owner")}
          value={form.owner}
          onChange={(event) => setForm((current) => ({ ...current, owner: event.target.value }))}
          disabled={props.readOnly}
        />
        <input
          placeholder={t("Confidence (0-1)")}
          value={form.confidence}
          onChange={(event) =>
            setForm((current) => ({ ...current, confidence: event.target.value }))
          }
          disabled={props.readOnly}
        />
        <div className="wizardActions">
          <button className="secondaryButton" onClick={props.onBack} type="button">
            <ArrowLeft size={15} /> {t("上一步")}
          </button>
          <Button
            type="primary"
            icon={<Plus size={15} />}
            disabled={props.readOnly || props.busy || creating || !form.targetId || !form.fieldId}
            onClick={() => setCreating(true)}
          >
            {t("添加 mapping")}
          </Button>
        </div>
      </div>
      <div className="wizardSide">
        <div className="wizardSideHeader">
          <strong>
            {t("已有 mapping ({n})", { n: envelope?.items.length ?? 0 })}
          </strong>
          <Button
            size="small"
            icon={<RefreshCw size={14} />}
            onClick={() => void load()}
            disabled={loading}
          >
            {t("Refresh")}
          </Button>
        </div>
        {error && (
          <Alert
            type="error"
            showIcon
            message={t("Mapping operation failed")}
            description={error}
            closable
            onClose={() => setError("")}
          />
        )}
        {loading ? (
          <Skeleton active />
        ) : envelope && envelope.items.length > 0 ? (
          <div className="dataList">
            {envelope.items.map((row) => (
              <div className="dataRow" key={row.mapping}>
                <span className="rowContent">
                  <Route size={15} />
                  <div>
                    <strong>{row.target ?? row.mapping}</strong>
                    <code>{row.external_field ?? "—"}</code>
                    {row.confidence !== null && (
                      <Tag>{t("confidence")}: {row.confidence}</Tag>
                    )}
                    {row.owner && <Tag>{row.owner}</Tag>}
                  </div>
                </span>
                <button
                  className="iconButton"
                  type="button"
                  aria-label={t("Delete mapping")}
                  disabled={props.readOnly || props.busy}
                  onClick={() => void deleteMapping(row.mapping)}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <div className="emptyState">
            {t("暂无 RDF mapping。新增一条以开始。")}
          </div>
        )}
      </div>

      <Modal
        title={t("Create mapping")}
        open={creating}
        onCancel={() => {
          setCreating(false);
          setError("");
        }}
        onOk={() => void submitNewMapping()}
        confirmLoading={creating}
        okText={t("Create mapping")}
        okButtonProps={{ disabled: !form.targetId || !form.fieldId }}
      >
        <Card size="small" type="inner">
          <pre className="jsonBlock">{JSON.stringify(
            {
              target_type: form.targetType,
              target_id: form.targetId,
              field_id: form.fieldId,
              join_key: form.joinKey,
              confidence: Number(form.confidence || 1),
              owner: form.owner || null,
              graph_set_id: props.graphSetId,
              ontology_id: props.ontologyId,
            },
            null,
            2,
          )}</pre>
        </Card>
      </Modal>

      <div className="wizardAdvance">
        <Button
          type="primary"
          icon={<ArrowRight size={15} />}
          onClick={props.onAdvance}
          disabled={props.busy}
        >
          {t("下一步")}
        </Button>
      </div>
    </div>
  );
}

export type { CatalogMappingsStepProps };
