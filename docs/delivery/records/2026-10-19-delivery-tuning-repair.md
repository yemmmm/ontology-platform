# 2026-10-19 Delivery降耗问题修复与后续验证

用户授权：“请定位并修复上面这些问题，并记录调优项，后续运行建模任务验证调优项是否
生效”。沿现有022／029／030／032实施复盘已定位的必要差异，不新增运行框架或建模
硬计数门。[原复盘](../modeling-retrospectives/2026-10-19-dsh-input-fixes-delivery-retrospective.md)
和[数值证据](../evidence/2026-10-19-dsh-input-fixes-delivery-analysis.json)保持历史结论。
基线9945ea2；原组三轮已用1、剩余2。本次仅修复及工程检查，未启动新模型、继续原run
或消耗余额。实际采用与token收益交后续获准建模验证，不把本记录当独立语义验收。

## 本次实现与最窄原因

| 调优项 | 实现 |
| --- | --- |
| OPT-20261019-DSH-01 恢复状态准确 | Host派生等待识别recovery-effective的实际claimed/settled回执，校验issue/epoch、dispatch及reporter；历史回执无顶层reporter_id时，必须精确匹配原report.thread_id与native session/process。submitted、错身份／epoch或未消费仍保持待办 |
| OPT-20261019-DSH-02 同一原生问题不重复唤醒 | 从原tool/call关联工具名到tool/result，解析原生JSON或明确isError文本，只去掉原生信封调用身份；按actor/session/process及工具保存问题状态。相同错误保持安静，本工具恢复／错误改变／复发继续送达；无关联的未知结果、保护性绑定继续保留。已知初始化成功回执与带error参数声明的常规header不误报错误 |
| OPT-20261019-DSH-03 F3真实阶段交接 | 当前最小决策输入展示phase_thread_handoff及实际已接受请求身份；production须由Delivery选真正冻结通知，acceptance须已有handoff和运行验收。交接完成后不再提供旧production候选，切线程失败后仍可在新输入重新显式交接。复用原yield及安全判断，不自动猜业务指令或重启生产 |
| OPT-20261019-DSH-04 精简CQ实际提示 | 修复进入Profile真正加载、替代通用说明的minimal-chain-competency-question包，明确使用已挂载输入／实际收件材料、权限拒绝不重试、不探测其他身份；草稿走原CQ能力，权限不放宽 |
| OPT-20261019-DSH-05 上游格式与排队返工 | 实际精简Modeling包明确六个兄弟键、fields不含执行键／slice_ids；按实际发出的参数判断错误，不以意图或同一拒绝digest推断桥接注入；不往业务模型写诊断探针。Modeling／Coordinator收到未消费输入反馈时结束活动、先消费和核对当前回执，不重复完成消息或已应用写入 |
| OPT-20261019-DSH-06 Host结果完整引用可直接读 | 已匹配私有Host journal结果、权限和原件digest后，归一该绑定的相对路径identity；长度／scope／digest检查及其他文件身份保持，原source_ref不被修改 |

调用范围限Delivery决策投影／原件读取／当前阶段输入、Host只读issue派生和实际精简角色
提示。Runner原子application、权限、未知写入、CQ私审、独立Consumer/Judge、原终态
输入完整性守卫未放宽。按T0复核，错状态与误唤醒不保护必要业务不变量，应纠正派生和
投影；终态不能跳过真实未消费输入仍有实际必要，保留可恢复反馈。

GitNexus对_issue_pending和maybe_switch_phase_thread返回Target not found／UNKNOWN；
没有据此声称图覆盖。实际调用点为get_pending_actions→_issue_pending→get_run_status，
record_observation→_decision_events→_diagnostic_state，_model_observation阶段提示及
原maybe_switch_phase_thread、read_delivery_artifact受控读取；按这些范围验证。
提交前detect_changes报告14个变化文件、low，但changed_symbols／affected_processes
均为空；结合上述Target not found结果，不把它当作图覆盖证明。

## 工程验证

验证日志保存在`workspaces/delivery-tuning-20261019-repair/`，不含凭据或隐藏答案。

- 首批15项先出现9 failed／6 passed，正确复现状态误报、重复原生错误、schema误报、
  阶段提示缺位和相对引用失败；修复后15通过。
