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
  BookOpen,
  Box,
  Braces,
  Check,
  ChevronRight,
  CircleGauge,
  CircleHelp,
  Clipboard,
  Database,
  FileCheck2,
  FileText,
  Flag,
  GitBranch,
  History,
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
  ShieldCheck,
  Trash2,
  Upload,
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
  Proposal,
  ProposalItem,
  ReviewBatch,
  SourceChunk,
  SourceDocument,
  KnowledgeConflict,
  OntologyVersion,
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
import {
  EntityGraphCanvas,
  pickColor,
  type EntityGraphLayout,
} from "./components/EntityGraphCanvas";
import { EntityDetailDrawer } from "./components/EntityDetailDrawer";
import { BuildOverviewPage } from "./pages/BuildOverviewPage";
import { CompetencyQuestionsPage } from "./pages/CompetencyQuestionsPage";
import { ProjectBriefPage } from "./pages/ProjectBriefPage";
import { FactAuditPage } from "./pages/FactAuditPage";
import { PublicationPage } from "./pages/PublicationPage";
import { VersionsPage } from "./pages/VersionsPage";
import { EvidenceExplorer } from "./pages/EvidenceExplorer";

type AppView = "home" | "workspace";
type WorkspaceTab =
  | "overview"
  | "brief"
  | "questions"
  | "topology"
  | "schema-review"
  | "sources"
  | "graph-review"
  | "facts"
  | "publication"
  | "classes"
  | "entities"
  | "entities-search"
  | "versions"
  | "evidence"
  | "agent-test"
  | "mcp-tools"
  | "setting";
type ClassPageMode = "topology" | "create" | "edit";
type EntityPageMode = "topology" | "create" | "edit";
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
  group: "Build" | "Review" | "Model" | "Tools";
  label: string;
  detail: string;
  icon: typeof Network;
}> = [
  { id: "overview", group: "Build", label: "Overview", detail: "Progress & next actions", icon: CircleGauge },
  { id: "brief", group: "Build", label: "Brief", detail: "Scope & intent", icon: BookOpen },
  { id: "questions", group: "Build", label: "Questions", detail: "Competency validation", icon: CircleHelp },
  { id: "sources", group: "Build", label: "Sources", detail: "Documents & chunks", icon: FileText },
  { id: "schema-review", group: "Review", label: "Schema", detail: "Schema proposals", icon: Clipboard },
  { id: "graph-review", group: "Review", label: "Graph", detail: "Knowledge candidates", icon: GitBranch },
  { id: "facts", group: "Review", label: "Facts", detail: "Layered fact audit", icon: FileCheck2 },
  { id: "publication", group: "Review", label: "Publication", detail: "Readiness & release", icon: Flag },
  { id: "classes", group: "Model", label: "Classes", detail: "Class topology", icon: Box },
  { id: "entities", group: "Model", label: "Entities", detail: "Entity editor", icon: Database },
  { id: "versions", group: "Model", label: "Versions", detail: "Lineage & diff", icon: History },
  { id: "evidence", group: "Model", label: "Evidence", detail: "Source traceability", icon: ShieldCheck },
  { id: "entities-search", group: "Tools", label: "Search", detail: "Retrieval tests", icon: Search },
  { id: "agent-test", group: "Tools", label: "Agent Test", detail: "Question runs", icon: Send },
  { id: "mcp-tools", group: "Tools", label: "MCP Tools", detail: "Tool catalog", icon: Wrench },
  { id: "setting", group: "Tools", label: "Settings", detail: "Runtime status", icon: Settings },
];

function isWorkspaceTab(value: string | null): value is WorkspaceTab {
  return workspaceTabs.some((tab) => tab.id === value);
}

