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

UI 启动后先调用 `/api/auth/me`；无有效 session 时显示登录页。登录成功后使用 HttpOnly session，
写请求自动发送 double-submit CSRF header。运行期 401 会清空 UI 主体并回到登录页，logout 清除
session/CSRF cookie；用户名、密码和 API key 都不会写入 localStorage/sessionStorage。

## 当前页面

- Home：Project 与 Ontology 的创建、选择和删除。
- Overview：Project Brief、结构化需求问题和 Project 级 Evidence Reference。
- Modeling：Classes、Entities、Rules 和 Facts 的当前 RDF 读模型视图。
- Debug：语义治理/运行状态、Build Context、Recall、MCP Tools 和 Graph Sets。
- Settings：编辑锁与 `/api/health/dependencies` 的 PostgreSQL/Oxigraph 状态。

Evidence 页面只保存文档名和原文片段，不上传或解析完整文档。Build Context 页面只读显示
workspace version、lease/fence/recovery、最近 Modeling Batch、Attempt、Item 和 Finding；它不会
触发 apply 或恢复。

代码中仍有部分 legacy 页面组件和 URL tab 兼容重定向。它们不表示旧 Evidence Artifact、
Proposal/Review、Version/Publication、Catalog/Connector 或 Neo4j 写入 API 仍受支持。

## Agent 查询边界

旧 `POST /api/agent-test/run` 和 Agent Test 页面已移除。当前面向外部 Agent 的查询入口是
Context Query 与 scoped SPARQL；平台返回结构化事实和诊断状态，最终自然语言答案由外部 Agent 生成。

## 数据流与安全

```text
React UI -> FastAPI /api -> PostgreSQL + RDF Dataset/Oxigraph
```

UI 不直接连接数据库。backend 从 session 解析全组织 admin 主体，并使用显式
`ONTOLOGY_UI_ORIGINS` allowlist 校验 session 写请求的浏览器 Origin；Vite `changeOrigin` 改写后的
backend Host 不参与信任判断。

## 验证

```bash
cd frontend
npm run build
npx playwright test
```

其中三个真实 backend/Oxigraph contract 用例需要通过 `ONTOLOGY_PLAYWRIGHT_API_KEY` 注入专用的
全组织 admin 测试 key；未配置时仅跳过这三个会写入真实运行时的用例，其余 UI 用例仍执行。

手工验证应覆盖 Project/Ontology 选择、Overview、Evidence、Classes/Entities/Rules/Facts、Debug、
Build Context、Recall、MCP Tools、Graph Sets 和 Settings 的 loading/empty/error 状态，并确认
依赖健康显示 PostgreSQL 与 Oxigraph。
