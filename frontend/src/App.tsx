import {
  Activity,
  ArrowLeft,
  BookOpen,
  Check,
  ChevronRight,
  Database,
  FileText,
  Flag,
  GitBranch,
  History,
  Layers,
  Loader2,
  Lock,
  Network,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Trash2,
  Unlock,
  Upload,
  Waypoints,
  Workflow,
  Wrench,
  X,
} from "lucide-react";
// Note: CircleGauge removed (overview tab gone), as were FileCheck2/FileText/Link2/Save/Braces/Box.
import { Card, ConfigProvider, Modal, Progress, Tag, Tooltip } from "antd";
import "antd/dist/reset.css";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { API_BASE_URL, apiRequest, errorNotice } from "./api";
import type {
  Health,
  Notice,
  Ontology,
  Project,
} from "./types";
import { classNames, compactId, formatDate, prettyJson } from "./utils";
import { ClassesPage } from "./pages/ClassesPage";
import { EntitiesPage } from "./pages/EntitiesPage";
import { RulesPage } from "./pages/RulesPage";
import { EntitiesSearchPage } from "./pages/EntitiesSearchPage";
import { RequirementQuestionsPage } from "./pages/RequirementQuestionsPage";
import { EvidenceReferencesPage } from "./pages/EvidenceReferencesPage";
import { AgentTestPage } from "./pages/AgentTestPage";
import { McpToolsPage } from "./pages/McpToolsPage";
import { FactAuditPage } from "./pages/FactAuditPage";
import { GraphSetHistoryPage } from "./pages/GraphSetHistoryPage";
import { PublicationPage } from "./pages/PublicationPage";
import { NamedGraphsPage } from "./pages/NamedGraphsPage";
import { GraphSetPage } from "./pages/GraphSetPage";
import { SemanticRunsPage } from "./pages/SemanticRunsPage";
import { SemanticEditWorkbenchPage } from "./pages/SemanticEditWorkbenchPage";
import { SemanticImportExportPage } from "./pages/SemanticImportExportPage";
import { ConfirmActionDialog } from "./components/workbench";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { useT } from "./i18n";
import {
  getGovernanceStatus,
  getProjectionStatus,
  listGraphSets,
  listReasoningRuns,
  listRuleRuns,
  listValidationRuns,
} from "./semanticApi";
import type {
  SemanticGovernanceStatusResponse,
  SemanticGraphSetListResponse,
  SemanticProjectionStatusResponse,
  SemanticReasoningRunListResponse,
  SemanticRuleRunListResponse,
  SemanticValidationRunListResponse,
} from "./types";

type AppView = "home" | "workspace";
type WorkspaceTab =
  | "brief"
  | "questions"
  | "evidence"
  | "facts"
  | "publication"
  | "classes"
  | "entities"
  | "rules"
  | "graph-set-history"
  | "agent-test"
  | "search"
  | "mcp-tools"
  | "setting"
  | "graph-governance"
  | "named-graphs"
  | "graph-sets"
  | "semantic-edits"
  | "semantic-runs"
  | "semantic-import-export";
type WorkspaceStage = "intake" | "knowledge" | "publish" | "tools" | "governance";
type VisibleWorkspaceStage = "overview" | "modeling" | "debug" | "settings";
type Requester = <T,>(path: string, options?: RequestInit) => Promise<T>;

const UI_KEYS = {
  project: "ontology-platform-ui-selected-project",
  ontology: "ontology-platform-ui-selected-ontology",
  workspaceTab: "ontology-platform-ui-workspace-tab-v4",
} as const;

const stageMeta: Array<{
  id: VisibleWorkspaceStage;
  label: string;
  detail: string;
  icon: typeof Network;
}> = [
  { id: "overview", label: "Overview", detail: "Brief · questions", icon: BookOpen },
  { id: "modeling", label: "Modeling", detail: "Classes · entities · facts", icon: GitBranch },
  { id: "debug", label: "Debug", detail: "Agent · recall · runtime", icon: ShieldCheck },
  { id: "settings", label: "Settings", detail: "Edit lock · platform", icon: Settings },
];

