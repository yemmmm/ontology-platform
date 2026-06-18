import {
  Activity,
  ArrowLeft,
  ArrowDownToLine,
  Box,
  Braces,
  Check,
  ChevronRight,
  Clipboard,
  Database,
  Download,
  FileJson,
  GitBranch,
  Layers,
  Link2,
  Loader2,
  Maximize2,
  Network,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  Settings,
  Shield,
  Trash2,
  Upload,
  Waypoints,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Card, ConfigProvider, Tag, Tooltip } from "antd";
import "antd/dist/reset.css";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE_URL, TOKEN_KEY, apiRequest, errorNotice } from "./api";
import type {
  AgentTestResponse,
  ClassDef,
  Entity,
  EntityExplain,
  EntitySearchResult,
  EntityWithRelations,
  Health,
  JsonObject,
  Notice,
  Ontology,
  OntologyExport,
  Project,
  PropertyDef,
  RelatedEntity,
  Relation,
  RelationType,
} from "./types";
import {
  classNames,
  compactId,
  csv,
  downloadJson,
  formatDate,
  nameFor,
  parseJsonObject,
  prettyJson,
  propertyTypes,
  splitCsv,
} from "./utils";

type Tab = "workspace" | "graph" | "import" | "agent" | "settings";
type WorkspaceView = "home" | "new-project" | "ontology" | "class";
type Requester = <T,>(path: string, options?: RequestInit) => Promise<T>;

const UI_KEYS = {
  tab: "ontology-platform-ui-tab-v2",
  project: "ontology-platform-ui-selected-project",
  ontology: "ontology-platform-ui-selected-ontology",
  class: "ontology-platform-ui-selected-class",
} as const;

const tabs: Array<{ id: Tab; label: string; detail: string; icon: typeof Network }> = [
  { id: "workspace", label: "Workspace", detail: "Projects and ontologies", icon: Layers },
  { id: "graph", label: "Graph Data", detail: "Entities and relations", icon: Network },
  { id: "import", label: "Import / Export", detail: "Portable JSON", icon: FileJson },
  { id: "agent", label: "Agent Lab", detail: "Question tests", icon: Send },
  { id: "settings", label: "Settings", detail: "Token and system health", icon: Settings },
];

function isTab(value: string | null): value is Tab {
  return tabs.some((tab) => tab.id === value);
}

function useStoredString(key: string, fallback = "") {
  const [value, setValue] = useState(() => {
    try {
      return localStorage.getItem(key) ?? fallback;
    } catch {
      return fallback;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Storage is optional for the local workspace.
    }
  }, [key, value]);

  return [value, setValue] as const;
}

function useStoredTab(key: string, fallback: Tab) {
  const [value, setValue] = useState<Tab>(() => {
    try {
      const stored = localStorage.getItem(key);
      return isTab(stored) ? stored : fallback;
    } catch {
      return fallback;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Storage is optional for the local workspace.
    }
  }, [key, value]);

  return [value, setValue] as const;
}

