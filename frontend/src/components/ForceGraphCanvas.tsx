import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { GitBranch } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import type { Core, EdgeSingular, ElementDefinition } from "cytoscape";

cytoscape.use(fcose);

export type ForceGraphNode = {
  id: string;
  label: string;
  group?: string | null;
  tone?: string | null;
};

export type ForceGraphEdge = {
  id: string;
  source: string;
  target: string;
  label?: string | null;
  tone?: string | null;
};

type ForceGraphCanvasProps = {
  nodes: ForceGraphNode[];
  edges: ForceGraphEdge[];
  selectedNodeId: string | null;
  selectedEdgeId?: string | null;
  onSelectNode: (id: string | null) => void;
  onSelectEdge?: (id: string | null) => void;
  searchQuery?: string;
  groupLabels?: string[];
  emptyTitle: string;
  emptyHint?: string;
};

const GROUP_PALETTE = [
  "#4464ad",
  "#2f8f75",
  "#c47f22",
  "#7a54b8",
  "#b7477d",
  "#21899f",
  "#8b7c28",
  "#bf5a30",
  "#5f7f37",
  "#5e6a9e",
  "#a34b4b",
  "#2d7ca5",
];

const NODE_MIN_SIZE = 25;
const NODE_MAX_SIZE = 58;
const LABEL_VISIBILITY_THRESHOLD = 24;
const EDGE_LABEL_GAP = 4;

function pickColor(group: string, allGroups: string[]) {
  const idx = allGroups.indexOf(group);
  return GROUP_PALETTE[(idx >= 0 ? idx : 0) % GROUP_PALETTE.length];
}

function computeDegreeStats(degrees: number[]) {
  if (degrees.length === 0) return { mean: 0, std: 0 };
  const mean = degrees.reduce((sum, degree) => sum + degree, 0) / degrees.length;
  const variance =
    degrees.reduce((sum, degree) => sum + (degree - mean) ** 2, 0) / degrees.length;
  return { mean, std: Math.sqrt(variance) };
}

function nodeBaseSize(degree: number, mean: number, std: number) {
  if (std < 1e-6) return NODE_MIN_SIZE;
  const z = (degree - mean) / std;
  const t = Math.tanh(z * 0.5) * 0.5 + 0.5;
  return NODE_MIN_SIZE + t * (NODE_MAX_SIZE - NODE_MIN_SIZE);
}

function applyLabelVisibility(cy: Core) {
  const zoom = cy.zoom();
  cy.nodes().forEach((node) => {
    const base = Number(node.data("baseSize")) || NODE_MIN_SIZE;
    node.toggleClass("label-hidden", base * zoom < LABEL_VISIBILITY_THRESHOLD);
  });
  cy.edges().forEach((edge) => {
    const endpointsHidden =
      edge.source().hasClass("label-hidden") || edge.target().hasClass("label-hidden");
    edge.toggleClass("label-hidden", endpointsHidden);
  });
}

function applyEdgeLabelOffsets(cy: Core) {
  cy.edges().forEach((edge) => {
    const source = edge.source().position();
    const target = edge.target().position();
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const length = Math.hypot(dx, dy);

    if (length < 1e-6) {
      edge.data("labelMarginX", 0);
      edge.data("labelMarginY", -EDGE_LABEL_GAP);
      return;
    }

    let normalX = -dy / length;
    let normalY = dx / length;
    if (normalY > 0 || (Math.abs(normalY) < 1e-6 && normalX < 0)) {
      normalX *= -1;
      normalY *= -1;
    }
    edge.data("labelMarginX", normalX * EDGE_LABEL_GAP);
    edge.data("labelMarginY", normalY * EDGE_LABEL_GAP);
  });
}

