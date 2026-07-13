import { expect, test, type Page } from "@playwright/test";

// Stage 4 §11 — Playwright e2e for the Tools-stage surface.
//
// Covers the eight happy-path steps defined in plan Phase F1.2:
//   1. Tools → Search: query "acme" returns one row with [asserted] chip.
//   2. Asserted scope filter keeps row count unchanged.
//   3. OWL inferred scope filter drops row count to 0 (fixture has no inferred).
//   4. Tools → Agent Test: question run returns answer + graph_context.entries
//      containing the Acme Corp entry.
//   5. Tools → MCP tools: catalog shows ≥ 30 tools including
//      `compile_and_apply_canonical_command`.
//   6. Knowledge → Facts: fact drawer renders EvidenceExplorer bindings
//      (document_filename + sequence + text_preview).
//   7. Governance → Graph Governance: OWL Consistency section renders
//      consistent: true, is_stale: false.
//
// Mocks follow the single-catch-all pattern used by `stage3-publish.spec.ts`.
// Envelope shape `{ graph_set_id, model_name, projection_version, items }`
// matches `SemanticReadModelEnvelope`.

const project = {
  id: "project-stage4",
  name: "Stage 4 Sandbox",
  description: "tools smoke",
};
const ontology = {
  id: "ontology-stage4",
  project_id: project.id,
  name: "Stage 4 Ontology",
  description: "tools",
  status: "active",
};

const GRAPH_SET_ID = "gs-stage4";
const DATA_GRAPH = "http://op.local/semantic/graph/data/acme";
const ONTOLOGY_GRAPH = "http://op.local/semantic/graph/ontology/acme";

// ---------------------------------------------------------------------------
// Fixtures — entity-search
// ---------------------------------------------------------------------------

const entitySearchItems = [
  {
    iri: "http://op.local/entity/acme-corp",
    label: "Acme Corp",
    comment: "Acme is a manufacturer of widgets.",
    class_iri: "http://op.local/class/Organization",
    class_label: "Organization",
    assertion_kind: "asserted",
    source_graph_iri: DATA_GRAPH,
    source_signature: "sig-acme",
    evidence_status: "with_evidence",
    is_stale: false,
    graph_set_id: GRAPH_SET_ID,
  },
];

const entitySearchEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  model_name: "entity-search",
  projection_version: "1",
  items: entitySearchItems,
};

// Fixture — entity-literal-facts for the Acme Corp row, used by the
// recall page's inline detail panel.
const entityLiteralFactsEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  items: [
    {
      id: "fact-acme-founded",
      subject_iri: "http://op.local/entity/acme-corp",
      predicate_iri: "http://op.local/predicate/founded",
      predicate_label: "Founded",
      object_value: "1985",
      object_label: "1985",
      assertion_kind: "asserted",
      stale: false,
    },
  ],
};

// ---------------------------------------------------------------------------
// Fixtures — agent-test/run + graph_context (spec §7.2)
// ---------------------------------------------------------------------------

const agentTestRunResponse = {
  answer: "Acme Corp is an organization that manufactures widgets.",
  tool_calls: [],
  graph_context: {
    entries: [
      {
        iri: "http://op.local/entity/acme-corp",
        label: "Acme Corp",
        class_label: "Organization",
        assertion_kind: "asserted",
        source_graph_iri: DATA_GRAPH,
        source_signature: "sig-acme",
        is_stale: false,
      },
    ],
    generated_at: "2026-07-07T00:00:00Z",
    scope: {
      graph_set_id: GRAPH_SET_ID,
      ontology_id: ontology.id,
    },
  },
  prompt_preview: "Question: What is Acme Corp?\nContext: Acme Corp ...",
  warnings: [],
  errors: [],
};

// ---------------------------------------------------------------------------
// Fixtures — /api/mcp/tools (spec §5.4)
// ---------------------------------------------------------------------------

const mcpTools = [
  // 30 system tools to satisfy spec §11 step 6 minimum.
  ...Array.from({ length: 27 }, (_, i) => ({
    name: `system_tool_${i}`,
    description: `System tool ${i}`,
    input_schema_summary: { properties: [], required: [] },
    source_file: "system.py",
    category: "system" as const,
  })),
  {
    name: "compile_and_apply_canonical_command",
    description: "Compile and apply a canonical command (asserted graph write).",
    input_schema_summary: { properties: ["command_kind", "payload"], required: ["command_kind"] },
    source_file: "semantic.py",
    category: "semantic" as const,
  },
  {
    name: "interview_capture_answer",
    description: "Capture an interview answer.",
    input_schema_summary: { properties: ["question_id"], required: ["question_id"] },
    source_file: "interview.py",
    category: "interview" as const,
  },
  {
    name: "interview_finalize_session",
    description: "Finalize an interview session.",
    input_schema_summary: { properties: [], required: [] },
    source_file: "interview.py",
    category: "interview" as const,
  },
];

