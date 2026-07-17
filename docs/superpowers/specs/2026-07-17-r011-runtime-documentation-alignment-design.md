# R-011 当前 API、MCP 与配置文档对齐设计

## 1. 状态与决策摘要

实现状态：`已实现`（2026-07-17，plan review Round 3 `PASS`，独立测试 Round 2 `PASS`）。
Round 1/2 的三个 High 均已接受并修订：README 支持安装的
`skills/ontology-builder` 仍依赖已删除工具；CI 不能依赖本机 Codex 绝对路径；手写 eval trace
不能替代隔离新上下文的 Skill forward test。Round 3 无剩余 Critical/High。

本设计落实 `docs/requirements-v1.0.md` 的 R-011。用户已确认按完整范围交付，但文档只能描述
当前真实能力：R-008 仍未实现，R-009 仍部分实现，R-010 仍未实现，不得把规划中的认证、查询诊断
或 Dify 验收写成已可用功能。

R-011 采用“运行时注册表生成接口清单、人工文档解释契约、CI 检查两者同步”的边界：

1. FastAPI `app.openapi()` 是 HTTP 操作清单的唯一权威来源。
2. FastMCP `mcp.list_tools()` 是 MCP 工具清单的唯一权威来源。
3. README、API、MCP、平台指南、UI、架构和仓库指引只描述当前实际启动、配置和边界。
4. 自动化工具只维护带标记的清单，不生成业务解释，也不修改需求状态。
5. CI 运行只读 `--check`；开发者显式运行 `--write` 才更新生成区块。

## 2. 当前问题

2026-07-17 的运行时核对结果：

- FastAPI 注册 115 个 HTTP 操作，FastMCP 注册 55 个工具。
- `docs/api.md` 同时描述当前接口和已经移除的 Version、Proposal、Catalog、Neo4j Entity 等接口。
- `docs/mcp.md` 仍列出已经从 `register_all` 删除的 governance、catalog、entity、fact 工具。
- README 声称 `ADMIN_TOKEN` 和 `MCP_API_KEY` 已生效，但当前 `Settings` 没有这些字段，HTTP/MCP
  也没有认证依赖。
- 本地一键启动使用 backend `8001`、frontend `5173`、PostgreSQL host port `5434` 和 Oxigraph
  `7878`；README/API/UI/平台指南仍混用手动启动的 `8000`、PostgreSQL `5432` 和 Neo4j 表述。
- `AGENTS.md` 仍指向不存在的 catalog 模块，并把当前 RDF/Oxigraph 路径描述成 Neo4j 路径，可能
  直接误导后续需求开发。
- README 支持安装的 `skills/ontology-builder` 仍指导 Agent 调用已经删除的 Evidence Artifact、
  Proposal/Review、Catalog/Connector、Entity/Fact MCP 工具；Skill 的 references、evals 和上传脚本
  也固化了这些旧协议。
- 仓库没有 CI 工作流，接口变更后没有文档漂移门禁。

## 3. 目标与非目标

### 3.1 目标

- README 的环境变量、认证状态、默认端口、启动命令与当前代码一致。
- `docs/api.md` 只列出真实注册的 HTTP 操作，并解释当前主要契约和已知缺口。
- `docs/mcp.md` 只列出真实注册工具；完整清单由 runtime registry 生成。
- 修正会影响开发判断的 `AGENTS.md`、`docs/platform-guide.md`、`docs/ui.md` 和
  `docs/architecture.md` 当前态矛盾。
- 将 README 支持安装的 `skills/ontology-builder` 主流程、references、evals、scripts 和
  `agents/openai.yaml` 收敛到 R-001 至 R-007 当前接口。
- 建立可重复的 `--write` / `--check` 文档同步命令和 CI 门禁。
- 同步需求总表、当前实现基线和 R-011 实现/验证结果。

### 3.2 非目标

- 不实现 R-008 的 API key、session、授权、actor 覆盖或 secret 扫描。
- 不重构 R-009 Agent Test，不删除其现有 LLM 调用。
- 不建立 R-010 Dify 数据集、外部 Agent 执行器或评测报告。
- 不恢复旧 Version、Proposal、Catalog、Connector、Neo4j Entity 或旧 MCP 工具。
- 不保留 Skill 对 Evidence Artifact 上传/解析、人工 Proposal Review、Publication、Catalog 或
  Connector 的兼容指引；这些当前不可执行流程直接移除，不建立模拟层。
- 不承诺尚未注册的接口，不为历史需求文档生成接口清单。
- 不把所有 Markdown 自动生成；业务语义、限制和缺口仍由人工维护。

## 4. 文档契约

### 4.1 README 与配置

README 区分两种运行方式：

- `./scripts/start-local.sh`：backend `8001`，frontend preview `5173`，PostgreSQL host port
  `5434`，Oxigraph `7878`。
- 手动 `uvicorn`：未显式传 `--port` 时 backend `8000`；手动 Vite dev server 使用其命令输出端口。

