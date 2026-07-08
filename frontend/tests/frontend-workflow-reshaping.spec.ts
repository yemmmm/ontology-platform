import { expect, test, type Page } from "@playwright/test";

const project = { id: "project-phase8", name: "Phase 8 Project", description: "workflow reshape" };
const ontology = {
  id: "ontology-phase8",
  project_id: project.id,
  name: "Phase 8 Ontology",
  description: "business modeling",
  status: "active",
};

const GRAPH_SET_ID = "gs-phase8";
const graphSet = {
  id: GRAPH_SET_ID,
  name: "Internal workspace",
  scope_type: "ontology",
  scope_id: ontology.id,
  status: "active",
  source_signature: "sig-phase8",
  created_by: "test",
  members: [],
  current_pointers: [],
  metadata: {},
};

const classTopologyEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      iri: "http://op.local/class/Supplier",
      label: "Supplier",
      source_graph_iri: "http://op.local/internal/ontology",
      assertion_kind: "asserted",
    },
  ],
};

const relationTypeEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [],
};

const entityListEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      iri: "http://op.local/entity/acme",
      label: "Acme Corp",
      source_graph_iri: "http://op.local/internal/data",
      assertion_kind: "asserted",
      class_iri: "http://op.local/class/Supplier",
      class_label: "Supplier",
    },
  ],
};

const entityRelationsEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      iri: "relationship-1",
      label: "supplies",
      assertion_kind: "asserted",
      source: "http://op.local/entity/acme",
      target: "http://op.local/entity/acme",
    },
  ],
};

