# R1.1-004 可复现的 Dify 官方文档建模资料集共享测试计划

## 1. 测试依据与记录规则

- 需求：`docs/requirements/requirements-v1.1.md` R1.1-004。
- 设计：`docs/delivery/designs/2026-07-18-r1-1-004-dify-corpus-design.md`。
- 交付记录：`docs/delivery/records/2026-07-18-r1-1-004-dify-corpus-delivery-record.md`。
- 固定官方源：`langgenius/dify-docs@5396c1a1afbea0dee3d089abfabdf6dac91d30d5`。

开发 Agent 和独立测试 Agent 复用本计划。独立测试在第 8 节追加新 Round，不覆盖此前记录；产品
缺陷由开发 Agent 修复，测试 Agent 不修改产品实现或放宽验收条件。

## 2. 审查重点

1. 快照是否只包含 R1.1-004 基础能力范围，且所有正文来自固定官方 commit。
2. manifest 是否足以在没有原 Agent 浏览器缓存时重建和解释每个文件的来源、语言、选择与 hash。
3. 校验是否真正失败关闭，而不是只验证正常样本或在异常时回退非官方来源。
4. 英文权威源、官方中文配对、翻译状态和 Evidence Reference 边界是否明确。
5. 旧快照不可覆盖、版本 diff 可读，且没有把 R1.1-004 扩成平台爬虫或 R1.1-003 修复。

## 3. 必测场景

### A. Manifest 与快照完整性

- manifest schema/version、snapshot ID、创建时间、用途、范围、非目标、状态、previous snapshot 完整。
- repository URL、40 位 commit、官网入口、CC BY 4.0、归属和 LICENSE 路径完整。
- 每个 entry 具有唯一 source/snapshot path、官方页面 URL、语言、标题、主题、理由和 SHA-256。
- `official/` 中登记文件恰好存在一次；缺失、额外、重复 entry/path 和 hash drift 均非零失败。
- 绝对路径、`..`、符号链接、未知 schema、非官方 repo/host 和非法语言状态均拒绝。

### B. 范围覆盖与排除

- 产品介绍、应用类型、Workflow/Chatflow、空白创建、画布/变量、测试/发布、复用/DSL、核心节点、
  Jinja2 Template 和官方 quick start 都至少有一个英文权威文件。
- 每个英文正文有同 commit 官方中文 entry，或 manifest 明确 `missing/possibly_stale`；不得存在项目自译。
- `docs.json` 作为固定官方导航索引入库并校验；live `llms.txt` 不作为重建字节依赖。
- 没有 `api-reference/`、`develop-plugin/`、部署、知识库高级、monitor/log 全目录或未说明例外。
- 没有图片、JavaScript、可执行文件、Cookie、用户数据或网页跟踪内容。

### C. 工具正向与负向行为

- `verify` 对 committed snapshot 重复运行稳定成功且不修改文件。
- `locate` 可按 topic 稳定列出文件、标题和 hash；未知 topic 非零或明确空结果。
- `rebuild` 在全新临时目录从固定 commit 得到与 committed snapshot 字节相同的全部官方文件。
- download 失败、commit/path 不存在、hash 不匹配、非空目标目录时 `rebuild` 失败，不切换搜索、缓存或转载。
- `diff` 对相同 manifest 输出全 unchanged；构造新增/删除/修改 fixture 时逐类准确报告且不写文件。
- 秘密扫描发现私钥、真实形态 JWT/Bearer/app key 时失败且错误不回显秘密；明显 placeholder 不误报。

### D. 三角色离线读取

三个隔离新上下文使用以下可审计机制，而不是只在提示词中声明禁网：

```bash
codex exec --ephemeral --sandbox read-only --json -C <snapshot-dir> '<role prompt>'
```

每个 prompt 要求第一条 shell 工具调用使用 Python `socket.create_connection(("docs.dify.ai", 443), 2)`
执行网络 canary，并且只有明确返回权限拒绝/网络不可达后才能继续。保存每个进程的完整 JSONL 到
系统临时验收目录；tester 必须核对 canary 失败、后续工具事件只有本地只读命令、没有 Web/MCP
网络调用，并对角色报告中的路径、SHA-256 和短摘录重新从本地文件计算。canary 成功、未执行、日志
不完整或无法证明只有本地读取时，本场景为 `FAIL`/`BLOCKED`，不能以角色自述替代。

