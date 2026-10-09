# v4.3 共享测试计划

范围：[需求](../../requirements/requirements-v4.3.md)、[设计](../designs/2026-10-09-v4-3-modeling-efficiency-design.md)。
真实建模保持暂停。测试数据使用 uniquely owned 临时目录，保留失败记录，不污染生产。

| 编号 | 必须证明的行为 |
| --- | --- |
| T001 | 同轮起点不随修模／重验重置，终点要求完整独立 PASS 和必要收尾；故障并集、人工等待、未知及总墙钟分别展示；配置／资料／题集身份可追溯 |
| T002 | 完整获批依赖计划按引用连续执行，每批用当前版本取得 dry-run；正常回执不重复语义批准；实际定义／关系／跨 Ontology 引用完整 |
| T003 | 计划变更、未批准、越权、失效 proof、漂移和失败准确反馈；成功提交不重放、未知写入不盲重试，可修正后继续 |
| T004 | 多页保留受治理读取可按本轮引用无损关联扫描，定位及摘要匹配；缺页 PARTIAL，篡改／其他 run／任意路径拒绝 |
| T005 | 角色合同与确定性计划覆盖保持完整业务链、明确不落地项；首条完整小链安全读回后可以通过现有有界公开反馈路径，隐藏题不泄漏 |
| T006 | 心跳／字节／日志／无关计数增长不唤醒；同数量新问题、内容版本更新、成果、阶段终态、异常与未知请求必须唤醒；用户暂停／停止／输入及时送达 |
| T007 | Judge 初始 packet 不重复内嵌业务全文；读取本轮冻结副本，修改当前源文件不影响；资料版本／章节可区分，同文复用与重读均合法 |
| T008 | Judge 原文读取拒绝越权／路径／其他 run／未知 identity；摘要篡改／读取失败可定位；未实际读相关原文或只持 manifest 不可 PASS；无平台写入、DB、仓库能力 |
| T009 | 主动无损去重缩小平台响应正文，逐题引用、绑定、权限、分页、完整性不丢；业务资料节省另计 |
| T010 | 按实际输入体积主动分组，完整题分母／顺序／实际判据不丢；单题超软目标可完整执行，超硬限明确未完成；不把分组拼成单会话 |
| T011 | 当前 Team 回归与变更 skill／工具 schema／链接检查；若涉及 backend／frontend，执行对应仓库强制检查、重启及端点健康验证 |
| T012 | 待恢复授权的真实从零运行：固定 industrial-service-v3 获准资料、17 公开＋10 隐藏及配置，全量独立 PASS，完整端到端 ≤120 分钟；当前未执行 |

## 轮次

- 设计审阅 Round 1：独立 `plan_reviewer` PASS，无 Critical／High；只读审阅，无代码测试。
- 开发验证：待执行。
- 独立功能验收：待执行。
- 真实性能验收：未执行；暂停授权边界，不能以工程测试替代。

### 独立工程功能验收 Round 1 — FAIL

时间：2026-10-09T04:55:15Z。测试 Agent 只增加本节与 gitignored 独立测试探针，
未修改产品、运行保留证据、交付记录或提交代码。环境为现有 backend uv 环境，
`env -u DEEPSEEK_API_KEY PYTHONPATH=..`；没有启动生产 semantic/evaluation/repair。
代码为当前 dirty 工作树，29 个 Team 文件逐个核对
`workspaces/v4-3-engineering-20261009/product-baseline-round1.json`，全部摘要一致；
manifest SHA-256：`0b8dabd5675716c1eb86ef298f031b34e5204150323ee09d4069713fe96768b0`。

执行与证据：

1. 从 `backend/` 执行
   `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../workspaces/v4-3-engineering-20261009/independent_native_round1.py --basetemp=/tmp/v43-ind-r1-20261009`：
   **11 passed**，9.78 秒，日志
   `workspaces/v4-3-engineering-20261009/independent-native-round1-corrected.log`。
   真实 run-local capability AF_UNIX、真实 stdio MCP/socket/report sink、真实计时 CLI；
   平台写入仅临时 fixture forwarder，分页读取用既有 ScopedSparql/RDF fixture。