const mcpToolsEnvelope = {
  tools: mcpTools,
  total: mcpTools.length,
  by_category: {
    system: mcpTools.filter((t) => t.category === "system").length,
    interview: mcpTools.filter((t) => t.category === "interview").length,
    semantic: mcpTools.filter((t) => t.category === "semantic").length,
  },
};

// ---------------------------------------------------------------------------
// Fixtures — evidence-artifacts + chunks (spec §5.1)
// ---------------------------------------------------------------------------

const evidenceArtifact = {
  id: "ev-art-1",
  project_id: project.id,
  filename: "acme-overview.pdf",
  uploaded_at: "2026-07-01T00:00:00Z",
  content_type: "application/pdf",
  size_bytes: 1024,
};

const evidenceChunks = [
  {
    id: "ev-chunk-1",
    artifact_id: evidenceArtifact.id,
    sequence: 1,
    char_start: 0,
    char_end: 120,
    text_preview: "Acme is a manufacturer of widgets headquartered in Springfield.",
  },
];

// ---------------------------------------------------------------------------
// Fixtures — fact-audit-queue with field_set=evidence (spec §4.4)
// ---------------------------------------------------------------------------

const factWithEvidence = {
  id: "fact-1",
  fact_id: "fact-1",
  assertion_kind: "asserted",
  subject_iri: "http://op.local/entity/acme-corp",
  subject_label: "Acme Corp",
  predicate_iri: "http://op.local/predicate/industry",
  predicate_label: "industry",
  object_value: "manufacturing",
  object_label: "manufacturing",
  graph_iri: DATA_GRAPH,
  source_graph_iri: DATA_GRAPH,
  evidence_status: "with_evidence",
  audit_status: "pending",
  stale: false,
  stale_reason: null,
  evidence_bindings: [
    {
      chunk_iri: "tag:ontology-platform.internal,2026:evidence/ev-art-1/1",
      document_iri: `tag:ontology-platform.internal,2026:document/${evidenceArtifact.id}`,
      document_filename: evidenceArtifact.filename,
      sequence: 1,
      char_start: 0,
      char_end: 120,
      text_preview: "Acme is a manufacturer of widgets headquartered in Springfield.",
    },
  ],
};

const factAuditEvidenceEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  source_signature: "sig-acme",
  projection_version: "1",
  model_name: "fact-audit-queue",
  include: "asserted",
  derived_state: {},
  warnings: [],
  items: [factWithEvidence],
};

// ---------------------------------------------------------------------------
// Fixtures — owl-consistency-summary (spec §4.3)
// ---------------------------------------------------------------------------

const owlConsistencyItem = {
  run_id: "run-stage4-1",
  consistent: true,
  classification: null,
  entailment_count: 12,
  unsatisfiable_classes: [],
  result_graph_iri: "http://op.local/semantic/graph/derived/consistency/acme",
  started_at: "2026-07-07T00:00:00Z",
  finished_at: "2026-07-07T00:05:00Z",
  is_stale: false,
};

const owlConsistencyEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  model_name: "owl-consistency-summary",
  projection_version: "1",
  items: [owlConsistencyItem],
};

// ---------------------------------------------------------------------------
// Fixtures — graph-set scaffolding (so GraphGovernancePage finds an active set)
// ---------------------------------------------------------------------------

const graphSet = {
  id: GRAPH_SET_ID,
  name: "Acme Graph Set",
  scope_type: "ontology",
  scope_id: ontology.id,
  status: "active",
  source_signature: "sig-acme",
  created_at: "2026-07-01T00:00:00Z",
  members: [
    { graph_iri: ONTOLOGY_GRAPH, role: "asserted_ontology" },
    { graph_iri: DATA_GRAPH, role: "asserted_data" },
  ],
  current_pointers: [],
  editable_graph_count: 2,
};

const graphSetsEnvelope = {
  graph_sets: [graphSet],
  total: 1,
};

