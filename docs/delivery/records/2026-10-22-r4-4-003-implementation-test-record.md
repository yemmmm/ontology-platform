# R4.4-003 工程实现与本地测试记录

- 日期：2026-10-22。
- 授权：用户要求“请实现R4.4-003需求并通过测试”；承接已独立审阅通过的设计。
- [权威需求](../../requirements/requirements-v4.4.md#r4-4-003)；
  [详细设计](../designs/2026-10-22-r4-4-003-delivery-periodic-review-design.md)。
- 实现起点：`fba8148`，工作区原有需求实测补记、复盘、README及演示材料改动继续保留。
- 当前结论：**工程实现及本地测试通过**；真实采用、净降耗及独立语义验收未执行。

## 实现范围

普通更新继续留在原事件／卡片存储，程序按字段和来源位置计数，不调用另一个模型生成
摘要。Delivery默认180秒查看一次，Host可用正整数`status_review_interval_seconds`
调整；忙碌不steer普通窗口，跨多周期只处理一次到期，普通变化不重置计时。

用户／Host输入保持原文、身份、来源和授权，空闲send、忙碌steer；同文不同输入不合并。
正式Host结果仍按原技术投影读取。关键就绪／结果、预算控制、未知写入、首次不明异常、
owner异常和观察缺口及时送达；同一问题按当前状态去重，恢复／复发、请求与保护性绑定
变化重新处理。预算暂停先走原程序控制，输入保留并回告限制，不扩大付费例外。

`delivery-decision-input/v2`新增`trigger`及`periodic_review`。窗口提供当前工作卡／缺卡、
变化字段及次数、重复失败和最新结果、实际活动、原件定位及覆盖缺口；已确认的不变卡片
正文用版本引用替代。`yield_delivery.next_review_at`仅延期无新事实时的复查，格式错误
返回可纠正字段反馈。新卡片、关键输入及既有期限不受延期抑制。

原journal保存窗口、来源上界、投递与完成事实。只有必要页连续接收且原生正常完成后
确认概况位置；失败／unknown或来源缺口保留原位置。已确认的新概况可替代旧的已知未送
普通页，并明确记录superseded，不把旧页或原件伪称已读。unknown原生尝试必须对账，
控制和输入接收仍继续。完成且资源／请求已收口后停止普通定时推理，新输入和异常仍可处理。

工作卡片history新增`after_record_seq`，限定非负整数、固定来源前缀内严格大于该序号；
selection／cursor、权限及version语义保持，Host、MCP、CLI和接口文档同步。
Delivery实际instructions与Skill对齐程序定时巡检、定向诊断、即时输入及确认边界。

## DSH显式恢复的窄兼容处理

源码及真实本地DSH／SDK夹具确认：旧基线严格比较工具schema和instructions SHA，会
拒绝本条新增可选参数与已批准提示的恢复。这属于`platform-contract`兼容问题，不是
模型质量失败。按T0复核，模型／构建／插件、原session、授权及未知工具／写入屏障仍须
保留；兼容的可选读参／yield参数与当前提示更新不应迫使重建生产或另开session。

因此仅允许旧无策略标记的基线一次性迁移到`delivery-periodic-review/v1`：工具名不变，
只有`yield_delivery.next_review_at`和`get_team_work_board.after_record_seq`可选字段、
这两个工具的描述及当前instructions更新获准；其他schema、模型、构建、composition
和Host检查字段漂移继续拒绝。新完整基线同一行保留旧SHA和差异证据，原行不改写；
后续恢复严格核对策略标记。迁移不发推理请求，下一次正常请求才采用新提示和工具。

## 测试范围与证据

所有测试均不调用收费Provider、不启动或恢复真实生产建模，也不执行业务语义验收。
Codex原生协议夹具与DSH真实本地进程／SDK＋确定性本地Provider分别验证运行时合同。

| 范围 | 证据与边界 |
| --- | --- |
| A1／A5／A6 | 一个窗口100次普通更新、工具可纠正失败、重试及最新恢复、未知异常、保护性绑定与请求变化；不把静默或token增长当业务结论 |
| A2／A3／A4 | 原会话输入去重／来源、忙闲send／steer、完成竞态、旧页优先级、CQ／Host私有结果投影、现有就绪／预算控制回归 |
| A7／A11 | 默认／自定义周期、持续更新、忙碌跨周期、明确延期、新卡取消无变化延期、无变化巡检、完成静止及后续异常 |
| A8／A9 | 序号固定前缀、同时间／并发追加、分页／来源失败、正常完成确认、失败页留洞、unknown不盲重放、superseded、旧journal及阶段线程 |
| A10 | 两adapter现有原生运行时测试及真实本地DSH旧session迁移；实际包／Skill装载到后续本地Provider请求，非生产采用证明 |
| A12 | 未执行；完整最小链公开1题／隐藏3题、净token／金额／时间对照及独立语义结果另需真实运行授权 |

开发中出现的缺口按原测试定位并修复：旧逐事件／Codex不steer断言与新合同不符，
当前／历史卡片分页失败未明确覆盖，失败分页可能误确认，unknown投递盲重送风险，
空闲原生明确拒绝后原消息未留队，以及旧DSH基线与本次兼容增量冲突。错误原件不被
后续绿色结果覆盖；本地日志留存在`workspaces/requirement-tests/r4.4-003-20261022/`。

执行命令统一从`backend/`使用`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`。

| 验证轮次 | 结果 |
| --- | --- |
| 共享组件全量回归 | 3814 passed，12 skipped，318 subtests passed（457.18秒）；其后收尾增量另测 |
| 收尾输入／唤醒回归 | 191 passed（25.06秒） |
| DSH迁移及既有adapter | 28 passed（23.53秒） |
| 最终巡检需求用例 | 31 passed（2.33秒） |
| 最终受影响调用链／授权／预算回归 | 687 passed，2 skipped（92.55秒） |
| 最终工作树验证 | 变更Python文件Ruff、接口同步、文档链接／格式／合同及diff检查通过 |

最后的687项覆盖`test_delivery*.py`、`test_dsh_delivery.py`、`test_host_ops*.py`、
`test_work_board.py`及`test_task_budget*.py`，包含正常／失败接收、原授权与幂等、
私有审核、原生加载、阶段线程、真实本地DSH兼容恢复等调用链。全量回归之后收尾增量
均由这些相关用例覆盖；未变组件复用此前全量结果。最终31项另复核收尾后的巡检用例。

GitNexus未收录当前Delivery／DSH关键方法，impact返回target-not-found；本次使用实际
调用点、diff及上述测试定位影响，不宣称图覆盖。提交前detect_changes识别24个变更文件、
0个已索引符号，返回low；索引未覆盖的符号不视为无影响。静态检查范围为本次变更的Python文件，
不把未修改测试文件的既有lint问题算入通过。

本轮未修改应用后端／前端或服务配置，不重启`ontology-platform.service`，不热改任何
存活Delivery／生产进程。工程通过不表示真实降耗、完整任务10M、独立语义或重复性通过；
R4.3-030与R4.4-002原有未验证边界及历史结果保持。
