import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Input, Select, Modal, Tag } from "antd";
import type { Ontology } from "../types";
import type { WorkbenchRequest } from "./workbenchTypes";
import { FieldTable, ResourceCard, type SemanticResource } from "./SemanticModelPage";
import { semanticViews } from "./semanticViews";
export type ContextResult = {
  scope: Record<string, unknown>; query: Record<string, unknown>; result_status: string;
  primary_matches: SemanticResource[]; related_context: SemanticResource[];
  matches_page: {next_match_cursor?: string | null; truncated?: boolean};
  context_page: {next_context_cursor?: string | null; truncated?: boolean; expansion?: unknown};
  recall: Record<string, unknown>; warnings: {code: string; message: string}[]; truncated: boolean;
};
export function ContextQueryPage({projectId, ontologies, request}: {projectId: string; ontologies: Ontology[]; request: WorkbenchRequest}) {
  const [query,setQuery] = useState("");
  const [ontologyIds,setOntologyIds] = useState<string[]>([]);
  const [roles,setRoles] = useState<string[]>([]);
  const [types,setTypes] = useState<string[]>([]);
  const [assertions,setAssertions] = useState<string[]>([]);
  const [selected,setSelected] = useState<SemanticResource|null>(null);
  const [mode,setMode] = useState("hybrid");
  const [detail,setDetail] = useState("full");
  const [depth,setDepth] = useState(1);
  const [limit,setLimit] = useState(20);
  const [budget,setBudget] = useState(100);
  const [result,setResult] = useState<ContextResult|null>(null);
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const generation = useRef(0);
  const input = JSON.stringify({project_id:projectId, scope_mode:ontologyIds.length ? "ontologies":"project", ontology_ids:ontologyIds, query, semantic_roles:roles.length ? roles:null, resource_types:types.length ? types:null, assertion_types:assertions.length ? assertions:null, search_mode:mode, context_detail:detail, depth, limit, context_limit:budget});
  useEffect(()=>{generation.current++; setResult(null);setSelected(null);setError("");setBusy(false);},[input]);
  async function run(cursor?: "match"|"context") {
    const ticket=++generation.current;
    setBusy(true);setError("");
    try {
      const body=JSON.parse(input);
      if(cursor==="match") body.match_cursor=result?.matches_page.next_match_cursor;
      if(cursor==="context") body.context_cursor=result?.context_page.next_context_cursor;
      const next=await request<ContextResult>("/semantic/context:query",{method:"POST",body:JSON.stringify(body)});
      if(ticket!==generation.current)return;
      // Context cursor owns the current match page; keep its roots visible.
      setResult(cursor==="context" ? {...next, primary_matches: result?.primary_matches??next.primary_matches, matches_page:result?.matches_page??next.matches_page, related_context:[...(result?.related_context??[]),...next.related_context]}:next);
    }catch(cause){if(ticket===generation.current){setError(String(cause));setResult(null);}}
    finally{if(ticket===generation.current)setBusy(false);}
  }
  async function openResource(resource:SemanticResource) {
    if(!resource.iri||!resource.ontology_id)return;
    const ticket=generation.current;setSelected(null);setError("");
    try {const workspace=await request<{default_graph_set_id:string|null}>(`/ontologies/${resource.ontology_id}/workspace-context`);
      if(!workspace.default_graph_set_id)throw new Error("当前授权范围暂无默认资源 GraphSet");
      const detail=await request<SemanticResource>(`/semantic/resources/${encodeURIComponent(resource.iri)}?graph_set_id=${encodeURIComponent(workspace.default_graph_set_id)}&include=${resource.assertion_kind==="inferred"||resource.assertion_kind==="derived"?"asserted-plus-reasoning":"asserted"}`);
      if(ticket===generation.current)setSelected({...resource,...detail,data:undefined,projection:undefined});
    }catch(cause){if(ticket===generation.current)setError(String(cause));}
  }
  return <section aria-label="context-query-page" className="v41Page">
    <Card title="跨视角语义检索"><form onSubmit={e=>{e.preventDefault();void run();}} className="v41Form">
      <label>查询表达式<Input aria-label="查询表达式" value={query} onChange={e=>setQuery(e.target.value)} /></label>
      <label>模型范围<Select aria-label="模型范围" mode="multiple" placeholder="整个项目" value={ontologyIds} onChange={setOntologyIds} options={ontologies.map(o=>({value:o.id,label:o.name}))}/></label>
      <label>主命中语义角色<Select aria-label="主命中语义角色" mode="tags" value={roles} onChange={setRoles} options={semanticViews.map(([value,label])=>({value,label}))}/></label>
      <label>资源类型<Select aria-label="资源类型" mode="multiple" value={types} onChange={setTypes} options={["concept","instance","relation","fact","operation","mapping","metric"].map(value=>({value}))}/></label>
      <label>陈述类型<Select aria-label="陈述类型" mode="multiple" value={assertions} onChange={setAssertions} options={[{value:"asserted",label:"已断言"},{value:"derived",label:"OWL 派生"}]}/></label>
      <label>召回模式<select aria-label="召回模式" value={mode} onChange={e=>setMode(e.target.value)}><option>hybrid</option><option>lexical</option></select></label>
      <label>上下文投影<select aria-label="上下文投影" value={detail} onChange={e=>setDetail(e.target.value)}><option>full</option><option>compact</option></select></label>
      <label>展开深度<input type="number" min={0} max={3} value={depth} onChange={e=>setDepth(Number(e.target.value))}/></label>
      <label>主命中页大小<input type="number" min={1} max={100} value={limit} onChange={e=>setLimit(Number(e.target.value))}/></label>
      <label>上下文预算<input type="number" min={0} max={1000} value={budget} onChange={e=>setBudget(Number(e.target.value))}/></label>
      <Button aria-label="查询" type="primary" htmlType="submit" loading={busy} disabled={!query.trim()}>查询</Button>
    </form><p className="inlineHint">语义角色只筛选主命中。空结果或读完当前页不能证明业务知识不存在或已经完整。</p></Card>
    {error&&<Alert type="error" message={error} description="游标过期、模型版本或授权范围变化时，请重新查询。"/>}
    {result&&<><Card title="范围与检索限制"><FieldTable value={{scope:result.scope, recall:result.recall, expansion:result.context_page.expansion, truncated:result.truncated}}/>{result.warnings.map((w,i)=><Alert key={i} type="warning" message={w.code} description={w.message}/>)}</Card>
    <div className="v41Split"><Card title="主命中"><Tag>{result.primary_matches.length}</Tag>{result.primary_matches.map((r,i)=><ResourceCard key={`${r.iri}-${i}`} resource={r} onOpen={()=>void openResource(r)}/>)}<Button disabled={busy||!result.matches_page.next_match_cursor} onClick={()=>void run("match")}>下一页主命中</Button></Card><Card title="关联上下文"><Tag>{result.related_context.length}</Tag>{result.related_context.map((r,i)=><ResourceCard key={`${r.id}-${i}`} resource={r} onOpen={()=>void openResource(r)}/>)}<Button disabled={busy||!result.context_page.next_context_cursor} onClick={()=>void run("context")}>继续当前页上下文</Button></Card></div></>}
    <Modal title="精确资源详情" open={!!selected} onCancel={()=>setSelected(null)} footer={null} width={800}>{selected&&<ResourceCard resource={selected}/>}</Modal>
    {!result&&!busy&&!error&&<Card>输入查询取得受授权的语义上下文。</Card>}
  </section>;
}
