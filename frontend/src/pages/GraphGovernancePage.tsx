import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  FileCheck2,
  Layers,
  Network,
  RefreshCw,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import type {
  SemanticDerivedResultReconcileResponse,
  SemanticEditAuditRead,
  SemanticGovernanceStatusResponse,
  SemanticGraphRegistryListResponse,
  SemanticGraphSetListResponse,
  SemanticProjectionStatusResponse,
} from "../types";
import { useT } from "../i18n";
import { errorNotice } from "../api";
import type { Notice } from "../types";
import {
  getGovernanceStatus,
  getProjectionStatus,
  listEditAudits,
  listGraphRegistry,
  listGraphSets,
  readModel,
  reconcileDerivedResults,
  type SemanticRequester,
} from "../semanticApi";
import { GraphIriLabel, StalenessBadge } from "../components/semantic";
import { RefreshButton, SemanticEmpty, SemanticPanel, SemanticTag, StatTile } from "../components/semantic/primitives";
import { prettyJson } from "../utils";

type OwlConsistencyEnvelope = {
  graph_set_id: string;
  model_name: string;
  projection_version: string;
  items: Array<{
    run_id: string;
    consistent: boolean | null;
    classification: unknown;
    entailment_count: number;
    unsatisfiable_classes: string[];
    result_graph_iri: string;
    started_at: string;
    finished_at: string | null;
    is_stale: boolean;
  }>;
};

