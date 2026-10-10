import { useEffect, useState } from "react";
import { BookOpen, MessageSquare, Network, Search, ShieldCheck, Settings } from "lucide-react";
import { useT } from "./i18n";
import { workspaceApi } from "./workspaceApi";
import type { Project } from "./workspaceTypes";
import { OverviewPage } from "./pages/OverviewPage";
import { ModelBrowserPage } from "./pages/ModelBrowserPage";
import { RecallTestPage } from "./pages/RecallTestPage";
import { MemberPermissionsPage } from "./pages/MemberPermissionsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { DeliveryConversationPage } from "./pages/DeliveryConversationPage";
const tabs = [
  ["overview", "Overview", BookOpen], ["conversation", "Modeling conversation", MessageSquare], ["model", "Model browser", Network],
  ["recall", "Recall test", Search], ["access", "Member permissions", ShieldCheck],
  ["settings", "Settings", Settings],
] as const;
type Tab = typeof tabs[number][0];
const projectKey = "ontology-platform-ui-selected-project";
const tabKey = "ontology-platform-ui-workspace-tab-v4.2";
function stored(key: string) { try { return localStorage.getItem(key); } catch { return null; } }
function persist(key: string, value: string) { try { localStorage.setItem(key, value); } catch { /* Optional browser preference. */ } }
function cleanOldPreferences() {
  try {
    Object.keys(localStorage).filter(key => key === "ontology-platform-ui-workspace-tab-v4" || key === "ontology-platform-ui-selected-ontology" || key.startsWith("ontology-platform-ui-location-") || key.startsWith("ontology-platform-ui-project-lock:") || key.startsWith("ontology-platform-ui-workspace-lock:") || key.startsWith("ontology-platform-ui-edit-lock") || key.startsWith("ontology-platform-ui-lock") || key.startsWith("topology:layout:")).forEach(key => localStorage.removeItem(key));
  } catch { /* Optional browser preference. */ }
}
function location(projects: Project[], initial: boolean) {
  const params = new URLSearchParams(window.location.search);
  const requestedProject = params.get("project") ?? (initial ? stored(projectKey) : null);
  const project = projects.find(item => item.id === requestedProject)?.id ?? projects[0]?.id ?? "";
  const requestedTab = params.get("tab") ?? (params.has("ontology") ? "overview" : initial ? stored(tabKey) : null);
  const tab: Tab = tabs.some(item => item[0] === requestedTab) ? requestedTab as Tab : "overview";
  return { project, tab };
}
function urlFor(project: string, tab: Tab) {
  const url = new URL(window.location.href);
  url.search = "";
  if (project) url.searchParams.set("project", project);
  url.searchParams.set("tab", tab);
  return url;
}
export function App() {
  const t = useT();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selection, setSelection] = useState<{ project: string; tab: Tab }>({ project: "", tab: "overview" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    cleanOldPreferences();
    let active = true;
    workspaceApi.projects().then(items => {
      if (!active) return;
      setProjects(items);
      const next = location(items, true);
      setSelection(next);
      history.replaceState({}, "", urlFor(next.project, next.tab));
      if (next.project) persist(projectKey, next.project);
      persist(tabKey, next.tab);
    }).catch(reason => { if (active) setError(String(reason)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    const onPop = () => {
      const next = location(projects, false);
      setSelection(next);
      history.replaceState({}, "", urlFor(next.project, next.tab));
      if (next.project) persist(projectKey, next.project);
      persist(tabKey, next.tab);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [projects]);
  function navigate(project: string, tab: Tab) {
    history.pushState({}, "", urlFor(project, tab));
    setSelection({ project, tab });
    if (project) persist(projectKey, project);
    persist(tabKey, tab);
  }
  const project = projects.find(item => item.id === selection.project);
  return <div className="workspaceShell">
    <aside className="workspaceRail"><div className="brand"><Network size={26} /><span>Ontology<br /><strong>Platform</strong></span></div>
      <nav aria-label={t("Workspace navigation")}>{tabs.map(([tab, label, Icon]) => <a key={tab} href={`${urlFor(selection.project, tab).search}`} aria-current={selection.tab === tab ? "page" : undefined} onClick={event => { if (event.button === 0 && !event.metaKey && !event.ctrlKey) { event.preventDefault(); navigate(selection.project, tab); } }}><Icon size={19} /><span>{t(label)}</span></a>)}</nav>
    </aside>
    <main className="workspaceMain"><header className="workspaceHeader"><div><p className="eyebrow">Ontology Platform</p><h1>{t(tabs.find(item => item[0] === selection.tab)![1])}</h1></div>
      {selection.tab === "overview" && <label className="projectPicker">{t("Project")}<select value={selection.project} aria-label={t("Project")} onChange={event => navigate(event.target.value, "overview")} disabled={!projects.length}>{projects.length ? projects.map(item => <option value={item.id} key={item.id}>{item.name}</option>) : <option value="">{t("No accessible projects")}</option>}</select></label>}
    </header>
      {error && <p className="errorMessage" role="alert">{t("Project list could not be read")}: {error}</p>}
      {selection.tab === "settings" ? <SettingsPage /> : loading ? <p role="status">{t("Loading…")}</p> : !project ? <section className="panel emptyState">{t("No accessible projects")}</section> : <div key={`${project.id}:${selection.tab}`}>
        {selection.tab === "overview" && <OverviewPage project={project} />}
        {selection.tab === "conversation" && <DeliveryConversationPage project={project} />}
        {selection.tab === "model" && <ModelBrowserPage project={project} />}
        {selection.tab === "recall" && <RecallTestPage project={project} />}
        {selection.tab === "access" && <MemberPermissionsPage project={project} />}
      </div>}
    </main>
  </div>;
}
