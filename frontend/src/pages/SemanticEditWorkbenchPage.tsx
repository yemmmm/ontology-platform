import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Braces,
  CheckCircle2,
  FileCheck2,
  Loader2,
  Play,
  Sparkles,
  Wrench,
} from "lucide-react";
import type {
  SemanticEditAuditRead,
  SemanticEditEvidenceStatus,
  SemanticEditInputFormat,
  SemanticEditResponse,
  SemanticGraphSetListResponse,
  SemanticJsonObject,
} from "../types";
import { useT } from "../i18n";
import { errorNotice } from "../api";
import type { Notice } from "../types";
import {
  applySemanticEdit,
  listEditAudits,
  listGraphSets,
  previewSemanticEdit,
  type SemanticRequester,
} from "../semanticApi";
import {
  EvidenceBindingPanel,
  GraphDeltaViewer,
  GraphSetSelector,
  parseWarningState,
  SemanticWarningList,
  splitEvidenceIds,
} from "../components/semantic";
import { RefreshButton, SemanticEmpty, SemanticPanel, SemanticTag } from "../components/semantic/primitives";
import { prettyJson } from "../utils";

const SAMPLE_TURTLE = `@prefix ex: <http://example.org/> .
ex:Sample a ex:Concept ;
  ex:label "Sample concept" .`;

const SAMPLE_TRIG = `@prefix ex: <http://example.org/> .
ex:SampleGraph {
  ex:Sample a ex:Concept ;
    ex:label "Sample concept" .
}`;

const SAMPLE_JSONLD = JSON.stringify(
  {
    "@context": { ex: "http://example.org/" },
    "@id": "ex:Sample",
    "@type": "ex:Concept",
    "ex:label": "Sample concept",
  },
  null,
  2,
);

const SAMPLE_SPARQL_UPDATE = `PREFIX ex: <http://example.org/>
INSERT DATA {
  GRAPH ex:SampleGraph {
    ex:Sample a ex:Concept .
  }
}`;