function applyVisualState(
  cy: Core,
  nodes: ForceGraphNode[],
  selectedNodeId: string | null,
  selectedEdgeId: string | null,
  searchQuery: string,
) {
  cy.nodes().removeClass("dimmed highlighted").unselect();
  cy.edges().removeClass("dimmed highlighted").unselect();

  if (selectedNodeId) {
    const selectedNode = cy.getElementById(selectedNodeId);
    if (selectedNode.nonempty()) {
      selectedNode.select();
      const connectedEdges = selectedNode.connectedEdges();
      const neighborhoodIds = new Set<string>([selectedNodeId]);

      connectedEdges.forEach((edge) => {
        neighborhoodIds.add(edge.source().id());
        neighborhoodIds.add(edge.target().id());
        edge.addClass("highlighted");
      });
      cy.nodes().forEach((node) => {
        if (node.id() === selectedNodeId) return;
        node.addClass(neighborhoodIds.has(node.id()) ? "highlighted" : "dimmed");
      });
      cy.edges().forEach((edge) => {
        if (!edge.hasClass("highlighted")) edge.addClass("dimmed");
      });
      return;
    }
  }

  if (selectedEdgeId) {
    const selectedEdge = cy.getElementById(selectedEdgeId);
    if (selectedEdge.nonempty()) {
      selectedEdge.select();
      const sourceId = selectedEdge.source().id();
      const targetId = selectedEdge.target().id();
      selectedEdge.addClass("highlighted");
      cy.nodes().forEach((node) => {
        if (node.id() === sourceId || node.id() === targetId) {
          node.addClass("highlighted");
        } else {
          node.addClass("dimmed");
        }
      });
      cy.edges().forEach((edge) => {
        if (edge.id() !== selectedEdgeId) edge.addClass("dimmed");
      });
      return;
    }
  }

  const query = searchQuery.trim().toLowerCase();
  if (!query) return;
  const matched = new Set<string>();
  cy.nodes().forEach((node) => {
    const label = String(node.data("label") || "").toLowerCase();
    const graphNode = nodes.find((item) => item.id === node.id());
    const groupHit = graphNode?.group?.toLowerCase().includes(query) ?? false;
    if (label.includes(query) || groupHit) {
      matched.add(node.id());
    } else {
      node.addClass("dimmed");
    }
  });
  cy.edges().forEach((edge) => {
    const connected = matched.has(edge.source().id()) || matched.has(edge.target().id());
    if (!connected) edge.addClass("dimmed");
  });
}

const CYTO_STYLE: cytoscape.StylesheetStyle[] = [
  {
    selector: "node",
    style: {
      "background-color": "data(color)",
      "background-opacity": 1,
      label: "data(label)",
      color: "#151720",
      "font-size": 11,
      "font-weight": 600,
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 6,
      "text-outline-width": 2,
      "text-outline-color": "#ffffff",
      width: "data(baseSize)",
      height: "data(baseSize)",
      "border-width": 0,
      "transition-property": "width, height, opacity, border-width",
      "transition-duration": 180,
    },
  },
  {
    selector: "node:selected",
    style: {
      "border-width": 3,
      "border-color": "#151720",
      "border-opacity": 0.9,
    },
  },
  {
    selector: ".dimmed",
    style: {
      opacity: 0.18,
    },
  },
  {
    selector: ".highlighted",
    style: {
      "border-width": 2,
      "border-color": "#4464ad",
      "border-opacity": 0.8,
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "#a5a9ba",
      "line-opacity": 0.72,
      "target-arrow-color": "#a5a9ba",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.85,
      label: "data(label)",
      "font-size": 5,
      color: "#74788d",
      "text-rotation": "autorotate",
      "text-margin-x": (edge: EdgeSingular) => Number(edge.data("labelMarginX")) || 0,
      "text-margin-y": (edge: EdgeSingular) => Number(edge.data("labelMarginY")) || 0,
    },
  },
  {
    selector: "edge.highlighted",
    style: {
      width: 3,
      "line-color": "#4464ad",
      "line-opacity": 0.95,
      "target-arrow-color": "#4464ad",
      "arrow-scale": 1,
      color: "#35529a",
      "font-size": 6,
      "font-weight": 600,
      "text-opacity": 1,
      "z-index": 10,
    },
  },
  {
    selector: "edge:selected",
    style: {
      width: 3.2,
      "line-color": "#151720",
      "target-arrow-color": "#151720",
      "line-opacity": 1,
    },
  },
  {
    selector: "edge.dimmed",
    style: {
      "line-opacity": 0.08,
      "target-arrow-color": "#eceef6",
      "text-opacity": 0,
    },
  },
  {
    selector: "node.label-hidden",
    style: {
      label: "",
    },
  },
  {
    selector: "edge.label-hidden",
    style: {
      label: "",
    },
  },
];

