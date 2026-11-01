import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../AuthGate";
import { useT } from "../i18n";
import { workspaceApi } from "../workspaceApi";
import type { ProjectQuestion } from "../workspaceTypes";

const lines = (value: string) => value.split("\n").map(item => item.trim()).filter(Boolean);
const empty = { question: "", topic: "", answer: "", criteria: "", sources: "", confirmed: false };

export function ProjectQuestions({ projectId }: { projectId: string }) {
  const t = useT();
  const { principal } = useAuth();
  const editable = principal.scopes.some(scope => ["admin", "model", "write"].includes(scope));
  const [questions, setQuestions] = useState<ProjectQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<ProjectQuestion | null | undefined>(undefined);
  const [form, setForm] = useState(empty);
  async function load() {
    setLoading(true);
    try { setQuestions((await workspaceApi.projectQuestions(projectId)).filter(q => q.cq_definition?.kind === "custom")); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    let current = true;
    workspaceApi.projectQuestions(projectId).then(items => { if (current) setQuestions(items.filter(q => q.cq_definition?.kind === "custom")); })
      .catch(reason => { if (current) setError(String(reason)); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [projectId]);
  async function act(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { await action(); }
    catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }
  function edit(question: ProjectQuestion | null) {
    setEditing(question); setError("");
    setForm(question ? { question: question.question, topic: question.cq_definition.business_topic ?? "",
      answer: question.cq_definition.reference_answer ?? "", criteria: (question.cq_definition.acceptance_criteria ?? []).join("\n"),
      sources: (question.cq_definition.source_refs ?? []).join("\n"), confirmed: question.cq_definition.criteria_status === "confirmed" } : empty);
  }
  function save(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      const value = { question: form.question, cq_definition: { ...editing?.cq_definition, kind: "custom",
        business_topic: form.topic || null, reference_answer: form.answer || null,
        acceptance_criteria: lines(form.criteria), source_refs: lines(form.sources),
        criteria_status: form.confirmed ? "confirmed" : "draft", selected: editing?.cq_definition.selected ?? true } };
      if (editing) await workspaceApi.updateQuestion(editing.id, { ...value, expected_revision: editing.content_revision });
      else await workspaceApi.createQuestion(projectId, value);
      setEditing(undefined); await load();
    });
  }
  function update(question: ProjectQuestion, values: Record<string, unknown>) {
    const before = questions;
    setQuestions(items => items.map(item => item.id === question.id ? { ...item, ...values } as ProjectQuestion : item));
    void act(async () => {
      try { await workspaceApi.updateQuestion(question.id, { ...values, expected_revision: question.content_revision }); await load(); }
      catch (reason) { setQuestions(before); throw reason; }
    });
  }
  function label(value: unknown) {
    const labels: Record<string, string> = { supported: "Supported", conditional: "Conditional", unsupported: "Unsupported",
      unverified: "Unverified", not_run: "Not executed", blocked: "Blocked", pass: "Passed", fail: "Failed",
      "question-answer-review": "Criteria need review", "platform-runtime-incomplete": "Evaluation incomplete",
      "model-recall-insufficient": "Model information insufficient" };
    return t(labels[String(value)] ?? "Unverified");
  }
  return <section className="panel projectQuestionsPanel" aria-label={t("Project questions")}>
    <div className="cqHeading"><div><h2>{t("Project questions")}</h2><p className="inlineHint">{t("Save the questions your model should answer. Answers are optional.")}</p></div>
      {editable && <button disabled={busy} onClick={() => edit(null)}>{t("Add question")}</button>}</div>
    <p className="inlineHint">{t("Selected questions guide future modeling and regression checks. Existing evaluations keep their frozen versions.")}</p>
    <div className="cqActions">
      <button disabled={busy || loading} onClick={() => void act(load)}>{t("Reload questions")}</button>
      {editable && <><label className="cqImport">{t("Import questions")}<input type="file" accept="application/json,.json" disabled={busy} onChange={event => {
        const file = event.target.files?.[0]; event.target.value = "";
        if (file) void act(async () => { await workspaceApi.importQuestions(projectId, JSON.parse(await file.text())); await load(); });
      }} /></label>
      <button disabled={busy || !questions.some(q => q.active && q.cq_definition.selected)} onClick={() => void act(async () => {
        const snapshot = await workspaceApi.freezeQuestions(projectId);
        const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" }));
        const link = document.createElement("a"); link.href = url; link.download = `${snapshot.snapshot_id}.json`; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      })}>{t("Download selected questions")}</button></>}
    </div>
    {error && <p role="alert" className="errorMessage">{error}</p>}
    {editing !== undefined && <form className="cqForm" onSubmit={save}>
      <label>{t("Question")}<textarea aria-label={t("Question")} required maxLength={4000} value={form.question} onChange={event => setForm({ ...form, question: event.target.value })} /></label>
      <details><summary>{t("Optional answer and criteria")}</summary><div className="cqFields">
        <label>{t("Business topic")}<input value={form.topic} maxLength={1000} onChange={event => setForm({ ...form, topic: event.target.value })} /></label>
        <label>{t("Reference answer (optional)")}<textarea value={form.answer} onChange={event => setForm({ ...form, answer: event.target.value })} /></label>
        <label>{t("Acceptance criteria (one per line)")}<textarea value={form.criteria} onChange={event => setForm({ ...form, criteria: event.target.value })} /></label>
        <label>{t("Source references (one per line)")}<textarea value={form.sources} onChange={event => setForm({ ...form, sources: event.target.value })} /></label>
        <label className="cqCheckbox"><input type="checkbox" checked={form.confirmed} onChange={event => setForm({ ...form, confirmed: event.target.checked })} />{t("I confirm these criteria and their sources")}</label>
      </div></details>
      <div className="cqActions"><button disabled={busy} type="submit">{t("Save question")}</button><button disabled={busy} type="button" onClick={() => setEditing(undefined)}>{t("Cancel")}</button></div>
    </form>}
    {loading && <p role="status">{t("Loading…")}</p>}
    {!loading && !questions.length && <p>{t("No project questions yet")}</p>}
    <ol className="questionList">{questions.map(question => {
      const result = question.validation_result;
      return <li key={question.id}><strong className="cqQuestion">{question.question}</strong>
        <div className="questionTags"><span className="tag">{t(question.active ? "Active" : "Inactive")}</span>
          <span className="tag">{t(question.cq_definition.criteria_status === "confirmed" ? "Criteria confirmed" : "Criteria need review")}</span>
          {question.cq_definition.business_topic && <span className="tag">{question.cq_definition.business_topic}</span>}</div>
        <p>{t("Model answerability")}: {label(result.answerability)} · {t("SQL readiness")}: {label(result.sql_readiness)} · {t("SQL execution")}: {label(result.sql_execution ?? "not_run")}</p>
        {result.outcome != null && <p>{t("Last evaluation")}: {label(result.outcome)}{result.stale === true && ` · ${t("Needs recheck")}`}</p>}
        {result.model_revisions != null && <p className="inlineHint">{t("Evaluated model versions")}: {JSON.stringify(result.model_revisions)}</p>}
        {editable && <div className="cqActions"><label className="cqCheckbox"><input type="checkbox" disabled={busy || !question.active} checked={question.cq_definition.selected}
          onChange={event => update(question, { cq_definition: { ...question.cq_definition, selected: event.target.checked } })} />{t("Use in future modeling")}</label>
          <button disabled={busy} onClick={() => edit(question)}>{t("Edit question")}</button>
          <button disabled={busy} onClick={() => update(question, { active: !question.active })}>{t(question.active ? "Deactivate question" : "Reactivate question")}</button></div>}
      </li>;
    })}</ol>
  </section>;
}
