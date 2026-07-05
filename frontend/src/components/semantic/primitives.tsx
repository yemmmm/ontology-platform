import { Card, Tag, Tooltip } from "antd";
import { Loader2, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { useT } from "../../i18n";

export function SemanticPanel({
  title,
  icon,
  children,
  className,
  actions,
}: {
  title: string;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
}) {
  return (
    <Card
      className={`semanticPanel ${className ?? ""}`}
      title={
        <div className="semanticPanelHeader">
          {icon}
          <h2>{title}</h2>
        </div>
      }
      extra={actions}
      variant="borderless"
    >
      {children}
    </Card>
  );
}

export function SemanticEmpty({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="semanticEmpty">
      {icon ?? null}
      <span>{title}</span>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function RefreshButton({
  busy,
  onClick,
  label,
}: {
  busy: boolean;
  onClick: () => void;
  label?: string;
}) {
  const t = useT();
  const text = label ?? t("Refresh");
  return (
    <Tooltip title={text}>
      <button className="iconButton" disabled={busy} onClick={onClick} type="button" aria-label={text}>
        {busy ? <Loader2 className="spin" size={14} /> : <RefreshCw size={14} />}
        <span>{text}</span>
      </button>
    </Tooltip>
  );
}

export function StatTile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: "ok" | "warning" | "error";
}) {
  return (
    <div className={`statTile ${tone ?? ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function SemanticTag({ children, tone }: { children: ReactNode; tone?: "ok" | "warning" | "error" }) {
  const color = tone === "ok" ? "success" : tone === "error" ? "error" : tone === "warning" ? "warning" : "default";
  return <Tag color={color}>{children}</Tag>;
}
