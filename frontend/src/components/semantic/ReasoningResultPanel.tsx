import { Alert, Card, Tag } from "antd";
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
  const declaredMode = run.implementation_mode ?? (typeof run.classification.mode === "string" ? run.classification.mode : null);
  const stub = declaredMode === "development_stub";
  const consistent = run.consistent === true && !stub && declaredMode !== null;
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
      <Alert type={stub?"warning":"info"} message={`实际推理实现：${declaredMode??"未知／未声明"}`} description={stub?"development_stub 未执行真实 OWL DL 推理；不能据此声称 DL 验收通过。":"实现模式与结果适用范围以引擎声明为准；局部一致性结果不代表全模型验收。"}/>
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
      <div><dt>引擎名称</dt><dd>{run.engine_name??"未知／未声明"}</dd></div>
      <div><dt>一致性原始结果</dt><dd>{run.consistent===null?"未知":String(run.consistent)}</dd></div>
      <div><dt>源版本与有效性</dt><dd><code>{run.source_signature}</code> · {run.derived_pointer?.stale===true||run.derived_pointer?.status==="stale"?"已过期":run.derived_pointer?.status==="current"?"指针声明 current":"有效性未知／未记录"}</dd></div>
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