function queryValue(name: string) {
  try {
    return new URLSearchParams(window.location.search).get(name) ?? "";
  } catch {
    return "";
  }
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
  const [view, setView] = useState<AppView>(() => queryValue("ontology") ? "workspace" : "home");
  const requestedTab = queryValue("tab");
  const [workspaceTab, setWorkspaceTab] = useStoredWorkspaceTab(
    UI_KEYS.workspaceTab,
    isWorkspaceTab(requestedTab) ? requestedTab : "overview",
  );
  const [projects, setProjects] = useState<Project[]>([]);
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [classes, setClasses] = useState<ClassDef[]>([]);
  const [propertiesByClass, setPropertiesByClass] = useState<Record<string, PropertyDef[]>>({});
  const [relationTypes, setRelationTypes] = useState<RelationType[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [versions, setVersions] = useState<OntologyVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState(() => queryValue("version"));
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useStoredString(UI_KEYS.project, queryValue("project"));
  const [selectedOntologyId, setSelectedOntologyId] = useStoredString(UI_KEYS.ontology, queryValue("ontology"));
  const [selectedClassId, setSelectedClassId] = useState("");
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(false);
  const [pageDirty, setPageDirty] = useState(false);

  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const selectedOntology = ontologies.find((ontology) => ontology.id === selectedOntologyId) ?? null;
  const selectedVersion = versions.find((version) => version.id === selectedVersionId) ?? null;
  const activeTab = workspaceTabs.find((tab) => tab.id === workspaceTab) ?? workspaceTabs[0];

  const request = useCallback(<T,>(path: string, options?: RequestInit) => apiRequest<T>(path, options), []);
  const showError = useCallback((error: unknown) => setNotice(errorNotice(error)), []);
  const navigateWorkspace = useCallback((tab: string, params: Record<string, string> = {}) => {
    if (!isWorkspaceTab(tab)) return;
    if (pageDirty && !window.confirm("Discard unsaved changes and leave this page?")) return;
    setPageDirty(false);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    for (const key of ["batch", "proposal", "claim", "item", "evidence", "document"]) {
      if (!(key in params)) url.searchParams.delete(key);
    }
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
    window.history.pushState(null, "", url);
    setWorkspaceTab(tab);
  }, [pageDirty, setWorkspaceTab]);

  useEffect(() => {
    const linkedProject = queryValue("project");
    const linkedOntology = queryValue("ontology");
    const linkedTab = queryValue("tab");
    if (linkedProject) setSelectedProjectId(linkedProject);
    if (linkedOntology) setSelectedOntologyId(linkedOntology);
    if (isWorkspaceTab(linkedTab)) setWorkspaceTab(linkedTab);
    const linkedVersion = queryValue("version");
    if (linkedVersion) setSelectedVersionId(linkedVersion);
  }, [setSelectedOntologyId, setSelectedProjectId, setWorkspaceTab]);

  useEffect(() => {
    if (view !== "workspace" || !selectedProjectId || !selectedOntologyId) return;
    const params = new URLSearchParams(window.location.search);
    params.set("project", selectedProjectId);
    params.set("ontology", selectedOntologyId);
    params.set("tab", workspaceTab);
    if (selectedVersionId) params.set("version", selectedVersionId);
    else params.delete("version");
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [selectedOntologyId, selectedProjectId, selectedVersionId, view, workspaceTab]);

  const loadProjects = useCallback(async () => {
    const data = await request<Project[]>("/projects");
    setProjects(data);
    setSelectedProjectId((current) =>
      current || data[0]?.id || "",
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
        current || "",
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

  const loadVersions = useCallback(
    async (ontologyId = selectedOntologyId) => {
      if (!ontologyId) {
        setVersions([]);
        setSelectedVersionId("");
        return;
      }
      const data = await request<OntologyVersion[]>(`/ontologies/${ontologyId}/versions`);
      setVersions(data);
      setSelectedVersionId(
        (current) => current || selectedOntology?.current_version_id || data[data.length - 1]?.id || "",
      );
    },
    [request, selectedOntology?.current_version_id, selectedOntologyId],
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
    Promise.all([loadSchema(), loadGraph(), loadVersions()]).catch(showError);
  }, [selectedOntologyId, loadSchema, loadGraph, loadVersions, showError]);

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
    setSelectedVersionId(ontology.current_version_id ?? "");
    setWorkspaceTab("overview");
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
              {(["Build", "Review", "Model", "Tools"] as const).map((group) => (
                <section className="navGroup" key={group}>
                  <span className="navGroupLabel">{group}</span>
                  {workspaceTabs.filter((item) => item.group === group).map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        className={classNames("navButton", workspaceTab === item.id && "active")}
                        key={item.id}
                        onClick={() => navigateWorkspace(item.id)}
                        type="button"
                      >
                        <Icon size={17} />
                        <span><strong>{item.label}</strong><small>{item.detail}</small></span>
                      </button>
                    );
                  })}
                </section>
              ))}
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
                <label className="versionSelector">
                  <span>Version</span>
                  <select
                    aria-label="Active ontology version"
                    onChange={(event) => setSelectedVersionId(event.target.value)}
                    value={selectedVersionId}
                  >
                    {!versions.length && <option value="">No versions</option>}
                    {versions.map((version) => (
                      <option key={version.id} value={version.id}>
                        v{version.version_number} · {version.status}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedVersion?.status === "published" && <span className="readOnlyPill">Read-only</span>}
                <button className="secondaryButton" onClick={() => setView("home")} type="button">
                  <ArrowLeft size={15} /> Ontologies
                </button>
                <Tooltip title="Refresh ontology data">
                  <button
                    className="iconButton"
                    disabled={loading}
                    onClick={() => Promise.all([loadSchema(), loadGraph(), loadVersions()]).catch(showError)}
                    type="button"
                  >
                    {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
                  </button>
                </Tooltip>
              </div>
            </header>

            {notice && <StatusBanner notice={notice} onDismiss={() => setNotice(null)} />}

            <div className="contentFrame">
              {!selectedOntology || !selectedProject ? (
                <EmptyState
                  icon={<Waypoints size={22} />}
                  title="The linked project and ontology context is not available"
                />
              ) : (
                <WorkspaceContent
                  classes={classes}
                  entities={entities}
                  health={health}
                  mutate={mutate}
                  ontology={selectedOntology}
                  project={selectedProject}
                  selectedVersion={selectedVersion}
                  selectedVersionId={selectedVersionId}
                  versions={versions}
                  propertiesByClass={propertiesByClass}
                  relations={relations}
                  relationTypes={relationTypes}
                  request={request}
                  reloadGraph={loadGraph}
                  reloadSchema={loadSchema}
                  selectedClassId={selectedClassId}
                  setHealth={setHealth}
                  setSelectedClassId={setSelectedClassId}
                  setSelectedVersionId={setSelectedVersionId}
                  reloadVersions={loadVersions}
                  navigateWorkspace={navigateWorkspace}
                  setPageDirty={setPageDirty}
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
  project: Project;
  ontology: Ontology;
  selectedVersion: OntologyVersion | null;
  selectedVersionId: string;
  versions: OntologyVersion[];
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
  reloadVersions: () => Promise<void>;
  setSelectedVersionId: (id: string) => void;
  navigateWorkspace: (tab: string, params?: Record<string, string>) => void;
  setPageDirty: (dirty: boolean) => void;
  setHealth: (health: Health | null) => void;
  showError: (error: unknown) => void;
}) {
  const readOnly = props.selectedVersion?.status === "published";
  // Stable identity is required: child pages (BuildOverviewPage et al.) put `request`
  // in their `load` useCallback deps, and a fresh inline function here would retrigger
  // their load effect on every parent render, producing an infinite fetch/Skeleton loop.
  const governedRequest = useCallback<Requester>(
    (path, options) => {
      const method = (options?.method ?? "GET").toUpperCase();
      if (readOnly && method !== "GET" && method !== "HEAD") {
        return Promise.reject(new Error("Published ontology versions are immutable. Create a successor draft to make changes."));
      }
      return props.request(path, options);
    },
    [props.request, readOnly],
  );

  if (props.tab === "overview") {
    return <BuildOverviewPage onNavigate={props.navigateWorkspace} ontologyId={props.ontology.id} projectId={props.project.id} readOnly={readOnly} request={governedRequest} versionId={props.selectedVersionId} />;
  }

  if (props.tab === "brief") {
    return <ProjectBriefPage onDirtyChange={props.setPageDirty} projectId={props.project.id} readOnly={readOnly} request={governedRequest} />;
  }

  if (props.tab === "questions") {
    return <CompetencyQuestionsPage ontologyId={props.ontology.id} projectId={props.project.id} readOnly={readOnly} request={governedRequest} versionId={props.selectedVersionId} />;
  }

  if (props.tab === "facts" || props.tab === "publication") {
    if (!props.selectedVersion) return <EmptyState icon={<History size={22} />} title="Select a valid ontology version" />;
    const context = { ontology: props.ontology, project: props.project, readOnly, request: governedRequest, version: props.selectedVersion };
    if (props.tab === "facts") return <FactAuditWithBatch {...context} batchId={queryValue("batch") || undefined} initialClaimId={queryValue("claim") || undefined} />;
    return <PublicationPage {...context} onNavigate={props.navigateWorkspace} onPublished={async (version) => { await props.reloadVersions(); props.setSelectedVersionId(version.id); }} />;
  }

  if (props.tab === "versions") {
    if (!props.selectedVersion) return <EmptyState icon={<History size={22} />} title="Select a valid ontology version" />;
    return (
      <VersionsPage
        ontology={props.ontology}
        project={props.project}
        request={governedRequest}
        version={props.selectedVersion}
        onVersionChange={(version) => {
          props.setSelectedVersionId(version.id);
          void props.reloadVersions();
        }}
      />
    );
  }

  if (props.tab === "evidence") {
    return (
      <EvidenceExplorer
        documentId={queryValue("document") || undefined}
        evidenceIds={(queryValue("evidence") || "").split(",").filter(Boolean)}
        itemKey={queryValue("item") || undefined}
        proposalId={queryValue("proposal") || undefined}
        request={governedRequest}
      />
    );
  }

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
        request={governedRequest}
        selectedClassId={props.selectedClassId}
        setSelectedClassId={props.setSelectedClassId}
      />
    );
  }

  if (props.tab === "schema-review") {
    return (
      <SchemaReviewPage
        batchId={queryValue("batch") || undefined}
        classes={props.classes}
        ontology={props.ontology}
        reloadSchema={props.reloadSchema}
        request={governedRequest}
        versionId={props.selectedVersionId}
      />
    );
  }

  if (props.tab === "sources") {
    return <SourceDocumentsPage navigate={props.navigateWorkspace} projectId={props.ontology.project_id} readOnly={readOnly} request={governedRequest} />;
  }

  if (props.tab === "graph-review") {
    return (
      <GraphReviewPage
        batchId={queryValue("batch") || undefined}
        ontology={props.ontology}
        reloadGraph={props.reloadGraph}
        request={governedRequest}
        versionId={props.selectedVersionId}
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
        propertiesByClass={props.propertiesByClass}
        relations={props.relations}
        relationTypes={props.relationTypes}
        reloadGraph={props.reloadGraph}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "entities-search") {
    return <EntitiesSearchPage classes={props.classes} ontologyId={props.ontology.id} request={governedRequest} />;
  }

  if (props.tab === "agent-test") {
    return <AgentTestPage ontology={props.ontology} request={governedRequest} mutate={props.mutate} />;
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

function FactAuditWithBatch(props: {
  project: Project;
  ontology: Ontology;
  version: OntologyVersion;
  request: Requester;
  readOnly: boolean;
  batchId?: string;
  initialClaimId?: string;
}) {
  const [batch, setBatch] = useState<ReviewBatch | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!props.batchId) {
      setBatch(null);
      return;
    }
    props.request<ReviewBatch>(`/review-batches/${props.batchId}`).then((value) => {
      if (value.ontology_id !== props.ontology.id || value.ontology_version_id !== props.version.id || value.review_type !== "fact") {
        throw new Error("This review batch does not match the selected ontology version or fact review type.");
      }
      setBatch(value);
    }).catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, [props.batchId, props.ontology.id, props.request, props.version.id]);

  if (error) return <div className="reviewError">{error}</div>;
  return (
    <div className="workspaceStack">
      {batch && <div className="batchContext"><strong>Review batch · facts</strong><span>{batch.status} · {batch.item_ids.length} scoped claims</span></div>}
      <FactAuditPage {...props} batchItemIds={batch?.item_ids} />
    </div>
  );
}

function SourceDocumentsPage(props: { projectId: string; request: Requester; navigate: (tab: string, params?: Record<string, string>) => void; readOnly: boolean }) {
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [chunks, setChunks] = useState<SourceChunk[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const data = await props.request<SourceDocument[]>(`/projects/${props.projectId}/source-documents`);
    setDocuments(data);
    setSelectedId((current) => data.some((item) => item.id === current) ? current : data[0]?.id || "");
  }, [props.projectId, props.request]);

  useEffect(() => { load().catch((cause) => setError(String(cause))); }, [load]);
  useEffect(() => {
    if (!selectedId) { setChunks([]); return; }
    props.request<SourceChunk[]>(`/source-documents/${selectedId}/chunks`).then(setChunks).catch((cause) => setError(String(cause)));
  }, [props.request, selectedId]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const uploaded = await props.request<SourceDocument>(`/projects/${props.projectId}/source-documents`, { method: "POST", body });
      setSelectedId(uploaded.id);
      setFile(null);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function reparse() {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      await props.request<SourceDocument>(`/source-documents/${selectedId}/reparse`, { method: "POST" });
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function openProposals() {
    if (!selectedId) return;
    setBusy(true);
    setError("");
    try {
      const proposals = await props.request<Proposal[]>(`/source-documents/${selectedId}/proposals`);
      const first = proposals[0];
      if (!first) {
        setError("This document has not generated any proposals yet.");
        return;
      }
      props.navigate(first.proposal_type === "schema_change" ? "schema-review" : "graph-review", { proposal: first.id });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  const selected = documents.find((document) => document.id === selectedId);
  return (
    <section className="sourcePage">
      <aside className="sourceSidebar">
        <form className="sourceUpload" onSubmit={upload}>
          <label><Upload size={16} /><span>PDF, Markdown or text</span><input accept=".pdf,.md,.markdown,.txt,text/plain,text/markdown,application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" /></label>
          <button className="primaryButton" disabled={!file || busy || props.readOnly} type="submit">Upload & parse</button>
        </form>
        {documents.map((document) => (
          <button className={classNames("sourceDocument", document.id === selectedId && "active")} key={document.id} onClick={() => setSelectedId(document.id)} type="button">
            <strong>{document.filename}</strong>
            <span><Badge>{document.parse_status}</Badge>{document.chunk_count} chunks · {(document.size_bytes / 1024).toFixed(1)} KB</span>
          </button>
        ))}
      </aside>
      <main className="sourceSurface">
        {error && <div className="reviewError">{error}</div>}
        {!selected ? <EmptyState icon={<FileText size={24} />} title="Upload a source document" /> : <>
          <header className="reviewHeader"><div><span className="eyebrow">Source document</span><h2>{selected.filename}</h2><p>SHA-256 {selected.content_hash.slice(0, 16)}… · parser {selected.parser_version} · parsed {selected.parse_count} time(s)</p></div><div className="reviewHeaderActions"><button className="secondaryButton" disabled={busy} onClick={() => void openProposals()} type="button">Generated proposals</button><button className="secondaryButton" disabled={busy || props.readOnly || selected.parse_status === "parsing"} onClick={() => void reparse()} type="button"><RefreshCw className={busy ? "spin" : ""} size={14} />{selected.parse_status === "failed" ? "Retry parse" : "Reparse"}</button></div></header>
          {selected.parse_error && <div className="reviewError">{selected.parse_error}</div>}
          <div className="chunkList">{chunks.map((chunk) => <article className="sourceChunk" key={chunk.id}><header><strong>Chunk {chunk.sequence + 1}</strong><span>{chunk.page_number ? `Page ${chunk.page_number} · ` : ""}characters {chunk.char_start}–{chunk.char_end}</span></header><pre>{chunk.text}</pre><code>{chunk.content_hash.slice(0, 20)}…</code></article>)}</div>
        </>}
      </main>
    </section>
  );
}

function GraphReviewPage(props: { ontology: Ontology; request: Requester; reloadGraph: () => Promise<void>; batchId?: string; versionId: string }) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [conflicts, setConflicts] = useState<KnowledgeConflict[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState<ReviewBatch | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [editingKey, setEditingKey] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [manualValues, setManualValues] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [all, conflictData, batchData] = await Promise.all([
      props.request<Proposal[]>(`/ontologies/${props.ontology.id}/proposals`),
      props.request<KnowledgeConflict[]>(`/ontologies/${props.ontology.id}/knowledge-conflicts`),
      props.batchId ? props.request<ReviewBatch>(`/review-batches/${props.batchId}`) : Promise.resolve(null),
    ]);
    if (batchData && (batchData.ontology_id !== props.ontology.id || batchData.ontology_version_id !== props.versionId || !["entity", "relation", "merge", "conflict"].includes(batchData.review_type))) {
      throw new Error("This review batch does not belong to the selected ontology version or graph review type.");
    }
    const knowledge = all.filter((item) => ["entity", "relation", "merge"].includes(item.proposal_type));
    setProposals(knowledge);
    setConflicts(conflictData);
    setBatch(batchData);
    const batchProposalId = batchData?.stable_key.split(":")[1] ?? "";
    setSelectedId((current) => batchProposalId || (knowledge.some((item) => item.id === current) ? current : knowledge[0]?.id || ""));
  }, [props.batchId, props.ontology.id, props.request, props.versionId]);

  useEffect(() => { load().catch((cause) => setError(String(cause))); }, [load]);
  const selected = proposals.find((proposal) => proposal.id === selectedId);
  const selectedConflicts = conflicts.filter((conflict) => conflict.proposal_id === selectedId);
  const items = (selected?.payload.items ?? []).filter((item) => !batch || batch.item_ids.includes(item.key));

  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); await load(); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } finally { setBusy(false); }
  }

  function proposalAction(action: "validate" | "approve" | "reject" | "apply") {
    if (!selected) return;
    void run(async () => {
      if (action === "validate" || action === "apply") await props.request(`/proposals/${selected.id}/${action}`, { method: "POST" });
      else await props.request(`/proposals/${selected.id}/review`, { method: "POST", body: JSON.stringify({ decision: action === "approve" ? "approved" : "rejected", reviewer_type: "user" }) });
      if (action === "apply") await props.reloadGraph();
    });
  }

  function reviewItem(itemKey: string, action: "approved" | "rejected" | "edited", data?: JsonObject) {
    if (!selected) return;
    void run(() => props.request(`/proposals/${selected.id}/items/${encodeURIComponent(itemKey)}/review`, {
      method: "POST",
      body: JSON.stringify({ action, reviewer_type: "user", ...(data ? { data } : {}) }),
    }));
  }

  function batchReview(action: "approved" | "rejected") {
    if (!selected || selectedKeys.length === 0) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/review`, {
        method: "POST",
        body: JSON.stringify({ item_keys: selectedKeys, action, reviewer_type: "user" }),
      });
      setSelectedKeys([]);
    });
  }

  function saveEdit(itemKey: string) {
    try {
      reviewItem(itemKey, "edited", JSON.parse(editorValue) as JsonObject);
      setEditingKey("");
    } catch {
      setError("Edited candidate data must be valid JSON.");
    }
  }

  function resolve(conflictId: string, action: "keep_existing" | "accept_proposed" | "manual") {
    let value: unknown;
    if (action === "manual") {
      try {
        value = JSON.parse(manualValues[conflictId] ?? "");
      } catch {
        setError("Manual conflict values must be valid JSON.");
        return;
      }
    }
    void run(() => props.request(`/knowledge-conflicts/${conflictId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ action, ...(action === "manual" ? { value } : {}) }),
    }));
  }

  return <section className="schemaReviewPage">
    <aside className="reviewQueue"><header><div><span className="eyebrow">Review queue</span><h2>Graph candidates</h2></div></header>{proposals.map((proposal) => <button className={classNames("reviewQueueItem", proposal.id === selectedId && "active")} key={proposal.id} onClick={() => setSelectedId(proposal.id)} type="button"><span><strong>{proposal.payload.items?.length ?? 0} {proposal.proposal_type}</strong><Badge>{proposal.status}</Badge></span><small>{formatDate(proposal.created_at)} · {compactId(proposal.id)}</small></button>)}</aside>
    <main className="reviewSurface">{error && <div className="reviewError">{error}</div>}{!selected ? <EmptyState icon={<GitBranch size={24} />} title="No knowledge candidates" /> : <>
      <header className="reviewHeader"><div><span className="eyebrow">{selected.proposal_type} proposal</span><h2>{items.length} candidates</h2><p>{selected.proposal_type === "merge" ? "Compare the source and target identities before approving the merge." : "Every knowledge candidate keeps its structured data and traceable evidence."}</p></div><div className="reviewHeaderActions">{selected.status === "proposed" && <button className="secondaryButton" disabled={busy} onClick={() => proposalAction("validate")} type="button">Validate</button>}{selected.status === "validated" && <><button className="secondaryButton" disabled={busy} onClick={() => proposalAction("reject")} type="button">Reject</button><button className="primaryButton" disabled={busy || selectedConflicts.some((item) => item.status === "pending") || items.some((item) => !item.review_status || item.review_status === "pending")} onClick={() => proposalAction("approve")} type="button">Approve proposal</button></>}{selected.status === "approved" && <button className="primaryButton" disabled={busy} onClick={() => proposalAction("apply")} type="button">Apply atomically</button>}</div></header>
      {selectedConflicts.map((conflict) => <article className="conflictCard" key={conflict.id}><div><Badge>{conflict.status}</Badge><strong>{conflict.item_key} · {conflict.field}</strong><p>Existing: {prettyJson(conflict.existing_value)}<br />Proposed: {prettyJson(conflict.proposed_value)}</p></div>{conflict.status === "pending" && <div className="conflictActions"><button onClick={() => resolve(conflict.id, "keep_existing")} type="button">Keep existing</button><button onClick={() => resolve(conflict.id, "accept_proposed")} type="button">Accept proposed</button><input aria-label={`Manual value for ${conflict.field}`} onChange={(event) => setManualValues((current) => ({ ...current, [conflict.id]: event.target.value }))} placeholder="Manual JSON value" value={manualValues[conflict.id] ?? ""} /><button onClick={() => resolve(conflict.id, "manual")} type="button">Use manual</button></div>}</article>)}
      {batch && <div className="batchContext"><strong>Review batch · {batch.review_type}</strong><span>{batch.status} · {batch.item_ids.length} scoped items</span><button className="secondaryButton" onClick={() => { const url = new URL(window.location.href); url.searchParams.delete("batch"); window.location.assign(url); }} type="button">Exit batch</button></div>}
      {selectedKeys.length > 0 && <div className="batchBar"><strong>{selectedKeys.length} selected</strong><button onClick={() => batchReview("approved")} type="button"><Check size={14} /> Approve</button><button onClick={() => batchReview("rejected")} type="button"><X size={14} /> Reject</button></div>}
      <div className="reviewItems">{items.map((item) => { const evidence = selected.evidence.filter((record) => item.evidence_ids?.includes(record.id)); const checked = selectedKeys.includes(item.key); return <article className={classNames("reviewItem", `status-${item.review_status ?? "pending"}`)} key={item.key}><div className="reviewItemSelect"><input aria-label={`Select ${item.key}`} checked={checked} onChange={() => setSelectedKeys(checked ? selectedKeys.filter((key) => key !== item.key) : [...selectedKeys, item.key])} type="checkbox" /></div><div className="reviewItemBody"><header><div><Badge>{item.kind}</Badge><h3>{String(item.data.name ?? item.key)}</h3></div><Badge>{item.review_status ?? "pending"}</Badge></header>{item.kind === "merge" ? <div className="schemaDiff"><div><span>Source entity</span><pre>{prettyJson(item.data.source_entity_id ?? item.data.source ?? "New entity")}</pre></div><div><span>Merge target</span><pre>{prettyJson(item.data.target_entity_id ?? item.data.target ?? "Existing entity")}</pre></div></div> : <pre className="jsonBlock">{prettyJson(item.data)}</pre>}{editingKey === item.key && <div className="reviewEditor"><textarea onChange={(event) => setEditorValue(event.target.value)} value={editorValue} /><button className="primaryButton" onClick={() => saveEdit(item.key)} type="button">Save candidate</button></div>}<EvidenceExplorer compact evidence={evidence} request={props.request} /></div><div className="reviewItemActions"><button aria-label={`Approve ${item.key}`} onClick={() => reviewItem(item.key, "approved")} type="button"><Check size={15} /></button><button aria-label={`Edit ${item.key}`} onClick={() => { setEditingKey(item.key); setEditorValue(prettyJson(item.data)); }} type="button"><Braces size={15} /></button><button aria-label={`Reject ${item.key}`} onClick={() => reviewItem(item.key, "rejected")} type="button"><X size={15} /></button></div></article>; })}</div>
    </>}</main>
  </section>;
}

