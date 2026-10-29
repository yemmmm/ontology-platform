# v5 生产成员通信、任务卡与材料交接

## 范围与结果

2026-10-29 用户批准按[通信与交接澄清](../../research/2026-10-29-v5-agent-communication-handoff-boundaries.md)
实现并启动最小真实建模验证。归属 [R5.0-001／002／003／007](../../requirements/requirements-v5.0.md#r5-0-001)，
承接 [R4.4-001](../../requirements/requirements-v4.4.md#r4-4-001) 的生产成员工作卡和
[R4.3-013](../../requirements/requirements-v4.3.md#r43-013-agent-自主选择文件或目录引用交接) 的材料交接。
沿本次 v5 研发已有 `usage_only` 授权，所有托管角色为 `glm-direct / glm-5.3-flash / low`。

**本批功能已实现；107 项开发测试通过，真实双成员交接、一次应用及治理自查完成，独立
公开工程判据 1/1 PASS。真实运行经过宿主技术修复后沿同一 run 接续成功，不称全程自主
或最终代码的无干预冷启动通过。** 公开最小场景不是盲测，不关闭完整 P1.3／P2／v5 或
完整业务语义验收；本轮没有证明净降耗。

## 实现

- Task 可选 `collaboration.peers`，当前 `modeling` 及显式 peer 为稳定生产身份，peer
  复用获准 modeling 模型配置。LangGraph 增加 `collaborate`，在原生回合结束后按队列
  串行执行有输入的成员，回复回到原步骤；无消息时保存 `waiting_peer` 并退出，不轮询模型。
  不新建递归／并行团队调度器，也不因增加成员而开放独立验收通道。
- 六个 MCP 工具：`send_team_message`、`publish_handoff_material`、
  `read_handoff_material`、`update_work_card`、`get_work_board`、`resolve_work_request`。
  Provider、Codex 装配和实际 MCP 服务同步接线；独立验收保持两项原读取工具。
- 普通对话与附带署名 `work_request` 的请求共用发送入口；可关联 `reply_to`。消息 ID
  在 run／发起者内稳定，重提不新增队列记录；同身份不同内容返回可纠正冲突。
  请求在双方卡片关联展示，只有发起者判断 satisfied／withdrawn，回复不自动满足依赖。
- 工作卡只写本人当前工作、范围、近期计划、等待及成果引用，保存真实更新时间和版本。
  同内容重提不伪造新进展；历史读取用原对象 revision。本人 author 可冗余提供，最终
  身份仍由工具绑定；不能冒充另一成员修改计划。版本可在顶层或 card 内提供，冲突明确反馈。
- 消息正文与材料引用分开。发布本人分析或用 `source_material_id` 冻结获准原文，无需
  重抄大材料。接收方按 object_id／revision 读取固定版本和字符范围，工具补全摘要，
  显式摘要不符仍拒绝；新版本不替换旧交接。接收权限绑定本人材料或已收到的对应版本。
  材料引用字段在工具 schema 中显式给出。
- 同伴消息 source=agent，宿主修复 source=host；不冒充 source=user 的人工答复。
  `resolved_request_ids` 仅接受人工 HITL 请求，协作请求通过专用工具关闭。混合提问与
  同伴派单时先保存人工问题，再推进同伴；问题不因流程切换而丢失。
- 复用 PostgreSQL 对象版本和原 TaskControl 队列，没有新增数据库模型、后台服务或
  FastAPI 路由。正常消息仍等完整 `turn/completed`，工具结束／输出 item 结束不算。
  已退出的等待任务用显式 resume；成员源代码、当前卡和队列不注入隐藏验收。

入口和使用方法见 [v5 README](../../../modeling_team/v5/README.md#可选生产成员通信与任务卡)。

## 开发验证

使用锁定 v5 环境、真实 PostgreSQL 随机 schema／PostgresSaver。最终命令：

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

最终 **107 passed、0 skipped、1 条既有第三方 warning，81.22 秒**；Ruff check 与
32 个 Python 文件 format check 通过。此前完整轮次 102、103、104 项及各次针对性测试
按当时输入保留，不覆盖后续修复。最终日志 `workspaces/v5-runs/team-20261029-delivery-tests.log`。

新增 11 项覆盖真实 MCP 装配、隔离 Codex 工具直调、busy 入队、分段读取、原版本保留、
跨 run／未授权读取、双方卡片及历史、署名与发起者关闭权限、幂等与不透明 ID、
技术反馈定向路由、人工问题不被同伴切换吞掉、原流程接续及不重放应用。
隔离 SDK 测试不发起模型请求；确定性 Actor 流程不作为真实语义证据。

## 真实任务与失败修复

Task `v5-minimal-team-20261029`；run `v5-minimal-team-20261029-start1`；工作单元 `team-unit`。
初始基线 `11a5237` 加本批工作区实现，后续修复沿原 run 追加，旧事件、失败与回执保留。
输入位于 `workspaces/v5-runs/team-20261029-inputs/`，运行与 `runtime-summary.json` 位于
`workspaces/v5-runs/team-20261029-start1/`。私有连接、凭据及 gitignored 原件不提交。

公开原文为 [team-source.md](../../../modeling_team/v5/tests/fixtures/team-source.md)，SHA256：
`99de578cdbdca5e276ded24231cc27f38cb18c197fd104499f3701e51e87a328`。仅定义“演示设备”一个
概念；协作角色检验原文忠实度和范围，不补业务事实。冻结公开工程判据
`v5-team-public-criterion-20261029`，1 题，SHA256：
`efdddd6de59435f11f5d1f36a4adc35679f020c688d311f18801948cad2fe82e`。

| 第一阻塞及后续发现 | 归因／修复 | 证据边界 |
| --- | --- | --- |
| 新通信 MCP 无法解析 localhost，原文读取正常 | runtime/infrastructure；沿已有 P0 hostaddr 方式在 Host 解析地址，新增实际 Codex 装配的卡片／发布／分段读取测试 | 最初测试未覆盖新入口的隔离装配，是复用路径遗漏，非模型质量失败 |
| 原生回合反复重试同一失效连接，正常暂停等不到结束 | collaboration/routing，伴随 prompt-contract 缺陷；权威提示要求持续基础设施故障返回 recoverable_issue | model-00003 已发生 54 次工具调用；关闭该执行独有 Provider 代理后，原生真实返回 failed，停稳再接续。无模型写入，未伪造原生成功或补造消费 |
| 完整消息 ID 含冒号，被路径式 safe_id 拒绝 | platform-contract；T0 复核后删除无必要的路径格式限制，保留非空、身份绑定、授权、参数化存储及幂等冲突检查 | ID 只用于数据库对象／队列，不进入文件路径；删除不会增加任意文件访问或跨成员写入 |
| 材料摘要省略、字段猜测、卡片版本放置导致多次纠正 | platform-contract，伴随 prompt-contract 缺陷；固定对象＋版本已约束不可变原件，摘要改为可省略并由工具补全，显式不符仍拒绝；引用用显式 schema，版本入参做最小归一化 | 授权仍检查实际获准对象与版本，不放宽源材料或跨 run 读取 |
| 把材料 ID 当消费 ID，把协作请求当人工解决项 | collaboration/routing，伴随 prompt-contract 缺陷；保留消费／人工确认校验，返回实际可消费 ID，提示和 schema 明确两种请求不同 | 这些守卫保护真实消费及人工来源，不能通过过滤错误声明冒充成功 |
| 只有定向宿主修复输入时 peer 不被调度 | collaboration/routing；按目标工作单元发现实际 input，不把技术消息显示为生产协作卡片 | 原消息未被复制为业务答复；定向回归与原 run 中的重读／回复均有证据 |

T0 结论：不透明 ID 的路径校验和读固定版本时必须回传摘要均未保护额外不变量，反而令
可修正输入陷入重复；删除／降级由既有身份、版本、授权和存储约束覆盖。人工来源、
消费归属和实际原文读取则保护真实合同，保留并给准确反馈。三个宿主补充均 source=host，
只含技术修复与原有路由引用，不新增业务材料，不进入人工业务答案。

最终原请求及三条不同修订回复均有唯一队列记录，七条 input 全部 consumed。部分消息
在前一消费声明未确认时多次交付，原 deliveries 保留；不声称一次交付或无重读。
协作 Agent 实际以 300 字符和后续范围读取 480 字符原文，最后读完本场景；证明分段能力，
不声称本次避免了全文读取或因此节省 token。双方卡片最终 revision 分别 4／2，请求由
modeling 标记 satisfied；卡片正文与原生事件共同保留。

只有 `apply-00009` 一次实际应用，Ontology revision 0→1，随后治理自查通过。独立只读
评价实际读取原文、冻结题和目标并查询实际模型，首个报告 **1/1 PASS**，不接收生产
候选或生产卡片作为模型答案。semantic-start **1**、初建轮次 **1**；内部 round=9、
peer_round=3 属问答／技术纠正，不另作实质修模轮次。

## 资源、时间与成本

项目 `a328b725-57f9-4670-b2e1-89b59b0cf7e6`，Ontology
`6fdd60ba-e426-469e-a1e1-fd948523c8c9`，Class `b010172e-fdb0-56eb-892d-c927bee718e0`。
Batch `0fecb062-54fc-404c-9c1b-c17e1b9c0cc6`、Attempt
`7d617cd1-a4b7-4fbd-8e46-a2c7d533b865` 均 applied。cleanup 返回 `written-retained`，
原模型与证据保留，session 终态、无在途 Attempt。四个精确 key ID 经后端只读核实均已
撤销；最终无在途 Agent 或未消费 input。兼容层原 disposition 原样保留在清理回执。

授权 `08:36:29Z`；首个真实原生回合 `08:46:01Z`，间隔 **9 分 32 秒**，在 20 分钟内。
从首个回合到撤权 `09:15:19.856445Z` 墙钟 **29 分 18.856 秒**，包含修复、暂停和等待。
原生回合累计 **1174.502 秒**；142 个完整上游请求累计 **1121.177 秒**，另有 1 个因
失效代理关闭而缺终态的请求；控制 paused 模式累计 **463.935 秒**。上述区间有重叠，
不能相加；原生时间也不是纯语义建模时间。宿主开发／测试／文档有效分类计时 unknown。

各原生 thread 取最后累计量，失败与纠正均计入，重复通知不重复相加：

| 用途 | 原生执行数 | 输入 token | 输出 token | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 建模及纠正 | 10 | 952565 | 17381 | 969946 |
| 生产协作 Agent | 3 | 251039 | 9176 | 260215 |
| 治理自查 | 1 | 40380 | 678 | 41058 |
| 独立公开工程检查 | 1 | 12941 | 1126 | 14067 |
| 合计 | **15** | **1256925** | **28361** | **1285286** |

每个原生执行都有用量记录，但中断请求及上游结算未完整覆盖，金额计量仍 **PARTIAL**。
外部 Host 用量单列 unknown，不计任务金额费用。重复失败及参数纠正明显增加成本，
不能以本批功能通过证明降耗或完整自主稳定性；最终代码无干预冷启动仍待后续有界验证。

本批无 backend／frontend、依赖或共享应用配置变化，无需重启应用服务；新的 CLI／MCP
进程加载 v5 代码。GitNexus 未索引 v5，impact 返回 UNKNOWN／target not found；采用
当前调用点、diff、开发测试及真实链验证，不宣称图影响覆盖。没有额外独立工程验收角色。
提交前 detect_changes 检查 15 个 staged 文件，返回 low、0 个索引符号和 0 条流程；
因 v5 缺失于旧索引，这不证明本批完整图影响或无风险。
当前仅提供单工作单元、显式生产成员的串行协作；完整递归、并行、项目记忆、金额控制及
旧工作展台全部查询能力没有在本批实现或验收。
