import { useEffect, useState } from "react";
import { History, Loader2, Network, RefreshCw, ShieldCheck } from "lucide-react";
import type {
  SemanticReasoningRunRead,
  SemanticRuleRunRead,
  SemanticValidationRunRead,
} from "../types";
import { useT } from "../i18n";
import { errorNotice } from "../api";
import type { Notice } from "../types";
import {
  getReasoningRun,
  getRuleRun,
  getValidationRun,
  listReasoningRuns,
  listRuleRuns,
  listValidationRuns,
  type SemanticRequester,
} from "../semanticApi";
import { RefreshButton, SemanticEmpty, SemanticPanel, SemanticTag } from "../components/semantic/primitives";
import { ReasoningResultPanel, RuleResultPanel, StalenessBadge, ValidationReportPanel } from "../components/semantic";
import { prettyJson } from "../utils";

type RunKind = "validation" | "reasoning" | "rule";

export function SemanticRunsPage({
  request,
  notify,
  initialRunKind,
  initialRunId,
}: {
  request: SemanticRequester;
  notify: (notice: Notice) => void;
  initialRunKind?: RunKind;
  initialRunId?: string;
}) {
  const t = useT();
  const [kind, setKind] = useState<RunKind>(initialRunKind ?? "validation");
  const [runId, setRunId] = useState(initialRunId ?? "");
  const [loading, setLoading] = useState(false);
  const [validation, setValidation] = useState<SemanticValidationRunRead | null>(null);
  const [reasoning, setReasoning] = useState<SemanticReasoningRunRead | null>(null);
  const [ruleRun, setRuleRun] = useState<SemanticRuleRunRead | null>(null);
  const [history, setHistory] = useState<Array<SemanticValidationRunRead | SemanticReasoningRunRead | SemanticRuleRunRead>>([]);
  const [summary, setSummary] = useState<{ total: number; stale_count: number; superseded_count: number } | null>(null);
  const [graphSetId, setGraphSetId] = useState("");

  async function loadRun(targetId: string, targetKind: RunKind) {
    if (!targetId) return;
    setLoading(true);
    try {
      if (targetKind === "validation") {
        const result = await getValidationRun(request, targetId);
        setValidation(result);
        setReasoning(null);
        setRuleRun(null);
      } else if (targetKind === "reasoning") {
        const result = await getReasoningRun(request, targetId);
        setReasoning(result);
        setValidation(null);
        setRuleRun(null);
      } else {
        const result = await getRuleRun(request, targetId);
        setRuleRun(result);
        setValidation(null);
        setReasoning(null);
      }
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory(targetKind: RunKind = kind) {
    setLoading(true);
    try {
      const filters = { graphSetId: graphSetId || undefined, limit: 50 };
      if (targetKind === "validation") {
        const result = await listValidationRuns(request, filters);
        setHistory(result.items);
        setSummary(result.summary);
      } else if (targetKind === "reasoning") {
        const result = await listReasoningRuns(request, filters);
        setHistory(result.items);
        setSummary(result.summary);
      } else {
        const result = await listRuleRuns(request, filters);
        setHistory(result.items);
        setSummary(result.summary);
      }
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (initialRunId && initialRunKind) {
      setKind(initialRunKind);
      setRunId(initialRunId);
      void loadRun(initialRunId, initialRunKind);
    }
    void loadHistory(initialRunKind ?? "validation");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="semanticRunsPage" aria-label="semantic-runs-page">
      <header className="pageSubHeader">
        <div>
          <span className="eyebrow">{t("Graph Governance")}</span>
          <h2>{t("Semantic Runs")}</h2>
          <p>{t("Inspect validation, reasoning, and rule run records by ID. Run jobs from the Graph Set page.")}</p>
        </div>
        <RefreshButton busy={loading} onClick={() => void loadHistory(kind)} />
      </header>

      <SemanticPanel
        title={t("Run history")}
        icon={<History size={15} />}
        actions={summary ? <SemanticTag>{summary.total} {t("run(s)")}</SemanticTag> : undefined}
      >
        <div className="filterRow">
          <label>
            <span>{t("Run kind")}</span>
            <select
              onChange={(event) => {
                const next = event.target.value as RunKind;
                setKind(next);
                setValidation(null);
                setReasoning(null);
                setRuleRun(null);
                void loadHistory(next);
              }}
              value={kind}
            >
              <option value="validation">{t("Validation")}</option>
              <option value="reasoning">{t("Reasoning")}</option>
              <option value="rule">{t("Rule")}</option>
            </select>
          </label>
          <label>
            <span>{t("Graph set")}</span>
            <input
              onChange={(event) => setGraphSetId(event.target.value)}
              placeholder="graph-set-..."
              value={graphSetId}
            />
          </label>
          <button className="secondaryButton" disabled={loading} onClick={() => void loadHistory(kind)} type="button">
            {loading ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />} {t("Load history")}
          </button>
          <label>
            <span>{t("Run ID")}</span>
            <input
              onChange={(event) => setRunId(event.target.value)}
              placeholder="run-..."
              value={runId}
            />
          </label>
          <button className="primaryButton" disabled={!runId || loading} onClick={() => void loadRun(runId, kind)} type="button">
            {loading ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />} {t("Load")}
          </button>
        </div>
        {summary && (
          <div className="runHistorySummary" aria-label="run-history-summary">
            <SemanticTag>{t("Total")}: {summary.total}</SemanticTag>
            <SemanticTag tone={summary.stale_count > 0 ? "warning" : "ok"}>{t("Stale")}: {summary.stale_count}</SemanticTag>
            <SemanticTag tone={summary.superseded_count > 0 ? "warning" : undefined}>{t("Superseded")}: {summary.superseded_count}</SemanticTag>
          </div>
        )}
        {!history.length ? (
          <SemanticEmpty title={t("No run history")} hint={t("Run validation, reasoning, or rules from the Graph Set page.")} />
        ) : (
          <table className="namedGraphTable" aria-label="run-history-table">
            <thead>
              <tr>
                <th>{t("Run")}</th>
                <th>{t("Scope")}</th>
                <th>{t("Status")}</th>
                <th>{t("Result")}</th>
                <th>{t("Started")}</th>
                <th>{t("Staleness")}</th>
              </tr>
            </thead>
            <tbody>
              {history.map((run) => (
                <tr key={run.run_id}>
                  <td>
                    <button
                      className="ghostButton"
                      type="button"
                      onClick={() => {
                        setRunId(run.run_id);
                        void loadRun(run.run_id, kind);
                      }}
                    >
                      <code>{run.run_id}</code>
                    </button>
                  </td>
                  <td>{run.graph_set_id ?? "—"}</td>
                  <td><SemanticTag tone={run.status === "succeeded" ? "ok" : run.status === "failed" ? "error" : "warning"}>{run.status}</SemanticTag></td>
                  <td>{runResultLabel(run)}</td>
                  <td>{run.started_at ? new Date(run.started_at).toLocaleString() : "—"}</td>
                  <td><StalenessBadge stale={runIsStale(run)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </SemanticPanel>

      <SemanticPanel title={t("Selected run")} icon={<ShieldCheck size={15} />}
        actions={
          <div className="headerActions">
            <SemanticTag>{kind}</SemanticTag>
            {validation && <StalenessBadge stale={isStale(validation.staleness)} />}
            {reasoning && <StalenessBadge stale={isStale(reasoning.input_derived_pointers)} />}
            {ruleRun && <SemanticTag>{ruleRun.engine_name}</SemanticTag>}
          </div>
        }
      >
        {!validation && !reasoning && !ruleRun ? (
          <SemanticEmpty title={t("No run loaded")} hint={t("Enter a run ID and choose a run kind to inspect.")} icon={<History size={20} />} />
        ) : (
          <div className="semanticRunDetailGrid">
            <ValidationReportPanel run={validation} />
            <ReasoningResultPanel run={reasoning} />
            <RuleResultPanel run={ruleRun} />
            <SemanticPanel title={t("Raw run record")} icon={<Network size={15} />}>
              <pre className="jsonBlock">
                {prettyJson(validation ?? reasoning ?? ruleRun ?? {})}
              </pre>
            </SemanticPanel>
          </div>
        )}
      </SemanticPanel>
    </section>
  );
}

function runResultLabel(run: SemanticValidationRunRead | SemanticReasoningRunRead | SemanticRuleRunRead): string {
  if ("conforms" in run) return run.conforms === null ? "pending" : run.conforms ? "conforms" : "violations";
  if ("consistent" in run) return run.consistent === null ? "pending" : run.consistent ? "consistent" : "inconsistent";
  return `${run.generated_statement_count} statement(s)`;
}

function runIsStale(run: SemanticValidationRunRead | SemanticReasoningRunRead | SemanticRuleRunRead): boolean {
  if ("staleness" in run) return isStale(run.staleness);
  if ("derived_pointer" in run && run.derived_pointer) return isStale(run.derived_pointer);
  return false;
}

function isStale(state: unknown): boolean {
  if (!state) return false;
  if (typeof state === "boolean") return state;
  if (typeof state === "object") {
    const record = state as Record<string, unknown>;
    return record.stale === true || record.is_stale === true || record.status === "stale";
  }
  return false;
}
