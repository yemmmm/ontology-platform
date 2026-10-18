# R4.3-032 开发与测试记录

- 用户授权：根据已审阅设计完成 R4.3-032 开发与测试。
- 权威范围：[需求032](../../requirements/requirements-v4.3.md#r4-3-032)、
  [详细设计](../designs/2026-10-18-r4-3-032-dsh-delivery-runtime-design.md)、
  [独立设计审阅](2026-10-18-r4-3-032-design-review-record.md)。
- 复用031已提交实现 `f34fe1f`；保留 README、029、复盘、优化跟踪、演示及相邻需求的既有修改。
- 本轮为工程实现与测试，不启动真实生产、修模或语义验收，不调用外部模型，不消耗建模轮次。

## 实现范围

| 合同 | 实际实现 |
| --- | --- |
| F1 独立选择 | Delivery配置显式codex／dsh，省略保留codex；只校验原优先级解析后的Delivery绑定，不随生产Profile切换。DSH拒绝显式Codex tier／窗口／压缩设置，不注入Codex默认窗口。旧记录缺runtime按codex读取，拒绝热迁。 |
| F2 工具与权限 | 独立DSH进程、HOME／持久session store；复用031固定构建、最小composition、bubblewrap及Messages持钥代理。直接注册原Host工具和精确schema，以官方双向JSON-RPC传原生session／callId，单工具执行队列不阻塞事件泵及控制。内部原始查询结果及模型投影继续分别保留。 |
| F3 观察与结束 | 原约2秒观察、v2输入、分页、主动get精简、一次期限变化、yield和standby保持。真实turn/end及pending／在途工具共同确定忙闲；yield回执、session.status、工具成功均不算推理或业务完成。未知通知、进程／事件泵故障及未解决序号缺口明确中断监督。 |
| F4 输入与消费 | 普通prompt入next-turn，窄steer调用底层Agent.steer进入next-step。Host派发ID连原input_id／分页或用户message_id，原生session／messageId／seq与process_instance分列；接收与queued／claimed／settled分别留证，不向Codex turn字段填DSH ID。 |
| F5 控制与收尾 | DSH生产按原Host pause_run／resume_live_run及实际Runner回执；Codex／未迁验收保持协作确认，Delivery在线。暂停期间禁止新建工作；撤权先关闭Host准入，缓存schema不能重获权限。技术cancel保留inbox；stop只程序观察owner退出，不派发新推理。EOF无server记supervision_interrupted；明确stop关闭本轮进程和代理。 |
| F6 恢复 | session/resume只恢复原DSH持久session，核对构建／composition／工具／方法／模型以及原任务、范围、源授权。先关闭效果性准入，核对原inbox与工具账本；未知工具效果拒绝恢复并指明原call_identity，不创建替代session。丢失入队回执按持久输入正文的Host dispatch ID核对；已queued页／原用户输入不重复派发。原用户约束、有效yield决定、起点／额度和029未决交接仍从原账本重建。 |
| F7 阶段边界 | 未实施030 F3／F4，不迁033验收，不改034默认选择／统一计量；原始DSH用量及压缩事件保留，不宣称净降耗。原直接application、治理读取、私有CQ隔离和独立语义合同保持。 |

只修改Modeling Team与相关指令、配置和文档；没有backend／frontend、平台API、迁移、
依赖或共享服务配置变更，因此不需要产品服务重启或backend／frontend全量套件。
实际Host操作继续使用原权限检查；DSH事件泵和工具回调并行，session快照文件写入串行化。

## 工程测试

所有pytest在 `backend/` 执行，设置 `env -u DEEPSEEK_API_KEY PYTHONPATH=..`。
真实固定DSH／Node／bubblewrap只访问本地确定性Messages服务，测试未读取真实provider key。

- 首批DSH真实本地工程用例6项通过；扩展工具全集、挂载隔离、回执丢失、恢复拒绝、
  原分页核对、暂停／撤权、conversation消费关联及实际Host循环EOF／stop后14项通过。
  最初两条测试断言未解析JSON工具正文的转义／嵌套，已改为解析原JSON后逐值核对；
  没有为断言改变产品返回结构。
- 原Delivery runtime／session／decision-input／wakeups／conversation／token-reduction／
  Host-actions定向回归：172 passed、2 skipped。
- 进一步复核补齐原任务／范围／源绑定恢复不可扩大、序号缺口不能伪装永久idle两项边界。
  首轮全量在这些增量后主动中止，原日志保留，不计PASS；最终全量使用最后代码版本。
- 增补真实活动中断＋未消费inbox恢复测试后，DSH专项最终17 passed（18.09秒）；
  核对原messageId、原中断结局、原queued输入仍在，恢复本身没有新prompt／provider请求。
- 第二轮完整全量：1 failed、3208 passed、12 skipped、318 subtests passed，359 warnings，
  454.49秒。唯一失败是旧checkpoint测试用`object.__new__`绕过构造后缺少`activity`，
  新控制检查按正常Session不变量读取该字段。只为该测试夹具补`activity="active"`，
  不降级生产权限／私有CQ隔离检查；失败原件为`round2-team-tests.log/xml`。
  修正后的整个checkpoint文件＋DSH专项：28 passed（20.58秒）。
- backend只读conversation服务复用该stdlib日志模块，额外运行
  `uv run pytest tests/test_delivery_conversations.py -q`：4 passed、5既有弃用warnings，
  0.66秒；公开字段白名单、私有隔离及同一在线socket收发合同保持。
- 最终全量：`uv run pytest ../modeling_team/tests -q --tb=short
  --junitxml=../workspaces/r4-3-032-engineering-20261018/team-tests.xml`：
  **3210 passed、12 skipped、318 subtests passed**，359既有warnings，444.20秒，退出码0。
  全量开始时的源码／配置／测试摘要与最终文件逐一一致，清单为
  `full-suite-source-sha256.json`；本轮包含全部17项DSH专项与已修正的旧夹具。
- 静态检查：变更Python的 `ruff check --select F`、Python编译、两个Node入口语法，
  相关文档相对链接、需求锚点及diff检查均通过；DSH生产配置CLI validate通过，无模型请求。

工程原件目录：`workspaces/r4-3-032-engineering-20261018/`（gitignored），保留完整测试
日志、JUnit与全量开始时源码摘要。测试凭据、临时session、生成日志和外部Harness不提交。

## 验证边界

GitNexus未找到`_run_delivery`；detect_changes返回的旧索引未覆盖当前Modeling Team
代码（出现历史pi-modeling-agent路径），不作为本次图覆盖或低风险证明。本轮使用实际
调用点、diff、原Codex回归、真实本地DSH工具／事件／恢复及Host循环测试。

A1—A4的配置、隔离、协议、实际本地活动／控制接点及恢复工程测试与真实业务验收分开。
本地模拟provider自然结束和无变化无请求，只证明接线与调度；不能证明真实模型遵从
yield、真实长期空闲行为或自主交付。真实平台长调用／晚回执与DSH暂停的联合效果仍须
在获准运行中取证。**A5最小链、外部provider实际推理与模型绑定、真实application及治理
读回、独立L1、自主交付、L2、完整切换及净降耗均未验证。** 独立设计PASS不扩写为
独立工程／语义PASS；033前验收仍可走明确披露的原Codex路径。
