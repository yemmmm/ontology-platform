# v4 待解决问题公开回归验收记录

日期：2026-10-03。状态：`PASS`（有界公开回归）。G-04 已通过一次独立的 governed live
read 取得技术映射维护责任的模型定义，M-03 已满足 `ISSUE-V4-003` 的有界关闭依据。两题
均不形成 R4.0-009 L1、live E2E 或更高阶段的结论。

本记录用于独立核对 `ISSUE-V4-002`（映射维护责任遗漏）与 `ISSUE-V4-003`（关闭请求结果
与工单状态解释混淆）的公开回归。回归使用修改后的 Platform Examiner 真实 runtime，重放
原验收保留的公开平台响应；它不是原隐藏题的重新判题，也不改写第四轮报告。

## 范围与证据边界

获准业务依据为本轮新增公开补充资料：

- [approved-business-supplement-v1](../../../workspaces/v4-acceptance-20261002/approved-business-supplement-v1.md)
- [approved-business-supplement-v2](../../../workspaces/v4-acceptance-20261002/approved-business-supplement-v2.md)

角色合同为当前通用的 [Platform Examiner package](../../../modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md)
与实际装载的 [v3-acceptance-batch Skill](../../../modeling_team/skills/v3-acceptance-batch/SKILL.md)。
它要求答案先给直接结论，区分 transport/API response、request/action result 与业务对象状态，
并分开业务维护、数据库/API 映射维护和平台授权；这些是通用作答合同，不是预置答案。两次
成功重放的 [G-04 runtime contract hash](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/g04-retry2/runtime-contract-hashes.json)
与 [M-03 runtime contract hash](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/m03-retry2/runtime-contract-hashes.json)
均记录了 prompt 与 Skill 的 mounted/repository `byte_equal=true`；装载的 Skill SHA-256 为
`f4dd45cee0dff8ac8397723992cf941a9ecc325cf301815956eb9e2117b52855`。

当前 replay 实际使用的 producer response artifacts 是：

- G-04：[10.json](../../../workspaces/modeling-runs/r4009-20261003-solmedium-auth01-start4c/acceptance/r3011-cq-batch-0001/platform-read/d30a2dd409f8d398e7b7374c8f93e1d71ad38731e9e27c442768e77fe93bc66d/10.json)
  与 [11.json](../../../workspaces/modeling-runs/r4009-20261003-solmedium-auth01-start4c/acceptance/r3011-cq-batch-0001/platform-read/d30a2dd409f8d398e7b7374c8f93e1d71ad38731e9e27c442768e77fe93bc66d/11.json)；
- M-03：[12.json](../../../workspaces/modeling-runs/r4009-20261003-solmedium-auth01-start4c/acceptance/r3011-cq-batch-0001/platform-read/d30a2dd409f8d398e7b7374c8f93e1d71ad38731e9e27c442768e77fe93bc66d/12.json)。

G-04 Round 3 使用独立 live read 产生的 [live-read-summary](../../../workspaces/v4-acceptance-20261002/public-consumer-live-20261003/g04-root-read-retry1/live-read-summary.json)
及 11 个 receipt-backed response；关键角色定义见 [response p3](../../../workspaces/v4-acceptance-20261002/public-consumer-live-20261003/g04-root-read-retry1/acceptance/r3011-g04-live-root-read-20261003-retry1/platform-read/93d99e25621fe15ed04adc54cc5c23c73bbe44a3fd054639bcce84c0395f3340/3.json)，映射和调用边界见 [response p10](../../../workspaces/v4-acceptance-20261002/public-consumer-live-20261003/g04-root-read-retry1/acceptance/r3011-g04-live-root-read-20261003-retry1/platform-read/93d99e25621fe15ed04adc54cc5c23c73bbe44a3fd054639bcce84c0395f3340/10.json)。

