# R1.1-004 可复现的 Dify 官方文档建模资料集设计

## 1. 状态与决策摘要

本设计落实 `docs/requirements/requirements-v1.1.md` 的 R1.1-004。功能合同已由用户确认：英文
官方文档是权威内容源；固定版本中存在的官方中文页面一并纳入；中文缺失或疑似滞后时只显式标记，
不自行翻译。

首个快照固定为 Dify 官方 `langgenius/dify-docs` 仓库 commit
`5396c1a1afbea0dee3d089abfabdf6dac91d30d5`，快照 ID 为
`dify-foundations-2026-07-18-5396c1a`。该 commit 的仓库规则明确 `en/` 是源语言、`zh/` 是官方
翻译，仓库许可证为 Creative Commons Attribution 4.0 International（CC BY 4.0）。

资料集是 repo-local 验收输入，不是平台通用采集功能。实现仅新增版本化资料、清单、标准库校验/
重建工具、离线测试与 CI 门禁，不修改 backend、frontend、数据库、MCP 或运行态服务。

## 2. 目标与非目标

### 2.1 目标

- 为“了解 Dify 基础功能及用法”提供小而完整的英文/官方中文固定资料快照。
- 每个官方文件具有固定仓库 commit、源路径、页面 URL、标题、语言、主题、选择理由和 SHA-256。
- 从全新目录按固定 commit 重建同一批字节；下载、路径或哈希异常时失败关闭。
- 自动发现缺失、重复、未登记文件、哈希漂移、非官方来源、格式错误、可执行文件和明显秘密。
- 让业务整理、建模和独立评审角色在禁止网络访问时读取同一快照并定位关键依据。
- 更新时创建新快照，通过 manifest diff 明确新增、删除、修改；旧快照不可原地覆盖。

### 2.2 非目标

- 不镜像 Dify 全站，不收集全量 API Reference、插件、部署运维、知识库高级能力或完整监控日志。
- 不下载图片、视频、字体、脚本或网页跟踪资产；正文已能表达本次能力问题。
- 不实现通用爬虫、平台上传/来源管理、自动同步、R-101 适配器或 Dify 专用平台接口。
- 不把本地文件直接当作 Evidence Reference；建模项仍需保存实际引用的精确原文片段。
- 不解决 R1.1-003 的大体量结构化建模产物交接问题，也不在本需求中重跑完整 Dify 建模。

## 3. 官方来源风险探针

### 3.1 仓库与固定版本

- 官方仓库：`https://github.com/langgenius/dify-docs`。
- 固定 commit：`5396c1a1afbea0dee3d089abfabdf6dac91d30d5`。
- commit 时间：`2026-07-17T19:52:12+08:00`。
- 内容获取只使用固定 commit 的
  `https://raw.githubusercontent.com/langgenius/dify-docs/<commit>/<path>`。
- 官网入口为 `https://docs.dify.ai/`；页面 URL 只作来源与人工复核入口，不作为重建字节源。

### 3.2 许可证与语言

- 固定 commit 的 `LICENSE` 是 CC BY 4.0，快照保存该文件并在项目 README/manifest 中保留 Dify/
  LangGenius 归属和许可证链接。
- 官方仓库 `AGENTS.md` 声明 English is the source language，并要求英文变更与 `zh`/`ja` 翻译同批
  交付。首版只收录已存在的 `en`/`zh` 对；manifest 仍逐页记录 `translation_status`，不以同 commit
  自动推断语义完全等价。
- 不创建项目自译正文；若后续官方中文缺失，manifest 使用 `missing` 或 `possibly_stale`。

### 3.3 导航索引

官网 `llms.txt` 会随部署变化且没有独立可寻址历史版本。为同时满足“官方导航索引”和固定 commit
重建，本快照保存同一 commit 的 `docs.json` 作为等价官方导航索引，并记录
`https://docs.dify.ai/llms.txt` 为新鲜度发现入口。重建和离线建模不依赖 live `llms.txt`。

## 4. 首版资料范围

英文及对应官方中文各收录下列正文；另收录固定 commit 的 `LICENSE` 与 `docs.json`：

| 主题 | 官方仓库相对路径（语言前缀省略） | 纳入理由 |
| --- | --- | --- |
| 产品介绍 | `home.mdx`、`cloud/use-dify/getting-started/introduction.mdx` | Dify 定位、主要使用面 |
| 核心概念与应用类型 | `learn/key-concepts.mdx` | Workflow、Chatflow、其他应用类型和 DSL 定义 |
| Workflow/Chatflow 边界 | `cloud/use-dify/build/workflow-chatflow.mdx` | 单次流程与会话流程的选择边界 |
| 画布与变量 | `cloud/use-dify/build/orchestrate-node.mdx` | 节点连接、串并行和变量依赖 |
| 应用复用 | `cloud/use-dify/workspace/app-management.mdx` | duplicate、template、DSL import/export |
| 测试与发布 | `cloud/use-dify/build/version-control.mdx` | draft、test/publish 后版本边界 |
| 官方示例 | `quick-start.mdx` | 从空白创建 Multi-platform content generator 及节点数据流 |
| 起点与输入 | `cloud/use-dify/nodes/start.mdx`、`cloud/use-dify/nodes/user-input.mdx` | Start/Trigger/User Input 与变量 |
| 核心节点 | `cloud/use-dify/nodes/llm.mdx`、`ifelse.mdx`、`iteration.mdx`、`template.mdx`、`output.mdx` | R1.1-004 指定节点及其语义 |

该范围刻意排除 `api-reference/`、`develop-plugin/`、`self-host/deploy/`、`knowledge/`、`monitor/` 和
其他未直接支持当前能力问题的节点。图片引用保留在 MDX 原文中但不下载资产；离线角色以文字为证据，
不能把未快照的图片内容当作依据。

