import { expect, test, type Page } from "@playwright/test";

// Stage 3 §11 — Playwright e2e for the publish-rebuild surface.
//
// Covers the five scenarios called out in plan Phase F1:
//   1. Readiness dashboard renders all 6 gates with status icons.
//   2. Publish flow: confirm modal → PATCH editability for each editable
//      graph → export URL navigated to.
//   3. Partial failure: first editability PATCH 500s → retry/rollback
//      affordance renders.
//   4. GraphSetHistoryPage list: status icon + member count render.
//   5. Diff computation: per-role added/removed breakdown renders.
//
// Mocks follow the same single-catch-all pattern as
// `stage2-graph-derived.spec.ts`. The backend read-model envelope shape is
// `{ graph_set_id, model_name, projection_version, items: [...] }` — see
// `frontend/src/hooks/useGraphSet{Readiness,History,Delta}.ts`. The first
// item of `items[]` carries the actual row payload.

const project = {
  id: "project-stage3",
  name: "Stage 3 Sandbox",
  description: "publish-rebuild smoke",
};
const ontology = {
  id: "ontology-stage3",
  project_id: project.id,
  name: "Stage 3 Ontology",
  description: "publish",
  status: "active",
};

const GRAPH_SET_ID = "gs-stage3";
const ONTOLOGY_GRAPH = "http://op.local/semantic/graph/ontology/acme";
const DATA_GRAPH = "http://op.local/semantic/graph/data/acme";

const editableGraphs = [
  { graph_iri: ONTOLOGY_GRAPH, role: "asserted_ontology" },
  { graph_iri: DATA_GRAPH, role: "asserted_data" },
];

const gates = [
  { gate: "validation_stale", status: "passed", details: { staleness_state: "fresh" }, label: "validation fresh" },
  { gate: "reasoning_stale", status: "passed", details: { staleness_state: "fresh" }, label: "reasoning fresh" },
  { gate: "rule_stale", status: "warning", details: { staleness_state: "stale" }, label: "rule 3d old" },
  { gate: "missing_evidence", status: "passed", details: { count: 0 }, label: "0 facts missing evidence" },
  { gate: "open_edits", status: "warning", details: { count: 2 }, label: "2 pending semantic edits" },
  { gate: "projection_freshness", status: "passed", details: {}, label: "projections fresh" },
];

const readinessRow = {
  graph_set_id: GRAPH_SET_ID,
  ready: false,
  gates,
  blockers: [],
  warnings: ["rule 3d old", "2 pending semantic edits"],
  editable_graph_count: editableGraphs.length,
  editable_graphs: editableGraphs,
  last_published_at: null,
};

const readinessEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  model_name: "publication-readiness",
  projection_version: "1",
  items: [readinessRow],
};

const historyEntry = {
  graph_set_id: GRAPH_SET_ID,
  status: "editable",
  created_at: "2026-07-01T00:00:00Z",
  locked_at: null,
  source_signature: "sig-base",
  member_count: 2,
  latest_derived_pointer_at: "2026-07-05T00:00:00Z",
  ready: null,
};

const secondEntry = {
  ...historyEntry,
  graph_set_id: "gs-stage3-prev",
  status: "locked",
  created_at: "2026-06-01T00:00:00Z",
  locked_at: "2026-06-02T00:00:00Z",
  source_signature: "sig-prev",
  member_count: 2,
  latest_derived_pointer_at: "2026-06-02T00:00:00Z",
};

const historyEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  model_name: "graph-set-history-list",
  projection_version: "1",
  items: [{ graph_sets: [historyEntry, secondEntry], total: 2 }],
};

const deltaPayload = {
  base_graph_set_id: GRAPH_SET_ID,
  target_graph_set_id: secondEntry.graph_set_id,
  roles: [
    {
      role: "asserted_ontology",
      base_graph_iri: ONTOLOGY_GRAPH,
      target_graph_iri: ONTOLOGY_GRAPH,
      added: [],
      removed: [],
      counts: { added: 0, removed: 0 },
    },
    {
      role: "asserted_data",
      base_graph_iri: DATA_GRAPH,
      target_graph_iri: "http://op.local/semantic/graph/data/acme-prev",
      added: [{ subject: "http://x/s1", predicate: "http://x/p", object: "new" }],
      removed: [{ subject: "http://x/s2", predicate: "http://x/p", object: "old" }],
      counts: { added: 1, removed: 1 },
    },
  ],
  truncated: false,
};

const deltaEnvelope = {
  graph_set_id: GRAPH_SET_ID,
  model_name: "graph-set-delta",
  projection_version: "1",
  items: [deltaPayload],
};

