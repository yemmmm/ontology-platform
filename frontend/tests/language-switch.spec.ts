import { expect, test } from "@playwright/test";
import { mockWorkspace } from "./v42-fixtures";
test("settings switches all system navigation and keeps business content unchanged", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/?tab=settings");
  await page.getByLabel("Language preference").selectOption("zh");
  await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "模型浏览" })).toBeVisible();
  await expect(page.getByLabel("项目")).toContainText("维修项目");
  await page.getByLabel("语言偏好").selectOption("en");
  await expect(page.getByRole("link", { name: "Recall test" })).toBeVisible();
  await expect(page.getByLabel("Project")).toContainText("维修项目");
});
test("language persists on reload and translated login still uses existing auth", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/?tab=settings");
  await page.getByLabel("Language preference").selectOption("zh");
  await page.reload();
  await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page.getByRole("heading", { name: "登录", exact: true })).toBeVisible();
  await expect(page.getByLabel("用户名")).toBeVisible();
  await expect(page.getByLabel("密码")).toBeVisible();
});
