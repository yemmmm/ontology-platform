import { Card, Tag } from "antd";
import { CheckCircle2, XCircle, Network } from "lucide-react";
import type { SemanticReasoningRunRead } from "../../types";
import { useT } from "../../i18n";
import { SemanticWarningList } from "./SemanticWarningList";

export function ReasoningResultPanel({ run }: { run: SemanticReasoningRunRead | null }) {
  const t = useT();
  if (!run) {
    return (
      <Card className="reasoningResultPanel empty" aria-label="reasoning-result-empty">
        <div className="emptyState">{t("No reasoning run")}</div>
      </Card>
    );
  }
  const consistent = run.consistent === true;
  const inconsistent = run.consistent === false;
  const entailmentCount = Array.isArray(run.entailments) ? run.entailments.length : 0;
  return (
    <Card
      className={`reasoningResultPanel ${consistent ? "consistent" : inconsistent ? "failed" : "pending"}`}
      aria-label="reasoning-result-panel"
      title={
        <div className="reportPanelHeader">
          <Network size={15} />
          <span>{t("OWL reasoning")}</span>
          {consistent ? (
            <Tag color="success" icon={<CheckCircle2 size={12} />}>
              {t("Consistent")}
            </Tag>
          ) : inconsistent ? (
            <Tag color="error" icon={<XCircle size={12} />}>
              {t("Inconsistent")}
            </Tag>
          ) : (
            <Tag color="default">{run.status}</Tag>
          )}
        </div>
      }
    >
      <ReasoningSummary run={run} entailmentCount={entailmentCount} />
      {run.warnings.length > 0 && <SemanticWarningList warnings={run.warnings} />}
      {run.error && <div className="inlineError">{run.error}</div>}
    </Card>
  );
}

function ReasoningSummary({ run, entailmentCount }: { run: SemanticReasoningRunRead; entailmentCount: number }) {
  const t = useT();
  const classification = run.classification as Record<string, unknown>;
  const classifiedCount = pickNumber(classification, ["classified_classes", "classified", "class_count"]);
  return (
    <dl className="reportSummary">
      <div>
        <dt>{t("Run ID")}</dt>
        <dd><code>{run.run_id}</code></dd>
      </div>
      {run.profile && (
        <div>
          <dt>{t("Profile")}</dt>
          <dd>{run.profile}</dd>
        </div>
      )}
      {run.engine_version && (
        <div>
          <dt>{t("Engine version")}</dt>
          <dd><code>{run.engine_version}</code></dd>
        </div>
      )}
      {run.tasks.length > 0 && (
        <div>
          <dt>{t("Tasks")}</dt>
          <dd>{run.tasks.join(", ")}</dd>
        </div>
      )}
      <div>
        <dt>{t("Entailments")}</dt>
        <dd>{entailmentCount}</dd>
      </div>
      {classifiedCount !== null && (
        <div>
          <dt>{t("Classified classes")}</dt>
          <dd>{classifiedCount}</dd>
        </div>
      )}
      {run.result_graph_iri && (
        <div>
          <dt>{t("Result graph")}</dt>
          <dd><code>{run.result_graph_iri}</code></dd>
        </div>
      )}
    </dl>
  );
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
