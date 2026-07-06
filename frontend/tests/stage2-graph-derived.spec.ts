import { expect, test, type Page } from "@playwright/test";

// Stage 2 §4–§7 — graph-derived smoke tests.
//
// Each test mounts a Stage 2 page via the `?graphSet=` URL parameter and
// mocks the corresponding read-model endpoint to assert the page renders
// its key UI affordances (eyebrow text, list rows, action buttons, kind
// tabs). These are intentionally minimal: canonical-write flows live
// behind Modal interactions and are out of scope for this smoke slice.

const project = { id: "project-stage2", name: "Stage 2 Sandbox", description: "graph-derived smoke" };
const ontology = {
  id: "ontology-stage2",
  project_id: project.id,
  current_version_id: "version-stage2",
  name: "Stage 2 Ontology",
  description: "graph-derived",
  status: "active",
};
const version = {
  id: "version-stage2",
  ontology_id: ontology.id,
  parent_version_id: null,
  version_number: 1,
  status: "draft",
  workflow_status: "schema_draft",
  schema_snapshot: {},
  graph_snapshot: {},
  publication_report: {},
  created_at: "2026-07-01T00:00:00Z",
  published_at: null,
};
const brief = {
  id: "brief-stage2",
  project_id: project.id,
  fields: {},
  field_states: {},
  field_sources: {},
  missing_fields: [],
  clarification_items: [],
  completeness: 1,
};

const GRAPH_SET_ID = "gs-test";

const classTopologyEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      iri: "http://x/Class1",
      label: "Class 1",
      source_graph_iri: "http://x/g",
      assertion_kind: "asserted",
    },
  ],
};

const entityListEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      iri: "http://x/Entity1",
      label: "Entity One",
      source_graph_iri: "http://x/g",
      assertion_kind: "asserted",
      class_iri: "http://x/Class1",
      class_label: "Class 1",
    },
  ],
};
const entityRelationsEnvelope = { graph_set_id: GRAPH_SET_ID, items: [] };

const mappingListEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      mapping: "http://x/mapping/m1",
      external_field: "http://x/external-field/field-1",
      target: "http://x/class/Class1",
      join_key: { entity_property: "id", external_field: "eid" },
      confidence: 0.9,
      owner: "catalog-owner",
      graph: "http://x/g",
    },
  ],
};

function factRow(kind: string) {
  return {
    id: `fact-${kind}-1`,
    fact_id: `fact-${kind}-1`,
    assertion_kind: kind,
    subject_iri: "http://x/s1",
    subject_label: "Entity One",
    predicate_iri: "http://x/p/hasStatus",
    predicate_label: "hasStatus",
    object_value: "active",
    object_label: "active",
    graph_iri: "http://x/g",
    source_graph_iri: "http://x/g",
    evidence_status: "with_evidence",
    audit_status: "pending",
    stale: false,
    stale_reason: null,
  };
}

const factEnvelopeAsserted = {
  graph_set_id: GRAPH_SET_ID,
  source_signature: "sig",
  projection_version: "1",
  model_name: "fact-audit-queue",
  include: "asserted",
  derived_state: {},
  warnings: [],
  items: [factRow("asserted")],
};
const factEnvelopeEmpty = {
  ...factEnvelopeAsserted,
  items: [],
};

const dataSource = {
  id: "src-1",
  project_id: project.id,
  name: "Source 1",
  source_type: "postgres",
  owner: null,
  authority_level: "official",
  status: "available",
  description: null,
  connection_policy: {},
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};
const dataResource = {
  id: "res-1",
  project_id: project.id,
  data_source_id: dataSource.id,
  name: "Resource 1",
  resource_type: "table",
  owner: null,
  authority_level: "official",
  status: "available",
  description: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};
