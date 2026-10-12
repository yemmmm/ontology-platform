import { expect, test, type Page } from "@playwright/test";
import { match, mockWorkspace, recall } from "./v42-fixtures";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("ontology-platform-ui-lang", "en"));
});

async function search(page: Page, query = "work orders") {
  await page.goto("/?project=p1&tab=recall");
  await page.getByLabel("Query", { exact: true }).fill(query);
  await page.getByRole("button", { name: "Find related nodes" }).click();
  await expect(page.getByRole("button", { name: "Give feedback" })).toBeVisible();
}
async function draft(page: Page, description = "Expected the warranty conditions.") {
  await page.getByRole("button", { name: "Give feedback" }).click();
  await page.getByLabel("Incomplete data", { exact: true }).check();
  await page.getByLabel("Feedback description").fill(description);
}
function result(revision = 12, cursor: string | null = null, items: unknown[] = []) {
  return { ...recall(items, cursor), scope: { project_id: "p1", mode: "project", status: "complete", ontologies: [{ ontology_id: "o1", model_revision: revision }] }, context_page: { returned: 0, complete: true }, truncated: false };
}

test("empty result submits actual request, scope and original text; saved is only a receipt", async ({ page }) => {
  let queryRequest: unknown;
  const submissions: any[] = [];
  const response = { ...result(), result_status: "no_match", recall: { completeness: "degraded" }, warnings: [{ code: "fallback", message: "Lexical fallback" }] };
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path === "/semantic/context:query") {
      queryRequest = route.request().postDataJSON();
      await route.fulfill({ json: response }); return true;
    }
    if (path === "/semantic/feedback") {
      const body = route.request().postDataJSON(); submissions.push(body);
      await route.fulfill({ json: { feedback_id: body.feedback_id, received_at: "2026-10-12T12:00:00Z", status: "received" } }); return true;
    }
    return false;
  } });
  await search(page);
  await expect(page.getByText("No related nodes found")).toBeVisible();
  await page.getByRole("button", { name: "Give feedback" }).click();
  await expect(page.getByRole("button", { name: "Save feedback", exact: true })).toBeDisabled();
  await page.getByLabel("Incomplete data", { exact: true }).check();
  await page.getByLabel("Incorrect information", { exact: true }).check();
  await page.getByLabel("Feedback description").fill("  No warranty conditions.\nOriginal wording.  ");
  await page.getByRole("button", { name: "Save feedback", exact: true }).click();
  await expect(page.getByText("Feedback saved", { exact: true })).toBeVisible();
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).toMatchObject({ query_request: queryRequest, reasons: ["incomplete", "incorrect"], description: "  No warranty conditions.\nOriginal wording.  ", snapshot_complete: true, result_snapshot: { pages: [{ query_request: queryRequest, result: response }] } });
  expect(submissions[0].feedback_id).toMatch(/^[0-9a-f-]{36}$/);
  await expect(page.getByText("Model corrected", { exact: true })).toHaveCount(0);
});

test("lost receipt retries exactly the same ID and body, with the draft locked", async ({ page }) => {
  const submissions: any[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path === "/semantic/context:query") { await route.fulfill({ json: result() }); return true; }
    if (path === "/semantic/feedback") {
      const body = route.request().postDataJSON(); submissions.push(body);
      if (submissions.length === 1) await route.abort("connectionfailed");
      else await route.fulfill({ json: { feedback_id: body.feedback_id, received_at: "2026-10-12T12:00:00Z", status: "received" } });
      return true;
    }
    return false;
  } });
  await search(page); await draft(page);
  await page.getByRole("button", { name: "Save feedback", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Feedback submission failed");
  await expect(page.getByLabel("Feedback description")).toBeDisabled();
  await expect(page.getByLabel("Include the frozen result snapshot")).toBeDisabled();
  await page.getByRole("button", { name: "Retry original feedback", exact: true }).click();
  await expect(page.getByText("Feedback saved", { exact: true })).toBeVisible();
  expect(submissions).toHaveLength(2); expect(submissions[1]).toEqual(submissions[0]);
});

