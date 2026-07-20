import { expect, test, type Page } from "@playwright/test";

// Stage 2 §4–§7 — graph-derived smoke tests.
//
// Each test mounts a Stage 2 page via the `?graphSet=` URL parameter and
// mocks the corresponding read-model endpoint to assert the page renders
// its key UI affordances (eyebrow text, topology canvas, action buttons,
// kind tabs). These are intentionally minimal: canonical-write flows live
// behind Modal interactions and are out of scope for this smoke slice.

const project = { id: "project-stage2", name: "Stage 2 Sandbox", description: "graph-derived smoke" };
const ontology = {
  id: "ontology-stage2",
  project_id: project.id,
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
type ReadModelRequest = { model: string; include: string | null };

const classTopologyEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      iri: "http://x/Class1",
      label: "Class 1",
      source_graph_iri: "http://x/g",
      assertion_kind: "asserted",
      parent: "http://x/Class0",
    },
    {
      iri: "http://x/Class0",
      label: "Class 0",
      source_graph_iri: "http://x/g",
      assertion_kind: "asserted",
    },
  ],
};

const relationTypeEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      iri: "http://x/relation/owns",
      label: "owns",
      source_graph_iri: "http://x/g",
      assertion_kind: "asserted",
      source: "http://x/Class1",
      target: "http://x/Class0",
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
    {
      iri: "http://x/Entity2",
      label: "Entity Two",
      source_graph_iri: "http://x/g",
      assertion_kind: "asserted",
      class_iri: "http://x/Class1",
      class_label: "Class 1",
    },
    {
      iri: "http://x/Entity3",
      label: "Rule Classified Entity",
      source_graph_iri: "http://x/rule",
      assertion_kind: "rule_derived",
      class_iri: "http://x/RuleClass",
      class_label: "Rule Class",
    },
  ],
};
const entityRelationsEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      iri: "http://x/rel/1",
      label: "knows",
      source_graph_iri: "http://x/g",
      assertion_kind: "asserted",
      source: "http://x/Entity1",
      target: "http://x/Entity2",
      relation: "http://x/relation/knows",
    },
    {
      iri: "http://x/rel/2",
      label: "infers",
      source_graph_iri: "http://x/reasoning",
      assertion_kind: "owl_inferred",
      source: "http://x/Entity1",
      target: "http://x/Entity2",
      relation: "http://x/relation/infers",
    },
    {
      iri: "http://x/rel/3",
      label: "qualifies",
      source_graph_iri: "http://x/rule",
      assertion_kind: "rule_derived",
      stale: true,
      source: "http://x/Entity2",
      target: "http://x/Entity1",
      relation: "http://x/relation/qualifies",
    },
  ],
};
const entityLiteralFactsEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      id: "literal-fact-1",
      subject_iri: "http://x/Entity1",
      predicate_iri: "http://x/property/status",
      predicate_label: "status",
      object_value: "active",
      object_label: "active",
      assertion_kind: "asserted",
      stale: false,
    },
  ],
};

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
const factEnvelopeRule = {
  ...factEnvelopeAsserted,
  include: "asserted-plus-rules",
  items: [
    {
      ...factRow("rule_derived"),
      id: "fact-rule-type-1",
      fact_id: "fact-rule-type-1",
      subject_label: "Rule Classified Entity",
      predicate_iri: "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
      predicate_label: "type",
      object_value: "http://x/RuleClass",
      object_is_iri: true,
      object_label: "Rule Class",
    },
  ],
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
  const readModelRequests: ReadModelRequest[] = [];
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
    // `ontologies/{id}/versions` endpoint was removed in Phase B (legacy
    // governance hard-cut). Mock kept as defensive `[]` only.
    else if (path === `/ontologies/${ontology.id}/versions`) body = [];
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
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/relation-type-list`) {
      body = relationTypeEnvelope;
    } else if (path === "/semantic/context:query") {
      const payload = route.request().postDataJSON();
      expect(method).toBe("POST");
      expect(payload).toEqual(expect.objectContaining({
        project_id: project.id,
        scope_mode: "ontologies",
        ontology_ids: [ontology.id],
        resource_types: ["concept"],
        depth: 0,
        search_mode: "hybrid",
      }));
      const entityOnly = payload.query === "entity-only";
      body = {
        query: { text: payload.query, normalized_terms: [payload.query] },
        result_status: "matched",
        scope: {},
        primary_matches: entityOnly
          ? [{ kind: "instance", iri: "http://x/Entity1" }]
          : [
              { kind: "concept", iri: "http://x/Class1" },
              { kind: "instance", iri: "http://x/Entity1" },
            ],
        related_context: [],
        warnings: [],
        recall: { completeness: "complete" },
      };
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-list`) {
      const include = url.searchParams.get("include");
      readModelRequests.push({ model: "entity-list", include });
      body = {
        ...entityListEnvelope,
        items: entityListEnvelope.items.filter((row) => entityVisibleInInclude(row.assertion_kind, include)),
      };
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-relations`) {
      const include = url.searchParams.get("include");
      readModelRequests.push({ model: "entity-relations", include });
      body = {
        ...entityRelationsEnvelope,
        items: entityRelationsEnvelope.items.filter((row) => relationVisibleInInclude(row.assertion_kind, include)),
      };
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-literal-facts`) {
      readModelRequests.push({ model: "entity-literal-facts", include: url.searchParams.get("include") });
      expect(url.searchParams.get("entity")).toBe("http://x/Entity1");
      body = entityLiteralFactsEnvelope;
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/mapping-list`) {
      body = mappingListEnvelope;
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/fact-audit-queue`) {
      const kind = url.searchParams.get("kind");
      body = kind === "asserted"
        ? factEnvelopeAsserted
        : kind === "rule_derived"
          ? factEnvelopeRule
          : factEnvelopeEmpty;
    }

    else if (path === "/health/dependencies") body = { postgres: { status: "ok" } };
    // Ignore canonical-write and side-effect endpoints in the smoke slice.
    else if (method !== "GET") body = {};
    await route.fulfill({ json: body });
  });
  return readModelRequests;
}

