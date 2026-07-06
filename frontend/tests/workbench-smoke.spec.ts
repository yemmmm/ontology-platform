import { expect, test, type Page } from "@playwright/test";

const project = { id: "project-1", name: "Supply Chain", description: "Operational model" };
const ontology = {
  id: "ontology-1",
  project_id: project.id,
  current_version_id: "version-1",
  name: "Supply Network",
  description: "Supplier and shipment knowledge",
  status: "active",
};
const version = {
  id: "version-1",
  ontology_id: ontology.id,
  parent_version_id: null,
  version_number: 1,
  status: "draft",
  workflow_status: "gathering",
  schema_snapshot: {},
  graph_snapshot: {},
  publication_report: {},
  created_at: "2026-06-23T00:00:00Z",
  published_at: null,
};
const brief = {
  id: "brief-1",
  project_id: project.id,
  fields: {},
  field_states: {},
  field_sources: {},
  missing_fields: ["domain_name", "business_goal"],
  clarification_items: [],
  completeness: 0,
};
const schemaProposal = {
  id: "proposal-1",
  project_id: project.id,
  ontology_id: ontology.id,
  target_version_id: version.id,
  proposal_type: "schema_change",
  status: "applied",
  source_type: "agent",
  payload: { items: [{ key: "supplier", kind: "class", data: { name: "Supplier" } }] },
  validation_result: {},
  review_result: {},
  application_result: {},
  audit_log: [],
  evidence: [],
  created_at: "2026-06-23T00:00:00Z",
  updated_at: "2026-06-23T00:00:00Z",
  applied_at: "2026-06-23T00:00:00Z",
};
const ruleProposal = {
  ...schemaProposal,
  id: "proposal-rule",
  proposal_type: "rule",
  payload: {
    items: [{
      key: "excellent-student",
      kind: "rule",
      data: {
        rule_type: "classification",
        scope: { class: "student" },
        condition: { ">": [{ property: "average_score" }, 90] },
        conclusion: { assert: { predicate: "student_status", value: "excellent" } },
      },
    }],
  },
};
const buildingClass = {
  id: "building",
  ontology_id: ontology.id,
  name: "Building",
  normalized_label: "building",
  description: null,
  aliases: [],
  parent_class_ids: [],
  external_mappings: {},
};
const labClass = {
  id: "lab",
  ontology_id: ontology.id,
  name: "Lab",
  normalized_label: "lab",
  description: null,
  aliases: [],
  parent_class_ids: ["building"],
  external_mappings: {},
};
const labEntity = {
  id: "lab-1",
  project_id: project.id,
  ontology_id: ontology.id,
  ontology_version_id: version.id,
  class_id: "lab",
  class_label: "Lab",
  name: "Lab 1",
  aliases: [],
  properties: { floor: 2, description: "North wing lab" },
};
const labRelation = {
  id: "rel-lab-self",
  project_id: project.id,
  ontology_id: ontology.id,
  ontology_version_id: version.id,
  relation_type_id: "rt-linked",
  relation_type: "LINKED_TO",
  source_entity_id: "lab-1",
  target_entity_id: "lab-1",
  properties: {},
};
const derivedClaim = {
  id: "claim-rule-1",
  claim_key: "rule_derived:rule-1:s1:student_status:a",
  project_id: project.id,
  ontology_id: ontology.id,
  ontology_version_id: version.id,
  claim_type: "derived",
  layer: "rule_derived",
  subject: { entity_id: "student-1", name: "小明", class_id: "student" },
  predicate: "student_status",
  value: "excellent",
  anchor: { type: "rule", target_id: "rule-1", output_anchor: { type: "entity", target_id: "student-1" } },
  graph_path: [{ node: "student-1", kind: "entity" }, { rule: "rule-1", version: 1 }],
  evidence_ids: [],
  generation_reason: "rule:rule-1",
  confidence: 1,
  sensitivity: "normal",
  access_policy: {},
  override_of_claim_id: null,
  audit_status: "pending",
  review_decision: {},
  linked_fix_proposal_id: null,
  stale: false,
  stale_reason: null,
  created_at: "2026-06-23T00:00:00Z",
  updated_at: "2026-06-23T00:00:00Z",
  reviewed_at: null,
};
const nodeKnowledgeContext = {
  entity: labEntity,
  class_chain: [labClass, buildingClass],
  relation_ids: [labRelation.id],
  properties: [{
    source_type: "entity_property",
    claim_id: null,
    predicate: "floor",
    value: 2,
    anchor: { type: "entity", target_id: labEntity.id },
    layer: null,
    audit_status: null,
    confidence: null,
    sensitivity: null,
    access_policy: {},
    access_decision: null,
    redacted: false,
    evidence_ids: [],
    generation_reason: null,
    relation_id: null,
    rule_id: null,
    inherited_from_class_id: null,
    overrides: null,
    overridden: false,
  }],
  entity_assertions: [],
  inherited_class_assertions: [{
    source_type: "class_assertion",
    claim_id: "claim-class-close",
    predicate: "closes_at",
    value: "23:00",
    anchor: { type: "class", target_id: "building" },
    layer: "class_assertion",
    audit_status: "approved",
    confidence: 1,
    sensitivity: "normal",
    access_policy: {},
    access_decision: "allow",
    redacted: false,
    evidence_ids: [],
    generation_reason: "direct_user_statement",
    relation_id: null,
    rule_id: null,
    inherited_from_class_id: "building",
    overrides: null,
    overridden: false,
  }],
  relation_assertions: [{
    source_type: "relation_assertion",
    claim_id: "claim-relation-verified",
    predicate: "verified_by",
    value: "registry",
    anchor: { type: "relation", target_id: labRelation.id },
    layer: "relation_assertion",
    audit_status: "pending",
    confidence: 0.9,
    sensitivity: "normal",
    access_policy: {},
    access_decision: "allow",
    redacted: false,
    evidence_ids: [],
    generation_reason: "direct_user_statement",
    relation_id: labRelation.id,
    rule_id: null,
    inherited_from_class_id: null,
    overrides: null,
    overridden: false,
  }],
  rule_assertions: [{
    source_type: "rule_derived",
    claim_id: derivedClaim.id,
    predicate: derivedClaim.predicate,
    value: derivedClaim.value,
    anchor: derivedClaim.anchor,
    layer: "rule_derived",
    audit_status: "pending",
    confidence: 1,
    sensitivity: "normal",
    access_policy: {},
    access_decision: "allow",
    redacted: false,
    evidence_ids: [],
    generation_reason: "rule:rule-1",
    relation_id: null,
    rule_id: "rule-1",
    inherited_from_class_id: null,
    overrides: null,
    overridden: false,
  }],
  rules: [{
    id: "rule-1",
    rule_type: "validation",
    scope: { class: "lab" },
    condition: {},
    conclusion: { assert: { predicate: "needs_inspection", value: true } },
    status: "active",
    priority: 1,
    evidence_ids: [],
    version: 1,
  }],
};

