import { useEffect, useMemo, useState } from "react";
import { ForceGraphCanvas, type ForceGraphEdge } from "../components/ForceGraphCanvas";
import { assignNodeColors, UNCLASSIFIED_COLORS, VIEWPOINT_COLORS } from "../components/nodeColors";
import { useT } from "../i18n";
import { workspaceApi } from "../workspaceApi";
import { semanticViews, type JsonObject, type Project, type Relation, type Resource } from "../workspaceTypes";
type Position = { ontologyId: string; ontologyName: string; graphSetId: string; signature: string; resource: Resource };
type Node = { iri: string; label: string; positions: Position[] };
function definition(resource: Resource): JsonObject {
  const value = resource.detail_fields?.semantic_definition;
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : {};
}
function readable(value: unknown): string {
  if (value == null || value === "") return "";
  if (Array.isArray(value)) return value.map(readable).join(" · ");
  if (typeof value === "object") return Object.entries(value).map(([key, item]) => `${key}: ${readable(item)}`).join(" · ");
  return String(value);
}
export function ModelBrowserPage({ project }: { project: Project }) {
  const t = useT();
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<(ForceGraphEdge & { positions: string[] })[]>([]);
  const [view, setView] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [position, setPosition] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [limits, setLimits] = useState<{ name: string; code: string; detail?: string }[]>([]);
  const [ontologyCount, setOntologyCount] = useState<number | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setNodes([]); setEdges([]); setSelected(null); setPosition(0); setError(""); setLimits([]); setLoading(true); setOntologyCount(null);
    async function load() {
      try {
        const ontologies = await workspaceApi.ontologies(project.id);
        if (!active) return;
        setOntologyCount(ontologies.length);
        const results = await Promise.all(ontologies.map(async ontology => {
          const warnings: { name: string; code: string; detail?: string }[] = [];
          let items: Position[] = [];
          let relations: Relation[] = [];
          let graphSetId = "";
          try {
            const workspace = await workspaceApi.workspace(ontology.id);
            graphSetId = workspace.default_graph_set_id ?? "";
            if (!graphSetId) return { items, relations, graphSetId, warnings: [{ name: ontology.name, code: "Default workspace is not ready" }] };
            const [resourceResult, relationResult] = await Promise.allSettled([workspaceApi.resources(graphSetId), workspaceApi.relations(graphSetId)]);
            if (resourceResult.status === "rejected") throw resourceResult.reason;
            const resources = resourceResult.value;
            items = resources.items.filter(item => item.iri
              && item.type_iri !== "http://www.w3.org/2002/07/owl#DatatypeProperty"
              && item.type_iri !== "http://www.w3.org/2002/07/owl#ObjectProperty"
            ).map(resource => ({ ontologyId: ontology.id, ontologyName: ontology.name, graphSetId, signature: resources.source_signature, resource }));
            if (resources.paging?.complete === false) warnings.push({ name: ontology.name, code: "Resource window is incomplete" });
            for (const warning of resources.warnings ?? []) warnings.push({ name: ontology.name, code: "Partial loading", detail: warning.message || warning.code });
            if (relationResult.status === "rejected") warnings.push({ name: ontology.name, code: "Relations could not be read", detail: String(relationResult.reason) });
            else {
              const relationEnvelope = relationResult.value;
              if (!resources.source_signature || resources.source_signature !== relationEnvelope.source_signature) warnings.push({ name: ontology.name, code: "Source versions differ; refresh before combining relations" });
              else relations = relationEnvelope.items;
              if (relationEnvelope.paging?.complete === false) warnings.push({ name: ontology.name, code: "Relation window is incomplete" });
              for (const warning of relationEnvelope.warnings ?? []) warnings.push({ name: ontology.name, code: "Partial loading", detail: warning.message || warning.code });
            }
          } catch (reason) { warnings.push({ name: ontology.name, code: "Scope not loaded", detail: String(reason) }); }
          return { items, relations, graphSetId, warnings };
        }));
        if (!active) return;
        const uniqueNodes = new Map<string, Node>();
        const uniqueEdges = new Map<string, ForceGraphEdge & { positions: string[] }>();
        for (const result of results) {
          for (const item of result.items) {
            const existing = uniqueNodes.get(item.resource.iri);
            if (existing) existing.positions.push(item);
            else uniqueNodes.set(item.resource.iri, { iri: item.resource.iri, label: item.resource.label || item.resource.iri, positions: [item] });
          }
          const localIds = new Set(result.items.map(item => item.resource.iri));
          for (const relation of result.relations) {
            if (!localIds.has(relation.source) || !localIds.has(relation.target)) continue;
            const id = JSON.stringify([relation.source, relation.relation, relation.target, relation.field_path ?? ""]);
            const existing = uniqueEdges.get(id);
            if (existing) existing.positions.push(result.graphSetId);
            else uniqueEdges.set(id, { id, source: relation.source, target: relation.target, label: relation.label || relation.relation, edgeKind: relation.edge_kind, positions: [result.graphSetId] });
          }
        }
        setNodes([...uniqueNodes.values()]); setEdges([...uniqueEdges.values()]); setLimits(results.flatMap(result => result.warnings));
      } catch (reason) { if (active) setError(String(reason)); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [project.id, revision]);
  const visible = useMemo(() => nodes.filter(node => !view || node.positions.some(item => definition(item.resource).semantic_role === view)), [nodes, view]);
  const visibleIds = useMemo(() => new Set(visible.map(node => node.iri)), [visible]);
  const graphEdges = useMemo(() => edges.filter(edge => visibleIds.has(edge.source) && visibleIds.has(edge.target)), [edges, visibleIds]);
  const nodeColors = useMemo(() => assignNodeColors(nodes.map(node => ({
    id: node.iri, roles: node.positions.map(item => definition(item.resource).semantic_role),
  }))), [nodes]);
  const graphNodes = useMemo(() => visible.map(node => ({ id: node.iri, label: node.label, color: nodeColors.get(node.iri)! })), [visible, nodeColors]);
  const search = query.trim().toLowerCase();
  const matches = visible.filter(node => node.positions.some(item => [item.resource.label, node.iri, item.resource.description, readable(definition(item.resource).business_meaning)].join(" ").toLowerCase().includes(search)));
  const highlighted = useMemo(() => search ? matches.map(node => node.iri) : [], [search, visible]);
  const selectedNode = visible.find(node => node.iri === selected);
  const selectedPosition = selectedNode?.positions[position] ?? selectedNode?.positions[0];
  const semantic = selectedPosition ? definition(selectedPosition.resource) : {};
  function select(iri: string | null) { setSelected(iri); setPosition(0); }
  return <section className="modelPage"><div className="panel modelToolbar"><label className="modelSearch">{t("Search loaded model")}<input value={query} onChange={event => setQuery(event.target.value)} placeholder={t("Name, IRI or recorded meaning")} /></label><label>{t("Viewpoint")}<select value={view} onChange={event => { setView(event.target.value); select(null); }}><option value="">{t("All")}</option>{semanticViews.map(([role, name]) => <option value={role} key={role}>{t(name)}</option>)}</select></label><button onClick={() => { setQuery(""); setView(""); select(null); }}>{t("Clear filters")}</button><button disabled={loading} onClick={() => setRevision(value => value + 1)}>{t("Refresh")}</button></div>
    {loading && <p role="status">{t("Loading…")}</p>}{error && <p className="errorMessage" role="alert">{t("Model could not be read")}: {error}</p>}
    {limits.length > 0 && <div className="notice" role="status"><strong>{t("Partial loading")}</strong>{limits.map((limit, i) => <p key={i}>{limit.name}: {t(limit.code)}{limit.detail ? ` · ${limit.detail}` : ""}</p>)}<p>{t("Search covers loaded nodes only")}</p></div>}
    {!loading && <p className="inlineHint">{t("Loaded nodes")}: {nodes.length} · {t("Visible nodes")}: {visible.length} · {t("Read relations")}: {graphEdges.length}</p>}
    {!loading && nodes.length > 0 && <>
      <ul className="nodeColorLegend" aria-label={t("Node color legend")}>{semanticViews.map(([role, name]) =>
        <li key={role} data-viewpoint={role}><span className="nodeColorSwatches" aria-hidden="true">{VIEWPOINT_COLORS[role].map(color => <i key={color} style={{ backgroundColor: color }} />)}</span>{t(name)}</li>
      )}<li data-viewpoint="unclassified"><span className="nodeColorSwatches" aria-hidden="true">{UNCLASSIFIED_COLORS.map(color => <i key={color} style={{ backgroundColor: color }} />)}</span>{t("Unclassified / multiple viewpoints")}</li></ul>
      <p className="inlineHint">{t("Color families indicate viewpoints; shade differences distinguish nodes, not importance.")}</p>
    </>}
    {!loading && graphEdges.some(edge => edge.edgeKind === "structured_reference") && <p className="inlineHint">{t("Solid lines: asserted relations. Dashed lines: recorded structured references; labels show source fields.")}</p>}
    {search && <div className="searchMatches" aria-label={t("Search matches")}><p>{t("Matches in loaded viewpoint")}: {matches.length}</p>{matches.length ? matches.map(node => <button key={node.iri} onClick={() => select(node.iri)}>{node.label}</button>) : <p>{t("No matches in the loaded viewpoint")}</p>}</div>}
    <div className={`modelBody${selectedNode ? " hasDetail" : ""}`}><div className="panel graphPanel"><ForceGraphCanvas nodes={graphNodes} edges={graphEdges} selectedNodeId={selectedNode?.iri ?? null} onSelectNode={select} highlightedNodeIds={highlighted} searchActive={Boolean(search)} emptyTitle={t(loading ? "Loading…" : error || limits.length && !nodes.length ? "Model scopes have not been loaded" : ontologyCount === 0 ? "No Ontologies in this project" : nodes.length ? "No nodes in this viewpoint" : "No model resources in the current scope")} emptyHint={t("The canvas displays the authorized default workspace only")} /></div>
    {selectedNode && selectedPosition && <aside className="panel nodeDetail" aria-label={t("Node details")}><div className="detailHeading"><h2>{selectedPosition.resource.label || selectedNode.iri}</h2><button onClick={() => select(null)} aria-label={t("Close node details")}>×</button></div><p className="resourceIri">{selectedNode.iri}</p><label>{t("Read location")}<select value={position} onChange={event => setPosition(Number(event.target.value))}>{selectedNode.positions.map((item, i) => <option key={`${item.ontologyId}:${item.graphSetId}`} value={i}>{item.ontologyName} · {item.graphSetId}</option>)}</select></label><dl className="nodeFacts"><dt>{t("Declared viewpoint")}</dt><dd>{semanticViews.some(([role]) => role === semantic.semantic_role) ? t(semanticViews.find(([role]) => role === semantic.semantic_role)![1]) : readable(semantic.semantic_role) || t("Unknown")}</dd><dt>{t("Business meaning")}</dt><dd>{readable(semantic.business_meaning) || selectedPosition.resource.description || t("Unknown")}</dd><dt>{t("Applicable scope")}</dt><dd>{readable(semantic.applicability) || t("Unknown")}</dd><dt>Ontology</dt><dd>{selectedPosition.ontologyName}</dd><dt>GraphSet</dt><dd>{selectedPosition.graphSetId}</dd><dt>{t("Source graph")}</dt><dd>{selectedPosition.resource.source_graph_iri || t("Unknown")}</dd><dt>{t("Source version")}</dt><dd>{selectedPosition.signature || t("Unknown")}</dd><dt>{t("Source time")}</dt><dd>{t("Unknown")}</dd></dl></aside>}
    </div>
  </section>;
}