旧 [retention manifest](../../../workspaces/v4-acceptance-20261002/cq-failed-cli-0001-retained/manifest.json)
只用于说明公开保留边界；本轮不把旧 CLI 失败目录当作当前 replay 的 source path。保留响应只
作为新的公开题目读取证据。不得读取、复制或引用原隐藏 expected answer、原 Judge 裁决或原
`batch-report.json` 作为本轮答案依据；原始响应字节、原失败日志、原报告及 producer run 均
保持不变。本轮不创建、继续或修复被验收 producer run，不写语义模型资源，不在线调用外部
API／SQL／脚本。

## 公开回归题目

| 题目 | Consumer 题干 | 验收方公开依据（不随题干下发） | 当前状态 |
| --- | --- | --- | --- |
| `public-g04-responsibility-v1` | 共享“提交关闭请求”合同发生变更后，业务／流程和技术映射各由谁负责，重审应覆盖哪些关联，平台权限有什么边界？ | supplement v2：核对业务维护者、技术数据库/API 映射维护者、受影响引用重审范围及平台授权边界；这些判据只供验收方读取 | `PASS`（Round 3 live，ISSUE-V4-002 有界关闭依据）：两类维护责任均有模型定义支持；已知引用、未发现引用和实际授权均保留边界 |
| `public-m03-status-separation-v1` | 提交关闭请求返回 202/accepted，另一次返回 204；应查询哪个对象／接口、按什么结果判断请求成功，这与工单状态有什么区别？ | supplement v1：核对请求进度对象／接口、成功判据、空响应含义及其与工单状态的分离；具体字段判据只供验收方读取 | `PASS`（仅 ISSUE-V4-003 有界关闭依据）：答案正确分开三层并保留响应未返回的精确路径、工单字段和实际执行状态为 `unknown` |

## 独立判定规则

收到 answer path 后，验收方只读取该 answer、真实 replay response 及上述公开资料，逐题记录：

1. 直接结论是否回答题目要求，并指向正确对象、字段、版本或操作；
2. 是否把业务／流程维护、技术映射维护和平台授权混为一谈，或把未发现引用说成全覆盖；
3. 是否把 HTTP 受理、关闭请求状态和工单状态混为一个状态，或把无正文响应当作成功证明；
4. 每项结论对应的真实 response handle／read evidence 与公开资料；资料或响应不足时保留
   `unknown`，不以缺少一次命中推断模型缺失；
5. replay/runtime、查询获得、Consumer 作答和题目自身问题分别记录，不用公开回归结果
   改判原始隐藏报告。

逐题结果按 `PASS`、`PARTIAL`、`REVISE` 或 `BLOCKED` 记录。`PASS` 允许答案把响应未提供的
事实明确标为 `unknown`；这表示该题的有界解释正确，不表示模型已覆盖所有业务事实或已
证明真实接口在线。两题均有真实 answer/replay 证据且没有未闭合范围，才可给这项公开回归
整体结论；当前两题的未知项均已由响应或验收依据明确界定，故本次有界公开回归为 `PASS`。

## 逐题独立核对

### G-04／ISSUE-V4-002

Round 2 的 [Consumer answer](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/g04-retry2/consumer-answer.json)
有 1 个 report、4 次 replayed read，teardown 六项均为 true，runtime error 为空。
答案正确指出 `service-supervisor` 的业务／流程维护、合同版本和已知调用重审边界，也明确
当前没有从返回内容确认技术数据库/API 映射维护责任人、确切 Operation/bindingId 和具体
平台权限。其 `evidence_refs` 为 `p0`–`p3`，对应本轮四个 replay response；例如首个输出见
[G-04 response 0](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/g04-retry2/acceptance/r3011-consumer-replay-g04-retry2-20261003/platform-read/ede07fb7f5efd180240276b429dc8f3624de63a60a5b859a7f71b524c7fd5434/0.json)。

独立结论为 `PARTIAL`。当前 source `10.json` 与 `11.json` 的实际返回内容没有给出 integration／
database/API mapping maintainer 的定义，Consumer 没有把业务主管角色代推为技术维护责任人，
这一点作答是诚实的；但 `ISSUE-V4-002` 的关闭依据要求取得有依据的映射维护责任，故不能
把本轮结果记为 prompt-contract 通过或问题关闭。后续若继续查询，必须沿正常授权的 governed
read 定位已有独立技术责任定义；不能从 supplement 或题干补编业务事实。

