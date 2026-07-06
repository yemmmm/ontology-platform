/**
 * Stage 3 §7.1 — graph-set Publication Readiness dashboard.
 *
 * Replaces the legacy version-mutability switch + JSON gate list. Reads
 * `/semantic/graph-sets/{id}/read-models/publication-readiness` (polled by
 * `useGraphSetReadiness` every 30s while the tab is visible) and renders:
 *
 *   - Status badge (Ready / Has warnings / Blocked) + editable graph ratio
 *   - Per-gate list (validation, reasoning, rule, missing evidence, open
 *     edits, projection freshness)
 *   - Per-graph editability list
 *   - "Lock all graphs and export package" flow:
 *       on confirm → PATCH /semantic/graphs/{iri}/editability for each
 *       editable graph; on success trigger export download; on partial
 *       failure show retry / rollback (rollback unlocks the graphs that
 *       were just locked).
 *
 * Phase E rewires App.tsx routing to pass `graphSetId`; until then the page
 * also tolerates being rendered without one (empty state).
 */

import {
  Alert,
  Button,
  Card,
  Empty,
  Modal,
  Skeleton,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Lock,
  LockKeyhole,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  UnlockKeyhole,
  Undo2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import { useGraphSetReadiness } from "../hooks/useGraphSetReadiness";
import type {
  PublicationGate,
  PublicationGateStatus,
  PublicationReadinessRow,
} from "../hooks/useGraphSetReadiness";
import {
  buildGraphSetExportUrl,
  updateGraphEditability,
} from "../semanticApi";
import type { WorkbenchRequest } from "./workbenchTypes";

const { Text, Paragraph } = Typography;

type PublicationPageProps = {
  request: WorkbenchRequest;
  graphSetId: string | null;
  readOnly?: boolean;
};

type PublishPhase =
  | { kind: "idle" }
  | { kind: "confirm" }
  | { kind: "running"; locked: string[] }
  | {
      kind: "partial";
      locked: string[];
      remaining: { graph_iri: string; role: string }[];
      error: string;
    }
  | { kind: "done" };

function gateStatusColor(status: PublicationGateStatus): string {
  if (status === "passed") return "success";
  if (status === "warning") return "warning";
  return "error";
}

function gateStatusLabel(
  status: PublicationGateStatus,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  if (status === "passed") return t("Ready");
  if (status === "warning") return t("Has warnings");
  return t("Blocked");
}

function gateIcon(status: PublicationGateStatus) {
  if (status === "passed") return <CheckCircle2 size={16} color="#168764" />;
  if (status === "warning") return <AlertTriangle size={16} color="#f5b84b" />;
  return <ShieldAlert size={16} color="#c33542" />;
}

function formatDetails(details: Record<string, unknown>): string {
  // Compact human-readable summary of the gate details. The composer puts
  // either {count: number}, {staleness_state, latest_run_id}, or a projection
  // manifest map into `details`. We render keys/values; falls back to JSON.
  const entries = Object.entries(details);
  if (entries.length === 0) return "";
  return entries
    .map(([key, value]) => {
      if (value === null || value === undefined) return `${key}: —`;
      if (typeof value === "object") return `${key}: ${JSON.stringify(value)}`;
      return `${key}: ${String(value)}`;
    })
    .join(" · ");
}

function overallStatus(row: PublicationReadinessRow): PublicationGateStatus {
  if (row.blockers.length > 0) return "blocked";
  if (row.warnings.length > 0 || row.gates.some((g) => g.status === "warning")) {
    return "warning";
  }
  return "passed";
}

function StatusBadge({
  status,
  t,
}: {
  status: PublicationGateStatus;
  t: (k: string, params?: Record<string, string | number>) => string;
}) {
  const color = gateStatusColor(status);
  const icon =
    status === "passed" ? (
      <ShieldCheck size={16} color="#168764" />
    ) : status === "warning" ? (
      <AlertTriangle size={16} color="#f5b84b" />
    ) : (
      <ShieldAlert size={16} color="#c33542" />
    );
  return (
    <Tag color={color} style={{ paddingInline: 8, fontWeight: 600 }}>
      <Space size={6}>
        {icon}
        {gateStatusLabel(status, t)}
      </Space>
    </Tag>
  );
}

function GateRow({
  gate,
  t,
}: {
  gate: PublicationGate;
  t: (k: string, params?: Record<string, string | number>) => string;
}) {
  const detail = formatDetails(gate.details);
  return (
    <div
      data-gate={gate.gate}
      data-status={gate.status}
      style={{
        display: "flex",
        gap: 10,
        alignItems: "flex-start",
        paddingBlock: 6,
        borderBottom: "1px solid #f0f0f0",
      }}
    >
      <span style={{ paddingTop: 2 }}>{gateIcon(gate.status)}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <Space size={8} wrap>
          <strong>{gate.label}</strong>
          <Tag color={gateStatusColor(gate.status)}>{gateStatusLabel(gate.status, t)}</Tag>
        </Space>
        {detail && (
          <div style={{ marginTop: 4 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {detail}
            </Text>
          </div>
        )}
      </div>
      <code style={{ fontSize: 11, color: "#999" }}>{gate.gate}</code>
    </div>
  );
}

function EditableGraphRow({
  graphIri,
  role,
  editable,
  t,
}: {
  graphIri: string;
  role: string;
  editable: boolean;
  t: (k: string, params?: Record<string, string | number>) => string;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        alignItems: "center",
        paddingBlock: 4,
        borderBottom: "1px solid #f5f5f5",
      }}
    >
      {editable ? (
        <UnlockKeyhole size={15} color="#168764" />
      ) : (
        <LockKeyhole size={15} color="#8c8c8c" />
      )}
      <code style={{ flex: 1, overflowWrap: "anywhere" }}>{graphIri}</code>
      <Tag color={editable ? "warning" : "default"}>
        {editable ? t("Editable") : t("Locked ({role})", { role })}
      </Tag>
    </div>
  );
}

export function PublicationPage({
  request,
  graphSetId,
  readOnly = false,
}: PublicationPageProps) {
  const t = useT();
  const { data, loading, refreshing, error, reload } = useGraphSetReadiness(
    request,
    graphSetId,
  );
  const [phase, setPhase] = useState<PublishPhase>({ kind: "idle" });

  // Reset the publish modal whenever the graph set id changes.
  useEffect(() => {
    setPhase({ kind: "idle" });
  }, [graphSetId]);

  // All editable graphs from the read model. For member listing we also want
  // to show locked ones; the row doesn't expose them, so the per-graph section
  // is editable-only (matching the spec §7.1 wireframe).
  const editableGraphs = useMemo(() => data?.editable_graphs ?? [], [data]);

  async function handlePublishConfirm() {
    if (!data) return;
    const targets = [...data.editable_graphs];
    if (targets.length === 0) {
      setPhase({ kind: "done" });
      return;
    }
    setPhase({ kind: "running", locked: [] });
    const locked: string[] = [];
    let lastError: string | null = null;
    let failedIndex = targets.length;
    for (let i = 0; i < targets.length; i += 1) {
      const g = targets[i];
      try {
        await updateGraphEditability(request, g.graph_iri, false, "stage3-publish", "publication");
        locked.push(g.graph_iri);
      } catch (reason) {
        lastError = reason instanceof Error ? reason.message : String(reason);
        failedIndex = i;
        break;
      }
    }
    if (lastError && locked.length < targets.length) {
      const remaining = targets.slice(failedIndex);
      setPhase({
        kind: "partial",
        locked,
        remaining,
        error: lastError,
      });
      await reload();
      return;
    }
    // All locked — trigger the export download.
    const exportUrl = buildGraphSetExportUrl(data.graph_set_id, {
      format: "trig",
      include: "asserted",
      includeEvidence: true,
      includeShapes: true,
      includePolicy: true,
      includeMetadata: true,
    });
    window.location.href = exportUrl;
    setPhase({ kind: "done" });
    await reload();
  }

  async function handleRetry() {
    if (phase.kind !== "partial") return;
    const remaining = phase.remaining;
    const lockedSoFar = phase.locked;
    setPhase({ kind: "running", locked: lockedSoFar });
    let lastError: string | null = null;
    let failedIndex = remaining.length;
    const locked = [...lockedSoFar];
    for (let i = 0; i < remaining.length; i += 1) {
      const g = remaining[i];
      try {
        await updateGraphEditability(request, g.graph_iri, false, "stage3-publish", "publication");
        locked.push(g.graph_iri);
      } catch (reason) {
        lastError = reason instanceof Error ? reason.message : String(reason);
        failedIndex = i;
        break;
      }
    }
    if (lastError && locked.length < lockedSoFar.length + remaining.length) {
      setPhase({
        kind: "partial",
        locked,
        remaining: remaining.slice(failedIndex),
        error: lastError,
      });
      await reload();
      return;
    }
    if (data) {
      const exportUrl = buildGraphSetExportUrl(data.graph_set_id, {
        format: "trig",
        include: "asserted",
        includeEvidence: true,
        includeShapes: true,
        includePolicy: true,
        includeMetadata: true,
      });
      window.location.href = exportUrl;
    }
    setPhase({ kind: "done" });
    await reload();
  }

  async function handleRollback() {
    if (phase.kind !== "partial") return;
    const toUnlock = phase.locked;
    let lastError: string | null = null;
    for (const iri of toUnlock) {
      try {
        await updateGraphEditability(request, iri, true, "stage3-publish", "rollback");
      } catch (reason) {
        lastError = reason instanceof Error ? reason.message : String(reason);
      }
    }
    if (lastError) {
      setPhase({ ...phase, error: lastError });
    } else {
      setPhase({ kind: "idle" });
    }
    await reload();
  }

  // ----- Render states -----------------------------------------------------

  if (!graphSetId) {
    return (
      <section className="publicationPage stage3" data-testid="publication-readiness">
        <div className="topBar">
          <div>
            <span className="eyebrow">{t("Stage 3 · graph-set readiness")}</span>
            <h1>{t("Publication readiness")}</h1>
          </div>
        </div>
        <Empty description={t("Select a graph set to view publication readiness.")} />
      </section>
    );
  }

  if (loading && !data) {
    return (
      <section className="publicationPage stage3" data-testid="publication-readiness">
        <Spin tip={t("Loading…")} />
      </section>
    );
  }

  if (error && !data) {
    return (
      <section className="publicationPage stage3" data-testid="publication-readiness">
        <div className="topBar">
          <div>
            <span className="eyebrow">{t("Stage 3 · graph-set readiness")}</span>
            <h1>{t("Publication readiness")}</h1>
          </div>
        </div>
        <Alert
          type="error"
          showIcon
          message={t("publication-readiness not available")}
          description={error}
          action={
            <Button size="small" onClick={() => void reload()}>
              {t("Refresh")}
            </Button>
          }
        />
      </section>
    );
  }

  if (!data) {
    return (
      <section className="publicationPage stage3" data-testid="publication-readiness">
        <Empty description={t("publication-readiness not available")} />
      </section>
    );
  }

  const status = overallStatus(data);
  const memberRows = data.editable_graphs;

  const isPublishing = phase.kind === "running";
  const showConfirm = phase.kind === "confirm";
  const partial = phase.kind === "partial" ? phase : null;

  return (
    <section className="publicationPage stage3" data-testid="publication-readiness">
      <div className="topBar">
        <div>
          <span className="eyebrow">{t("Stage 3 · graph-set readiness")}</span>
          <h1>
            {t("Publication readiness · {graphSet}", {
              graphSet: data.graph_set_id,
            })}
          </h1>
          <div className="crumbTrail">
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("Polling every 30s while this tab is visible.")}
            </Text>
          </div>
        </div>
        <div className="topActions">
          <Button
            icon={<RefreshCw size={15} />}
            onClick={() => void reload()}
            loading={refreshing}
            disabled={loading}
          >
            {t("Refresh")}
          </Button>
        </div>
      </div>

      {error && (
        <Alert
          type="warning"
          showIcon
          message={t("publication-readiness not available")}
          description={error}
          style={{ marginBottom: 12 }}
        />
      )}

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space size={24} wrap>
          <Space size={8}>
            <Text type="secondary">{t("Status")}:</Text>
            <StatusBadge status={status} t={t} />
          </Space>
          <Space size={8}>
            <Text type="secondary">{t("Editable graphs: {count}", {
              count: data.editable_graph_count,
            })}</Text>
          </Space>
          <Space size={8}>
            <Text type="secondary">
              {data.last_published_at
                ? t("Last published {time}", { time: data.last_published_at })
                : t("Never published")}
            </Text>
          </Space>
        </Space>
      </Card>

      <Card
        size="small"
        title={t("Gates")}
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            {data.gates.filter((g) => g.status === "passed").length}/{data.gates.length}
          </Text>
        }
        style={{ marginBottom: 12 }}
      >
        {data.gates.length === 0 ? (
          <Empty />
        ) : (
          <div>
            {data.gates.map((gate) => (
              <GateRow key={gate.gate} gate={gate} t={t} />
            ))}
          </div>
        )}
      </Card>

      <Card
        size="small"
        title={
          <Space size={6}>
            <Lock size={15} />
            {t("Per-graph state")}
          </Space>
        }
        style={{ marginBottom: 12 }}
      >
        {memberRows.length === 0 ? (
          <Empty description={t("No editable graphs in this graph set.")} />
        ) : (
          <div>
            {memberRows.map((g) => (
              <EditableGraphRow
                key={g.graph_iri}
                graphIri={g.graph_iri}
                role={g.role}
                editable
                t={t}
              />
            ))}
          </div>
        )}
      </Card>

      {partial && (
        <Alert
          type="error"
          showIcon
          message={t("Partial failure: locked {locked}/{total} editable graphs.", {
            locked: partial.locked.length,
            total: partial.locked.length + partial.remaining.length,
          })}
          description={
            <Space direction="vertical" size={6}>
              <Text>{t("Last error: {error}", { error: partial.error })}</Text>
              <Space>
                <Button size="small" onClick={() => void handleRetry()}>
                  {t("Retry remaining")}
                </Button>
                <Button
                  size="small"
                  icon={<Undo2 size={14} />}
                  onClick={() => void handleRollback()}
                >
                  {t("Rollback (unlock {count})", { count: partial.locked.length })}
                </Button>
              </Space>
            </Space>
          }
          style={{ marginBottom: 12 }}
        />
      )}

      {phase.kind === "done" && (
        <Alert
          type="success"
          showIcon
          message={t("Lock all graphs and export package")}
          description={t("All editable graphs were locked and the export download started.")}
          style={{ marginBottom: 12 }}
          closable
          onClose={() => setPhase({ kind: "idle" })}
        />
      )}

      <div style={{ display: "flex", justifyContent: "center", paddingBlock: 12 }}>
        <Button
          type="primary"
          size="large"
          icon={<Download size={16} />}
          disabled={readOnly || memberRows.length === 0 || isPublishing || phase.kind === "done"}
          loading={isPublishing}
          onClick={() => setPhase({ kind: "confirm" })}
        >
          {t("Lock all graphs and export package")}
        </Button>
      </div>

      <Modal
        title={t("Confirm publication")}
        open={showConfirm}
        onCancel={() => setPhase({ kind: "idle" })}
        onOk={() => void handlePublishConfirm()}
        okText={t("Lock and export")}
        cancelText={t("Cancel")}
        okButtonProps={{ loading: isPublishing }}
        confirmLoading={isPublishing}
      >
        <Paragraph>
          {t("Publication will lock the following editable graphs and then download an export package.")}
        </Paragraph>
        {memberRows.length === 0 ? (
          <Skeleton active />
        ) : (
          <ul style={{ marginBlock: 0, paddingLeft: 20 }}>
            {memberRows.map((g) => (
              <li key={g.graph_iri}>
                <code>{g.graph_iri}</code> <Tag>{g.role}</Tag>
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </section>
  );
}

export type { PublicationPageProps };
