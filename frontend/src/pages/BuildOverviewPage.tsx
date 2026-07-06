import { Alert, Card, Skeleton, Tag } from "antd";
import { ArrowRight, CheckCircle2, Circle, Network, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useT } from "../i18n";
import type {
  BuildOverviewResponse,
  GraphSetMemberStaleness,
  WorkbenchNavigate,
  WorkbenchRequest,
} from "./workbenchTypes";

export type BuildOverviewPageProps = {
  projectId: string;
  ontologyId: string;
  versionId?: string | null;
  readOnly?: boolean;
  request: WorkbenchRequest;
  onNavigate: WorkbenchNavigate;
};

function StalenessTag({ value }: { value: boolean | null }) {
  const t = useT();
  if (value === null) return <Tag>{t("未知")}</Tag>;
  return value ? <Tag color="orange">{t("已过期")}</Tag> : <Tag color="green">{t("最新")}</Tag>;
}

export function BuildOverviewPage({
  projectId,
  ontologyId,
  readOnly = false,
  request,
  onNavigate,
}: BuildOverviewPageProps) {
  const t = useT();
  const [data, setData] = useState<BuildOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await request<BuildOverviewResponse>(
        `/ontologies/${ontologyId}/build-overview?project_id=${encodeURIComponent(projectId)}`,
      );
      setData(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [ontologyId, projectId, request]);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <Card className="panel"><Skeleton active paragraph={{ rows: 8 }} /></Card>;
  if (error) return <Alert type="error" showIcon message={t("构建概览加载失败")} description={error}
    action={<button className="secondaryButton" onClick={() => void load()}>{t("重试")}</button>} />;
  if (!data) return <Alert type="warning" showIcon
    message={t("当前本体还没有活跃的 graph-set。请先到 Governance 页面创建。")}
    action={<button className="secondaryButton" onClick={() => onNavigate("graph-governance")}>{t("前往 Governance")}</button>} />;

  const hasStaleReasoning = data.graph_set.members.some((m) => m.reasoning_stale);
  const hasStaleRule = data.graph_set.members.some((m) => m.rule_stale);
  const hasStaleValidation = data.graph_set.members.some((m) => m.validation_stale);

  return (
    <div className="workspaceStack">
      <div className="pageSubHeader">
        <div>
          <h2>{t("构建概览")}</h2>
          <p>{t("基于活跃 graph-set 的状态、派生结果新鲜度与下一步操作。")}</p>
        </div>
        <div className="rowActions">
          {readOnly && <Tag color="blue">{t("只读")}</Tag>}
          <button className="secondaryButton" onClick={() => void load()}><RefreshCw size={15} />{t("刷新")}</button>
        </div>
      </div>

      <div className="metricGrid">
        <button className="metric" onClick={() => onNavigate("brief")}>
          <div><CheckCircle2 size={18} /></div>
          <strong>{Math.round(data.project_brief.completeness * 100)}%</strong>
          <span>{t("Brief 完整度")}</span>
        </button>
        <button className="metric" onClick={() => onNavigate("questions")}>
          <div><Circle size={18} /></div>
          <strong>{data.competency_questions.total}</strong>
          <span>{t("能力问题")}</span>
        </button>
        <button className="metric" onClick={() => onNavigate("evidence")}>
          <div><Network size={18} /></div>
          <strong>{data.graph_set.missing_evidence_count}</strong>
          <span>{t("Missing evidence")}</span>
        </button>
      </div>

      <Card className="panel" title={t("活跃 Graph Set 状态")}>
        {data.graph_set.members.length ? (
          <div className="dataList">
            {data.graph_set.members.map((m: GraphSetMemberStaleness) => (
              <div className="dataRow" key={m.iri}>
                <span className="rowContent">
                  <strong>{m.role}</strong>
                  <span style={{ fontSize: 12, color: "#888", wordBreak: "break-all" }}>{m.iri}</span>
                  <span style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                    <Tag>{m.editable ? t("可编辑") : t("已锁定")}</Tag>
                    <span>V: <StalenessTag value={m.validation_stale} /></span>
                    <span>R: <StalenessTag value={m.reasoning_stale} /></span>
                    <span>Rule: <StalenessTag value={m.rule_stale} /></span>
                  </span>
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="emptyState">{t("暂无成员图。")}</div>
        )}
      </Card>

      <div className="pageGrid">
        <Card className="panel" title={t("派生结果新鲜度")}>
          <div style={{ display: "flex", justifyContent: "space-around" }}>
            <div style={{ textAlign: "center" }}>
              <strong>{t("Validation")}</strong>
              <div style={{ marginTop: 8 }}><StalenessTag value={hasStaleValidation ? true : false} /></div>
            </div>
            <div style={{ textAlign: "center" }}>
              <strong>{t("Reasoning")}</strong>
              <div style={{ marginTop: 8 }}><StalenessTag value={hasStaleReasoning ? true : false} /></div>
            </div>
            <div style={{ textAlign: "center" }}>
              <strong>{t("Rule")}</strong>
              <div style={{ marginTop: 8 }}><StalenessTag value={hasStaleRule ? true : false} /></div>
            </div>
          </div>
          {(hasStaleValidation || hasStaleReasoning || hasStaleRule) && (
            <button className="secondaryButton" style={{ marginTop: 16, width: "100%" }}
              onClick={() => onNavigate("graph-governance")}>{t("前往 Governance 重新运行")}</button>
          )}
        </Card>

        <Card className="panel" title={t("下一步")}>
          {data.next_actions.length ? (
            <div className="dataList">
              {data.next_actions.map((action) => (
                <button className="dataRow" key={action.key} onClick={() => onNavigate(action.tab)}>
                  <span className="rowContent"><strong>{action.label}</strong><span>{action.detail}</span></span>
                  <ArrowRight size={16} />
                </button>
              ))}
            </div>
          ) : (
            <div className="emptyState">{t("当前没有确定性的待办操作。")}</div>
          )}
        </Card>
      </div>
    </div>
  );
}