Round 3 使用 [G-04 live Consumer answer](../../../workspaces/v4-acceptance-20261002/public-consumer-live-20261003/g04-root-read-retry1/consumer-answer.json)
与 [proxy environment evidence](../../../workspaces/v4-acceptance-20261002/public-consumer-live-20261003/g04-root-read-retry1/proxy-env-presence.json)。
输入只包含公开题干、获准 Project/Ontology scope 和真实语义 read tools；child descriptor 标记
`can_write=false`，没有向 Consumer 提供 source artifacts、角色名、补充资料或隐藏答案。
运行终态为 `completed`，报告 1 个，receipt-backed read 11 个，`schema_rejections=0`，
`writes_attempted=false`，`semantic_start_consumed=0`，teardown 六项均为 true。

这次 read 的 p3 明确返回模型定义 `integration-maintainer`：
“Technical maintenance of database/API mappings, not business-contract confirmation.” 同一批
evidence 的 p3 也返回 `service-supervisor`，其定义是关闭审核、共享关闭请求含义／必填合同确认
及服务流程业务维护。p0/p3/p4/p10 支持新增必填参数的合同变化、已知原始／新调用和
`close-confirmation-map`；模型明确未发现引用、目标特定确认来源完整性和实际授权配置仍属
`unknown`。p3 的 response digest 为
`b383bf39479339160f53621c107f0909d9c089d5a88d84b36c7d7e17b6a1ac88`，p10 的 response digest
为 `9740cb9ab8f837dfc60be1b11f1d8bc85a502f3429c0ff34948b5bb106fb686e`。这些事实与 approved
supplement v2 的职责约定一致，Consumer 没有把 supplement 内容当作答案输入。

权限证据只证明本次 read 的 project-scoped API key：创建 `201`，scope 为 `[read]`，撤销
`200`，readback 显示 revoked，旧 key 后续访问 `401`；admin key 也已 revoked。运行主体的
有效范围包含 `admin/model/read`，因此本次不是普通 finance 权限的复测，不能从它推出普通
主体或数据库行列权限；proxy evidence 同时确认 parent/child 的六个 proxy 环境变量均存在，
但刻意不记录值。答案正确把实际 grant 归 Host 管理并保留外部数据库权限未知。

11 个 receipt 的 `model_state_digest` 均为
`sha256:932d83697e524cea30e1f71409886d1f3e78510fb53dab11f91f6c753c2dd14e`，graph set 与
ontology 也一致，支持本次读取期间使用同一绑定 workspace state。summary 没有独立的前后
workspace snapshot，因此不能据此证明完整的前后无漂移，只能确认 receipt 范围内的 model
state 未变。

Round 3 的独立结论为 `PASS`（仅 `ISSUE-V4-002` 的有界关闭依据）。技术映射维护责任已由
p3 的模型定义直接支撑，业务维护、已知引用重审和权限边界均有对应 read evidence，明确未知
仍被保留；这不改变 Round 2 的 `PARTIAL` 历史记录，也不构成 prompt 或全量 L1 通过。

### M-03／ISSUE-V4-003

Round 1 的 [G-04 answer](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/g04-retry1/consumer-answer.json)
与 [M-03 answer](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/m03-retry1/consumer-answer.json)
均为 runtime `BLOCKED`：实际失败链是 provider `responseStreamDisconnected`，随后 workspace
routing discovery timeout／`systemError`，最终 child-exited；reports/replayed_reads 均为 0，
且 `provider-error-terminal` 标记 `will_retry=false`。answer JSON 的 wrapper
`error.message=binding-rejected` 只是通用包装字段，不能证明 sink 或 MCP binding 被拒绝；本轮
没有发现这种 binding failure。两次均无 persistence failure，child、proxy、report sink、
private root、socket root 的 teardown 均完成；运行日志另记录了
`Falling back from WebSockets to HTTPS transport. workspace routing discovery timed out`。
这一轮只记 runtime `BLOCKED`，不作语义失败结论。

