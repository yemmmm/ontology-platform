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
  workflow_status: "validated",
  schema_snapshot: {},
  graph_snapshot: {},
  publication_report: {},
  created_at: "2026-07-05T00:00:00Z",
  published_at: null,
};

const namedGraph = {
  graph_iri: "http://example.org/graphs/ontology/main",
  category: "ontology",
  registered: true,
  owner_type: "ontology",
  owner_id: ontology.id,
  mutable_by_direct_edit: true,
  editable: true,
  editability_reason: null,
  revision: 3,
  content_hash: "abc123",
  derived_pointers: [],
  metadata: {},
};
const dataGraph = {
  ...namedGraph,
  graph_iri: "http://example.org/graphs/data/main",
  category: "data",
  editable: false,
  editability_reason: "Locked for review",
};
const graphSet = {
  id: "graph-set-1",
  name: "Working view",
  scope_type: "ontology",
  scope_id: ontology.id,
  status: "active",
  source_signature: "sig-1",
  created_by: "tester",
  members: [
    {
      graph_iri: namedGraph.graph_iri,
      role: "asserted_ontology",
      required: true,
      sort_order: 0,
      metadata: {},
    },
    {
      graph_iri: dataGraph.graph_iri,
      role: "asserted_data",
      required: true,
      sort_order: 1,
      metadata: {},
    },
  ],
  current_pointers: [
    { kind: "reasoning_result", graph_iri: "http://example.org/graphs/reasoning-result/run-1", stale: false },
    { kind: "rule_result", graph_iri: "http://example.org/graphs/rule-result/run-2", stale: true },
  ],
  metadata: {},
};
const ruleDefinition = {
  id: "rule-def-1",
  rule_iri: "http://example.org/rules/DangerousSupplier",
  name: "Flag dangerous supplier",
  language: "sparql_construct",
  version: "v1",
  status: "active",
  body: { template: "CONSTRUCT WHERE { ?s a ex:Dangerous }" },
  input_roles: ["asserted_data"],
  output_kind: "assertion",
  uses_inferred_facts: false,
  requires_review: false,
  priority: 1,
  safety_profile: {},
  created_by: "tester",
  created_at: "2026-07-05T00:00:00Z",
  updated_at: "2026-07-05T00:00:00Z",
  metadata: {},
};
const validationRun = {
  run_id: "validation-1",
  status: "succeeded",
  conforms: true,
  report_graph_iri: "http://example.org/graphs/validation-report/validation-1",
  summary: { violation_count: 0 },
  guidance: {},
  warnings: [],
  graph_set_id: graphSet.id,
  source_signature: graphSet.source_signature,
  input_graph_revisions: { [namedGraph.graph_iri]: 3 },
  shape_version: "v1",
  engine_version: "pyshacl-0.26",
  validation_scope: "asserted_only",
  missing_evidence_dependencies: {},
  staleness: { stale: false },
  started_at: "2026-07-05T00:00:00Z",
  finished_at: "2026-07-05T00:00:05Z",
  error: null,
};
const reasoningRun = {
  run_id: "reasoning-1",
  status: "succeeded",
  consistent: true,
  classification: { classified_classes: 12 },
  entailments: [{ subject: "ex:A", predicate: "rdfs:subClassOf", object: "ex:B" }],
  result_graph_iri: "http://example.org/graphs/reasoning-result/reasoning-1",
  graph_set_id: graphSet.id,
  source_signature: graphSet.source_signature,
  input_graph_revisions: { [namedGraph.graph_iri]: 3 },
  input_derived_pointers: {},
  engine_version: "HermiT-1.4",
  shape_version: null,
  tasks: ["consistency"],
  profile: "owl2_dl",
  missing_evidence_dependencies: {},
  warnings: [],
  derived_pointer: { kind: "reasoning_result", stale: false },
  started_at: "2026-07-05T00:00:00Z",
  finished_at: "2026-07-05T00:00:30Z",
  error: null,
};
const ruleRun = {
  run_id: "rule-1",
  status: "succeeded",
  engine_name: "sparql_construct",
  engine_version: "v1",
  graph_set_id: graphSet.id,
  rule_definition_id: ruleDefinition.id,
  rule_version: ruleDefinition.version,
  result_graph_iri: "http://example.org/graphs/rule-result/rule-1",
  rule_run_graph_iri: "http://example.org/graphs/rule-run/rule-1",
  generated_statement_count: 4,
  statements: [],
  bindings: [],
  warnings: [],
  truncated: false,
  missing_evidence_dependencies: {},
  audit_status: "system_accepted",
  explanations: [],
  rule_count: 1,
  derived_pointer: { kind: "rule_result", stale: false },
  started_at: "2026-07-05T00:00:00Z",
  finished_at: "2026-07-05T00:00:02Z",
  error: null,
};
const missingEvidenceSummary = {
  graph_set_id: graphSet.id,
  dependencies: [
    {
      graph_iri: dataGraph.graph_iri,
      subject: "ex:Supplier/A",
      predicate: "ex:certifiedBy",
      evidence_status: "missing_evidence",
    },
  ],
  summary: { missing_evidence_count: 1 },
  warning: "Some statements carry missing-evidence status.",
};
const auditRecord = {
  id: "audit-1",
  actor: "agent-test",
  reason: "Smoke edit",
  input_format: "turtle",
  target_graph_iri: namedGraph.graph_iri,
  affected_graph_iris: [namedGraph.graph_iri],
  validation_result: { conforms: true },
  graph_delta: {
    added_quads: [{ graph: namedGraph.graph_iri, subject: "ex:A", predicate: "ex:label", object: '"Sample"' }],
    removed_quads: [],
    affected_graph_iris: [namedGraph.graph_iri],
  },
  evidence_status: "evidence_bound",
  warning_state: {},
  applied: true,
  created_at: "2026-07-05T00:00:00Z",
};

