# v5 P0 Codex 接入验证记录

日期：2026-10-28。归属：[R5.0-001 F8](../../requirements/requirements-v5.0.md#r5-0-001)、
[实施计划 P0](../implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#5-p0在全面改造前验证什么)。

**结论：无推理 SDK 接入基线通过 9 项开发测试；P0 整体为 PARTIAL，V1—V8 未放行。**
没有真实模型调用、收费建模、平台应用、独立功能测试或独立语义验收。

## 授权与实现范围

用户追加授权按计划开始 v5 底座技术切换，要求优雅架构实现现有功能，遇到需知晓或决策的事项暂停。
本批从 P0 开始，以实际 SDK 接入消除配置和隔离假设；不提前开发 P1—P4。
本次没有创建或追加任务预算，没有恢复旧任务或占用旧任务额度。

实施前 HEAD 为 `1edb162`。新增[独立 Python 包](../../../modeling_team/v5/README.md)
`ontoweave_modeling`；它不导入会立即加载旧 Runner 的 `modeling_team.__init__`。
使用 SDK 自带传输和类型解析，没有复制旧 Runner 或手写第二套 JSON-RPC 客户端。
namespace 隔离布局沿用现有实现经验，本次无推理入口额外禁用网络。

当前改动不改变后端、前端、平台合同、活跃运行配置、数据库或默认任务入口，
无需重启服务。原有 GraphRAG 文档的三处未提交改动保持。

## 实际候选环境

| 项目 | 本批实际值与边界 |
| --- | --- |
| Python | 3.12.3；项目固定 3.12 系列，未声明其他 Python 版本实测通过。 |
| Python SDK | `openai-codex==0.163.0`。 |
| SDK 绑定运行时 | `openai-codex-cli-bin==0.163.0`，实际执行返回 `codex-cli 0.163.0`。 |
| CLI SHA-256 | `399ff69c431c066e40de318fba45c2b07f45a76b19939d247ee4828fc70c4215`。 |
| 全局 CLI | `0.165.0`，未用于本批 SDK 测试，未升级或替换。 |
| 模型配置 | 从现有 `glm-flash-low.yaml` 的 modeling 角色读取；真实 thread 返回 `glm-direct / glm-5.3-flash / low`。只证明配置采用，不证明模型执行。 |
| 测试／格式工具 | pytest 9.1.1、Ruff 0.17.3。 |
| 环境与依赖 | `workspaces/v5-codex-p0/.venv`；项目 `uv.lock` 锁定直接及传递依赖，使用 `uv sync --locked`。 |
| 本批未接入 | LangGraph／PostgreSQL checkpointer、业务工作空间、真实 MCP、预算主账、真实平台及独立评价；它们仍属后续 P0 范围。 |

SDK 绑定 CLI 的官方合同见[Codex SDK 文档](https://learn.chatgpt.com/docs/codex-sdk)。
本批依赖安装后通过实际二进制及 RPC 核对，没有借用全局 CLI 的旧 schema 结论。
初次依赖安装下载了 SDK 绑定 CLI；随后锁定项目环境复用已安装的同版本包，
取消了重复环境的 CLI 下载。复跑以锁文件与上述明确环境为准。

## 测试轮次与真实观察

| 轮次 | 结果 | 发现与处置 |
| --- | --- | --- |
| 开发第 1 轮 | 8 PASS／1 FAIL | 真实 SDK 启动、绑定读回和 namespace 隔离通过；能力清单只读取了前 100 项，`nextCursor=100`，导致 `goals` 尚未出现在结果中。 |
| 开发第 2 轮 | 9 PASS／0 FAIL／0 SKIP | 接续读取全部分页后通过。没有删减所需能力断言或增加 run 守卫。 |
| 命令行入口 | PASS（无推理范围） | 使用仓库实际模型 Profile 执行；完整读取 175 项能力，`nextCursor=null`，临时 thread 的 turns 为空。 |

[测试源码](../../../modeling_team/v5/tests/test_preflight.py)覆盖：独立包不加载旧 Runner、
角色配置精确读取、三种缺失／无效 effort、显式无凭据配置、真实 Linux namespace
隐藏宿主输入、真实 SDK／CLI 配置读回，以及已有证据目录不被覆盖。

namespace 实测中，宿主测试材料、父目录 AGENTS、宿主环境变量和宿主凭据均不可见；
仅有隔离 loopback 接口，没有宿主网络接口。SDK 子进程只运行初始化与读取类 RPC，
未调用 `turn/start`，模型地址也不可达。该结果不等于真实生产／评价工具授权通过。

**尚需处理的实测发现**：空 home 仍自动安装并启用 `imagegen`、`openai-docs`、
`review-agent`、`skill-creator`、`skill-installer` 五个系统 Skills。
它们来自运行时内置内容，不是读到了宿主 Skills；后续真实 Agent 必须按获准范围裁剪，
并核对实际出站上下文和工具。当前未发模型请求，因此尚无出站证据可判定 V2。

## 命令与原始证据

在仓库根目录执行，先设置本批隔离环境：

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/workspaces/v5-codex-p0/.venv"
uv sync --locked --project modeling_team/v5 --group dev
uv run --locked --project modeling_team/v5 pytest -q \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests \
  --junitxml=workspaces/v5-codex-p0/developer-round2.xml
uv run --locked --project modeling_team/v5 python -m ontoweave_modeling.preflight \
  --model-profile modeling_team/model-profiles/glm-flash-low.yaml --role modeling \
  --output-dir workspaces/v5-codex-p0/runtime-baseline-001
uv run --locked --project modeling_team/v5 ruff check modeling_team/v5/src modeling_team/v5/tests
uv run --locked --project modeling_team/v5 ruff format --check modeling_team/v5/src modeling_team/v5/tests
uv lock --check --project modeling_team/v5
```

上述命令行的输出目录已存在，复跑时须换用新目录以保留原件。

gitignored 证据目录为 `workspaces/v5-codex-p0/`：

- `developer-round1.log`、`developer-round1.xml` 及复制保留的 `developer-round1-preflight.json`。
- `developer-round2.log`、`developer-round2.xml`。
- `runtime-baseline-001.log` 及 `runtime-baseline-001/preflight.json`：版本、哈希、
  配置层、实际绑定、完整能力清单、Skills 与空 MCP 清单。

SDK 读取证据和测试结果不作为独立验收。已有 LangGraph／SQLite 风险实验仍按
[原范围](2026-10-27-v5-langgraph-risk-validation.md)复用，本批未重复执行。

Ruff 检查、100 列格式检查和锁文件一致性检查通过；4 份相关 Markdown 的 63 个本地链接、
14 个锚点及围栏／空白检查通过。GitNexus 暂存检查识别 10 个变更文件，未映射出符号；
索引落后 HEAD 518 个提交，因此该结果不提供图影响覆盖。本批按源码、导入和调用点核对，
变更只接入新包及其自有测试，不改变旧入口的调用关系。

## 剩余范围与暂停点

| 项目 | 当前证据状态 |
| --- | --- |
| V1 | 真实 SDK 启动及配置已核对；真实模型、MCP 循环、类型化错误与流式错误未验证。 |
| V2 | 宿主输入 namespace 隔离有实测；内置 Skills 裁剪、真实出站及生产／评价权限边界未验证。 |
| V3—V8 | 未在本批执行；不得以本批 9 项测试关闭计量、控制、压缩、协作、平台故障对账或独立交接。 |
| 选型结论 | Codex 仍暂定；未达到进入 P1 全面实现的放行条件。 |

下一步真实集成需要本次 P0 的明确金额授权与稳定 `budget_ref`。
建议按现行默认采用 `glm-flash-low`，为 P0 单独授权人民币 3 元，覆盖生产、独立评价、
失败与恢复；外部 Host 用量沿现行合同单列。额度状态在原生回合边界检查，保留在途尾差。
授权前不发收费调用；P1—P4 和默认入口继续保持待放行。