2. 从 `backend/` 执行
   `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests/test_v43_production_refs.py ../modeling_team/tests/test_v43_judge_references.py ../modeling_team/tests/test_delivery_wakeups.py ../modeling_team/tests/test_efficiency.py ../modeling_team/tests/test_delivery_session.py::test_run_delivery_control_keeps_priority_while_turn_is_busy ../modeling_team/tests/test_delivery_session.py::test_run_delivery_steers_queued_input_into_the_active_turn_in_order`：
   **54 passed**，24.78 秒，日志
   `workspaces/v4-3-engineering-20261009/independent-contract-round1.log`。
3. 主代理准确命令为
   `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q > ../workspaces/v4-3-engineering-20261009/team-regression-round1.log 2>&1`，
   handle `60844`，exit 1。检查同一 baseline 全 Team 回归实际终态日志
   `workspaces/v4-3-engineering-20261009/team-regression-round1.log`：
   **3 failed、2576 passed、11 skipped、304 subtests passed**，199.07 秒。
   复用当前全套结果，没有再执行同状态全套。
4. `python3 modeling_team/skills/ontology-modeling/evals/validate_skill.py` PASS；
   需求、设计、共享计划、Delivery/Acceptance Skill 共五份文档本地链接检查无断链；
   `git diff --check` PASS。backend/frontend 未改，不要求相应全套或服务重启。
   GitNexus 索引陈旧，本轮没有图影响覆盖主张。

| 项目 | 本轮结果 | 当前工程证据与边界 |
| --- | --- | --- |
| T001 | PASS | 起点不可覆盖、resume 防重置、完整 PASS/收尾缺项保留未知、故障并集与人工等待分别计时；独立真实 CLI 读同文件不改写、不裁决性能 |
| T002 | PASS | 两个完整 plan_ref native 连续 dry/apply，第二批当前版本、精确 projection；ScopedSparql 实际分页读定义/关系/跨 Ontology 共享目标并按保留 refs 扫描。版本回执明确 pending_protocol_governed_read，不当资源读回 |
| T003 | PASS | 未批准/变更在写前拒绝；独立撤销 dry 后批准阻 apply，恢复后继续；确定未写入失败可重试；已成功不重放，未知/缺终态 proof 拒绝盲重试；CQ freeze/gate/actor/path/schema 边界保持 |
| T004 | PASS | 多页 refs、原文摘要、read locator、缺页 PARTIAL；任意/其他 run/未观察 refs 拒绝；独立 scoped 项目不匹配 PARTIAL，摘要篡改返回 named read_ref |
| T005 | PASS | 关系缺计划保持 PARTIAL，明确 unknown 等处置可核对、actual apply 与仅计划分开；角色合同保留完整小链、materialization_progress 和有界 public-feedback，现有公开反馈工程回归无失败。真实小链消费质量/收益未测 |
| T006 | PASS | 心跳/日志/字节/计数不唤醒，新问题同数、版本、阶段/终态、异常/存活、请求/结果唤醒；busy steer 与竞态保留；原暂停控制先 interrupt 再 steer、排队用户输入顺序保持 |
| T007 | PASS | 首始 prompt/input.json 无业务全文；冻结副本不受当前源改写影响；章/版不同身份、同文复用/重读；独立 stdio 重读生成两份可核对 receipt |
| T008 | PASS | manifest-only PASS 被真实 sink 拒绝；foreign run/path/identity 与摘要变化反馈；native mount 仅 report+frozen read；独立 stdio 读相关原文后两题可 PASS，完整结束后拒绝再读；组间 receipt 不串用 |
| T009 | PASS | lossless transport 可展开回原 packet；同正文 registry 去重，逐题摘要/定位/分页/完整性保持；资料与平台响应体积分别统计 |
| T010 | PASS | 5/27 题按实际 byte 提前分组、顺序和完整分母保持；单题超软目标仍完整，超硬限准确 failure；每组 source registry 和 read receipt 独立 |
| T011 | FAIL | 三个原测试未同步获批新合同，详见下方缺陷；其他全 Team 回归、变更 schema/角色、Skill/链接/diff 检查通过 |
| T012 | BLOCKED / 未执行 | 用户真实运行暂停；需恢复真实完整运行授权才可执行。独立工程通过不能证明完整语义 PASS、27题质量或120分钟实测 |