环境变量表以 `Settings` 和启动脚本实际读取项为准。认证章节必须明确：

- 当前 HTTP 与 MCP 均未实施 R-008 认证；只适合受信任本地环境。
- `ADMIN_TOKEN`、`MCP_API_KEY`、`ONTOLOGY_MCP_API_KEY` 目前均不是已生效配置。
- R-008 文档中的未来变量和协议不能出现在“当前配置”表中。

`.env.example` 的 PostgreSQL host port 与一键启动默认值统一为 `5434`，避免首次创建
`backend/.env` 后与 Docker Compose 暴露端口冲突。该变更只修正示例，不改变运行时代码。

### 4.2 HTTP API 文档

重写 `docs/api.md`：

- 顶部说明一键启动与手动启动 Base URL。
- 明确当前无认证，R-008 未实现。
- 保留当前主要契约、错误语义和示例。
- 完整操作清单放在生成标记之间，按 OpenAPI tag、method、path 稳定排序。
- 每行来自 OpenAPI operation，包含 method、完整 `/api` path 和 summary。
- 移除所有未注册旧接口及其示例，历史能力只能在历史需求/设计文档中查阅。

### 4.3 MCP 文档

重写 `docs/mcp.md`：

- 启动命令和 Codex 配置指向真实 backend cwd。
- 明确当前进程没有认证，R-008 未实现；工具参数不接受通用 `api_key`。
- 说明公共返回/错误边界以实际工具 schema 和实现为准，不虚构统一 envelope。
- 完整工具清单放在生成标记之间，按 registry category 和 name 稳定排序。
- 每行包含工具名、描述、必填参数、全部参数和源文件。
- 手工部分只解释当前 55 个工具的主要工作流，不维护第二份完整名称列表。

### 4.4 相关当前态文档

- `AGENTS.md`：移除不存在的 catalog 文件指引和 Neo4j 当前路径；指向 RDF/Oxigraph、R-001 至
  R-007 的真实模块；修正一键启动端口说明。
- `docs/platform-guide.md`：修正启动、健康检查、存储和认证说明；删除对旧治理接口的当前态描述。
- `docs/ui.md`：修正默认 API base、依赖健康和 Agent Test 当前边界。
- `docs/architecture.md`：把 PostgreSQL + RDF Dataset/Oxigraph 标为当前权威存储；Neo4j 只在
  明确的历史背景中出现，不能作为当前写入路径。
- `docs/requirements-v1.0.md`：修正过期的“当前实现基线”行；R-008/R-009/R-010 状态保持不变；
  R-011 只有在全部门禁通过后改为 `已实现`。

### 4.5 ontology-builder Skill

README 继续支持通过 symlink 安装仓库内 Skill，因此 Skill 必须是当前可执行客户端，不采用“保留旧
流程但标记 deprecated”的方案。更新后的主流程固定为：

1. 用 `get_project_build_context` 恢复 Project 当前事实；需要写入时创建或恢复 Build Session。
2. 用 Project Brief、Interview Answer 和 Competency Question 工具完成需求澄清。
3. 外部 Agent 自行读取资料，只把实际使用的 `document_name + excerpt` 保存成 Evidence Reference；
   不上传完整文件、不等待平台解析。
4. 获取 Ontology workspace/modeling context，获取 lease，通过 `submit_modeling_batch` 执行
   `dry_run` 和 apply；不经过 Proposal/Review/Publish 队列。
5. 用 Context Query、scoped SPARQL、read model 和 lineage 验证结果；保存 checkpoint，完成或取消
   Build Session。
6. 人工确认只影响 Agent 是否继续提交下一批，不伪装成平台 approve/publish 能力。

Skill 资源按此收敛：

- 重写 `SKILL.md`，保留简洁核心流程和 `.ontology-build.md` 本地工作记忆边界。
- 保留并修正仍适用的 interview、ambiguity、modeling references；用 Modeling Batch/Evidence
  Reference 格式替换 Proposal/Evidence Artifact/Review 说明。
- 删除仅服务于已移除 multipart Evidence Artifact endpoint 的上传脚本及相应测试；不让一个失效
  helper 看起来像受支持入口。
- 更新 eval cases/traces 为 Build Session、Evidence Reference、Modeling Batch、Context Query 和
  lineage 场景。
- 在 eval contract 中把 `required_tools` 与普通 `required_actions` 分开；CI 从所有 cases 聚合
  `required_tools` 并逐项验证存在于 runtime registry。Skill 正文/引用中宣称的 MCP 调用必须进入
  同一 dependency contract，独立测试进行交叉核对。
- 提供仓库内可移植的 Skill 结构校验，检查 frontmatter、名称、description、资源链接和
  `agents/openai.yaml`；本机可额外运行 `skill-creator` 的 `quick_validate.py` 交叉验证，但 CI
  不依赖 `/home/.../.codex` 路径。
