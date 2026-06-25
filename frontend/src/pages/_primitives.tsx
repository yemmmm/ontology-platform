import { Tag } from "antd";
import type { ReactNode } from "react";

export function classNames(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export function Badge({ children }: { children: ReactNode }) {
  return <Tag color="success">{children}</Tag>;
}

export function EmptyState({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="emptyState">
      {icon}
      <span>{title}</span>
    </div>
  );
}
