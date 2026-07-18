# R-011 当前 API、MCP 与配置文档对齐共享测试计划

## 1. 测试依据与记录规则

- 需求：`docs/requirements-v1.0.md` R-011。
- 设计：`docs/superpowers/specs/2026-07-17-r011-runtime-documentation-alignment-design.md`。
- 当前功能基线：R-001 至 R-008 已实现；R-009 部分实现；R-010 未实现。第 8 节中“R-008 未实现”
  的内容属于首次交付测试记录，不能作为当前行为断言。

开发 Agent 与独立测试 Agent 必须复用本计划。测试 Agent 在第 8 节追加 Round，不覆盖此前记录，
并使用 `PASS | FAIL | BLOCKED`；修复后使用 `FIXED | STILL FAILING | REGRESSION`。

## 2. 审查重点

1. 文档是否只描述当前真实行为，没有把 R-008/R-009/R-010 目标态伪装成当前态。
2. HTTP/MCP 完整清单是否从运行时注册表生成，而不是另一份手工 allowlist。
3. 自动校验能否同时发现“新增未更新”和“删除后仍残留”的接口漂移。
4. README、`.env.example`、启动脚本和 systemd 实际端口是否一致。
5. 旧 Version/Proposal/Catalog/Connector/Neo4j 路径是否不再影响当前开发指引。
6. README 支持安装的 ontology-builder 是否只依赖 runtime registry 中真实存在的工具。

## 3. 必测场景

### A. HTTP inventory

- `app.openapi()` 中所有 GET/POST/PUT/PATCH/DELETE 操作在生成区块恰好出现一次。
- 生成区块没有 OpenAPI 中不存在的 operation。
- `/api` 前缀、path parameter、冒号 action 和 path converter 均保持真实公共路径。
- 按 tag、method、path 稳定排序；summary 中 Markdown 特殊字符不会破坏表格。
- 临时增加或删除一个测试 route 时 `--check` 失败，`--write` 可收敛，恢复后不污染仓库。

### B. MCP inventory

- `mcp.list_tools()` / `_enumerate_tools()` 的全部工具在生成区块恰好出现一次。
- name、description、required/all parameters、category 和 source file 与 registry endpoint 一致。
- deprecated compatibility 工具仍存在并明确 deprecated；未注册旧工具不出现。
- 临时注册一个测试 tool 或从测试 registry 移除一个 tool 时漂移检查失败。

### C. 文档与配置真实性

- README 明确 HTTP/UI/MCP 的认证入口、公开与受保护边界，以及 Project scope/隔离约束；不得描述
  匿名业务 API 或匿名 MCP 为当前支持路径。
- README 区分一键启动 backend `8001` 与手动 uvicorn `8000`，frontend preview 为 `5173`。
- `.env.example`、Docker Compose、Settings 和启动脚本的 PostgreSQL/Oxigraph 地址没有互相冲突。
- `docs/api.md` 不把旧 Version、Proposal、Catalog、Connector、Neo4j Entity 接口列为当前能力。
- `docs/mcp.md` 不把旧 governance、catalog、entity、fact 工具列为当前能力。
- AGENTS、platform guide、UI 和 architecture 的当前路径与实际 repo/runtime 一致。

### D. R-008/R-009/R-010 边界

- R-008 为 `已实现`；文档说明统一认证主体、scope 授权和 Project 隔离边界。
- 无凭证调用受保护业务 API 返回 `401`；认证主体跨 Project 或 scope 不足时按授权契约拒绝。公开
  `health`、认证入口和 OpenAPI/docs 保持可访问。
- R-009 仍为 `部分实现`；Agent Test 的 LLM 调用和中文分词缺口被如实记录。
- R-010 仍为 `未实现`；不存在虚构的 Dify 基准通过数字。

### E. 工具行为与失败语义

- `--check` 默认只读；成功时退出 0，文件 hash 不变。
- 有漂移时退出非零、列出文件并给出 `--write` 修复命令。
- `--write` 只改 marker 区块，重复执行后字节不变。
- marker 缺失、重复或反序时失败，不截断文档。
- 从 repo root、backend cwd 和其他 cwd 调用均定位同一仓库文件。