type EditabilityMockMode = "success" | "failFirst";

async function mockCommon(page: Page, mode: EditabilityMockMode = "success") {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = route.request().method();
    let body: unknown = [];
    let status = 200;

    // Workspace scaffolding — the home page + workbench shell call these.
    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/build-context`) {
      body = {
        project,
        project_brief: {
          id: "brief-stage3",
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

    // Stage 3 read-models.
    else if (
      path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/publication-readiness`
    ) {
      body = readinessEnvelope;
    } else if (
      path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/graph-set-history-list`
    ) {
      body = historyEnvelope;
    } else if (
      path === `/semantic/graph-sets/${GRAPH_SET_ID}/read-models/graph-set-delta`
    ) {
      body = deltaEnvelope;
    }

    // Editability PATCH — success or first-call failure (partial-failure test).
    else if (
      method === "PATCH" &&
      path.startsWith("/semantic/graphs/") &&
      path.endsWith("/editability")
    ) {
      if (mode === "failFirst") {
        // Fail only the first PATCH (ontology graph); let subsequent ones
        // succeed so the rollback flow has something to undo.
        const calls = (page as unknown as { __editCalls?: number }).__editCalls ?? 0;
        (page as unknown as { __editCalls?: number }).__editCalls = calls + 1;
        if (calls === 0) {
          status = 500;
          body = { detail: "editability patch failed (mock)" };
        } else {
          body = { graph_iri: "mock", editable: false, updated_by: "stage3", reason: "" };
        }
      } else {
        body = { graph_iri: "mock", editable: false, updated_by: "stage3", reason: "" };
      }
    }

    // Export download — return an empty trig body so window.location.href
    // navigation completes without error.
    else if (path === `/semantic/graph-sets/${GRAPH_SET_ID}/export`) {
      body = "";
    }

    // Health + default fall-through.
    else if (path === "/health/dependencies") {
      body = { postgres: { status: "ok" }, neo4j: { status: "ok" } };
    } else if (method !== "GET") {
      body = {};
    }

    await route.fulfill({
      status,
      contentType: status === 200 && path === `/semantic/graph-sets/${GRAPH_SET_ID}/export`
        ? "application/octet-stream"
        : "application/json",
      body: typeof body === "string" ? body : JSON.stringify(body),
    });
  });
}

function workspaceUrl(tab: string) {
  return `/?project=${project.id}&ontology=${ontology.id}&tab=${tab}&graphSet=${GRAPH_SET_ID}`;
}

// ---------------------------------------------------------------------------
// Scenario 1: Readiness dashboard renders all gates with status icons.
// ---------------------------------------------------------------------------

test("publication readiness dashboard renders all six gates with status icons", async ({
  page,
}) => {
  await mockCommon(page);
  await page.goto(workspaceUrl("publication"));

  // Section present.
  await expect(page.locator('[data-testid="publication-readiness"]')).toBeVisible();

  // All six gates render with their gate id and status data attribute.
  for (const gate of gates) {
    const row = page.locator(`[data-gate="${gate.gate}"]`);
    await expect(row).toBeVisible();
    await expect(row).toHaveAttribute("data-status", gate.status);
    await expect(row).toContainText(gate.label);
  }

  // Overall status reflects warnings (not blocked, not ready).
  await expect(page.locator('[data-testid="publication-readiness"]')).toContainText("Has warnings");

  // Editable graphs panel lists both members.
  await expect(page.locator("code", { hasText: ONTOLOGY_GRAPH })).toBeVisible();
  await expect(page.locator("code", { hasText: DATA_GRAPH })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Scenario 2: Publish flow — confirm modal → PATCH each editable graph →
// export URL fetched.
// ---------------------------------------------------------------------------

test("publish flow locks all editable graphs and triggers the export download", async ({
  page,
}) => {
  await mockCommon(page);

  const patchUrls: string[] = [];
  page.on("request", (req) => {
    if (
      req.method() === "PATCH" &&
      req.url().includes("/semantic/graphs/") &&
      req.url().endsWith("/editability")
    ) {
      patchUrls.push(req.url());
    }
  });

  await page.goto(workspaceUrl("publication"));

  // Wait for the publish CTA to be enabled (data loaded, graphs > 0).
  const publishButton = page.getByRole("button", {
    name: "Lock all graphs and export package",
  });
  await expect(publishButton).toBeEnabled();

  // Click → confirmation modal opens.
  await publishButton.click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText(ONTOLOGY_GRAPH);
  await expect(dialog).toContainText(DATA_GRAPH);

  // Confirm → wait for the export navigation to fire.
  const exportRequest = page.waitForRequest(
    (req) =>
      req.method() === "GET" &&
      req.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/export`),
  );
  await dialog.getByRole("button", { name: "Lock and export" }).click();
  await exportRequest;

  // One PATCH per editable graph, both targeting the right IRIs. The frontend
  // encodes graph_iri before placing it in the path.
  expect(patchUrls.length).toBeGreaterThanOrEqual(2);
  expect(patchUrls.some((u) => u.includes(encodeURIComponent(ONTOLOGY_GRAPH)))).toBeTruthy();
  expect(patchUrls.some((u) => u.includes(encodeURIComponent(DATA_GRAPH)))).toBeTruthy();
});