const externalField = {
  id: "field-1",
  project_id: project.id,
  data_source_id: dataSource.id,
  data_resource_id: dataResource.id,
  name: "Field 1",
  data_type: "string",
  sensitivity: "internal",
  access_policy: "allow",
  masking_rule: null,
  approval_note: null,
  audit_required: false,
  description: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

async function mockCommon(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = route.request().method();
    let body: unknown = [];

    // Generic workspace scaffolding.
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
    else if (path === `/ontologies/${ontology.id}/build-overview`) body = {
      ontology_id: ontology.id,
      graph_set: {
        graph_set_id: GRAPH_SET_ID,
        members: [],
        missing_evidence_count: 0,
        last_semantic_edit_at: "2026-07-01T00:00:00Z",
      },
      project_brief: { completeness: 1, missing_fields: [] },
      competency_questions: { total: 0, by_status: {} },
      next_actions: [],
    };
    else if (path === `/ontologies/${ontology.id}/versions`) body = [version];
    else if (path === `/ontologies/${ontology.id}/classes`) body = [];
    else if (path === `/ontologies/${ontology.id}/relation-types`) body = [];
    else if (path === `/ontologies/${ontology.id}/entities`) body = [];
    else if (path === `/ontologies/${ontology.id}/relations`) body = [];
    else if (path === `/ontologies/${ontology.id}/proposals`) body = [];

    // Postgres catalog endpoints (still Postgres even with graphSet per spec §7.1).
    else if (path === `/projects/${project.id}/data-sources`) body = [dataSource];
    else if (path === `/projects/${project.id}/data-resources`) body = [dataResource];
    else if (path === `/projects/${project.id}/external-fields`) body = [externalField];
    else if (path === `/projects/${project.id}/semantic-mappings`) body = [];
    else if (path === `/projects/${project.id}/connector-templates`) body = [];

    // Semantic (graph-derived) read models.
    else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/class-topology`) {
      body = classTopologyEnvelope;
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-list`) {
      body = entityListEnvelope;
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-relations`) {
      body = entityRelationsEnvelope;
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/mapping-list`) {
      body = mappingListEnvelope;
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/fact-audit-queue`) {
      const kind = url.searchParams.get("kind");
      body = kind === "asserted" ? factEnvelopeAsserted : factEnvelopeEmpty;
    }

    else if (path === "/health/dependencies") body = { postgres: { status: "ok" }, neo4j: { status: "ok" } };
    // Ignore canonical-write and side-effect endpoints in the smoke slice.
    else if (method !== "GET") body = {};
    await route.fulfill({ json: body });
  });
}

test("ClassesPage graph-derived path renders class topology", async ({ page }) => {
  await mockCommon(page);
  await page.goto(
    `/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=classes&graphSet=${GRAPH_SET_ID}`,
  );
  await expect(page.getByText("Stage 2 · graph-derived").first()).toBeVisible();
  // Stage 2 page h1 — disambiguate from the sidebar nav heading.
  await expect(page.locator("section.classesPage.stage2").getByRole("heading", { name: "Classes" })).toBeVisible();
  await expect(page.getByText("Class 1")).toBeVisible();
  await expect(page.getByRole("button", { name: "Refresh" })).toBeEnabled();
});

test("EntitiesPage graph-derived path renders entity and relations cards", async ({ page }) => {
  await mockCommon(page);
  await page.goto(
    `/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=entities&graphSet=${GRAPH_SET_ID}`,
  );
  await expect(page.getByText("Stage 2 · graph-derived").first()).toBeVisible();
  await expect(page.locator("section.entitiesPage.stage2").getByRole("heading", { name: "Entities" })).toBeVisible();
  await expect(page.getByText("Entity One")).toBeVisible();
  await expect(page.getByRole("button", { name: "New entity" })).toBeEnabled();
});

test("CatalogMappingsStep graph-derived path renders mapping list on step 4", async ({ page }) => {
  await mockCommon(page);
  await page.goto(
    `/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=catalog&graphSet=${GRAPH_SET_ID}`,
  );
  await expect(page.getByRole("heading", { name: "Data Catalog" })).toBeVisible();

  // Step 1: pick the existing data source to seed wizardSourceId → step 2.
  await page.getByRole("button", { name: /Source 1/ }).first().click();
  // Step 2: pick the existing data resource to seed wizardResourceId → step 3
  // and unlock step 4 in the indicator.
  await page.getByRole("button", { name: /Resource 1/ }).first().click();
  // Step 3: jump directly to step 4 via the indicator (now reachable because
  // wizardResourceId is set).
  await page
    .locator(".wizardStep")
    .filter({ hasText: "语义映射" })
    .first()
    .click();

  // Mapping list rendered with the mocked row.
  await expect(page.getByText(/已有 mapping/).first()).toBeVisible();
  await expect(page.getByText("http://x/class/Class1")).toBeVisible();
  // "Add mapping" button present on the new graph-derived step. It is
  // disabled until the user fills target + field (smoke scope stops here;
  // form fill + canonical write is out of scope).
  await expect(page.getByRole("button", { name: "添加 mapping" })).toBeVisible();
});

test("FactAuditPage graph-derived path renders asserted rows and kind tabs", async ({ page }) => {
  await mockCommon(page);
  await page.goto(
    `/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=facts&graphSet=${GRAPH_SET_ID}`,
  );
  await expect(page.getByText("Stage 2 · graph-derived").first()).toBeVisible();
  await expect(page.locator("section.factAuditPage.stage2").getByRole("heading", { name: "Fact Audit" })).toBeVisible();
  // Asserted tab default-selected with one row.
  await expect(page.getByText("Entity One").first()).toBeVisible();
  // All 4 kind tabs present (Antd Segmented renders the radio input as
  // visually-hidden — assert against the visible labels instead).
  await expect(page.locator("section.factAuditPage.stage2").getByText("Asserted", { exact: true })).toBeVisible();
  await expect(page.locator("section.factAuditPage.stage2").getByText("Inferred", { exact: true })).toBeVisible();
  await expect(page.locator("section.factAuditPage.stage2").getByText("Rule-derived", { exact: true })).toBeVisible();
  await expect(page.locator("section.factAuditPage.stage2").getByText("Missing evidence", { exact: true })).toBeVisible();
});
