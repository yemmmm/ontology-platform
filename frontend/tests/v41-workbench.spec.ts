import {expect,test,type Page,type TestInfo} from "@playwright/test";
const project={id:"v41-project",name:"项目工作台",description:"维修业务定义；不导入业务行"};
const ontology={id:"v41-ontology",project_id:project.id,name:"业务模型",status:"active",description:null};
const gs={id:"v41-gs",name:"业务模型范围",scope_type:"ontology",scope_id:ontology.id,status:"active",members:[],current_pointers:[],source_signature:"model-version-2"};
const views=["object","behavior","rule","business_role","process","data_mapping","interface_mapping"];
const resources=views.map((role,index)=>({iri:`https://example.test/${role}`,label:`定义${index+1}`,kind:"instance",ontology_id:ontology.id,assertion_kind:"asserted",detail_fields:{semantic_definition:{semantic_role:role,business_meaning:`含义${index+1}`,applicability:"当前维修切片",unknowns:["未确认业务口径"]},...(role==="behavior"?{action_definition:{object_applicability:"目标工单",input_parameters:["目标对象","布尔观察"],preconditions:["输入属于目标"],success_effects:["返回计算结果"],responsibilities:["主管"],operation_bindings:[]}}:{}),...(role==="rule"?{rule_definition:{script_source:"def evaluate(v):\n  return 'unknown' if v is None else v",script_language:"python",script_version:"3.11/v1",execution_environment:"外部Consumer",input_parameters:["可选布尔"],output_parameters:["eligible/unknown"],null_semantics:"缺失不是false",failure_semantics:"外部Consumer报告",side_effects:"无业务写入"}}:{}),...(role==="process"?{object_positions:[{position_id:"original-order",definition_ref:"https://example.test/object"},{position_id:"followup-order",definition_ref:"https://example.test/object"}],calls:[{action_ref:"https://example.test/behavior",target:"original-order"},{action_ref:"https://example.test/behavior",target:"followup-order"}],parameter_sources:["各目标自己的观察"],branch:"unknown分支待确认",loop:"逐项请求",output_conditions:["明确created"]}:{}),...(role==="data_mapping"?{mapping_definition:{row_grain:"一行一个工单",technical_keys:["work_order_id"],business_keys:["work_order_number"],join_cardinality:"1:N",encoding:"R→RESOLVED",conversion_rule:"API身份转换未知",metric_definition:"分母规则待确认"}}:{}),...(role==="interface_mapping"?{mapping_definition:{system:"service-gateway",interface_version:"v1",request_location:"body.reason",response_location:"body.requestId",mapping_direction:"response_to_parameter",object_positions:["original-order"],operation_iri:"https://example.test/op/close",binding_iri:"https://example.test/binding/close-v1"}}:{}),...(role==="business_role"?{responsibilities:["主管维护关闭合同"],participation:["审核原工单及复查工单"]}:{})}}));
function artifact(kind:string,data:unknown,id=kind){return {artifact_id:id,kind,availability:"available",schema_version:"fixture-v1",version:2,source:{path:`run-fixture/${id}.json`,updated_at:"2026-10-07T00:00:00Z",sha256:"sha256:fixture"},observed_at:"2026-10-07T00:01:00Z",scope:{project_id:project.id,run_id:"run-fixture",ontology_ids:[ontology.id]},limitations:[],data};}
const artifacts={
  competency_questions:[artifact("competency_questions",{batch_id:"batch-public",snapshot_digest:"freeze-2",projection_digest:"public-2",review_binding:{review_id:"review-2",review_content_version:2,decision_digest:"approved-2"},questions:[{question_id:"P1",question:"原工单与复查工单为何复用定义而保持独立？",answer_points:["共同身份","独立对象位置"],review_content_version:2,scope:{kind:"cross_slice",slice_ids:["service","integration"]},unknown:["外部执行未验"]}]})],
  scenario_map:[artifact("scenario_map",{slices:[{slice_id:"service",name:"服务切片",scope:"工单关闭定义",owner:"modeling",status:"analyzed",viewpoints:[{viewpoint:"object",status:"modeled",note:"已表达未应用",candidate_refs:[{candidate_id:"candidate1",revision:2,item_ids:["shared-order"]}]},{viewpoint:"role",status:"unknown",note:"职责待确认"}]}],shared_terms:[{definition_id:"shared-order",term:"工单",owner_slice:"service",used_by_slices:["service","integration"],candidate_refs:[{candidate_id:"candidate1",revision:2}]}],cross_slice_dependencies:[{from_slice:"integration",to_slice:"service",direction:"uses",connection_points:["shared-order"]}],adjustments:[{kind:"reference_review",reason:"新关闭输入"}],explicit_unknowns:[{topic:"外部绑定",status:"unknown"}]})],
  candidates:[artifact("candidates",{candidate_id:"candidate1",revision:2,items:[{item_id:"shared-order",item_kind:"entity",value:{entity_id:"order",semantic_definition:{semantic_role:"object",business_meaning:"共享工单定义"}},unknowns:["数据行不入图"]}]})],
  materialization:[artifact("materialization_ledger",{status:"dry_run_complete",projection_digest:"same-content-2",entries:[{candidate_id:"candidate1",candidate_revision:2,item_ids:["shared-order"],status:"not_applied",applied_attempt_id:null}]})],
  public_feedback:[artifact("public_feedback",{purpose:"early_public_feedback",formal_acceptance:false,feedback_summary:"使用反馈：参数来源仍未知",first_failure:{failure_layer:"modeling-quality",code:"source_unknown"}})],
  reports:[artifact("public_regression_report",{denominator:3,public_count:1,full_pass:false,applicability:"binding_unknown",applicability_limitations:["live_model_and_freeze_binding_not_reverified"],verdicts:[{question_id:"P1",verdict:"model-recall-insufficient",note:"保留原裁决",answer_point_diagnostics:[{point_id:"A1",diagnosis:"retrieval",verdict:"incomplete",cause:"原因未确定"},{point_id:"A2",diagnosis:"consumer_understanding",verdict:"pending-review",cause:"待复核"}]}],unexecuted_question_ids:["P2"],hidden_summary:{verdict_counts:{pass:1},unexecuted_count:1},summary_by_scope:{cross_slice:{"model-recall-insufficient":1}},freeze_digest:"freeze-2",model_binding_digest:"old-model"})],
  host:[artifact("run_lifecycle",{state:"RUNNING",run_id:"run-fixture",scope:{project_id:project.id,ontology_ids:[ontology.id]},runtime:{processes_stopped:false,locks_released:false},acceptance:{status:"pending"},terminal_results:{},process_liveness:"unknown"}),artifact("role_configuration",{roles:{modeling:{model:"model-a",requested_effort:"high",effective_effort:"medium"}},hot_switch_verified:false,configuration_status:"frozen_run_configuration"})],
  handoff:[artifact("handoff",{ready:false,pending_writes:true,unknown_writes:true,scope_binding:{project_id:project.id,ontology_ids:[ontology.id]}})],
};
async function fixture(page:Page,options:{noOntology?:boolean;scopeAdmin?:boolean;forbiddenWorkbench?:boolean}={}){
  await page.addInitScript(()=>localStorage.setItem("ontology-platform-ui-lang","en"));
  const requests:{path:string;method:string;body:Record<string,unknown>|null}[]=[];
  let users=[{id:"u1",username:"业务用户",disabled_at:null as string|null,is_org_admin:false}];
  let members=[{user_id:"u1",username:"业务用户"}];let roleIds:string[]=[];
  let roles=[{id:"r1",name:"业务语义阅读",description:null,grants:["service-read"],business_role_iri:"https://example.test/business_role",business_role_ontology_id:ontology.id,business_role_status:"resolved"}];
  let protections=[{id:"ps1",name:"成本语义",description:null,allowed_grants:["cost-read"],member_count:1}];
  let protectionMembers=[{resource_iri:"https://example.test/cost",ontology_id:ontology.id}];
  let keys=[{id:"key1",name:"现有Key",user_id:"u1",project_id:project.id,scopes:["read"],revoked_at:null as string|null}];
  await page.route("**/api/**",async route=>{
    const url=new URL(route.request().url()),path=url.pathname.replace(/^\/api/,""),method=route.request().method();const body=route.request().postData()?route.request().postDataJSON():null;
    requests.push({path,method,body});let result:unknown=[];let status=200;
    if(path==="/auth/me")result={actor:"user:admin",project_id:options.scopeAdmin?project.id:null,scopes:["admin"],subject_type:options.scopeAdmin?"api_key":"user"};
    else if(path==="/projects")result=[project];
    else if(path.endsWith("/ontologies"))result=options.noOntology?[]:[ontology];
    else if(path.endsWith("/workbench")){if(options.forbiddenWorkbench){status=403;result={detail:{code:"forbidden_scope"}};}else result={project_id:project.id,observed_at:"2026-10-07T00:01:00Z",current_run_id:"run-fixture",runs:[{run_id:"run-fixture",state:"RUNNING",source_updated_at:"2026-10-07T00:00:00Z",platform_binding:{project_id:project.id,ontology_ids:[ontology.id]},limitations:["recorded_state_is_not_process_liveness"]},{run_id:"old-run",state:"COMPLETED",source_updated_at:"2026-10-06T00:00:00Z",platform_binding:{project_id:project.id,ontology_ids:[ontology.id]},limitations:[]}],completeness:{complete:false,limit:1000},limitations:[]};}
    else if(path.includes("/workbench/runs/"))result={project_id:project.id,run_id:path.endsWith("old-run")?"old-run":"run-fixture",state:path.endsWith("old-run")?"COMPLETED":"RUNNING",platform_binding:{project_id:project.id,ontology_ids:[ontology.id]},observed_at:"2026-10-07T00:01:00Z",artifacts,limitations:["classified_effective_time_not_recorded_in_a_structured_run_artifact"]};
    else if(path.endsWith("/brief"))result={id:"brief1",project_id:project.id,fields:{domain_name:"维修",competency_questions:["旧Brief问题"]},field_states:{domain_name:"confirmed",scope:"unknown",identity_rules:"conflict",business_goal:"unconfirmed"},field_sources:{},missing_fields:["core_concepts"],clarification_items:[{field:"core_concepts",question:"范围缺失？",reason:"missing"},{field:"business_goal",question:"请确认含义",reason:"unconfirmed"}],completeness:0.9};
    else if(path.endsWith("/workspace-context"))result={default_graph_set_id:gs.id};
    else if(path==="/semantic/graph-sets")result={graph_sets:[{...gs,id:"unrelated-first-gs"},gs]};
    else if(path.endsWith("/read-models/resource-list"))result={items:resources,warnings:[],source_signature:"model-2"};
    else if(path.endsWith("/read-models/entity-relations"))result={items:[{iri:"https://example.test/relation1",label:"调用共享定义",source:resources[4].iri,target:resources[1].iri,relation:"https://example.test/invokes"}]};
    else if(path.startsWith("/semantic/resources/")){const iri=decodeURIComponent(path.replace("/semantic/resources/",""));const resource=resources.find(r=>r.iri===iri);result=resource?{...resource,properties:resource.detail_fields}:{};}
    else if(path==="/users"){if(options.scopeAdmin){status=403;result={detail:{code:"forbidden_scope"}};}else{if(method==="POST")users.push({id:"u2",username:body.username,disabled_at:null,is_org_admin:false});result=users;}}
    else if(path.startsWith("/users/")){const user=users.find(u=>u.id===path.split("/").at(-1));if(user){if(body.disabled!==undefined)user.disabled_at=body.disabled?"2026-10-07":null;if(body.username)user.username=body.username;}result=user;}
    else if(path===`/projects/${project.id}/members`){if(method==="POST")members.push({user_id:body.user_id,username:users.find(u=>u.id===body.user_id)?.username??""});result=members;}
    else if(path.includes("/members/")&&path.endsWith("/roles")){if(method==="PUT")roleIds=body.role_ids;result={role_ids:roleIds};}
    else if(path.includes("/members/")&&method==="DELETE"){members=members.filter(m=>m.user_id!==path.split("/").at(-1));status=204;}
    else if(path.endsWith("/semantic-access-roles")){if(method==="POST")roles.push({id:"r2",...body,business_role_status:"unresolved"});result=roles;}
    else if(path.includes("/semantic-access-roles/")){const id=path.split("/").at(-1);if(method==="DELETE"){roles=roles.filter(r=>r.id!==id);status=204;}else{const r=roles.find(r=>r.id===id);Object.assign(r??{},body);result=r;}}
    else if(path.endsWith("/protection-sets")){if(method==="POST")protections.push({id:"ps2",...body,member_count:0});result=protections;}
    else if(path.startsWith("/protection-sets/")&&path.endsWith("/members")){if(method==="POST")protectionMembers.push(...body.members);else protectionMembers=protectionMembers.filter(m=>!body.resource_iris.includes(m.resource_iri));result={member_count:protectionMembers.length};}
    else if(path.startsWith("/protection-sets/")){const id=path.split("/").at(-1);if(method==="DELETE"){protections=protections.filter(p=>p.id!==id);status=204;}else {const s=protections.find(s=>s.id===id);if(method==="PATCH")Object.assign(s??{},body);result={...s,members:protectionMembers,member_total:protectionMembers.length,member_offset:0,member_limit:100};}}
    else if(path==="/api-keys"){if(method==="POST"){const key={id:"key2",...body,revoked_at:null};keys.push(key);result={...key,plaintext_key:"ONCE-ONLY-SENTINEL"};}else result=keys;}
    else if(path.startsWith("/api-keys/")){const id=path.split("/").at(-1)?.replace(":revoke","");const key=keys.find(k=>k.id===id);if(key){if(path.endsWith(":revoke"))key.revoked_at="2026-10-07";else key.name=body.name;}result=key;}
    if(status===204)await route.fulfill({status});else await route.fulfill({status,json:result});
  });return requests;
}
const url=(tab:string)=>`/?project=${project.id}&tab=${tab}`;
test("T01 real host envelope without task fields opens four states and explicit unknown work/actions",async({page})=>{
  const requests=await fixture(page,{noOntology:true});await page.goto(url("brief"));
  for(const state of ["业务确认","建模表达","平台应用","独立验收"])await expect(page.getByText(state,{exact:true})).toBeVisible();
  await expect(page.getByText("剩余工作未知／未接入",{exact:true})).toBeVisible();await expect(page.getByText("下一动作未知／需核实宿主记录",{exact:true})).toBeVisible();await expect(page.getByText("运行枚举不完整，上限 1000")).toBeVisible();
  await expect(page.getByText(/来源 · run-fixture\/scenario_map.json/)).toBeVisible();expect(requests.some(r=>/canonical-writes|modeling-runs:start/.test(r.path))).toBe(false);
});
test("T01 overview summarizes independent source facts and keeps original records secondary",async({page})=>{
  await fixture(page);
  const staleReport=artifact("reports",{...artifacts.reports[0].data,full_pass:true,applicability:"stale"});
  await page.route("**/workbench/runs/*",route=>route.fulfill({json:{project_id:project.id,run_id:"run-fixture",state:"RUNNING",platform_binding:{project_id:project.id,ontology_ids:[ontology.id]},observed_at:"2026-10-07T00:01:00Z",artifacts:{...artifacts,reports:[staleReport]},limitations:[]}}));
  await page.goto(url("brief"));
  const business=page.getByLabel("业务确认摘要"),model=page.getByLabel("建模表达摘要"),application=page.getByLabel("平台应用摘要"),acceptance=page.getByLabel("独立验收摘要");
  await expect(business.getByText("Brief 字段原状态：已确认 1 项、明确未知 1 项、冲突 1 项、未确认 1 项。",{exact:true})).toBeVisible();
  await expect(business.getByText("仅说明 Brief 字段记录，不代表完整业务确认。",{exact:true})).toBeVisible();
  await expect(model.getByText("视角原状态：modeled 1 项、unknown 1 项。",{exact:true})).toBeVisible();
  await expect(model.getByText("候选修订：2；本记录关键 item：1 个。",{exact:true})).toBeVisible();
  await expect(application.getByText("台账条目原状态：not_applied 1 项。",{exact:true})).toBeVisible();
  await expect(acceptance.getByText("原验收报告 · 当前适用性：stale。",{exact:true})).toBeVisible();
  await expect(acceptance.getByText("原报告 full_pass：是（仅记录，未重新裁决）。",{exact:true})).toBeVisible();
  await expect(acceptance.locator(".ant-tag-success")).toHaveCount(0);
  await expect(page.getByText(/完整 PASS|业务完成率|当前验收通过/)).toHaveCount(0);
  await expect(business.getByText("domain_name",{exact:true}).first()).not.toBeVisible();
  await expect(model.getByText("candidate1",{exact:true}).first()).not.toBeVisible();
  await expect(application.getByText("same-content-2",{exact:true})).not.toBeVisible();
  const runDetails=page.getByLabel("运行技术记录");await expect(runDetails.getByText("platform_binding",{exact:true})).not.toBeVisible();
  await business.locator(".v41StateDetails > summary").click();await expect(business.getByText("identity_rules",{exact:true})).toBeVisible();await expect(business.getByText("conflict",{exact:true})).toBeVisible();
  await model.locator(".v41StateDetails > summary").nth(1).click();await expect(model.getByText("共享工单定义",{exact:true})).toBeVisible();
  await application.locator(".v41StateDetails > summary").click();await expect(application.getByText("same-content-2",{exact:true})).toBeVisible();await expect(application.getByText("not_applied",{exact:true})).toBeVisible();
  await runDetails.locator("summary").click();await expect(runDetails.getByText(project.id,{exact:true})).toBeVisible();
  await expect(page.getByText("剩余工作未知／未接入",{exact:true})).toBeVisible();await expect(page.getByText("下一动作未知／需核实宿主记录",{exact:true})).toBeVisible();
});
test("T02 Brief unknown/conflict stays separate from approved CQ version and freeze",async({page})=>{
  const requests=await fixture(page,{noOntology:true});await page.goto(url("questions"));
  await expect(page.getByText("Explicit unknown",{exact:true})).toBeVisible();await expect(page.getByText("Conflict",{exact:true})).toBeVisible();await expect(page.getByText(/旧 Brief CQ 不是 Team 冻结题集/)).toBeVisible();
  await page.locator(".mainNav").getByRole("button",{name:"Capability questions",exact:true}).click();
  await expect(page.getByText("原工单与复查工单为何复用定义而保持独立？",{exact:true})).toBeVisible();await expect(page.getByText("独立对象位置",{exact:true})).toBeVisible();await expect(page.getByText("freeze-2",{exact:true})).toBeVisible();
  expect(requests.some(r=>/private|hidden|freeze:write|competency-questions.*:/.test(r.path))).toBe(false);const stored=await page.evaluate(()=>JSON.stringify({...localStorage}));expect(stored).not.toContain("共同身份");
});
test("T03 map preserves seven viewpoints, unregistered, revision and independent application",async({page})=>{
  await fixture(page);await page.goto(url("scenario-map"));const matrix=page.getByRole("table",{name:"scenario-view-matrix"});await expect(matrix.locator("thead th")).toHaveCount(8);await expect(matrix.getByRole("button",{name:"未登记",exact:true})).toHaveCount(5);
  await matrix.getByRole("button",{name:"modeled",exact:true}).click();await expect(page.getByLabel("scenario-cell-detail").getByText("已表达未应用",{exact:true})).toBeVisible();await expect(page.getByLabel("scenario-cell-detail").getByText("shared-order",{exact:true})).toBeVisible();await expect(page.getByLabel("scenario-cell-detail").getByText("modeling",{exact:true})).toBeVisible();await expect(page.getByText(/modeled 仅表示建模表达/)).toBeVisible();
  await matrix.getByRole("button",{name:"unknown",exact:true}).click();await expect(page.getByLabel("scenario-cell-detail").getByText("职责待确认",{exact:true})).toBeVisible();
});
test("T04 unified no-Class resources share selection across viewpoints and read full detail",async({page})=>{
  const requests=await fixture(page);await page.goto(url("semantic-model"));await expect(page.locator(".v41ResourceList li")).toHaveCount(7);
  await page.locator(".v41ResourceList").getByRole("button",{name:"定义3"}).click();await expect(page.getByText(/def evaluate/)).toBeVisible();await expect(page.getByText("缺失不是false",{exact:true})).toBeVisible();await expect(page.getByText("外部Consumer报告",{exact:true})).toBeVisible();expect(requests.some(r=>r.path.includes("unrelated-first-gs/read-models"))).toBe(false);expect(requests.filter(r=>r.path.startsWith("/semantic/resources/")).every(r=>r.method==="GET")).toBe(true);
  await page.getByLabel("阅读视角",{exact:true}).click();await page.locator('.ant-select-item-option[title="行为"]').click();await expect(page.locator(".v41ResourceList li")).toHaveCount(1);await expect(page.getByText(/def evaluate/)).toBeVisible();
  await page.locator(".v41ResourceList").getByRole("button",{name:"定义2"}).click();await expect(page.getByText("目标工单",{exact:true})).toBeVisible();await expect(page.getByText("明确空列表",{exact:true})).toBeVisible();
  await page.getByLabel("阅读视角",{exact:true}).click();await page.locator('.ant-select-item-option[title="流程"]').click();await page.locator(".v41ResourceList").getByRole("button",{name:"定义5"}).click();await expect(page.getByText("original-order",{exact:true}).first()).toBeVisible();await expect(page.getByText("followup-order",{exact:true}).first()).toBeVisible();await expect(page.getByTestId("force-graph-canvas")).toBeVisible();
  await page.getByLabel("阅读视角",{exact:true}).click();await page.locator('.ant-select-item-option[title="数据映射"]').click();await page.locator(".v41ResourceList").getByRole("button",{name:"定义6"}).click();for(const t of ["一行一个工单","work_order_id","work_order_number","1:N","R→RESOLVED","分母规则待确认"])await expect(page.getByText(t,{exact:true})).toBeVisible();
  await page.getByLabel("阅读视角",{exact:true}).click();await page.locator('.ant-select-item-option[title="接口映射"]').click();await page.locator(".v41ResourceList").getByRole("button",{name:"定义7"}).click();for(const t of ["service-gateway","v1","body.reason","body.requestId","response_to_parameter","https://example.test/binding/close-v1"])await expect(page.getByText(t,{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:/运行脚本|Run rules/})).toHaveCount(0);
});
test("T04 business meaning, scope, unknowns and script precede technical positions regardless of property order",async({page})=>{
  await fixture(page);
  await page.route("**/semantic/resources/**",route=>route.fulfill({json:{iri:resources[2].iri,label:"定义3",ontology_id:ontology.id,assertion_kind:"asserted",properties:{class_iris:["https://example.test/TechnicalClass"],rdf_types:["http://www.w3.org/2002/07/owl#NamedIndividual"],source_graph_iri:"https://example.test/model-data-graph",...resources[2].detail_fields}}}));
  await page.goto(url("semantic-model"));await page.locator(".v41ResourceList").getByRole("button",{name:"定义3"}).click();
  const detail=page.getByLabel("模型定义详情"),meaning=detail.getByLabel("业务含义范围与未知");
  for(const text of ["含义3","当前维修切片","未确认业务口径"])await expect(meaning.getByText(text,{exact:true})).toBeVisible();
  await expect(detail.getByText(/def evaluate/)).toBeVisible();await expect(detail.getByText("缺失不是false",{exact:true})).toBeVisible();
  await expect(detail.getByLabel("资源读取位置")).toHaveText("业务模型");
  await expect(detail.getByText("https://example.test/TechnicalClass",{exact:true})).not.toBeVisible();
  await expect(detail.getByText("https://example.test/model-data-graph",{exact:true})).not.toBeVisible();
  await expect(detail.getByText(gs.id,{exact:true})).not.toBeVisible();
  expect(await detail.evaluate(root=>{
    const business=root.querySelector('[aria-label="业务含义范围与未知"]')!,technical=root.querySelector('[aria-label="资源技术详情"]')!,location=root.querySelector('[aria-label="模型读取位置详情"]')!;
    return Boolean(business.compareDocumentPosition(technical)&Node.DOCUMENT_POSITION_FOLLOWING)&&Boolean(business.compareDocumentPosition(location)&Node.DOCUMENT_POSITION_FOLLOWING);
  })).toBe(true);
  await detail.getByLabel("资源技术详情").locator("summary").click();await expect(detail.getByText("https://example.test/TechnicalClass",{exact:true})).toBeVisible();await expect(detail.getByText("http://www.w3.org/2002/07/owl#NamedIndividual",{exact:true})).toBeVisible();
  await detail.getByLabel("模型读取位置详情").locator("summary").click();await expect(detail.getByText(gs.id,{exact:true})).toBeVisible();await expect(meaning.getByText("含义3",{exact:true})).toBeVisible();
});
test("T05 second match page keeps context cursor ownership, compact omissions and resets",async({page})=>{
  const requests=await fixture(page);await page.route("**/semantic/context:query",async route=>{
    const b=route.request().postDataJSON();requests.push({path:"/semantic/context:query",method:"POST",body:b});
    const second=b.match_cursor==="M2"||b.context_cursor==="C2";
    await route.fulfill({json:{query:{queries:[b.query]},scope:{project_id:project.id},result_status:"matched",primary_matches:[{...resources[second?1:0],data:resources[second?1:0].detail_fields}],related_context:b.context_cursor?[{...resources[2],data:{rule_definition:{script_language:"python"}},projection:{omitted_fields:["data.rule_definition.script_source"]}}]:[],matches_page:{next_match_cursor:second?null:"M2"},context_page:{next_context_cursor:b.context_cursor?null:second?"C2":"C1",expansion:{budget_limited:true}},recall:{completeness:"degraded"},warnings:[{code:"context_truncated",message:"预算限制"}],truncated:true}});
  });await page.goto(url("search"));await page.getByLabel("查询表达式",{exact:true}).fill("工单");await page.getByRole("button",{name:"查询",exact:true}).click();await expect(page.getByRole("button",{name:"定义1",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"下一页主命中"}).click();await expect(page.getByRole("button",{name:"定义2",exact:true})).toBeVisible();await page.getByRole("button",{name:"继续当前页上下文"}).click();await expect(page.getByRole("button",{name:"定义2",exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"定义1",exact:true})).toHaveCount(0);await expect(page.getByText("data.rule_definition.script_source",{exact:true})).toBeVisible();
  const body=requests.filter(r=>r.path==="/semantic/context:query").at(-1)?.body;expect(body?.context_cursor).toBe("C2");expect(body?.match_cursor).toBeUndefined();
  await page.getByLabel("查询表达式",{exact:true}).fill("新范围");await expect(page.getByText("主命中",{exact:true})).toHaveCount(0);await page.getByRole("button",{name:"查询",exact:true}).click();const fresh=requests.filter(r=>r.path==="/semantic/context:query").at(-1)?.body;expect(fresh?.context_cursor).toBeUndefined();expect(fresh?.match_cursor).toBeUndefined();
});
test("T05 expiration and changed projection cannot retain old results",async({page})=>{
  await fixture(page);await page.route("**/semantic/context:query",route=>route.fulfill({status:409,json:{detail:{code:"context_snapshot_changed"}}}));await page.goto(url("search"));await page.getByLabel("查询表达式",{exact:true}).fill("工单");await page.getByRole("button",{name:"查询",exact:true}).click();await expect(page.getByText(/context_snapshot_changed/)).toBeVisible();await expect(page.getByText(/游标过期/)).toBeVisible();
  await page.getByLabel("上下文投影",{exact:true}).selectOption("compact");await expect(page.getByText(/context_snapshot_changed/)).toHaveCount(0);
});
test("T06 original point diagnostics, denominator and binding remain separate from current PASS",async({page})=>{
  await fixture(page);await page.goto(url("acceptance"));await expect(page.getByText("公开回归报告 · 原裁决与适用性",{exact:true})).toBeVisible();await expect(page.getByText("model-recall-insufficient",{exact:true}).first()).toBeVisible();await expect(page.getByText("原因未确定",{exact:true})).toBeVisible();await expect(page.getByText("pending-review",{exact:true})).toBeVisible();await expect(page.getByText("完整分母",{exact:true})).toBeVisible();await expect(page.getByText("原报告 full_pass（仅记录，未重新裁决）",{exact:true})).toBeVisible();await expect(page.getByText("报告适用性：binding_unknown")).toBeVisible();await expect(page.getByText(/L0 Runtime、L1 模型质量、L2 可重复性、L3 产品化/)).toBeVisible();
  await page.getByLabel("Team 运行",{exact:true}).click();await page.locator('.ant-select-item-option[title="old-run · 历史"]').click();await expect(page.getByText("历史记录",{exact:true})).toBeVisible();await expect(page.getByText("使用反馈：参数来源仍未知",{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:/自动修复|启动验收/})).toHaveCount(0);
});
test("T07 run/host configuration, unknown writes and continuation preserve source facts",async({page})=>{
  const requests=await fixture(page);await page.goto(url("run-records"));for(const t of ["dry_run_complete","not_applied","same-content-2","requested_effort","effective_effort","hot_switch_verified","process_liveness","unknown"] )await expect(page.getByText(t,{exact:true}).first()).toBeVisible();await expect(page.getByText(/未知写入须先按现有合同对账/)).toBeVisible();await expect(page.getByRole("button",{name:"打开现有 Session 与 Batch 诊断"})).toBeVisible();expect(requests.some(r=>r.method!=="GET")).toBe(false);
  await page.goto(url("brief"));await expect(page.getByLabel("pending_work").getByText("剩余工作未知／未接入",{exact:true})).toBeVisible();await expect(page.getByLabel("next_action").getByText("下一动作未知／需核实宿主记录",{exact:true})).toBeVisible();await expect(page.getByText("继续同一建模目标",{exact:true})).toHaveCount(0);
});
test("T08 administrators manage explicit roles, protection membership and one-time Keys",async({page})=>{
  const requests=await fixture(page);await page.goto(url("project-access"));await expect(page.getByText("resolved",{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"禁用用户"})).toBeEnabled();await page.getByRole("button",{name:"禁用用户"}).click();await expect(page.getByText("已禁用",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"创建权限角色",exact:true}).click();let dialog=page.getByRole("dialog",{name:"创建权限角色"});await dialog.getByLabel("角色名",{exact:true}).fill("新权限角色");await dialog.getByRole("button",{name:"OK",exact:true}).click();await expect(page.getByText("新权限角色",{exact:true})).toBeVisible();expect(requests.find(r=>r.path.endsWith("semantic-access-roles")&&r.method==="POST")?.body?.grants).toEqual([]);
  await page.getByLabel("业务用户 的权限角色",{exact:true}).click();await page.locator('.ant-select-item-option[title="新权限角色"]').click();await expect.poll(()=>requests.filter(r=>r.method==="PUT").length).toBe(1);expect(requests.find(r=>r.method==="PUT")?.body).toEqual({role_ids:["r2"]});
  await page.getByRole("button",{name:"成本语义",exact:true}).click();await page.getByLabel("保护资源 IRI",{exact:true}).fill("https://example.test/second-cost");await page.getByLabel("资源 Ontology ID",{exact:true}).fill(ontology.id);await page.getByRole("button",{name:"添加保护资源",exact:true}).click();await expect(page.getByText("https://example.test/second-cost",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"创建 Key",exact:true}).click();dialog=page.getByRole("dialog",{name:"创建 Key"});await dialog.getByLabel("Key 名称",{exact:true}).fill("测试Key");await dialog.getByLabel("Key 所属用户",{exact:true}).click();await page.locator('.ant-select-item-option[title="业务用户"]').click();await dialog.getByRole("button",{name:"OK",exact:true}).click();await expect(page.getByTestId("key-plaintext")).toHaveText("ONCE-ONLY-SENTINEL");const storage=await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}));expect(storage).not.toContain("ONCE-ONLY-SENTINEL");await page.getByRole("button",{name:"已保存，关闭明文"}).click();await expect(page.getByTestId("key-plaintext")).toHaveCount(0);
  const row=page.locator(".v41AdminList li").filter({has:page.getByText("测试Key",{exact:true})});await row.getByRole("button",{name:"撤销 Key",exact:true}).click();await expect(row.getByText("已撤销",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"启用防误操作锁",exact:true}).click();await expect(page.getByRole("button",{name:"创建 Key",exact:true})).toBeDisabled();await expect(page.getByText(/不暂停 Agent，不改变后端授权/)).toBeVisible();expect(requests.some(r=>/pause|resume|agent-command/.test(r.path))).toBe(false);
});
test("T08 project-admin users denial keeps permitted role and Key panels usable",async({page})=>{
  await fixture(page,{scopeAdmin:true});await page.goto(url("project-access"));await expect(page.getByText(/403/)).toBeVisible();await expect(page.getByRole("button",{name:"创建权限角色",exact:true})).toBeEnabled();await expect(page.getByRole("button",{name:"创建 Key",exact:true})).toBeEnabled();await expect(page.getByRole("button",{name:"创建用户",exact:true})).toBeDisabled();
});
test("T10 management projection forbidden is distinct from an empty run",async({page})=>{
  await fixture(page,{forbiddenWorkbench:true});await page.goto(url("brief"));await expect(page.getByText(/403.*forbidden_scope/)).toBeVisible();await expect(page.getByText("未知／未接入",{exact:true})).toHaveCount(3);await expect(page.getByText("完整 PASS",{exact:true})).toHaveCount(0);
});
test("T12 desktop/mobile and keyboard project workspace rendering",async({page},info:TestInfo)=>{
  await fixture(page,{noOntology:true});await page.goto(url("brief"));await expect(page.getByText("剩余工作未知／未接入",{exact:true})).toBeVisible();await expect(page.getByText("下一动作未知／需核实宿主记录",{exact:true})).toBeVisible();await page.screenshot({path:info.outputPath("v41-desktop.png"),fullPage:true});await page.setViewportSize({width:390,height:844});await page.screenshot({path:info.outputPath("v41-mobile.png"),fullPage:true});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);await page.keyboard.press("Tab");expect(await page.evaluate(()=>document.activeElement?.tagName)).not.toBe("BODY");
});