const stageDefaultTab: Record<VisibleWorkspaceStage, WorkspaceTab> = {
  overview: "brief",
  modeling: "classes",
  debug: "graph-governance",
  settings: "setting",
};

const workspaceTabs: Array<{
  id: WorkspaceTab;
  stage: VisibleWorkspaceStage;
  label: string;
  detail: string;
  icon: typeof Network;
}> = [
  { id: "brief", stage: "overview", label: "Overview", detail: "Brief · status", icon: BookOpen },
  { id: "questions", stage: "overview", label: "Structured Requirements", detail: "Requirement clarification", icon: Check },
  { id: "evidence", stage: "overview", label: "Evidence", detail: "Shared source excerpts", icon: FileText },
  { id: "classes", stage: "modeling", label: "Classes", detail: "Class diagram", icon: Layers },
  { id: "entities", stage: "modeling", label: "Entities", detail: "Entity diagram", icon: Database },
  { id: "rules", stage: "modeling", label: "Rules", detail: "Rule definitions", icon: Workflow },
  { id: "facts", stage: "modeling", label: "Facts", detail: "Fact list", icon: ShieldCheck },
  { id: "graph-governance", stage: "debug", label: "Debug", detail: "Validation · projection · runtime", icon: Wrench },
  { id: "agent-test", stage: "debug", label: "Agent Test", detail: "Question runs", icon: Send },
  { id: "search", stage: "debug", label: "Recall", detail: "Entity search", icon: Search },
  { id: "mcp-tools", stage: "debug", label: "MCP Tools", detail: "Tool catalog", icon: Wrench },
  { id: "graph-sets", stage: "debug", label: "Graph Sets", detail: "Members · runs", icon: Layers },
  { id: "setting", stage: "settings", label: "Settings", detail: "Edit lock · platform", icon: Settings },
];

const legacyWorkspaceTabs: Array<{
  id: WorkspaceTab;
  stage: WorkspaceStage;
  label: string;
  detail: string;
  icon: typeof Network;
}> = [
  { id: "publication", stage: "publish", label: "Publication", detail: "Readiness & release", icon: Flag },
  { id: "graph-set-history", stage: "publish", label: "Graph Set History", detail: "Lineage & diff", icon: History },
  { id: "named-graphs", stage: "governance", label: "Named Graphs", detail: "Registry · editability", icon: Database },
  { id: "semantic-edits", stage: "governance", label: "Semantic Edit", detail: "Direct workbench", icon: ShieldCheck },
  { id: "semantic-runs", stage: "governance", label: "Semantic Runs", detail: "Validation · reasoning · rule", icon: History },
  { id: "semantic-import-export", stage: "governance", label: "Import / Export", detail: "Standards exchange", icon: Upload },
];

const allWorkspaceTabs = [...workspaceTabs, ...legacyWorkspaceTabs];
const legacyTabRedirects: Partial<Record<WorkspaceTab, WorkspaceTab>> = {
  publication: "brief",
  "graph-set-history": "graph-governance",
  "named-graphs": "graph-governance",
  "semantic-edits": "graph-governance",
  "semantic-runs": "graph-governance",
  "semantic-import-export": "graph-governance",
};

function normalizeWorkspaceTab(tab: WorkspaceTab): WorkspaceTab {
  return legacyTabRedirects[tab] ?? tab;
}

