import { useEffect, useMemo, useState } from "react";
import { Database, Filter } from "lucide-react";
import type {
  SemanticGraphRegistryListResponse,
  SemanticGraphRegistryRead,
} from "../types";
import { useT } from "../i18n";
import { errorNotice } from "../api";
import type { Notice } from "../types";
import {
  listGraphRegistry,
  updateGraphEditability,
  type SemanticRequester,
} from "../semanticApi";
import {
  EditabilityBadge,
  GraphEditabilityToggle,
  GraphIriLabel,
  StalenessBadge,
} from "../components/semantic";
import { RefreshButton, SemanticEmpty, SemanticPanel, StatTile } from "../components/semantic/primitives";
import { prettyJson } from "../utils";

const CATEGORY_VALUES = [
  "",
  "ontology",
  "data",
  "proposal",
  "evidence",
  "policy",
  "import",
  "validation_run",
  "reasoning_run",
  "reasoning_result",
  "rule_run",
  "rule_result",
  "review",
  "shape",
  "namespace",
  "other",
];

export function NamedGraphsPage({
  request,
  notify,
  initialCategory,
}: {
  request: SemanticRequester;
  notify: (notice: Notice) => void;
  initialCategory?: string;
}) {
  const t = useT();
  const [data, setData] = useState<SemanticGraphRegistryListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [category, setCategory] = useState(initialCategory ?? "");
  const [ownerType, setOwnerType] = useState("");
  const [editability, setEditability] = useState<"" | "editable" | "locked">("");
  const [freshness, setFreshness] = useState<"" | "current" | "stale">("");
  const [selectedGraphIri, setSelectedGraphIri] = useState<string>("");

  async function load() {
    setLoading(true);
    try {
      const result = await listGraphRegistry(request, {
        category: category || undefined,
        ownerType: ownerType || undefined,
        includeRevisions: true,
      });
      setData(result);
    } catch (error) {
      notify(errorNotice(error));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, ownerType]);

  const filtered = useMemo(() => {
    const graphs = data?.graphs ?? [];
    return graphs.filter((graph) => {
      if (editability === "editable" && graph.editable !== true) return false;
      if (editability === "locked" && graph.editable !== false) return false;
      const stale = isGraphStale(graph);
      if (freshness === "current" && stale) return false;
      if (freshness === "stale" && !stale) return false;
      return true;
    });
  }, [data, editability, freshness]);

  const summary = useMemo(() => {
    const counts: Record<string, number> = {};
    let editable = 0;
    let locked = 0;
    for (const graph of data?.graphs ?? []) {
      counts[graph.category] = (counts[graph.category] ?? 0) + 1;
      if (graph.editable === true) editable += 1;
      else if (graph.editable === false) locked += 1;
    }
    return { counts, editable, locked };
  }, [data]);

  async function toggleEditability(graph: SemanticGraphRegistryRead, next: boolean, reason: string) {
    try {
      await updateGraphEditability(request, graph.graph_iri, next, undefined, reason);
      notify({ kind: "ok", message: t("Graph editability updated") });
      await load();
    } catch (error) {
      notify(errorNotice(error));
      throw error;
    }
  }

  const selected = filtered.find((graph) => graph.graph_iri === selectedGraphIri) ?? null;

  return (
    <section className="namedGraphsPage" aria-label="named-graphs-page">
      <header className="pageSubHeader">
        <div>
          <span className="eyebrow">{t("Graph Governance")}</span>
          <h2>{t("Named Graph Registry")}</h2>
          <p>{t("Inspect and govern actual ontology/data graphs, derived result graphs, evidence, policy, and review graphs.")}</p>
        </div>
        <RefreshButton busy={loading} onClick={() => void load()} />
      </header>

      <section className="statTileRow" aria-label="named-graph-summary">
        <StatTile label={t("Total graphs")} value={data?.graphs.length ?? 0} />
        <StatTile label={t("Editable")} value={summary.editable} tone={summary.editable > 0 ? "ok" : "warning"} />
        <StatTile label={t("Locked")} value={summary.locked} tone={summary.locked > 0 ? "warning" : "ok"} />
        <StatTile
          label={t("Ontology / Data")}
          value={(summary.counts.ontology ?? 0) + (summary.counts.data ?? 0)}
        />
        <StatTile
          label={t("Reasoning / Rule results")}
          value={(summary.counts.reasoning_result ?? 0) + (summary.counts.rule_result ?? 0)}
        />
      </section>

      <SemanticPanel
        title={t("Filters")}
        icon={<Filter size={15} />}
        actions={
          <button
            className="secondaryButton"
            onClick={() => {
              setCategory("");
              setOwnerType("");
              setEditability("");
              setFreshness("");
            }}
            type="button"
          >
            {t("Reset")}
          </button>
        }
      >
        <div className="filterRow">
          <label>
            <span>{t("Category")}</span>
            <select onChange={(event) => setCategory(event.target.value)} value={category}>
              {CATEGORY_VALUES.map((value) => (
                <option key={value} value={value}>
                  {value ? value : t("All categories")}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>{t("Owner type")}</span>
            <input
              onChange={(event) => setOwnerType(event.target.value)}
              placeholder="ontology | version | graph_set | import | …"
              value={ownerType}
            />
          </label>
          <label>
            <span>{t("Editability")}</span>
            <select
              onChange={(event) => setEditability(event.target.value as "" | "editable" | "locked")}
              value={editability}
            >
              <option value="">{t("Editable and locked")}</option>
              <option value="editable">{t("Editable only")}</option>
              <option value="locked">{t("Locked only")}</option>
            </select>
          </label>
          <label>
            <span>{t("Freshness")}</span>
            <select
              onChange={(event) => setFreshness(event.target.value as "" | "current" | "stale")}
              value={freshness}
            >
              <option value="">{t("Current and stale")}</option>
              <option value="current">{t("Current only")}</option>
              <option value="stale">{t("Stale only")}</option>
            </select>
          </label>
        </div>
      </SemanticPanel>

      <SemanticPanel title={t("Registered graphs")} icon={<Database size={15} />}>
        {!filtered.length ? (
          <SemanticEmpty title={t("No graphs match these filters")} hint={t("Adjust filters or register a new graph via direct semantic edit.")} />
        ) : (
          <table className="namedGraphTable" aria-label="named-graph-table">
            <thead>
              <tr>
                <th>{t("Graph")}</th>
                <th>{t("Category")}</th>
                <th>{t("Owner type")}</th>
                <th>{t("Revision")}</th>
                <th>{t("Statements")}</th>
                <th>{t("Latest audit")}</th>
                <th>{t("Editability")}</th>
                <th>{t("Freshness")}</th>
                <th aria-label="actions">{t("Actions")}</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((graph) => {
                const derivedStale = isGraphStale(graph);
                return (
                  <tr key={graph.graph_iri} aria-label={`graph-row-${graph.graph_iri}`}>
                    <td>
                      <button className="ghostButton" onClick={() => setSelectedGraphIri(graph.graph_iri)} type="button">
                        <GraphIriLabel iri={graph.graph_iri} copyable={false} />
                      </button>
                    </td>
                    <td><code>{graph.category}</code></td>
                    <td>
                      {graph.owner_type ?? t("unknown")}
                      {graph.owner_id ? <small> · {graph.owner_id}</small> : null}
                    </td>
                    <td>{graph.revision ?? "—"}</td>
                    <td>{graph.statement_count ?? "—"}</td>
                    <td>{graph.latest_audit_at ? new Date(graph.latest_audit_at).toLocaleString() : "—"}</td>
                    <td>
                      <EditabilityBadge editable={graph.editable} reason={graph.editability_reason} />
                    </td>
                    <td>
                      <StalenessBadge stale={derivedStale} detail={t("One or more derived pointers are stale")} />
                      <span>{graph.derived_pointers?.length ?? 0}</span>
                    </td>
                    <td>
                      <GraphEditabilityToggle
                        disabled={!graph.mutable_by_direct_edit}
                        editable={graph.editable}
                        graphIri={graph.graph_iri}
                        reason={graph.editability_reason}
                        onToggle={(next, reason) => toggleEditability(graph, next, reason)}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </SemanticPanel>

      {selected && (
        <SemanticPanel title={t("Graph detail")} icon={<Database size={15} />}>
          <dl className="kvList">
            <div><dt>{t("IRI")}</dt><dd><GraphIriLabel iri={selected.graph_iri} /></dd></div>
            <div><dt>{t("Category")}</dt><dd>{selected.category}</dd></div>
            <div><dt>{t("Owner")}</dt><dd>{selected.owner_type ?? "—"}{selected.owner_id ? ` · ${selected.owner_id}` : ""}</dd></div>
            <div><dt>{t("Revision")}</dt><dd>{selected.revision ?? "—"}</dd></div>
            <div><dt>{t("Content hash")}</dt><dd><code>{selected.content_hash ?? "—"}</code></dd></div>
            <div><dt>{t("Statement count")}</dt><dd>{selected.statement_count ?? "—"}</dd></div>
            <div><dt>{t("Latest audit")}</dt><dd>{selected.latest_audit_at ? new Date(selected.latest_audit_at).toLocaleString() : "—"}</dd></div>
            <div><dt>{t("Mutable by direct edit")}</dt><dd>{selected.mutable_by_direct_edit ? t("yes") : t("no")}</dd></div>
            <div><dt>{t("Editability reason")}</dt><dd>{selected.editability_reason ?? "—"}</dd></div>
            <div>
              <dt>{t("Derived pointers")}</dt>
              <dd><pre className="jsonBlock">{prettyJson(selected.derived_pointers ?? [])}</pre></dd>
            </div>
            <div>
              <dt>{t("Metadata")}</dt>
              <dd><pre className="jsonBlock">{prettyJson(selected.metadata ?? {})}</pre></dd>
            </div>
          </dl>
        </SemanticPanel>
      )}
    </section>
  );
}

function isGraphStale(graph: SemanticGraphRegistryRead): boolean {
  return (graph.derived_pointers ?? []).some((pointer) => {
    const record = pointer as Record<string, unknown>;
    return record.stale === true || record.is_stale === true || record.status === "stale";
  });
}
