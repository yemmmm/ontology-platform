import { Alert, Button, Card, Progress } from "antd";
import { Check, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import type { ProjectBrief, WorkbenchRequest } from "./workbenchTypes";
import { ProjectBriefPage } from "./ProjectBriefPage";

type RequirementQuestionsPageProps = {
  projectId: string;
  readOnly?: boolean;
  request: WorkbenchRequest;
  onDirtyChange?: (dirty: boolean) => void;
};

export function RequirementQuestionsPage({
  projectId,
  readOnly = false,
  request,
  onDirtyChange,
}: RequirementQuestionsPageProps) {
  const t = useT();
  const [brief, setBrief] = useState<ProjectBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setBrief(await request<ProjectBrief>(`/projects/${projectId}/brief`));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [projectId, request]);

  useEffect(() => {
    void load();
  }, [load]);

  const questionCountByReason = useMemo(() => {
    return (brief?.clarification_items ?? []).reduce<Record<string, number>>((acc, item) => {
      acc[item.reason] = (acc[item.reason] ?? 0) + 1;
      return acc;
    }, {});
  }, [brief]);

  const completeness = Math.round((brief?.completeness ?? 0) * 100);
  const openQuestions = brief?.clarification_items.length ?? 0;

  return (
    <section className="questionsPage" aria-label="requirement-questions-page">
      <header className="topBar">
        <div>
          <span className="eyebrow">{t("Structured Requirements")}</span>
          <h1>{t("Structured Requirements")}</h1>
          <div className="crumbTrail">
            <span>{t("Requirement clarification")}</span>
          </div>
        </div>
        <Button icon={<RefreshCw size={15} />} loading={loading} onClick={() => void load()}>
          {t("Refresh")}
        </Button>
      </header>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}

      <div className="questionSummaryGrid">
        <div className="questionSummaryTile">
          <span>{t("Open questions")}</span>
          <strong>{openQuestions}</strong>
        </div>
        <div className="questionSummaryTile">
          <span>{t("Missing")}</span>
          <strong>{questionCountByReason.missing ?? 0}</strong>
        </div>
        <div className="questionSummaryTile">
          <span>{t("Unconfirmed")}</span>
          <strong>{questionCountByReason.unconfirmed ?? 0}</strong>
        </div>
        <div className="questionSummaryTile">
          <span>{t("Completeness")}</span>
          <strong>{brief ? `${completeness}%` : "-"}</strong>
        </div>
      </div>

      <Card title={t("Requirement clarification questions")} size="small">
        <Progress percent={completeness} status={completeness === 100 ? "success" : "active"} />
        <p className="inlineHint">
          {t("Answer the structured requirement fields below. Open questions are generated from missing or unconfirmed fields.")}
        </p>
      </Card>

      <ProjectBriefPage
        onDirtyChange={onDirtyChange}
        onRefresh={load}
        projectId={projectId}
        readOnly={readOnly}
        request={request}
      />
    </section>
  );
}

export type { RequirementQuestionsPageProps };
