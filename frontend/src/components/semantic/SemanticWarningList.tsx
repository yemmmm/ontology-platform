import { Alert } from "antd";
import { AlertTriangle } from "lucide-react";
import { useT } from "../../i18n";

export type SemanticWarning = string | { kind?: string; message?: string; field?: string; [key: string]: unknown };

export function SemanticWarningList({ warnings, title }: { warnings: SemanticWarning[] | null | undefined; title?: string }) {
  const t = useT();
  if (!warnings || !warnings.length) return null;
  const normalized = warnings.map((warning) => normalizeWarning(warning));
  return (
    <div className="semanticWarningList" aria-label="semantic-warnings">
      {title && <header><AlertTriangle size={14} /> <span>{t(title)}</span></header>}
      <ul>
        {normalized.map((warning, idx) => (
          <li key={idx}>
            <Alert
              type={warning.kind === "missing_evidence" ? "error" : "warning"}
              showIcon
              message={warning.field ? `${warning.field}: ${warning.message}` : warning.message}
              description={warning.detail ?? undefined}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

function normalizeWarning(warning: SemanticWarning): {
  kind: string;
  message: string;
  field?: string;
  detail?: string;
} {
  if (typeof warning === "string") {
    return { kind: "general", message: warning };
  }
  const message = (warning.message as string) || (warning.kind as string) || JSON.stringify(warning);
  return {
    kind: (warning.kind as string) ?? "general",
    message,
    field: warning.field as string | undefined,
    detail: warning.detail as string | undefined,
  };
}
