import React, { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  Activity,
  Box,
  Braces,
  Database,
  GitBranch,
  Layers,
  Link2,
  Network,
  Play,
  Plus,
  RefreshCw,
  Send,
  Server,
  Settings,
  Shield,
  Trash2,
  Waypoints,
} from "lucide-react";
import "./styles.css";

declare global {
  interface ImportMetaEnv {
    readonly VITE_API_BASE_URL?: string;
  }

  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api").replace(/\/$/, "");
const TOKEN_KEY = "ontology-platform-admin-token";

type Tab = "projects" | "designer" | "graph" | "agent" | "health";
type JsonObject = Record<string, unknown>;

type Project = {
  id: string;
  name: string;
  description: string | null;
  created_at?: string;
  updated_at?: string;
};

type Ontology = {
  id: string;
  project_id: string;
  current_version_id: string | null;
  name: string;
  description: string | null;
  status: string;
};

type ClassDef = {
  id: string;
  ontology_id: string;
  name: string;
  normalized_label?: string;
  description: string | null;
  aliases: string[];
  parent_class_ids: string[];
};

type PropertyDef = {
  id: string;
  class_id: string;
  name: string;
  type: string;
  description: string | null;
  required: boolean;
  multi_valued: boolean;
  enum_values: string[];
};

type RelationType = {
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
};

type Entity = {
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

type Relation = {
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

type Health = Record<string, unknown>;
type Notice = { kind: "ok" | "error"; message: string } | null;

const propertyTypes = ["string", "number", "boolean", "date", "enum", "reference", "json"] as const;

function classNames(...names: Array<string | false | null | undefined>) {
  return names.filter(Boolean).join(" ");
}

function splitCsv(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseJsonObject(value: string): JsonObject {
  if (!value.trim()) return {};
  const parsed = JSON.parse(value);
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("JSON must be an object");
  }
  return parsed as JsonObject;
}

function compactId(id: string) {
  return id.length > 10 ? `${id.slice(0, 8)}...` : id;
}

function nameFor<T extends { id: string; name?: string }>(items: T[], id: string | null | undefined) {
  if (!id) return "None";
  return items.find((item) => item.id === id)?.name ?? compactId(id);
}

function ErrorText({ message }: { message?: string | null }) {
  if (!message) return null;
  return <div className="inlineError">{message}</div>;
}

async function apiRequest<T>(path: string, token: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token.trim()) headers.set("Authorization", `Bearer ${token.trim()}`);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  const text = await response.text();
  let payload: unknown = null;

  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? JSON.stringify((payload as { detail: unknown }).detail)
        : typeof payload === "string"
          ? payload
          : response.statusText;
    throw new Error(`${response.status} ${detail}`);
  }

  return payload as T;
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? "");
  const [tab, setTab] = useState<Tab>("projects");
  const [projects, setProjects] = useState<Project[]>([]);
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [classes, setClasses] = useState<ClassDef[]>([]);
  const [propertiesByClass, setPropertiesByClass] = useState<Record<string, PropertyDef[]>>({});
  const [relationTypes, setRelationTypes] = useState<RelationType[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedOntologyId, setSelectedOntologyId] = useState("");
  const [selectedClassId, setSelectedClassId] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const selectedOntology = ontologies.find((ontology) => ontology.id === selectedOntologyId) ?? null;
  const selectedClass = classes.find((classDef) => classDef.id === selectedClassId) ?? null;

  const request = useCallback(
    <T,>(path: string, options?: RequestInit) => apiRequest<T>(path, token, options),
    [token],
  );

  function saveToken(value: string) {
    setToken(value);
    localStorage.setItem(TOKEN_KEY, value);
  }

  const showError = useCallback((error: unknown) => {
    setNotice({ kind: "error", message: error instanceof Error ? error.message : String(error) });
  }, []);

  const loadProjects = useCallback(async () => {
    const data = await request<Project[]>("/projects");
    setProjects(data);
    setSelectedProjectId((current) =>
      current && data.some((project) => project.id === current) ? current : data[0]?.id || "",
    );
  }, [request]);

  const loadOntologies = useCallback(
    async (projectId = selectedProjectId) => {
      if (!projectId) {
        setOntologies([]);
        setSelectedOntologyId("");
        return;
      }
      const data = await request<Ontology[]>(`/projects/${projectId}/ontologies`);
      setOntologies(data);
      setSelectedOntologyId((current) =>
        current && data.some((ontology) => ontology.id === current) ? current : data[0]?.id || "",
      );
    },
    [request, selectedProjectId],
  );

  const loadSchema = useCallback(
    async (ontologyId = selectedOntologyId) => {
      if (!ontologyId) {
        setClasses([]);
        setPropertiesByClass({});
        setRelationTypes([]);
        setSelectedClassId("");
        return;
      }
      const [classData, relationTypeData] = await Promise.all([
        request<ClassDef[]>(`/ontologies/${ontologyId}/classes`),
        request<RelationType[]>(`/ontologies/${ontologyId}/relation-types`),
      ]);
      const propertyPairs = await Promise.all(
        classData.map(async (classDef) => [classDef.id, await request<PropertyDef[]>(`/classes/${classDef.id}/properties`)] as const),
      );
      setClasses(classData);
      setPropertiesByClass(Object.fromEntries(propertyPairs));
      setRelationTypes(relationTypeData);
      setSelectedClassId((current) =>
        current && classData.some((classDef) => classDef.id === current) ? current : classData[0]?.id || "",
      );
    },
    [request, selectedOntologyId],
  );

  const loadGraph = useCallback(
    async (ontologyId = selectedOntologyId) => {
      if (!ontologyId) {
        setEntities([]);
        setRelations([]);
        return;
      }
      const [entityData, relationData] = await Promise.all([
        request<Entity[]>(`/ontologies/${ontologyId}/entities?limit=200`),
        request<Relation[]>(`/ontologies/${ontologyId}/relations?limit=200`),
      ]);
      setEntities(entityData);
      setRelations(relationData);
    },
    [request, selectedOntologyId],
  );

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setNotice(null);
    try {
      await loadProjects();
    } catch (error) {
      showError(error);
    } finally {
      setLoading(false);
    }
  }, [loadProjects, showError]);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  useEffect(() => {
    loadOntologies().catch(showError);
  }, [selectedProjectId, loadOntologies, showError]);

  useEffect(() => {
    Promise.all([loadSchema(), loadGraph()]).catch(showError);
  }, [selectedOntologyId, loadSchema, loadGraph, showError]);

  async function mutate(action: () => Promise<void>, success: string) {
    setLoading(true);
    setNotice(null);
    try {
      await action();
      setNotice({ kind: "ok", message: success });
    } catch (error) {
      showError(error);
    } finally {
      setLoading(false);
    }
  }

  const tabs = [
    { id: "projects" as const, label: "Projects", icon: Layers },
    { id: "designer" as const, label: "Ontology Designer", icon: Waypoints },
    { id: "graph" as const, label: "Graph Manager", icon: Network },
    { id: "agent" as const, label: "MCP/Agent Test", icon: Send },
    { id: "health" as const, label: "Health", icon: Activity },
  ];

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Network size={22} />
          <span>Ontology Platform</span>
        </div>
        <nav>
          {tabs.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={classNames("navItem", tab === item.id && "active")}
                onClick={() => setTab(item.id)}
                type="button"
              >
                <Icon size={16} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <h1>{tabs.find((item) => item.id === tab)?.label}</h1>
            <div className="crumbs">
              <span>{selectedProject?.name ?? "No project"}</span>
              <span>{selectedOntology?.name ?? "No ontology"}</span>
              <span>{API_BASE_URL}</span>
            </div>
          </div>
          <div className="topActions">
            <label className="tokenField">
              <Shield size={15} />
              <input
                value={token}
                onChange={(event) => saveToken(event.target.value)}
                placeholder="Admin token"
                type="password"
              />
            </label>
            <button className="iconButton" disabled={loading} onClick={refreshAll} title="Refresh" type="button">
              <RefreshCw size={17} />
            </button>
          </div>
        </header>

        {notice && <div className={classNames("notice", notice.kind)}>{notice.message}</div>}

        <ContextBar
          ontologies={ontologies}
          projects={projects}
          selectedOntologyId={selectedOntologyId}
          selectedProjectId={selectedProjectId}
          setSelectedOntologyId={setSelectedOntologyId}
          setSelectedProjectId={setSelectedProjectId}
        />

        {tab === "projects" && (
          <ProjectsPage
            mutate={mutate}
            ontologies={ontologies}
            projects={projects}
            request={request}
            selectedProjectId={selectedProjectId}
            setSelectedOntologyId={setSelectedOntologyId}
            setSelectedProjectId={setSelectedProjectId}
            reloadOntologies={loadOntologies}
            reloadProjects={loadProjects}
          />
        )}
        {tab === "designer" && (
          <DesignerPage
            classes={classes}
            mutate={mutate}
            ontologyId={selectedOntologyId}
            propertiesByClass={propertiesByClass}
            relationTypes={relationTypes}
            request={request}
            selectedClassId={selectedClassId}
            setSelectedClassId={setSelectedClassId}
            reloadSchema={loadSchema}
          />
        )}
        {tab === "graph" && (
          <GraphPage
            classes={classes}
            entities={entities}
            mutate={mutate}
            ontologyId={selectedOntologyId}
            relationTypes={relationTypes}
            relations={relations}
            request={request}
            reloadGraph={loadGraph}
          />
        )}
        {tab === "agent" && <AgentPage ontology={selectedOntology} project={selectedProject} request={request} mutate={mutate} />}
        {tab === "health" && <HealthPage health={health} request={request} setHealth={setHealth} showError={showError} />}

        {tab !== "projects" && !selectedOntology && (
          <section className="emptyState">
            <Database size={24} />
            <span>Select or create a project and ontology before using this workspace.</span>
          </section>
        )}
        {selectedClass && <span className="srOnly">{selectedClass.name}</span>}
      </section>
    </main>
  );
}