- 新增“其他工具成功不表示本工具恢复”反例先失败，补齐原tool/call身份关联后通过。
- 补“其他native session成功不恢复当前问题”及阶段失败后重提／不倒退到已完成阶段
  三个反例，均先失败再修；另补目录外真实错误／插件失败不被常规协议降噪隐藏的
  两个反例，同样先失败再修。最终相关317 passed（20.21s）。
- 第一轮相关回归309 passed；包含原唤醒、最小输入、阶段线程、token接续和Host合同。
- 保留原件回放发现旧DSH回执无reporter_id，补完整旧信封反例后再修，Host／新专项
  111 passed。真实旧run的Host只读派生issue_wait已为null；未改原证据。
- 原1114条native原件离线重放，决策事件37→18，正常初始化／header不再送达；
  错误、实际恢复／复发和保护性事实仍由合同测试覆盖。这个数字不是模型调用或token
  降幅，不作为真实建模／独立验收结果。
- 全量Team回归：3454 passed、12 skipped、318 subtests passed（550.80s，退出0）。
  该轮启动后补正的session隔离、阶段候选及目录外错误边界，已按最终代码重新跑上述
  317项相关回归；全量中的其他未变范围复用该轮结果。此前中断的一轮为551 passed、
  2 skipped、62 subtests passed，明确不作为完整通过。
- Ruff与Delivery skill validator通过；DSH最小链Profile确实绑定本次三个精简包，
  CQ包required_skills为空，故纠正放入该包本身。已同步接口说明，新增Markdown链接
  解析、代码围栏、数值JSON及git diff检查通过；最终收口以提交内容为准。

相关回归从`backend/`执行：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_delivery_tuning_regressions.py ../modeling_team/tests/test_delivery_wakeups.py ../modeling_team/tests/test_delivery_decision_input.py ../modeling_team/tests/test_delivery_phase_threads.py ../modeling_team/tests/test_delivery_token_reduction.py ../modeling_team/tests/test_host_ops.py -q --tb=short
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short
```

未改backend/frontend运行代码，不需要产品服务重启。原Team／Delivery进程的冻结代码
与提示不会因这些文件更新自动重载，后续运行必须核对实际新版本和挂载身份。

## 后续建模验证口径

使用原最小链Task、唯一业务source、公开1题／隐藏3题完整范围，沿最新适用用户选择
保留DSH／glm-5.3-flash／low及同等独立验收。F3须显式启用production／acceptance，
不能仅看配置就宣称采用；不为制造故障额外写业务探针或扩大源范围。

| 调优项 | 后续应观察的实际证据 | 未触发或缺证据时 |
| --- | --- | --- |
| 01 | 有真实issue时，submitted待办保持；bound native恢复后Host待办消失，不再重复resolve | 正常无issue只记未触发，不能关闭真实恢复子项 |
| 02 | 按工具／问题对齐原日志、送达事件和真实响应；相同问题不随调用身份重复唤醒，改变／恢复／复发仍及时送达 | 不以无错误样本证明全部错误分支，不把字节／事件减少换算成token |
| 03 | 实际core提示→Agent yield.thread_boundary→旧turn结束→原进程新native session；原约束／未决项／有效决定与全线程用量承接完整 | 安全条件不足保留原因，0切换仍是未采用，不能算F3通过 |
| 04 | 实际精简包hash和完整材料装配正确，CQ不猜身份／不重复权限错误，仍完成原全景及切片审核 | 只校验提示文字不等于行为已验证 |
| 05 | 原始changes键结构正确、无诊断业务资源；旧指导按当前回执消费，未消费输入不被终态跳过 | 本轮未遇相应反馈就保留分支未验证 |
| 06 | 复制真实Host结果引用一次读取成功；改内容、错误identity或越界仍准确拒绝 | 未发生此读取保持未触发 |

主指标仍为Delivery累计input与input+output，另列响应数、单次平均／峰值输入、
缓存／非缓存、补读及纠错次数、墙钟、全部角色和Host成本；原未用余额不是必须耗尽
的目标。失败／恢复／新旧线程和收尾不能漏计。原四题独立语义验收、源忠实及写入
完整性继续保持，缓存率升高和局部日志减量不能代替真实净降耗。

当前6项均登记为**已实现待实测**；工程结果不关闭030、032整体或账单缺口，F4未实施、
021继续暂停。后续复盘沿原台账逐项追加采用版本、触发情况及有效／待调整证据。
