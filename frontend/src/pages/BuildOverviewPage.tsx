import { Alert, Card, Skeleton, Tag } from "antd";
import { ArrowRight, CheckCircle2, Circle, Clock3, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useT } from "../i18n";
import type {
  BuildContext,
  OntologyVersionSummary,
  ProposalSummary,
  WorkbenchNavigate,
  WorkbenchRequest,
} from "./workbenchTypes";

const workflow = [
  "gathering",
  "schema_draft",
  "schema_review",
  "graph_building",
  "graph_review",
  "validated",
  "published",
];

const labelKeys: Record<string, string> = {
  gathering: "需求收集",
  schema_draft: "Schema 草拟",
  schema_review: "Schema 校验",
  graph_building: "图谱构建",
  graph_review: "图谱校验",
  validated: "验证完成",
  published: "已发布",
};

export type BuildOverviewPageProps = {
  projectId: string;
  ontologyId: string;
  versionId?: string | null;
  readOnly?: boolean;
  request: WorkbenchRequest;
  onNavigate: WorkbenchNavigate;
};

export function BuildOverviewPage({
  projectId,
  ontologyId,
  versionId,
  readOnly = false,
  request,
  onNavigate,
}: BuildOverviewPageProps) {
  const t = useT();
  const [context, setContext] = useState<BuildContext | null>(null);
  const [versions, setVersions] = useState<OntologyVersionSummary[]>([]);
  const [proposals, setProposals] = useState<ProposalSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextContext, nextVersions, nextProposals] = await Promise.all([
        request<BuildContext>(`/projects/${projectId}/build-context`),
        request<OntologyVersionSummary[]>(`/ontologies/${ontologyId}/versions`),
        request<ProposalSummary[]>(`/ontologies/${ontologyId}/proposals`),
      ]);
      setContext(nextContext);
      setVersions(nextVersions);
      setProposals(nextProposals);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [ontologyId, projectId, request]);

  useEffect(() => {
    void load();
  }, [load]);

  const ontology = context?.ontologies.find((item) => item.id === ontologyId);
  const selectedVersion = versionId
    ? versions.find((item) => item.id === versionId) ?? null
    : versions.find((item) => item.id === ontology?.current_version_id) ?? null;
  const stage = selectedVersion?.workflow_status ?? ontology?.current_version?.workflow_status ?? "gathering";
  const stageIndex = Math.max(0, workflow.indexOf(stage));
  const questionCounts = context?.competency_question_counts ?? {};
  const totalQuestions = Object.values(questionCounts).reduce((sum, count) => sum + count, 0);
  const effectiveVersionId = versionId ?? selectedVersion?.id;
  const activeProposals = proposals
    .filter((proposal) => !effectiveVersionId || proposal.target_version_id === effectiveVersionId)
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at));
  const unresolvedProposals = activeProposals.filter((proposal) => proposal.status !== "applied");

  const actions = useMemo(() => {
    if (!context) return [];
    const result: Array<{ label: string; detail: string; tab: string }> = [];
    if (context.project_brief.completeness < 1) {
      result.push({ label: t("完善 Project Brief"), detail: t("{n} 个字段待处理", { n: context.project_brief.missing_fields.length }), tab: "brief" });
    }
    if (totalQuestions === 0) {
      result.push({ label: t("定义能力问题"), detail: t("用可验收的问题约束本体设计"), tab: "questions" });
    } else if ((questionCounts.draft ?? 0) > 0) {
      result.push({ label: t("批准能力问题"), detail: t("{n} 个草稿待批准", { n: questionCounts.draft ?? 0 }), tab: "questions" });
    }
    if (unresolvedProposals.length > 0) {
      result.push({ label: t("查看未应用变更"), detail: t("{n} 个批次未应用", { n: unresolvedProposals.length }), tab: "classes" });
    }
    if (stage === "validated") {
      result.push({ label: t("检查发布门槛"), detail: t("运行确定性 readiness 检查"), tab: "publication" });
    }
    return result.slice(0, 3);
  }, [context, questionCounts, stage, t, totalQuestions, unresolvedProposals.length]);

  if (loading) return <Card className="panel"><Skeleton active paragraph={{ rows: 8 }} /></Card>;
  if (error) return <Alert type="error" showIcon message={t("构建概览加载失败")} description={error} action={<button className="secondaryButton" onClick={() => void load()}>{t("重试")}</button>} />;
  if (!context || !ontology) return <div className="emptyState">{t("当前项目中找不到所选本体。")}</div>;
  if (versionId && !selectedVersion) return <Alert type="error" showIcon message={t("版本上下文无效")} description={t("所选版本不属于当前本体或已不存在。请返回版本列表重新选择。")} action={<button className="secondaryButton" onClick={() => onNavigate("versions")}>{t("版本列表")}</button>} />;

  return (
    <div className="workspaceStack">
      <div className="pageSubHeader">
        <div><h2>{t("构建概览")}</h2><p>{t("服务端构建状态、自动变更批次和下一步操作。")}</p></div>
        <div className="rowActions">
          {(readOnly || selectedVersion?.status === "published") && <Tag color="blue">{t("已发布 · 只读")}</Tag>}
          <button className="secondaryButton" onClick={() => void load()}><RefreshCw size={15} />{t("刷新")}</button>
        </div>
      </div>

      <Card className="panel" title={t("工作流进度")}>
        <div className="timeline">
          {workflow.map((item, index) => (
            <div className="timelineItem" key={item}>
              <span>{index < stageIndex ? <CheckCircle2 size={16} /> : index === stageIndex ? <Clock3 size={16} /> : <Circle size={16} />}</span>
              <div><strong>{t(labelKeys[item])}</strong>{index === stageIndex && <Tag color="purple">{t("当前阶段")}</Tag>}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="metricGrid">
        <button className="metric" onClick={() => onNavigate("brief")}><div><CheckCircle2 size={18} /></div><strong>{Math.round(context.project_brief.completeness * 100)}%</strong><span>{t("Brief 完整度")}</span></button>
        <button className="metric" onClick={() => onNavigate("questions")}><div><Circle size={18} /></div><strong>{totalQuestions}</strong><span>{t("能力问题")}</span></button>
        <button className="metric" onClick={() => onNavigate("classes")}><div><Clock3 size={18} /></div><strong>{unresolvedProposals.length}</strong><span>{t("未应用批次")}</span></button>
        <button className="metric" onClick={() => onNavigate("versions")}><div><CheckCircle2 size={18} /></div><strong>v{selectedVersion?.version_number ?? "—"}</strong><span>{selectedVersion?.status ?? t("无版本")}</span></button>
      </div>

      <div className="pageGrid">
        <Card className="panel" title={t("当前版本")}>
          {selectedVersion ? <dl className="detailList">
            <dt>{t("版本")}</dt><dd>v{selectedVersion.version_number}</dd>
            <dt>{t("工作流状态")}</dt><dd><Tag>{t(labelKeys[selectedVersion.workflow_status] ?? selectedVersion.workflow_status)}</Tag></dd>
            <dt>{t("父版本")}</dt><dd>{selectedVersion.parent_version_id ?? t("首个版本")}</dd>
            <dt>{t("创建时间")}</dt><dd>{new Date(selectedVersion.created_at).toLocaleString()}</dd>
            <dt>{t("发布时间")}</dt><dd>{selectedVersion.published_at ? new Date(selectedVersion.published_at).toLocaleString() : t("未发布")}</dd>
          </dl> : <div className="emptyState">{t("尚未创建本体版本。")}</div>}
        </Card>
        <Card className="panel" title={t("下一步")}>
          {actions.length ? <div className="dataList">{actions.map((action) => <button className="dataRow" key={action.tab} onClick={() => onNavigate(action.tab)}><span className="rowContent"><strong>{action.label}</strong><span>{action.detail}</span></span><ArrowRight size={16} /></button>)}</div> : <div className="emptyState">{t("当前没有确定性的待办操作。")}</div>}
        </Card>
      </div>

      <Card className="panel" title={t("确定性阻塞项")}>
        {context.project_brief.missing_fields.length === 0 && unresolvedProposals.length === 0
          ? <div className="emptyState">{t("Build Context 与变更批次当前未报告可展示的阻塞项；完整发布门槛请在 Publication 页面运行。")}</div>
          : <div className="dataList">
            {context.project_brief.missing_fields.length > 0 && <button className="dataRow" onClick={() => onNavigate("brief")}><span className="rowContent"><strong>{t("Project Brief 尚不完整")}</strong><span>{context.project_brief.missing_fields.join("、")}</span></span><ArrowRight size={16} /></button>}
            {unresolvedProposals.length > 0 && <button className="dataRow" onClick={() => onNavigate("classes")}><span className="rowContent"><strong>{t("存在未应用变更批次")}</strong><span>{t("{n} 个批次需要修正后重新提交", { n: unresolvedProposals.length })}</span></span><ArrowRight size={16} /></button>}
          </div>}
      </Card>

      <Card className="panel" title={t("最近变更批次")}>
        {activeProposals.length ? <div className="dataList">{activeProposals.slice(0, 6).map((proposal) => <button className="dataRow" key={proposal.id} onClick={() => onNavigate(proposal.proposal_type === "schema_change" ? "classes" : "entities", { proposal: proposal.id })}><span className="rowContent"><strong>{proposal.proposal_type}</strong><span>{t("{status} · 更新于 {time}", { status: proposal.status, time: new Date(proposal.updated_at).toLocaleString() })}</span></span><ArrowRight size={16} /></button>)}</div> : <div className="emptyState">{t("尚无变更批次。")}</div>}
      </Card>
    </div>
  );
}