function ContextBar(props: {
  projects: Project[];
  ontologies: Ontology[];
  selectedProjectId: string;
  selectedOntologyId: string;
  setSelectedProjectId: (id: string) => void;
  setSelectedOntologyId: (id: string) => void;
}) {
  return (
    <section className="contextBar">
      <label>
        Project
        <select value={props.selectedProjectId} onChange={(event) => props.setSelectedProjectId(event.target.value)}>
          <option value="">Select project</option>
          {props.projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Ontology
        <select value={props.selectedOntologyId} onChange={(event) => props.setSelectedOntologyId(event.target.value)}>
          <option value="">Select ontology</option>
          {props.ontologies.map((ontology) => (
            <option key={ontology.id} value={ontology.id}>
              {ontology.name}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}

function ProjectsPage(props: {
  projects: Project[];
  ontologies: Ontology[];
  selectedProjectId: string;
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadProjects: () => Promise<void>;
  reloadOntologies: (projectId?: string) => Promise<void>;
  setSelectedProjectId: (id: string) => void;
  setSelectedOntologyId: (id: string) => void;
}) {
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [ontologyName, setOntologyName] = useState("");
  const [ontologyDescription, setOntologyDescription] = useState("");

  function createProject(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const created = await props.request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name: projectName, description: projectDescription || null }),
      });
      setProjectName("");
      setProjectDescription("");
      props.setSelectedProjectId(created.id);
      await props.reloadProjects();
    }, "Project created");
  }

  function createOntology(event: FormEvent) {
    event.preventDefault();
    if (!props.selectedProjectId) return;
    props.mutate(async () => {
      const created = await props.request<Ontology>(`/projects/${props.selectedProjectId}/ontologies`, {
        method: "POST",
        body: JSON.stringify({ name: ontologyName, description: ontologyDescription || null, external_mappings: {} }),
      });
      setOntologyName("");
      setOntologyDescription("");
      props.setSelectedOntologyId(created.id);
      await props.reloadOntologies(props.selectedProjectId);
    }, "Ontology created");
  }

  return (
    <section className="twoColumn">
      <Panel title="Projects" icon={<Layers size={17} />}>
        <form className="inlineForm" onSubmit={createProject}>
          <input required value={projectName} onChange={(event) => setProjectName(event.target.value)} placeholder="Project name" />
          <input value={projectDescription} onChange={(event) => setProjectDescription(event.target.value)} placeholder="Description" />
          <button className="primaryButton" type="submit">
            <Plus size={16} /> Create
          </button>
        </form>
        <div className="listTable">
          {props.projects.map((project) => (
            <div className={classNames("row", project.id === props.selectedProjectId && "selected")} key={project.id}>
              <button className="rowMain" onClick={() => props.setSelectedProjectId(project.id)} type="button">
                <strong>{project.name}</strong>
                <span>{project.description || compactId(project.id)}</span>
              </button>
              <button
                className="iconButton danger"
                onClick={() =>
                  props.mutate(async () => {
                    await props.request<void>(`/projects/${project.id}`, { method: "DELETE" });
                    await props.reloadProjects();
                  }, "Project deleted")
                }
                title="Delete project"
                type="button"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Ontologies" icon={<Waypoints size={17} />}>
        <form className="inlineForm" onSubmit={createOntology}>
          <input required value={ontologyName} onChange={(event) => setOntologyName(event.target.value)} placeholder="Ontology name" />
          <input
            value={ontologyDescription}
            onChange={(event) => setOntologyDescription(event.target.value)}
            placeholder="Description"
          />
          <button className="primaryButton" disabled={!props.selectedProjectId} type="submit">
            <Plus size={16} /> Create
          </button>
        </form>
        <div className="listTable">
          {props.ontologies.map((ontology) => (
            <div className="row" key={ontology.id}>
              <button className="rowMain" onClick={() => props.setSelectedOntologyId(ontology.id)} type="button">
                <strong>{ontology.name}</strong>
                <span>{ontology.status} - {ontology.description || compactId(ontology.id)}</span>
              </button>
              <button
                className="iconButton danger"
                onClick={() =>
                  props.mutate(async () => {
                    await props.request<void>(`/ontologies/${ontology.id}`, { method: "DELETE" });
                    await props.reloadOntologies(props.selectedProjectId);
                  }, "Ontology deleted")
                }
                title="Delete ontology"
                type="button"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </Panel>
    </section>
  );
}

function DesignerPage(props: {
  ontologyId: string;
  classes: ClassDef[];
  relationTypes: RelationType[];
  propertiesByClass: Record<string, PropertyDef[]>;
  selectedClassId: string;
  setSelectedClassId: (id: string) => void;
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadSchema: () => Promise<void>;
}) {
  const [classForm, setClassForm] = useState({ name: "", description: "", aliases: "", parents: [] as string[] });
  const [propertyForm, setPropertyForm] = useState({
    name: "",
    type: "string",
    description: "",
    required: false,
    multiValued: false,
    enumValues: "",
  });
  const [relationTypeForm, setRelationTypeForm] = useState({
    name: "",
    description: "",
    sourceClassId: "",
    targetClassId: "",
    inverseName: "",
  });

  useEffect(() => {
    if (!relationTypeForm.sourceClassId && props.classes[0]) {
      setRelationTypeForm((current) => ({ ...current, sourceClassId: props.classes[0].id, targetClassId: props.classes[0].id }));
    }
  }, [props.classes, relationTypeForm.sourceClassId]);

  function createClass(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const created = await props.request<ClassDef>(`/ontologies/${props.ontologyId}/classes`, {
        method: "POST",
        body: JSON.stringify({
          name: classForm.name,
          description: classForm.description || null,
          aliases: splitCsv(classForm.aliases),
          parent_class_ids: classForm.parents,
          external_mappings: {},
        }),
      });
      setClassForm({ name: "", description: "", aliases: "", parents: [] });
      props.setSelectedClassId(created.id);
      await props.reloadSchema();
    }, "Class created");
  }

  function createProperty(event: FormEvent) {
    event.preventDefault();
    if (!props.selectedClassId) return;
    props.mutate(async () => {
      await props.request<PropertyDef>(`/classes/${props.selectedClassId}/properties`, {
        method: "POST",
        body: JSON.stringify({
          name: propertyForm.name,
          type: propertyForm.type,
          description: propertyForm.description || null,
          required: propertyForm.required,
          multi_valued: propertyForm.multiValued,
          enum_values: splitCsv(propertyForm.enumValues),
          constraints: {},
          external_mappings: {},
        }),
      });
      setPropertyForm({ name: "", type: "string", description: "", required: false, multiValued: false, enumValues: "" });
      await props.reloadSchema();
    }, "Property created");
  }

  function createRelationType(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      await props.request<RelationType>(`/ontologies/${props.ontologyId}/relation-types`, {
        method: "POST",
        body: JSON.stringify({
          name: relationTypeForm.name,
          description: relationTypeForm.description || null,
          aliases: [],
          parent_relation_type_id: null,
          source_class_id: relationTypeForm.sourceClassId,
          target_class_id: relationTypeForm.targetClassId,
          inverse_name: relationTypeForm.inverseName || null,
          external_mappings: {},
        }),
      });
      setRelationTypeForm((current) => ({ ...current, name: "", description: "", inverseName: "" }));
      await props.reloadSchema();
    }, "Relation type created");
  }

  return (
    <section className="designerGrid">
      <Panel title="Classes" icon={<Box size={17} />}>
        <form className="stackForm" onSubmit={createClass}>
          <input required value={classForm.name} onChange={(event) => setClassForm({ ...classForm, name: event.target.value })} placeholder="Class name" />
          <input
            value={classForm.description}
            onChange={(event) => setClassForm({ ...classForm, description: event.target.value })}
            placeholder="Description"
          />
          <input
            value={classForm.aliases}
            onChange={(event) => setClassForm({ ...classForm, aliases: event.target.value })}
            placeholder="Aliases, comma separated"
          />
          <select
            multiple
            value={classForm.parents}
            onChange={(event) =>
              setClassForm({ ...classForm, parents: Array.from(event.currentTarget.selectedOptions).map((option) => option.value) })
            }
          >
            {props.classes.map((classDef) => (
              <option key={classDef.id} value={classDef.id}>
                {classDef.name}
              </option>
            ))}
          </select>
          <button className="primaryButton" disabled={!props.ontologyId} type="submit">
            <Plus size={16} /> Add class
          </button>
        </form>
        <div className="listTable compact">
          {props.classes.map((classDef) => (
            <div className={classNames("row", classDef.id === props.selectedClassId && "selected")} key={classDef.id}>
              <button className="rowMain" onClick={() => props.setSelectedClassId(classDef.id)} type="button">
                <strong>{classDef.name}</strong>
                <span>{classDef.normalized_label ?? compactId(classDef.id)}</span>
              </button>
              <button
                className="iconButton danger"
                onClick={() =>
                  props.mutate(async () => {
                    await props.request<void>(`/classes/${classDef.id}`, { method: "DELETE" });
                    await props.reloadSchema();
                  }, "Class deleted")
                }
                title="Delete class"
                type="button"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Properties" icon={<Braces size={17} />}>
        <form className="stackForm" onSubmit={createProperty}>
          <select value={props.selectedClassId} onChange={(event) => props.setSelectedClassId(event.target.value)}>
            <option value="">Class</option>
            {props.classes.map((classDef) => (
              <option key={classDef.id} value={classDef.id}>
                {classDef.name}
              </option>
            ))}
          </select>
          <input
            required
            value={propertyForm.name}
            onChange={(event) => setPropertyForm({ ...propertyForm, name: event.target.value })}
            placeholder="Property name"
          />
          <select value={propertyForm.type} onChange={(event) => setPropertyForm({ ...propertyForm, type: event.target.value })}>
            {propertyTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <input
            value={propertyForm.enumValues}
            onChange={(event) => setPropertyForm({ ...propertyForm, enumValues: event.target.value })}
            placeholder="Enum values, comma separated"
          />
          <div className="checkRow">
            <label>
              <input
                checked={propertyForm.required}
                onChange={(event) => setPropertyForm({ ...propertyForm, required: event.target.checked })}
                type="checkbox"
              />
              Required
            </label>
            <label>
              <input
                checked={propertyForm.multiValued}
                onChange={(event) => setPropertyForm({ ...propertyForm, multiValued: event.target.checked })}
                type="checkbox"
              />
              Multi
            </label>
          </div>
          <button className="primaryButton" disabled={!props.selectedClassId} type="submit">
            <Plus size={16} /> Add property
          </button>
        </form>
        <div className="listTable compact">
          {(props.propertiesByClass[props.selectedClassId] ?? []).map((property) => (
            <div className="row" key={property.id}>
              <div className="rowMain static">
                <strong>{property.name}</strong>
                <span>{property.type}{property.required ? " - required" : ""}{property.multi_valued ? " - multi" : ""}</span>
              </div>
              <button
                className="iconButton danger"
                onClick={() =>
                  props.mutate(async () => {
                    await props.request<void>(`/properties/${property.id}`, { method: "DELETE" });
                    await props.reloadSchema();
                  }, "Property deleted")
                }
                title="Delete property"
                type="button"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Relation Types" icon={<GitBranch size={17} />}>
        <form className="stackForm" onSubmit={createRelationType}>
          <input
            required
            value={relationTypeForm.name}
            onChange={(event) => setRelationTypeForm({ ...relationTypeForm, name: event.target.value })}
            placeholder="Relation type name"
          />
          <select
            required
            value={relationTypeForm.sourceClassId}
            onChange={(event) => setRelationTypeForm({ ...relationTypeForm, sourceClassId: event.target.value })}
          >
            <option value="">Source class</option>
            {props.classes.map((classDef) => (
              <option key={classDef.id} value={classDef.id}>
                {classDef.name}
              </option>
            ))}
          </select>
          <select
            required
            value={relationTypeForm.targetClassId}
            onChange={(event) => setRelationTypeForm({ ...relationTypeForm, targetClassId: event.target.value })}
          >
            <option value="">Target class</option>
            {props.classes.map((classDef) => (
              <option key={classDef.id} value={classDef.id}>
                {classDef.name}
              </option>
            ))}
          </select>
          <input
            value={relationTypeForm.inverseName}
            onChange={(event) => setRelationTypeForm({ ...relationTypeForm, inverseName: event.target.value })}
            placeholder="Inverse name"
          />
          <button className="primaryButton" disabled={!props.ontologyId || props.classes.length < 1} type="submit">
            <Plus size={16} /> Add relation type
          </button>
        </form>
        <div className="listTable compact">
          {props.relationTypes.map((relationType) => (
            <div className="row" key={relationType.id}>
              <div className="rowMain static">
                <strong>{relationType.name}</strong>
                <span>
                  {nameFor(props.classes, relationType.source_class_id)}
                  {" -> "}
                  {nameFor(props.classes, relationType.target_class_id)}
                </span>
              </div>
              <button
                className="iconButton danger"
                onClick={() =>
                  props.mutate(async () => {
                    await props.request<void>(`/relation-types/${relationType.id}`, { method: "DELETE" });
                    await props.reloadSchema();
                  }, "Relation type deleted")
                }
                title="Delete relation type"
                type="button"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      </Panel>
    </section>
  );
}

function GraphPage(props: {
  ontologyId: string;
  classes: ClassDef[];
  relationTypes: RelationType[];
  entities: Entity[];
  relations: Relation[];
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadGraph: () => Promise<void>;
}) {
  const [entityForm, setEntityForm] = useState({ name: "", classId: "", aliases: "", properties: "{}" });
  const [relationForm, setRelationForm] = useState({ relationTypeId: "", sourceEntityId: "", targetEntityId: "", properties: "{}" });
  const [entityJsonError, setEntityJsonError] = useState("");
  const [relationJsonError, setRelationJsonError] = useState("");

  useEffect(() => {
    if (!entityForm.classId && props.classes[0]) setEntityForm((current) => ({ ...current, classId: props.classes[0].id }));
  }, [props.classes, entityForm.classId]);

  useEffect(() => {
    if (!relationForm.relationTypeId && props.relationTypes[0]) {
      setRelationForm((current) => ({ ...current, relationTypeId: props.relationTypes[0].id }));
    }
  }, [props.relationTypes, relationForm.relationTypeId]);

  function createEntity(event: FormEvent) {
    event.preventDefault();
    setEntityJsonError("");
    props.mutate(async () => {
      let properties: JsonObject;
      try {
        properties = parseJsonObject(entityForm.properties);
      } catch (error) {
        setEntityJsonError(error instanceof Error ? error.message : String(error));
        throw error;
      }
      await props.request<Entity>(`/ontologies/${props.ontologyId}/entities`, {
        method: "POST",
        body: JSON.stringify({
          name: entityForm.name,
          class_id: entityForm.classId,
          aliases: splitCsv(entityForm.aliases),
          properties,
        }),
      });
      setEntityForm((current) => ({ ...current, name: "", aliases: "", properties: "{}" }));
      await props.reloadGraph();
    }, "Entity created");
  }

  function createRelation(event: FormEvent) {
    event.preventDefault();
    setRelationJsonError("");
    props.mutate(async () => {
      let properties: JsonObject;
      try {
        properties = parseJsonObject(relationForm.properties);
      } catch (error) {
        setRelationJsonError(error instanceof Error ? error.message : String(error));
        throw error;
      }
      await props.request<Relation>(`/ontologies/${props.ontologyId}/relations`, {
        method: "POST",
        body: JSON.stringify({
          relation_type_id: relationForm.relationTypeId,
          source_entity_id: relationForm.sourceEntityId,
          target_entity_id: relationForm.targetEntityId,
          properties,
        }),
      });
      setRelationForm((current) => ({ ...current, properties: "{}" }));
      await props.reloadGraph();
    }, "Relation created");
  }

  return (
    <section className="graphGrid">
      <Panel title="Entities" icon={<Database size={17} />}>
        <form className="stackForm" onSubmit={createEntity}>
          <input required value={entityForm.name} onChange={(event) => setEntityForm({ ...entityForm, name: event.target.value })} placeholder="Entity name" />
          <select required value={entityForm.classId} onChange={(event) => setEntityForm({ ...entityForm, classId: event.target.value })}>
            <option value="">Class</option>
            {props.classes.map((classDef) => (
              <option key={classDef.id} value={classDef.id}>
                {classDef.name}
              </option>
            ))}
          </select>
          <input value={entityForm.aliases} onChange={(event) => setEntityForm({ ...entityForm, aliases: event.target.value })} placeholder="Aliases" />
          <textarea value={entityForm.properties} onChange={(event) => setEntityForm({ ...entityForm, properties: event.target.value })} />
          <ErrorText message={entityJsonError} />
          <button className="primaryButton" disabled={!props.ontologyId || !props.classes.length} type="submit">
            <Plus size={16} /> Add entity
          </button>
        </form>
        <DataTable
          rows={props.entities.map((entity) => ({
            id: entity.id,
            first: entity.name,
            second: entity.class_label,
            meta: JSON.stringify(entity.properties),
          }))}
        />
      </Panel>

      <Panel title="Relations" icon={<Link2 size={17} />}>
        <form className="stackForm" onSubmit={createRelation}>
          <select
            required
            value={relationForm.relationTypeId}
            onChange={(event) => setRelationForm({ ...relationForm, relationTypeId: event.target.value })}
          >
            <option value="">Relation type</option>
            {props.relationTypes.map((relationType) => (
              <option key={relationType.id} value={relationType.id}>
                {relationType.name}
              </option>
            ))}
          </select>
          <select
            required
            value={relationForm.sourceEntityId}
            onChange={(event) => setRelationForm({ ...relationForm, sourceEntityId: event.target.value })}
          >
            <option value="">Source entity</option>
            {props.entities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
              </option>
            ))}
          </select>
          <select
            required
            value={relationForm.targetEntityId}
            onChange={(event) => setRelationForm({ ...relationForm, targetEntityId: event.target.value })}
          >
            <option value="">Target entity</option>
            {props.entities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
              </option>
            ))}
          </select>
          <textarea value={relationForm.properties} onChange={(event) => setRelationForm({ ...relationForm, properties: event.target.value })} />
          <ErrorText message={relationJsonError} />
          <button className="primaryButton" disabled={!props.ontologyId || props.entities.length < 2 || !props.relationTypes.length} type="submit">
            <Plus size={16} /> Add relation
          </button>
        </form>
        <DataTable
          rows={props.relations.map((relation) => ({
            id: relation.id,
            first: relation.relation_type,
            second: `${nameFor(props.entities, relation.source_entity_id)} -> ${nameFor(props.entities, relation.target_entity_id)}`,
            meta: JSON.stringify(relation.properties),
          }))}
        />
      </Panel>

      <Panel title="Graph View" icon={<Network size={17} />} wide>
        <GraphSvg entities={props.entities} relations={props.relations} relationTypes={props.relationTypes} />
      </Panel>
    </section>
  );
}

function GraphSvg({ entities, relations, relationTypes }: { entities: Entity[]; relations: Relation[]; relationTypes: RelationType[] }) {
  const nodes = useMemo(() => {
    const count = Math.max(entities.length, 1);
    return entities.map((entity, index) => {
      const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
      return {
        entity,
        x: 320 + Math.cos(angle) * 230,
        y: 205 + Math.sin(angle) * 145,
      };
    });
  }, [entities]);
  const byId = new Map(nodes.map((node) => [node.entity.id, node]));

  if (!entities.length) {
    return <div className="emptyGraph">No entities to render.</div>;
  }

  return (
    <svg className="graphSvg" viewBox="0 0 640 410" role="img" aria-label="Knowledge graph">
      <defs>
        <marker id="arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
          <path d="M0,0 L8,4 L0,8 Z" fill="#49656f" />
        </marker>
      </defs>
      {relations.map((relation) => {
        const source = byId.get(relation.source_entity_id);
        const target = byId.get(relation.target_entity_id);
        if (!source || !target) return null;
        const label = relationTypes.find((item) => item.id === relation.relation_type_id)?.name ?? relation.relation_type;
        const midX = (source.x + target.x) / 2;
        const midY = (source.y + target.y) / 2;
        return (
          <g key={relation.id}>
            <line className="edge" markerEnd="url(#arrow)" x1={source.x} x2={target.x} y1={source.y} y2={target.y} />
            <text className="edgeLabel" x={midX} y={midY - 6}>
              {label}
            </text>
          </g>
        );
      })}
      {nodes.map((node) => (
        <g key={node.entity.id}>
          <circle className="node" cx={node.x} cy={node.y} r="34" />
          <text className="nodeTitle" x={node.x} y={node.y - 3}>
            {node.entity.name.slice(0, 18)}
          </text>
          <text className="nodeMeta" x={node.x} y={node.y + 14}>
            {node.entity.class_label}
          </text>
        </g>
      ))}
    </svg>
  );
}

function AgentPage(props: {
  project: Project | null;
  ontology: Ontology | null;
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
}) {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<JsonObject | null>(null);

  function run(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const response = await props.request<JsonObject>("/agent-test/run", {
        method: "POST",
        body: JSON.stringify({
          question,
          project_id: props.project?.id ?? null,
          ontology_id: props.ontology?.id ?? null,
        }),
      });
      setResult(response);
    }, "Agent test completed");
  }

  return (
    <section className="agentGrid">
      <Panel title="Run Agent Test" icon={<Play size={17} />}>
        <form className="stackForm" onSubmit={run}>
          <textarea
            className="questionBox"
            required
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a question against the selected project and ontology"
          />
          <button className="primaryButton" type="submit">
            <Play size={16} /> Run
          </button>
        </form>
      </Panel>
      <Panel title="Result" icon={<Settings size={17} />} wide>
        <ResultField title="Answer" value={result?.answer} />
        <ResultField title="Tool calls" value={result?.tool_calls} />
        <ResultField title="Graph context" value={result?.graph_context} />
        <ResultField title="Prompt preview" value={result?.prompt_preview} />
        <ResultField title="Warnings" value={result?.warnings} />
        <ResultField title="Errors" value={result?.errors} />
        {!result && <div className="emptyGraph">No run output yet.</div>}
      </Panel>
    </section>
  );
}

function HealthPage(props: {
  health: Health | null;
  request: <T>(path: string, options?: RequestInit) => Promise<T>;
  setHealth: (health: Health) => void;
  showError: (error: unknown) => void;
}) {
  const { health, request, setHealth, showError } = props;

  useEffect(() => {
    request<Health>("/health/dependencies").then(setHealth).catch(showError);
  }, [request, setHealth, showError]);

  return (
    <section className="twoColumn">
      <Panel title="Dependencies" icon={<Server size={17} />}>
        <button
          className="primaryButton"
          onClick={() => request<Health>("/health/dependencies").then(setHealth).catch(showError)}
          type="button"
        >
          <RefreshCw size={16} /> Check
        </button>
        <pre className="jsonBlock">{JSON.stringify(health, null, 2)}</pre>
      </Panel>
    </section>
  );
}

function Panel({ title, icon, children, wide }: { title: string; icon: React.ReactNode; children: React.ReactNode; wide?: boolean }) {
  return (
    <section className={classNames("panel", wide && "widePanel")}>
      <div className="panelTitle">
        {icon}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

function DataTable({ rows }: { rows: Array<{ id: string; first: string; second: string; meta: string }> }) {
  return (
    <div className="listTable compact">
      {rows.map((row) => (
        <div className="row" key={row.id}>
          <div className="rowMain static">
            <strong>{row.first}</strong>
            <span>{row.second}</span>
          </div>
          <code>{row.meta}</code>
        </div>
      ))}
    </div>
  );
}

function ResultField({ title, value }: { title: string; value: unknown }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <section className="resultField">
      <h3>{title}</h3>
      <pre>{typeof value === "string" ? value : JSON.stringify(value, null, 2)}</pre>
    </section>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
