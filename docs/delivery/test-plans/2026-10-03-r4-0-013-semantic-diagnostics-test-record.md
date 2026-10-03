# R4.0-013 独立功能验证记录

## 需求、范围与通过标准

依据 [R4.0-013](../../requirements/requirements-v4.0.md#r40-013-语义验收分层诊断与-cq-题干评分范围对齐)
及 [已 PASS 设计 §7](../designs/2026-10-03-r4-0-013-semantic-diagnostics-design.md#7-验证计划与结论边界)，
复用该计划，不另设计语义验收流程。覆盖 A1—A6、A8—A10；A7 不在本次范围。

通过标准：机械合同检查通过；真实隔离 Judge 对受控 packet 的裁决与逐点 note 经独立人工核对符合输入；
宿主根据已有复核记录正确区分有效诊断与原因未确定。结构接受不代表诊断正确。

非目标：不创建／继续生产 run，不消耗 fresh semantic starts，不调用平台或追加诊断查询，
不修改产品代码、模型、历史冻结题／裁决，不宣称真实业务语义、盲测泛化或知识覆盖率 PASS。

## 环境及步骤

- 测试代码：`modeling_team/tests/test_r4013_semantic_diagnostics.py`。
- 从 `backend/` 使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest` 执行本文件及相关既有 CQ／runtime／CLI 回归。
- 真实 Judge 使用现有 `CodexRuntimeAdapter.run_v3_acceptance_child`、`openai-sol-medium` 配置、
  active v3 child 提示、`_CQ_JUDGE_ROLE_INSTRUCTIONS` 及真实 report-only MCP sink。
- 真实调用显式 opt-in：`R4013_LIVE_JUDGE=1`；原始 packet、verdict、teardown 与错误写入
  `workspaces/r4013-functional-tests/<轮次>/`。不将参考 verdict 或诊断标签注入 Judge。
- 在主 Agent 通知 stable-ready 后执行真实模型测试；逐点人工核对输出，不建立自动 note 解析器或语义裁判。

## 用例（复用设计 §7）

| 用例 | 步骤与输入 | 期望结果 | 对应验收 |
| --- | --- | --- | --- |
| C01 | 私有 CQ note 原样保存；带旧版本决定被拒后提交正确版本；正式 modify；公开投影检查 | 私有决定保留全文／digest，恢复可继续；note 不进入生产投影；冻结决定摘要算法不变 | A4、A9、A10 |
| C02 | 核对 active child 路径及 actual first-turn input，Consumer packet 检查 | Judge 用活跃提示及同步注入指令；Consumer 无答案点、依据及诊断，Judge 无读取工具 | A1—A6、A10 |
| C03 | 保留多因 note、待复核、skipped／未裁决、漂移及旧报告 | 原文保留；每题计一次；完整分母不缩小；待复核／缺裁决／漂移不 full_pass | A6、A8—A10 |
| J01 | 本题响应正确说明 202 仅受理，答案声称完成 | 未通过；Consumer 误解，不能声称相应知识缺失 | A1 |
| J02 | 响应将 202 表述为完成，与业务资料冲突 | 未通过；具体模型含义错误，不能说正确知识已返回 | A3 |
| J03 | 响应明示准确实体的全部规则表达及完整有界清单，缺少批准前提 | 未通过；仅该有界模型表达缺失，不推广全平台 | A3、A5 |
| J04 | 相关成功读取为空，无存在性旁证 | 未通过；原因未确定，不能从空结果定位模型缺失或 outage | A3、A6 |
| J05 | 资料与本题响应一致说明 SLA 尚未定义，答案明确未知 | pass | A3 |
| J06 | 202 题附加“本体平台不执行 API”必答点，但题意没要求 | question-answer-review；不能删点后 pass，不缩分母 | A4、A5、A9 |
| J07 | 题意清楚但答案点“退款两天内完成”无获准来源 | question-answer-review | A4、A9 |
| J08 | 三点分别有 Consumer 误解、模型错误、有限投影导致未知 | 同题逐点三种理由，仍只计一题 | A8 |
| J09／J10 | J09 相关空结果；J10 已保留相同业务相关正确含义 | J09 未通过；J10 仅作存在性诊断旁证，不能补入 J09 作答证据；不能反推不可见请求参数 | A2、A10 |
| J11 | 相同问题但 packet 内没有相应旁证 | 未通过；原因未确定 | A2 |
| J12 | 本题首次直接读取充分，后续空查询，最终答案仍错 | Consumer 漏用已有内容，不挑空查询归因纯检索 | A1、A2 |
| J13 | 工具执行失败导致无法作答，已有第一失败层 | platform-runtime-incomplete，保留 runtime/infrastructure | A6 |
| J14 | 获批问题问权限不足时能否判断；响应 forbidden，答案遵守拒绝 | 按题意 pass；拒绝不被误解为 outage／模型缺失 | A6 |
| J15 | 相关响应 partial／投影省略，答案无依据猜中 | 不 pass；原因未确定 | A6、A10 |
| J16 | 必答点已答，但主动错误声称本体平台执行外部 API，响应明确相反 | 未通过；Consumer 错误断言，保留必要边界 | A5 |
| H01 | 使用真实 J09 note，核对 Q09 和旁证 Q10 的 digest/path；两题 stable，无模型漂移 | 旁证可支持有限存在性／可发现性诊断，原 verdict 不提升 | A2、A10 |
| H02—H06 | 同题 stable，旁证分别 drift、unavailable、缺复核、引用不匹配；以及模型绑定漂移 | 保留原 note／verdict；说明证据资格未通过，有效归因原因未确定 | A2、A10 |

## 测试轮次

### Round 1（2026-10-03，BLOCKED）

代码基线：`ef66041` 加 R4.0-013 工作区修改；真实调用的具体提示原文在原始证据目录的
`prompt-snapshot.json`。新增测试代码仅属于本需求，未修改产品逻辑。

1. `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4013_semantic_diagnostics.py -q`：7 passed，1 live skipped，0.52 秒。
2. Ruff 首次发现复用 fixture 的 F811 命名问题；仅调整测试 fixture 导入方式，复测仍为 7 passed／1 skipped；`uv run ruff check ../modeling_team/tests/test_r4013_semantic_diagnostics.py` PASS。
3. 真实 Judge 已用显式 opt-in 启动；600 秒限时。证据根：`workspaces/r4013-functional-tests/round-1/`，结果待独立逐点复核。

CQ 人工检查的完整合成资料、题干、必答点及实际检查理由位于
`workspaces/r4013-functional-tests/round-1/cq-manual-cases.json`。
独立验证者按输入逐点检查：CQ-01 的点1／2均来自 §1且影响完成判断；点3虽来自 §2却超出题意，移出后由 CQ-04 明确检验执行主体。
CQ-02 的“两天”没有任何来源，正式修改为 §4的未知；CQ-03 的审批条件来自 §3，虽属隐含条件但决定退款能否开始，必须保留；
CQ-04 的两点来自 §2，题干直接要求，均保留。四类理由与输入一致，审核方法功能检查 PASS。
这项是独立人工语义复核；`test_private_review_note_round_trip...` 仅证明既有 note 传输、私有保存及 digest，不能代替该检查。

J04 实际 packet 同时保留其他关闭题的相关知识；因此允许 Judge 明确引用这些旁证作有限诊断，
不能将“必须未知”当作该输入的唯一预期。没有实体相关旁证的未知分支由 Q-11 金色任务检查，
紫色任务的事实不能仅凭相同 accepted/completed 词汇推广到金色任务。

主 Agent 返回既有 Team 全量回归：2181 passed、1 skipped、314 subtests passed，168.88 秒；
包含既有 partial_judging／CLI 的运行不完整跳过与部分判题检查。J13 是注入 packet 的 Judge 保留失败层功能反例，
不宣称生产路径实际会为 runtime-incomplete 题创建 Judge 裁决。

Round 1 真实命令：
`cd backend && env -u DEEPSEEK_API_KEY R4013_LIVE_JUDGE=1 R4013_EVIDENCE_DIR=/home/yangxiang/ontology-platform/workspaces/r4013-functional-tests/round-1 PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4013_semantic_diagnostics.py::test_real_judge_raw_verdict_collection -q -s`。

实际：1 failed，218.63 秒。`ExaminerRuntimeBlocked` 的展示文本是 `binding-rejected`，
实际退出分支 `reason_code=child-exited, reports=0`；并非 600 秒 deadline。16题均无模型裁决，
`verdicts.json=[]`，`teardown.json` 六项全部 true。第一阻塞层为 runtime/infrastructure，
不能判定 Judge 诊断质量或模型知识不足。首轮测试只保存包装错误，详细错误记录不足；第二轮补保存类型化异常／运行失败队列。

现场核对发现该工具启动环境无任何代理键；现存四个 Codex 进程的 http/https 代理均为
`http://127.0.0.1:1080`，该端口实际监听。现有 `_minimal_codex_process_env` 只转发已存在的白名单代理，
且代码已记录本机访问 chatgpt 需代理。仅修复测试命令的启动环境，不更改产品或提示。

Round 1 结论：BLOCKED；机械合同及 CQ 人工检查 PASS，真实 Judge 无裁决，H资格检查待有真实note。

### Round 2（2026-10-03，PASS：受控功能范围）

修复测试启动环境，仍使用相同模型、packet及提示；补类型化错误／运行失败队列持久化。
命令：
`cd backend && env -u DEEPSEEK_API_KEY http_proxy=http://127.0.0.1:1080 https_proxy=http://127.0.0.1:1080 no_proxy=127.0.0.1,localhost R4013_LIVE_JUDGE=1 R4013_EVIDENCE_DIR=/home/yangxiang/ontology-platform/workspaces/r4013-functional-tests/round-2 PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4013_semantic_diagnostics.py::test_real_judge_raw_verdict_collection -q -s`。

优先复测首轮被阻塞的16个真实 Judge 案例，再做宿主资格人工核对。

实际：1 passed，187.81 秒；真实 report-only MCP sink 接收 16/16 逐题裁决，
`runtime-failures.json=[]`，`teardown.json` 六项全部 true。首轮基础设施阻塞 FIXED。
这条 pytest 的 PASS 只证明真实输出完整收集；下面的独立人工逐点核对才建立诊断功能结论。

#### 真实裁决与输入一致性

输入：`workspaces/r4013-functional-tests/round-2/packet.json`；原始裁决：同目录 `verdicts.json`。
独立验证者已逐一核对16题的 source、完整 content_digest、locator、question_id、response_digest、
artifact_path，以及被引用字段／IRI与Consumer原句；全部与实际 packet 匹配，不推导不可见请求。
下面使用简称：M=`model-recall-insufficient`／`modeling-quality`，R=`question-answer-review`／null，
P=`pass`／null，I=`platform-runtime-incomplete`／`runtime/infrastructure`。

| 题号／用例 | 实际裁决与逐点说明 | 独立核对 |
| --- | --- | --- |
| Q-01／J01 | M；正确响应返回受理与完成区别，Consumer反说已完成，定位Consumer推理 | PASS |
| Q-02／J02 | M；响应与答案均错误，把202说成完成；明确模型表达错误候选、Consumer结论错误，不称正确知识已返回 | PASS |
| Q-03／J03 | M；仅 `urn:fixture:Refund` 的全部直接规则／前提等闭合清单缺批准条件；说明有界缺失候选，不称全模型缺失或稳定已验证 | PASS |
| Q-04／J04 | M；相关no_match不是outage／缺失证明；明确Q-01为诊断旁证、本题仍不通过、原始请求与稳定性未知 | PASS；实际旁证范围见首轮说明 |
| Q-05／J05 | P；资料、响应sla_status=unknown与Consumer显式未知一致 | PASS |
| Q-06／J06 | R；点2虽有来源但平台执行声明超出202题意；保留点1业务成功结果，不暗删点后pass | PASS |
| Q-07／J07 | R；两天时限与获准未知冲突，定位冻结答案问题 | PASS |
| Q-08／J08 | M；点1Consumer误解，点2模型错误加Consumer错误，点3partial投影缺保留期限、原因未知 | PASS；逐点多原因完整 |
| Q-09／J09 | M；本题no_match，Q-10 Purple正确含义仅作诊断旁证；明确两题资格待宿主核对，不能以共享绑定放行 | PASS |
| Q-10／J10 | P；本题真实响应支持Purple受理与完成区别，Consumer等义回答 | PASS |
| Q-11／J11 | M；Gold无对应旁证，原因未知；明确Purple不能证明Gold存在性 | PASS |
| Q-12／J12 | M；本题初次充分读取、后续空结果不能抹除已读知识，定位Consumer证据整合 | PASS |
| Q-13／J13 | I；保留runtime阻塞与原第一失败层，不作模型知识结论 | PASS；仅注入packet功能，生产skip见既有回归 |
| Q-14／J14 | P；题意询问权限不足能否确认，遵守forbidden正是获准正确答案，未扩权限 | PASS |
| Q-15／J15 | M；答案猜中，但自身partial投影没有前提；未知根因，不能根据参考答案或Q-03空清单证明知识返回 | PASS |
| Q-16／J16 | M；必要点虽正确，主动错误宣称平台执行API仍失败；定位实际错误原句和正确响应，Consumer错误 | PASS |

原始16题端到端分布：P 3、M 10、R 2、I 1；每題恰计一次，Q-08的三种理由不增加题数。
这是合成功能反例的分布，M 10不是模型缺失数，也不能换算知识覆盖率或真实业务通过率。

#### 宿主证据资格人工核对（H01—H08）

资格输入位于 `workspaces/r4013-functional-tests/round-2/host-qualification-fixtures/`；
它们是合成“已有报告”反例，复用真实Q-09的原 note／verdict／响应，未调用平台、未做实际状态复核。
`host-fixture-provenance.json` 明确记录合成前后完整绑定与来源：
原 Judge packet 的固定合成状态 digest 为
`sha256:f560c9f533f92236dfef22773e66fc8a18ca16d2063869acad2054e9902e1104`；
host fixture 的完整绑定 digest 为
`sha256:dd6b207c7c6da73abc4dafec0a6dfc483d8aa7d56fe2f83587118d78b0d9f3c7`。
这些分别代表两种合成输入，不能冒充原真实平台report或称Round2平台状态已验证stable。
既有CLI前后实际绑定机制由Team回归另证。

人工定位真实 Q-09 note 的两个引用：

- 本题 Q-09，`response_digest=sha256:2baa134997a7d32b55e54c1e5abd839fdeac2e667c0d5a5e7f78c14d591e8989`，
  `artifact_path=acceptance/r4013-controlled/platform-read/Q-09/0.json`，内容为相关no_match。
- 旁证 Q-10，`response_digest=sha256:2e0d4b92ab68277ea50c156a093c31c0b61d01656ef60af0b1564f25b21f2433`，
  `artifact_path=acceptance/r4013-controlled/platform-read/Q-10/0.json`，
  `result.semantics`／`urn:fixture:Purple` 表达受理不等于完成。

逐项按活跃runbook核对，无自动note解析器。所有fixture中原Q-09裁决仍为M，原note逐字保留：

| 资格用例／文件名 | 实际既有记录输入 | 宿主交付说明与有效归因 | 结论 |
| --- | --- | --- | --- |
| H01-stable | 两个引用唯一匹配；Q-09与Q-10均stable，相关drift／unavailable空；完整前后fixture绑定相同且无漂移 | 证据资格通过；仅在合成稳定状态中，Purple含义存在且本题未取得，支持检索／可发现性相关候选；原请求未知，不能声称实现bug或升级本题pass | PASS |
| H02-corroboration-drift | Q-09 stable，Q-10 drift且明细含该响应 | Judge原诊断仍是检索候选；证据资格未通过：旁证漂移；有效归因原因未确定 | PASS |
| H03-corroboration-unavailable | Q-09 stable，Q-10 platform-runtime-incomplete且unavailable含旁证 | Judge原诊断保留；证据资格未通过：旁证复核不可用；有效归因原因未确定 | PASS |
| H04-missing-recheck | 两个引用仍匹配，但整个evidence_recheck缺失 | Judge原诊断保留；证据资格未通过：缺复核记录，共享digest不能兜底；有效归因原因未确定 | PASS |
| H05-reference-mismatch | Q-10路径存在但报告中的digest替换，与原note不匹配 | Judge原诊断保留；证据资格未通过：引用不能唯一匹配；有效归因原因未确定 | PASS |
| H06-model-binding-drift | 两题响应stable，但后绑定graph_state变更，漂移记录含ontology-1 | Judge原诊断保留；证据资格未通过：前后模型绑定漂移；有效归因原因未确定 | PASS |
| H07-status-stable-but-drift-detail | question_status仍stable，但drift明细含Q-10响应 | Judge原诊断保留；证据资格未通过：复核明细有冲突，不能只读stable标签；有效归因原因未确定 | PASS |
| H08-missing-corroboration-status | 有复核记录但缺Q-10状态 | Judge原诊断保留；证据资格未通过：旁证状态缺失；有效归因原因未确定 | PASS |

H02—H08仍可表述“原Q-10响应当时包含受理不等于完成”，不能由此交付稳定模型存在／缺失已定位。
该矩阵证明runbook人工资格方法及交付口径的功能可执行性，**不证明任何实际平台读取stable**。

Round 2 结论：PASS（A1—A6、A8—A10 的受控功能／合同范围），0 产品缺陷；
删除实际旁证的同题独立变体继续在下一轮验证，不覆盖本轮原件。

### Round 3（2026-10-03，PASS：删除旁证反例）

针对Q-09实际删除Q-10以及所有其他题，同步过滤questions、examiner_reports、evidence_bundle与
platform_read_responses，并根据新问题集重算freeze_digest；提示、模型与本题来源／答案／响应相同。
没有向Judge注入“预期未知”的提示。

命令：
`cd backend && env -u DEEPSEEK_API_KEY http_proxy=http://127.0.0.1:1080 https_proxy=http://127.0.0.1:1080 no_proxy=127.0.0.1,localhost R4013_LIVE_JUDGE=1 R4013_LIVE_CASE=without-corroboration R4013_EVIDENCE_DIR=/home/yangxiang/ontology-platform/workspaces/r4013-functional-tests/round-3-no-corroboration PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4013_semantic_diagnostics.py::test_real_judge_raw_verdict_collection -q -s`。

实际：1 passed，34.43 秒，1/1真实裁决。原始packet／note／teardown位于
`workspaces/r4013-functional-tests/round-3-no-corroboration/`，未覆写Round1／2。
Q-09仍为M，其note明确原因未确定，完整分页／结果标记不证明有界语义覆盖，
没有原始请求、旁证或状态复核，不能证明Consumer收到正确知识却漏用，也不能定位模型缺失。
独立核对来源摘要、locator及本题响应摘要／路径均与packet相符，未引用已删除Q-10。
teardown六项均true、runtime-failures空。该用例 PASS，无REGRESSION。

最终结论：**PASS：R4.0-013本次授权功能／合同范围**。A1—A6、A8—A10已验证，
A7真实业务语义验收未执行，不可宣称真实业务模型／盲测泛化／知识覆盖率PASS。
fresh semantic starts消耗0，平台写入0，额外诊断平台查询0。无需产品修复后复测。

最终代码验证（去旁证variant及类型化错误观测已落入测试后）：相同focused pytest命令
7 passed、1 opt-in live skipped，0.53秒；相同Ruff命令PASS；测试记录本地链接／围栏与
本次两份文件的scoped `git diff --check` PASS。没有扩展平台测试、修改产品文件或提交。
