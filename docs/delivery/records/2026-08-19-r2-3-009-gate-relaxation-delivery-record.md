# R2.3-009 Modeling Team 校验降级与 Agent 自修复 — 交付记录

- 日期：2026-08-19（设计）/ 2026-08-20（交付）
- 需求：`docs/requirements/requirements-v2.3.md` R2.3-009（目标 1–7，用户 2026-08-19 确认）
- 设计：`docs/delivery/design/2026-08-19-r2-3-009-gate-relaxation-design.md`（plan review 通过）
- 测试计划：`docs/delivery/test-plans/2026-08-19-r2-3-009-gate-relaxation-test-plan.md`
- 实现：commits `8c78308..9dfaec7`（6 步各自全绿提交），design/review/requirement 记录性
  commits `520227f` / `fde390b`
- 状态：**R1–R7 独立 PASS（2026-08-20 第 1 轮）；R8 真实运行演练待用户授权 start 预算**

## 1. 交付范围

将 modeling_team Runner 工具层的"校验失败 → 终止运行"路径整体降级为 Agent 自修复反馈：

1. **C 类**（检索证据警告扫描，defect 9 一般化）：`_validate_response_quality` 无 raise，
   警告记入 receipt `warnings_observed` 与 `evidence/retrieval-quality-warnings.jsonl`；
   结构性不变量（cursor 绑定、artifact digest、frozen query 漂移）保持 typed 返还 protocol。
2. **B 类**（候选通道协议，defect 10/11 一般化）：违约投递先持久化证据，再记
   `observed-issue`，向责任 Agent 投递 typed conflict（候选工件缺陷→modeling、
   receipt/handoff 行为→protocol）；revision 门检查本身保留（拒绝该投递，不杀 run）。
3. **A 类**（写入完整性）：同步站点 error 载荷升级 `{code, detail, remediation}`；异步
   registration-rejected 按 reason 细分责任人，经通道 2 Runtime typed 反馈投递；
   post-complete 重开迁移（`complete → awaiting_revision`）与注册侧联动成套（重开时作废
   `_accepted_candidate_identity`，泛化 `acceptance.py:1735/1750` task 门），删除 R2.3-003
   专属 `allow_post_receipt_revision` 硬编码。
4. **兜底分层**：T1 nudge（`candidate_redrive_limit` 默认 3）→ T2 自动 issue
   （`feedback_escalation_repeat` 默认 3；issue 开/解决显式接线 `progress.pause()/resume()`，
   本变更新增于 runner.py:4076/4200/4220）→ T3 run 级 active clock
   （`run_fallback_timeout_seconds` 默认 5400s，排除 issue-pending 时段）——唯一保留的
   校验类 latch（`collaboration/routing:run-fallback-timeout`）。
5. **预算退款**（用户决定"自修复 run 不计预算"）：新账本事件
   `terminal_settlement(outcome=agent_blocked|agent_completed)` 与 `budget_refund`（每 run
   至多一次、紧跟终局、仅 agent_blocked / T3）；`_start_cap` 回放每有效退款 +1；退款后
   `terminal_failure` 拒绝；非 strict 账本保持历史记账不退款。
6. **白名单守恒**：`_FORMAL_FAILURE_LATCH_WHITELIST`（7 项：5×I 类
   `internal-invariant:`、1×`runtime/infrastructure`、1×T3）+ AST 源码扫描守恒测试；
   S 类前缀 `startup-config:`。

## 2. Plan review 处置摘要

初审 4 High（A 类异步无通道 / 3259 路由与状态机 / turn-binding 误归 A / pause 未接线）与
复审 2 New High（重开撞 mutation 守卫 / 4331/4334 误入 I 类白名单）全部确认并修订关闭；
终审 gate clear。需求目标 2 补 I 类边界澄清；测试基线更正为实测 938。

## 3. 独立测试（第 1 轮，2026-08-20）

- R1–R7 全 PASS（25 个独立 fake-adapter 用例 + AST/源码扫描），证据录入测试计划。
- 聚焦三项裁定：(a) 替换分支"遮蔽"mutation 守卫为死代码但不可达非法路径——非缺陷；
  (b) T3 terminal_evidence 替代形状 replay 正确、legacy 账本不退款；(c) pause/resume 接线
  为本变更新增（开发方"已存在"说法不实，最终状态正确）。
- 全量回归（tester 独立执行）：**970 passed / 1 skipped / 302 subtests**（≥ 基线 938）。
- defect 9/10/11 既有回归测试全部保持通过。

## 4. 残留风险与接受决定

| 项 | 处置 |
|---|---|
| `acceptance.py:1843-1844` 死分支（differing-record 先入泛化替换分支） | 接受保留（低危清洁项，独立验证不可达非法路径）；后续迭代删除 |
| T1/T2/T3 参数（3/3/5400s）未经真实运行标定 | R8 授权后标定 |
| `agent_blocked` 判定为"任一 Agent 报 blocked 即 blocked"（混合终态） | R8 观察确认 |
| R8 真实运行演练 | 待用户显式 start 授权；届时验证自修闭环、无 validator kill、退款记账 |

## 5. 验证命令

```
env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q
# 970 passed / 1 skipped / 302 subtests（主 agent 与 tester 各自独立执行确认）
```

未触碰 `backend/`，无服务重启需求；未启动任何建模 run。
