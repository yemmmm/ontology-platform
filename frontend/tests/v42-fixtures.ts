import type { Page, Route } from "@playwright/test";
export const project = { id: "p1", name: "维修项目", description: "维修业务与外部接口的语义范围。" };
export const secondProject = { id: "p2", name: "Integration", description: null };
export const ontologies = [{ id: "o1", name: "Service" }, { id: "o2", name: "Integration" }];
export function artifact(kind: string, data: Record<string, unknown>, id = kind, time = "2026-10-07T10:00:00Z") {
  return { artifact_id: id, kind, availability: "available", data, source: { path: `public/${id}`, updated_at: time }, limitations: [], scope: { phase: "L1", slices: ["maintenance"] } };
}
export function report(id = "report-current", applicability = "verified_current") {
  return artifact("reports", { applicability, denominator: 3, public_count: 2, full_pass: false,
    verdicts: [{ question_id: "Q1", verdict: "pass" }, { question_id: "Q1", verdict: "pass" }], unexecuted_question_ids: ["Q2"],
    hidden_summary: { verdict_counts: { "pending-review": 1 }, unexecuted_count: 0 }, summary_by_scope: { slice: { pass: 1, "not-executed": 1 } }, coverage_gaps: { cross_slice_projection_gap: true },
  }, id);
}
export function index(runs = [{ run_id: "r1", state: "RUNNING", source_updated_at: "2026-10-07T10:00:00Z" }], current: string | null = "r1", complete = true) {
  return { current_run_id: current, runs, completeness: { complete }, observed_at: "2026-10-07T10:10:00Z" };
}
export function run() {
  return { run_id: "r1", state: "RUNNING", observed_at: "2026-10-07T10:10:00Z", artifacts: {
    competency_questions: [artifact("competency_questions", { batch_id: "batch1", snapshot_digest: "digest1", questions: [{ question_id: "Q1", question: "谁可以关闭工单？", scope: "maintenance", content_version: 1, answer_points: ["ANSWER_SENTINEL"] }] }, "cq1"), artifact("competency_questions", { batch_id: "batch2", snapshot_digest: "digest2", questions: [{ question_id: "Q1", question: "复查工单如何保持独立？", scope: "cross_slice", review_content_version: 2 }] }, "cq2")],
    host: [artifact("cq-freeze", { records: [{ batch_id: "batch2", snapshot_digest: "digest2", recorded_at: "2026-10-07T10:00:00Z" }] })],
    reports: [report(), artifact("public_regression_report", { full_pass: true, denominator: 50 }, "regression")],
  } };
}
export function resource(iri: string, label: string, role?: string, meaning = "已记录业务含义") {
  return { iri, label, source_graph_iri: "urn:graph:data", detail_fields: { semantic_definition: { ...(role ? { semantic_role: role } : {}), business_meaning: meaning, applicability: "maintenance" } } };
}
export const resources = [
  resource("urn:work", "工单", "object"), resource("urn:process", "关闭流程", "process"),
  resource("urn:unknown", "未知声明", "custom"), resource("urn:class", "工单定义"),
  resource("urn:property", "状态属性"), resource("urn:relation", "父单关系"), resource("urn:loose", "无分类节点"),
  resource("urn:operation", "关闭操作", "behavior"), resource("urn:mapping", "字段映射", "data_mapping"), resource("urn:metric", "完成时长"),
  resource("urn:same-name", "工单", "rule"), resource("urn:role", "维修责任", "business_role"), resource("urn:interface", "关闭接口", "interface_mapping"),
];
export function envelope(items: unknown[], signature = "sig1", complete = true) { return { items, source_signature: signature, paging: { complete }, warnings: [] }; }
export const relations = [{ id: "e1", source: "urn:work", target: "urn:process", relation: "urn:hasProcess", source_graph_iri: "urn:graph:data", assertion_kind: "asserted" }];
export function recall(items: unknown[], cursor: string | null = null) { return { primary_matches: items, related_context: [{ kind: "fact", id: "FACT_SENTINEL" }], result_status: "matched", matches_page: { complete: !cursor, next_match_cursor: cursor }, recall: { completeness: "complete" }, warnings: [] }; }
export function match(id: string, label = id) { return { id, iri: `urn:${id}`, label, ontology_id: "o1", kind: "instance", description: "已记录摘要" }; }
type Options = { projects?: unknown[]; ontologies?: unknown[]; index?: unknown; run?: unknown; roles?: unknown; handler?: (path: string, route: Route) => Promise<boolean> };
export async function mockWorkspace(page: Page, options: Options = {}) {
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname.replace(/^\/api/, "");
    if (options.handler && await options.handler(path, route)) return;
    let data: unknown = [];
    if (path === "/auth/me" || path === "/auth/login") data = { actor: "user:test-admin", scopes: ["admin", "read", "write"], project_id: null };
    else if (path === "/auth/logout") { await route.fulfill({ status: 204, body: "" }); return; }
    else if (path === "/projects") data = options.projects ?? [project, secondProject];
    else if (path.endsWith("/workbench")) data = options.index ?? index();
    else if (path.includes("/workbench/runs/")) data = options.run ?? run();
    else if (path.endsWith("/ontologies")) data = options.ontologies ?? ontologies;
    else if (path.endsWith("/workspace-context")) data = { default_graph_set_id: path.includes("o2") ? "g2" : "g1" };
    else if (path.endsWith("/resource-list")) data = envelope(path.includes("g2") ? [resource("urn:work", "Work order", "process", "integration meaning")] : resources);
    else if (path.endsWith("/resource-relations")) data = envelope(path.includes("g2") ? [] : relations);
    else if (path.endsWith("/semantic-access-roles")) data = options.roles ?? [{ id: "role1", name: "Reader", description: "Scope reader", grants: ["context:query", "read:model"] }, { id: "role2", name: "Empty", description: null, grants: [] }];
    else if (path === "/semantic/context:query") data = recall([]);
    await route.fulfill({ json: data });
  });
}
