import { useEffect, useState } from "react";
import { Alert, Button, Card, Select, Tag } from "antd";
import type { Project, ProjectBrief } from "../types";
import type { WorkbenchRequest, WorkbenchNavigate } from "./workbenchTypes";
import { FieldTable } from "./SemanticModelPage";
import { scenarioViews } from "./semanticViews";
import { RequirementQuestionsPage } from "./RequirementQuestionsPage";
export type WorkbenchArtifact = {
  artifact_id:string;kind:string;availability:string;schema_version?:string;version?:unknown;
  source:{path:string;updated_at?:string;sha256?:string};observed_at:string;
  scope:Record<string,unknown>;limitations:string[];data:Record<string,unknown>;
};
export type WorkbenchRunSummary = {run_id:string;state:Record<string,unknown>|string;source_updated_at:string;platform_binding:Record<string,unknown>;limitations:string[]};
export type WorkbenchIndex = {project_id:string;observed_at:string;current_run_id:string|null;runs:WorkbenchRunSummary[];completeness:{complete:boolean;limit:number};limitations:string[]};
export type WorkbenchRun = {project_id:string;run_id:string;observed_at:string;state:Record<string,unknown>|string;platform_binding:Record<string,unknown>;artifacts:Record<string,WorkbenchArtifact[]>;limitations:string[]};
export function ArtifactSource({artifact}: {artifact:WorkbenchArtifact}) {
  return <details className="v41Source"><summary>来源 · {artifact.source.path??artifact.artifact_id} · {artifact.source.updated_at??"源时点未知"}</summary><FieldTable value={{artifact_id:artifact.artifact_id,kind:artifact.kind,version:artifact.version,schema_version:artifact.schema_version,source:artifact.source,observed_at:artifact.observed_at,scope:artifact.scope}}/></details>;
}
export function ArtifactPanel({artifact,title}: {artifact:WorkbenchArtifact;title?:string}) {
  return <Card title={artifact.kind==="public_regression_report"?"公开回归报告 · 原裁决与适用性":title??artifact.kind} extra={<Tag>{artifact.availability}</Tag>}><ArtifactSource artifact={artifact}/>{["reports","public_regression_report"].includes(artifact.kind)&&<Alert type="warning" message={`报告适用性：${String(artifact.data.applicability??"未知")}`} description="保留原裁决；未核实当前模型与冻结绑定时，本报告不能作为最新有效验收 PASS。"/>}{artifact.limitations.map((l,i)=><Alert key={i} type="warning" message={l}/>)}{artifact.availability==="available" ? <FieldTable value={artifact.data}/>:<p>{artifact.availability==="missing" ? "所选运行缺少此内容":"产物加载失败，请查看来源与限制"}</p>}</Card>;
}
function Artifacts({run,kind,title}: {run:WorkbenchRun|null;kind:string;title:string}) {
  const artifacts=run?.artifacts[kind]??[];
  return <>{artifacts.length ? artifacts.map(a=><ArtifactPanel key={a.artifact_id} artifact={a} title={title}/>):<Card title={title}>当前所选运行无已接入产物；状态未知。</Card>}</>;
}
function ScenarioMap({artifact}: {artifact:WorkbenchArtifact}) {
  const [selected,setSelected]=useState<Record<string,unknown>|null>(null);
  const slices=Array.isArray(artifact.data.slices) ? artifact.data.slices as Record<string,unknown>[]:[];
  return <Card title="业务切片 × 七视角"><ArtifactSource artifact={artifact}/>{artifact.limitations.map((l,i)=><Alert key={i} type="warning" message={l}/>)}
    <div className="v41TableScroll"><table className="namedGraphTable" aria-label="scenario-view-matrix"><thead><tr><th>业务切片</th>{scenarioViews.map(([v,l])=><th key={v}>{l}</th>)}</tr></thead><tbody>{slices.map((s,i)=><tr key={String(s.slice_id??i)}><th>{String(s.name??s.slice_id)}<small>{String(s.scope??"")}</small></th>{scenarioViews.map(([v])=>{const views=Array.isArray(s.viewpoints)?s.viewpoints as Record<string,unknown>[]:[];const cell=views.find(c=>c.viewpoint===v);return <td key={v}><button className="secondaryButton" onClick={()=>setSelected({slice_id:s.slice_id,owner:s.owner,...(cell??{viewpoint:v,status:"未登记"})})}>{String(cell?.status??"未登记")}</button></td>;})}</tr>)}</tbody></table></div>
    {!slices.length&&<p>未接入切片矩阵，不能将未登记视角视为不适用。</p>}{selected&&<Card title="单元格范围、责任与修订" aria-label="scenario-cell-detail"><FieldTable value={selected}/></Card>}
    <p className="inlineHint">modeled 仅表示建模表达。业务确认、平台应用与独立验收仍以各自记录为准。</p>
    <Card title="共享定义、引用与跨切片依赖"><FieldTable value={{shared_terms:artifact.data.shared_terms,cross_slice_dependencies:artifact.data.cross_slice_dependencies,collaboration_matrix:artifact.data.collaboration_matrix,adjustments:artifact.data.adjustments,explicit_unknowns:artifact.data.explicit_unknowns}}/><p>依赖未读全时不能声称没有引用。</p></Card>
  </Card>;
}
function CurrentWorkSummary({run}: {run:WorkbenchRun|null}) {
  const artifacts=[...(run?.artifacts.host??[]),...(run?.artifacts.handoff??[])];
  const fields=[
    {key:"pending_work",title:"剩余工作记录",missing:"剩余工作未知／未接入"},
    {key:"next_action",title:"下一动作记录",missing:"下一动作未知／需核实宿主记录"},
  ];
  return <><div className="v41Split">{fields.map(field=>{
    const sources=artifacts.filter(a=>a.availability==="available"&&a.data[field.key]!=null&&a.data[field.key]!=="");
    return <section key={field.key} aria-label={field.key}><h3>{field.title}</h3>{sources.length?sources.map(a=><div key={a.artifact_id}><ArtifactSource artifact={a}/><FieldTable value={a.data[field.key]}/></div>):<p>{field.missing}</p>}</section>;
  })}</div><p className="inlineHint">这里只展示明确记录的工作和动作；运行状态与交接专项状态不能证明剩余工作已列全。</p><details><summary>宿主记录字段与来源</summary>{(run?.artifacts.host??[]).map(a=><div key={a.artifact_id}><ArtifactSource artifact={a}/><FieldTable value={a.data}/></div>)}</details></>;
}
const states=[
    ["业务确认","business_confirmation","来自 Brief 的字段确认、未知及冲突记录；CQ 审核冻结单独呈现。"],
    ["建模表达","scenario_map","来自地图和候选；modeled 不代表已经应用。"],
    ["平台应用","materialization","来自 Batch／Attempt／写入回执与读回。"],
    ["独立验收","reports","来自原报告；历史、绑定未知或失效不表示当前通过。"],
  ];
