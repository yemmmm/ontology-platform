# R2.1-001 M7 暂停收尾记录

- 日期：2026-07-29
- 状态：`PAUSED / 未通过 L1`
- 用户决定：暂停本次需求开发，整理现状与实施过程，清理本次产生的测试文档并完成收尾
- 场景：`docs/evaluation-scenarios/dify-workflow-impact-m7/`
- 详细历史：`docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`

## 当前结论

M7 尚未完成。L0 Runtime 已通过，但三次正式 fresh Producer 尝试都在 principal apply 前终止，
因此没有形成可交给独立 Judge 的已应用 M7 本体，也没有 L1、blind Consumer、independent repeat
或 mutation PASS。

固定 Host 程序的责任已收敛为协议、scope、hash、dry-run/apply 一致性、validation/reasoning、
公开证据、citation 和清理。开放式业务语义应由 fresh read-only Judge subagent 判断，再由主 Agent
裁决；Host 不再通过固定角色或 case mapping 充当业务判卷程序。

## 已完成工作

- 冻结 Workflow orchestration + typed variable flow 的业务边界、五项澄清答案、三个 CQ、M1 回归
  和四项 mutation 方向。
- 完成独立 L0 probe；真实 fresh Agent 使用冻结命令运行成功，L0 结论为 `PASS`。
- 建成 scenario-local Host spine：fresh scope、确定性 base、Modeling Batch dry-run/apply、lease、
  validation、reasoning、scoped SPARQL、失败清理。
- 建成 visible sealer、Producer/Judge/Consumer staging 隔离、完整 RDF snapshot、citation、
  `AWAITING_JUDGE` / `AWAITING_L2_CONSUMER` 和配对终止清理状态机。
- 使用现有公开 `/api/ontologies/{id}/workspace-context` 修正 graph-set 读取；未修改平台产品代码。
- v4 已把未发布的 governed Evidence/CQ ID 引用改为提交前拒绝，inline evidence 和 `cq_claims`
  继续承载来源与语义。
- 暂停收尾后的 scenario canonical stable hash 为
  `12f3b630b81b496c3d20cd504d607a9702cddd826a578457a9f9d056a793f1dd`。

## 三次建模尝试

| Attempt | Contract | 到达阶段 | 结果 | 是否 principal apply |
| --- | --- | --- | --- | --- |
| 1 | `m7-contract-v1` | Producer 完成五问和语义包 | visible envelope/Modeling Item 协议未公开，Host pre-admission 拒绝 | 否 |
| 2 | `m7-contract-v2` | Producer 完成五问和候选 | 冻结命令使用不存在的 `python`，sealer 未启动 | 否 |
| 3 | `m7-contract-v3-judge` | Producer 完成五问并成功 seal，进入 principal dry-run | fresh Project 无对应 governed Evidence/CQ 记录，平台返回 `evidence_not_found` / `competency_question_not_found` | 否 |

三条 `modeling_started` 事件保留在 scenario-global append-only ledger，既有 runtime 目录不改写。
三次 owned Project 的 cleanup receipt 均为成功。

## 暂停点与已知缺陷

当前源代码版本为 `m7-contract-v4-recovery`。开发自测为 M7 `57 passed`、M1/M6 `18 passed`、
49-item compiler preflight、Ruff 和 diff check 通过。

独立 Test Round 11 结论为 `FAIL`，唯一确认阻断项是：

- `M7-V4-001`（High）：读取 attempt ledger 时只检查
  `l1_pass_authorized` 的事件名、run ID、版本和非空 digest。向临时 ledger 直接注入伪造 JSONL
  事件即可错误解锁 attempt 5，尚未证明该授权确实由配对 Judge all-PASS + 主 Agent accept 路径
  产生。

由于用户要求暂停，不继续修复此缺陷，不启动 Round 12，不创建 attempt 4。

## 运行与资源收尾

- `SEMANTIC_PRODUCT_WRITE_MODE` 的临时 systemd manager override 已撤销。
- `ontology-platform.service` 已恢复 active。
- 后端 `/api/health` 返回 `{"status":"ok"}`，前端返回 HTTP `200`。
- Attempt 1–3 的 Host state 均记录 owned Project cleanup success；暂停收尾再次检查这些 Project
  不可访问。
- 没有 backend/frontend 产品代码或数据库 migration 变更。
- 收尾回归：M7 `57 passed`（一条第三方 TestClient deprecation warning）、M1/M6
  `18 passed`、Ruff 和 `git diff --check` 通过。
- 两个冻结 official source 文件仅移除了 trailing whitespace，并同步更新输入 manifest；语义
  内容未改变。

## 清理范围

本次新建的 M7 共享测试计划文档已删除；其关键轮次结果、失败原因和恢复门槛已收敛到本记录及总
delivery record。生成的 `.pytest_cache` 文档也已删除。

保留 `tests/` 下的可执行回归代码、scenario source、不可变 attempt ledger 和 ignored runtime
证据，因为它们是以后复现与恢复所需的工程资产，不属于被清理的测试文档。

## 恢复条件

恢复 M7 时从当前 v4 暂停点继续，不重做已完成的 L0、Judge 边界或三次历史尝试：

1. 先修复 `M7-V4-001`：授权事件必须与 Host 生成且封存的 Judge verdict、run/scope、contract、
   verdict digest 和主 Agent adjudication 配对，伪造/篡改/跨 run 事件必须失败。
2. 对将修改的既有符号先执行 GitNexus impact；运行完整 M7、M1/M6、compiler、Ruff、diff 和
   canonical hash。
3. 由独立 tester 执行新的离线轮次；只有 `PASS` 才能考虑 attempt 4。
4. 启动前再次确认 attempt ceiling 和 attempt 5 的必要性；不得修改历史 ledger 或复用失败 scope。
5. 若 attempt 4 成功 apply，才创建 fresh Judge；Judge all-PASS 后再执行 blind Consumer。M7
   仍需 independent repeat、四项 mutation、M1 回归和最终独立 PASS 才能标记完成。
