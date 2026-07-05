import { History } from "lucide-react";
import type { SemanticEditAuditRead, SemanticJsonObject } from "../../types";
import { useT } from "../../i18n";
import { formatDate } from "../../utils";

export function ProvenanceTimeline({ audits }: { audits: SemanticEditAuditRead[] }) {
  const t = useT();
  if (!audits.length) {
    return (
      <section className="provenanceTimeline empty" aria-label="provenance-timeline-empty">
        <div className="emptyState">
          <History size={18} />
          <span>{t("No audit records yet")}</span>
        </div>
      </section>
    );
  }
  return (
    <section className="provenanceTimeline" aria-label="provenance-timeline">
      <header>
        <History size={14} />
        <span>{t("Recent semantic edit audits")}</span>
      </header>
      <ol>
        {audits.map((audit) => (
          <li key={audit.id} className="provenanceTimelineItem">
            <code>{audit.id}</code>
            <span>
              {audit.input_format}
              {audit.target_graph_iri ? ` · ${audit.target_graph_iri}` : ""}
            </span>
            <span>{audit.actor ?? t("actor unknown")}</span>
            <span>{audit.reason ?? t("reason unset")}</span>
            <span>{formatDate(audit.created_at)}</span>
            <span aria-label="audit-applied">{audit.applied ? t("applied") : t("rejected")}</span>
            {audit.evidence_status && (
              <Tag>{audit.evidence_status}</Tag>
            )}
            <pre className="jsonBlock">{prettyJson(audit.graph_delta)}</pre>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="tagChip">{children}</span>;
}

function prettyJson(value: SemanticJsonObject): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
