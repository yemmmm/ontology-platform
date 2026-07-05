import { Card, Tag } from "antd";
import { Workflow } from "lucide-react";
import type { SemanticRuleRunRead } from "../../types";
import { useT } from "../../i18n";
import { SemanticWarningList } from "./SemanticWarningList";

export function RuleResultPanel({ run }: { run: SemanticRuleRunRead | null }) {
  const t = useT();
  if (!run) {
    return (
      <Card className="ruleResultPanel empty" aria-label="rule-result-empty">
        <div className="emptyState">{t("No rule run")}</div>
      </Card>
    );
  }
  const succeeded = run.status === "succeeded" || run.status === "ok";
  return (
    <Card
      className={`ruleResultPanel ${succeeded ? "succeeded" : "pending"}`}
      aria-label="rule-result-panel"
      title={
        <div className="reportPanelHeader">
          <Workflow size={15} />
          <span>{t("Rule run")}</span>
          <Tag color={succeeded ? "success" : "default"}>{run.status}</Tag>
          {run.audit_status && <Tag>{run.audit_status}</Tag>}
        </div>
      }
    >
      <RuleSummary run={run} />
      {run.warnings.length > 0 && <SemanticWarningList warnings={run.warnings} />}
      {run.error && <div className="inlineError">{run.error}</div>}
    </Card>
  );
}

function RuleSummary({ run }: { run: SemanticRuleRunRead }) {
  const t = useT();
  return (
    <dl className="reportSummary">
      <div>
        <dt>{t("Run ID")}</dt>
        <dd><code>{run.run_id}</code></dd>
      </div>
      <div>
        <dt>{t("Engine")}</dt>
        <dd>{run.engine_name}{run.engine_version ? ` · ${run.engine_version}` : ""}</dd>
      </div>
      <div>
        <dt>{t("Generated")}</dt>
        <dd>{run.generated_statement_count}</dd>
      </div>
      {run.rule_count !== null && (
        <div>
          <dt>{t("Rules")}</dt>
          <dd>{run.rule_count}</dd>
        </div>
      )}
      {run.result_graph_iri && (
        <div>
          <dt>{t("Result graph")}</dt>
          <dd><code>{run.result_graph_iri}</code></dd>
        </div>
      )}
      {run.rule_run_graph_iri && (
        <div>
          <dt>{t("Rule run graph")}</dt>
          <dd><code>{run.rule_run_graph_iri}</code></dd>
        </div>
      )}
      {run.truncated && (
        <div>
          <dt>{t("Truncated")}</dt>
          <dd>{t("Yes")}</dd>
        </div>
      )}
    </dl>
  );
}
