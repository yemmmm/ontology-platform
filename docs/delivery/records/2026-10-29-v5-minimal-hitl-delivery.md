# v5 最小 HITL 开发与验证

## 授权与交付范围

2026-10-29 用户批准最小范围：Agent 发问、CLI 查看／答复和主动补充、按原工作单元与
步骤恢复、进程重建后接续且不重复消费／应用。归属
[R5.0-001 F9](../../requirements/requirements-v5.0.md#r5-0-001)及
[P1.3](../implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md#p1-3)。
沿当前 v5 实验的 `usage_only` 授权，不前置完整项目记忆、UI、多单元并发或一般额度
控制。初始代码为 `bfbd89b`；期间独立研究提交 `7038f60` 及无关 GraphRAG 工作保留。

## 已实现

- Agent 回合结果增加 `human_requests`（问题、理由、影响）和 `resolved_request_ids`。
  程序保存请求的稳定 ID、不可变版本、工作单元、原步骤、来源摘要、基线和执行引用，
  然后进入独立 LangGraph `interrupt` 节点；等待节点不启动 Agent 或应用。
- 复用现有 PostgreSQL 对象／版本仓储及队列。`questions` 显示问题、版本、答复、状态；
  `reply` 关联原请求，`input` 保存主动补充。支持正文文件、消息 ID、作者和 `--partial`。
- 答复先保存后入队；相同消息重试复用原回执，不同内容冲突返回可纠正错误。消费按 task、
  run、工作单元、步骤绑定；busy 时不 steer／interrupt，下一适用回合消费。
- 显式 `resume` 在新 CLI 进程中以 `Command(resume=...)` 恢复原步骤。模型阶段先刷新
  实际基线供 Agent 判断旧答复的适用性；自查阶段继续实际读回。无答复不轮询模型，
  stop 不被答复或 resume 撤销，交接后不把新输入静默注入旧目标。
- 收到／交付／消费不自动解决问题。首次解决须匹配已消费的非部分答复，并由 Agent 明确
  确认；部分答复保留未决。重复确认已解决请求为幂等操作。
- 执行登记保存原 prompt；问题已保存但 checkpoint 丢失等重入复用原结果，不因新问答
  上下文改变原意图，不重新启动未知执行。原应用及目标版本不被重放或覆盖。
- 交接后将有归属人工答复作为单独来源材料交给只读评价，保留作者、版本及 partial 标记，
  排除宿主技术输入／生产候选；报告必须有该材料的实际成功读取证据。

实现位于 `human_input.py`、流程、CLI、控制、执行登记及现有仓储的 task 内按类型读取。
通用结果合同与建模提示同步更新；未新增数据库模型、服务或 Agent 数据库权限，也没有
增加 HITL MCP 服务。问题来自回合结构化结果，原文／模型读取继续使用原 MCP 工具。

## 工程验证

使用锁定 v5 环境及真实 PostgreSQL 随机 schema／PostgresSaver。确定性 Actor／平台
替身用于故障窗口，不称为真实建模或独立语义 PASS。最终命令：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 pytest -q \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff check \
  modeling_team/v5/src modeling_team/v5/host modeling_team/v5/tests
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff format --check \
  modeling_team/v5/src modeling_team/v5/host modeling_team/v5/tests
```

最终 **96 passed、0 skipped、1 条既有第三方 warning，74.00s**；Ruff check 及
29 个 Python 文件 format check 通过。原有 83 项及新增 13 项均覆盖；共用 fixture 移至
conftest，不修改原业务断言。首轮完整回归为 90 passed，后续修改按受影响范围复验。
最终五份文档的 83 个本地链接、代码围栏及 diff 检查通过；原应用健康检查仍返回 `ok`。

新增覆盖：持久等待／重建、无答复不唤醒、完整／部分答复、版本与跨 task／run 隔离、基线
变化后重读、CLI 多行／幂等／主动输入、busy 入队、stop 后拒绝新输入、技术输入不冒充
业务来源、应用后等待不重放、问答与 checkpoint／队列不同先后失败，以及人工来源读回。

## 真实问答与原 run 接续

授权记录 `03:07:44Z`；约 `03:19:46Z` 启动真实建模，在 20 分钟内。所有角色使用
`glm-direct / glm-5.3-flash / low`。Task 为 `v5-minimal-hitl-20261029`，run 为
`v5-minimal-hitl-20261029-start1`。输入／日志在 `workspaces/v5-runs/hitl-20261029-inputs/`，
原运行在 `workspaces/v5-runs/hitl-20261029-start1/`，私有连接／凭据不提交。

公开 fixture `tests/fixtures/hitl-source.md` 确实未给概念名称；SHA256 为
`0f7d29ba2eba55150627e26bb059ab87f26904b7a06abed7b13295c74dd6b7ed`。Agent 实际读取后
自行提问：“请提供本次要创建的演示业务对象概念的正式名称是什么？”请求
`human-request-a0b1965920dd041f05645840` 被持久保存，CLI start 自然退出等待；随后
`questions` 读取原问题／版本，没有额外模型调用。

用户实际回复“你直接回答即可”。据此明确授权，宿主代答“人工确认演示对象”，作者为
`host-on-explicit-user-delegation`，原授权一并保留。证据准确称为“真实 Agent 提问＋
用户授权宿主代答”，不称用户亲自指定了名称。

`reply --message-id naming-delegated-answer-001 --request-revision 1 --text-file ...`
提交原答复后，新 CLI 进程 resume 原 run。答复一次交付、一次消费，请求最终 `resolved`，
只发生 `apply-00001` 一次实际应用；原等待前建模不被重新执行。项目
`2e36aee6-aa1d-4338-b7fa-2156c987aa7f`，Ontology
`58cf883e-59de-4af6-be23-91d81e7a9fe6`，最终 `handoff_ready`，实际模型修订 1。

真实过程发现：自查重复列出已解决请求，被过严校验要求再次消费答复，造成无效重试。
T0 复核确认首次答复关联保护有必要，但重复确认不改变业务／资源，原 resolution 和消费
记录已覆盖风险；故对重复确认改为幂等，保留未答复／部分答复拒绝。新测试先复现失败，
再验证修复；原事件与失败返回保留。

公开工程判据为模型是否使用获准答复名称并保持原范围。只读检查实际读取原文、判据、目标
及人工输入材料后 **1/1 PASS**；首次报告 JSON 格式错误沿同一评价身份更正，模型、
答复与判据未变。判据由宿主公开准备，不是盲测，不升级为完整业务语义验收或完整 P1.3／
v5 PASS。真实部分答复等业务反例未逐项进行模型实验，机械测试与真实采用分开记录。

## 资源、用量与边界

cleanup 确认会话终态、无在途 Attempt、模型保留，返回 `written-retained`。另按本任务
四个精确 key ID 只读核实 modeling／acceptance／protocol／admin key 全部撤销，没有
创建替代凭据或重放应用。原始问答、消费、失败、检查点、模型、报告及汇总
`runtime-summary.json` 均保留。

真实任务从 `03:19:46Z` 至 `03:38:57.337067Z` 撤权，墙钟 **19 分 11.337 秒**，
含人工等待和修复；控制暂停 **4 分 25.447 秒**。26 个上游请求累计 **4 分 46.949 秒**，
可能与暂停尾部重叠，不能与墙钟相加。宿主有效开发／文档／测试未完整分类计时，保持 unknown。

取每个原生 thread 最后累计量，含失败及纠正，重复通知不重复累加：

| 用途 | 输入 token | 输出 token | 合计 | 原生执行数 |
| --- | ---: | ---: | ---: | ---: |
| 建模／问答接续 | 28041 | 611 | 28652 | 2 |
| 自查及纠正 | 114067 | 2015 | 116082 | 5 |
| 只读检查及格式纠正 | 40275 | 1727 | 42002 | 2 |
| 合计 | **182383** | **4353** | **186736** | **9** |

原生量覆盖全部九个执行，但不是完整上游费用结算；金额计量仍 PARTIAL。外部 Host 用量
未取得、单列 unknown，不计任务费用。semantic-start 为 1、初建轮次为 1；问答接续和
技术纠正不从内部 round／check_round 值另扣轮次。

本批没有 backend／frontend、依赖、共享运行配置或启动脚本修改，不要求应用服务重启。
GitNexus 未索引 v5，impact 为 UNKNOWN／target not found；使用当前调用点、diff、
v5 全套及真实链核对，不宣称图影响覆盖。本批没有额外独立工程验收角色。
提交前 `detect_changes(scope=staged)` 读取 18 个文件，返回 low、0 个索引符号及 0 条
流程；v5 缺失于旧索引，这不是本批完整图影响或无风险证明。

CLI 答复先入队；已退出等待的 run 用显式 resume 推进，没有后台自动唤醒服务。完整
P1.3、多单元调度、真实部分答复的更多场景、项目记忆、UI 与金额额度控制仍属后续阶段。
