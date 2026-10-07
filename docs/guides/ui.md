# UI

frontend 是 `frontend/` 下的 React/Vite 项目阅读工作区，当前范围为
[v4.2 五 Tab](../requirements/requirements-v4.2.md)。

```bash
cd frontend
npm install
npm run dev
```

默认请求同源 `/api`。一键启动使用 preview `http://127.0.0.1:5173/`，将 `/api` 代理到
backend `8001`；单独运行 dev server 可使用 `VITE_API_BASE_URL` 指定后端地址。

UI 先调用 `/api/auth/me`；没有有效 session 时显示管理员登录。登录使用 HttpOnly session，
退出沿用现有会话合同。运行期 401 回到登录页；用户名、密码、API Key 和接口响应不写入
localStorage/sessionStorage。普通用户的 Key 访问方式没有因前端重写而改变。

## 五个页面

| 页面 | 内容与交互 |
| --- | --- |
| 概览 | 项目介绍、一句话进度、获准 CQ、正式验收进度；可刷新或选择已有版本／报告 |
| 模型浏览 | 图谱画布、已加载节点搜索、全部／七视角过滤、节点基本信息、缩放与拖动 |
| 召回测试 | 输入 query，通过项目范围的受治理 Context Query 返回节点主命中，支持加载更多 |
| 成员权限 | 只读已有权限角色、说明及 Grant 原值 |
| 设置 | 语言偏好、当前账号、退出登录 |

顶部项目选择只读取可访问项目，不创建或管理项目／Ontology。没有 Ontology 的项目仍可
进入概览、成员权限和设置；没有可访问项目时设置中的账号和语言仍可用。
导航为五个同级入口。旧页面链接或旧浏览器 Tab 状态回到概览，Class 不再有专页、
专属列表、导航或管理界面；已有分类信息参与统一模型阅读。

概览只显示已绑定项目的公开产物。运行生命周期不证明业务已完成；无可核实业务进度时
显示未知。最近终态记录标为历史，CQ 冻结版本与正式报告保持各自绑定；局部 PASS、
公开回归或旧报告均不合并成当前全项目 PASS。隐藏题、参考答案、答案点与私有诊断不展示。

模型浏览有界读取当前项目各 Ontology 默认 GraphSet：节点来自 `resource-list`，关系来自
`resource-relations`，同一 IRI 保留一个节点及其读取位置。搜索只定位已加载节点，
视角根据真实语义声明过滤；部分加载、工作空间未就绪、空模型与无匹配分别说明。
前端不把图谱中未显示当作项目没有该知识。

召回只呈现节点主命中，固定使用已有 hybrid 召回、已断言内容和 depth=0；不生成答案、
展示复杂检索参数、运行 SQL／API 或自动验收。修改 query 或切换项目会清除旧结果与游标，
召回降级、未取完、空结果与错误按实际接口说明。

## 退役与访问边界

旧 Brief／访谈编辑、CQ 工作区、场景地图、运行记录、独立 Class／Entity 页、规则与 Facts
专页、图管理、校验／推理操作、Build Context、MCP Tools、Key／保护集／成员配置管理、
编辑锁、健康诊断及其专属前端代码退役。设置或节点详情不承接这些功能。
这次退役不删除后端／MCP 能力、模型、历史报告或建模运行证据。

```text
React UI -> FastAPI /api -> PostgreSQL + RDF Dataset/Oxigraph
```

UI 不直接连接数据库；模型、查询和角色读取由后端按现有合同授权。
成员身份、业务角色和权限 Grant 分别表达，浏览器不自报或推断有效授权。
Context Query 与 scoped SPARQL 仍是外部 Agent 的现有读取入口。

## 验证

```bash
cd frontend
npm run build
npx playwright test
```

页面测试与真实 backend／Oxigraph contract 测试分别记录；真实 contract 用例通过已有
受保护本地凭据或 `ONTOLOGY_PLAYWRIGHT_API_KEY` 接入，凭据不输出到日志或页面。
桌面和 390px 小屏检查五 Tab、图谱操作空间、键盘／focus、加载／缺内容／部分读取／错误，
并以实际截图核对现有浅色、白面板、紫色强调和控件风格。
本版本的具体开发与独立验收证据见
[交付记录](../delivery/records/2026-10-07-v4-2-five-tab-frontend-delivery-record.md)。
