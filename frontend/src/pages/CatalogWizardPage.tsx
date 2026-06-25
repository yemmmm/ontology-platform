import { Alert, Card, Select, Skeleton, Tag } from "antd";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Circle,
  Clock3,
  Database,
  FlaskConical,
  Link2,
  Play,
  Plus,
  RefreshCw,
  Route,
  ShieldCheck,
  SkipForward,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  ClassDef,
  ConnectorQueryResult,
  ConnectorTemplate,
  DataResource,
  DataSource,
  Entity,
  ExternalField,
  IdentifierResolutionStats,
  JsonObject,
  PropertyDef,
  RelationType,
  SemanticMapping,
} from "../types";
import { compactId, prettyJson, splitCsv } from "../utils";
import type { WorkbenchRequest } from "./workbenchTypes";

type CatalogPageProps = {
  projectId: string;
  ontologyId: string;
  classes: ClassDef[];
  propertiesByClass: Record<string, PropertyDef[]>;
  relationTypes: RelationType[];
  entities: Entity[];
  readOnly?: boolean;
  request: WorkbenchRequest;
};

type SourceForm = {
  name: string;
  sourceType: string;
  owner: string;
  authorityLevel: string;
  description: string;
};

type ResourceForm = {
  dataSourceId: string;
  name: string;
  resourceType: string;
  owner: string;
  authorityLevel: string;
  description: string;
};

type FieldForm = {
  dataResourceId: string;
  name: string;
  dataType: string;
  sensitivity: ExternalField["sensitivity"];
  accessPolicy: ExternalField["access_policy"];
  maskingRule: string;
  approvalNote: string;
};

type MappingForm = {
  targetType: SemanticMapping["target_type"];
  targetId: string;
  fieldId: string;
  joinKey: string;
  confidence: string;
  owner: string;
};

type TemplateForm = {
  dataSourceId: string;
  name: string;
  allowedFieldIds: string[];
  accessPolicy: ConnectorTemplate["access_policy"];
  resultRows: string;
};

const defaultSource: SourceForm = {
  name: "",
  sourceType: "postgres",
  owner: "",
  authorityLevel: "authoritative",
  description: "",
};

const defaultResource: ResourceForm = {
  dataSourceId: "",
  name: "",
  resourceType: "table",
  owner: "",
  authorityLevel: "authoritative",
  description: "",
};

const defaultField: FieldForm = {
  dataResourceId: "",
  name: "",
  dataType: "string",
  sensitivity: "internal",
  accessPolicy: "allow",
  maskingRule: "",
  approvalNote: "",
};

const defaultMapping: MappingForm = {
  targetType: "entity",
  targetId: "",
  fieldId: "",
  joinKey: '{\n  "entity_property": "student_number",\n  "external_field": "student_no"\n}',
  confidence: "1",
  owner: "",
};

const defaultTemplate: TemplateForm = {
  dataSourceId: "",
  name: "",
  allowedFieldIds: [],
  accessPolicy: "allow",
  resultRows: '[\n  {"student_number": "S1", "midterm_score": 42}\n]',
};

const wizardSteps = [
  { id: 1, label: "数据源", detail: "注册外部系统", icon: Database },
  { id: 2, label: "资源", detail: "表 / API 端点", icon: ShieldCheck },
  { id: 3, label: "字段", detail: "敏感度与访问策略", icon: Link2 },
  { id: 4, label: "语义映射", detail: "Ontology ↔ 字段", icon: Route },
  { id: 5, label: "Connector", detail: "可选 · 受控查询", icon: Play },
] as const;

type WizardStepId = (typeof wizardSteps)[number]["id"];

