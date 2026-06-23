import { Alert, Button, Card, Collapse, Descriptions, Empty, Modal, Space, Spin, Tag, Typography } from "antd";
import { CheckCircle2, RefreshCw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { GovernancePageContext, OntologyVersion } from "./governanceTypes";
import { formatTimestamp, jsonText, messageFrom } from "./governanceTypes";

type PublicationGate = {
  gate_type: string;
  status: string;
  details: Record<string, unknown>;
  checked_at?: string;
};

type PublicationReadiness = {
  version_id: string;
  ready: boolean;
  gates: PublicationGate[];
  blocking: string[];
  warnings: string[];
};

type PublicationPageProps = GovernancePageContext & {
  onPublished?: (version: OntologyVersion) => void | Promise<void>;
};

const gateLabels: Record<string, string> = {
  schema_validation: "Schema validation",
  pending_proposals: "Pending proposals",
  unresolved_conflicts: "Unresolved conflicts",
  low_confidence_review: "Low-confidence review",
  evidence_coverage: "Evidence coverage",
  competency_questions: "Competency questions",
  fact_audit: "Fact audit",
};

export function PublicationPage({
  project,
  ontology,
  version,
  request,
  readOnly = false,
  onNavigate,
  onPublished,
}: PublicationPageProps) {
  const [readiness, setReadiness] = useState<PublicationReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  const check = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await request<PublicationReadiness>(`/versions/${version.id}/publication-readiness`);
      setReadiness(result);
      return result;
    } catch (checkError) {
      setError(messageFrom(checkError));
      return null;
    } finally {
      setLoading(false);
    }
  }, [request, version.id]);

  useEffect(() => {
    void check();
  }, [check]);

  const passed = useMemo(
    () => readiness?.gates.filter((gate) => gate.status === "passed").length ?? 0,
    [readiness],
  );

  async function preparePublish() {
    setBusy(true);
    const before = readiness;
    const current = await check();
    setBusy(false);
    if (!current?.ready) {
      setError("Publication readiness changed or still contains blocking gates.");
      return;
    }
    const stableGates = (value: PublicationReadiness) => value.gates.map(({ gate_type, status, details }) => ({ gate_type, status, details }));
    if (before && JSON.stringify(stableGates(before)) !== JSON.stringify(stableGates(current))) {
      setError("Gate results changed during the final check. Review the new results before publishing.");
      return;
    }
    setConfirmed(false);
    setConfirmOpen(true);
  }

  async function publish() {
    if (!confirmed) return;
    setBusy(true);
    setError("");
    try {
      const published = await request<OntologyVersion>(`/versions/${version.id}/publish`, {
        method: "POST",
        body: JSON.stringify({ confirm: true }),
      });
      setConfirmOpen(false);
      await onPublished?.(published);
    } catch (publishError) {
      setError(messageFrom(publishError));
    } finally {
      setBusy(false);
    }
  }

  if (loading && !readiness) return <Spin tip="Evaluating publication gates…" />;

  const published = version.status === "published";
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <div className="topBar">
        <div>
          <span className="eyebrow">Review / immutable release</span>
          <h1>Publication</h1>
          <div className="crumbTrail">{project.name} / {ontology.name} / v{version.version_number}</div>
        </div>
        <Button icon={<RefreshCw size={15} />} onClick={() => void check()} loading={loading}>Recheck gates</Button>
      </div>
      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}
      {published && <Alert type="success" showIcon message={`Version ${version.version_number} is published and immutable.`} description={`Published ${formatTimestamp(version.published_at)}`} />}
      <Card title="Target version">
        <Descriptions column={{ xs: 1, sm: 2, lg: 4 }} items={[
          { key: "ontology", label: "Ontology", children: ontology.name },
          { key: "version", label: "Version", children: `v${version.version_number}` },
          { key: "workflow", label: "Workflow", children: <Tag>{version.workflow_status}</Tag> },
          { key: "status", label: "Snapshot", children: <Tag color={published ? "green" : "gold"}>{version.status}</Tag> },
        ]} />
      </Card>
      <Card title={`Publication gates · ${passed}/${readiness?.gates.length ?? 0} passed`}>
        {!readiness?.gates.length ? <Empty description="No gate result is available" /> : (
          <Space direction="vertical" size={10} style={{ width: "100%" }}>
            {readiness.gates.map((gate) => (
              <Card key={gate.gate_type} size="small" style={{ borderLeft: `4px solid ${gate.status === "passed" ? "#2fbf8f" : gate.status === "warning" ? "#f5b84b" : "#e84855"}` }}>
                <Space direction="vertical" size={8} style={{ width: "100%" }}>
                  <Space wrap>
                    {gate.status === "passed" ? <CheckCircle2 size={17} color="#168764" /> : <ShieldAlert size={17} color="#c33542" />}
                    <strong>{gateLabels[gate.gate_type] ?? gate.gate_type}</strong>
                    <Tag color={gate.status === "passed" ? "success" : gate.status === "warning" ? "warning" : "error"}>{gate.status.toUpperCase()}</Tag>
                  </Space>
                  <Typography.Text type="secondary">The backend currently exposes gate details as unstructured JSON.</Typography.Text>
                  <Collapse ghost size="small" items={[{ key: "details", label: "Validation details", children: <pre style={{ overflow: "auto", whiteSpace: "pre-wrap" }}>{jsonText(gate.details)}</pre> }]} />
                  {gate.status !== "passed" && onNavigate && (
                    <Button size="small" onClick={() => onNavigate(gate.gate_type === "fact_audit" || gate.gate_type === "low_confidence_review" ? "facts" : gate.gate_type === "competency_questions" ? "questions" : gate.gate_type === "evidence_coverage" ? "sources" : "overview")}>Open remediation area</Button>
                  )}
                </Space>
              </Card>
            ))}
          </Space>
        )}
      </Card>
      {readiness && !readiness.ready && (
        <Alert type="warning" showIcon message="Publication is blocked" description={`Blocking gates: ${readiness.blocking.map((name) => gateLabels[name] ?? name).join(", ") || "unknown"}`} />
      )}
      <Card title="Explicit publication confirmation">
        <Space direction="vertical" size={12}>
          <Typography.Paragraph style={{ margin: 0 }}>Publishing creates an immutable schema and graph snapshot. Further changes require a successor draft.</Typography.Paragraph>
          <Button type="primary" danger onClick={() => void preparePublish()} loading={busy} disabled={readOnly || published || !readiness?.ready}>Run final check and publish…</Button>
          {!readiness?.ready && <Typography.Text type="secondary">The action remains disabled until every hard gate passes.</Typography.Text>}
        </Space>
      </Card>
      {published && Object.keys(version.publication_report).length > 0 && (
        <Card title="Publication report"><pre style={{ overflow: "auto", whiteSpace: "pre-wrap" }}>{jsonText(version.publication_report)}</pre></Card>
      )}
      <Modal title="Publish immutable version" open={confirmOpen} onCancel={() => setConfirmOpen(false)} onOk={() => void publish()} okText="Publish now" okButtonProps={{ danger: true, disabled: !confirmed, loading: busy }}>
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Alert type="warning" showIcon message={`${ontology.name} · v${version.version_number}`} description={`${readiness?.gates.length ?? 0} gates checked; ${passed} passed. This operation is irreversible.`} />
          <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} style={{ width: 16, minHeight: 16 }} />I understand that this version becomes immutable.</label>
        </Space>
      </Modal>
    </Space>
  );
}