function SchemaReviewPage(props: {
  ontology: Ontology;
  classes: ClassDef[];
  request: Requester;
  reloadSchema: () => Promise<void>;
  batchId?: string;
  versionId: string;
}) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [editingKey, setEditingKey] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState<ReviewBatch | null>(null);

  const load = useCallback(async () => {
    const [data, batchData] = await Promise.all([
      props.request<Proposal[]>(`/ontologies/${props.ontology.id}/proposals?proposal_type=schema_change`),
      props.batchId ? props.request<ReviewBatch>(`/review-batches/${props.batchId}`) : Promise.resolve(null),
    ]);
    if (batchData && (batchData.ontology_id !== props.ontology.id || batchData.ontology_version_id !== props.versionId || batchData.review_type !== "schema")) {
      throw new Error("This review batch does not belong to the selected ontology version or schema review type.");
    }
    setBatch(batchData);
    setProposals(data);
    setSelectedId((current) => {
      const batchProposalId = batchData?.stable_key.startsWith("proposal:") ? batchData.stable_key.slice(9) : "";
      if (batchProposalId) return batchProposalId;
      const requested = queryValue("proposal");
      if (current && data.some((item) => item.id === current)) return current;
      return data.some((item) => item.id === requested) ? requested : data[0]?.id || "";
    });
  }, [props.batchId, props.ontology.id, props.request, props.versionId]);

  useEffect(() => {
    load().catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, [load]);

  const selected = proposals.find((proposal) => proposal.id === selectedId) ?? null;
  const items = (selected?.payload.items ?? []).filter((item) => !batch || batch.item_ids.includes(item.key));
  const classNamesById = useMemo(
    () => new Map(props.classes.map((classDef) => [classDef.id, classDef.name])),
    [props.classes],
  );

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

  function reviewItem(itemKey: string, action: "approved" | "rejected") {
    if (!selected) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/${encodeURIComponent(itemKey)}/review`, {
        method: "POST",
        body: JSON.stringify({ action, reviewer_type: "user" }),
      });
    });
  }

  function batchReview(action: "approved" | "rejected") {
    if (!selected || !selectedKeys.length) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/review`, {
        method: "POST",
        body: JSON.stringify({ item_keys: selectedKeys, action, reviewer_type: "user" }),
      });
      setSelectedKeys([]);
    });
  }

  function saveEdit(item: ProposalItem) {
    if (!selected) return;
    let data: JsonObject;
    try {
      data = JSON.parse(editorValue) as JsonObject;
    } catch {
      setError("Edited item data must be valid JSON.");
      return;
    }
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/${encodeURIComponent(item.key)}/review`, {
        method: "POST",
        body: JSON.stringify({ action: "edited", reviewer_type: "user", data }),
      });
      setEditingKey("");
    });
  }

  function mergeItem(itemKey: string, mergeIntoKey: string) {
    if (!selected || !mergeIntoKey) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/${encodeURIComponent(itemKey)}/review`, {
        method: "POST",
        body: JSON.stringify({ action: "merged", reviewer_type: "user", merge_into_key: mergeIntoKey }),
      });
    });
  }

  function proposalAction(action: "validate" | "approve" | "reject" | "apply") {
    if (!selected) return;
    void run(async () => {
      if (action === "validate" || action === "apply") {
        await props.request(`/proposals/${selected.id}/${action}`, { method: "POST" });
      } else {
        await props.request(`/proposals/${selected.id}/review`, {
          method: "POST",
          body: JSON.stringify({ decision: action === "approve" ? "approved" : "rejected", reviewer_type: "user" }),
        });
      }
      if (action === "apply") await props.reloadSchema();
    });
  }

  return (
    <section className="schemaReviewPage">
      <aside className="reviewQueue" aria-label="Schema proposal batches">
        <header>
          <div><span className="eyebrow">Review queue</span><h2>Schema batches</h2></div>
          <button className="iconButton" disabled={busy} onClick={() => void load()} type="button">
            <RefreshCw className={busy ? "spin" : ""} size={16} />
          </button>
        </header>
        {proposals.length ? proposals.map((proposal) => (
          <button
            className={classNames("reviewQueueItem", proposal.id === selectedId && "active")}
            key={proposal.id}
            onClick={() => { setSelectedId(proposal.id); setSelectedKeys([]); }}
            type="button"
          >
            <span><strong>{proposal.payload.items?.length ?? 0} changes</strong><Badge>{proposal.status}</Badge></span>
            <small>{formatDate(proposal.created_at)} · {compactId(proposal.id)}</small>
          </button>
        )) : <EmptyState icon={<Clipboard size={20} />} title="No schema proposals" />}
      </aside>

      <main className="reviewSurface">
        {error && <div className="reviewError">{error}</div>}
        {batch && <div className="batchContext"><strong>Review batch · schema</strong><span>{batch.status} · {batch.item_ids.length} scoped items</span><button className="secondaryButton" onClick={() => { const url = new URL(window.location.href); url.searchParams.delete("batch"); window.location.assign(url); }} type="button">Exit batch</button></div>}
        {!selected ? (
          <EmptyState icon={<Clipboard size={24} />} title="Select a schema proposal" />
        ) : (
          <>
            <header className="reviewHeader">
              <div>
                <span className="eyebrow">Schema change proposal</span>
                <h2>{items.length} candidate changes</h2>
                <p>Draft {compactId(selected.target_version_id)} · evidence and deterministic validation remain attached.</p>
              </div>
              <div className="reviewHeaderActions">
                {selected.status === "proposed" && <button className="secondaryButton" disabled={busy} onClick={() => proposalAction("validate")} type="button"><Play size={14} /> Validate</button>}
                {selected.status === "validated" && <button className="primaryButton" disabled={busy || items.some((item) => !item.review_status || item.review_status === "pending")} onClick={() => proposalAction("approve")} title="Every candidate needs an explicit decision" type="button"><Check size={14} /> Approve proposal</button>}
                {selected.status === "approved" && <button className="primaryButton" disabled={busy} onClick={() => proposalAction("apply")} type="button"><Save size={14} /> Apply atomically</button>}
              </div>
            </header>

            <div className="reviewSummary">
              <div><strong>{items.filter((item) => item.review_status === "approved").length}</strong><span>Approved</span></div>
              <div><strong>{items.filter((item) => item.review_status === "rejected").length}</strong><span>Rejected</span></div>
              <div><strong>{items.filter((item) => !item.review_status || item.review_status === "pending").length}</strong><span>Pending</span></div>
              <div><strong>{selected.evidence.length}</strong><span>Evidence records</span></div>
            </div>

            {(selected.validation_result.errors?.length || selected.validation_result.ambiguities?.length) ? (
              <div className="validationStrip">
                {(selected.validation_result.errors ?? []).map((message) => <span className="validationError" key={message}>{message}</span>)}
                {(selected.validation_result.ambiguities ?? []).map((item, index) => <span className="validationAmbiguity" key={index}>{String(item.message ?? "Modeling ambiguity requires review")}</span>)}
              </div>
            ) : null}

            {selectedKeys.length > 0 && (
              <div className="batchBar">
                <strong>{selectedKeys.length} selected</strong>
                <button onClick={() => batchReview("approved")} type="button"><Check size={14} /> Approve</button>
                <button onClick={() => batchReview("rejected")} type="button"><X size={14} /> Reject</button>
              </div>
            )}

            <div className="reviewItems">
              {items.map((item) => {
                const checked = selectedKeys.includes(item.key);
                const currentClass = item.kind === "class"
                  ? props.classes.find((classDef) => classDef.name === item.data.name)
                  : null;
                const evidence = selected.evidence.filter((record) => item.evidence_ids?.includes(record.id));
                return (
                  <article className={classNames("reviewItem", `status-${item.review_status ?? "pending"}`)} key={item.key}>
                    <div className="reviewItemSelect">
                      <input
                        aria-label={`Select ${item.key}`}
                        checked={checked}
                        onChange={() => setSelectedKeys(checked ? selectedKeys.filter((key) => key !== item.key) : [...selectedKeys, item.key])}
                        type="checkbox"
                      />
                    </div>
                    <div className="reviewItemBody">
                      <header>
                        <div><Badge>{item.kind.replace("_", " ")}</Badge><h3>{String(item.data.name ?? item.key)}</h3></div>
                        <div className="reviewItemMeta"><span>{Math.round((item.confidence ?? 0) * 100)}% confidence</span><Badge>{item.review_status ?? "pending"}</Badge></div>
                      </header>
                      <div className="schemaDiff">
                        <div><span>Before</span><pre>{currentClass ? prettyJson(currentClass) : "Not defined"}</pre></div>
                        <div><span>After</span><pre>{prettyJson(item.data)}</pre></div>
                      </div>
                      <div className="reviewFacts">
                        <span>Impact: {item.kind === "class" ? `${props.classes.filter((classDef) => classDef.parent_class_ids.includes(String(item.data.id ?? ""))).length} child classes` : classNamesById.get(String(item.data.class_id ?? "")) ?? "Schema only"}</span>
                        <span>Sources: {item.evidence_ids?.length ?? 0} evidence · {item.competency_question_ids?.length ?? 0} questions</span>
                      </div>
                      <EvidenceExplorer compact evidence={evidence} request={props.request} />
                      {editingKey === item.key && (
                        <div className="reviewEditor">
                          <SchemaItemEditor item={item} onChange={setEditorValue} value={editorValue} />
                          <button className="primaryButton" onClick={() => saveEdit(item)} type="button">Save candidate</button>
                        </div>
                      )}
                    </div>
                    <div className="reviewItemActions">
                      <button title="Approve" onClick={() => reviewItem(item.key, "approved")} type="button"><Check size={15} /></button>
                      <button title="Edit" onClick={() => { setEditingKey(item.key); setEditorValue(prettyJson(item.data)); }} type="button"><Braces size={15} /></button>
                      <button title="Reject" onClick={() => reviewItem(item.key, "rejected")} type="button"><X size={15} /></button>
                      <select
                        aria-label={`Merge ${item.key} into another candidate`}
                        onChange={(event) => mergeItem(item.key, event.target.value)}
                        value=""
                      >
                        <option value="">Merge…</option>
                        {items.filter((candidate) => candidate.key !== item.key && candidate.kind === item.kind).map((candidate) => (
                          <option key={candidate.key} value={candidate.key}>{String(candidate.data.name ?? candidate.key)}</option>
                        ))}
                      </select>
                    </div>
                  </article>
                );
              })}
            </div>
          </>
        )}
      </main>
    </section>
  );
}