export function CatalogWizardPage(props: CatalogPageProps) {
  const readOnly = props.readOnly ?? false;
  const [mode, setMode] = useState<"wizard" | "test">("wizard");
  const [sources, setSources] = useState<DataSource[]>([]);
  const [resources, setResources] = useState<DataResource[]>([]);
  const [fields, setFields] = useState<ExternalField[]>([]);
  const [mappings, setMappings] = useState<SemanticMapping[]>([]);
  const [templates, setTemplates] = useState<ConnectorTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [sourceData, resourceData, fieldData, mappingData, templateData] = await Promise.all([
        props.request<DataSource[]>(`/projects/${props.projectId}/data-sources`),
        props.request<DataResource[]>(`/projects/${props.projectId}/data-resources`),
        props.request<ExternalField[]>(`/projects/${props.projectId}/external-fields`),
        props.request<SemanticMapping[]>(
          `/projects/${props.projectId}/semantic-mappings?ontology_id=${props.ontologyId}`,
        ),
        props.request<ConnectorTemplate[]>(`/projects/${props.projectId}/connector-templates`),
      ]);
      setSources(sourceData);
      setResources(resourceData);
      setFields(fieldData);
      setMappings(mappingData);
      setTemplates(templateData);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [props.ontologyId, props.projectId, props.request]);

  useEffect(() => { void load(); }, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Card className="panel"><Skeleton active paragraph={{ rows: 10 }} /></Card>;

  return (
    <section className="catalogPage">
      <header className="pageSubHeader">
        <div>
          <h2>Data Catalog</h2>
          <p>注册外部系统、把本体目标路由到字段、运行受控 Connector 查询。</p>
        </div>
        <div className="rowActions">
          {readOnly && <Tag color="blue">已发布 · 只读</Tag>}
          <div className="catalogSegmented" role="tablist">
            <button
              className={classNames("catalogSegmentedItem", mode === "wizard" && "active")}
              onClick={() => setMode("wizard")}
              role="tab"
              aria-selected={mode === "wizard"}
              type="button"
            >
              <Route size={14} /> 向导
            </button>
            <button
              className={classNames("catalogSegmentedItem", mode === "test" && "active")}
              onClick={() => setMode("test")}
              role="tab"
              aria-selected={mode === "test"}
              type="button"
            >
              <FlaskConical size={14} /> Test
            </button>
          </div>
          <button className="secondaryButton" disabled={busy} onClick={() => void load()} type="button">
            <RefreshCw className={busy ? "spin" : ""} size={15} /> Refresh
          </button>
        </div>
      </header>

      {error && <Alert type="error" showIcon closable onClose={() => setError("")} message="Catalog operation failed" description={error} />}

      <div className="catalogSummary">
        <Metric icon={<Database size={17} />} label="Sources" value={sources.length} />
        <Metric icon={<ShieldCheck size={17} />} label="External fields" value={fields.length} />
        <Metric icon={<Link2 size={17} />} label="Mappings" value={mappings.length} />
        <Metric icon={<Route size={17} />} label="Connector templates" value={templates.length} />
      </div>

      {mode === "wizard" ? (
        <CatalogWizard
          {...props}
          readOnly={readOnly}
          sources={sources}
          resources={resources}
          fields={fields}
          run={run}
          busy={busy}
        />
      ) : (
        <CatalogTest
          {...props}
          templates={templates}
          run={run}
          busy={busy}
        />
      )}

      <Card className="panel" title="Catalog records">
        <div className="catalogRecords">
          {sources.map((source) => <RecordItem key={source.id} title={source.name} meta={`${source.source_type} · ${source.authority_level}`} tag={source.status} />)}
          {fields.map((field) => <RecordItem key={field.id} title={field.name} meta={`${field.data_type} · ${field.access_policy}`} tag={field.sensitivity} />)}
          {mappings.map((mapping) => <RecordItem key={mapping.id} title={`${mapping.target_type} ${compactId(mapping.target_id)}`} meta={`${mapping.external_resource_name}.${mapping.external_field_name}`} tag={mapping.status} />)}
          {!sources.length && !fields.length && !mappings.length && <div className="emptyState">No catalog records yet.</div>}
        </div>
      </Card>
    </section>
  );
}

type WizardShared = {
  projectId: string;
  ontologyId: string;
  classes: ClassDef[];
  propertiesByClass: Record<string, PropertyDef[]>;
  relationTypes: RelationType[];
  entities: Entity[];
  request: WorkbenchRequest;
  readOnly: boolean;
  sources: DataSource[];
  resources: DataResource[];
  fields: ExternalField[];
  busy: boolean;
  run: (action: () => Promise<void>) => Promise<void>;
};

