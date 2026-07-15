import { expect, test, type Page, type Route } from "@playwright/test";

const project = { id: "project-build-context", name: "Supply Chain Project", description: "R-003 debug" };
const ontology = {
  id: "ontology-supply",
  project_id: project.id,
  name: "Supply Ontology",
  description: "",
  status: "active",
};

const checkpoint = {
  id: "checkpoint-active",
  build_session_id: "session-active-001",
  client_checkpoint_id: "client-checkpoint-active",
  sequence: 2,
  ontology_id: ontology.id,
  phase: "handoff",
  current_step: "Prepare modeling handoff",
  next_step: "Verify platform batches",
  summary: "Agent believes modeling is ready",
  blockers: ["Waiting for source confirmation"],
  failure: { code: "source_missing", message: "Source excerpt is unavailable" },
  related_batch_id: null,
  reported_by: "test-agent",
  created_at: "2026-07-15T05:10:00Z",
};

const activeSession = {
  id: "session-active-001",
  project_id: project.id,
  client_session_id: "client-session-active",
  previous_session_id: null,
  status: "active",
  revision: 2,
  created_by: "test-agent",
  completion_summary: null,
  unresolved_items: [],
  cancel_reason: null,
  last_activity_at: "2026-07-15T05:10:00Z",
  completed_at: null,
  cancelled_at: null,
  created_at: "2026-07-15T05:00:00Z",
  updated_at: "2026-07-15T05:10:00Z",
  latest_checkpoint: checkpoint,
};

function terminalSession(id: string, unresolved: string[] = []) {
  return {
    ...activeSession,
    id,
    client_session_id: `client-${id}`,
    status: "completed",
    revision: 3,
    completion_summary: "Completed scoped review",
    unresolved_items: unresolved,
    completed_at: "2026-07-15T05:20:00Z",
    latest_checkpoint: { ...checkpoint, id: `checkpoint-${id}`, build_session_id: id, phase: "verification", blockers: [], failure: null },
  };
}

function contextResponse(
  recentSessions: ReturnType<typeof terminalSession>[] = [terminalSession("session-recent-001", ["Review naming"])],
  nextCursor: number | null = 10,
  modelingBatches: Array<Record<string, unknown>> = [],
) {
  return {
    project,
    generated_at: "2026-07-15T05:30:00Z",
    platform_state: {
      project_brief: {
        id: "brief-001",
        project_id: project.id,
        fields: { domain_name: "Supply chain" },
        field_states: { domain_name: "confirmed" },
        field_sources: {},
        missing_fields: ["quality_constraints"],
        clarification_items: [],
        completeness: 0.75,
      },
      competency_question_counts: { approved: 2, draft: 1 },
      ontologies: [{
        id: ontology.id,
        name: ontology.name,
        status: ontology.status,
        workspace: {
          state: "incomplete",
          workspace_version: "opaque-version-42",
          editable: false,
          issues: ["semantic_workspace_incomplete"],
        },
      }],
      evidence_reference_count: 4,
      modeling_batches: modelingBatches,
    },
    agent_state: {
      active_sessions: [activeSession],
      recent_sessions: recentSessions,
      recent_sessions_next_cursor: nextCursor,
      unresolved_items: recentSessions.flatMap((session) => session.unresolved_items),
    },
  };
}

const recoveringBatch = {
  id: "batch-recovering-001",
  batch_id: "batch-recovering-001",
  client_batch_id: "supplier-model-v1",
  build_session_id: activeSession.id,
  ontology_id: ontology.id,
  batch_status: "recovering",
  item_count: 2,
  latest_attempt: {
    attempt_id: "attempt-apply-001",
    mode: "apply_partial",
    attempt_status: "recovering",
    finding_count: 2,
    recovery_state: "recovering",
  },
  created_at: "2026-07-15T05:12:00Z",
};

const appliedBatch = {
  ...recoveringBatch,
  id: "batch-applied-001",
  batch_id: "batch-applied-001",
  client_batch_id: "warehouse-model-v1",
  batch_status: "applied",
  latest_attempt: {
    attempt_id: "attempt-applied-002",
    mode: "apply_atomic",
    attempt_status: "applied",
    finding_count: 0,
    recovery_state: "not_required",
  },
  created_at: "2026-07-15T05:11:00Z",
};

