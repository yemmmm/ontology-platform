import { Card, Tag } from "antd";
import { CheckCircle2, XCircle, ShieldCheck } from "lucide-react";
import type { SemanticValidationRunRead } from "../../types";
import { useT } from "../../i18n";
import { SemanticWarningList } from "./SemanticWarningList";

export function ValidationReportPanel({ run }: { run: SemanticValidationRunRead | null }) {
  const t = useT();
  if (!run) {
    return (
      <Card className="validationReportPanel empty" aria-label="validation-report-empty">
        <div className="emptyState">{t("No validation run")}</div>
      </Card>
    );
  }
  const conforms = run.conforms === true;
  const failed = run.conforms === false;
  return (
    <Card
      className={`validationReportPanel ${conforms ? "conforms" : failed ? "failed" : "pending"}`}
      aria-label="validation-report-panel"
      title={
        <div className="reportPanelHeader">
          <ShieldCheck size={15} />
          <span>{t("SHACL validation")}</span>
          {conforms ? (
            <Tag color="success" icon={<CheckCircle2 size={12} />}>
              {t("Conforms")}
            </Tag>
          ) : failed ? (
            <Tag color="error" icon={<XCircle size={12} />}>
              {t("Failed")}
            </Tag>
          ) : (
            <Tag color="default">{run.status}</Tag>
          )}
        </div>
      }
    >
      <ValidationSummary run={run} />
      {run.warnings.length > 0 && <SemanticWarningList warnings={run.warnings} />}
      {run.error && <div className="inlineError">{run.error}</div>}
    </Card>
  );
}

function ValidationSummary({ run }: { run: SemanticValidationRunRead }) {
  const t = useT();
  const summary = run.summary as Record<string, unknown>;
  const violationCount = pickNumber(summary, ["violation_count", "violations", "errors"]);
  const resultCount = pickNumber(summary, ["result_count", "results"]);
  const focusNodes = pickArray(summary, ["focus_nodes", "focus_node_count"]);
  return (
    <dl className="reportSummary">
      <div>
        <dt>{t("Run ID")}</dt>
        <dd><code>{run.run_id}</code></dd>
      </div>
      {run.shape_version && (
        <div>
          <dt>{t("Shape version")}</dt>
          <dd><code>{run.shape_version}</code></dd>
        </div>
      )}
      {run.engine_version && (
        <div>
          <dt>{t("Engine version")}</dt>
          <dd><code>{run.engine_version}</code></dd>
        </div>
      )}
      <div>
        <dt>{t("Scope")}</dt>
        <dd>{run.validation_scope}</dd>
      </div>
      {violationCount !== null && (
        <div>
          <dt>{t("Violations")}</dt>
          <dd>{violationCount}</dd>
        </div>
      )}
      {resultCount !== null && (
        <div>
          <dt>{t("Result count")}</dt>
          <dd>{resultCount}</dd>
        </div>
      )}
      {focusNodes && focusNodes.length > 0 && (
        <div>
          <dt>{t("Focus nodes")}</dt>
          <dd>{focusNodes.length}</dd>
        </div>
      )}
      {run.report_graph_iri && (
        <div>
          <dt>{t("Report graph")}</dt>
          <dd><code>{run.report_graph_iri}</code></dd>
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

function pickArray(record: Record<string, unknown>, keys: string[]): unknown[] | null {
  for (const key of keys) {
    if (key in record) {
      const value = record[key];
      if (Array.isArray(value)) return value;
      if (typeof value === "number") return [];
    }
  }
  return null;
}
