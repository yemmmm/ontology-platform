# R4.3-019 实现与开发测试记录

- 权威范围：[R4.3-019](../../requirements/requirements-v4.3.md#r4-3-019)。
- 复用[已独立审阅PASS的设计](../designs/2026-10-14-r4-3-019-model-usage-reconciliation-design.md)。
- 本轮授权：2026-10-14“请根据设计完成v4.3-019需求，并通过测试”。基线 `07696db`。
- 结论：A1—A6开发工程验证通过；A7冻结历史切片复算通过。独立功能验收未执行；
  新真实任务与供应商同窗口对账未执行，历史8,717,117差额仍PARTIAL。

## 实现

`modeling_team.usage_report` 离线读取显式scope与冻结原件，生成数值JSON和简明Markdown。
报告保留scope摘要、绑定证据、源字节范围／digest、字段覆盖及定位；不覆盖旧报告。
逐响应按provider／非秘密key_ref／response_id去重，唯一请求替代需实际证据。
同身份冲突不任取值；线程累计有连续段／基线及包含证明时补总量与残差，不重复相加。
共享线程未切片及归属冲突留unallocated；未知不补零，压缩只作真实ID绑定的子集。

任务、账单窗口、角色／阶段、精确模型和两种effort分组。缓存率注明成对字段的样本
输入覆盖。版本价格用Decimal、显式计费类别／舍入；缺价／订阅／跨价格段金额unknown。
账单差额有符号，范围／时区／定义不齐只有raw_difference；token、金额和归属分别判断。
请求／头后／首输出／turn／墙钟分开；计时必须唯一绑定，缺失样本计unknown，推理不再相加。
耗时加权、同一时钟的并集及包含空闲的窗口速率分别显示，不把Examiner工具delta当首token。

Delivery只将thread/tokenUsage的白名单数值留在native/usage-events.jsonl。共享代理的
可选on_attempt在每次上游发送前／结束后留身份、固定状态、HTTP数值与UTC时间。
ProviderSessionManager的初建／重建均传递回调；Delivery及Codex生产／独立evaluation接线。
无可证role/thread／task／Key或response绑定时保留未知，不推测API吞吐或收费。
采集异常只记录固定usage_capture_incomplete，不改变请求、重试、转发、权限或run终态。
未新增正文留存、流解析器、服务、平台API、数据库、前端或统计LLM角色。

使用说明与scope／价格／计时合同见[Host用量报告](../../../modeling_team/references/model-usage-report.md)。
建模轮次、semantic-start及外部调用增量均为0。仅Team工具／文档变更，不需应用服务重启。

## 验证证据

| 范围 | 结果与依据 |
| --- | --- |
| A1 | 复制响应／冲突、无ID、累计恢复／重置／无基线／重叠、共享线程与跨task冲突均有反例测试；安全字段保留，未证明量不双算 |
| A2 | Delivery／其他任务／未知层／未调用层及attempt无usage测试；实际角色与operation上下文采集不按类名猜测 |
| A3 | 正负差额、半开窗口、未知时区、request-start绑定、供应商非法子集、数值匹配但归属未闭合分别验证 |
| A4 | 耗时加权／并行并集、缺计时／绑定、冲突计时、失败状态与含推理输出；无首输出仍unknown |
| A5 | 坏行／截断／字节前缀、非法数值／子集、零输入、真实压缩ID、缺价／重叠价表／订阅、token与金额状态分别验证 |
| A6 | 重复Delivery通知、写失败／回调抛错、429→成功、transport／stream／client disconnect；原请求体及转发字节、重试次数不变 |
| A7本地 | 同一真实保留切片，两次规范JSON／Markdown完全一致；与独立直接求和一致，原件digest未变。没有供应商明细，不代表真实对账PASS |

开发过程发现并修正：初次定向测试19 failed／121 passed／2 skipped，定位为缺值覆盖绑定
及缺少原生thread字段时错误拒绝有证据的source绑定；修正后相关反例通过。
首轮Team回归2 failed／2936 passed／12 skipped，均为独立evaluation的测试替身未接受
新增可选on_attempt；更新替身并断言回调已接线，定向30项通过。随后Team全量两轮通过。

最终验证组合（针对变化范围复用不变输入的结果，不把自测称独立验收）：

- 从backend运行 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`：
  **2942 passed，12 skipped，318 subtests passed**；356条现有rdflib弃用警告。
- 全量回归后仅报告数值边界／证据字段与Markdown投影收尾；最终六个直接相关模块
  `test_usage_report.py`、`test_usage_capture.py`、`test_delivery_runtime.py`、
  `test_deepseek_codex_runtime.py`、`test_deepseek_provider_proxy.py`、`test_model_routing.py`
  **191 passed，2 skipped**。相关结果覆盖当前代码，其他runtime代码未再变化。
- 变更Python Ruff通过；git diff空白检查及文档链接／合同检查通过。
- GitNexus修改前：ProviderSessionManager LOW，共享ResponsesProviderSession CRITICAL
  （4个直接引用，图展开92条流程）；已告知用户并核对manager、Codex、兼容wrapper和测试。
  DeliveryRuntime不在索引中，补聚焦调用点检查。暂存差异detect_changes为medium、2条
  session start/stop流程。旧索引对新增模块／Delivery不构成完整图覆盖。

## 冻结历史复算

仅复算 `industrial-service-smallchain-deepseek-20261014-a` 的当前native_thread_id
`01a13670-b96a-72c0-bd4e-bd92ecd7ca3c`；归属由session.json的native_thread_id与model_binding
绑定，不按目录名称推断其他角色。Key别名明确未核验账单，actual_model没有伪造成请求模型。
不声称完整任务覆盖、授权起止或供应商匹配。

- 原件冻结29,249,608字节，SHA256
  `23603e073ae56e326dacd7984457f2a896d6ab42004942ee12ffa7386c2d6df5`。
- 136响应；input 23,451,642、cached 19,222,016、uncached 4,229,626、output 351,481、
  reasoning_output 277,556；推理已包含在output内。
- Host私有证据：`workspaces/usage-report-validation/r4319-history-20261014/`，
  最终冻结scope及报告目录见该目录 `final-scope.json` 与 `final-1/`、`final-2/`。
- usage=partial，billing=NOT_PROVIDED；原件未改写，旧中间报告也保留。

没有独立工程验收、供应商取数、新semantic start、净费用改善或真实建模质量PASS。
后续真实任务／账单验证需相应运行授权及同窗口供应商证据，工程PASS不关闭历史差额。