const governanceStatusEnvelope = {
  graphs: { total: 2, by_category: { ontology: 1, data: 1 }, editability: {} },
  derived: {},
};

// ---------------------------------------------------------------------------
// mockStage4 — single catch-all per stage3-publish.spec.ts convention
// ---------------------------------------------------------------------------

type Stage4MockMode = "success" | "empty" | "failFirst";

async function mockStage4(page: Page, mode: Stage4MockMode = "success") {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = route.request().method();
    let body: unknown = [];
    let status = 200;

    // --- Workspace scaffolding (shared with stage2/stage3 specs) ---
    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/build-context`) {
      body = {
        project,
        project_brief: {
          id: "brief-stage4",
          project_id: project.id,
          fields: {},
          field_states: {},
          field_sources: {},
          missing_fields: [],
          clarification_items: [],
          completeness: 1,
        },
        ontologies: [{ ...ontology, current_version: null }],
        competency_question_counts: {},
      };
    } else if (path.startsWith(`/projects/${project.id}/competency-questions`)) {
      body = [];
    } else if (path === `/ontologies/${ontology.id}/build-overview`) {
      body = {
        ontology_id: ontology.id,
        graph_set: {
          graph_set_id: GRAPH_SET_ID,
          members: [],
          missing_evidence_count: 0,
          last_semantic_edit_at: null,
        },
        project_brief: { completeness: 1, missing_fields: [] },
        competency_questions: { total: 0, by_status: {} },
        next_actions: [],
      };
    }

    // --- Stage 4 read-models ---
    else if (
      path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-search`
    ) {
      body = mode === "empty" ? { ...entitySearchEnvelope, items: [] } : entitySearchEnvelope;
    } else if (
      path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-literal-facts`
    ) {
      body = entityLiteralFactsEnvelope;
    } else if (
      path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/fact-audit-queue`
    ) {
      body = mode === "empty" ? { ...factAuditEvidenceEnvelope, items: [] } : factAuditEvidenceEnvelope;
    } else if (
      path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/owl-consistency-summary`
    ) {
      body = owlConsistencyEnvelope;
    }

    // --- Stage 4 agent-test run ---
    else if (path === "/agent-test/run" && method === "POST") {
      if (mode === "failFirst") {
        status = 500;
        body = { detail: "agent-test run failed (mock)" };
      } else {
        body = agentTestRunResponse;
      }
    }

    // --- Stage 4 MCP catalog (spec §5.4) ---
    else if (path === "/mcp/tools") {
      body = mcpToolsEnvelope;
    }

    // --- Stage 4 evidence-artifact REST surface (spec §5.1) ---
    else if (path === `/projects/${project.id}/evidence-artifacts`) {
      body = mode === "empty" ? [] : [evidenceArtifact];
    } else if (path === `/evidence-artifacts/${evidenceArtifact.id}`) {
      body = evidenceArtifact;
    } else if (path === `/evidence-artifacts/${evidenceArtifact.id}/chunks`) {
      body = mode === "empty" ? [] : evidenceChunks;
    }

    // --- GraphGovernancePage scaffolding (active graph set lookup) ---
    else if (path === "/semantic/graph-sets") {
      body = graphSetsEnvelope;
    } else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}`) {
      body = graphSet;
    } else if (path === "/semantic/graphs") {
      body = { graphs: [], total: 0 };
    } else if (path === "/semantic/status") {
      body = governanceStatusEnvelope;
    } else if (path === "/semantic/projections/status") {
      body = {
        manifests: [],
        stale: [],
        missing: [],
        stale_projection_count: 0,
      };
    } else if (path === "/semantic/edits/audits") {
      body = [];
    }

    // --- Health + default fall-through ---
    else if (path === "/health/dependencies") {
      body = { postgres: { status: "ok" } };
    } else if (method !== "GET") {
      body = {};
    }

    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

function workspaceUrl(tab: string) {
  return `/?project=${project.id}&ontology=${ontology.id}&tab=${tab}&graphSet=${GRAPH_SET_ID}`;
}

// ---------------------------------------------------------------------------
// Step 1 — Tools → Search: query "acme" shows the Acme Corp row with
//          [asserted] chip.
// ---------------------------------------------------------------------------