for (const status of [422, 413]) {
  test(`explicit ${status} rejection preserves the draft and allows correction with the same ID`, async ({ page }) => {
    const submissions: any[] = [];
    await mockWorkspace(page, { handler: async (path, route) => {
      if (path === "/semantic/context:query") { await route.fulfill({ json: result() }); return true; }
      if (path === "/semantic/feedback") {
        const body = route.request().postDataJSON(); submissions.push(body);
        if (submissions.length === 1) await route.fulfill({ status, json: { detail: { code: status === 413 ? "feedback_snapshot_too_large" : "feedback_invalid" } } });
        else await route.fulfill({ json: { feedback_id: body.feedback_id, received_at: "2026-10-12T12:00:00Z", status: "received" } });
        return true;
      }
      return false;
    } });
    await search(page); await draft(page, "Original draft");
    await page.getByRole("button", { name: "Save feedback", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("Feedback submission failed");
    await expect(page.getByLabel("Feedback description")).toBeEnabled();
    await expect(page.getByLabel("Feedback description")).toHaveValue("Original draft");
    await expect(page.getByLabel("Incomplete data", { exact: true })).toBeChecked();
    await expect(page.getByRole("alert")).toContainText("Feedback was rejected; edit and submit again");
    if (status === 413) await page.getByLabel("Include the frozen result snapshot").uncheck();
    else await page.getByLabel("Feedback description").fill("Corrected description");
    await page.getByRole("button", { name: "Save feedback", exact: true }).click();
    await expect(page.getByText("Feedback saved", { exact: true })).toBeVisible();
    expect(submissions).toHaveLength(2);
    expect(submissions[1].feedback_id).toEqual(submissions[0].feedback_id);
    expect(submissions[1].query_request).toEqual(submissions[0].query_request);
    if (status === 413) {
      expect(submissions[1].result_snapshot).toBeUndefined();
      expect(submissions[1].snapshot_complete).toBe(false);
    } else expect(submissions[1].description).toBe("Corrected description");
  });
}

test("multi-page feedback freezes each request and revision before later pages load", async ({ page }) => {
  let submission: any;
  const queries: any[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path === "/semantic/context:query") {
      const body = route.request().postDataJSON(); queries.push(body);
      const pageResult = body.match_cursor === "second" ? result(13, "third", [match("b")]) : body.match_cursor === "third" ? result(14, null, [match("c")]) : result(12, "second", [match("a")]);
      await route.fulfill({ json: pageResult }); return true;
    }
    if (path === "/semantic/feedback") {
      submission = route.request().postDataJSON();
      await route.fulfill({ json: { feedback_id: submission.feedback_id, received_at: "2026-10-12T12:00:00Z", status: "received" } }); return true;
    }
    return false;
  } });
  await search(page);
  await page.getByRole("button", { name: "Load more related nodes" }).click();
  await expect(page.locator(".recallNode h2")).toHaveText(["a", "b"]);
  await draft(page);
  await expect(page.getByText("Model revisions differ between pages; each page is retained and the snapshot is incomplete")).toBeVisible();
  await page.getByRole("button", { name: "Load more related nodes" }).click();
  await expect(page.locator(".recallNode h2")).toHaveText(["a", "b", "c"]);
  await page.getByRole("button", { name: "Save feedback", exact: true }).click();
  await expect(page.getByText("Feedback saved", { exact: true })).toBeVisible();
  expect(submission.query_request).toEqual(queries[0]);
  expect(submission.query_request.match_cursor).toBeUndefined();
  expect(submission.snapshot_complete).toBe(false);
  expect(submission.result_snapshot.pages.map((p: any) => p.query_request)).toEqual(queries.slice(0, 2));
  expect(submission.result_snapshot.pages.map((p: any) => p.result.scope.ontologies[0].model_revision)).toEqual([12, 13]);
});

test("editing the query or switching project discards the old feedback draft", async ({ page }) => {
  const submissions: any[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path === "/semantic/context:query") { await route.fulfill({ json: result() }); return true; }
    if (path === "/semantic/feedback") { submissions.push(route.request().postDataJSON()); await route.fulfill({ json: { status: "received" } }); return true; }
    return false;
  } });
  await search(page); await draft(page, "Old draft");
  await page.getByLabel("Query", { exact: true }).fill("new query");
  await expect(page.getByLabel("Feedback description")).toHaveCount(0);
  await page.getByRole("button", { name: "Find related nodes" }).click();
  await page.getByRole("button", { name: "Give feedback" }).click();
  await expect(page.getByLabel("Feedback description")).toHaveValue("");
  await page.getByLabel("Feedback description").fill("New draft");
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await page.getByLabel("Project", { exact: true }).selectOption("p2");
  await page.getByRole("link", { name: "Recall test", exact: true }).click();
  await expect(page.getByLabel("Query", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Feedback description")).toHaveCount(0);
  expect(submissions).toHaveLength(0);
});

test("oversize snapshot is not silently truncated; explicit omission submits incomplete", async ({ page }) => {
  let submission: any;
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path === "/semantic/context:query") { await route.fulfill({ json: result(12, null, [{ ...match("large"), description: "中".repeat(90_000) }]) }); return true; }
    if (path === "/semantic/feedback") { submission = route.request().postDataJSON(); await route.fulfill({ json: { feedback_id: submission.feedback_id, received_at: "2026-10-12T12:00:00Z", status: "received" } }); return true; }
    return false;
  } });
  await search(page); await draft(page);
  await expect(page.getByRole("alert")).toContainText("Result snapshot exceeds 256 KiB");
  await expect(page.getByRole("button", { name: "Save feedback", exact: true })).toBeDisabled();
  expect(submission).toBeUndefined();
  await page.getByLabel("Include the frozen result snapshot").uncheck();
  await page.getByRole("button", { name: "Save feedback", exact: true }).click();
  await expect(page.getByText("Feedback saved", { exact: true })).toBeVisible();
  expect(submission.result_snapshot).toBeUndefined(); expect(submission.snapshot_complete).toBe(false);
});