### F. ontology-builder Skill 对齐

- Skill 主流程使用 Project Build Context、Build Session、Evidence Reference、Modeling Batch、
  Context Query/SPARQL 和 lineage，不调用 Proposal/Review/Publish/Catalog/Connector 旧协议。
- Skill 明确资料由外部 Agent 读取，平台只保存 `document_name + excerpt`，不承诺文件上传或解析。
- eval cases 中 `required_tools` 与普通 Agent `required_actions` 分离，所有 required tool 均在 FastMCP
  registry；插入不存在的 tool 后校验必须失败。
- Skill 正文和所有 references 中宣称调用的 MCP 工具均被 dependency contract 覆盖；不存在
  `get_evidence_artifact_status`、`get_evidence_artifact_chunks`、`validate_proposal`、
  `create_data_source`、`create_semantic_mapping`、`run_connector_query` 等旧调用。
- 旧 multipart upload helper 及其测试被移除，或者 README/Skill 完全不再把它作为支持路径；本设计
  选择移除并验证无残留引用。
- `agents/openai.yaml` 与新 SKILL.md 描述一致；skill-creator `quick_validate.py` 通过。
- 更新后的 eval schema/cases/example traces 和 runner 自检通过，至少覆盖开始/恢复、证据建模、冲突、
  幂等恢复和资料 prompt injection。
- 仓库内 `validate_skill.py` 在 clean checkout 可运行，不依赖用户 home 或 Codex 安装路径；检查
  frontmatter、资源链接和 openai metadata。可用系统 `quick_validate.py` 时只作额外交叉检查。
- 主 Agent 在稳定实现上启动 `fork_turns=none` 的新 Agent，输入只包含原始 Skill 路径、mock/read-only
  场景和“不得访问 live/不得修改文件”的安全约束，不泄漏预期动作或旧工具缺陷。实际输出必须：
  使用当前工具、遵守 session/lease/evidence/batch 顺序、在需要用户决定或写入前停止、没有旧工具。
  tester 将原始输出摘要、判定和任何失败记录在第 8 节；手写 example trace 不替代此门槛。

### G. Regression、CI 与 runtime

- `tests/test_documentation_sync.py` 通过。
- 全量 backend pytest 通过；新增/修改 Python 文件 Ruff 和 format check 通过。
- frontend build 和全量 Playwright 通过，因为用户可见文档包含 UI/端口现状。
- `git diff --check` 通过；生成命令后工作区无新增漂移。
- `.github/workflows/docs-sync.yml` 语法可解析，命令在本地等价环境成功。
- ontology-builder skill 校验、eval 和 registry dependency check 纳入 CI。
- CI 中实际列出 `validate_skill.py`、`run_evals.py --check-registry`，不引用 `/home/.../.codex`。
- 服务重启后 systemd active，backend health、dependency health、frontend 均正常。
- 运行时 OpenAPI/MCP 数量与最终文档生成区块一致。

## 4. 建议自动化命令

```bash
cd backend
uv run python ../scripts/sync-interface-docs.py --check
uv run pytest tests/test_documentation_sync.py -q
uv run pytest
uv run ruff check ../scripts/sync-interface-docs.py tests/test_documentation_sync.py
uv run ruff format --check ../scripts/sync-interface-docs.py tests/test_documentation_sync.py

uv run python ../skills/ontology-builder/evals/validate_skill.py
uv run python ../skills/ontology-builder/evals/run_evals.py \
  --traces ../skills/ontology-builder/evals/example-traces.json \
  --check-registry

cd ..
# 本机存在 skill-creator 时可额外交叉检查，不作为 CI 前提：
python /home/yangxiang/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/ontology-builder

cd ../frontend
npm run build
npx playwright test

cd ..
git diff --check
```

## 5. 真实运行态验收

1. 从 `http://127.0.0.1:8001/openapi.json` 枚举 HTTP operation，与生成 API 清单逐项比较。
2. 从 `http://127.0.0.1:8001/api/mcp/tools` 枚举 MCP 工具，与生成 MCP 清单逐项比较。
3. 无 Authorization header 请求受保护 `/api/projects`，验证返回 `401`；使用合法凭证的请求只在
   主体 scope 与 Project 范围内成功。
