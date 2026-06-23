import { Button, Empty } from "antd";
import type { ReactNode } from "react";

export function EmptyState({ title, description, actionLabel, onAction, icon }: {
  title: ReactNode;
  description?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  icon?: ReactNode;
}) {
  return (
    <Empty image={icon ?? Empty.PRESENTED_IMAGE_SIMPLE} description={(
      <div className="empty-state__copy">
        <strong>{title}</strong>
        {description ? <div>{description}</div> : null}
      </div>
    )}>
      {actionLabel && onAction ? <Button onClick={onAction}>{actionLabel}</Button> : null}
    </Empty>
  );
}
