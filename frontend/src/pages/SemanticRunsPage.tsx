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

  useEffect(() => {
    if (initialRunId && initialRunKind) {
      setKind(initialRunKind);
      setRunId(initialRunId);
      void loadRun(initialRunId, initialRunKind);
    }
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
        <RefreshButton busy={loading} onClick={() => runId && void loadRun(runId, kind)} />
      </header>

      <SemanticPanel title={t("Run lookup")} icon={<History size={15} />}>
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
              }}
              value={kind}
            >
              <option value="validation">{t("Validation")}</option>
              <option value="reasoning">{t("Reasoning")}</option>
              <option value="rule">{t("Rule")}</option>
            </select>
          </label>
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

function isStale(state: unknown): boolean {
  if (!state) return false;
  if (typeof state === "boolean") return state;
  if (typeof state === "object") {
    const record = state as Record<string, unknown>;
    return record.stale === true || record.is_stale === true || record.status === "stale";
  }
  return false;
}