async function mockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    const method = route.request().method();
    let body: unknown = [];
    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    // `ontologies/{id}/versions` endpoint was removed in Phase B (legacy
    // governance hard-cut). The mock is kept as a defensive `[]` in case a
    // future caller fetches it through OntologyHomePage.
    else if (path === `/ontologies/${ontology.id}/versions`) body = [];
    else if (path === `/ontologies/${ontology.id}/classes`) body = [];
    else if (path === `/ontologies/${ontology.id}/relation-types`) body = [];
    else if (path === `/ontologies/${ontology.id}/entities`) body = [];
    else if (path === `/ontologies/${ontology.id}/relations`) body = [];
    else if (path === "/semantic/status") body = {
      graphs: { total: 2, by_category: { ontology: 1, data: 1 }, editability: { editable: 1, locked: 1 } },
      derived: { missing_evidence_count: 1, stale_count: 1 },
    };
    else if (path === "/semantic/graphs") body = { graphs: [namedGraph, dataGraph], summary: {} };
    else if (path === `/semantic/graphs/${namedGraph.graph_iri}`) body = namedGraph;
    else if (path === "/semantic/graph-sets") body = { graph_sets: [graphSet] };
    else if (path === `/semantic/graph-sets/${graphSet.id}`) body = graphSet;
    else if (path === `/semantic/graph-sets/${graphSet.id}/missing-evidence`) body = missingEvidenceSummary;
    else if (path === "/semantic/rule-definitions") body = { rules: [ruleDefinition] };
    else if (path === "/semantic/edits/audits") body = [auditRecord];
    else if (path === "/semantic/validation-runs/validation-1") body = validationRun;
    else if (path === "/semantic/reasoning-runs/reasoning-1") body = reasoningRun;
    else if (path === "/semantic/rule-runs/rule-1") body = ruleRun;
    else if (method === "POST" && path === "/semantic/datasets:load") body = {
      loaded: true,
      format: "turtle",
      graph_count: 1,
      triple_count: 4,
      warnings: [],
    };
    else if (method === "POST" && path === "/semantic/sparql:query") body = {
      result: { head: { vars: ["s"] }, results: { bindings: [] } },
      result_format: "json",
      truncated: false,
      warnings: [],
    };
    else if (method === "POST" && path === "/semantic/edits") body = {
      audit_id: "audit-preview",
      applied: false,
      affected_graph_iris: [namedGraph.graph_iri],
      delta: auditRecord.graph_delta,
      warnings: [],
      validation: { conforms: true },
      graph_revisions: { [namedGraph.graph_iri]: 4 },
      stale_derived_pointers: [],
    };
    else if (method === "PATCH" && path.startsWith("/semantic/graphs/") && path.endsWith("/editability")) body = {
      graph_iri: namedGraph.graph_iri,
      editable: false,
      updated_by: "tester",
      reason: "Lock for review",
    };
    else if (method === "POST" && path === "/semantic/derived-results:reconcile") body = {
      graph_sets_inspected: 1,
      pointers_marked_current: 1,
      pointers_marked_stale: 1,
    };
    else if (path === "/health/dependencies") body = { postgres: { status: "ok" }, neo4j: { status: "ok" } };
    await route.fulfill({ json: body });
  });
}

