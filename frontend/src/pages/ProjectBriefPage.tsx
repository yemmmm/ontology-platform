import { Alert, Card, Progress, Skeleton, Tag } from "antd";
import { Check, RotateCcw, Save, SkipForward } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ProjectBrief, WorkbenchRequest } from "./workbenchTypes";

const fieldConfig = [
  ["domain_name", "领域名称", "领域目标"],
  ["business_goal", "业务目标", "领域目标"],
  ["scope", "范围及明确排除项", "范围"],
  ["core_concepts", "核心概念、事件和参与者", "核心概念"],
  ["identity_rules", "关键身份规则和生命周期", "身份规则"],
  ["expected_granularity", "期望粒度", "粒度"],
  ["data_sources", "数据来源及可信度优先级", "来源"],
  ["boundaries", "时间、地域和版本边界", "边界"],
  ["terminology", "行业术语、别名和语言", "术语"],
  ["inference_scope", "允许的推理范围", "推理范围"],
] as const;

const requiredFields = new Set(["domain_name", "business_goal", "scope", "core_concepts", "identity_rules", "expected_granularity"]);

function textValue(value: unknown): string {
  if (value === undefined || value === null) return "";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function editedValue(text: string, original: unknown): unknown {
  if (typeof original === "object" && original !== null) {
    try {
      return JSON.parse(text) as unknown;
    } catch {
      return text;
    }
  }
  return text;
}

export type ProjectBriefPageProps = {
  projectId: string;
  readOnly?: boolean;
  request: WorkbenchRequest;
  onRefresh?: () => void | Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
};

export function ProjectBriefPage({ projectId, readOnly = false, request, onRefresh, onDirtyChange }: ProjectBriefPageProps) {
  const [brief, setBrief] = useState<ProjectBrief | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const resetDraft = useCallback((value: ProjectBrief) => {
    setDraft(Object.fromEntries(fieldConfig.map(([key]) => [key, textValue(value.fields[key])])));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await request<ProjectBrief>(`/projects/${projectId}/brief`);
      setBrief(result);
      resetDraft(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [projectId, request, resetDraft]);

  useEffect(() => { void load(); }, [load]);

  const dirty = useMemo(() => brief !== null && fieldConfig.some(([key]) => draft[key] !== textValue(brief.fields[key])), [brief, draft]);
  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);

  const mutate = async (confirmedFields: string[] = [], skippedFields: string[] = []) => {
    if (!brief || readOnly) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const fields = Object.fromEntries(fieldConfig.flatMap(([key]) => {
        if (skippedFields.includes(key)) return [];
        if (draft[key] === textValue(brief.fields[key])) return [];
        const text = draft[key]?.trim() ?? "";
        return [[key, editedValue(text, brief.fields[key])]];
      }));
      const next = await request<ProjectBrief>(`/projects/${projectId}/brief`, {
        method: "PATCH",
        body: JSON.stringify({ fields, confirmed_fields: confirmedFields, skipped_fields: skippedFields, source_answer_ids: {} }),
      });
      setBrief(next);
      resetDraft(next);
      setSuccess(skippedFields.length ? "字段已跳过。" : confirmedFields.length ? "字段已确认。" : "Brief 草稿已保存。引用该字段的已验证能力问题可能被标记为过期。");
      await onRefresh?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Card className="panel"><Skeleton active paragraph={{ rows: 10 }} /></Card>;
  if (!brief) return <Alert type="error" showIcon message="Project Brief 加载失败" description={error} action={<button className="secondaryButton" onClick={() => void load()}>重试</button>} />;

  const known = new Set(fieldConfig.map(([key]) => key));
  const extensions = Object.entries(brief.fields).filter(([key]) => !known.has(key as typeof fieldConfig[number][0]));

  return (
    <div className="workspaceStack">
      <div className="pageSubHeader">
        <div><h2>Project Brief</h2><p>维护领域边界和质量约束；确认后的字段可作为能力问题来源。</p></div>
        {readOnly && <Tag color="blue">已发布 · 只读</Tag>}
      </div>
      {error && <Alert type="error" showIcon closable onClose={() => setError(null)} message="操作失败" description={error} />}
      {success && <Alert type="success" showIcon closable onClose={() => setSuccess(null)} message={success} />}

      <div className="pageGrid">
        <Card className="panel wide" title="结构化需求">
          <div className="stackForm" style={{ maxWidth: "none" }}>
            {fieldConfig.map(([key, label, group]) => {
              const state = brief.field_states[key] ?? (brief.missing_fields.includes(key) ? "missing" : "answered");
              return <label key={key}>
                <span>{group} · {label} {requiredFields.has(key) && <Tag color="red">必填</Tag>} <Tag>{state}</Tag> <small className="muted">来源 {brief.field_sources[key]?.length ?? 0}</small></span>
                <textarea rows={key === "core_concepts" || key === "scope" ? 4 : 3} value={draft[key] ?? ""} disabled={readOnly || saving} onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))} />
                {!readOnly && <span className="rowActions">
                  <button className="secondaryButton" disabled={saving || !draft[key]?.trim()} onClick={() => void mutate([key])}><Check size={14} />确认字段</button>
                  {!requiredFields.has(key) && <button className="secondaryButton" disabled={saving} onClick={() => void mutate([], [key])}><SkipForward size={14} />跳过</button>}
                </span>}
              </label>;
            })}
          </div>
          {!readOnly && <div className="buttonRow" style={{ marginTop: 16 }}>
            <button className="primaryButton" disabled={saving || !dirty} onClick={() => void mutate()}><Save size={15} />{saving ? "保存中" : "保存草稿"}</button>
            <button className="secondaryButton" disabled={saving || !dirty} onClick={() => resetDraft(brief)}><RotateCcw size={15} />撤销修改</button>
          </div>}
        </Card>

        <div className="workspaceStack">
          <Card className="panel" title="完整度">
            <Progress percent={Math.round(brief.completeness * 100)} status={brief.completeness === 1 ? "success" : "active"} />
            <p className="muted">缺失 {brief.missing_fields.length} 个字段，未保存修改{dirty ? "存在" : "不存在"}。</p>
          </Card>
          <Card className="panel" title="待澄清">
            {brief.clarification_items.length ? <div className="dataList">{brief.clarification_items.map((item) => <div className="callout quiet" key={`${item.field}-${item.reason}`}><strong>{item.field}</strong><span>{item.question}</span><span>{item.reason}</span></div>)}</div> : <div className="emptyState">没有待澄清项。</div>}
          </Card>
          {extensions.length > 0 && <Card className="panel" title="扩展字段（只读）"><div className="dataList">{extensions.map(([key, value]) => <div className="callout quiet" key={key}><strong>{key}</strong><pre className="jsonBlock">{textValue(value)}</pre></div>)}</div></Card>}
        </div>
      </div>
    </div>
  );
}