function relationVisibleInInclude(assertionKind: string, include: string | null) {
  if (assertionKind === "asserted") return true;
  if (assertionKind === "owl_inferred") {
    return include === "asserted-plus-reasoning" || include === "full-working-view";
  }
  if (assertionKind === "rule_derived") {
    return include === "asserted-plus-rules" || include === "full-working-view";
  }
  return false;
}

function entityVisibleInInclude(assertionKind: string, include: string | null) {
  if (assertionKind === "asserted") return true;
  if (assertionKind === "rule_derived") {
    return include === "asserted-plus-rules" || include === "full-working-view";
  }
  return include === "asserted-plus-reasoning" || include === "full-working-view";
}

test("ClassesPage graph-derived path renders class topology", async ({ page }) => {
  await mockCommon(page);
  await page.goto(
    `/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=classes&graphSet=${GRAPH_SET_ID}`,
  );
  await expect(page.getByText("Business modeling").first()).toBeVisible();
  // Stage 2 page h1 — disambiguate from the sidebar nav heading.
  await expect(page.locator("section.classesPage.stage2").getByRole("heading", { name: "Classes" })).toBeVisible();
  await expect(page.getByText(/Class force graph · 2 nodes · 2 edges/)).toBeVisible();
  await expect(page.getByTestId("force-graph-canvas")).toBeVisible();
  await expect(page.getByLabel("Graph item details")).toHaveCount(0);
  await expect(page.locator("section.classesPage.stage2 .classList")).toHaveCount(0);
  await page.locator('button[aria-label="Select node Class 1"]').dispatchEvent("click");
  const details = page.getByLabel("Graph item details");
  await expect(details.getByRole("heading", { name: "Class 1" })).toBeVisible();
  await details.getByRole("button", { name: "Edit" }).click();
  await details.getByLabel("Name").fill("Class 1 renamed");
  const updateRequest = page.waitForRequest(
    (request) =>
      request.url().includes("/semantic/canonical-writes:compile-and-apply") &&
      request.method() === "POST" &&
      request.postDataJSON().command_kind === "update_class",
  );
  await details.getByRole("button", { name: "Save" }).click();
  await updateRequest;
  await page.locator('button[aria-label="Select edge owns"]').dispatchEvent("click");
  await expect(details.getByText("Relation type")).toBeVisible();
  await details.getByRole("button", { name: "Close details" }).click();
  await expect(page.getByLabel("Graph item details")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Refresh" })).toBeEnabled();
});

test("ClassesPage uses concept-only hybrid recall to filter loaded topology", async ({ page }) => {
  await mockCommon(page);
  await page.goto(
    `/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=classes&graphSet=${GRAPH_SET_ID}`,
  );

  const input = page.getByPlaceholder("Search classes");
  const recallRequest = page.waitForRequest((request) =>
    request.method() === "POST" &&
    request.url().includes("/semantic/context:query") &&
    request.postDataJSON().query === "分类",
  );
  await input.fill("分类");
  await recallRequest;
  await expect(page.locator('button[aria-label="Select node Class 1"]')).toBeVisible();
  await expect(page.locator('button[aria-label="Select node Class 0"]')).toHaveCount(0);

  const instanceOnlyRequest = page.waitForRequest((request) =>
    request.method() === "POST" &&
    request.url().includes("/semantic/context:query") &&
    request.postDataJSON().query === "entity-only",
  );
  await input.fill("entity-only");
  await instanceOnlyRequest;
  await expect(page.locator('button[aria-label="Select node Class 1"]')).toHaveCount(0);
  await expect(page.locator('button[aria-label="Select node Class 0"]')).toHaveCount(0);

  await input.fill("");
  await expect(page.locator('button[aria-label="Select node Class 1"]')).toBeVisible();
  await expect(page.locator('button[aria-label="Select node Class 0"]')).toBeVisible();
});

test("EntitiesPage graph-derived path renders entity topology only", async ({ page }) => {
  const readModelRequests = await mockCommon(page);
  await page.goto(
    `/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=entities&graphSet=${GRAPH_SET_ID}`,
  );
  await expect(page.getByText("Business modeling").first()).toBeVisible();
  await expect(page.locator("section.entitiesPage.stage2").getByRole("heading", { name: "Entities" })).toBeVisible();
  await expect(page.getByText(/Entity force graph · 2 nodes · 1 edges/)).toBeVisible();
  await expect(page.getByTestId("force-graph-canvas")).toBeVisible();
  expect(readModelRequests).toEqual(
    expect.arrayContaining([
      { model: "entity-list", include: "asserted" },
      { model: "entity-relations", include: "asserted" },
    ]),
  );
  await expect(page.getByLabel("Graph item details")).toHaveCount(0);
  await expect(page.locator("section.entitiesPage.stage2 .entityList")).toHaveCount(0);
  await expect(page.locator("section.entitiesPage.stage2 .relationList")).toHaveCount(0);
  await expect(page.locator("section.entitiesPage.stage2")).not.toContainText("http://x/g");
  await expect(page.locator("section.entitiesPage.stage2")).not.toContainText("source_graph_iri");

  await Promise.all([
    page.waitForRequest((request) => (
      request.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-list`) &&
      new URL(request.url()).searchParams.get("include") === "asserted-plus-reasoning"
    )),
    page.waitForRequest((request) => (
      request.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-relations`) &&
      new URL(request.url()).searchParams.get("include") === "asserted-plus-reasoning"
    )),
    page.locator("section.entitiesPage.stage2").getByText("Reasoning graph", { exact: true }).click(),
  ]);
  await expect(page.getByText("Facts plus currently available reasoning results.")).toBeVisible();
  await expect(page.getByText(/Entity force graph · 2 nodes · 2 edges/)).toBeVisible();
  await expect(page.locator('button[aria-label="Select edge infers"]')).toHaveAttribute("data-edge-kind", "owl_inferred");
  await expect(page.locator("section.entitiesPage.stage2").getByText("Focus")).not.toBeVisible();
  await page.locator('button[aria-label="Select edge infers"]').dispatchEvent("click");
  let details = page.getByLabel("Graph item details");
  await expect(details.getByText("Relation", { exact: true })).toBeVisible();
  await expect(details.getByText("Reasoning", { exact: true })).toBeVisible();
  await details.getByRole("button", { name: "Close details" }).click();

  await Promise.all([
    page.waitForRequest((request) => (
      request.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-list`) &&
      new URL(request.url()).searchParams.get("include") === "asserted-plus-rules"
    )),
    page.waitForRequest((request) => (
      request.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-relations`) &&
      new URL(request.url()).searchParams.get("include") === "asserted-plus-rules"
    )),
    page.locator("section.entitiesPage.stage2").getByText("Rule graph", { exact: true }).click(),
  ]);
  await expect(page.getByText("Facts plus currently available rule results.")).toBeVisible();
  await expect(page.getByText(/Entity force graph · 3 nodes · 2 edges/)).toBeVisible();
  await expect(page.locator('button[aria-label="Select node Rule Classified Entity"]')).toHaveAttribute(
    "data-node-kind",
    "rule_derived",
  );
  await expect(page.locator('button[aria-label="Select edge qualifies"]')).toHaveAttribute("data-edge-kind", "rule_derived");
  await expect(page.locator('button[aria-label="Select edge qualifies"]')).toHaveAttribute("data-edge-stale", "true");
  await expect(page.locator("section.entitiesPage.stage2").getByText("Focus")).not.toBeVisible();
  await page.locator('button[aria-label="Select edge qualifies"]').dispatchEvent("click");
  details = page.getByLabel("Graph item details");
  await expect(details.getByText("Relation", { exact: true })).toBeVisible();
  await expect(details.getByText("Rule", { exact: true })).toBeVisible();
  await details.getByRole("button", { name: "Close details" }).click();

  await Promise.all([
    page.waitForRequest((request) => (
      request.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-list`) &&
      new URL(request.url()).searchParams.get("include") === "full-working-view"
    )),
    page.waitForRequest((request) => (
      request.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-relations`) &&
      new URL(request.url()).searchParams.get("include") === "full-working-view"
    )),
    page.locator("section.entitiesPage.stage2").getByText("Complete view", { exact: true }).click(),
  ]);
  await expect(page.getByText(/Entity force graph · 3 nodes · 3 edges/)).toBeVisible();
  await expect(page.locator("section.entitiesPage.stage2").getByText("Focus", { exact: true })).toBeVisible();
  await page.locator("section.entitiesPage.stage2").getByText("Reasoning", { exact: true }).click();
  await expect(page.locator("section.entitiesPage.stage2").getByRole("radio", { name: "Reasoning", exact: true })).toBeChecked();

  await page.locator('button[aria-label="Select node Entity One"]').dispatchEvent("click");
  details = page.getByLabel("Graph item details");
  await expect(details.getByRole("heading", { name: "Entity One" })).toBeVisible();
  await expect(details).not.toContainText("http://x/g");
  await expect(details).not.toContainText("Source graph");
  await expect(details.getByText("Fact", { exact: true }).first()).toBeVisible();
  await expect(details.getByText("Literal facts")).toBeVisible();
  await expect(details.getByText("status")).toBeVisible();
  await expect(details.getByText("active")).toBeVisible();
  expect(readModelRequests).toEqual(
    expect.arrayContaining([
      { model: "entity-literal-facts", include: "full-working-view" },
    ]),
  );
  await details.getByRole("button", { name: "Edit" }).click();
  await details.getByLabel("Label").fill("Entity One renamed");
  const updateRequest = page.waitForRequest(
    (request) =>
      request.url().includes("/semantic/canonical-writes:compile-and-apply") &&
      request.method() === "POST" &&
      request.postDataJSON().command_kind === "update_entity",
  );
  await details.getByRole("button", { name: "Save" }).click();
  await updateRequest;
  await page.locator('button[aria-label="Select edge knows"]').dispatchEvent("click");
  await expect(details.getByText("Relation", { exact: true })).toBeVisible();
  await details.getByRole("button", { name: "Close details" }).click();
  await expect(page.getByLabel("Graph item details")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "New entity" })).toBeEnabled();
});

