import { Alert, Button, Card, Collapse, Descriptions, Empty, Space, Spin, Switch, Tag, Typography } from "antd";
import { CheckCircle2, LockKeyhole, RefreshCw, ShieldAlert, UnlockKeyhole } from "lucide-react";
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
  onVersionChanged?: (version: OntologyVersion) => void | Promise<void>;
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
  onNavigate,
  onVersionChanged,
}: PublicationPageProps) {
  const [readiness, setReadiness] = useState<PublicationReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  async function setMutable(mutable: boolean) {
    setBusy(true);
    setError("");
    try {
      const updated = await request<OntologyVersion>(`/versions/${version.id}/mutability`, {
        method: "PATCH",
        body: JSON.stringify({ mutable }),
      });
      await onVersionChanged?.(updated);
      void check();
    } catch (toggleError) {
      setError(messageFrom(toggleError));
    } finally {
      setBusy(false);
    }
  }

  if (loading && !readiness) return <Spin tip="Evaluating publication gates…" />;

  const locked = version.status === "published";
  const mutable = !locked;
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <div className="topBar">
        <div>
          <span className="eyebrow">Version mutability</span>
          <h1>Publication</h1>
          <div className="crumbTrail">{project.name} / {ontology.name} / v{version.version_number}</div>
        </div>
        <Button icon={<RefreshCw size={15} />} onClick={() => void check()} loading={loading}>Recheck gates</Button>
      </div>
      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}
      {locked && <Alert type="success" showIcon message={`Version ${version.version_number} is locked and immutable.`} description={`Locked ${formatTimestamp(version.published_at)}`} />}
      <Card title="Target version">
        <Descriptions column={{ xs: 1, sm: 2, lg: 4 }} items={[
          { key: "ontology", label: "Ontology", children: ontology.name },
          { key: "version", label: "Version", children: `v${version.version_number}` },
          { key: "workflow", label: "Workflow", children: <Tag>{version.workflow_status}</Tag> },
          { key: "status", label: "Mutability", children: <Tag color={locked ? "green" : "gold"}>{locked ? "locked" : "editable"}</Tag> },
        ]} />
      </Card>
      <Card title="Version edit switch">
        <Space direction="vertical" size={12}>
          <Space wrap>
            {mutable ? <UnlockKeyhole size={18} color="#168764" /> : <LockKeyhole size={18} color="#c33542" />}
            <Switch
              checked={mutable}
              checkedChildren="Editable"
              unCheckedChildren="Locked"
              loading={busy}
              disabled={busy}
              onChange={(next) => void setMutable(next)}
            />
            <Tag color={mutable ? "warning" : "success"}>{mutable ? "Schema, entity, assertion and rule writes are allowed" : "Schema, entity, assertion and rule writes are blocked"}</Tag>
          </Space>
          <Typography.Paragraph style={{ margin: 0 }}>
            Turning mutability off captures the current schema and graph snapshot and makes version-scoped write APIs reject changes. Turning it back on reopens the same version for editing.
          </Typography.Paragraph>
        </Space>
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
        <Alert type="warning" showIcon message="Readiness has warnings or blockers" description={`Blocking gates: ${readiness.blocking.map((name) => gateLabels[name] ?? name).join(", ") || "none"}`} />
      )}
      {locked && Object.keys(version.publication_report).length > 0 && (
        <Card title="Lock snapshot report"><pre style={{ overflow: "auto", whiteSpace: "pre-wrap" }}>{jsonText(version.publication_report)}</pre></Card>
      )}
    </Space>
  );
}
