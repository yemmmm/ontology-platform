import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace } from "./v42-fixtures";

const q1 = "a1111111-1111-4111-8111-111111111111";
const q2 = "a2222222-2222-4222-8222-222222222222";
const actor = { kind: "delivery", reference: "session-one" };
const questions = [q1, q2].map((message_id, index) => ({ message_id, kind: "business_question", text: `Question ${index + 1}`, sender: actor, entrypoint: "delivery" }));
const events = questions.map((message, index) => ({ event_seq: index + 1, event_type: "delivery_message", message_id: message.message_id, message, recorded_at: "2026-10-10T00:00:00Z" }));

async function setup(page: Page, options: { offline?: boolean; timeout?: boolean } = {}) {
  const submissions: Record<string, unknown>[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    if (!path.includes("delivery-conversations")) return false;
    let data: unknown;
    if (path.endsWith("delivery-conversations")) data = { items: [{ delivery_session_id: "session-one" }, { delivery_session_id: "session-two" }], enumeration_complete: true };
    else if (path.endsWith("/messages") && route.request().method() === "POST") {
      const input = route.request().postDataJSON(); submissions.push(input);
      if (options.timeout && submissions.length === 1) { await route.abort("timedout"); return true; }
      data = { created: true, message: { ...input, sender: { kind: "user", reference: "user:test-admin" }, entrypoint: "web", received_seq: 3, dispatch: "pending" } };
    } else if (path.includes("/messages/")) { await route.fulfill({ status: 503, json: { error: { code: "message_receipt_unknown" } } }); return true; }
    else if (path.endsWith("/events")) {
      const after = Number(new URL(route.request().url()).searchParams.get("after_seq"));
      data = { items: after ? [] : events, next_after_seq: 2, has_more: false, history_complete: true };
    } else data = { connection: options.offline ? "offline" : "online", activity: "pause_pending", observed_at: "2026-10-10T00:00:00Z", basis: "supervisor_ping", history_started_at: "2026-10-10T00:00:00Z", pending_questions: questions, history_complete: true };
    await route.fulfill({ json: data }); return true;
  } });
  await page.goto("/?project=p1&tab=conversation");
  await page.getByLabel("Delivery conversation", { exact: true }).selectOption("session-one");
  await expect(page.getByText("Status basis: supervisor_ping", { exact: true })).toBeVisible();
  return submissions;
}

test("Delivery answers bind the selected real question and preserve multiline text", async ({ page }) => {
  const calls = await setup(page);
  await page.getByLabel("Answer a question").selectOption(q2);
  await page.getByLabel("Message", { exact: true }).fill("original line one\n原文第二行");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect.poll(() => calls.length).toBe(1);
  expect(calls[0]).toMatchObject({ kind: "answer", reply_to_message_id: q2, text: "original line one\n原文第二行" });
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("");
  await expect(page.getByText("Received and delivered do not mean business work is complete")).toBeVisible();
});

test("Unknown receipt preserves draft and the exact original UUID on explicit retry", async ({ page }) => {
  const calls = await setup(page, { timeout: true });
  await page.getByLabel("Message", { exact: true }).fill("keep this original draft");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByRole("button", { name: "Retry original message" })).toBeVisible();
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("keep this original draft");
  await page.getByRole("button", { name: "Retry original message" }).click();
  await expect.poll(() => calls.length).toBe(2);
  expect(calls[1]).toEqual(calls[0]);
});

test("Offline history remains readable while send and controls cannot wake Delivery", async ({ page }) => {
  const calls = await setup(page, { offline: true });
  await expect(page.getByRole("region", { name: "Conversation history" }).getByText("Question 1", { exact: true })).toBeVisible();
  await page.getByLabel("Message", { exact: true }).fill("kept offline");
  for (const name of ["Send message", "Pause flow", "Continue flow", "Stop Team"]) await expect(page.getByRole("button", { name, exact: true })).toBeDisabled();
  await expect(page.getByText("Resume through the original Host entry before sending")).toBeVisible();
  expect(calls).toEqual([]);
});