async function mockApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    const method = route.request().method();
    let body: unknown = [];
    if (path === "/projects") body = [project];
    else if (path === `/projects/${project.id}/ontologies`) body = [ontology];
    else if (path === `/projects/${project.id}/build-context`) body = {
      project,
      project_brief: brief,
      ontologies: [{ ...ontology, current_version: version }],
      competency_question_counts: {},
    };
    else if (path === `/ontologies/${ontology.id}/build-overview`) body = {
      ontology_id: ontology.id,
      graph_set: {
        graph_set_id: "gs-1",
        members: [
          {
            iri: "https://x/graph/ontology/1",
            role: "asserted_ontology",
            editable: true,
            validation_stale: false,
            reasoning_stale: true,
            rule_stale: false,
            last_semantic_edit_at: "2026-07-05T00:00:00Z",
          },
          {
            iri: "https://x/graph/data/1",
            role: "asserted_data",
            editable: true,
            validation_stale: false,
            reasoning_stale: false,
            rule_stale: false,
            last_semantic_edit_at: null,
          },
        ],
        missing_evidence_count: 4,
        last_semantic_edit_at: "2026-07-05T00:00:00Z",
      },
      project_brief: { completeness: 0.5, missing_fields: ["scope"] },
      competency_questions: {
        total: 3,
        by_status: { draft: 1, approved: 0, testable: 0, passed: 2, failed: 0 },
      },
      next_actions: [
        { key: "complete_brief", label: "完善 Project Brief", detail: "1 个字段待处理", tab: "brief" },
        { key: "approve_questions", label: "批准能力问题", detail: "1 个草稿待批准", tab: "questions" },
        { key: "recompute_derived", label: "重新运行推理 / 规则", detail: "派生结果已过期", tab: "governance" },
      ],
    };
    else if (path === `/projects/${project.id}/brief`) body = brief;
    else if (path.startsWith(`/projects/${project.id}/competency-questions`)) body = [];
    else if (path === `/projects/${project.id}/data-sources`) body = [];
    else if (path === `/projects/${project.id}/data-resources`) body = [];
    else if (path === `/projects/${project.id}/external-fields`) body = [];
    else if (path.startsWith(`/projects/${project.id}/semantic-mappings`)) body = [];
    else if (path === `/projects/${project.id}/connector-templates`) body = [];
    else if (path === `/ontologies/${ontology.id}/versions`) body = [version];
    else if (path === `/ontologies/${ontology.id}/classes`) body = [buildingClass, labClass];
    else if (path === `/classes/${buildingClass.id}/properties`) body = [];
    else if (path === `/classes/${labClass.id}/properties`) body = [];
    else if (path === `/ontologies/${ontology.id}/relation-types`) body = [];
    else if (path === `/ontologies/${ontology.id}/entities`) body = [labEntity];
    else if (path === `/ontologies/${ontology.id}/relations`) body = [labRelation];
    else if (path === `/ontologies/${ontology.id}/proposals`) body = [schemaProposal, ruleProposal];
    else if (path === `/versions/${version.id}/fact-claims`) body = [derivedClaim];
    else if (path === `/versions/${version.id}/entities/${labEntity.id}/knowledge-context`) body = nodeKnowledgeContext;
    else if (method === "POST" && path === `/versions/${version.id}/rule-definitions:execute`) body = [derivedClaim];
    else if (method === "POST" && path === `/versions/${version.id}/background-knowledge:recall`) body = [{
      source_type: "background_recall",
      knowledge_id: "bg-1",
      text: "8 小时睡眠能保证上课状态",
      summary: "Sleep background",
      tags: ["sleep"],
      confidence: 0.6,
      score: 1,
      core_fact: false,
    }];
    else if (method === "PATCH" && path === `/versions/${version.id}/mutability`) body = { ...version, status: "published", workflow_status: "published", published_at: "2026-06-23T00:00:00Z" };
    else if (path === `/versions/${version.id}/publication-readiness`) body = {
      version_id: version.id,
      ready: false,
      gates: [{ gate_type: "schema_validation", status: "failed", details: { errors: ["sample"] } }],
      blocking: ["schema_validation"],
      warnings: [],
    };
    else if (path === "/health/dependencies") body = { postgres: { status: "ok" }, neo4j: { status: "ok" } };
    await route.fulfill({ json: body });
  });
}