- 实现稳定后，由主 Agent 启动一个 `fork_turns=none` 的新 Agent，直接给出原始 Skill 路径和一个
  mock/read-only 建模场景，不提供预期动作或本次缺陷结论。forward-test Agent 不访问 live service、
  不修改仓库，只输出其计划调用的工具、顺序、停止条件和边界；独立 tester 将真实输出与当前
  registry/设计核对并记录到共享测试计划。未通过 forward test 不能关闭 R-011。

## 5. 自动生成与校验

新增 `scripts/sync-interface-docs.py`：

- 从仓库根目录定位 backend 和目标文档，不依赖调用者 cwd。
- 将 backend 加入 `sys.path`，导入 `app.main.app` 与 `app.api.mcp_catalog._enumerate_tools`。
- OpenAPI 仅接受 `GET/POST/PUT/PATCH/DELETE`，忽略 FastAPI 自带 `/docs`、`/redoc`、
  `/openapi.json`，因为它们不在 schema `paths` 中。
- HTTP 和 MCP 生成内容使用固定排序、固定 Markdown 转义和固定换行，重复执行字节稳定。
- `--write` 仅替换两个文档的生成标记区块；标记缺失、重复或顺序错误时失败，不重写整份文件。
- `--check` 比较期望区块与当前文件，不写文件；漂移时列出目标文件并返回非零，提示运行
  `cd backend && uv run python ../scripts/sync-interface-docs.py --write`。
- 默认模式为 `--check`，避免误改文档。

新增自动化测试覆盖：

- 当前运行时 inventory 与两个生成区块完全一致。
- `--write` 后再次 `--check` 通过且文件不再变化。
- 文档中显式写出的 `METHOD /api/path` 引用均存在于 OpenAPI；允许 query string，但校验 path。
- 生成 MCP 清单恰好覆盖 registry，不多不少、无重复。
- README 当前配置不再声称已实施认证，关键端口与脚本一致。
- R-008/R-009/R-010 状态没有被误改成已实现。
- ontology-builder eval contract 的每个 `required_tool` 都存在于 FastMCP registry，且 Skill 文档
  不再声称调用已删除工具；eval runner 拒绝未注册或未声明的工具依赖。

新增 `.github/workflows/docs-sync.yml`，在 push 和 pull request 上安装 backend dev 依赖并运行：

```bash
cd backend
uv run python ../scripts/sync-interface-docs.py --check
uv run pytest tests/test_documentation_sync.py -q
uv run python ../skills/ontology-builder/evals/validate_skill.py
uv run python ../skills/ontology-builder/evals/run_evals.py \
  --traces ../skills/ontology-builder/evals/example-traces.json \
  --check-registry
```

`validate_skill.py` 和 `run_evals.py` 均位于仓库内，只使用 Python 标准库及已安装 backend 环境；
`--check-registry` 从 backend import 当前 FastMCP registry 并验证 `required_tools`。该检查不启动
PostgreSQL、Oxigraph、backend 或 frontend；registry 枚举已经验证不需要外部依赖。

CI 负责确定性结构/契约门禁；fresh-agent forward test 依赖协作 Agent，不伪装成 GitHub runner
可以执行的普通单元测试，而是作为本需求独立验收的必需记录。

## 6. 错误与兼容性

- 生成标记损坏：工具 fail closed，不猜测替换范围。
- runtime import 失败：CI 失败并显示 Python 异常，不能用旧缓存掩盖。
- 文档漂移：`--check` 非零退出，不自动提交生成结果。
- 描述为空：仍生成工具/操作行，以空描述占位，不遗漏注册项。
- 接口变更：开发者先改代码，再运行 `--write` 并提交文档；CI 验证最终一致。
- 旧外部调用方不受影响，因为 R-011 不改变 HTTP/MCP runtime。

## 7. 验收标准

1. README、`.env.example`、启动命令、端口和当前无认证事实一致。
2. `docs/api.md` 生成清单与 115 个当前 HTTP 操作完全一致，且没有旧接口被描述为当前能力。
3. `docs/mcp.md` 生成清单与 55 个当前 MCP 工具完全一致，且无第二份手工全量清单。
4. 相关开发/运行文档不再把 Neo4j、旧 Catalog/Proposal/Version 路径描述为当前实现。
5. README 安装的 ontology-builder 只使用当前 MCP/HTTP 契约，Skill dependency contract 由 registry
   自动验证，仓库可移植基础校验和更新后的 eval 全部通过，隔离新上下文 forward test PASS。
6. `--write` 幂等，`--check` 能检测 API 或 MCP registry 漂移。
7. CI 工作流执行文档和 Skill 同步测试。
8. R-008 保持未实现、R-009 保持部分实现、R-010 保持未实现；文档明确其现实影响。
9. 独立测试 PASS、全量 backend/frontend 验证通过、服务重启健康，R-011 再更新为已实现并提交。
