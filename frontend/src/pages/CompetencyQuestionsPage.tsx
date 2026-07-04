import { Alert, Card, Modal, Select, Skeleton, Tag } from "antd";
import { ArrowDown, ArrowUp, Check, Edit3, Play, Plus, Power, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useT } from "../i18n";
import type { CompetencyQuestion, WorkbenchRequest } from "./workbenchTypes";

const briefFields = ["domain_name", "business_goal", "scope", "core_concepts", "identity_rules", "expected_granularity", "data_sources", "boundaries", "terminology", "inference_scope"];

function parseObject(text: string): Record<string, unknown> {
  if (!text.trim()) return {};
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Query definition 必须是 JSON 对象。");
  return value as Record<string, unknown>;
}

type EditorState = {
  question: string;
  importance: number;
  queryDefinition: string;
  sourceBriefFields: string[];
};

const emptyEditor: EditorState = { question: "", importance: 3, queryDefinition: "{}", sourceBriefFields: [] };

export type CompetencyQuestionsPageProps = {
  projectId: string;
  ontologyId: string;
  versionId?: string | null;
  readOnly?: boolean;
  request: WorkbenchRequest;
  onRefresh?: () => void | Promise<void>;
};

export function CompetencyQuestionsPage({ projectId, ontologyId, readOnly = false, request, onRefresh }: CompetencyQuestionsPageProps) {
  const t = useT();
  const [questions, setQuestions] = useState<CompetencyQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [activityFilter, setActivityFilter] = useState("active");
  const [editing, setEditing] = useState<CompetencyQuestion | "new" | null>(null);
  const [editor, setEditor] = useState<EditorState>(emptyEditor);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await request<CompetencyQuestion[]>(`/projects/${projectId}/competency-questions?include_inactive=true`);
      setQuestions(result.sort((left, right) => left.position - right.position));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [projectId, request]);

  useEffect(() => { void load(); }, [load]);

  const filtered = useMemo(() => questions.filter((item) =>
    (statusFilter === "all" || item.status === statusFilter) &&
    (activityFilter === "all" || (activityFilter === "active" ? item.active : !item.active))), [activityFilter, questions, statusFilter]);

  const run = async (id: string, action: () => Promise<CompetencyQuestion>, message: string) => {
    setBusyId(id);
    setError(null);
    setSuccess(null);
    try {
      const next = await action();
      setQuestions((current) => current.map((item) => item.id === next.id ? next : item).sort((left, right) => left.position - right.position));
      setSuccess(message);
      await onRefresh?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusyId(null);
    }
  };

  const openEditor = (question: CompetencyQuestion | "new") => {
    setEditing(question);
    setEditor(question === "new" ? emptyEditor : {
      question: question.question,
      importance: question.importance,
      queryDefinition: JSON.stringify(question.query_definition, null, 2),
      sourceBriefFields: question.source_brief_fields,
    });
  };

  const saveEditor = async () => {
    if (!editing || !editor.question.trim()) return;
    let queryDefinition: Record<string, unknown>;
    try { queryDefinition = parseObject(editor.queryDefinition); } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      return;
    }
    const id = editing === "new" ? "new" : editing.id;
    await run(id, async () => {
      if (editing === "new") {
        return request<CompetencyQuestion>(`/projects/${projectId}/competency-questions`, {
          method: "POST",
          body: JSON.stringify({ ontology_id: ontologyId, question: editor.question.trim(), importance: editor.importance, query_definition: queryDefinition, source_answer_ids: [], source_brief_fields: editor.sourceBriefFields }),
        });
      }
      return request<CompetencyQuestion>(`/competency-questions/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify({ question: editor.question.trim(), importance: editor.importance, query_definition: queryDefinition, source_brief_fields: editor.sourceBriefFields }),
      });
    }, editing === "new" ? t("能力问题已创建。") : t("能力问题已更新，已有验证结果可能已过期。"));
    setEditing(null);
  };

  const transition = (question: CompetencyQuestion, status: string) => run(question.id, () => request<CompetencyQuestion>(`/competency-questions/${question.id}/status`, { method: "POST", body: JSON.stringify({ status, validation_result: {} }) }), t("状态已更新为 {status}。", { status }));
  const toggleActive = (question: CompetencyQuestion) => run(question.id, () => request<CompetencyQuestion>(`/competency-questions/${question.id}`, { method: "PATCH", body: JSON.stringify({ active: !question.active }) }), question.active ? t("能力问题已停用。") : t("能力问题已重新启用。"));
  const validate = (question: CompetencyQuestion) => run(question.id, () => request<CompetencyQuestion>(`/competency-questions/${question.id}/validate`, { method: "POST" }), t("验证已完成。"));

  const move = async (question: CompetencyQuestion, offset: -1 | 1) => {
    const ordered = [...questions].sort((left, right) => left.position - right.position);
    const index = ordered.findIndex((item) => item.id === question.id);
    const other = ordered[index + offset];
    if (!other) return;
    setBusyId(question.id);
    setError(null);
    try {
      const [moved, swapped] = await Promise.all([
        request<CompetencyQuestion>(`/competency-questions/${question.id}`, { method: "PATCH", body: JSON.stringify({ position: other.position }) }),
        request<CompetencyQuestion>(`/competency-questions/${other.id}`, { method: "PATCH", body: JSON.stringify({ position: question.position }) }),
      ]);
      setQuestions((current) => current.map((item) => item.id === moved.id ? moved : item.id === swapped.id ? swapped : item).sort((left, right) => left.position - right.position));
      setSuccess(t("排序已更新。"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      await load();
    } finally { setBusyId(null); }
  };

  if (loading) return <Card className="panel"><Skeleton active paragraph={{ rows: 9 }} /></Card>;

  return <div className="workspaceStack">
    <div className="pageSubHeader">
      <div><h2>{t("Competency Questions")}</h2><p>{t("问题的状态转换和验证均由治理 API 执行。")}</p></div>
      <div className="rowActions">{readOnly && <Tag color="blue">{t("已发布 · 只读")}</Tag>}<button className="secondaryButton" onClick={() => void load()}><RefreshCw size={15} />{t("刷新")}</button><button className="primaryButton" disabled={readOnly} onClick={() => openEditor("new")}><Plus size={15} />{t("新增问题")}</button></div>
    </div>
    {error && <Alert type="error" showIcon closable onClose={() => setError(null)} message={t("操作失败")} description={error} />}
    {success && <Alert type="success" showIcon closable onClose={() => setSuccess(null)} message={success} />}
    <Card className="panel">
      <div className="rowActions">
        <Select value={statusFilter} onChange={setStatusFilter} options={["all", "draft", "approved", "testable", "passed", "failed"].map((value) => ({ value, label: value === "all" ? t("全部状态") : value }))} />
        <Select value={activityFilter} onChange={setActivityFilter} options={[{ value: "active", label: t("启用") }, { value: "inactive", label: t("停用") }, { value: "all", label: t("全部") }]} />
      </div>
      {filtered.length ? <div className="dataList">{filtered.map((question, index) => {
        const stale = question.validation_result.stale === true;
        return <div className="dataRow" key={question.id}>
          <span className="rowContent"><strong>{question.question}</strong><span>{t("重要度 {n}/5 · 顺序 {pos} · ", { n: question.importance, pos: question.position })}<Tag>{question.status}</Tag>{!question.active && <Tag>inactive</Tag>}{stale && <Tag color="orange">{t("验证已过期")}</Tag>}</span>{Object.keys(question.validation_result).length > 0 && <details><summary>{t("验证详情")}</summary><pre className="jsonBlock">{JSON.stringify(question.validation_result, null, 2)}</pre></details>}</span>
          <span className="rowActions">
            <button className="iconButton" aria-label={t("上移")} disabled={readOnly || busyId !== null || index === 0} onClick={() => void move(question, -1)}><ArrowUp size={15} /></button>
            <button className="iconButton" aria-label={t("下移")} disabled={readOnly || busyId !== null || index === filtered.length - 1} onClick={() => void move(question, 1)}><ArrowDown size={15} /></button>
            <button className="iconButton" aria-label={t("编辑")} disabled={readOnly || busyId !== null} onClick={() => openEditor(question)}><Edit3 size={15} /></button>
            {question.status === "draft" && <button className="secondaryButton" disabled={readOnly || busyId !== null || !question.active} onClick={() => void transition(question, "approved")}><Check size={15} />{t("批准")}</button>}
            {question.status === "approved" && <button className="secondaryButton" disabled={readOnly || busyId !== null || !question.active || Object.keys(question.query_definition).length === 0} onClick={() => void transition(question, "testable")}><Play size={15} />{t("可测试")}</button>}
            {question.status === "testable" && <button className="primaryButton" disabled={readOnly || busyId !== null || !question.active} onClick={() => void validate(question)}><Play size={15} />{t("执行验证")}</button>}
            <button className="iconButton" aria-label={question.active ? t("停用") : t("启用")} disabled={readOnly || busyId !== null} onClick={() => void toggleActive(question)}><Power size={15} /></button>
          </span>
        </div>;
      })}</div> : <div className="emptyState">{t("当前筛选条件下没有能力问题。")}</div>}
    </Card>

    <Modal title={editing === "new" ? t("新增能力问题") : t("编辑能力问题")} open={editing !== null} onCancel={() => setEditing(null)} onOk={() => void saveEditor()} okText={t("保存")} confirmLoading={busyId === "new" || (editing !== null && editing !== "new" && busyId === editing.id)} okButtonProps={{ disabled: readOnly || !editor.question.trim() }}>
      <div className="stackForm">
        <label><span>{t("自然语言问题")}</span><textarea className="questionBox" value={editor.question} onChange={(event) => setEditor((current) => ({ ...current, question: event.target.value }))} /></label>
        <label><span>{t("重要度（1–5）")}</span><input type="number" min={1} max={5} value={editor.importance} onChange={(event) => setEditor((current) => ({ ...current, importance: Number(event.target.value) }))} /></label>
        <label><span>{t("Query definition（JSON）")}</span><textarea className="codeArea" value={editor.queryDefinition} onChange={(event) => setEditor((current) => ({ ...current, queryDefinition: event.target.value }))} /></label>
        <label><span>{t("来源 Brief 字段（批准前至少选择一个已确认字段，或由 API 关联访谈答案）")}</span><Select mode="multiple" style={{ width: "100%" }} value={editor.sourceBriefFields} onChange={(value: string[]) => setEditor((current) => ({ ...current, sourceBriefFields: value }))} options={briefFields.map((value) => ({ value, label: value }))} /></label>
      </div>
    </Modal>
  </div>;
}
