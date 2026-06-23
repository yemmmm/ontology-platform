import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  InputNumber,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { Check, RefreshCw, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { EvidenceExplorer } from "./EvidenceExplorer";
import type { GovernancePageContext } from "./governanceTypes";
import { jsonText, messageFrom } from "./governanceTypes";

type FactClaim = {
  id: string;
  claim_key: string;
  project_id: string;
  ontology_id: string;
  ontology_version_id: string;
  claim_type: string;
  layer: string;
  subject: Record<string, unknown>;
  predicate: string;
  value: unknown;
  graph_path: Array<Record<string, unknown>>;
  evidence_ids: string[];
  generation_reason: string;
  confidence: number;
  audit_status: string;
  review_decision: Record<string, unknown>;
  linked_fix_proposal_id: string | null;
  stale: boolean;
  stale_reason: string | null;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
};

type FactAuditPageProps = GovernancePageContext & {
  batchItemIds?: string[];
  initialClaimId?: string;
};

const layers = [
  "entity_attribute",
  "entity_relation",
  "inferred_inverse",
  "low_confidence",
  "value_conflict",
];

function subjectLabel(subject: Record<string, unknown>): string {
  const name = subject.name;
  if (typeof name === "string" && name) return name;
  const entityId = subject.entity_id;
  if (typeof entityId === "string" && entityId) return entityId;
  return "Structured subject";
}

export function FactAuditPage({
  project,
  ontology,
  version,
  request,
  readOnly = false,
  batchItemIds,
  initialClaimId,
}: FactAuditPageProps) {
  const [claims, setClaims] = useState<FactClaim[]>([]);
  const [selectedId, setSelectedId] = useState(initialClaimId ?? "");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [layer, setLayer] = useState("all");
  const [claimType, setClaimType] = useState("all");
  const [auditStatus, setAuditStatus] = useState("all");
  const [stale, setStale] = useState("all");
  const [minimumConfidence, setMinimumConfidence] = useState(0);
  const [sampleSize, setSampleSize] = useState(5);
  const [reason, setReason] = useState("");
  const [fixProposalId, setFixProposalId] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await request<FactClaim[]>(`/versions/${version.id}/fact-claims`);
      setClaims(data);
      setSelectedId((current) =>
        data.some((item) => item.id === current) ? current : (initialClaimId ?? data[0]?.id ?? ""),
      );
    } catch (loadError) {
      setError(messageFrom(loadError));
    } finally {
      setLoading(false);
    }
  }, [initialClaimId, request, version.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const scopedClaims = useMemo(() => {
    const batchSet = batchItemIds ? new Set(batchItemIds) : null;
    return claims.filter((claim) => {
      if (batchSet && !batchSet.has(claim.id)) return false;
      if (layer !== "all" && claim.layer !== layer) return false;
      if (claimType !== "all" && claim.claim_type !== claimType) return false;
      if (auditStatus !== "all" && claim.audit_status !== auditStatus) return false;
      if (stale !== "all" && claim.stale !== (stale === "yes")) return false;
      return claim.confidence >= minimumConfidence;
    });
  }, [auditStatus, batchItemIds, claimType, claims, layer, minimumConfidence, stale]);
  const selected = claims.find((claim) => claim.id === selectedId) ?? scopedClaims[0];
  const counts = useMemo(
    () => ({
      total: claims.length,
      pending: claims.filter((claim) => claim.audit_status === "pending").length,
      approved: claims.filter((claim) => claim.audit_status === "approved").length,
      stale: claims.filter((claim) => claim.stale).length,
    }),
    [claims],
  );

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const data = await request<FactClaim[]>(`/versions/${version.id}/fact-claims:generate`, {
        method: "POST",
      });
      setClaims(data);
      setSelectedId(data[0]?.id ?? "");
      setSuccess(`Generated ${data.length} deterministic facts.`);
    } catch (generateError) {
      setError(messageFrom(generateError));
    } finally {
      setBusy(false);
    }
  }

  async function sample() {
    setBusy(true);
    setError("");
    try {
      const config = Object.fromEntries(layers.map((name) => [name, sampleSize]));
      const data = await request<FactClaim[]>(`/versions/${version.id}/fact-claims:sample`, {
        method: "POST",
        body: JSON.stringify({ config }),
      });
      setClaims(data);
      setSelectedId(data[0]?.id ?? "");
      setSuccess(`Loaded a stratified sample of ${data.length} facts.`);
    } catch (sampleError) {
      setError(messageFrom(sampleError));
    } finally {
      setBusy(false);
    }
  }

  async function review(decision: "approved" | "rejected" | "needs_correction") {
    if (!selected || selected.stale) return;
    if (decision === "rejected" && (!reason.trim() || !fixProposalId.trim())) {
      setError("Reject requires both a reason and a linked fix proposal ID.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await request<FactClaim>(`/fact-claims/${selected.id}/review`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          reason: reason.trim() || null,
          linked_fix_proposal_id: decision === "rejected" ? fixProposalId.trim() : null,
        }),
      });
      setClaims((current) => current.map((claim) => (claim.id === updated.id ? updated : claim)));
      setSuccess(`Fact marked ${decision.replace("_", " ")}.`);
      setReason("");
      setFixProposalId("");
    } catch (reviewError) {
      setError(messageFrom(reviewError));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spin tip="Loading fact audit…" />;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <div className="topBar">
        <div>
          <span className="eyebrow">Review / deterministic facts</span>
          <h1>Fact Audit</h1>
          <div className="crumbTrail">{project.name} / {ontology.name} / v{version.version_number}</div>
        </div>
        <Space wrap>
          <InputNumber min={1} max={100} value={sampleSize} onChange={(value) => setSampleSize(value ?? 5)} />
          <Button onClick={() => void sample()} disabled={busy || claims.length === 0}>Sample</Button>
          <Button icon={<RefreshCw size={15} />} onClick={() => void load()} disabled={busy}>Refresh</Button>
          <Button type="primary" icon={<Sparkles size={15} />} onClick={() => void generate()} disabled={busy || readOnly}>Generate</Button>
        </Space>
      </div>
      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}
      {success && <Alert type="success" showIcon message={success} closable onClose={() => setSuccess("")} />}
      {readOnly && <Alert type="info" showIcon message="This published version is read-only. Fact generation and review are disabled." />}
      <Space wrap size={24}>
        <Statistic title="All facts" value={counts.total} />
        <Statistic title="Pending" value={counts.pending} />
        <Statistic title="Approved" value={counts.approved} />
        <Statistic title="Stale" value={counts.stale} />
      </Space>
      <Card size="small" title="Filters">
        <Space wrap style={{ width: "100%" }}>
          <Select aria-label="Layer" value={layer} onChange={setLayer} style={{ width: 190 }} options={[{ value: "all", label: "All layers" }, ...layers.map((value) => ({ value, label: value.replace(/_/g, " ") }))]} />
          <Select aria-label="Claim type" value={claimType} onChange={setClaimType} style={{ width: 170 }} options={["all", "direct", "inferred", "conflict", "low_confidence"].map((value) => ({ value, label: value === "all" ? "All claim types" : value.replace(/_/g, " ") }))} />
          <Select aria-label="Audit status" value={auditStatus} onChange={setAuditStatus} style={{ width: 170 }} options={["all", "pending", "approved", "rejected", "needs_correction"].map((value) => ({ value, label: value === "all" ? "All audit states" : value.replace(/_/g, " ") }))} />
          <Select aria-label="Stale state" value={stale} onChange={setStale} style={{ width: 150 }} options={[{ value: "all", label: "Fresh and stale" }, { value: "no", label: "Fresh only" }, { value: "yes", label: "Stale only" }]} />
          <InputNumber aria-label="Minimum confidence" min={0} max={1} step={0.05} value={minimumConfidence} onChange={(value) => setMinimumConfidence(value ?? 0)} addonBefore="Confidence ≥" />
        </Space>
      </Card>
      <div className="factAuditLayout">
        <Card title={`Fact queue · ${scopedClaims.length}`} styles={{ body: { padding: 8, maxHeight: 680, overflow: "auto" } }}>
          {scopedClaims.length === 0 ? <Empty description={claims.length ? "No facts match these filters" : "Generate facts to start an audit"} /> : (
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              {scopedClaims.map((claim) => (
                <Button key={claim.id} block type={selected?.id === claim.id ? "primary" : "default"} onClick={() => setSelectedId(claim.id)} style={{ height: "auto", padding: 10, textAlign: "left", whiteSpace: "normal" }}>
                  <Space direction="vertical" size={3} style={{ width: "100%" }}>
                    <Space wrap><Tag>{claim.layer.replace(/_/g, " ")}</Tag><Tag>{claim.claim_type}</Tag>{claim.stale && <Tag color="warning">STALE</Tag>}</Space>
                    <strong>{subjectLabel(claim.subject)} · {claim.predicate}</strong>
                    <Typography.Text type="secondary" ellipsis>{jsonText(claim.value)}</Typography.Text>
                  </Space>
                </Button>
              ))}
            </Space>
          )}
        </Card>
        <Card title="Fact inspector">
          {!selected ? <Empty description="Select a fact" /> : (
            <Space direction="vertical" size={14} style={{ width: "100%" }}>
              {selected.stale && <Alert type="warning" showIcon message="This fact is stale and cannot be reviewed. Regenerate facts from the current graph first." description={selected.stale_reason ?? undefined} />}
              <Space wrap><Tag color={selected.claim_type === "inferred" ? "geekblue" : "green"}>{selected.claim_type.toUpperCase()}</Tag><Tag>{selected.audit_status}</Tag><Tag>{Math.round(selected.confidence * 100)}% confidence</Tag></Space>
              <Descriptions size="small" bordered column={1} items={[
                { key: "subject", label: "Subject", children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.subject)}</pre> },
                { key: "predicate", label: "Predicate", children: selected.predicate },
                { key: "value", label: "Object / value", children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.value)}</pre> },
                { key: "reason", label: "Generated because", children: selected.generation_reason },
                { key: "path", label: "Graph path", children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.graph_path)}</pre> },
                { key: "history", label: "Review record", children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.review_decision)}</pre> },
              ]} />
              <EvidenceExplorer request={request} evidenceIds={selected.evidence_ids} compact />
              <Input.TextArea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Review reason (required for rejection)" disabled={busy || readOnly || selected.stale} />
              <Input value={fixProposalId} onChange={(event) => setFixProposalId(event.target.value)} placeholder="Linked fix proposal ID (required for rejection)" disabled={busy || readOnly || selected.stale} />
              <Space wrap>
                <Button type="primary" icon={<Check size={15} />} onClick={() => void review("approved")} disabled={busy || readOnly || selected.stale}>Approve</Button>
                <Button danger icon={<X size={15} />} onClick={() => void review("rejected")} disabled={busy || readOnly || selected.stale}>Reject</Button>
                <Button onClick={() => void review("needs_correction")} disabled={busy || readOnly || selected.stale}>Needs correction</Button>
              </Space>
            </Space>
          )}
        </Card>
      </div>
    </Space>
  );
}
