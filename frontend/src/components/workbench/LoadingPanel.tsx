import { Spin } from "antd";

export function LoadingPanel({ label = "Loading", minHeight = 180 }: {
  label?: string;
  minHeight?: number;
}) {
  return (
    <div
      className="loading-panel"
      style={{ minHeight, display: "grid", placeItems: "center" }}
      role="status"
      aria-live="polite"
    >
      <Spin tip={label}><span aria-hidden="true" /></Spin>
    </div>
  );
}
