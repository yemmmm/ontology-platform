# v5 P1.1 整体框架实施记录

- 日期：2026-10-29；开发基线：`1d4a08d`。
- 用户授权：“请开始实现本次设计，先将整体框架搭建好”。
- 归属：[v5.0 需求](../../requirements/requirements-v5.0.md)、[P1.1 阶段](../implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#p1-1)、[已独立审阅的架构设计](../designs/2026-10-28-v5-p1-1-architecture-design.md)。
- 当前结论：**整体框架已实现，开发工程验证通过；不关闭完整 P1.1，不升级 P0 的计量 PARTIAL，不切换默认入口。**

## 已实现的框架

| 模块 | 实际行为 |
| --- | --- |
| [CLI](../../../modeling_team/v5/src/ontoweave_modeling/cli.py) | 显式 `start/status/pause/stop/resume/evaluate/cleanup`；`--prepare-only` 只冻结输入并保存工作记录；原默认入口保持。 |
| [任务及结果合同](../../../modeling_team/v5/src/ontoweave_modeling/contracts.py) | 冻结获准来源、Profile、指令、目标、范围、授权及独立冻结引用；自然 JSON＋程序校验；未支持的授权／provider 在准备前准确拒绝。 |
| [工作空间](../../../modeling_team/v5/src/ontoweave_modeling/workspace.py) | 复用原版本仓储；增加精确修订／内容摘要引用和读取；checkpointer 可使用单独 schema，不覆盖较新业务内容。 |
| [执行登记](../../../modeling_team/v5/src/ontoweave_modeling/execution.py) | 启动前登记执行及输入身份；保存原返回；重入复用已完成结果，原完成事件可补回执；未知不重启。 |
| [工作单元图](../../../modeling_team/v5/src/ontoweave_modeling/flow.py) | `prepare → model → apply → self_check → handoff`，按实际结果纠正、等待、保留未知与重入；checkpoint 保存引用，不保存完整聊天／候选。 |
| [Host 桥](../../../modeling_team/v5/src/ontoweave_modeling/host_bridge.py)、[worker](../../../modeling_team/v5/host/worker.py) | v5 与 backend 两个现有环境之间的固定 JSON 调用；复用 provider、编译、依赖绑定、执行器、原分批／回执、作用域及 scoped read 凭据；不执行旧 Runner 编排。 |
| [控制](../../../modeling_team/v5/src/ontoweave_modeling/control.py) | 原生回合及平台活动准入、控制登记、自然结束后停稳；保留候选；未知活动不清 active；stop 不由 resume 撤销，虚假消费确认不生效。 |
| [独立交接合同](../../../modeling_team/v5/src/ontoweave_modeling/acceptance.py) | 独立入口／上下文／材料；核对冻结身份、原来源及实际成功治理读取、模型修订和题目覆盖；公开投影不含隐藏答案；不自动判断业务语义。 |
| [旧依赖解耦](../../../modeling_team/platform_bootstrap.py) | 旧 bootstrap 原逻辑移到窄模块，旧 CLI 保留转调入口；包根三个公开名称惰性导出，机械模块导入不加载旧 Runner。 |

Host provider 仍只接入已核对的 `glm-direct`，精确使用任务 Profile 的 provider／model／effort。
本任务沿原 `usage_only` 授权保留原始用量及身份；普通金额／次数模式、完整计量和净成本证明
待后续阶段，不用本任务例外推及其他任务。独立评价计入 Host 的在途成员统计，但不接收生产
业务队列输入；隐藏材料不进入生产 MCP 范围。

## 验证范围及实际轮次

本批没有启动收费模型、创建平台业务资源或访问真实隐藏题集。工程测试使用真实 PostgreSQL
自有随机 schema 与 PostgresSaver；Agent／平台效果用明确标注的确定性替身，Host worker
导入与编译使用真实 backend 环境及既有编译器。不存在把替身结果记为真实建模通过的结论。

开发过程中先验证缺失框架模块的失败，再实现并迭代；原失败包括快照重复准备的错误顺序，
以及测试 fixture 误把 `semantic_definition` 写成字符串。前者已修复，后者改用既有真实字段合同。
控制状态及报告格式纠正反例均纳入现有测试体系，不新建场景专用语义评分器。

最终验证命令与结果：

```bash
# 仓库根目录，独立 v5 锁定环境
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 pytest -q \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff check \
  modeling_team/v5/src modeling_team/v5/host modeling_team/v5/tests
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff format --check \
  modeling_team/v5/src modeling_team/v5/host modeling_team/v5/tests

# backend/ 内，现有 Host 环境
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q
```

- v5：**78 passed，0 skipped，1 warning，25.86s**；包括原 P0 测试及新增 31 项框架测试。
  警告为原有第三方 Pydantic settings 的 `lifespan` forward-reference 提示。
- 旧 Team 完整回归：**3856 passed，12 skipped，318 subtests passed，359 warnings，601.61s**。
  12 项跳过不计 PASS；本批新框架没有跳过。警告来自既有 rdflib 弃用及 Python fork 提示。
- v5 Ruff check 通过，26 个 Python 文件格式检查通过，`git diff --check` 通过。
- 旧包导出及新 bootstrap 的定向 Ruff 检查通过；真实 `python -m ontoweave_modeling --help`
  正常列出七个显式命令。五份相关 Markdown 的 115 个本地链接、18 个锚点、21 个表格、
  9 个围栏块检查通过。
- 环境：v5 Python **3.12.3**；Host backend Python **3.14.3**；SDK／CLI 及依赖沿已有 v5 lock。
  不据此声称其他 Python 版本通过。

实际覆盖：冻结与篡改／授权边界、精确历史引用、真实 PostgreSQL checkpoint、普通链与格式
纠正、模型完成后 checkpoint 丢失、未知执行不重启、未知应用同身份接续、忙碌暂停／停止、
虚假消费、真实 Host 导入／编译／原计划复用、旧公开导出兼容，以及独立报告覆盖、修订、成功
读取、来源、私有投影和可纠正格式。独立评价使用自己的材料／执行身份，不推进生产工作记录，
也不消费生产队列输入；Host 在途统计包含评价。

图中的 `round` 为内部候选／执行代次，不是建模轮次或 semantic-start 额度。真实运行仍须按
原授权记录两种计数；本批没有真实 semantic start。

## 影响与保留边界

GitNexus 对旧 `_bootstrap_helpers` 的索引结果为 LOW，但索引已落后 525 个提交，且未包含
当前 v5 包。依据仓库规则补充当前源码调用点与 diff 检查：旧 CLI、incremental、P0 探针及其
已有调用继续使用兼容函数；不把旧索引结果称为当前完整图影响覆盖。提交前
`detect_changes(scope=staged)` 返回 **LOW**，仅识别 `_bootstrap_helpers` 等 2 个旧索引符号、
0 条已索引受影响流程；新增 v5 未被覆盖，不能据此推导“没有实际影响”。本批以定向源码检查、
真实 Host 导入／编译测试和上述完整旧 Team 回归补充该缺口。

本批仅修改 `modeling_team/` 及本需求文档，没有修改 backend／frontend 代码、依赖、服务配置
或启动脚本，不要求应用服务重启。v5 使用原独立锁定环境；backend Host worker 使用现有环境。
原有 GraphRAG 研究、导航的未提交变更保持，不纳入本次提交。

## 尚未完成

- 同一获准小目标的真实 Codex → 实际应用 → 治理读回／业务自查 → 独立语义评价，仍待执行。
- 原生未知执行的全面自动重连、实际平台新桥的全部故障窗口及联合持久接续，仍须按阶段验证；
  当前在证据不足时准确阻塞，不盲重放。
- 完整方法、项目发现查询、动态 HITL、递归并行、增量／总览、一般预算与默认切换仍归 P1.2—P4。
- 本批为开发者工程验证，未要求或执行额外独立工程验收；设计的独立 PASS 不替代工程或语义证据。

操作说明见 [v5 README](../../../modeling_team/v5/README.md)。
