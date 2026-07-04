import { Spin } from "antd";
import { useT } from "../../i18n";

export function LoadingPanel({ label = "Loading", minHeight = 180 }: {
  label?: string;
  minHeight?: number;
}) {
  const t = useT();
  return (
    <div
      className="loading-panel"
      style={{ minHeight, display: "grid", placeItems: "center" }}
      role="status"
      aria-live="polite"
    >
      <Spin tip={t(label)}><span aria-hidden="true" /></Spin>
    </div>
  );
}
