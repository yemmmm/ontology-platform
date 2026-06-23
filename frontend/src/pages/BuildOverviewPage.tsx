import { Alert, Card, Skeleton, Tag } from "antd";
import { ArrowRight, CheckCircle2, Circle, Clock3, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  BuildContext,
  OntologyVersionSummary,
  ReviewBatchSummary,
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

const labels: Record<string, string> = {
  gathering: "需求收集",
  schema_draft: "Schema 草拟",
  schema_review: "Schema 审核",
  graph_building: "图谱构建",
  graph_review: "图谱审核",
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
  onRefresh?: () => void | Promise<void>;
};

export function BuildOverviewPage({
  projectId,
  ontologyId,
  versionId,
  readOnly = false,
  request,
  onNavigate,
  onRefresh,
}: BuildOverviewPageProps) {
  const [context, setContext] = useState<BuildContext | null>(null);
  const [versions, setVersions] = useState<OntologyVersionSummary[]>([]);
  const [batches, setBatches] = useState<ReviewBatchSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextContext, nextVersions, nextBatches] = await Promise.all([
        request<BuildContext>(`/projects/${projectId}/build-context`),
        request<OntologyVersionSummary[]>(`/ontologies/${ontologyId}/versions`),
        request<ReviewBatchSummary[]>(`/ontologies/${ontologyId}/review-batches`),
      ]);
      setContext(nextContext);
      setVersions(nextVersions);
      setBatches(nextBatches);
      await onRefresh?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [ontologyId, onRefresh, projectId, request]);

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
  const activeBatches = batches
    .filter((batch) => !effectiveVersionId || batch.ontology_version_id === effectiveVersionId)
    .sort((left, right) => right.updated_at.localeCompare(left.updated_at));
  const pendingReview = activeBatches.reduce((sum, batch) => sum + (batch.counts.pending ?? 0), 0);

  const actions = useMemo(() => {
    if (!context) return [];
    const result: Array<{ label: string; detail: string; tab: string }> = [];
    if (context.project_brief.completeness < 1) {
      result.push({ label: "完善 Project Brief", detail: `${context.project_brief.missing_fields.length} 个字段待处理`, tab: "brief" });
    }
    if (totalQuestions === 0) {
      result.push({ label: "定义能力问题", detail: "用可验收的问题约束本体设计", tab: "questions" });
    } else if ((questionCounts.draft ?? 0) > 0) {
      result.push({ label: "批准能力问题", detail: `${questionCounts.draft} 个草稿待批准`, tab: "questions" });
    }
    if (pendingReview > 0) {
      result.push({ label: "继续提案审核", detail: `${pendingReview} 个项目待处理`, tab: "schema-review" });
    }
    if (stage === "validated") {
      result.push({ label: "检查发布门槛", detail: "运行确定性 readiness 检查", tab: "publication" });
    }
    return result.slice(0, 3);
  }, [context, pendingReview, questionCounts, stage, totalQuestions]);

  if (loading) return <Card className="panel"><Skeleton active paragraph={{ rows: 8 }} /></Card>;
  if (error) return <Alert type="error" showIcon message="构建概览加载失败" description={error} action={<button className="secondaryButton" onClick={() => void load()}>重试</button>} />;
  if (!context || !ontology) return <div className="emptyState">当前项目中找不到所选本体。</div>;
  if (versionId && !selectedVersion) return <Alert type="error" showIcon message="版本上下文无效" description="所选版本不属于当前本体或已不存在。请返回版本列表重新选择。" action={<button className="secondaryButton" onClick={() => onNavigate("versions")}>版本列表</button>} />;

  return (
    <div className="workspaceStack">
      <div className="pageSubHeader">
        <div><h2>构建概览</h2><p>服务端构建状态、治理队列和下一步操作。</p></div>
        <div className="rowActions">
          {(readOnly || selectedVersion?.status === "published") && <Tag color="blue">已发布 · 只读</Tag>}
          <button className="secondaryButton" onClick={() => void load()}><RefreshCw size={15} />刷新</button>
        </div>
      </div>

      <Card className="panel" title="工作流进度">
        <div className="timeline">
          {workflow.map((item, index) => (
            <div className="timelineItem" key={item}>
              <span>{index < stageIndex ? <CheckCircle2 size={16} /> : index === stageIndex ? <Clock3 size={16} /> : <Circle size={16} />}</span>
              <div><strong>{labels[item]}</strong>{index === stageIndex && <Tag color="purple">当前阶段</Tag>}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="metricGrid">
        <button className="metric" onClick={() => onNavigate("brief")}><div><CheckCircle2 size={18} /></div><strong>{Math.round(context.project_brief.completeness * 100)}%</strong><span>Brief 完整度</span></button>
        <button className="metric" onClick={() => onNavigate("questions")}><div><Circle size={18} /></div><strong>{totalQuestions}</strong><span>能力问题</span></button>
        <button className="metric" onClick={() => onNavigate("schema-review")}><div><Clock3 size={18} /></div><strong>{pendingReview}</strong><span>待审核项</span></button>
        <button className="metric" onClick={() => onNavigate("versions")}><div><CheckCircle2 size={18} /></div><strong>v{selectedVersion?.version_number ?? "—"}</strong><span>{selectedVersion?.status ?? "无版本"}</span></button>
      </div>

      <div className="pageGrid">
        <Card className="panel" title="当前版本">
          {selectedVersion ? <dl className="detailList">
            <dt>版本</dt><dd>v{selectedVersion.version_number}</dd>
            <dt>工作流状态</dt><dd><Tag>{labels[selectedVersion.workflow_status] ?? selectedVersion.workflow_status}</Tag></dd>
            <dt>父版本</dt><dd>{selectedVersion.parent_version_id ?? "首个版本"}</dd>
            <dt>创建时间</dt><dd>{new Date(selectedVersion.created_at).toLocaleString()}</dd>
            <dt>发布时间</dt><dd>{selectedVersion.published_at ? new Date(selectedVersion.published_at).toLocaleString() : "未发布"}</dd>
          </dl> : <div className="emptyState">尚未创建本体版本。</div>}
        </Card>
        <Card className="panel" title="下一步">
          {actions.length ? <div className="dataList">{actions.map((action) => <button className="dataRow" key={action.tab} onClick={() => onNavigate(action.tab)}><span className="rowContent"><strong>{action.label}</strong><span>{action.detail}</span></span><ArrowRight size={16} /></button>)}</div> : <div className="emptyState">当前没有确定性的待办操作。</div>}
        </Card>
      </div>

      <Card className="panel" title="确定性阻塞项">
        {context.project_brief.missing_fields.length === 0 && pendingReview === 0
          ? <div className="emptyState">Build Context 与审核批次当前未报告可展示的阻塞项；完整发布门槛请在 Publication 页面运行。</div>
          : <div className="dataList">
            {context.project_brief.missing_fields.length > 0 && <button className="dataRow" onClick={() => onNavigate("brief")}><span className="rowContent"><strong>Project Brief 尚不完整</strong><span>{context.project_brief.missing_fields.join("、")}</span></span><ArrowRight size={16} /></button>}
            {pendingReview > 0 && <button className="dataRow" onClick={() => onNavigate("schema-review")}><span className="rowContent"><strong>存在待审核提案</strong><span>{pendingReview} 个批次项目尚未决策</span></span><ArrowRight size={16} /></button>}
          </div>}
      </Card>

      <Card className="panel" title="最近审核批次">
        {activeBatches.length ? <div className="dataList">{activeBatches.slice(0, 6).map((batch) => <button className="dataRow" key={batch.id} onClick={() => onNavigate(batch.review_type === "schema" ? "schema-review" : "graph-review", { batch: batch.id })}><span className="rowContent"><strong>{batch.review_type}</strong><span>{batch.status} · 待处理 {batch.counts.pending ?? 0} · 更新于 {new Date(batch.updated_at).toLocaleString()}</span></span><ArrowRight size={16} /></button>)}</div> : <div className="emptyState">尚无审核批次。</div>}
      </Card>
    </div>
  );
}
