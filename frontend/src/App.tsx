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
  EvidenceChunk,
  EvidenceArtifact,
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
import { ClassesPage as Stage2ClassesPageModule } from "./pages/ClassesPage";
import { EntitiesPage as Stage2EntitiesPageModule } from "./pages/EntitiesPage";
import { ProjectBriefPage } from "./pages/ProjectBriefPage";
import { FactAuditPage } from "./pages/FactAuditPage";
import { PublicationPage } from "./pages/PublicationPage";
import { VersionsPage } from "./pages/VersionsPage";
import { EvidenceExplorer } from "./pages/EvidenceExplorer";
import { CatalogWizardPage } from "./pages/CatalogWizardPage";
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
  | "overview"
  | "brief"
  | "questions"
  | "topology"
  | "sources"
  | "facts"
  | "publication"
  | "classes"
  | "entities"
  | "catalog"
  | "entities-search"
  | "versions"
  | "evidence"
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
type ClassPageMode = "topology" | "create" | "edit";
type EntityPageMode = "topology" | "create" | "edit";
type Requester = <T,>(path: string, options?: RequestInit) => Promise<T>;

function lazyStage2ClassesPage() {
  return Stage2ClassesPageModule;
}

function lazyStage2EntitiesPage() {
  return Stage2EntitiesPageModule;
}

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

const stageMeta: Array<{
  id: WorkspaceStage;
  label: string;
  detail: string;
  icon: typeof Network;
  workflowStatuses?: string[];
}> = [
  { id: "intake", label: "Intake", detail: "Brief · questions · evidence", icon: BookOpen, workflowStatuses: ["gathering"] },
  { id: "knowledge", label: "Modeling", detail: "Classes · entities · facts · catalog", icon: GitBranch, workflowStatuses: ["schema_draft", "schema_review", "graph_building", "graph_review", "validated"] },
  { id: "governance", label: "Governance", detail: "Graphs · graph sets · semantic edit · runs · import/export", icon: ShieldCheck },
  { id: "publish", label: "Publish", detail: "Publication · versions", icon: Flag, workflowStatuses: ["published"] },
  { id: "tools", label: "Tools", detail: "Search · agent · MCP · settings", icon: Wrench },
];

