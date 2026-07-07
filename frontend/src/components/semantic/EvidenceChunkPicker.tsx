/**
 * Phase 8.2 — EvidenceChunkPicker.
 *
 * Modal that lets the user paste or type evidence text plus optional
 * document metadata, then submit via the ``onSubmit`` callback (which
 * routes to ``bindFactEvidence`` in FactAuditPage).
 *
 * MVP scope: free-text entry. A future iteration will add a PDF chunk
 * browser (select from evidence_chunks list, pick a range, auto-populate
 * the text field).
 */

import { useState } from "react";
import { Button, Input, Modal, Tag } from "antd";

import { useT } from "../../i18n";

type EvidenceChunkPickerProps = {
  open: boolean;
  factId: string;
  onClose: () => void;
  onSubmit: (
    text: string,
    meta?: { document_filename?: string; sequence?: number },
  ) => Promise<void>;
};

export function EvidenceChunkPicker({
  open,
  factId,
  onClose,
  onSubmit,
}: EvidenceChunkPickerProps) {
  const t = useT();
  const [text, setText] = useState("");
  const [docName, setDocName] = useState<string | undefined>();
  const [sequence, setSequence] = useState<number | undefined>();
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    if (!text.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(text.trim(), {
        document_filename: docName,
        sequence,
      });
      setText("");
      setDocName(undefined);
      setSequence(undefined);
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title={t("Add evidence")}
      onCancel={onClose}
      footer={[
        <Button key="cancel" onClick={onClose}>
          {t("Cancel")}
        </Button>,
        <Button
          key="ok"
          type="primary"
          loading={submitting}
          disabled={!text.trim()}
          onClick={() => void handleSubmit()}
        >
          {t("Add")}
        </Button>,
      ]}
    >
      <p style={{ marginBottom: 8 }}>
        <Tag>fact_id</Tag>
        <code style={{ fontSize: 12 }}>{factId.slice(0, 16)}…</code>
      </p>
      <Input.TextArea
        rows={6}
        placeholder={t("Paste or type evidence text")}
        value={text}
        onChange={(event) => setText(event.target.value)}
      />
      <Input
        style={{ marginTop: 8 }}
        placeholder={t("Document filename (optional)")}
        value={docName ?? ""}
        onChange={(event) => setDocName(event.target.value || undefined)}
      />
      <Input
        style={{ marginTop: 8 }}
        type="number"
        placeholder={t("Sequence (optional)")}
        value={sequence ?? ""}
        onChange={(event) =>
          setSequence(event.target.value ? Number(event.target.value) : undefined)
        }
      />
    </Modal>
  );
}

export type { EvidenceChunkPickerProps };
