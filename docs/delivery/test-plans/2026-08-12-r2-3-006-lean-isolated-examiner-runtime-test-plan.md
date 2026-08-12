# R2.3-006 精简隔离 Examiner Runtime 共享测试计划

- 状态：reviewed / 待实施（plan review Round2 PASS）
- Requirement：`docs/requirements/requirements-v2.3.md#r23-006-精简隔离-examiner-runtime`
- Design：`docs/delivery/designs/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-design.md`
- Delivery record：`docs/delivery/records/2026-08-12-r2-3-006-lean-isolated-examiner-runtime-delivery-record.md`

## 1. 完成门

1. Source/Platform/Acceptance 每题 fresh instances 无主线程 turns；Acceptance 无 source/raw platform/main/前题历史。
2. 三类 role packet 字段、digest、token breakdown 可重算；host packet 不超过约定范围。
3. Platform 直接调用 strict proxy；无主 Agent人工转发，无 plaintext key。
4. 横向协作、缺输入、未知 tool/path/body/scope 在发送/backend 前 fail closed。
5. 每个 Examiner 正常最多 3 model turns；记录 TTFT、wall、proxy time 和 token breakdown。
6. R2.3-003 N=2 只读语义回归 PASS；N=1/3/5 顺序机械 PASS；R2.3-005/default 不变。
7. key exactly-once revoke/post-revoke denial，model/ledger 不变，零 process/socket/secret residue。
8. 独立 tester PASS；失败轮保留；需求/设计/记录/运行文档和提交同步。

## 2. 测试矩阵

### A. Packet 与上下文隔离

- A1 Source packet 只含当前 CQ、批准 source、binding 和 schema；注入 main-history marker 后 child 不可见。
- A2 Platform packet 只含 CQ、P/O/G/workspace/model digest、proxy/schema；不含 source/历史 verdict。
- A3 每题 fresh Acceptance packet 只含 ticket/standard、当前题两份 report+digest、ordinal 和 verdict schema；
  thread identity 不复用且 CQ2 输入不含 CQ1 report/verdict。
- A4 实际 first-call context inventory 证明 inherited conversation turns=0；system/safety、host packet、source/
  response token 分开计量。

### B. 路由与失败

- B1 Source→Platform、Platform→Source、Examiner→main/其他 Agent 的协作请求 pre-send 拒绝且留下 receipt。
- B2 删除 CQ、P/O/G、schema、digest 任一字段，Agent 不追问而返回准确 typed BLOCKED。
- B3 每个 wrapper exact schema 对 unknown/extra/missing/wrong-type tool/path/body/scope 均在 forwarder 前拒绝，
  `McpReadForwarder/session/backend_calls=0`；source missing 和 proxy failure 分类准确。
- B4 malformed report/digest 不进入 Acceptance 语义裁决。

### C. Direct proxy 与数据质量

- C1 Platform 从 capability 直接调用 proxy，一次 tool result 同时得到 structured response/request digest/
  response digest；Host 无人工数据消息。
- C2 使用 CQ1/CQ2 只读请求证明现有 entities/facts 足够生成 current/usable reports。
- C3 若 3-turn 内缺事实，保留具体 missing relation/evidence；不得用业务专属 API 修复本轮。

### D. Turns、性能与 positive-N

- D1 真实 App Server 探针先冻结 token-usage 事件名/字段/粒度；每个 Source/Platform/Acceptance 正常 path
  observable inference steps<=3；第4步前中断并 typed `BLOCKED/runtime-budget`。
- D2 每个 Examiner 目标<=60s、上限<=90s；proxy HTTP 单独计时；provider outage 单独分类。
- D3 N=1/3/5 ordinal/previous/next/final/settlement 无固定题名或数量逻辑。
- D4 `ExaminerRunMetrics/v1` 可重算 fresh thread、canonical first_turn_input、turn/start、token-usage increments、
  first/total/cached/task/evidence/output/reasoning、TTFT/terminal/proxy time；metrics 缺失时性能验收 FAIL/BLOCKED。

### E. Real acceptance、回归与清理

- E1 R2.3-003 final workspace N=2 每题 fresh Source/Platform/Acceptance 全部 PASS/current/usable，未预填历史答案。
- E2 StartLedger/ontology/batch/session/lease/attempt 前后不变，无 semantic start。
- E3 exactly-one read key create/revoke，post-revoke 401/403，child 无 plaintext，零 scoped residue。
- E4 R2.3-005/default 和非 Examiner Agent 上下文/工具行为无变化。
- E5 repository-required suites、compile/lint/diff、service restart/health（若改 runtime/backend）通过。

## 3. 计划轮次

- Round 1：实现审查 + focused deterministic packet/transport/proxy tests。
- Round 2：独立 real N=2 只读验收、性能/token 证据、清理和隔离回归。
- 后续轮次只处理已确认 requirement defect，继续追加本文，不创建新测试计划。

## 4. 当前未执行

本文件当前只冻结未来验收范围；没有启动 Agent、创建 key、调用平台或消耗建模授权。
