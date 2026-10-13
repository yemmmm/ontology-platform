# 两次建模复盘后的修复与优化验证

日期：2026-10-13。修复前基线：`752f6e5`。开始时只有用户无关未跟踪目录
`docs/presentations/`；本次不修改、不暂存该目录。

授权：用户要求调用modeling-retrospective重新复盘最近FlashX/Luna两次任务，随后明确
“对于已识别简易问题，请直接调用子agent完成修复”。该增量允许窄工程修复与验证，
不恢复已撤销的生产/验收运行、不新增semantic start、不改变冻结或原裁决。

权威范围：R3.0-011/012/016、R4.0-018/021/023、R4.3-003/005/006/007/013。
具体定位与原件见[复盘](../modeling-retrospectives/2026-10-13-two-task-retrospective.md#第二次复盘已识别问题逐项定位)。

## 改动与开发验证

| 责任范围 | 最小变更及保留边界 | 子Agent定向验证 |
| --- | --- | --- |
| Runner resolution | Coordinator provider defer在已有relay/settlement之后报告；真open、未知写入、原typed错误/异常原因保留，abort沿同路径 | provider wait 40 passed；resolution/self-resume 12 passed；transport 32 passed/7 subtests；issue escalation 20 passed |
| Host pending/CQ | 指导持久化不直接闭合pending，消费实际resume/abort证据；CQ revision默认1且可选，保留真实版本/摘要/题目/run校验，旧wire字段仍存在 | 首轮相关Host/CQ/MCP 148 passed；显式abort遗漏修后定向22 passed/59 deselected，错issue/epoch反例保持pending |
| Delivery启动拒绝 | 明确repair启动前拒绝释放新登记owner；Host已有操作、未知异常/丢失回执、已发生launch失败仍保留 | 首轮session 22 passed；ops/wakeups 36 passed。input_path_invalid遗漏修后session 23 passed |
| CQ响应复核 | 仅屏蔽query_semantic_context的recall.ranking.cache_hit布尔元数据，支持bare/API封套；其他ranking/事实/身份/分页/范围和同名业务字段继续比较 | response 55 passed；R3.0-012相关164 passed；R3.0-011/CQ相邻198 passed；Ruff通过 |
| 必需关系身份 | 指引复用applied Attempt item的真实resource_outputs.resource_iri，再沿既有定点SPARQL；dry-run/Batch预分配不能作已应用身份，不新增allowlist/API或常驻全量复核 | identity/contracts/R4.0-009 59 passed/3 subtests；JSON/Ruff/diff检查通过 |
| 验收freeze身份 | 已冻结snapshot文件stem与batch ID沿同源内容绑定衔接，handoff真实digest消歧；不重冻、不重新签名、不猜不一致冻结 | delivery ops 17 passed；stem/batch、错误digest、歧义及同源消歧反例通过 |

上述是子Agent开发验证；不同命令覆盖重叠，不相加成总测试数量，也不是新增独立功能
验收或真实业务语义PASS。

## 主Agent复核与交叉审阅

主Agent检查最终diff和实际调用点。另一子Agent只读交叉审阅Host/Delivery修复，发现：

1. Runner显式abort写issue-abort而不走通用issue-control记录，首版pending修复遗漏该
   真正终态，仍会误报issue_wait；退回原Host修复者处理，原发现保留。
2. repair启动前resolve_repo_path的input_path_invalid也是明确零执行拒绝，首版修复未
   消费该code，仍会形成phantom owner；退回原Delivery修复者处理，原发现保留。
3. 主Agent检查中另排除了delivery_operation_exists从owner移除列表：同一Host ID可能
   已有真实进程，即使本Delivery首次登记也不能当未启动。最终反例保持该身份。

CQ默认序号及真实content_version/digest校验的兼容审阅通过。审阅未读取隐藏题、答案
或私有裁决，不替代独立语义验收。

GitNexus对validate_review_decision返回CRITICAL（110影响符号、96流程、20模块）。
已向用户明确告警；实际该函数只改说明/注释，既有校验逻辑字节行为保持，真正行为变更
位于Host参数默认值及pending说明。图的广域风险不能忽略，也不能当作本次改了全部
平台流程；本次以直接调用点、兼容反例和完整Team回归核实局部变更。Runner当前方法
未被图解析，使用源码调用检查，不声称完整图覆盖。

## 最终验证

Round 1完整Team回归退出1：**2783 passed、1 failed、11 skipped、318 subtests passed**，
249.49秒。命令从backend/执行：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q
```

原日志：[Round 1](../../../workspaces/v4-delivery-20261013/retrospective-team-regression.log)。
失败为test_r30008b_runner_wiring的CQ runtime工具面断言：先前3604f22已把四个获准
handoff工具加入实际工具面，测试仍只断言cq_publish_question_draft。本次未改codex
runtime；按原合同/历史变更核对后由子Agent修正过期精确断言，保留未选角色与旧任务
权限边界，不删工具面检查。Round 1原日志不覆盖，最终复验另存。

核对3604f22及其父版本确认该旧断言已经过期；仅将该fixture的CQ runtime期望改为
已导入的CQ_OPERATIONS，真实socket也正是该工具集合。相邻五文件复验102 passed、
55 subtests passed；无handoff时仍只有单一CQ能力、额外工具fail-closed的覆盖保留。
新增diff仅一行测试期望，未修改codex runtime或生产工具面。

Round 2完整Team回归退出0：**2784 passed、11 skipped、318 subtests passed**，250.70秒；
356条既有rdflib弃用warning，跳过项不计为通过。使用上述同一命令，新日志为
[Round 2](../../../workspaces/v4-delivery-20261013/retrospective-team-regression-round2.log)。
本次工程开发/回归结论PASS，无未修复测试失败；这是新的工程证据，非独立业务验收。
最终17个Team文件摘要保留在
[source manifest](../../../workspaces/v4-delivery-20261013/retrospective-final-source-manifest.json)，
回归后核对未漂移。Ruff对15个改动Python文件与原HEAD分别比较，7个
F401/F841为runner.py和test_provider_wait_recovery.py的既存问题，无新增lint发现；
不能宣称完整Ruff零错误。其他改动模块定向Ruff通过。首次文档检查7个Markdown文件、
11个新增/变更本地链接及JSON合同通过；最终检查7个Markdown文件、18个新增/变更
本地链接与锚点、JSON合同及git diff --check通过，17个Team文件摘要未漂移。

最终GitNexus detect_changes返回low（20个changed symbols、22文件、0 affected），但结果含
旧行号/旧函数归属且索引陈旧，只作提示；不以affected=0主张无影响。真实调用检查和
完整Team回归是本次工程证据。图原回执保留在宿主工作目录。

原运行步骤未重新执行，真实运行生效、完整独立语义验收和端到端性能均未取得新证据。

本次只改Team代码、角色/合同指引、测试和文档；backend/frontend、应用配置与迁移未变。
因此没有重启ontology-platform.service，也没有重启已停止的Team。后续进程必须实际
加载新代码，不能假定旧进程热生效。文档/工程检查不恢复历史报告的PASS资格。

## 同日后续：阶段采用纠正与信息保留优化

修复前基线：`c180d79`。用户明确要求实施本次提出的优化并记录供下次复盘验证。
范围为 R4.3-015 的具体阶段派单、连续执行及首链反馈采用，以及
RETRO-20261013-07／08／09 的已知与未知、源反查和答案限定保留。当前只有
`docs/presentations/`、`slide-deck/` 两个无关未跟踪目录，本次不修改或暂存。

| 优化 | 实际权威触点 | 本次实施与下次效果边界 |
| --- | --- | --- |
| R4.3-015 采用纠正 | 当前009 Task；Coordinator／Modeling／Protocol／Delivery指令，ontology-modeling／delivery技能 | 具体当前阶段及共享依赖、全局范围概览；按已批准计划连续引用执行；首链已审且applied后组织现有公开反馈。原成功写入确认、必要依赖及最终独立验收保持 |
| RETRO-20261013-07 | 生产角色指令、ontology-modeling技能及交接模板 | 未知缩小到具体含义，已知和实际交付状态分别保留；延后原因、能力影响及下一责任放既有交接／note，不新增字段或物化未批准映射 |
| RETRO-20261013-08 | 当前Task、Modeling／Coordinator指令、ontology-modeling技能及模板 | 当前阶段原资料→候选反查，再核对候选依据；只检查获准可读原件，不以摘要证明全部已读，不建逐字段台账或首链前置全面审计 |
| RETRO-20261013-09 | 实际v3 Platform Examiner指令 | 在既有提交前核对中保留答案涉及关系方向、必要条件／例外／范围／基数及未知，只用本题真实平台响应，不扩大到无关返回审计或新report字段 |

生产侧与Delivery／Consumer侧分别由子Agent实施，主Agent复核。子Agent仅收到通用
优化要求及归属文件，未继承宿主私有复盘上下文，未读取隐藏原件；没有供应商调用、
真实建模／验收、模型写入或旧运行恢复。本次未修改Python执行代码、工具面、权限、
模型profile或后端／前端；已有`glm-flash-high`各角色绑定`glm-5.3-flash`，后续启动须按
用户实际模型／effort选择核对，不假定未启动进程已采用。

### 复核与相关检查

主Agent复核收窄了两处指令：反馈未执行只表示质量未验证，不把已确认applied写入
变成未知；Consumer只核对本题答案涉及的关系和必要限定，合并至已有提交前检查，
不增加一段重复的全量返回审核。全局待办保留业务范围与剩余阶段概览，不要求先列出
全部详细item；原因／影响／下一责任为既有说明内容，不新增合同字段或状态。

生产侧子Agent执行`python modeling_team/skills/ontology-modeling/evals/validate_skill.py`
通过；从backend运行`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`，选取
`test_contracts.py`、`test_r4009_acceptance_contract.py`、`test_r4315_independent.py`、
`test_v43_production_refs.py`四个现有Team测试文件：**87 passed，3 subtests passed**，
158条既有rdflib warning。Delivery／Consumer最终修改后的定向检查：
`test_v4_consumer_answer_contract.py` **3 passed**、`test_r4315_independent.py` **16 passed**、
`test_delivery_ops.py`反馈／验收入口子集**8 passed／
9 deselected**；未受本次文字收窄影响的Delivery session **23 passed**、wakeups **23 passed**
结果复用。各命令有重叠，不相加成独立测试总数。主Agent补查与未知／映射边界相关的
`test_r4007_scenario_map_contract.py`与`test_r4010_mapping_contract.py`两个文件：
**17 passed**。未修改执行代码或测试断言。

另一子Agent对最终生产侧指令及权威需求做只读交叉审阅，未发现证据支持的Critical／High
阻塞或行为冲突；未读取隐藏材料，没有新增独立功能／真实语义裁决。本次保留的指令
摘要见[source manifest](../../../workspaces/v4-delivery-20261013/retrospective-adoption-final-source-manifest.json)。
这些检查只能证明当前指令、包装与既有工具合同兼容，不能证明Agent实际采用、语义
质量提升或节省时间。最终14份改动Markdown的围栏、11个新增／变更本地链接／锚点、
十份Team指令／任务／技能摘要与manifest对应关系及差异空白检查通过。
指令／文档改动不要求后端／前端全套测试、服务重启或新建模启动。

### 下一次复盘必须核验的效果

先确认新运行manifest所记录的Task、角色指令和技能摘要与本次实现匹配，再核对相关
场景是否实际发生，按优化台账分别验证：阶段派单与首链公开反馈、已知／具体未知和
未交付去向、原资料关键内容的候选定位，以及本题平台证据到答案的方向与限定保留。
记录首链／首反馈时点、实际返工与独立语义结果，不能只凭新增文字或事件数量判生效。
无新运行、未触发或证据不足保持已实现待实测；实际采用但未达预期／退步转待调整，
达到各项原预期且质量约束满足后才关闭，历史失败和原件保留。