缺陷（均需主代理交原开发者更新并复测；没有已证实产品 Critical/High）：

- **E43-TEST-01 / Medium / T011**：运行
  `test_r23006_lean_runtime.py::R23006LeanRuntimeTests::test_lean_acceptance_package_and_inventory_are_report_only`。
  期望旧 packet 仅 report，新引用 packet 才加 frozen read；实际测试 unrestricted Mock
  未明确 `frozen_evidence_reads=False`，新增字段读取得到 truthy Mock，断言实际集合多
  `read_frozen_evidence`。证据：全回归日志行 39–92。更新 fixture 并覆盖旧/新两种真实布尔配置。
- **E43-TEST-02 / Medium / T011**：运行
  `test_staged_associate_evidence.py::test_staged_protocol_operation_set_pairs_submission_with_evidence_repost`。
  期望 008B live surface 仍单 submit、unified surface 增三 refs 能力且退役 evidence repost
  不复活；实际旧全集断言仍将 ROLE/全集等同单 staged 集合，差三工具。证据：日志行 93–106。
  更新全集与 active 008B/unified 分支断言，保留退役与隔离边界。
- **E43-TEST-03 / Medium / T011**：运行
  `test_transport.py::TransportTests::test_transport_budget_splits_route_through_the_coordinator_not_new_tools`。
  期望获批 v4.3 完整引用执行/真实约束形成计划/精确 projection/变更重新批准合同可验证；
  实际仍断言旧逐字转录及拒绝引用工具的提示原文，首条缺旧字符串失败。证据：日志行 107–123。
  按新权威合同重写断言并保留精确内容、批准、版本、成功不重放与真实容量边界。

测试探针自身的失败历史保留：首次 collection 导入不存在的测试异常名
`StagedBatchForwardFailed`，改用已有 `StagedBatchForwardError`；首次可执行 probe
**8 passed/3 failed** 记录在 `independent-native-round1.log`，其中两例未展开 native
`ok/data` envelope，stdio 自定义长 basetemp 超 AF_UNIX 路径长度。
仅改测试断言和短 `/tmp` basetemp 后 11/11 通过；不将这些 harness 问题归为产品或语义失败。
首轮 FAIL 结论保留。后续轮次优先复测以上三项，再做受修复影响回归；T012 保持未执行。

### 独立工程功能验收 Round 2 — PASS（工程范围）

时间：2026-10-09T05:00:37Z。复用首轮方案、测试文档和独立探针，没有新增方案或改产品。
稳定工作树核对 `product-baseline-round2.json` 的 `files` 中 32 个文件，全部摘要一致；
manifest SHA-256：`a3f4db0cc0386cdfaf3b217e4f3fe9f71f83782cf59a9ee341f0d9bececb303b`，
基线 commit `157c8becf2fa86cac73cf94bce335fe5d01e1fdd`。
对比 Round 1 只有六文件变更：Protocol instructions、capability_mcp、Codex runtime 以及
首轮三个失败测试文件；Runner、读引用处理、Judge packet/正文注册表、计时及 Delivery 未变。
未受修复影响的通过证据按原规则复用；本轮关注失败复测和相关原生权限/执行边界。

从 `backend/` 执行：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q \
  ../modeling_team/tests/test_r23006_lean_runtime.py::R23006LeanRuntimeTests::test_lean_acceptance_package_and_inventory_are_report_only \
  ../modeling_team/tests/test_r23006_lean_runtime.py::R23006LeanRuntimeTests::test_frozen_evidence_inventory_requires_explicit_boolean_opt_in \
  ../modeling_team/tests/test_staged_associate_evidence.py::test_staged_protocol_operation_set_pairs_submission_with_evidence_repost \
  ../modeling_team/tests/test_staged_associate_evidence.py::test_capability_endpoint_declares_and_dispatches_the_evidence_operation \
  ../modeling_team/tests/test_transport.py::TransportTests::test_transport_budget_splits_keep_review_and_exact_reference_projection \
  ../modeling_team/tests/test_v43_judge_references.py \
  ../workspaces/v4-3-engineering-20261009/independent_native_round1.py \
  --basetemp=/tmp/v43-ind-r2-20261009 \
  > ../workspaces/v4-3-engineering-20261009/independent-round2.log 2>&1
