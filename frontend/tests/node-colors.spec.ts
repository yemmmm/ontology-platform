import { expect, test, type Page } from "@playwright/test";
import type { Core } from "cytoscape";
import { assignNodeColorFamilies, VIEWPOINT_COLORS } from "../src/components/nodeColors";
import { semanticViews } from "../src/workspaceTypes";
import { envelope, mockWorkspace, resource } from "./v42-fixtures";

async function nodeColors(page: Page) {
  return page.getByRole("img", { name: "Model graph" }).evaluate(element => {
    const cy = (element as HTMLElement & { _cyreg: { cy: Core } })._cyreg.cy;
    return Object.fromEntries(cy.nodes().map(node => [node.id(), node.style("background-color")]));
  });
}

// Read rendered RGB, so assertions also cover Cytoscape's HSL conversion.
function channels(color: string) {
  const [r, g, b] = color.match(/[\d.]+/g)!.map(value => Number(value) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const delta = max - min, lightness = (max + min) / 2;
  const saturation = delta === 0 ? 0 : delta / (1 - Math.abs(2 * lightness - 1));
  const hue = delta === 0 ? 0 : 60 * (max === r ? ((g - b) / delta + 6) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4);
  return { hue, saturation: saturation * 100, lightness: lightness * 100 };
}

test("visible degree controls saturation while viewpoint, search emphasis and refresh remain correct", async ({ page }) => {
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
  const saturation = (id: string, colors = initial) => channels(colors[id]).saturation;
  expect(saturation("urn:hub")).toBeGreaterThan(saturation("urn:leaf1"));
  expect(saturation("urn:leaf1")).toBeGreaterThan(saturation("urn:isolated"));
  expect(initial["urn:leaf1"]).toBe(initial["urn:leaf3"]);
  expect(channels(initial["urn:leaf2"]).hue).toBeCloseTo(263, 0);
  for (const id of ["urn:hub", "urn:leaf1", "urn:leaf3", "urn:isolated"]) {
    const color = channels(initial[id]);
    expect(color.hue).toBeCloseTo(212, 0);
    expect(color.saturation).toBeGreaterThanOrEqual(34);
    expect(color.saturation).toBeLessThanOrEqual(76);
    expect(color.lightness).toBeCloseTo(55, 0);
  }
  const legend = page.getByRole("list", { name: "Node color legend" });
  for (const [role, name] of semanticViews) {
    await expect(legend.locator(`[data-viewpoint="${role}"]`)).toHaveText(name);
    const swatches = await legend.locator(`[data-viewpoint="${role}"] i`).evaluateAll(elements => elements.map(element => getComputedStyle(element).backgroundColor));
    expect(swatches).toHaveLength(3);
    expect(channels(swatches[0]).saturation).toBeLessThan(channels(swatches[1]).saturation);
    expect(channels(swatches[1]).saturation).toBeLessThan(channels(swatches[2]).saturation);
  }
  await expect(page.getByText("Color families indicate viewpoints. Larger, more vivid nodes have more visible connections; gray nodes become darker. This does not indicate business importance or model quality.")).toBeVisible();

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

  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Object", exact: true }).click();
  await expect(graph).toHaveAttribute("data-node-count", "4");
  const filtered = await nodeColors(page);
  expect(filtered["urn:leaf2"]).toBeUndefined();
  expect(saturation("urn:hub", filtered)).toBeLessThan(saturation("urn:hub"));
  expect(saturation("urn:hub", filtered)).toBeGreaterThan(saturation("urn:leaf1", filtered));
  expect(channels(filtered["urn:hub"]).hue).toBeCloseTo(212, 0);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(graph).toHaveAttribute("data-node-count", "5");
  expect(await nodeColors(page)).toEqual(initial);

  nodes = [...nodes].reverse(); edges = [...edges].reverse();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(graph).toHaveAttribute("data-node-count", "5");
  expect(await nodeColors(page)).toEqual(initial);

  edges = [];
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(graph).toHaveAttribute("data-edge-count", "0");
  const equal = await nodeColors(page);
  expect(new Set([equal["urn:hub"], equal["urn:leaf1"], equal["urn:leaf3"], equal["urn:isolated"]]).size).toBe(1);
  expect(channels(equal["urn:hub"]).saturation).toBeCloseTo(35, 0);
});

test("every explicit viewpoint has its own family and unknown or multiple declarations use neutral colors", () => {
  const nodes = semanticViews.flatMap(([role]) => Array.from({ length: 30 }, (_, i) => ({ id: `urn:${role}:${i}`, roles: [role] })));
  const assigned = assignNodeColorFamilies(nodes);
  for (const [role] of semanticViews) {
    const colors = new Set(nodes.filter(node => node.roles[0] === role).map(node => assigned.get(node.id)));
    expect([...colors]).toEqual([role]);
  }
  expect(new Set(Object.values(VIEWPOINT_COLORS).flat()).size).toBe(21);
  expect(assignNodeColorFamilies([...nodes].reverse())).toEqual(assigned);
  const cases = [
    { id: "urn:empty", roles: [] },
    { id: "urn:unknown", roles: ["custom"] },
    { id: "urn:invalid", roles: [null, {}] },
    { id: "urn:multiple", roles: ["object", "process"] },
    { id: "urn:partially-known", roles: ["object", "custom"] },
    { id: "urn:prototype", roles: ["__proto__"] },
  ];
  for (const family of assignNodeColorFamilies(cases).values()) expect(family).toBe("unclassified");
  expect(assignNodeColorFamilies([{ id: "urn:work", roles: ["object", "object", null] }]).get("urn:work"))
    .toBe(assignNodeColorFamilies([{ id: "urn:work", roles: ["object"] }]).get("urn:work"));
  expect(assignNodeColorFamilies([])).toEqual(new Map());
});

test("a shared resource with multiple viewpoint declarations keeps its neutral identity across filters", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/?tab=model");
  const graph = page.getByRole("img", { name: "Model graph" });
  await expect(graph).toHaveAttribute("data-node-count", "11");
  const initial = await nodeColors(page);
  expect(initial["urn:work"]).not.toBe(initial["urn:process"]);
  await expect(page.getByRole("list", { name: "Node color legend" }).getByText("Unclassified / multiple viewpoints")).toBeVisible();
  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Object", exact: true }).click();
  await expect(graph).toHaveAttribute("data-node-count", "1");
  const filtered = (await nodeColors(page))["urn:work"];
  expect(channels(filtered).saturation).toBe(0);
  expect(channels(filtered).lightness).toBeGreaterThan(channels(initial["urn:work"]).lightness);
  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Process", exact: true }).click();
  await expect(graph).toHaveAttribute("data-node-count", "2");
  expect(channels((await nodeColors(page))["urn:work"]).saturation).toBe(0);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(graph).toHaveAttribute("data-node-count", "11");
  expect(await nodeColors(page)).toEqual(initial);
});
