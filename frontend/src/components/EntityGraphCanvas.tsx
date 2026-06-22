import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef } from "react";
import type { Core, ElementDefinition } from "cytoscape";
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
};

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
      width: 34,
      height: 34,
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
      width: 46,
      height: 46,
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
      "font-size": 9,
      color: "#74788d",
      "text-background-color": "#ffffff",
      "text-background-opacity": 0.85,
      "text-background-padding": "2px",
      "text-background-shape": "roundrectangle",
      "text-rotation": "autorotate",
      "text-border-color": "#eceef6",
      "text-border-width": 1,
      "text-border-opacity": 1,
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
];

export function EntityGraphCanvas(props: EntityGraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  // Latest props mirrored in refs so the singleton event handler always sees fresh values.
  const onSelectRef = useRef(props.onSelectEntity);
  onSelectRef.current = props.onSelectEntity;

  const allClassLabels = useMemo(() => {
    if (props.classLabels && props.classLabels.length > 0) return props.classLabels;
    const labels = new Set<string>();
    props.entities.forEach((entity) => labels.add(entity.class_label));
    return Array.from(labels).sort();
  }, [props.entities, props.classLabels]);

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

    const nodes: ElementDefinition[] = visibleEntities.map((entity) => ({
      data: {
        id: entity.id,
        label: entity.name,
        classLabel: entity.class_label,
        color: pickColor(entity.class_label, allClassLabels),
      },
    }));
    const edges: ElementDefinition[] = visibleRelations.map((relation) => ({
      data: {
        id: relation.id,
        source: relation.source_entity_id,
        target: relation.target_entity_id,
        label: relation.relation_type,
      },
    }));
    return [...nodes, ...edges];
  }, [props.entities, props.relations, props.classFilter, allClassLabels]);

  useEffect(() => {
    if (!containerRef.current) return;
    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: CYTO_STYLE,
      layout: { name: "fcose", animate: false, randomize: false } as cytoscape.LayoutOptions,
      minZoom: 0.18,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    });
    cy.on("tap", "node", (event) => onSelectRef.current(String(event.target.id())));
    cy.on("tap", (event) => {
      if (event.target === cy) onSelectRef.current(null);
    });
    cyRef.current = cy;
    return () => {
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
    const shouldRandomize = cy.nodes().length > 12;
    cy.layout({
      name: "fcose",
      animate: true,
      animationDuration: 320,
      animationEasing: "ease-out",
      randomize: shouldRandomize,
      nodeSep: 60,
      idealEdgeLength: 130,
      uniformNodeDimensions: true,
    } as unknown as cytoscape.LayoutOptions).run();
    cy.fit(undefined, 50);
  }, [elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    const query = props.searchQuery.trim().toLowerCase();
    cy.nodes().removeClass("dimmed highlighted");
    cy.edges().removeClass("dimmed");
    if (!query) return;
    const matched = new Set<string>();
    cy.nodes().forEach((node) => {
      const label = String(node.data("label") || "").toLowerCase();
      const aliases: string[] = [];
      const entity = props.entities.find((item) => item.id === node.id());
      if (entity) aliases.push(...entity.aliases.map((alias) => alias.toLowerCase()));
      const hit = label.includes(query) || aliases.some((alias) => alias.includes(query));
      if (hit) {
        matched.add(node.id());
      } else {
        node.addClass("dimmed");
      }
    });
    cy.edges().forEach((edge) => {
      const connected = matched.has(edge.source().id()) || matched.has(edge.target().id());
      if (!connected) edge.addClass("dimmed");
    });
  }, [props.searchQuery, props.entities, elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().unselect();
    if (props.selectedEntityId) {
      const node = cy.getElementById(props.selectedEntityId);
      if (node && node.nonempty()) {
        node.select();
      }
    }
  }, [props.selectedEntityId, elements]);

  return <div className="entityGraphCanvas" ref={containerRef} />;
}
