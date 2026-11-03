# R5.0-011 首轮真实过程评价缺陷修复

日期：2026-11-03。归属：[R5.0-011](../../requirements/requirements-v5.0.md#r5-0-011)。
问题依据：[首次真实运行复核](../../research/2026-11-03-process-evaluation-first-live-findings.md)。

范围：仅修复 v5 过程评价的报告选择、阶段提示、重试错误归属和满意度汇总；不改全局 JSON 解析器、生产建模、受治理写入、正式验收合同或原始 run。代码、模型、历史评分与失败原件不混为同一验证结论。

## 修复与验证对应

| 问题 | 最小修复 | 证据与限制 |
|---|---|---|
| 正文 `{}` 与报告同时被识别 | 本地 `REPORT_SCHEMA` 以真实报告的必需键与类型选择唯一对象 | 原始五份真实返回均可离线解析并通过报告结构检查；真正两份不同报告仍失败，不任选第一份；未改旧记录 |
| 计划被要求已经应用 | v2 提示区分 CQ／能力目标、切片方案与实际整合；前两者不要求实际模型或回执，缺必要材料为未验证 | 已检查实际 invocation 接收权威提示；提示语义效果尚未以新原生评分校准 |
| 评价器自身错误扣生产分 | `evaluator_feedback` 显式 `scope=process_evaluation_only`，保留原解析细节；成功后清当前 error，旧版本失败保留 | 原生替身＋真实 PostgreSQL 测试检查实际重试输入、成功记录及失败历史；不声称保证 LLM 永不误读 |
| “无缺口”与正常边界变成缺口 | 以结构化 status／score／priority 判定；任一真实缺口必须在维度上标非 none 优先级；正文仅解释；增加可选 boundary_notes | 高分＋none 不被“无缺口”正文误标；低分及 low/medium/high/critical 缺口均保留；必要证据未知仍 unverified |
| 新提示改变旧绑定标准 | 新提交为 rubric v2；新准入及评分前核对标准；旧在途先由原 ExecutionManager 对账，再提示显式重新提交新标准 | 原始中断结果可排空 active，不重调原生；旧已完成记录仍复用、不重评；未创建另一调度／恢复框架 |

T0 复核：唯一报告选择与冻结标准保护评价结果归属，须保留；用宽泛 object 形状将普通说明误当报告不保护额外不变量，收窄为真实报告形状。格式失败仅影响本次诊断并允许显式纠正，不停止生产。满意度不再以自然语言正文承担程序判定，不新增语言词典或自动修模。

## 开发验证

- 先红：新增回归首次 **4 failed、5 passed**，准确复现空对象歧义、正文触发误报、重试反馈归属和标准混用。
- 边界补充先红：在途结果遇标准变化时，旧检查位置阻挡 active 排空，**1 failed**；将检查移到新准入及对账后的评分边界。
- 初版针对性：`test_process_evaluation.py`＋既有独立工程用例 **49 passed**。
- 最终新增范围：`-k 'rubric or no_gap or declared_gap or retry_feedback or report_selection or two_distinct'` **10 passed、30 deselected**。
- 完整 v5 回归（首次修复版）：**325 passed，1 warning，383.18s**。warning 为既有
  Pydantic `lifespan` 前向引用警告，未产生测试失败。
- 独立复核补充先红：空／不完整模板 2 例、来源漂移不得视为修报告 1 例、版本身份 1 例，
  **4 failed**；补充嵌套报告形状、按错误发生阶段隔离反馈、同时核对版本和摘要。
- 最终过程评价回归：两份 `test_process_evaluation*.py` **54 passed，25.34s**。
  最后修改仍限于同一过程评价模块，相应全部用例已复测，不重复未变组件全套。
- 最终嵌套报告形状再次离线核对真实返回：**5/5** 解析和结构验证通过，原文件 SHA256 不变。
- 修改文件 Ruff、格式检查、`git diff --check`、新增文档链接检查通过。
- GitNexus 未索引到新 v5 符号；`detect_changes(scope=all)` 返回 low，但仅识别到既有
  文档符号，不作为 v5 图覆盖证明。实际影响按过程模块调用点、diff 和回归测试核对。

环境：Python 3.12 锁定 v5 环境，真实 PostgreSQL 随机临时 schema，由 fixture 清理；原生调用使用既有测试替身，无付费模型调用。

```sh
env ONTOWEAVE_TEST_POSTGRES_CONFIG=/home/yangxiang/ontology-platform/workspaces/v5-codex-p0/postgres-host.json \
    UV_PROJECT_ENVIRONMENT=/home/yangxiang/ontology-platform/workspaces/v5-codex-p0/.venv \
    uv run --locked --project modeling_team/v5 pytest -q modeling_team/v5/tests
```

离线原件核查：`workspaces/v5-runs/process-high-20261103-inputs/repair-original-replay.json` 记录五份 `executions/process-*/result.json` SHA256 及解析结构 PASS；逐份读取前后字节一致。该操作不调用过程 worker，不将历史失败改成成功，不更新历史 satisfaction 或正式验收。

## 独立复核与范围

独立 reviewer 使用全新上下文，只读实现与原件、运行无付费探针。首轮确认本次原始四项
修复通过，定向 **50 passed**，扩展过程／控制／预算／Flow **90 passed**；同时要求
收紧本次新增反馈的错误归属、空模板形状及版本身份，均已纳入上述补充与最终回归。
最终独立范围验收：**PASS**。独立侧再次执行 **54 passed，25.27s**，Ruff 与
`git diff --check` 通过；本轮四项修复及三项补充无 Critical／High／Medium 阻断。
结论覆盖工程行为及实际提示接线，不代表完整 R5.0-011 验收或修后原生评分校准。

复核另指出以下 HEAD 基线已有问题，本次未修改这些汇总逻辑，不将本次交付扩大为
完整 R5.0-011 关闭：模型修订变化未参与 summary 适用性更新；未开始即失败时耗时可能
以 Unix 时间戳计入；`evaluation_complete` 当前仅表示没有 queued/running 记录；
`score_deltas` 未计算显式复评变化。它们是保留的既有汇总限制，尤其不能把旧模型版本
的报告当成新模型已验证，不能用该布尔值代替所有阶段有效完成或正式验收。

## 验证边界

本次仅修复过程评价，未改 `backend/`、`frontend/`、依赖或启动脚本，无需重启应用。没有新的 semantic start，也没有付费过程重评；原授权 run 保持停止、模型与凭据收口状态不变。工程测试不能证明修后原生评分准确率、阶段评分稳定性或净降耗。语义效果需后续明确授权的有界评分校准，不由本轮自动恢复旧 run 或追加预算。
