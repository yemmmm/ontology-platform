import { expect, test, type Page } from "@playwright/test";
import type { Core } from "cytoscape";
import { assignNodeColors, UNCLASSIFIED_COLORS, VIEWPOINT_COLORS } from "../src/components/nodeColors";
import { semanticViews } from "../src/workspaceTypes";
import { envelope, mockWorkspace, resource } from "./v42-fixtures";

async function nodeColors(page: Page) {
  return page.getByRole("img", { name: "Model graph" }).evaluate(element => {
    const cy = (element as HTMLElement & { _cyreg: { cy: Core } })._cyreg.cy;
    return Object.fromEntries(cy.nodes().map(node => [node.id(), node.style("background-color")]));
  });
}

test("viewpoint color families and identity shades survive search, selection, filtering and reordered refresh", async ({ page }) => {
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
  const rgb = (hex: string) => `rgb(${[1, 3, 5].map(start => parseInt(hex.slice(start, start + 2), 16)).join(",")})`;
  const objectPalette = VIEWPOINT_COLORS.object.map(rgb);
  for (const id of ["urn:hub", "urn:leaf1", "urn:leaf3", "urn:isolated"]) expect(objectPalette).toContain(initial[id]);
  expect(VIEWPOINT_COLORS.process.map(rgb)).toContain(initial["urn:leaf2"]);
  expect(new Set(Object.values(initial)).size).toBeGreaterThan(1);
  const legend = page.getByRole("list", { name: "Node color legend" });
  for (const [role, name] of semanticViews) {
    await expect(legend.locator(`[data-viewpoint="${role}"]`)).toHaveText(name);
    expect(await legend.locator(`[data-viewpoint="${role}"] i`).evaluateAll(elements => elements.map(element => (element as HTMLElement).style.backgroundColor.replaceAll(" ", "")))).toEqual(VIEWPOINT_COLORS[role].map(rgb));
  }
  await expect(page.getByText("Color families indicate viewpoints; shade differences distinguish nodes, not importance.")).toBeVisible();

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

test("every explicit viewpoint has its own family and unknown or multiple declarations use neutral colors", () => {
  const nodes = semanticViews.flatMap(([role]) => Array.from({ length: 30 }, (_, i) => ({ id: `urn:${role}:${i}`, roles: [role] })));
  const assigned = assignNodeColors(nodes);
  for (const [role] of semanticViews) {
    const colors = new Set(nodes.filter(node => node.roles[0] === role).map(node => assigned.get(node.id)));
    expect(colors.size).toBe(3);
    for (const color of colors) expect(VIEWPOINT_COLORS[role]).toContain(color);
  }
  const declaredPalette = Object.values(VIEWPOINT_COLORS).flat();
  expect(new Set(declaredPalette).size).toBe(declaredPalette.length);
  expect(assignNodeColors([...nodes].reverse())).toEqual(assigned);
  const cases = [
    { id: "urn:empty", roles: [] },
    { id: "urn:unknown", roles: ["custom"] },
    { id: "urn:invalid", roles: [null, {}] },
    { id: "urn:multiple", roles: ["object", "process"] },
    { id: "urn:partially-known", roles: ["object", "custom"] },
    { id: "urn:prototype", roles: ["__proto__"] },
  ];
  for (const color of assignNodeColors(cases).values()) expect(UNCLASSIFIED_COLORS).toContain(color);
  expect(assignNodeColors([{ id: "urn:work", roles: ["object", "object", null] }]).get("urn:work"))
    .toBe(assignNodeColors([{ id: "urn:work", roles: ["object"] }]).get("urn:work"));
  expect(assignNodeColors([])).toEqual(new Map());
});

test("a shared resource with multiple viewpoint declarations keeps its neutral identity across filters", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/?tab=model");
  const graph = page.getByRole("img", { name: "Model graph" });
  await expect(graph).toHaveAttribute("data-node-count", "11");
  const initial = await nodeColors(page);
  expect(initial["urn:work"]).not.toBe(initial["urn:process"]);
  await expect(page.getByRole("list", { name: "Node color legend" }).getByText("Unclassified / multiple viewpoints")).toBeVisible();
  await page.getByLabel("Viewpoint").selectOption("object");
  await expect(graph).toHaveAttribute("data-node-count", "1");
  expect((await nodeColors(page))["urn:work"]).toBe(initial["urn:work"]);
  await page.getByLabel("Viewpoint").selectOption("process");
  await expect(graph).toHaveAttribute("data-node-count", "2");
  expect((await nodeColors(page))["urn:work"]).toBe(initial["urn:work"]);
});
