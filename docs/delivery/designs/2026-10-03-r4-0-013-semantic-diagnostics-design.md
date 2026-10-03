# R4.0-013 语义验收分层诊断与 CQ 必答点质量检查设计

## 1. 状态与设计范围

- 权威需求：[R4.0-013](../../requirements/requirements-v4.0.md#r40-013-语义验收分层诊断与-cq-题干评分范围对齐)。
  D1—D9 的决策及来源以该条目为主记录。
- 用户已确认方案 A：只分析已有证据，证据不足保留原因未确定；CQ 生成后、冻结前的
  必答点质量检查并入现有审核。设计阶段授权详细设计、独立审阅及修订至方案 PASS；
  后续已授权按设计开发与测试。
- 核对基线：`9e7ff41`，2026-10-03。工作区已有其他任务的 Consumer 提示、Task、
  host_ops、测试和宿主 runbook 修改；本设计按当前实际入口说明衔接，不接管在途改动。
- 设计完成；独立审阅 Round 1 的 H013-01 已修订，Round 2 PASS（0 Critical／0 High）。
  审阅记录见 §8。2026-10-03 已实施，A1—A6、A8—A10 独立功能验证 PASS，见
  [交付记录](../records/2026-10-03-r4-0-013-semantic-diagnostics-delivery-record.md)及
  [测试记录](../test-plans/2026-10-03-r4-0-013-semantic-diagnostics-test-record.md)。
  A7 真实业务语义验收未授权、未执行，需求整体 PARTIAL。

例如，“202 是否证明工单关闭”可以要求说明受理与业务成功的区别；不能因答案没复述
“本体平台不执行 API”就失败。但若 Consumer 把 202 解释为已关闭，仍需失败，并依响应
区分模型表达错误与 Consumer 理解错误。检查题意不等于放宽必要业务语义。

最小方案：在现有 CQ 私有审核 `note` 记录逐点检查，在 Judge 的逐题 `note` 记录有依据的
诊断，在宿主报告中解释粗粒度结果。沿用当前 JSON 字段、四态裁决与四层失败枚举，不增加
诊断服务、角色、查询、报告解析 DSL 或平台数据结构。

## 2. 实际入口与证据流

| 环节 | 当前入口及已核对行为 | 本次增量 |
| --- | --- | --- |
| CQ 起草 | [起草 Skill](../../../modeling_team/skills/competency-question-authoring/SKILL.md)与[角色指令](../../../modeling_team/agent-packages/competency-question/instructions.md)已有来源、未知、公开／隐藏及版本合同 | 增加生成后逐点检查方法；用草稿已有 `note` 汇总检查说明 |
| 用户审核 | [host_ops_mcp.py](../../../modeling_team/host_ops_mcp.py)的 `tool_submit_cq_review` 已接收 `note`；[runner.py](../../../modeling_team/runner.py)的 `_handle_cq_review` 将完整决定写入私有 `decision-*.json` | 宿主按授权记录审核理由；不加新审核状态或必填字段 |
| 公开投影／冻结 | [competency_questions.py](../../../modeling_team/competency_questions.py)的 `public_projection` 不投影审核 note；`validate_review_decision` 绑定当前 review/version/digest | 复用隔离及版本校验，检查说明不传生产角色 |
| 平台作答 | [Platform Examiner](../../../modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md)已有答案、显式未知和响应 handle；工作区已有通用作答组织增量 | 只补齐本需求尚缺的条件／未知／无关声明边界，避免重复既有段落 |
| 响应取证 | [__main__.py](../../../modeling_team/__main__.py)的 `_cq_collect_platform_read_responses` 核对已引用回执；`_cq_recheck_evidence_responses` 复核原读取 | 原路径保留，不扫描未引用记录，不新增诊断补查 |
| Judge 输入 | [acceptance_runtime.py](../../../modeling_team/acceptance_runtime.py)的 `AcceptanceBatchPacket` 与 `_validated_platform_read_responses` 接收题目、业务依据、答案、逐题真实响应 | 输入结构不变，明确来源资料与平台响应各证明什么 |
| Judge 提示 | [__main__.py](../../../modeling_team/__main__.py)的 `_CQ_JUDGE_ROLE_INSTRUCTIONS` 和[实际 child 提示](../../../modeling_team/agent-packages/v3-acceptance-batch/acceptance-judge.md)同时生效 | 同步题意审核、裁决含义和逐点诊断要求 |
| 保存与收口 | `validate_acceptance_verdict`、`build_batch_report` 原样保留 note；`batch_report_is_full_pass` 和 CLI 保留完整分母／漂移／未裁决边界 | 保持算法和摘要机制；宿主交付解释结果与诊断 |

流程为：CQ 私有草稿及检查说明 → 用户审核决定及 note → 获批公开投影／冻结题池 →
独立 Consumer 查询与答案 → 宿主已有回执核对及状态复核 → 独立 Judge 裁决与诊断 note →
私有 batch-report.json → 宿主向用户交付汇总。诊断不回流生产角色或 Consumer。

`CodexRuntimeAdapter._child_package_assets(v3_batch=True)` 实际选择
`v3-acceptance-batch/acceptance-judge.md`；旧目录
`agent-packages/acceptance/instructions-v3.md` 不作为当前 child 的唯一修改入口。
当前 Task 挂载的 R3 CQ 合同也要同步文字含义，避免活跃语义说明冲突。

## 3. CQ 检查与审核记录

### 3.1 谁检查，何时检查

CQ 在提交 panorama-review／slice-review 前，逐题逐必答点自查；宿主在向用户提交审核
或根据已有明确代审授权记录决定时，按同一标准复核。自查不等于用户批准，没有代审授权
时仍等待用户决定。用户已经批准的范围和分组继续适用，不新增二次批准环节。

检查三项：获准依据；题干明确要求或正确回答所必需；遗漏产生的业务影响或范围违背。
资料中出现某句话不自动成为每题必答点。必要隐含条件如审批前提继续保留；若要检验执行
主体等独立方面，题干应明确，或在现有覆盖范围内另设专项问题。

### 3.2 存在哪里，如何修订

- CQ 草稿既有 `note` 为文本，可按 `question_id / answer_points 的一基序号` 说明检查。
  同一内容版本内的位置足以定位，不新增答案点身份表；重排答案点按新内容版本重新引用。
- 宿主将最终逐点结论写入 `submit_cq_review.note`。必要内容是答案点、来源定位、题意
  对应、保留／修改／移出及理由；可合并具有相同依据的点，但不能漏掉某个必答点。
- `note` 不含机器标记硬门，不解析为评分规则，也不新增自动语义合规校验。格式疏漏可
  通过现有 CQ 修订／审核反馈恢复；缺少检查记录不得在人工交付时宣称该质量检查已完成。
- 内容修改复用 `modify`／`supplement` 及 `modified_question`，绑定真实 review 版本；
  CQ 重新发布时生成新的 review 快照。`approve` 不能暗中附带未经确认的答案修改。
  仅记录理由不改变题目；修改内容必须走现有正式决定，不以 note 覆盖被冻结文本。
- 理由存入私有 `competency-questions/reviews/decision-*.json`，已有记录全文 digest
  覆盖 note。`review_decision_digest` 的冻结决定摘要当前不含 note；本期不改变该算法，
  不把说明文字声称为新的冻结评分内容。评分依据仍是冻结题目、答案点和获准来源。
- 生产公开投影保持原字段。隐藏题检查理由不得进入 scenario-map、共享事件正文或生产
  消息；现有共享记录只用 ID、摘要、状态和路径。

说明示例（文本示意，非新增 Schema）：

```text
Q-01 / answer_points[1]：保留；依据 source-X 的受理定义；题干直接问是否完成。
Q-01 / answer_points[2]：保留；依据 source-X 的成功判据；说明怎样判断完成。
Q-01 / 原 answer_points[3]：移出本题必答范围；执行主体不在题意内。
平台执行边界仍由已批准的专项检查覆盖。修订内容见 modified_question。
```

上述示例已公开，仅可用作合同测试说明，不算新的隐藏业务题。

## 4. Judge 的判定与诊断

### 4.1 输入范围与方案 A

Judge 仅使用实际 packet 内已核对的资料，不请求读取、不读宿主文件、不调用新 Agent。
`evidence_bundle` 证明业务预期，`platform_read_responses` 证明平台实际返回内容；
Consumer 自报答案、IRI 和 `collaboration_context` 都不能代替平台语义证据。

每题正式裁决只使用其已绑定且业务相关的响应。为诊断“知识存在但本题没取到”，可核对
同一 packet 中另一题已保留的相关响应：只能作为原因说明中的旁证，必须明确原 question_id、
响应摘要、相关内容和本题没有取得的区别；不能把它补进本题 evidence_refs、补写 Consumer
答案或据此给本题 PASS。packet 共用同一 model_binding_digest，但这本身不证明逐题读取
复核稳定；既有 evidence_recheck 不在 Judge packet 中，Judge 不能自称检查过它。
Judge 对平台模型状态的诊断先作为候选说明，宿主必须按 §5 的确定性资格核对后才能向用户
交付为有效归因。其他批次或宿主额外找到的响应不注入；没有这种已有证据时保留未知。

同一题此前的直接读取已完整返回所需知识，后续查询虽漏掉它，但最终答案仍遗漏时，诊断
Consumer 漏用已有内容；不能只挑选空查询声称纯检索问题。要指出查询参数或确切路径错误，
必须有可见依据；现有响应投影只有 request_digest、tool、page、result，不含原始 request，
故不能从摘要反推搜索词／过滤条件或把未见关系断言为关系未建。

方案 A 禁止新增为定位根因而发起的读取；R3.0-012 既有原请求重放和模型状态复核仍执行，
用于保证证据稳定，不算新增诊断补查。复核所得内容不替换 Examiner 当时收到的原响应。

### 4.2 顺序与四态映射

宿主已存在的 judgeable 子集筛选继续适用：没有 Examiner 报告、实际 runtime-incomplete、
来源无法解析或没有可信响应时，保留 `sessions.question_judging.skipped` 及原报告，不伪造
Judge 裁决。其他可判断题继续；缺裁决不能获得整批 PASS。

进入 Judge 的题目按下表处理。某点诊断不覆盖已有运行第一阻塞层；若多个问题并存，在 note
全部说明。存在实际阻断、使题目无法有效判定时优先保留运行／路由状态；证据可用但评分
范围本身有问题时用待复核；其余再判答案是否满足。

| 条件 | verdict / failure_layer | note 的诊断含义 |
| --- | --- | --- |
| 有效题目，答案含全部必要含义，并获本题真实响应支持 | `pass` / null | 简述支持理由；获准资料及响应支持的未知也可通过 |
| 答案遗漏、误解或断言错误；或相关成功读取未支撑必要回答 | `model-recall-insufficient` / `modeling-quality` | 粗粒度表示端到端语义消费未满足；逐点区分模型、检索、Consumer 和原因未确定 |
| 来源不支持答案点，或题意没有要求附带必答义务／存在关键歧义 | `question-answer-review` / null（纯题目问题） | 记录具体评分点及题意冲突；不擅自删点后判 pass |
| 实际工具、执行或证据路由失败阻断有效判定 | `platform-runtime-incomplete` / 既有第一失败层 | 保留观察到的阻断，不解释成模型知识缺失 |

需要修改 Judge 现有“successful relevant read showing a semantic gap”的说明：相关读取
成功而答案错误也属于端到端未满足，不要求先证明模型存在语义缺口。固定枚举及映射不变；
只有自然语言含义和诊断要求调整。成功但无关或错绑的响应仍按原路由错误处理；相关查询
的空结果不自动算路由故障。有响应但答案猜中了参考答案、响应无法支持时仍不能 PASS。

有效相关读取不充分时可以得出“本次问答未满足、根因未确定”；不能用原因未知逃避端到端
结论。反之，有依据的业务未知可能正是正确答案，不能机械判失败。

### 4.3 note 的最小内容

每个未满足点或重要错误断言分别写入：

1. 答案点位置及必要含义；非答案点中的错误以答案原句定位。
2. 题意对应及获准依据（source、content_digest、locator）。
3. 对应答案内容和实际响应依据（question_id、response_digest、artifact_path、必要的
   result 内字段／IRI／短摘录）；引用 packet 真实值，不发明 handle 与摘要对应关系。
4. 诊断：Consumer 作答、检索／可发现性、模型错误、模型缺失、题目待复核或原因未确定。
   这是人读说明，不注册新枚举；可并列不同因素。
5. 已证明范围与限制；指向应核对的环节，不把建议写成已经定位的根因。

模型缺失只有在已有证据确实完整覆盖相应有界范围时才成立；分页完整标记本身不证明查询
语义覆盖了全部目标。原始请求不在 packet，无法建立范围时使用未知。错误响应不算正确
知识已返回；需要保留模型与 Consumer 可能同时存在的问题。

例（note 文本示意，尖括号为实际 packet 值占位，不可直接当回执提交）：

```text
端到端：未满足。必答点 1 要求区分受理与完成；题干直接询问关闭是否成功。
依据：source=<source>，content_digest=<source digest>，locator=<locator>。
Consumer 回答“已经关闭”；本题响应 response_digest=<response digest>、
artifact_path=<retained path> 的 result.<字段位置> 说明该状态仅表示受理。
诊断：Consumer 误解。该点的平台含义已正确返回；未据此证明其他模型部分完整。
```

裁决 JSON 的七个字段、报告 schema_version、`conflicting_evidence` 原有合同均不变。
不把 note 改为 JSON 字符串 DSL，不根据诊断标签自动决定 pass，也不加语义关键词硬拒绝。
独立功能验证要实查说明与证据的一致性；结构接受不代表诊断正确。

## 5. 汇总、权限及历史

`build_batch_report` 原样保留逐题 note；现有 `summary_by_scope` 继续按 verdict 计题，
本期不新增自动诊断计数器。宿主从保留的 batch-report 交付用户时，列出：

- 应验收／已执行／有效裁决／通过题数、待复核、未完成和覆盖缺口，按现有批次范围解释。
- “端到端语义消费未满足”及对应的原始 `model-recall-insufficient` 名称；明确其不是
  已证明模型缺失数，不能换算知识覆盖率。
- 每个未通过题的答案点诊断和证据定位；多个因素不重复计题。没有诊断证据时列未知。
- skipped、模型漂移和读取复核失败来自宿主原记录；没有 Judge 的题明确无语义裁决。

无需新增自动 Markdown 导出器。汇总由现有宿主交付职责承担，写法固定在
[modeling-dev-loop runbook](../../../skills/modeling-dev-loop/references/team-runbook.md)。
宿主按 Judge 原理由整理；发现诊断缺失／语义矛盾时记录缺口，不代改其根因或旧裁决。
对诊断依赖的平台证据，交付前执行以下确定性资格核对，属于已有记录读取，不调用平台：

1. 从 note 中定位本题以及每个旁证的 question_id、response_digest 和 artifact_path，
   在原报告的 platform_read_responses 中匹配；引用缺失或无法唯一定位时，诊断资格未确认。
2. 核对 report.evidence_recheck.question_status：本题和每个被引用旁证题均须为 stable；
   同时核对 drift／unavailable 明细不得含这些题或响应。缺少复核记录、状态缺失、drift
   或 platform-runtime-incomplete 都不满足，不能仅凭同一个 model_binding_digest 放行。
3. 同时沿用报告的模型状态漂移／前后绑定核对；有漂移或核对失败时不确认稳定模型归因。
4. 不满足资格时，在宿主交付说明中列出“Judge 原诊断：…；证据资格：未通过，原因：…；
   有效归因：原因未确定”。这是否定证据资格，不另作语义裁决；batch-report 原 note、
   原 verdict 和原始响应全部保留。可继续陈述“原响应当时包含某句话”这样的历史观察，
   不能据此声明稳定模型存在／缺失或交付相应根因已定位。

本期不增加自动 note 解析器；宿主按可定位引用检查，并由独立功能验证检查交付记录。
同题稳定而旁证漂移／不可用时，只使依赖该旁证的归因无效，不用别题的正常结果替它兜底。
后续复审或修题仍按原授权／版本规则另留记录，不能就地覆盖首次发布的 batch-report。

原有回执、schema、tool allowlist、状态复核及全量通过门保留。隐藏诊断和审核理由是私有
验收资料，只向获准用户／验收方交付；不能把当前建模角色当接收方。公开反馈归 015。
旧报告不回填 note、不批量重算；旧例诊断另标非盲回归及其原始版本。

## 6. 实施触点与交接顺序

已按后续开发授权落实下列最小差异，验证及边界见上述交付记录；不改变已审阅方案的行为范围。

| 文件／入口 | 计划修改 | 验证重点 |
| --- | --- | --- |
| `modeling_team/skills/competency-question-authoring/SKILL.md` | 三项检查、草稿 note、修订范围 | 公开／隐藏均检查，必要条件不能删 |
| `modeling_team/agent-packages/competency-question/instructions.md` | note 按题／答案点定位及私有边界 | 不新增字段或代批权限 |
| `skills/modeling-dev-loop/SKILL.md`、`references/team-runbook.md` | 审核记录职责及结果／诊断汇总口径，入口短说明指向 runbook | 不吞掉现有在途修复，不触发新建模 |
| `modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md` | 在已有通用作答合同上补剩余差异 | Consumer 不接触答案点或隐藏审核理由 |
| `modeling_team/agent-packages/v3-acceptance-batch/acceptance-judge.md` | §4 判定与 note 内容；已有响应与题意复核 | 只读、逐点、多原因、未知、跨题旁证只用于诊断 |
| `modeling_team/__main__.py::_CQ_JUDGE_ROLE_INSTRUCTIONS` | 同步实际注入指令的题意和判定含义 | 不改变 packet、查询或生命周期代码 |
| `modeling_team/references/r3-0-011-competency-question-contract.json` | 仅规则说明同步粗粒度判定含义及诊断边界 | 字段、枚举、Schema 版本不变，旧报告可原样读取 |
| `modeling_team/agent-packages/acceptance/instructions-v3.md` | 同步新 v3 使用时的含义，避免残留冲突说明 | 不改 R2.3 per-question 提示／证据 |
| `modeling_team/tests/` 中 CQ、batch runtime 与 009 合同测试 | 增量覆盖活跃装载、note 往返、隔离及保留裁决边界 | 见 §7；具体新增测试文件随现有组织放置 |

`runner.py`、`competency_questions.py`、`report_sink_mcp.py`、`acceptance_runtime.py` 是复用
和验证入口，本方案不需要改执行逻辑。也不改 Task 的问题集、场景资料、历史冻结或生产模型。
先同步提示与规则说明，再验证实际 child 装载和现有数据往返，最后交独立功能验证；发现代码
实际不支持上述合同才修最窄缺口，不能顺带升级报告框架或扩大到补查方案 B。

## 7. 验证计划与结论边界

| 范围 | 验证方式与关键反例 | 对应验收 |
| --- | --- | --- |
| CQ 检查内容 | 对有依据但题意未要求、题意要求但无依据、必要隐含条件及相关专项边界四类案例，独立检查保留／修订理由 | A4、A5 |
| 审核记录往返 | 在已有 CQ lifecycle 测试中验证 note 原样保存在私有决定、旧版绑定被拒绝且可修正、公开投影无隐藏理由；决定摘要原逻辑不变 | A4、A9、A10 |
| 实际提示装载 | 验证 v3 child 选择正确文件且 `_CQ_JUDGE_ROLE_INSTRUCTIONS` 同步；Consumer 输入没有答案或诊断 | A1—A6、A10 的合同覆盖 |
| 诊断语义 | 用获准受控 packet 实际让 Judge 判题，再由独立验证者逐点对照响应检查；覆盖响应正确却漏答、模型响应错误、完整有界缺失、空结果未知、业务未知正确、附加评分义务 | A1—A6、A8 |
| A2 可达性与资格 | packet 内另一题已保留相关知识，本题只得到相关空结果；两题复核均 stable 时可作为存在性旁证，本题仍不得 PASS。删除旁证后只能未知；本题 stable 而旁证 drift／unavailable、复核缺失、引用不匹配时，宿主须保留原 note 并明确归因无效／原因未确定；本题已充分取得知识时定位 Consumer | A2、A8、A10 |
| 证据／汇总回归 | 复用 report/CLI 测试验证 note 原样保留、多原因不多计题、skipped 保留、待复核阻止 full_pass、漂移／不可信回执不出 PASS、相关空结果不假冒 outage | A6、A8—A10 |
| 真实语义效果 | 后续获准真实批次对照来源、保留响应、Consumer 答案和 Judge 诊断，记录实际出现的类别及无法定位部分 | A7，单独授权和取证 |

受控语义 packet 使用合成资料或已公开的历史例，不伪装成新隐藏题。实际模型调用与独立
功能验证已在后续授权实施／测试阶段完成并另留上述记录；纯静态断言和脚本返回预设 verdict
只证明合同或
传输，不证明 Judge 能正确诊断。功能案例不要求新建生产 run，不增加 semantic start。

实施后运行相关 CQ、CLI、runtime、009 合同及隔离回归；改活跃 Skill 时运行仓库可用的
Skill 校验。只修改 Team 提示／代码不触发 backend/frontend 全套测试或服务重启要求；若
实际改动超出此范围，按对应仓库规则执行。临时测试文件完成后删除，正式验收记录保留。

## 8. 独立方案审阅与文档检查

用户已授权独立审阅并修订至 PASS。本节记录每轮实际结果；方案审阅不运行产品测试、
不修改模型或验收原件，不代表功能和真实语义验收通过。

| 轮次 | 结论 | 问题与处理 |
| --- | --- | --- |
| Round 1 | REVISE，0 Critical／1 High | H013-01：Judge packet 不含读取复核结果，原方案无法保证旁证稳定。§4.1／§5／§7 及需求 D9 补宿主确定性资格核对、无效诊断呈现与反例 |
| Round 2 | PASS，0 Critical／0 High | 同一独立 plan_reviewer 确认 H013-01 FIXED，现有报告足以支持资格核对，无新增查询／权限／Schema；无待确认关键假设 |

审阅 Agent：`/root/r4013_plan_review`，两轮均于 2026-10-03 完成，只读审阅，未修改文件、
运行产品测试或启动服务。设计阶段 Round 2 后只回填审阅结果与需求状态，没有追加行为变更。
文档检查：本地链接／锚点、D1—D9／A1—A10 编号、围栏及 diff 检查已通过。
