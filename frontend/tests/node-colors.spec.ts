import { expect, test, type Page } from "@playwright/test";
import type { Core } from "cytoscape";
import { assignNodeColors } from "../src/components/nodeColors";
import { envelope, mockWorkspace, resource } from "./v42-fixtures";

async function nodeColors(page: Page) {
  return page.getByRole("img", { name: "Model graph" }).evaluate(element => {
    const cy = (element as HTMLElement & { _cyreg: { cy: Core } })._cyreg.cy;
    return Object.fromEntries(cy.nodes().map(node => [node.id(), node.style("background-color")]));
  });
}

test("nodes have distinct neighbor colors that survive search, selection, filtering and reordered refresh", async ({ page }) => {
  let nodes = [
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
  await mockWorkspace(page, { ontologies: [{ id: "o1", name: "Color test" }], handler: async (path, route) => {
    if (path.endsWith("/resource-list")) await route.fulfill({ json: envelope(nodes) });
    else if (path.endsWith("/resource-relations")) await route.fulfill({ json: envelope(edges) });
    else return false;
    return true;
  } });
  await page.goto("/?tab=model");
  const graph = page.getByRole("img", { name: "Model graph" });
  await expect(graph).toHaveAttribute("data-node-count", "5");
  await expect(graph).toHaveAttribute("data-edge-count", "3");
  const initial = await nodeColors(page);
  for (const edge of edges) expect(initial[edge.source]).not.toBe(initial[edge.target]);
  expect(new Set(Object.values(initial)).size).toBeGreaterThan(1);
  await expect(page.getByText("Colors distinguish nodes; the same color does not imply the same category.")).toBeVisible();

  await page.getByLabel("Search loaded model").fill("Hub");
  await page.getByRole("button", { name: "Hub", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Node details" })).toBeVisible();
  expect(await nodeColors(page)).toEqual(initial);
  const emphasis = await graph.evaluate(element => {
    const cy = (element as HTMLElement & { _cyreg: { cy: Core } })._cyreg.cy;
    const node = cy.getElementById("urn:hub");
    return { selected: node.selected(), underlay: parseFloat(node.style("underlay-opacity")), border: parseFloat(node.style("border-width")) };
  });
  expect(emphasis.selected).toBe(true);
  expect(emphasis.underlay).toBeGreaterThan(0);
  expect(emphasis.border).toBeGreaterThan(1);

  await page.getByLabel("Viewpoint").selectOption("object");
  await expect(graph).toHaveAttribute("data-node-count", "4");
  const { "urn:leaf2": _hidden, ...objectColors } = initial;
  expect(await nodeColors(page)).toEqual(objectColors);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(graph).toHaveAttribute("data-node-count", "5");
  expect(await nodeColors(page)).toEqual(initial);

  nodes = [...nodes].reverse(); edges = [...edges].reverse();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(graph).toHaveAttribute("data-node-count", "5");
  expect(await nodeColors(page)).toEqual(initial);
});

test("a dense graph exceeding the palette reuses colors deterministically", () => {
  const ids = Array.from({ length: 11 }, (_, i) => `urn:node:${i}`);
  const edges = ids.flatMap((source, i) => ids.slice(i + 1).map(target => ({ source, target })));
  edges.push({ source: ids[0], target: ids[0] });
  const initial = assignNodeColors(ids, edges);
  expect(initial.size).toBe(11);
  expect(new Set(initial.values()).size).toBe(10);
  expect(assignNodeColors([...ids].reverse(), [...edges].reverse())).toEqual(initial);
  expect(assignNodeColors([], [])).toEqual(new Map());
});
