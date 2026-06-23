import type { ReactNode } from "react";

export type WorkbenchPageHeaderProps = {
  title: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
};

export function WorkbenchPageHeader({
  title,
  description,
  eyebrow,
  actions,
  meta,
}: WorkbenchPageHeaderProps) {
  return (
    <header className="workbench-page-header">
      <div className="workbench-page-header__content">
        {eyebrow ? <div className="workbench-page-header__eyebrow">{eyebrow}</div> : null}
        <h1>{title}</h1>
        {description ? <div className="workbench-page-header__description">{description}</div> : null}
        {meta ? <div className="workbench-page-header__meta">{meta}</div> : null}
      </div>
      {actions ? <div className="workbench-page-header__actions">{actions}</div> : null}
    </header>
  );
}
