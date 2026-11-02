import { expect, test } from "@playwright/test";
import type { Core } from "cytoscape";
import { envelope, mockWorkspace, resource } from "./v42-fixtures";

test("join mappings retain explicit endpoint references when predicate nodes are hidden", async ({ page }) => {
  const relation = {
    ...resource("urn:owns", "工单属于站点", "rule"),
    type_iri: "http://www.w3.org/2002/07/owl#ObjectProperty",
  };
  const mapping = {
    ...resource("urn:join", "工单站点连接", "data_mapping"),
    detail_fields: { mapped_relation: relation.iri, semantic_definition: { semantic_role: "data_mapping" } },
  };
  let nodes = [resource("urn:work", "工单", "object"), resource("urn:site", "站点", "object"), mapping, relation];
  const edges = [
    { source: mapping.iri, target: relation.iri, relation: "urn:vocab:mappedRelationType" },
    { source: relation.iri, target: "urn:work", relation: "http://www.w3.org/2000/01/rdf-schema#domain" },
    { source: relation.iri, target: "urn:site", relation: "http://www.w3.org/2000/01/rdf-schema#range" },
  ];
  await mockWorkspace(page, { ontologies: [{ id: "o1", name: "References" }], handler: async (path, route) => {
    if (path.endsWith("/resource-list")) await route.fulfill({ json: envelope(nodes) });
    else if (path.endsWith("/resource-relations")) await route.fulfill({ json: envelope(edges) });
    else return false;
    return true;
  } });
  await page.goto("/?tab=model");
  const graph = page.getByRole("img", { name: "Model graph" });
  await expect(graph).toHaveAttribute("data-node-count", "3");
  await expect(graph).toHaveAttribute("data-reference-count", "2");
  await expect(page.getByRole("button", { name: "Select node 工单属于站点", exact: true })).toHaveCount(0);
  const references = await graph.evaluate(element => {
    const cy = (element as HTMLElement & { _cyreg: { cy: Core } })._cyreg.cy;
    return cy.edges().map(edge => ({ source: edge.source().id(), target: edge.target().id(),
      via: edge.data("viaResourceIri"), path: edge.data("fieldPath"), style: edge.style("line-style") }));
  });
  expect(references).toEqual(expect.arrayContaining([
    { source: "urn:join", target: "urn:work", via: "urn:owns", path: "mapped_relation.domain", style: "dashed" },
    { source: "urn:join", target: "urn:site", via: "urn:owns", path: "mapped_relation.range", style: "dashed" },
  ]));
  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Data mapping", exact: true }).click();
  await expect(graph).toHaveAttribute("data-node-count", "1");
  await expect(graph).toHaveAttribute("data-edge-count", "0");
  await page.getByRole("button", { name: "Clear filters" }).click();
  // A missing/denied endpoint cannot become a node through a retained reference.
  nodes = nodes.filter(node => node.iri !== "urn:site");
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(graph).toHaveAttribute("data-reference-count", "1");
  await expect(page.getByRole("button", { name: "Select node 站点", exact: true })).toHaveCount(0);
  // The formal mapping reference is required; a coincidental edge is insufficient.
  nodes = nodes.map(node => node.iri === mapping.iri ? resource(mapping.iri, "工单站点连接", "data_mapping") : node);
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(graph).toHaveAttribute("data-reference-count", "0");
});
