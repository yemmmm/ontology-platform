# R2.3-006 精简隔离 Examiner Runtime 设计

- 状态：Implemented；真实 N=2 `BLOCKED/runtime-budget`，prompt 修复待新 operation authorization 复验
- 权威需求：`docs/requirements/requirements-v2.3.md#r23-006-精简隔离-examiner-runtime`
- 交付记录：`docs/delivery/records/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-delivery-record.md`
- 共享测试计划：`docs/delivery/test-plans/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-test-plan.md`

## 1. 目标

把 formal semantic Acceptance 的每题执行收敛为三个真正隔离的判断面：Source Examiner 只看 source，
Platform Examiner 只看当前平台事实，Acceptance 只看两份 typed report。消除主线程历史继承、Agent 横向补问、
主 Agent人工转发平台结果和 13–17 轮模型调用，同时保持 source fidelity、model binding 和 independent verdict。

## 2. 当前证据与判断

R2.3-003 start20-2 中，Platform read-model HTTP 请求各约 1 秒，查询数据已包含回答 CQ 所需实体、事实和链路；
主要延迟来自约 26k–33k 的每轮输入上下文、重复调用和协作等待。因此当前最小改动是 role runtime/transport，
不是 backend read API。API 改进是后置、证据触发的选项。

## 3. 功能设计

### 3.1 Host-owned role packet

Host 为每题生成三个不可变输入：

- Source packet：question、ordinal/count、approved source path+digest+bytes、report schema；
- Platform packet：question、ordinal/count、P/O/G/workspace/model digest、proxy capability、exact request/report
  schema；
- Acceptance packet：ticket/standard binding、当前题两份 report+digest、ordinal/count、verdict schema。

每个 packet 记录 canonical digest、字段清单和 token 计数。运行实例不得继承主线程 turns；不可移除的系统/安全
prefix 单独计量，不混入 host packet 指标。

### 3.2 Role-private execution and transport

Source/Platform/Acceptance 全部每题 fresh；不复用现有 persistent Acceptance thread。Host 只在前题 typed PASS
且两个 child 已清理后机械推进 ordinal，不把前题 report/verdict 投影给下一题 Agent。正式实现使用 Runner-owned
fresh Codex thread/process，不使用本次对话的 collaboration subagent。运行时不向 Examiner 暴露 team-wide
collaboration tool；若底层无法移除该工具，Host transport 只允许 terminal typed output 回给 owner，其他
recipient 在发送前拒绝并记录证据。

输入不完整时，Agent只能返回 typed BLOCKED，不能询问主 Agent或同级角色。该规则由 packet validator、tool/
transport allowlist 和回归测试共同证明，不能只靠 prompt。

### 3.3 Direct strict read proxy

Platform Examiner 直接获得 operation-local proxy capability。proxy 持有唯一临时 Project read key，机械校验
tool/method/path/body/P/O/G，在 backend 前拒绝越界，并把 structured response、request digest、response digest
作为单次 tool result 返回。主 Agent不读取后转述，也不补充 digest。Examiner 不获得 plaintext key。

当前 `ScopedReadProxy` + `McpReadForwarder` 的 broad schema-property filtering 不能作为实现：R2.3-006 wrapper
必须为每个允许 tool 冻结 exact JSON argument schema，在 forwarder/session/backend 前拒绝 unknown/missing/
wrong-type 字段并记录 `backend_calls=0`。无需修改 backend API。

### 3.4 Turns and metrics

正常 Source/Platform/Acceptance 路径最多 3 个可观测 inference steps：理解/发起读取、消费证据并调用 typed
report tool、provider terminal completion。预装 source bytes 的 Source 和预装 reports 的 Acceptance 可以更早提交；
Platform 必须把所有独立 read calls 合并到首个 parallel tool wave，下一 inference 提交 typed report。首轮出现
cursor/truncation/incomplete/missing fact 时保留 completeness/unknown/gap，不发起第二 retrieval wave。
Runner operation 为每个 child 记录独立 `ExaminerRunMetrics/v1`：fresh thread identity、Host 发出的 canonical
`first_turn_input` 字段清单/digest、`turn/start` 次数、每个 cumulative token-usage（或 provider 等价精确事件）
增量、first/total/cached/task/evidence/output/reasoning tokens、TTFT、terminal wall time、proxy time 和拒绝次数。

