import { expect, test, type Page } from "@playwright/test";
import type { Core } from "cytoscape";
import { envelope, mockWorkspace, resource } from "./v42-fixtures";

async function graphState(page: Page) {
  return page.getByRole("img", { name: "Model graph" }).evaluate(element => {
    const cy = (element as HTMLElement & { _cyreg: { cy: Core } })._cyreg.cy;
    return {
      selected: cy.nodes(":selected").map(node => node.id()).sort(),
      highlighted: cy.nodes(".highlighted").map(node => node.id()).sort(),
      dimmed: cy.nodes(".dimmed").map(node => node.id()).sort(),
      edges: cy.edges().map(edge => ({
        source: edge.source().id(), target: edge.target().id(),
        highlighted: edge.hasClass("highlighted"), opacity: Number(edge.style("opacity")),
        width: parseFloat(edge.style("width")), lineStyle: edge.style("line-style"),
      })),
      colors: Object.fromEntries(cy.nodes().map(node => [node.id(), node.style("background-color")])),
    };
  });
}

async function clickNode(page: Page, id: string) {
  const graph = page.getByRole("img", { name: "Model graph" });
  await graph.scrollIntoViewIfNeeded();
  const point = await graph.evaluate((element, nodeId) => {
    const cy = (element as HTMLElement & { _cyreg: { cy: Core } })._cyreg.cy;
    cy.resize();
    cy.center(cy.getElementById(nodeId));
    const position = cy.getElementById(nodeId).renderedPosition();
    return { x: position.x, y: position.y };
  }, id);
  await graph.click({ position: point });
  await expect.poll(async () => (await graphState(page)).selected).toEqual([id]);
}

async function selectWithKeyboard(page: Page, label: string) {
  const button = page.getByRole("button", { name: `Select node ${label}`, exact: true });
  await button.focus();
  await button.press("Enter");
}

test("selection focuses one-hop neighbors and incident edges, then restores search or default styles", async ({ page }) => {
  const nodes = [
    resource("urn:hub", "Hub", "object"),
    resource("urn:incoming", "Incoming", "process"),
    resource("urn:outgoing", "Outgoing", "object"),
    resource("urn:second", "Second hop", "process"),
    resource("urn:isolated", "Isolated", "object"),
  ];
  let edges = [
    { source: "urn:hub", target: "urn:outgoing", relation: "urn:links" },
    { source: "urn:incoming", target: "urn:hub", relation: "urn:reference", edge_kind: "structured_reference", field_path: "definition_ref" },
    { source: "urn:outgoing", target: "urn:second", relation: "urn:links" },
    { source: "urn:incoming", target: "urn:outgoing", relation: "urn:links" },
    { source: "urn:hub", target: "urn:hub", relation: "urn:self" },
    { source: "urn:hub", target: "urn:outgoing", relation: "urn:other" },
  ];
  await mockWorkspace(page, { ontologies: [{ id: "o1", name: "Selection test" }], handler: async (path, route) => {
    if (path.endsWith("/resource-list")) await route.fulfill({ json: envelope(nodes) });
    else if (path.endsWith("/resource-relations")) await route.fulfill({ json: envelope(edges) });
    else return false;
    return true;
  } });
  await page.goto("/?tab=model");
  const graph = page.getByRole("img", { name: "Model graph" });
  await expect(graph).toHaveAttribute("data-edge-count", "6");
  const initial = await graphState(page);
  await clickNode(page, "urn:hub");
  const selected = await graphState(page);
  expect(selected.highlighted).toEqual(["urn:hub", "urn:incoming", "urn:outgoing"]);
  expect(selected.dimmed).toEqual(["urn:isolated", "urn:second"]);
  for (const edge of selected.edges) {
    const incident = edge.source === "urn:hub" || edge.target === "urn:hub";
    expect(edge.highlighted).toBe(incident);
    expect(edge.opacity).toBe(incident ? 1 : 0.22);
    expect(edge.width).toBe(incident ? 3 : 1.5);
  }
  expect(selected.edges.find(edge => edge.source === "urn:incoming" && edge.target === "urn:hub")!.lineStyle).toBe("dashed");
  for (const id of selected.highlighted) expect(selected.colors[id]).toBe(initial.colors[id]);
  for (const id of selected.dimmed) expect(selected.colors[id]).toBe("rgb(196,198,205)");
  await page.screenshot({ path: test.info().outputPath("selected-neighborhood.png"), fullPage: true });

  // Switching selection clears the old neighborhood, including second-hop exclusions.
  await selectWithKeyboard(page, "Outgoing");
  expect((await graphState(page)).highlighted).toEqual(["urn:hub", "urn:incoming", "urn:outgoing", "urn:second"]);
  await page.getByRole("button", { name: "Close node details" }).click();
  expect(await graphState(page)).toEqual(initial);

  await page.getByLabel("Search loaded model").fill("Hub");
  await expect.poll(async () => (await graphState(page)).highlighted).toEqual(["urn:hub"]);
  const searched = await graphState(page);
  await page.getByRole("button", { name: "Hub", exact: true }).click();
  expect((await graphState(page)).highlighted).toEqual(selected.highlighted);
  await page.getByRole("button", { name: "Close node details" }).click();
  expect(await graphState(page)).toEqual(searched);
  await page.getByRole("button", { name: "Clear filters" }).click();

  await selectWithKeyboard(page, "Isolated");
  expect((await graphState(page)).highlighted).toEqual(["urn:isolated"]);
  expect((await graphState(page)).edges.every(edge => !edge.highlighted && edge.opacity === 0.22)).toBe(true);
  await graph.click({ position: { x: 10, y: 10 } });
  await expect.poll(async () => graphState(page)).toEqual(initial);

  await selectWithKeyboard(page, "Hub");
  edges = [];
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(graph).toHaveAttribute("data-edge-count", "0");
  await expect(graph).toHaveAttribute("data-node-count", "5");
  expect((await graphState(page)).selected).toEqual([]);
  expect((await graphState(page)).dimmed).toEqual([]);
  await selectWithKeyboard(page, "Hub");
  expect((await graphState(page)).highlighted).toEqual(["urn:hub"]);
  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Process", exact: true }).click();
  await expect(graph).toHaveAttribute("data-node-count", "2");
  expect((await graphState(page)).selected).toEqual([]);
  expect((await graphState(page)).dimmed).toEqual([]);
});