function modelingContextResponse(options: { empty?: boolean } = {}) {
  return {
    project,
    ontology,
    generated_at: "2026-07-15T05:31:00Z",
    workspace: {
      workspace_version: "opaque-modeling-version-43",
      state: "ready",
      editable: true,
      issues: [],
    },
    resource_counts: options.empty ? {} : {
      classes: 7,
      entities: 18,
      facts: 29,
      rule_definitions: 2,
    },
    derived_state: {
      stale_count: options.empty ? 0 : 2,
      warning: options.empty ? null : "Rule and projection results await rebuild",
    },
    lease: {
      active: !options.empty,
      fenced: !options.empty,
      state: options.empty ? null : "recovering",
      lease_token: "modeling-context-lease-token",
    },
    recovering: {
      active: !options.empty,
      attempt_id: options.empty ? null : "attempt-apply-001",
    },
    recent_batches: options.empty ? [] : [recoveringBatch],
    recent_batches_next_cursor: options.empty ? null : "batch-cursor-2",
    batch_history: `/api/ontologies/${ontology.id}/modeling-batches`,
    query_entries: {
      classes: { url: `/ontologies/${ontology.id}/semantic-read-models/classes` },
      private: {
        api_key: "query-entry-api-key",
        apiKey: "query-entry-camel-api-key",
        target_graph_iri: "http://internal.example/modeling-context/query-target",
        graphSetId: "query-entry-graph-set",
      },
    },
  };
}

const modelingBatchDetail = {
  id: recoveringBatch.id,
  batch_id: recoveringBatch.id,
  client_batch_id: recoveringBatch.client_batch_id,
  build_session_id: activeSession.id,
  ontology_id: ontology.id,
  status: "recovering",
  batch_status: "recovering",
  items: [{
    item_id: "item-customer-class",
    client_item_id: "customer-class",
    ordinal: 0,
    command_kind: "create_class",
    payload: { name: "Customer" },
    depends_on: [],
    resource_outputs: { resource_id: "customer-class-resource" },
  }, {
    item_id: "item-invalid-shape",
    client_item_id: "invalid-shape",
    ordinal: 1,
    command_kind: "create_shape",
    payload: { name: "Invalid Shape" },
    depends_on: ["customer-class"],
    resource_outputs: { resource_id: "invalid-shape-resource" },
  }],
  findings: [{
    code: "recovery_requires_intervention",
    severity: "warning",
    message: "Recovery has not converged yet",
    scope: "batch",
  }],
  attempts: [{
    attempt_id: "attempt-dry-run-001",
    mode: "dry_run",
    attempt_status: "validated",
    items: [{
      item_id: "item-customer-class",
      client_item_id: "customer-class",
      command_kind: "create_class",
      status: "validated",
      finding_codes: ["missing_evidence"],
    }],
    findings: [{
      code: "missing_evidence",
      severity: "warning",
      message: "No evidence was associated",
      scope: "item",
      client_item_id: "customer-class",
    }],
    recovery: { state: "not_required", safe_to_retry: true },
    completed_at: "2026-07-15T05:12:30Z",
  }, {
    attempt_id: "attempt-apply-001",
    mode: "apply_partial",
    attempt_status: "recovering",
    items: [{
      item_id: "item-customer-class",
      client_item_id: "customer-class",
      command_kind: "create_class",
      status: "applied",
      finding_codes: [],
    }, {
      item_id: "item-invalid-shape",
      client_item_id: "invalid-shape",
      command_kind: "create_shape",
      status: "blocked",
      finding_codes: ["shacl_violation"],
    }],
    findings: [{
      code: "shacl_violation",
      severity: "error",
      message: "Shape constraint could not be satisfied",
      scope: "item",
      client_item_id: "invalid-shape",
      details: {
        credential: "finding-private-credential",
        graph_iri: "http://internal.example/finding/graph",
      },
    }],
    recovery: {
      state: "recovering",
      safe_to_retry: true,
      history: [{
        message: "Awaiting deterministic convergence",
        access_token: "recovery-access-token",
        affected_graph_iris: ["http://internal.example/recovery/affected"],
      }],
    },
    created_at: "2026-07-15T05:13:00Z",
  }],
  recovery: {
    state: "recovering",
    private_secret: "batch-recovery-secret",
  },
  target: {
    graph_set_id: "batch-detail-graph-set",
    graphs: [{ role: "asserted_ontology", graph_iri: "http://internal.example/detail/graph" }],
  },
  created_at: "2026-07-15T05:12:00Z",
  completed_at: null,
};