```

结果：exit 0，**31 passed、12 subtests passed**，9.58 秒。

| 项目/缺陷 | 本轮结果 | 证据 |
| --- | --- | --- |
| E43-TEST-01 | FIXED | 原 report-only Mock 断言保留通过；两 inventory checker 对 False/None/1/string/Mock 不授权原文入口，只有 True 增加 read；真实 native Judge factory/stdio 原文读取继续通过 |
| E43-TEST-02 | FIXED | 显式 legacy STAGED 与 UNIFIED 集合；legacy 活入口拒绝三个 unified 能力，unified 列表精确，退役 evidence repost 不复活；独立 native actor/path/批准漂移/恢复继续通过 |
| E43-TEST-03 | FIXED | 新断言覆盖完整 projection 及 rationale/depends_on/CQ fields、批准前按实际限制形成 successor、禁止执行工具重切批准投影、版本/审批及不重放；独立 dry 后批准漂移阻 apply、恢复与重试边界继续通过 |
| T001 | PASS / 复用+回归 | 核心代码未变，首轮计时合同证据复用，本轮真实 CLI 再过 |
| T002–T004 | PASS / 复用+回归 | Runner/引用解析未变；本轮独立 native 计划执行、权限、CQ freeze、失败恢复、关联 scope/摘要再过 |
| T005 | PASS / 复用+合同复测 | 核心 coverage/公开路径未变；Protocol 精确获批完整链及容量合同复测通过，首轮工程证据有效 |
| T006 | PASS / 复用 | Delivery 与计时代码摘要未变，保留首轮用户 priority/决策唤醒工程证据 |
| T007–T010 | PASS / 回归 | Judge 引用测试全部及独立真实 stdio/read receipts/重读复用/分组隔离再过；strict optin 修改无权限扩张或回归 |
| T011 | PASS | 主代理稳定版本全套 session 11260 exit 0，日志 team-regression-round2.log：2580 passed、11 skipped、316 subtests passed；首轮三失败窄复测全部 FIXED；链接/Skill证据复用、diff检查通过 |
| T012 | BLOCKED / 未执行 | 真实建模暂停，未恢复生产/验收/修复；完整语义 PASS 与120分钟仍无证据 |

本轮独立窄复测未发现新缺陷或 REGRESSION。初次 manifest 检查脚本按旧 flat map
读取新 `baseline_commit/files` envelope 出现 FileNotFoundError；修正只读检查读取 `files`
后 32 文件一致，属于检查脚本问题，未改 manifest 或产品。Round 1 FAIL 历史保持。

全 Team 终态已独立核对日志：**2580 passed、11 skipped、316 subtests passed**，
198.92 秒（288 条 rdflib deprecation warnings），session `11260` exit 0。准确命令为
`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`，
stdout/stderr 保留在 `workspaces/v4-3-engineering-20261009/team-regression-round2.log`。
结束后再核对 32 文件摘要，全部仍与 Round 2 manifest 一致。

独立工程结论：**PASS**，T001–T011 工程要求通过，E43-TEST-01/02/03 全部 FIXED，
没有新缺陷或 REGRESSION，无需继续工程修复。11 skipped 不是通过，不用其支持新需求；
本次核心验收边界由上列已执行 native/stdio/权限/失败/分组测试覆盖。
T012 继续 **BLOCKED / 未执行**；真实生产与独立语义运行仍暂停，不消耗额度，不读取或
修复保留 run。工程 PASS 不证明真实 27 题完整语义 PASS、无故障 ≤120 分钟或60分钟目标。
首条小链公开反馈的真实质量与效率收益同属待恢复授权后的运行证据。