4. 检查 `/api/health`、`/api/health/dependencies` 和 frontend `5173`。
5. 重启 `ontology-platform.service` 后重复 1 至 4，避免只验证导入态。

本需求不创建业务测试数据，不需要数据库清理。

## 6. 重启与健康门槛

R-011 修改共享配置示例和运行文档，但不改变 backend/frontend 代码。为验证文档中的运行方式，仍执行：

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:8001/api/health/dependencies
curl --fail http://127.0.0.1:5173/
```

失败时检查：

```bash
journalctl --user -u ontology-platform.service --no-pager -n 200
```

## 7. 完成门槛

- 设计、需求、README、API、MCP、config、AGENTS、platform/UI/architecture 当前态一致。
- README 安装的 ontology-builder、references、evals、scripts 和 metadata 与当前 registry 一致。
- 隔离新上下文的 ontology-builder forward test 已执行并由独立 tester 在第 8 节判定 PASS。
- 运行时生成区块覆盖全部 115 HTTP operations 和 55 MCP tools；若实现期间数量变化，以最终
  runtime registry 为准，不固化历史数字。
- CI 防漂移检查可重复运行并能证明正反例。
- 独立测试 Agent 在本文件追加 `PASS` Round，所有缺陷有明确处置。
- backend、frontend、Ruff/format、diff、restart/health 门禁全部通过。
- R-011 状态更新为已实现；R-008/R-009/R-010 状态保持真实；提交只包含 R-011 和用户已有
  R-008 文档修改中经确认需要保留的内容，不覆盖其他工作。

## 8. 独立测试记录

测试 Agent 在此追加每轮结果，不覆盖前一轮。

### Round 1（2026-07-17）— FAIL

#### 稳定测试状态

- 测试基于 `bb617e6` 的稳定未提交工作树执行。开发 Agent 已停止写入；本轮未修改产品代码或文档
  正文，只追加本测试记录。
- 测试前后的 R-011 文件集合与开发交接一致；用户原有的 R-008 需求补充保持不变。临时负向测试
  使用系统临时目录并已清理，没有创建业务数据。
- 实现审查确认 HTTP inventory 直接读取 `app.openapi()`，MCP inventory 直接读取
  `app.api.mcp_catalog._enumerate_tools()` / FastMCP registry；生成器只替换 marker 区块，默认执行
  `--check`，CI 使用仓库内 Skill 校验器，不依赖用户 home 或 Codex 安装目录。

#### 结论与缺陷

总体结论：`FAIL`。接口清单、Skill、配置、回归和真实运行态门禁均通过，但存在一个会直接违背
R-011 当前态契约的 High 缺陷，修复并重新独立测试前不能把 R-011 标为已实现。

1. **High — R-009 详细状态与总表、设计和测试基线矛盾。**
   `docs/requirements-v1.0.md` 总表把 R-009 标为 `部分实现`，但 R-009 详细条目当前写成
   `当前状态：进行中`。设计第 1、4.4 和验收标准 8，以及本计划第 1、D 节，均明确要求 R-009
   保持 `部分实现`；当前也没有 R-009 实施已启动的证据。现有
   `test_configuration_and_unimplemented_requirements_are_truthful` 只校验总表行，因此测试仍通过，
   未能发现同一权威需求文档内部的矛盾。该状态会误导后续需求开发和依赖判断。修复要求：把
   R-009 详细状态恢复为 `部分实现`，并让自动化同时校验总表和对应详细条目。

#### 通过的验收证据

- 文档同步与聚焦测试：
  - `cd backend && uv run python ../scripts/sync-interface-docs.py --check`：退出 0，输出
    `Interface documentation is synchronized.`。
  - `cd backend && uv run pytest tests/test_documentation_sync.py -q`：`10 passed in 7.26s`；包含
    自定义 `POSTGRES_PORT=5544` 时同时修正生成 `.env` 的 `POSTGRES_PORT` 与 `DATABASE_URL`。
  - 从 repo root、backend cwd 和 `/tmp` 执行默认检查均退出 0；实际执行 `--write` 后 API/MCP
    文档 SHA-256 分别仍为
    `e1ab651a6d2c9dc49c364547d716a7553d1fd5f14fe61ff228737a26b23f033c` 和
    `e269b191ef98ef940312604d84e500eb4642a9cea72047dfb84db5a5ecd5ec8d`，证明只读和幂等。
  - 隔离负向用例确认：HTTP/MCP runtime 各删除一个条目时 `--check` 返回 1 并列出两个文件，
    `--write` 后收敛；marker 缺失、重复、反序均拒绝；未知 required tool 和未声明 trace tool
    均返回 1 并同时报告 dependency/registry 错误。
  - `uv run ruff check ...`：通过；`uv run ruff format --check ...`：`2 files already formatted`；
    `git diff --check`：通过。
- ontology-builder 与 CI 等价检查：
  - 仓库校验：`Validated ontology-builder structure, 5 references, and 27 declared MCP dependencies.`。
  - eval：`Validated 6 ontology-builder eval cases and traces against the runtime registry.`；开始/恢复、
    Evidence 建模、apply/verify、冲突、幂等超时恢复和资料 prompt injection 六个场景均覆盖。
  - skill-creator `quick_validate.py`：`Skill is valid!`；从 `/tmp` 用系统 Python 运行仓库校验也通过。
  - `.github/workflows/docs-sync.yml` 可由 YAML parser 解析，Bash `-n` 和两个 eval JSON 解析通过；
    CI 文件和仓库校验脚本未引用 `/home/...` 或 `.codex`。
  - README、AGENTS、API、MCP、platform guide、UI、architecture 七份当前态文档中显式
    `METHOD /api/path` 引用全部存在于 OpenAPI。旧工具名只存在于校验器的禁止列表，不存在于
    Skill/当前能力说明中。
- 隔离新上下文 Skill forward test：`PASS`。
  - 主 Agent 使用 `fork_turns=none`，只提供原始 Skill 路径、mock/read-only 场景和禁止访问 live/
    修改文件的约束，没有泄漏预期动作或旧工具缺陷。
  - 实际输出只规划当前的 Project Build Context、workspace/session、Evidence Reference、Modeling
    Context、read model 和 Modeling Batch dry-run 调用；没有使用旧 Proposal/Catalog/Evidence
    Artifact 工具。
  - 输出在 dry-run 结果未知时停止，未提前获取 lease 或执行 apply；这符合“dry-run 不需要 lease，
    Findings/用户决定明确后才写入”的顺序。它未访问 live、未编辑文件、未虚构 Findings。
- 全量回归：
  - `cd backend && uv run pytest`：`656 passed, 3 skipped, 114 warnings in 46.88s`。
  - `cd frontend && npm run build`：通过；Vite 仅报告现有约 1.6 MB 单 chunk 警告。
  - `cd frontend && npx playwright test`：`34 passed (8.4s)`。
- 配置与真实运行态：
  - `bash -n scripts/start-local.sh` 和 `docker compose config` 通过；Compose 暴露 PostgreSQL
    `5434 -> 5432`、Oxigraph `7878 -> 7878`，实际 `Settings()` 解析到 PostgreSQL `5434` 和
    `http://localhost:7878`。
  - 重启前 live registry 与生成区块逐项相等：HTTP `115`、MCP `55`；health、dependency health
    和 frontend 均为 200。无 Authorization header 请求 `/api/projects` 返回 200（17 条），作为
    R-008 尚未实现的预期现状证据，不作为安全通过。
  - `systemctl --user restart ontology-platform.service` 后第 8 次探测就绪；unit 保持 `active
    (running)`。`/api/health` 返回 `{"status":"ok"}`，dependency health 返回 PostgreSQL/Oxigraph
    均 `ok`，frontend 返回 200。
  - 重启后再次逐项比较仍为 HTTP `115`、MCP `55`；无认证 `/api/projects` 仍返回 200，frontend
    仍返回 200。