export function GraphGovernancePage({
  request,
  navigate,
  notify,
}: {
  request: SemanticRequester;
  navigate: (tab: string, params?: Record<string, string>) => void;
  notify: (notice: Notice) => void;
}) {
  const t = useT();
  const [status, setStatus] = useState<SemanticGovernanceStatusResponse | null>(null);
  const [graphSets, setGraphSets] = useState<SemanticGraphSetListResponse | null>(null);
  const [graphs, setGraphs] = useState<SemanticGraphRegistryListResponse | null>(null);
  const [audits, setAudits] = useState<SemanticEditAuditRead[]>([]);
  const [projectionStatus, setProjectionStatus] = useState<SemanticProjectionStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [owlConsistency, setOwlConsistency] = useState<OwlConsistencyEnvelope | null>(null);

  async function loadAll() {
    setLoading(true);
    try {
      const [statusData, setsData, graphsData, auditsData, projectionData] = await Promise.all([
        getGovernanceStatus(request),
        listGraphSets(request),
        listGraphRegistry(request),
        listEditAudits(request, 8),
        getProjectionStatus(request).catch(() => null),
      ]);
      setStatus(statusData);
      setGraphSets(setsData);
      setGraphs(graphsData);
      setAudits(auditsData);
      setProjectionStatus(projectionData);
      // Stage 4 §4.3 — fetch the OWL consistency summary for the
      // first active graph set. Falls back silently if there is no
      // active graph set; the panel renders an empty state in that case.
      const loadedGraphSets = safeArray(setsData?.graph_sets);
      const targetGraphSetId =
        loadedGraphSets.find((gs) => gs.status === "active")?.id ??
        loadedGraphSets[0]?.id ??
        null;
      if (targetGraphSetId) {
        try {
          const envelope = await readModel<OwlConsistencyEnvelope>(
            request,
            targetGraphSetId,
            "owl-consistency-summary",
          );
          setOwlConsistency(envelope);
        } catch {
          // The composer fails open when no reasoning run exists for
          // the graph set yet; surface an empty state instead of an error.
          setOwlConsistency(null);
        }
      } else {
        setOwlConsistency(null);
      }
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const graphSetList = safeArray(graphSets?.graph_sets);
  const activeGraphSetId =
    graphSetList.find((gs) => gs.status === "active")?.id ??
    graphSetList[0]?.id ??
    null;
  const summary = useMemo(
    () => deriveSummary(status, graphs, graphSets, projectionStatus),
    [status, graphs, graphSets, projectionStatus],
  );

  async function reconcile() {
    setReconciling(true);
    try {
      const result: SemanticDerivedResultReconcileResponse = await reconcileDerivedResults(request);
      notify({
        kind: result.pointers_marked_stale > 0 || result.pointers_marked_current > 0 ? "ok" : "info",
        message: t(
          "Reconciled {inspected} graph sets · {stale} marked stale · {current} marked current",
          {
            inspected: result.graph_sets_inspected,
            stale: result.pointers_marked_stale,
            current: result.pointers_marked_current,
          },
        ),
      });
      await loadAll();
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setReconciling(false);
    }
  }

  return (
    <section className="graphGovernancePage" aria-label="graph-governance-page">
      <header className="pageSubHeader">
        <div>
          <span className="eyebrow">{t("Graph Governance")}</span>
          <h2>{t("Graph Governance Dashboard")}</h2>
          <p>{t("Semantic health across named graphs, graph sets, derived results, projections, and audit deltas.")}</p>
        </div>
        <RefreshButton busy={loading || reconciling} onClick={() => void loadAll()} />
      </header>

      <section className="statTileRow" aria-label="governance-summary-tiles">
        <StatTile
          label={t("Registered graphs")}
          value={summary.registeredGraphs}
          hint={t("Across all categories")}
        />
        <StatTile
          label={t("Editable actual graphs")}
          value={`${summary.editableGraphs} / ${summary.actualGraphs}`}
          hint={summary.editableGraphs < summary.actualGraphs ? t("Some graphs are locked") : undefined}
          tone={summary.editableGraphs < summary.actualGraphs ? "warning" : "ok"}
        />
        <StatTile
          label={t("Graph sets")}
          value={summary.graphSetsCount}
          hint={summary.graphSetNames.length ? summary.graphSetNames.slice(0, 3).join(", ") : undefined}
        />
        <StatTile
          label={t("Stale derived results")}
          value={summary.staleDerived}
          tone={summary.staleDerived > 0 ? "warning" : "ok"}
        />
        <StatTile
          label={t("Stale projections")}
          value={summary.staleProjections}
          hint={summary.staleProjections > 0 ? t("Projection manifests need rebuild") : t("Projection manifests are current")}
          tone={summary.staleProjections > 0 ? "warning" : "ok"}
        />
        <StatTile
          label={t("Missing evidence")}
          value={summary.missingEvidence}
          tone={summary.missingEvidence > 0 ? "error" : "ok"}
        />
      </section>

      <OwlConsistencySection
        envelope={owlConsistency}
        activeGraphSetId={activeGraphSetId}
      />

      <section className="governanceGrid" aria-label="governance-grid">
        <SemanticPanel
          title={t("Graph set health")}
          icon={<Layers size={15} />}
          actions={<SemanticTag tone={summary.activeGraphSets > 0 ? "ok" : "warning"}>{summary.activeGraphSets} {t("active")}</SemanticTag>}
        >
          {summary.activeGraphSets === 0 ? (
            <SemanticEmpty icon={<Network size={20} />} title={t("No active graph sets")} hint={t("Create a graph set on the Graph Sets page.")} />
          ) : (
            <ul className="graphSetHealthList">
              {graphSetList.slice(0, 5).map((graphSet) => {
                const currentPointers = safeArray(graphSet.current_pointers);
                const staleCount = currentPointers.filter((pointer) => isStalePointer(pointer)).length;
                return (
                  <li key={graphSet.id} className="graphSetHealthRow">
                    <button
                      className="graphSetHealthMain"
                      onClick={() => navigate("graph-sets", { graphSet: graphSet.id })}
                      type="button"
                    >
                      <strong>{graphSet.name}</strong>
                      <span>{graphSet.scope_type}{graphSet.scope_id ? ` · ${graphSet.scope_id}` : ""}</span>
                      <code>{String(graphSet.source_signature ?? "").slice(0, 12) || t("unset")}</code>
                    </button>
                    <div className="graphSetHealthState">
                      <StalenessBadge stale={staleCount > 0} detail={t("{count} stale pointer(s)", { count: staleCount })} />
                      <SemanticTag>{currentPointers.length} {t("pointer(s)")}</SemanticTag>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </SemanticPanel>

        <SemanticPanel
          title={t("Latest graph deltas")}
          icon={<FileCheck2 size={15} />}
          actions={<SemanticTag>{audits.length} {t("audit(s)")}</SemanticTag>}
        >
          {!audits.length ? (
            <SemanticEmpty title={t("No audit records yet")} hint={t("Apply a governed semantic edit to populate this list.")} />
          ) : (
            <ol className="auditList">
              {audits.map((audit) => (
                <li key={audit.id} className="auditRow" aria-label={`audit-${audit.id}`}>
                  <div className="auditMain">
                    <strong>{audit.input_format}</strong>
                    {audit.target_graph_iri && <GraphIriLabel iri={audit.target_graph_iri} />}
                    {audit.applied ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                  </div>
                  <dl>
                    <div><dt>{t("Audit ID")}</dt><dd><code>{audit.id}</code></dd></div>
                    <div><dt>{t("Actor")}</dt><dd>{audit.actor ?? t("unknown")}</dd></div>
                    <div><dt>{t("Reason")}</dt><dd>{audit.reason ?? t("unset")}</dd></div>
                    {audit.evidence_status && (
                      <div><dt>{t("Evidence")}</dt><dd>{audit.evidence_status}</dd></div>
                    )}
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

        <SemanticPanel
          title={t("Derived results")}
          icon={<Workflow size={15} />}
          actions={<button className="secondaryButton" disabled={reconciling} onClick={() => void reconcile()} type="button">{t("Reconcile staleness")}</button>}
        >
          <DerivedSummary derived={summary.derivedSummary} />
        </SemanticPanel>

        <SemanticPanel title={t("Validation & reasoning summary")} icon={<ShieldCheck size={15} />}>
          <ValidationReasoningSummary status={status} />
        </SemanticPanel>
      </section>

      <section className="governanceActions" aria-label="governance-actions">
        <button className="secondaryButton" onClick={() => navigate("named-graphs")} type="button">
          <Database size={14} /> {t("Open named graph registry")}
        </button>
        <button className="secondaryButton" onClick={() => navigate("graph-sets")} type="button">
          <Layers size={14} /> {t("Open graph sets")}
        </button>
        <button className="secondaryButton" onClick={() => navigate("semantic-runs")} type="button">
          <Workflow size={14} /> {t("Open runs")}
        </button>
        <button className="secondaryButton" onClick={() => navigate("semantic-edits")} type="button">
          <FileCheck2 size={14} /> {t("Open semantic workbench")}
        </button>
        <button className="secondaryButton" onClick={() => navigate("semantic-import-export")} type="button">
          <RefreshCw size={14} /> {t("Open import / export")}
        </button>
      </section>
    </section>
  );
}

function DerivedSummary({ derived }: { derived: Record<string, unknown> | null }) {
  const t = useT();
  if (!derived) {
    return <SemanticEmpty title={t("Derived state unavailable")} hint={t("Run reconcile to inspect pointers.")} />;
  }
  const entries = Object.entries(derived);
  if (!entries.length) return <SemanticEmpty title={t("No derived results to display")} />;
  return (
    <ul className="derivedSummaryList">
      {entries.map(([key, value]) => (
        <li key={key}>
          <code>{key}</code>
          <span>{prettyJson(value)}</span>
        </li>
      ))}
    </ul>
  );
}

function ValidationReasoningSummary({ status }: { status: SemanticGovernanceStatusResponse | null }) {
  const t = useT();
  if (!status) return <SemanticEmpty title={t("Status unavailable")} />;
  const graphs = (status.graphs ?? {}) as Record<string, unknown>;
  const derived = (status.derived ?? {}) as Record<string, unknown>;
  return (
    <dl className="kvList">
      <div><dt>{t("Graphs by category")}</dt><dd>{prettyJson(graphs.by_category ?? graphs.categories ?? {})}</dd></div>
      <div><dt>{t("Editable vs locked")}</dt><dd>{prettyJson(graphs.editability ?? graphs.editability_state ?? {})}</dd></div>
      <div><dt>{t("Reasoning pointers")}</dt><dd>{prettyJson(derived.reasoning ?? derived.reasoning_pointers ?? {})}</dd></div>
      <div><dt>{t("Rule pointers")}</dt><dd>{prettyJson(derived.rules ?? derived.rule_pointers ?? {})}</dd></div>
      <div><dt>{t("Missing-evidence warnings")}</dt><dd>{prettyJson(derived.missing_evidence ?? derived.missing_evidence_summary ?? {})}</dd></div>
    </dl>
  );
}

function deriveSummary(
  status: SemanticGovernanceStatusResponse | null,
  graphs: SemanticGraphRegistryListResponse | null,
  graphSets: SemanticGraphSetListResponse | null,
  projectionStatus: SemanticProjectionStatusResponse | null,
) {
  const graphsSummary = (status?.graphs ?? {}) as Record<string, unknown>;
  const derivedSummary = (status?.derived ?? {}) as Record<string, unknown>;
  const graphList = safeArray(graphs?.graphs);
  const graphSetList = safeArray(graphSets?.graph_sets);
  const graphCount = (graphsSummary.total ?? graphsSummary.registered ?? graphList.length) as number;
  const editableGraphs = pickNumber(graphsSummary, ["editable", "editable_count"]) ?? countEditable(graphList, true);
  const actualGraphs = pickNumber(graphsSummary, ["actual", "actual_count"]) ?? countActual(graphList);
  const staleDerived = pickNumber(derivedSummary, ["stale_count", "stale"]) ?? countStaleDerived(status);
  const staleProjections =
    projectionStatus?.stale_projection_count ?? safeArray(projectionStatus?.stale).length;
  const missingEvidence = pickNumber(derivedSummary, ["missing_evidence_count", "missing_evidence"]) ?? 0;
  const activeGraphSets = graphSetList.filter((graphSet) => graphSet.status === "active").length;
  return {
    registeredGraphs: typeof graphCount === "number" ? graphCount : graphList.length,
    editableGraphs,
    actualGraphs: actualGraphs || graphList.length,
    staleDerived,
    staleProjections,
    missingEvidence,
    graphSetsCount: graphSetList.length,
    activeGraphSets,
    graphSetNames: graphSetList.map((graphSet) => graphSet.name),
    derivedSummary,
  };
}

function countEditable(graphs: SemanticGraphRegistryListResponse["graphs"], editable: boolean): number {
  return graphs.filter((graph) => graph.editable === editable).length;
}

function countActual(graphs: SemanticGraphRegistryListResponse["graphs"]): number {
  return graphs.filter((graph) => graph.category === "ontology" || graph.category === "data").length;
}

function countStaleDerived(status: SemanticGovernanceStatusResponse | null): number {
  if (!status) return 0;
  const derived = (status.derived ?? {}) as Record<string, unknown>;
  const pointers = pickArray(derived, ["pointers", "derived_pointers"]) ?? [];
  return pointers.filter((pointer) => isStalePointer(pointer as Record<string, unknown>)).length;
}

function pickNumber(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    if (key in record) {
      const value = Number(record[key]);
      if (!Number.isNaN(value)) return value;
    }
  }
  return null;
}

function pickArray(record: Record<string, unknown>, keys: string[]): unknown[] | null {
  for (const key of keys) {
    if (key in record) {
      const value = record[key];
      if (Array.isArray(value)) return value;
    }
  }
  return null;
}

function safeArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : [];
}

function formatOptionalValue(value: unknown, fallback: string): string {
  if (value === null || value === undefined || value === "") return fallback;
  return typeof value === "string" ? value : prettyJson(value);
}

function isStalePointer(pointer: unknown): boolean {
  if (!pointer || typeof pointer !== "object") return false;
  const record = pointer as Record<string, unknown>;
  return record.stale === true || record.is_stale === true || record.status === "stale";
}

/**
 * Stage 4 §4.3 — OWL Consistency section.
 *
 * Renders the latest ``reasoning-runs`` consistency result for the
 * dashboard's first active graph set, surfaced via the
 * ``owl-consistency-summary`` read model. The section sits between the
 * summary stat tiles and the existing governance grid.
 */
function OwlConsistencySection({
  envelope,
  activeGraphSetId,
}: {
  envelope: OwlConsistencyEnvelope | null;
  activeGraphSetId: string | null;
}) {
  const t = useT();
  if (!activeGraphSetId) {
    return (
      <SemanticPanel
        title={t("OWL Consistency")}
        icon={<ShieldCheck size={15} />}
      >
        <SemanticEmpty
          icon={<Network size={20} />}
          title={t("No active graph set")}
          hint={t("Create a graph set on the Graph Sets page to inspect OWL consistency.")}
        />
      </SemanticPanel>
    );
  }
  const item = envelope?.items?.[0] ?? null;
  if (!item) {
    return (
      <SemanticPanel
        title={t("OWL Consistency · {id}", { id: activeGraphSetId })}
        icon={<ShieldCheck size={15} />}
      >
        <SemanticEmpty
          title={t("No OWL consistency run yet")}
          hint={t("Run reasoning on the graph set to populate this section.")}
        />
      </SemanticPanel>
    );
  }
  const consistentTone: "ok" | "error" | "warning" =
    item.consistent === null ? "warning" : item.consistent ? "ok" : "error";
  const consistentLabel =
    item.consistent === null
      ? t("Pending")
      : item.consistent
        ? t("Consistent")
        : t("Inconsistent");
  const unsatisfiableClasses = safeArray(item.unsatisfiable_classes);
  return (
    <SemanticPanel
      title={t("OWL Consistency · {id}", { id: activeGraphSetId })}
      icon={<ShieldCheck size={15} />}
      actions={<SemanticTag tone={consistentTone}>{consistentLabel}</SemanticTag>}
    >
      {item.is_stale && (
        <div className="callout warning" aria-label="owl-consistency-stale-banner">
          <AlertTriangle size={14} />
          <span>
            {t("Consistency result is stale — run reasoning to refresh.")}
          </span>
        </div>
      )}
      <dl className="kvList" aria-label="owl-consistency-summary">
        <div>
          <dt>{t("Consistent")}</dt>
          <dd>
            <SemanticTag tone={consistentTone}>{consistentLabel}</SemanticTag>
          </dd>
        </div>
        <div>
          <dt>{t("Classification")}</dt>
          <dd>{formatOptionalValue(item.classification, t("unset"))}</dd>
        </div>
        <div>
          <dt>{t("Entailments")}</dt>
          <dd>{item.entailment_count}</dd>
        </div>
        <div>
          <dt>{t("Unsatisfiable classes")}</dt>
          <dd>
            {unsatisfiableClasses.length === 0 ? (
              <span>{t("None")}</span>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {unsatisfiableClasses.map((cls) => (
                  <li key={cls}>
                    <code>{cls}</code>
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
        <div>
          <dt>{t("Result graph")}</dt>
          <dd>{item.result_graph_iri ? <code>{item.result_graph_iri}</code> : t("unset")}</dd>
        </div>
        <div>
          <dt>{t("Started")}</dt>
          <dd>{item.started_at}</dd>
        </div>
        <div>
          <dt>{t("Finished")}</dt>
          <dd>{item.finished_at ?? t("unset")}</dd>
        </div>
        <div>
          <dt>{t("Run ID")}</dt>
          <dd><code>{item.run_id}</code></dd>
        </div>
      </dl>
    </SemanticPanel>
  );
}