Round 2 的 [M-03 Consumer answer](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/m03-retry2/consumer-answer.json)
成功产生 1 个 report、2 次 replayed read，`error=null`、`persistence_failures=0`、
`live_modeling_start=false`，teardown 六项均为 true。真实 source artifact 是上面的 `12.json`
（SHA-256 `cf6a4361fbc5dc2d25569dfbca0b171abbc7be78aac19e914aa6db25cad3e7f4`）；两次 replay
响应的 response digest 均为 `c73586832e89c5cd9c2b059e72bf78adaddcced70a3e2b7a2d933eb03b771df4`，
对应 [response 0](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/m03-retry2/acceptance/r3011-consumer-replay-m03-retry2-20261003/platform-read/ac9dfb85952f03f08fcb9f4c0ca1e535815bf0b3d93be7330cb51841fc179f57/0.json)
和 [response 1](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/m03-retry2/acceptance/r3011-consumer-replay-m03-retry2-20261003/platform-read/ac9dfb85952f03f08fcb9f4c0ca1e535815bf0b3d93be7330cb51841fc179f57/1.json)。

答案正确区分：202／`accepted` 只表示关闭请求受理；`close-accepted` 的 request id 与
accepted status 不是关闭完成；204 的 `no-response-body` 不证明关闭成功；应读取
`close-request-response` 的 `request-status`，其中 `closed` 才是请求完成、`rejected` 为
业务拒绝；工单业务对象状态与请求进度不是同一层次。答案同时明确当前响应没有返回精确查询
接口路径、工单状态字段、同步保证或实际执行结果。

独立结论为 `PASS`（仅 `ISSUE-V4-003` 的有界关闭依据）。这满足“准确区分接口返回、请求结果
与业务对象状态，且结论有实际获准响应支撑”的关闭条件；响应未提供的精确路径和实际状态保留
为 `unknown`，不因缺少该字段重定义本 bug，也不把公开回放当作全题 L1 或真实执行 PASS。

## Replay 轮次

| Round | Runtime／输入 | 题目 | 真实 response／answer refs | 独立结论 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 1 | 修改后的 runtime；实际 producer source 10/11/12 | G-04、M-03 | `g04-retry1/consumer-answer.json`、`m03-retry1/consumer-answer.json`；responseStreamDisconnected → workspace routing timeout/systemError → child-exited，reports=0、replayed_reads=0 | 语义未判定 | `BLOCKED`（runtime-infrastructure） |
| 2 | v3-acceptance-batch Skill；prompt／Skill mounted 与 repository byte-equal | G-04 | [g04-retry2 answer](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/g04-retry2/consumer-answer.json)，4 reads、1 report | `PARTIAL`；技术映射维护责任未取得 | `PENDING` |
| 2 | v3-acceptance-batch Skill；prompt／Skill mounted 与 repository byte-equal | M-03 | [m03-retry2 answer](../../../workspaces/v4-acceptance-20261002/public-consumer-replay-20261003/m03-retry2/consumer-answer.json)，2 reads、1 report | `PASS`（ISSUE-V4-003 有界关闭依据） | `PASS`（不等于 L1/live E2E） |
| 3 | governed live read；Project/Ontology scope，11 receipt-backed reads，writes=false | G-04 | [live answer](../../../workspaces/v4-acceptance-20261002/public-consumer-live-20261003/g04-root-read-retry1/consumer-answer.json)、[live summary](../../../workspaces/v4-acceptance-20261002/public-consumer-live-20261003/g04-root-read-retry1/live-read-summary.json)；p3 返回 `integration-maintainer` 模型定义 | `PASS`（ISSUE-V4-002 有界关闭依据） | `PASS`（不等于 L1/live E2E） |

公开题已暴露，不恢复盲测属性；两题的有界 bug 关闭依据成立，也不自动证明 R4.0-009
L1、L2、L3 或 live E2E 整体 PASS。