function SchemaItemEditor(props: { item: ProposalItem; value: string; onChange: (value: string) => void }) {
  let data: JsonObject = {};
  try {
    data = JSON.parse(props.value) as JsonObject;
  } catch {
    return <textarea aria-label="Advanced candidate JSON" onChange={(event) => props.onChange(event.target.value)} value={props.value} />;
  }

  const fieldsByKind: Record<ProposalItem["kind"], string[]> = {
    class: ["name", "description", "aliases", "parent_class_ids"],
    property: ["name", "class_id", "type", "description", "required", "multi_valued"],
    relation_type: ["name", "source_class_id", "target_class_id", "description", "inverse_name"],
    constraint: ["name", "class_id", "expression", "severity", "description"],
    entity: ["name"],
    relation: ["relation_type_id"],
    merge: ["source_entity_id", "target_entity_id"],
  };

  function update(field: string, value: unknown) {
    props.onChange(prettyJson({ ...data, [field]: value }));
  }

  return (
    <div className="structuredEditor">
      {fieldsByKind[props.item.kind].map((field) => {
        const current = data[field];
        if (typeof current === "boolean" || field === "required" || field === "multi_valued") {
          return <label key={field}><span>{field.replace(/_/g, " ")}</span><input checked={Boolean(current)} onChange={(event) => update(field, event.target.checked)} type="checkbox" /></label>;
        }
        const arrayValue = Array.isArray(current);
        return <label key={field}><span>{field.replace(/_/g, " ")}</span><input onChange={(event) => update(field, arrayValue ? splitCsv(event.target.value) : event.target.value)} value={arrayValue ? current.join(", ") : current === undefined || current === null ? "" : String(current)} /></label>;
      })}
      <details><summary>Advanced JSON</summary><textarea aria-label="Advanced candidate JSON" onChange={(event) => props.onChange(event.target.value)} value={props.value} /></details>
    </div>
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
  propertiesByClass: Record<string, PropertyDef[]>;
  relationTypes: RelationType[];
  entities: Entity[];
  relations: Relation[];
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadGraph: () => Promise<void>;
}) {
  const [mode, setMode] = useState<EntityPageMode>("topology");
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [classFilter, setClassFilter] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [graphLayout, setGraphLayout] = useState<EntityGraphLayout>("force");

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

  function deleteSelectedEntity() {
    if (!selectedEntity) return;
    props.mutate(async () => {
      await props.request<void>(
        `/ontologies/${props.ontologyId}/entities/${selectedEntity.id}`,
        { method: "DELETE" },
      );
      setSelectedEntityId(null);
      await props.reloadGraph();
    }, "Entity deleted");
  }

  if (mode === "create" || (mode === "edit" && selectedEntity)) {
    return (
      <EntityFormPage
        classes={props.classes}
        entity={mode === "edit" ? selectedEntity ?? undefined : undefined}
        entities={props.entities}
        relations={props.relations}
        mutate={props.mutate}
        onBack={() => setMode("topology")}
        onCreated={(entityId) => {
          setSelectedEntityId(entityId);
          setMode("topology");
        }}
        ontologyId={props.ontologyId}
        propertiesByClass={props.propertiesByClass}
        relationTypes={props.relationTypes}
        reloadGraph={props.reloadGraph}
        request={props.request}
      />
    );
  }

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
        <div aria-label="Graph layout" className="entityLayoutSwitch" role="group">
          <button
            aria-pressed={graphLayout === "hierarchical"}
            className={classNames(graphLayout === "hierarchical" && "active")}
            onClick={() => setGraphLayout("hierarchical")}
            title="Arrange relations from left to right and reduce crossings"
            type="button"
          >
            <GitBranch size={14} /> Hierarchy
          </button>
          <button
            aria-pressed={graphLayout === "force"}
            className={classNames(graphLayout === "force" && "active")}
            onClick={() => setGraphLayout("force")}
            title="Arrange dense or cyclic relations as a force-directed network"
            type="button"
          >
            <Network size={14} /> Force
          </button>
        </div>
        <button className="primaryButton entityCreateButton" onClick={() => setMode("create")} type="button">
          <Plus size={15} /> New entity
        </button>
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
            layoutMode={graphLayout}
          />
        )}
        <EntityDetailDrawer
          entity={selectedEntity}
          relations={props.relations}
          entities={props.entities}
          onClose={() => setSelectedEntityId(null)}
          onDelete={deleteSelectedEntity}
          onEdit={() => setMode("edit")}
        />
      </div>
    </section>
  );
}

