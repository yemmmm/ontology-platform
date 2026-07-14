import { expect, test, type Page } from "@playwright/test";

const project = { id: "project-evidence", name: "Agent Platform", description: "Shared evidence" };
const ontology = {
  id: "ontology-evidence",
  project_id: project.id,
  name: "Agent Operations",
  description: "Operation semantics",
  status: "active",
};

async function mockApi(page: Page) {
  const references = [
    {
      id: "ref-1",
      project_id: project.id,
      document_name: "Dify API Guide",
      excerpt: "Publish the workflow before invoking the application API.",
      excerpt_hash: "a".repeat(64),
      created_by: "agent:test",
      created_at: "2026-07-14T08:00:00Z",
      association_count: 1,
    },
  ];
  await page.addInitScript(() => window.localStorage.setItem("ontology-platform-ui-lang", "en"));
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    let body: unknown = [];
    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/evidence-references`) {
      if (route.request().method() === "POST") {
        const payload = route.request().postDataJSON() as { document_name: string; excerpt: string };
        const created = {
          id: "ref-2",
          project_id: project.id,
          document_name: payload.document_name.trim(),
          excerpt: payload.excerpt.trim(),
          excerpt_hash: "b".repeat(64),
          created_by: null,
          created_at: "2026-07-14T09:00:00Z",
          association_count: 0,
          created: true,
        };
        references.unshift(created);
        body = created;
      } else {
        body = { items: references, total: references.length, limit: 200, offset: 0 };
      }
    } else if (path === "/evidence-references/ref-1/associations") {
      body = {
        items: [
          {
            id: "association-1",
            ontology_id: ontology.id,
            graph_set_id: "graph-set-1",
            target_type: "create_class",
            target_id: "https://example.test/Workflow",
            client_item_id: "item-1",
            edit_audit_id: "audit-1",
            created_at: "2026-07-14T08:10:00Z",
          },
        ],
      };
    } else if (path === "/evidence-references/ref-2/associations") {
      body = { items: [], total: 0 };
    }
    await route.fulfill({ json: body });
  });
}

test("project evidence ledger creates and inspects lightweight references", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&tab=evidence`);

  const ledger = page.locator("section[aria-label='evidence-references-page']");
  await expect(ledger).toBeVisible();
  await expect(ledger.getByText("Shared by project")).toBeVisible();
  await expect(ledger.getByText("Dify API Guide", { exact: true }).first()).toBeVisible();
  await expect(ledger.getByText("create class")).toBeVisible();
  await expect(ledger.getByText("Current ontology")).toBeVisible();

  await ledger.getByPlaceholder("Example: Dify API Guide").fill("Operations Manual");
  await ledger
    .getByPlaceholder("Paste the exact passage that supports a class, relation, entity, or fact...")
    .fill("An operation declares its required parameters.");
  await ledger.getByRole("button", { name: "Save reference" }).click();

  await expect(ledger.getByText("Evidence reference saved")).toBeVisible();
  await expect(ledger.getByText("Operations Manual", { exact: true }).first()).toBeVisible();
  await expect(ledger.getByRole("blockquote")).toHaveText("An operation declares its required parameters.");
});

test("evidence ledger remains usable at a narrow desktop width", async ({ page }) => {
  await page.setViewportSize({ width: 720, height: 900 });
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&tab=evidence`);

  const ledger = page.locator("section[aria-label='evidence-references-page']");
  await expect(ledger.getByPlaceholder("Example: Dify API Guide")).toBeVisible();
  await expect(ledger.getByText("Dify API Guide", { exact: true }).first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});
