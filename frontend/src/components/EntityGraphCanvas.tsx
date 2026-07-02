import dagre from "@dagrejs/dagre";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef } from "react";
import type { Core, EdgeSingular, ElementDefinition } from "cytoscape";
import type { Entity, Relation } from "../types";

cytoscape.use(fcose);

type EntityGraphCanvasProps = {
  entities: Entity[];
  relations: Relation[];
  selectedEntityId: string | null;
  onSelectEntity: (id: string | null) => void;
  classFilter: string[];
  searchQuery: string;
  classLabels?: string[];
  layoutMode: EntityGraphLayout;
};

export type EntityGraphLayout = "hierarchical" | "force";

export const CLASS_PALETTE = [
  "#6c4df6",
  "#2fbf8f",
  "#f5b84b",
  "#3b82f6",
  "#ec4899",
  "#14b8a6",
  "#f97316",
  "#8b5cf6",
  "#06b6d4",
  "#84cc16",
  "#ef4444",
  "#0ea5e9",
];

export function pickColor(classLabel: string, allLabels: string[]) {
  const idx = allLabels.indexOf(classLabel);
  return CLASS_PALETTE[(idx >= 0 ? idx : 0) % CLASS_PALETTE.length];
}

const NODE_MIN_SIZE = 24;
const NODE_MAX_SIZE = 56;
const LABEL_VISIBILITY_THRESHOLD = 24;
const EDGE_LABEL_GAP = 4;
const HIERARCHICAL_NODE_SEPARATION = 38;
const HIERARCHICAL_RANK_SEPARATION = 130;

function hierarchicalPositions(cy: Core) {
  const graph = new dagre.graphlib.Graph({ multigraph: true })
    .setDefaultEdgeLabel(() => ({}))
    .setGraph({
      acyclicer: "greedy",
      edgesep: 28,
      marginx: 40,
      marginy: 40,
      nodesep: HIERARCHICAL_NODE_SEPARATION,
      rankdir: "LR",
      ranker: "network-simplex",
      ranksep: HIERARCHICAL_RANK_SEPARATION,
    });

  cy.nodes()
    .sort((left, right) => left.id().localeCompare(right.id()))
    .forEach((node) => {
      const baseSize = Number(node.data("baseSize")) || NODE_MIN_SIZE;
      const labelWidth = Math.min(140, Math.max(baseSize, String(node.data("label")).length * 7));
      graph.setNode(node.id(), { height: baseSize + 22, width: labelWidth });
    });
  cy.edges()
    .sort((left, right) => left.id().localeCompare(right.id()))
    .forEach((edge) => {
      graph.setEdge(edge.source().id(), edge.target().id(), {}, edge.id());
    });

  dagre.layout(graph);
  return Object.fromEntries(
    cy.nodes().map((node) => {
      const position = graph.node(node.id());
      return [node.id(), { x: position?.x ?? 0, y: position?.y ?? 0 }];
    }),
  );
}