#### 未执行项与残余风险

- 未在 GitHub 托管 runner 上实际触发 workflow；已在本机按 workflow 的所有命令做等价执行并验证
  YAML/路径可移植性，远端触发留待 push/PR。
- forward test 按设计是 mock/read-only，不访问 live 或执行真实 apply；其门槛验证 Skill 规划和停止
  行为，不能替代 R-004 已有的写入测试。
- 本需求不创建业务数据，因此无数据库清理项。临时负向文件均已删除，服务按仓库要求保留为 active。
- R-009 平台内 LLM/中文分词缺口和 R-010 无 Dify 验收仍是明确的后续需求风险；R-008 的认证、
  scope 授权和 Project 隔离已完成，R-011 只需持续保证文档与其运行态边界一致。

### Round 2（2026-07-17）— PASS

#### 稳定测试状态与 Round 1 修复

- 本轮仍基于 `bb617e6` 的稳定未提交工作树；开发者只修正 Round 1 的 High：
  `docs/requirements-v1.0.md` R-009 详细状态由 `进行中` 恢复为 `部分实现`，并扩展
  `backend/tests/test_documentation_sync.py`，同时校验 R-008/R-009/R-010 的总表状态和详细
  `当前状态`。本轮未修改产品代码或其他文档正文，只追加本记录。
