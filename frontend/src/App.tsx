import dagre from "@dagrejs/dagre";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Activity,
  ArrowLeft,
  Box,
  Braces,
  Check,
  ChevronRight,
  Clipboard,
  Database,
  GitBranch,
  Layers,
  Link2,
  Loader2,
  Network,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  Settings,
  Trash2,
  Waypoints,
  Wrench,
  X,
} from "lucide-react";
import { Card, ConfigProvider, Tag, Tooltip } from "antd";
import "antd/dist/reset.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties, FormEvent, ReactNode } from "react";
import { API_BASE_URL, apiRequest, errorNotice } from "./api";
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
  formatDate,
  nameFor,
  parseJsonObject,
  prettyJson,
  propertyTypes,
  splitCsv,
} from "./utils";
import { EntityGraphCanvas, pickColor } from "./components/EntityGraphCanvas";
import { EntityDetailDrawer } from "./components/EntityDetailDrawer";

type AppView = "home" | "workspace";
type WorkspaceTab =
  | "topology"
  | "classes"
  | "entities"
  | "entities-search"
  | "agent-test"
  | "mcp-tools"
  | "setting";
type ClassPageMode = "topology" | "create" | "edit";
type Requester = <T,>(path: string, options?: RequestInit) => Promise<T>;
type ParentClassPickerProps = {
  classes: ClassDef[];
  excludedClassId?: string;
  selectedIds: string[];
  onChange: (ids: string[]) => void;
};
type ClassNodeData = {
  label: string;
  description: string;
  propertyCount: number;
  relationCount: number;
};

const UI_KEYS = {
  project: "ontology-platform-ui-selected-project",
  ontology: "ontology-platform-ui-selected-ontology",
  workspaceTab: "ontology-platform-ui-workspace-tab-v3",
} as const;

const workspaceTabs: Array<{
  id: WorkspaceTab;
  label: string;
  detail: string;
  icon: typeof Network;
}> = [
  { id: "topology", label: "Topology", detail: "Reserved canvas", icon: Network },
  { id: "classes", label: "Classes", detail: "Class topology", icon: Box },
  { id: "entities", label: "Entities", detail: "Entity editor", icon: Database },
  { id: "entities-search", label: "Entities Search", detail: "Retrieval tests", icon: Search },
  { id: "agent-test", label: "Agent Test", detail: "Question runs", icon: Send },
  { id: "mcp-tools", label: "MCP Tools", detail: "Tool catalog", icon: Wrench },
  { id: "setting", label: "Setting", detail: "Runtime status", icon: Settings },
];

function isWorkspaceTab(value: string | null): value is WorkspaceTab {
  return workspaceTabs.some((tab) => tab.id === value);
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
      // Local storage is optional in embedded previews.
    }
  }, [key, value]);

  return [value, setValue] as const;
}

function useStoredWorkspaceTab(key: string, fallback: WorkspaceTab) {
  const [value, setValue] = useState<WorkspaceTab>(() => {
    try {
      const stored = localStorage.getItem(key);
      return isWorkspaceTab(stored) ? stored : fallback;
    } catch {
      return fallback;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Local storage is optional in embedded previews.
    }
  }, [key, value]);

  return [value, setValue] as const;
}

function classDepth(classDef: ClassDef, byId: Map<string, ClassDef>, seen = new Set<string>()): number {
  if (!classDef.parent_class_ids.length) return 0;
  if (seen.has(classDef.id)) return 0;
  seen.add(classDef.id);
  return (
    1 +
    Math.max(
      ...classDef.parent_class_ids.map((parentId) => {
        const parent = byId.get(parentId);
        return parent ? classDepth(parent, byId, new Set(seen)) : 0;
      }),
    )
  );
}

function ParentClassPicker(props: ParentClassPickerProps) {
  const byId = useMemo(() => new Map(props.classes.map((classDef) => [classDef.id, classDef])), [props.classes]);
  const orderedClasses = useMemo(() => {
    return [...props.classes]
      .filter((classDef) => classDef.id !== props.excludedClassId)
      .sort((first, second) => {
        const depthDelta = classDepth(first, byId) - classDepth(second, byId);
        return depthDelta || first.name.localeCompare(second.name);
      });
  }, [props.classes, props.excludedClassId, byId]);

  function toggleParent(id: string) {
    if (props.selectedIds.includes(id)) {
      props.onChange(props.selectedIds.filter((item) => item !== id));
      return;
    }
    props.onChange([...props.selectedIds, id]);
  }

  if (!orderedClasses.length) {
    return <div className="parentPickerEmpty">No other classes available</div>;
  }

  return (
    <div className="parentPicker">
      {orderedClasses.map((classDef) => {
        const selected = props.selectedIds.includes(classDef.id);
        const depth = classDepth(classDef, byId);
        return (
          <button
            className={classNames("parentOption", selected && "selected")}
            key={classDef.id}
            onClick={() => toggleParent(classDef.id)}
            style={{ "--level": depth } as CSSProperties}
            type="button"
          >
            <span className="parentOptionMain">
              <span className="parentOptionLevel">L{depth}</span>
              <strong>{classDef.name}</strong>
              <span>{classDef.description || classDef.normalized_label || compactId(classDef.id)}</span>
            </span>
            <span className="parentOptionState">{selected ? <Check size={14} /> : <Plus size={14} />}</span>
          </button>
        );
      })}
    </div>
  );
}