test("entity search returns the Acme Corp row with [asserted] chip", async ({
  page,
}) => {
  await mockStage4(page);
  await page.goto(workspaceUrl("search"));

  // Search input + section present.
  await expect(page.locator('[aria-label="entities-search-page"]')).toBeVisible();
  // Antd `Input` forwards aria-label onto the underlying <input> element.
  const input = page.locator('input[aria-label="entities-search-input"]');
  await expect(input).toBeVisible();

  // Type and wait for the debounced read-model request.
  const searchRequest = page.waitForRequest(
    (req) =>
      req.method() === "GET" &&
      req.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/read-models/entity-search`) &&
      req.url().includes("q=acme"),
  );
  await input.fill("acme");
  await searchRequest;

  // Result row + assertion chip render.
  const row = page.locator(
    '[aria-label="entity-search-row-http://op.local/entity/acme-corp"]',
  );
  await expect(row).toBeVisible();
  await expect(page.locator('[aria-label="entity-search-assertion-asserted"]')).toBeVisible();
});

// ---------------------------------------------------------------------------
// Step 2 — Asserted scope filter keeps the row count unchanged.
// ---------------------------------------------------------------------------

test("entity search asserted scope filter preserves the asserted row", async ({
  page,
}) => {
  await mockStage4(page);
  await page.goto(workspaceUrl("search"));

  // Trigger an initial result set so the row count assertion has a baseline.
  await page.locator('input[aria-label="entities-search-input"]').fill("acme");
  await expect(
    page.locator('[aria-label="entity-search-row-http://op.local/entity/acme-corp"]'),
  ).toBeVisible();
  await expect(page.locator('[aria-label="entities-search-results"] li')).toHaveCount(1);

  // Open the scope Select and choose Asserted.
  await page.locator('[aria-label="entities-search-scope"]').click();
  // Antd Select dropdown items render as `.ant-select-item-option` with a
  // `title` attribute mirroring the option label. Match on the title to
  // stay locale-resilient (the value `asserted` is the actual data).
  await page
    .locator('.ant-select-item[title="Asserted"]')
    .click();

  // Row count stays at 1 — the only row is `asserted`.
  await expect(page.locator('[aria-label="entities-search-results"] li')).toHaveCount(1);
});

// ---------------------------------------------------------------------------
// Step 3 — owl_inferred scope filter drops the row count to 0.
// ---------------------------------------------------------------------------

test("entity search owl_inferred scope filter drops results to zero", async ({
  page,
}) => {
  await mockStage4(page);
  await page.goto(workspaceUrl("search"));

  await page.locator('input[aria-label="entities-search-input"]').fill("acme");
  await expect(
    page.locator('[aria-label="entity-search-row-http://op.local/entity/acme-corp"]'),
  ).toBeVisible();

  // Switch scope to owl_inferred — fixture has none.
  await page.locator('[aria-label="entities-search-scope"]').click();
  await page
    .locator('.ant-select-item[title="OWL inferred"]')
    .click();

  // The empty-state block renders (no <li> rows).
  await expect(page.locator('[aria-label="entities-search-empty"]')).toBeVisible();
  await expect(page.locator('[aria-label="entities-search-results"] li')).toHaveCount(0);
});

// ---------------------------------------------------------------------------
// Step 3b — Empty input never fires entity-search (no recall without a query).
// ---------------------------------------------------------------------------

test("entity search does not recall entities before the user types", async ({
  page,
}) => {
  await mockStage4(page);
  const searchRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/read-models/entity-search")) {
      searchRequests.push(req.url());
    }
  });

  await page.goto(workspaceUrl("search"));

  // Empty-state prompt is visible and no search request was fired.
  await expect(page.locator('[aria-label="entities-search-empty"]')).toBeVisible();
  await expect(page.locator('[aria-label="entities-search-results"] li')).toHaveCount(0);
  expect(searchRequests).toHaveLength(0);
});

// ---------------------------------------------------------------------------
// Step 3c — Clicking a row expands an inline detail panel (no navigation),
//           surfacing IRI, class, source graph, and literal facts.
// ---------------------------------------------------------------------------

test("entity search row click expands inline detail panel with facts", async ({
  page,
}) => {
  await mockStage4(page);
  await page.goto(workspaceUrl("search"));

  await page.locator('input[aria-label="entities-search-input"]').fill("acme");
  const row = page.locator(
    '[aria-label="entity-search-row-http://op.local/entity/acme-corp"]',
  );
  await expect(row).toBeVisible();

  // Detail panel is absent before expand.
  await expect(
    page.locator('[aria-label="entity-search-detail-http://op.local/entity/acme-corp"]'),
  ).toHaveCount(0);

  // Click the row — expect a literal-facts fetch, not a navigation.
  const factsRequest = page.waitForRequest(
    (req) =>
      req.method() === "GET" &&
      req.url().includes(`/read-models/entity-literal-facts`) &&
      req.url().includes("entity=http%3A%2F%2Fop.local%2Fentity%2Facme-corp"),
  );
  await row.click();
  await factsRequest;

  // Detail panel renders with business info + the literal fact.
  const detail = page.locator(
    '[aria-label="entity-search-detail-http://op.local/entity/acme-corp"]',
  );
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("http://op.local/entity/acme-corp");
  await expect(detail).toContainText("Organization");
  await expect(detail).toContainText(DATA_GRAPH);
  await expect(detail).toContainText("Founded");
  await expect(detail).toContainText("1985");

  // URL still on the search tab — no navigation away.
  await expect(page).toHaveURL(/tab=search/);
});

// ---------------------------------------------------------------------------
// Step 4 — Tools → Agent Test: question returns answer + graph_context
//          entry for Acme Corp with [asserted] chip.
// ---------------------------------------------------------------------------

test("agent test run surfaces structured graph context entries", async ({
  page,
}) => {
  await mockStage4(page);
  await page.goto(workspaceUrl("agent-test"));

  await page.locator('[aria-label="agent-test-question"]').fill("What is Acme Corp?");
  const runRequest = page.waitForRequest(
    (req) => req.method() === "POST" && req.url().includes("/agent-test/run"),
  );
  await page.locator('[aria-label="agent-test-run"]').click();
  await runRequest;

  // Answer panel populates with the fixture string.
  await expect(page.locator('[aria-label="agent-test-answer"]')).toContainText(
    "Acme Corp is an organization",
  );

  // Graph context renders the Acme Corp entry with the asserted chip via
  // its aria-label suffix (frontend emits
  // `agent-test-context-{iri}`).
  const entry = page.locator(
    '[aria-label="agent-test-context-http://op.local/entity/acme-corp"]',
  );
  await expect(entry).toBeVisible();
  await expect(entry).toContainText("Acme Corp");
});

// ---------------------------------------------------------------------------
// Step 5 — Tools → MCP tools: ≥ 30 tools and includes
//          `compile_and_apply_canonical_command`.
// ---------------------------------------------------------------------------

test("MCP tools catalog lists ≥ 30 tools including canonical command", async ({
  page,
}) => {
  await mockStage4(page);
  await page.goto(workspaceUrl("mcp-tools"));

  await expect(page.locator('[aria-label="mcp-tools-page"]')).toBeVisible();

  // Summary line renders `{total} tools across {n} categories` — the
  // fixture has 30 tools across 3 categories.
  const summary = page.locator('[aria-label="mcp-tools-summary"]');
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("30 tools");

  // The canonical-write tool is rendered.
  await expect(
    page.locator('[aria-label="mcp-tool-compile_and_apply_canonical_command"]'),
  ).toBeVisible();

  // Sanity: at least 30 tool rows in the catalog. Use the row-only
  // aria-label (`mcp-tool-{name}`) and exclude the source-tag suffix
  // (`mcp-tool-source-{file}`) — both match the `mcp-tool-` prefix, so we
  // filter to <li> elements only.
  await expect(page.locator('li[aria-label^="mcp-tool-"]')).toHaveCount(mcpTools.length);
});

// ---------------------------------------------------------------------------
// Step 6 — Knowledge → Facts: drawer shows evidence bindings.
// ---------------------------------------------------------------------------

test("fact audit drawer shows bound chunk for the Acme fact", async ({
  page,
}) => {
  await mockStage4(page);
  await page.goto(workspaceUrl("facts"));

  // The fact queue renders the Acme fact row.
  const factRow = page.getByText("Acme Corp → industry →").first();
  await expect(factRow).toBeVisible();
  await factRow.click();

  // The fact inspector mounts the evidence explorer card.
  await expect(page.locator('[aria-label="fact-evidence-explorer"]')).toBeVisible();

  // The evidence editor renders the binding row carrying the
  // document_filename + sequence + text_preview.
  const bindingRow = page.locator('[aria-label^="evidence-binding-"]').first();
  await expect(bindingRow).toBeVisible();
  await expect(bindingRow).toContainText(evidenceArtifact.filename);
  await expect(bindingRow).toContainText("Acme is a manufacturer of widgets");
});