三个角色只给快照路径和角色目标：

1. 业务整理角色定位 Workflow 创建、测试、发布和 Workflow/Chatflow 选择边界。
2. 建模角色定位 app template/duplicate、DSL import/export、Jinja2 Template node 的不同业务概念。
3. 独立评审角色定位 Multi-platform content generator 的主要节点与数据流，并复核前两组证据。

每个角色必须返回 snapshot ID、相对文件、SHA-256、短摘录位置/标题和“官方原文/角色推断”区分；
不得使用 live URL 内容补全。三者看到的 manifest hash 必须相同。若当前 Codex 版本的
`--sandbox read-only` 不能阻止 shell 网络访问，则停止验收并记录 blocker，不降级成提示词约束。

### E. 易混概念证据

- `app-management.mdx` 中 application template/duplicate/DSL 是应用复用与可移植配置。
- `nodes/template.mdx` 中 Template 是用 Jinja2 转换/格式化运行数据的工作流节点。
- quick start 对 Template 节点和 Multi-platform content generator 的引用与上述节点定义一致。
- Evidence fixture 的摘录逐字存在于快照，关联 snapshot path/hash；中文摘要或 Agent 结论不能标成原文。

### F. 版本更新与恢复

- 对测试用 v2 manifest 执行 diff，准确列出 added/removed/modified/unchanged。
- update/rebuild 不允许覆盖已有 snapshot 目录；旧 manifest 和文件仍可 verify/locate。
- previous snapshot 指向存在的旧 ID；旧 Build Session 可仅凭旧 ID 定位其 manifest。

### G. 回归、CI 与收口

- corpus 工具、tests 和 manifest JSON 可由 Python 3.11 解析，Ruff（若纳入当前配置）与格式检查通过。
- `.github/workflows/docs-sync.yml` 或独立 CI job 运行离线 `verify` 和 corpus tests，不依赖用户 home。
- `git diff --check` 通过；secret scanner 对交付文件通过。
- `docs/requirements/requirements-v1.1.md` 的文档信息、R1.1-004 详细状态和交付结果一致；本轮只能
  更新为 `进行中（资料集已交付，等待 R1.1-003 后集成重跑）`。R1.1-003 保持未实现，R1.1-001
  不因资料集交付被错误关闭。
- 本需求没有 backend/frontend/runtime 改动，因此不重启 `ontology-platform.service`；若实施实际触及
  两侧代码，则恢复执行 AGENTS.md 的对应全量测试和重启健康门禁。

## 4. 建议自动化命令

```bash
python docs/evaluation-corpora/dify-foundations/tools/corpus.py verify \
  docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a
python -m unittest discover \
  -s docs/evaluation-corpora/dify-foundations/tests -p 'test_*.py' -v
python -m json.tool \
  docs/evaluation-corpora/dify-foundations/snapshots/dify-foundations-2026-07-18-5396c1a/manifest.json \
  >/dev/null
git diff --check
```

真实重建由独立测试在临时新目录执行，完成后比较每个 manifest entry 的 SHA-256；不把临时目录或
下载日志提交到仓库。

## 5. 完成门槛

- 设计中的首版范围、固定 commit、许可、语言和安全合同全部有落盘证据。
- 自动校验的正反例、全新目录重建、版本 diff 和三角色离线测试通过。
- 独立测试 Agent 在本文件留下资料集交付 `PASS` Round；此前失败轮次不得删除。
- requirement、README、CI、设计、测试计划和 delivery record 同步。
- 只提交 R1.1-004 文件，不包含工作区既有 v1.2/Agent 指令修改。
- R1.1-004 保持 `进行中`，直至 R1.1-003 完成后使用固定快照通过 Draft、dry-run、独立评审、apply
  和能力问题集成验收；该后置 Round PASS 后才允许改为 `已实现`。

## 6. 清理

本需求不创建平台业务数据。真实重建只写入系统临时目录；测试结束后可保留到进程退出或使用明确
临时目录清理，不删除仓库路径。没有唯一所有权证据时不执行递归清理。

## 7. 已知不可由本需求关闭的事项

- R1.1-003 的大体量建模产物可靠交接与恢复。
- R1.1-003 完成后的完整 Dify dry-run、review、apply、query、validation 和 lineage 重跑；这是本轮
  无法执行但仍然保留的 R1.1-004 最终完成门禁，不是已放弃的范围。