function effectivePropertiesForClass(
  classId: string,
  classes: ClassDef[],
  propertiesByClass: Record<string, PropertyDef[]>,
  seen = new Set<string>(),
): PropertyDef[] {
  if (seen.has(classId)) return [];
  const nextSeen = new Set(seen).add(classId);
  const classDef = classes.find((item) => item.id === classId);
  if (!classDef) return [];

  const properties = new Map<string, PropertyDef>();
  classDef.parent_class_ids.forEach((parentId) => {
    effectivePropertiesForClass(parentId, classes, propertiesByClass, nextSeen).forEach((property) => {
      properties.set(property.name, property);
    });
  });
  (propertiesByClass[classId] ?? []).forEach((property) => properties.set(property.name, property));
  return Array.from(properties.values());
}

function parseEntityPropertyValue(property: PropertyDef, value: unknown): unknown {
  if (property.multi_valued) {
    const values = Array.isArray(value) ? value : [];
    return values
      .filter((item) => item !== undefined && item !== null && item !== "")
      .map((item) => parseEntityPropertyValue({ ...property, multi_valued: false }, item));
  }
  if (property.type === "number") return Number(value);
  if (property.type === "boolean") return value === "true";
  if (property.type === "json") return JSON.parse(String(value));
  return String(value);
}