async function mockApi(page: Page) {
  await page.addInitScript(() => {
    window.localStorage.setItem("ontology-platform-ui-lang", "en");
    window.localStorage.removeItem("ontology-platform-ui-workspace-lock:ontology-phase8");
  });

  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const readModelPath = (modelName: string) =>
      `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/${modelName}`;
    let body: unknown = [];

    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/brief`) body = {
      id: "brief-1",
      project_id: project.id,
      fields: { domain_name: "" },
      field_states: { domain_name: "missing" },
      field_sources: {},
      missing_fields: ["domain_name"],
      clarification_items: [
        {
          field: "domain_name",
          question: "What is the domain name?",
          reason: "missing",
        },
      ],
      completeness: 0.9,
    };
    else if (path === "/semantic/graph-sets") body = { graph_sets: [graphSet] };
    else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}`) body = graphSet;
    else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/missing-evidence`) body = {
      graph_set_id: GRAPH_SET_ID,
      dependencies: [],
      summary: {},
      warning: null,
    };
    else if (path === "/semantic/rule-definitions") body = { rules: [] };
    // Match by pathname so read-model query strings such as ?include=asserted
    // do not bypass the route mock.
    else if (path === readModelPath("class-topology")) body = classTopologyEnvelope;
    else if (path === readModelPath("relation-type-list")) body = relationTypeEnvelope;
    else if (path === readModelPath("entity-list")) body = entityListEnvelope;
    else if (path === readModelPath("entity-relations")) body = entityRelationsEnvelope;
    else if (path === readModelPath("fact-audit-queue")) body = {
      graph_set_id: GRAPH_SET_ID,
      source_signature: "sig",
      projection_version: "1",
      model_name: "fact-audit-queue",
      include: "asserted",
      derived_state: {},
      warnings: [],
      items: [],
    };
    else if (path === "/semantic/status") body = {
      graphs: { total: 2 },
      derived: { missing_evidence_count: 0, stale_derived_count: 0 },
    };
    else if (path === "/semantic/projections/status") body = {
      manifests: [],
      stale: [],
      missing: [],
      stale_projection_count: 0,
    };
    else if (path === "/semantic/validation-runs") body = {
      items: [],
      summary: { total: 0, stale_count: 0, superseded_count: 0 },
    };
    else if (path === "/semantic/reasoning-runs") body = {
      items: [],
      summary: { total: 0, stale_count: 0, superseded_count: 0 },
    };
    else if (path === "/semantic/rule-runs") body = {
      items: [],
      summary: { total: 0, stale_count: 0, superseded_count: 0 },
    };
    else if (path === "/health/dependencies") body = { postgres: { status: "ok" } };

    await route.fulfill({ json: body });
  });
}

function workspaceUrl(tab: string) {
  return `/?project=${project.id}&ontology=${ontology.id}&tab=${tab}`;
}

test("modeling classes opens without a graphSet URL parameter", async ({ page }) => {
  await mockApi(page);
  await page.goto(workspaceUrl("classes"));

  await expect(page).not.toHaveURL(/graphSet=/);
  await expect(page.locator("section.classesPage.stage2").getByRole("heading", { name: "Classes" })).toBeVisible();
  await expect(page.getByText(/Class force graph · 1 nodes · 0 edges/)).toBeVisible();
  await expect(page.getByTestId("force-graph-canvas")).toBeVisible();
  await expect(page.locator("section.classesPage.stage2 .classList")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "New class" })).toBeEnabled();
});

test("settings lock disables modeling mutation controls", async ({ page }) => {
  await mockApi(page);
  await page.goto(workspaceUrl("setting"));

  await page.getByRole("button", { name: "Lock workspace" }).click();
  await expect(page.getByText("Workspace locked")).toBeVisible();

  await page.getByRole("button", { name: "Modeling" }).click();
  await expect(page.getByRole("button", { name: "New class" })).toBeDisabled();
  await expect(page.getByText("Workspace is locked. Unlock in Settings to edit modeling data.")).toBeVisible();
});

test("main navigation separates overview questions and debug tools", async ({ page }) => {
  await mockApi(page);
  await page.goto(workspaceUrl("classes"));

  const nav = page.locator(".mainNav");
  await expect(nav.getByRole("button", { name: /^Overview/ }).first()).toBeVisible();
  await expect(nav.getByRole("button", { name: "Structured Requirements", exact: true })).toBeVisible();
  await expect(nav.getByRole("button", { name: /^Modeling/ }).first()).toBeVisible();
  await expect(nav.getByRole("button", { name: /^Debug/ }).first()).toBeVisible();
  await expect(nav.getByRole("button", { name: "Agent Test", exact: true })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Recall", exact: true })).toBeVisible();
  await expect(nav.getByRole("button", { name: "MCP Tools", exact: true })).toBeVisible();
  await expect(nav.getByRole("button", { name: "Graph Sets", exact: true })).toBeVisible();
  await expect(nav.getByRole("button", { name: /^Settings/ }).first()).toBeVisible();
  await expect(nav).not.toContainText(/Named Graph|Named Graphs|RDF/i);
});

test("overview only summarizes structured requirement completion", async ({ page }) => {
  await mockApi(page);
  await page.goto(workspaceUrl("brief"));

  await expect(page.locator("section[aria-label='overview-diagnostics']")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Structured Requirements" })).toBeVisible();
  await expect(page.getByText("Open questions")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open Structured Requirements" })).toBeVisible();
  await expect(page.getByText("What is the domain name?")).toHaveCount(0);
});

test("questions deep link opens standalone requirement questions tab", async ({ page }) => {
  await mockApi(page);
  await page.goto(workspaceUrl("questions"));

  await expect(page).toHaveURL(/tab=questions/);
  const questionsPage = page.locator("section[aria-label='requirement-questions-page']");
  await expect(questionsPage).toBeVisible();
  await expect(questionsPage.getByRole("heading", { name: "Structured Requirements" })).toBeVisible();
  await expect(questionsPage.getByText("Open questions", { exact: true })).toBeVisible();
  await expect(questionsPage.getByText("Requirement clarification", { exact: true })).toBeVisible();
  await expect(questionsPage.getByRole("heading", { name: "Project Brief" })).toBeVisible();
  await expect(questionsPage.getByText("结构化需求")).toBeVisible();
  await expect(questionsPage.locator("textarea").first()).toBeEnabled();
});

test("graph-set deep link opens the debug graph sets tool", async ({ page }) => {
  await mockApi(page);
  await page.goto(workspaceUrl("graph-sets"));

  await expect(page).toHaveURL(/tab=graph-sets/);
  await expect(page.locator("section[aria-label='graph-set-page']")).toBeVisible();
  await expect(page.locator(".mainNav")).toContainText("Graph Sets");
});