- 图片内容的完全离线复现、官方中文语义等价保证及自动最新同步。

## 8. 独立测试记录

独立测试 Agent 在此追加 Round，不覆盖计划正文或历史 Round。

### Independent Test Round 1 — 2026-07-18

**结论：FAIL。** 测试基线为 `e52f276` 加 DEVELOPMENT_READY 工作树，快照 manifest SHA-256 为
`9bc401fde174c4a0023ab9f2605fde2c5c9de0702b069a21f891904ca04a5f3f`。固定快照、真实重建、
离线角色读取和既有正反向测试通过，但非官方 GitHub 页面来源和版本前驱链仍可绕过 `verify`，不满足
失败关闭验收标准。R1.1-004 必须保持 `进行中（资料集已交付，等待 R1.1-003 后集成重跑）`。

#### 实现审查与通过证据

- manifest 登记 32 个官方对象：15 组英文源及同 commit 官方中文页面，另含 `LICENSE` 和
  `docs.json`；逐文件本地 SHA-256、登记路径、文件集合、主题覆盖和英中配对均通过 `verify`。
- `python .../corpus.py verify .../dify-foundations-2026-07-18-5396c1a`：exit 0，
  `verified ... (32 files)`；重复执行不修改快照。
- `python -m unittest discover -s docs/evaluation-corpora/dify-foundations/tests -p 'test_*.py' -v`：
  exit 0，21/21 PASS。覆盖缺失/额外/重复、hash drift、schema、非官方非 GitHub host、路径穿越、
  symlink、可执行位、秘密抑制、placeholder、语言配对、topic、locate、diff、下载失败、hash mismatch、
  非空目标和固定 raw URL。
- `python -m json.tool .../manifest.json >/dev/null` 与 `git diff --check`：均 exit 0。
- `locate --topic jinja2-template`：exit 0，稳定返回英中 Template node 与 quick start 共 4 项；
  `locate --topic not-a-topic`：exit 1，明确报告 `unknown or uncovered topic`。
- 真实固定 commit 重建：从
  `langgenius/dify-docs@5396c1a1afbea0dee3d089abfabdf6dac91d30d5` 下载至全新临时目录，
  exit 0、耗时 21.22 秒；32 个 entry 的 committed/rebuilt/manifest hash 0 不一致，双方均为 33 个
  文件且文件集合完全相同。
- 三个角色分别使用全新的
  `codex exec --ephemeral --sandbox read-only --json -C <snapshot-dir>` 上下文。三者第一条 shell
  调用均为 `socket.create_connection(("docs.dify.ai", 443), 2)`，均以 `socket.gaierror`、exit 1
  失败且未输出连接成功标识；完整 JSONL 共 61 个事件。canary 后仅出现本地只读
  `sed`、`jq`、`sha256sum`、`rg`、`nl` 命令，没有 Web、MCP、browser 或其他网络工具事件。
  三者均返回相同 snapshot ID 与 manifest hash；tester 从本地重新计算所报文件 hash，并逐字核对
  Workflow/Chatflow、空白创建/测试/发布、应用 template/duplicate/DSL、Jinja2 Template node 和
  Multi-platform content generator 的英文摘录及路径，均匹配 manifest 与快照。原始 JSONL 保存在
  `/tmp/r11004-independent-round1-arnagJ/`，各角色 stderr 未包含秘密。

#### 缺陷

1. **High — GitHub 页面来源可伪装为官方来源。** 将一个 entry 的 `official_page_url` 改为
   `https://github.com/unrelated-owner/unrelated-repo/blob/main/copied.mdx` 后，`verify` 仍 exit 0 并
   报 32 files verified。`_validate_url` 只 allowlist `github.com` 主机，没有约束 URL 必须位于
   `langgenius/dify-docs`。这违反需求中“只允许官方 GitHub 仓库”和“自动发现非官方来源并非零
   失败”的合同。复现证据：`/tmp/r11004-negative-round1-Vwdj3S/github-spoof*`。
2. **Medium — 快照版本前驱可以悬空。** 将测试用新 snapshot 的 `previous_snapshot` 设置为
   `does-not-exist` 后，`verify` 仍 exit 0。当前仅检查该字段是字符串，没有验证 ID 形状或同 corpus
   旧快照存在，不能证明旧 Build Session 的恢复链完整。复现证据：
   `/tmp/r11004-negative-round1-Vwdj3S/previous-link*`。