export function ForceGraphCanvas({
  nodes,
  edges,
  selectedNodeId,
  selectedEdgeId = null,
  onSelectNode,
  onSelectEdge,
  searchQuery = "",
  groupLabels,
  emptyTitle,
  emptyHint,
}: ForceGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelectNode);
  const onSelectEdgeRef = useRef(onSelectEdge);
  onSelectRef.current = onSelectNode;
  onSelectEdgeRef.current = onSelectEdge;

  const allGroups = useMemo(() => {
    if (groupLabels && groupLabels.length > 0) return groupLabels;
    return Array.from(new Set(nodes.map((node) => node.group || "Ungrouped"))).sort();
  }, [nodes, groupLabels]);

  const elements = useMemo<ElementDefinition[]>(() => {
    const visibleIds = new Set(nodes.map((node) => node.id));
    const visibleEdges = edges.filter(
      (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target),
    );
    const degree = new Map<string, number>();
    visibleEdges.forEach((edge) => {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    });

    const degreeValues = nodes.map((node) => degree.get(node.id) ?? 0);
    const { mean, std } = computeDegreeStats(degreeValues);
    const cyNodes: ElementDefinition[] = nodes.map((node) => {
      const group = node.group || "Ungrouped";
      const nodeDegree = degree.get(node.id) ?? 0;
      return {
        data: {
          id: node.id,
          label: node.label,
          group,
          color: node.tone || pickColor(group, allGroups),
          degree: nodeDegree,
          baseSize: nodeBaseSize(nodeDegree, mean, std),
        },
      };
    });
    const cyEdges: ElementDefinition[] = visibleEdges.map((edge) => ({
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label || "",
        labelMarginX: 0,
        labelMarginY: 0,
      },
    }));
    return [...cyNodes, ...cyEdges];
  }, [nodes, edges, allGroups]);

  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: CYTO_STYLE,
      layout: { name: "fcose", animate: false, randomize: false } as cytoscape.LayoutOptions,
      minZoom: 0.18,
      maxZoom: 3,
      wheelSensitivity: 2,
    });
    cy.on("tap", "node", (event) => {
      onSelectEdgeRef.current?.(null);
      onSelectRef.current(String(event.target.id()));
    });
    cy.on("tap", "edge", (event) => {
      onSelectRef.current(null);
      onSelectEdgeRef.current?.(String(event.target.id()));
    });
    cy.on("tap", (event) => {
      if (event.target === cy) {
        onSelectRef.current(null);
        onSelectEdgeRef.current?.(null);
      }
    });
    const onViewportChange = () => applyLabelVisibility(cy);
    const onNodePositionSettled = () => applyEdgeLabelOffsets(cy);
    cy.on("zoom pan", onViewportChange);
    cy.on("free", "node", onNodePositionSettled);
    cyRef.current = cy;
    return () => {
      cy.off("zoom pan", onViewportChange);
      cy.off("free", "node", onNodePositionSettled);
      cy.destroy();
      cyRef.current = null;
    };
  }, []);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.elements().remove();
    if (elements.length === 0) return;
    cy.add(elements);
    const layout = cy.layout({
      name: "fcose",
      animate: true,
      animationDuration: 320,
      animationEasing: "ease-out",
      randomize: cy.nodes().length > 12,
      nodeSep: 64,
      idealEdgeLength: 132,
      uniformNodeDimensions: true,
    } as unknown as cytoscape.LayoutOptions);
    layout.one("layoutstop", () => {
      applyEdgeLabelOffsets(cy);
      cy.fit(undefined, 52);
      applyLabelVisibility(cy);
    });
    layout.run();
  }, [elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    applyVisualState(cy, nodes, selectedNodeId, selectedEdgeId, searchQuery);
  }, [selectedNodeId, selectedEdgeId, searchQuery, nodes, elements]);

  return (
    <div className="entityGraphCanvasWrap">
      <div className="srOnlyGraphControls" aria-label="force graph selectable items">
        {nodes.map((node) => (
          <button
            key={node.id}
            type="button"
            onClick={() => {
              onSelectEdgeRef.current?.(null);
              onSelectRef.current(node.id);
            }}
            aria-label={`Select node ${node.label}`}
          >
            {node.label}
          </button>
        ))}
        {edges.map((edge) => (
          <button
            key={edge.id}
            type="button"
            onClick={() => {
              onSelectRef.current(null);
              onSelectEdgeRef.current?.(edge.id);
            }}
            aria-label={`Select edge ${edge.label || edge.id}`}
          >
            {edge.label || edge.id}
          </button>
        ))}
      </div>
      {nodes.length === 0 ? (
        <div className="entityGraphEmpty">
          <div>
            <GitBranch size={24} />
            <h3>{emptyTitle}</h3>
            {emptyHint && <p>{emptyHint}</p>}
          </div>
        </div>
      ) : null}
      <div className="entityGraphCanvas" data-testid="force-graph-canvas" ref={containerRef} />
    </div>
  );
}
