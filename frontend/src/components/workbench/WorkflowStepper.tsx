import { Steps } from "antd";
import type { WorkflowStatus } from "../../types";
import { useT } from "../../i18n";

export const workflowSteps: Array<{ status: WorkflowStatus; title: string }> = [
  { status: "gathering", title: "Gathering" },
  { status: "schema_draft", title: "Schema draft" },
  { status: "schema_review", title: "Schema review" },
  { status: "graph_building", title: "Graph building" },
  { status: "graph_review", title: "Graph review" },
  { status: "validated", title: "Validated" },
  { status: "published", title: "Published" },
];

export function WorkflowStepper({ current, compact = false }: {
  current: WorkflowStatus;
  compact?: boolean;
}) {
  const t = useT();
  const currentIndex = workflowSteps.findIndex((step) => step.status === current);
  return (
    <Steps
      aria-label={t("Ontology build workflow")}
      current={Math.max(currentIndex, 0)}
      direction={compact ? "vertical" : "horizontal"}
      responsive
      size="small"
      status={currentIndex < 0 ? "error" : "process"}
      items={workflowSteps.map((step) => ({ title: t(step.title) }))}
    />
  );
}
