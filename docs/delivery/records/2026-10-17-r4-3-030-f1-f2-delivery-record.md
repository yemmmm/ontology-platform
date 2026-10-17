# R4.3-030 首批 F1＋F2 交付及测试记录

用户授权：“请根据设计实现v4.3-030需求，并完成必要测试”。基线为
`5b2750d`；按[权威需求](../../requirements/requirements-v4.3.md#r4-3-030) D1 与
[设计](../designs/2026-10-17-r4-3-030-delivery-token-reduction-design.md) §7，
先交付 F1＋F2，不将后续阶段框架一次扩建。本批不运行 Provider、生产建模、修模或真实验收，
不占用新建模轮次、不恢复任何保留 run。工作区既有 README、029、复盘、需求其他条目
及演示材料保留；需求文件仅提交本次030状态差异。

## 实现与作用范围

- `modeling_team/delivery.py` 增加本地 `yield_delivery`：校验原输入及 session/run/request/
  operation/Host request 身份，在原 journal 留阶段、等待、下一步、理由与有效决定。
  只返回接续回执；不代替原生 turn 完成，不清 pending，不强制 interrupt 或限调用次数。
- 原约2秒 busy/idle 监督循环持续观察全部绑定。明确 config `deadline`、授权期限及
  operation 的原 `started_at`＋`request_binding.session_timeout` 进入原变化指纹／队列，
  Host静止时也只产生一次到期变化；不从心跳或无期限等待臆造超时，不续权／重发。
- 模型展示升级 `delivery-decision-input/v2`：当前 core、全部未决紧凑身份／状态、实际
  changes 正文及精确引用。正常变化不重发不变 snapshot；新事件用实际正文，不用累计
  事件链哈希。首启／显式恢复 bootstrap 不附整份 config，保留明确 task_context、原用户
  消息／未决问题及有效 yield 接续；程序原始观察、事件与回执保持。
- 大变化与超量未决项按原 UTF-8 机制显式分页。大首阻塞在 core 中标明预览不完整、
  总字节及原件定位，完整正文只在 bootstrap／changes 中展开一次。coverage明确投影、
  历史省略及未返回范围，不表示全业务完成。
- 四个模型侧主动 get 查询先保留原始工具结果，再返回有 coverage 的简明视图。
  内部 observe、Host 当前绑定校验、请求结果判据和 finish 继续用原始结果；Python 选项
  不能经工具参数注入。CQ action 的私有审核职责仍隔离；损坏形状不补默认成功或完整。
- 沿原 journal、pending 队列、attempted/accepted/rejected/unknown 回执恢复。v1只读转换；
  旧分页偏移不用于新投影。bootstrap仅确认自身，并先完成其分页，旧 pending 与原用户
  消息确认不被清空。未知输入只重送事实；分页正文不受回执状态或新 current_state 引用
  变化干扰，不重放平台动作。
- 同步实际 Delivery instructions／skill、宿主 modeling-dev-loop 及 MCP 参考。
  本批不修改 backend/frontend，不需要产品服务重启。

## 测试轮次与证据

这是开发者工程验证，没有另一个验收 Agent，不能写为030独立工程或真实语义PASS。
所有 pytest 从 `backend/` 执行，前缀 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`。

| 轮次 | 范围与结果 | 发现及处置 |
| --- | --- | --- |
| 基线 | 原 decision_input/wakeups/session：120 passed | 原路径可复用 |
| 新行为反例 | 初始6项全部失败 | 未声明yield、v1全量输入、查询原始输出、长值只有引用、无到期变化／bootstrap身份隔离，均为预期红灯 |
| 首批定向 | 132 passed；新增14项单跑14 passed | 更新v2断言；解决旧偏移及分页期间transport字段变化；保留原事件／隔离／busy竞态检查 |
| 扩展定向 | Delivery/runtime/ops/conversation/Host actions/usage：232 passed, 2 skipped | 覆盖最终query形状与coverage纠正前后的相关路径 |
| 首次Team全量 | 3158 passed, 1 failed, 12 skipped；318 subtests passed | 唯一失败为旧029回归仍索引完整host_actions snapshot；改为断言v2未决身份及变化正文，保留原恢复要求 |
| 最终长值／新合同定向 | 19 passed | 包括当时18项030测试及长阻塞分页；去掉重复长正文后提高原分页fixture大小以继续覆盖超量路径 |
| Team全量收敛回归 | 3163 passed, 12 skipped；318 subtests passed；285.75s | 基线为末次即时request登记修正前的源码，SHA256见下；没有030独立验收结论 |
| 最终窄修及回归 | decision_input/wakeups/session/030/029恢复：148 passed | 新提交request在下一次observe前即可从真实账本认领，避免为登记yield再要求模型主动轮询；未落账ID仍返回可恢复反馈 |

Team全量命令（随后仅新增yield即时request认领分支，并完成上述148项当前代码回归）：

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short
```

最终030测试共19项，新增测试覆盖：yield不等于ack／完成，等待记录持久恢复及越界反馈；稳定正文不重发；
unknown事件真实正文；四类主动get与原始观察分离；错误／报告／请求绑定及CQ隔离；
超量中文正文完整分页；分页中unknown回执与更新状态不改变正文偏移；v1部分页恢复不改原件；
bootstrap不误确认旧pending、保留原用户早先约束且不注入整份配置；明确期限一次唤醒；
standby不误判超时；损坏查询保留限制；假原生runtime自然完成后反复观察零新turn，实际
unknown写入变化后才唤醒。该runtime测试没有模型主动轮询，不能证明真实LLM遵守新提示。

两份活跃skill的 `quick_validate.py` 均通过；最终diff、6份文档相对链接／围栏、需求030行为及A1—A6合同正文未改检查通过。
GitNexus `impact(call_tool)` 未找到当前符号；`detect_changes` 返回low但缺失Delivery
源码符号并出现旧路径，不能当有效图覆盖。实际使用源码／调用点和回归测试核对：调用范围
限 Delivery模型入口、内部 observe/Host绑定/request投影、原监督循环；底层Host公开API、
生产Runner、原生线程／用量采集未修改。

Team全量收敛回归的 `modeling_team/delivery.py` SHA256：
`3853d13e27db78550a736f719f8f1d9252c301d1527ea8992e3b7c60a516864f`。
最终源码SHA256（含即时request认领、148项回归通过）：
`bddb8b64296016b25a3a5c5bd53b8f6d84872a25175fbaa7972546d57e3d516f`。
未变调用路径复用全量结果；最后增量覆盖实际账本、未知身份、恢复和原内部原始结果路径，
不将全量旧代码结果冒称最后窄修已参加同一命令。

## 验收状态及停止边界

| 项 | 当前结论 |
| --- | --- |
| F1／A1 | 程序工程与假runtime覆盖；真实模型yield后自然结束、不主动轮询仍未验证 |
| F2／A2 | 离线工程覆盖；不是真实LLM效果或独立验收 |
| F3／A3 | 未实施／未启用；按设计需先有F1＋F2可比实测及历史膨胀证据，再选择阶段边界 |
| F4／A4 | 两种机械连续动作未实施，保留原单步工具，后续分项交付 |
| F5／A5 | 019原计量继续可用；未创建新scope／对照run，T_D、input实际下降及全任务净效果未验证 |
| A6 | 未启动独立业务语义验收；不继承其他运行的PASS |

030保持**部分实现／部分验证**。本批工程机制不证明token、费用、墙钟或综合效率改善；
缓存／推理／压缩仍为原总量子集，不能叠加当新收益。后续真实对照须保持完整公开1题／
隐藏3题及评分、全部角色模型／effort／窗口／并行，覆盖准备、失败恢复和必要收尾；
须有当时有效的运行授权，不能因这次实施而自行启动。