// CatalogMappingsStep graph-derived smoke — REMOVED in Phase F.
// The catalog tab was deleted in Phase E (App.tsx rewrite). The Postgres
// catalog data layer still exists, but the wizard UI that consumed it is
// gone. This test asserted the now-removed wizard's step-4 mapping list,
// so it cannot pass without resurrecting removed UI.

test("FactAuditPage graph-derived path renders asserted rows and kind tabs", async ({ page }) => {
  await mockCommon(page);
  await page.goto(
    `/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=facts&graphSet=${GRAPH_SET_ID}`,
  );
  await expect(page.getByText("Business modeling").first()).toBeVisible();
  await expect(page.locator("section.factAuditPage.stage2").getByRole("heading", { name: "Facts" })).toBeVisible();
  // Asserted tab default-selected with one row.
  await expect(page.getByText("Entity One").first()).toBeVisible();
  // All 4 kind tabs present (Antd Segmented renders the radio input as
  // visually-hidden — assert against the visible labels instead).
  await expect(page.locator("section.factAuditPage.stage2").getByText("Asserted", { exact: true })).toBeVisible();
  await expect(page.locator("section.factAuditPage.stage2").getByText("Inferred", { exact: true })).toBeVisible();
  await expect(page.locator("section.factAuditPage.stage2").getByText("Rule-derived", { exact: true })).toBeVisible();
  await page.locator("section.factAuditPage.stage2").getByText("Rule-derived", { exact: true }).click();
  await expect(page.getByText("Rule Classified Entity").first()).toBeVisible();
  await expect(page.getByText("Rule Class").first()).toBeVisible();
});
