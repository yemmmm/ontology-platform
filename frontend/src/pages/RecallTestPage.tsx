import { useEffect, useRef, useState, type FormEvent } from "react";
import { useT } from "../i18n";
import { workspaceApi } from "../workspaceApi";
import type { Project, RecallResponse, RecallResult, SemanticContextQueryRequest, SemanticFeedbackReason, SemanticFeedbackRequest } from "../workspaceTypes";
type RecallPage = { query_request: SemanticContextQueryRequest; result: RecallResponse };
type FeedbackDraft = {
  id: string; pages: RecallPage[]; reasons: SemanticFeedbackReason[]; description: string;
  includeSnapshot: boolean; payload?: SemanticFeedbackRequest;
};
const feedbackReasons = [["incomplete", "Incomplete data"], ["incorrect", "Incorrect information"], ["irrelevant", "Irrelevant results"], ["other", "Other"]] as const;
function revisionKey(response: RecallResponse) {
  const ontologies = response.scope?.ontologies as { ontology_id: string; model_revision: number }[] | undefined;
  return JSON.stringify(ontologies?.map(item => [item.ontology_id, item.model_revision]).sort());
}
export function RecallTestPage({ project }: { project: Project }) {
  const t = useT();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [items, setItems] = useState<RecallResult[]>([]);
  const [response, setResponse] = useState<RecallResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [pages, setPages] = useState<RecallPage[]>([]);
  const [feedback, setFeedback] = useState<FeedbackDraft | null>(null);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const [feedbackSaved, setFeedbackSaved] = useState(false);
  const sequence = useRef(0);
  const feedbackSequence = useRef(0);
  const feedbackInFlight = useRef(false);
  useEffect(() => () => { sequence.current++; feedbackSequence.current++; }, []);
  function clearFeedback() {
    feedbackSequence.current++;
    feedbackInFlight.current = false;
    setFeedback(null); setFeedbackError(""); setFeedbackSaved(false); setFeedbackBusy(false);
  }
  function edit(value: string) {
    sequence.current++;
    clearFeedback();
    setQuery(value); setSubmitted(""); setItems([]); setPages([]); setResponse(null); setLoading(false); setError("");
  }
  async function search(more = false) {
    const text = more ? submitted : query.trim();
    if (!text || text.length > 2000) return;
    const token = ++sequence.current;
    setLoading(true); setError("");
    if (!more) { clearFeedback(); setSubmitted(text); setItems([]); setPages([]); setResponse(null); }
    const request: SemanticContextQueryRequest = {
      project_id: project.id, scope_mode: "project", query: text,
      resource_types: ["concept", "instance", "operation", "mapping", "metric"], assertion_types: ["asserted"],
      search_mode: "hybrid", depth: 0, limit: 20, context_limit: 0, context_detail: "compact",
      ...(more && response?.matches_page.next_match_cursor ? { match_cursor: response.matches_page.next_match_cursor } : {}),
    };
    try {
      const value = await workspaceApi.recall(request);
      if (sequence.current !== token) return;
      setResponse(value);
      setPages(current => more ? [...current, { query_request: request, result: value }] : [{ query_request: request, result: value }]);
      const nodes = value.primary_matches.filter(item => ["concept", "instance", "operation", "mapping", "metric"].includes(item.kind ?? ""));
      setItems(current => [...new Map((more ? [...current, ...nodes] : nodes).map(item => [item.id, item])).values()]);
    } catch (reason) {
      if (sequence.current === token) { setError(String(reason)); setResponse(null); }
    } finally { if (sequence.current === token) setLoading(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void search(); }
  function openFeedback() {
    clearFeedback();
    setFeedback({ id: crypto.randomUUID(), pages: structuredClone(pages), reasons: [], description: "", includeSnapshot: true });
  }
  const snapshot = feedback ? { pages: feedback.pages } : undefined;
  const snapshotTooLarge = snapshot ? new TextEncoder().encode(JSON.stringify(snapshot)).length > 256 * 1024 : false;
  const revisionsDiffer = !!feedback && feedback.pages.some(page => revisionKey(page.result) !== revisionKey(feedback.pages[0].result));
  async function submitFeedback(event: FormEvent) {
    event.preventDefault();
    if (!feedback || feedbackInFlight.current) return;
    const payload = feedback.payload ?? {
      feedback_id: feedback.id, query_request: feedback.pages[0].query_request,
      reasons: feedback.reasons, description: feedback.description,
      ...(feedback.includeSnapshot ? { result_snapshot: snapshot } : {}),
      snapshot_complete: feedback.includeSnapshot && !revisionsDiffer,
    };
    feedbackInFlight.current = true;
    const token = ++feedbackSequence.current;
    setFeedback({ ...feedback, payload }); setFeedbackBusy(true); setFeedbackError("");
    try {
      await workspaceApi.submitSemanticFeedback(payload);
      if (feedbackSequence.current !== token) return;
      setFeedbackSaved(true); setFeedback(null);
    } catch (reason) {
      if (feedbackSequence.current === token) {
        setFeedbackError(String(reason));
        // These responses explicitly reject the submission without saving it.
        // An unknown receipt must instead retain the original retry payload.
        if (reason instanceof Error && /^(400|413|422)\s/.test(reason.message)) {
          setFeedback({ ...feedback, payload: undefined });
        }
      }
    } finally {
      if (feedbackSequence.current === token) { feedbackInFlight.current = false; setFeedbackBusy(false); }
    }
  }
  return <section className="recallPage"><form className="panel" onSubmit={submit}><label htmlFor="recall-query">{t("Query")}</label><textarea id="recall-query" rows={3} value={query} onChange={event => edit(event.target.value)} placeholder={t("Describe the model nodes you want to find")} />
    <div className="queryActions"><small>{t("Enter 1–2000 characters")}</small><button className="primaryButton" disabled={loading || !query.trim() || query.trim().length > 2000}>{t("Find related nodes")}</button></div>
    {query.trim().length > 2000 && <p className="errorMessage" role="alert">{t("Query is too long")}</p>}
  </form>
    {loading && <p role="status">{t("Loading…")}</p>}
    {error && <div className="notice errorMessage" role="alert"><p>{t("Query failed")}: {error}</p><button onClick={() => void search()}>{t("Query again")}</button></div>}
    {response && <><p className="inlineHint">{t("Related nodes for")}: {submitted}</p>
      {response.recall.completeness === "degraded" && <p className="notice">{t("Recall is degraded")}</p>}
      {(response.matches_page.complete === false || response.matches_page.has_more || response.matches_page.next_match_cursor) && <p className="notice">{t("More primary matches remain")}</p>}
      {response.warnings.map((warning, i) => <p className="notice" key={i}>{warning.message || warning.code}</p>)}
      {!items.length && <p className="panel emptyState">{t("No related nodes found")}</p>}
      <div className="resultGrid">{items.map(item => <article className="panel recallNode" key={item.id}><h2>{item.label || item.iri || item.id}</h2><p className="resourceIri">{item.iri || item.id}</p><span className="tag">Ontology · {item.ontology_id || t("Unknown")}</span>{item.description && <p>{item.description}</p>}</article>)}</div>
      {response.matches_page.next_match_cursor && <button disabled={loading} onClick={() => void search(true)}>{t("Load more related nodes")}</button>}
      {!feedback && <button disabled={loading} onClick={openFeedback}>{t("Give feedback")}</button>}
    </>}
    {feedbackSaved && <p className="notice" role="status">{t("Feedback saved")}</p>}
    {feedback && <form className="panel feedbackForm" onSubmit={event => void submitFeedback(event)}>
      <h2>{t("Query feedback")}</h2>
      <p>{t("Related nodes for")}: {feedback.pages[0].query_request.query}</p>
      <small>{t("Feedback describes your observation; saving does not mean the model has been corrected")}</small>
      <fieldset disabled={feedbackBusy || !!feedback.payload}><legend>{t("Feedback reasons")}</legend>
        {feedbackReasons.map(([reason, label]) => <label className="feedbackOption" key={reason}><input type="checkbox" checked={feedback.reasons.includes(reason)} onChange={event => setFeedback({ ...feedback, reasons: event.target.checked ? [...feedback.reasons, reason] : feedback.reasons.filter(item => item !== reason) })} />{t(label)}</label>)}
      </fieldset>
      <label htmlFor="feedback-description">{t("Feedback description")}</label>
      <textarea id="feedback-description" rows={4} value={feedback.description} disabled={feedbackBusy || !!feedback.payload} onChange={event => setFeedback({ ...feedback, description: event.target.value })} />
      <small>{t("Enter 1–65536 characters")}</small>
      <label className="feedbackOption"><input type="checkbox" checked={feedback.includeSnapshot} disabled={feedbackBusy || !!feedback.payload} onChange={event => setFeedback({ ...feedback, includeSnapshot: event.target.checked })} />{t("Include the frozen result snapshot")}</label>
      {snapshotTooLarge && feedback.includeSnapshot && <p className="notice" role="alert">{t("Result snapshot exceeds 256 KiB; omit it explicitly to submit an incomplete snapshot")}</p>}
      {!feedback.includeSnapshot && <p className="notice">{t("Result snapshot omitted; snapshot is incomplete")}</p>}
      {revisionsDiffer && <p className="notice">{t("Model revisions differ between pages; each page is retained and the snapshot is incomplete")}</p>}
      {feedbackError && <p className="errorMessage" role="alert">{t("Feedback submission failed")}: {feedbackError}. {t(feedback.payload ? "Retry sends the same feedback ID and content" : "Feedback was rejected; edit and submit again")}</p>}
      <div className="queryActions"><button type="button" disabled={feedbackBusy} onClick={clearFeedback}>{t("Cancel feedback")}</button><button className="primaryButton" disabled={feedbackBusy || !feedback.reasons.length || !feedback.description.trim() || Array.from(feedback.description).length > 65536 || (feedback.includeSnapshot && snapshotTooLarge)}>{t(feedbackBusy ? "Saving feedback…" : feedback.payload ? "Retry original feedback" : "Save feedback")}</button></div>
    </form>}
  </section>;
}