for (const viewport of [{ width: 1280, height: 900 }, { width: 768, height: 900 }]) {
  test(`workbench navigation at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await mockApi(page);
    await page.goto("/");
    await expect(page.getByText("Supply Network", { exact: true })).toBeVisible();
    await page.getByText("Supply Network", { exact: true }).click();
    await expect(page.getByRole("heading", { name: "构建概览" })).toBeVisible();

    for (const [nav, heading] of [
      ["Brief", "Project Brief"],
      ["Questions", "Competency Questions"],
      ["Facts", "Fact Audit"],
      ["Publication", "Publication"],
      ["Versions", "Versions"],
      ["Catalog", "Data Catalog"],
      ["Evidence", "Evidence Explorer"],
    ] as const) {
      await page.locator(".navStageButton").filter({ hasText: nav }).first().click();
      await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
      if (nav === "Publication") await expect(page.getByRole("switch")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `${nav} should not overflow the ${viewport.width}px viewport`).toBeLessThanOrEqual(1);
    }

    await expect(page.locator(".workflowProgressItem.current")).toBeVisible();
  });
}

test("v0.5 fact audit exposes rule execution and background recall", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=facts`);
  await expect(page.getByRole("heading", { name: "Fact Audit" })).toBeVisible();
  await expect(page.getByText("rule derived").first()).toBeVisible();
  await page.getByRole("button", { name: "Run rules" }).click();
  await expect(page.getByText(/created 1 derived assertions/i)).toBeVisible();
  await page.getByPlaceholder("Search unanchored knowledge without treating it as governed fact").fill("sleep");
  await page.getByRole("button", { name: "Recall" }).click();
  await expect(page.getByText("background_recall")).toBeVisible();
  await expect(page.getByText("Sleep background")).toBeVisible();
});

