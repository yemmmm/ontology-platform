import { ShieldCheck, AlertTriangle } from "lucide-react";
import type { SemanticEditEvidenceStatus, SemanticJsonObject } from "../../types";
import { useT } from "../../i18n";

export function EvidenceBindingPanel({
  evidenceStatus,
  evidenceIds,
  warningState,
  onStatusChange,
  onEvidenceIdsChange,
  onWarningStateChange,
}: {
  evidenceStatus: SemanticEditEvidenceStatus | null;
  evidenceIds: string;
  warningState: string;
  onStatusChange: (next: SemanticEditEvidenceStatus | null) => void;
  onEvidenceIdsChange: (next: string) => void;
  onWarningStateChange: (next: string) => void;
}) {
  const t = useT();
  const missing = evidenceStatus === "missing_evidence";
  return (
    <section className="evidenceBindingPanel" aria-label="evidence-binding-panel">
      <header>
        {missing ? <AlertTriangle size={14} /> : <ShieldCheck size={14} />}
        <span>{t("Evidence binding")}</span>
      </header>
      <div className="stackForm">
        <label>
          <span>{t("Evidence status")}</span>
          <select
            onChange={(event) => {
              const value = event.target.value || null;
              if (value === "evidence_bound" || value === "missing_evidence") {
                onStatusChange(value);
              } else {
                onStatusChange(null);
              }
            }}
            value={evidenceStatus ?? ""}
          >
            <option value="">{t("Unset")}</option>
            <option value="evidence_bound">{t("Evidence bound")}</option>
            <option value="missing_evidence">{t("Missing evidence")}</option>
          </select>
        </label>
        <label>
          <span>{t("Evidence IDs (comma separated)")}</span>
          <input
            onChange={(event) => onEvidenceIdsChange(event.target.value)}
            placeholder="evidence-1,evidence-2"
            value={evidenceIds}
          />
        </label>
        <label>
          <span>{t("Warning state (JSON)")}</span>
          <textarea
            onChange={(event) => onWarningStateChange(event.target.value)}
            placeholder='{"note":"low confidence"}'
            value={warningState}
          />
        </label>
      </div>
      {missing && (
        <div className="callout warning">
          <strong>{t("Missing-evidence acknowledgement")}</strong>
          <span>{t("Statements written with missing evidence will be visible with warnings on read paths and propagated into derived outputs.")}</span>
        </div>
      )}
    </section>
  );
}

export function parseWarningState(value: string): SemanticJsonObject {
  if (!value.trim()) return {};
  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as SemanticJsonObject;
    }
  } catch {
    // ignore parse errors so the user can keep editing
  }
  return {};
}

export function splitEvidenceIds(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
