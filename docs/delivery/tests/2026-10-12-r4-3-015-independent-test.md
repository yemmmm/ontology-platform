# R4.3-015 独立功能验收

## 权威范围与验证边界

复用 [R4.3-015](../../requirements/requirements-v4.3.md#r43-015-分阶段建模反馈与成功写入信任边界)
及 [详细设计第 8 节](../designs/2026-10-12-r4-3-015-staged-feedback-write-trust-design.md#8-验证范围与独立审阅)
的 V1—V6，不另设验收门。修改范围是 Team Runner、Delivery 读取白名单及活跃角色／方法指令；
不修改产品实现或既有测试。独立新增覆盖仅在 `modeling_team/tests/test_r4315_independent.py`。

前提：从 `backend/` 使用当前 uv 环境，`env -u DEEPSEEK_API_KEY PYTHONPATH=..`。
native broker、临时 run、真实保留文件、受控 launcher 及 RDF Store fixture 可运行；
不调用外部模型、不启动／恢复生产建模、不重启服务。

非目标：V6 新授权真实运行、模型质量／真实 Agent 协作行为及提速收益；
fixture／指令合同 PASS 不能提升为这些结论。主 Agent 全套开发回归与本独立验收分别记录。

## 既定用例与步骤

| 用例 | 既定范围 | 步骤及预期 |
| --- | --- | --- |
| V1 | A1—A3 正常执行 | 复用 native broker production fixture，运行当前审批计划与重试；完整 projection、当前版本、原身份及终态保留；正常／already_applied 返回 not_evaluated，只保留必要版本读取与回执，不强制资源扫描；dry-run 为 not_applied |
| V2 | A3、A7 异常恢复 | 执行缺证明、改引用、未知写入、版本读回失败等反例；保留第一错误、完成项和原身份，安全重试不重放已应用计划 |
| V3a | A4—A6 原公开反馈 operation | 控制 launcher 的 0／非零退出与等待；无 owner 时 exited、exit_code、ended_at 是完成证据，work_state 可仍 working；原 operation 查询、拒绝重复 operation、过期／错绑定保留；摘要不提供答案 |
| V3b | Delivery 正文 | 读取当前绑定报告和响应，对照实际 content_digest；旧报告不绑定，改正文与原 digest 不一致；跨 run、host 路径、越界 symlink、目录和大文件拒绝 |
| V3c | 提交窗口 | 审查现有 guidance／Team reply 合同；暂停新 dry-run/apply、等在途回执、允许分析／候选／计划准备；实际 operation 完成才释放，未知写入／用户暂停不解除；仅为指令约定证据 |
| V4 | A3、A8 最终关联检查 | 执行独立显式关联检查、ScopedSparql 分页／共享目标、游离与修复复查；能力保留、最终实际读取保留、不回到逐批强制扫描 |
| V5 | A6、A8—A9 最终边界 | 检查活跃角色／方法／Task 的真实依赖（含共享引用）、已应用／质量／未知分账、局部反馈不代替最终完整只读独立验收及公开／隐藏隔离；旧 formal 回归 |
| V6 | 真实效果 | 未获准执行；须新授权运行后核对资源读取业务用途、首链反馈、全局覆盖、成本与质量。本轮不据 fixture 宣称通过 |

通过标准：V1—V5 可执行功能与指令合同全部满足且无需求缺陷；V6 清晰保留未执行。
若发现产品问题报告主 Agent 修复后复测，不直接修改产品。每轮追加结果，不覆盖历史。

## 测试轮次

### Round 1（2026-10-12，执行前）

代码基线与工作区：实施分支当前 HEAD，主 Agent 正在修改 15 个已知产品／测试／指令路径，
独立验收使用当前工作区而非声称已提交版本。准确 HEAD、命令、结果及证据在执行结束后追加。

状态：测试计划已落盘，尚未执行；V6 不在本轮授权范围内。

### Round 1 结果（2026-10-12 18:44 SGT）

HEAD：`a26261a297224020f7890394c364aaa90ca3e4f1`；使用主 Agent 未提交的本需求工作区。
产品修改是 `runner.py` 成功字段／后续动作、`capability_mcp.py` 说明、`delivery.py` 读取目录，
以及任务／角色／方法指令。测试开始前已阅读根 AGENTS.md、权威 A1—A9、设计 V1—V6 和本轮 diff。

命令均在 `backend/` 执行：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4315_independent.py ../modeling_team/tests/test_v43_production_refs.py ../modeling_team/tests/test_delivery_session.py ../modeling_team/tests/test_delivery_ops.py ../modeling_team/tests/test_r4015_public_feedback.py ../modeling_team/tests/test_staged_batch_write_forwarder.py ../modeling_team/tests/test_r4024_model_check.py -q -k 'not live_oxigraph'
```

结果：132 用例收集，**131 passed、1 deselected，70.20s**；唯一排除项为
`test_live_oxigraph_scan_repair_and_cleanup`，未执行 live Oxigraph 写入／修复。
356 条警告来自 rdflib 既有 Dataset API 弃用，没有测试失败。
本轮新增独立文件当时为 14 项 operation／正文用例。

V5 的既定相邻回归：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r3011_acceptance_cli_flow.py::test_tg41_two_v3_sessions_complete_the_batch_through_real_sockets ../modeling_team/tests/test_r3011_acceptance_cli_flow.py::test_tg41_platform_packet_stays_blind_and_multi_ontology_scope ../modeling_team/tests/test_r3011_acceptance_cli_flow.py::test_tg46_post_read_drift_keeps_reports_and_fails_the_batch ../modeling_team/tests/test_r3012_partial_judging.py::test_a_partial_batch_judges_only_its_judgeable_questions ../modeling_team/tests/test_r3012_partial_judging.py::test_judge_native_input_partition_preserves_complete_ordered_evidence ../modeling_team/tests/test_r3012_partial_judging.py::test_oversized_judge_groups_use_real_factory_sink_and_global_denominator -q
```

结果：6 个指定节点展开为 **11 passed，9.77s**，未跳过。
这些用例使用受控运行适配器和真实本地 socket／报告 sink，不调用外部模型。

| 范围 | 结果／实际证据 |
| --- | --- |
| V1 | PASS：native capability 按审批精确投影与依赖顺序 dry-run/apply，版本 1→2、4→5；重试 already_applied 无重放，只有 get_modeling_context 与 submit_modeling_batch 保留回执，无额外全资源扫描。顶层及单项 not_evaluated，dry-run not_applied |
| V2 | PASS：原引用／审批漂移、未知写入、缺终态证明、版本确认失败保留具体错误及恢复路径；write forwarder 通过真实受控子进程验证原请求／Attempt／内容身份、超时／断线未知和确定拒绝可恢复；已应用后读回失败重试不重放 |
| V3a | PASS：新独立例驱动实际 operation record／reaper，0 和 9 退出 × observed／partial／superseded／not-executed；无 owner 时 exited、exit_code、ended_at 真实存在，而 work_state=working。等待受控任务时 exited 证据不存在；释放后查询同一 operation，launcher 只调用一次 |
| V3b | PASS：旧报告不绑定；当前报告的 summary 不含 Consumer 答案，通过 Delivery 正文读取返回答案及实际 digest；修改正文后与原 binding digest 不同。错 run／freeze／checkpoint／题目报告绑定被拒绝，但非零实际结束仍保留。绑定 run 的公开正文／响应可读，越界路径、symlink、目录、大小限制保持 |
| V3c | PASS（指令合同）：Delivery／Coordinator／Protocol／Modeling 明确现有 sourced guidance、reply-required Team 消息、新提交暂停、在途回执与 write_positions、准备继续、原 operation 超时查询、结束后解除正常提交等待。未知写入／用户暂停不自动解除，非零／不足报告不制造永久窗口；不是实际 Agent 执行这些消息的证据 |
| V4 | PASS：显式最终关联读取由实际 RDF Store、ScopedSparql 分页和保留 read_refs 支持，共享跨 Ontology 目标仍检查，500+ 分页、游离处置与修复复查仍在；未删除能力或改名强制逐批扫描 |
| V5 | PASS（功能＋指令合同）：实际 socket 受控完整验收保留全冻结分母、分组 Judge 完整有序证据、PARTIAL、绑定漂移拒绝与 hidden 输入隔离；旧 formal sink／capability 回归保留。活跃指令要求真实依赖含共享引用、仅修订变更内容、完整范围／未知／最终独立只读验收。依赖判断／业务选题仍为 Agent 方法合同，不是本轮真实 Agent 行为证据 |
| V6 | 未执行：新授权真实阶段建模、业务质量和成本／提速比较；本轮不产生这些证据 |

Round 1 独立结论：**PASS（工程功能与指令合同限定范围）**；无产品缺陷，不要求产品修复。
主 Agent 全套开发回归结果不作为本表独立执行结果。

### Round 2（2026-10-12 18:46 SGT，补足 V2 及旧提示断言对齐）

工作区仍基于 `a26261a297224020f7890394c364aaa90ca3e4f1`。
产品代码／指令未变。独立文件增加 2 项 V2 既定中途失败反例：第二计划返回明确
`failed`／`validation_failed`；第一计划 applied、原 completed／error.stage／plan_ref 保留，
修复受控失败后第一计划 already_applied，仅第二计划再 apply。

主 Agent 更新既有 `test_transport.py` 的旧断言：取消“每次 apply 后逐项核对 SPO”，
改为正常不重复核验、业务读取／必要恢复仍完整分页。独立审查 diff 确认原 missing／extra／
delete／binding／unknown-write、计数不替代 SPO 的约束未删除；该变化与 A3／A7 一致。

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4315_independent.py -q
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_transport.py::TransportTests::test_prompts_adjudicate_cross_slice_relations_by_actual_triples -q
```

结果：独立新增文件 **16 passed，4.05s**；更新提示合同 **1 passed，0.09s**。
V2 补充反例 PASS；其他独立例复测 PASS；无 STILL FAILING／REGRESSION／BLOCKED。
V6 及真实 Agent 消息协作仍未执行，不因 Round 2 变成已验证。

最终独立结论：**PASS**。已有 Round 1 的其他结果在产品／指令输入不变时继续有效；
Round 2 覆盖新增测试和主 Agent 后续测试改动。没有需开发 Agent 修复的产品缺陷。
不宣称真实语义 PASS 或提速 PASS，不执行生产启动、暂停解除、服务重启或外部模型调用。

文档／测试文件检查：`git diff --check -- modeling_team/tests/test_r4315_independent.py
docs/delivery/tests/2026-10-12-r4-3-015-independent-test.md` 无错误；另用 Python 检查
本测试文档本地链接存在、两份新增文件无尾随空白、独立测试源码可编译，输出
`PASS: local links, whitespace, independent test syntax`。未修改产品路径、既有测试或运行保留证据。