## 5. 目录与清单合同

```text
docs/evaluation-corpora/dify-foundations/
  README.md
  snapshots/
    dify-foundations-2026-07-18-5396c1a/
      manifest.json
      official/
        LICENSE
        docs.json
        en/...
        zh/...
  tools/corpus.py
  tests/test_corpus.py
```

`manifest.json` 使用版本化 JSON schema，至少包含：

- corpus/snapshot ID、创建时间、用途、范围、明确非目标、状态和 previous snapshot；
- 官方仓库、固定 commit、官网/导航入口、许可证标识、归属和许可文件；
- 每个文件的 `source_path`、`snapshot_path`、`official_page_url`、`language`、`title`、`topics`、
  `selection_reason`、`sha256`；
- 中文文件的英文 `translation_of` 与 `translation_status`；
- 纳入能力主题、明确排除类别和例外理由。

manifest 自身和 `official/` 内容纳入 Git。旧 snapshot 目录禁止由更新命令覆盖；新版本使用新 ID 和
manifest，并用 `previous_snapshot` 串联。

## 6. 工具行为

`tools/corpus.py` 只使用 Python 3.11 标准库，提供：

- `verify <snapshot-dir>`：离线校验 schema、官方来源、路径安全、唯一性、登记文件集合、SHA-256、
  主题覆盖、语言对应、许可证、允许扩展名和秘密模式；任一异常非零退出。
- `rebuild <snapshot-dir> --destination <dir>`：只从固定官方仓库/commit 构造 raw URL，目标必须为空，
  按 manifest 下载并逐文件验 hash；失败时保留明确错误且不声称成功。
- `diff <old-manifest> <new-manifest>`：稳定输出 added/removed/modified/unchanged；比较 source path 与
  hash，不修改任何快照。
- `locate <snapshot-dir> --topic <topic>`：离线列出主题对应文件、标题和 hash，供 Agent 先定位再读取。

安全与失败边界：

- 只接受 exact official repo `langgenius/dify-docs`、40 位 commit 和 allowlist host；不跟随 manifest
  指向的任意 URL。
- 拒绝绝对路径、`..`、符号链接、未登记文件、重复 entry/path、未知字段版本和非文本扩展名。
- 重建不读取 Cookie、Authorization 或 API key，不执行下载内容；urllib 请求不附加认证 header。
- MDX 中的示例代码仍是文档文本；快照本身不得包含可执行脚本/二进制。秘密检查区分占位符与高风险
  私钥、JWT、Bearer/app key 形态，命中时失败并只报告文件，不回显秘密。

## 7. 建模与证据边界

- Business Knowledge Pack 记录 snapshot ID、manifest hash、使用文件和各文件 hash。
- Coverage Matrix 对每个页面使用 `MODELED | DEFERRED | AMBIGUOUS | UNSUPPORTED | MISSING`；状态属于
  本次建模产物，不写回不可变官方快照。
- Evidence Reference 的 `document_name` 标明 snapshot ID 和相对路径，`excerpt` 必须逐字来自对应
  快照；Agent 摘要和推断另行标记，不能冒充官方原文。
- 新鲜度检查只报告官方 repo HEAD 与 pinned commit 的差异。决定更新时先创建新 snapshot，再启动新
  Build Session；一个 Session 不混用版本。

## 8. 测试与交付门槛

- 自动正向/负向测试覆盖 verify、rebuild URL/失败关闭、diff、locate、缺失/额外/重复/hash drift、
  非官方来源、路径穿越、格式错误、秘密和可执行文件。
- 在三个 `codex exec --ephemeral --sandbox read-only --json` 隔离上下文中，业务整理、建模和评审角色
  分别只读同一 snapshot。每个角色的第一条 shell 探针必须尝试访问 `docs.dify.ai:443` 并因 Codex
  shell sandbox 禁网而失败；完整 JSONL 工具事件保存在临时验收目录并由 tester 核对只有本地读取。
  任一网络 canary 成功、角色未执行 canary 或事件无法审计时，本门禁 FAIL/BLOCKED，不能用提示词
  声明替代。通过后分别定位 Workflow 创建/发布、应用模板/DSL、Jinja2 Template 节点和
  Multi-platform content generator，并用本地 hash/原文交叉核验。
- 对 DSL/app template 与 Jinja2 Template 两组易混概念分别创建精确快照摘录，证明来源路径、hash 和
  官方/Agent 表述边界；不要求写入 live 平台 Evidence Reference 数据。
- CI 运行离线 verify 与测试，不在每次 CI 从网络重建。独立测试额外在临时全新目录执行一次真实
  rebuild 并与 committed snapshot 比较。
- 本需求不改 backend/frontend，仓库规则不要求服务重启；最终仍执行 `git diff --check`、corpus
  verify/tests、CI 等价命令和独立 PASS。完成这些门禁后只能把 R1.1-004 标为
  `进行中（资料集已交付，等待 R1.1-003 后集成重跑）`。只有 R1.1-003 完成后，再用该固定快照完成
  Draft 持久化、dry-run、独立评审、apply 和能力问题验收，R1.1-004 才能更新为 `已实现`。

## 9. 已知限制与后续

- 固定快照不是最新官方文档承诺；新鲜度由显式对比报告体现。
- MDX 可能引用未下载图片，图片不能作为本轮离线证据。
- 官方同 commit 的中文也可能存在翻译语义差异；英文始终是冲突时的权威源。
- 本轮可以交付并提交资料集，但 R1.1-003 完成后的完整 Dify 重跑仍是 R1.1-004 的最终完成门禁；
  在此之前 R1.1-004 保持 `进行中`，也不得宣称 R1.1-003 或 R1.1-001 已完成。
