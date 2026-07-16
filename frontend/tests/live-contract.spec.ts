import { expect, test, type Page } from "@playwright/test";

/**
 * Live-contract smoke: drives the running backend at :8001 (no mocks).
 * Verifies the integration test plan's runtime spine + governance +
 * rule derivation actually work end-to-end against real Oxigraph.
 *
 * Pre-conditions:
 *   - backend up at http://127.0.0.1:8001
 *   - Oxigraph reachable at http://127.0.0.1:7878
 *
 * Each test uses a unique graph scope so they don't trip on each
 * other's data. Requests go through the vite dev server's /api proxy
 * (same-origin), matching what the real frontend (semanticApi.ts) does.
 */

interface GraphScope {
  ontology: string;
  data: string;
  shapes: string;
  evidence: string;
  policy: string;
}

let counter = 0;
function uniqueScope(): GraphScope {
  counter += 1;
  const id = `${Date.now()}-${counter}`;
  const base = "http://ontology-platform.local/semantic/graph";
  return {
    ontology: `${base}/ontology/live-${id}`,
    data: `${base}/data/live-${id}`,
    shapes: `${base}/shapes/live-${id}`,
    evidence: `${base}/evidence/live-${id}`,
    policy: `${base}/policy/live-${id}`,
  };
}

function seedTrig(s: GraphScope): string {
  return `
@prefix ex: <http://example.test/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix prov: <http://www.w3.org/ns/prov#> .

<${s.ontology}> {
  ex:Person a owl:Class ; rdfs:label "Person" .
  ex:Organization a owl:Class ; rdfs:label "Organization" .
  ex:name a owl:DatatypeProperty ; rdfs:domain ex:Person ; rdfs:range xsd:string .
  ex:age a owl:DatatypeProperty ; rdfs:domain ex:Person ; rdfs:range xsd:integer .
  ex:worksFor a owl:ObjectProperty ; rdfs:domain ex:Person ; rdfs:range ex:Organization .
}

<${s.data}> {
  ex:acme a ex:Organization ; ex:name "Acme" .
  ex:alice a ex:Person ; ex:name "Alice" ; ex:age 30 ; ex:worksFor ex:acme .
}

<${s.shapes}> {
  ex:PersonShape a sh:NodeShape ;
    sh:targetClass ex:Person ;
    sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:datatype xsd:string ] .
}

<${s.evidence}> {
  <http://ontology-platform.local/semantic/evidence/live-ev> a prov:Entity .
}

<${s.policy}> {
  ex:PublicPolicy a owl:Ontology .
}
`;
}