function computeDegreeStats(degrees: number[]) {
  if (degrees.length === 0) return { mean: 0, std: 0 };
  const mean = degrees.reduce((sum, d) => sum + d, 0) / degrees.length;
  const variance =
    degrees.reduce((sum, d) => sum + (d - mean) ** 2, 0) / degrees.length;
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
      edge.source().hasClass("label-hidden") ||
      edge.target().hasClass("label-hidden");
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
    // Keep labels on the upper (or right-hand, for vertical edges) side for consistency.
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
  entities: Entity[],
  selectedEntityId: string | null,
  searchQuery: string,
) {
  cy.nodes().removeClass("dimmed highlighted").unselect();
  cy.edges().removeClass("dimmed highlighted");

  if (selectedEntityId) {
    const selectedNode = cy.getElementById(selectedEntityId);
    if (selectedNode.nonempty()) {
      selectedNode.select();
      const connectedEdges = selectedNode.connectedEdges();
      const neighborhoodIds = new Set<string>([selectedEntityId]);

      connectedEdges.forEach((edge) => {
        neighborhoodIds.add(edge.source().id());
        neighborhoodIds.add(edge.target().id());
        edge.addClass("highlighted");
      });
      cy.nodes().forEach((node) => {
        if (node.id() === selectedEntityId) return;
        node.addClass(neighborhoodIds.has(node.id()) ? "highlighted" : "dimmed");
      });
      cy.edges().forEach((edge) => {
        if (!edge.hasClass("highlighted")) edge.addClass("dimmed");
      });
      return;
    }
  }

  const query = searchQuery.trim().toLowerCase();
  if (!query) return;
  const matched = new Set<string>();
  cy.nodes().forEach((node) => {
    const label = String(node.data("label") || "").toLowerCase();
    const entity = entities.find((item) => item.id === node.id());
    const aliasHit = entity?.aliases.some((alias) => alias.toLowerCase().includes(query)) ?? false;
    if (label.includes(query) || aliasHit) {
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
      color: "#171821",
      "font-size": 11,
      "font-weight": 600,
      "text-valign": "bottom",
      "text-halign": "center",
      "text-margin-y": 5,
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
      "border-color": "#171821",
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
      "border-color": "#6c4df6",
      "border-opacity": 0.7,
    },
  },
  {
    selector: "edge",
    style: {
      width: 1.5,
      "line-color": "#a5a9ba",
      "line-opacity": 0.7,
      "target-arrow-color": "#a5a9ba",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 0.85,
      label: "data(label)",
      "font-size": 4.5,
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
      "line-color": "#6c4df6",
      "line-opacity": 0.95,
      "target-arrow-color": "#6c4df6",
      "arrow-scale": 1,
      color: "#5d3fec",
      "font-size": 6,
      "font-weight": 600,
      "text-opacity": 1,
      "z-index": 10,
    },
  },
  {
    selector: "edge.dimmed",
    style: {
      "line-opacity": 0.08,
      "target-arrow-color": "#eceef6",
      "text-opacity": 0.0,
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

export function EntityGraphCanvas(props: EntityGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const singleVisibleEntityIdRef = useRef<string | null>(null);

  // Latest props mirrored in refs so the singleton event handler always sees fresh values.
  const onSelectRef = useRef(props.onSelectEntity);
  onSelectRef.current = props.onSelectEntity;

  const allClassLabels = useMemo(() => {
    if (props.classLabels && props.classLabels.length > 0) return props.classLabels;
    const labels = new Set<string>();
    props.entities.forEach((entity) => labels.add(entity.class_label));
    return Array.from(labels).sort();
  }, [props.entities, props.classLabels]);

  const singleVisibleEntityId = useMemo(() => {
    const classSet = new Set(props.classFilter);
    const visibleEntities =
      classSet.size === 0
        ? props.entities
        : props.entities.filter((entity) => classSet.has(entity.class_label));
    return visibleEntities.length === 1 ? visibleEntities[0].id : null;
  }, [props.entities, props.classFilter]);

  const elements = useMemo<ElementDefinition[]>(() => {
    const classSet = new Set(props.classFilter);
    const visibleEntities =
      classSet.size === 0
        ? props.entities
        : props.entities.filter((entity) => classSet.has(entity.class_label));
    const visibleIds = new Set(visibleEntities.map((entity) => entity.id));
    const visibleRelations = props.relations.filter(
      (relation) =>
        visibleIds.has(relation.source_entity_id) && visibleIds.has(relation.target_entity_id),
    );

    const degree = new Map<string, number>();
    visibleRelations.forEach((relation) => {
      degree.set(relation.source_entity_id, (degree.get(relation.source_entity_id) ?? 0) + 1);
      degree.set(relation.target_entity_id, (degree.get(relation.target_entity_id) ?? 0) + 1);
    });

    const degreeValues = visibleEntities.map((entity) => degree.get(entity.id) ?? 0);
    const { mean, std } = computeDegreeStats(degreeValues);

    const nodes: ElementDefinition[] = visibleEntities.map((entity) => {
      const nodeDegree = degree.get(entity.id) ?? 0;
      return {
        data: {
          id: entity.id,
          label: entity.name,
          classLabel: entity.class_label,
          color: pickColor(entity.class_label, allClassLabels),
          degree: nodeDegree,
          baseSize: nodeBaseSize(nodeDegree, mean, std),
        },
      };
    });
    const edges: ElementDefinition[] = visibleRelations.map((relation) => ({
      data: {
        id: relation.id,
        source: relation.source_entity_id,
        target: relation.target_entity_id,
        label: relation.relation_type,
        labelMarginX: 0,
        labelMarginY: 0,
      },
    }));
    return [...nodes, ...edges];
  }, [props.entities, props.relations, props.classFilter, allClassLabels]);

  singleVisibleEntityIdRef.current = singleVisibleEntityId;

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    const onContainerClick = () => {
      if (singleVisibleEntityIdRef.current) onSelectRef.current(singleVisibleEntityIdRef.current);
    };
    container.addEventListener("click", onContainerClick, true);
    const cy = cytoscape({
      container,
      elements: [],
      style: CYTO_STYLE,
      layout: { name: "fcose", animate: false, randomize: false } as cytoscape.LayoutOptions,
      minZoom: 0.18,
      maxZoom: 3,
      wheelSensitivity: 2,
    });
    cy.on("tap", "node", (event) => onSelectRef.current(String(event.target.id())));
    cy.on("tap", (event) => {
      if (event.target === cy) onSelectRef.current(singleVisibleEntityIdRef.current);
    });
    const onViewportChange = () => applyLabelVisibility(cy);
    const onNodePositionSettled = () => applyEdgeLabelOffsets(cy);
    cy.on("zoom pan", onViewportChange);
    cy.on("free", "node", onNodePositionSettled);
    cyRef.current = cy;
    return () => {
      container.removeEventListener("click", onContainerClick, true);
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
    const sharedLayoutOptions = {
      animate: true,
      animationDuration: 320,
      animationEasing: "ease-out",
      fit: false,
    };
    const layout = props.layoutMode === "hierarchical"
      ? cy.layout({
          ...sharedLayoutOptions,
          name: "preset",
          positions: hierarchicalPositions(cy),
        } as unknown as cytoscape.LayoutOptions)
      : cy.layout({
          ...sharedLayoutOptions,
          name: "fcose",
          idealEdgeLength: 130,
          nodeRepulsion: 7000,
          nodeSeparation: 90,
          numIter: 3200,
          quality: "default",
          randomize: cy.nodes().length > 12,
          tile: true,
          tilingPaddingHorizontal: 24,
          tilingPaddingVertical: 24,
          uniformNodeDimensions: true,
        } as unknown as cytoscape.LayoutOptions);
    layout.one("layoutstop", () => {
      applyEdgeLabelOffsets(cy);
      cy.fit(undefined, 50);
      applyLabelVisibility(cy);
    });
    layout.run();
  }, [elements, props.layoutMode]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    applyVisualState(cy, props.entities, props.selectedEntityId, props.searchQuery);
  }, [props.selectedEntityId, props.searchQuery, props.entities, props.layoutMode, elements]);

  return (
    <div
      className="entityGraphCanvas"
      ref={containerRef}
      data-single-visible-entity-id={singleVisibleEntityId ?? ""}
    />
  );
}