export function SemanticEditWorkbenchPage({
  request,
  notify,
  initialTargetGraphIri,
  initialGraphSetId,
}: {
  request: SemanticRequester;
  notify: (notice: Notice) => void;
  initialTargetGraphIri?: string;
  initialGraphSetId?: string;
}) {
  const t = useT();
  const [graphSets, setGraphSets] = useState<SemanticGraphSetListResponse | null>(null);
  const [graphSetId, setGraphSetId] = useState(initialGraphSetId ?? "");
  const [format, setFormat] = useState<SemanticEditInputFormat>("turtle");
  const [content, setContent] = useState(SAMPLE_TURTLE);
  const [targetGraphIri, setTargetGraphIri] = useState(initialTargetGraphIri ?? "");
  const [shapeGraphIris, setShapeGraphIris] = useState("");
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [evidenceStatus, setEvidenceStatus] = useState<SemanticEditEvidenceStatus | null>(null);
  const [evidenceIds, setEvidenceIds] = useState("");
  const [warningState, setWarningState] = useState("");
  const [preview, setPreview] = useState<SemanticEditResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [audits, setAudits] = useState<SemanticEditAuditRead[]>([]);

  async function loadGraphSets() {
    try {
      const data = await listGraphSets(request);
      setGraphSets(data);
      if (!graphSetId && data.graph_sets.length) setGraphSetId(data.graph_sets[0]!.id);
    } catch (error) {
      notify(errorNotice(error));
    }
  }

  async function loadAudits() {
    try {
      const data = await listEditAudits(request, 5);
      setAudits(data);
    } catch {
      // audits are best-effort
    }
  }

  useEffect(() => {
    void loadGraphSets();
    void loadAudits();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const payload = useMemo(
    () => ({
      format,
      content,
      targetGraphIri: targetGraphIri || undefined,
      shapeGraphIris: splitEvidenceIds(shapeGraphIris),
      actor: actor || undefined,
      reason: reason || undefined,
      evidenceStatus,
      warningState: parseWarningState(warningState),
      evidenceIds,
    }),
    [format, content, targetGraphIri, shapeGraphIris, actor, reason, evidenceStatus, warningState, evidenceIds],
  );

  async function previewEdit() {
    setPreviewing(true);
    setPreview(null);
    try {
      const result = await previewSemanticEdit(request, payload);
      setPreview(result);
      if (result.applied) {
        notify({ kind: "info", message: t("Backend applied this edit even during preview. Inspect the delta below.") });
      }
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setPreviewing(false);
    }
  }

  async function applyEdit() {
    setApplying(true);
    try {
      const result = await applySemanticEdit(request, payload);
      notify({ kind: "ok", message: t("Semantic edit applied · audit {id}", { id: result.audit_id }) });
      setPreview(result);
      await loadAudits();
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setApplying(false);
    }
  }

  const previewDisabled = !content.trim() || previewing;

  return (
    <section className="semanticEditWorkbenchPage" aria-label="semantic-edit-workbench">
      <header className="pageSubHeader">
        <div>
          <span className="eyebrow">{t("Graph Governance")}</span>
          <h2>{t("Direct Semantic Edit Workbench")}</h2>
          <p>{t("Submit TriG, Turtle, JSON-LD, or constrained SPARQL Update through the governed semantic edit path.")}</p>
        </div>
        <RefreshButton busy={previewing || applying} onClick={() => void loadAudits()} label={t("Refresh audits")} />
      </header>

      <div className="semanticEditSplit" aria-label="semantic-edit-split">
        <SemanticPanel
          title={t("Edit input")}
          icon={<Braces size={15} />}
          actions={
            <div className="headerActions">
              <select
                onChange={(event) => {
                  const next = event.target.value as SemanticEditInputFormat;
                  setFormat(next);
                  setContent(defaultContentFor(next));
                }}
                value={format}
              >
                <option value="turtle">Turtle</option>
                <option value="trig">TriG</option>
                <option value="json-ld">JSON-LD</option>
                <option value="sparql-update">SPARQL Update</option>
              </select>
            </div>
          }
        >
          <div className="stackForm">
            <label>
              <span>{t("Target graph IRI")}</span>
              <input
                onChange={(event) => setTargetGraphIri(event.target.value)}
                placeholder="graph:ontology/... (optional for TriG/JSON-LD)"
                value={targetGraphIri}
              />
            </label>
            <label>
              <span>{t("Shape graph IRIs (comma separated)")}</span>
              <input
                onChange={(event) => setShapeGraphIris(event.target.value)}
                placeholder="graph:shape/..."
                value={shapeGraphIris}
              />
            </label>
            <label>
              <span>{t("Actor")}</span>
              <input onChange={(event) => setActor(event.target.value)} placeholder="agent or user identifier" value={actor} />
            </label>
            <label>
              <span>{t("Reason / audit note")}</span>
              <input onChange={(event) => setReason(event.target.value)} placeholder="why is this edit being submitted?" value={reason} />
            </label>
            <GraphSetSelector
              graphSets={graphSets?.graph_sets ?? []}
              value={graphSetId || null}
              onChange={setGraphSetId}
            />
            <textarea
              aria-label={t("Semantic edit content")}
              className="semanticEditContent"
              onChange={(event) => setContent(event.target.value)}
              spellCheck={false}
              value={content}
            />
            <EvidenceBindingPanel
              evidenceIds={evidenceIds}
              evidenceStatus={evidenceStatus}
              warningState={warningState}
              onEvidenceIdsChange={setEvidenceIds}
              onStatusChange={setEvidenceStatus}
              onWarningStateChange={setWarningState}
            />
            <div className="buttonRow">
              <button
                className="secondaryButton"
                disabled={previewDisabled}
                onClick={() => void previewEdit()}
                type="button"
              >
                {previewing ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />} {t("Preview")}
              </button>
              <button
                className="primaryButton"
                disabled={previewDisabled || applying || (preview !== null && preview.applied === false && (preview.validation?.["ok"] === false))}
                onClick={() => void applyEdit()}
                type="button"
              >
                {applying ? <Loader2 className="spin" size={14} /> : <Play size={14} />} {t("Apply edit")}
              </button>
            </div>
            <p className="inlineHint">
              {t("Apply runs validation, editability checks, audit, and graph-delta calculation server-side.")}
            </p>
          </div>
        </SemanticPanel>

        <SemanticPanel
          title={t("Preview & validation")}
          icon={<Wrench size={15} />}
          actions={preview ? <SemanticTag tone={preview.applied ? "ok" : "warning"}>{preview.applied ? t("applied") : t("preview")}</SemanticTag> : undefined}
        >
          {!preview ? (
            <SemanticEmpty title={t("No preview yet")} hint={t("Press Preview to validate the edit and inspect the graph delta.")} icon={<FileCheck2 size={20} />} />
          ) : (
            <div className="semanticEditPreview">
              <SemanticWarningList warnings={preview.warnings} title={t("Warnings")} />
              <GraphDeltaViewer delta={preview.delta as SemanticJsonObject} defaultExpanded />
              {preview.validation && (
                <details>
                  <summary>{t("Validation report")}</summary>
                  <pre className="jsonBlock">{prettyJson(preview.validation)}</pre>
                </details>
              )}
              <dl className="kvList">
                <div><dt>{t("Audit ID")}</dt><dd><code>{preview.audit_id}</code></dd></div>
                <div><dt>{t("Affected graphs")}</dt><dd>{preview.affected_graph_iris.join(", ") || "—"}</dd></div>
                <div>
                  <dt>{t("Graph revisions")}</dt>
                  <dd><pre className="jsonBlock">{prettyJson(preview.graph_revisions)}</pre></dd>
                </div>
                <div>
                  <dt>{t("Stale derived pointers")}</dt>
                  <dd>{preview.stale_derived_pointers.length}</dd>
                </div>
              </dl>
              {preview.stale_derived_pointers.length > 0 && (
                <div className="callout warning" aria-label="stale-derived-pointer-warning">
                  <AlertTriangle size={14} />
                  <span>{t("Stale derived pointers were created. Reconcile from the Graph Governance dashboard.")}</span>
                </div>
              )}
            </div>
          )}
        </SemanticPanel>
      </div>

      <SemanticPanel title={t("Recent semantic edit audits")} icon={<FileCheck2 size={15} />}>
        {!audits.length ? (
          <SemanticEmpty title={t("No audit records yet")} />
        ) : (
          <ol className="auditList">
            {audits.map((audit) => (
              <li key={audit.id} className="auditRow">
                <div className="auditMain">
                  <strong>{audit.input_format}</strong>
                  <code>{audit.target_graph_iri ?? "—"}</code>
                  {audit.applied ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                </div>
                <dl className="kvList">
                  <div><dt>{t("Audit ID")}</dt><dd><code>{audit.id}</code></dd></div>
                  <div><dt>{t("Actor")}</dt><dd>{audit.actor ?? "—"}</dd></div>
                  <div><dt>{t("Reason")}</dt><dd>{audit.reason ?? "—"}</dd></div>
                  <div><dt>{t("Evidence status")}</dt><dd>{audit.evidence_status ?? "—"}</dd></div>
                </dl>
                <details>
                  <summary>{t("Graph delta")}</summary>
                  <pre className="jsonBlock">{prettyJson(audit.graph_delta)}</pre>
                </details>
              </li>
            ))}
          </ol>
        )}
      </SemanticPanel>
    </section>
  );
}

function defaultContentFor(format: SemanticEditInputFormat): string {
  switch (format) {
    case "trig":
      return SAMPLE_TRIG;
    case "json-ld":
      return SAMPLE_JSONLD;
    case "sparql-update":
      return SAMPLE_SPARQL_UPDATE;
    case "turtle":
    default:
      return SAMPLE_TURTLE;
  }
}
