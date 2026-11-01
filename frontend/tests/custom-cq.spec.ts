import { expect, test } from "@playwright/test";
import { mockWorkspace } from "./v42-fixtures";
import { readFileSync } from "node:fs";

test("project question can be saved without an ontology or answer, edited and deselected", async ({ page }) => {
  let questions: Record<string, any>[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path === "/projects/p1/competency-questions") {
      if (route.request().method() === "POST") {
        const value = route.request().postDataJSON();
        expect(value.ontology_id).toBeUndefined();
        questions.push({ id: "custom-1", project_id: "p1", ontology_id: null, active: true,
          content_revision: 1, validation_result: {}, ...value,
          cq_definition: { kind: "custom", selected: true, criteria_status: "draft", reference_answer: null, ...value.cq_definition } });
        await route.fulfill({ status: 201, json: questions[0] });
      } else await route.fulfill({ json: questions });
      return true;
    }
    if (path === "/competency-questions/custom-1") {
      const value = route.request().postDataJSON();
      expect(value.expected_revision).toBe(questions[0].content_revision);
      questions[0] = { ...questions[0], ...value, content_revision: questions[0].content_revision + 1 };
      await route.fulfill({ json: questions[0] });
      return true;
    }
    return false;
  } });
  await page.goto("/?project=p1&tab=overview");
  const bank = page.getByRole("region", { name: "Project questions", exact: true });
  await bank.getByRole("button", { name: "Add question", exact: true }).click();
  await bank.getByLabel("Question", { exact: true }).fill("每个凭证调用多少次？\n包含零调用。");
  await bank.getByRole("button", { name: "Save question", exact: true }).click();
  await expect(bank.getByText("每个凭证调用多少次？ 包含零调用。", { exact: true })).toBeVisible();
  await expect(bank.getByText("Criteria need review", { exact: true })).toBeVisible();
  await expect(bank.getByText("SQL execution: Not executed", { exact: false })).toBeVisible();
  await bank.getByRole("button", { name: "Edit question", exact: true }).click();
  await bank.getByLabel("Question", { exact: true }).fill("按月统计成功调用次数");
  await bank.getByRole("button", { name: "Save question", exact: true }).click();
  await expect(bank.getByText("按月统计成功调用次数", { exact: true })).toBeVisible();
  await bank.getByRole("checkbox", { name: "Use in future modeling" }).uncheck();
  await expect.poll(() => questions[0].cq_definition.selected).toBe(false);
  await bank.getByRole("button", { name: "Deactivate question", exact: true }).click();
  await expect.poll(() => questions[0].active).toBe(false);
});

test("version conflict keeps the user's draft and offers a reload instead of overwriting", async ({ page }) => {
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path === "/projects/p1/competency-questions") {
      await route.fulfill({ json: [{ id: "custom-1", question: "旧题干", active: true, content_revision: 1,
        cq_definition: { kind: "custom", selected: true, criteria_status: "draft" }, validation_result: {} }] });
      return true;
    }
    if (path === "/competency-questions/custom-1") {
      await route.fulfill({ status: 409, json: { detail: { code: "cq_revision_conflict", current_revision: 2 } } });
      return true;
    }
    return false;
  } });
  await page.goto("/?project=p1&tab=overview");
  const bank = page.getByRole("region", { name: "Project questions", exact: true });
  await bank.getByRole("button", { name: "Edit question", exact: true }).click();
  await bank.getByLabel("Question", { exact: true }).fill("尚未提交成功的修改");
  await bank.getByRole("button", { name: "Save question", exact: true }).click();
  await expect(bank.getByRole("alert")).toContainText("409");
  await expect(bank.getByLabel("Question", { exact: true })).toHaveValue("尚未提交成功的修改");
  await expect(bank.getByRole("button", { name: "Reload questions", exact: true })).toBeVisible();
});

test("JSON import shows all nine persistent questions and exports a selected snapshot", async ({ page }) => {
  const seed = JSON.parse(readFileSync("../examples/llm-access-lab/competency-questions.json", "utf8"));
  let rows: Record<string, unknown>[] = [];
  await mockWorkspace(page, { handler: async (path, route) => {
    if (path === "/projects/p1/competency-questions/import") {
      expect(route.request().postDataJSON().questions).toHaveLength(9);
      rows = seed.questions.map((q: Record<string, unknown>, index: number) => ({ id: `q${index}`, question: q.question,
        active: true, content_revision: 1, cq_definition: { kind: "custom", criteria_status: "draft", selected: true }, validation_result: {} }));
      await route.fulfill({ json: { questions: rows } }); return true;
    }
    if (path === "/projects/p1/competency-questions") { await route.fulfill({ json: rows }); return true; }
    if (path === "/projects/p1/competency-questions/snapshot") {
      await route.fulfill({ json: { snapshot_id: "cq-frozen", questions: rows } }); return true;
    }
    return false;
  } });
  await page.goto("/?project=p1&tab=overview");
  const bank = page.getByRole("region", { name: "Project questions", exact: true });
  await bank.getByLabel("Import questions", { exact: true }).setInputFiles("../examples/llm-access-lab/competency-questions.json");
  await expect(bank.locator("li")).toHaveCount(9);
  const download = page.waitForEvent("download");
  await bank.getByRole("button", { name: "Download selected questions", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("cq-frozen.json");
});
