import { expect, test } from "@playwright/test";

const principal = {
  actor: "user:test-admin",
  scopes: ["admin", "read", "write"],
  project_id: null,
};

test("unauthenticated users can sign in and sign out", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    if (path === "/auth/me") {
      await route.fulfill({ status: 401, json: { detail: { code: "invalid_authentication" } } });
      return;
    }
    if (path === "/auth/login") {
      await route.fulfill({ json: principal });
      return;
    }
    if (path === "/auth/logout") {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({ json: [] });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

  await page.getByLabel("Username").fill("test-admin");
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByText(principal.actor)).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("login failures use a generic message", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    await route.fulfill({
      status: 401,
      json: { detail: { code: path === "/auth/login" ? "invalid_credentials" : "invalid_authentication" } },
    });
  });

  await page.goto("/");
  await page.getByLabel("Username").fill("unknown");
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("alert")).toHaveText("Authentication failed.");
});
