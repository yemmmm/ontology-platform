import { Alert, Button, Card, Descriptions, Empty, Modal, Select, Space, Spin, Steps, Tag, Typography } from "antd";
import { GitCompareArrows, GitFork, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import type { GovernancePageContext, OntologyVersion } from "./governanceTypes";
import { formatTimestamp, jsonText, messageFrom } from "./governanceTypes";

type VersionDiff = {
  from_version_id: string;
  to_version_id: string;
  schema: Record<string, unknown>;
  graph: Record<string, unknown>;
};

type VersionsPageProps = GovernancePageContext & {
  onVersionChange?: (version: OntologyVersion) => void;
};

export function VersionsPage({ ontology, version, request, onVersionChange }: VersionsPageProps) {
  const t = useT();
  const [versions, setVersions] = useState<OntologyVersion[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fromId, setFromId] = useState("");
  const [toId, setToId] = useState("");
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [parent, setParent] = useState<OntologyVersion | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await request<OntologyVersion[]>(`/ontologies/${ontology.id}/versions`);
      const ordered = [...data].sort((left, right) => left.version_number - right.version_number);
      setVersions(ordered);
      setFromId((current) => current || ordered[ordered.length - 2]?.id || ordered[0]?.id || "");
      setToId((current) => current || ordered[ordered.length - 1]?.id || "");
    } catch (loadError) {
      setError(messageFrom(loadError));
    } finally {
      setLoading(false);
    }
  }, [ontology.id, request]);

  useEffect(() => { void load(); }, [load]);

  const selected = versions.find((item) => item.id === version.id) ?? version;
  const optionItems = useMemo(() => versions.map((item) => ({ value: item.id, label: `v${item.version_number} · ${item.status}` })), [versions]);

  async function compare() {
    if (!fromId || !toId || fromId === toId) return;
    setBusy(true);
    setError("");
    try {
      setDiff(await request<VersionDiff>(`/versions/${fromId}/diff/${toId}`));
    } catch (compareError) {
      setError(messageFrom(compareError));
    } finally {
      setBusy(false);
    }
  }

  async function createSuccessor() {
    if (!parent) return;
    setBusy(true);
    setError("");
    try {
      const created = await request<OntologyVersion>(`/ontologies/${ontology.id}/versions`, {
        method: "POST",
        body: JSON.stringify({ parent_version_id: parent.id }),
      });
      setVersions((current) => [...current, created].sort((left, right) => left.version_number - right.version_number));
      setParent(null);
      onVersionChange?.(created);
    } catch (createError) {
      setError(messageFrom(createError));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spin tip={t("Loading version lineage…")} />;
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <div className="topBar">
        <div><span className="eyebrow">{t("Model / immutable lineage")}</span><h1>{t("Versions")}</h1><div className="crumbTrail">{ontology.name} / v{selected.version_number}</div></div>
        <Button icon={<RefreshCw size={15} />} onClick={() => void load()}>{t("Refresh")}</Button>
      </div>
      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}
      <Card title={t("Version timeline")}>
        {versions.length === 0 ? <Empty description={t("No ontology versions")} /> : (
          <Steps direction="vertical" current={versions.findIndex((item) => item.id === selected.id)} items={versions.map((item) => ({
            title: <Space wrap><Button type="link" style={{ padding: 0 }} onClick={() => onVersionChange?.(item)}>v{item.version_number}</Button><Tag color={item.status === "published" ? "green" : "gold"}>{item.status}</Tag><Tag>{item.workflow_status}</Tag></Space>,
            description: <Space direction="vertical" size={2}><span>{item.parent_version_id ? t("Parent: {id}", { id: item.parent_version_id }) : t("Parent: root")}</span><span>{t("Created {time} · Published {pub}", { time: formatTimestamp(item.created_at), pub: formatTimestamp(item.published_at) })}</span>{item.status === "published" && <Button size="small" icon={<GitFork size={14} />} onClick={() => setParent(item)}>{t("Create successor draft")}</Button>}</Space>,
            status: item.status === "published" ? "finish" : item.id === selected.id ? "process" : "wait",
          }))} />
        )}
      </Card>
      <Card title={t("Compare versions")}>
        <Space wrap>
          <Select aria-label={t("From version")} value={fromId || undefined} onChange={setFromId} options={optionItems} style={{ width: 180 }} placeholder={t("From version")} />
          <span>→</span>
          <Select aria-label={t("To version")} value={toId || undefined} onChange={setToId} options={optionItems} style={{ width: 180 }} placeholder={t("To version")} />
          <Button type="primary" icon={<GitCompareArrows size={15} />} onClick={() => void compare()} loading={busy} disabled={!fromId || !toId || fromId === toId}>{t("Compare")}</Button>
        </Space>
        {fromId === toId && fromId && <Alert style={{ marginTop: 12 }} type="info" showIcon message={t("Choose two different versions.")} />}
        {diff && <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 12, marginTop: 16 }}>
          <Card size="small" title={t("Schema diff")}><pre style={{ overflow: "auto", whiteSpace: "pre-wrap" }}>{jsonText(diff.schema)}</pre></Card>
          <Card size="small" title={t("Graph statistics diff")}><pre style={{ overflow: "auto", whiteSpace: "pre-wrap" }}>{jsonText(diff.graph)}</pre></Card>
        </div>}
      </Card>
      <Card title={t("Selected snapshot · v{n}", { n: selected.version_number })}>
        <Descriptions bordered column={{ xs: 1, md: 2 }} items={[
          { key: "id", label: t("Version ID"), children: selected.id },
          { key: "parent", label: t("Parent"), children: selected.parent_version_id ?? t("Root") },
          { key: "status", label: t("Status"), children: selected.status },
          { key: "workflow", label: t("Workflow"), children: selected.workflow_status },
        ]} />
        {selected.status === "published" && Object.keys(selected.publication_report).length > 0 && <Card size="small" title={t("Publication report")} style={{ marginTop: 12 }}><pre style={{ overflow: "auto", whiteSpace: "pre-wrap" }}>{jsonText(selected.publication_report)}</pre></Card>}
        {selected.status === "published" && <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>{t("Published snapshots expose no mutation actions.")}</Typography.Paragraph>}
      </Card>
      <Modal title={t("Create successor draft")} open={Boolean(parent)} onCancel={() => setParent(null)} onOk={() => void createSuccessor()} okText={t("Create draft")} confirmLoading={busy}>
        <Alert type="info" showIcon message={t("Parent: {name} v{n}", { name: ontology.name, n: parent?.version_number ?? "" })} description={t("The published parent remains immutable. A new mutable draft will be created with this lineage reference.")} />
      </Modal>
    </Space>
  );
}
