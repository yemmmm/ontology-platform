import { useEffect, useState } from "react";
import { useT } from "../i18n";
import { workspaceApi } from "../workspaceApi";
import type { Artifact, JsonObject, Project, Run, RunIndex } from "../workspaceTypes";
const terminal = new Set(["CLEANED", "FAILED", "TERMINAL_REPORT_COMPLETE"]);
function state(value: string | JsonObject) { return typeof value === "string" ? value : String(value.state ?? ""); }
function objects(value: unknown): JsonObject[] { return Array.isArray(value) ? value.filter(item => item && typeof item === "object") : []; }
function text(value: unknown): string {
  if (value == null || value === "") return "";
  if (Array.isArray(value)) return value.map(text).filter(Boolean).join(" · ");
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${text(item)}`).join(" · ");
  return String(value);
}
function Source({ artifact }: { artifact: Artifact }) {
  const t = useT();
  return <p className="sourceHint">{t("Source")}: {artifact.source.path || artifact.artifact_id}<br />{t("Updated")}: {artifact.source.updated_at || t("Unknown")}</p>;
}
function Questions({ run, historical }: { run: Run | null; historical: boolean }) {
  const t = useT();
  const [selected, setSelected] = useState("");
  const [expanded, setExpanded] = useState(false);
  const artifacts = (run?.artifacts.competency_questions ?? []).filter(item => item.availability === "available");
  const freeze = (run?.artifacts.host ?? []).filter(item => item.kind === "cq-freeze" && item.availability === "available").flatMap(item => objects(item.data.records)).filter(item => item.snapshot_digest).slice(-1)[0];
  const matches = freeze ? artifacts.filter(item => item.data.snapshot_digest === freeze.snapshot_digest && item.data.batch_id === freeze.batch_id) : [];
  const current = !historical && matches.length === 1 ? matches[0] : null;
  const groups = new Map<string, { artifacts: Artifact[]; questions: JsonObject[] }>();
  for (const artifact of artifacts) {
    const key = `${text(artifact.data.batch_id)} · ${text(artifact.data.snapshot_digest)}`;
    const group = groups.get(key) ?? { artifacts: [], questions: [] };
    group.artifacts.push(artifact);
    group.questions.push(...objects(artifact.data.questions));
    groups.set(key, group);
  }
  const currentKey = current ? `${text(current.data.batch_id)} · ${text(current.data.snapshot_digest)}` : "";
  const chosenKey = groups.has(selected) ? selected : currentKey || [...groups.keys()][0] || "";
  const chosen = groups.get(chosenKey);
  const questions = [...new Map((chosen?.questions ?? []).map((item, i) => [item.question_id ?? i, item])).values()];
  return <section className="panel" aria-label={t("Competency questions")}><h2>{t("Competency questions")}</h2>
    {!run ? <p>{t("Current questions cannot be determined")}</p> : !groups.size ? <p>{t("No public competency questions recorded")}</p> : <>
      <label>{t("Question version")}<select value={chosenKey} onChange={event => { setSelected(event.target.value); setExpanded(false); }}>{[...groups.keys()].map(key => <option key={key}>{key}</option>)}</select></label>
      <p className="tag">{historical ? t("Historical questions") : chosenKey === currentKey ? t("Current frozen version") : t("Version applicability unverified")}</p>
      <ol className="questionList">{(expanded ? questions : questions.slice(0, 10)).map((item, i) => <li key={String(item.question_id ?? i)}><strong>{text(item.question)}</strong><p>{text(item.scope) || t("Scope not recorded")}</p><small>{text(item.question_id)} · {t("Version")}: {text(item.review_content_version ?? item.content_version) || t("Not recorded")} · {text(item.status) || t("Status not recorded")}</small></li>)}</ol>
      {questions.length > 10 && <button onClick={() => setExpanded(value => !value)}>{t(expanded ? "Show fewer questions" : "Expand remaining questions")}</button>}
      {chosen?.artifacts.map(item => <Source key={item.artifact_id} artifact={item} />)}
    </>}
  </section>;
}
function Reports({ run, historical }: { run: Run | null; historical: boolean }) {
  const t = useT();
  const [selected, setSelected] = useState("");
  const reports = (run?.artifacts.reports ?? []).filter(item => item.kind === "reports" && item.availability === "available").sort((a, b) => (b.source.updated_at ?? "").localeCompare(a.source.updated_at ?? ""));
  const current = reports.filter(item => item.data.applicability === "verified_current");
  const report = reports.find(item => item.artifact_id === selected) ?? (current.length === 1 ? current[0] : reports[0]);
  const data = report?.data ?? {};
  const verdicts = objects(data.verdicts);
  const unique = new Map<string, string>();
  let conflict = false;
  for (const item of verdicts) {
    if (typeof item.question_id !== "string" || typeof item.verdict !== "string") { conflict = true; continue; }
    if (unique.has(item.question_id) && unique.get(item.question_id) !== item.verdict) conflict = true;
    unique.set(item.question_id, item.verdict);
  }
  const counts = new Map<string, number>();
  unique.forEach(verdict => counts.set(verdict, (counts.get(verdict) ?? 0) + 1));
  const hidden = data.hidden_summary as { verdict_counts?: Record<string, number>; unexecuted_count?: number } | undefined;
  const unexecuted = new Set(Array.isArray(data.unexecuted_question_ids) ? data.unexecuted_question_ids : []);
  if ([...unexecuted].some(id => unique.has(String(id)))) conflict = true;
  const hiddenCounts = hidden?.verdict_counts ?? {};
  const hiddenTotal = Object.values(hiddenCounts).reduce((sum, count) => sum + count, 0);
  const validCounts = Object.values(hiddenCounts).every(count => Number.isInteger(count) && count >= 0) && Number.isInteger(hidden?.unexecuted_count) && (hidden?.unexecuted_count ?? -1) >= 0;
  const denominator = data.denominator;
  const accounted = unique.size + unexecuted.size + hiddenTotal + (hidden?.unexecuted_count ?? 0);
  const incomplete = !Number.isInteger(denominator) || !validCounts || conflict || accounted !== denominator || typeof data.public_count !== "number" || data.public_count !== unique.size + unexecuted.size;
  return <section className="panel" aria-label={t("Acceptance progress")}><h2>{t("Acceptance progress")}</h2>
    {!run ? <p>{t("Current acceptance cannot be determined")}</p> : !report ? <p>{t("No formal acceptance results yet")}</p> : <>
      <label>{t("Acceptance record")}<select value={report.artifact_id} onChange={event => setSelected(event.target.value)}>{reports.map(item => <option value={item.artifact_id} key={item.artifact_id}>{item.source.updated_at || item.artifact_id}</option>)}</select></label>
      <p className="tag">{historical ? `${t("Historical record")} · ` : ""}{t("Applicability")}: {text(data.applicability) || t("Unknown")}</p>
      <p>{t("Report scope")}: {text(report.scope) || t("Scope not recorded")}</p>
      {data.summary_by_scope && typeof data.summary_by_scope === "object" && !Array.isArray(data.summary_by_scope) ? <div aria-label={t("Recorded scope counts")}>{Object.entries(data.summary_by_scope).map(([scope, counts]) => <p key={scope}>{scope}: {text(counts)}</p>)}</div> : null}
      <p>{t("Denominator")}: {typeof denominator === "number" ? denominator : t("Not recorded")}</p>
      <div className="reportCounts"><div><h3>{t("Public verdicts")}</h3>{counts.size ? [...counts].map(([verdict, count]) => <p key={verdict}>{verdict}: {count}</p>) : <p>{t("Not recorded")}</p>}<p>{t("Not executed")}: {unexecuted.size}</p></div><div><h3>{t("Authorized hidden summary")}</h3>{Object.entries(hiddenCounts).map(([verdict, count]) => <p key={verdict}>{verdict}: {count}</p>)}<p>{t("Not executed")}: {hidden?.unexecuted_count ?? t("Not recorded")}</p></div></div>
      {incomplete && <p className="notice">{t("Progress data is incomplete")}</p>}
      <p>{t("Original full_pass")}: {typeof data.full_pass === "boolean" ? String(data.full_pass) : t("Not recorded")}</p>
      <p className="inlineHint">{t("A report verdict does not establish whole-project semantic acceptance")}</p>
      {text(data.coverage_gaps) && <p>{t("Coverage gaps")}: {text(data.coverage_gaps)}</p>}
      {[...(report.limitations ?? []), ...(Array.isArray(data.applicability_limitations) ? data.applicability_limitations : [])].map((item, i) => <p className="notice" key={i}>{text(item)}</p>)}
      <Source artifact={report} />
    </>}
  </section>;
}
export function OverviewPage({ project }: { project: Project }) {
  const t = useT();
  const [index, setIndex] = useState<RunIndex | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [historical, setHistorical] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setRun(null); setIndex(null); setError(""); setLoading(true); setHistorical(false);
    async function load() {
      try {
        const value = await workspaceApi.index(project.id);
        if (!active) return;
        setIndex(value);
        let chosen: string | null = null;
        let history = false;
        if (value.completeness.complete) {
          if (value.current_run_id) chosen = value.current_run_id;
          else if (value.runs.length && value.runs.every(item => terminal.has(state(item.state)))) {
            chosen = [...value.runs].sort((a, b) => (b.source_updated_at ?? "").localeCompare(a.source_updated_at ?? ""))[0].run_id;
            history = true;
          }
        }
        if (chosen) {
          const detail = await workspaceApi.run(project.id, chosen);
          if (active) { setRun(detail); setHistorical(history); }
        }
      } catch (reason) { if (active) setError(String(reason)); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [project.id, revision]);
  const recordedStage = (run?.artifacts.host ?? []).filter(item => item.availability === "available" && item.kind !== "cq-freeze").flatMap(artifact => objects(artifact.data.records).map((item): JsonObject & { time: number; sourceTime: number } => ({ ...item, time: Date.parse(String(item.recorded_at || artifact.source.updated_at || "")), sourceTime: Date.parse(artifact.source.updated_at || "") }))).filter(item => item.stage && Number.isFinite(item.time)).sort((a, b) => b.time - a.time || (b.sourceTime || 0) - (a.sourceTime || 0))[0];
  const progress = historical ? t("The latest run ended; current project progress needs verification") : recordedStage ? `${t("Recorded phase")}: ${text(recordedStage.stage)}${recordedStage.reason_code ? ` · ${text(recordedStage.reason_code)}` : ""}` : run && state(run.state) === "RUNNING" ? t("The latest record is running; business progress is unverified") : t("Current progress is unverified");
  return <section className="overviewPage"><div className="pageActions"><button disabled={loading} onClick={() => setRevision(value => value + 1)}>{t("Refresh")}</button></div>
    {loading && <p role="status">{t("Loading…")}</p>}{error && <p className="errorMessage" role="alert">{t("Overview could not be read")}: {error}</p>}
    <div className="overviewGrid"><section className="panel" aria-label={t("Project introduction")}><p className="eyebrow">{t("Project introduction")}</p><h2>{project.name}</h2><p>{project.description || t("Project introduction has not been recorded")}</p></section>
    <section className="panel" aria-label={t("Project progress")}><h2>{t("Project progress")}</h2><p className="progressSentence">{progress}</p>{run && <p className="sourceHint">{t(historical ? "Latest record (historical)" : "Current record")}: {run.run_id}</p>}{index && !index.completeness.complete && <p className="notice">{t("Run enumeration is incomplete")}</p>}{index && !index.runs.length && <p>{t("No run records")}</p>}<small>{t("Observed")}: {run?.observed_at || index?.observed_at || t("Unknown")}</small></section>
    <Questions key={`questions:${run?.run_id ?? "none"}:${revision}`} run={run} historical={historical} /><Reports key={`reports:${run?.run_id ?? "none"}:${revision}`} run={run} historical={historical} /></div>
  </section>;
}
