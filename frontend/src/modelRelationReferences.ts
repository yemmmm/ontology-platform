import type { Relation, Resource } from "./workspaceTypes";

export type ModelRelation = Relation & { via_resource_iri?: string };

// Keep predicates off the canvas while preserving a join mapping's explicit
// reference path through its relation definition. These are read-only paths,
// never asserted business relationships between the displayed endpoints.
export function withMappingEndpointReferences(resources: Resource[], relations: Relation[]): ModelRelation[] {
  const byIri = new Map(resources.map(resource => [resource.iri, resource]));
  const projected: ModelRelation[] = [];
  for (const reference of relations) {
    const mapping = byIri.get(reference.source);
    const predicate = byIri.get(reference.target);
    if (mapping?.detail_fields?.mapped_relation !== reference.target
      || predicate?.type_iri !== "http://www.w3.org/2002/07/owl#ObjectProperty") continue;
    for (const endpoint of relations) {
      if (endpoint.source !== predicate.iri) continue;
      const field = endpoint.relation === "http://www.w3.org/2000/01/rdf-schema#domain" ? "domain"
        : endpoint.relation === "http://www.w3.org/2000/01/rdf-schema#range" ? "range" : null;
      if (!field || !byIri.has(endpoint.target)) continue;
      const path = `mapped_relation.${field}`;
      projected.push({ ...reference,
        id: JSON.stringify([reference.id, endpoint.id, path]), target: endpoint.target,
        label: `${predicate.label || predicate.iri} · ${path}`,
        edge_kind: "structured_reference", field_path: path, via_resource_iri: predicate.iri,
      });
    }
  }
  return [...relations, ...projected];
}