- R-009 总表与详细条目现均为 `部分实现`；R-008 均为 `未实现`，R-010 均为 `未实现`。
  在临时需求文档副本中重新注入“R-009 总表部分实现、详细进行中”后，新测试按预期抛出
  `AssertionError`，证明缺陷不只被文字修正，也被自动化锁定。临时副本已清理。
- Round 1 的 High 标记为 `FIXED`。未发现 Critical、High、Medium 或 Low 新缺陷，Round 1 其他已通过
  证据继续有效。

#### Round 2 验证结果

- `cd backend && uv run python ../scripts/sync-interface-docs.py --check`：退出 0，接口文档同步。
- `cd backend && uv run pytest tests/test_documentation_sync.py -q`：`10 passed in 6.21s`。
- `cd backend && uv run ruff check ../scripts/sync-interface-docs.py tests/test_documentation_sync.py`：
  `All checks passed!`。
- `cd backend && uv run ruff format --check ../scripts/sync-interface-docs.py
  tests/test_documentation_sync.py`：`2 files already formatted`。
- `git diff --check`：通过。
- `cd backend && uv run pytest`：`656 passed, 3 skipped, 114 warnings in 42.03s`。
- `cd frontend && npm run build`：通过；仅保留 Round 1 已记录的约 1.6 MB 单 chunk 警告。
- `cd frontend && npx playwright test`：`34 passed (8.8s)`。
- 当前运行服务保持 `active (running)`；本次修复只涉及需求文字和测试，不改变 backend/frontend/
  配置，因此未重复重启，复用 Round 1 已完成的稳定工作树重启证据，并重新执行全部 live 检查：
  - `/api/health`：200，`{"status":"ok"}`；
  - `/api/health/dependencies`：200，PostgreSQL/Oxigraph 均 `ok`；
  - live OpenAPI、MCP endpoint、本地 registry 与两个生成区块逐项一致：HTTP `115`、MCP `55`；
  - frontend：200；本条为首次交付的历史证据。R-008 完成后，当前回归断言已改为无 Authorization
    header 的受保护 `/api/projects` 返回 401。
- ontology-builder Skill、CI 负向漂移、仓库可移植校验和隔离 forward test 未被本次两文件修复影响；
  Round 1 的对应 PASS 证据继续成立。

#### 清理与剩余风险

- R-011 聚焦测试只使用临时副本，没有创建业务数据。全量 Playwright 的既有
  `frontend/tests/live-contract.spec.ts` 会创建时间戳 `R006 Live` 项目/图且不自行清理；本轮根据
  精确 ID、名称、创建时间和图前缀解析并清除了 Round 1/2 两次运行唯一对应的 2 个 Project、
  2 个 Ontology 工作区及 30 个命名图，Project 数恢复到测试前的 16。未触碰其他历史项目或图。
- GitHub 托管 runner 仍未实际触发；Round 1 已完整执行 workflow 本地等价命令并验证可移植性，
  最终 push/PR 后由托管 CI 再确认。
- R-008、R-009、R-010 的功能缺口仍按现状存在，不属于 R-011 失败。独立测试现已满足 PASS 门槛；
  主 Agent 可按关闭流程把 R-011 总表与详细状态同步为 `已实现`，完成最终 diff/status 检查并提交。
