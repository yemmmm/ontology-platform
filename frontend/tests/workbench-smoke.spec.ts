import { expect, test, type Page } from "@playwright/test";

const project = { id: "project-1", name: "Supply Chain", description: "Operational model" };
const ontology = {
  id: "ontology-1",
  project_id: project.id,
  current_version_id: "version-1",
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
  clarification_items: [],
  completeness: 0,
};
const schemaProposal = {
  id: "proposal-1",
  ontology_id: ontology.id,
  target_version_id: version.id,
  proposal_type: "schema_change",
  status: "validated",
  source_type: "agent",
  payload: { items: [{ key: "supplier", kind: "class", data: { name: "Supplier" }, review_status: "pending" }] },
  validation_result: {},
  application_result: {},
  evidence: [],
  created_at: "2026-06-23T00:00:00Z",
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
    else if (path === `/projects/${project.id}/brief`) body = brief;
    else if (path.startsWith(`/projects/${project.id}/competency-questions`)) body = [];
    else if (path === `/projects/${project.id}/data-sources`) body = [];
    else if (path === `/projects/${project.id}/data-resources`) body = [];
    else if (path === `/projects/${project.id}/external-fields`) body = [];
    else if (path.startsWith(`/projects/${project.id}/semantic-mappings`)) body = [];
    else if (path === `/projects/${project.id}/connector-templates`) body = [];
    else if (path === `/ontologies/${ontology.id}/versions`) body = [version];
    else if (path === `/ontologies/${ontology.id}/proposals`) body = [schemaProposal];
    else if (path === "/review-batches/batch-1") body = {
      id: "batch-1",
      stable_key: `proposal:${schemaProposal.id}`,
      project_id: project.id,
      ontology_id: ontology.id,
      ontology_version_id: version.id,
      review_type: "schema",
      status: "pending",
      item_ids: ["supplier"],
      counts: { pending: 1 },
      deep_link: "",
      created_at: "2026-06-23T00:00:00Z",
      updated_at: "2026-06-23T00:00:00Z",
    };
    else if (path === `/versions/${version.id}/publication-readiness`) body = {
      version_id: version.id,
      ready: false,
      gates: [{ gate_type: "schema_validation", status: "failed", details: { errors: ["sample"] } }],
      blocking: ["schema_validation"],
      warnings: [],
    };
    else if (path === "/health/dependencies") body = { postgres: { status: "ok" }, neo4j: { status: "ok" } };
    await route.fulfill({ json: body });
  });
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 768, height: 900 }]) {
  test(`workbench navigation at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByText("Supply Network", { exact: true })).toBeVisible();
    await page.getByText("Supply Network", { exact: true }).click();
    await expect(page.getByRole("heading", { name: "构建概览" })).toBeVisible();

    for (const [nav, heading] of [
      ["Brief", "Project Brief"],
      ["Questions", "Competency Questions"],
      ["Facts", "Fact Audit"],
      ["Publication", "Publication"],
      ["Versions", "Versions"],
      ["Catalog", "Data Catalog"],
      ["Evidence", "Evidence Explorer"],
    ] as const) {
      await page.locator(".navStageButton").filter({ hasText: nav }).first().click();
      await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
      if (nav === "Publication") await expect(page.getByRole("button", { name: /publish/i }).last()).toBeDisabled();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${nav} should not overflow the ${viewport.width}px viewport`).toBeLessThanOrEqual(1);
    }

    await expect(page.locator(".workflowProgressItem.current")).toBeVisible();
  });
}

test("schema review batch deep link restores exact context", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=schema-review&batch=batch-1`);
  await expect(page.getByText("Review batch · schema")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Supplier" })).toBeVisible();
  await expect(page).toHaveURL(/batch=batch-1/);
});

test("catalog wizard renders step indicator and Test toggle", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=catalog`);
  await expect(page.getByRole("heading", { name: "Data Catalog" })).toBeVisible();
  await expect(page.getByText("数据源 · Step 1 / 5")).toBeVisible();
  await expect(page.getByRole("button", { name: "创建并继续" })).toBeVisible();
  await page.getByRole("tab", { name: /Test/ }).click();
  await expect(page.getByText("Governed connector query").first()).toBeVisible();
  await expect(page.getByText("Identifier resolution analysis").first()).toBeVisible();
});

test("schema review auto-validates proposed batch and exposes approve-and-apply", async ({ page }) => {
  const proposedProposal = { ...schemaProposal, id: "proposal-proposed", status: "proposed" };
  const state: { proposal: typeof schemaProposal } = { proposal: proposedProposal };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    const method = route.request().method();
    let body: unknown = [];
    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/build-context`) body = {
      project,
      project_brief: brief,
      ontologies: [{ ...ontology, current_version: version }],
      competency_question_counts: {},
    };
    else if (path === `/ontologies/${ontology.id}/proposals`) body = [state.proposal];
    else if (method === "POST" && path === `/proposals/${state.proposal.id}/validate`) {
      state.proposal = { ...state.proposal, status: "validated" };
      body = state.proposal;
    }
    else if (path === `/ontologies/${ontology.id}/versions`) body = [version];
    else if (path === "/health/dependencies") body = { postgres: { status: "ok" }, neo4j: { status: "ok" } };
    await route.fulfill({ json: body });
  });

  const validateRequest = page.waitForRequest(
    (request) => request.url().includes(`/proposals/${proposedProposal.id}/validate`) && request.method() === "POST",
  );

  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=schema-review`);
  await validateRequest;
  await expect(page.getByRole("button", { name: /Approve proposal.*& apply/ })).toBeVisible();
});
