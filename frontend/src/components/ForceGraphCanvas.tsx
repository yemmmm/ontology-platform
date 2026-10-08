import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef } from "react";
import { useT } from "../i18n";
import { connectionColor, type NodeColorFamily } from "./nodeColors";
cytoscape.use(fcose);
export type ForceGraphNode = { id: string; label: string; colorFamily: NodeColorFamily; group?: string };
export type ForceGraphEdge = { id: string; source: string; target: string; label?: string; edgeKind?: string };
type Props = {
  nodes: ForceGraphNode[]; edges: ForceGraphEdge[]; selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void; highlightedNodeIds: string[]; searchActive: boolean;
  emptyTitle: string; emptyHint: string;
};
const NODE_MIN_SIZE = 25;
const NODE_MAX_SIZE = 58;
const style: cytoscape.StylesheetStyle[] = [
  { selector: "node", style: { "background-color": "data(color)", "border-width": 1, "border-color": "#171821", "border-opacity": 0.22, label: "data(label)", color: "#171821", "font-size": 12, "text-valign": "bottom", "text-margin-y": 7, "text-outline-color": "#fff", "text-outline-width": 2, "text-wrap": "wrap", "text-max-width": "150px", width: "data(baseSize)", height: "data(baseSize)" } },
  { selector: "edge", style: { width: 1.5, "line-color": "#b1abc8", "target-arrow-color": "#b1abc8", "target-arrow-shape": "triangle", "curve-style": "bezier", label: "data(label)", "font-size": 9, color: "#74788d", "text-rotation": "autorotate", "text-wrap": "wrap", "text-max-width": "140px" } },
  { selector: 'edge[edgeKind = "structured_reference"]', style: { "line-style": "dashed" } },
  { selector: ".dimmed", style: { opacity: 0.22 } },
  { selector: "node.selection-dimmed", style: { "background-color": "#c4c6cd", color: "#74788d" } },
  { selector: ".highlighted", style: { "underlay-color": "#171821", "underlay-opacity": 0.16, "underlay-padding": 5 } },
  { selector: "edge.highlighted", style: { width: 3, "line-color": "#6b5cad", "target-arrow-color": "#6b5cad" } },
  { selector: "node:selected", style: { "border-width": 4, "border-color": "#171821", "border-opacity": 1 } },
];
export function ForceGraphCanvas({ nodes, edges, selectedNodeId, onSelectNode, highlightedNodeIds, searchActive, emptyTitle, emptyHint }: Props) {
  const t = useT();
  const container = useRef<HTMLDivElement>(null);
  const engine = useRef<Core | null>(null);
  const positions = useRef(new Map<string, { x: number; y: number }>());
  const select = useRef(onSelectNode);
  select.current = onSelectNode;
  const elements = useMemo<ElementDefinition[]>(() => {
    if (!nodes.length) return [];
    const degree = new Map<string, number>();
    edges.forEach(edge => {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    });
    const degrees = nodes.map(node => degree.get(node.id) ?? 0);
    const mean = degrees.reduce((sum, value) => sum + value, 0) / nodes.length;
    const std = Math.sqrt(degrees.reduce((sum, value) => sum + (value - mean) ** 2, 0) / nodes.length);
    return [
      ...nodes.map(node => {
        const nodeDegree = degree.get(node.id) ?? 0;
        const strength = std < 1e-6 ? 0
          : Math.tanh((nodeDegree - mean) / std * 0.5) * 0.5 + 0.5;
        const baseSize = NODE_MIN_SIZE + strength * (NODE_MAX_SIZE - NODE_MIN_SIZE);
        return { data: { id: node.id, label: node.label, color: connectionColor(node.colorFamily, strength), degree: nodeDegree, baseSize }, position: positions.current.get(node.id) };
      }),
      ...edges.map(edge => ({ data: edge })),
    ];
  }, [nodes, edges]);
  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({ container: container.current, style, elements: [], minZoom: 0.15, maxZoom: 4, wheelSensitivity: 0.25 });
    engine.current = cy;
    cy.on("tap", "node", event => select.current(String(event.target.id())));
    cy.on("tap", event => { if (event.target === cy) select.current(null); });
    cy.on("free", "node", event => positions.current.set(event.target.id(), { ...event.target.position() }));
    const observer = new ResizeObserver(() => cy.resize());
    observer.observe(container.current);
    return () => { observer.disconnect(); cy.destroy(); engine.current = null; };
  }, []);
  useEffect(() => {
    const cy = engine.current;
    if (!cy) return;
    cy.nodes().forEach(node => { positions.current.set(node.id(), { ...node.position() }); });
    cy.elements().remove();
    if (!elements.length) return;
    cy.add(elements);
    const known = nodes.every(node => positions.current.has(node.id));
    if (known) {
      cy.nodes().forEach(node => { node.position(positions.current.get(node.id())!); });
      cy.fit(undefined, 48);
    } else {
      const layout = cy.layout({ name: "fcose", animate: false, randomize: true, nodeDimensionsIncludeLabels: true, nodeSeparation: 85, idealEdgeLength: 140, tilingPaddingHorizontal: 45, tilingPaddingVertical: 40 } as unknown as cytoscape.LayoutOptions);
      layout.one("layoutstop", () => {
        cy.nodes().forEach(node => { const saved = positions.current.get(node.id()); if (saved) node.position(saved); else positions.current.set(node.id(), { ...node.position() }); });
        cy.fit(undefined, 48);
      });
      layout.run();
    }
  }, [elements, nodes]);
  useEffect(() => {
    const cy = engine.current;
    if (!cy) return;
    cy.elements().removeClass("highlighted dimmed selection-dimmed").unselect();
    const selected = selectedNodeId ? cy.getElementById(selectedNodeId) : cy.collection();
    if (selected.nonempty()) {
      const neighborhood = selected.closedNeighborhood();
      neighborhood.addClass("highlighted");
      cy.elements().difference(neighborhood).addClass("dimmed");
      cy.nodes().difference(neighborhood).addClass("selection-dimmed");
      selected.select();
      cy.center(selected);
      return;
    }
    if (searchActive) {
      const ids = new Set(highlightedNodeIds);
      cy.nodes().forEach(node => { node.addClass(ids.has(node.id()) ? "highlighted" : "dimmed"); });
      cy.edges().forEach(edge => { if (!ids.has(edge.source().id()) && !ids.has(edge.target().id())) edge.addClass("dimmed"); });
    }
  }, [selectedNodeId, highlightedNodeIds, searchActive, elements]);
  return <div className="graphCanvasWrap"><div className="graphZoom"><button aria-label={t("Zoom in")} onClick={() => engine.current?.zoom(Math.min(4, (engine.current?.zoom() ?? 1) * 1.3))}>+</button><button aria-label={t("Zoom out")} onClick={() => engine.current?.zoom(Math.max(0.15, (engine.current?.zoom() ?? 1) / 1.3))}>−</button><button onClick={() => engine.current?.fit(undefined, 48)}>{t("Fit graph")}</button></div>
    <div className="graphKeyboard" aria-label={t("Select model node")}>{nodes.map(node => <button key={node.id} onClick={() => select.current(node.id)} aria-label={`${t("Select node")} ${node.label}`}>{node.label}</button>)}</div>
    <div className="graphCanvas" ref={container} role="img" aria-label={t("Model graph")} data-node-count={nodes.length} data-edge-count={edges.length} data-reference-count={edges.filter(edge => edge.edgeKind === "structured_reference").length} />
    {!nodes.length && <div className="graphEmpty"><h3>{emptyTitle}</h3><p>{emptyHint}</p></div>}
  </div>;
}