async function setup(page: Page, options: {
  empty?: boolean;
  contextError?: boolean;
  sensitiveBatches?: boolean;
  modelingContext?: "success" | "empty" | "error";
  slowModelingContext?: boolean;
  batchPageError?: boolean;
  batchDetailError?: boolean;
} = {}) {
  const requests: string[] = [];
  await page.addInitScript(() => window.localStorage.setItem("ontology-platform-ui-lang", "en"));
  await page.route("**/api/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    requests.push(`${route.request().method()} ${path}${url.search}`);
    if (path === "/projects") return route.fulfill({ json: [project] });
    if (path === `/projects/${project.id}/ontologies`) return route.fulfill({ json: options.empty ? [] : [ontology] });
    if (path === `/ontologies/${ontology.id}/modeling-context`) {
      if (options.slowModelingContext) await new Promise((resolve) => setTimeout(resolve, 120));
      if (options.modelingContext === "error") {
        return route.fulfill({ status: 503, json: { detail: "modeling context offline" } });
      }
      return route.fulfill({ json: modelingContextResponse({ empty: options.modelingContext === "empty" }) });
    }
    if (path === `/ontologies/${ontology.id}/modeling-batches`) {
      if (options.batchPageError) {
        return route.fulfill({ status: 503, json: { detail: "batch history offline" } });
      }
      return route.fulfill({ json: { items: [appliedBatch], next_cursor: null } });
    }
    if (path === `/modeling-batches/${recoveringBatch.id}`) {
      if (options.batchDetailError) {
        return route.fulfill({ status: 503, json: { detail: "batch detail offline" } });
      }
      return route.fulfill({ json: modelingBatchDetail });
    }
    if (path === `/projects/${project.id}/build-context`) {
      if (options.contextError) return route.fulfill({ status: 503, json: { detail: "build context offline" } });
      if (options.empty) {
        const empty = contextResponse([], null);
        empty.platform_state.ontologies = [];
        empty.platform_state.project_brief.missing_fields = [];
        empty.platform_state.competency_question_counts = {};
        empty.platform_state.evidence_reference_count = 0;
        empty.agent_state.active_sessions = [];
        return route.fulfill({ json: empty });
      }
      const cursor = url.searchParams.get("recent_session_cursor");
      const platformBatches = options.sensitiveBatches ? [{
        id: "platform-batch-public-001",
        ontology_id: ontology.id,
        status: "validated",
        result: {
          message: "Platform batch public result",
          target_graph_iri: "http://internal.example/platform/result-target",
          graph_set_id: "internal-platform-result-set",
          lease_token: "platform-result-token",
        },
        source_graph_iri: "http://internal.example/platform/source-graph",
        target_graph_iri: "http://internal.example/platform/target-graph",
        affected_graph_iris: ["http://internal.example/platform/affected-graph"],
        default_graph_set_id: "internal-platform-graph-set",
        nested: { graphSetId: "internal-nested-graph-set", leaseToken: "nested-platform-token" },
      }] : [];
      return route.fulfill({
        json: cursor === "10"
          ? contextResponse([terminalSession("session-recent-002")], null, platformBatches)
          : contextResponse(undefined, 10, platformBatches),
      });
    }
    if (path === `/build-sessions/${activeSession.id}`) {
      return route.fulfill({ json: {
        session: activeSession,
        latest_checkpoint: checkpoint,
        checkpoints: [checkpoint, { ...checkpoint, id: "checkpoint-1", sequence: 1, phase: "modeling", current_step: "Draft classes" }],
        checkpoints_next_cursor: null,
        involved_ontology_ids: [ontology.id],
        leases: [{
          ontology_id: ontology.id,
          build_session_id: activeSession.id,
          lease_revision: 1,
          state: "active",
          acquired_at: "2026-07-15T05:00:00Z",
          renewed_at: null,
          expires_at: "2026-07-15T06:00:00Z",
          released_at: null,
          lease_token: "lease-token-must-never-render",
        }],
        modeling_batches: [{
          id: "batch-safe-001",
          ontology_id: ontology.id,
          status: "accepted",
          created_at: "2026-07-15T05:08:00Z",
          error: {
            message: "Session batch public warning",
            affected_graph_iris: ["http://internal.example/session/error-affected"],
            default_graph_set_id: "internal-session-error-set",
            lease_token: "session-error-token",
          },
          graph_iri: "http://internal.example/graph/must-not-render",
          source_graph_iri: "http://internal.example/session/source-graph",
          target_graph_iri: "http://internal.example/session/target-graph",
          affected_graph_iris: ["http://internal.example/session/affected-graph"],
          default_graph_set_id: "internal-session-graph-set",
          nested: { graphSetId: "internal-session-nested-set", leaseToken: "nested-session-token" },
        }],
        evidence: {
          references: [{
            id: "evidence-reference-001",
            document_name: "Supplier policy.pdf",
            excerpt: "Approved suppliers require source evidence.",
          }],
          next_cursor: "evidence-cursor-2",
        },
        recent_activity: [{
          type: "checkpoint_saved",
          at: checkpoint.created_at,
          checkpoint_id: checkpoint.id,
          ontology_id: ontology.id,
          internal: { source_graph_iri: "http://internal.example/activity/source", lease_token: "activity-token" },
        }],
      } });
    }
    return route.fulfill({ json: [] });
  });
  return requests;
}

