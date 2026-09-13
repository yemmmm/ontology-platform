# R3.0-014 物化计划先 dry-run 后翻译审阅 — 共享测试计划

- 日期：2026-09-13
- 状态：设计评审 D1=REVISE、D2=PASS，三项 accepted-high 已闭合；产品测试、真实 L0/L1 和语义验收均为 NOT RUN。
- 需求：[requirements-v3.0.md 的 R3.0-014](../../requirements/requirements-v3.0.md#r30-014-物化计划先-dry-run-后翻译审阅)
- 设计：[R3.0-014 交付设计](../designs/2026-09-13-r3-0-014-dry-run-before-translation-review-design.md)
- 历史统计：[近轮审阅与 dry-run 失败统计](../records/2026-09-13-modeling-review-failure-statistics.md)

本文件是本需求唯一共享测试计划。后续开发机械轮、独立测试轮和真实验收轮都追加在这里，不新建
并行测试计划，不删除失败记录。

## 1. 测试目标与非目标

验证 009 staged Team 的顺序增量：业务语义批准后，Protocol 先把最终待转发内容送真实平台
`dry_run`，根据真实 Attempt 结果修正技术问题，再由 Coordinator 审阅最终翻译计划，最后以同一
内容 `apply_atomic`。验证 platform receipt、Attempt status、Batch content hash、workspace
version 和重试 key 的边界；验证 dry-run 的元数据持久化不被误报为正式模型写入。

不以 mock 的 `ok=true`、Batch/receipt 数量、文档检查、旧运行摘要或单纯单元测试证明语义模型质量；
不在本轮启动真实建模或写平台资源。

## 2. 设计评审记录

| 轮次 | 角色/范围 | 结果 | 证据 |
| --- | --- | --- | --- |
| D0 | planner 写稿和主代理文档核对 | 已执行，不是独立验收 | 需求、源码定位、链接和格式核对 |
| D1 | 2026-09-13，独立 `plan_reviewer`，初稿工作树 | REVISE | 以下三项 accepted-high；主代理补充合同及 M8/M28/M29 后复审 |
| D2 | 2026-09-13，独立 `plan_reviewer`，D1 修订稿 | PASS | 三项 High 均闭合；未发现仍阻断实施的 Critical/High。既有 Batch 读回、Runner host proof 与身份绑定可实施 |

D1 问题处置（保留原失败轮）：

1. **accepted-high**：内容变化后未写清新 client_batch_id 恢复正例；后端同 ID 不可变内容会
   `batch_content_conflict`，现有 Protocol 不会随 plan revision 自动改 ID。设计 §3.3 已明确
   新 ID/新 key/新 projection、旧证据保留及既有交接关联；M8 覆盖成功修复。
2. **accepted-high**：mode 分支未落实审批 artifact 的选择范围，可能让旧/拒绝 translation
   阻断 dry-run，或误跳过业务批准。设计 §3.3 明确分支、当前决定与历史处理；M28 覆盖组合。
3. **accepted-high**：apply 缺当前 Coordinator 身份绑定。009 已有该所有权要求但代码只做
   非空字段检查，设计 §3.3 已绑定本 run 当前 role ID/所有权，M29 覆盖错误身份。

非 High 的接口选择建议已收敛：固定既有 get_modeling_batch 读回，Runner 在现有 host evidence
追加 proof；operation-plan hash 仅作诊断，不要求扩展 backend response 或旧 receipt schema。

独立评审必须检查：无 translation approval 的 dry-run 路径、真实 Attempt proof、Batch 不可变/重试、
workspace 漂移、dry-run 元数据与正式写入边界、旧 schema/hidden 隔离。评审未完成前不得把设计标记
为通过或进入实现完成门。

## 3. 测试数据和证据边界

- 使用独立临时 run root、固定 009 Task/Profile、明确的 candidate revision、plan revision、
  projection digest、client batch 和 workspace version；不修改或覆盖历史 run。
- 机械测试可使用后端 fixture，但必须断言真实 response 的 `attempt_id`、`attempt_status`、
  findings、content hash 和 workspace 字段，而不是只断言 capability `ok`。
- 真实 L0/L1 必须使用用户新授权和真实平台/模型；不复用旧授权、旧 receipt 或历史 dry-run
  作为成功证明。成功和失败 Attempt、intent/receipt、unknown、修订和 cleanup 证据均保留。
- Coordinator 可见候选、计划、批准和平台 findings；隐藏题答案、tester-only 真值、参考答案包和
  隐藏材料不得进入 Modeling/Protocol/翻译审阅上下文。翻译审阅不是新增 Reviewer Agent。

## 4. 机械合同用例（实现后执行）

| ID | 场景 | 预期 |
| --- | --- | --- |
| M1 | 合法 009 batch，无 translation approval，具备 candidate/decision/plan/value unlock，调用 `dry_run` | 得到真实平台 Attempt 和 findings；允许 `validated` 或 `validation_failed`，不要求翻译 approval；不写正式 Modeling 资源 |
| M2 | 同一条件直接 `apply_atomic` | 类型化拒绝；无新的正式模型写入或 apply Attempt |
| M3 | dry-run 返回 `attempt_status=validated`，但 staged capability 只返回 `ok=true`/receipt | 不得进入翻译审阅或 apply；缺平台 proof 必须失败闭合 |
| M4 | dry-run 返回 `validation_failed`，包含可定位技术 finding | Protocol 能在同一 run 修正并以新 idempotency key 重跑；失败 Attempt/Batch 元数据保留 |
| M5 | dry-run 返回 unknown、只有 batch identity 或 response 截断 | intent 进入现有 unknown 对账/写门；不得盲重试或把 receipt 当 validated |
| M6 | 真实 validated dry-run 后，Coordinator translation approval 精确匹配 `plan_ref`+`projection_digest` | apply gate 可继续；approval 由当前 approvals artifact 读取并绑定，不仅做形状校验 |
| M7 | translation approval 缺失、rejected、旧 plan_ref、旧 projection_digest 或不对应当前 candidate | apply 类型化拒绝；无平台正式写入 |
| M8 | 技术修正改变默认值/依赖/命令 payload，但候选业务含义不变 | 新 plan revision 显式使用新 client_batch_id、新 projection digest 和 dry/apply key；实际重跑通过并可 apply；旧 Batch/Attempt/receipt 与已有交接中的替代关系保留，只审最终计划、不重做业务批准 |
| M9 | dry-run 修正改变业务含义、候选、拓扑、共性关系或值表达 | 回到责任 Agent 确认并发布新候选/决定；受影响翻译不能沿用 |
| M10 | apply 使用与 proof 相同的实际 item projection/content hash，但新的 apply idempotency key | 允许进入平台 apply；记录 apply Attempt，回读证明正式资源状态 |
| M11 | apply 重用 dry-run idempotency key | 按现有请求/Attempt 语义拒绝或返回同一 dry-run Attempt；不得把它视为 apply 成功 |
| M12 | 改命令 payload、依赖、evidence、rationale 或 CQ IDs 后沿用 client_batch_id | 后端 `batch_content_conflict`；不得借新 key或 receipt覆盖不可变 Batch |
| M13 | 仅改变 mode、lease、idempotency key 或 expected workspace version | content hash 不变；execution parameters 不进 plan projection digest；apply 仍需新的 key和当前租约 |
| M14 | Batch items 输入顺序变化但规范化内容相同 | 后端 content hash 稳定；projection 按合同比较；不产生虚假漂移 |
| M15 | plan_ref、projection 或 candidate 文件在 dry-run 后被改写/替换/软链逃逸 | plan/candidate close 返回 typed mismatch/stale；旧 approval/proof 不放行 |
| M16 | workspace 在 dry-run 成功后、translation approval 后发生漂移 | apply 拒绝；同一内容需新的 dry-run Attempt；不能以旧 proof继续 |
| M17 | dry-run 后读取 Batch/Attempt 明确“无正式资源”，但 DB 有 Batch/Attempt/findings/operation plan | 报告为 validated/failed dry-run metadata，不报告 applied/materialized；正式资源和 Evidence association均为空 |
| M18 | dry-run findings 含 evidence candidates 或 safe operation-plan evidence | 可保留/读取必要校验信息；不创建 EvidenceReference/Association，不把候选证据当正式 lineage |
| M19 | 值语义命令缺 unlock、unlock mode=skip、结论/trace 不匹配 | dry-run 和 apply 均在平台转发前拒绝；顺序调整不绕过 value semantic gate |
| M20 | 无候选批准、无 scope/ontology 授权、CQ freeze pending、未知 intent pending | 分别返回现有 typed gate；不得以“先 dry-run”泛化放开更高层安全门 |
| M21 | 008B 普通 staged run、未启用 unified selector、普通产品 submit | 继续旧审批/入口/receipt 行为；不要求 R3.0-014 translation approval 或 proof schema |
| M22 | 历史 008B/009 intent、receipt、candidate 和 plan 读取 | 按记录 schema 验证；不 retro-fit R3.0-014 字段，不被新流程静默重写 |
| M23 | successful dry-run response 的 `attempt_status` 被伪造、遗漏或与 `mode` 不一致 | forwarder/Runner 拒绝为 proof；`ok=true` 不足以放行 |
| M24 | response 的 batch_id、attempt_id、idempotency_key、content_hash 彼此不一致 | 记录 platform-contract failure；不写翻译批准、不 apply；原始响应保留 |
| M25 | apply 前或 apply 后发生 forwarder timeout/异常，无法知道平台是否提交 | 进入现有 unknown reconciliation；保留 intent/receipt/Attempt listing；禁止 retry 直到闭合 |
| M26 | 旧失败 Attempt 后新 Attempt 成功 | 旧 findings/response/receipt 保留；只把新 Attempt 作为当前 proof，不以最终成功覆盖失败事实 |
| M27 | 同一 plan 发生并发 dry-run/apply 或 write admission quiescing | 现有 admission/lease/fence 保持原子性；无双写、无跨 key receipt 混用；可恢复反馈可继续 |
| M28 | dry-run/apply × translation 为空/旧版/rejected/格式问题/当前 approved × 业务决定完整/缺失 | dry-run 不受 translation 状态影响但缺业务决定拒绝；apply 只接受当前唯一有效 approved，不接受冲突/重复；旧历史保留、不以全量 translation 校验阻塞技术修正 |
| M29 | 匹配 plan/hash 的 approval，但 approved_by 是错误角色、旧 Coordinator、外 run；对照当前 Coordinator-owned 决定 | 前三者 apply 拒绝，当前本 run Coordinator 及内容/proof 全部匹配才放行；不引入额外角色审批门 |

## 5. 独立测试和真实验收用例（实现稳定后执行）

### 5.1 L0 平台流程和交付安全

| ID | 场景 | 必须观察 |
| --- | --- | --- |
| L0-1 | 新授权的 009 run 走完整 dry-run → proof → translation approval → apply | run、Task/Profile、candidate/plan revision、Attempt、proof、approval、apply receipt和清理证据闭合 |
| L0-2 | dry-run 技术失败后同 run 修正、重跑，最终只审最终计划 | 失败 Attempt 不被抹除；Coordinator 没有审阅已废弃的中间计划 |
| L0-3 | dry-run validated 后 apply 使用同一内容、新 key和当前 lease | platform Batch content hash 与 plan projection/commands一致；正式写入可读回且原子 |
| L0-4 | workspace drift、过期 approval、伪造 response digest、改写 plan 文件 | apply 不放行；failure layer 是平台/协作合同，不归因模型质量 |
| L0-5 | dry-run response/平台 listing 不可用或 dispatch timeout | unknown intent、kill-switch、对账和停止路径可观察；无盲 retry、无继续写 |
| L0-6 | 用户 stop、child teardown、后续重试 | 已写资源、Attempt、receipt、失败证据和 cleanup 状态保留；不追加 semantic start |

### 5.2 L1 语义翻译质量和隔离

| ID | 场景 | 必须观察 |
| --- | --- | --- |
| L1-1 | 平台技术合法、Coordinator 审阅最终翻译忠实表达 | Coordinator 只能批准与当前 plan/projection 相符的内容；过多/漏项/限定含义错误可退回 |
| L1-2 | 技术修正后最终计划业务语义未变 | 只审最终 plan；不把每次平台 finding 误计为一次语义审阅失败 |
| L1-3 | 技术合法但翻译错误 | translation approval 被退回，发布新 plan revision 并重新 dry-run；apply 不发生 |
| L1-4 | dry-run findings 暴露候选业务含义缺口 | 交责任 Agent 修正业务候选/决定；不由 Protocol 擅自改变语义，也不把它算作平台技术失败 |
| L1-5 | Coordinator/Protocol/Modeling 接触 hidden acceptance answers 或 tester-only material | 隔离违规；不产生有效语义验收证据，hidden 内容不得进入普通运行上下文 |
| L1-6 | 成功 apply 后独立读取/检索/证据验收 | 只能由独立验收给模型质量结论；dry-run validated、translation approval 或 receipt不替代 L1 |

## 6. 失败归因和报告格式

每个失败保留第一阻塞层和原始证据，使用既有四类：`modeling-quality`、`platform-contract`、
`collaboration/routing`、`runtime/infrastructure`。题目/参考材料问题单列为 `question-answer-review`，
不是第五种失败层。必须区分：

- 业务候选/语义批准退回；
- 平台 dry-run `validation_failed`；
- translation approval 退回；
- Runner schema/permission/admission 拒绝；
- forwarder/平台 unknown；
- apply 后真实资源/回读缺陷。

报告至少记录 run、代码基线、Task/Profile、mode、Batch/Attempt、intent/receipt、plan/candidate
revision、projection/content/response digest、workspace 前后版本、failure layer、finding code、
是否发生正式写入、修复/重试关系和证据路径。不得把 rejected candidate、revision 数、receipt 数或
`ok=true` 数直接当成失败轮数。历史审阅失败的已确认统计只引用共享统计报告。

## 7. 执行顺序、清理和完成门

### 7.1 后续执行顺序

1. 独立设计评审，处理每个 Critical/High 后再冻结设计。
2. 开发机械测试：先跑 changed-scope contract tests，再按仓库要求运行 backend/modeling tests；不
   以这些结果代替真实语义验收。
3. 独立 requirement tester 复核实现和本计划，追加独立机械轮；失败回开发修复，再在本文件追加
   新轮次，保留旧轮次。
4. 在新的用户授权下执行真实 L0，随后独立语义 L1；记录真实 platform Attempt 和 readback。
5. 最后同步需求状态、设计/计划记录和运行证据；本需求未通过独立 PASS 前不得标记 complete。

后续实现验证命令（本次均未执行）：仓库根目录使用
`env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest -q modeling_team/tests/`；
若改动 backend，另执行 `cd backend && uv run pytest`，并遵循 AGENTS.md 的服务重启和健康检查。
只改文档/提示时执行对应链接、格式和合同检查，不因此重启服务或启动真实运行。

### 7.2 清理

- 只清理本轮可证明归属的 child、socket、临时 key 和测试数据；Batch/Attempt、intent/receipt、
  dry-run findings、unknown/失败报告和审计证据必须保留。
- 不覆盖既有 report、receipt、plan 或 candidate；相同路径存在时类型化拒绝，改用新的 attempt/run
  目录或在同一 run 追加不可变记录。
- 如果 unknown 或正式写入归属不能证明，跳过删除并记录 BLOCKED/未清理原因。

### 7.3 完成门

| 阶段 | 完成条件 | 当前状态 |
| --- | --- | --- |
| 设计 | 权威需求、设计、共享计划一致；独立评审无未处置 Critical/High | PASS（D2，仅设计） |
| 机械实现验收 | M1-M29 中适用项通过，旧模式和 hidden 隔离回归通过 | NOT RUN |
| L0 Runtime | 真实平台 dry-run/proof/apply/unknown/cleanup 闭合 | NOT RUN |
| L1 Modeling quality | 独立语义翻译和模型质量证据通过；失败不被平台状态洗绿 | NOT RUN |
| 完成 | 以上门槛、需求状态同步、独立 PASS 和安全清理均完成 | NOT RUN |

本轮仅交付需求、设计、测试计划和统计文档；没有执行上述任何产品或真实运行用例。

### 7.4 本轮文档交付检查

- 主代理交付四文件：权威需求增量、设计、本共享计划、历史统计；未修改产品或运行代码。
- 相对 Markdown 链接存在性、代码围栏配对检查：4 文件，0 问题。
- `git diff --cached --check`：PASS，0 格式错误。
- GitNexus `detect_changes(scope=staged)`：四文件、LOW、无受影响执行流程；不代表语义验收。
- 历史统计复查：112 completed staged submit = 112 唯一调用；12 唯一失败 Attempt，
  六轮分别 2/3/0/3/0/4；阶段未到达不作为零失败样本进入均值。
- 不运行后端/前端测试、不重启服务、不启动 semantic start：此次为文档设计交付，非代码实现。
