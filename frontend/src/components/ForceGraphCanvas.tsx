import { graphlib, layout as dagreLayout } from "@dagrejs/dagre";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { GitBranch } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import type { Core, EdgeSingular, ElementDefinition, NodeSingular } from "cytoscape";

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
  kind?: string | null;
  stale?: boolean | null;
};

type DerivedFocus = "reasoning" | "rules" | null;

type ForceGraphCanvasProps = {
  nodes: ForceGraphNode[];
  edges: ForceGraphEdge[];
  layoutMode?: "force" | "hierarchy";
  selectedNodeId: string | null;
  selectedEdgeId?: string | null;
  onSelectNode: (id: string | null) => void;
  onSelectEdge?: (id: string | null) => void;
  searchQuery?: string;
  groupLabels?: string[];
  derivedFocus?: DerivedFocus;
  emptyTitle: string;
  emptyHint?: string;
  cacheKey?: string;
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
const HIERARCHY_MIN_NODE_WIDTH = 120;
const HIERARCHY_NODE_HEIGHT = 58;
const LAYOUT_CACHE_PREFIX = "topology:layout:";

function hashFingerprint(input: string): string {
  let hash = 5381;
  for (let i = 0; i < input.length; i++) {
    hash = ((hash << 5) + hash + input.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(36);
}

function loadCachedLayout(
  cacheKey: string,
  layoutMode: string,
): { fingerprint: string; positions: Record<string, { x: number; y: number }> } | null {
  try {
    const raw = localStorage.getItem(`${LAYOUT_CACHE_PREFIX}${cacheKey}:${layoutMode}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.fingerprint === "string" && parsed.positions) {
      return parsed;
    }
    return null;
  } catch {
    return null;
  }
}

function saveCachedLayout(
  cacheKey: string,
  layoutMode: string,
  fingerprint: string,
  positions: Record<string, { x: number; y: number }>,
) {
  try {
    localStorage.setItem(
      `${LAYOUT_CACHE_PREFIX}${cacheKey}:${layoutMode}`,
      JSON.stringify({ fingerprint, positions }),
    );
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

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

function computeHierarchyPositions(cy: Core) {
  const graph = new graphlib.Graph({ multigraph: true });
  graph.setGraph({
    rankdir: "TB",
    nodesep: 72,
    ranksep: 112,
    edgesep: 28,
    marginx: 24,
    marginy: 24,
  });
  graph.setDefaultEdgeLabel(() => ({}));

  cy.nodes().forEach((node) => {
    const label = String(node.data("label") || node.id());
    graph.setNode(node.id(), {
      width: Math.max(HIERARCHY_MIN_NODE_WIDTH, label.length * 7 + 34),
      height: HIERARCHY_NODE_HEIGHT,
    });
  });

  const subclassEdges = cy.edges().filter((edge) => edge.id().startsWith("subclass:"));
  const layoutEdges = subclassEdges.length > 0 ? subclassEdges : cy.edges();
  layoutEdges.forEach((edge) => {
    const sourceId = edge.source().id();
    const targetId = edge.target().id();
    if (edge.id().startsWith("subclass:")) {
      graph.setEdge(targetId, sourceId, { weight: 2 }, edge.id());
    } else {
      graph.setEdge(sourceId, targetId, { weight: 1 }, edge.id());
    }
  });

  dagreLayout(graph);
  const positions = new Map<string, { x: number; y: number }>();
  for (const nodeId of graph.nodes()) {
    const position = graph.node(nodeId);
    if (position) positions.set(nodeId, { x: position.x, y: position.y });
  }
  return positions;
}

function getPresetNodeId(node: string | NodeSingular) {
  return typeof node === "string" ? node : node.id();
}

function applyVisualState(
  cy: Core,
  nodes: ForceGraphNode[],
  selectedNodeId: string | null,
  selectedEdgeId: string | null,
  searchQuery: string,
  derivedFocus: DerivedFocus,
) {
  cy.nodes().removeClass("dimmed highlighted focus-dimmed focus-highlighted").unselect();
  cy.edges().removeClass("dimmed highlighted focus-dimmed focus-highlighted").unselect();

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
  if (!query && derivedFocus) {
    const targetKinds =
      derivedFocus === "reasoning"
        ? new Set(["owl_inferred", "inferred"])
        : new Set(["rule_derived"]);
    const highlightedNodes = new Set<string>();
    cy.edges().forEach((edge) => {
      const kind = String(edge.data("kind") || "").toLowerCase();
      if (targetKinds.has(kind)) {
        edge.addClass("focus-highlighted");
        highlightedNodes.add(edge.source().id());
        highlightedNodes.add(edge.target().id());
      } else {
        edge.addClass("focus-dimmed");
      }
    });
    if (highlightedNodes.size > 0) {
      cy.nodes().forEach((node) => {
        node.addClass(highlightedNodes.has(node.id()) ? "focus-highlighted" : "focus-dimmed");
      });
    }
    return;
  }

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
    selector: 'edge[kind = "owl_inferred"], edge[kind = "inferred"]',
    style: {
      width: 2.2,
      "line-color": "#5668d9",
      "target-arrow-color": "#5668d9",
      "line-opacity": 0.86,
      color: "#4856b8",
      "font-weight": 600,
    },
  },
  {
    selector: 'edge[kind = "rule_derived"]',
    style: {
      width: 2.2,
      "line-color": "#2f8f75",
      "target-arrow-color": "#2f8f75",
      "line-opacity": 0.86,
      color: "#257561",
      "font-weight": 600,
    },
  },
  {
    selector: 'edge[stale = "true"]',
    style: {
      "line-style": "dashed",
      "line-opacity": 0.58,
      "target-arrow-shape": "triangle",
    },
  },
  {
    selector: "edge.focus-highlighted",
    style: {
      width: 3.4,
      "line-opacity": 1,
      "arrow-scale": 1.05,
      "font-size": 6,
      "text-opacity": 1,
      "z-index": 9,
    },
  },
  {
    selector: "edge.focus-dimmed",
    style: {
      "line-opacity": 0.16,
      "target-arrow-color": "#d7dbe8",
      "text-opacity": 0,
    },
  },
  {
    selector: "node.focus-highlighted",
    style: {
      "border-width": 2,
      "border-color": "#5668d9",
      "border-opacity": 0.72,
    },
  },
  {
    selector: "node.focus-dimmed",
    style: {
      opacity: 0.42,
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
  layoutMode = "force",
  selectedNodeId,
  selectedEdgeId = null,
  onSelectNode,
  onSelectEdge,
  searchQuery = "",
  groupLabels,
  derivedFocus = null,
  emptyTitle,
  emptyHint,
  cacheKey,
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
        kind: normalizeEdgeKind(edge.kind),
        stale: edge.stale ? "true" : "false",
        labelMarginX: 0,
        labelMarginY: 0,
      },
    }));
    return [...cyNodes, ...cyEdges];
  }, [nodes, edges, allGroups]);

  const fingerprint = useMemo(() => {
    const nodeIds = nodes.map((n) => n.id).sort().join(",");
    const edgeIds = edges.map((e) => e.id).sort().join(",");
    return hashFingerprint(`${nodeIds}|${edgeIds}|${layoutMode}`);
  }, [nodes, edges, layoutMode]);

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

    let cachedPositions: Record<string, { x: number; y: number }> | null = null;
    if (cacheKey) {
      const cached = loadCachedLayout(cacheKey, layoutMode);
      if (cached && cached.fingerprint === fingerprint) {
        cachedPositions = cached.positions;
      }
    }
    if (cachedPositions) {
      const layout = cy.layout({
        name: "preset",
        animate: true,
        animationDuration: 80,
        positions: (node) => {
          const pos = cachedPositions![getPresetNodeId(node)];
          return pos ?? cy.getElementById(getPresetNodeId(node)).position();
        },
      });
      layout.one("layoutstop", () => {
        applyEdgeLabelOffsets(cy);
        cy.fit(undefined, 52);
        applyLabelVisibility(cy);
      });
      layout.run();
      return;
    }

    const hierarchyPositions =
      layoutMode === "hierarchy" ? computeHierarchyPositions(cy) : null;
    const layout = cy.layout(
      layoutMode === "hierarchy"
        ? ({
            name: "preset",
            animate: true,
            animationDuration: 320,
            animationEasing: "ease-out",
            positions: (node) => {
              const nodeId = getPresetNodeId(node);
              return hierarchyPositions?.get(nodeId) ?? cy.getElementById(nodeId).position();
            },
          } as cytoscape.LayoutOptions)
        : ({
            name: "fcose",
            animate: true,
            animationDuration: 320,
            animationEasing: "ease-out",
            randomize: cy.nodes().length > 12,
            nodeSep: 64,
            idealEdgeLength: 132,
            uniformNodeDimensions: true,
          } as unknown as cytoscape.LayoutOptions),
    );
    layout.one("layoutstop", () => {
      applyEdgeLabelOffsets(cy);
      cy.fit(undefined, 52);
      applyLabelVisibility(cy);
      if (cacheKey) {
        const positions: Record<string, { x: number; y: number }> = {};
        cy.nodes().forEach((node) => {
          const pos = node.position();
          positions[node.id()] = { x: pos.x, y: pos.y };
        });
        saveCachedLayout(cacheKey, layoutMode, fingerprint, positions);
      }
    });
    layout.run();
  }, [elements, layoutMode, fingerprint, cacheKey]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    applyVisualState(cy, nodes, selectedNodeId, selectedEdgeId, searchQuery, derivedFocus);
  }, [selectedNodeId, selectedEdgeId, searchQuery, derivedFocus, nodes, elements]);

  return (
    <div className="entityGraphCanvasWrap">
      <div className="srOnlyGraphControls" aria-label="graph selectable items">
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
            data-edge-kind={normalizeEdgeKind(edge.kind)}
            data-edge-stale={edge.stale ? "true" : "false"}
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

function normalizeEdgeKind(kind: string | null | undefined) {
  return (kind || "asserted").toLowerCase().replace(/[-\s]/g, "_");
}