function workspaceUrl(tab: string, includeOntology = true) {
  const ontologyQuery = includeOntology ? `&ontology=${ontology.id}` : "";
  return `/?project=${project.id}${ontologyQuery}&tab=${tab}`;
}

test("Debug tool opens Build Context and keeps platform facts separate from Agent reports", async ({ page }) => {
  const requests = await setup(page);
  await page.goto(workspaceUrl("graph-governance"));

  await page.locator(".debugToolCard").filter({ hasText: "Build Context" }).click();
  await expect(page).toHaveURL(/tab=build-context/);
  await expect(page.getByRole("heading", { name: project.name })).toBeVisible();
  await expect(page.locator('[aria-label="platform-state"]')).toContainText("Platform State");
  await expect(page.locator('[aria-label="platform-state"]')).toContainText("75%");
  await expect(page.locator('[aria-label="platform-state"]')).toContainText("No modeling batches observed");
  await expect(page.locator('[aria-label="agent-state"]')).toContainText("Prepare modeling handoff");
  await expect(page.getByText("Checkpoint reports a failure")).toBeVisible();
  await expect(page.getByText("Ontology workspace needs attention")).toBeVisible();

  expect(requests.some((item) => item.startsWith("POST "))).toBe(false);
  expect(requests.some((item) => item.includes("ontology-leases"))).toBe(false);
});

