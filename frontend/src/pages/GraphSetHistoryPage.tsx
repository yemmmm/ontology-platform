/**
 * Stage 3 §7.2 — graph-set history + delta dashboard.
 *
 * Replaces the legacy `VersionsPage` (immutable ontology-version lineage).
 * Reads `/semantic/graph-sets/{id}/read-models/graph-set-history-list`
 * (one-shot fetch on mount + manual Refresh button — no polling, since
 * graph sets change rarely) and renders:
 *
 *   - Left: list of graph sets in scope, status icon (editable / locked /
 *     superseded), member count, latest derived pointer timestamp.
 *   - Right: detail panel for the selected graph set (status, members,
 *     locked_at, source_signature, latest derived pointer).
 *   - Diff section: two input fields (base / target graph set id) +
 *     "Compute delta" button; on success shows per-role added/removed
 *     triple counts (and a truncated warning when the composer capped the
 *     triple arrays).
 *
 * The composer queries by `(scope_type, scope_id)`, so any graph set id
 * in scope is a valid anchor — typically the active graph set passed via
 * the `?graphSet=` query param. The page tolerates being rendered without
 * one (empty state).
 */

import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import {
  AlertTriangle,
  GitCompareArrows,
  Lock,
  RefreshCw,
  Unlock,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import { useGraphSetDelta } from "../hooks/useGraphSetDelta";
import {
  useGraphSetHistory,
  type GraphSetHistoryEntry,
  type GraphSetHistoryStatus,
} from "../hooks/useGraphSetHistory";
import type { WorkbenchRequest } from "./workbenchTypes";

const { Text, Paragraph } = Typography;

type GraphSetHistoryPageProps = {
  request: WorkbenchRequest;
  ontologyId: string;
  graphSetId: string | null;
  readOnly?: boolean;
};

function statusColor(status: GraphSetHistoryStatus): string {
  if (status === "editable") return "warning";
  if (status === "locked") return "default";
  return "blue";
}

function statusLabel(
  status: GraphSetHistoryStatus,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  if (status === "editable") return t("Editable");
  if (status === "locked") return t("Locked");
  return t("Superseded");
}

function StatusIcon({ status }: { status: GraphSetHistoryStatus }) {
  if (status === "editable")
    return <Unlock size={15} color="#168764" aria-hidden />;
  if (status === "locked")
    return <Lock size={15} color="#8c8c8c" aria-hidden />;
  return <AlertTriangle size={15} color="#1677ff" aria-hidden />;
}

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "—";
  // Backend returns ISO strings (semantic_read_model composers). Render
  // them in the user's locale. Fall back to the raw string if invalid.
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const diffMs = date.getTime() - Date.now();
  const abs = Math.abs(diffMs);
  const minutes = Math.round(abs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d`;
  return formatTimestamp(value);
}

function GraphSetRow({
  entry,
  selected,
  onSelect,
  t,
}: {
  entry: GraphSetHistoryEntry;
  selected: boolean;
  onSelect: (id: string) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(entry.graph_set_id)}
      data-selected={selected}
      data-status={entry.status}
      data-graph-set-id={entry.graph_set_id}
      aria-pressed={selected}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
        width: "100%",
        textAlign: "left",
        padding: "10px 12px",
        borderRadius: 6,
        cursor: "pointer",
        background: selected ? "#e6f4ff" : "transparent",
        border: selected ? "1px solid #1677ff" : "1px solid #f0f0f0",
      }}
    >
      <Space size={6} wrap>
        <StatusIcon status={entry.status} />
        <code style={{ fontSize: 13 }}>{entry.graph_set_id}</code>
        <Tag color={statusColor(entry.status)} style={{ marginInlineEnd: 0 }}>
          {statusLabel(entry.status, t)}
        </Tag>
      </Space>
      <Space size={10} wrap>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t("{count} members", { count: entry.member_count })}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {t("Created {ago}", { ago: relativeTime(entry.created_at) })}
        </Text>
        {entry.latest_derived_pointer_at && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t("Derived {ago}", {
              ago: relativeTime(entry.latest_derived_pointer_at),
            })}
          </Text>
        )}
      </Space>
    </button>
  );
}

function GraphSetDetail({
  entry,
  t,
}: {
  entry: GraphSetHistoryEntry | undefined;
  t: (key: string, params?: Record<string, string | number>) => string;
}) {
  if (!entry) {
    return <Empty description={t("Select a graph set from the list.")} />;
  }
  return (
    <Descriptions
      bordered
      size="small"
      column={{ xs: 1, md: 1 }}
      items={[
        {
          key: "id",
          label: t("Graph set ID"),
          children: <code>{entry.graph_set_id}</code>,
        },
        {
          key: "status",
          label: t("Status"),
          children: (
            <Tag color={statusColor(entry.status)}>
              {statusLabel(entry.status, t)}
            </Tag>
          ),
        },
        {
          key: "created",
          label: t("Created"),
          children: formatTimestamp(entry.created_at),
        },
        {
          key: "locked",
          label: t("Locked at"),
          children: entry.locked_at ? formatTimestamp(entry.locked_at) : "—",
        },
        {
          key: "members",
          label: t("Members"),
          children: entry.member_count,
        },
        {
          key: "derived",
          label: t("Latest derived pointer"),
          children: entry.latest_derived_pointer_at
            ? formatTimestamp(entry.latest_derived_pointer_at)
            : "—",
        },
        {
          key: "signature",
          label: t("Source signature"),
          children: <code>{entry.source_signature || "—"}</code>,
        },
      ]}
    />
  );
}

function RoleDeltaRow({
  role,
  counts,
  t,
}: {
  role: string;
  counts: { added: number; removed: number };
  t: (key: string, params?: Record<string, string | number>) => string;
}) {
  const unchanged = counts.added === 0 && counts.removed === 0;
  return (
    <div
      data-role={role}
      style={{
        display: "flex",
        gap: 10,
        alignItems: "center",
        paddingBlock: 6,
        borderBottom: "1px solid #f0f0f0",
      }}
    >
      <code style={{ flex: 1, overflowWrap: "anywhere" }}>{role}</code>
      {unchanged ? (
        <Tag>{t("Unchanged")}</Tag>
      ) : (
        <Space size={6}>
          {counts.added > 0 && (
            <Tag color="success">+{counts.added}</Tag>
          )}
          {counts.removed > 0 && (
            <Tag color="error">−{counts.removed}</Tag>
          )}
        </Space>
      )}
    </div>
  );
}

export function GraphSetHistoryPage({
  request,
  ontologyId,
  graphSetId,
  readOnly = false,
}: GraphSetHistoryPageProps) {
  const t = useT();
  const {
    data: history,
    loading,
    refreshing,
    error,
    reload,
  } = useGraphSetHistory(request, graphSetId);

  const { data: delta, loading: deltaLoading, error: deltaError, compute } =
    useGraphSetDelta(request);

  const [selected, setSelected] = useState<string | null>(null);
  const [baseId, setBaseId] = useState<string>("");
  const [targetId, setTargetId] = useState<string>("");

  // Default-select the anchor graph set once the list loads, and prefill the
  // diff's base field so the user can compare against the current set
  // immediately.
  useEffect(() => {
    if (!graphSetId) return;
    setSelected((current) => current ?? graphSetId);
    setBaseId((current) => current || graphSetId);
  }, [graphSetId]);

  // When the list arrives, default the diff target to the second-most-recent
  // graph set (history is sorted newest-first by the composer) so the user
  // can compute "what changed since the previous set" with one click.
  useEffect(() => {
    if (!history || history.length === 0) return;
    setTargetId((current) => {
      if (current) return current;
      const previous = history.find((entry) => entry.graph_set_id !== baseId);
      return previous?.graph_set_id ?? "";
    });
  }, [history, baseId]);

  const selectedEntry = useMemo(
    () => history?.find((entry) => entry.graph_set_id === selected),
    [history, selected],
  );

  if (!graphSetId) {
    return (
      <section
        className="graphSetHistoryPage stage3"
        data-testid="graph-set-history"
      >
        <div className="topBar">
          <div>
            <span className="eyebrow">{t("Stage 3 · graph-set history")}</span>
            <h1>{t("Graph set history")}</h1>
          </div>
        </div>
        <Empty description={t("Select a graph set to view its history.")} />
      </section>
    );
  }

  if (loading && !history) {
    return (
      <section
        className="graphSetHistoryPage stage3"
        data-testid="graph-set-history"
      >
        <Spin tip={t("Loading…")} />
      </section>
    );
  }

  if (error && !history) {
    return (
      <section
        className="graphSetHistoryPage stage3"
        data-testid="graph-set-history"
      >
        <div className="topBar">
          <div>
            <span className="eyebrow">{t("Stage 3 · graph-set history")}</span>
            <h1>{t("Graph set history")}</h1>
          </div>
        </div>
        <Alert
          type="error"
          showIcon
          message={t("graph-set-history-list not available")}
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

  const list = history ?? [];

  return (
    <section
      className="graphSetHistoryPage stage3"
      data-testid="graph-set-history"
    >
      <div className="topBar">
        <div>
          <span className="eyebrow">{t("Stage 3 · graph-set history")}</span>
          <h1>{t("Graph set history")}</h1>
          <div className="crumbTrail">
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t("Anchor: {graphSet}", { graphSet: graphSetId })}
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
          message={t("graph-set-history-list not available")}
          description={error}
          style={{ marginBottom: 12 }}
        />
      )}

      <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 360px) 1fr", gap: 16, alignItems: "start" }}>
        <Card
          size="small"
          title={t("Graph sets in scope")}
          extra={
            <Text type="secondary" style={{ fontSize: 12 }}>
              {list.length}
            </Text>
          }
        >
          {list.length === 0 ? (
            <Empty description={t("No graph sets in this scope.")} />
          ) : (
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              {list.map((entry) => (
                <GraphSetRow
                  key={entry.graph_set_id}
                  entry={entry}
                  selected={selected === entry.graph_set_id}
                  onSelect={setSelected}
                  t={t}
                />
              ))}
            </Space>
          )}
        </Card>

        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Card size="small" title={t("Selected graph set")}>
            <GraphSetDetail entry={selectedEntry} t={t} />
          </Card>

          <Card
            size="small"
            title={
              <Space size={6}>
                <GitCompareArrows size={15} />
                {t("Compare two graph sets")}
              </Space>
            }
          >
            <Paragraph type="secondary" style={{ fontSize: 12 }}>
              {t(
                "Compute the per-role RDF delta between a base and a target graph set.",
              )}
            </Paragraph>
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Space wrap style={{ width: "100%" }}>
                <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {t("Base")}
                  </Text>
                  <Input
                    aria-label={t("Base graph set")}
                    value={baseId}
                    onChange={(e) => setBaseId(e.target.value)}
                    placeholder="gs-…"
                    style={{ width: 220 }}
                  />
                </label>
                <span>→</span>
                <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {t("Target")}
                  </Text>
                  <Input
                    aria-label={t("Target graph set")}
                    value={targetId}
                    onChange={(e) => setTargetId(e.target.value)}
                    placeholder="gs-…"
                    style={{ width: 220 }}
                  />
                </label>
                <Button
                  type="primary"
                  icon={<GitCompareArrows size={15} />}
                  loading={deltaLoading}
                  disabled={
                    readOnly ||
                    !baseId ||
                    !targetId ||
                    baseId === targetId
                  }
                  onClick={() => void compute(baseId, targetId)}
                >
                  {t("Compute delta")}
                </Button>
              </Space>
              {baseId && targetId && baseId === targetId && (
                <Alert
                  type="info"
                  showIcon
                  message={t("Choose two different graph sets.")}
                />
              )}
              {deltaError && (
                <Alert
                  type="error"
                  showIcon
                  message={t("graph-set-delta not available")}
                  description={deltaError}
                />
              )}
              {delta && (
                <div
                  data-section="delta-roles"
                  style={{ marginTop: 4 }}
                >
                  {delta.truncated && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 8 }}
                      message={t(
                        "Diff arrays were truncated. Counts are accurate; shown triples are capped.",
                      )}
                    />
                  )}
                  {delta.roles.length === 0 ? (
                    <Empty description={t("No roles in either graph set.")} />
                  ) : (
                    delta.roles.map((r) => (
                      <RoleDeltaRow
                        key={r.role}
                        role={r.role}
                        counts={r.counts}
                        t={t}
                      />
                    ))
                  )}
                  <Descriptions
                    size="small"
                    bordered
                    column={1}
                    style={{ marginTop: 12 }}
                    items={[
                      {
                        key: "base",
                        label: t("Base graph set"),
                        children: <code>{delta.base_graph_set_id}</code>,
                      },
                      {
                        key: "target",
                        label: t("Target graph set"),
                        children: <code>{delta.target_graph_set_id}</code>,
                      },
                    ]}
                  />
                </div>
              )}
            </Space>
          </Card>
        </Space>
      </div>
    </section>
  );
}

export type { GraphSetHistoryPageProps };