test("entity graph drawer shows inherited relation and rule knowledge", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=entities`);
  const canvas = page.locator(".entityGraphCanvas");
  await expect(canvas).toBeVisible();
  await expect(canvas).toHaveAttribute("data-single-visible-entity-id", labEntity.id);
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await page.waitForTimeout(500);
  await canvas.evaluate((element) => {
    element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
  });
  const heading = page.getByRole("heading", { name: "Lab 1" });
  for (const xRatio of [0.5, 0.35, 0.65, 0.2, 0.8]) {
    for (const yRatio of [0.5, 0.35, 0.65, 0.2, 0.8]) {
      await page.mouse.click(box!.x + box!.width * xRatio, box!.y + box!.height * yRatio);
      if (await heading.isVisible().catch(() => false)) break;
    }
    if (await heading.isVisible().catch(() => false)) break;
  }
  await expect(page.getByRole("heading", { name: "Lab 1" })).toBeVisible();
  await page.getByRole("button", { name: "Knowledge" }).click();
  await expect(page.getByText("Inherited class knowledge")).toBeVisible();
  await expect(page.getByText("closes_at")).toBeVisible();
  await expect(page.getByText("verified_by")).toBeVisible();
  await expect(page.getByText("student_status")).toBeVisible();
  await page.getByRole("button", { name: "Rules" }).click();
  await expect(page.getByText("validation")).toBeVisible();
  await expect(page.getByText("Produced assertions")).toBeVisible();
});

test("publication mutability switch locks the current version", async ({ page }) => {
  await mockApi(page);
  const toggleRequest = page.waitForRequest(
    (request) => request.url().includes(`/versions/${version.id}/mutability`) && request.method() === "PATCH",
  );
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=publication`);
  await page.getByRole("switch").click();
  await toggleRequest;
  await expect(page.getByText("Version edit switch")).toBeVisible();
});

test("catalog wizard renders step indicator and Test toggle", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&version=${version.id}&tab=catalog`);
  await expect(page.getByRole("heading", { name: "Data Catalog" })).toBeVisible();
  await expect(page.getByText("数据源 · Step 1 / 5")).toBeVisible();
  await expect(page.getByRole("button", { name: "创建并继续" })).toBeVisible();
  await page.getByRole("tab", { name: /Test/ }).click();
  await expect(page.getByText("Governed connector query").first()).toBeVisible();
  await expect(page.getByText("Identifier resolution analysis").first()).toBeVisible();
});

test("BuildOverview shows graph-set panel and next actions", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/?project=${project.id}&ontology=${ontology.id}&tab=overview`);
  await expect(page.getByRole("heading", { name: "构建概览" })).toBeVisible();
  await expect(page.getByText("活跃 Graph Set 状态")).toBeVisible();
  await expect(page.getByText("完善 Project Brief")).toBeVisible();
  await expect(page.getByText("重新运行推理 / 规则")).toBeVisible();
});
