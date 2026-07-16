import { useEffect, useMemo, useState } from "react";
import { Download, Loader2, Play, Sparkles, Upload } from "lucide-react";
import type {
  SemanticDatasetLoadResponse,
  SemanticEditInputFormat,
  SemanticEditResponse,
  SemanticExportFormat,
  SemanticExportInclude,
  SemanticGraphSetListResponse,
  SemanticJsonObject,
  SemanticSparqlQueryResponse,
} from "../types";
import { useT } from "../i18n";
import { errorNotice } from "../api";
import type { Notice } from "../types";
import {
  applySemanticEdit,
  buildGraphSetExportUrl,
  listGraphSets,
  loadDataset,
  sparqlQuery,
  type SemanticRequester,
} from "../semanticApi";
import { GraphSetSelector, SemanticWarningList } from "../components/semantic";
import { RefreshButton, SemanticEmpty, SemanticPanel, SemanticTag } from "../components/semantic/primitives";
import { prettyJson } from "../utils";

const SAMPLE_DATASET = `@prefix ex: <http://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:SampleConcept a owl:Class .`;

export function SemanticImportExportPage({
  request,
  notify,
  projectId,
  ontologyId,
  initialGraphSetId,
}: {
  request: SemanticRequester;
  notify: (notice: Notice) => void;
  projectId: string;
  ontologyId: string;
  initialGraphSetId?: string;
}) {
  const t = useT();
  const [graphSets, setGraphSets] = useState<SemanticGraphSetListResponse | null>(null);
  const [graphSetId, setGraphSetId] = useState(initialGraphSetId ?? "");
  const [importFormat, setImportFormat] = useState<"trig" | "turtle" | "json-ld">("turtle");
  const [importContent, setImportContent] = useState(SAMPLE_DATASET);
  const [importBaseIri, setImportBaseIri] = useState("");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<SemanticDatasetLoadResponse | null>(null);
  const [editPreview, setEditPreview] = useState<SemanticEditResponse | null>(null);
  const [reason, setReason] = useState("");

  const [exportFormat, setExportFormat] = useState<SemanticExportFormat>("trig");
  const [exportInclude, setExportInclude] = useState<SemanticExportInclude>("asserted");
  const [includeEvidence, setIncludeEvidence] = useState(false);
  const [includeShapes, setIncludeShapes] = useState(false);
  const [includePolicy, setIncludePolicy] = useState(false);
  const [includeMetadata, setIncludeMetadata] = useState(true);
  const [allowStale, setAllowStale] = useState(false);
  const [exportPreview, setExportPreview] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const [sparqlQueryText, setSparqlQueryText] = useState("SELECT * WHERE { ?s ?p ?o } LIMIT 10");
  const [sparqlResult, setSparqlResult] = useState<SemanticSparqlQueryResponse | null>(null);
  const [querying, setQuerying] = useState(false);

  async function loadGraphSets() {
    try {
      const data = await listGraphSets(request);
      setGraphSets(data);
      if (!graphSetId && data.graph_sets.length) setGraphSetId(data.graph_sets[0]!.id);
    } catch (error) {
      notify(errorNotice(error));
    }
  }

  useEffect(() => {
    void loadGraphSets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function importAsDataset() {
    setImporting(true);
    setImportResult(null);
    try {
      const result = await loadDataset(request, {
        content: importContent,
        format: importFormat,
        baseIri: importBaseIri || undefined,
      });
      setImportResult(result);
      notify({
        kind: result.loaded ? "ok" : "error",
        message: t("Dataset import {status}", { status: result.loaded ? t("loaded") : t("failed") }),
      });
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setImporting(false);
    }
  }

  async function previewAsEdit() {
    setImporting(true);
    setEditPreview(null);
    try {
      const result = await applySemanticEdit(request, {
        format: importFormat as SemanticEditInputFormat,
        content: importContent,
        reason: reason || t("Import via Semantic Import/Export workspace"),
      });
      setEditPreview(result);
      notify({
        kind: result.applied ? "ok" : "info",
        message: t("Import applied via governed edit · audit {id}", { id: result.audit_id ?? "preview" }),
      });
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setImporting(false);
    }
  }

  async function runExport() {
    if (!graphSetId) {
      notify({ kind: "error", message: t("Choose a graph set first") });
      return;
    }
    setExporting(true);
    setExportPreview(null);
    try {
      const url = buildExportUrl();
      const response = await fetch(url, { headers: { Accept: "application/json, application/trig, application/ld+json, text/turtle" } });
      const text = await response.text();
      if (!response.ok) {
        throw new Error(`${response.status} ${text}`);
      }
      setExportPreview(text);
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setExporting(false);
    }
  }

  function buildExportUrl() {
    return buildGraphSetExportUrl(graphSetId, {
      format: exportFormat,
      include: exportInclude,
      includeEvidence,
      includeShapes,
      includePolicy,
      includeMetadata,
      allowStaleDerived: allowStale,
    });
  }

  async function runQuery() {
    setQuerying(true);
    setSparqlResult(null);
    try {
      const result = await sparqlQuery(request, {
        projectId,
        ontologyIds: [ontologyId],
        query: sparqlQueryText,
        resultLimit: 50,
      });
      setSparqlResult(result);
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setQuerying(false);
    }
  }

  const exportUrl = useMemo(() => (graphSetId ? buildExportUrl() : ""), [graphSetId, exportFormat, exportInclude, includeEvidence, includeShapes, includePolicy, includeMetadata, allowStale]);

  return (
    <section className="semanticImportExportPage" aria-label="semantic-import-export-page">
      <header className="pageSubHeader">
        <div>
          <span className="eyebrow">{t("Graph Governance")}</span>
          <h2>{t("Import / Export Workspace")}</h2>
          <p>{t("Standards-based exchange without embedding Protégé. Import data, run governed edits, export graph sets, and run read SPARQL.")}</p>
        </div>
        <RefreshButton busy={importing || exporting} onClick={() => void loadGraphSets()} />
      </header>

      <SemanticPanel title={t("Active graph set")} icon={<Sparkles size={15} />}>
        {graphSets && graphSets.graph_sets.length ? (
          <GraphSetSelector graphSets={graphSets.graph_sets} value={graphSetId || null} onChange={setGraphSetId} />
        ) : (
          <SemanticEmpty title={t("No graph sets available")} hint={t("Create one on the Graph Sets page.")} />
        )}
      </SemanticPanel>

      <div className="importExportGrid" aria-label="import-export-grid">
        <SemanticPanel title={t("Import")} icon={<Upload size={15} />}>
          <div className="stackForm">
            <label>
              <span>{t("Format")}</span>
              <select
                onChange={(event) => setImportFormat(event.target.value as "trig" | "turtle" | "json-ld")}
                value={importFormat}
              >
                <option value="turtle">Turtle</option>
                <option value="trig">TriG</option>
                <option value="json-ld">JSON-LD</option>
              </select>
            </label>
            <label>
              <span>{t("Base IRI (optional)")}</span>
              <input
                onChange={(event) => setImportBaseIri(event.target.value)}
                placeholder="http://example.org/"
                value={importBaseIri}
              />
            </label>
            <label>
              <span>{t("Audit reason")}</span>
              <input
                onChange={(event) => setReason(event.target.value)}
                placeholder={t("Why is this import being staged?")}
                value={reason}
              />
            </label>
            <textarea
              className="semanticImportContent"
              onChange={(event) => setImportContent(event.target.value)}
              spellCheck={false}
              value={importContent}
            />
            <div className="buttonRow">
              <button className="secondaryButton" disabled={!importContent || importing} onClick={() => void importAsDataset()} type="button">
                {importing ? <Loader2 className="spin" size={14} /> : <Upload size={14} />} {t("Load dataset")}
              </button>
              <button className="primaryButton" disabled={!importContent || importing} onClick={() => void previewAsEdit()} type="button">
                {importing ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />} {t("Apply as governed edit")}
              </button>
            </div>
            <p className="inlineHint">{t("Datasets are loaded into the canonical RDF store. To enter a managed named graph, use Apply as governed edit.")}</p>
            {importResult && (
              <div className="callout" aria-label="import-result">
                <strong>{t("Loaded")}</strong>
                <SemanticTag tone={importResult.loaded ? "ok" : "warning"}>{importResult.loaded ? t("yes") : t("no")}</SemanticTag>
                <span>{importResult.graph_count ?? "—"} graphs · {importResult.triple_count ?? "—"} triples</span>
                <SemanticWarningList warnings={importResult.warnings} />
              </div>
            )}
            {editPreview && (
              <details>
                <summary>{t("Governed edit response")}</summary>
                <pre className="jsonBlock">{prettyJson(editPreview)}</pre>
              </details>
            )}
          </div>
        </SemanticPanel>

        <SemanticPanel title={t("Export")} icon={<Download size={15} />}>
          {!graphSetId ? (
            <SemanticEmpty title={t("Choose a graph set to enable export")} />
          ) : (
            <div className="stackForm">
              <div className="filterRow">
                <label>
                  <span>{t("Format")}</span>
                  <select onChange={(event) => setExportFormat(event.target.value as SemanticExportFormat)} value={exportFormat}>
                    <option value="trig">TriG</option>
                    <option value="turtle">Turtle</option>
                    <option value="json-ld">JSON-LD</option>
                  </select>
                </label>
                <label>
                  <span>{t("Include")}</span>
                  <select onChange={(event) => setExportInclude(event.target.value as SemanticExportInclude)} value={exportInclude}>
                    <option value="asserted">{t("Asserted only")}</option>
                    <option value="asserted-plus-reasoning">{t("Asserted + reasoning")}</option>
                    <option value="asserted-plus-rules">{t("Asserted + rules")}</option>
                    <option value="full-working-view">{t("Full working view")}</option>
                  </select>
                </label>
              </div>
              <div className="checkRow">
                <label><input checked={includeEvidence} onChange={(event) => setIncludeEvidence(event.target.checked)} type="checkbox" /> {t("Evidence")}</label>
                <label><input checked={includeShapes} onChange={(event) => setIncludeShapes(event.target.checked)} type="checkbox" /> {t("Shapes")}</label>
                <label><input checked={includePolicy} onChange={(event) => setIncludePolicy(event.target.checked)} type="checkbox" /> {t("Policy")}</label>
                <label><input checked={includeMetadata} onChange={(event) => setIncludeMetadata(event.target.checked)} type="checkbox" /> {t("Metadata")}</label>
                <label><input checked={allowStale} onChange={(event) => setAllowStale(event.target.checked)} type="checkbox" /> {t("Allow stale derived")}</label>
              </div>
              <div className="buttonRow">
                <button className="secondaryButton" disabled={!graphSetId || exporting} onClick={() => void runExport()} type="button">
                  {exporting ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />} {t("Preview export")}
                </button>
                <a className="primaryButton" download={`${graphSetId}.${exportFormat}`} href={exportUrl}>
                  <Download size={14} /> {t("Download")}
                </a>
              </div>
              {exportPreview && (
                <details>
                  <summary>{t("Export preview")}</summary>
                  <pre className="jsonBlock">{exportPreview}</pre>
                </details>
              )}
            </div>
          )}
        </SemanticPanel>
      </div>

      <SemanticPanel title={t("SPARQL read query")} icon={<Play size={15} />}>
        <div className="stackForm">
          <textarea
            className="semanticImportContent sparqlInput"
            onChange={(event) => setSparqlQueryText(event.target.value)}
            spellCheck={false}
            value={sparqlQueryText}
          />
          <div className="buttonRow">
            <button
              className="primaryButton"
              disabled={!sparqlQueryText || querying}
              onClick={() => void runQuery()}
              type="button"
            >
              {querying ? <Loader2 className="spin" size={14} /> : <Play size={14} />} {t("Run query")}
            </button>
          </div>
          {sparqlResult && (
            <details>
              <summary>{t("SPARQL result ({format})", { format: sparqlResult.result_format })}</summary>
              <SemanticWarningList warnings={sparqlResult.warnings} />
              <pre className="jsonBlock">{prettyJson(sparqlResult.result as SemanticJsonObject)}</pre>
            </details>
          )}
        </div>
      </SemanticPanel>
    </section>
  );
}
