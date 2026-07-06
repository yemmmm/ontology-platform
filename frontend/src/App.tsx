import {
  Activity,
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  Clipboard,
  Database,
  Flag,
  GitBranch,
  History,
  Layers,
  Loader2,
  Network,
  Play,
  Plus,
  RefreshCw,
  Send,
  Settings,
  ShieldCheck,
  Trash2,
  Upload,
  Waypoints,
  Wrench,
  X,
} from "lucide-react";
// Note: CircleGauge removed (overview tab gone), as were FileCheck2/FileText/Link2/Save/Search/Braces/Box.
import { Card, ConfigProvider, Tag, Tooltip } from "antd";
import "antd/dist/reset.css";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { API_BASE_URL, apiRequest, errorNotice } from "./api";
import type {
  AgentTestResponse,
  Health,
  JsonObject,
  Notice,
  Ontology,
  OntologyVersion,
  Project,
} from "./types";
import { classNames, compactId, formatDate, prettyJson } from "./utils";
import { ClassesPage } from "./pages/ClassesPage";
import { EntitiesPage } from "./pages/EntitiesPage";
import { ProjectBriefPage } from "./pages/ProjectBriefPage";
import { FactAuditPage } from "./pages/FactAuditPage";
import { PublicationPage } from "./pages/PublicationPage";
import { VersionsPage } from "./pages/VersionsPage";
import { GraphGovernancePage } from "./pages/GraphGovernancePage";
import { NamedGraphsPage } from "./pages/NamedGraphsPage";
import { GraphSetPage } from "./pages/GraphSetPage";
import { SemanticRunsPage } from "./pages/SemanticRunsPage";
import { SemanticEditWorkbenchPage } from "./pages/SemanticEditWorkbenchPage";
import { SemanticImportExportPage } from "./pages/SemanticImportExportPage";
import { WorkflowProgress } from "./components/WorkflowProgress";
import { ConfirmActionDialog } from "./components/workbench";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { useT } from "./i18n";

type AppView = "home" | "workspace";
type WorkspaceTab =
  | "brief"
  | "facts"
  | "publication"
  | "classes"
  | "entities"
  | "versions"
  | "agent-test"
  | "mcp-tools"
  | "setting"
  | "graph-governance"
  | "named-graphs"
  | "graph-sets"
  | "semantic-edits"
  | "semantic-runs"
  | "semantic-import-export";
type WorkspaceStage = "intake" | "knowledge" | "publish" | "tools" | "governance";
type Requester = <T,>(path: string, options?: RequestInit) => Promise<T>;

const UI_KEYS = {
  project: "ontology-platform-ui-selected-project",
  ontology: "ontology-platform-ui-selected-ontology",
  workspaceTab: "ontology-platform-ui-workspace-tab-v3",
} as const;

const stageMeta: Array<{
  id: WorkspaceStage;
  label: string;
  detail: string;
  icon: typeof Network;
  workflowStatuses?: string[];
}> = [
  { id: "intake", label: "Intake", detail: "Brief", icon: BookOpen, workflowStatuses: ["gathering"] },
  { id: "knowledge", label: "Modeling", detail: "Classes · entities · facts", icon: GitBranch, workflowStatuses: ["schema_draft", "schema_review", "graph_building", "graph_review", "validated"] },
  { id: "governance", label: "Governance", detail: "Graphs · graph sets · semantic edit · runs · import/export", icon: ShieldCheck },
  { id: "publish", label: "Publish", detail: "Publication · versions", icon: Flag, workflowStatuses: ["published"] },
  { id: "tools", label: "Tools", detail: "Agent · MCP · settings", icon: Wrench },
];

const stageDefaultTab: Record<WorkspaceStage, WorkspaceTab> = {
  intake: "brief",
  knowledge: "classes",
  governance: "graph-governance",
  publish: "publication",
  tools: "agent-test",
};

const workflowStatusToStage: Record<string, WorkspaceStage> = {
  gathering: "intake",
  schema_draft: "knowledge",
  schema_review: "knowledge",
  graph_building: "knowledge",
  graph_review: "knowledge",
  validated: "knowledge",
  published: "publish",
};

