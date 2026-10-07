import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Input, Select, Tag } from "antd";
import type { Ontology } from "../types";
import type { WorkbenchRequest } from "./workbenchTypes";
import { listGraphSets, readModel } from "../semanticApi";
import { ForceGraphCanvas, type ForceGraphEdge } from "../components/ForceGraphCanvas";
import { semanticViews } from "./semanticViews";
export type SemanticResource = {
  id?: string; iri?: string; label?: string | null; description?: string; kind?: string; ontology_id?: string;
  data?: Record<string, unknown>; detail_fields?: Record<string, unknown>; properties?: Record<string, unknown>;
  warnings?: unknown[]; projection?: {omitted_fields?: string[]}; [key: string]: unknown;
};
const fieldLabels: Record<string,string> = {
  applicability_status:"适用性", scope:"适用范围", question:"题干", answer_points:"获准必答点", review_content_version:"审核内容版本", snapshot_digest:"冻结内容绑定", review_binding:"审核绑定", projection_digest:"公开投影绑定",
  verdict:"原裁决", denominator:"完整分母", public_count:"公开题数", hidden_summary:"获准隐藏分组汇总", point_diagnostics:"逐答案点诊断", answer_point_diagnostics:"逐答案点诊断", applicability_limitations:"适用性限制", full_pass:"原报告 full_pass（仅记录，未重新裁决）", failure_layer:"原运行失败分类", note:"原始说明",
  business_role_status:"业务角色关联状态", grants:"显式 Grant", business_role_iri:"业务角色 IRI", business_role_ontology_id:"业务角色 Ontology", semantic_definition:"业务含义与适用范围", semantic_role:"语义角色声明", business_meaning:"业务含义", applicability:"适用范围",
  action_definition:"Action 定义", parameter_definition:"参数定义", rule_definition:"业务规则定义", mapping_definition:"映射定义",
  class_iris:"正式 Class 分类", rdf_types:"底层类型", class_id:"分类", source_signature:"来源版本", source_graph_iri:"所在图",
  script_source:"脚本文本（只读）", execution_environment:"执行环境", language:"语言", version:"版本", input_parameters:"输入参数",
  output_parameters:"输出参数", preconditions:"前置条件", success_effects:"成功效果", operation_bindings:"外部能力关联", null_semantics:"空值语义",
  failure_semantics:"失败语义", side_effects:"副作用语义", responsibilities:"业务职责", process_definition:"流程定义", calls:"Action 调用点",
  invocation:"局部调用", object_positions:"对象位置", parameter_sources:"参数来源", branch:"分支", loop:"循环", output_conditions:"输出条件",
  row_grain:"行粒度", technical_keys:"技术键", business_keys:"业务键", cardinality:"Join 基数", encoding:"编码", transformations:"转换", metric_definition:"指标口径",
  system:"系统身份", interface:"接口身份", request_fields:"请求字段位置", response_fields:"响应字段位置", direction:"映射方向", operation_iri:"精确 Operation", binding_id:"精确 binding",
  pending:"待处理", unknowns:"显式未知", omitted_fields:"投影省略", derived_state:"派生结果有效性", projection:"投影声明", assertion_kind:"陈述类型",
};
export function FieldTable({value}: {value: unknown}) {
  if(value===null)return <span className="inlineHint">明确空值</span>;
  if(value===undefined)return <span className="inlineHint">未知／未记录</span>;
  if(Array.isArray(value)) return value.length ? <ol className="v41Values">{value.map((v,i)=><li key={i}><FieldTable value={v}/></li>)}</ol> : <span>明确空列表</span>;
  if(typeof value==="object")return <dl className="v41Fields">{Object.entries(value as Record<string,unknown>).map(([k,v])=><div key={k}><dt>{fieldLabels[k]??k}</dt><dd><FieldTable value={v}/></dd></div>)}</dl>;
  return <span className="v41Text">{typeof value==="boolean" ? (value ? "是":"否") : String(value)}</span>;
}
export function ResourceCard({resource, onOpen}: {resource:SemanticResource;onOpen?:(iri:string)=>void}) {
  const data=resource.properties??resource.data??resource.detail_fields??{};
  const declaration=data.semantic_definition;
  const semantic=declaration&&typeof declaration==="object"&&!Array.isArray(declaration)?declaration as Record<string,unknown>:{};
  const {business_meaning,applicability,unknowns,...otherSemantic}=semantic;
  const technicalFields=new Set(["iri","ontology_id","graph_set_id","graph_iri","source_graph_iri","source_signature","class_iris","class_iri","class_id","rdf_types"]);
  const attributes=Object.fromEntries(Object.entries(data).filter(([key])=>key!=="semantic_definition"&&!technicalFields.has(key)));
  const technical=Object.fromEntries(Object.entries(data).filter(([key])=>technicalFields.has(key)));
  return <article className="v41Resource"><h3>{onOpen&&resource.iri ? <button className="linkButton" onClick={()=>onOpen(resource.iri!)}>{resource.label??resource.iri}</button>:resource.label??resource.iri??resource.id}</h3>
    {resource.description&&<p>{resource.description}</p>}<section aria-label="业务含义范围与未知"><FieldTable value={{business_meaning,applicability,unknowns}}/></section>
    <Tag>{resource.kind??"语义资源"}</Tag>{Object.keys(otherSemantic).length>0&&<FieldTable value={otherSemantic}/>}<FieldTable value={attributes}/>
    {resource.projection&&<Alert type="warning" message="当前投影有省略" description={<FieldTable value={resource.projection}/>}/>}
    {Boolean(resource.warnings?.length)&&<FieldTable value={resource.warnings}/>}
    <details aria-label="资源技术详情"><summary>资源身份、底层分类与技术位置</summary><FieldTable value={{iri:resource.iri,ontology_id:resource.ontology_id,assertion_kind:resource.assertion_kind,source_graph_iri:resource.source_graph_iri,source_signature:resource.source_signature,derived_state:resource.derived_state,...technical}}/></details>
  </article>;
}
type ResourceLocation = {graphSetId:string; ontology_id:string; ontology_name:string};
type ModelRow = SemanticResource & { graphSetId: string; ontology_id: string; locations:ResourceLocation[] };
type Envelope = {items:SemanticResource[]; warnings?:unknown[]; truncated?:boolean; paging?:{complete:boolean;has_more?:boolean;truncated?:boolean}; source_signature?:string};
export function SemanticModelPage({projectId,ontologies,request,initialView=""}: {projectId:string;ontologies:Ontology[];request:WorkbenchRequest;initialView?:string}) {
  const [view,setView]=useState(initialView);
  const [scope,setScope]=useState("");
  const [search,setSearch]=useState("");
  const [rows,setRows]=useState<ModelRow[]>([]);
  const [relations,setRelations]=useState<SemanticResource[]>([]);
  const [selected,setSelected]=useState("");
  const [locationIndex,setLocationIndex]=useState(0);
  const [detail,setDetail]=useState<SemanticResource|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [limits,setLimits]=useState<unknown[]>([]);
  const [revision,setRevision]=useState(0);
  useEffect(()=>setView(initialView),[initialView]);
  useEffect(()=>{
    let cancelled=false;setRows([]);setRelations([]);setDetail(null);setError("");setBusy(true);
    const selectedOntologies=ontologies.filter(o=>!scope||o.id===scope);
    Promise.all(selectedOntologies.map(async ontology=>{
      const [sets,workspace]=await Promise.all([listGraphSets(request,{scopeType:"ontology",scopeId:ontology.id,status:"active"}),request<{default_graph_set_id:string|null}>(`/ontologies/${ontology.id}/workspace-context`)]);
      if(!sets.graph_sets.length)return {items:[],relations:[],warnings:[`${ontology.name}: 尚无可查询 GraphSet`]};
      const gs=workspace.default_graph_set_id;
      if(!gs||!sets.graph_sets.some(s=>s.id===gs))return {items:[],relations:[],warnings:[`${ontology.name}: 默认 GraphSet 未就绪，不能用其他活动集合替代`]};
      const [resources,edges]=await Promise.all([readModel<Envelope>(request,gs,"resource-list",{fieldSet:"detail",limit:500}),readModel<Envelope>(request,gs,"entity-relations",{limit:500})]);
      return {items:resources.items.map(r=>({...r,graphSetId:gs,ontology_id:ontology.id,locations:[{graphSetId:gs,ontology_id:ontology.id,ontology_name:ontology.name}]})),relations:edges.items,warnings:[...(sets.graph_sets.length>1?[`${ontology.name}: 当前读取默认 GraphSet ${gs}；另有 ${sets.graph_sets.length-1} 个活动集合未纳入此范围`]:[]),...(resources.warnings??[]),...(edges.warnings??[]),...(resources.paging?.complete===false||edges.paging?.complete===false||resources.items.length>=500||edges.items.length>=500?["达到读取上限，当前列表／关联图可能不完整"]:[])]};
    })).then(results=>{if(cancelled)return;const unique=new Map<string,ModelRow>();results.flatMap(r=>r.items).forEach(r=>{if(!r.iri)return;const existing=unique.get(r.iri);if(existing)existing.locations.push(...r.locations);else unique.set(r.iri,r);});setRows([...unique.values()]);setRelations(results.flatMap(r=>r.relations));setLimits(results.flatMap(r=>r.warnings));}).catch(cause=>{if(!cancelled)setError(String(cause));}).finally(()=>{if(!cancelled)setBusy(false);});
    return ()=>{cancelled=true;};
  },[projectId,ontologies,request,scope,revision]);
  const selectedRow=rows.find(r=>r.iri===selected);
  const selectedLocation=selectedRow?.locations[locationIndex]??selectedRow?.locations[0];
  useEffect(()=>{
    if(!selectedRow||!selectedLocation){setDetail(null);return;}
    let cancelled=false;setDetail(null);
    request<SemanticResource>(`/semantic/resources/${encodeURIComponent(selectedRow.iri!)}?graph_set_id=${encodeURIComponent(selectedLocation.graphSetId)}&include=asserted`).then(value=>{if(!cancelled)setDetail({...selectedRow,...value,ontology_id:selectedLocation.ontology_id});}).catch(cause=>{if(!cancelled)setError(String(cause));});
    return()=>{cancelled=true;};
  },[selectedRow,selectedLocation,request]);
  const visible=rows.filter(r=>{
    const sem=(r.detail_fields?.semantic_definition??r.data?.semantic_definition) as {semantic_role?:string}|undefined;
    return (!view||sem?.semantic_role===view)&&(!search||[r.label,r.iri,JSON.stringify(sem)].join(" ").toLowerCase().includes(search.toLowerCase()));
  });
  const graph=useMemo(()=>{
    const linked=relations.filter(r=>r.source===selected||r.target===selected);
    const ids=new Set([selected,...linked.flatMap(r=>[String(r.source),String(r.target)])]);
    const nodes=rows.filter(r=>r.iri&&ids.has(r.iri)).map(r=>({id:r.iri!,label:r.label??r.iri!}));
    const known=new Set(nodes.map(n=>n.id));
    const edges:ForceGraphEdge[]=linked.filter(r=>known.has(String(r.source))&&known.has(String(r.target))).map((r,i)=>({id:`relation-${i}`,source:String(r.source),target:String(r.target),label:String(r.label??r.relation??"")}));
    return {nodes,edges};
  },[selected,relations,rows]);
  return <section className="v41Page" aria-label="semantic-model-page"><Card title="语义模型"><div className="v41Form">
    <label>Ontology 范围<select aria-label="Ontology 范围" value={scope} onChange={e=>{setScope(e.target.value);setSelected("");}}><option value="">全部获准模型</option>{ontologies.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
    <label>阅读视角<Select aria-label="阅读视角" value={view} onChange={setView} options={[{value:"",label:"全部"},...semanticViews.map(([value,label])=>({value,label}))]}/></label>
    <label>筛选已读取列表<Input aria-label="筛选已读取列表" value={search} onChange={e=>setSearch(e.target.value)}/></label><Button loading={busy} onClick={()=>setRevision(r=>r+1)}>刷新模型</Button>
    </div><p className="inlineHint">角色来自真实语义声明。七个视角共享同一资源身份，脚本仅供阅读。业务角色与权限角色、Agent 角色分别管理。</p></Card>
    {error&&<Alert type="error" message={error}/>}{limits.length>0&&<Card title="读取限制"><FieldTable value={limits}/></Card>}
    <div className="v41Split"><Card title={`模型列表 · ${visible.length}`} loading={busy}><ul className="v41ResourceList">{visible.map(r=><li key={r.iri}><button aria-pressed={selected===r.iri} onClick={()=>{setSelected(r.iri!);setLocationIndex(0);}}><strong>{r.label??r.iri}</strong><small>{String((r.detail_fields?.semantic_definition as {semantic_role?:string})?.semantic_role??"未声明角色")}</small></button></li>)}</ul>{!busy&&!visible.length&&<p>当前范围暂无匹配资源；未取完不表示模型不存在。</p>}</Card>
    <Card title="定义详情" aria-label="模型定义详情">{selectedRow ? <><ResourceCard resource={detail??selectedRow}/><label className="v41LocationChoice">资源读取位置<select aria-label="资源读取位置" value={locationIndex} onChange={e=>setLocationIndex(Number(e.target.value))}>{selectedRow.locations.map((location,i)=><option key={`${location.ontology_id}-${location.graphSetId}`} value={i}>{location.ontology_name}</option>)}</select></label><details className="v41StateDetails" aria-label="模型读取位置详情"><summary>查看 Ontology 与 GraphSet 技术位置</summary><FieldTable value={selectedRow.locations}/></details></>:<p>选择定义查看业务含义、属性与关联。</p>}</Card></div>
    {selectedRow&&<Card title="关联语义图"><div className="v41Graph"><ForceGraphCanvas nodes={graph.nodes} edges={graph.edges} selectedNodeId={selected} onSelectNode={id=>id&&setSelected(id)} emptyTitle="当前读取范围内无可显示关联"/></div><details className="v41StateDetails"><summary>查看已读取关联的原始字段</summary><FieldTable value={relations.filter(r=>r.source===selected||r.target===selected)}/></details><p className="inlineHint">关联未读全时不能声称没有引用。图只表达建模语义。</p></Card>}
  </section>;
}
