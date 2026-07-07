/**
 * Stage 4 §4.4 — EvidenceExplorerPanel.
 *
 * Read-only view over the ``evidence_bindings`` field set returned by
 * the ``fact-audit-queue`` read model. Each row shows the bound chunk's
 * document filename, sequence number, char range, and a short text
 * preview.
 *
 * Phase 8.2 — the "missing evidence" tag is now derived purely from
 * the binding list length (empty list ⇒ missing). The previous
 * ``hideMissingTag`` opt-out has been removed; call sites that want to
 * suppress the tag can simply not render this panel for non-asserted
 * fact kinds.
 */

import { Empty, Tag, Typography } from "antd";
import { FileText } from "lucide-react";

import { useT } from "../../i18n";
import type { EvidenceBinding } from "../../types";

type EvidenceExplorerPanelProps = {
  bindings: EvidenceBinding[];
};

export function EvidenceExplorerPanel({ bindings }: EvidenceExplorerPanelProps) {
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
              {t("No evidence binding for this fact.")}{" "}
              <Tag color="warning">{t("missing evidence")}</Tag>
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