export function App() {
  const [view, setView] = useState<AppView>("home");
  const [workspaceTab, setWorkspaceTab] = useStoredWorkspaceTab(UI_KEYS.workspaceTab, "classes");
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
  const [selectedClassId, setSelectedClassId] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(false);

  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const selectedOntology = ontologies.find((ontology) => ontology.id === selectedOntologyId) ?? null;
  const activeTab = workspaceTabs.find((tab) => tab.id === workspaceTab) ?? workspaceTabs[0];

  const request = useCallback(<T,>(path: string, options?: RequestInit) => apiRequest<T>(path, options), []);
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
        current && data.some((ontology) => ontology.id === current) ? current : "",
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
        current && classData.some((classDef) => classDef.id === current) ? current : "",
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

  useEffect(() => {
    if (view === "workspace" && selectedOntologyId && !selectedOntology && ontologies.length) {
      setView("home");
    }
  }, [view, selectedOntologyId, selectedOntology, ontologies.length]);

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

  function openOntology(ontology: Ontology) {
    setSelectedOntologyId(ontology.id);
    setSelectedClassId("");
    setWorkspaceTab("classes");
    setView("workspace");
  }

  return (
    <ConfigProvider
      theme={{
        token: {
          borderRadius: 8,
          colorInfo: "#2fbf8f",
          colorPrimary: "#6c4df6",
          colorText: "#151722",
          fontFamily:
            "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
      }}
    >
      {view === "home" ? (
        <main className="homeShell">
          <header className="homeTopBar">
            <div>
              <span className="eyebrow">Ontology workspace</span>
              <h1>Ontologies</h1>
              <div className="crumbTrail">
                <span>{selectedProject?.name ?? "No project"}</span>
                <ChevronRight size={13} />
                <span>{ontologies.length} ontologies</span>
              </div>
            </div>
            <Tooltip title="Refresh workspace data">
              <button className="iconButton" disabled={loading} onClick={refreshAll} type="button">
                {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
              </button>
            </Tooltip>
          </header>
          {notice && <StatusBanner notice={notice} onDismiss={() => setNotice(null)} />}
          <OntologyHomePage
            mutate={mutate}
            onOpenOntology={openOntology}
            ontologies={ontologies}
            projects={projects}
            reloadOntologies={loadOntologies}
            reloadProjects={loadProjects}
            request={request}
            selectedOntologyId={selectedOntologyId}
            selectedProjectId={selectedProjectId}
            setSelectedOntologyId={setSelectedOntologyId}
            setSelectedProjectId={(projectId) => {
              setSelectedProjectId(projectId);
              setSelectedOntologyId("");
            }}
          />
        </main>
      ) : (
        <main className="appShell">
          <aside className="rail">
            <button className="brandMark brandButton" onClick={() => setView("home")} type="button">
              <Network size={22} />
              <div>
                <strong>Ontology Platform</strong>
                <span>Back to ontology list</span>
              </div>
            </button>
            <nav className="mainNav" aria-label="Ontology workspace navigation">
              {workspaceTabs.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    className={classNames("navButton", workspaceTab === item.id && "active")}
                    key={item.id}
                    onClick={() => setWorkspaceTab(item.id)}
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
                <span className="eyebrow">Ontology workspace</span>
                <h1>{activeTab.label}</h1>
                <div className="crumbTrail">
                  <button className="crumbButton" onClick={() => setView("home")} type="button">
                    {selectedProject?.name ?? "Projects"}
                  </button>
                  <ChevronRight size={13} />
                  <span>{selectedOntology?.name ?? "No ontology"}</span>
                  <ChevronRight size={13} />
                  <span>{activeTab.label}</span>
                </div>
              </div>
              <div className="topActions">
                <button className="secondaryButton" onClick={() => setView("home")} type="button">
                  <ArrowLeft size={15} /> Ontologies
                </button>
                <Tooltip title="Refresh ontology data">
                  <button
                    className="iconButton"
                    disabled={loading}
                    onClick={() => Promise.all([loadSchema(), loadGraph()]).catch(showError)}
                    type="button"
                  >
                    {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
                  </button>
                </Tooltip>
              </div>
            </header>

            {notice && <StatusBanner notice={notice} onDismiss={() => setNotice(null)} />}

            <div className="contentFrame">
              {!selectedOntology ? (
                <EmptyState icon={<Waypoints size={22} />} title="Select an ontology from the home page" />
              ) : (
                <WorkspaceContent
                  classes={classes}
                  entities={entities}
                  health={health}
                  mutate={mutate}
                  ontology={selectedOntology}
                  propertiesByClass={propertiesByClass}
                  relations={relations}
                  relationTypes={relationTypes}
                  request={request}
                  reloadGraph={loadGraph}
                  reloadSchema={loadSchema}
                  selectedClassId={selectedClassId}
                  setHealth={setHealth}
                  setSelectedClassId={setSelectedClassId}
                  showError={showError}
                  tab={workspaceTab}
                />
              )}
            </div>
          </section>
        </main>
      )}
    </ConfigProvider>
  );
}

function OntologyHomePage(props: {
  projects: Project[];
  ontologies: Ontology[];
  selectedProjectId: string;
  selectedOntologyId: string;
  setSelectedProjectId: (id: string) => void;
  setSelectedOntologyId: (id: string) => void;
  onOpenOntology: (ontology: Ontology) => void;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadProjects: () => Promise<void>;
  reloadOntologies: (projectId?: string) => Promise<void>;
}) {
  const [projectForm, setProjectForm] = useState({ name: "", description: "" });
  const [ontologyForm, setOntologyForm] = useState({ name: "", description: "" });
  const selectedProject = props.projects.find((project) => project.id === props.selectedProjectId) ?? null;

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

  function deleteOntology(ontology: Ontology) {
    props.mutate(async () => {
      await props.request<void>(`/ontologies/${ontology.id}`, { method: "DELETE" });
      if (props.selectedOntologyId === ontology.id) props.setSelectedOntologyId("");
      await props.reloadOntologies(props.selectedProjectId);
    }, "Ontology deleted");
  }

  return (
    <section className="homeLayout">
      <div className="homePrimary">
        <div className="homeFilterBar">
          <label>
            <span>Project</span>
            <select
              value={props.selectedProjectId}
              onChange={(event) => props.setSelectedProjectId(event.target.value)}
            >
              {props.projects.length ? (
                props.projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))
              ) : (
                <option value="">No projects</option>
              )}
            </select>
          </label>
        </div>

        {props.ontologies.length ? (
          <div className="ontologyCardGrid homeOntologyGrid">
            {props.ontologies.map((ontology) => (
              <article
                className={classNames("ontologyCard", ontology.id === props.selectedOntologyId && "selected")}
                key={ontology.id}
              >
                <button className="ontologyCardMain" onClick={() => props.onOpenOntology(ontology)} type="button">
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
                <button
                  className="iconButton danger ontologyCardDelete"
                  onClick={() => deleteOntology(ontology)}
                  title="Delete ontology"
                  type="button"
                >
                  <Trash2 size={15} />
                </button>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState icon={<Waypoints size={22} />} title="No ontologies in this project" />
        )}
      </div>

      <aside className="homeSide">
        <Panel title="Add ontology" icon={<Plus size={17} />}>
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
            <span>New ontologies are created inside the selected project.</span>
          </div>
        </Panel>

        {!props.projects.length && (
          <Panel title="Create project" icon={<Layers size={17} />}>
            <form className="stackForm" onSubmit={createProject}>
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
        )}
      </aside>
    </section>
  );
}

function WorkspaceContent(props: {
  tab: WorkspaceTab;
  ontology: Ontology;
  classes: ClassDef[];
  relationTypes: RelationType[];
  propertiesByClass: Record<string, PropertyDef[]>;
  selectedClassId: string;
  setSelectedClassId: (id: string) => void;
  entities: Entity[];
  relations: Relation[];
  health: Health | null;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadSchema: () => Promise<void>;
  reloadGraph: () => Promise<void>;
  setHealth: (health: Health | null) => void;
  showError: (error: unknown) => void;
}) {
  if (props.tab === "topology") {
    return (
      <section className="reservedTopology">
        <Panel title="Topology" icon={<Network size={17} />} wide>
          <EmptyState icon={<Network size={24} />} title="Topology canvas reserved" />
        </Panel>
      </section>
    );
  }

  if (props.tab === "classes") {
    return (
      <ClassesPage
        classes={props.classes}
        mutate={props.mutate}
        ontologyId={props.ontology.id}
        propertiesByClass={props.propertiesByClass}
        relationTypes={props.relationTypes}
        reloadSchema={props.reloadSchema}
        request={props.request}
        selectedClassId={props.selectedClassId}
        setSelectedClassId={props.setSelectedClassId}
      />
    );
  }

  if (props.tab === "entities") {
    return (
      <EntitiesPage
        classes={props.classes}
        entities={props.entities}
        mutate={props.mutate}
        ontologyId={props.ontology.id}
        relations={props.relations}
        relationTypes={props.relationTypes}
        reloadGraph={props.reloadGraph}
        request={props.request}
      />
    );
  }

  if (props.tab === "entities-search") {
    return <EntitiesSearchPage classes={props.classes} ontologyId={props.ontology.id} request={props.request} />;
  }

  if (props.tab === "agent-test") {
    return <AgentTestPage ontology={props.ontology} request={props.request} mutate={props.mutate} />;
  }

  if (props.tab === "mcp-tools") {
    return <McpToolsPage />;
  }

  return (
    <SystemPage
      health={props.health}
      ontology={props.ontology}
      request={props.request}
      setHealth={props.setHealth}
      showError={props.showError}
    />
  );
}

function ClassesPage(props: {
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
  const [mode, setMode] = useState<ClassPageMode>("topology");
  const [query, setQuery] = useState("");
  const searchResults = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return [];
    return props.classes
      .filter((classDef) => {
        const haystack = [
          classDef.name,
          classDef.description ?? "",
          classDef.normalized_label ?? "",
          ...classDef.aliases,
        ]
          .join(" ")
          .toLowerCase();
        return haystack.includes(term);
      })
      .slice(0, 8);
  }, [props.classes, query]);

  function selectClass(classId: string) {
    props.setSelectedClassId(classId);
    setQuery("");
    setMode("edit");
  }

  function newClass() {
    props.setSelectedClassId("");
    setQuery("");
    setMode("create");
  }

  return (
    <section className="classesPage">
      <header className="classesToolbar">
        <div className="classSearchStack">
          <form className="classSearch" onSubmit={(event) => event.preventDefault()}>
            <Search size={16} />
            <input
              placeholder="Search classes"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </form>
          {query.trim() && (
            <div className="classSearchResults">
              {searchResults.length ? (
                searchResults.map((classDef) => (
                  <button
                    className={classNames("searchResultItem", classDef.id === props.selectedClassId && "selected")}
                    key={classDef.id}
                    onClick={() => selectClass(classDef.id)}
                    type="button"
                  >
                    <strong>{classDef.name}</strong>
                    <span>{classDef.description || classDef.normalized_label || compactId(classDef.id)}</span>
                  </button>
                ))
              ) : (
                <span className="searchEmpty">No matching classes</span>
              )}
            </div>
          )}
        </div>
        <button className="primaryButton" onClick={newClass} type="button">
          <Plus size={15} /> New class
        </button>
      </header>

      {mode === "topology" ? (
        <Panel title="Class topology" icon={<Waypoints size={17} />} className="classTopologyPanel" wide>
          <ClassTopologyCanvas
            classes={props.classes}
            onSelectClass={selectClass}
            propertiesByClass={props.propertiesByClass}
            relationTypes={props.relationTypes}
            selectedClassId={props.selectedClassId}
          />
        </Panel>
      ) : (
        <ClassEditorPage
          classes={props.classes}
          mode={mode}
          mutate={props.mutate}
          ontologyId={props.ontologyId}
          onBack={() => setMode("topology")}
          propertiesByClass={props.propertiesByClass}
          relationTypes={props.relationTypes}
          reloadSchema={props.reloadSchema}
          request={props.request}
          selectedClassId={props.selectedClassId}
          setMode={setMode}
          setSelectedClassId={props.setSelectedClassId}
        />
      )}
    </section>
  );
}

function ClassTopologyCanvas(props: {
  classes: ClassDef[];
  relationTypes: RelationType[];
  propertiesByClass: Record<string, PropertyDef[]>;
  selectedClassId: string;
  onSelectClass: (classId: string) => void;
}) {
  const { nodes, edges } = useMemo(
    () =>
      buildClassTopology(props.classes, props.relationTypes, props.propertiesByClass, props.selectedClassId),
    [props.classes, props.relationTypes, props.propertiesByClass, props.selectedClassId],
  );
  const onNodeClick: NodeMouseHandler<Node<ClassNodeData>> = useCallback(
    (_event, node) => props.onSelectClass(node.id),
    [props.onSelectClass],
  );

  if (!props.classes.length) {
    return <EmptyState icon={<Box size={22} />} title="No classes yet" />;
  }

  return (
    <div className="classFlowCanvas">
      <ReactFlow
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.24 }}
        nodes={nodes}
        nodesConnectable={false}
        nodesDraggable={false}
        nodeTypes={classNodeTypes}
        onNodeClick={onNodeClick}
      >
        <Background gap={18} />
        <MiniMap pannable zoomable />
        <Controls />
      </ReactFlow>
    </div>
  );
}

const classNodeTypes = {
  classNode: ClassFlowNode,
};

function ClassFlowNode(props: NodeProps<Node<ClassNodeData>>) {
  return (
    <div className={classNames("classFlowNodeBody", props.selected && "selected")}>
      <Handle position={Position.Left} type="target" />
      <strong>{props.data.label}</strong>
      <span>{props.data.description}</span>
      <div>
        <small>{props.data.propertyCount} props</small>
        <small>{props.data.relationCount} rels</small>
      </div>
      <Handle position={Position.Right} type="source" />
    </div>
  );
}

function buildClassTopology(
  classes: ClassDef[],
  relationTypes: RelationType[],
  propertiesByClass: Record<string, PropertyDef[]>,
  selectedClassId: string,
) {
  const classIds = new Set(classes.map((classDef) => classDef.id));
  const relationCount = new Map<string, number>();
  relationTypes.forEach((relationType) => {
    relationCount.set(relationType.source_class_id, (relationCount.get(relationType.source_class_id) ?? 0) + 1);
    relationCount.set(relationType.target_class_id, (relationCount.get(relationType.target_class_id) ?? 0) + 1);
  });

  const edges: Edge[] = [];
  relationTypes.forEach((relationType) => {
    if (!classIds.has(relationType.source_class_id) || !classIds.has(relationType.target_class_id)) return;
    edges.push({
      id: `relation-${relationType.id}`,
      label: relationType.name,
      markerEnd: { type: MarkerType.ArrowClosed },
      source: relationType.source_class_id,
      target: relationType.target_class_id,
      type: "smoothstep",
    });
  });

  classes.forEach((classDef) => {
    classDef.parent_class_ids.forEach((parentId) => {
      if (!classIds.has(parentId)) return;
      edges.push({
        id: `parent-${parentId}-${classDef.id}`,
        label: "parent",
        markerEnd: { type: MarkerType.ArrowClosed },
        source: parentId,
        style: { strokeDasharray: "5 5" },
        target: classDef.id,
        type: "smoothstep",
      });
    });
  });

  const graph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ marginx: 36, marginy: 36, nodesep: 58, rankdir: "LR", ranksep: 112 });

  const nodeWidth = 216;
  const nodeHeight = 86;
  classes.forEach((classDef) => graph.setNode(classDef.id, { height: nodeHeight, width: nodeWidth }));
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);

  const nodes: Node<ClassNodeData>[] = classes.map((classDef) => {
    const position = graph.node(classDef.id) ?? { x: nodeWidth / 2, y: nodeHeight / 2 };
    return {
      className: "classFlowNode",
      data: {
        description: classDef.description || classDef.normalized_label || compactId(classDef.id),
        label: classDef.name,
        propertyCount: propertiesByClass[classDef.id]?.length ?? 0,
        relationCount: relationCount.get(classDef.id) ?? 0,
      },
      id: classDef.id,
      position: { x: position.x - nodeWidth / 2, y: position.y - nodeHeight / 2 },
      selected: classDef.id === selectedClassId,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      type: "classNode",
    };
  });

  return { edges, nodes };
}

