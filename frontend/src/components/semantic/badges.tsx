import { Tag, Tooltip } from "antd";
import { Clipboard } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { useT } from "../../i18n";

export type AssertionKind =
  | "asserted"
  | "owl_inferred"
  | "rule_derived"
  | "imported"
  | "review_metadata"
  | "policy_metadata"
  | "missing_evidence";

const ASSERTION_KIND_META: Record<AssertionKind, { color: string; label: string; zh: string }> = {
  asserted: { color: "blue", label: "Asserted", zh: "已断言" },
  owl_inferred: { color: "purple", label: "OWL inferred", zh: "OWL 推理" },
  rule_derived: { color: "magenta", label: "Rule derived", zh: "规则派生" },
  imported: { color: "cyan", label: "Imported", zh: "外部导入" },
  review_metadata: { color: "gold", label: "Review metadata", zh: "评审元数据" },
  policy_metadata: { color: "volcano", label: "Policy metadata", zh: "策略元数据" },
  missing_evidence: { color: "red", label: "Missing evidence", zh: "证据缺失" },
};

export function normalizeAssertionKind(kind: string): AssertionKind {
  const lower = kind.toLowerCase().replace(/[-\s]/g, "_");
  if (lower in ASSERTION_KIND_META) return lower as AssertionKind;
  if (lower.includes("assert")) return "asserted";
  if (lower.includes("inferred") || lower.includes("owl")) return "owl_inferred";
  if (lower.includes("rule")) return "rule_derived";
  if (lower.includes("import")) return "imported";
  if (lower.includes("review")) return "review_metadata";
  if (lower.includes("policy")) return "policy_metadata";
  if (lower.includes("missing") || lower.includes("evidence")) return "missing_evidence";
  return "asserted";
}

export function AssertionKindBadge({ kind, stale }: { kind: string; stale?: boolean }) {
  const t = useT();
  const normalized = normalizeAssertionKind(kind);
  const meta = ASSERTION_KIND_META[normalized];
  const label = t(meta.label) === meta.label ? meta.zh : t(meta.label);
  return (
    <Tooltip title={t("Assertion kind: {label}", { label: meta.label })}>
      <Tag color={meta.color} aria-label={`assertion-kind-${normalized}`}>
        {label}
        {stale ? <span aria-label="stale-marker"> · {t("Stale")}</span> : null}
      </Tag>
    </Tooltip>
  );
}

export function EvidenceStatusBadge({ status }: { status: string }) {
  const t = useT();
  const normalized = (status || "unknown").toLowerCase();
  const color =
    normalized.includes("missing") || normalized.includes("absent")
      ? "red"
      : normalized.includes("bound") || normalized.includes("verified")
        ? "green"
        : "default";
  const label = normalized.includes("missing")
    ? t("Missing evidence")
    : normalized.includes("bound")
      ? t("Evidence bound")
      : t("Evidence: {status}", { status });
  return (
    <Tag color={color} aria-label={`evidence-status-${normalized}`}>
      {label}
    </Tag>
  );
}

export function EditabilityBadge({ editable, reason }: { editable: boolean | null; reason?: string | null }) {
  const t = useT();
  if (editable === null) {
    return (
      <Tag color="default" aria-label="editability-unknown">
        {t("Editability unknown")}
      </Tag>
    );
  }
  return (
    <Tooltip title={reason ?? undefined}>
      <Tag color={editable ? "green" : "red"} aria-label={`editability-${editable ? "editable" : "locked"}`}>
        {editable ? t("Editable") : t("Locked")}
      </Tag>
    </Tooltip>
  );
}

export function StalenessBadge({ stale, detail }: { stale: boolean; detail?: string }) {
  const t = useT();
  if (!stale) {
    return (
      <Tag color="green" aria-label="staleness-current">
        {t("Current")}
      </Tag>
    );
  }
  return (
    <Tooltip title={detail ?? undefined}>
      <Tag color="orange" aria-label="staleness-stale">
        {t("Stale derived")}
      </Tag>
    </Tooltip>
  );
}

export function WarningBadge({ count }: { count: number }) {
  const t = useT();
  if (!count) return null;
  return (
    <Tag color="warning" aria-label="warning-badge">
      {t("{count} warning(s)", { count })}
    </Tag>
  );
}

export function GraphIriLabel({ iri, copyable = true, shortened = true }: { iri: string; copyable?: boolean; shortened?: boolean }) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  const display = shortened ? shortenIri(iri) : iri;

  async function copy() {
    try {
      await navigator.clipboard.writeText(iri);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore clipboard errors
    }
  }

  return (
    <span className="graphIriLabel">
      <code title={iri}>{display}</code>
      {copyable && (
        <button
          aria-label={t("Copy graph IRI")}
          className="iconButton subtle"
          onClick={() => void copy()}
          title={t("Copy graph IRI")}
          type="button"
        >
          <Clipboard size={13} />
        </button>
      )}
      {copied && <span className="inlineOk">{t("Copied")}</span>}
    </span>
  );
}

export function shortenIri(iri: string, max = 56): string {
  if (!iri) return "";
  if (iri.length <= max) return iri;
  const slash = iri.lastIndexOf("/");
  if (slash >= 0 && iri.length - slash - 1 <= max) {
    const tail = iri.slice(slash + 1);
    return `…/${tail}`;
  }
  return `${iri.slice(0, max - 1)}…`;
}

export function EmptySemanticState({ icon, title, detail }: { icon: ReactNode; title: string; detail?: string }) {
  return (
    <div className="emptyState semanticEmpty">
      {icon}
      <span>{title}</span>
      {detail && <small>{detail}</small>}
    </div>
  );
}

export function countWarnings(warnings: unknown): number {
  if (!warnings) return 0;
  if (Array.isArray(warnings)) return warnings.length;
  if (typeof warnings === "object") {
    const values = Object.values(warnings as Record<string, unknown>);
    return values.length;
  }
  return 0;
}
