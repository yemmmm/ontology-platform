import { expect, test, type Page } from "@playwright/test";
import type { Core } from "cytoscape";
import { envelope, mockWorkspace, resource } from "./v42-fixtures";

async function nodeSizes(page: Page) {
  return page.getByRole("img", { name: "Model graph" }).evaluate(element => {
    const cy = (element as HTMLElement & { _cyreg: { cy: Core } })._cyreg.cy;
    return Object.fromEntries(cy.nodes().map(node => [node.id(), {
      width: node.width(), height: node.height(), degree: node.degree(),
    }]));
  });
}

test("node sizes reflect visible incoming and outgoing edges and refresh after filtering", async ({ page }) => {
  const nodes = [
    resource("urn:hub", "Hub", "object"),
    resource("urn:leaf1", "Leaf 1", "object"),
    resource("urn:leaf2", "Leaf 2", "process"),
    resource("urn:leaf3", "Leaf 3", "object"),
    resource("urn:isolated", "Isolated", "object"),
  ];
  let edges = [
    { source: "urn:hub", target: "urn:leaf1", relation: "urn:links" },
    { source: "urn:leaf2", target: "urn:hub", relation: "urn:references", edge_kind: "structured_reference", field_path: "definition_ref" },
    { source: "urn:hub", target: "urn:leaf3", relation: "urn:links" },
  ];
  await mockWorkspace(page, { ontologies: [{ id: "o1", name: "Size test" }], handler: async (path, route) => {
    if (path.endsWith("/resource-list")) await route.fulfill({ json: envelope(nodes) });
    else if (path.endsWith("/resource-relations")) await route.fulfill({ json: envelope(edges) });
    else return false;
    return true;
  } });
  await page.goto("/?tab=model");
  const graph = page.getByRole("img", { name: "Model graph" });
  await expect(graph).toHaveAttribute("data-edge-count", "3");
  await expect(graph).toHaveAttribute("data-reference-count", "1");
  const initial = await nodeSizes(page);
  expect(initial["urn:hub"].degree).toBe(3);
  expect(initial["urn:hub"].width).toBeGreaterThan(initial["urn:leaf1"].width);
  expect(initial["urn:leaf1"].width).toBeGreaterThan(initial["urn:isolated"].width);
  expect(initial["urn:leaf1"].width).toBe(initial["urn:leaf2"].width);
  for (const node of Object.values(initial)) {
    expect(node.width).toBeGreaterThanOrEqual(25);
    expect(node.width).toBeLessThanOrEqual(58);
    expect(node.height).toBe(node.width);
  }
  await page.getByLabel("Search loaded model").fill("Hub");
  expect(await nodeSizes(page)).toEqual(initial);
  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Object", exact: true }).click();
  await expect(graph).toHaveAttribute("data-edge-count", "2");
  const filtered = await nodeSizes(page);
  expect(filtered["urn:leaf2"]).toBeUndefined();
  expect(filtered["urn:hub"].degree).toBe(2);
  expect(filtered["urn:hub"].width).toBeLessThan(initial["urn:hub"].width);
  expect(filtered["urn:hub"].width).toBeGreaterThan(filtered["urn:leaf1"].width);
  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Process", exact: true }).click();
  await expect(graph).toHaveAttribute("data-edge-count", "3");
  expect(await nodeSizes(page)).toEqual(initial);
  edges = [];
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(graph).toHaveAttribute("data-edge-count", "0");
  for (const node of Object.values(await nodeSizes(page))) {
    expect(node).toEqual({ degree: 0, width: 25, height: 25 });
  }
});