function ClassEditorPage(props: {
  mode: "create" | "edit";
  ontologyId: string;
  classes: ClassDef[];
  relationTypes: RelationType[];
  propertiesByClass: Record<string, PropertyDef[]>;
  selectedClassId: string;
  setSelectedClassId: (id: string) => void;
  setMode: (mode: ClassPageMode) => void;
  onBack: () => void;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadSchema: () => Promise<void>;
}) {
  const selectedClass = props.classes.find((item) => item.id === props.selectedClassId) ?? null;
  const selectedProperties = selectedClass ? props.propertiesByClass[selectedClass.id] ?? [] : [];
  const relatedRelationTypes = selectedClass
    ? props.relationTypes.filter(
        (relationType) =>
          relationType.source_class_id === selectedClass.id || relationType.target_class_id === selectedClass.id,
      )
    : [];
  const [classForm, setClassForm] = useState({ name: "", description: "", aliases: "", parents: [] as string[] });
  const [propertyForm, setPropertyForm] = useState({
    description: "",
    enumValues: "",
    multiValued: false,
    name: "",
    required: false,
    type: "string",
  });
  const [relationForm, setRelationForm] = useState({
    aliases: "",
    description: "",
    inverseName: "",
    name: "",
    sourceClassId: "",
    targetClassId: "",
  });
  const [editingPropertyId, setEditingPropertyId] = useState("");
  const [editingRelationId, setEditingRelationId] = useState("");
  const editingProperty = selectedProperties.find((property) => property.id === editingPropertyId) ?? null;
  const editingRelation = props.relationTypes.find((relation) => relation.id === editingRelationId) ?? null;

  useEffect(() => {
    if (props.mode === "edit" && selectedClass) {
      setClassForm({
        aliases: csv(selectedClass.aliases),
        description: selectedClass.description ?? "",
        name: selectedClass.name,
        parents: selectedClass.parent_class_ids,
      });
      return;
    }
    if (props.mode === "create") {
      setClassForm({ name: "", description: "", aliases: "", parents: [] });
    }
  }, [props.mode, selectedClass]);

  useEffect(() => {
    if (!editingProperty) return;
    setPropertyForm({
      description: editingProperty.description ?? "",
      enumValues: csv(editingProperty.enum_values),
      multiValued: editingProperty.multi_valued,
      name: editingProperty.name,
      required: editingProperty.required,
      type: editingProperty.type,
    });
  }, [editingProperty]);

  useEffect(() => {
    if (editingRelation) {
      setRelationForm({
        aliases: csv(editingRelation.aliases),
        description: editingRelation.description ?? "",
        inverseName: editingRelation.inverse_name ?? "",
        name: editingRelation.name,
        sourceClassId: editingRelation.source_class_id,
        targetClassId: editingRelation.target_class_id,
      });
      return;
    }
    if (selectedClass && !relationForm.sourceClassId) {
      setRelationForm((current) => ({
        ...current,
        sourceClassId: selectedClass.id,
        targetClassId: props.classes.find((classDef) => classDef.id !== selectedClass.id)?.id ?? selectedClass.id,
      }));
    }
  }, [editingRelation, selectedClass, props.classes, relationForm.sourceClassId]);

  function saveClass(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const body = {
        aliases: splitCsv(classForm.aliases),
        description: classForm.description || null,
        external_mappings: selectedClass?.external_mappings ?? {},
        name: classForm.name,
        parent_class_ids: classForm.parents,
      };
      if (props.mode === "edit" && selectedClass) {
        await props.request<ClassDef>(`/classes/${selectedClass.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        const created = await props.request<ClassDef>(`/ontologies/${props.ontologyId}/classes`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        props.setSelectedClassId(created.id);
        props.setMode("edit");
      }
      await props.reloadSchema();
    }, props.mode === "edit" ? "Class updated" : "Class created");
  }

  function deleteClass() {
    if (!selectedClass) return;
    props.mutate(async () => {
      await props.request<void>(`/classes/${selectedClass.id}`, { method: "DELETE" });
      props.setSelectedClassId("");
      props.setMode("topology");
      await props.reloadSchema();
    }, "Class deleted");
  }

  function saveProperty(event: FormEvent) {
    event.preventDefault();
    if (!selectedClass) return;
    props.mutate(async () => {
      const body = {
        constraints: editingProperty?.constraints ?? {},
        description: propertyForm.description || null,
        enum_values: splitCsv(propertyForm.enumValues),
        external_mappings: editingProperty?.external_mappings ?? {},
        multi_valued: propertyForm.multiValued,
        name: propertyForm.name,
        required: propertyForm.required,
        type: propertyForm.type,
      };
      if (editingProperty) {
        await props.request<PropertyDef>(`/properties/${editingProperty.id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        await props.request<PropertyDef>(`/classes/${selectedClass.id}/properties`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      setEditingPropertyId("");
      setPropertyForm({
        name: "",
        type: "string",
        description: "",
        required: false,
        multiValued: false,
        enumValues: "",
      });
      await props.reloadSchema();
    }, editingProperty ? "Property updated" : "Property created");
  }

  function saveRelationType(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const body = {
        aliases: splitCsv(relationForm.aliases),
        description: relationForm.description || null,
        external_mappings: editingRelation?.external_mappings ?? {},
        inverse_name: relationForm.inverseName || null,
        name: relationForm.name,
        parent_relation_type_id: editingRelation?.parent_relation_type_id ?? null,
        source_class_id: relationForm.sourceClassId,
        target_class_id: relationForm.targetClassId,
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
      setEditingRelationId("");
      setRelationForm({ name: "", description: "", aliases: "", sourceClassId: "", targetClassId: "", inverseName: "" });
      await props.reloadSchema();
    }, editingRelation ? "Relation updated" : "Relation created");
  }

  function resetRelationForm() {
    setEditingRelationId("");
    setRelationForm({
      name: "",
      description: "",
      aliases: "",
      sourceClassId: selectedClass?.id ?? props.classes[0]?.id ?? "",
      targetClassId: props.classes.find((classDef) => classDef.id !== selectedClass?.id)?.id ?? selectedClass?.id ?? "",
      inverseName: "",
    });
  }

  return (
    <section className="classEditorPage">
      <div className="pageSubHeader">
        <button className="secondaryButton" onClick={props.onBack} type="button">
          <ArrowLeft size={15} /> Topology
        </button>
        <div>
          <h2>{props.mode === "create" ? "Create class" : selectedClass?.name ?? "Edit class"}</h2>
          <p>{props.mode === "create" ? "Define a new ontology class." : "Edit class fields, properties, and relation types."}</p>
        </div>
      </div>

      <section className="pageGrid classDetailGrid">
        <Panel title="Class information" icon={<Box size={17} />}>
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
              <ParentClassPicker
                classes={props.classes}
                excludedClassId={selectedClass?.id}
                selectedIds={classForm.parents}
                onChange={(parents) => setClassForm({ ...classForm, parents })}
              />
            </label>
            <div className="buttonRow">
              <button className="primaryButton" disabled={!props.ontologyId} type="submit">
                <Save size={15} /> {props.mode === "create" ? "Create class" : "Save class"}
              </button>
              {selectedClass && (
                <button className="secondaryButton dangerText" onClick={deleteClass} type="button">
                  <Trash2 size={15} /> Delete
                </button>
              )}
            </div>
          </form>
        </Panel>

        <Panel title="Properties" icon={<Braces size={17} />}>
          {selectedClass ? (
            <>
              <form className="stackForm" onSubmit={saveProperty}>
                <input
                  required
                  placeholder="Property name"
                  value={propertyForm.name}
                  onChange={(event) => setPropertyForm({ ...propertyForm, name: event.target.value })}
                />
                <div className="formPair">
                  <select
                    value={propertyForm.type}
                    onChange={(event) => setPropertyForm({ ...propertyForm, type: event.target.value })}
                  >
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
                  <button className="primaryButton" type="submit">
                    <Save size={15} /> {editingProperty ? "Save property" : "Add property"}
                  </button>
                  {editingProperty && (
                    <button className="secondaryButton" onClick={() => setEditingPropertyId("")} type="button">
                      Cancel
                    </button>
                  )}
                </div>
              </form>
              <DataList
                empty="No properties"
                items={selectedProperties.map((property) => ({
                  id: property.id,
                  title: property.name,
                  subtitle: `${property.type}${property.required ? " - required" : ""}${property.multi_valued ? " - multi" : ""}`,
                  selected: editingPropertyId === property.id,
                  onSelect: () => setEditingPropertyId(property.id),
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
            </>
          ) : (
            <EmptyState icon={<Braces size={20} />} title="Create the class before adding properties" />
          )}
        </Panel>

        <Panel title="Relation information" icon={<GitBranch size={17} />}>
          {selectedClass ? (
            <>
              <button className="secondaryButton fullWidth" onClick={resetRelationForm} type="button">
                <Plus size={15} /> New relation
              </button>
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
                <button className="primaryButton" disabled={!props.classes.length} type="submit">
                  <Save size={15} /> {editingRelation ? "Save relation" : "Create relation"}
                </button>
              </form>
              <DataList
                empty="No relation types for this class"
                items={relatedRelationTypes.map((relationType) => ({
                  id: relationType.id,
                  title: relationType.name,
                  subtitle: `${nameFor(props.classes, relationType.source_class_id)} -> ${nameFor(
                    props.classes,
                    relationType.target_class_id,
                  )}`,
                  selected: editingRelationId === relationType.id,
                  onSelect: () => setEditingRelationId(relationType.id),
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
            </>
          ) : (
            <EmptyState icon={<GitBranch size={20} />} title="Create the class before adding relations" />
          )}
        </Panel>
      </section>
    </section>
  );
}

function EntitiesPage(props: {
  ontologyId: string;
  classes: ClassDef[];
  relationTypes: RelationType[];
  entities: Entity[];
  relations: Relation[];
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadGraph: () => Promise<void>;
}) {
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [classFilter, setClassFilter] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  const classLabels = useMemo(
    () => Array.from(new Set(props.classes.map((classDef) => classDef.name))).sort(),
    [props.classes],
  );
  const colorForLabel = (label: string) => pickColor(label, classLabels);

  const toggleClassFilter = (classId: string) => {
    const classDef = props.classes.find((item) => item.id === classId);
    if (!classDef) return;
    const label = classDef.name;
    setClassFilter((current) =>
      current.includes(label)
        ? current.filter((item) => item !== label)
        : [...current, label],
    );
  };

  const visibleEntities =
    classFilter.length === 0
      ? props.entities
      : props.entities.filter((entity) => classFilter.includes(entity.class_label));
  const visibleRelations = props.relations.filter(
    (relation) =>
      visibleEntities.some((entity) => entity.id === relation.source_entity_id) &&
      visibleEntities.some((entity) => entity.id === relation.target_entity_id),
  );

  const selectedEntity = selectedEntityId
    ? props.entities.find((entity) => entity.id === selectedEntityId) ?? null
    : null;

  return (
    <section className="entityGraphPage">
      <div className="entityGraphToolbar">
        <Search size={15} className="toolbarIcon" />
        <input
          placeholder="Search entities by name or alias"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
        <span className="toolbarDivider" />
        <span className="toolbarLabel">Classes</span>
        <div className="classChipRow">
          {props.classes.length === 0 ? (
            <span className="toolbarEmptyHint">No classes defined</span>
          ) : (
            props.classes.map((classDef) => {
              const active = classFilter.includes(classDef.name);
              return (
                <button
                  className={classNames("classChip", active && "active")}
                  key={classDef.id}
                  onClick={() => toggleClassFilter(classDef.id)}
                  style={
                    active
                      ? ({
                          "--chip-color": colorForLabel(classDef.name),
                        } as CSSProperties)
                      : undefined
                  }
                  type="button"
                >
                  <span
                    className="classChipDot"
                    style={{ background: colorForLabel(classDef.name) }}
                  />
                  {classDef.name}
                </button>
              );
            })
          )}
          {classFilter.length > 0 && (
            <button
              className="classChipClear"
              onClick={() => setClassFilter([])}
              type="button"
            >
              Clear ({classFilter.length})
            </button>
          )}
        </div>
        <span className="toolbarStats">
          {visibleEntities.length} entities · {visibleRelations.length} relations
          {props.entities.length === 0 && " · No entities yet"}
        </span>
      </div>

      <div className="entityGraphCanvasWrap">
        {props.entities.length === 0 ? (
          <div className="entityGraphEmpty">
            <div>
              <Database size={28} />
              <h3>No entities yet</h3>
              <p>Entities will appear here as a topology graph once created.</p>
            </div>
          </div>
        ) : (
          <EntityGraphCanvas
            entities={props.entities}
            relations={props.relations}
            selectedEntityId={selectedEntityId}
            onSelectEntity={setSelectedEntityId}
            classFilter={classFilter}
            searchQuery={searchQuery}
            classLabels={classLabels}
          />
        )}
        <EntityDetailDrawer
          entity={selectedEntity}
          relations={props.relations}
          entities={props.entities}
          onClose={() => setSelectedEntityId(null)}
        />
      </div>
    </section>
  );
}

function EntitiesSearchPage(props: {
  ontologyId: string;
  classes: ClassDef[];
  request: Requester;
}) {
  const [mode, setMode] = useState<"text" | "id">("text");
  const [query, setQuery] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [entityId, setEntityId] = useState("");
  const [results, setResults] = useState<EntitySearchResult | null>(null);
  const [detail, setDetail] = useState<EntityWithRelations | null>(null);
  const [localError, setLocalError] = useState("");

  async function loadEntityDetail(id: string) {
    setLocalError("");
    try {
      const data = await props.request<EntityWithRelations>(`/ontologies/${props.ontologyId}/entities/${id}`);
      setDetail(data);
    } catch (error) {
      setDetail(null);
      setLocalError(error instanceof Error ? error.message : String(error));
    }
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    setLocalError("");
    setDetail(null);
    try {
      const params = new URLSearchParams({ query, limit: "20" });
      if (classFilter) params.set("class_id", classFilter);
      const data = await props.request<EntitySearchResult>(
        `/ontologies/${props.ontologyId}/entities/search?${params.toString()}`,
      );
      setResults(data);
    } catch (error) {
      setResults(null);
      setLocalError(error instanceof Error ? error.message : String(error));
    }
  }

  async function lookupById(event: FormEvent) {
    event.preventDefault();
    if (!entityId.trim()) return;
    await loadEntityDetail(entityId.trim());
  }

  return (
    <section className="entitySearchPage">
      <Panel title="Retrieval test" icon={<Search size={17} />}>
        <div className="segmented">
          <button className={classNames(mode === "text" && "active")} onClick={() => setMode("text")} type="button">
            Text
          </button>
          <button className={classNames(mode === "id" && "active")} onClick={() => setMode("id")} type="button">
            Entity ID
          </button>
        </div>
        {mode === "text" ? (
          <form className="stackForm" onSubmit={search}>
            <textarea
              className="questionBox"
              required
              placeholder="Input text to match similar entities"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <select value={classFilter} onChange={(event) => setClassFilter(event.target.value)}>
              <option value="">All classes</option>
              {props.classes.map((classDef) => (
                <option key={classDef.id} value={classDef.id}>
                  {classDef.name}
                </option>
              ))}
            </select>
            <button className="primaryButton" disabled={!props.ontologyId} type="submit">
              <Search size={15} /> Match
            </button>
          </form>
        ) : (
          <form className="stackForm" onSubmit={lookupById}>
            <input
              required
              placeholder="Entity ID"
              value={entityId}
              onChange={(event) => setEntityId(event.target.value)}
            />
            <button className="primaryButton" disabled={!props.ontologyId} type="submit">
              <Search size={15} /> Lookup
            </button>
          </form>
        )}
        <ErrorText message={localError} />
      </Panel>

      <Panel title="Matches" icon={<Database size={17} />}>
        {mode === "text" ? (
          <DataList
            empty="No matches yet"
            items={(results?.results ?? []).map((entity) => ({
              id: entity.id,
              title: entity.name,
              subtitle: entity.class_label,
              meta: compactId(entity.id),
              selected: detail?.id === entity.id,
              onSelect: () => loadEntityDetail(entity.id),
            }))}
          />
        ) : (
          <EmptyState icon={<Search size={20} />} title="Use the Entity ID lookup form" />
        )}
      </Panel>

      <Panel title="Entity detail" icon={<Clipboard size={17} />} wide>
        {detail ? (
          <div className="inspector">
            <h2>{detail.name}</h2>
            <p>{detail.class_label}</p>
            <dl className="detailList">
              <dt>ID</dt>
              <dd>{detail.id}</dd>
              <dt>Outgoing</dt>
              <dd>{detail.outgoing.length}</dd>
              <dt>Incoming</dt>
              <dd>{detail.incoming.length}</dd>
            </dl>
            <pre className="jsonBlock tall">{prettyJson(detail)}</pre>
          </div>
        ) : (
          <EmptyState icon={<Clipboard size={20} />} title="Select or lookup an entity" />
        )}
      </Panel>
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

function AgentTestPage(props: {
  ontology: Ontology;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
}) {
  const [question, setQuestion] = useState("");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [temperature, setTemperature] = useState("0.2");
  const [result, setResult] = useState<AgentTestResponse | null>(null);

  function run(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const response = await props.request<AgentTestResponse>("/agent-test/run", {
        method: "POST",
        body: JSON.stringify({
          base_url: baseUrl || null,
          model: model || null,
          ontology_id: props.ontology.id,
          question,
          temperature: temperature ? Number(temperature) : null,
        }),
      });
      setResult(response);
    }, "Agent test completed");
  }

  return (
    <section className="agentLayout">
      <Panel title="Agent test" icon={<Play size={17} />}>
        <form className="stackForm" onSubmit={run}>
          <textarea
            className="questionBox"
            required
            placeholder="Ask a question against the selected ontology"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <input placeholder="Model override" value={model} onChange={(event) => setModel(event.target.value)} />
          <input
            placeholder="OpenAI-compatible base URL"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
          />
          <input
            max="2"
            min="0"
            step="0.1"
            type="number"
            value={temperature}
            onChange={(event) => setTemperature(event.target.value)}
          />
          <button className="primaryButton" type="submit">
            <Play size={15} /> Run
          </button>
        </form>
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

function McpToolsPage() {
  const tools = [
    ["search_entities", "Search entities by text within an ontology."],
    ["get_entity", "Fetch one entity and direct relations by entity id."],
    ["find_related_entities", "Find related entities by depth and direction."],
    ["validate_entity", "Validate entity data against class schema."],
    ["explain_entity", "Generate entity context and explanation."],
  ];

  return (
    <section className="mcpToolsPage">
      <Panel title="MCP tools" icon={<Wrench size={17} />} wide>
        <div className="toolList">
          {tools.map(([tool, description]) => (
            <div className="toolRow" key={tool}>
              <div>
                <strong>{tool}</strong>
                <span>{description}</span>
              </div>
              <Badge>server</Badge>
            </div>
          ))}
        </div>
      </Panel>
    </section>
  );
}

function SystemPage(props: {
  ontology: Ontology;
  health: Health | null;
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
      <Panel title="Ontology" icon={<Waypoints size={17} />}>
        <dl className="detailList">
          <dt>Name</dt>
          <dd>{props.ontology.name}</dd>
          <dt>Status</dt>
          <dd><Badge>{props.ontology.status}</Badge></dd>
          <dt>Version</dt>
          <dd>{compactId(props.ontology.current_version_id)}</dd>
          <dt>Updated</dt>
          <dd>{formatDate(props.ontology.updated_at)}</dd>
        </dl>
      </Panel>
      <Panel title="Connection" icon={<Activity size={17} />}>
        <dl className="detailList">
          <dt>API base URL</dt>
          <dd><code>{API_BASE_URL}</code></dd>
        </dl>
      </Panel>
      <Panel title="Dependencies" icon={<Activity size={17} />} wide>
        <button className="primaryButton" onClick={checkHealth} type="button">
          <RefreshCw size={15} /> Check
        </button>
        {props.health ? (
          <pre className="jsonBlock">{prettyJson(props.health)}</pre>
        ) : (
          <EmptyState icon={<Activity size={20} />} title="No health check yet" />
        )}
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
      variant="borderless"
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
