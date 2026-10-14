import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

/**
 * Live-contract smoke: drives the running backend at :8001 (no mocks).
 * Verifies the integration test plan's runtime spine + governance +
 * Single-model reads/writes and retired capability contracts against real Oxigraph.
 *
 * Pre-conditions:
 *   - backend up at http://127.0.0.1:8001
 *   - Oxigraph reachable at http://127.0.0.1:7878
 *
 * Each test uses a unique graph scope so they don't trip on each
 * other's data. Requests go through the vite dev server's /api proxy
 * (same-origin), matching what the real frontend (semanticApi.ts) does.
 */

let counter = 0;
const cleanupProjects = new Set<string>();
const cleanupGraphs = new Set<string>();
function protectedLiveApiKey(): string {
  if (process.env.ONTOLOGY_PLAYWRIGHT_API_KEY) return process.env.ONTOLOGY_PLAYWRIGHT_API_KEY;
  try {
    const credentialPath = new URL(
      "../../backend/.local/ontology-platform-bootstrap.json",
      import.meta.url,
    );
    const credentials = JSON.parse(readFileSync(credentialPath, "utf8")) as { api_key?: string };
    return credentials.api_key ?? "";
  } catch {
    return "";
  }
}

const liveApiKey = protectedLiveApiKey();

function requireLiveApiKey() {
  if (!liveApiKey) {
    throw new Error("Protected local live-contract credentials are unavailable.");
  }
}

const modelTurtle = `
@prefix ex: <http://example.test/> .
@prefix op: <http://ontology-platform.local/semantic/vocab/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:Person a owl:Class ; rdfs:label "Person" .
ex:Organization a owl:Class ; rdfs:label "Organization" .
ex:worksFor a owl:ObjectProperty .
ex:acme a owl:NamedIndividual, ex:Organization ; op:id "acme" ; rdfs:label "Acme" ; ex:name "Acme" .
ex:alice a owl:NamedIndividual, ex:Person ; op:id "alice" ; rdfs:label "Alice" ; ex:name "Alice" ; ex:worksFor ex:acme .
`;

async function createModel(page: Page) {
  requireLiveApiKey();
  const project = await apiPost(page, "/projects", { name: `Single model ${Date.now()}-${counter += 1}` });
  expect(project.status).toBe(201);
  cleanupProjects.add(project.json.id);
  const ontology = await apiPost(page, `/projects/${project.json.id}/ontologies`, { name: "Business model" });
  expect(ontology.status).toBe(201);
  // Internal locator used solely to clean this isolated test's RDF artifact.
  cleanupGraphs.add(`http://ontology-platform.local/semantic/graph/ontology/${ontology.json.id}`);
  return { projectId: project.json.id, ontologyId: ontology.json.id };
}