function isWorkspaceTab(value: string | null): value is WorkspaceTab {
  return allWorkspaceTabs.some((tab) => tab.id === value);
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
      return isWorkspaceTab(stored) ? normalizeWorkspaceTab(stored) : fallback;
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
    isWorkspaceTab(requestedTab) ? normalizeWorkspaceTab(requestedTab) : "brief",
  );
  const [projects, setProjects] = useState<Project[]>([]);
  const [ontologies, setOntologies] = useState<Ontology[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useStoredString(UI_KEYS.project, queryValue("project"));
  const [selectedOntologyId, setSelectedOntologyId] = useStoredString(UI_KEYS.ontology, queryValue("ontology"));
  const [notice, setNotice] = useState<Notice>(null);
  const [loading, setLoading] = useState(false);
  const [pageDirty, setPageDirty] = useState(false);

  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const selectedOntology = ontologies.find((ontology) => ontology.id === selectedOntologyId) ?? null;
  const activeTab = allWorkspaceTabs.find((tab) => tab.id === workspaceTab) ?? workspaceTabs[0];

  const request = useCallback(<T,>(path: string, options?: RequestInit) => apiRequest<T>(path, options), []);
  const showError = useCallback((error: unknown) => setNotice(errorNotice(error)), []);
  const navigateWorkspace = useCallback((tab: string, params: Record<string, string> = {}) => {
    if (!isWorkspaceTab(tab)) return;
    const normalizedTab = normalizeWorkspaceTab(tab);
    if (pageDirty && !window.confirm(t("Discard unsaved changes and leave this page?"))) return;
    setPageDirty(false);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", normalizedTab);
    for (const key of ["proposal", "claim", "item", "graph", "graphSet", "run", "category"]) {
      if (!(key in params)) url.searchParams.delete(key);
    }
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
    window.history.pushState(null, "", url);
    setWorkspaceTab(normalizedTab);
  }, [pageDirty, setWorkspaceTab, t]);

  useEffect(() => {
    const linkedProject = queryValue("project");
    const linkedOntology = queryValue("ontology");
    const linkedTab = queryValue("tab");
    if (linkedProject) setSelectedProjectId(linkedProject);
    if (linkedOntology) setSelectedOntologyId(linkedOntology);
    if (isWorkspaceTab(linkedTab)) setWorkspaceTab(normalizeWorkspaceTab(linkedTab));
  }, [setSelectedOntologyId, setSelectedProjectId, setWorkspaceTab]);

  useEffect(() => {
    if (view !== "workspace" || !selectedProjectId || !selectedOntologyId) return;
    const params = new URLSearchParams(window.location.search);
    params.set("project", selectedProjectId);
    params.set("ontology", selectedOntologyId);
    params.set("tab", workspaceTab);
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }, [selectedOntologyId, selectedProjectId, view, workspaceTab]);

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
            loading={loading}
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
                const tabStage = workspaceTabs.find((item) => item.id === workspaceTab)?.stage;
                const isActiveStage = tabStage === stage.id;
                return (
                  <section
                    className={classNames(
                      "navGroup",
                      "navStage",
                      isActiveStage && "stageActive",
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
                <button className="secondaryButton" onClick={() => setView("home")} type="button">
                  <ArrowLeft size={15} /> {t("Ontologies")}
                </button>
                <Tooltip title={t("Refresh workspace data")}>
                  <button
                    className="iconButton"
                    disabled={loading}
                    onClick={refreshAll}
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
                  title={t("The linked project and ontology context is not available")}
                />
              ) : (
                <WorkspaceContent
                  health={health}
                  mutate={mutate}
                  notify={setNotice}
                  ontology={selectedOntology}
                  project={selectedProject}
                  request={request}
                  setHealth={setHealth}
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
  loading: boolean;
}) {
  const t = useT();
  const [projectForm, setProjectForm] = useState({ name: "", description: "" });
  const [ontologyForm, setOntologyForm] = useState({ name: "", description: "" });
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [createOntologyOpen, setCreateOntologyOpen] = useState(false);
  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const selectedProject = props.projects.find((project) => project.id === props.selectedProjectId) ?? null;

  function createProject() {
    if (!projectForm.name.trim()) return;
    props.mutate(async () => {
      const created = await props.request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name: projectForm.name, description: projectForm.description || null }),
      });
      setProjectForm({ name: "", description: "" });
      setCreateProjectOpen(false);
      props.setSelectedProjectId(created.id);
      await props.reloadProjects();
    }, t("Project created"));
  }

  function createOntology() {
    if (!props.selectedProjectId || !ontologyForm.name.trim()) return;
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
      setCreateOntologyOpen(false);
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
    <section className="homeLayout homeLayoutFull">
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
          <div className="homeFilterActions">
            <button
              className="primaryButton"
              onClick={() => setCreateProjectOpen(true)}
              type="button"
            >
              <Plus size={15} /> {t("Create project")}
            </button>
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
        </div>

        <div className="ontologyCardGrid homeOntologyGrid">
          {props.ontologies.map((ontology) => (
            <article
              className={classNames("ontologyCard", ontology.id === props.selectedOntologyId && "selected")}
              key={ontology.id}
            >
              <button className="ontologyCardMain" onClick={() => props.onOpenOntology(ontology)} type="button">
                <span className="ontologyCardTop">
                  <strong>{ontology.name}</strong>
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
          <button
            className="createOntologyCard"
            disabled={!props.selectedProjectId}
            onClick={() => setCreateOntologyOpen(true)}
            type="button"
          >
            <span className="createOntologyCardIcon">
              <Plus size={20} />
            </span>
            <strong>{t("Add ontology")}</strong>
            <span>{t("Create a new ontology in this project")}</span>
          </button>
        </div>
      </div>

      <Modal
        open={createProjectOpen}
        title={t("Create project")}
        okText={t("Create project")}
        cancelText={t("Cancel")}
        okButtonProps={{ disabled: !projectForm.name.trim() }}
        confirmLoading={props.loading}
        closable={!props.loading}
        maskClosable={!props.loading}
        keyboard={!props.loading}
        destroyOnHidden
        onOk={createProject}
        onCancel={() => setCreateProjectOpen(false)}
      >
        <form
          className="stackForm"
          onSubmit={(event) => {
            event.preventDefault();
            createProject();
          }}
        >
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
        </form>
      </Modal>

      <Modal
        open={createOntologyOpen}
        title={t("Add ontology")}
        okText={t("Create ontology")}
        cancelText={t("Cancel")}
        okButtonProps={{ disabled: !ontologyForm.name.trim() || !props.selectedProjectId }}
        confirmLoading={props.loading}
        closable={!props.loading}
        maskClosable={!props.loading}
        keyboard={!props.loading}
        destroyOnHidden
        onOk={createOntology}
        onCancel={() => setCreateOntologyOpen(false)}
      >
        <form
          className="stackForm"
          onSubmit={(event) => {
            event.preventDefault();
            createOntology();
          }}
        >
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
          <div className="callout quiet">
            <strong>{selectedProject?.name ?? t("No project selected")}</strong>
            <span>{t("New ontologies are created inside the selected project.")}</span>
          </div>
        </form>
      </Modal>

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
  health: Health | null;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  notify: (notice: Notice) => void;
  navigateWorkspace: (tab: string, params?: Record<string, string>) => void;
  setPageDirty: (dirty: boolean) => void;
  setHealth: (health: Health | null) => void;
  showError: (error: unknown) => void;
}) {
  const t = useT();
  const governedRequest = props.request;
  const lockStorageKey = `ontology-platform-ui-workspace-lock:${props.ontology.id}`;
  const [locked, setLocked] = useState(() => {
    try {
      return localStorage.getItem(lockStorageKey) === "locked";
    } catch {
      return false;
    }
  });
  const [graphSetId, setGraphSetId] = useState(() => queryValue("graphSet"));
  const [graphSetLoading, setGraphSetLoading] = useState(false);
  const [graphSetError, setGraphSetError] = useState("");
  const readOnly = locked;

  useEffect(() => {
    try {
      localStorage.setItem(lockStorageKey, locked ? "locked" : "unlocked");
    } catch {
      // Local storage is optional in embedded previews.
    }
  }, [lockStorageKey, locked]);

  useEffect(() => {
    const explicitGraphSetId = queryValue("graphSet");
    if (explicitGraphSetId) {
      setGraphSetId(explicitGraphSetId);
      return;
    }
    if (!["classes", "entities", "facts", "agent-test", "search", "publication", "graph-set-history"].includes(props.tab)) {
      return;
    }
    let cancelled = false;
    setGraphSetLoading(true);
    setGraphSetError("");
    listGraphSets(governedRequest, { scopeType: "ontology", scopeId: props.ontology.id })
      .then((data: SemanticGraphSetListResponse) => {
        if (cancelled) return;
        const activeId =
          data.graph_sets?.find((graphSet) => graphSet.status === "active")?.id ??
          data.graph_sets?.[0]?.id ??
          "";
        setGraphSetId(activeId);
      })
      .catch((error) => {
        if (!cancelled) setGraphSetError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (!cancelled) setGraphSetLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [governedRequest, props.ontology.id, props.tab]);

  const graphSetGate = (title: string) => (
    <EmptyState
      icon={graphSetLoading ? <Loader2 className="spin" size={22} /> : <Database size={22} />}
      title={graphSetLoading ? t("Preparing workspace data") : title}
      action={graphSetError ? <span className="inlineHint">{graphSetError}</span> : undefined}
    />
  );

  if (props.tab === "brief") {
    return (
      <OverviewPage
        navigateWorkspace={props.navigateWorkspace}
        notify={props.notify}
        projectId={props.project.id}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "questions") {
    return (
      <RequirementQuestionsPage
        onDirtyChange={props.setPageDirty}
        projectId={props.project.id}
        readOnly={readOnly}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "evidence") {
    return (
      <EvidenceReferencesPage
        ontologyId={props.ontology.id}
        projectId={props.project.id}
        readOnly={readOnly}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "classes") {
    if (!graphSetId) {
      return graphSetGate(t("Workspace data is not ready yet"));
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
    if (!graphSetId) {
      return graphSetGate(t("Workspace data is not ready yet"));
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
    if (!graphSetId) {
      return graphSetGate(t("Workspace data is not ready yet"));
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

  if (props.tab === "rules") {
    return (
      <RulesPage
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

  if (props.tab === "graph-set-history") {
    const graphSetId = queryValue("graphSet");
    if (!graphSetId) {
      return (
        <EmptyState
          icon={<History size={22} />}
          title={t("Select a graph set to view its history")}
          action={
            <button className="primaryButton" onClick={() => props.navigateWorkspace("graph-sets")} type="button">
              <Layers size={15} /> {t("Open Graph Sets")}
            </button>
          }
        />
      );
    }
    return (
      <GraphSetHistoryPage
        request={governedRequest}
        ontologyId={props.ontology.id}
        graphSetId={graphSetId}
        readOnly={readOnly}
      />
    );
  }

  if (props.tab === "agent-test") {
    if (!graphSetId) {
      return graphSetGate(t("Workspace data is not ready yet"));
    }
    return (
      <AgentTestPage
        ontology={props.ontology}
        graphSetId={graphSetId}
        request={governedRequest}
        mutate={props.mutate}
      />
    );
  }

  if (props.tab === "search") {
    if (!graphSetId) {
      return graphSetGate(t("Workspace data is not ready yet"));
    }
    return (
      <EntitiesSearchPage
        graphSetId={graphSetId}
        ontologyId={props.ontology.id}
        readOnly={readOnly}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "mcp-tools") {
    return <McpToolsPage request={governedRequest} />;
  }

  if (props.tab === "graph-governance") {
    return (
      <DebugPage
        navigateWorkspace={props.navigateWorkspace}
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
    <SettingsPage
      health={props.health}
      locked={locked}
      onLockedChange={setLocked}
      ontology={props.ontology}
      request={props.request}
      setHealth={props.setHealth}
      showError={props.showError}
    />
  );
}

function SettingsPage(props: {
  ontology: Ontology;
  health: Health | null;
  locked: boolean;
  onLockedChange: (locked: boolean) => void;
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
      <Panel title={t("Workspace edit lock")} icon={props.locked ? <Lock size={17} /> : <Unlock size={17} />} wide>
        <div className={classNames("lockStatePanel", props.locked ? "locked" : "unlocked")}>
          <div>
            <strong>{props.locked ? t("Workspace locked") : t("Workspace unlocked")}</strong>
            <p>
              {props.locked
                ? t("Modeling changes are paused. Unlock the workspace to create, edit, or delete classes, entities, relationships, and facts.")
                : t("Modeling changes take effect after backend validation. Lock the workspace to prevent accidental edits.")}
            </p>
          </div>
          <button
            className={props.locked ? "primaryButton" : "secondaryButton"}
            onClick={() => props.onLockedChange(!props.locked)}
            type="button"
          >
            {props.locked ? <Unlock size={15} /> : <Lock size={15} />}
            {props.locked ? t("Unlock workspace") : t("Lock workspace")}
          </button>
        </div>
      </Panel>
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

function OverviewPage(props: {
  projectId: string;
  navigateWorkspace: (tab: string, params?: Record<string, string>) => void;
  request: Requester;
  notify: (notice: Notice) => void;
}) {
  return (
    <div className="overviewWorkspace">
      <BriefCompletionPanel
        navigateWorkspace={props.navigateWorkspace}
        projectId={props.projectId}
        request={props.request}
      />
      <OverviewDiagnostics notify={props.notify} request={props.request} />
    </div>
  );
}

function BriefCompletionPanel(props: {
  projectId: string;
  navigateWorkspace: (tab: string, params?: Record<string, string>) => void;
  request: Requester;
}) {
  const t = useT();
  type BriefCompletionState = {
    completeness: number;
    missing_fields: string[];
    clarification_items: Array<{ field: string; question: string; reason: string }>;
  };
  const [brief, setBrief] = useState<BriefCompletionState | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    props.request<BriefCompletionState>(`/projects/${props.projectId}/brief`)
      .then((data) => {
        if (!cancelled) setBrief(data);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => {
      cancelled = true;
    };
  }, [props.projectId, props.request]);

  const completeness = Math.round((brief?.completeness ?? 0) * 100);
  const missingCount = brief?.missing_fields.length ?? 0;
  const openQuestions = brief?.clarification_items.length ?? 0;
  const unconfirmedCount =
    brief?.clarification_items.filter((item) => item.reason === "unconfirmed").length ?? 0;

  return (
    <Panel title={t("Structured Requirements")} icon={<Check size={17} />} wide>
      {error ? (
        <p className="inlineError">{error}</p>
      ) : (
        <div className="overviewRequirementSummary">
          <div className="overviewRequirementProgress">
            <Progress percent={completeness} status={completeness === 100 ? "success" : "active"} />
            <p className="inlineHint">
              {t("Overview only tracks completion. Fill requirement questions on the Structured Requirements page.")}
            </p>
          </div>
          <div className="debugRunGrid">
            <div className="debugRunTile">
              <span>{t("Open questions")}</span>
              <strong>{openQuestions}</strong>
            </div>
            <div className="debugRunTile">
              <span>{t("Missing")}</span>
              <strong>{missingCount}</strong>
            </div>
            <div className="debugRunTile">
              <span>{t("Unconfirmed")}</span>
              <strong>{unconfirmedCount}</strong>
            </div>
          </div>
          <button className="primaryButton" onClick={() => props.navigateWorkspace("questions")} type="button">
            <Check size={15} /> {t("Open Structured Requirements")}
          </button>
        </div>
      )}
    </Panel>
  );
}

function OverviewDiagnostics(props: {
  request: Requester;
  notify: (notice: Notice) => void;
}) {
  const t = useT();
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<SemanticGovernanceStatusResponse | null>(null);
  const [projection, setProjection] = useState<SemanticProjectionStatusResponse | null>(null);
  const [validationRuns, setValidationRuns] = useState<SemanticValidationRunListResponse | null>(null);
  const [reasoningRuns, setReasoningRuns] = useState<SemanticReasoningRunListResponse | null>(null);
  const [ruleRuns, setRuleRuns] = useState<SemanticRuleRunListResponse | null>(null);

  async function loadDebugState() {
    setLoading(true);
    try {
      const [statusData, projectionData, validationData, reasoningData, ruleData] = await Promise.all([
        getGovernanceStatus(props.request).catch(() => null),
        getProjectionStatus(props.request).catch(() => null),
        listValidationRuns(props.request, { limit: 5 }).catch(() => null),
        listReasoningRuns(props.request, { limit: 5 }).catch(() => null),
        listRuleRuns(props.request, { limit: 5 }).catch(() => null),
      ]);
      setStatus(statusData);
      setProjection(projectionData);
      setValidationRuns(validationData);
      setReasoningRuns(reasoningData);
      setRuleRuns(ruleData);
    } catch (error) {
      props.notify(errorNotice(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDebugState();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runItems = useMemo(
    () => [
      { label: t("Validation"), count: validationRuns?.summary?.total ?? validationRuns?.items?.length ?? 0 },
      { label: t("Reasoning"), count: reasoningRuns?.summary?.total ?? reasoningRuns?.items?.length ?? 0 },
      { label: t("Rule"), count: ruleRuns?.summary?.total ?? ruleRuns?.items?.length ?? 0 },
    ],
    [reasoningRuns, ruleRuns, t, validationRuns],
  );
  const graphCount = numericJsonValue(status?.graphs, "total");
  const missingEvidenceCount = numericJsonValue(status?.derived, "missing_evidence_count");
  const staleDerivedCount =
    numericJsonValue(status?.derived, "stale_derived_count") ?? numericJsonValue(status?.derived, "stale_count");

  return (
    <section className="pageGrid systemGrid" aria-label="overview-diagnostics">
      <Panel title={t("Runtime status")} icon={<Activity size={17} />}>
        <button className="primaryButton" onClick={() => void loadDebugState()} disabled={loading} type="button">
          {loading ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}
          {t("Refresh")}
        </button>
        <dl className="detailList">
          <dt>{t("Registered workspace areas")}</dt>
          <dd>{graphCount ?? t("unknown")}</dd>
          <dt>{t("Missing evidence")}</dt>
          <dd>{missingEvidenceCount ?? 0}</dd>
          <dt>{t("Stale derived results")}</dt>
          <dd>{staleDerivedCount ?? 0}</dd>
        </dl>
      </Panel>
      <Panel title={t("Projection status")} icon={<Network size={17} />}>
        <dl className="detailList">
          <dt>{t("Stale projections")}</dt>
          <dd>{projection?.stale_projection_count ?? projection?.stale?.length ?? 0}</dd>
          <dt>{t("Missing projections")}</dt>
          <dd>{projection?.missing?.length ?? 0}</dd>
          <dt>{t("Projection manifests")}</dt>
          <dd>{projection?.manifests?.length ?? 0}</dd>
        </dl>
      </Panel>
      <Panel title={t("Validation and runtime jobs")} icon={<History size={17} />} wide>
        <div className="debugRunGrid">
          {runItems.map((item) => (
            <div className="debugRunTile" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.count}</strong>
            </div>
          ))}
        </div>
        <p className="inlineHint">
          {t("Overview shows workspace diagnostics. Modeling data is edited from the Modeling area.")}
        </p>
      </Panel>
    </section>
  );
}

function DebugPage(props: {
  navigateWorkspace: (tab: string, params?: Record<string, string>) => void;
}) {
  const t = useT();
  return (
    <section className="pageGrid systemGrid" aria-label="debug-page">
      <Panel title={t("Debug tools")} icon={<Wrench size={17} />} wide>
        <div className="debugToolGrid">
          <DebugToolCard
            icon={<Send size={17} />}
            title={t("Agent Test")}
            detail={t("Run ontology-grounded questions against the active graph set.")}
            onClick={() => props.navigateWorkspace("agent-test")}
          />
          <DebugToolCard
            icon={<Search size={17} />}
            title={t("Recall")}
            detail={t("Search graph context and inspect recall candidates before agent runs.")}
            onClick={() => props.navigateWorkspace("search")}
          />
          <DebugToolCard
            icon={<Wrench size={17} />}
            title={t("MCP Tools")}
            detail={t("Inspect tool surfaces available to external agents.")}
            onClick={() => props.navigateWorkspace("mcp-tools")}
          />
          <DebugToolCard
            icon={<Layers size={17} />}
            title={t("Graph Sets")}
            detail={t("Inspect active graph-set membership and generated run history.")}
            onClick={() => props.navigateWorkspace("graph-sets")}
          />
        </div>
      </Panel>
    </section>
  );
}

function DebugToolCard(props: { icon: ReactNode; title: string; detail: string; onClick: () => void }) {
  return (
    <button className="debugToolCard" onClick={props.onClick} type="button">
      <div className="debugToolIcon">{props.icon}</div>
      <strong>{props.title}</strong>
      <span>{props.detail}</span>
    </button>
  );
}

function numericJsonValue(source: unknown, key: string): number | null {
  if (!source || typeof source !== "object" || !(key in source)) return null;
  const value = (source as Record<string, unknown>)[key];
  return typeof value === "number" ? value : null;
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