async function apiPost(page: Page, path: string, body: unknown) {
  if (!page.url().startsWith("http://127.0.0.1:5173")) {
    await page.goto("/").catch(() => undefined);
  }
  return page.evaluate(
    async ({ path, body }) => {
      const res = await fetch(`/api${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      return { status: res.status, json: await res.json().catch(() => null) };
    },
    { path, body },
  );
}

async function apiGet(page: Page, path: string) {
  if (!page.url().startsWith("http://127.0.0.1:5173")) {
    await page.goto("/").catch(() => undefined);
  }
  return page.evaluate(async (path) => {
    const res = await fetch(`/api${path}`);
    return { status: res.status, json: await res.json().catch(() => null) };
  }, path);
}

test.describe("semantic live-contract (real backend + Oxigraph)", () => {
  test("runtime spine: load → query → write-SPARQL rejected", async ({ page }) => {
    const suffix = `${Date.now()}-${counter += 1}`;
    const project = await apiPost(page, "/projects", { name: `R006 Live ${suffix}` });
    expect(project.status).toBe(201);
    const ontology = await apiPost(page, `/projects/${project.json.id}/ontologies`, {
      name: `R006 Ontology ${suffix}`,
    });
    expect(ontology.status).toBe(201);
    const workspace = await apiGet(page, `/ontologies/${ontology.json.id}/workspace-context`);
    expect(workspace.status).toBe(200);
    const members = Object.fromEntries(
      (workspace.json.members as Array<{ role: string; graph_iri: string }>).map((member) => [
        member.role,
        member.graph_iri,
      ]),
    );
    const s: GraphScope = {
      ontology: members.asserted_ontology,
      data: members.asserted_data,
      shapes: members.shapes,
      evidence: `${members.policy}/evidence-not-in-query-scope`,
      policy: members.policy,
    };
    await apiPost(page, "/semantic/datasets:load", {
      format: "trig",
      base_iri: "http://ontology-platform.local/semantic/",
      content: seedTrig(s),
    });

    const q = await apiPost(page, "/semantic/sparql:query", {
      project_id: project.json.id,
      scope_mode: "ontologies",
      ontology_ids: [ontology.json.id],
      query: `PREFIX ex: <http://example.test/> SELECT ?s ?n WHERE { GRAPH <${s.data}> { ?s ex:name ?n } }`,
    });
    expect(q.status, JSON.stringify(q.json)).toBe(200);
    const names = (q.json.result.results.bindings as Array<{ n?: { value: string } }>)
      .map((b) => b.n?.value)
      .sort();
    expect(names).toEqual(["Acme", "Alice"]);

    const context = await apiPost(page, "/semantic/context:query", {
      project_id: project.json.id,
      scope_mode: "ontologies",
      ontology_ids: [ontology.json.id],
      query: "Alice worksFor Acme",
      depth: 1,
    });
    expect(context.status, JSON.stringify(context.json)).toBe(200);
    expect(context.json.result_status).toBe("matched");
    expect(context.json.primary_matches.length).toBeGreaterThan(0);
    expect(JSON.stringify(context.json)).not.toContain("graph_iri");
    expect(JSON.stringify(context.json)).not.toContain("graph_set");
    expect(JSON.stringify(context.json)).not.toContain("excerpt");

    const write = await apiPost(page, "/semantic/sparql:query", {
      project_id: project.json.id,
      scope_mode: "ontologies",
      ontology_ids: [ontology.json.id],
      query: `DELETE DATA { <http://example.test/x> <http://example.test/y> "z" }`,
    });
    expect(write.status).toBe(400);
    expect(write.json.detail.code).toBe("invalid_query");
  });

  test("governed edits accept valid Turtle and reject malformed RDF with 400", async ({ page }) => {
    const s = uniqueScope();
    await apiPost(page, "/semantic/datasets:load", {
      format: "trig",
      base_iri: "http://ontology-platform.local/semantic/",
      content: seedTrig(s),
    });

    const good = await apiPost(page, "/semantic/edits", {
      format: "turtle",
      content: `@prefix ex: <http://example.test/> . ex:bob a ex:Person ; ex:name "Bob" .`,
      target_graph_iri: s.data,
      actor: "live-contract",
      reason: "valid edit",
      evidence_status: "evidence_bound",
      warning_state: {},
    });
    expect(good.status).toBe(200);
    expect(good.json.applied).toBe(true);
    expect(good.json.delta.triple_count).toBeGreaterThan(0);
    expect(good.json.graph_revisions[s.data]).toBeGreaterThanOrEqual(1);

    const bad = await apiPost(page, "/semantic/edits", {
      format: "turtle",
      content: "GARBAGE not valid turtle",
      target_graph_iri: s.data,
      actor: "live-contract",
      reason: "malformed",
      evidence_status: "evidence_bound",
      warning_state: {},
    });
    expect(bad.status).toBe(400);
    const detail = typeof bad.json.detail === "string" ? bad.json.detail : bad.json.detail?.message;
    expect(detail).toContain("RDF parse error");
  });

  test("graph-set validation + CONSTRUCT rule (no LIMIT) succeed against Oxigraph", async ({ page }) => {
    const s = uniqueScope();
    await apiPost(page, "/semantic/datasets:load", {
      format: "trig",
      base_iri: "http://ontology-platform.local/semantic/",
      content: seedTrig(s),
    });

    const gs = await apiPost(page, "/semantic/graph-sets", {
      name: `live-${Date.now()}`,
      scope_type: "ontology_version",
      scope_id: `live-${Date.now()}`,
      members: [
        { graph_iri: s.ontology, role: "ontology", sort_order: 1 },
        { graph_iri: s.data, role: "data", sort_order: 2 },
        { graph_iri: s.shapes, role: "shapes", sort_order: 3 },
        { graph_iri: s.evidence, role: "evidence", sort_order: 4 },
        { graph_iri: s.policy, role: "policy", sort_order: 5 },
      ],
      created_by: "live-contract",
    });
    if (gs.status !== 200 && gs.status !== 201) {
      throw new Error(`graph-set create failed: ${gs.status} ${JSON.stringify(gs.json)}`);
    }
    const gsId = gs.json.id;

    const sh = await apiPost(page, `/semantic/graph-sets/${gsId}/validation-runs`, {});
    expect(sh.status).toBe(200);
    expect(sh.json.status).toBe("succeeded");
    expect(sh.json.conforms).toBe(true);

    const rule = await apiPost(page, "/semantic/rule-definitions", {
      rule_iri: `http://ontology-platform.local/semantic/rule/live-${Date.now()}`,
      name: "Derive employment label",
      language: "sparql_construct",
      body: {
        template: `PREFIX ex: <http://example.test/> CONSTRUCT { ?person ex:employmentLabel "active" } WHERE { GRAPH <${s.data}> { ?person ex:worksFor ?org } }`,
      },
      input_roles: ["asserted_data"],
      output_kind: "assertion",
      status: "active",
      created_by: "live-contract",
    });
    expect(rule.status).toBe(200);

    const run = await apiPost(page, `/semantic/graph-sets/${gsId}/rule-runs`, {
      rule_definition_id: rule.json.id,
      promote_pointer: true,
      actor: "live-contract",
    });
    expect(run.status).toBe(200);
    expect(run.json.status).toBe("succeeded");
    expect(run.json.generated_statement_count).toBeGreaterThan(0);
    expect(run.json.derived_pointer?.status).toBe("current");
  });

  test("frontend dev server renders home page", async ({ page }) => {
    const res = await page.goto("/");
    expect(res?.status()).toBe(200);
    await expect(page.locator("#root")).not.toBeEmpty({ timeout: 10_000 });
    await expect(page).toHaveTitle(/Ontology Platform/i);
  });
});