function recordedStates(values: unknown[], labels: Record<string,string> = {}) {
  const counts=new Map<string,number>();
  values.forEach(value=>{const state=typeof value==="string"&&value?value:"未记录";counts.set(state,(counts.get(state)??0)+1);});
  return counts.size?[...counts].map(([state,count])=>`${labels[state]??state} ${count} 项`).join("、"):"本产物未读到状态条目";
}
function ArtifactStateSummary({artifact,kind}: {artifact:WorkbenchArtifact;kind:string}) {
  const data=artifact.data;
  if(artifact.availability!=="available")return <p>{artifact.availability==="missing"?"此来源内容缺失，状态未知。":"此来源读取失败，状态未知。"}</p>;
  if(kind==="scenario_map") {
    if(artifact.kind==="candidates")return <><p>候选修订：{data.revision==null?"未记录":String(data.revision)}；本记录关键 item：{Array.isArray(data.items)?data.items.length:"未记录"} 个。</p><p className="inlineHint">候选表达记录，不表示已应用或已验收。</p></>;
    const slices=Array.isArray(data.slices)?data.slices as Record<string,unknown>[]:null;
    const viewpoints=slices?.flatMap(slice=>Array.isArray(slice.viewpoints)?slice.viewpoints as Record<string,unknown>[]:[])??[];
    return <><p>地图记录：{slices?slices.length:"未记录"} 个业务切片，{viewpoints.length} 条视角记录。</p><p>切片原状态：{recordedStates(slices?.map(slice=>slice.status)??[])}。</p><p>视角原状态：{recordedStates(viewpoints.map(view=>view.status))}。</p>{Array.isArray(data.explicit_unknowns)&&<p>另有 {data.explicit_unknowns.length} 条显式未知记录。</p>}<p className="inlineHint">modeled 只说明已有表达；未登记视角与应用状态仍分别核实。</p></>;
  }
  if(kind==="reports")return <><p>{artifact.kind==="public_regression_report"?"公开回归报告":"原验收报告"} · 当前适用性：{String(data.applicability??"未知／未核实")}。</p><p>原报告 full_pass：{typeof data.full_pass==="boolean"?(data.full_pass?"是":"否"):"未记录"}（仅记录，未重新裁决）。</p><p>完整分母：{typeof data.denominator==="number"?data.denominator:"未记录"}；公开题数：{typeof data.public_count==="number"?data.public_count:"未记录"}。</p><p className="inlineHint">报告原裁决与当前适用性分别读取；这张摘要不产生当前验收结论。</p></>;
  const entries=Array.isArray(data.entries)?data.entries as Record<string,unknown>[]:null;
  const commands=Array.isArray(data.commands)?data.commands as Record<string,unknown>[]:null;
  const proofs=Array.isArray(data.records)?data.records as Record<string,unknown>[]:null;
  return <><p>本来源模式：{String(data.mode??"未记录")}；原状态：{String(data.status??"未记录")}。</p>{entries&&<p>台账条目原状态：{recordedStates(entries.map(entry=>entry.status))}。</p>}{commands&&<p>命令原状态：{recordedStates(commands.map(command=>command.status))}。</p>}{proofs&&<><p>执行证据记录：{proofs.length} 条；模式：{recordedStates(proofs.map(proof=>proof.mode))}。</p><p>尝试原状态：{recordedStates(proofs.map(proof=>proof.attempt_status))}。</p></>}<p className="inlineHint">每份记录保留自己的范围；完整应用与读回应核实同内容回执和当前平台状态。</p></>;
}
function StateCards({run,brief}: {run:WorkbenchRun|null;brief:ProjectBrief|null}) {
  const artifactNames:Record<string,string>={scenario_map:"场景地图",candidates:"候选修订",materialization_plan:"物化计划",submission_intent:"提交意图",submission_receipt:"写入回执",materialization_ledger:"应用台账",approvals:"审批记录",attempt_proofs:"尝试证据",reports:"原验收报告",public_regression_report:"公开回归报告"};
  return <div className="v41StateGrid">{states.map(([title,kind,hint])=>{
    const artifacts=kind==="scenario_map"?[...(run?.artifacts.scenario_map??[]),...(run?.artifacts.candidates??[])]:run?.artifacts[kind]??[];
    return <Card title={title} key={kind} aria-label={`${title}摘要`}><p className="inlineHint">{hint}</p>{kind==="business_confirmation"&&brief?<><p>Brief 字段原状态：{recordedStates(Object.values(brief.field_states),{confirmed:"已确认",answered:"已回答",missing:"缺失",skipped:"已跳过",unknown:"明确未知",conflict:"冲突",unconfirmed:"未确认"})}。</p><p>Brief 另记录 {brief.missing_fields.length} 个缺失字段、{brief.clarification_items.length} 个澄清事项。</p><p className="inlineHint">仅说明 Brief 字段记录，不代表完整业务确认。</p><details className="v41StateDetails"><summary>查看 Brief 完整字段记录与来源</summary><FieldTable value={{fields:brief.fields,field_states:brief.field_states,field_sources:brief.field_sources,missing_fields:brief.missing_fields,clarification_items:brief.clarification_items}}/></details></>:artifacts.length?artifacts.map(a=><article key={a.artifact_id} className="v41StateRecord"><h3>{artifactNames[a.kind]??"来源记录"}</h3><ArtifactStateSummary artifact={a} kind={kind}/><ArtifactSource artifact={a}/><details className="v41StateDetails"><summary>查看此来源完整记录</summary><FieldTable value={{availability:a.availability,limitations:a.limitations,data:a.data}}/></details></article>):<Tag>未知／未接入</Tag>}</Card>;
  })}</div>;
}
export function ProjectWorkbenchPage({project,request,page,navigate,onDirtyChange,readOnly=false}: {project:Project;request:WorkbenchRequest;page:string;navigate:WorkbenchNavigate;onDirtyChange:(dirty:boolean)=>void;readOnly?:boolean}) {
  const [brief,setBrief]=useState<ProjectBrief|null>(null);
  const [index,setIndex]=useState<WorkbenchIndex|null>(null);
  const [run,setRun]=useState<WorkbenchRun|null>(null);
  const [runId,setRunId]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{let cancelled=false;setBrief(null);request<ProjectBrief>(`/projects/${project.id}/brief`).then(value=>{if(!cancelled&&value.field_states)setBrief(value);}).catch(()=>{});return()=>{cancelled=true;};},[project.id,request,revision]);
  useEffect(()=>{let cancelled=false;setIndex(null);setRun(null);setError("");setBusy(true);request<WorkbenchIndex>(`/projects/${project.id}/workbench`).then(value=>{if(cancelled)return;if(!Array.isArray(value.runs)||!value.completeness)throw new Error("工作台响应合同不完整");setIndex(value);setRunId(current=>value.runs.some(r=>r.run_id===current)?current:value.current_run_id??"");}).catch(cause=>{if(!cancelled)setError(String(cause));}).finally(()=>{if(!cancelled)setBusy(false);});return()=>{cancelled=true;};},[project.id,request,revision]);
  useEffect(()=>{let cancelled=false;setRun(null);if(!runId)return;setError("");setBusy(true);request<WorkbenchRun>(`/projects/${project.id}/workbench/runs/${encodeURIComponent(runId)}`).then(value=>{if(!cancelled)setRun(value);}).catch(cause=>{if(!cancelled)setError(String(cause));}).finally(()=>{if(!cancelled)setBusy(false);});return()=>{cancelled=true;};},[project.id,request,runId,revision]);
  return <section aria-label="project-workbench-page" className="v41Page"><Card title={project.name} extra={<Button loading={busy} onClick={()=>setRevision(v=>v+1)}>核实最新产物</Button>}>
    <p>{project.description??"场景目标尚未记录"}</p><div className="v41Form"><label>Team 运行<Select aria-label="Team 运行" allowClear placeholder="选择已绑定运行；不自动采用历史运行" value={runId||undefined} onChange={v=>setRunId(v??"")} options={index?.runs.map(r=>({value:r.run_id,label:`${r.run_id}${r.run_id===index.current_run_id?" · 当前":" · 历史"}`}))??[]}/></label><span>最近核实：{index?.observed_at??"尚未核实"}</span></div>
    {index&&!index.completeness.complete&&<Alert type="warning" message={`运行枚举不完整，上限 ${index.completeness.limit}`}/>}{index?.limitations.map((l,i)=><Alert key={i} type="warning" message={l}/>)}
    {!runId&&!busy&&<p>尚无已核实的当前运行；可选择历史记录查看其原始范围。没有 Ontology 仍可进行业务澄清与获准 CQ 阅读。</p>}
    {run&&<><Tag>{run.run_id===index?.current_run_id?"当前记录":"历史记录"}</Tag><details className="v41StateDetails" aria-label="运行技术记录"><summary>运行身份、原始状态与读取限制</summary><FieldTable value={{state:run.state,platform_binding:run.platform_binding,observed_at:run.observed_at,limitations:run.limitations}}/></details></>}
    </Card>{error&&<Alert type="error" message={error} description="未接入、禁止访问、缺少内容和读取失败按接口原合同显示。"/>}
    {page==="brief"&&<><StateCards run={run} brief={brief}/>
    <Card title="当前工作、待决定事项与下一动作"><CurrentWorkSummary run={run}/><div className="buttonRow"><Button onClick={()=>navigate("questions")}>业务澄清</Button><Button onClick={()=>navigate("capability-questions")}>获准能力问题</Button><Button onClick={()=>navigate("scenario-map")}>地图与候选</Button><Button onClick={()=>navigate("run-records")}>运行与交接</Button></div></Card><details className="v41StateDetails"><summary>查看交接范围与专项原始记录</summary><Artifacts run={run} kind="handoff" title="交接范围及剩余工作"/></details></>}
    {page==="questions"&&<><Alert type="info" message="Brief 与访谈资料" description="这里的完整度只表示 Brief 字段，旧 Brief CQ 不是 Team 冻结题集。业务问题与技术故障分开处理。"/><RequirementQuestionsPage projectId={project.id} request={request} readOnly={readOnly} onDirtyChange={onDirtyChange}/></>}
    {page==="capability-questions"&&<><Alert type="info" message="获准公开 CQ" description="覆盖范围与公开可见性分别读取；这里只接收公开获准投影，不显示隐藏题或答案。"/><Artifacts run={run} kind="competency_questions" title="能力问题、必答点与审核冻结绑定"/></>}
    {page==="scenario-map"&&<><StateCards run={run} brief={brief}/>{run?.artifacts.scenario_map?.length?run.artifacts.scenario_map.map(a=><ScenarioMap key={a.artifact_id} artifact={a}/>):<Card>场景地图尚未接入。</Card>}<Artifacts run={run} kind="candidates" title="候选修订、关键 item 与引用重审"/></>}
    {page==="acceptance"&&<><Alert type="info" message="验收边界" description="开发验证、独立功能验收和真实语义证据分别记录。L0 Runtime、L1 模型质量、L2 可重复性、L3 产品化独立；局部 CQ 不代替完整 v4、SQL／API 或真实 DL 验收。未执行、待复核及失败不能从历史 PASS 补齐。"/><Artifacts run={run} kind="public_feedback" title="早期公开反馈（独立于正式验收）"/><Artifacts run={run} kind="reports" title="正式报告 · 原裁决、完整分母、逐点结果与适用性"/></>}
    {page==="run-records"&&<><Alert type="info" message="Team run、Session 与宿主记录分别呈现" description="阶段结束、交接、排空、释放进程、检查点验收和最终收尾分别核实。历史记录不证明当前可恢复，未知写入须先按现有合同对账。"/><Artifacts run={run} kind="host" title="宿主摘要、请求及实际配置、授权台账与分类时间"/><Artifacts run={run} kind="materialization" title="候选 → plan → dry-run → 翻译审阅 → apply → 读回／恢复"/><Artifacts run={run} kind="handoff" title="交接与后续已授权工作"/><Card title="Session 技术诊断"><Button onClick={()=>navigate("build-context")}>打开现有 Session 与 Batch 诊断</Button></Card></>}
  </section>;
}