function CatalogWizard(props: WizardShared) {
  const [step, setStep] = useState<WizardStepId>(1);
  const [sourceForm, setSourceForm] = useState<SourceForm>(defaultSource);
  const [resourceForm, setResourceForm] = useState<ResourceForm>(defaultResource);
  const [fieldForm, setFieldForm] = useState<FieldForm>(defaultField);
  const [mappingForm, setMappingForm] = useState<MappingForm>(defaultMapping);
  const [templateForm, setTemplateForm] = useState<TemplateForm>(defaultTemplate);
  const [wizardSourceId, setWizardSourceId] = useState("");
  const [wizardResourceId, setWizardResourceId] = useState("");
  const [fieldAddedCount, setFieldAddedCount] = useState(0);
  const [mappingAddedCount, setMappingAddedCount] = useState(0);
  const [templateDone, setTemplateDone] = useState<"pending" | "created" | "skipped">("pending");

  const stepIndex = wizardSteps.findIndex((item) => item.id === step);
  const activeDef = wizardSteps[stepIndex];

  function jumpTo(target: WizardStepId) {
    setStep(target);
  }

  function parseObject(text: string): JsonObject {
    const value = JSON.parse(text) as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("JSON must be an object");
    return value as JsonObject;
  }

  function parseRows(text: string): JsonObject[] {
    const value = JSON.parse(text) as unknown;
    if (!Array.isArray(value) || value.some((item) => !item || typeof item !== "object" || Array.isArray(item))) {
      throw new Error("Rows must be a JSON array of objects");
    }
    return value as JsonObject[];
  }

  function submitSource() {
    void props.run(async () => {
      const created = await props.request<DataSource>(`/projects/${props.projectId}/data-sources`, {
        method: "POST",
        body: JSON.stringify({
          name: sourceForm.name,
          source_type: sourceForm.sourceType,
          owner: sourceForm.owner || null,
          authority_level: sourceForm.authorityLevel,
          status: "available",
          description: sourceForm.description || null,
          connection_policy: {},
        }),
      });
      setWizardSourceId(created.id);
      setResourceForm((current) => ({ ...current, dataSourceId: created.id }));
      setTemplateForm((current) => ({ ...current, dataSourceId: created.id }));
      setSourceForm(defaultSource);
      setStep(2);
    });
  }

  function useExistingSource(sourceId: string) {
    if (!sourceId) return;
    setWizardSourceId(sourceId);
    setResourceForm((current) => ({ ...current, dataSourceId: sourceId }));
    setTemplateForm((current) => ({ ...current, dataSourceId: sourceId }));
    setStep(2);
  }

  function submitResource() {
    void props.run(async () => {
      const created = await props.request<DataResource>(`/projects/${props.projectId}/data-resources`, {
        method: "POST",
        body: JSON.stringify({
          data_source_id: resourceForm.dataSourceId,
          name: resourceForm.name,
          resource_type: resourceForm.resourceType,
          owner: resourceForm.owner || null,
          authority_level: resourceForm.authorityLevel,
          status: "available",
          description: resourceForm.description || null,
        }),
      });
      setWizardResourceId(created.id);
      setFieldForm((current) => ({ ...current, dataResourceId: created.id }));
      setResourceForm((current) => ({ ...defaultResource, dataSourceId: wizardSourceId || current.dataSourceId }));
      setStep(3);
    });
  }

  function useExistingResource(resourceId: string) {
    if (!resourceId) return;
    const resource = props.resources.find((item) => item.id === resourceId);
    setWizardResourceId(resourceId);
    setFieldForm((current) => ({ ...current, dataResourceId: resourceId }));
    if (resource && !wizardSourceId) {
      setWizardSourceId(resource.data_source_id);
      setTemplateForm((current) => ({ ...current, dataSourceId: resource.data_source_id }));
    }
    setStep(3);
  }

  function submitField(advance: boolean) {
    void props.run(async () => {
      await props.request<ExternalField>(`/projects/${props.projectId}/external-fields`, {
        method: "POST",
        body: JSON.stringify({
          data_resource_id: fieldForm.dataResourceId,
          name: fieldForm.name,
          data_type: fieldForm.dataType,
          sensitivity: fieldForm.sensitivity,
          access_policy: fieldForm.accessPolicy,
          masking_rule: fieldForm.maskingRule || null,
          approval_note: fieldForm.approvalNote || null,
          audit_required: fieldForm.accessPolicy !== "allow",
          description: null,
        }),
      });
      setFieldForm((current) => ({ ...defaultField, dataResourceId: wizardResourceId || current.dataResourceId }));
      setFieldAddedCount((count) => count + 1);
      if (advance) setStep(4);
    });
  }

  function useExistingField(fieldId: string) {
    if (!fieldId) return;
    setMappingForm((current) => ({ ...current, fieldId }));
    setStep(4);
  }

  const targetOptions = useMemo(() => {
    if (mappingForm.targetType === "class") {
      return props.classes.map((item) => ({ value: item.id, label: `${item.name} · class` }));
    }
    if (mappingForm.targetType === "property") {
      return Object.values(props.propertiesByClass).flat().map((item) => ({ value: item.id, label: `${item.name} · property` }));
    }
    if (mappingForm.targetType === "relation_type") {
      return props.relationTypes.map((item) => ({ value: item.id, label: `${item.name} · relation type` }));
    }
    return props.entities.map((item) => ({ value: item.id, label: `${item.name} · entity` }));
  }, [mappingForm.targetType, props.classes, props.entities, props.propertiesByClass, props.relationTypes]);

  function submitMapping(advance: boolean) {
    void props.run(async () => {
      await props.request<SemanticMapping>(`/projects/${props.projectId}/semantic-mappings`, {
        method: "POST",
        body: JSON.stringify({
          ontology_id: props.ontologyId,
          target_type: mappingForm.targetType,
          target_id: mappingForm.targetId,
          field_id: mappingForm.fieldId,
          join_key: parseObject(mappingForm.joinKey),
          confidence: Number(mappingForm.confidence || 1),
          owner: mappingForm.owner || null,
          status: "active",
        }),
      });
      setMappingForm((current) => ({ ...defaultMapping, fieldId: current.fieldId }));
      setMappingAddedCount((count) => count + 1);
      if (advance) setStep(5);
    });
  }

  function submitTemplate() {
    void props.run(async () => {
      await props.request<ConnectorTemplate>(`/projects/${props.projectId}/connector-templates`, {
        method: "POST",
        body: JSON.stringify({
          data_source_id: templateForm.dataSourceId,
          name: templateForm.name,
          description: null,
          allowed_field_ids: templateForm.allowedFieldIds,
          parameter_schema: {},
          result_schema: { rows: parseRows(templateForm.resultRows) },
          access_policy: templateForm.accessPolicy,
        }),
      });
      setTemplateForm((current) => ({ ...defaultTemplate, dataSourceId: current.dataSourceId }));
      setTemplateDone("created");
    });
  }

  function skipTemplate() {
    setTemplateDone("skipped");
  }

  function restartWizard() {
    setStep(1);
    setSourceForm(defaultSource);
    setResourceForm(defaultResource);
    setFieldForm(defaultField);
    setMappingForm(defaultMapping);
    setTemplateForm(defaultTemplate);
    setWizardSourceId("");
    setWizardResourceId("");
    setFieldAddedCount(0);
    setMappingAddedCount(0);
    setTemplateDone("pending");
  }

  return (
    <>
      <Card className="panel wizardCard">
        <ol className="wizardSteps">
          {wizardSteps.map((item, index) => {
            const Icon = item.icon;
            const isComplete =
              (item.id === 1 && wizardSourceId) ||
              (item.id === 2 && wizardResourceId) ||
              (item.id === 3 && fieldAddedCount > 0) ||
              (item.id === 4 && mappingAddedCount > 0) ||
              (item.id === 5 && templateDone !== "pending");
            const isActive = item.id === step;
            const isReachable =
              item.id === 1 ||
              (item.id === 2 && wizardSourceId) ||
              (item.id === 3 && wizardResourceId) ||
              (item.id === 4 && wizardResourceId) ||
              (item.id === 5 && mappingAddedCount > 0);
            return (
              <li key={item.id}>
                <button
                  className={classNames("wizardStep", isActive && "active", isComplete && "complete")}
                  disabled={!isReachable || props.readOnly}
                  onClick={() => jumpTo(item.id)}
                  type="button"
                >
                  <span className="wizardStepBadge">
                    {isComplete ? <Check size={14} /> : <Icon size={14} />}
                  </span>
                  <span className="wizardStepMeta">
                    <strong>{item.label}</strong>
                    <small>{item.detail}</small>
                  </span>
                  <span className="wizardStepIndex">Step {index + 1}</span>
                </button>
                {index < wizardSteps.length - 1 && <span className="wizardStepConnector" aria-hidden />}
              </li>
            );
          })}
        </ol>
      </Card>

      <Card
        className="panel"
        title={
          <span className="wizardCardTitle">
            <activeDef.icon size={16} />
            <span>{activeDef.label} · Step {stepIndex + 1} / {wizardSteps.length}</span>
          </span>
        }
      >
        {props.readOnly && (
          <div className="callout quiet">
            <strong>当前版本只读</strong>
            <span>已发布版本的 catalog 配置不可写入；如需修改请新建后继草稿。</span>
          </div>
        )}

        {step === 1 && (
          <SourceStep
            form={sourceForm}
            setForm={setSourceForm}
            existing={props.sources}
            busy={props.busy}
            readOnly={props.readOnly}
            onCreate={submitSource}
            onUseExisting={useExistingSource}
          />
        )}

        {step === 2 && (
          <ResourceStep
            form={resourceForm}
            setForm={setResourceForm}
            existing={props.resources}
            scopedSourceId={wizardSourceId}
            sources={props.sources}
            busy={props.busy}
            readOnly={props.readOnly}
            onCreate={submitResource}
            onUseExisting={useExistingResource}
            onBack={() => setStep(1)}
          />
        )}

        {step === 3 && (
          <FieldStep
            form={fieldForm}
            setForm={setFieldForm}
            existing={props.fields}
            scopedResourceId={wizardResourceId}
            resources={props.resources}
            addedCount={fieldAddedCount}
            busy={props.busy}
            readOnly={props.readOnly}
            onCreate={(advance) => submitField(advance)}
            onBack={() => setStep(2)}
          />
        )}

        {step === 4 && (
          <MappingStep
            form={mappingForm}
            setForm={setMappingForm}
            existing={props.fields}
            targetOptions={targetOptions}
            addedCount={mappingAddedCount}
            busy={props.busy}
            readOnly={props.readOnly}
            onCreate={(advance) => submitMapping(advance)}
            onUseExistingField={useExistingField}
            onBack={() => setStep(3)}
          />
        )}

        {step === 5 && (
          <TemplateStep
            form={templateForm}
            setForm={setTemplateForm}
            existingFields={props.fields}
            scopedSourceId={wizardSourceId}
            sources={props.sources}
            done={templateDone}
            busy={props.busy}
            readOnly={props.readOnly}
            onCreate={submitTemplate}
            onSkip={skipTemplate}
            onBack={() => setStep(4)}
            onRestart={restartWizard}
          />
        )}
      </Card>
    </>
  );
}

