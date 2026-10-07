import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef } from "react";
import { useT } from "../i18n";
cytoscape.use(fcose);
export type ForceGraphNode = { id: string; label: string; group?: string };
export type ForceGraphEdge = { id: string; source: string; target: string; label?: string };
type Props = {
  nodes: ForceGraphNode[]; edges: ForceGraphEdge[]; selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void; highlightedNodeIds: string[]; searchActive: boolean;
  emptyTitle: string; emptyHint: string;
};
const style: cytoscape.StylesheetStyle[] = [
  { selector: "node", style: { "background-color": "#6c4df6", label: "data(label)", color: "#171821", "font-size": 12, "text-valign": "bottom", "text-margin-y": 7, "text-outline-color": "#fff", "text-outline-width": 2, "text-wrap": "wrap", "text-max-width": "150px", width: 30, height: 30 } },
  { selector: "edge", style: { width: 1.5, "line-color": "#b1abc8", "target-arrow-color": "#b1abc8", "target-arrow-shape": "triangle", "curve-style": "bezier", label: "data(label)", "font-size": 9, color: "#74788d", "text-rotation": "autorotate", "text-wrap": "wrap", "text-max-width": "140px" } },
  { selector: ".dimmed", style: { opacity: 0.22 } },
  { selector: ".highlighted", style: { "border-width": 3, "border-color": "#2fbf8f" } },
  { selector: "node:selected", style: { "border-width": 4, "border-color": "#171821" } },
];
export function ForceGraphCanvas({ nodes, edges, selectedNodeId, onSelectNode, highlightedNodeIds, searchActive, emptyTitle, emptyHint }: Props) {
  const t = useT();
  const container = useRef<HTMLDivElement>(null);
  const engine = useRef<Core | null>(null);
  const positions = useRef(new Map<string, { x: number; y: number }>());
  const select = useRef(onSelectNode);
  select.current = onSelectNode;
  const elements = useMemo<ElementDefinition[]>(() => [
    ...nodes.map(node => ({ data: { id: node.id, label: node.label }, position: positions.current.get(node.id) })),
    ...edges.map(edge => ({ data: edge })),
  ], [nodes, edges]);
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
    cy.elements().removeClass("highlighted dimmed").unselect();
    if (searchActive) {
      const ids = new Set(highlightedNodeIds);
      cy.nodes().forEach(node => { node.addClass(ids.has(node.id()) ? "highlighted" : "dimmed"); });
      cy.edges().forEach(edge => { if (!ids.has(edge.source().id()) && !ids.has(edge.target().id())) edge.addClass("dimmed"); });
    }
    if (selectedNodeId) {
      const selected = cy.getElementById(selectedNodeId);
      if (selected.nonempty()) { selected.select(); cy.center(selected); }
    }
  }, [selectedNodeId, highlightedNodeIds, searchActive, elements]);
  return <div className="graphCanvasWrap"><div className="graphZoom"><button aria-label={t("Zoom in")} onClick={() => engine.current?.zoom(Math.min(4, (engine.current?.zoom() ?? 1) * 1.3))}>+</button><button aria-label={t("Zoom out")} onClick={() => engine.current?.zoom(Math.max(0.15, (engine.current?.zoom() ?? 1) / 1.3))}>−</button><button onClick={() => engine.current?.fit(undefined, 48)}>{t("Fit graph")}</button></div>
    <div className="graphKeyboard" aria-label={t("Select model node")}>{nodes.map(node => <button key={node.id} onClick={() => select.current(node.id)} aria-label={`${t("Select node")} ${node.label}`}>{node.label}</button>)}</div>
    <div className="graphCanvas" ref={container} role="img" aria-label={t("Model graph")} data-node-count={nodes.length} data-edge-count={edges.length} />
    {!nodes.length && <div className="graphEmpty"><h3>{emptyTitle}</h3><p>{emptyHint}</p></div>}
  </div>;
}