const stageDefaultTab: Record<WorkspaceStage, WorkspaceTab> = {
  intake: "overview",
  knowledge: "classes",
  governance: "graph-governance",
  publish: "publication",
  tools: "entities-search",
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
  { id: "overview", stage: "intake", label: "Overview", detail: "Progress & next actions", icon: CircleGauge },
  { id: "brief", stage: "intake", label: "Brief", detail: "Scope & intent", icon: BookOpen },
  { id: "questions", stage: "intake", label: "Questions", detail: "Competency validation", icon: CircleHelp },
  { id: "sources", stage: "intake", label: "Files", detail: "Evidence originals", icon: FileText },
  { id: "classes", stage: "knowledge", label: "Classes", detail: "Class topology", icon: Box },
  { id: "entities", stage: "knowledge", label: "Entities", detail: "Entity editor", icon: Database },
  { id: "facts", stage: "knowledge", label: "Facts", detail: "Layered fact audit", icon: FileCheck2 },
  { id: "catalog", stage: "knowledge", label: "Catalog", detail: "Mappings & connectors", icon: Link2 },
  { id: "publication", stage: "publish", label: "Publication", detail: "Readiness & release", icon: Flag },
  { id: "versions", stage: "publish", label: "Versions", detail: "Lineage & diff", icon: History },
  { id: "entities-search", stage: "tools", label: "Search", detail: "Retrieval tests", icon: Search },
  { id: "agent-test", stage: "tools", label: "Agent Test", detail: "Question runs", icon: Send },
  { id: "mcp-tools", stage: "tools", label: "MCP Tools", detail: "Tool catalog", icon: Wrench },
  { id: "evidence", stage: "tools", label: "Evidence", detail: "Source traceability", icon: ShieldCheck },
  { id: "setting", stage: "tools", label: "Settings", detail: "Runtime status", icon: Settings },
  { id: "graph-governance", stage: "governance", label: "Graph Governance", detail: "Status · graph sets · audits", icon: ShieldCheck },
  { id: "named-graphs", stage: "governance", label: "Named Graphs", detail: "Registry · editability", icon: Database },
  { id: "graph-sets", stage: "governance", label: "Graph Sets", detail: "Members · runs · exports", icon: Layers },
  { id: "semantic-edits", stage: "governance", label: "Semantic Edit", detail: "Direct workbench", icon: FileCheck2 },
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
  const t = useT();
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
    if (pageDirty && !window.confirm(t("Discard unsaved changes and leave this page?"))) return;
    setPageDirty(false);
    const url = new URL(window.location.href);
    url.searchParams.set("tab", tab);
    for (const key of ["batch", "proposal", "claim", "item", "evidence", "document", "graph", "graphSet", "run", "category"]) {
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
    // Gate on the project list: skip if it hasn't loaded yet but we already have
    // a stored ID (race with loadProjects), or if the stored ID isn't in the list
    // (stale localStorage after a DB reset) — loadProjects will correct it.
    if (selectedProjectId) {
      if (!projects.length) return;
      if (!projects.some((project) => project.id === selectedProjectId)) return;
    }
    loadOntologies().catch(showError);
  }, [selectedProjectId, projects, loadOntologies, showError]);

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
                    onClick={() => Promise.all([loadSchema(), loadGraph(), loadVersions()]).catch(showError)}
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
                    gathering: "overview",
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
                  classes={classes}
                  entities={entities}
                  health={health}
                  mutate={mutate}
                  notify={setNotice}
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
  const t = useT();
  const [projectForm, setProjectForm] = useState({ name: "", description: "" });
  const [ontologyForm, setOntologyForm] = useState({ name: "", description: "" });
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
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
    }, t("Project created"));
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
                    <dt>{t("Version")}</dt>
                    <dd>{compactId(ontology.current_version_id)}</dd>
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
  notify: (notice: Notice) => void;
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
  const t = useT();
  // Stable identity is required: child pages (BuildOverviewPage et al.) put `request`
  // in their `load` useCallback deps, and a fresh inline function here would retrigger
  // their load effect on every parent render, producing an infinite fetch/Skeleton loop.
  const governedRequest = useCallback<Requester>(
    (path, options) => {
      const method = (options?.method ?? "GET").toUpperCase();
      const mutabilityToggle = /^\/versions\/[^/]+\/mutability$/.test(path);
      if (readOnly && method !== "GET" && method !== "HEAD" && !mutabilityToggle) {
        return Promise.reject(new Error(t("Locked ontology versions are immutable. Turn mutability back on before making changes.")));
      }
      return props.request(path, options);
    },
    [props.request, readOnly, t],
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
    if (!props.selectedVersion) return <EmptyState icon={<History size={22} />} title={t("Select a valid ontology version")} />;
    const context = { ontology: props.ontology, project: props.project, readOnly, request: governedRequest, version: props.selectedVersion };
    if (props.tab === "facts") return <FactAuditPage {...context} initialClaimId={queryValue("claim") || undefined} />;
    return <PublicationPage {...context} onNavigate={props.navigateWorkspace} onVersionChanged={async (version) => { await props.reloadVersions(); props.setSelectedVersionId(version.id); }} />;
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

  if (props.tab === "evidence") {
    return (
      <EvidenceExplorer
        artifactId={queryValue("artifact") || undefined}
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
    const stage2GraphSet = queryValue("graphSet");
    if (stage2GraphSet) {
      const Stage2ClassesPage = lazyStage2ClassesPage();
      return (
        <Stage2ClassesPage
          graphSetId={stage2GraphSet}
          ontologyId={props.ontology.id}
          readOnly={readOnly}
          request={governedRequest}
        />
      );
    }
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

  if (props.tab === "sources") {
    return <EvidenceArtifactsPage navigate={props.navigateWorkspace} projectId={props.ontology.project_id} readOnly={readOnly} request={governedRequest} />;
  }

  if (props.tab === "entities") {
    const stage2GraphSet = queryValue("graphSet");
    if (stage2GraphSet) {
      const Stage2EntitiesPage = lazyStage2EntitiesPage();
      return (
        <Stage2EntitiesPage
          graphSetId={stage2GraphSet}
          ontologyId={props.ontology.id}
          readOnly={readOnly}
          request={governedRequest}
        />
      );
    }
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
        versionId={props.selectedVersionId}
        onOpenFact={(claimId) => props.navigateWorkspace("facts", { claim: claimId })}
        request={governedRequest}
      />
    );
  }

  if (props.tab === "catalog") {
    return (
      <CatalogWizardPage
        classes={props.classes}
        entities={props.entities}
        ontologyId={props.ontology.id}
        projectId={props.project.id}
        propertiesByClass={props.propertiesByClass}
        readOnly={readOnly}
        relationTypes={props.relationTypes}
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

function EvidenceArtifactsPage(props: { projectId: string; request: Requester; navigate: (tab: string, params?: Record<string, string>) => void; readOnly: boolean }) {
  const t = useT();
  const [artifacts, setArtifacts] = useState<EvidenceArtifact[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [chunks, setChunks] = useState<EvidenceChunk[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const data = await props.request<EvidenceArtifact[]>(`/projects/${props.projectId}/evidence-artifacts`);
    setArtifacts(data);
    setSelectedId((current) => data.some((item) => item.id === current) ? current : data[0]?.id || "");
  }, [props.projectId, props.request]);

  useEffect(() => { load().catch((cause) => setError(String(cause))); }, [load]);
  useEffect(() => {
    if (!selectedId) { setChunks([]); return; }
    props.request<EvidenceChunk[]>(`/evidence-artifacts/${selectedId}/chunks`).then(setChunks).catch((cause) => setError(String(cause)));
  }, [props.request, selectedId]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      const uploaded = await props.request<EvidenceArtifact>(`/projects/${props.projectId}/evidence-artifacts`, { method: "POST", body });
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
      await props.request<EvidenceArtifact>(`/evidence-artifacts/${selectedId}/reparse`, { method: "POST" });
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
      const proposals = await props.request<Proposal[]>(`/evidence-artifacts/${selectedId}/proposals`);
      const first = proposals[0];
      if (!first) {
        setError(t("No proposals cite this evidence artifact yet. Agent extraction must submit candidates with evidence references first."));
        return;
      }
      props.navigate(first.proposal_type === "schema_change" ? "classes" : "entities", { proposal: first.id });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  const selected = artifacts.find((artifact) => artifact.id === selectedId);
  return (
    <section className="sourcePage">
      <aside className="sourceSidebar">
        <form className="sourceUpload" onSubmit={upload}>
          <label><Upload size={16} /><span>{t("PDF, Markdown or text evidence")}</span><input accept=".pdf,.md,.markdown,.txt,text/plain,text/markdown,application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} type="file" /></label>
          <button className="primaryButton" disabled={!file || busy || props.readOnly} type="submit">{t("Store evidence")}</button>
        </form>
        {artifacts.map((artifact) => (
          <button className={classNames("sourceDocument", artifact.id === selectedId && "active")} key={artifact.id} onClick={() => setSelectedId(artifact.id)} type="button">
            <strong>{artifact.filename}</strong>
            <span><Badge>{artifact.parse_status}</Badge>{artifact.chunk_count} chunks · {(artifact.size_bytes / 1024).toFixed(1)} KB</span>
          </button>
        ))}
      </aside>
      <main className="sourceSurface">
        {error && <div className="reviewError">{error}</div>}
        {!selected ? <EmptyState icon={<FileText size={24} />} title={t("Store an evidence artifact")} /> : <>
          <header className="reviewHeader"><div><span className="eyebrow">{t("Evidence artifact")}</span><h2>{selected.filename}</h2><p>{t("Stored original · SHA-256 {hash}… · parser {parser} · parsed {count} time(s)", { hash: selected.content_hash.slice(0, 16), parser: selected.parser_version, count: selected.parse_count })}</p></div><div className="reviewHeaderActions"><button className="secondaryButton" disabled={busy} onClick={() => void openProposals()} type="button">{t("Linked proposals")}</button><button className="secondaryButton" disabled={busy || props.readOnly || selected.parse_status === "parsing"} onClick={() => void reparse()} type="button"><RefreshCw className={busy ? "spin" : ""} size={14} />{selected.parse_status === "failed" ? t("Retry parse") : t("Reparse chunks")}</button></div></header>
          <div className="infoBanner">{t("Artifacts are stored as evidence for Agent-extracted candidates. The platform parses chunks for traceability, but does not infer graph knowledge from the original text.")}</div>
          {selected.parse_error && <div className="reviewError">{selected.parse_error}</div>}
          <div className="chunkList">{chunks.map((chunk) => <article className="sourceChunk" key={chunk.id}><header><strong>{t("Chunk {n}", { n: chunk.sequence + 1 })}</strong><span>{chunk.page_number ? t("Page {n} · ", { n: chunk.page_number }) : ""}{t("characters {start}–{end}", { start: chunk.char_start, end: chunk.char_end })}</span></header><pre>{chunk.text}</pre><code>{chunk.content_hash.slice(0, 20)}…</code></article>)}</div>
        </>}
      </main>
    </section>
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
  const t = useT();
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
              placeholder={t("Search classes")}
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
                <span className="searchEmpty">{t("No matching classes")}</span>
              )}
            </div>
          )}
        </div>
        <button className="primaryButton" onClick={newClass} type="button">
          <Plus size={15} /> {t("New class")}
        </button>
      </header>

      {mode === "topology" ? (
        <Panel title={t("Class topology")} icon={<Waypoints size={17} />} className="classTopologyPanel" wide>
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
  const t = useT();
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
    return <EmptyState icon={<Box size={22} />} title={t("No classes yet")} />;
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
  const t = useT();
  return (
    <div className={classNames("classFlowNodeBody", props.selected && "selected")}>
      <Handle position={Position.Left} type="target" />
      <strong>{props.data.label}</strong>
      <span>{props.data.description}</span>
      <div>
        <small>{t("{n} props", { n: props.data.propertyCount })}</small>
        <small>{t("{n} rels", { n: props.data.relationCount })}</small>
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
  const t = useT();
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
    }, props.mode === "edit" ? t("Class updated") : t("Class created"));
  }

  function deleteClass() {
    if (!selectedClass) return;
    props.mutate(async () => {
      await props.request<void>(`/classes/${selectedClass.id}`, { method: "DELETE" });
      props.setSelectedClassId("");
      props.setMode("topology");
      await props.reloadSchema();
    }, t("Class deleted"));
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
    }, editingProperty ? t("Property updated") : t("Property created"));
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
    }, editingRelation ? t("Relation updated") : t("Relation created"));
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
          <ArrowLeft size={15} /> {t("Topology")}
        </button>
        <div>
          <h2>{props.mode === "create" ? t("Create class") : selectedClass?.name ?? t("Edit class")}</h2>
          <p>{props.mode === "create" ? t("Define a new ontology class.") : t("Edit class fields, properties, and relation types.")}</p>
        </div>
      </div>

      <section className="pageGrid classDetailGrid">
        <Panel title={t("Class information")} icon={<Box size={17} />}>
          <form className="stackForm" onSubmit={saveClass}>
            <input
              required
              placeholder={t("Class name")}
              value={classForm.name}
              onChange={(event) => setClassForm({ ...classForm, name: event.target.value })}
            />
            <textarea
              placeholder={t("Description")}
              value={classForm.description}
              onChange={(event) => setClassForm({ ...classForm, description: event.target.value })}
            />
            <input
              placeholder={t("Aliases, comma separated")}
              value={classForm.aliases}
              onChange={(event) => setClassForm({ ...classForm, aliases: event.target.value })}
            />
            <label>
              <span>{t("Parent classes")}</span>
              <ParentClassPicker
                classes={props.classes}
                excludedClassId={selectedClass?.id}
                selectedIds={classForm.parents}
                onChange={(parents) => setClassForm({ ...classForm, parents })}
              />
            </label>
            <div className="buttonRow">
              <button className="primaryButton" disabled={!props.ontologyId} type="submit">
                <Save size={15} /> {props.mode === "create" ? t("Create class") : t("Save class")}
              </button>
              {selectedClass && (
                <button className="secondaryButton dangerText" onClick={deleteClass} type="button">
                  <Trash2 size={15} /> {t("Delete")}
                </button>
              )}
            </div>
          </form>
        </Panel>

        <Panel title={t("Properties")} icon={<Braces size={17} />}>
          {selectedClass ? (
            <>
              <form className="stackForm" onSubmit={saveProperty}>
                <input
                  required
                  placeholder={t("Property name")}
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
                    placeholder={t("Enum values")}
                    value={propertyForm.enumValues}
                    onChange={(event) => setPropertyForm({ ...propertyForm, enumValues: event.target.value })}
                  />
                </div>
                <textarea
                  placeholder={t("Description")}
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
                    {t("Required")}
                  </label>
                  <label>
                    <input
                      checked={propertyForm.multiValued}
                      onChange={(event) => setPropertyForm({ ...propertyForm, multiValued: event.target.checked })}
                      type="checkbox"
                    />
                    {t("Multi-valued")}
                  </label>
                </div>
                <div className="buttonRow">
                  <button className="primaryButton" type="submit">
                    <Save size={15} /> {editingProperty ? t("Save property") : t("Add property")}
                  </button>
                  {editingProperty && (
                    <button className="secondaryButton" onClick={() => setEditingPropertyId("")} type="button">
                      {t("Cancel")}
                    </button>
                  )}
                </div>
              </form>
              <DataList
                empty={t("No properties")}
                items={selectedProperties.map((property) => ({
                  id: property.id,
                  title: property.name,
                  subtitle: `${property.type}${property.required ? t(" - required") : ""}${property.multi_valued ? t(" - multi") : ""}`,
                  selected: editingPropertyId === property.id,
                  onSelect: () => setEditingPropertyId(property.id),
                  actions: (
                    <button
                      className="iconButton danger"
                      onClick={() =>
                        props.mutate(async () => {
                          await props.request<void>(`/properties/${property.id}`, { method: "DELETE" });
                          await props.reloadSchema();
                        }, t("Property deleted"))
                      }
                      title={t("Delete property")}
                      type="button"
                    >
                      <Trash2 size={15} />
                    </button>
                  ),
                }))}
              />
            </>
          ) : (
            <EmptyState icon={<Braces size={20} />} title={t("Create the class before adding properties")} />
          )}
        </Panel>

        <Panel title={t("Relation information")} icon={<GitBranch size={17} />}>
          {selectedClass ? (
            <>
              <button className="secondaryButton fullWidth" onClick={resetRelationForm} type="button">
                <Plus size={15} /> {t("New relation")}
              </button>
              <form className="stackForm" onSubmit={saveRelationType}>
                <input
                  required
                  placeholder={t("Relation type name")}
                  value={relationForm.name}
                  onChange={(event) => setRelationForm({ ...relationForm, name: event.target.value })}
                />
                <input
                  placeholder={t("Aliases")}
                  value={relationForm.aliases}
                  onChange={(event) => setRelationForm({ ...relationForm, aliases: event.target.value })}
                />
                <textarea
                  placeholder={t("Description")}
                  value={relationForm.description}
                  onChange={(event) => setRelationForm({ ...relationForm, description: event.target.value })}
                />
                <div className="formPair">
                  <label>
                    <span>{t("Source class")}</span>
                    <select
                      required
                      value={relationForm.sourceClassId}
                      onChange={(event) => setRelationForm({ ...relationForm, sourceClassId: event.target.value })}
                    >
                      <option value="">{t("Source class")}</option>
                      {props.classes.map((classDef) => (
                        <option key={classDef.id} value={classDef.id}>
                          {classDef.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span>{t("Target class")}</span>
                    <select
                      required
                      value={relationForm.targetClassId}
                      onChange={(event) => setRelationForm({ ...relationForm, targetClassId: event.target.value })}
                    >
                      <option value="">{t("Target class")}</option>
                      {props.classes.map((classDef) => (
                        <option key={classDef.id} value={classDef.id}>
                          {classDef.name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <input
                  placeholder={t("Inverse name")}
                  value={relationForm.inverseName}
                  onChange={(event) => setRelationForm({ ...relationForm, inverseName: event.target.value })}
                />
                <button className="primaryButton" disabled={!props.classes.length} type="submit">
                  <Save size={15} /> {editingRelation ? t("Save relation") : t("Create relation")}
                </button>
              </form>
              <DataList
                empty={t("No relation types for this class")}
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
                        }, t("Relation type deleted"))
                      }
                      title={t("Delete relation type")}
                      type="button"
                    >
                      <Trash2 size={15} />
                    </button>
                  ),
                }))}
              />
            </>
          ) : (
            <EmptyState icon={<GitBranch size={20} />} title={t("Create the class before adding relations")} />
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
  versionId: string;
  request: Requester;
  mutate: (action: () => Promise<void>, success: string) => Promise<void>;
  reloadGraph: () => Promise<void>;
  onOpenFact: (claimId: string) => void;
}) {
  const t = useT();
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
    }, t("Entity deleted"));
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
          placeholder={t("Search entities by name or alias")}
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
        <span className="toolbarDivider" />
        <span className="toolbarLabel">{t("Classes")}</span>
        <div className="classChipRow">
          {props.classes.length === 0 ? (
            <span className="toolbarEmptyHint">{t("No classes defined")}</span>
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
              {t("Clear ({n})", { n: classFilter.length })}
            </button>
          )}
        </div>
        <span className="toolbarStats">
          {t("{entities} entities · {relations} relations", { entities: visibleEntities.length, relations: visibleRelations.length })}
          {props.entities.length === 0 && t(" · No entities yet")}
        </span>
        <div aria-label={t("Graph layout")} className="entityLayoutSwitch" role="group">
          <button
            aria-pressed={graphLayout === "hierarchical"}
            className={classNames(graphLayout === "hierarchical" && "active")}
            onClick={() => setGraphLayout("hierarchical")}
            title={t("Arrange relations from left to right and reduce crossings")}
            type="button"
          >
            <GitBranch size={14} /> {t("Hierarchy")}
          </button>
          <button
            aria-pressed={graphLayout === "force"}
            className={classNames(graphLayout === "force" && "active")}
            onClick={() => setGraphLayout("force")}
            title={t("Arrange dense or cyclic relations as a force-directed network")}
            type="button"
          >
            <Network size={14} /> {t("Force")}
          </button>
        </div>
        <button className="primaryButton entityCreateButton" onClick={() => setMode("create")} type="button">
          <Plus size={15} /> {t("New entity")}
        </button>
      </div>

      <div className="entityGraphCanvasWrap">
        {props.entities.length === 0 ? (
          <div className="entityGraphEmpty">
            <div>
              <Database size={28} />
              <h3>{t("No entities yet")}</h3>
              <p>{t("Entities will appear here as a topology graph once created.")}</p>
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
          versionId={props.versionId}
          request={props.request}
          onClose={() => setSelectedEntityId(null)}
          onDelete={deleteSelectedEntity}
          onEdit={() => setMode("edit")}
          onOpenFact={props.onOpenFact}
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
  const t = useT();
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
        if (missing.length) throw new Error(t("Required properties: {names}", { names: missing.map((item) => item.name).join(", ") }));

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
      }, props.entity ? t("Entity updated") : t("Entity created"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="entityCreatePage">
      <header className="pageSubHeader">
        <button aria-label={t("Back to entity topology")} className="iconButton subtle" onClick={props.onBack} type="button">
          <ArrowLeft size={17} />
        </button>
        <div>
          <span className="eyebrow">{t("Entity editor")}</span>
          <h2>{props.entity ? t("Edit entity") : t("Create entity")}</h2>
          <p>{props.entity ? t("Update the node identity and schema-defined properties.") : t("Choose a class and add an instance that conforms to its property schema.")}</p>
        </div>
      </header>

      <form className="entityCreateForm" onSubmit={saveEntity}>
        <Panel className="entityIdentityPanel" icon={<Database size={17} />} title={t("Identity")}>
          <div className="stackForm">
            <label>
              <span>{t("Class")}</span>
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
                {!props.classes.length && <option value="">{t("No classes available")}</option>}
                {props.classes.map((classDef) => <option key={classDef.id} value={classDef.id}>{classDef.name}</option>)}
              </select>
            </label>
            <label>
              <span>{t("Name")}</span>
              <input
                maxLength={300}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder={t("Entity name")}
                required
                value={form.name}
              />
            </label>
            <label>
              <span>{t("Aliases")}</span>
              <input
                onChange={(event) => setForm((current) => ({ ...current, aliases: event.target.value }))}
                placeholder={t("Comma-separated aliases")}
                value={form.aliases}
              />
            </label>
            {selectedClass && (
              <div className="entityClassSummary">
                <span>{selectedClass.normalized_label || selectedClass.name}</span>
                <p>{selectedClass.description || t("No class description.")}</p>
              </div>
            )}
          </div>
        </Panel>

        <Panel className="entityPropertiesPanel" icon={<Braces size={17} />} title={t("Properties")}>
          {!selectedClass ? (
            <EmptyState icon={<Box size={20} />} title={t("Create a class before adding entities")} />
          ) : properties.length === 0 ? (
            <div className="entityNoProperties">
              <Check size={18} />
              <div><strong>{t("No properties required")}</strong><span>{t("This class can be instantiated with identity fields only.")}</span></div>
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

        <Panel className="entityRelationsPanel" icon={<GitBranch size={17} />} title={t("Relations")}>
            {!selectedClass ? (
              <EmptyState icon={<GitBranch size={20} />} title={t("Select a class to configure relations")} />
            ) : relationChoices.length === 0 ? (
              <div className="entityNoProperties">
                <Check size={18} />
                <div><strong>{t("No relations defined")}</strong><span>{t("This class has no compatible relation types.")}</span></div>
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
                        <span>{choice.direction === "outgoing" ? t("Outgoing") : t("Incoming")}</span>
                      </div>
                      {choice.relationType.aliases.length > 0 && (
                        <small className="entityRelationAliases">
                          {t("Aliases: {values}", { values: choice.relationType.aliases.join(", ") })}
                        </small>
                      )}
                      <p>
                        {choice.direction === "outgoing" ? `${selectedClass.name} → ` : `${nameFor(props.classes, expectedClassId)} → `}
                        {choice.direction === "outgoing" ? nameFor(props.classes, expectedClassId) : selectedClass.name}
                      </p>
                      <label className="entityRelationSearch">
                        <Search size={13} />
                        <input
                          aria-label={t("Search {name} instances by name or alias", { name: choice.relationType.name })}
                          disabled={choice.candidates.length === 0}
                          onChange={(event) => setRelationQueries((current) => ({
                            ...current,
                            [key]: event.target.value,
                          }))}
                          placeholder={t("Search instances by name or alias")}
                          type="search"
                          value={relationQueries[key] ?? ""}
                        />
                      </label>
                      {choice.candidates.length === 0 ? (
                        <small>{t("No compatible {class} entities available.", { class: nameFor(props.classes, expectedClassId) })}</small>
                      ) : visibleCandidates.length === 0 ? (
                        <div className="entityRelationNoResults">{t("No instances match \"{query}\".", { query: relationQueries[key] })}</div>
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
          <button className="secondaryButton" disabled={submitting} onClick={props.onBack} type="button">{t("Cancel")}</button>
          <button className="primaryButton" disabled={!selectedClass || !form.name.trim() || submitting} type="submit">
            {submitting ? <Loader2 className="spin" size={15} /> : <Save size={15} />}
            {submitting ? (props.entity ? t("Saving...") : t("Creating...")) : (props.entity ? t("Save changes") : t("Create entity"))}
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
  const t = useT();
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
                aria-label={t("Remove {name} value", { name: property.name })}
                className="iconButton danger"
                onClick={() => props.onChange(values.filter((_, itemIndex) => itemIndex !== index))}
                type="button"
              ><Trash2 size={14} /></button>
            </div>
          ))}
          <button className="secondaryButton entityAddValue" onClick={() => props.onChange([...values, ""])} type="button">
            <Plus size={14} /> {t("Add value")}
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
  const t = useT();
  return (
    <span className="entityPropertyLabel">
      <span>{property.name}{property.required && <b aria-label={t("Required")}> *</b>}</span>
      <small>{property.type}{property.multi_valued ? t(" · multiple") : ""}</small>
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
  const t = useT();
  const value = props.value === undefined ? "" : String(props.value);
  if (props.property.type === "boolean") {
    return <select aria-label={props.property.name} onChange={(event) => props.onChange(event.target.value)} value={value}><option value="">{t("Not set")}</option><option value="true">{t("True")}</option><option value="false">{t("False")}</option></select>;
  }
  if (props.property.type === "enum") {
    return <select aria-label={props.property.name} onChange={(event) => props.onChange(event.target.value)} value={value}><option value="">{t("Select a value")}</option>{props.property.enum_values.map((item) => <option key={item} value={item}>{item}</option>)}</select>;
  }
  if (props.property.type === "reference") {
    return <select aria-label={props.property.name} onChange={(event) => props.onChange(event.target.value)} value={value}><option value="">{t("Select an entity")}</option>{props.entities.map((entity) => <option key={entity.id} value={entity.id}>{entity.name} · {entity.class_label}</option>)}</select>;
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
  const t = useT();
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
      <Panel title={t("Retrieval test")} icon={<Search size={17} />}>
        <div className="segmented">
          <button className={classNames(mode === "text" && "active")} onClick={() => setMode("text")} type="button">
            {t("Text")}
          </button>
          <button className={classNames(mode === "id" && "active")} onClick={() => setMode("id")} type="button">
            {t("Entity ID")}
          </button>
        </div>
        {mode === "text" ? (
          <form className="stackForm" onSubmit={search}>
            <textarea
              className="questionBox"
              required
              placeholder={t("Input text to match similar entities")}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <label>
              <span>{t("Retrieval mode")}</span>
              <select
                value={retrievalMode}
                onChange={(event) => setRetrievalMode(event.target.value as typeof retrievalMode)}
              >
                <option value="hybrid">{t("Hybrid")}</option>
                <option value="vector">{t("Vector")}</option>
                <option value="text">{t("Text")}</option>
              </select>
            </label>
            <select value={classFilter} onChange={(event) => setClassFilter(event.target.value)}>
              <option value="">{t("All classes")}</option>
              {props.classes.map((classDef) => (
                <option key={classDef.id} value={classDef.id}>
                  {classDef.name}
                </option>
              ))}
            </select>
            <button className="primaryButton" disabled={!props.ontologyId} type="submit">
              <Search size={15} /> {t("Match")}
            </button>
          </form>
        ) : (
          <form className="stackForm" onSubmit={lookupById}>
            <input
              required
              placeholder={t("Entity ID")}
              value={entityId}
              onChange={(event) => setEntityId(event.target.value)}
            />
            <button className="primaryButton" disabled={!props.ontologyId} type="submit">
              <Search size={15} /> {t("Lookup")}
            </button>
          </form>
        )}
        <ErrorText message={localError} />
      </Panel>

      <Panel title={t("Matches")} icon={<Database size={17} />}>
        {mode === "text" ? (
          <DataList
            empty={t("No matches yet")}
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
          <EmptyState icon={<Search size={20} />} title={t("Use the Entity ID lookup form")} />
        )}
      </Panel>

      <Panel title={t("Entity detail")} icon={<Clipboard size={17} />} wide>
        {detail ? (
          <div className="inspector">
            <h2>{detail.name}</h2>
            <p>{detail.class_label}</p>
            <dl className="detailList">
              <dt>{t("ID")}</dt>
              <dd>{detail.id}</dd>
              <dt>{t("Outgoing")}</dt>
              <dd>{detail.outgoing.length}</dd>
              <dt>{t("Incoming")}</dt>
              <dd>{detail.incoming.length}</dd>
            </dl>
            <pre className="jsonBlock tall">{prettyJson(detail)}</pre>
          </div>
        ) : (
          <EmptyState icon={<Clipboard size={20} />} title={t("Select or lookup an entity")} />
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
  const t = useT();
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
          <dt>{t("Version")}</dt>
          <dd>{compactId(props.ontology.current_version_id)}</dd>
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