async function apiPost(page: Page, path: string, body: unknown) {
  if (!page.url().startsWith("http://127.0.0.1:5173")) {
    await page.goto("/").catch(() => undefined);
  }
  return page.evaluate(
    async ({ path, body, apiKey }) => {
      const res = await fetch(`/api${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify(body),
      });
      return { status: res.status, json: await res.json().catch(() => null) };
    },
    { path, body, apiKey: liveApiKey },
  );
}

async function apiGet(page: Page, path: string) {
  if (!page.url().startsWith("http://127.0.0.1:5173")) {
    await page.goto("/").catch(() => undefined);
  }
  return page.evaluate(async ({ path, apiKey }) => {
    const res = await fetch(`/api${path}`, {
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    return { status: res.status, json: await res.json().catch(() => null) };
  }, { path, apiKey: liveApiKey });
}

test.describe("semantic live-contract (real backend + Oxigraph)", () => {
  test.afterEach(async ({ request }) => {
    for (const projectId of cleanupProjects) {
      const response = await request.delete(`http://127.0.0.1:8001/api/projects/${projectId}`, {
        headers: { Authorization: `Bearer ${liveApiKey}` },
      });
      expect(response.status(), `cleanup Project ${projectId}`).toBe(204);
    }
    cleanupProjects.clear();
    for (const graph of cleanupGraphs) {
      const response = await request.delete(
        `http://127.0.0.1:7878/store?graph=${encodeURIComponent(graph)}`,
      );
      expect(response.ok(), `cleanup graph ${graph}`).toBeTruthy();
    }
    cleanupGraphs.clear();
  });

  test("single model: ontology writes, governed reads and rejected write-SPARQL", async ({ page }) => {
    const { projectId, ontologyId } = await createModel(page);
    const workspace = await apiGet(page, `/ontologies/${ontologyId}/workspace-context`);
    expect(workspace.status).toBe(200);
    expect(workspace.json.ontology_id).toBe(ontologyId);
    for (const field of ["graph_set_id", "members", "source_graph_iri", "model_graph_iri"]) expect(workspace.json).not.toHaveProperty(field);
    const edit = await apiPost(page, "/semantic/edits", { ontology_id: ontologyId, format: "turtle", content: modelTurtle });
    expect(edit.status, JSON.stringify(edit.json)).toBe(200);
    const scope = { project_id: projectId, scope_mode: "ontologies", ontology_ids: [ontologyId] };
    const query = await apiPost(page, "/semantic/sparql:query", { ...scope, query: "PREFIX ex: <http://example.test/> SELECT ?s ?n WHERE { ?s ex:name ?n }" });
    expect(query.status, JSON.stringify(query.json)).toBe(200);
    expect(query.json.result.results.bindings.map((b: { n: { value: string } }) => b.n.value).sort()).toEqual(["Acme", "Alice"]);
    const context = await apiPost(page, "/semantic/context:query", { ...scope, query: "Alice worksFor Acme", depth: 1 });
    expect(context.status, JSON.stringify(context.json)).toBe(200);
    expect(context.json.result_status).toBe("matched");
    expect(context.json.primary_matches.every((r: { ontology_id: string }) => r.ontology_id === ontologyId)).toBe(true);
    expect(JSON.stringify(context.json)).not.toContain('"source_graph_iri"');
    const write = await apiPost(page, "/semantic/sparql:query", { ...scope, query: 'DELETE DATA { <urn:a> <urn:b> "z" }' });
    expect(write.status).toBe(400);
    expect(write.json.detail.code).toBe("invalid_query");
  });

  test("ontology edits preserve versions and reject malformed RDF and retired graph selectors", async ({ page }) => {
    const { ontologyId } = await createModel(page);
    const before = await apiGet(page, `/ontologies/${ontologyId}/workspace-context`);
    const good = await apiPost(page, "/semantic/edits", { ontology_id: ontologyId, format: "turtle", content: modelTurtle });
    expect(good.status, JSON.stringify(good.json)).toBe(200);
    expect(good.json.applied).toBe(true);
    const after = await apiGet(page, `/ontologies/${ontologyId}/workspace-context`);
    expect(after.json.model_revision).toBeGreaterThan(before.json.model_revision);
    const bad = await apiPost(page, "/semantic/edits", { ontology_id: ontologyId, format: "turtle", content: "GARBAGE not valid turtle" });
    expect(bad.status).toBe(400);
    const selector = await apiPost(page, "/semantic/edits", { ontology_id: ontologyId, format: "turtle", content: modelTurtle, target_graph_iri: "urn:other" });
    expect(selector.status).toBe(422);
  });

  test("GraphSet, SHACL, OWL and executable rules stay retired; generic model reads work", async ({ page }) => {
    const { ontologyId } = await createModel(page);
    const edit = await apiPost(page, "/semantic/edits", { ontology_id: ontologyId, format: "turtle", content: modelTurtle });
    expect(edit.status, JSON.stringify(edit.json)).toBe(200);
    for (const path of ["/semantic/graph-sets", `/semantic/ontologies/${ontologyId}/validation-runs`, `/semantic/ontologies/${ontologyId}/reasoning-runs`, "/semantic/rule-definitions"]) {
      const retired = await apiPost(page, path, {});
      expect([404, 410]).toContain(retired.status);
    }
    const model = await apiGet(page, `/semantic/ontologies/${ontologyId}/read-models/resource-list?include=asserted&field_set=detail`);
    expect(model.status, JSON.stringify(model.json)).toBe(200);
    expect(model.json.items.some((r: { iri: string }) => r.iri === "http://example.test/alice")).toBe(true);
    expect(model.json.items.every((r: { ontology_id: string }) => r.ontology_id === ontologyId)).toBe(true);
    expect(JSON.stringify(model.json)).not.toContain('"source_graph_iri"');
  });

  test("frontend dev server renders home page", async ({ page }) => {
    const res = await page.goto("/");
    expect(res?.status()).toBe(200);
    await expect(page.locator("#root")).not.toBeEmpty({ timeout: 10_000 });
    await expect(page).toHaveTitle(/OntoWeave/i);
  });
});
