import { useState } from "react";
import { Lock, Unlock } from "lucide-react";
import { Tooltip } from "antd";
import { useT } from "../../i18n";
import { ConfirmActionDialog } from "../workbench";

export function GraphEditabilityToggle({
  graphIri,
  editable,
  reason,
  disabled,
  onToggle,
}: {
  graphIri: string;
  editable: boolean | null;
  reason: string | null;
  disabled?: boolean;
  onToggle: (next: boolean, reason: string) => Promise<void>;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [pendingReason, setPendingReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const next = editable !== true;

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await onToggle(next, pendingReason);
      setOpen(false);
      setPendingReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Tooltip title={disabled ? t("Editability change unavailable") : (reason ?? undefined)}>
        <button
          aria-label={t("Toggle graph editability")}
          className={editable ? "iconButton" : "iconButton warning"}
          disabled={disabled || busy}
          onClick={() => setOpen(true)}
          type="button"
        >
          {editable ? <Unlock size={14} /> : <Lock size={14} />}
          <span>{editable ? t("Editable") : t("Locked")}</span>
        </button>
      </Tooltip>
      <ConfirmActionDialog
        open={open}
        title={next ? t("Lock graph") : t("Unlock graph")}
        confirmLabel={next ? t("Lock graph") : t("Unlock graph")}
        danger={next}
        onCancel={() => setOpen(false)}
        onConfirm={() => void confirm()}
        loading={busy}
      >
        <p>{t("Graph: {iri}", { iri: graphIri })}</p>
        <p>
          {next
            ? t("Locking this graph rejects further governed semantic edits until it is unlocked.")
            : t("Unlocking this graph lets governed semantic edits reach it again.")}
        </p>
        <label className="stackForm">
          <span>{t("Reason (audit)")}</span>
          <textarea
            onChange={(event) => setPendingReason(event.target.value)}
            placeholder={t("Why are you changing editability?")}
            value={pendingReason}
          />
        </label>
        {error && <div className="inlineError">{error}</div>}
      </ConfirmActionDialog>
    </>
  );
}
