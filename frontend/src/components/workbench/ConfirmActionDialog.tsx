import { Alert, Modal } from "antd";
import type { ReactNode } from "react";
import { useT } from "../../i18n";

export type ConfirmActionDialogProps = {
  open: boolean;
  title: ReactNode;
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  disabled?: boolean;
  loading?: boolean;
  warning?: ReactNode;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
};

export function ConfirmActionDialog({
  open,
  title,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  disabled = false,
  loading = false,
  warning,
  onConfirm,
  onCancel,
}: ConfirmActionDialogProps) {
  const t = useT();
  return (
    <Modal
      open={open}
      title={title}
      okText={t(confirmLabel)}
      cancelText={t(cancelLabel)}
      okButtonProps={{ danger, disabled }}
      confirmLoading={loading}
      closable={!loading}
      maskClosable={!loading}
      keyboard={!loading}
      onOk={onConfirm}
      onCancel={onCancel}
      destroyOnHidden
    >
      {warning ? <Alert type="warning" showIcon message={warning} style={{ marginBottom: 16 }} /> : null}
      {children}
    </Modal>
  );
}
