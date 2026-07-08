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
 *   - missing_evidence → facts whose evidence_bindings list is empty
 *
 * Toolbar actions:
 *   - Generate  → POST /graph-sets/{gs}/reasoning-runs + /rule-runs (async,
 *                 polled until both settle, then refetch)
 *   - Run rules → POST /graph-sets/{gs}/rule-runs only
 *   - Refresh   → invalidate local cache and refetch
 *
 * Selected facts can be edited/deleted through the canonical-write command
 * path. Phase 8 routes evidence bind/unbind through the dedicated
 * ``/graph-sets/{gs}/fact-evidence`` REST endpoints (see semanticApi.ts).
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
  Space,
  Spin,
  Tag,
} from "antd";
import { Edit3, FileText, Play, Plus, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useT } from "../i18n";
import {
  bindFactEvidence,
  compileAndApplyProductCommand,
  getReasoningRun,
  getRuleRun,
  readModel,
  runGraphSetReasoning,
  runGraphSetRules,
  unbindFactEvidence,
} from "../semanticApi";
import { EvidenceChunkPicker } from "../components/semantic";
import type { EvidenceBinding } from "../types";
import type { WorkbenchRequest } from "./workbenchTypes";

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
  object_is_iri: boolean;
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
  const [editOpen, setEditOpen] = useState(false);
  const [editObjectValue, setEditObjectValue] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
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

  function openEdit() {
    if (!selected) return;
    setEditObjectValue(factObjectText(selected));
    setEditOpen(true);
  }

  async function submitEdit() {
    if (!selected) return;
    if (!editObjectValue.trim()) {
      setError(t("Object / value is required."));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await compileAndApplyProductCommand(request, {
        command_kind: "update_fact",
        payload: {
          ontology_id: ontologyId,
          subject_iri: selected.subject_iri,
          predicate_iri: selected.predicate_iri,
          old_object_value: selected.object_value,
          old_object_is_iri: selected.object_is_iri,
          new_object_value: editObjectValue.trim(),
          new_object_is_iri: selected.object_is_iri,
          graph_iri: selected.graph_iri,
        },
        graph_set_id: graphSetId,
        actor: "user:facts-page",
        reason: "Update fact from Facts page",
      });
      setSuccess(t("Fact updated."));
      setEditOpen(false);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function deleteSelected() {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      await compileAndApplyProductCommand(request, {
        command_kind: "delete_fact",
        payload: {
          ontology_id: ontologyId,
          subject_iri: selected.subject_iri,
          predicate_iri: selected.predicate_iri,
          object_value: selected.object_value,
          object_is_iri: selected.object_is_iri,
          graph_iri: selected.graph_iri,
        },
        graph_set_id: graphSetId,
        actor: "user:facts-page",
        reason: "Delete fact from Facts page",
      });
      setSuccess(t("Fact deleted."));
      setSelectedId(null);
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function addEvidence(
    text: string,
    meta?: { document_filename?: string; sequence?: number },
  ) {
    if (!selected || !text.trim()) return;
    setBusy(true);
    setError("");
    try {
      // Phase 8 §3 — bind text evidence via the dedicated fact-evidence
      // endpoint (replaces the legacy bind_fact_evidence_text canonical
      // write command, which has been removed). The backend resolves the
      // subject/predicate/object triple plus ontology id to a fact_id.
      await bindFactEvidence(request, graphSetId, {
        ontology_id: ontologyId,
        subject_iri: selected.subject_iri,
        predicate_iri: selected.predicate_iri,
        object_value: stringifyFactObjectValue(selected.object_value, selected.object_is_iri),
        object_is_iri: selected.object_is_iri,
        graph_iri: selected.graph_iri,
        fact_id: selected.fact_id,
        text,
        document_filename: meta?.document_filename,
        sequence: meta?.sequence,
        actor: "user:facts-page",
        reason: "Bind text evidence from Facts page",
      });
      setSuccess(t("Evidence bound."));
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function removeEvidence(binding: EvidenceBinding) {
    if (!selected) return;
    const bindingId = binding.id;
    if (!bindingId) {
      // Legacy read-model rows (no Phase 8 id) cannot be removed via the
      // new endpoint — surface a clear error rather than silently failing.
      setError(t("This evidence binding cannot be removed (missing id)."));
      return;
    }
    setBusy(true);
    setError("");
    try {
      // Phase 8 §3 — DELETE /fact-evidence/{binding_id} replaces the old
      // unbind_fact_evidence canonical write command (which keyed off
      // chunk_iri). Idempotent on the backend.
      await unbindFactEvidence(request, graphSetId, bindingId);
      setSuccess(t("Evidence unbound."));
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
                {selected.stale && <Tag color="warning">{t("STALE")}</Tag>}
                {(selected.evidence_bindings ?? []).length === 0 && (
                  <Tag color="warning">{t("missing evidence")}</Tag>
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
                title={t("Evidence · {n} binding(s)", {
                  n: (selected.evidence_bindings ?? []).length,
                })}
                aria-label="fact-evidence-explorer"
              >
                <EvidenceBindingEditor
                  bindings={selected.evidence_bindings ?? []}
                  onAdd={() => setPickerOpen(true)}
                  onRemove={(binding) => void removeEvidence(binding)}
                  disabled={busy || readOnly}
                />
              </Card>
              <Space wrap>
                <Button
                  icon={<Edit3 size={15} />}
                  onClick={openEdit}
                  disabled={busy || readOnly || selected.stale}
                >
                  {t("Edit")}
                </Button>
                <Button
                  danger
                  icon={<Trash2 size={15} />}
                  onClick={() => {
                    Modal.confirm({
                      title: t("Delete fact?"),
                      content: factLine(selected),
                      okText: t("Delete"),
                      okButtonProps: { danger: true },
                      onOk: () => deleteSelected(),
                    });
                  }}
                  disabled={busy || readOnly || selected.stale}
                >
                  {t("Delete")}
                </Button>
              </Space>
            </Space>
          )}
        </Card>
      </div>

      <Modal
        title={t("Edit fact")}
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => void submitEdit()}
        confirmLoading={busy}
        okText={t("Save")}
        okButtonProps={{ disabled: !editObjectValue.trim() }}
      >
        <Space direction="vertical" size={10} style={{ width: "100%" }}>
          {selected && <ModalFactLine>{factLine(selected)}</ModalFactLine>}
          <Input.TextArea
            value={editObjectValue}
            onChange={(event) => setEditObjectValue(event.target.value)}
            placeholder={t("Object / value")}
            autoSize={{ minRows: 2, maxRows: 6 }}
          />
        </Space>
      </Modal>

      {selected && (
        <EvidenceChunkPicker
          open={pickerOpen}
          factId={selected.fact_id}
          onClose={() => setPickerOpen(false)}
          onSubmit={async (text, meta) => {
            await addEvidence(text, meta);
          }}
        />
      )}
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
          title={factLineFull(row)}
          style={{ height: "auto", padding: 10, textAlign: "left", whiteSpace: "normal" }}
        >
          <span className="factListLine">{factLine(row)}</span>
        </Button>
      ))}
    </Space>
  );
}

function EvidenceBindingEditor({
  bindings,
  onAdd,
  onRemove,
  disabled,
}: {
  bindings: EvidenceBinding[];
  onAdd: () => void;
  onRemove: (binding: EvidenceBinding) => void;
  disabled: boolean;
}) {
  const t = useT();
  return (
    <Space direction="vertical" size={10} style={{ width: "100%" }}>
      {bindings.length === 0 ? (
        <Empty image={<FileText size={28} />} description={t("No evidence binding for this fact.")} />
      ) : (
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          {bindings.map((binding) => {
            // Phase 8 — bindings now carry a stable ``id``; fall back to the
            // legacy chunk_iri for unmigrated read-model rows.
            const rowKey = binding.id ?? binding.chunk_iri ?? binding.fact_id ?? "";
            const preview = binding.text_preview ?? binding.text ?? "";
            return (
              <div
                key={rowKey}
                className="evidenceBindingRow"
                aria-label={`evidence-binding-${rowKey}`}
              >
                <div className="evidenceBindingHeader">
                  <FileText size={14} />
                  <strong>{binding.document_filename ?? t("Text evidence")}</strong>
                  {typeof binding.sequence === "number" && <Tag>#{binding.sequence}</Tag>}
                  <Button
                    danger
                    size="small"
                    icon={<Trash2 size={13} />}
                    onClick={() => onRemove(binding)}
                    disabled={disabled}
                  >
                    {t("Delete")}
                  </Button>
                </div>
                <p className="factEvidenceText">{preview}</p>
              </div>
            );
          })}
        </Space>
      )}
      <Button
        icon={<Plus size={15} />}
        onClick={onAdd}
        disabled={disabled}
      >
        {t("Add evidence")}
      </Button>
    </Space>
  );
}

function shortenIri(iri: string): string {
  if (!iri) return "";
  const idx = Math.max(iri.lastIndexOf("#"), iri.lastIndexOf("/"));
  return idx >= 0 ? iri.slice(idx + 1) : iri;
}

/** Display form for an RDF term: prefer the human-readable label; when it
 *  is missing, fall back to the IRI's local name (fragment or last path
 *  segment) so long property IRIs do not blow up the one-line queue
 *  entries. Literals without a label pass through unchanged. */
function termDisplay(label: string | null, iri: string): string {
  if (label) return label;
  return iri ? shortenIri(iri) : "";
}

function factObjectText(row: FactRow) {
  if (typeof row.object_value === "string") {
    if (row.object_label) return row.object_label;
    if (row.object_is_iri) return shortenIri(row.object_value);
    return row.object_value;
  }
  return JSON.stringify(row.object_value);
}

/** Compact one-liner used as the queue button label. Falls back to the
 *  local name of any term whose ``rdfs:label`` is missing. */
function factLine(row: FactRow) {
  return `${termDisplay(row.subject_label, row.subject_iri)} → ${termDisplay(row.predicate_label, row.predicate_iri)} → ${factObjectText(row)}`;
}

/** Full-form one-liner (no shortening) used as the button hover tooltip so
 *  users can still recover complete IRIs on demand. */
function factLineFull(row: FactRow) {
  const objectText =
    typeof row.object_value === "string"
      ? (row.object_label ?? row.object_value)
      : JSON.stringify(row.object_value);
  return `${row.subject_label ?? row.subject_iri} → ${row.predicate_label ?? row.predicate_iri} → ${objectText}`;
}

/**
 * Phase 8 §3 — coerce a FactRow's typed ``object_value`` (rendered by the
 * read model as either a string or a JSON literal) into the canonical
 * string form expected by ``bindFactEvidence``. For IRI-typed objects we
 * prefer the raw IRI (``object_value`` already carries it when
 * ``object_is_iri`` is true); for literals we fall back to the existing
 * display rendering to preserve the user-visible form.
 */
function stringifyFactObjectValue(value: unknown, isIri: boolean): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  if (isIri && typeof value === "object" && value !== null && "value" in value) {
    const inner = (value as { value?: unknown }).value;
    if (typeof inner === "string") return inner;
  }
  return JSON.stringify(value);
}

function ModalFactLine({ children }: { children: string }) {
  return <div className="factModalLine">{children}</div>;
}

function FactTerm({ iri, label }: { iri: string; label: string | null }) {
  return <span>{label ?? iri}</span>;
}

export type { FactAuditPageProps };
