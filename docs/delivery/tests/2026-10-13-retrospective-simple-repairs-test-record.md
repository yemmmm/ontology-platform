# 两次建模复盘后的简易工程修复验证

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
