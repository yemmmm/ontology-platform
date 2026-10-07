import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  Layers,
  Network,
  Plus,
  Play,
  Trash2,
  Workflow,
} from "lucide-react";
import type {
  SemanticGraphSetRead,
  SemanticJsonObject,
} from "../types";
import { useT } from "../i18n";
import { errorNotice } from "../api";
import type { Notice } from "../types";
import {
  buildGraphSetExportUrl,
  createGraphSet,
  getGraphSet,
  listGraphSets,
  runGraphSetReasoning,
  runGraphSetValidation,
  updateGraphSetMembers,
  type SemanticRequester,
} from "../semanticApi";
import {
  EditabilityBadge,
  GraphIriLabel,
  GraphSetSelector,
  ReasoningResultPanel,
  StalenessBadge,
  ValidationReportPanel,
} from "../components/semantic";
import { RefreshButton, SemanticEmpty, SemanticPanel, SemanticTag } from "../components/semantic/primitives";
import type { SemanticReasoningRunRead, SemanticValidationRunRead } from "../types";

export function GraphSetPage({
  request,
  notify,
  initialGraphSetId,
  navigate,
}: {
  request: SemanticRequester;
  notify: (notice: Notice) => void;
  initialGraphSetId?: string;
  navigate: (tab: string, params?: Record<string, string>) => void;
}) {
  const t = useT();
  const [graphSets, setGraphSets] = useState<SemanticGraphSetRead[]>([]);
  const [selectedId, setSelectedId] = useState(initialGraphSetId ?? "");
  const [graphSet, setGraphSet] = useState<SemanticGraphSetRead | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftOntologyIri, setDraftOntologyIri] = useState("");
  const [draftDataIri, setDraftDataIri] = useState("");
  const [validation, setValidation] = useState<SemanticValidationRunRead | null>(null);
  const [reasoning, setReasoning] = useState<SemanticReasoningRunRead | null>(null);

  async function loadGraphSets() {
    try {
      const data = await listGraphSets(request);
      setGraphSets(data.graph_sets);
      if (!selectedId && data.graph_sets.length) {
        setSelectedId(data.graph_sets[0]!.id);
      }
    } catch (error) {
      notify(errorNotice(error));
    }
  }

  async function loadDetail(id: string) {
    if (!id) {
      setGraphSet(null);
      return;
    }
    setLoading(true);
    try {
      const detail = await getGraphSet(request, id);
      setGraphSet(detail);
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadGraphSets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
    else {
      setGraphSet(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const groupedMembers = useMemo(() => groupMembersByRole(graphSet?.members ?? []), [graphSet]);
  const currentPointers = (graphSet?.current_pointers ?? []).filter(pointer => (pointer as Record<string, unknown>).kind !== "rule_result");
  const stalePointers = currentPointers.filter((pointer) => isStalePointer(pointer));

  async function runValidation() {
    if (!graphSet) return;
    setBusy(true);
    try {
      const result = await runGraphSetValidation(request, graphSet.id, {});
      notify({
        kind: result.conforms === false ? "error" : "ok",
        message: t("Validation run {id} status: {status}", { id: result.run_id, status: result.status }),
      });
      try {
        const detail = await request<SemanticValidationRunRead>(`/semantic/validation-runs/${result.run_id}`);
        setValidation(detail);
      } catch (error) {
        notify(errorNotice(error));
      }
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setBusy(false);
    }
  }

  async function runReasoning() {
    if (!graphSet) return;
    setBusy(true);
    try {
      const result = await runGraphSetReasoning(request, graphSet.id, { tasks: ["consistency"] });
      notify({
        kind: result.consistent === false ? "error" : "ok",
        message: t("Reasoning run {id} status: {status}", { id: result.run_id, status: result.status }),
      });
      try {
        const detail = await request<SemanticReasoningRunRead>(`/semantic/reasoning-runs/${result.run_id}`);
        setReasoning(detail);
      } catch (error) {
        notify(errorNotice(error));
      }
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setBusy(false);
    }
  }

  async function removeMember(graphIri: string) {
    if (!graphSet) return;
    const remaining = graphSet.members
      .filter((member) => member.graph_iri !== graphIri)
      .map((member) => ({
        graph_iri: member.graph_iri,
        role: member.role,
        required: member.required,
        sort_order: member.sort_order,
        metadata: member.metadata,
      }));
    try {
      const updated = await updateGraphSetMembers(request, graphSet.id, remaining);
      setGraphSet(updated);
      notify({ kind: "ok", message: t("Member removed from graph set") });
    } catch (error) {
      notify(errorNotice(error));
    }
  }

  async function createFirstGraphSet() {
    if (!draftName.trim()) return;
    const members = [
      ...(draftOntologyIri
        ? [{ graph_iri: draftOntologyIri, role: "asserted_ontology", required: true, sort_order: 0, metadata: {} as SemanticJsonObject }]
        : []),
      ...(draftDataIri
        ? [{ graph_iri: draftDataIri, role: "asserted_data", required: true, sort_order: 1, metadata: {} as SemanticJsonObject }]
        : []),
    ];
    if (!members.length) {
      notify({ kind: "error", message: t("Provide at least one graph IRI") });
      return;
    }
    setBusy(true);
    try {
      const created = await createGraphSet(request, {
        name: draftName,
        scopeType: "ad_hoc",
        members,
      });
      notify({ kind: "ok", message: t("Graph set created") });
      setShowCreate(false);
      setDraftName("");
      setDraftOntologyIri("");
      setDraftDataIri("");
      await loadGraphSets();
      setSelectedId(created.id);
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="graphSetPage" aria-label="graph-set-page">
      <header className="pageSubHeader">
        <button className="iconButton subtle" onClick={() => navigate("graph-governance")} type="button" aria-label={t("Back to graph governance")}>
          <ArrowLeft size={15} />
        </button>
        <div>
          <span className="eyebrow">{t("Graph Governance")}</span>
          <h2>{t("Graph Set Detail")}</h2>
          <p>{t("Inspect members, source signature, current derived pointers, and staleness.")}</p>
        </div>
        <RefreshButton busy={loading} onClick={() => selectedId && void loadDetail(selectedId)} />
      </header>

      <SemanticPanel title={t("Choose graph set")} icon={<Layers size={15} />}
        actions={<button className="secondaryButton" onClick={() => setShowCreate(true)} type="button"><Plus size={14} /> {t("New graph set")}</button>}
      >
        {graphSets.length === 0 ? (
          <SemanticEmpty title={t("No graph sets registered")} hint={t("Create a graph set to begin governing semantic state.")} icon={<Layers size={20} />} />
        ) : (
          <GraphSetSelector graphSets={graphSets} value={selectedId || null} onChange={setSelectedId} />
        )}
      </SemanticPanel>

      {graphSet && (
        <>
          <section className="graphSetSummaryRow" aria-label="graph-set-summary">
            <SemanticPanel title={t("Identity")} icon={<Network size={15} />}>
              <dl className="kvList">
                <div><dt>{t("Name")}</dt><dd>{graphSet.name}</dd></div>
                <div><dt>{t("Scope")}</dt><dd>{graphSet.scope_type}{graphSet.scope_id ? ` · ${graphSet.scope_id}` : ""}</dd></div>
                <div><dt>{t("Status")}</dt><dd>{graphSet.status}</dd></div>
                <div><dt>{t("Source signature")}</dt><dd><code>{graphSet.source_signature}</code></dd></div>
                <div><dt>{t("Created by")}</dt><dd>{graphSet.created_by ?? "—"}</dd></div>
              </dl>
            </SemanticPanel>

            <SemanticPanel title={t("Current derived pointers")} icon={<Workflow size={15} />}
              actions={<StalenessBadge stale={stalePointers.length > 0} detail={t("{count} stale", { count: stalePointers.length })} />}
            >
              {currentPointers.length === 0 ? (
                <SemanticEmpty title={t("No current pointers")} hint={t("Run validation or reasoning to populate pointers.")} />
              ) : (
                <ul className="pointerList">
                  {currentPointers.map((pointer, idx) => {
                    const record = pointer as Record<string, unknown>;
                    const stale = record.stale === true || record.is_stale === true;
                    return (
                      <li key={idx}>
                        <code>{String(record.kind ?? record.target_kind ?? "pointer")}</code>
                        {typeof record.graph_iri === "string" && <GraphIriLabel iri={record.graph_iri} copyable />}
                        <StalenessBadge stale={stale} />
                      </li>
                    );
                  })}
                </ul>
              )}
            </SemanticPanel>
          </section>

          <SemanticPanel title={t("Members")} icon={<Layers size={15} />}
            actions={
              <div className="headerActions">
                <button className="secondaryButton" disabled={busy} onClick={() => void runValidation()} type="button"><CheckCircle2 size={14} /> {t("Validate")}</button>
                <button className="secondaryButton" disabled={busy} onClick={() => void runReasoning()} type="button"><Network size={14} /> {t("Run reasoning")}</button>
              </div>
            }
          >
            {groupedMembers.length === 0 ? (
              <SemanticEmpty title={t("No members in this graph set")} />
            ) : (
              <div className="memberGroupList">
                {groupedMembers.map((group) => (
                  <div className="memberGroup" key={group.role}>
                    <header>
                      <code>{group.role}</code>
                      <SemanticTag>{group.members.length}</SemanticTag>
                    </header>
                    <ul>
                      {group.members.map((member) => (
                        <li key={member.graph_iri}>
                          <GraphIriLabel iri={member.graph_iri} />
                          <small>{member.required ? t("required") : t("optional")}</small>
                          <button className="iconButton danger" onClick={() => removeMember(member.graph_iri)} title={t("Remove member")} type="button">
                            <Trash2 size={13} />
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
          </SemanticPanel>

          <section className="graphSetResultsRow" aria-label="graph-set-results">
            <ValidationReportPanel run={validation} />
            <ReasoningResultPanel run={reasoning} />
          </section>

          <SemanticPanel title={t("Export")} icon={<Download size={15} />}>
            <ExportControls graphSet={graphSet} />
          </SemanticPanel>
        </>
      )}

      {showCreate && (
        <SemanticPanel title={t("Create graph set")} icon={<Plus size={15} />}>
          <div className="stackForm">
            <label>
              <span>{t("Name")}</span>
              <input onChange={(event) => setDraftName(event.target.value)} value={draftName} required />
            </label>
            <label>
              <span>{t("Ontology graph IRI")}</span>
              <input onChange={(event) => setDraftOntologyIri(event.target.value)} placeholder="graph:ontology/..." value={draftOntologyIri} />
            </label>
            <label>
              <span>{t("Data graph IRI")}</span>
              <input onChange={(event) => setDraftDataIri(event.target.value)} placeholder="graph:data/..." value={draftDataIri} />
            </label>
            <div className="buttonRow">
              <button className="primaryButton" disabled={busy} onClick={() => void createFirstGraphSet()} type="button">{t("Create")}</button>
              <button className="secondaryButton" onClick={() => setShowCreate(false)} type="button">{t("Cancel")}</button>
            </div>
          </div>
        </SemanticPanel>
      )}

      <section className="graphSetPageFooter">
        <EditabilityBadge editable={null} />
        <Play size={14} />
        <small>{t("Membership changes are governance events: validation and reasoning results may become stale.")}</small>
      </section>
    </section>
  );
}

function ExportControls({ graphSet }: { graphSet: SemanticGraphSetRead }) {
  const t = useT();
  const [format, setFormat] = useState<"trig" | "turtle" | "json-ld">("trig");
  const [include, setInclude] = useState<"asserted" | "asserted-plus-reasoning" | "full-working-view">("asserted");
  const [stale, setStale] = useState(false);
  const url = buildGraphSetExportUrl(graphSet.id, {
    format,
    include,
    includeShapes: false,
    includePolicy: false,
    includeMetadata: true,
    allowStaleDerived: stale,
  });
  return (
    <div className="exportControls" aria-label="graph-set-export-controls">
      <div className="filterRow">
        <label>
          <span>{t("Format")}</span>
          <select onChange={(event) => setFormat(event.target.value as "trig" | "turtle" | "json-ld")} value={format}>
            <option value="trig">TriG</option>
            <option value="turtle">Turtle</option>
            <option value="json-ld">JSON-LD</option>
          </select>
        </label>
        <label>
          <span>{t("Include")}</span>
          <select onChange={(event) => setInclude(event.target.value as "asserted" | "asserted-plus-reasoning" | "full-working-view")} value={include}>
            <option value="asserted">{t("Asserted only")}</option>
            <option value="asserted-plus-reasoning">{t("Asserted + reasoning")}</option>
            <option value="full-working-view">{t("Full working view")}</option>
          </select>
        </label>
        <label>
          <input checked={stale} onChange={(event) => setStale(event.target.checked)} type="checkbox" />
          <span>{t("Allow stale derived")}</span>
        </label>
      </div>
      <a className="secondaryButton" download={`${graphSet.name}.${format}`} href={`${url}`}>
        <Download size={14} /> {t("Download export")}
      </a>
    </div>
  );
}

function groupMembersByRole(members: SemanticGraphSetRead["members"]): Array<{ role: string; members: SemanticGraphSetRead["members"] }> {
  const map = new Map<string, SemanticGraphSetRead["members"]>();
  for (const member of members.filter(item => item.role !== "rule_result")) {
    const list = map.get(member.role) ?? [];
    list.push(member);
    map.set(member.role, list);
  }
  return Array.from(map.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([role, list]) => ({ role, members: list }));
}

function isStalePointer(pointer: unknown): boolean {
  if (!pointer || typeof pointer !== "object") return false;
  const record = pointer as Record<string, unknown>;
  return record.stale === true || record.is_stale === true || record.status === "stale";
}
