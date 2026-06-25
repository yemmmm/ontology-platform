import { CheckCircle2, Circle, Clock3 } from "lucide-react";
import { Tag } from "antd";

export const workflowStages = [
  "gathering",
  "schema_draft",
  "schema_review",
  "graph_building",
  "graph_review",
  "validated",
  "published",
] as const;

export type WorkflowStage = (typeof workflowStages)[number];

export const workflowStageLabels: Record<WorkflowStage, string> = {
  gathering: "需求收集",
  schema_draft: "Schema 草拟",
  schema_review: "Schema 审核",
  graph_building: "图谱构建",
  graph_review: "图谱审核",
  validated: "验证完成",
  published: "已发布",
};

export type WorkflowProgressProps = {
  status: string;
  variant?: "compact" | "full";
  onStageClick?: (stage: WorkflowStage, defaultTab: string) => void;
  stageDefaultTab?: Partial<Record<WorkflowStage, string>>;
};

export function WorkflowProgress(props: WorkflowProgressProps) {
  const stageIndex = Math.max(0, workflowStages.indexOf(props.status as WorkflowStage));
  const isFull = props.variant !== "compact";

  return (
    <ol className={`workflowProgress ${isFull ? "full" : "compact"}`}>
      {workflowStages.map((stage, index) => {
        const Icon = index < stageIndex ? CheckCircle2 : index === stageIndex ? Clock3 : Circle;
        const isCurrent = index === stageIndex;
        const isComplete = index < stageIndex;
        const clickable = Boolean(props.onStageClick && props.stageDefaultTab?.[stage]);
        const handle = () => {
          if (!clickable || !props.onStageClick || !props.stageDefaultTab?.[stage]) return;
          props.onStageClick(stage as WorkflowStage, props.stageDefaultTab[stage] as string);
        };
        return (
          <li key={stage}>
            <button
              className={`workflowProgressItem ${isCurrent ? "current" : ""} ${isComplete ? "complete" : ""}`}
              disabled={!clickable}
              onClick={handle}
              type="button"
            >
              <span className="workflowProgressBadge">
                <Icon size={isFull ? 16 : 13} />
              </span>
              <span className="workflowProgressMeta">
                <strong>{workflowStageLabels[stage]}</strong>
                {isCurrent && isFull && <Tag color="purple">当前阶段</Tag>}
              </span>
            </button>
            {index < workflowStages.length - 1 && <span className="workflowProgressConnector" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}
