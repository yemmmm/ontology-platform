import { expect, test, type Page } from "@playwright/test";

// Stage 4 §11 — Playwright e2e for the Tools-stage surface.
//
// Covers the eight happy-path steps defined in plan Phase F1.2:
//   1. Tools → Search: query "acme" returns one row with [asserted] chip.
//   2. Asserted scope filter keeps row count unchanged.
//   3. OWL inferred scope filter drops row count to 0 (fixture has no inferred).
//   4. Tools → MCP tools: catalog shows ≥ 30 tools including
//      `compile_and_apply_canonical_command`.
//   5. Knowledge → Facts: fact drawer renders ordinary RDF terms
//      (document_filename + sequence + text_preview).
//   6. Governance → Graph Governance: OWL Consistency section renders
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
// Fixtures — ordinary fact-audit-queue (R4.0-012)
// ---------------------------------------------------------------------------

const factWithoutEvidence = {
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
  audit_status: "pending",
  stale: false,
  stale_reason: null,

};

const factAuditEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  source_signature: "sig-acme",
  projection_version: "1",
  model_name: "fact-audit-queue",
  include: "asserted",
  derived_state: {},
  warnings: [],
  items: [factWithoutEvidence],
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
    if(path === "/semantic/context:query") {
      const q=route.request().postDataJSON();
      body={query:{queries:[q.query]},result_status:q.assertion_types?.includes("derived")?"no_match":"matched",scope:{project_id:project.id},primary_matches:q.assertion_types?.includes("derived")?[]:entitySearchItems.map(r=>({...r,kind:"instance",ontology_id:ontology.id,data:{semantic_definition:{semantic_role:"object",business_meaning:r.comment}}})),related_context:[],matches_page:{},context_page:{},recall:{completeness:"complete"},warnings:[],truncated:false};
    }
    else if(path.startsWith("/semantic/resources/"))body={iri:entitySearchItems[0].iri,label:"Acme Corp",properties:{class_label:"Organization",Founded:"1985"},source_graph_iri:DATA_GRAPH};
    else if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if(path.endsWith("/workspace-context"))body={default_graph_set_id:GRAPH_SET_ID};
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
      body = mode === "empty" ? { ...factAuditEnvelope, items: [] } : factAuditEnvelope;
    } else if (
      path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/owl-consistency-summary`
    ) {
      body = owlConsistencyEnvelope;
    }

    // --- Stage 4 MCP catalog (spec §5.4) ---
    else if (path === "/mcp/tools") {
      body = mcpToolsEnvelope;
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

test("Context Query returns Acme Corp with its asserted business semantics", async ({page})=>{
  await mockStage4(page); await page.goto(workspaceUrl("search"));
  await expect(page.getByLabel("context-query-page")).toBeVisible();
  await page.getByLabel("查询表达式",{exact:true}).fill("acme");await page.getByRole("button",{name:"查询",exact:true}).click();
  await expect(page.getByRole("button",{name:"Acme Corp",exact:true})).toBeVisible();
  await expect(page.getByText("Acme is a manufacturer of widgets.",{exact:true})).toBeVisible();
});
test("Context Query explicitly uses default hybrid retrieval",async ({page})=>{
  await mockStage4(page);await page.goto(workspaceUrl("search"));
  const requested=page.waitForRequest(r=>r.url().endsWith("/semantic/context:query")&&r.method()==="POST");
  await page.getByLabel("查询表达式",{exact:true}).fill("acme");await page.getByRole("button",{name:"查询",exact:true}).click();
  expect((await requested).postDataJSON().search_mode).toBe("hybrid");
});
test("Context Query asserted filter retains fixture semantics",async ({page})=>{
  await mockStage4(page);await page.goto(workspaceUrl("search"));
  await page.getByLabel("查询表达式",{exact:true}).fill("acme");
  await page.getByLabel("陈述类型",{exact:true}).click();await page.locator('.ant-select-item-option[title="已断言"]').click();
  await page.getByRole("button",{name:"查询",exact:true}).click();
  await expect(page.getByRole("button",{name:"Acme Corp",exact:true})).toBeVisible();
});
test("Context Query OWL derived filter returns bounded no-match",async ({page})=>{
  await mockStage4(page);await page.goto(workspaceUrl("search"));
  await page.getByLabel("查询表达式",{exact:true}).fill("acme");
  await page.getByLabel("陈述类型",{exact:true}).click();await page.locator('.ant-select-item-option[title="OWL 派生"]').click();
  await page.getByRole("button",{name:"查询",exact:true}).click();
  await expect(page.getByRole("button",{name:"Acme Corp",exact:true})).toHaveCount(0);
  await expect(page.getByText("空结果或读完当前页不能证明业务知识不存在或已经完整。",{exact:false})).toBeVisible();
});
test("Context Query never recalls before an explicit query",async ({page})=>{
  await mockStage4(page);const calls:string[]=[];page.on("request",r=>{if(r.url().includes("context:query"))calls.push(r.url());});
  await page.goto(workspaceUrl("search"));await expect(page.getByText("输入查询取得受授权的语义上下文。")).toBeVisible();expect(calls).toHaveLength(0);
});
test("Context Query exact resource detail reads governed fields and facts",async ({page})=>{
  await mockStage4(page);await page.goto(workspaceUrl("search"));
  await page.getByLabel("查询表达式",{exact:true}).fill("acme");await page.getByRole("button",{name:"查询",exact:true}).click();
  const detailRequest=page.waitForRequest(r=>r.url().includes("/semantic/resources/"));
  await page.getByRole("button",{name:"Acme Corp",exact:true}).click();await detailRequest;
  const dialog=page.getByRole("dialog",{name:"精确资源详情"});await expect(dialog.getByText("Organization",{exact:true})).toBeVisible();await expect(dialog.getByText("Founded",{exact:true})).toBeVisible();await expect(dialog.getByText("1985",{exact:true})).toBeVisible();
  await expect(page).toHaveURL(/tab=search/);
});

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
// Step 6 — Facts retain inspect/edit controls without a trace collection task.
// ---------------------------------------------------------------------------

test("fact audit drawer reads without evidence parameters or requests", async ({ page }) => {
  const reads: URL[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) reads.push(new URL(request.url()));
  });
  await mockStage4(page);
  await page.goto(workspaceUrl("facts"));
  const factRow = page.getByText("Acme Corp → industry →").first();
  await expect(factRow).toBeVisible();
  await factRow.click();
  await expect(page.getByText("Fact inspector", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Edit", exact: true })).toBeVisible();
  await expect(page.locator('[aria-label="fact-evidence-explorer"]')).toHaveCount(0);
  await expect(page.getByText("Missing evidence only", { exact: true })).toHaveCount(0);
  expect(reads.some((url) => /evidence|lineage|provenance/.test(url.pathname))).toBe(false);
  const factReads = reads.filter((url) => url.pathname.includes("fact-audit-queue"));
  expect(factReads.length).toBeGreaterThan(0);
  expect(factReads.every((url) => url.searchParams.get("field_set") !== "evidence")).toBe(true);
});