test("T04 same resource identity keeps multiple ontology reading locations",async({page})=>{
  await fixture(page);const other={...ontology,id:"other-ontology",name:"第二模型"};
  await page.route("**/projects/*/ontologies",route=>route.fulfill({json:[ontology,other]}));
  await page.goto(url("semantic-model"));await expect(page.locator(".v41ResourceList li")).toHaveCount(7);
  await page.locator(".v41ResourceList").getByRole("button",{name:"定义1"}).click();await expect(page.getByLabel("资源读取位置").locator("option")).toHaveCount(2);
  await page.getByLabel("资源读取位置").selectOption("1");await expect(page.getByLabel("资源读取位置").locator("option").nth(1)).toHaveText("第二模型");await page.getByLabel("模型读取位置详情").locator("summary").click();await expect(page.getByLabel("模型读取位置详情").getByText("other-ontology",{exact:true})).toBeVisible();
});
test("T08 user and member administration roundtrip uses existing contracts",async({page})=>{
  const requests=await fixture(page);await page.goto(url("project-access"));await page.getByLabel("新用户名").fill("新增用户");await page.getByRole("button",{name:"创建用户",exact:true}).click();
  const userRow=page.locator(".v41AdminList li").filter({has:page.getByText("新增用户",{exact:true})});await expect(userRow).toBeVisible();
  page.once("dialog",dialog=>dialog.accept("更新用户"));await userRow.getByRole("button",{name:"修改用户名"}).click();await expect(page.getByText("更新用户",{exact:true})).toBeVisible();
  await page.getByLabel("添加项目成员",{exact:true}).click();await page.locator('.ant-select-item-option[title="更新用户"]').click();await page.getByRole("button",{name:"添加成员",exact:true}).click();
  const member=page.locator(".v41AdminList li").filter({has:page.getByLabel("更新用户 的权限角色")});await expect(member).toBeVisible();await member.getByRole("button",{name:"移除成员"}).click();await expect(page.getByLabel("更新用户 的权限角色")).toHaveCount(0);
  expect(requests.find(r=>r.path==="/users/u2"&&r.method==="PATCH")?.body).toEqual({username:"更新用户"});expect(requests.some(r=>r.path.endsWith("/members/u2")&&r.method==="DELETE")).toBe(true);
});
test("T08 role, protection set and Key updates preserve explicit grant definitions",async({page})=>{
  const requests=await fixture(page);await page.goto(url("project-access"));await page.getByRole("button",{name:"编辑权限角色",exact:true}).click();let dialog=page.getByRole("dialog",{name:"编辑权限角色"});await dialog.getByLabel("角色名",{exact:true}).fill("更新阅读角色");await dialog.getByRole("button",{name:"OK",exact:true}).click();await expect(page.getByText("更新阅读角色",{exact:true})).toBeVisible();expect(requests.find(r=>r.path.endsWith("/semantic-access-roles/r1")&&r.method==="PATCH")?.body?.grants).toEqual(["service-read"]);
  await page.getByRole("button",{name:"创建保护集",exact:true}).click();dialog=page.getByRole("dialog",{name:"创建保护集"});await dialog.getByLabel("保护集名",{exact:true}).fill("新增保护集");await dialog.getByRole("button",{name:"OK",exact:true}).click();
  let setRow=page.locator(".v41AdminList li").filter({has:page.getByRole("button",{name:"新增保护集",exact:true})});await setRow.getByRole("button",{name:"编辑保护集"}).click();dialog=page.getByRole("dialog",{name:"编辑保护集"});await dialog.getByLabel("保护集名",{exact:true}).fill("更新保护集");await dialog.getByRole("button",{name:"OK",exact:true}).click();setRow=page.locator(".v41AdminList li").filter({has:page.getByRole("button",{name:"更新保护集",exact:true})});await setRow.getByRole("button",{name:"删除保护集"}).click();await expect(page.getByRole("button",{name:"更新保护集",exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"成本语义",exact:true}).click();await page.getByRole("button",{name:"移除保护资源"}).click();await expect(page.getByText("https://example.test/cost",{exact:true})).toHaveCount(0);
  const key=page.locator(".v41AdminList li").filter({has:page.getByText("现有Key",{exact:true})});await key.getByRole("button",{name:"更新 Key"}).click();dialog=page.getByRole("dialog",{name:"更新 Key"});await dialog.getByLabel("Key 名称",{exact:true}).fill("更新Key");await dialog.getByRole("button",{name:"OK",exact:true}).click();await expect(page.getByText("更新Key",{exact:true})).toBeVisible();await expect(page.getByTestId("key-plaintext")).toHaveCount(0);
  await page.getByRole("button",{name:"删除权限角色",exact:true}).click();await expect(page.getByText("更新阅读角色",{exact:true})).toHaveCount(0);
});

test("T05 compact OWL resource opens exact detail in default non-first GraphSet",async({page})=>{
  await fixture(page);await page.route("**/semantic/context:query",route=>route.fulfill({json:{query:{},scope:{project_id:project.id},result_status:"matched",primary_matches:[{...resources[2],assertion_kind:"inferred",data:{rule_definition:{script_language:"python"}},projection:{omitted_fields:["data.rule_definition.script_source"]}}],related_context:[],matches_page:{},context_page:{},recall:{},warnings:[],truncated:false}}));
  await page.goto(url("search"));await page.getByLabel("查询表达式").fill("派生规则");await page.getByRole("button",{name:"查询",exact:true}).click();await expect(page.getByText(/def evaluate/)).toHaveCount(0);const requested=page.waitForRequest(r=>r.url().includes("/semantic/resources/"));await page.getByRole("button",{name:"定义3",exact:true}).click();const readUrl=new URL((await requested).url());expect(readUrl.searchParams.get("graph_set_id")).toBe(gs.id);expect(readUrl.searchParams.get("include")).toBe("asserted-plus-reasoning");const dialog=page.getByRole("dialog",{name:"精确资源详情"});await expect(dialog.getByText(/def evaluate/)).toBeVisible();await expect(dialog.getByText("data.rule_definition.script_source",{exact:true})).toHaveCount(0);
});