#### 未执行、清理与剩余风险

- R1.1-003 尚未实现，因此未执行 Draft 持久化、dry-run、独立评审、apply、能力问题查询、
  validation 和 lineage 的固定资料集集成重跑；这是 R1.1-004 的后置完成门禁，不是本轮豁免项。
- 本次没有 backend/frontend/runtime 改动，按仓库规则未运行其全量测试、未重启
  `ontology-platform.service`；不适用而非阻塞。
- 测试未创建平台业务数据，也未写入快照；真实 rebuild 及负向 fixture 仅位于唯一命名的 `/tmp`
  目录，仓库状态检查没有发现测试生成的登记外快照文件。原始角色日志暂留上述临时目录供本轮复核。
- 缺陷修复后需在本计划追加 Round 2，至少加入无关 GitHub repo、合法官方 GitHub URL、悬空/
  合法 `previous_snapshot` 的自动回归，并重跑完整离线角色、真实 rebuild 和 CI 等价门禁。

### Independent Test Round 2 — 2026-07-18

**结论：PASS（资料集交付门禁）。** 测试基线仍为 `e52f276` 加修复后的稳定 DEVELOPMENT_READY
工作树；快照 manifest SHA-256 保持
`9bc401fde174c4a0023ab9f2605fde2c5c9de0702b069a21f891904ca04a5f3f`。Round 1 的 High/Medium
缺陷均已修复且加入自动回归，本轮未发现新的 Critical、High、Medium 或 Low 缺陷。该 PASS 只关闭
R1.1-004 的资料集交付门禁；R1.1-003 后集成重跑尚未执行，R1.1-004 继续保持
`进行中（资料集已交付，等待 R1.1-003 后集成重跑）`。

#### Round 1 缺陷复测

- 定向执行 GitHub URL、previous snapshot 身份/存在性、self/unsafe/cycle 三组测试：3/3 PASS。
- 合法的 `github.com/langgenius/dify-docs/blob/<fixed-commit>/<source-path>` LICENSE、docs.json URL
  正常通过；无关 owner/repo、错误 commit、与登记 source path 不符以及带 query 的 GitHub URL 均
  非零失败。
- 悬空前驱、unsafe ID、self reference、前驱 manifest identity mismatch、corpus mismatch 和两节点
  cycle 均非零失败；合法前驱链通过。
- 额外构造两代完整快照链：旧/当前 snapshot 分别 `verify` 为 32 files，旧 snapshot 的
  `locate --topic jinja2-template` 通过；两代相同内容的 `diff` 为 added/removed/modified 全空、
  unchanged 32，证明旧 ID 可独立定位和读取。

#### 全量、重建与证据门禁

- `python .../corpus.py verify .../dify-foundations-2026-07-18-5396c1a`：exit 0，32 files。
- `python -m unittest discover -s docs/evaluation-corpora/dify-foundations/tests -p 'test_*.py' -v`：
  exit 0，24/24 PASS；在 Round 1 的 21 项基础上新增并覆盖上述 URL 和版本链修复。
- 真实固定 commit rebuild：exit 0、耗时 21.71 秒；32 个 entry 的 committed/rebuilt/manifest hash
  0 不一致，双方 33 个文件且文件集合完全相同。
- 三个角色重新使用全新的
  `codex exec --ephemeral --sandbox read-only --json -C <snapshot-dir>` 上下文，三个进程均 exit 0。
  每个上下文的第一条 shell 调用均为 `socket.create_connection(("docs.dify.ai", 443), 2)`，均以
  `socket.gaierror`、exit 1 失败且没有成功连接标识。完整 JSONL 共 56 个事件；canary 后只有本地
  `sed`、`jq`、`sha256sum`、`rg`、`find`、`nl` 命令，没有 Web、MCP、browser、apps 或其他网络
  工具事件。
- 三个角色均报告 snapshot ID `dify-foundations-2026-07-18-5396c1a` 和相同 manifest hash。
  tester 独立重新计算 Workflow/Chatflow、quick start、version control、app management、Template
  node 等关键文件 hash，并逐字核对 Workflow 创建/测试/发布、应用 template/duplicate/DSL、Jinja2
  Template node 和 Multi-platform content generator 摘录，路径、行文与 manifest 均匹配；官方
  原文和角色推断保持分离。
