import { expect, test, type Page } from "@playwright/test";

const project = { id: "project-test", name: "Agent Platform", description: "Business semantics" };
const ontology = {
  id: "ontology-test",
  project_id: project.id,
  name: "Agent Operations",
  description: "Operation semantics",
  status: "active",
};

async function mockApi(page: Page, storedTab = "brief") {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) requests.push(new URL(request.url()).pathname);
  });
  await page.addInitScript((tab) => {
    localStorage.setItem("ontology-platform-ui-lang", "en");
    localStorage.setItem("ontology-platform-ui-workspace-tab-v4", tab);
  }, storedTab);
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    let body: unknown = [];
    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/brief`) body = {
      project_id: project.id, fields: { business_goal: "Describe operation semantics" },
      field_states: {}, field_sources: {}, missing_fields: [], clarification_items: [], completeness: 1,
    };
    else if (path === "/semantic/graph-sets") body = { graph_sets: [] };
    await route.fulfill({ json: body });
  });
  return requests;
}

for (const stored of [false, true]) {
  test(`retired evidence ${stored ? "stored tab" : "URL"} returns to overview without requests`, async ({ page }) => {
    const requests = await mockApi(page, stored ? "evidence" : "brief");
    await page.goto(`/?project=${project.id}&ontology=${ontology.id}${stored ? "" : "&tab=evidence"}`);
    await expect(page.getByRole("heading", { name: "Overview", exact: true, level: 1 })).toBeVisible();
    await expect(page.locator("section[aria-label='evidence-references-page']")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Evidence/ })).toHaveCount(0);
    expect(requests.some((path) => /evidence|lineage|provenance/.test(path))).toBe(false);
  });
}