function hasEntityPropertyValue(property: PropertyDef, value: unknown) {
  if (property.multi_valued) {
    return Array.isArray(value) && value.some((item) => item !== undefined && item !== null && item !== "");
  }
  return value !== undefined && value !== null && value !== "";
}

function editablePropertyValue(property: PropertyDef, value: unknown): unknown {
  if (property.multi_valued) {
    return Array.isArray(value)
      ? value.map((item) => editablePropertyValue({ ...property, multi_valued: false }, item))
      : [];
  }
  if (property.type === "json" && value !== undefined) return JSON.stringify(value, null, 2);
  if (property.type === "boolean" && typeof value === "boolean") return String(value);
  return value;
}

function classMatchesRelation(
  actualClassId: string,
  expectedClassId: string,
  classes: ClassDef[],
  seen = new Set<string>(),
): boolean {
  if (actualClassId === expectedClassId) return true;
  if (seen.has(actualClassId)) return false;
  const classDef = classes.find((item) => item.id === actualClassId);
  if (!classDef) return false;
  const nextSeen = new Set(seen).add(actualClassId);
  return classDef.parent_class_ids.some((parentId) =>
    classMatchesRelation(parentId, expectedClassId, classes, nextSeen),
  );
}

type EntityRelationChoice = {
  direction: "incoming" | "outgoing";
  relationType: RelationType;
  candidates: Entity[];
};