- 完整角色日志保存在 `/tmp/r11004-independent-round2-hgSMAi/`，秘密模式扫描 PASS；stderr 仅含
  Codex stdin 提示，没有凭证。

#### CI、状态与清理

- CI 等价 corpus `verify`、24 项 unittest 和 manifest `json.tool`：全部 exit 0。
- `cd backend && uv run ruff check ../docs/evaluation-corpora/dify-foundations/tools/corpus.py
  ../docs/evaluation-corpora/dify-foundations/tests/test_corpus.py`：exit 0，`All checks passed!`。
- `git diff --check`：exit 0。requirements 状态核对：R1.1-001、R1.1-003 仍为 `未实现`；R1.1-004
  仍为 `进行中（资料集已交付，等待 R1.1-003 后集成重跑）`。
- 测试未创建平台业务数据、未修改 committed snapshot，也未触及 backend/frontend/runtime，因此
  不运行其全量测试且不重启服务。唯一命名的真实 rebuild
  `/tmp/r11004-rebuild-round2-FAU8cN/`、完整版本链 fixture
  `/tmp/r11004-valid-chain-round2-gXq9d9/` 和上述角色日志暂留供交付复核；仓库状态没有出现测试生成
  的登记外快照文件。

#### 未执行与剩余风险

- R1.1-003 尚未实现，因而 Draft 持久化、dry-run、独立评审、apply、能力问题查询、validation 和
  lineage 的固定资料集集成重跑仍未执行；只有该后置 Round PASS 后才能把 R1.1-004 更新为
  `已实现`。
- 固定快照不承诺等于官网最新内容；图片未离线保存，官方中文同 commit 也不保证语义完全等价。
  这些限制与设计一致，不推翻本轮资料集交付 PASS。

### Independent Test Round 3 — 2026-07-18

**结论：FAIL（提交闭环）。** 本轮只复测 Round 2 后的 whitespace/提交闭环，不重跑已通过的三角色
门禁。新增 `.gitattributes` 规则的范围和 staged whitespace 检查正确，工作树资料及先前固定 commit
rebuild 仍然一致；但 staged index 仅包含 manifest 登记的 32 个官方对象中的 26 个。6 个路径包含
`cloud/use-dify/build/` 的英中官方页面仍被仓库根 `.gitignore` 的 `build/` 规则忽略，新 checkout 将
缺失这些文件，无法通过 `verify`。本轮存在 1 个 High 缺陷，不能维持 Round 2 的资料集交付 PASS。
R1.1-004 继续保持 `进行中（资料集已交付，等待 R1.1-003 后集成重跑）`。

#### 已通过的窄复测

- staged `.gitattributes` 规则精确为
  `docs/evaluation-corpora/dify-foundations/snapshots/**/official/** -whitespace`。
- `git check-attr whitespace`：`official/LICENSE`、`official/en/home.mdx` 为 `unset`；manifest、
  `tools/corpus.py`、`tests/test_corpus.py`、corpus README、requirements 和 CI workflow 均为
  `unspecified`，没有把规则扩散到项目自有文件。
- `git diff --cached --check`：exit 0。
- 在仓库 `docs/` 下创建唯一命名的规则外尾随空白 canary，并用隔离 Git index 执行
  `git diff --check`：exit 2，准确报告第 1 行 trailing whitespace；随后删除 canary，仓库状态确认
  不再存在该文件。隔离 index/log 位于 `/tmp/r11004-whitespace-index-round3-YrAYTK/`。
- 当前工作树 snapshot 与 Round 2 真实固定 commit rebuild 分别执行 `verify`：均 exit 0、32 files；
  manifest SHA-256 保持
  `9bc401fde174c4a0023ab9f2605fde2c5c9de0702b069a21f891904ca04a5f3f`。
- corpus 全量回归：24/24 PASS。Ruff check 为 `All checks passed!`，Ruff format check 为
  `2 files already formatted`；manifest JSON 和工作树 `git diff --check` 通过。

#### 缺陷