export function App() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? "");
  const [tab, setTab] = useStoredTab(UI_KEYS.tab, "workspace");
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("home");
  const [projects, setProjects] = useState<Project[]>([]);
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [classes, setClasses] = useState<ClassDef[]>([]);
  const [propertiesByClass, setPropertiesByClass] = useState<Record<string, PropertyDef[]>>({});
  const [relationTypes, setRelationTypes] = useState<RelationType[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useStoredString(UI_KEYS.project);
  const [selectedOntologyId, setSelectedOntologyId] = useStoredString(UI_KEYS.ontology);
  const [selectedClassId, setSelectedClassId] = useStoredString(UI_KEYS.class);
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(false);

  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const selectedOntology = ontologies.find((ontology) => ontology.id === selectedOntologyId) ?? null;

  const request = useCallback(
    <T,>(path: string, options?: RequestInit) => apiRequest<T>(path, token, options),
    [token],
  );

  const showError = useCallback((error: unknown) => setNotice(errorNotice(error)), []);

  const loadProjects = useCallback(async () => {
    const data = await request<Project[]>("/projects");
    setProjects(data);
    setSelectedProjectId((current) =>
      current && data.some((project) => project.id === current) ? current : data[0]?.id || "",
    );
  }, [request, setSelectedProjectId]);

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
    [request, selectedProjectId, setSelectedOntologyId],
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
      const [classData, relationData] = await Promise.all([
        request<ClassDef[]>(`/ontologies/${ontologyId}/classes`),
        request<RelationType[]>(`/ontologies/${ontologyId}/relation-types`),
      ]);
      const propertyPairs = await Promise.all(
        classData.map(async (classDef) => [
          classDef.id,
          await request<PropertyDef[]>(`/classes/${classDef.id}/properties`),
        ] as const),
      );
      setClasses(classData);
      setPropertiesByClass(Object.fromEntries(propertyPairs));
      setRelationTypes(relationData);
      setSelectedClassId((current) =>
        current && classData.some((classDef) => classDef.id === current) ? current : classData[0]?.id || "",
      );
    },
    [request, selectedOntologyId, setSelectedClassId],
  );

  const loadGraph = useCallback(
    async (ontologyId = selectedOntologyId) => {
      if (!ontologyId) {
        setEntities([]);
        setRelations([]);
        return;
      }
      const [entityData, relationData] = await Promise.all([
        request<Entity[]>(`/ontologies/${ontologyId}/entities?limit=300`),
        request<Relation[]>(`/ontologies/${ontologyId}/relations?limit=300`),
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

  function saveToken(value: string) {
    setToken(value);
    localStorage.setItem(TOKEN_KEY, value);
  }

  const pageTitle = tabs.find((item) => item.id === tab)?.label ?? "Workspace";

  return (
    <ConfigProvider
      theme={{
        token: {
          borderRadius: 8,
          colorPrimary: "#6c4df6",
          colorInfo: "#2fbf8f",
          colorText: "#151722",
          fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
      }}
    >
    <main className="appShell">
      <aside className="rail">
        <div className="brandMark">
          <Network size={22} />
          <div>
            <strong>Ontology Platform</strong>
            <span>Knowledge engineering</span>
          </div>
        </div>
        <nav className="mainNav" aria-label="Workspace navigation">
          {tabs.map((item) => {
            const Icon = item.icon;
            return (
              <button
                className={classNames("navButton", tab === item.id && "active")}
                key={item.id}
                onClick={() => setTab(item.id)}
                type="button"
              >
                <Icon size={17} />
                <span>
                  <strong>{item.label}</strong>
                  <small>{item.detail}</small>
                </span>
              </button>
            );
          })}
        </nav>
        <div className="railFooter">
          <span>API</span>
          <code>{API_BASE_URL}</code>
        </div>
      </aside>

      <section className="workbench">
        <header className="topBar">
          <div className="titleBlock">
            <span className="eyebrow">Local ontology workspace</span>
            <h1>{pageTitle}</h1>
            <div className="crumbTrail">
              <span>{selectedProject?.name ?? "No project"}</span>
              <ChevronRight size={13} />
              <span>{selectedOntology?.name ?? "No ontology"}</span>
              <ChevronRight size={13} />
              <span>{selectedOntology?.status ?? "unscoped"}</span>
            </div>
          </div>
          <div className="topActions">
            <ContextSwitcher
              ontologies={ontologies}
              onNewProject={() => {
                setTab("workspace");
                setWorkspaceView("new-project");
              }}
              projects={projects}
              selectedOntologyId={selectedOntologyId}
              selectedProjectId={selectedProjectId}
              setSelectedOntologyId={setSelectedOntologyId}
              setSelectedProjectId={(id) => {
                setSelectedProjectId(id);
                setWorkspaceView("home");
              }}
            />
            <Tooltip title="Refresh workspace data">
              <button className="iconButton" disabled={loading} onClick={refreshAll} type="button">
                {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
              </button>
            </Tooltip>
          </div>
        </header>

        {notice && <StatusBanner notice={notice} onDismiss={() => setNotice(null)} />}

        <div className="contentFrame">
        {tab === "workspace" && (
          <WorkspacePage
            classes={classes}
            entities={entities}
            mutate={mutate}
            ontologies={ontologies}
            projects={projects}
            relations={relations}
            relationTypes={relationTypes}
            request={request}
            selectedOntology={selectedOntology}
            selectedProjectId={selectedProjectId}
            selectedClassId={selectedClassId}
            setSelectedClassId={setSelectedClassId}
            setSelectedOntologyId={setSelectedOntologyId}
            setSelectedProjectId={setSelectedProjectId}
            view={workspaceView}
            setView={setWorkspaceView}
            propertiesByClass={propertiesByClass}
            reloadOntologies={loadOntologies}
            reloadProjects={loadProjects}
            reloadSchema={loadSchema}
          />
        )}
        {tab === "graph" && (
          <GraphWorkbenchPage
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
        {tab === "import" && (
          <ImportExportPage
            mutate={mutate}
            ontology={selectedOntology}
            project={selectedProject}
            request={request}
            reloadOntologies={loadOntologies}
          />
        )}
        {tab === "agent" && <AgentLabPage ontology={selectedOntology} request={request} mutate={mutate} />}
        {tab === "settings" && (
          <SystemPage
            health={health}
            request={request}
            saveToken={saveToken}
            setHealth={setHealth}
            showError={showError}
            token={token}
          />
        )}
        </div>
      </section>
    </main>
    </ConfigProvider>
  );
}

function ContextSwitcher(props: {
  projects: Project[];
  ontologies: Ontology[];
  selectedProjectId: string;
  selectedOntologyId: string;
  setSelectedProjectId: (id: string) => void;
  setSelectedOntologyId: (id: string) => void;
  onNewProject: () => void;
}) {
  return (
    <section className="contextStrip">
      <label>
        <span>Project</span>
        <select
          value={props.selectedProjectId}
          onChange={(event) => {
            if (event.target.value === "__new_project__") {
              props.onNewProject();
              return;
            }
            props.setSelectedProjectId(event.target.value);
          }}
        >
          <option value="">Select project</option>
          {props.projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
          <option value="__new_project__">New project...</option>
        </select>
      </label>
      <label>
        <span>Ontology</span>
        <select value={props.selectedOntologyId} onChange={(event) => props.setSelectedOntologyId(event.target.value)}>
          <option value="">Select ontology</option>
          {props.ontologies.map((ontology) => (
            <option key={ontology.id} value={ontology.id}>
              {ontology.name}
            </option>
          ))}
        </select>
      </label>
      <div className="contextMetric">
        <span>Scope</span>
        <strong>{props.selectedOntologyId ? compactId(props.selectedOntologyId) : "Not selected"}</strong>
      </div>
    </section>
  );
}

function WorkspacePage(props: {
  projects: Project[];
  ontologies: Ontology[];
  selectedProjectId: string;
  selectedOntology: Ontology | null;
  selectedClassId: string;
  classes: ClassDef[];
  relationTypes: RelationType[];
  entities: Entity[];
  relations: Relation[];
  propertiesByClass: Record<string, PropertyDef[]>;
  view: WorkspaceView;
  setView: (view: WorkspaceView) => void;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadProjects: () => Promise<void>;
  reloadOntologies: (projectId?: string) => Promise<void>;
  reloadSchema: () => Promise<void>;
  setSelectedProjectId: (id: string) => void;
  setSelectedOntologyId: (id: string) => void;
  setSelectedClassId: (id: string) => void;
}) {
  const [projectForm, setProjectForm] = useState({ name: "", description: "" });
  const [ontologyForm, setOntologyForm] = useState({ name: "", description: "" });
  const [classForm, setClassForm] = useState({ name: "", description: "", aliases: "", parents: [] as string[] });
  const [relationForm, setRelationForm] = useState({
    name: "",
    description: "",
    aliases: "",
    sourceClassId: "",
    targetClassId: "",
    inverseName: "",
  });
  const [editingRelation, setEditingRelation] = useState<RelationType | null>(null);

  const selectedClass = props.classes.find((item) => item.id === props.selectedClassId) ?? null;
  const selectedProperties = selectedClass ? props.propertiesByClass[selectedClass.id] ?? [] : [];
  const outgoingRelationTypes = selectedClass
    ? props.relationTypes.filter((relationType) => relationType.source_class_id === selectedClass.id)
    : [];
  const incomingRelationTypes = selectedClass
    ? props.relationTypes.filter((relationType) => relationType.target_class_id === selectedClass.id)
    : [];

  useEffect(() => {
    if (selectedClass && props.view === "class") {
      setClassForm({
        name: selectedClass.name,
        description: selectedClass.description ?? "",
        aliases: csv(selectedClass.aliases),
        parents: selectedClass.parent_class_ids,
      });
    }
  }, [selectedClass, props.view]);

  useEffect(() => {
    if (editingRelation) {
      setRelationForm({
        name: editingRelation.name,
        description: editingRelation.description ?? "",
        aliases: csv(editingRelation.aliases),
        sourceClassId: editingRelation.source_class_id,
        targetClassId: editingRelation.target_class_id,
        inverseName: editingRelation.inverse_name ?? "",
      });
      return;
    }
    if (selectedClass && props.view === "class" && !relationForm.sourceClassId) {
      setRelationForm((current) => ({
        ...current,
        sourceClassId: selectedClass.id,
        targetClassId: props.classes.find((classDef) => classDef.id !== selectedClass.id)?.id ?? selectedClass.id,
      }));
    }
  }, [editingRelation, selectedClass, props.classes, props.view, relationForm.sourceClassId]);

  function createProject(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const created = await props.request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name: projectForm.name, description: projectForm.description || null }),
      });
      setProjectForm({ name: "", description: "" });
      props.setSelectedProjectId(created.id);
      await props.reloadProjects();
      props.setView("home");
    }, "Project created");
  }

  function createOntology(event: FormEvent) {
    event.preventDefault();
    if (!props.selectedProjectId) return;
    props.mutate(async () => {
      const created = await props.request<Ontology>(`/projects/${props.selectedProjectId}/ontologies`, {
        method: "POST",
        body: JSON.stringify({
          name: ontologyForm.name,
          description: ontologyForm.description || null,
          external_mappings: {},
        }),
      });
      setOntologyForm({ name: "", description: "" });
      props.setSelectedOntologyId(created.id);
      await props.reloadOntologies(props.selectedProjectId);
      props.setView("ontology");
    }, "Ontology created");
  }

  function saveClass(event: FormEvent) {
    event.preventDefault();
    const ontology = props.selectedOntology;
    if (!ontology) return;
    props.mutate(async () => {
      const body = {
        name: classForm.name,
        description: classForm.description || null,
        aliases: splitCsv(classForm.aliases),
        parent_class_ids: classForm.parents,
        external_mappings: selectedClass && props.view === "class" ? selectedClass.external_mappings ?? {} : {},
      };
      if (selectedClass && props.view === "class") {
        await props.request<ClassDef>(`/classes/${selectedClass.id}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        const created = await props.request<ClassDef>(`/ontologies/${ontology.id}/classes`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        props.setSelectedClassId(created.id);
        props.setView("class");
      }
      setClassForm({ name: "", description: "", aliases: "", parents: [] });
      await props.reloadSchema();
    }, selectedClass && props.view === "class" ? "Class updated" : "Class created");
  }

  function saveRelationType(event: FormEvent) {
    event.preventDefault();
    const ontology = props.selectedOntology;
    if (!ontology) return;
    props.mutate(async () => {
      const body = {
        name: relationForm.name,
        description: relationForm.description || null,
        aliases: splitCsv(relationForm.aliases),
        parent_relation_type_id: editingRelation?.parent_relation_type_id ?? null,
        source_class_id: relationForm.sourceClassId,
        target_class_id: relationForm.targetClassId,
        inverse_name: relationForm.inverseName || null,
        external_mappings: editingRelation?.external_mappings ?? {},
      };
      if (editingRelation) {
        await props.request<RelationType>(`/relation-types/${editingRelation.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        await props.request<RelationType>(`/ontologies/${ontology.id}/relation-types`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      setEditingRelation(null);
      setRelationForm({ name: "", description: "", aliases: "", sourceClassId: "", targetClassId: "", inverseName: "" });
      await props.reloadSchema();
    }, editingRelation ? "Relation type updated" : "Relation type created");
  }

  function selectOntology(ontology: Ontology) {
    props.setSelectedOntologyId(ontology.id);
    props.setSelectedClassId("");
    setClassForm({ name: "", description: "", aliases: "", parents: [] });
    props.setView("ontology");
  }

  function selectClass(classDef: ClassDef) {
    props.setSelectedClassId(classDef.id);
    setEditingRelation(null);
    props.setView("class");
  }

  if (props.view === "new-project") {
    return (
      <section className="pageGrid workspaceGrid">
        <Panel title="New project" icon={<Layers size={17} />} wide>
          <button className="secondaryButton" onClick={() => props.setView("home")} type="button">
            <ArrowLeft size={15} /> Workspace
          </button>
          <form className="stackForm spacedForm" onSubmit={createProject}>
            <input
              required
              placeholder="Project name"
              value={projectForm.name}
              onChange={(event) => setProjectForm({ ...projectForm, name: event.target.value })}
            />
            <textarea
              placeholder="Description"
              value={projectForm.description}
              onChange={(event) => setProjectForm({ ...projectForm, description: event.target.value })}
            />
            <button className="primaryButton" type="submit">
              <Plus size={15} /> Create project
            </button>
          </form>
        </Panel>
      </section>
    );
  }

  if (props.view === "ontology") {
    return (
      <section className="workspaceStack">
        <button className="secondaryButton" onClick={() => props.setView("home")} type="button">
          <ArrowLeft size={15} /> Ontologies
        </button>
        <div className="metricGrid">
          <Metric label="Classes" value={props.classes.length} icon={<Box size={18} />} />
          <Metric label="Relation types" value={props.relationTypes.length} icon={<GitBranch size={18} />} />
          <Metric label="Entities" value={props.entities.length} icon={<Database size={18} />} />
          <Metric label="Relations" value={props.relations.length} icon={<Link2 size={18} />} />
        </div>
        <section className="pageGrid classWorkspaceGrid">
          <Panel title={props.selectedOntology?.name ?? "Ontology"} icon={<Waypoints size={17} />} wide>
            {props.selectedOntology ? (
              <div className="overview">
                <p>{props.selectedOntology.description || "No description provided."}</p>
                <dl className="detailList">
                  <dt>Status</dt>
                  <dd><Badge>{props.selectedOntology.status}</Badge></dd>
                  <dt>Current version</dt>
                  <dd>{compactId(props.selectedOntology.current_version_id)}</dd>
                  <dt>Updated</dt>
                  <dd>{formatDate(props.selectedOntology.updated_at)}</dd>
                </dl>
              </div>
            ) : (
              <EmptyState icon={<Database size={22} />} title="Select an ontology" />
            )}
          </Panel>
          <Panel title="Create class" icon={<Plus size={17} />}>
            <form className="stackForm" onSubmit={saveClass}>
              <input
                required
                placeholder="Class name"
                value={classForm.name}
                onChange={(event) => setClassForm({ ...classForm, name: event.target.value })}
              />
              <textarea
                placeholder="Description"
                value={classForm.description}
                onChange={(event) => setClassForm({ ...classForm, description: event.target.value })}
              />
              <input
                placeholder="Aliases, comma separated"
                value={classForm.aliases}
                onChange={(event) => setClassForm({ ...classForm, aliases: event.target.value })}
              />
              <button className="primaryButton" disabled={!props.selectedOntology} type="submit">
                <Plus size={15} /> Create class
              </button>
            </form>
          </Panel>
          <Panel title="Classes" icon={<Box size={17} />} wide>
            <DataList
              empty="No classes"
              items={props.classes.map((classDef) => ({
                id: classDef.id,
                title: classDef.name,
                subtitle: classDef.description || classDef.normalized_label || compactId(classDef.id),
                meta: `${(props.propertiesByClass[classDef.id] ?? []).length} props`,
                onSelect: () => selectClass(classDef),
                actions: (
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
                ),
              }))}
            />
          </Panel>
        </section>
      </section>
    );
  }

  if (props.view === "class") {
    const relationItems = [...outgoingRelationTypes, ...incomingRelationTypes];
    return (
      <section className="workspaceStack">
        <button className="secondaryButton" onClick={() => props.setView("ontology")} type="button">
          <ArrowLeft size={15} /> Classes
        </button>
        {selectedClass ? (
          <section className="pageGrid classDetailGrid">
            <Panel title="Class details" icon={<Box size={17} />}>
              <form className="stackForm" onSubmit={saveClass}>
                <input
                  required
                  placeholder="Class name"
                  value={classForm.name}
                  onChange={(event) => setClassForm({ ...classForm, name: event.target.value })}
                />
                <textarea
                  placeholder="Description"
                  value={classForm.description}
                  onChange={(event) => setClassForm({ ...classForm, description: event.target.value })}
                />
                <input
                  placeholder="Aliases, comma separated"
                  value={classForm.aliases}
                  onChange={(event) => setClassForm({ ...classForm, aliases: event.target.value })}
                />
                <label>
                  <span>Parent classes</span>
                  <select
                    multiple
                    value={classForm.parents}
                    onChange={(event) =>
                      setClassForm({
                        ...classForm,
                        parents: Array.from(event.currentTarget.selectedOptions).map((option) => option.value),
                      })
                    }
                  >
                    {props.classes
                      .filter((classDef) => classDef.id !== selectedClass.id)
                      .map((classDef) => (
                        <option key={classDef.id} value={classDef.id}>
                          {classDef.name}
                        </option>
                      ))}
                  </select>
                </label>
                <button className="primaryButton" type="submit">
                  <Save size={15} /> Save class
                </button>
              </form>
            </Panel>

            <Panel title="Related relations" icon={<GitBranch size={17} />}>
              <div className="relationSummary">
                <Boundary title="As source" text={`${outgoingRelationTypes.length} relation types`} />
                <Boundary title="As target" text={`${incomingRelationTypes.length} relation types`} />
              </div>
              <DataList
                empty="No relation types for this class"
                items={relationItems.map((relationType) => ({
                  id: relationType.id,
                  title: relationType.name,
                  subtitle: `${nameFor(props.classes, relationType.source_class_id)} -> ${nameFor(
                    props.classes,
                    relationType.target_class_id,
                  )}`,
                  selected: editingRelation?.id === relationType.id,
                  onSelect: () => setEditingRelation(relationType),
                  actions: (
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
                  ),
                }))}
              />
            </Panel>

            <Panel title={editingRelation ? "Edit relation" : "Create relation"} icon={<GitBranch size={17} />}>
              <form className="stackForm" onSubmit={saveRelationType}>
                <input
                  required
                  placeholder="Relation type name"
                  value={relationForm.name}
                  onChange={(event) => setRelationForm({ ...relationForm, name: event.target.value })}
                />
                <input
                  placeholder="Aliases"
                  value={relationForm.aliases}
                  onChange={(event) => setRelationForm({ ...relationForm, aliases: event.target.value })}
                />
                <textarea
                  placeholder="Description"
                  value={relationForm.description}
                  onChange={(event) => setRelationForm({ ...relationForm, description: event.target.value })}
                />
                <div className="buttonRow">
                  <button
                    className="secondaryButton"
                    onClick={() => setRelationForm({ ...relationForm, sourceClassId: selectedClass.id })}
                    type="button"
                  >
                    Source here
                  </button>
                  <button
                    className="secondaryButton"
                    onClick={() => setRelationForm({ ...relationForm, targetClassId: selectedClass.id })}
                    type="button"
                  >
                    Target here
                  </button>
                </div>
                <div className="formPair">
                  <label>
                    <span>Source class</span>
                    <select
                      required
                      value={relationForm.sourceClassId}
                      onChange={(event) => setRelationForm({ ...relationForm, sourceClassId: event.target.value })}
                    >
                      <option value="">Source class</option>
                      {props.classes.map((classDef) => (
                        <option key={classDef.id} value={classDef.id}>
                          {classDef.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>Target class</span>
                    <select
                      required
                      value={relationForm.targetClassId}
                      onChange={(event) => setRelationForm({ ...relationForm, targetClassId: event.target.value })}
                    >
                      <option value="">Target class</option>
                      {props.classes.map((classDef) => (
                        <option key={classDef.id} value={classDef.id}>
                          {classDef.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <input
                  placeholder="Inverse name"
                  value={relationForm.inverseName}
                  onChange={(event) => setRelationForm({ ...relationForm, inverseName: event.target.value })}
                />
                <div className="buttonRow">
                  <button className="primaryButton" disabled={props.classes.length < 1} type="submit">
                    <Save size={15} /> {editingRelation ? "Save relation" : "Create relation"}
                  </button>
                  {editingRelation && (
                    <button
                      className="secondaryButton"
                      onClick={() => {
                        setEditingRelation(null);
                        setRelationForm({
                          name: "",
                          description: "",
                          aliases: "",
                          sourceClassId: selectedClass.id,
                          targetClassId: props.classes.find((classDef) => classDef.id !== selectedClass.id)?.id ?? selectedClass.id,
                          inverseName: "",
                        });
                      }}
                      type="button"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </form>
            </Panel>

            <Panel title="Properties" icon={<Braces size={17} />}>
              <DataList
                empty="No properties for this class"
                items={selectedProperties.map((property) => ({
                  id: property.id,
                  title: property.name,
                  subtitle: `${property.type}${property.required ? " - required" : ""}${property.multi_valued ? " - multi" : ""}`,
                }))}
              />
            </Panel>
          </section>
        ) : (
          <EmptyState icon={<Box size={22} />} title="Select a class" />
        )}
      </section>
    );
  }

  const selectedProject = props.projects.find((project) => project.id === props.selectedProjectId) ?? null;

  return (
    <section className="workspaceStack">
      <div className="metricGrid">
        <Metric label="Ontologies" value={props.ontologies.length} icon={<Waypoints size={18} />} />
        <Metric label="Classes" value={props.classes.length} icon={<Box size={18} />} />
        <Metric label="Relation types" value={props.relationTypes.length} icon={<GitBranch size={18} />} />
        <Metric label="Entities" value={props.entities.length} icon={<Database size={18} />} />
      </div>
      <section className="pageGrid workspaceGrid">
        <Panel title="Ontologies" icon={<Waypoints size={17} />} wide>
          {props.ontologies.length ? (
            <div className="ontologyCardGrid">
              {props.ontologies.map((ontology) => (
                <button
                  className={classNames("ontologyCard", ontology.id === props.selectedOntology?.id && "selected")}
                  key={ontology.id}
                  onClick={() => selectOntology(ontology)}
                  type="button"
                >
                  <span className="ontologyCardTop">
                    <strong>{ontology.name}</strong>
                    <Badge>{ontology.status}</Badge>
                  </span>
                  <span>{ontology.description || "No description provided."}</span>
                  <dl>
                    <dt>Updated</dt>
                    <dd>{formatDate(ontology.updated_at)}</dd>
                    <dt>Version</dt>
                    <dd>{compactId(ontology.current_version_id)}</dd>
                  </dl>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState icon={<Database size={22} />} title="No ontologies" />
          )}
        </Panel>
        <Panel title="Create ontology" icon={<Plus size={17} />}>
          <form className="stackForm" onSubmit={createOntology}>
            <input
              required
              placeholder="Ontology name"
              value={ontologyForm.name}
              onChange={(event) => setOntologyForm({ ...ontologyForm, name: event.target.value })}
            />
            <textarea
              placeholder="Description"
              value={ontologyForm.description}
              onChange={(event) => setOntologyForm({ ...ontologyForm, description: event.target.value })}
            />
            <button className="primaryButton" disabled={!props.selectedProjectId} type="submit">
              <Plus size={15} /> Create ontology
            </button>
          </form>
          <div className="callout quiet">
            <strong>{selectedProject?.name ?? "No project selected"}</strong>
            <span>Use the project selector above to switch project scope or create a new project.</span>
          </div>
        </Panel>
      </section>
    </section>
  );
}

function LegacyWorkspacePage(props: {
  projects: Project[];
  ontologies: Ontology[];
  selectedProjectId: string;
  selectedOntology: Ontology | null;
  classes: ClassDef[];
  relationTypes: RelationType[];
  entities: Entity[];
  relations: Relation[];
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadProjects: () => Promise<void>;
  reloadOntologies: (projectId?: string) => Promise<void>;
  setSelectedProjectId: (id: string) => void;
  setSelectedOntologyId: (id: string) => void;
}) {
  const [projectForm, setProjectForm] = useState({ name: "", description: "" });
  const [ontologyForm, setOntologyForm] = useState({ name: "", description: "" });
  const [editingProjectId, setEditingProjectId] = useState("");
  const [editingOntologyId, setEditingOntologyId] = useState("");
  const editingProject = props.projects.find((project) => project.id === editingProjectId) ?? null;
  const editingOntology = props.ontologies.find((ontology) => ontology.id === editingOntologyId) ?? null;

  useEffect(() => {
    if (editingProject) {
      setProjectForm({ name: editingProject.name, description: editingProject.description ?? "" });
    }
  }, [editingProject]);

  useEffect(() => {
    if (editingOntology) {
      setOntologyForm({ name: editingOntology.name, description: editingOntology.description ?? "" });
    }
  }, [editingOntology]);

  function createProject(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const created = await props.request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name: projectForm.name, description: projectForm.description || null }),
      });
      setProjectForm({ name: "", description: "" });
      props.setSelectedProjectId(created.id);
      await props.reloadProjects();
    }, "Project created");
  }

  function saveProject(event: FormEvent) {
    event.preventDefault();
    if (!editingProject) return;
    props.mutate(async () => {
      await props.request<Project>(`/projects/${editingProject.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: projectForm.name, description: projectForm.description || null }),
      });
      await props.reloadProjects();
    }, "Project updated");
  }

  function createOntology(event: FormEvent) {
    event.preventDefault();
    if (!props.selectedProjectId) return;
    props.mutate(async () => {
      const created = await props.request<Ontology>(`/projects/${props.selectedProjectId}/ontologies`, {
        method: "POST",
        body: JSON.stringify({
          name: ontologyForm.name,
          description: ontologyForm.description || null,
          external_mappings: {},
        }),
      });
      setOntologyForm({ name: "", description: "" });
      props.setSelectedOntologyId(created.id);
      await props.reloadOntologies(props.selectedProjectId);
    }, "Ontology created");
  }

  function saveOntology(event: FormEvent) {
    event.preventDefault();
    if (!editingOntology) return;
    props.mutate(async () => {
      await props.request<Ontology>(`/ontologies/${editingOntology.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: ontologyForm.name,
          description: ontologyForm.description || null,
          external_mappings: editingOntology.external_mappings ?? {},
        }),
      });
      await props.reloadOntologies(props.selectedProjectId);
    }, "Ontology updated");
  }

  return (
    <section className="pageGrid workspaceGrid">
      <div className="span2">
        <div className="metricGrid">
          <Metric label="Classes" value={props.classes.length} icon={<Box size={18} />} />
          <Metric label="Relation types" value={props.relationTypes.length} icon={<GitBranch size={18} />} />
          <Metric label="Entities" value={props.entities.length} icon={<Database size={18} />} />
          <Metric label="Relations" value={props.relations.length} icon={<Link2 size={18} />} />
        </div>
        <Panel title="Current ontology" icon={<Waypoints size={17} />}>
          {props.selectedOntology ? (
            <div className="overview">
              <div>
                <h2>{props.selectedOntology.name}</h2>
                <p>{props.selectedOntology.description || "No description provided."}</p>
              </div>
              <dl className="detailList">
                <dt>Status</dt>
                <dd>
                  <Badge>{props.selectedOntology.status}</Badge>
                </dd>
                <dt>Current version</dt>
                <dd>{compactId(props.selectedOntology.current_version_id)}</dd>
                <dt>Updated</dt>
                <dd>{formatDate(props.selectedOntology.updated_at)}</dd>
              </dl>
              <div className="callout">
                <strong>Version workflow pending</strong>
                <span>The backend stores version metadata, but no publish API is exposed yet.</span>
                <button className="secondaryButton" disabled type="button">
                  <ArrowDownToLine size={15} /> Publish version
                </button>
              </div>
            </div>
          ) : (
            <EmptyState icon={<Database size={22} />} title="Select an ontology" />
          )}
        </Panel>
      </div>

      <Panel title="Projects" icon={<Layers size={17} />}>
        <form className="stackForm" onSubmit={editingProject ? saveProject : createProject}>
          <input
            required
            placeholder="Project name"
            value={projectForm.name}
            onChange={(event) => setProjectForm({ ...projectForm, name: event.target.value })}
          />
          <textarea
            placeholder="Description"
            value={projectForm.description}
            onChange={(event) => setProjectForm({ ...projectForm, description: event.target.value })}
          />
          <div className="buttonRow">
            <button className="primaryButton" type="submit">
              {editingProject ? <Save size={15} /> : <Plus size={15} />}
              {editingProject ? "Save" : "Create"}
            </button>
            {editingProject && (
              <button className="secondaryButton" onClick={() => setEditingProjectId("")} type="button">
                Cancel
              </button>
            )}
          </div>
        </form>
        <DataList
          empty="No projects"
          items={props.projects.map((project) => ({
            id: project.id,
            title: project.name,
            subtitle: project.description || compactId(project.id),
            selected: project.id === props.selectedProjectId,
            onSelect: () => props.setSelectedProjectId(project.id),
            actions: (
              <>
                <button className="iconButton" onClick={() => setEditingProjectId(project.id)} title="Edit project" type="button">
                  <Settings size={15} />
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
              </>
            ),
          }))}
        />
      </Panel>

      <Panel title="Ontologies" icon={<Waypoints size={17} />}>
        <form className="stackForm" onSubmit={editingOntology ? saveOntology : createOntology}>
          <input
            required
            placeholder="Ontology name"
            value={ontologyForm.name}
            onChange={(event) => setOntologyForm({ ...ontologyForm, name: event.target.value })}
          />
          <textarea
            placeholder="Description"
            value={ontologyForm.description}
            onChange={(event) => setOntologyForm({ ...ontologyForm, description: event.target.value })}
          />
          <div className="buttonRow">
            <button className="primaryButton" disabled={!props.selectedProjectId} type="submit">
              {editingOntology ? <Save size={15} /> : <Plus size={15} />}
              {editingOntology ? "Save" : "Create"}
            </button>
            {editingOntology && (
              <button className="secondaryButton" onClick={() => setEditingOntologyId("")} type="button">
                Cancel
              </button>
            )}
          </div>
        </form>
        <DataList
          empty="No ontologies"
          items={props.ontologies.map((ontology) => ({
            id: ontology.id,
            title: ontology.name,
            subtitle: `${ontology.status} - ${ontology.description || compactId(ontology.id)}`,
            selected: ontology.id === props.selectedOntology?.id,
            onSelect: () => props.setSelectedOntologyId(ontology.id),
            actions: (
              <>
                <button className="iconButton" onClick={() => setEditingOntologyId(ontology.id)} title="Edit ontology" type="button">
                  <Settings size={15} />
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
              </>
            ),
          }))}
        />
      </Panel>
    </section>
  );
}

function OntologyDesignerPage(props: {
  mode: "classes" | "relations";
  ontologyId: string;
  classes: ClassDef[];
  relationTypes: RelationType[];
  propertiesByClass: Record<string, PropertyDef[]>;
  selectedClassId: string;
  setSelectedClassId: (id: string) => void;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadSchema: () => Promise<void>;
}) {
  const selectedClass = props.classes.find((item) => item.id === props.selectedClassId) ?? null;
  const selectedProperties = selectedClass ? props.propertiesByClass[selectedClass.id] ?? [] : [];
  const [classForm, setClassForm] = useState({ name: "", description: "", aliases: "", parents: [] as string[] });
  const [propertyForm, setPropertyForm] = useState({
    name: "",
    type: "string",
    description: "",
    required: false,
    multiValued: false,
    enumValues: "",
  });
  const [relationForm, setRelationForm] = useState({
    name: "",
    description: "",
    aliases: "",
    sourceClassId: "",
    targetClassId: "",
    inverseName: "",
  });
  const [editingProperty, setEditingProperty] = useState<PropertyDef | null>(null);
  const [editingRelation, setEditingRelation] = useState<RelationType | null>(null);

  useEffect(() => {
    if (selectedClass) {
      setClassForm({
        name: selectedClass.name,
        description: selectedClass.description ?? "",
        aliases: csv(selectedClass.aliases),
        parents: selectedClass.parent_class_ids,
      });
    }
  }, [selectedClass]);

  useEffect(() => {
    if (editingProperty) {
      setPropertyForm({
        name: editingProperty.name,
        type: editingProperty.type,
        description: editingProperty.description ?? "",
        required: editingProperty.required,
        multiValued: editingProperty.multi_valued,
        enumValues: csv(editingProperty.enum_values),
      });
    }
  }, [editingProperty]);

  useEffect(() => {
    if (editingRelation) {
      setRelationForm({
        name: editingRelation.name,
        description: editingRelation.description ?? "",
        aliases: csv(editingRelation.aliases),
        sourceClassId: editingRelation.source_class_id,
        targetClassId: editingRelation.target_class_id,
        inverseName: editingRelation.inverse_name ?? "",
      });
    } else if (!relationForm.sourceClassId && props.classes[0]) {
      setRelationForm((current) => ({
        ...current,
        sourceClassId: props.classes[0].id,
        targetClassId: props.classes[0].id,
      }));
    }
  }, [editingRelation, props.classes, relationForm.sourceClassId]);

  function saveClass(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const body = {
        name: classForm.name,
        description: classForm.description || null,
        aliases: splitCsv(classForm.aliases),
        parent_class_ids: classForm.parents,
        external_mappings: selectedClass?.external_mappings ?? {},
      };
      if (selectedClass) {
        await props.request<ClassDef>(`/classes/${selectedClass.id}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        const created = await props.request<ClassDef>(`/ontologies/${props.ontologyId}/classes`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        props.setSelectedClassId(created.id);
      }
      setClassForm({ name: "", description: "", aliases: "", parents: [] });
      await props.reloadSchema();
    }, selectedClass ? "Class updated" : "Class created");
  }

  function saveProperty(event: FormEvent) {
    event.preventDefault();
    if (!selectedClass) return;
    props.mutate(async () => {
      const body = {
        name: propertyForm.name,
        type: propertyForm.type,
        description: propertyForm.description || null,
        required: propertyForm.required,
        multi_valued: propertyForm.multiValued,
        enum_values: splitCsv(propertyForm.enumValues),
        constraints: editingProperty?.constraints ?? {},
        external_mappings: editingProperty?.external_mappings ?? {},
      };
      if (editingProperty) {
        await props.request<PropertyDef>(`/properties/${editingProperty.id}`, { method: "PATCH", body: JSON.stringify(body) });
      } else {
        await props.request<PropertyDef>(`/classes/${selectedClass.id}/properties`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      setEditingProperty(null);
      setPropertyForm({ name: "", type: "string", description: "", required: false, multiValued: false, enumValues: "" });
      await props.reloadSchema();
    }, editingProperty ? "Property updated" : "Property created");
  }

  function saveRelationType(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const body = {
        name: relationForm.name,
        description: relationForm.description || null,
        aliases: splitCsv(relationForm.aliases),
        parent_relation_type_id: editingRelation?.parent_relation_type_id ?? null,
        source_class_id: relationForm.sourceClassId,
        target_class_id: relationForm.targetClassId,
        inverse_name: relationForm.inverseName || null,
        external_mappings: editingRelation?.external_mappings ?? {},
      };
      if (editingRelation) {
        await props.request<RelationType>(`/relation-types/${editingRelation.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        await props.request<RelationType>(`/ontologies/${props.ontologyId}/relation-types`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      setEditingRelation(null);
      setRelationForm({ name: "", description: "", aliases: "", sourceClassId: "", targetClassId: "", inverseName: "" });
      await props.reloadSchema();
    }, editingRelation ? "Relation type updated" : "Relation type created");
  }

  return (
    <section className={classNames("pageGrid", props.mode === "classes" ? "classDesignerGrid" : "relationTypesGrid")}>
      {props.mode === "classes" && (
        <>
          <Panel title="Class catalog" icon={<Box size={17} />}>
        <button
          className="secondaryButton fullWidth"
          onClick={() => {
            props.setSelectedClassId("");
            setClassForm({ name: "", description: "", aliases: "", parents: [] });
          }}
          type="button"
        >
          <Plus size={15} /> New class
        </button>
        <DataList
          empty="No classes"
          items={props.classes.map((classDef) => ({
            id: classDef.id,
            title: classDef.name,
            subtitle: classDef.normalized_label ?? compactId(classDef.id),
            selected: classDef.id === props.selectedClassId,
            onSelect: () => props.setSelectedClassId(classDef.id),
            meta: `${(props.propertiesByClass[classDef.id] ?? []).length} props`,
            actions: (
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
            ),
          }))}
        />
          </Panel>

          <Panel title={selectedClass ? "Edit class" : "Create class"} icon={<Settings size={17} />}>
        <form className="stackForm" onSubmit={saveClass}>
          <input
            required
            placeholder="Class name"
            value={classForm.name}
            onChange={(event) => setClassForm({ ...classForm, name: event.target.value })}
          />
          <textarea
            placeholder="Description"
            value={classForm.description}
            onChange={(event) => setClassForm({ ...classForm, description: event.target.value })}
          />
          <input
            placeholder="Aliases, comma separated"
            value={classForm.aliases}
            onChange={(event) => setClassForm({ ...classForm, aliases: event.target.value })}
          />
          <label>
            <span>Parent classes</span>
            <select
              multiple
              value={classForm.parents}
              onChange={(event) =>
                setClassForm({
                  ...classForm,
                  parents: Array.from(event.currentTarget.selectedOptions).map((option) => option.value),
                })
              }
            >
              {props.classes
                .filter((classDef) => classDef.id !== selectedClass?.id)
                .map((classDef) => (
                  <option key={classDef.id} value={classDef.id}>
                    {classDef.name}
                  </option>
                ))}
            </select>
          </label>
          <button className="primaryButton" disabled={!props.ontologyId} type="submit">
            <Save size={15} /> {selectedClass ? "Save class" : "Create class"}
          </button>
        </form>
          </Panel>

          <Panel title="Properties" icon={<Braces size={17} />}>
        <form className="stackForm" onSubmit={saveProperty}>
          <input
            required
            placeholder="Property name"
            value={propertyForm.name}
            onChange={(event) => setPropertyForm({ ...propertyForm, name: event.target.value })}
          />
          <div className="formPair">
            <select value={propertyForm.type} onChange={(event) => setPropertyForm({ ...propertyForm, type: event.target.value })}>
              {propertyTypes.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <input
              placeholder="Enum values"
              value={propertyForm.enumValues}
              onChange={(event) => setPropertyForm({ ...propertyForm, enumValues: event.target.value })}
            />
          </div>
          <textarea
            placeholder="Description"
            value={propertyForm.description}
            onChange={(event) => setPropertyForm({ ...propertyForm, description: event.target.value })}
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
              Multi-valued
            </label>
          </div>
          <div className="buttonRow">
            <button className="primaryButton" disabled={!selectedClass} type="submit">
              <Save size={15} /> {editingProperty ? "Save property" : "Add property"}
            </button>
            {editingProperty && (
              <button className="secondaryButton" onClick={() => setEditingProperty(null)} type="button">
                Cancel
              </button>
            )}
          </div>
        </form>
        <DataList
          empty="No properties for selected class"
          items={selectedProperties.map((property) => ({
            id: property.id,
            title: property.name,
            subtitle: `${property.type}${property.required ? " - required" : ""}${property.multi_valued ? " - multi" : ""}`,
            onSelect: () => setEditingProperty(property),
            selected: editingProperty?.id === property.id,
            actions: (
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
            ),
          }))}
        />
          </Panel>
        </>
      )}

      {props.mode === "relations" && (
        <>
          <Panel title="Relation type editor" icon={<GitBranch size={17} />}>
        <form className="stackForm" onSubmit={saveRelationType}>
          <input
            required
            placeholder="Relation type name"
            value={relationForm.name}
            onChange={(event) => setRelationForm({ ...relationForm, name: event.target.value })}
          />
          <input
            placeholder="Aliases"
            value={relationForm.aliases}
            onChange={(event) => setRelationForm({ ...relationForm, aliases: event.target.value })}
          />
          <textarea
            placeholder="Description"
            value={relationForm.description}
            onChange={(event) => setRelationForm({ ...relationForm, description: event.target.value })}
          />
          <div className="formPair">
            <label>
              <span>Source class</span>
              <select
                required
                value={relationForm.sourceClassId}
                onChange={(event) => setRelationForm({ ...relationForm, sourceClassId: event.target.value })}
              >
                <option value="">Source class</option>
                {props.classes.map((classDef) => (
                  <option key={classDef.id} value={classDef.id}>
                    {classDef.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Target class</span>
              <select
                required
                value={relationForm.targetClassId}
                onChange={(event) => setRelationForm({ ...relationForm, targetClassId: event.target.value })}
              >
                <option value="">Target class</option>
                {props.classes.map((classDef) => (
                  <option key={classDef.id} value={classDef.id}>
                    {classDef.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <input
            placeholder="Inverse name"
            value={relationForm.inverseName}
            onChange={(event) => setRelationForm({ ...relationForm, inverseName: event.target.value })}
          />
          <div className="buttonRow">
            <button className="primaryButton" disabled={!props.ontologyId || props.classes.length < 1} type="submit">
              <Save size={15} /> {editingRelation ? "Save relation type" : "Create relation type"}
            </button>
            {editingRelation && (
              <button className="secondaryButton" onClick={() => setEditingRelation(null)} type="button">
                Cancel
              </button>
            )}
          </div>
        </form>
          </Panel>

          <Panel title="Relation type catalog" icon={<Waypoints size={17} />}>
        <DataList
          empty="No relation types"
          items={props.relationTypes.map((relationType) => ({
            id: relationType.id,
            title: relationType.name,
            subtitle: `${nameFor(props.classes, relationType.source_class_id)} -> ${nameFor(
              props.classes,
              relationType.target_class_id,
            )}`,
            selected: editingRelation?.id === relationType.id,
            onSelect: () => setEditingRelation(relationType),
            actions: (
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
            ),
          }))}
        />
          </Panel>
        </>
      )}
    </section>
  );
}

function GraphWorkbenchPage(props: {
  ontologyId: string;
  classes: ClassDef[];
  relationTypes: RelationType[];
  entities: Entity[];
  relations: Relation[];
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadGraph: () => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [relationTypeFilter, setRelationTypeFilter] = useState("");
  const [entityFilter, setEntityFilter] = useState("");
  const [searchResult, setSearchResult] = useState<EntitySearchResult | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState("");
  const [entityDetail, setEntityDetail] = useState<EntityWithRelations | null>(null);
  const [related, setRelated] = useState<RelatedEntity[]>([]);
  const [explain, setExplain] = useState<EntityExplain | null>(null);
  const [entityForm, setEntityForm] = useState({ name: "", classId: "", aliases: "", properties: "{}" });
  const [relationForm, setRelationForm] = useState({ relationTypeId: "", sourceEntityId: "", targetEntityId: "", properties: "{}" });
  const [jsonError, setJsonError] = useState("");

  const visibleEntities = searchResult?.results ?? props.entities;
  const filteredRelations = props.relations.filter((relation) => {
    const matchesType = !relationTypeFilter || relation.relation_type_id === relationTypeFilter;
    const matchesEntity =
      !entityFilter || relation.source_entity_id === entityFilter || relation.target_entity_id === entityFilter;
    return matchesType && matchesEntity;
  });
  const selectedEntity = props.entities.find((entity) => entity.id === selectedEntityId) ?? visibleEntities[0] ?? null;

  useEffect(() => {
    if (!selectedEntityId && selectedEntity) setSelectedEntityId(selectedEntity.id);
  }, [selectedEntity, selectedEntityId]);

  useEffect(() => {
    if (!entityForm.classId && props.classes[0]) setEntityForm((current) => ({ ...current, classId: props.classes[0].id }));
  }, [props.classes, entityForm.classId]);

  useEffect(() => {
    if (!relationForm.relationTypeId && props.relationTypes[0]) {
      setRelationForm((current) => ({ ...current, relationTypeId: props.relationTypes[0].id }));
    }
  }, [props.relationTypes, relationForm.relationTypeId]);

  useEffect(() => {
    if (!selectedEntityId || !props.ontologyId) return;
    Promise.all([
      props.request<EntityWithRelations>(`/ontologies/${props.ontologyId}/entities/${selectedEntityId}`),
      props.request<RelatedEntity[]>(`/ontologies/${props.ontologyId}/entities/${selectedEntityId}/related?depth=1&direction=both&limit=20`),
    ])
      .then(([detail, relatedData]) => {
        setEntityDetail(detail);
        setRelated(relatedData);
      })
      .catch(() => {
        setEntityDetail(null);
        setRelated([]);
      });
  }, [selectedEntityId, props.ontologyId, props.request]);

  useEffect(() => {
    if (selectedEntity) {
      setEntityForm({
        name: selectedEntity.name,
        classId: selectedEntity.class_id,
        aliases: csv(selectedEntity.aliases),
        properties: prettyJson(selectedEntity.properties),
      });
    }
  }, [selectedEntity]);

  function searchEntities(event?: FormEvent) {
    event?.preventDefault();
    if (!props.ontologyId) return;
    props.mutate(async () => {
      const params = new URLSearchParams({ query, limit: "100" });
      if (classFilter) params.set("class_id", classFilter);
      const data = await props.request<EntitySearchResult>(
        `/ontologies/${props.ontologyId}/entities/search?${params.toString()}`,
      );
      setSearchResult(data);
      setSelectedEntityId(data.results[0]?.id ?? "");
    }, "Search completed");
  }

  function saveEntity(event: FormEvent) {
    event.preventDefault();
    setJsonError("");
    if (!props.ontologyId) return;
    props.mutate(async () => {
      const properties = parseJsonObject(entityForm.properties);
      const body = {
        name: entityForm.name,
        class_id: entityForm.classId,
        aliases: splitCsv(entityForm.aliases),
        properties,
      };
      if (selectedEntity) {
        await props.request<Entity>(`/ontologies/${props.ontologyId}/entities/${selectedEntity.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            name: body.name,
            aliases: body.aliases,
            properties: body.properties,
            ontology_version_id: selectedEntity.ontology_version_id,
          }),
        });
      } else {
        await props.request<Entity>(`/ontologies/${props.ontologyId}/entities`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      await props.reloadGraph();
      setSearchResult(null);
    }, selectedEntity ? "Entity updated" : "Entity created");
  }

  function createRelation(event: FormEvent) {
    event.preventDefault();
    setJsonError("");
    props.mutate(async () => {
      const properties = parseJsonObject(relationForm.properties);
      await props.request<Relation>(`/ontologies/${props.ontologyId}/relations`, {
        method: "POST",
        body: JSON.stringify({ ...snakeRelationForm(relationForm), properties }),
      });
      setRelationForm((current) => ({ ...current, properties: "{}" }));
      await props.reloadGraph();
    }, "Relation created");
  }

  async function explainSelected() {
    if (!selectedEntityId || !props.ontologyId) return;
    await props.mutate(async () => {
      const data = await props.request<EntityExplain>(`/ontologies/${props.ontologyId}/entities/${selectedEntityId}/explain`);
      setExplain(data);
    }, "Entity explanation loaded");
  }

  return (
    <section className="graphWorkbench">
      <div className="graphLeft">
        <Panel title="Entity search" icon={<Search size={17} />}>
          <form className="searchForm" onSubmit={searchEntities}>
            <input placeholder="Keyword" value={query} onChange={(event) => setQuery(event.target.value)} />
            <select value={classFilter} onChange={(event) => setClassFilter(event.target.value)}>
              <option value="">All classes</option>
              {props.classes.map((classDef) => (
                <option key={classDef.id} value={classDef.id}>
                  {classDef.name}
                </option>
              ))}
            </select>
            <button className="primaryButton" type="submit">
              <Search size={15} /> Search
            </button>
            <button className="secondaryButton" onClick={() => setSearchResult(null)} type="button">
              Clear
            </button>
          </form>
          <DataList
            empty="No entities"
            items={visibleEntities.map((entity) => ({
              id: entity.id,
              title: entity.name,
              subtitle: entity.class_label,
              selected: entity.id === selectedEntityId,
              onSelect: () => setSelectedEntityId(entity.id),
              meta: compactId(entity.id),
              actions: (
                <button
                  className="iconButton danger"
                  onClick={() =>
                    props.mutate(async () => {
                      await props.request<void>(`/ontologies/${props.ontologyId}/entities/${entity.id}`, { method: "DELETE" });
                      await props.reloadGraph();
                    }, "Entity deleted")
                  }
                  title="Delete entity"
                  type="button"
                >
                  <Trash2 size={15} />
                </button>
              ),
            }))}
          />
        </Panel>

        <Panel title="Entity editor" icon={<Database size={17} />}>
          <button
            className="secondaryButton fullWidth"
            onClick={() => {
              setSelectedEntityId("");
              setEntityForm({ name: "", classId: props.classes[0]?.id ?? "", aliases: "", properties: "{}" });
            }}
            type="button"
          >
            <Plus size={15} /> New entity
          </button>
          <form className="stackForm" onSubmit={saveEntity}>
            <input required placeholder="Entity name" value={entityForm.name} onChange={(event) => setEntityForm({ ...entityForm, name: event.target.value })} />
            <select required value={entityForm.classId} onChange={(event) => setEntityForm({ ...entityForm, classId: event.target.value })}>
              <option value="">Class</option>
              {props.classes.map((classDef) => (
                <option key={classDef.id} value={classDef.id}>
                  {classDef.name}
                </option>
              ))}
            </select>
            <input placeholder="Aliases" value={entityForm.aliases} onChange={(event) => setEntityForm({ ...entityForm, aliases: event.target.value })} />
            <textarea className="codeArea" value={entityForm.properties} onChange={(event) => setEntityForm({ ...entityForm, properties: event.target.value })} />
            <ErrorText message={jsonError} />
            <button className="primaryButton" disabled={!props.ontologyId || !props.classes.length} type="submit">
              <Save size={15} /> {selectedEntity ? "Save entity" : "Create entity"}
            </button>
          </form>
        </Panel>
      </div>

      <Panel title="Graph map" icon={<Network size={17} />} className="graphCenter">
        <GraphMap
          entities={props.entities}
          relations={filteredRelations}
          selectedEntityId={selectedEntityId}
          setSelectedEntityId={setSelectedEntityId}
        />
      </Panel>

      <div className="graphRight">
        <Panel title="Relation filters" icon={<Link2 size={17} />}>
          <div className="stackForm">
            <select value={entityFilter} onChange={(event) => setEntityFilter(event.target.value)}>
              <option value="">Any entity</option>
              {props.entities.map((entity) => (
                <option key={entity.id} value={entity.id}>
                  {entity.name}
                </option>
              ))}
            </select>
            <select value={relationTypeFilter} onChange={(event) => setRelationTypeFilter(event.target.value)}>
              <option value="">Any relation type</option>
              {props.relationTypes.map((relationType) => (
                <option key={relationType.id} value={relationType.id}>
                  {relationType.name}
                </option>
              ))}
            </select>
          </div>
          <DataList
            empty="No matching relations"
            items={filteredRelations.map((relation) => ({
              id: relation.id,
              title: relation.relation_type,
              subtitle: `${nameFor(props.entities, relation.source_entity_id)} -> ${nameFor(
                props.entities,
                relation.target_entity_id,
              )}`,
              meta: "read-only",
              actions: (
                <button className="iconButton" disabled title="Relation update API pending" type="button">
                  <Settings size={15} />
                </button>
              ),
            }))}
          />
        </Panel>

        <Panel title="Create relation" icon={<GitBranch size={17} />}>
          <form className="stackForm" onSubmit={createRelation}>
            <select required value={relationForm.relationTypeId} onChange={(event) => setRelationForm({ ...relationForm, relationTypeId: event.target.value })}>
              <option value="">Relation type</option>
              {props.relationTypes.map((relationType) => (
                <option key={relationType.id} value={relationType.id}>
                  {relationType.name}
                </option>
              ))}
            </select>
            <select required value={relationForm.sourceEntityId} onChange={(event) => setRelationForm({ ...relationForm, sourceEntityId: event.target.value })}>
              <option value="">Source entity</option>
              {props.entities.map((entity) => (
                <option key={entity.id} value={entity.id}>
                  {entity.name}
                </option>
              ))}
            </select>
            <select required value={relationForm.targetEntityId} onChange={(event) => setRelationForm({ ...relationForm, targetEntityId: event.target.value })}>
              <option value="">Target entity</option>
              {props.entities.map((entity) => (
                <option key={entity.id} value={entity.id}>
                  {entity.name}
                </option>
              ))}
            </select>
            <textarea className="codeArea small" value={relationForm.properties} onChange={(event) => setRelationForm({ ...relationForm, properties: event.target.value })} />
            <button className="primaryButton" disabled={!props.ontologyId || props.entities.length < 2 || !props.relationTypes.length} type="submit">
              <Plus size={15} /> Create relation
            </button>
          </form>
        </Panel>

        <Panel title="Entity context" icon={<Clipboard size={17} />}>
          {entityDetail ? (
            <div className="inspector">
              <h2>{entityDetail.name}</h2>
              <p>{entityDetail.class_label}</p>
              <dl className="detailList">
                <dt>Outgoing</dt>
                <dd>{entityDetail.outgoing.length}</dd>
                <dt>Incoming</dt>
                <dd>{entityDetail.incoming.length}</dd>
                <dt>Related</dt>
                <dd>{related.length}</dd>
              </dl>
              <pre className="jsonBlock">{prettyJson(entityDetail.properties)}</pre>
              <button className="secondaryButton fullWidth" onClick={explainSelected} type="button">
                <Clipboard size={15} /> Explain entity
              </button>
              {explain && <pre className="jsonBlock">{explain.explain_text}</pre>}
            </div>
          ) : (
            <EmptyState icon={<Database size={20} />} title="Select an entity" />
          )}
        </Panel>
      </div>
    </section>
  );
}

function snakeRelationForm(form: { relationTypeId: string; sourceEntityId: string; targetEntityId: string }) {
  return {
    relation_type_id: form.relationTypeId,
    source_entity_id: form.sourceEntityId,
    target_entity_id: form.targetEntityId,
  };
}

function GraphMap(props: {
  entities: Entity[];
  relations: Relation[];
  selectedEntityId: string;
  setSelectedEntityId: (id: string) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const nodes = useMemo(() => {
    const count = Math.max(props.entities.length, 1);
    const radiusX = Math.max(170, Math.min(360, 100 + count * 15));
    const radiusY = Math.max(120, Math.min(240, 80 + count * 10));
    return props.entities.map((entity, index) => {
      const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
      return { entity, x: 430 + Math.cos(angle) * radiusX, y: 280 + Math.sin(angle) * radiusY };
    });
  }, [props.entities]);
  const byId = new Map(nodes.map((node) => [node.entity.id, node]));

  if (!props.entities.length) {
    return <EmptyState icon={<Network size={24} />} title="No graph data" />;
  }

  function boundedZoom(next: number) {
    setZoom(Math.min(1.8, Math.max(0.55, Number(next.toFixed(2)))));
  }

  return (
    <div className="graphExplorer">
      <div className="graphToolbar">
        <div className="graphStats">
          <strong>{props.entities.length}</strong><span>entities</span>
          <strong>{props.relations.length}</strong><span>relations</span>
        </div>
        <div className="buttonRow">
          <button className="iconButton" onClick={() => boundedZoom(zoom - 0.15)} title="Zoom out" type="button"><ZoomOut size={15} /></button>
          <span className="zoomValue">{Math.round(zoom * 100)}%</span>
          <button className="iconButton" onClick={() => boundedZoom(zoom + 0.15)} title="Zoom in" type="button"><ZoomIn size={15} /></button>
          <button className="iconButton" onClick={() => setZoom(1)} title="Reset" type="button"><Maximize2 size={15} /></button>
        </div>
      </div>
      <svg className="graphSvg" viewBox="0 0 860 560" role="img" aria-label="Knowledge graph">
        <defs>
          <marker id="arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="4">
            <path d="M0,0 L8,4 L0,8 Z" fill="#52616b" />
          </marker>
        </defs>
        <g transform={`translate(${430 - 430 * zoom} ${280 - 280 * zoom}) scale(${zoom})`}>
          {props.relations.map((relation) => {
            const source = byId.get(relation.source_entity_id);
            const target = byId.get(relation.target_entity_id);
            if (!source || !target) return null;
            const highlighted = relation.source_entity_id === props.selectedEntityId || relation.target_entity_id === props.selectedEntityId;
            return (
              <g className={classNames("edgeGroup", highlighted && "selected")} key={relation.id}>
                <line className="edge" markerEnd="url(#arrow)" x1={source.x} x2={target.x} y1={source.y} y2={target.y} />
                <text className="edgeLabel" x={(source.x + target.x) / 2} y={(source.y + target.y) / 2 - 8}>
                  {relation.relation_type}
                </text>
              </g>
            );
          })}
          {nodes.map((node) => {
            const selected = node.entity.id === props.selectedEntityId;
            return (
              <g
                className={classNames("graphNode", selected && "selected")}
                key={node.entity.id}
                onClick={() => props.setSelectedEntityId(node.entity.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") props.setSelectedEntityId(node.entity.id);
                }}
                role="button"
                tabIndex={0}
              >
                <circle className="node" cx={node.x} cy={node.y} r="40" />
                <text className="nodeTitle" x={node.x} y={node.y - 5}>{node.entity.name.slice(0, 18)}</text>
                <text className="nodeMeta" x={node.x} y={node.y + 15}>{node.entity.class_label.slice(0, 22)}</text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

function ImportExportPage(props: {
  project: Project | null;
  ontology: Ontology | null;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadOntologies: (projectId?: string) => Promise<void>;
}) {
  const [fileName, setFileName] = useState("");
  const [payload, setPayload] = useState<OntologyExport | null>(null);

  async function exportOntology() {
    if (!props.ontology) return;
    await props.mutate(async () => {
      const data = await props.request<OntologyExport>(`/ontologies/${props.ontology!.id}/export`);
      downloadJson(`${props.ontology!.name.replace(/\s+/g, "-").toLowerCase()}-ontology.json`, data);
    }, "Ontology exported");
  }

  function readFile(file: File | null) {
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      try {
        setPayload(JSON.parse(String(reader.result)) as OntologyExport);
      } catch {
        setPayload(null);
      }
    };
    reader.readAsText(file);
  }

  async function importOntology() {
    if (!props.project || !payload) return;
    await props.mutate(async () => {
      await props.request<OntologyExport>(`/projects/${props.project!.id}/ontologies/import`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await props.reloadOntologies(props.project!.id);
      setPayload(null);
      setFileName("");
    }, "Ontology imported");
  }

  return (
    <section className="pageGrid importGrid">
      <Panel title="Export current ontology" icon={<Download size={17} />}>
        <div className="overview">
          <h2>{props.ontology?.name ?? "No ontology selected"}</h2>
          <p>Export schema, entities, and relations as the backend JSON import shape.</p>
          <button className="primaryButton" disabled={!props.ontology} onClick={exportOntology} type="button">
            <Download size={15} /> Download JSON
          </button>
        </div>
      </Panel>
      <Panel title="Import into project" icon={<Upload size={17} />}>
        <div className="stackForm">
          <label>
            <span>Target project</span>
            <input readOnly value={props.project?.name ?? "Select a project first"} />
          </label>
          <label className="filePicker">
            <FileJson size={18} />
            <span>{fileName || "Choose ontology JSON"}</span>
            <input accept="application/json,.json" onChange={(event) => readFile(event.target.files?.[0] ?? null)} type="file" />
          </label>
          {payload && (
            <div className="callout">
              <strong>{payload.ontology?.name ?? "Unnamed ontology"}</strong>
              <span>
                {payload.classes?.length ?? 0} classes, {payload.entities?.length ?? 0} entities, {payload.relations?.length ?? 0} relations
              </span>
            </div>
          )}
          <button className="primaryButton" disabled={!props.project || !payload} onClick={importOntology} type="button">
            <Upload size={15} /> Import JSON
          </button>
        </div>
      </Panel>
      <Panel title="Import preview" icon={<FileJson size={17} />} wide>
        {payload ? <pre className="jsonBlock tall">{prettyJson(payload)}</pre> : <EmptyState icon={<FileJson size={22} />} title="No file selected" />}
      </Panel>
    </section>
  );
}

function AgentLabPage(props: {
  ontology: Ontology | null;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
}) {
  const [mode, setMode] = useState<"agent" | "mcp">("agent");
  const [question, setQuestion] = useState("");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [temperature, setTemperature] = useState("0.2");
  const [result, setResult] = useState<AgentTestResponse | null>(null);

  function run(event: FormEvent) {
    event.preventDefault();
    if (!props.ontology) return;
    props.mutate(async () => {
      const response = await props.request<AgentTestResponse>("/agent-test/run", {
        method: "POST",
        body: JSON.stringify({
          ontology_id: props.ontology!.id,
          question,
          model: model || null,
          base_url: baseUrl || null,
          temperature: temperature ? Number(temperature) : null,
        }),
      });
      setResult(response);
    }, "Agent test completed");
  }

  return (
    <section className="agentLayout">
      <Panel title="Lab controls" icon={<Play size={17} />}>
        <div className="segmented">
          <button className={classNames(mode === "agent" && "active")} onClick={() => setMode("agent")} type="button">Agent Test</button>
          <button className={classNames(mode === "mcp" && "active")} onClick={() => setMode("mcp")} type="button">MCP Tools</button>
        </div>
        {mode === "agent" ? (
          <form className="stackForm" onSubmit={run}>
            <textarea
              className="questionBox"
              required
              placeholder="Ask a question against the selected ontology"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />
            <input placeholder="Model override" value={model} onChange={(event) => setModel(event.target.value)} />
            <input placeholder="OpenAI-compatible base URL" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
            <input
              max="2"
              min="0"
              step="0.1"
              type="number"
              value={temperature}
              onChange={(event) => setTemperature(event.target.value)}
            />
            <button className="primaryButton" disabled={!props.ontology} type="submit">
              <Play size={15} /> Run
            </button>
          </form>
        ) : (
          <div className="toolList">
            {["search_entities", "get_entity", "find_related_entities", "validate_entity", "explain_entity"].map((tool) => (
              <div className="toolRow" key={tool}>
                <div>
                  <strong>{tool}</strong>
                  <span>HTTP/MCP tool browser pending frontend bridge</span>
                </div>
                <button className="secondaryButton" disabled type="button">Open</button>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Run output" icon={<Clipboard size={17} />} className="agentOutput">
        {result ? (
          <div className="resultGrid">
            <ResultBlock title="Answer" value={result.answer} />
            <Timeline title="Tool calls" items={result.tool_calls} />
            <ResultBlock title="Graph context" value={result.graph_context} copyable />
            <ResultBlock title="Prompt preview" value={result.prompt_preview} />
            <ResultBlock title="Warnings" value={result.warnings} />
            <ResultBlock title="Errors" value={result.errors} />
          </div>
        ) : (
          <EmptyState icon={<Send size={22} />} title="No run output yet" />
        )}
      </Panel>
    </section>
  );
}

function SystemPage(props: {
  health: Health | null;
  token: string;
  saveToken: (value: string) => void;
  request: Requester;
  setHealth: (health: Health | null) => void;
  showError: (error: unknown) => void;
}) {
  async function checkHealth() {
    try {
      props.setHealth(await props.request<Health>("/health/dependencies"));
    } catch (error) {
      props.showError(error);
    }
  }

  return (
    <section className="pageGrid systemGrid">
      <Panel title="Admin token" icon={<Shield size={17} />}>
        <div className="stackForm">
          <label>
            <span>Bearer token</span>
            <input
              aria-label="Admin token"
              autoComplete="off"
              onChange={(event) => props.saveToken(event.target.value)}
              placeholder="Paste admin token"
              type="password"
              value={props.token}
            />
          </label>
          <div className="callout quiet">
            <strong>{props.token ? "Token stored locally" : "Token missing"}</strong>
            <span>The value is saved in browser localStorage and sent as the Authorization bearer token.</span>
          </div>
        </div>
      </Panel>
      <Panel title="Connection" icon={<Activity size={17} />}>
        <dl className="detailList">
          <dt>API base URL</dt>
          <dd><code>{API_BASE_URL}</code></dd>
          <dt>Token</dt>
          <dd>{props.token ? "Stored for local session" : "Missing"}</dd>
        </dl>
      </Panel>
      <Panel title="Dependencies" icon={<Activity size={17} />}>
        <button className="primaryButton" onClick={checkHealth} type="button">
          <RefreshCw size={15} /> Check dependencies
        </button>
        {props.health ? <pre className="jsonBlock">{prettyJson(props.health)}</pre> : <EmptyState icon={<Activity size={20} />} title="No health check yet" />}
      </Panel>
      <Panel title="Operational boundaries" icon={<Settings size={17} />} wide>
        <div className="boundaryGrid">
          <Boundary title="Authentication" text="Shared admin token only; no user/RBAC UI is implemented." />
          <Boundary title="Versioning" text="Stored version metadata is visible, but publishing is backend-pending." />
          <Boundary title="Relations" text="Relations can be created and listed; update/delete endpoints are not exposed." />
          <Boundary title="MCP" text="Agent Test is HTTP-backed; a dedicated MCP tool browser is reserved." />
        </div>
      </Panel>
    </section>
  );
}

function Panel(props: { title: string; icon: ReactNode; children: ReactNode; wide?: boolean; className?: string }) {
  return (
    <Card
      className={classNames("panel", props.wide && "wide", props.className)}
      title={
        <div className="panelHeaderTitle">
          {props.icon}
          <h2>{props.title}</h2>
        </div>
      }
      bordered={false}
    >
      <header className="panelHeader" aria-hidden="true">
        <div>
          {props.icon}
          <h2>{props.title}</h2>
        </div>
      </header>
      {props.children}
    </Card>
  );
}

function Metric(props: { label: string; value: number; icon: ReactNode }) {
  return (
    <div className="metric">
      <div>{props.icon}</div>
      <strong>{props.value}</strong>
      <span>{props.label}</span>
    </div>
  );
}

function Badge(props: { children: ReactNode }) {
  return <Tag color="success">{props.children}</Tag>;
}

function StatusBanner(props: { notice: NonNullable<Notice>; onDismiss: () => void }) {
  return (
    <div className={classNames("notice", props.notice.kind)}>
      <span>{props.notice.kind === "ok" ? <Check size={16} /> : <X size={16} />}</span>
      <p>{props.notice.message}</p>
      <button className="iconButton subtle" onClick={props.onDismiss} title="Dismiss" type="button">
        <X size={14} />
      </button>
    </div>
  );
}

function EmptyState(props: { icon: ReactNode; title: string }) {
  return (
    <div className="emptyState">
      {props.icon}
      <span>{props.title}</span>
    </div>
  );
}

function ErrorText({ message }: { message?: string | null }) {
  if (!message) return null;
  return <div className="inlineError">{message}</div>;
}

function DataList(props: {
  items: Array<{
    id: string;
    title: string;
    subtitle: string;
    meta?: string;
    selected?: boolean;
    onSelect?: () => void;
    actions?: ReactNode;
  }>;
  empty: string;
}) {
  if (!props.items.length) return <EmptyState icon={<Database size={20} />} title={props.empty} />;
  return (
    <div className="dataList">
      {props.items.map((item) => (
        <div className={classNames("dataRow", item.selected && "selected")} key={item.id}>
          <button className="rowContent" onClick={item.onSelect} type="button">
            <strong>{item.title}</strong>
            <span>{item.subtitle}</span>
          </button>
          {item.meta && <code>{item.meta}</code>}
          {item.actions && <div className="rowActions">{item.actions}</div>}
        </div>
      ))}
    </div>
  );
}

function ResultBlock(props: { title: string; value: unknown; copyable?: boolean }) {
  const rendered = typeof props.value === "string" ? props.value : prettyJson(props.value);
  return (
    <section className="resultBlock">
      <header>
        <h3>{props.title}</h3>
        {props.copyable && (
          <button className="iconButton" onClick={() => navigator.clipboard.writeText(rendered)} title="Copy" type="button">
            <Clipboard size={14} />
          </button>
        )}
      </header>
      <pre className="jsonBlock">{rendered}</pre>
    </section>
  );
}

function Timeline(props: { title: string; items: JsonObject[] }) {
  return (
    <section className="resultBlock">
      <h3>{props.title}</h3>
      <div className="timeline">
        {props.items.length ? (
          props.items.map((item, index) => (
            <div className="timelineItem" key={`${index}-${JSON.stringify(item).slice(0, 24)}`}>
              <span>{index + 1}</span>
              <pre>{prettyJson(item)}</pre>
            </div>
          ))
        ) : (
          <span className="muted">No tool calls</span>
        )}
      </div>
    </section>
  );
}

function Boundary(props: { title: string; text: string }) {
  return (
    <div className="boundary">
      <strong>{props.title}</strong>
      <span>{props.text}</span>
    </div>
  );
}
