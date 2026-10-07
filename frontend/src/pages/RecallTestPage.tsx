import { useEffect, useRef, useState, type FormEvent } from "react";
import { useT } from "../i18n";
import { workspaceApi } from "../workspaceApi";
import type { Project, RecallResponse, RecallResult } from "../workspaceTypes";
export function RecallTestPage({ project }: { project: Project }) {
  const t = useT();
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [items, setItems] = useState<RecallResult[]>([]);
  const [response, setResponse] = useState<RecallResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  useEffect(() => () => { sequence.current++; }, []);
  function edit(value: string) {
    sequence.current++;
    setQuery(value); setSubmitted(""); setItems([]); setResponse(null); setLoading(false); setError("");
  }
  async function search(more = false) {
    const text = more ? submitted : query.trim();
    if (!text || text.length > 2000) return;
    const token = ++sequence.current;
    setLoading(true); setError("");
    if (!more) { setSubmitted(text); setItems([]); setResponse(null); }
    try {
      const value = await workspaceApi.recall(project.id, text, more ? response?.matches_page.next_match_cursor ?? undefined : undefined);
      if (sequence.current !== token) return;
      setResponse(value);
      const nodes = value.primary_matches.filter(item => ["concept", "instance", "operation", "mapping", "metric"].includes(item.kind ?? ""));
      setItems(current => [...new Map((more ? [...current, ...nodes] : nodes).map(item => [item.id, item])).values()]);
    } catch (reason) {
      if (sequence.current === token) { setError(String(reason)); setResponse(null); }
    } finally { if (sequence.current === token) setLoading(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); void search(); }
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
    </>}
  </section>;
}
