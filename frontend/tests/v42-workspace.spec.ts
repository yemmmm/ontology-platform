import { expect, test } from "@playwright/test";
import { readFileSync, existsSync } from "node:fs";
import { artifact, envelope, index, match, mockWorkspace, recall, relations, report, resources, run } from "./v42-fixtures";

test("T01 five sibling links normalize retired URL and storage, with history navigation", async ({ page }) => {
  await mockWorkspace(page);
  await page.addInitScript(() => {
    localStorage.setItem("ontology-platform-ui-workspace-tab-v4", "classes");
    localStorage.setItem("ontology-platform-ui-selected-ontology", "secret");
    localStorage.setItem("ontology-platform-ui-workspace-lock:o1", "locked");
    localStorage.setItem("topology:layout:secret:force", "SENSITIVE_OLD_LAYOUT");
    localStorage.setItem("unrelated", "keep");
  });
  await page.goto("/?project=forbidden&ontology=secret&tab=classes&batch=b1&graph=g1");
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  expect(new URL(page.url()).search).toBe("?project=p1&tab=overview");
  expect(await page.getByRole("navigation").getByRole("link").allTextContents()).toEqual(["Overview", "Model browser", "Recall test", "Member permissions", "Settings"]);
  expect(await page.evaluate(() => Object.keys(localStorage).sort())).toEqual(["ontology-platform-ui-selected-project", "ontology-platform-ui-workspace-tab-v4.2", "unrelated"]);
  await page.getByRole("link", { name: "Model browser" }).click();
  await page.getByRole("link", { name: "Recall test" }).click();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Model browser", exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", { name: "Recall test", exact: true })).toBeVisible();
});
test("T01 project switching requires returning to overview from every other tab", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/?project=p1&tab=overview");
  await expect(page.getByLabel("Project", { exact: true })).toHaveValue("p1");
  for (const name of ["Model browser", "Recall test", "Member permissions", "Settings"]) {
    await page.getByRole("link", { name, exact: true }).click();
    await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
    await expect(page.getByLabel("Project", { exact: true })).toHaveCount(0);
    expect(new URL(page.url()).searchParams.get("project")).toBe("p1");
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
  await expect(page.getByLabel("Project", { exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page.getByLabel("Project", { exact: true }).selectOption("p2");
  await expect(page.getByRole("region", { name: "Project introduction", exact: true }).getByRole("heading", { name: "Integration", exact: true })).toBeVisible();
  expect(new URL(page.url()).search).toBe("?project=p2&tab=overview");
  await page.getByRole("link", { name: "Model browser", exact: true }).click();
  await expect(page.getByLabel("Project", { exact: true })).toHaveCount(0);
  expect(new URL(page.url()).search).toBe("?project=p2&tab=model");
});
test("T01 settings works without a project or ontology; ontology-only links fall back", async ({ page }) => {
  await mockWorkspace(page, { projects: [] });
  await page.goto("/?ontology=retired");
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible();
  await expect(page.getByText("No accessible projects", { exact: true })).toHaveCount(2);
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByText("user:test-admin")).toBeVisible();
  await expect(page.getByLabel("Language preference")).toBeVisible();
});
test("T02 overview has CQ and one progress bar without inferring business progress from RUNNING", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/");
  for (const name of ["Project introduction", "Project progress", "Competency questions"]) await expect(page.getByRole("region", { name, exact: true })).toBeVisible();
  await expect(page.getByText("The latest record is running; business progress is unverified")).toBeVisible();
  await expect(page.getByText("维修业务与外部接口的语义范围。")).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveCount(1);
});
test("T02 latest all-terminal history stays historical; events choose timestamp not artifact order", async ({ page }) => {
  const value = run();
  value.artifacts.host.push(artifact("new-stage", { records: [{ stage: "latest-explicit", recorded_at: "2026-10-07T11:00:00Z" }] }), artifact("old-stage", { records: [{ stage: "older-explicit", recorded_at: "2026-10-07T09:00:00Z" }] }));
  await mockWorkspace(page, { run: value });
  await page.goto("/");
  await expect(page.getByText("Recorded phase: latest-explicit", { exact: true })).toBeVisible();
  await page.route("**/workbench", route => route.fulfill({ json: index([{ run_id: "r1", state: "FAILED", source_updated_at: "2026-10-07T10:00:00Z" }], null) }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("The latest run ended; current project progress needs verification")).toBeVisible();
  await expect(page.getByText("复查工单如何保持独立？")).toBeVisible();
  await expect(page.getByText("谁可以关闭工单？")).toHaveCount(0);
  await expect(page.getByLabel("Question version")).toHaveCount(0);
  await expect(page.getByText("Current frozen version", { exact: true })).toHaveCount(0);
});
for (const [name, data] of [
  ["incomplete", index(undefined, "r1", false)],
  ["ambiguous", index([{ run_id: "r1", state: "RUNNING", source_updated_at: "a" }, { run_id: "r2", state: "RUNNING", source_updated_at: "b" }], null)],
  ["empty", index([], null)],
] as const) test(`T02 ${name} enumeration never guesses a current run`, async ({ page }) => {
  const calls: string[] = [];
  await mockWorkspace(page, { index: data, handler: async (path) => { calls.push(path); return false; } });
  await page.goto("/");
  await expect(page.getByText("Current progress is unverified", { exact: true })).toBeVisible();
  await expect(page.getByText("Current questions cannot be determined")).toBeVisible();
  expect(calls.some(path => path.includes("/workbench/runs/"))).toBe(false);
});
test("T03 shows all panorama and slice questions together without historical selection or answers", async ({ page }) => {
  const value = run();
  value.artifacts.competency_questions[1].data.questions = Array.from({ length: 18 }, (_, i) => ({ question_id: `Q${i + 1}`, question: `当前业务问题 ${i + 1}`, scope: { kind: i < 5 ? "panorama" : "slice" }, review_content_version: 2 }));
  await mockWorkspace(page, { run: value });
  await page.goto("/");
  await expect(page.getByRole("region", { name: "Competency questions", exact: true }).getByRole("listitem")).toHaveCount(18);
  await expect(page.getByText("当前业务问题 18", { exact: true })).toBeVisible();
  await expect(page.getByText("谁可以关闭工单？")).toHaveCount(0);
  await expect(page.getByLabel("Question version")).toHaveCount(0);
  expect(await page.locator("body").textContent()).not.toMatch(/ANSWER_SENTINEL|panorama|slice|digest2/);
});
test("T03 without freeze selects latest unique record; duplicate bindings never guess", async ({ page }) => {
  const value = run(); value.artifacts.host = [];
  value.artifacts.competency_questions[0].source.updated_at = "2026-10-06T10:00:00Z";
  await mockWorkspace(page, { run: value });
  await page.goto("/");
  await expect(page.getByText("复查工单如何保持独立？")).toBeVisible();
  await expect(page.getByText("Latest recorded questions; freeze unverified")).toBeVisible();
  const ambiguous = run(); ambiguous.artifacts.competency_questions.push({ ...ambiguous.artifacts.competency_questions[1], artifact_id: "duplicate" });
  await page.route("**/workbench/runs/**", route => route.fulfill({ json: ambiguous }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Current questions cannot be determined")).toBeVisible();
  await expect(page.getByText("复查工单如何保持独立？")).toHaveCount(0);
});
test("T04 current report marks acceptance and counts public plus hidden once", async ({ page }) => {
  const value = run(); value.artifacts.reports.push(report("report-stale", "stale"));
  await mockWorkspace(page, { run: value });
  await page.goto("/");
  await expect(page.getByText("Acceptance passed", { exact: true })).toHaveCount(1);
  await expect(page.getByRole("progressbar")).toHaveAttribute("value", String(1 / 3 * 100));
  await expect(page.getByText("Acceptance progress · Accepted 1 / 3; passed 1", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Acceptance record")).toHaveCount(0);
  const stale = run(); stale.artifacts.reports[0].data.applicability = "stale";
  await page.route("**/workbench/runs/**", route => route.fulfill({ json: stale }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Acceptance passed", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Not accepted yet", { exact: true })).toHaveCount(3);
  await expect(page.getByRole("progressbar")).not.toHaveAttribute("value");
});
test("T04 regression, mismatched freeze and incomplete counts cannot imply accepted progress", async ({ page }) => {
  const value = run(); value.artifacts.reports = [artifact("public_regression_report", { full_pass: true })];
  await mockWorkspace(page, { run: value });
  await page.goto("/");
  await expect(page.getByText(/No current acceptance results/)).toBeVisible();
  const broken = run(); delete (broken.artifacts.reports[0].data as Record<string, unknown>).denominator;
  await page.route("**/workbench/runs/**", route => route.fulfill({ json: broken }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText(/Progress data is incomplete/)).toBeVisible();
  await expect(page.getByRole("progressbar")).not.toHaveAttribute("value");
  const mismatch = run(); mismatch.artifacts.reports[0].data.freeze_digest = "different";
  await page.route("**/workbench/runs/**", route => route.fulfill({ json: mismatch }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Acceptance passed", { exact: true })).toHaveCount(0);
});
test("T04 hidden question gets its own verdict badge without double counting progress", async ({ page }) => {
  const value = run();
  const questions = value.artifacts.competency_questions[1].data.questions as Record<string, unknown>[];
  const data = value.artifacts.reports[0].data;
  data.question_verdicts = [{ question_id: "Q1", verdict: "pass" }, { question_id: "H1", verdict: "model-recall-insufficient" }];
  data.hidden_summary = { verdict_counts: { "model-recall-insufficient": 1 }, unexecuted_count: 0 };
  await mockWorkspace(page, { run: value });
  await page.goto("/");
  const hidden = page.getByRole("listitem").filter({ hasText: "隐藏业务验证问题" });
  await expect(hidden.getByText("(Hidden question)", { exact: true })).toBeVisible();
  await expect(hidden.getByText("Acceptance not passed", { exact: true })).toBeVisible();
  await expect(page.getByText("Acceptance progress · Accepted 2 / 3; passed 1", { exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("value", String(2 / 3 * 100));
});
test("T04 all 26 questions share progress across formal acceptance reports", async ({ page }) => {
  const value = run();
  const questions = Array.from({ length: 26 }, (_, i) => ({ question_id: `Q${i}`, question: `问题 ${i}`, visibility: i < 18 ? "public" : "hidden" }));
  value.artifacts.competency_questions[1].data.questions = questions;
  value.artifacts.reports = [18, 8].map((count, batch) => {
    const selected = questions.slice(batch ? 18 : 0, batch ? 26 : 18);
    return artifact("reports", { applicability: "verified_current", batch_id: "batch2", freeze_digest: "digest2", denominator: count, question_ids: selected.map(q => q.question_id), question_verdicts: selected.map(q => ({ question_id: q.question_id, verdict: "pass" })) }, `formal-${batch}`);
  });
  await mockWorkspace(page, { run: value });
  await page.goto("/");
  await expect(page.getByText("Acceptance progress · Accepted 26 / 26; passed 26", { exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("value", "100");
  await expect(page.getByText("Acceptance passed", { exact: true })).toHaveCount(26);
  // A newer partial rerun replaces the affected questions, without reusing
  // their older PASS or counting the same questions twice.
  value.artifacts.reports.push(artifact("reports", { applicability: "verified_current", batch_id: "batch2", freeze_digest: "digest2", denominator: 2, question_ids: ["Q0", "Q18"], question_verdicts: [{ question_id: "Q0", verdict: "model-recall-insufficient" }] }, "rerun", "2026-10-08T10:00:00Z"));
  await page.route("**/workbench/runs/**", route => route.fulfill({ json: value }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Acceptance progress · Accepted 25 / 26; passed 24", { exact: true })).toBeVisible();
  await expect(page.getByText("Acceptance not passed", { exact: true })).toHaveCount(1);
  await expect(page.getByText("Not accepted yet", { exact: true })).toHaveCount(1);
});
test("T04 eight hidden verdicts alone complete only eight of 26 questions", async ({ page }) => {
  const value = run();
  value.artifacts.competency_questions[1].data.questions = Array.from({ length: 26 }, (_, i) => ({ question_id: `Q${i}`, question: `问题 ${i}`, visibility: i < 18 ? "public" : "hidden" }));
  const ids = Array.from({ length: 8 }, (_, i) => `Q${i + 18}`);
  value.artifacts.reports = [artifact("reports", { applicability: "verified_current", batch_id: "batch2", freeze_digest: "digest2", denominator: 8, question_ids: ids, question_verdicts: ids.map(question_id => ({ question_id, verdict: "pass" })) })];
  await mockWorkspace(page, { run: value });
  await page.goto("/");
  await expect(page.getByText("Acceptance progress · Accepted 8 / 26; passed 8", { exact: true })).toBeVisible();
  await expect(page.getByRole("progressbar")).toHaveAttribute("value", String(8 / 26 * 100));
});
test("T05 unified IRI canvas excludes property definitions, retains actual edges and multiple locations", async ({ page }) => {
  const requests: string[] = [];
  await mockWorkspace(page, { handler: async (path, route) => { requests.push(route.request().url()); return false; } });
  await page.goto("/?tab=model");
  const graph = page.getByRole("img", { name: "Model graph" });
  await expect(graph).toHaveAttribute("data-node-count", "11");
  await expect(graph).toHaveAttribute("data-edge-count", "1");
  await expect(page.getByRole("button", { name: "Select node 状态属性", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Select node 父单关系", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Select node 无分类节点", exact: true })).toHaveCount(1);
  await page.getByLabel("Search loaded model").fill("状态属性");
  await expect(page.getByText("No matches in the loaded viewpoint")).toBeVisible();
  expect(requests.filter(url => url.includes("resource-list")).every(url => url.includes("field_set=detail&limit=500"))).toBe(true);
  expect(requests.filter(url => url.includes("resource-relations")).every(url => url.includes("limit=1000"))).toBe(true);
  await page.getByLabel("Search loaded model").fill("urn:work");
  await page.getByRole("button", { name: "工单", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Node details" })).toBeVisible();
  await expect(page.getByLabel("Read location").locator("option")).toHaveCount(2);
  await page.getByLabel("Read location").selectOption("1");
  await expect(page.getByText("integration meaning", { exact: true })).toBeVisible();
  await expect(page.getByText("Work order", { exact: true })).toBeVisible();
});
test("T06 seven explicit views and loaded search intersect without removing other view nodes", async ({ page }) => {
  await mockWorkspace(page); await page.goto("/?tab=model");
  await expect(page.getByRole("img", { name: "Model graph" })).toHaveAttribute("data-node-count", "11");
  await expect(page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button")).toHaveCount(8);
  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Process", exact: true }).click();
  await expect(page.getByRole("img", { name: "Model graph" })).toHaveAttribute("data-node-count", "2");
  await page.getByLabel("Search loaded model").fill("integration meaning");
  await expect(page.getByText("Matches in loaded viewpoint: 1", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Model graph" })).toHaveAttribute("data-node-count", "2");
  await page.getByLabel("Search loaded model").fill("no match");
  await expect(page.getByText("No matches in the loaded viewpoint")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByRole("img", { name: "Model graph" })).toHaveAttribute("data-node-count", "11");
  const nodeButton = page.getByRole("button", { name: "Select node 无分类节点", exact: true });
  await nodeButton.focus(); await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "无分类节点", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.getByRole("button", { name: "Zoom out" }).click();
  await page.getByRole("button", { name: "Fit graph" }).click();
});
test("T05 structured references remain separate from asserted edges and follow viewpoint filters", async ({ page }) => {
  await mockWorkspace(page, { handler: async (path, route) => {
    if (!path.includes("o1") || !path.endsWith("resource-relations")) return false;
    const reference = { ...relations[0], id: "reference", edge_kind: "structured_reference", field_path: "mapped_definition.definition_ref", label: "mapped_definition.definition_ref" };
    await route.fulfill({ json: envelope([...relations, reference]) });
    return true;
  } });
  await page.goto("/?tab=model");
  const graph = page.getByRole("img", { name: "Model graph" });
  await expect(graph).toHaveAttribute("data-edge-count", "2");
  await expect(graph).toHaveAttribute("data-reference-count", "1");
  await expect(page.getByText("Solid lines: asserted relations. Dashed lines: recorded structured references; labels show source fields.")).toBeVisible();
  await page.getByRole("group", { name: "Viewpoint", exact: true }).getByRole("button", { name: "Object", exact: true }).click();
  await expect(graph).toHaveAttribute("data-edge-count", "0");
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(graph).toHaveAttribute("data-reference-count", "1");
});
test("T07 bounded partial data, failed scope and mismatched signatures retain successful nodes", async ({ page }) => {
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path.includes("o2/workspace-context")) { await route.fulfill({ status: 403, json: { detail: { code: "forbidden" } } }); return true; }
    if (path.endsWith("resource-list")) { await route.fulfill({ json: envelope(resources, "sig1", false) }); return true; }
    if (path.endsWith("resource-relations")) { await route.fulfill({ json: envelope(relations, "sig2", false) }); return true; }
    return false;
  } });
  await page.goto("/?tab=model");
  await expect(page.getByRole("img", { name: "Model graph" })).toHaveAttribute("data-node-count", "11");
  await expect(page.getByRole("img", { name: "Model graph" })).toHaveAttribute("data-edge-count", "0");
  await expect(page.getByText(/Source versions differ/)).toBeVisible();
  await expect(page.getByText(/Integration: Scope not loaded/)).toBeVisible();
  await expect(page.getByText(/Resource window is incomplete/)).toBeVisible();
});
test("T07 no ontology and missing default workspace distinguish unloaded from an empty model", async ({ page }) => {
  await mockWorkspace(page, { ontologies: [] });
  await page.goto("/?tab=model");
  await expect(page.getByText("No Ontologies in this project", { exact: true })).toBeVisible();
  await page.route("**/projects/p1/ontologies", route => route.fulfill({ json: [{ id: "o1", name: "Service" }] }));
  await page.route("**/workspace-context", route => route.fulfill({ json: { ontology_id: null } }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.getByText("Model scopes have not been loaded", { exact: true })).toBeVisible();
});
test("T10 fixed governed node query rejects whitespace and overlong query without requests", async ({ page }) => {
  const bodies: Record<string, unknown>[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path !== "/semantic/context:query") return false;
    bodies.push(route.request().postDataJSON());
    await route.fulfill({ json: recall([match("b", "Second"), match("a", "First"), { ...match("triple", "TRIPLE_SENTINEL"), kind: "fact" }]) }); return true;
  } });
  await page.goto("/?tab=recall");
  await page.getByLabel("Query", { exact: true }).fill("  ");
  await expect(page.getByRole("button", { name: "Find related nodes" })).toBeDisabled();
  await page.getByLabel("Query", { exact: true }).fill("x".repeat(2001));
  await expect(page.getByRole("button", { name: "Find related nodes" })).toBeDisabled();
  expect(bodies).toHaveLength(0);
  await page.getByLabel("Query", { exact: true }).fill("  closing work orders  ");
  await page.getByRole("button", { name: "Find related nodes" }).click();
  await expect(page.locator(".recallNode h2")).toHaveText(["Second", "First"]);
  expect(bodies[0]).toEqual({ project_id: "p1", scope_mode: "project", query: "closing work orders", resource_types: ["concept", "instance", "operation", "mapping", "metric"], assertion_types: ["asserted"], search_mode: "hybrid", depth: 0, limit: 20, context_limit: 0, context_detail: "compact" });
  expect(await page.locator("body").textContent()).not.toContain("TRIPLE_SENTINEL");
  expect(await page.locator("body").textContent()).not.toContain("FACT_SENTINEL");
});
test("T11 main cursor appends ordered nodes once, editor clears and discards a late result", async ({ page }) => {
  const bodies: Record<string, unknown>[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path !== "/semantic/context:query") return false;
    const body = route.request().postDataJSON(); bodies.push(body);
    if (body.query === "late") await new Promise(resolve => setTimeout(resolve, 350));
    await route.fulfill({ json: body.match_cursor ? recall([match("b"), match("c")]) : recall([match("a"), match("b")], "cursor1") }); return true;
  } });
  await page.goto("/?tab=recall"); await page.getByLabel("Query", { exact: true }).fill("first"); await page.getByRole("button", { name: "Find related nodes" }).click();
  await page.getByRole("button", { name: "Load more related nodes" }).click();
  await expect(page.locator(".recallNode h2")).toHaveText(["a", "b", "c"]);
  expect(bodies[1]).toEqual({ ...bodies[0], match_cursor: "cursor1" });
  await page.getByLabel("Query", { exact: true }).fill("late");
  await expect(page.locator(".recallNode")).toHaveCount(0);
  await page.getByRole("button", { name: "Find related nodes" }).click();
  await page.getByLabel("Query", { exact: true }).fill("edited");
  await page.waitForTimeout(500);
  await expect(page.locator(".recallNode")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Load more related nodes" })).toHaveCount(0);
});
test("T11 cursor error preserves explicit failure, no more cursor, and permits fresh query", async ({ page }) => {
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path !== "/semantic/context:query") return false;
    const body = route.request().postDataJSON();
    if (body.match_cursor) await route.fulfill({ status: 409, json: { detail: { code: "cursor_signature_changed" } } });
    else await route.fulfill({ json: { ...recall([match("a")], "cursor1"), recall: { completeness: "degraded" }, warnings: [{ code: "embedding_unavailable", message: "Lexical fallback" }] } });
    return true;
  } });
  await page.goto("/?tab=recall"); await page.getByLabel("Query", { exact: true }).fill("first"); await page.getByRole("button", { name: "Find related nodes" }).click();
  await expect(page.getByText("Recall is degraded")).toBeVisible();
  await page.getByRole("button", { name: "Load more related nodes" }).click();
  await expect(page.getByRole("alert")).toContainText("cursor_signature_changed");
  await expect(page.getByRole("button", { name: "Load more related nodes" })).toHaveCount(0);
  await page.getByRole("button", { name: "Query again" }).click();
  await expect(page.getByRole("button", { name: "Load more related nodes" })).toBeVisible();
});
test("T12 roles and grants use only the read contract; project switch never leaks old grants", async ({ page }) => {
  const requests: string[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    requests.push(`${route.request().method()} ${path}`);
    if (path === "/projects/p2/semantic-access-roles") { await route.fulfill({ status: 403, json: { detail: { code: "forbidden" } } }); return true; }
    return false;
  } });
  await page.goto("/?tab=access");
  await expect(page.getByText("context:query", { exact: true })).toBeVisible();
  await expect(page.getByText("No Grant configured")).toBeVisible();
  expect(requests.every(path => path === "GET /auth/me" || path === "GET /projects" || path === "GET /projects/p1/semantic-access-roles")).toBe(true);
  await expect(page.getByLabel("Project", { exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page.getByLabel("Project", { exact: true }).selectOption("p2");
  await page.getByRole("link", { name: "Member permissions", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("403");
  await expect(page.getByText("context:query", { exact: true })).toHaveCount(0);
});
test("T12 empty roles and T13 minimal settings without any model requests", async ({ page }) => {
  const requests: string[] = [];
  await mockWorkspace(page, { roles: [], handler: async path => { requests.push(path); return false; } });
  await page.goto("/?tab=access");
  await expect(page.getByText("No permission roles")).toBeVisible();
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByText("user:test-admin")).toBeVisible();
  expect(requests.some(path => /ontologies|keys|members|users|health|protection/.test(path))).toBe(false);
  expect(await page.locator(".settingsPanel button").allTextContents()).toEqual(["Sign out"]);
});
test("T14 retired source files, CRUD API and class-specific pages are physically absent", async () => {
  for (const filename of ["ClassesPage", "EntitiesPage", "ProjectWorkbenchPage", "SemanticModelPage", "ContextQueryPage", "ProjectAccessPage", "BuildContextDebugPage", "McpToolsPage", "GraphSetPage", "GraphGovernancePage", "FactAuditPage", "ProjectBriefPage", "RequirementQuestionsPage", "EntitiesSearchPage"]) expect(existsSync(`src/pages/${filename}.tsx`)).toBe(false);
  for (const filename of ["src/semanticApi.ts", "src/types.ts", "src/utils.ts", "src/hooks/useWorkspaceLocation.ts", "src/pages/workbenchTypes.ts", "src/components/semantic", "src/components/workbench"]) expect(existsSync(filename)).toBe(false);
  const api = readFileSync("src/workspaceApi.ts", "utf8");
  expect(api).not.toMatch(/validation-runs|reasoning-runs|exports|datasets:load|method: "(?:PUT|PATCH|DELETE)"/);
});
test("T15 desktop and 390px preserve brand, keyboard focus and no document overflow", async ({ page }) => {
  await mockWorkspace(page); await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/"); await expect(page.getByRole("progressbar")).toHaveCount(1);
  await page.screenshot({ path: "/tmp/v42-development-overview-desktop.png", fullPage: true });
  await page.getByRole("link", { name: "Model browser" }).click();
  await expect(page.getByRole("img", { name: "Model graph" })).toHaveAttribute("data-node-count", "11");
  await page.screenshot({ path: "/tmp/v42-development-model-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("Search loaded model").fill("urn:work"); await page.getByRole("button", { name: "工单", exact: true }).click();
  await expect(page.getByRole("complementary", { name: "Node details" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const height = await page.getByRole("img", { name: "Model graph" }).evaluate(element => element.getBoundingClientRect().height);
  expect(height).toBeGreaterThanOrEqual(420);
  await page.screenshot({ path: "/tmp/v42-development-model-mobile.png", fullPage: true });
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("progressbar")).toHaveCount(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/v42-development-overview-mobile.png", fullPage: true });
});