1. **High — 6 个 manifest 登记文件未进入 staged index。** staged/worktree/prior-rebuild 逐 entry
   比较在首个 `official/en/cloud/use-dify/build/workflow-chatflow.mdx` 即失败；完整枚举为英中两种
   语言下的 `workflow-chatflow.mdx`、`orchestrate-node.mdx`、`version-control.mdx`，共 6 个文件。
   `git check-ignore -v` 对六者均指向 `.gitignore:12:build/`。当前 staged index 为 26 present、
   6 missing；若按此状态提交，新 checkout 的 manifest 会登记不存在的文件，直接违反“全新工作目录
   能取得并校验相同快照”的核心验收标准。

#### 清理、未执行与后续复测

- 临时项目 canary 已删除；未创建平台业务数据，未修改 official bytes、manifest、产品代码或交付
  记录，未提交。隔离临时 index 仅保留在上述 `/tmp` 目录供复核。
- 修复需让这 6 个固定快照文件明确进入版本控制，同时保持通用 `build/` ignore 边界；随后追加
  Round 4，至少验证 32/32 manifest entries 均存在于 staged index、逐 staged/worktree/rebuilt hash
  完全一致、全新 index/checkout 能 `verify`，并重跑 staged diff、24 tests、Ruff/format 和状态清理。
- R1.1-003 后的 Draft、dry-run、review、apply、query、validation、lineage 集成重跑仍未执行，继续
  作为最终状态更新门禁。

### Independent Test Round 4 — 2026-07-18

**结论：PASS（最终 submission/index 复测）。** Round 3 的 High 提交闭环缺陷已修复：仓库根
`.gitignore` 仅对 Dify 固定快照 `official/**/build/` 目录增加窄 re-include，六个英中 build MDX
均通过正常路径进入 staged index，不依赖 force-add；其他项目 build 路径仍保持忽略。本轮没有发现
新缺陷。该 PASS 恢复并确认资料集交付门禁，但 R1.1-003 后的完整集成重跑尚未执行，因此 R1.1-004
继续保持 `进行中（资料集已交付，等待 R1.1-003 后集成重跑）`。

#### Round 3 缺陷与边界复测

- `.gitignore` 新增规则仅为：
  `!docs/evaluation-corpora/dify-foundations/snapshots/**/official/**/build/` 和对应 `build/**`；
  原 `build/` 规则未删除或放宽。
- 英中两种语言下的 `workflow-chatflow.mdx`、`orchestrate-node.mdx`、`version-control.mdx` 共六个
  文件均已 staged，`git check-ignore` 对六者均返回未忽略。
- 对不存在的 `build/probe.txt`、`backend/build/probe.txt`、`docs/build/probe.txt`、
  `frontend/build/probe.txt` 执行 `git check-ignore -v --no-index`，四者仍命中 `.gitignore:12:build/`。
- manifest 32 个 `snapshot_path` 与 `git ls-files` 的 indexed official 集合精确相等：indexed 32、
  missing 0、extra 0。逐 entry 使用 `git show :<path>` 读取 staged blob，与工作树、Round 2 固定
  commit rebuild 和 manifest 登记 SHA-256 四方比较，hash mismatch 0。

#### 属性、回归与格式门禁

- `.gitattributes` 仍精确为
  `docs/evaluation-corpora/dify-foundations/snapshots/**/official/** -whitespace`。build MDX 的
  `whitespace` 为 `unset`；manifest、tool、tests、README 和 requirements 均为 `unspecified`。
- `git diff --cached --check` 与工作树 `git diff --check`：均 exit 0。
- 当前 snapshot 与 Round 2 prior rebuild 分别 `verify`：均 exit 0、32 files；manifest SHA-256 仍为
  `9bc401fde174c4a0023ab9f2605fde2c5c9de0702b069a21f891904ca04a5f3f`。
- corpus 全量回归：24/24 PASS；manifest `json.tool` 通过。
- Ruff check：`All checks passed!`；Ruff format check：`2 files already formatted`。

#### 状态、清理与剩余门禁

- Round 3 的仓库内 trailing-whitespace canary 保持已删除；本轮仅执行只读 index、ignore、hash、
  verify 和测试检查，没有创建平台业务数据、没有修改 official bytes、manifest、产品代码或交付
  记录，也没有提交。
- 复核所用 prior rebuild 仍为 `/tmp/r11004-rebuild-round2-FAU8cN/`；没有新增仓库内测试产物。
- R1.1-003 后的 Draft 持久化、dry-run、独立评审、apply、能力问题查询、validation 和 lineage
  集成重跑仍未执行；只有该后置 Round PASS 后才能把 R1.1-004 更新为 `已实现`。
