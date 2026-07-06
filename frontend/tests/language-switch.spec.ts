import { expect, test, type Page } from "@playwright/test";

const project = { id: "project-1", name: "Supply Chain", description: "Operational model" };
const ontology = {
  id: "ontology-1",
  project_id: project.id,
  name: "Supply Network",
  description: "Supplier and shipment knowledge",
  status: "active",
};
const version = {
  id: "version-1",
  ontology_id: ontology.id,
  parent_version_id: null,
  version_number: 1,
  status: "draft",
  workflow_status: "gathering",
  schema_snapshot: {},
  graph_snapshot: {},
  publication_report: {},
  created_at: "2026-06-23T00:00:00Z",
  published_at: null,
};
const brief = {
  id: "brief-1",
  project_id: project.id,
  fields: {},
  field_states: {},
  field_sources: {},
  missing_fields: ["domain_name", "business_goal"],
  clarification_item: [],
  completeness: 0,
};

async function mockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    let body: unknown = [];
    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/build-context`) body = {
      project,
      project_brief: brief,
      ontologies: [{ ...ontology, current_version: version }],
      competency_question_counts: {},
    };
    // `ontologies/{id}/versions` endpoint was removed in Phase B (legacy
    // governance hard-cut). Mock kept as defensive `[]` only.
    else if (path === `/ontologies/${ontology.id}/versions`) body = [];
    else if (path === `/ontologies/${ontology.id}/proposals`) body = [];
    await route.fulfill({ json: body });
  });
}

test("language switcher toggles between Chinese and English", async ({ page }) => {
  await mockApi(page);
  // Clear any previous language choice so we use navigator default (en-US in Playwright).
  await page.addInitScript(() => window.localStorage.removeItem("ontology-platform-ui-lang"));
  await page.goto("/");

  // Default in Playwright (en-US) is English. The home header should show English strings.
  await expect(page.locator("h1").filter({ hasText: "Ontologies" })).toBeVisible();

  // Click language switcher to flip to Chinese.
  await page.getByRole("button", { name: "Switch language" }).click();
  await expect(page.locator("h1").filter({ hasText: "本体" })).toBeVisible();

  // Click again to flip back to English.
  await page.getByRole("button", { name: "切换语言" }).click();
  await expect(page.locator("h1").filter({ hasText: "Ontologies" })).toBeVisible();
});

test("language choice persists across reloads", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  // Clear storage then reload, so we start from a clean state.
  await page.evaluate(() => window.localStorage.removeItem("ontology-platform-ui-lang"));
  await page.reload();
  await page.getByRole("button", { name: "Switch language" }).click();
  await expect(page.locator("h1").filter({ hasText: "本体" })).toBeVisible();

  await page.reload();
  // Should stay in Chinese after reload.
  await expect(page.locator("h1").filter({ hasText: "本体" })).toBeVisible();
});