type SourceStepProps = {
  form: SourceForm;
  setForm: React.Dispatch<React.SetStateAction<SourceForm>>;
  existing: DataSource[];
  busy: boolean;
  readOnly: boolean;
  onCreate: () => void;
  onUseExisting: (id: string) => void;
};

function SourceStep(props: SourceStepProps) {
  return (
    <div className="wizardGrid">
      <div className="stackForm">
        <div className="wizardHelp">注册一个新的外部系统（Postgres / API / File）。提交后自动进入下一步。</div>
        <input placeholder="Data source name" value={props.form.name} onChange={(event) => props.setForm({ ...props.form, name: event.target.value })} disabled={props.readOnly} />
        <select value={props.form.sourceType} onChange={(event) => props.setForm({ ...props.form, sourceType: event.target.value })} disabled={props.readOnly}>
          <option value="postgres">PostgreSQL</option>
          <option value="api">API</option>
          <option value="file">File</option>
        </select>
        <input placeholder="Owner" value={props.form.owner} onChange={(event) => props.setForm({ ...props.form, owner: event.target.value })} disabled={props.readOnly} />
        <textarea placeholder="Description" value={props.form.description} onChange={(event) => props.setForm({ ...props.form, description: event.target.value })} disabled={props.readOnly} />
        <button className="primaryButton" disabled={props.busy || props.readOnly || !props.form.name.trim()} onClick={props.onCreate} type="button">
          <Plus size={15} /> 创建并继续
        </button>
      </div>
      <div className="wizardSide">
        <strong>已有数据源 ({props.existing.length})</strong>
        {props.existing.length ? (
          <div className="dataList">
            {props.existing.map((source) => (
              <button key={source.id} className="dataRow" disabled={props.readOnly} onClick={() => props.onUseExisting(source.id)} type="button">
                <span className="rowContent">
                  <strong>{source.name}</strong>
                  <span>{source.source_type} · {source.authority_level}</span>
                </span>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        ) : (
          <div className="emptyState">暂无数据源。先创建一个。</div>
        )}
      </div>
    </div>
  );
}

type ResourceStepProps = {
  form: ResourceForm;
  setForm: React.Dispatch<React.SetStateAction<ResourceForm>>;
  existing: DataResource[];
  scopedSourceId: string;
  sources: DataSource[];
  busy: boolean;
  readOnly: boolean;
  onCreate: () => void;
  onUseExisting: (id: string) => void;
  onBack: () => void;
};

function ResourceStep(props: ResourceStepProps) {
  const scopedSource = props.sources.find((item) => item.id === props.form.dataSourceId);
  const filtered = props.scopedSourceId
    ? props.existing.filter((item) => item.data_source_id === props.scopedSourceId)
    : props.existing;
  return (
    <div className="wizardGrid">
      <div className="stackForm">
        <div className="wizardHelp">
          {props.scopedSourceId
            ? <>绑定到上一步的数据源：<strong>{scopedSource?.name ?? props.form.dataSourceId}</strong></>
            : "选择一个已有数据源，或返回上一步创建。"}
        </div>
        <select value={props.form.dataSourceId} onChange={(event) => props.setForm({ ...props.form, dataSourceId: event.target.value })} disabled={props.readOnly}>
          <option value="">Select source</option>
          {props.sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
        </select>
        <input placeholder="Resource name, table, endpoint" value={props.form.name} onChange={(event) => props.setForm({ ...props.form, name: event.target.value })} disabled={props.readOnly} />
        <input placeholder="Resource type" value={props.form.resourceType} onChange={(event) => props.setForm({ ...props.form, resourceType: event.target.value })} disabled={props.readOnly} />
        <input placeholder="Owner" value={props.form.owner} onChange={(event) => props.setForm({ ...props.form, owner: event.target.value })} disabled={props.readOnly} />
        <div className="wizardActions">
          <button className="secondaryButton" onClick={props.onBack} type="button"><ArrowLeft size={15} /> 上一步</button>
          <button className="primaryButton" disabled={props.busy || props.readOnly || !props.form.dataSourceId || !props.form.name.trim()} onClick={props.onCreate} type="button">
            <Plus size={15} /> 创建并继续
          </button>
        </div>
      </div>
      <div className="wizardSide">
        <strong>该源的现有资源 ({filtered.length})</strong>
        {filtered.length ? (
          <div className="dataList">
            {filtered.map((resource) => (
              <button key={resource.id} className="dataRow" disabled={props.readOnly} onClick={() => props.onUseExisting(resource.id)} type="button">
                <span className="rowContent">
                  <strong>{resource.name}</strong>
                  <span>{resource.resource_type} · {resource.authority_level}</span>
                </span>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        ) : (
          <div className="emptyState">该源下尚无资源。</div>
        )}
      </div>
    </div>
  );
}

type FieldStepProps = {
  form: FieldForm;
  setForm: React.Dispatch<React.SetStateAction<FieldForm>>;
  existing: ExternalField[];
  scopedResourceId: string;
  resources: DataResource[];
  addedCount: number;
  busy: boolean;
  readOnly: boolean;
  onCreate: (advance: boolean) => void;
  onBack: () => void;
};

function FieldStep(props: FieldStepProps) {
  const scopedResource = props.resources.find((item) => item.id === props.form.dataResourceId);
  const loopRows = props.scopedResourceId
    ? props.existing.filter((item) => item.data_resource_id === props.scopedResourceId)
    : [];
  return (
    <div className="wizardGrid">
      <div className="stackForm">
        <div className="wizardHelp">
          {props.scopedResourceId
            ? <>绑定资源：<strong>{scopedResource?.name ?? props.form.dataResourceId}</strong>。可循环添加多个字段。</>
            : "选择一个资源，或返回上一步创建。"}
          {props.addedCount > 0 && <Tag color="green" className="wizardTag">本轮已加 {props.addedCount} 个字段</Tag>}
        </div>
        <select value={props.form.dataResourceId} onChange={(event) => props.setForm({ ...props.form, dataResourceId: event.target.value })} disabled={props.readOnly}>
          <option value="">Select resource</option>
          {props.resources.map((resource) => <option key={resource.id} value={resource.id}>{resource.name}</option>)}
        </select>
        <input placeholder="Field name" value={props.form.name} onChange={(event) => props.setForm({ ...props.form, name: event.target.value })} disabled={props.readOnly} />
        <input placeholder="Data type" value={props.form.dataType} onChange={(event) => props.setForm({ ...props.form, dataType: event.target.value })} disabled={props.readOnly} />
        <select value={props.form.sensitivity} onChange={(event) => props.setForm({ ...props.form, sensitivity: event.target.value as ExternalField["sensitivity"] })} disabled={props.readOnly}>
          <option value="public">public</option>
          <option value="internal">internal</option>
          <option value="confidential">confidential</option>
          <option value="restricted">restricted</option>
        </select>
        <select value={props.form.accessPolicy} onChange={(event) => props.setForm({ ...props.form, accessPolicy: event.target.value as ExternalField["access_policy"] })} disabled={props.readOnly}>
          <option value="allow">allow</option>
          <option value="mask">mask</option>
          <option value="approval_required">approval required</option>
          <option value="deny">deny</option>
        </select>
        <input placeholder="Masking rule" value={props.form.maskingRule} onChange={(event) => props.setForm({ ...props.form, maskingRule: event.target.value })} disabled={props.readOnly} />
        <div className="wizardActions">
          <button className="secondaryButton" onClick={props.onBack} type="button"><ArrowLeft size={15} /> 上一步</button>
          <button className="secondaryButton" disabled={props.busy || props.readOnly || !props.form.dataResourceId || !props.form.name.trim()} onClick={() => props.onCreate(false)} type="button">
            <Plus size={15} /> 保存并继续添加
          </button>
          <button className="primaryButton" disabled={props.busy || props.readOnly || !props.form.dataResourceId || !props.form.name.trim()} onClick={() => props.onCreate(true)} type="button">
            保存并下一步 <ArrowRight size={15} />
          </button>
        </div>
      </div>
      <div className="wizardSide">
        <strong>该资源已注册字段 ({loopRows.length})</strong>
        {loopRows.length ? (
          <div className="dataList">
            {loopRows.map((field) => (
              <div className="dataRow" key={field.id}>
                <span className="rowContent">
                  <strong>{field.name}</strong>
                  <span>{field.data_type} · {field.sensitivity} · {field.access_policy}</span>
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="emptyState">该资源尚无字段。</div>
        )}
      </div>
    </div>
  );
}

type MappingStepProps = {
  form: MappingForm;
  setForm: React.Dispatch<React.SetStateAction<MappingForm>>;
  existing: ExternalField[];
  targetOptions: Array<{ value: string; label: string }>;
  addedCount: number;
  busy: boolean;
  readOnly: boolean;
  onCreate: (advance: boolean) => void;
  onUseExistingField: (id: string) => void;
  onBack: () => void;
};

function MappingStep(props: MappingStepProps) {
  return (
    <div className="wizardGrid">
      <div className="stackForm">
        <div className="wizardHelp">
          将本体元素（实体 / 类 / 属性 / 关系类型）映射到外部字段。可循环添加多条。
          {props.addedCount > 0 && <Tag color="green" className="wizardTag">本轮已加 {props.addedCount} 条映射</Tag>}
        </div>
        <select value={props.form.targetType} onChange={(event) => props.setForm({ ...props.form, targetType: event.target.value as SemanticMapping["target_type"], targetId: "" })} disabled={props.readOnly}>
          <option value="entity">Entity</option>
          <option value="class">Class</option>
          <option value="property">Property</option>
          <option value="relation_type">RelationType</option>
        </select>
        <Select
          showSearch
          optionFilterProp="label"
          options={props.targetOptions}
          placeholder="Ontology target"
          value={props.form.targetId || undefined}
          onChange={(value) => props.setForm({ ...props.form, targetId: value })}
          disabled={props.readOnly}
        />
        <select value={props.form.fieldId} onChange={(event) => props.setForm({ ...props.form, fieldId: event.target.value })} disabled={props.readOnly}>
          <option value="">Select external field</option>
          {props.existing.map((field) => <option key={field.id} value={field.id}>{field.name} · {field.sensitivity}</option>)}
        </select>
        <textarea rows={5} value={props.form.joinKey} onChange={(event) => props.setForm({ ...props.form, joinKey: event.target.value })} disabled={props.readOnly} />
        <input placeholder="Owner" value={props.form.owner} onChange={(event) => props.setForm({ ...props.form, owner: event.target.value })} disabled={props.readOnly} />
        <div className="wizardActions">
          <button className="secondaryButton" onClick={props.onBack} type="button"><ArrowLeft size={15} /> 上一步</button>
          <button className="secondaryButton" disabled={props.busy || props.readOnly || !props.form.targetId || !props.form.fieldId} onClick={() => props.onCreate(false)} type="button">
            <Plus size={15} /> 保存并继续添加
          </button>
          <button className="primaryButton" disabled={props.busy || props.readOnly || !props.form.targetId || !props.form.fieldId} onClick={() => props.onCreate(true)} type="button">
            保存并下一步 <ArrowRight size={15} />
          </button>
        </div>
      </div>
      <div className="wizardSide">
        <strong>已有外部字段 ({props.existing.length})</strong>
        {props.existing.length ? (
          <div className="dataList">
            {props.existing.slice(0, 20).map((field) => (
              <button key={field.id} className="dataRow" disabled={props.readOnly} onClick={() => props.onUseExistingField(field.id)} type="button">
                <span className="rowContent">
                  <strong>{field.name}</strong>
                  <span>{field.data_type} · {field.sensitivity}</span>
                </span>
                <ArrowRight size={16} />
              </button>
            ))}
          </div>
        ) : (
          <div className="emptyState">尚无外部字段，请返回字段步骤创建。</div>
        )}
      </div>
    </div>
  );
}

type TemplateStepProps = {
  form: TemplateForm;
  setForm: React.Dispatch<React.SetStateAction<TemplateForm>>;
  existingFields: ExternalField[];
  scopedSourceId: string;
  sources: DataSource[];
  done: "pending" | "created" | "skipped";
  busy: boolean;
  readOnly: boolean;
  onCreate: () => void;
  onSkip: () => void;
  onBack: () => void;
  onRestart: () => void;
};

function TemplateStep(props: TemplateStepProps) {
  const scopedSource = props.sources.find((item) => item.id === props.form.dataSourceId);
  if (props.done !== "pending") {
    return (
      <div className="wizardDone">
        <CheckCircle2 size={36} />
        <div>
          <strong>{props.done === "created" ? "Connector 模板已创建" : "已跳过 Connector 模板"}</strong>
          <span>向导已完成。可在 Test 探测页运行受控查询，或重新开始一轮配置。</span>
        </div>
        <div className="wizardActions">
          <button className="secondaryButton" onClick={props.onBack} type="button"><ArrowLeft size={15} /> 返回映射</button>
          <button className="primaryButton" onClick={props.onRestart} type="button"><RefreshCw size={15} /> 开始新一轮</button>
        </div>
      </div>
    );
  }
  return (
    <div className="wizardGrid">
      <div className="stackForm">
        <div className="wizardHelp">
          {props.scopedSourceId
            ? <>为数据源 <strong>{scopedSource?.name ?? props.form.dataSourceId}</strong> 注册一个受控查询模板（可跳过）。</>
            : "选择已有数据源注册 Connector 模板；如不需要可直接跳过。"}
        </div>
        <select value={props.form.dataSourceId} onChange={(event) => props.setForm({ ...props.form, dataSourceId: event.target.value, allowedFieldIds: [] })} disabled={props.readOnly}>
          <option value="">Select source</option>
          {props.sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
        </select>
        <input placeholder="Template name" value={props.form.name} onChange={(event) => props.setForm({ ...props.form, name: event.target.value })} disabled={props.readOnly} />
        <Select
          mode="multiple"
          optionFilterProp="label"
          options={props.existingFields
            .filter((field) => !props.form.dataSourceId || field.data_source_id === props.form.dataSourceId)
            .map((field) => ({ value: field.id, label: `${field.name} · ${field.access_policy}` }))}
          placeholder="Allowed fields"
          value={props.form.allowedFieldIds}
          onChange={(value) => props.setForm({ ...props.form, allowedFieldIds: value })}
          disabled={props.readOnly}
        />
        <select value={props.form.accessPolicy} onChange={(event) => props.setForm({ ...props.form, accessPolicy: event.target.value as ConnectorTemplate["access_policy"] })} disabled={props.readOnly}>
          <option value="allow">allow</option>
          <option value="approval_required">approval required</option>
          <option value="deny">deny</option>
        </select>
        <textarea rows={5} value={props.form.resultRows} onChange={(event) => props.setForm({ ...props.form, resultRows: event.target.value })} disabled={props.readOnly} />
        <div className="wizardActions">
          <button className="secondaryButton" onClick={props.onBack} type="button"><ArrowLeft size={15} /> 上一步</button>
          <button className="secondaryButton" onClick={props.onSkip} type="button"><SkipForward size={15} /> 跳过</button>
          <button className="primaryButton" disabled={props.busy || props.readOnly || !props.form.dataSourceId || !props.form.name.trim()} onClick={props.onCreate} type="button">
            <Plus size={15} /> 创建模板
          </button>
        </div>
      </div>
      <div className="wizardSide">
        <strong>当前源可选字段</strong>
        <FieldAllowList fields={props.existingFields} sourceId={props.form.dataSourceId} />
      </div>
    </div>
  );
}

function FieldAllowList(props: { fields: ExternalField[]; sourceId: string }) {
  const filtered = props.sourceId ? props.fields.filter((field) => field.data_source_id === props.sourceId) : props.fields;
  if (!filtered.length) return <div className="emptyState">所选源下暂无字段。</div>;
  return (
    <div className="dataList">
      {filtered.slice(0, 20).map((field) => (
        <div className="dataRow" key={field.id}>
          <span className="rowContent">
            <strong>{field.name}</strong>
            <span>{field.data_type} · {field.access_policy}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

type CatalogTestProps = {
  projectId: string;
  templates: ConnectorTemplate[];
  request: WorkbenchRequest;
  run: (action: () => Promise<void>) => Promise<void>;
  busy: boolean;
};

function CatalogTest(props: CatalogTestProps) {
  const [queryTemplateId, setQueryTemplateId] = useState("");
  const [queryParams, setQueryParams] = useState('{"student_number": "S1"}');
  const [queryApproved, setQueryApproved] = useState(false);
  const [queryResult, setQueryResult] = useState<ConnectorQueryResult | null>(null);
  const [leftIds, setLeftIds] = useState("S1, S2, S3");
  const [rightIds, setRightIds] = useState("S2, S3, S4");
  const [resolutionStats, setResolutionStats] = useState<IdentifierResolutionStats | null>(null);

  useEffect(() => {
    setQueryTemplateId((current) => current || props.templates[0]?.id || "");
  }, [props.templates]);

  function parseObject(text: string): JsonObject {
    const value = JSON.parse(text) as unknown;
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("JSON must be an object");
    return value as JsonObject;
  }

  function runConnectorQuery() {
    void props.run(async () => {
      const result = await props.request<ConnectorQueryResult>(
        `/projects/${props.projectId}/connector-templates/${queryTemplateId}/query`,
        {
          method: "POST",
          body: JSON.stringify({
            parameters: parseObject(queryParams),
            actor_id: "workbench",
            approved: queryApproved,
          }),
        },
      );
      setQueryResult(result);
    });
  }

  function analyzeResolution() {
    void props.run(async () => {
      const result = await props.request<IdentifierResolutionStats>(
        `/projects/${props.projectId}/identity-resolution/analyze`,
        {
          method: "POST",
          body: JSON.stringify({
            left_values: splitCsv(leftIds),
            right_values: splitCsv(rightIds),
          }),
        },
      );
      setResolutionStats(result);
    });
  }

  return (
    <div className="catalogGrid two">
      <Card className="panel" title="Governed connector query">
        <div className="stackForm">
          <select value={queryTemplateId} onChange={(event) => setQueryTemplateId(event.target.value)}>
            <option value="">Select template</option>
            {props.templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}
          </select>
          <textarea rows={4} value={queryParams} onChange={(event) => setQueryParams(event.target.value)} />
          <label className="inlineCheck"><input checked={queryApproved} onChange={(event) => setQueryApproved(event.target.checked)} type="checkbox" /> Approval granted</label>
          <button className="primaryButton" disabled={props.busy || !queryTemplateId} onClick={runConnectorQuery} type="button"><Play size={15} /> Run template</button>
        </div>
        {queryResult && <ConnectorResult result={queryResult} />}
      </Card>

      <Card className="panel" title="Identifier resolution analysis">
        <div className="stackForm">
          <textarea rows={3} value={leftIds} onChange={(event) => setLeftIds(event.target.value)} />
          <textarea rows={3} value={rightIds} onChange={(event) => setRightIds(event.target.value)} />
          <button className="secondaryButton" disabled={props.busy} onClick={analyzeResolution} type="button"><Route size={15} /> Analyze overlap</button>
        </div>
        {resolutionStats && <pre className="jsonBlock">{prettyJson(resolutionStats)}</pre>}
      </Card>
    </div>
  );
}

function Metric(props: { icon: React.ReactNode; label: string; value: number }) {
  return <div className="catalogMetric">{props.icon}<strong>{props.value}</strong><span>{props.label}</span></div>;
}

function RecordItem(props: { title: string; meta: string; tag: string }) {
  return <div className="catalogRecord"><strong>{props.title}</strong><span>{props.meta}</span><Tag>{props.tag}</Tag></div>;
}

function ConnectorResult(props: { result: ConnectorQueryResult }) {
  return (
    <div className="connectorResult">
      <div className="connectorState">
        <Tag color={props.result.authorized ? "green" : "red"}>{props.result.authorized ? "authorized" : "denied"}</Tag>
        <span>{props.result.denial_reason ?? `${props.result.rows.length} row(s)`}</span>
      </div>
      <pre className="jsonBlock">{prettyJson({ source: props.result.source, audit: props.result.audit, rows: props.result.rows })}</pre>
    </div>
  );
}

function classNames(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}
