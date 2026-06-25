import { Braces, Check, Clipboard, GitBranch, Play, RefreshCw, Save, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EvidenceExplorer } from "./EvidenceExplorer";
import type {
  ClassDef,
  JsonObject,
  KnowledgeConflict,
  Ontology,
  Proposal,
  ProposalItem,
  ReviewBatch,
} from "../types";
import { compactId, formatDate, prettyJson, splitCsv } from "../utils";
import { Badge, EmptyState, classNames } from "./_primitives";
import { useReviewPref } from "./_reviewPrefs";
import type { WorkbenchRequest } from "./workbenchTypes";

function queryValue(name: string) {
  try {
    return new URLSearchParams(window.location.search).get(name) ?? "";
  } catch {
    return "";
  }
}

export function SchemaReviewPage(props: {
  ontology: Ontology;
  classes: ClassDef[];
  request: WorkbenchRequest;
  reloadSchema: () => Promise<void>;
  batchId?: string;
  versionId: string;
}) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [editingKey, setEditingKey] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState<ReviewBatch | null>(null);
  const [autoValidatedIds, setAutoValidatedIds] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    const [data, batchData] = await Promise.all([
      props.request<Proposal[]>(`/ontologies/${props.ontology.id}/proposals?proposal_type=schema_change`),
      props.batchId ? props.request<ReviewBatch>(`/review-batches/${props.batchId}`) : Promise.resolve(null),
    ]);
    if (batchData && (batchData.ontology_id !== props.ontology.id || batchData.ontology_version_id !== props.versionId || batchData.review_type !== "schema")) {
      throw new Error("This review batch does not belong to the selected ontology version or schema review type.");
    }
    setBatch(batchData);
    setProposals(data);
    setSelectedId((current) => {
      const batchProposalId = batchData?.stable_key.startsWith("proposal:") ? batchData.stable_key.slice(9) : "";
      if (batchProposalId) return batchProposalId;
      const requested = queryValue("proposal");
      if (current && data.some((item) => item.id === current)) return current;
      return data.some((item) => item.id === requested) ? requested : data[0]?.id || "";
    });
  }, [props.batchId, props.ontology.id, props.request, props.versionId]);

  useEffect(() => {
    load().catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
  }, [load]);

  const selected = proposals.find((proposal) => proposal.id === selectedId) ?? null;
  const items = (selected?.payload.items ?? []).filter((item) => !batch || batch.item_ids.includes(item.key));
  const classNamesById = useMemo(
    () => new Map(props.classes.map((classDef) => [classDef.id, classDef.name])),
    [props.classes],
  );
  const pendingItems = items.filter((item) => !item.review_status || item.review_status === "pending");
  const [autoApplyOnApprove, setAutoApplyOnApprove] = useReviewPref("autoApplyOnApprove", true);

  useEffect(() => {
    if (!selected || selected.status !== "proposed") return;
    if (autoValidatedIds.has(selected.id)) return;
    const timer = setTimeout(() => {
      setAutoValidatedIds((current) => new Set(current).add(selected.id));
      void run(async () => {
        await props.request(`/proposals/${selected.id}/validate`, { method: "POST" });
      });
    }, 200);
    return () => clearTimeout(timer);
  }, [selected?.id, selected?.status, autoValidatedIds]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  function reviewItem(itemKey: string, action: "approved" | "rejected") {
    if (!selected) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/${encodeURIComponent(itemKey)}/review`, {
        method: "POST",
        body: JSON.stringify({ action, reviewer_type: "user" }),
      });
    });
  }

  function batchReview(action: "approved" | "rejected") {
    if (!selected || !selectedKeys.length) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/review`, {
        method: "POST",
        body: JSON.stringify({ item_keys: selectedKeys, action, reviewer_type: "user" }),
      });
      setSelectedKeys([]);
    });
  }

  function saveEdit(item: ProposalItem) {
    if (!selected) return;
    let data: JsonObject;
    try {
      data = JSON.parse(editorValue) as JsonObject;
    } catch {
      setError("Edited item data must be valid JSON.");
      return;
    }
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/${encodeURIComponent(item.key)}/review`, {
        method: "POST",
        body: JSON.stringify({ action: "edited", reviewer_type: "user", data }),
      });
      setEditingKey("");
    });
  }

  function mergeItem(itemKey: string, mergeIntoKey: string) {
    if (!selected || !mergeIntoKey) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/${encodeURIComponent(itemKey)}/review`, {
        method: "POST",
        body: JSON.stringify({ action: "merged", reviewer_type: "user", merge_into_key: mergeIntoKey }),
      });
    });
  }

  function proposalAction(action: "validate" | "approve" | "reject" | "apply") {
    if (!selected) return;
    void run(async () => {
      if (action === "validate" || action === "apply") {
        await props.request(`/proposals/${selected.id}/${action}`, { method: "POST" });
      } else {
        await props.request(`/proposals/${selected.id}/review`, {
          method: "POST",
          body: JSON.stringify({ decision: action === "approve" ? "approved" : "rejected", reviewer_type: "user" }),
        });
        if (action === "approve" && autoApplyOnApprove) {
          const validationErrors = selected.validation_result.errors?.length ?? 0;
          const allDecided = pendingItems.length === 0;
          if (validationErrors === 0 && allDecided) {
            await props.request(`/proposals/${selected.id}/apply`, { method: "POST" });
            await props.reloadSchema();
          }
        }
      }
      if (action === "apply") await props.reloadSchema();
    });
  }

  function reviewAllPending(decision: "approved" | "rejected") {
    if (!selected || pendingItems.length === 0) return;
    if (!window.confirm(`${decision === "approved" ? "Approve" : "Reject"} all ${pendingItems.length} pending item(s)?`)) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/review`, {
        method: "POST",
        body: JSON.stringify({ item_keys: pendingItems.map((item) => item.key), action: decision, reviewer_type: "user" }),
      });
    });
  }

  function applyAllApproved() {
    const approvedProposals = proposals.filter((proposal) => proposal.status === "approved");
    if (approvedProposals.length === 0) return;
    if (!window.confirm(`Apply ${approvedProposals.length} approved proposal(s) atomically?`)) return;
    void run(async () => {
      for (const proposal of approvedProposals) {
        await props.request(`/proposals/${proposal.id}/apply`, { method: "POST" });
      }
      await props.reloadSchema();
    });
  }

  return (
    <section className="schemaReviewPage">
      <aside className="reviewQueue" aria-label="Schema proposal batches">
        <header>
          <div><span className="eyebrow">Review queue</span><h2>Schema batches</h2></div>
          <button className="iconButton" disabled={busy} onClick={() => void load()} type="button">
            <RefreshCw className={busy ? "spin" : ""} size={16} />
          </button>
        </header>
        {proposals.filter((proposal) => proposal.status === "approved").length > 0 && (
          <button
            className="primaryButton applyAllButton"
            disabled={busy}
            onClick={applyAllApproved}
            type="button"
          >
            <Save size={14} /> Apply all approved ({proposals.filter((p) => p.status === "approved").length})
          </button>
        )}
        {proposals.length ? proposals.map((proposal) => (
          <button
            className={classNames("reviewQueueItem", proposal.id === selectedId && "active")}
            key={proposal.id}
            onClick={() => { setSelectedId(proposal.id); setSelectedKeys([]); }}
            type="button"
          >
            <span><strong>{proposal.payload.items?.length ?? 0} changes</strong><Badge>{proposal.status}</Badge></span>
            <small>{formatDate(proposal.created_at)} · {compactId(proposal.id)}</small>
          </button>
        )) : <EmptyState icon={<Clipboard size={20} />} title="No schema proposals" />}
      </aside>

      <main className="reviewSurface">
        {error && <div className="reviewError">{error}</div>}
        {batch && <div className="batchContext"><strong>Review batch · schema</strong><span>{batch.status} · {batch.item_ids.length} scoped items</span><button className="secondaryButton" onClick={() => { const url = new URL(window.location.href); url.searchParams.delete("batch"); window.location.assign(url); }} type="button">Exit batch</button></div>}
        {!selected ? (
          <EmptyState icon={<Clipboard size={24} />} title="Select a schema proposal" />
        ) : (
          <>
            <header className="reviewHeader">
              <div>
                <span className="eyebrow">Schema change proposal</span>
                <h2>{items.length} candidate changes</h2>
                <p>Draft {compactId(selected.target_version_id)} · evidence and deterministic validation remain attached.</p>
              </div>
              <div className="reviewHeaderActions">
                {(selected.status === "proposed" || selected.status === "validated") && <><button className="secondaryButton" disabled={busy} onClick={() => proposalAction("reject")} type="button"><X size={14} /> Reject</button>{selected.status === "proposed" && <button className="secondaryButton" disabled={busy} onClick={() => proposalAction("validate")} type="button"><Play size={14} /> Validate</button>}{selected.status === "validated" && <button className="primaryButton" disabled={busy || pendingItems.length > 0} onClick={() => proposalAction("approve")} title={pendingItems.length > 0 ? "Every candidate needs an explicit decision" : undefined} type="button"><Check size={14} /> Approve proposal{autoApplyOnApprove ? " & apply" : ""}</button>}</>}
                {selected.status === "approved" && <button className="primaryButton" disabled={busy} onClick={() => proposalAction("apply")} type="button"><Save size={14} /> Apply atomically</button>}
              </div>
            </header>

            <div className="reviewSummary">
              <div><strong>{items.filter((item) => item.review_status === "approved").length}</strong><span>Approved</span></div>
              <div><strong>{items.filter((item) => item.review_status === "rejected").length}</strong><span>Rejected</span></div>
              <div><strong>{pendingItems.length}</strong><span>Pending</span></div>
              <div><strong>{selected.evidence.length}</strong><span>Evidence records</span></div>
            </div>
            <div className="reviewSummaryBar">
              {pendingItems.length > 0 && selected.status === "validated" && (
                <div className="reviewSummaryActions">
                  <button className="secondaryButton" disabled={busy} onClick={() => reviewAllPending("approved")} type="button"><Check size={13} /> Approve all pending ({pendingItems.length})</button>
                  <button className="secondaryButton" disabled={busy} onClick={() => reviewAllPending("rejected")} type="button"><X size={13} /> Reject all pending</button>
                </div>
              )}
              <label className="reviewToggle inlineCheck" title="When enabled, approving a clean proposal also applies it atomically.">
                <input checked={autoApplyOnApprove} onChange={(event) => setAutoApplyOnApprove(event.target.checked)} type="checkbox" />
                Auto-apply on approve
              </label>
            </div>

            {(selected.validation_result.errors?.length || selected.validation_result.ambiguities?.length) ? (
              <div className="validationStrip">
                {(selected.validation_result.errors ?? []).map((message) => <span className="validationError" key={message}>{message}</span>)}
                {(selected.validation_result.ambiguities ?? []).map((item, index) => <span className="validationAmbiguity" key={index}>{String(item.message ?? "Modeling ambiguity requires review")}</span>)}
              </div>
            ) : null}

            {selectedKeys.length > 0 && (
              <div className="batchBar">
                <strong>{selectedKeys.length} selected</strong>
                <button onClick={() => batchReview("approved")} type="button"><Check size={14} /> Approve</button>
                <button onClick={() => batchReview("rejected")} type="button"><X size={14} /> Reject</button>
              </div>
            )}

            <div className="reviewItems">
              {items.map((item) => {
                const checked = selectedKeys.includes(item.key);
                const currentClass = item.kind === "class"
                  ? props.classes.find((classDef) => classDef.name === item.data.name)
                  : null;
                const evidence = selected.evidence.filter((record) => item.evidence_ids?.includes(record.id));
                return (
                  <article className={classNames("reviewItem", `status-${item.review_status ?? "pending"}`)} key={item.key}>
                    <div className="reviewItemSelect">
                      <input
                        aria-label={`Select ${item.key}`}
                        checked={checked}
                        onChange={() => setSelectedKeys(checked ? selectedKeys.filter((key) => key !== item.key) : [...selectedKeys, item.key])}
                        type="checkbox"
                      />
                    </div>
                    <div className="reviewItemBody">
                      <header>
                        <div><Badge>{item.kind.replace("_", " ")}</Badge><h3>{String(item.data.name ?? item.key)}</h3></div>
                        <div className="reviewItemMeta"><span>{Math.round((item.confidence ?? 0) * 100)}% confidence</span><Badge>{item.review_status ?? "pending"}</Badge></div>
                      </header>
                      <div className="schemaDiff">
                        <div><span>Before</span><pre>{currentClass ? prettyJson(currentClass) : "Not defined"}</pre></div>
                        <div><span>After</span><pre>{prettyJson(item.data)}</pre></div>
                      </div>
                      <div className="reviewFacts">
                        <span>Impact: {item.kind === "class" ? `${props.classes.filter((classDef) => classDef.parent_class_ids.includes(String(item.data.id ?? ""))).length} child classes` : classNamesById.get(String(item.data.class_id ?? "")) ?? "Schema only"}</span>
                        <span>Evidence: {item.evidence_ids?.length ?? 0} records · {item.competency_question_ids?.length ?? 0} questions</span>
                      </div>
                      <EvidenceExplorer compact evidence={evidence} request={props.request} />
                      {editingKey === item.key && (
                        <div className="reviewEditor">
                          <SchemaItemEditor item={item} onChange={setEditorValue} value={editorValue} />
                          <button className="primaryButton" onClick={() => saveEdit(item)} type="button">Save candidate</button>
                        </div>
                      )}
                    </div>
                    <div className="reviewItemActions">
                      <button title="Approve" onClick={() => reviewItem(item.key, "approved")} type="button"><Check size={15} /></button>
                      <button title="Edit" onClick={() => { setEditingKey(item.key); setEditorValue(prettyJson(item.data)); }} type="button"><Braces size={15} /></button>
                      <button title="Reject" onClick={() => reviewItem(item.key, "rejected")} type="button"><X size={15} /></button>
                      <select
                        aria-label={`Merge ${item.key} into another candidate`}
                        onChange={(event) => mergeItem(item.key, event.target.value)}
                        value=""
                      >
                        <option value="">Merge…</option>
                        {items.filter((candidate) => candidate.key !== item.key && candidate.kind === item.kind).map((candidate) => (
                          <option key={candidate.key} value={candidate.key}>{String(candidate.data.name ?? candidate.key)}</option>
                        ))}
                      </select>
                    </div>
                  </article>
                );
              })}
            </div>
          </>
        )}
      </main>
    </section>
  );
}

function SchemaItemEditor(props: { item: ProposalItem; value: string; onChange: (value: string) => void }) {
  let data: JsonObject = {};
  try {
    data = JSON.parse(props.value) as JsonObject;
  } catch {
    return <textarea aria-label="Advanced candidate JSON" onChange={(event) => props.onChange(event.target.value)} value={props.value} />;
  }

  const fieldsByKind: Record<ProposalItem["kind"], string[]> = {
    class: ["name", "description", "aliases", "parent_class_ids"],
    property: ["name", "class_id", "type", "description", "required", "multi_valued"],
    relation_type: [
      "name",
      "source_class_id",
      "target_class_id",
      "description",
      "inverse_name",
      "scope_policy",
      "symmetric",
      "transitive",
      "status",
      "valid_from",
      "valid_to",
    ],
    constraint: ["name", "class_id", "expression", "severity", "description"],
    entity: ["name"],
    relation: ["relation_type_id"],
    merge: ["source_entity_id", "target_entity_id"],
  };

  function update(field: string, value: unknown) {
    props.onChange(prettyJson({ ...data, [field]: value }));
  }

  return (
    <div className="structuredEditor">
      {fieldsByKind[props.item.kind].map((field) => {
        const current = data[field];
        if (typeof current === "boolean" || field === "required" || field === "multi_valued") {
          return <label key={field}><span>{field.replace(/_/g, " ")}</span><input checked={Boolean(current)} onChange={(event) => update(field, event.target.checked)} type="checkbox" /></label>;
        }
        const arrayValue = Array.isArray(current);
        return <label key={field}><span>{field.replace(/_/g, " ")}</span><input onChange={(event) => update(field, arrayValue ? splitCsv(event.target.value) : event.target.value)} value={arrayValue ? current.join(", ") : current === undefined || current === null ? "" : String(current)} /></label>;
      })}
      <details><summary>Advanced JSON</summary><textarea aria-label="Advanced candidate JSON" onChange={(event) => props.onChange(event.target.value)} value={props.value} /></details>
    </div>
  );
}

export function GraphReviewPage(props: { ontology: Ontology; request: WorkbenchRequest; reloadGraph: () => Promise<void>; batchId?: string; versionId: string }) {
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [conflicts, setConflicts] = useState<KnowledgeConflict[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState<ReviewBatch | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [editingKey, setEditingKey] = useState("");
  const [editorValue, setEditorValue] = useState("");
  const [manualValues, setManualValues] = useState<Record<string, string>>({});
  const [autoValidatedIds, setAutoValidatedIds] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    const [all, conflictData, batchData] = await Promise.all([
      props.request<Proposal[]>(`/ontologies/${props.ontology.id}/proposals`),
      props.request<KnowledgeConflict[]>(`/ontologies/${props.ontology.id}/knowledge-conflicts`),
      props.batchId ? props.request<ReviewBatch>(`/review-batches/${props.batchId}`) : Promise.resolve(null),
    ]);
    if (batchData && (batchData.ontology_id !== props.ontology.id || batchData.ontology_version_id !== props.versionId || !["entity", "relation", "merge", "conflict"].includes(batchData.review_type))) {
      throw new Error("This review batch does not belong to the selected ontology version or graph review type.");
    }
    const knowledge = all.filter((item) => ["entity", "relation", "merge"].includes(item.proposal_type));
    setProposals(knowledge);
    setConflicts(conflictData);
    setBatch(batchData);
    const batchProposalId = batchData?.stable_key.split(":")[1] ?? "";
    setSelectedId((current) => batchProposalId || (knowledge.some((item) => item.id === current) ? current : knowledge[0]?.id || ""));
  }, [props.batchId, props.ontology.id, props.request, props.versionId]);

  useEffect(() => { load().catch((cause) => setError(String(cause))); }, [load]);
  const selected = proposals.find((proposal) => proposal.id === selectedId);
  const selectedConflicts = conflicts.filter((conflict) => conflict.proposal_id === selectedId);
  const items = (selected?.payload.items ?? []).filter((item) => !batch || batch.item_ids.includes(item.key));
  const pendingItems = items.filter((item) => !item.review_status || item.review_status === "pending");
  const blockingConflicts = selectedConflicts.some((item) => item.status === "pending");
  const [autoApplyOnApprove, setAutoApplyOnApprove] = useReviewPref("autoApplyOnApprove", true);

  useEffect(() => {
    if (!selected || selected.status !== "proposed") return;
    if (autoValidatedIds.has(selected.id)) return;
    const timer = setTimeout(() => {
      setAutoValidatedIds((current) => new Set(current).add(selected.id));
      void run(async () => {
        await props.request(`/proposals/${selected.id}/validate`, { method: "POST" });
      });
    }, 200);
    return () => clearTimeout(timer);
  }, [selected?.id, selected?.status, autoValidatedIds]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError("");
    try { await action(); await load(); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } finally { setBusy(false); }
  }

  function proposalAction(action: "validate" | "approve" | "reject" | "apply") {
    if (!selected) return;
    void run(async () => {
      if (action === "validate" || action === "apply") await props.request(`/proposals/${selected.id}/${action}`, { method: "POST" });
      else {
        await props.request(`/proposals/${selected.id}/review`, { method: "POST", body: JSON.stringify({ decision: action === "approve" ? "approved" : "rejected", reviewer_type: "user" }) });
        if (action === "approve" && autoApplyOnApprove) {
          const validationErrors = selected.validation_result.errors?.length ?? 0;
          const allDecided = pendingItems.length === 0;
          if (validationErrors === 0 && allDecided && !blockingConflicts) {
            await props.request(`/proposals/${selected.id}/apply`, { method: "POST" });
            await props.reloadGraph();
          }
        }
      }
      if (action === "apply") await props.reloadGraph();
    });
  }

  function reviewAllPending(decision: "approved" | "rejected") {
    if (!selected || pendingItems.length === 0) return;
    if (!window.confirm(`${decision === "approved" ? "Approve" : "Reject"} all ${pendingItems.length} pending candidate(s)?`)) return;
    void run(() => props.request(`/proposals/${selected.id}/items/review`, {
      method: "POST",
      body: JSON.stringify({ item_keys: pendingItems.map((item) => item.key), action: decision, reviewer_type: "user" }),
    }));
  }

  function applyAllApproved() {
    const approvedProposals = proposals.filter((proposal) => proposal.status === "approved");
    if (approvedProposals.length === 0) return;
    if (!window.confirm(`Apply ${approvedProposals.length} approved proposal(s) atomically?`)) return;
    void run(async () => {
      for (const proposal of approvedProposals) {
        await props.request(`/proposals/${proposal.id}/apply`, { method: "POST" });
      }
      await props.reloadGraph();
    });
  }

  function reviewItem(itemKey: string, action: "approved" | "rejected" | "edited", data?: JsonObject) {
    if (!selected) return;
    void run(() => props.request(`/proposals/${selected.id}/items/${encodeURIComponent(itemKey)}/review`, {
      method: "POST",
      body: JSON.stringify({ action, reviewer_type: "user", ...(data ? { data } : {}) }),
    }));
  }

  function batchReview(action: "approved" | "rejected") {
    if (!selected || selectedKeys.length === 0) return;
    void run(async () => {
      await props.request(`/proposals/${selected.id}/items/review`, {
        method: "POST",
        body: JSON.stringify({ item_keys: selectedKeys, action, reviewer_type: "user" }),
      });
      setSelectedKeys([]);
    });
  }

  function saveEdit(itemKey: string) {
    try {
      reviewItem(itemKey, "edited", JSON.parse(editorValue) as JsonObject);
      setEditingKey("");
    } catch {
      setError("Edited candidate data must be valid JSON.");
    }
  }

  function resolve(conflictId: string, action: "keep_existing" | "accept_proposed" | "manual") {
    let value: unknown;
    if (action === "manual") {
      try {
        value = JSON.parse(manualValues[conflictId] ?? "");
      } catch {
        setError("Manual conflict values must be valid JSON.");
        return;
      }
    }
    void run(() => props.request(`/knowledge-conflicts/${conflictId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ action, ...(action === "manual" ? { value } : {}) }),
    }));
  }

  return <section className="schemaReviewPage">
    <aside className="reviewQueue">
      <header><div><span className="eyebrow">Review queue</span><h2>Graph candidates</h2></div></header>
      {proposals.filter((proposal) => proposal.status === "approved").length > 0 && (
        <button className="primaryButton applyAllButton" disabled={busy} onClick={applyAllApproved} type="button">
          <Save size={14} /> Apply all approved ({proposals.filter((p) => p.status === "approved").length})
        </button>
      )}
      {proposals.map((proposal) => (
        <button className={classNames("reviewQueueItem", proposal.id === selectedId && "active")} key={proposal.id} onClick={() => setSelectedId(proposal.id)} type="button">
          <span><strong>{proposal.payload.items?.length ?? 0} {proposal.proposal_type}</strong><Badge>{proposal.status}</Badge></span>
          <small>{formatDate(proposal.created_at)} · {compactId(proposal.id)}</small>
        </button>
      ))}
    </aside>
    <main className="reviewSurface">
      {error && <div className="reviewError">{error}</div>}
      {!selected ? <EmptyState icon={<GitBranch size={24} />} title="No knowledge candidates" /> : <>
        <header className="reviewHeader">
          <div><span className="eyebrow">{selected.proposal_type} proposal</span><h2>{items.length} candidates</h2><p>{selected.proposal_type === "merge" ? "Compare the source and target identities before approving the merge." : "Every knowledge candidate keeps its structured data and traceable evidence."}</p></div>
          <div className="reviewHeaderActions">
            {(selected.status === "proposed" || selected.status === "validated") && (
              <>
                <button className="secondaryButton" disabled={busy} onClick={() => proposalAction("reject")} type="button">Reject</button>
                {selected.status === "proposed" && <button className="secondaryButton" disabled={busy} onClick={() => proposalAction("validate")} type="button">Validate</button>}
                {selected.status === "validated" && (
                  <button
                    className="primaryButton"
                    disabled={busy || blockingConflicts || pendingItems.length > 0}
                    onClick={() => proposalAction("approve")}
                    title={blockingConflicts ? "Resolve pending conflicts first" : pendingItems.length > 0 ? "Every candidate needs an explicit decision" : undefined}
                    type="button"
                  >Approve proposal{autoApplyOnApprove ? " & apply" : ""}</button>
                )}
              </>
            )}
            {selected.status === "approved" && <button className="primaryButton" disabled={busy} onClick={() => proposalAction("apply")} type="button">Apply atomically</button>}
          </div>
        </header>
        {selectedConflicts.map((conflict) => <article className="conflictCard" key={conflict.id}><div><Badge>{conflict.status}</Badge><strong>{conflict.item_key} · {conflict.field}</strong><p>Existing: {prettyJson(conflict.existing_value)}<br />Proposed: {prettyJson(conflict.proposed_value)}</p></div>{conflict.status === "pending" && <div className="conflictActions"><button onClick={() => resolve(conflict.id, "keep_existing")} type="button">Keep existing</button><button onClick={() => resolve(conflict.id, "accept_proposed")} type="button">Accept proposed</button><input aria-label={`Manual value for ${conflict.field}`} onChange={(event) => setManualValues((current) => ({ ...current, [conflict.id]: event.target.value }))} placeholder="Manual JSON value" value={manualValues[conflict.id] ?? ""} /><button onClick={() => resolve(conflict.id, "manual")} type="button">Use manual</button></div>}</article>)}
        {batch && <div className="batchContext"><strong>Review batch · {batch.review_type}</strong><span>{batch.status} · {batch.item_ids.length} scoped items</span><button className="secondaryButton" onClick={() => { const url = new URL(window.location.href); url.searchParams.delete("batch"); window.location.assign(url); }} type="button">Exit batch</button></div>}
        <div className="reviewSummary">
          <div><strong>{items.filter((item) => item.review_status === "approved").length}</strong><span>Approved</span></div>
          <div><strong>{items.filter((item) => item.review_status === "rejected").length}</strong><span>Rejected</span></div>
          <div><strong>{pendingItems.length}</strong><span>Pending</span></div>
        </div>
        <div className="reviewSummaryBar">
          {pendingItems.length > 0 && selected.status === "validated" && (
            <div className="reviewSummaryActions">
              <button className="secondaryButton" disabled={busy} onClick={() => reviewAllPending("approved")} type="button"><Check size={13} /> Approve all pending ({pendingItems.length})</button>
              <button className="secondaryButton" disabled={busy} onClick={() => reviewAllPending("rejected")} type="button"><X size={13} /> Reject all pending</button>
            </div>
          )}
          <label className="reviewToggle inlineCheck" title="When enabled, approving a clean proposal also applies it atomically.">
            <input checked={autoApplyOnApprove} onChange={(event) => setAutoApplyOnApprove(event.target.checked)} type="checkbox" />
            Auto-apply on approve
          </label>
        </div>
        {selectedKeys.length > 0 && <div className="batchBar"><strong>{selectedKeys.length} selected</strong><button onClick={() => batchReview("approved")} type="button"><Check size={14} /> Approve</button><button onClick={() => batchReview("rejected")} type="button"><X size={14} /> Reject</button></div>}
        <div className="reviewItems">{items.map((item) => { const evidence = selected.evidence.filter((record) => item.evidence_ids?.includes(record.id)); const checked = selectedKeys.includes(item.key); return <article className={classNames("reviewItem", `status-${item.review_status ?? "pending"}`)} key={item.key}><div className="reviewItemSelect"><input aria-label={`Select ${item.key}`} checked={checked} onChange={() => setSelectedKeys(checked ? selectedKeys.filter((key) => key !== item.key) : [...selectedKeys, item.key])} type="checkbox" /></div><div className="reviewItemBody"><header><div><Badge>{item.kind}</Badge><h3>{String(item.data.name ?? item.key)}</h3></div><Badge>{item.review_status ?? "pending"}</Badge></header>{item.kind === "merge" ? <div className="schemaDiff"><div><span>Source entity</span><pre>{prettyJson(item.data.source_entity_id ?? item.data.source ?? "New entity")}</pre></div><div><span>Merge target</span><pre>{prettyJson(item.data.target_entity_id ?? item.data.target ?? "Existing entity")}</pre></div></div> : <pre className="jsonBlock">{prettyJson(item.data)}</pre>}{editingKey === item.key && <div className="reviewEditor"><textarea onChange={(event) => setEditorValue(event.target.value)} value={editorValue} /><button className="primaryButton" onClick={() => saveEdit(item.key)} type="button">Save candidate</button></div>}<EvidenceExplorer compact evidence={evidence} request={props.request} /></div><div className="reviewItemActions"><button aria-label={`Approve ${item.key}`} onClick={() => reviewItem(item.key, "approved")} type="button"><Check size={15} /></button><button aria-label={`Edit ${item.key}`} onClick={() => { setEditingKey(item.key); setEditorValue(prettyJson(item.data)); }} type="button"><Braces size={15} /></button><button aria-label={`Reject ${item.key}`} onClick={() => reviewItem(item.key, "rejected")} type="button"><X size={15} /></button></div></article>; })}</div>
      </>}
    </main>
  </section>;
}