实施前先用真实 Codex App Server 最小探针确认 token-usage notification 的 method、字段与触发粒度；不能确认则
该性能门 BLOCKED，不用累计 session 账单估算代替。Host 在第 4 个 inference step 前 interrupt/terminate child，
返回 `BLOCKED/runtime-budget`。首轮 context 证明同时绑定 fresh `thread/start`（不 resume）、唯一 `turn/start` 的
serialized input 与禁止 marker；`fork_turns=none` 声明本身不算证据。

墙钟目标为通常不超过 60 秒、单个不超过 90 秒。外部 provider 故障单独分类；不能通过增加横向询问或放松
隔离绕过。超过目标但满足正确性时仍需记录性能 FAIL/BLOCKED disposition，不得静默算 PASS。

## 4. 当前最小范围与非目标

当前只实现 formal semantic Acceptance Examiner runtime，复用 R2.3-003 operation-local proxy/envelope；不改
backend、Modeling/Protocol 语义、全局 Codex 指令或所有 subagent。只有精简执行后证据表明 generic retrieval 不足，
才单独提出通用查询改进；不添加 Dify/CQ 专属接口。

## 5. 错误与停止

- packet 字段或 binding 缺失：`BLOCKED/acceptance-input`；
- source bytes/digest 不可用：`BLOCKED/source-missing`；
- proxy/backend 读取失败：`BLOCKED/platform`；
- 横向协作或未授权 tool：发送前拒绝并使该 Examiner round BLOCKED；
- typed report schema/digest 不合法：Acceptance 不裁决语义，返回 `BLOCKED/acceptance-evidence`。

所有分支必须撤钥、终止 child、保持 model/ledger 不变；失败不触发 semantic start 或自动重试建模。

## 6. 验收与发布

先用 R2.3-003 final workspace 做只读 N=2 实证，再做 N=1/3/5 机械投影和 R2.3-005/default 隔离回归。
完成要求同时满足输入隔离、直接 proxy、最多 3 turns、typed verdict、性能记录、撤钥/清理和独立 tester PASS。
本需求是 current-minimal local runtime 改进，不宣称 L3 productization。

## 7. 未来演进

未来可把已证明的 role packet/transport 机制复用于 Pi Adapter 或其他 formal acceptance；跨机器调度、策略中心、
长期审计和通用 Agent sandbox 另立需求，当前不实现。

## 8. 实施与真实验证结果（2026-08-12）

- 已实现 per-CQ fresh Source/Platform/Acceptance child、inline immutable packets、report-only transport、
  exact-schema direct proxy、typed report/evidence binding、ordered aggregation、完整 metrics 与 callable retained
  operation；R2.3-005/default 路径保持兼容。最新 deterministic 独立测试为 full modeling_team 540 PASS、1 SKIP。
- 首次授权真实 operation 在 CQ-001 Platform 第四个 positive App Server usage increment 到达前正确返回
  `BLOCKED/runtime-budget`。修复 Platform prompt/Skill 后，下一次授权 operation 确认首轮单一并行 read wave，
  但 Platform child 在约 90 秒 watchdog 到期时仍未 terminal completion，最终为
  `BLOCKED/runtime-infrastructure`，底层安全 reason 为 `runtime/child-timeout`；没有 ordered N=2 verdict，
  因此不能宣称本需求 semantic PASS。
- 两次 operation 的 read key 都完成 exactly-once create/revoke/readback/old-key 401，bootstrap admin 撤销，
  model/ledger/live inventory 不变，output/process/socket/secret 零残留；独立 failure-path audit PASS。第二次运行
  暴露 outer operation 丢失 typed reason 且不保留失败 evidence 的 P1，现已在 cleanup、key lifecycle、invariance
  全部成立后写入 `0600`、明确 `BLOCKED` 的安全证据；secret、未知/错误类型 evidence 或不完整 cleanup 继续
  fail-closed 且不落盘。Round 12 deterministic observability 独立 PASS。
- 不根据单次 timeout 猜测或修改 timeout/provider/prompt；下一次真实 operation 必须另获授权，并直接保留完整
  failure/performance evidence。只有真实 N=2 得到六角色完整 metrics 与 ordered PASS 才能完成本需求；当前状态
  保持真实验收 `BLOCKED/runtime-infrastructure`。
