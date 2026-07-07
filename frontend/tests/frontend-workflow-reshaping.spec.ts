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
    let body: unknown = [];

    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/brief`) body = {
      id: "brief-1",
      project_id: project.id,
      fields: {},
      field_states: {},
      field_sources: {},
      missing_fields: [],
      clarification_items: [],
      completeness: 1,
    };
    else if (path === "/semantic/graph-sets") body = {
      graph_sets: [{ id: GRAPH_SET_ID, name: "Internal workspace", status: "active", members: [] }],
    };
    else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/class-topology`) body = classTopologyEnvelope;
    else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-list`) body = entityListEnvelope;
    else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-relations`) body = entityRelationsEnvelope;
    else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/fact-audit-queue`) body = {
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
    else if (path === "/health/dependencies") body = { postgres: { status: "ok" }, neo4j: { status: "ok" } };

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
  await expect(page.getByText("Supplier")).toBeVisible();
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

test("main navigation hides graph set, named graph, and RDF entry points", async ({ page }) => {
  await mockApi(page);
  await page.goto(workspaceUrl("classes"));

  const nav = page.locator(".mainNav");
  await expect(nav.getByRole("button", { name: /^Overview/ }).first()).toBeVisible();
  await expect(nav.getByRole("button", { name: /^Modeling/ }).first()).toBeVisible();
  await expect(nav.getByRole("button", { name: /^Debug/ }).first()).toBeVisible();
  await expect(nav.getByRole("button", { name: /^Settings/ }).first()).toBeVisible();
  await expect(nav).not.toContainText(/Graph Set|Graph Sets|Named Graph|Named Graphs|RDF/i);
});

test("legacy graph-set deep link is normalized to diagnostics", async ({ page }) => {
  await mockApi(page);
  await page.goto(workspaceUrl("graph-sets"));

  await expect(page).toHaveURL(/tab=graph-governance/);
  await expect(page.locator("section[aria-label='debug-page']")).toBeVisible();
  await expect(page.locator(".mainNav")).not.toContainText(/Graph Set|Graph Sets|Named Graph|Named Graphs|RDF/i);
});
