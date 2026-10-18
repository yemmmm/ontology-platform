# DSH Delivery复盘问题窄修复

授权：用户要求修复上一轮复盘识别的Delivery问题，复杂度较高的部分可登记需求后续设计实现。
依据[复盘P1—P5](../modeling-retrospectives/2026-10-18-dsh-low-retrospective.md)，归属
[R4.3-030／031／032及019／034](../../requirements/requirements-v4.3.md)。
代码起点6a37177。未改写原运行、授权、冻结题池、报告或清理证据，未启动外部模型。

## 处理范围与最窄责任面

| 原问题 | 本次处理 | 当前边界 |
| --- | --- | --- |
| P1 DSH例行事件触发Delivery变化链 | delivery.py沿现有noise／metadata投影识别DSH step、普通消息、正常工具及数值事件；原件保持，完整成功用量不唤醒 | 原生inbox、turn/end、错误、缺口／未知类型及坏记录继续可见；不是屏蔽全部DSH来源 |
| P2 HTTP错误缺原因 | Messages代理最多读取4097字节判断失败体是否超界，只导出固定原因分类、获准provider类型、原HTTP／request ID及数字化请求规模；写入原数值回执并进入Delivery异常投影 | 不保留／回传上游正文、提示或凭据；失败体不可读仍保留原HTTP，不增加请求重试。历史400正文已丢，不能追认其具体根因已修 |
| P2补充：错误turn记成普通结束 | DSHDeliveryRuntime将turn/end reason.kind=error标记failed，provider_error保留code／http_status | 真实SDK事件可观测，不将正常活动结束当业务成功；原Host恢复和unknown写入核对保持 |
| P3场景地图／动态CQ需手工转存 | 登记R4.3-035 | 涉及隔离角色材料、Runner原件接收及消费回执，留待详细设计／实现；未新增任意文件工具或第二套材料服务 |
| P4坏JSON误报额度故障 | Runner按MALFORMED_RESPONSE／INVALID_REQUEST／CONTEXT_WINDOW_EXCEEDED给出针对性提示 | 不删除wait、不自动重放；未派发工具的坏JSON由现有原session显式纠正路径处理，未知／已发工具仍先对账 |
| P5全任务成本不完整 | 维持019／034的原缺口与后续同条件验证 | 不补造Host、scoring、失败或收尾用量，不用本次事件减量声称净降耗，不重复立项 |

错误分类只改必要反馈，未移除授权、写入完整性、原子性、独立验收或未知结果保护。
没有新增模型、角色、后台服务、自动恢复、运行次数硬门或压缩机制。

## 根因与开发验证

1. 先补失败回归：DSH例行事件仍唤醒、native error元数据不可见、坏JSON等套用额度提示，
   以及HTTP400没有code／请求规模，DSH provider_error没有code。旧实现分别出现断言失败。
2. 局部修正后，第一组相关文件193通过、6失败：6条测试错误要求“没有变化的事件集合”
   仍出现在v2 changes；修正为确认它未进入变化正文，生产降噪行为当时已正确。
3. 第二组175通过；增加真实固定DSH边界测试后，DSH Delivery及wakeups共110通过：
   原生context错误分类到Host、坏工具JSON未派发工具、显式纠正后同原session完成，
   请求数证明没有自动重试；工具error不把业务code／源正文带入默认输入。
4. 又补一个上游error.type为数组的边界，先观察400被解析异常遮蔽，修正为未知provider
   类型的可恢复分类。该修正及工具error标记进入最终全量；中途全量主动中断，不算PASS。

最终全量：**3301 passed、12 skipped、318 subtests passed**，359项既有依赖／fork弃用告警，
498.57秒，退出码0；10个受测代码文件摘要与最终工作区一致。12项跳过保留原opt-in边界，
不冒称全部真实环境覆盖。测试是本地固定DSH＋离线Messages fixture，无外部模型费用，
不替代真实Delivery自主交付、独立语义或token下降证据。

命令均在backend目录：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short \
  --junitxml=../workspaces/dsh-retrospective-20261018/delivery-fixes-final.xml
uv run ruff check --select F ../modeling_team/delivery.py \
  ../modeling_team/messages_provider_proxy.py ../modeling_team/runtimes/dsh_delivery.py \
  ../modeling_team/usage_capture.py ../modeling_team/tests/test_delivery_wakeups.py \
  ../modeling_team/tests/test_dsh_delivery.py ../modeling_team/tests/test_dsh_runtime.py \
  ../modeling_team/tests/test_messages_provider_proxy.py
git diff --check
```

实际全量日志由shell重定向保存在同目录`delivery-fixes-final.log`，代码身份见
`tested-source-sha256.json`。其余定向日志与中断轮全量保留，不混用结果。

Ruff：八个相关文件检查通过；runner.py及test_provider_wait_recovery.py分别有7／3项
既有F类告警，与HEAD原文件逐项code／message一致，本次没有新增；不借机清理无关代码。
文档链接／锚点、改动格式及最终结果补记一并检查。

## 原运行事件的离线投影复核

仅通过当前生产投影函数读取r3/r4保留事件，未执行模型或新建一次性验收器。
`retained-event-projection.json`记录：

| 原件 | 总记录 | 例行记录不进入决策唤醒 | 保留记录 |
| --- | ---: | ---: | ---: |
| r3 dsh-wire | 1301 | 981 | 320 |
| r3 dsh-provider | 574 | 573 | 1 |
| r4 dsh-wire | 459 | 346 | 113 |
| r4 dsh-provider | 183 | 183 | 0 |

首轮原MALFORMED_RESPONSE继续保留并投影出真实code；未知／异常记录不整体过滤。
这是原件投影的机械证据，不是节省token／墙钟的测量，不能由记录数推算降幅。

## 影响、部署与后续验证

GitNexus对_is_decision_event_noise、_report_provider_wait_issue及NumericReceiptWriter
均Target not found／risk UNKNOWN；detect_changes低风险但未覆盖本次新代码，并出现
不在本次diff中的旧pi-modeling-agent路径。该结果不作图覆盖证明。

实际调用检查：噪声函数同时用于Delivery唤醒指纹和模型输入，metadata用于两者；
Messages代理被DSH生产、Delivery及验收共用，成功流字节不变、错误不重试，数值writer
仍限定枚举／数字；Runner修改仅为provider等待issue的文字，不改恢复准入；原Codex
投影／计量与恢复通过相关回归验证。DSH原生Runtime错误仍经过Delivery原失败退出通路。

修改仅在modeling_team与文档，不涉及backend／frontend可执行代码、产品依赖或配置，
无需产品服务重启；新Delivery／Runner进程才会加载本次修复，不热改任何已有会话。
当前建模任务已关闭且未用额度已收回，本次修复不重新启动。

后续按新授权核对：DSH Delivery自主完整四题交付及关闭、真实异常原因可见、同条件
Delivery input／T_D与全任务成本。035先细化现有接点；019／034补全可取得的成本，
取不到的保留unknown。工程、原件投影、真实语义、自主交付和净降耗分别报告。
