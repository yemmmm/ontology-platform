# UI

frontend 是 `frontend/` 下的 React/Vite 本地操作工作区。

```bash
cd frontend
npm install
npm run dev
```

frontend 默认请求同源 `/api`。一键启动使用 preview `http://127.0.0.1:5173/` 并把 `/api` 代理到
backend `8001`；单独运行 dev server 时可用 `VITE_API_BASE_URL` 指定 backend（手动 uvicorn 默认
为 `http://127.0.0.1:8000/api`）。

## 当前页面

- Home：Project 与 Ontology 的创建、选择和删除。
- Overview：Project Brief、结构化需求问题和 Project 级 Evidence Reference。
- Modeling：Classes、Entities、Rules 和 Facts 的当前 RDF 读模型视图。
- Debug：语义治理/运行状态、Build Context、Agent Test、Recall、MCP Tools 和 Graph Sets。
- Settings：编辑锁与 `/api/health/dependencies` 的 PostgreSQL/Oxigraph 状态。

Evidence 页面只保存文档名和原文片段，不上传或解析完整文档。Build Context 页面只读显示
workspace version、lease/fence/recovery、最近 Modeling Batch、Attempt、Item 和 Finding；它不会
触发 apply 或恢复。

代码中仍有部分 legacy 页面组件和 URL tab 兼容重定向。它们不表示旧 Evidence Artifact、
Proposal/Review、Version/Publication、Catalog/Connector 或 Neo4j 写入 API 仍受支持。

## Agent Test 的当前边界

Agent Test 调用 `POST /api/agent-test/run`，当前仍可能通过 OpenAI-compatible LLM 生成答案，并使用
不足以处理中文整句的简单分词。这与“平台只返回结构化上下文”的目标边界不一致，属于 R-009 的
已知缺口。当前面向外部 Agent 的目标查询入口是 Context Query 与 scoped SPARQL。

## 数据流与安全

```text
React UI -> FastAPI /api -> PostgreSQL + RDF Dataset/Oxigraph
```

UI 不直接连接数据库。当前 frontend 没有 login/session；backend 也没有认证与授权，Project 和
Ontology 隔离仅由请求范围校验提供，不能视为访问控制。只适合受信任本地环境，完整安全能力属于
R-008。

## 验证

```bash
cd frontend
npm run build
npx playwright test
```

手工验证应覆盖 Project/Ontology 选择、Overview、Evidence、Classes/Entities/Rules/Facts、Debug、
Build Context、Agent Test、MCP Tools、Graph Sets 和 Settings 的 loading/empty/error 状态，并确认
依赖健康显示 PostgreSQL 与 Oxigraph。
