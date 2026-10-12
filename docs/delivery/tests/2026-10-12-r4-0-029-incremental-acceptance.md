# R4.0-029 独立增量功能验收

结论：**PASS（A1—A10 的确定性／受控合同及必要相邻回归范围），0 未解决 Critical／High**。
第 2 轮 High 启动阻塞已 FIXED；A11、真实线程 semantic start 及真实 L1 未执行，完整真实验收仍 PARTIAL。

## 依据、范围与证据边界

- 权威需求：[R4.0-029](../../requirements/requirements-v4.0.md#r40-029-基于已有模型的增量建模)。
- 设计：[增量建模设计](../designs/2026-10-12-r4-0-029-incremental-modeling-design.md)。
- 只编辑本记录及 `modeling_team/tests/test_r4029_independent_acceptance.py`；产品代码只读。
- 独立功能范围为 A1—A10 的确定性／受控 runtime 合同，包括必要的恢复、待命、CQ 相邻回归。
- 不启动真实生产、不调用付费模型、不注入隐藏答案、不修改保留证据。
- A11 需要单独真实建模授权，本轮未执行；受控合同通过不构成真实 semantic start、业务效果或 L1 PASS。

## 环境与前置条件

仓库 `/home/yangxiang/ontology-platform`；Python 使用 backend 的 uv 环境。
实现负责人提供就绪消息后执行；记录 HEAD、相关工作区差异、命令、结果及缺陷。
HTTP／Delivery 外部边界以可观测 stand-in 控制，不访问业务服务；已有受控 fixture 按其原测试边界复用。
有并行 Agent 修改其他文件；不回退其改动、不修改他人测试。

## 用例、步骤与通过标准

| 编号 | 步骤／输入 | 期望结果与证据 |
| --- | --- | --- |
| A1 | 原 Team 不存在，调用内部 incremental start，捕获 Delivery 入口及生成快照 | 新任务／会话／run 身份，existing 当前模型绑定及获准资料；无旧线程／历史对话依赖；只证明受控启动接线 |
| A2 | 复用原目标恢复、同 run 修正及待命咨询测试；新目标调用增量入口 | 恢复不更改原目标，咨询不打开写门，新目标独立身份，不额外隐式 start |
| A3 | 单／多明确 ID；同名、缺失、跨 Project、重复 ID | 按实际 ID 绑定；错误可定位；不得按名称猜测或自动创建；捕获请求列表 |
| A4 | 有效当前读取 identity binding；仅复用及新增引用既有定义 | 稳定身份不 create／无意义 update；纯复核可交接；未应用的新定义仍拒绝覆盖 |
| A5 | 已有定义绑定配合修改／必要删除意图，检查计划及依赖合同 | 命令对应批准意图，已有定义不伪造 create；引用影响明确；无关定义保持 |
| A6 | 未授权新本体、授权拓扑新建、同名本体、创建 unknown／重试 | 未授权无 POST；获准同 Project 创建，实际回执复用；unknown 不按名称绑定／盲重放 |
| A7 | 获准来源、反馈观察及 current read 含受限／分页未完／冲突 | 内容及未知准确保留，生产输入不含隐藏目录／全对话；不把反馈期望当确认事实 |
| A8 | 修订漂移、unknown apply、active writer 及失败 cleanup | 沿既有对账／重读路径；不换身份重放；旧模型和新应用资源保留，仅本轮凭据收尾 |
| A9 | 新 CQ selector 与旧冻结／报告隔离；公开反馈和正式独立验收合同 | 明确本轮范围，新冻结不拼旧 PASS；公开反馈不作为盲测；验收边界只读 |
| A10 | 缺／过期／额度不足授权，重复 request_id、未知 launch、配置修复部署字段 | 未授权不启动；重复请求核对原启动，不隐式重试；代码修复／部署未授权不可执行 |
| A11 | 两条真实业务输入在当前模型上执行与独立语义检索 | BLOCKED：本轮没有真实建模授权；解除条件为明确授权与冻结业务范围 |

独立功能 PASS：本轮范围用例与必要相邻回归均通过，无未解决 Critical／High 产品缺陷。
未执行项标记 BLOCKED，明确其解除条件；局部覆盖不能提升为全部 A1—A10 或 L1 PASS。
首轮后只在同一文件追加复测记录，优先失败／阻塞项及受修复影响回归，保留历史。

## 测试轮次

### 第 1 轮：2026-10-12，PlatformScope 部分就绪

HEAD `40843fcc6abf229317dc66a8f591cec15d322e93`，工作区有并行未提交实现。
执行（backend 工作目录）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4029_independent_acceptance.py ../modeling_team/tests/test_platform_scope.py -q
```

首次为 18 passed、1 failed、5 subtests passed；失败为测试断言过宽地把安全 cleanup 的
POST revoke 误当成新启动写入。修正测试为检查新 key／Ontology 创建后，同命令复测
**19 passed，5 subtests passed，0.11 秒**。不是产品修复，无产品缺陷。
A3/A6/A8 的 exact ID、同名不误绑定、整计划授权、实际本轮创建回执、unknown create
不重放、active writer 阻断新凭据及既有／新增资源保留均 PASS（HTTP stand-in 合同）。
其余入口／纯复用验收未执行，A11 未授权 BLOCKED。

### 第 2 轮：2026-10-12，入口部分就绪

HEAD 同上，新增 `incremental.py`／029 Task 未提交，其他实现仍并行变更。
独立 fixture 复制仓库实际 Task/Profile/Package/Skill/Reference/Model Profile 到临时根，
使用实际 loader，仅 scope 和 Delivery 外部边界受控；没有 mock 产品配置验证。

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4029_independent_acceptance.py -q
```

结果：**15 passed，4 failed，0.40 秒，FAIL**。
A3/A6/A8 与授权拒绝／旧运行资料禁入 PASS；A1/A7/A9 正常快照及 A10 稳定/unknown
启动被相同产品缺陷阻塞。A2/A4/A5 相邻及新复用覆盖尚未执行。A11 仍 BLOCKED。

#### 缺陷 D029-1（High，platform-contract）

- 复现：运行 `test_a1_a9_prepare_normal_new_task_with_exact_current_scope`；输入明确当前
  project/ontology_ids、有正文的获准资料、有效授权和真实 4 角色 Profile。
- 期望：正常 v4 Task 被实际 `load_multi_slice_team_configuration` 接受，返回新任务快照。
- 实际：`incremental.py` 把获准资料快照放在 `workspaces/incremental-requests/<UUID>/source-0.md`；
  `contracts.py:_load_v2_source` 以 `workspaces/` token 拒绝，抛出
  `TeamConfigurationError: v2 Task source is not Agent-visible`（line 717）。所有正常新增入口失败。
- 证据：同轮四个失败栈均到上述 loader，包含快照、重复启动、unknown 启动及公开反馈。
- 建议：实现负责人窄修获准快照可见性／路径接线，保留旧 run/private/test material 禁入；
  修复后复测同一独立文件。不应通过 mock loader 或绕开正常 Task 合同将用例标 PASS。

### 第 3 轮：2026-10-12，修复后复验与必要相邻回归

实现负责人窄修正常 loader 对当前获准公开快照路径的支持，继续拒绝旧 run／private／test
输入。HEAD 同前，相关内容为未提交工作区。

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4029_independent_acceptance.py -q
```

**25 passed，1.11 秒**。D029-1 **FIXED**，正常实际 loader 快照、稳定 request_id、unknown
Delivery launch 禁重放、公开反馈白名单及来源保留均 PASS；仅外部 scope／启动边界受控。
新增独立复用测试从既有通用 production contract fixture 建立实际 observed read，验证：

- A4 **PASS**：已读稳定定义复用覆盖，无 create／update／dry-run／apply；新 relation 仍为
  unaccounted；明确 deferred 后纯复核可收口。受限／分页未完的单个实际已读条目可复用，
  不把未读其他定义当不存在。
- A5 **PASS（确定性身份合同）**：已有身份 create 被拒绝，update／delete 仅精确原 target
  被接受，错误 target 被拒绝；业务共享含义、影响依据是否正确仍需 A11 的实际 Agent 验证。
- A8 **PASS**：当前 revision 漂移准确返回 `approval_stale`，不写入；恢复有效读态后同 run
  可继续，不形成不可恢复死亡。

执行必要相邻回归（backend 工作目录）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4029_independent_acceptance.py ../modeling_team/tests/test_platform_scope.py ../modeling_team/tests/test_team_standby.py ../modeling_team/tests/test_r4314_recovery.py ../modeling_team/tests/test_r3011_cq_lifecycle.py -q
```

**76 passed，5 subtests passed，10.05 秒**，无 REGRESSION。
A2 原目标恢复保持原请求、同 run 修正、待命咨询不重新打开写门；A8 unknown／recovering
Attempt 核对原请求、不用换 Key 重放、无关范围可继续；A9 新冻结保留旧快照、公开题不能
回到 hidden、报告边界只读的既有合同回归 PASS。未启动真实模型或业务服务。

### 第 4 轮：2026-10-12，Delivery 授权绑定补验

增加直接调用真实 `DeliverySession.call_tool` 的独立参数化用例，验证固定 run/request
身份不能替换、repair／部署不因 production/evaluation 授权自动开放。首跑 fixture 未给
production 必需 task/profile/scope，4 failed／25 passed；该失败是测试前置遗漏，补齐后：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4029_independent_acceptance.py -q
uv run ruff check ../modeling_team/tests/test_r4029_independent_acceptance.py
```

**29 passed，1.18 秒；Ruff All checks passed**。A10 **PASS**，无新增产品缺陷。
`git diff --check` 通过；无需因测试文档／Team 测试代码改动重启产品服务。
第 3 轮必要相邻测试的相关输入未变，不重复其已通过执行。

### 第 5 轮：2026-10-12，最终恢复／授权边界补验

实现负责人补齐 unknown 写入门、native MCP envelope、范围绑定、Session 所有权清理及
到期只读查回执后，追加独立用例。unknown 测试首跑 fixture 缺实际写入所需 lease_tokens，
为 32 passed／1 failed；缩小诊断命令亦定位为 fixture 前置错误 `staged_submit_schema_mismatch`。
补齐真实 fixture 的原 lease 后 33 passed（1.33 秒）；补 Session 所有权后 34 passed（1.34 秒）；
补恢复身份与 Batch 授权边界后 **38 passed（1.76 秒），Ruff 通过**，无产品 FAIL。

- A3 **PASS**：实际 existing Batch 超出 scope.ontology_ids 返回 `forbidden_scope`，没有写调用。
- A4 **PASS**：native `content` envelope 与 structuredContent 按同一实际观察记录绑定，
  coverage 写入 `evidence/plan-coverage.jsonl`。
- A8 **PASS**：真实 unknown intent 留存时不能用空复用计划收口；原 apply 不重放。
  清理只 cancel 本 run 记录的 own-session，其他 run 的 Session 仍 active，模型无 DELETE。
- A10 **PASS**：过期后已启动请求仅查原 receipt；只有 prepared、未启动请求拒绝新启动。
  Delivery 恢复禁止提升预算或替换原 request/run。

对变更后的相关输入重跑第 3 轮同一组合命令：**89 passed，5 subtests passed，10.13 秒**。
无 REGRESSION；不把未授权真实 runtime 或 001 存储标 PASS。

### 第 6 轮：2026-10-12，最终拓扑接线补验

实现负责人明确区分完整本轮 scope.ontology_ids 与有序 ontology_plan_ids，独立补两项：
仅在 model-b 计划业务仍保留 model-a 的授权和 Protocol 交接；计划 [model-b, newly-created]
的新切片引用精确 PATCH newly-created → model-b，而非错误指向完整 scope 首项 model-a。
首跑 39 passed／1 failed，是 HTTP stand-in 的 modeling-context 未提供 Project／Ontology
归属（产品按预期拒绝）；补齐 stand-in 归属后：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4029_independent_acceptance.py -q
```

**40 passed，1.30 秒**。A3/A6 **PASS**，无新增产品缺陷。至此不继续扩大范围。

## 结论边界及交接

A1—A10 受控功能合同 PASS，不证明实际 Agent 能形成正确业务含义。A1 只验证新身份、
当前 scope、普通 Task 和 Delivery 启动接线；未启动真实角色线程，不声称已观察 semantic-start。
A7 只验证当前 read 限制／未知保留、公开反馈投影和隐藏隔离；不以 prompt 内容代替真实
冲突澄清质量。A5 共享定义变更的正确业务影响范围同样等待真实独立语义证据。
001 默认反馈存储尚未实现时准确返回 unavailable，接线 seam 的受控公开投影通过；
不宣称已交付 001 的生产反馈读写。

A11 **BLOCKED／未执行**：没有本轮真实语义建模授权；解除条件为单独授权两条真实输入、
获准业务资料及冻结范围，并由独立只读验收者判业务效果。当前没有建议必须再修的产品
Critical／High；主 agent 可按已通过的功能证据继续交付，不能把本记录改为完整 L1 PASS。


## 最终相关内容快照

HEAD `40843fcc6abf229317dc66a8f591cec15d322e93`，实现未提交工作区。以下摘要用于后续冻结核对；
相关输入变化后仅复验受影响证据。

| 文件 | SHA-256 |
| --- | --- |
| `modeling_team/incremental.py` | `98eb88099cbef1368188b540be17b232138d0ea5605aab4b4c571a20d4583f53` |
| `modeling_team/contracts.py` | `18ddcfc1a9a031848ba42676fced2f6f387fbefb80b6d3cef945f37b8020ed31` |
| `modeling_team/platform_scope.py` | `e1b5c42f32fe285f6dc9647a74e17f86be51b6f4399b6e2a3a03cb9bc8514542` |
| `modeling_team/scenario_map.py` | `6005fce15bea9cf14ead863ce0d0e18d5db4d4e86314e5abd70ee32946305343` |
| `modeling_team/runner.py` | `0f88101c363e92623b03fb1c533dda0131ad4514953ca76778a1ba0e1f3eb196` |
| `modeling_team/staged_decisions.py` | `bcdbae6479503188d306490340920da2d73612f1b2c67afc6c714d7b784aa21e` |
| `modeling_team/delivery.py` | `aa0ecd341e9188a1bb7d6341c1073219e847e4d9eee70a1b5f724270e19eb0f6` |
| `modeling_team/__main__.py` | `dc5967f9b529386ab646fef72232a96eb9febe4ccded154a4cf4b6309deab7b5` |
| `modeling_team/tasks/r4-0-029-existing-model-incremental.yaml` | `2005eb0e32cbca943166b0590e235096a37dd76734bbd515502c2b5b8e69b487` |
| `modeling_team/tests/test_r4029_independent_acceptance.py` | `99a7b0cdf661bc1f292ed5e15bd260e7ad837acf4f34db1df49ad2fa2c9c6b7c` |


## 第 7 轮：2026-10-12，后端身份夹具相邻回归

主 agent 提供 `backend/tests/test_r4007_team_identity.py` 的窄 fixture 修正：
workspace-context stand-in 由只有 state=ready 补齐明确 ontology_id/model_revision=0。
独立复核 diff 仅这一处返回值，全部原断言保留；没有产品代码修改。补齐当前修订前置后，
existing/checkpoint 用例继续走真实认证／SQL API 的原 key 创建 422 拒绝路径，验证没有
自动 Project membership 注入；create/fork 的合法身份／model/read key 绑定均保留。

执行（backend 工作目录）：

```bash
env -u DEEPSEEK_API_KEY SEMANTIC_JEV_ENABLED=false PYTHONPATH=.. uv run pytest tests/test_r4007_team_identity.py -q
```

结果：**4 passed，11 warnings，0.67 秒；PASS**。warnings 为既有 FastAPI/Starlette
弃用提示，无用例失败。测试进程显式关闭默认实网 Jev 重排，不改本机 `.env` 或服务配置；
本文件不需要 Jev，故该环境设置不影响本轮身份断言。

父 agent 报告另有全量后端测试正在执行；该全量结果未由本测试 Agent 独立核验，不计入
本轮独立 PASS。A11 与 001 存储限制不变。此前第 6 轮代码快照保留，新增夹具快照如下：

| 文件 | SHA-256 |
| --- | --- |
| `backend/tests/test_r4007_team_identity.py` | `a906125de3446d31c4533de79f8051a6c6722dd948febc07919ad7371d9e3c80` |


## 第 8 轮：2026-10-12，真实 topology gate 可恢复失败复验

针对最后的既有 opened latch 修复，仅扩到已批准 A6/A8 的同 run 重试边界。新增两个独立
参数化用例调用真实 `_check_multi_slice_topology_gate`，保留实际 topology/map 文件、实际
CandidatePlatformGate 和 PlatformScope，只有平台 HTTP 返回受控：

- 未获准新建时准确反馈 `topology_apply_incomplete`，opened=false；修正拓扑为获准已有 ID，
  同一 run 下一 tick gate 实际 open，完整 Protocol scope 交接成功，无新 run 或创建 POST。
- 已获准创建但响应丢失时，gate 返回同样可观察反馈，opened=false；同一 run 下一 tick
  仍进入检查，但原 unknown receipt 使创建不重放，总计仅一次创建 POST。

专项命令 `pytest ../modeling_team/tests/test_r4029_independent_acceptance.py -k actual_topology_gate -q`
为 **2 passed，40 deselected，0.83 秒**。完整独立文件与既有 gate 接线必要回归为
**59 passed，1.68 秒**，Ruff 通过；无产品失败。

实现随后精确区分创建写前 401/403/404/422 拒绝与 unknown response，独立补充首 POST
422、下一 POST 201 的同请求用例：第一次明确没有新增资源、receipt=rejected，下一次
允许修正重试并取得实际新身份；不能永久阻断。unknown 创建禁重放用例仍通过。

最终执行（backend 工作目录）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4029_independent_acceptance.py ../modeling_team/tests/test_r30002_runner_wiring.py -q
uv run ruff check ../modeling_team/tests/test_r4029_independent_acceptance.py
```

结果：**60 passed，1.72 秒；Ruff All checks passed**（独立文件 43 项、既有 gate 回归 17 项）。
A6/A8 PASS，无 REGRESSION；A11 与 001 生产存储仍未验收。
主 agent 报告隔离默认实网 Jev 后后端全量 1052 passed/56 skipped；该证据由主 agent 持有，
不计入本轮独立执行。以下为本轮受影响输入摘要，前轮失败与摘要保留：

| 文件 | SHA-256 |
| --- | --- |
| `modeling_team/runner.py` | `4dbc929f167d98fba3eb51615e58a13863eb5e5854cd0eab67900e332cad220a` |
| `modeling_team/platform_scope.py` | `eeeab330e2836679a57094559ea965e90564298e27e6ad1fc01ad64abda4ab96` |
| `modeling_team/tests/test_r4029_independent_acceptance.py` | `26e3cfd4ef9ae05218ba5323039c4b0a0f35e1e7c0548520e1251fc3e38a799d` |
