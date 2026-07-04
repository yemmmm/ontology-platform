import { Card, Tag } from "antd";
import type { ReactNode } from "react";
import { useT } from "../../i18n";

export type StatusSummaryTone = "default" | "success" | "warning" | "danger" | "info";

export type StatusSummaryItem = {
  key: string;
  label: ReactNode;
  value: ReactNode;
  detail?: ReactNode;
  tone?: StatusSummaryTone;
  onClick?: () => void;
};

const tagColors: Record<StatusSummaryTone, string | undefined> = {
  default: undefined,
  success: "success",
  warning: "warning",
  danger: "error",
  info: "processing",
};

export function StatusSummary({ items, ariaLabel = "Status summary" }: {
  items: StatusSummaryItem[];
  ariaLabel?: string;
}) {
  const t = useT();
  return (
    <section className="status-summary" aria-label={t(ariaLabel)}>
      {items.map((item) => {
        const content = (
          <Card size="small" className={`status-summary__item status-summary__item--${item.tone ?? "default"}`}>
            <div className="status-summary__label">{item.label}</div>
            <div className="status-summary__value">
              <Tag color={tagColors[item.tone ?? "default"]}>{item.value}</Tag>
            </div>
            {item.detail ? <div className="status-summary__detail">{item.detail}</div> : null}
          </Card>
        );
        return item.onClick ? (
          <button className="status-summary__button" type="button" onClick={item.onClick} key={item.key}>
            {content}
          </button>
        ) : <div key={item.key}>{content}</div>;
      })}
    </section>
  );
}