test("graph governance dashboard renders semantic health summary", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=graph-governance`);
  await expect(page.getByRole("heading", { name: "Graph Governance Dashboard" })).toBeVisible();
  await expect(page.getByText("Registered graphs").first()).toBeVisible();
  await expect(page.locator(".statTile", { hasText: "Stale derived results" })).toContainText("1");
  await expect(page.locator(".statTile", { hasText: "Missing evidence" })).toContainText("1");
  await expect(page.getByText("Working view").first()).toBeVisible();
  await expect(page.getByText("Smoke edit").first()).toBeVisible();
  await page.getByRole("button", { name: "Reconcile staleness" }).click();
  await expect(page.getByText(/Reconciled 1 graph sets/)).toBeVisible();
});

test("named graph registry lists graphs with editability state and lock toggle", async ({ page }) => {
  await mockApi(page);
  await page.addInitScript(() => {
    window.localStorage.setItem("ontology-platform-ui-lang", "en");
  });
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=named-graphs`);
  await expect(page.getByRole("heading", { name: "Named Graph Registry" })).toBeVisible();
  await expect(page.getByText("ontology/main").first()).toBeVisible();
  await expect(page.locator("tr", { hasText: "ontology/main" }).locator("[aria-label='editability-editable']")).toBeVisible();
  await expect(page.locator("tr", { hasText: "data/main" }).locator("[aria-label='editability-locked']")).toBeVisible();
  // Capture PATCH editability calls and replay a success body without asserting inside the click.
  const patchPromise = page.waitForRequest(
    (request) => request.url().includes("/semantic/graphs/") && request.url().includes("/editability") && request.method() === "PATCH",
  );
  await page.locator("tr", { hasText: "ontology/main" }).getByRole("button", { name: /Toggle graph editability/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("textbox").fill("Lock for review");
  await dialog.locator("button.ant-btn-primary").first().click();
  await patchPromise;
});

test("graph set detail shows members, pointers, and triggers reasoning run", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=graph-sets`);
  await expect(page.getByRole("heading", { name: "Graph Set Detail" })).toBeVisible();
  await expect(page.getByText("asserted_ontology").first()).toBeVisible();
  await expect(page.getByText("Stale derived").first()).toBeVisible();
  const runRequest = page.waitForRequest(
    (request) => request.url().includes(`/semantic/graph-sets/${graphSet.id}/reasoning-runs`) && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Run reasoning" }).click();
  await runRequest;
});

test("semantic edit workbench previews TriG content and exposes delta", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=semantic-edits`);
  await expect(page.getByRole("heading", { name: "Direct Semantic Edit Workbench" })).toBeVisible();
  await page.locator("textarea.semanticEditContent").fill("@prefix ex: <http://example.org/> . ex:Sample a ex:Concept .");
  const previewRequest = page.waitForRequest(
    (request) => request.url().includes("/semantic/edits") && request.method() === "POST",
  );
  await page.getByRole("button", { name: "Preview" }).click();
  await previewRequest;
  await expect(page.locator("[aria-label='graph-delta-viewer']")).toBeVisible();
  await expect(page.locator("[aria-label='affected-graphs']")).toBeVisible();
});

test("semantic runs page looks up reasoning run by ID and shows consistency", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=semantic-runs`);
  await expect(page.getByLabel("semantic-runs-page").getByRole("heading", { name: "Semantic Runs" })).toBeVisible();
  await page.getByLabel("Run kind").selectOption("reasoning");
  await page.getByPlaceholder("run-...").fill("reasoning-1");
  await page.getByRole("button", { name: "Load" }).click();
  await expect(page.locator("[aria-label='reasoning-result-panel']")).toBeVisible();
  await expect(page.getByText("Consistent").first()).toBeVisible();
});

test("import / export workspace uploads dataset and downloads export", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=semantic-import-export`);
  await expect(page.getByRole("heading", { name: "Import / Export Workspace" })).toBeVisible();
  await page.locator("textarea.semanticImportContent").first().fill("@prefix ex: <http://example.org/> . ex:Sample a ex:Concept .");
  await page.getByRole("button", { name: "Load dataset" }).click();
  await expect(page.getByText(/Dataset import loaded/)).toBeVisible();
  // Wait for the export endpoint mock to be ready and trigger preview.
  const exportRequest = page.waitForRequest(
    (request) => request.url().includes(`/semantic/graph-sets/${graphSet.id}/export`) && request.method() === "GET",
  );
  await page.getByRole("button", { name: "Preview export" }).click();
  await exportRequest;
  await expect(page.locator("details").filter({ hasText: "Export preview" })).toBeVisible();
});