const workspaceTabs: Array<{
  id: WorkspaceTab;
  stage: WorkspaceStage;
  label: string;
  detail: string;
  icon: typeof Network;
}> = [
  { id: "brief", stage: "intake", label: "Brief", detail: "Scope & intent", icon: BookOpen },
  { id: "classes", stage: "knowledge", label: "Classes", detail: "Class topology", icon: Layers },
  { id: "entities", stage: "knowledge", label: "Entities", detail: "Entity editor", icon: Database },
  { id: "facts", stage: "knowledge", label: "Facts", detail: "Layered fact audit", icon: ShieldCheck },
  { id: "publication", stage: "publish", label: "Publication", detail: "Readiness & release", icon: Flag },
  { id: "versions", stage: "publish", label: "Versions", detail: "Lineage & diff", icon: History },
  { id: "agent-test", stage: "tools", label: "Agent Test", detail: "Question runs", icon: Send },
  { id: "mcp-tools", stage: "tools", label: "MCP Tools", detail: "Tool catalog", icon: Wrench },
  { id: "setting", stage: "tools", label: "Settings", detail: "Runtime status", icon: Settings },
  { id: "graph-governance", stage: "governance", label: "Graph Governance", detail: "Status · graph sets · audits", icon: ShieldCheck },
  { id: "named-graphs", stage: "governance", label: "Named Graphs", detail: "Registry · editability", icon: Database },
  { id: "graph-sets", stage: "governance", label: "Graph Sets", detail: "Members · runs · exports", icon: Layers },
  { id: "semantic-edits", stage: "governance", label: "Semantic Edit", detail: "Direct workbench", icon: ShieldCheck },
  { id: "semantic-runs", stage: "governance", label: "Semantic Runs", detail: "Validation · reasoning · rule", icon: History },
  { id: "semantic-import-export", stage: "governance", label: "Import / Export", detail: "Standards exchange", icon: Upload },
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

export function App() {
  const t = useT();
  const [view, setView] = useState<AppView>(() => queryValue("ontology") ? "workspace" : "home");
  const requestedTab = queryValue("tab");
  const [workspaceTab, setWorkspaceTab] = useStoredWorkspaceTab(
    UI_KEYS.workspaceTab,
    isWorkspaceTab(requestedTab) ? requestedTab : "brief",
  );
  const [projects, setProjects] = useState<Project[]>([]);
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [versions, setVersions] = useState<OntologyVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState(() => queryValue("version"));
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useStoredString(UI_KEYS.project, queryValue("project"));
  const [selectedOntologyId, setSelectedOntologyId] = useStoredString(UI_KEYS.ontology, queryValue("ontology"));
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
    if (pageDirty && !window.confirm(t("Discard unsaved changes and leave this page?"))) return;
    setPageDirty(false);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    for (const key of ["proposal", "claim", "item", "graph", "graphSet", "run", "category"]) {
      if (!(key in params)) url.searchParams.delete(key);
    }
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
    window.history.pushState(null, "", url);
    setWorkspaceTab(tab);
  }, [pageDirty, setWorkspaceTab, t]);

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
      data.some((project) => project.id === current) ? current : data[0]?.id ?? "",
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
      setSelectedOntologyId((current) => current || "");
    },
    [request, selectedProjectId, setSelectedOntologyId],
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
        (current) => current || data[data.length - 1]?.id || "",
      );
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
    if (selectedProjectId) {
      if (!projects.length) return;
      if (!projects.some((project) => project.id === selectedProjectId)) return;
    }
    loadOntologies().catch(showError);
  }, [selectedProjectId, projects, loadOntologies, showError]);

  useEffect(() => {
    loadVersions().catch(showError);
  }, [selectedOntologyId, loadVersions, showError]);

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
    setSelectedVersionId("");
    setWorkspaceTab("brief");
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
              <span className="eyebrow">{t("Ontology workspace")}</span>
              <h1>{t("Ontologies")}</h1>
              <div className="crumbTrail">
                <span>{selectedProject?.name ?? t("No project")}</span>
                <ChevronRight size={13} />
                <span>{t("{count} ontologies", { count: ontologies.length })}</span>
              </div>
            </div>
            <div className="topActions">
              <LanguageSwitcher />
              <Tooltip title={t("Refresh workspace data")}>
                <button className="iconButton" disabled={loading} onClick={refreshAll} type="button">
                  {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
                </button>
              </Tooltip>
            </div>
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
                <strong>{t("Ontology Platform")}</strong>
                <span>{t("Back to ontology list")}</span>
              </div>
            </button>
            <nav className="mainNav" aria-label={t("Ontology workspace navigation")}>
              {stageMeta.map((stage) => {
                const tabsInStage = workspaceTabs.filter((item) => item.stage === stage.id);
                if (!tabsInStage.length) return null;
                const StageIcon = stage.icon;
                const activeStage = workflowStatusToStage[selectedVersion?.workflow_status ?? "gathering"] ?? "intake";
                const tabStage = workspaceTabs.find((item) => item.id === workspaceTab)?.stage;
                const isActiveStage = tabStage === stage.id;
                const isWorkflowStage = stage.id === activeStage;
                return (
                  <section
                    className={classNames(
                      "navGroup",
                      "navStage",
                      isActiveStage && "stageActive",
                      isWorkflowStage && "stageCurrent",
                    )}
                    key={stage.id}
                  >
                    <button
                      className="navStageHeader"
                      onClick={() => navigateWorkspace(stageDefaultTab[stage.id])}
                      type="button"
                    >
                      <StageIcon size={15} />
                      <span><strong>{t(stage.label)}</strong><small>{t(stage.detail)}</small></span>
                      {isWorkflowStage && <span className="navStageDot" aria-label={t("Current workflow stage")} />}
                    </button>
                    <div className="navStageTabs">
                      {tabsInStage.map((item) => {
                        const Icon = item.icon;
                        return (
                          <button
                            className={classNames("navButton", "navStageButton", workspaceTab === item.id && "active")}
                            key={item.id}
                            onClick={() => navigateWorkspace(item.id)}
                            type="button"
                          >
                            <Icon size={15} />
                            <span>{t(item.label)}</span>
                          </button>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </nav>
            <div className="railFooter">
              <span>{t("API")}</span>
              <code>{API_BASE_URL}</code>
              <div className="railFooterSwitcher"><LanguageSwitcher /></div>
            </div>
          </aside>

          <section className="workbench">
            <header className="topBar">
              <div className="titleBlock">
                <span className="eyebrow">{t("Ontology workspace")}</span>
                <h1>{t(activeTab.label)}</h1>
                <div className="crumbTrail">
                  <button className="crumbButton" onClick={() => setView("home")} type="button">
                    {selectedProject?.name ?? t("Projects")}
                  </button>
                  <ChevronRight size={13} />
                  <span>{selectedOntology?.name ?? t("No ontology")}</span>
                  <ChevronRight size={13} />
                  <span>{t(activeTab.label)}</span>
                </div>
              </div>
              <div className="topActions">
                <label className="versionSelector">
                  <span>{t("Version")}</span>
                  <select
                    aria-label={t("Active ontology version")}
                    onChange={(event) => setSelectedVersionId(event.target.value)}
                    value={selectedVersionId}
                  >
                    {!versions.length && <option value="">{t("No versions")}</option>}
                    {versions.map((version) => (
                      <option key={version.id} value={version.id}>
                        {t("v{n} · {status}", { n: version.version_number, status: version.status })}
                      </option>
                    ))}
                  </select>
                </label>
                {selectedVersion?.status === "published" && <span className="readOnlyPill">{t("Read-only")}</span>}
                <button className="secondaryButton" onClick={() => setView("home")} type="button">
                  <ArrowLeft size={15} /> {t("Ontologies")}
                </button>
                <Tooltip title={t("Refresh ontology data")}>
                  <button
                    className="iconButton"
                    disabled={loading}
                    onClick={() => loadVersions().catch(showError)}
                    type="button"
                  >
                    {loading ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
                  </button>
                </Tooltip>
              </div>
            </header>

            {selectedVersion && (
              <div className="workflowProgressHost">
                <WorkflowProgress
                  status={selectedVersion.workflow_status}
                  variant="compact"
                  stageDefaultTab={{
                    gathering: "brief",
                    schema_draft: "classes",
                    schema_review: "classes",
                    graph_building: "entities",
                    graph_review: "entities",
                    validated: "facts",
                    published: "publication",
                  }}
                  onStageClick={(_stage, tab) => navigateWorkspace(tab)}
                />
              </div>
            )}

            {notice && <StatusBanner notice={notice} onDismiss={() => setNotice(null)} />}

            <div className="contentFrame">
              {!selectedOntology || !selectedProject ? (
                <EmptyState
                  icon={<Waypoints size={22} />}
                  title={t("The linked project and ontology context is not available")}
                />
              ) : (
                <WorkspaceContent
                  health={health}
                  mutate={mutate}
                  notify={setNotice}
                  ontology={selectedOntology}
                  project={selectedProject}
                  selectedVersion={selectedVersion}
                  selectedVersionId={selectedVersionId}
                  versions={versions}
                  request={request}
                  setHealth={setHealth}
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
  const t = useT();
  const [projectForm, setProjectForm] = useState({ name: "", description: "" });
  const [ontologyForm, setOntologyForm] = useState({ name: "", description: "" });
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const selectedProject = props.projects.find((project) => project.id === props.selectedProjectId) ?? null;

  function createProject(event: React.FormEvent) {
    event.preventDefault();
    props.mutate(async () => {
      const created = await props.request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name: projectForm.name, description: projectForm.description || null }),
      });
      setProjectForm({ name: "", description: "" });
      props.setSelectedProjectId(created.id);
      await props.reloadProjects();
    }, t("Project created"));
  }

  function createOntology(event: React.FormEvent) {
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
    }, t("Ontology created"));
  }

  function deleteOntology(ontology: Ontology) {
    props.mutate(async () => {
      await props.request<void>(`/ontologies/${ontology.id}`, { method: "DELETE" });
      if (props.selectedOntologyId === ontology.id) props.setSelectedOntologyId("");
      await props.reloadOntologies(props.selectedProjectId);
    }, t("Ontology deleted"));
  }

  function deleteProject() {
    if (!deleteTarget) return;
    const target = deleteTarget;
    props.mutate(async () => {
      await props.request<void>(`/projects/${target.id}`, { method: "DELETE" });
      if (props.selectedProjectId === target.id) {
        props.setSelectedProjectId("");
        props.setSelectedOntologyId("");
      }
      setDeleteTarget(null);
      await props.reloadProjects();
      await props.reloadOntologies("");
    }, t("Project deleted"));
  }

  return (
    <section className="homeLayout">
      <div className="homePrimary">
        <div className="homeFilterBar">
          <label>
            <span>{t("Project")}</span>
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
                <option value="">{t("No projects")}</option>
              )}
            </select>
          </label>
          {selectedProject && (
            <button
              className="iconButton danger"
              onClick={() => setDeleteTarget(selectedProject)}
              title={t("Delete project")}
              type="button"
            >
              <Trash2 size={15} />
            </button>
          )}
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
                  <span>{ontology.description || t("No description provided.")}</span>
                  <dl>
                    <dt>{t("Updated")}</dt>
                    <dd>{formatDate(ontology.updated_at)}</dd>
                  </dl>
                </button>
                <button
                  className="iconButton danger ontologyCardDelete"
                  onClick={() => deleteOntology(ontology)}
                  title={t("Delete ontology")}
                  type="button"
                >
                  <Trash2 size={15} />
                </button>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState icon={<Waypoints size={22} />} title={t("No ontologies in this project")} />
        )}
      </div>

      <aside className="homeSide">
        <Panel title={t("Add ontology")} icon={<Plus size={17} />}>
          <form className="stackForm" onSubmit={createOntology}>
            <input
              required
              placeholder={t("Ontology name")}
              value={ontologyForm.name}
              onChange={(event) => setOntologyForm({ ...ontologyForm, name: event.target.value })}
            />
            <textarea
              placeholder={t("Description")}
              value={ontologyForm.description}
              onChange={(event) => setOntologyForm({ ...ontologyForm, description: event.target.value })}
            />
            <button className="primaryButton" disabled={!props.selectedProjectId} type="submit">
              <Plus size={15} /> {t("Create ontology")}
            </button>
          </form>
          <div className="callout quiet">
            <strong>{selectedProject?.name ?? t("No project selected")}</strong>
            <span>{t("New ontologies are created inside the selected project.")}</span>
          </div>
        </Panel>

        {!props.projects.length && (
          <Panel title={t("Create project")} icon={<Layers size={17} />}>
            <form className="stackForm" onSubmit={createProject}>
              <input
                required
                placeholder={t("Project name")}
                value={projectForm.name}
                onChange={(event) => setProjectForm({ ...projectForm, name: event.target.value })}
              />
              <textarea
                placeholder={t("Description")}
                value={projectForm.description}
                onChange={(event) => setProjectForm({ ...projectForm, description: event.target.value })}
              />
              <button className="primaryButton" type="submit">
                <Plus size={15} /> {t("Create project")}
              </button>
            </form>
          </Panel>
        )}
      </aside>

      <ConfirmActionDialog
        open={deleteTarget !== null}
        title={t("Delete project")}
        danger
        confirmLabel={t("Delete project")}
        warning={t("This permanently deletes \"{name}\" and all ontologies, entities, relations, evidence, and proposals inside it.", { name: deleteTarget?.name ?? "" })}
        onConfirm={deleteProject}
        onCancel={() => setDeleteTarget(null)}
      >
        <p>{t("This cannot be undone.")}</p>
      </ConfirmActionDialog>
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
  health: Health | null;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  notify: (notice: Notice) => void;
  reloadVersions: () => Promise<void>;
  setSelectedVersionId: (id: string) => void;
  navigateWorkspace: (tab: string, params?: Record<string, string>) => void;
  setPageDirty: (dirty: boolean) => void;
  setHealth: (health: Health | null) => void;
  showError: (error: unknown) => void;
}) {
  const readOnly = props.selectedVersion?.status === "published";
  const t = useT();
  const governedRequest = useCallback<Requester>(
    (path, options) => {
      const method = (options?.method ?? "GET").toUpperCase();
      if (readOnly && method !== "GET" && method !== "HEAD") {
        return Promise.reject(new Error(t("Locked ontology versions are immutable. Create a new draft to make changes.")));
      }
      return props.request(path, options);
    },
    [props.request, readOnly, t],
  );

  if (props.tab === "brief") {
    return <ProjectBriefPage onDirtyChange={props.setPageDirty} projectId={props.project.id} readOnly={readOnly} request={governedRequest} />;
  }

  if (props.tab === "classes") {
    const graphSetId = queryValue("graphSet");
    if (!graphSetId) {
      return (
        <EmptyState
          icon={<Database size={22} />}
          title={t("Select a graph set to view classes")}
          action={
            <button className="primaryButton" onClick={() => props.navigateWorkspace("graph-sets")} type="button">
              <Layers size={15} /> {t("Open Graph Sets")}
            </button>
          }
        />
      );
    }
    return (
      <ClassesPage
        graphSetId={graphSetId}
        ontologyId={props.ontology.id}
        readOnly={readOnly}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "entities") {
    const graphSetId = queryValue("graphSet");
    if (!graphSetId) {
      return (
        <EmptyState
          icon={<Database size={22} />}
          title={t("Select a graph set to view entities")}
          action={
            <button className="primaryButton" onClick={() => props.navigateWorkspace("graph-sets")} type="button">
              <Layers size={15} /> {t("Open Graph Sets")}
            </button>
          }
        />
      );
    }
    return (
      <EntitiesPage
        graphSetId={graphSetId}
        ontologyId={props.ontology.id}
        readOnly={readOnly}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "facts") {
    if (!props.selectedVersion) return <EmptyState icon={<History size={22} />} title={t("Select a valid ontology version")} />;
    const graphSetId = queryValue("graphSet");
    if (!graphSetId) {
      return (
        <EmptyState
          icon={<Database size={22} />}
          title={t("Select a graph set to audit facts")}
          action={
            <button className="primaryButton" onClick={() => props.navigateWorkspace("graph-sets")} type="button">
              <Layers size={15} /> {t("Open Graph Sets")}
            </button>
          }
        />
      );
    }
    return (
      <FactAuditPage
        graphSetId={graphSetId}
        ontologyId={props.ontology.id}
        readOnly={readOnly}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "publication") {
    const graphSetId = queryValue("graphSet");
    if (!graphSetId) {
      return (
        <EmptyState
          icon={<History size={22} />}
          title={t("Select a graph set to view publication readiness")}
          action={
            <button className="primaryButton" onClick={() => props.navigateWorkspace("graph-sets")} type="button">
              <Layers size={15} /> {t("Open Graph Sets")}
            </button>
          }
        />
      );
    }
    return (
      <PublicationPage
        request={governedRequest}
        graphSetId={graphSetId}
        readOnly={readOnly}
      />
    );
  }

  if (props.tab === "versions") {
    if (!props.selectedVersion) return <EmptyState icon={<History size={22} />} title={t("Select a valid ontology version")} />;
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

  if (props.tab === "agent-test") {
    return <AgentTestPage ontology={props.ontology} request={governedRequest} mutate={props.mutate} />;
  }

  if (props.tab === "mcp-tools") {
    return <McpToolsPage />;
  }

  if (props.tab === "graph-governance") {
    return (
      <GraphGovernancePage
        navigate={props.navigateWorkspace}
        notify={props.notify}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "named-graphs") {
    return (
      <NamedGraphsPage
        initialCategory={queryValue("category") || undefined}
        notify={props.notify}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "graph-sets") {
    return (
      <GraphSetPage
        initialGraphSetId={queryValue("graphSet") || undefined}
        navigate={props.navigateWorkspace}
        notify={props.notify}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "semantic-edits") {
    return (
      <SemanticEditWorkbenchPage
        initialGraphSetId={queryValue("graphSet") || undefined}
        initialTargetGraphIri={queryValue("graph") || undefined}
        notify={props.notify}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "semantic-runs") {
    const runParam = queryValue("run");
    const [runKind, runId] = runParam.includes(":") ? runParam.split(":") : ["", runParam];
    return (
      <SemanticRunsPage
        initialRunId={runId || undefined}
        initialRunKind={(runKind as "validation" | "reasoning" | "rule") || undefined}
        notify={props.notify}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "semantic-import-export") {
    return (
      <SemanticImportExportPage
        initialGraphSetId={queryValue("graphSet") || undefined}
        notify={props.notify}
        request={governedRequest}
      />
    );
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

function AgentTestPage(props: {
  ontology: Ontology;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
}) {
  const t = useT();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AgentTestResponse | null>(null);

  function run(event: React.FormEvent) {
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
    }, t("Agent test completed"));
  }

  return (
    <section className="agentLayout">
      <Panel title={t("Agent test")} icon={<Play size={17} />}>
        <form className="stackForm" onSubmit={run}>
          <textarea
            className="questionBox"
            required
            placeholder={t("Ask a question against the selected ontology")}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button className="primaryButton" type="submit">
            <Play size={15} /> {t("Run")}
          </button>
        </form>
      </Panel>

      <Panel title={t("Run output")} icon={<Clipboard size={17} />} className="agentOutput">
        {result ? (
          <div className="resultGrid">
            <ResultBlock title={t("Answer")} value={result.answer} />
            <Timeline title={t("Tool calls")} items={result.tool_calls} />
            <ResultBlock title={t("Graph context")} value={result.graph_context} copyable />
            <ResultBlock title={t("Prompt preview")} value={result.prompt_preview} />
            <ResultBlock title={t("Warnings")} value={result.warnings} />
            <ResultBlock title={t("Errors")} value={result.errors} />
          </div>
        ) : (
          <EmptyState icon={<Send size={22} />} title={t("No run output yet")} />
        )}
      </Panel>
    </section>
  );
}

function McpToolsPage() {
  const t = useT();
  const tools = [
    ["search_entities", "Recall entities globally with text, vector, or hybrid search."],
    ["get_entity", "Fetch one entity and direct relations by entity id."],
    ["find_related_entities", "Find related entities by depth and direction."],
    ["validate_entity", "Validate entity data against class schema."],
    ["explain_entity", "Generate entity context and explanation."],
  ];

  return (
    <section className="mcpToolsPage">
      <Panel title={t("MCP tools")} icon={<Wrench size={17} />} wide>
        <div className="toolList">
          {tools.map(([tool, description]) => (
            <div className="toolRow" key={tool}>
              <div>
                <strong>{tool}</strong>
                <span>{t(description)}</span>
              </div>
              <Badge>{t("server")}</Badge>
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
  const t = useT();
  async function checkHealth() {
    try {
      props.setHealth(await props.request<Health>("/health/dependencies"));
    } catch (error) {
      props.showError(error);
    }
  }

  return (
    <section className="pageGrid systemGrid">
      <Panel title={t("Ontology")} icon={<Waypoints size={17} />}>
        <dl className="detailList">
          <dt>{t("Name")}</dt>
          <dd>{props.ontology.name}</dd>
          <dt>{t("Status")}</dt>
          <dd><Badge>{props.ontology.status}</Badge></dd>
          <dt>{t("Updated")}</dt>
          <dd>{formatDate(props.ontology.updated_at)}</dd>
        </dl>
      </Panel>
      <Panel title={t("Connection")} icon={<Activity size={17} />}>
        <dl className="detailList">
          <dt>{t("API base URL")}</dt>
          <dd><code>{API_BASE_URL}</code></dd>
        </dl>
      </Panel>
      <Panel title={t("Dependencies")} icon={<Activity size={17} />} wide>
        <button className="primaryButton" onClick={checkHealth} type="button">
          <RefreshCw size={15} /> {t("Check")}
        </button>
        {props.health ? (
          <pre className="jsonBlock">{prettyJson(props.health)}</pre>
        ) : (
          <EmptyState icon={<Activity size={20} />} title={t("No health check yet")} />
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

function EmptyState(props: { icon: ReactNode; title: string; action?: ReactNode }) {
  return (
    <div className="emptyState">
      {props.icon}
      <span>{props.title}</span>
      {props.action}
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
