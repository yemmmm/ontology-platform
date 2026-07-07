/**
 * Stage 2 §6 — graph-derived FactAuditPage.
 *
 * The fact queue is sourced from the fact-audit-queue read-model composer
 * (backend/app/services/semantic_read_model.py::_compose_fact_audit_queue).
 * The composer routes by ``?kind=`` query parameter:
 *
 *   - asserted         → graph/data/{ontology_id}
 *   - inferred         → effective reasoning-result graph
 *   - rule_derived     → effective rule-result graph
 *   - missing_evidence → asserted_data rows carrying op:evidenceStatus
 *
 * Toolbar actions:
 *   - Generate  → POST /graph-sets/{gs}/reasoning-runs + /rule-runs (async,
 *                 polled until both settle, then refetch)
 *   - Run rules → POST /graph-sets/{gs}/rule-runs only
 *   - Refresh   → invalidate local cache and refetch
 *
 * Review on a selected fact calls ``compileAndApplyProductCommand`` with
 * ``command_kind: review_assertion`` (Stage 2 §6.4).
 *
 * Legacy inline implementation retained as ``FactAuditPage.legacy.tsx``
 * and dispatched from App.tsx when no ``?graphSet=`` URL parameter is set.
 */

import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Input,
  Modal,
  Segmented,
  Skeleton,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { Check, Edit3, Play, Plus, RefreshCw, Sparkles, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import {
  compileAndApplyProductCommand,
  getReasoningRun,
  getRuleRun,
  readModel,
  runGraphSetReasoning,
  runGraphSetRules,
} from "../semanticApi";
import type { EvidenceBinding } from "../types";
import type { WorkbenchRequest } from "./workbenchTypes";
import { EvidenceExplorerPanel } from "../components/semantic/EvidenceExplorerPanel";

type AssertionKind = "asserted" | "inferred" | "rule_derived" | "missing_evidence";

/**
 * Local envelope type for FactAuditPage rendering. The backend
 * ``fact-audit-queue`` composer decorates each row into the unified
 * FactRow shape (spec §6.3), which differs from the generic
 * SemanticStatementItem projected by other read models.
 */
type FactEnvelope = {
  graph_set_id: string;
  source_signature: string;
  projection_version: string;
  model_name: string;
  include: string;
  derived_state: Record<string, unknown>;
  warnings: Array<{ code: string; message: string }>;
  items: FactRow[];
};

type FactRow = {
  id: string;
  fact_id: string;
  assertion_kind: AssertionKind;
  subject_iri: string;
  subject_label: string | null;
  predicate_iri: string;
  predicate_label: string | null;
  object_value: unknown;
  object_label: string | null;
  graph_iri: string;
  source_graph_iri: string;
  evidence_status: "with_evidence" | "missing_evidence" | "not_applicable";
  audit_status: "pending" | "approved" | "rejected" | "needs_correction";
  stale: boolean;
  stale_reason: string | null;
  derived_from?: { run_id: string; rule_id?: string; rule_version?: string; reason?: string };
  /** Stage 4 §4.4 — populated when ``field_set=evidence`` is passed.
   * Empty array means no ``prov:wasDerivedFrom`` triple exists for this
   * fact; the drawer falls back to the "missing evidence" empty state. */
  evidence_bindings?: EvidenceBinding[];
};

type FactAuditPageProps = {
  graphSetId: string;
  ontologyId: string;
  readOnly: boolean;
  request: WorkbenchRequest;
};

const KIND_OPTIONS: Array<{ label: string; value: AssertionKind }> = [
  { label: "Asserted", value: "asserted" },
  { label: "Inferred", value: "inferred" },
  { label: "Rule-derived", value: "rule_derived" },
  { label: "Missing evidence", value: "missing_evidence" },
];

const INCLUDE_FOR_KIND: Record<AssertionKind, string> = {
  asserted: "asserted",
  missing_evidence: "asserted",
  inferred: "asserted-plus-reasoning",
  rule_derived: "asserted-plus-rules",
};

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 60_000;

export function FactAuditPage({ graphSetId, ontologyId, readOnly, request }: FactAuditPageProps) {
  const t = useT();
  const [kind, setKind] = useState<AssertionKind>("asserted");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [items, setItems] = useState<FactRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reviewReason, setReviewReason] = useState("");
  const [fixProposalId, setFixProposalId] = useState("");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewDecision, setReviewDecision] = useState<"approved" | "rejected" | "needs_correction">("approved");
  const [warnings, setWarnings] = useState<Array<{ code: string; message: string }>>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const envelope = await readModel<FactEnvelope>(
        request,
        graphSetId,
        "fact-audit-queue",
        // Stage 4 §4.4 — pass field_set=evidence so every row carries
        // an ``evidence_bindings`` array (possibly empty) for the
        // inspector drawer to render via EvidenceExplorerPanel.
        { kind, include: INCLUDE_FOR_KIND[kind], fieldSet: "evidence" },
      );
      const rows = envelope.items ?? [];
      setItems(rows);
      setWarnings(envelope.warnings ?? []);
      setSelectedId((current) => {
        if (current && rows.some((row) => row.id === current)) return current;
        return rows[0]?.id ?? null;
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [graphSetId, kind, request]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => items.find((row) => row.id === selectedId) ?? null,
    [items, selectedId],
  );

  function openReview(decision: "approved" | "rejected" | "needs_correction") {
    if (!selected) return;
    setReviewDecision(decision);
    setReviewReason("");
    setFixProposalId("");
    setReviewOpen(true);
  }

  async function submitReview() {
    if (!selected) return;
    if (reviewDecision === "rejected" && (!reviewReason.trim() || !fixProposalId.trim())) {
      setError(t("Reject requires both a reason and a linked fix proposal ID."));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await compileAndApplyProductCommand(request, {
        command_kind: "review_assertion",
        payload: {
          ontology_id: ontologyId,
          assertion_kind: selected.assertion_kind,
          subject_iri: selected.subject_iri,
          predicate_iri: selected.predicate_iri,
          object_value: selected.object_value,
          decision: reviewDecision,
          reason: reviewReason.trim() || "",
          linked_fix_proposal_id: reviewDecision === "rejected" ? fixProposalId.trim() : null,
          result_graph_iri:
            selected.assertion_kind === "inferred" || selected.assertion_kind === "rule_derived"
              ? selected.graph_iri
              : undefined,
        },
        graph_set_id: graphSetId,
        actor: "user:stage2-fact-audit",
        reason: reviewReason.trim() || `Stage 2 FactAuditPage review: ${reviewDecision}`,
      });
      setSuccess(t("Fact marked {decision}.", { decision: reviewDecision.replace("_", " ") }));
      setReviewOpen(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function pollRun(
    runId: string,
    isReasoning: boolean,
  ): Promise<{ status: string; error: string | null }> {
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    while (Date.now() < deadline) {
      try {
        const run = isReasoning
          ? await getReasoningRun(request, runId)
          : await getRuleRun(request, runId);
        const status = (run as { status?: string }).status ?? "running";
        if (status === "succeeded" || status === "completed" || status === "failed" || status === "error") {
          return { status, error: (run as { error?: string | null }).error ?? null };
        }
      } catch {
        // Swallow transient poll errors — keep polling until deadline.
      }
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
    return { status: "timeout", error: "Polling timed out" };
  }

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const reasoningRun = await runGraphSetReasoning(request, graphSetId, {
        tasks: ["consistency", "classification"],
        persistResultGraph: true,
      });
      const ruleRun = await runGraphSetRules(request, graphSetId, {
        promotePointer: true,
      });
      const reasoningId = (reasoningRun as { run_id?: string }).run_id;
      const ruleId = (ruleRun as { run_id?: string }).run_id;
      const polled: Array<{ label: string; status: string; error: string | null }> = [];
      if (reasoningId) {
        polled.push({ label: "reasoning", ...(await pollRun(reasoningId, true)) });
      }
      if (ruleId) {
        polled.push({ label: "rule", ...(await pollRun(ruleId, false)) });
      }
      const failures = polled.filter((p) => p.status === "failed" || p.status === "error" || p.status === "timeout");
      if (failures.length > 0) {
        setError(
          t("Some runs failed: {summary}", {
            summary: failures.map((f) => `${f.label}=${f.status}`).join(", "),
          }),
        );
      } else {
        setSuccess(t("Generate complete. Reasoning and rule runs finished."));
      }
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function runRules() {
    setBusy(true);
    setError("");
    try {
      const ruleRun = await runGraphSetRules(request, graphSetId, {
        promotePointer: true,
      });
      const ruleId = (ruleRun as { run_id?: string }).run_id;
      if (ruleId) {
        const result = await pollRun(ruleId, false);
        if (result.status === "failed" || result.status === "error" || result.status === "timeout") {
          setError(t("Rule run {status}: {error}", { status: result.status, error: result.error ?? "?" }));
        } else {
          setSuccess(t("Rule run finished."));
        }
      }
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  const counts = useMemo(() => {
    return {
      total: items.length,
      pending: items.filter((row) => row.audit_status === "pending").length,
      approved: items.filter((row) => row.audit_status === "approved").length,
      stale: items.filter((row) => row.stale).length,
    };
  }, [items]);

  if (loading) return <Spin tip={t("Loading fact audit…")} />;

  return (
    <section className="factAuditPage stage2">
      <header className="topBar">
        <div>
          <span className="eyebrow">{t("Business modeling")}</span>
          <h1>{t("Facts")}</h1>
          <div className="crumbTrail">
            <span>{t("Fact list")}</span>
          </div>
        </div>
        <Space wrap>
          <Button icon={<RefreshCw size={15} />} onClick={() => void load()} disabled={busy}>
            {t("Refresh")}
          </Button>
          <Button icon={<Play size={15} />} onClick={() => void runRules()} disabled={busy || readOnly}>
            {t("Run rules")}
          </Button>
          <Button
            type="primary"
            icon={<Sparkles size={15} />}
            onClick={() => void generate()}
            disabled={busy || readOnly}
            title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : undefined}
          >
            {t("Generate")}
          </Button>
          <Button
            icon={<Plus size={15} />}
            disabled
            title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Fact creation is not available from the current API yet.")}
          >
            {t("New fact")}
          </Button>
        </Space>
      </header>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError("")} />}
      {success && <Alert type="success" showIcon message={success} closable onClose={() => setSuccess("")} />}
      {readOnly && (
        <Alert
          type="info"
          showIcon
          message={t("Workspace is locked. Unlock in Settings to edit modeling data.")}
        />
      )}
      {warnings.map((w, idx) => (
        <Alert
          key={`${w.code}-${idx}`}
          type="warning"
          showIcon
          message={w.message}
          description={w.code}
        />
      ))}

      <Space wrap size={24}>
        <Statistic label={t("Total in tab")} value={counts.total} />
        <Statistic label={t("Pending")} value={counts.pending} />
        <Statistic label={t("Approved")} value={counts.approved} />
        <Statistic label={t("Stale")} value={counts.stale} />
      </Space>

      <Card size="small" title={t("Fact kind")}>
        <Segmented
          value={kind}
          onChange={(value) => setKind(value as AssertionKind)}
          options={KIND_OPTIONS}
        />
      </Card>

      <div className="factAuditLayout">
        <Card
          title={t("Fact queue · {n}", { n: items.length })}
          styles={{ body: { padding: 8, maxHeight: 680, overflow: "auto" } }}
        >
          <FactQueue
            rows={items}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </Card>
        <Card title={t("Fact inspector")}>
          {!selected ? (
            <Empty description={t("Select a fact")} />
          ) : (
            <Space direction="vertical" size={14} style={{ width: "100%" }}>
              {selected.stale && (
                <Alert
                  type="warning"
                  showIcon
                  message={t("This fact is stale. Run a new Generate to refresh.")}
                  description={selected.stale_reason ?? undefined}
                />
              )}
              <Space wrap>
                <Tag color={selected.assertion_kind === "inferred" ? "geekblue" : selected.assertion_kind === "rule_derived" ? "purple" : "green"}>
                  {selected.assertion_kind.toUpperCase()}
                </Tag>
                <Tag>{selected.audit_status}</Tag>
                {selected.evidence_status === "missing_evidence" && (
                  <Tag color="warning">⚠ {t("missing evidence")}</Tag>
                )}
              </Space>
              <Descriptions
                size="small"
                bordered
                column={1}
                items={[
                  { key: "subject", label: t("Subject"), children: <FactTerm iri={selected.subject_iri} label={selected.subject_label} /> },
                  { key: "predicate", label: t("Predicate"), children: <FactTerm iri={selected.predicate_iri} label={selected.predicate_label} /> },
                  { key: "object", label: t("Object / value"), children: <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{JSON.stringify(selected.object_value, null, 2)}</pre> },
                  ...(selected.derived_from
                    ? [{ key: "derived", label: t("Derived from"), children: <span>{selected.derived_from.run_id}</span> }]
                    : []),
                ]}
              />
              <Card
                size="small"
                title={t("Evidence explorer · {n} binding(s)", {
                  n: (selected.evidence_bindings ?? []).length,
                })}
                aria-label="fact-evidence-explorer"
              >
                <EvidenceExplorerPanel
                  bindings={selected.evidence_bindings ?? []}
                  hideMissingTag={selected.assertion_kind !== "asserted"}
                />
              </Card>
              <Space wrap>
                <Button
                  icon={<Edit3 size={15} />}
                  disabled
                  title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Fact editing is not available from the current API yet.")}
                >
                  {t("Edit")}
                </Button>
                <Button
                  danger
                  icon={<Trash2 size={15} />}
                  disabled
                  title={readOnly ? t("Workspace is locked. Unlock in Settings to edit modeling data.") : t("Fact deletion is not available from the current API yet.")}
                >
                  {t("Delete")}
                </Button>
                <Button
                  type="primary"
                  icon={<Check size={15} />}
                  onClick={() => openReview("approved")}
                  disabled={busy || readOnly || selected.stale}
                >
                  {t("Approve")}
                </Button>
                <Button
                  danger
                  icon={<X size={15} />}
                  onClick={() => openReview("rejected")}
                  disabled={busy || readOnly || selected.stale}
                >
                  {t("Reject")}
                </Button>
                <Button
                  onClick={() => openReview("needs_correction")}
                  disabled={busy || readOnly || selected.stale}
                >
                  {t("Needs correction")}
                </Button>
              </Space>
            </Space>
          )}
        </Card>
      </div>

      <Modal
        title={t("Review fact · {decision}", { decision: reviewDecision.replace("_", " ") })}
        open={reviewOpen}
        onCancel={() => setReviewOpen(false)}
        onOk={() => void submitReview()}
        confirmLoading={busy}
        okText={t("Submit review")}
        okButtonProps={{
          disabled:
            reviewDecision === "rejected" && (!reviewReason.trim() || !fixProposalId.trim()),
        }}
      >
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          <Input.TextArea
            value={reviewReason}
            onChange={(event) => setReviewReason(event.target.value)}
            placeholder={t("Review reason (required for rejection)")}
            autoSize={{ minRows: 2, maxRows: 4 }}
          />
          <Input
            value={fixProposalId}
            onChange={(event) => setFixProposalId(event.target.value)}
            placeholder={t("Linked fix proposal ID (required for rejection)")}
          />
        </Space>
      </Modal>
    </section>
  );
}

function Statistic({ label, value }: { label: string; value: number }) {
  return (
    <div className="stage2Statistic">
      <div className="stage2StatisticLabel">{label}</div>
      <div className="stage2StatisticValue">{value}</div>
    </div>
  );
}

function FactQueue({
  rows,
  selectedId,
  onSelect,
}: {
  rows: FactRow[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const t = useT();
  if (rows.length === 0) {
    return <Empty description={t("No facts in this kind. Run Generate or switch tabs.")} />;
  }
  return (
    <Space direction="vertical" size={6} style={{ width: "100%" }}>
      {rows.map((row) => (
        <Button
          key={row.id}
          block
          type={selectedId === row.id ? "primary" : "default"}
          onClick={() => onSelect(row.id)}
          style={{ height: "auto", padding: 10, textAlign: "left", whiteSpace: "normal" }}
        >
          <Space direction="vertical" size={3} style={{ width: "100%" }}>
            <Space wrap>
              <Tag>{row.assertion_kind.replace(/_/g, " ")}</Tag>
              <Tag>{row.audit_status}</Tag>
              {row.stale && <Tag color="warning">{t("STALE")}</Tag>}
              {row.evidence_status === "missing_evidence" && (
                <Tag color="warning">⚠ {t("missing evidence")}</Tag>
              )}
            </Space>
            <strong>
              {row.subject_label ?? row.subject_iri} · {row.predicate_label ?? row.predicate_iri}
            </strong>
            <Typography.Text type="secondary" ellipsis>
              {typeof row.object_value === "string"
                ? row.object_value
                : JSON.stringify(row.object_value)}
            </Typography.Text>
          </Space>
        </Button>
      ))}
    </Space>
  );
}

function FactTerm({ iri, label }: { iri: string; label: string | null }) {
  return <span>{label ?? iri}</span>;
}

export type { FactAuditPageProps };
