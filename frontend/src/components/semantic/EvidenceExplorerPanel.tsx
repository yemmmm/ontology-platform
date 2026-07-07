/**
 * Stage 4 §4.4 — EvidenceExplorerPanel.
 *
 * Reads-only view over the ``evidence_bindings`` field set returned by
 * the ``fact-audit-queue`` read model. Each row shows the bound chunk's
 * document filename, sequence number, char range, and a short text
 * preview.
 *
 * If the binding list is empty (i.e. no ``prov:wasDerivedFrom`` triple
 * exists for the fact), the panel falls back to a compact "No evidence
 * binding for this fact" empty state. The Stage 1 controlled-editor
 * ``EvidenceBindingPanel`` is intentionally not mounted here — that panel
 * writes through the canonical-write flow, which Stage 4 does not
 * invoke from the read-only explorer.
 */

import { Empty, Tag, Typography } from "antd";
import { FileText } from "lucide-react";

import { useT } from "../../i18n";
import type { EvidenceBinding } from "../../types";

type EvidenceExplorerPanelProps = {
  bindings: EvidenceBinding[];
  /** When ``true``, render the empty state without a "missing evidence"
   * tag (useful for non-asserted fact kinds where bindings never
   * apply). */
  hideMissingTag?: boolean;
};

export function EvidenceExplorerPanel({
  bindings,
  hideMissingTag = false,
}: EvidenceExplorerPanelProps) {
  const t = useT();
  if (!bindings || bindings.length === 0) {
    return (
      <div
        className="evidenceExplorerPanel evidenceExplorerEmpty"
        aria-label="evidence-explorer-empty"
      >
        <Empty
          image={<FileText size={28} />}
          description={
            <span>
              {t("No evidence binding for this fact.")}
              {!hideMissingTag && (
                <>
                  {" "}
                  <Tag color="warning">{t("missing evidence")}</Tag>
                </>
              )}
            </span>
          }
        />
      </div>
    );
  }
  return (
    <ul className="evidenceExplorerPanel" aria-label="evidence-explorer-bindings">
      {bindings.map((binding) => (
        <li
          key={binding.chunk_iri}
          className="evidenceBindingRow"
          aria-label={`evidence-binding-${binding.chunk_iri}`}
        >
          <div className="evidenceBindingHeader">
            <FileText size={14} />
            <strong>{binding.document_filename}</strong>
            <Tag>#{binding.sequence}</Tag>
            <Tag>
              {binding.char_start}–{binding.char_end}
            </Tag>
          </div>
          <Typography.Paragraph
            type="secondary"
            ellipsis={{ rows: 3 }}
            style={{ margin: 0 }}
            aria-label={`evidence-binding-preview-${binding.chunk_iri}`}
          >
            {binding.text_preview}
          </Typography.Paragraph>
          <code className="evidenceBindingIri">{binding.chunk_iri}</code>
        </li>
      ))}
    </ul>
  );
}

export type { EvidenceExplorerPanelProps };