test("Build Context paginates recent sessions and loads Session detail on demand", async ({ page }) => {
  const requests = await setup(page, { sensitiveBatches: true });
  await page.goto(workspaceUrl("build-context"));
  await expect(page.locator(".sessionItem").filter({ hasText: "Completed scoped review" })).toHaveCount(1);

  await page.getByRole("button", { name: "Load more sessions" }).click();
  await expect(page.locator(".sessionItem").filter({ hasText: "Completed scoped review" })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Load more sessions" })).toHaveCount(0);

  await page.getByRole("button", { name: /Prepare modeling handoff/ }).first().click();
  await expect(page.getByText("Checkpoint history")).toBeVisible();
  await expect(page.getByText("Draft classes", { exact: true })).toBeVisible();
  await expect(page.getByText("Involved ontologies")).toBeVisible();
  await expect(page.getByText(ontology.id, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Lease summaries")).toBeVisible();
  await expect(page.getByText("Lease revision")).toBeVisible();
  await expect(page.locator(".sessionDetailSection").filter({ hasText: "Modeling batch summaries" })).toContainText("accepted");
  await expect(page.locator(".sessionDetailSection").filter({ hasText: "Modeling batch summaries" })).toContainText("Session batch public warning");
  await expect(page.locator('[aria-label="platform-state"]')).toContainText("platform-batch-public-001");
  await expect(page.locator('[aria-label="platform-state"]')).toContainText("validated");
  await expect(page.locator('[aria-label="platform-state"]')).toContainText("Platform batch public result");
  const evidenceSection = page.locator(".sessionDetailSection").filter({ hasText: "Evidence references" });
  await expect(evidenceSection).toContainText("Supplier policy.pdf");
  await expect(evidenceSection).toContainText("evidence-cursor-2");
  await expect(page.getByText("checkpoint saved", { exact: true })).toBeVisible();
  await expect(page.getByText(`Focus ontology: ${ontology.id}`, { exact: false }).first()).toBeVisible();
  await expect(page.locator("body")).not.toContainText("lease-token-must-never-render");
  await expect(page.locator("body")).not.toContainText("http://internal.example/graph/must-not-render");
  for (const sensitiveValue of [
    "http://internal.example/platform/source-graph",
    "http://internal.example/platform/target-graph",
    "http://internal.example/platform/affected-graph",
    "internal-platform-graph-set",
    "internal-nested-graph-set",
    "nested-platform-token",
    "http://internal.example/platform/result-target",
    "internal-platform-result-set",
    "platform-result-token",
    "http://internal.example/session/source-graph",
    "http://internal.example/session/target-graph",
    "http://internal.example/session/affected-graph",
    "internal-session-graph-set",
    "internal-session-nested-set",
    "nested-session-token",
    "http://internal.example/session/error-affected",
    "internal-session-error-set",
    "session-error-token",
    "http://internal.example/activity/source",
    "activity-token",
  ]) {
    await expect(page.locator("body")).not.toContainText(sensitiveValue);
  }

  expect(requests).toContain(`GET /build-sessions/${activeSession.id}`);
  expect(requests.some((item) => item.includes("recent_session_cursor=10"))).toBe(true);
  expect(requests.every((item) => item.startsWith("GET "))).toBe(true);
});

test("project-level Build Context works without an ontology and renders empty state", async ({ page }) => {
  await setup(page, { empty: true });
  await page.goto(workspaceUrl("build-context", false));

  await expect(page.getByRole("heading", { name: project.name })).toBeVisible();
  await expect(page.getByText("No ontologies in this project")).toBeVisible();
  await expect(page.getByText("No active build sessions")).toBeVisible();
  await expect(page.getByText("No completed or cancelled sessions")).toBeVisible();
});

test("Build Context exposes a retryable request error", async ({ page }) => {
  await setup(page, { contextError: true });
  await page.goto(workspaceUrl("build-context", false));

  await expect(page.getByText("Build Context could not be loaded")).toBeVisible();
  await expect(page.getByText(/503/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("Workspace expands an authoritative Modeling Context and inspects immutable Batch diagnostics", async ({ page }) => {
  const requests = await setup(page, { modelingContext: "success", slowModelingContext: true });
  await page.goto(workspaceUrl("build-context"));

  const workspace = page.locator(".workspaceStateItem").filter({ hasText: ontology.name });
  await workspace.getByRole("button", { name: /Inspect Modeling Context/ }).click();
  await expect(workspace.getByText("Loading Modeling Context")).toBeVisible();
  await expect(workspace.getByText("Authoritative Modeling Context")).toBeVisible();
  await expect(workspace).toContainText("opaque-modeling-version-43");
  await expect(workspace).toContainText("classes");
  await expect(workspace).toContainText("7");
  await expect(workspace.getByText("Derived models are stale")).toBeVisible();
  await expect(workspace.getByText("Write fenced")).toBeVisible();
  await expect(workspace.getByText("Recovery is in progress").first()).toBeVisible();

  await workspace.getByRole("button", { name: /supplier-model-v1/ }).click();
  const detail = workspace.locator('[aria-label="Modeling Batch Detail"]');
  await expect(detail.getByText("Immutable batch audit")).toBeVisible();
  await expect(detail).toContainText("dry_run");
  await expect(detail).toContainText("apply_partial");
  await expect(detail).toContainText("customer-class");
  await expect(detail).toContainText("invalid-shape");
  await expect(detail).toContainText("missing_evidence");
  await expect(detail).toContainText("shacl_violation");
  await expect(detail).toContainText("recovery_requires_intervention");

  for (const sensitiveValue of [
    "modeling-context-lease-token",
    "query-entry-api-key",
    "query-entry-camel-api-key",
    "http://internal.example/modeling-context/query-target",
    "query-entry-graph-set",
    "finding-private-credential",
    "http://internal.example/finding/graph",
    "recovery-access-token",
    "http://internal.example/recovery/affected",
    "batch-recovery-secret",
    "batch-detail-graph-set",
    "http://internal.example/detail/graph",
  ]) {
    await expect(page.locator("body")).not.toContainText(sensitiveValue);
  }

  await expect(page.getByRole("button", { name: /^(Apply|Delete|Edit Batch|Retry Batch)$/i })).toHaveCount(0);
  expect(requests).toContain(`GET /ontologies/${ontology.id}/modeling-context`);
  expect(requests).toContain(`GET /modeling-batches/${recoveringBatch.id}`);
  expect(requests.every((item) => item.startsWith("GET "))).toBe(true);
});

test("Modeling Context paginates Batch history without duplicates", async ({ page }) => {
  const requests = await setup(page, { modelingContext: "success" });
  await page.goto(workspaceUrl("build-context"));
  const workspace = page.locator(".workspaceStateItem").filter({ hasText: ontology.name });
  await workspace.getByRole("button", { name: /Inspect Modeling Context/ }).click();

  await workspace.getByRole("button", { name: "Load more Modeling Batches" }).click();
  await expect(workspace.getByRole("button", { name: /supplier-model-v1/ })).toHaveCount(1);
  await expect(workspace.getByRole("button", { name: /warehouse-model-v1/ })).toHaveCount(1);
  await expect(workspace.getByRole("button", { name: "Load more Modeling Batches" })).toHaveCount(0);
  expect(requests.some((item) => item.includes("cursor=batch-cursor-2"))).toBe(true);
  expect(requests.every((item) => item.startsWith("GET "))).toBe(true);
});

test("Modeling Context has explicit empty and retryable error states", async ({ page }) => {
  await setup(page, { modelingContext: "empty" });
  await page.goto(workspaceUrl("build-context"));
  const workspace = page.locator(".workspaceStateItem").filter({ hasText: ontology.name });
  await workspace.getByRole("button", { name: /Inspect Modeling Context/ }).click();
  await expect(workspace.getByText("No canonical resources observed")).toBeVisible();
  await expect(workspace.getByText("No recent Modeling Batches")).toBeVisible();

  const errorPage = await page.context().newPage();
  await setup(errorPage, { modelingContext: "error" });
  await errorPage.goto(workspaceUrl("build-context"));
  const errorWorkspace = errorPage.locator(".workspaceStateItem").filter({ hasText: ontology.name });
  await errorWorkspace.getByRole("button", { name: /Inspect Modeling Context/ }).click();
  await expect(errorWorkspace.getByText(/503/)).toBeVisible();
  await expect(errorWorkspace.getByRole("button", { name: "Retry Modeling Context" })).toBeVisible();
});

test("Modeling Batch pagination and detail failures stay local to the expanded Workspace", async ({ page }) => {
  await setup(page, { modelingContext: "success", batchPageError: true, batchDetailError: true });
  await page.goto(workspaceUrl("build-context"));
  const workspace = page.locator(".workspaceStateItem").filter({ hasText: ontology.name });
  await workspace.getByRole("button", { name: /Inspect Modeling Context/ }).click();

  await workspace.getByRole("button", { name: "Load more Modeling Batches" }).click();
  await expect(workspace.getByText(/batch history offline|503/)).toBeVisible();
  await workspace.getByRole("button", { name: /supplier-model-v1/ }).click();
  await expect(workspace.getByText(/batch detail offline/)).toBeVisible();
  await expect(page.getByRole("heading", { name: project.name })).toBeVisible();
});