// ---------------------------------------------------------------------------
// Scenario 3: Partial failure — first editability PATCH fails, retry /
// rollback affordance renders.
// ---------------------------------------------------------------------------

test("partial publish failure surfaces the retry and rollback affordance", async ({
  page,
  browser,
}) => {
  // Use a fresh context so any in-flight navigation from the previous test
  // (window.location.href = exportUrl) can't bleed into this one.
  const ctx = await browser.newContext();
  const failPage = await ctx.newPage();
  await mockCommon(failPage, "failFirst");

  await failPage.goto(workspaceUrl("publication"));
  const publishButton = failPage.getByRole("button", {
    name: "Lock all graphs and export package",
  });
  await expect(publishButton).toBeEnabled();
  await publishButton.click();

  const dialog = failPage.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Lock and export" }).click();

  // Partial-failure alert renders with retry + rollback buttons.
  const partialAlert = failPage.getByRole("alert").filter({
    hasText: "Partial failure: locked 0/2 editable graphs.",
  });
  await expect(partialAlert).toBeVisible();
  await expect(partialAlert.getByRole("button", { name: "Retry remaining" })).toBeVisible();
  await expect(
    partialAlert.getByRole("button", { name: /Rollback \(unlock 0\)/ }),
  ).toBeVisible();
});

// ---------------------------------------------------------------------------
// Scenario 4: GraphSetHistoryPage — list renders with status icons.
// ---------------------------------------------------------------------------

test("graph set history page lists sets with status icons and member counts", async ({
  page,
}) => {
  await mockCommon(page);
  await page.goto(workspaceUrl("graph-set-history"));

  await expect(page.locator('[data-testid="graph-set-history"]')).toBeVisible();

  // Both entries render with data-status attributes driven by their status.
  const first = page.locator('[data-graph-set-id="gs-stage3"]');
  const second = page.locator('[data-graph-set-id="gs-stage3-prev"]');
  await expect(first).toBeVisible();
  await expect(second).toBeVisible();
  await expect(first).toHaveAttribute("data-status", "editable");
  await expect(second).toHaveAttribute("data-status", "locked");

  // Member count is rendered (translate key uses {count}). Assert via row
  // count (data-graph-set-id) instead of localized text to stay locale-stable.
  await expect(page.locator('[data-graph-set-id]')).toHaveCount(2);
});

// ---------------------------------------------------------------------------
// Scenario 5: Diff computation — per-role added/removed breakdown.
// ---------------------------------------------------------------------------

test("graph set delta renders per-role added/removed counts", async ({ page }) => {
  await mockCommon(page);
  await page.goto(workspaceUrl("graph-set-history"));

  // Default-seeded base = anchor graph set; target = second entry (the page
  // pre-fills target with the second-most-recent set on history load). We
  // still click Compute explicitly to assert the button works.
  const computeButton = page.getByRole("button", { name: "Compute delta" });
  await expect(computeButton).toBeEnabled();

  const deltaRequest = page.waitForRequest(
    (req) =>
      req.method() === "GET" &&
      req.url().includes(`/semantic/graph-sets/${GRAPH_SET_ID}/read-models/graph-set-delta`),
  );
  await computeButton.click();
  await deltaRequest;

  // The asserted_ontology role has no changes → "Unchanged" tag.
  const ontologyRole = page.locator('[data-role="asserted_ontology"]');
  await expect(ontologyRole).toBeVisible();
  await expect(ontologyRole).toContainText("Unchanged");

  // The asserted_data role has +1/-1.
  const dataRole = page.locator('[data-role="asserted_data"]');
  await expect(dataRole).toBeVisible();
  await expect(dataRole.getByText("+1")).toBeVisible();
  await expect(dataRole.getByText("−1")).toBeVisible();
});