function EntityFormPage(props: {
  ontologyId: string;
  classes: ClassDef[];
  entities: Entity[];
  relations: Relation[];
  propertiesByClass: Record<string, PropertyDef[]>;
  relationTypes: RelationType[];
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadGraph: () => Promise<void>;
  onBack: () => void;
  onCreated: (entityId: string) => void;
  entity?: Entity;
}) {
  const [form, setForm] = useState({
    aliases: props.entity?.aliases.join(", ") ?? "",
    classId: props.entity?.class_id ?? props.classes[0]?.id ?? "",
    name: props.entity?.name ?? "",
  });
  const initialProperties = effectivePropertiesForClass(
    props.entity?.class_id ?? props.classes[0]?.id ?? "",
    props.classes,
    props.propertiesByClass,
  );
  const [propertyValues, setPropertyValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(initialProperties.map((property) => [
      property.name,
      editablePropertyValue(property, props.entity?.properties[property.name]),
    ])),
  );
  const [relationTargets, setRelationTargets] = useState<Record<string, string[]>>(() => {
    if (!props.entity) return {};
    const targets: Record<string, string[]> = {};
    props.relations.forEach((relation) => {
      if (relation.source_entity_id === props.entity?.id) {
        const key = `outgoing:${relation.relation_type_id}`;
        targets[key] = [...(targets[key] ?? []), relation.target_entity_id];
      }
      if (relation.target_entity_id === props.entity?.id) {
        const key = `incoming:${relation.relation_type_id}`;
        targets[key] = [...(targets[key] ?? []), relation.source_entity_id];
      }
    });
    return targets;
  });
  const [relationQueries, setRelationQueries] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const selectedClass = props.classes.find((item) => item.id === form.classId) ?? null;
  const properties = useMemo(
    () => effectivePropertiesForClass(form.classId, props.classes, props.propertiesByClass),
    [form.classId, props.classes, props.propertiesByClass],
  );
  const relationChoices = useMemo<EntityRelationChoice[]>(() => {
    if (!form.classId) return [];
    return props.relationTypes.flatMap((relationType) => {
      const choices: EntityRelationChoice[] = [];
      if (classMatchesRelation(form.classId, relationType.source_class_id, props.classes)) {
        choices.push({
          direction: "outgoing",
          relationType,
          candidates: props.entities.filter((entity) =>
            classMatchesRelation(entity.class_id, relationType.target_class_id, props.classes),
          ),
        });
      }
      if (classMatchesRelation(form.classId, relationType.target_class_id, props.classes)) {
        choices.push({
          direction: "incoming",
          relationType,
          candidates: props.entities.filter((entity) =>
            classMatchesRelation(entity.class_id, relationType.source_class_id, props.classes),
          ),
        });
      }
      return choices;
    });
  }, [form.classId, props.classes, props.entities, props.relationTypes]);
  function setPropertyValue(name: string, value: unknown) {
    setPropertyValues((current) => ({ ...current, [name]: value }));
  }

  function toggleRelationTarget(key: string, entityId: string) {
    setRelationTargets((current) => {
      const selected = current[key] ?? [];
      return {
        ...current,
        [key]: selected.includes(entityId)
          ? selected.filter((item) => item !== entityId)
          : [...selected, entityId],
      };
    });
  }

  async function saveEntity(event: FormEvent) {
    event.preventDefault();
    if (!selectedClass || submitting) return;
    setSubmitting(true);
    try {
      await props.mutate(async () => {
        const missing = properties.filter(
          (property) => property.required && !hasEntityPropertyValue(property, propertyValues[property.name]),
        );
        if (missing.length) throw new Error(`Required properties: ${missing.map((item) => item.name).join(", ")}`);

        const entityProperties: JsonObject = { ...(props.entity?.properties ?? {}) };
        properties.forEach((property) => {
          const value = propertyValues[property.name];
          if (hasEntityPropertyValue(property, value)) {
            entityProperties[property.name] = parseEntityPropertyValue(property, value);
          } else {
            delete entityProperties[property.name];
          }
        });
        const saved = await props.request<Entity>(
          props.entity
            ? `/ontologies/${props.ontologyId}/entities/${props.entity.id}`
            : `/ontologies/${props.ontologyId}/entities`, {
          method: props.entity ? "PATCH" : "POST",
          body: JSON.stringify({
            aliases: splitCsv(form.aliases),
            ...(!props.entity && { class_id: form.classId }),
            name: form.name,
            properties: entityProperties,
          }),
        });
        const desiredRelations = new Map<string, {
          relationTypeId: string;
          sourceEntityId: string;
          targetEntityId: string;
        }>();
        relationChoices.forEach((choice) => {
          const key = `${choice.direction}:${choice.relationType.id}`;
          (relationTargets[key] ?? []).forEach((targetEntityId) => {
            const sourceEntityId = choice.direction === "outgoing" ? saved.id : targetEntityId;
            const targetId = choice.direction === "outgoing" ? targetEntityId : saved.id;
            desiredRelations.set(
              `${choice.relationType.id}:${sourceEntityId}:${targetId}`,
              { relationTypeId: choice.relationType.id, sourceEntityId, targetEntityId: targetId },
            );
          });
        });
        const existingRelations = props.entity
          ? props.relations.filter((relation) =>
              relation.source_entity_id === saved.id || relation.target_entity_id === saved.id,
            )
          : [];
        const existingKeys = new Set(existingRelations.map((relation) =>
          `${relation.relation_type_id}:${relation.source_entity_id}:${relation.target_entity_id}`,
        ));
        const createRequests = [...desiredRelations.entries()]
          .filter(([key]) => !existingKeys.has(key))
          .map(([, relation]) =>
              props.request<Relation>(`/ontologies/${props.ontologyId}/relations`, {
                method: "POST",
                body: JSON.stringify({
                  relation_type_id: relation.relationTypeId,
                  source_entity_id: relation.sourceEntityId,
                  target_entity_id: relation.targetEntityId,
                  properties: {},
                }),
              }));
        const deleteRequests = existingRelations
          .filter((relation) => !desiredRelations.has(
            `${relation.relation_type_id}:${relation.source_entity_id}:${relation.target_entity_id}`,
          ))
          .map((relation) => props.request<void>(
            `/ontologies/${props.ontologyId}/relations/${relation.id}`,
            { method: "DELETE" },
          ));
        await Promise.all([...createRequests, ...deleteRequests]);
        await props.reloadGraph();
        props.onCreated(saved.id);
      }, props.entity ? "Entity updated" : "Entity created");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="entityCreatePage">
      <header className="pageSubHeader">
        <button aria-label="Back to entity topology" className="iconButton subtle" onClick={props.onBack} type="button">
          <ArrowLeft size={17} />
        </button>
        <div>
          <span className="eyebrow">Entity editor</span>
          <h2>{props.entity ? "Edit entity" : "Create entity"}</h2>
          <p>{props.entity ? "Update the node identity and schema-defined properties." : "Choose a class and add an instance that conforms to its property schema."}</p>
        </div>
      </header>

      <form className="entityCreateForm" onSubmit={saveEntity}>
        <Panel className="entityIdentityPanel" icon={<Database size={17} />} title="Identity">
          <div className="stackForm">
            <label>
              <span>Class</span>
              <select
                onChange={(event) => {
                  setForm((current) => ({ ...current, classId: event.target.value }));
                  setPropertyValues({});
                  setRelationTargets({});
                }}
                required
                disabled={Boolean(props.entity)}
                value={form.classId}
              >
                {!props.classes.length && <option value="">No classes available</option>}
                {props.classes.map((classDef) => <option key={classDef.id} value={classDef.id}>{classDef.name}</option>)}
              </select>
            </label>
            <label>
              <span>Name</span>
              <input
                maxLength={300}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="Entity name"
                required
                value={form.name}
              />
            </label>
            <label>
              <span>Aliases</span>
              <input
                onChange={(event) => setForm((current) => ({ ...current, aliases: event.target.value }))}
                placeholder="Comma-separated aliases"
                value={form.aliases}
              />
            </label>
            {selectedClass && (
              <div className="entityClassSummary">
                <span>{selectedClass.normalized_label || selectedClass.name}</span>
                <p>{selectedClass.description || "No class description."}</p>
              </div>
            )}
          </div>
        </Panel>

        <Panel className="entityPropertiesPanel" icon={<Braces size={17} />} title="Properties">
          {!selectedClass ? (
            <EmptyState icon={<Box size={20} />} title="Create a class before adding entities" />
          ) : properties.length === 0 ? (
            <div className="entityNoProperties">
              <Check size={18} />
              <div><strong>No properties required</strong><span>This class can be instantiated with identity fields only.</span></div>
            </div>
          ) : (
            <div className="entityPropertyList">
              {properties.map((property) => (
                <EntityPropertyField
                  entities={props.entities}
                  key={property.id}
                  onChange={(value) => setPropertyValue(property.name, value)}
                  property={property}
                  value={propertyValues[property.name]}
                />
              ))}
            </div>
          )}
        </Panel>

        <Panel className="entityRelationsPanel" icon={<GitBranch size={17} />} title="Relations">
            {!selectedClass ? (
              <EmptyState icon={<GitBranch size={20} />} title="Select a class to configure relations" />
            ) : relationChoices.length === 0 ? (
              <div className="entityNoProperties">
                <Check size={18} />
                <div><strong>No relations defined</strong><span>This class has no compatible relation types.</span></div>
              </div>
            ) : (
              <div className="entityRelationChoices">
                {relationChoices.map((choice) => {
                  const key = `${choice.direction}:${choice.relationType.id}`;
                  const expectedClassId = choice.direction === "outgoing"
                    ? choice.relationType.target_class_id
                    : choice.relationType.source_class_id;
                  const query = (relationQueries[key] ?? "").trim().toLowerCase();
                  const visibleCandidates = query
                    ? choice.candidates.filter((entity) =>
                        [entity.name, ...entity.aliases].some((value) =>
                          value.toLowerCase().includes(query),
                        ),
                      )
                    : choice.candidates;
                  return (
                    <section className="entityRelationChoice" key={key}>
                      <div className="entityRelationChoiceHeader">
                        <strong>{choice.relationType.name}</strong>
                        <span>{choice.direction === "outgoing" ? "Outgoing" : "Incoming"}</span>
                      </div>
                      {choice.relationType.aliases.length > 0 && (
                        <small className="entityRelationAliases">
                          Aliases: {choice.relationType.aliases.join(", ")}
                        </small>
                      )}
                      <p>
                        {choice.direction === "outgoing" ? `${selectedClass.name} → ` : `${nameFor(props.classes, expectedClassId)} → `}
                        {choice.direction === "outgoing" ? nameFor(props.classes, expectedClassId) : selectedClass.name}
                      </p>
                      <label className="entityRelationSearch">
                        <Search size={13} />
                        <input
                          aria-label={`Search ${choice.relationType.name} instances by name or alias`}
                          disabled={choice.candidates.length === 0}
                          onChange={(event) => setRelationQueries((current) => ({
                            ...current,
                            [key]: event.target.value,
                          }))}
                          placeholder="Search instances by name or alias"
                          type="search"
                          value={relationQueries[key] ?? ""}
                        />
                      </label>
                      {choice.candidates.length === 0 ? (
                        <small>No compatible {nameFor(props.classes, expectedClassId)} entities available.</small>
                      ) : visibleCandidates.length === 0 ? (
                        <div className="entityRelationNoResults">No instances match “{relationQueries[key]}”.</div>
                      ) : (
                        <div className="entityRelationTargets">
                          {visibleCandidates.map((entity) => (
                            <label key={entity.id}>
                              <input
                                checked={(relationTargets[key] ?? []).includes(entity.id)}
                                onChange={() => toggleRelationTarget(key, entity.id)}
                                type="checkbox"
                              />
                              <span>{entity.name}</span>
                              <small>{entity.class_label}</small>
                            </label>
                          ))}
                        </div>
                      )}
                    </section>
                  );
                })}
              </div>
            )}
          </Panel>

        <footer className="entityCreateActions">
          <button className="secondaryButton" disabled={submitting} onClick={props.onBack} type="button">Cancel</button>
          <button className="primaryButton" disabled={!selectedClass || !form.name.trim() || submitting} type="submit">
            {submitting ? <Loader2 className="spin" size={15} /> : <Save size={15} />}
            {submitting ? (props.entity ? "Saving..." : "Creating...") : (props.entity ? "Save changes" : "Create entity")}
          </button>
        </footer>
      </form>
    </section>
  );
}

function EntityPropertyField(props: {
  property: PropertyDef;
  value: unknown;
  entities: Entity[];
  onChange: (value: unknown) => void;
}) {
  const { property } = props;
  const values = property.multi_valued && Array.isArray(props.value) ? props.value : [];

  if (property.multi_valued) {
    return (
      <div className="entityPropertyField">
        <EntityPropertyLabel property={property} />
        <div className="entityMultiValues">
          {values.map((value, index) => (
            <div className="entityMultiValue" key={`${property.id}-${index}`}>
              <EntityPropertyControl
                entities={props.entities}
                onChange={(nextValue) => props.onChange(values.map((item, itemIndex) => itemIndex === index ? nextValue : item))}
                property={{ ...property, multi_valued: false }}
                value={value}
              />
              <button
                aria-label={`Remove ${property.name} value`}
                className="iconButton danger"
                onClick={() => props.onChange(values.filter((_, itemIndex) => itemIndex !== index))}
                type="button"
              ><Trash2 size={14} /></button>
            </div>
          ))}
          <button className="secondaryButton entityAddValue" onClick={() => props.onChange([...values, ""])} type="button">
            <Plus size={14} /> Add value
          </button>
        </div>
      </div>
    );
  }

  return (
    <label className="entityPropertyField">
      <EntityPropertyLabel property={property} />
      <EntityPropertyControl entities={props.entities} onChange={props.onChange} property={property} value={props.value} />
    </label>
  );
}

function EntityPropertyLabel({ property }: { property: PropertyDef }) {
  return (
    <span className="entityPropertyLabel">
      <span>{property.name}{property.required && <b aria-label="required"> *</b>}</span>
      <small>{property.type}{property.multi_valued ? " · multiple" : ""}</small>
      {property.description && <em>{property.description}</em>}
    </span>
  );
}

function EntityPropertyControl(props: {
  property: PropertyDef;
  value: unknown;
  entities: Entity[];
  onChange: (value: unknown) => void;
}) {
  const value = props.value === undefined ? "" : String(props.value);
  if (props.property.type === "boolean") {
    return <select aria-label={props.property.name} onChange={(event) => props.onChange(event.target.value)} value={value}><option value="">Not set</option><option value="true">True</option><option value="false">False</option></select>;
  }
  if (props.property.type === "enum") {
    return <select aria-label={props.property.name} onChange={(event) => props.onChange(event.target.value)} value={value}><option value="">Select a value</option>{props.property.enum_values.map((item) => <option key={item} value={item}>{item}</option>)}</select>;
  }
  if (props.property.type === "reference") {
    return <select aria-label={props.property.name} onChange={(event) => props.onChange(event.target.value)} value={value}><option value="">Select an entity</option>{props.entities.map((entity) => <option key={entity.id} value={entity.id}>{entity.name} · {entity.class_label}</option>)}</select>;
  }
  if (props.property.type === "json") {
    return <textarea aria-label={props.property.name} className="codeArea small" onChange={(event) => props.onChange(event.target.value)} placeholder='{"key": "value"}' value={value} />;
  }
  return (
    <input
      aria-label={props.property.name}
      onChange={(event) => props.onChange(event.target.value)}
      placeholder={props.property.type === "number" ? "0" : props.property.name}
      step={props.property.type === "number" ? "any" : undefined}
      type={props.property.type === "number" ? "number" : props.property.type === "date" ? "date" : "text"}
      value={value}
    />
  );
}

function EntitiesSearchPage(props: {
  ontologyId: string;
  classes: ClassDef[];
  request: Requester;
}) {
  const [mode, setMode] = useState<"text" | "id">("text");
  const [retrievalMode, setRetrievalMode] = useState<"text" | "vector" | "hybrid">("hybrid");
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
      const params = new URLSearchParams({ query, limit: "20", mode: retrievalMode });
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
            <label>
              <span>Retrieval mode</span>
              <select
                value={retrievalMode}
                onChange={(event) => setRetrievalMode(event.target.value as typeof retrievalMode)}
              >
                <option value="hybrid">Hybrid</option>
                <option value="vector">Vector</option>
                <option value="text">Text</option>
              </select>
            </label>
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
              meta: `${entity.match_source} · ${entity.score.toFixed(4)} · ${compactId(entity.id)}`,
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
  const [result, setResult] = useState<AgentTestResponse | null>(null);

  function run(event: FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const response = await props.request<AgentTestResponse>("/agent-test/run", {
        method: "POST",
        body: JSON.stringify({
          ontology_id: props.ontology.id,
          question,
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
    ["search_entities", "Recall entities globally with text, vector, or hybrid search."],
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
