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
import { Check, Play, RefreshCw, Search, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
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
  anchor: Record<string, unknown>;
  graph_path: Array<Record<string, unknown>>;
  evidence_ids: string[];
  generation_reason: string;
  confidence: number;
  sensitivity: string;
  access_policy: Record<string, unknown>;
  override_of_claim_id: string | null;
  audit_status: string;
  review_decision: Record<string, unknown>;
  linked_fix_proposal_id: string | null;
  stale: boolean;
  stale_reason: string | null;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
};

type BackgroundRecall = {
  source_type: "background_recall";
  knowledge_id: string;
  text: string;
  summary: string | null;
  tags: string[];
  confidence: number;
  score: number;
  core_fact: boolean;
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
  "entity_assertion",
  "relation_assertion",
  "class_assertion",
  "rule_assertion",
  "rule_derived",
  "rule_validation",
  "workflow",
];

function subjectLabel(subject: Record<string, unknown>, fallback: string): string {
  const name = subject.name;
  if (typeof name === "string" && name) return name;
  const entityId = subject.entity_id;
  if (typeof entityId === "string" && entityId) return entityId;
  return fallback;
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
  const t = useT();
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
  const [backgroundQuery, setBackgroundQuery] = useState("");
  const [backgroundHits, setBackgroundHits] = useState<BackgroundRecall[]>([]);

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
      setSuccess(t("Generated {n} deterministic facts.", { n: data.length }));
    } catch (generateError) {
      setError(messageFrom(generateError));
    } finally {
      setBusy(false);
    }
  }

  async function executeRules() {
    setBusy(true);
    setError("");
    try {
      const data = await request<FactClaim[]>(`/versions/${version.id}/rule-definitions:execute`, {
        method: "POST",
      });
      await load();
      setSelectedId(data[0]?.id ?? selectedId);
      setSuccess(t("Executed active rules and created {n} derived assertions.", { n: data.length }));
    } catch (executeError) {
      setError(messageFrom(executeError));
    } finally {
      setBusy(false);
    }
  }

  async function recallBackground() {
    setBusy(true);
    setError("");
    try {
      const data = await request<BackgroundRecall[]>(`/versions/${version.id}/background-knowledge:recall`, {
        method: "POST",
        body: JSON.stringify({ query: backgroundQuery.trim() || null, limit: 5 }),
      });
      setBackgroundHits(data);
      setSuccess(
        data.length === 1
          ? t("Loaded {n} background recall item.", { n: data.length })
          : t("Loaded {n} background recall items.", { n: data.length }),
      );
    } catch (recallError) {
      setError(messageFrom(recallError));
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
      setSuccess(t("Loaded a stratified sample of {n} facts.", { n: data.length }));
    } catch (sampleError) {
      setError(messageFrom(sampleError));
    } finally {
      setBusy(false);
    }
  }

  async function review(decision: "approved" | "rejected" | "needs_correction") {
    if (!selected || selected.stale) return;
    if (decision === "rejected" && (!reason.trim() || !fixProposalId.trim())) {
      setError(t("Reject requires both a reason and a linked fix proposal ID."));
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
      setSuccess(t("Fact marked {decision}.", { decision: decision.replace("_", " ") }));
      setReason("");
      setFixProposalId("");
    } catch (reviewError) {
      setError(messageFrom(reviewError));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <Spin tip={t("Loading fact audit…")} />;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <div className="topBar">
        <div>
          <span className="eyebrow">{t("Review / deterministic facts")}</span>
          <h1>{t("Fact Audit")}</h1>
          <div className="crumbTrail">{project.name} / {ontology.name} / v{version.version_number}</div>
        </div>
        <Space wrap>
          <InputNumber min={1} max={100} value={sampleSize} onChange={(value) => setSampleSize(value ?? 5)} />
          <Button onClick={() => void sample()} disabled={busy || claims.length === 0}>{t("Sample")}</Button>
          <Button icon={<RefreshCw size={15} />} onClick={() => void load()} disabled={busy}>{t("Refresh")}</Button>
          <Button icon={<Play size={15} />} onClick={() => void executeRules()} disabled={busy || readOnly}>{t("Run rules")}</Button>
          <Button type="primary" icon={<Sparkles size={15} />} onClick={() => void generate()} disabled={busy || readOnly}>{t("Generate")}</Button>
        </Space>
      </div>
      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}
      {success && <Alert type="success" showIcon message={success} closable onClose={() => setSuccess("")} />}
      {readOnly && <Alert type="info" showIcon message={t("This published version is read-only. Fact generation and review are disabled.")} />}
      <Space wrap size={24}>
        <Statistic title={t("All facts")} value={counts.total} />
        <Statistic title={t("Pending")} value={counts.pending} />
        <Statistic title={t("Approved")} value={counts.approved} />
        <Statistic title={t("Stale")} value={counts.stale} />
      </Space>
      <Card size="small" title={t("Filters")}>
        <Space wrap style={{ width: "100%" }}>
          <Select aria-label={t("Layer")} value={layer} onChange={setLayer} style={{ width: 190 }} options={[{ value: "all", label: t("All layers") }, ...layers.map((value) => ({ value, label: value.replace(/_/g, " ") }))]} />
          <Select aria-label={t("Claim type")} value={claimType} onChange={setClaimType} style={{ width: 170 }} options={["all", "direct", "inferred", "conflict", "low_confidence"].map((value) => ({ value, label: value === "all" ? t("All claim types") : value.replace(/_/g, " ") }))} />
          <Select aria-label={t("Audit status")} value={auditStatus} onChange={setAuditStatus} style={{ width: 170 }} options={["all", "pending", "approved", "rejected", "needs_correction"].map((value) => ({ value, label: value === "all" ? t("All audit states") : value.replace(/_/g, " ") }))} />
          <Select aria-label={t("Stale state")} value={stale} onChange={setStale} style={{ width: 150 }} options={[{ value: "all", label: t("Fresh and stale") }, { value: "no", label: t("Fresh only") }, { value: "yes", label: t("Stale only") }]} />
          <InputNumber aria-label={t("Minimum confidence")} min={0} max={1} step={0.05} value={minimumConfidence} onChange={(value) => setMinimumConfidence(value ?? 0)} addonBefore={t("Confidence ≥")} />
        </Space>
      </Card>
      <Card size="small" title={t("Background recall")}>
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Space.Compact style={{ width: "100%" }}>
            <Input value={backgroundQuery} onChange={(event) => setBackgroundQuery(event.target.value)} placeholder={t("Search unanchored knowledge without treating it as governed fact")} />
            <Button icon={<Search size={15} />} onClick={() => void recallBackground()} disabled={busy}>{t("Recall")}</Button>
          </Space.Compact>
          {backgroundHits.length > 0 && (
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              {backgroundHits.map((item) => (
                <Card size="small" key={item.knowledge_id}>
                  <Space direction="vertical" size={4} style={{ width: "100%" }}>
                    <Space wrap><Tag color="blue">{t("background_recall")}</Tag><Tag>{t("{pct}% confidence", { pct: Math.round(item.confidence * 100) })}</Tag>{item.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</Space>
                    <Typography.Text>{item.summary || item.text}</Typography.Text>
                    {item.summary && <Typography.Text type="secondary">{item.text}</Typography.Text>}
                  </Space>
                </Card>
              ))}
            </Space>
          )}
        </Space>
      </Card>
      <div className="factAuditLayout">
        <Card title={t("Fact queue · {n}", { n: scopedClaims.length })} styles={{ body: { padding: 8, maxHeight: 680, overflow: "auto" } }}>
          {scopedClaims.length === 0 ? <Empty description={claims.length ? t("No facts match these filters") : t("Generate facts to start an audit")} /> : (
            <Space direction="vertical" size={6} style={{ width: "100%" }}>
              {scopedClaims.map((claim) => (
                <Button key={claim.id} block type={selected?.id === claim.id ? "primary" : "default"} onClick={() => setSelectedId(claim.id)} style={{ height: "auto", padding: 10, textAlign: "left", whiteSpace: "normal" }}>
                  <Space direction="vertical" size={3} style={{ width: "100%" }}>
                    <Space wrap><Tag>{claim.layer.replace(/_/g, " ")}</Tag><Tag>{claim.claim_type}</Tag>{claim.stale && <Tag color="warning">{t("STALE")}</Tag>}</Space>
                    <strong>{subjectLabel(claim.subject, t("Structured subject"))} · {claim.predicate}</strong>
                    <Typography.Text type="secondary" ellipsis>{jsonText(claim.value)}</Typography.Text>
                  </Space>
                </Button>
              ))}
            </Space>
          )}
        </Card>
        <Card title={t("Fact inspector")}>
          {!selected ? <Empty description={t("Select a fact")} /> : (
            <Space direction="vertical" size={14} style={{ width: "100%" }}>
              {selected.stale && <Alert type="warning" showIcon message={t("This fact is stale and cannot be reviewed. Regenerate facts from the current graph first.")} description={selected.stale_reason ?? undefined} />}
              <Space wrap><Tag color={selected.claim_type === "inferred" ? "geekblue" : "green"}>{selected.claim_type.toUpperCase()}</Tag><Tag>{selected.audit_status}</Tag><Tag>{t("{pct}% confidence", { pct: Math.round(selected.confidence * 100) })}</Tag></Space>
              <Descriptions size="small" bordered column={1} items={[
                { key: "subject", label: t("Subject"), children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.subject)}</pre> },
                { key: "predicate", label: t("Predicate"), children: selected.predicate },
                { key: "value", label: t("Object / value"), children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.value)}</pre> },
                { key: "anchor", label: t("Anchor"), children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.anchor)}</pre> },
                { key: "policy", label: t("Sensitivity / access"), children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText({ sensitivity: selected.sensitivity, access_policy: selected.access_policy })}</pre> },
                { key: "override", label: t("Override"), children: selected.override_of_claim_id ?? t("None") },
                { key: "reason", label: t("Generated because"), children: selected.generation_reason },
                { key: "path", label: t("Graph path"), children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.graph_path)}</pre> },
                { key: "history", label: t("Review record"), children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{jsonText(selected.review_decision)}</pre> },
              ]} />
              <EvidenceExplorer request={request} evidenceIds={selected.evidence_ids} compact />
              <Input.TextArea value={reason} onChange={(event) => setReason(event.target.value)} placeholder={t("Review reason (required for rejection)")} disabled={busy || readOnly || selected.stale} />
              <Input value={fixProposalId} onChange={(event) => setFixProposalId(event.target.value)} placeholder={t("Linked fix proposal ID (required for rejection)")} disabled={busy || readOnly || selected.stale} />
              <Space wrap>
                <Button type="primary" icon={<Check size={15} />} onClick={() => void review("approved")} disabled={busy || readOnly || selected.stale}>{t("Approve")}</Button>
                <Button danger icon={<X size={15} />} onClick={() => void review("rejected")} disabled={busy || readOnly || selected.stale}>{t("Reject")}</Button>
                <Button onClick={() => void review("needs_correction")} disabled={busy || readOnly || selected.stale}>{t("Needs correction")}</Button>
              </Space>
            </Space>
          )}
        </Card>
      </div>
    </Space>
  );
}
