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
function latestArtifact(artifacts: Artifact[]): Artifact | undefined {
  return [...artifacts].sort((a, b) => (b.source.updated_at ?? "").localeCompare(a.source.updated_at ?? ""))[0];
}
function Questions({ run }: { run: Run | null }) {
  const t = useT();
  const artifacts = (run?.artifacts.competency_questions ?? []).filter(item => item.availability === "available");
  const freeze = (run?.artifacts.host ?? []).filter(item => item.kind === "cq-freeze" && item.availability === "available").flatMap(item => objects(item.data.records)).filter(item => item.snapshot_digest).slice(-1)[0];
  const matches = freeze ? artifacts.filter(item => item.data.snapshot_digest === freeze.snapshot_digest && item.data.batch_id === freeze.batch_id) : [];
  const latest = latestArtifact(artifacts);
  const latestMatches = latest ? artifacts.filter(item => item.source.updated_at === latest.source.updated_at) : [];
  const chosen = freeze ? (matches.length === 1 ? matches[0] : undefined) : latestMatches.length === 1 ? latest : undefined;
  const questions = [...new Map(objects(chosen?.data.questions).map(item => [item.question_id, item])).values()];
  const reports = (run?.artifacts.reports ?? []).filter(item => item.kind === "reports" && item.availability === "available" && item.data.applicability === "verified_current" && item.data.batch_id === chosen?.data.batch_id && item.data.freeze_digest === chosen?.data.snapshot_digest);
  const questionIds = new Set(questions.map(item => String(item.question_id)));
  const questionVerdicts = new Map<string, string>();
  const timestamps = new Map<string, string>();
  let conflict = false;
  let incomplete = run?.acceptance_reports_complete === false;
  for (const report of [...reports].sort((a, b) => (a.source.updated_at ?? "").localeCompare(b.source.updated_at ?? ""))) {
    const data = report.data;
    const ids = Array.isArray(data.question_ids) ? new Set(data.question_ids.map(String)) : new Set<string>();
    const verdicts = new Map<string, string>();
    if (!ids.size || data.denominator !== ids.size || [...ids].some(id => !questionIds.has(id))) { incomplete = true; continue; }
    for (const item of objects(data.question_verdicts)) {
      const id = String(item.question_id);
      if (!ids.has(id) || typeof item.verdict !== "string" || (verdicts.has(id) && verdicts.get(id) !== item.verdict)) { conflict = true; continue; }
      verdicts.set(id, item.verdict);
    }
    const timestamp = report.source.updated_at ?? "";
    for (const id of ids) {
      const verdict = verdicts.get(id) ?? "not-executed";
      if (timestamps.get(id) === timestamp && questionVerdicts.get(id) !== verdict) conflict = true;
      timestamps.set(id, timestamp);
      questionVerdicts.set(id, verdict);
    }
  }
  incomplete ||= conflict;
  const completed = [...questionVerdicts.values()].filter(value => value === "pass" || value === "model-recall-insufficient").length;
  const passed = [...questionVerdicts.values()].filter(value => value === "pass").length;
  function verdictLabel(question: JsonObject): string {
    if (!reports.length || incomplete) return t("Not accepted yet");
    const verdict = questionVerdicts.get(String(question.question_id));
    if (verdict === "pass") return t("Acceptance passed");
    if (verdict === "model-recall-insufficient") return t("Acceptance not passed");
    if (verdict === "question-answer-review" || verdict === "pending-review") return t("Acceptance needs review");
    if (verdict === "platform-runtime-incomplete" || verdict === "incomplete") return t("Acceptance incomplete");
    return t("Not accepted yet");
  }
  const progressText = !run || !chosen ? t("Current acceptance cannot be determined") : !reports.length ? t("No current acceptance results") : incomplete ? t("Progress data is incomplete") : t("Accepted {completed} / {total}; passed {passed}", { completed, total: questions.length, passed });
  return <section className="panel questionsPanel" aria-label={t("Competency questions")}><h2>{t("Competency questions")}</h2>
    <div className="acceptanceProgress"><p id="cq-progress-label">{t("Acceptance progress")} · {progressText}</p><progress aria-labelledby="cq-progress-label" max={100} {...(reports.length > 0 && questions.length > 0 && !incomplete ? { value: completed / questions.length * 100 } : {})} /></div>
    {!run || run.current_questions_available === false || (artifacts.length > 0 && !chosen) ? <p>{t("Current questions cannot be determined")}</p> : !questions.length ? <p>{t("No competency questions recorded")}</p> : <>
      {!freeze && <p className="inlineHint">{t("Latest recorded questions; freeze unverified")}</p>}
      <ol className="questionList">{questions.map(item => <li key={String(item.question_id)}><strong>{text(item.question)}</strong>{item.visibility === "hidden" && <span className="inlineHint"> ({t("Hidden question")})</span>}<div className="questionTags"><span className="tag" data-verdict={conflict ? undefined : questionVerdicts.get(String(item.question_id))}>{verdictLabel(item)}</span></div></li>)}</ol>
    </>}
  </section>;
}
export function OverviewPage({ project }: { project: Project }) {
  const t = useT();
  const [index, setIndex] = useState<RunIndex | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [questionRun, setQuestionRun] = useState<Run | null>(null);
  const [historical, setHistorical] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setRun(null); setQuestionRun(null); setIndex(null); setError(""); setLoading(true); setHistorical(false);
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
          const [detail, questions] = await Promise.all([
            workspaceApi.run(project.id, chosen), workspaceApi.questions(project.id, chosen),
          ]);
          if (active) { setRun(detail); setQuestionRun(questions); setHistorical(history); }
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
    <Questions key={`questions:${questionRun?.run_id ?? "none"}:${revision}`} run={questionRun} /></div>
  </section>;
}
