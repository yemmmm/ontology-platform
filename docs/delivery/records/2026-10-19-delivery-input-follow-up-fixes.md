# 2026-10-19 Delivery输入返工与阶段历史修复

用户在Codex GLM C组与DSH共用防护组输入构成补查后，要求修复已发现的问题。
归属R4.3-029／030／022／032及036的必要计量适配；复用030既有F3设计，
不追加真实建模、独立语义验收或外部模型调用。既有Team及原件保持只读。

## 已定位问题及改动

- 缺source_ref.byte_length被误报artifact_changed：cb60bd5已声明完整必填身份并返回
  参数位置、缺失字段和可重试反馈。本次复用该修复，补齐Delivery package／skill的
  正确读取说明：复制全部身份字段，按报错补参数，不把参数缺失当作文件变化刷新重试。
- 已送达回执仍主动查询：v2新增request_results提供本次新接受或结果改变的实际回执；不再在changes重发整个已结列表，
  unresolved[].result带上未决／拒绝结果和纠错动作。提交态返回receipt_tracking，
  引导yield并由既有程序观察送达，不再发next_query轮询指引。查询能力保留用于
  真实缺口、未知提交和恢复，不增加禁止查询的硬门，不混淆submitted与consumed。
- CQ误用handoff材料通道：在CQ权威package明确仅消费实际发给本角色的材料引用；
  material_forbidden不重试或改actor，草稿仍走cq_publish_question_draft；缺必要材料
  才向Coordinator报告具体缺口。不放宽权限或传入私有答案。
- 已完成阶段历史累积：实现030既定可选production／acceptance边界。Host配置
  phase_thread_boundaries显式选择，默认空；Delivery在yield附当前输入的
  thread_boundary={phase,run_id,request_ids}及有效决定／原引用／理由。
  程序核对真实已接受回执、已启动验收和当前提交／写入状态；旧turn、工具或输入
  未结、未知结果、用户控制、缺交接时延后，继续原任务。Codex在原app-server建新线程，
  DSH在原SDK进程保留新session身份，均不再默认带入旧阶段对话；不是021压缩重写。
  当前事实、所有原用户约束和有效决定沿原journal分页重建。创建失败不热重试或
  重放业务动作，首轮输入不确定继续沿既有unknown派送对账；历史线程绑定追加保留。
- 切线程不能漏账：旧线程迟到用量按原thread/session记录；旧完成消息不能释放新
  活动的busy状态。036捕获源显式绑定全部实际线程，单个进程只留一份生命周期，
  汇总及冻结证据离线重放均累计旧／新线程。GLM额外采集保持删除状态。

## 影响与验证范围

影响调用链为DeliverySession.call_tool／record_observation／_model_observation及
_run_delivery空闲派送，两个Delivery runtime和DSH Host桥；036仅扩展同进程多线程
绑定。生产建模、平台application、CQ私审和独立Consumer/Judge职责不变。
GitNexus索引落后448提交，采用当前调用点、diff和相关回归，不声称图覆盖。

专项先记录失败，再实现：阶段切换／恢复／默认关闭／未知提交与写入／新观察须重新
交接、回执不需二次查询；Codex旧完成／旧用量归属；真实DSH SDK新阶段不含旧对话；
036反例先发现只计最后线程200、漏掉旧线程100，再验证合计300且不重复生命周期。

真实token／净费用、运行期间Agent实际采用、
独立语义结果和L2重复性仍待获准实测，不把本地确定性provider当作建模验收。
F4连续动作本次未实施；未改backend/frontend，无产品服务重启。

## 工程验证收口

最终相关回归418 passed、1 skipped、3 subtests passed，64.15秒。执行入口为backend下
`env -u DEEPSEEK_API_KEY PYTHONPATH=.. MODELING_TEAM_DELIVERY_LIVE_CODEX_BOUNDARY=1 uv run pytest`，
范围为test_delivery*.py、test_dsh_delivery.py、test_close_statistics.py、test_contracts.py、
test_dsh_contracts.py、test_dsh_usage_report.py、test_usage_report.py。全部当前改动均在
最终这次相关回归之前完成；与此前70项／417项等专项有交叉，不累计为额外通过数。

本机真实codex app-server通过本地固定Responses provider验证同进程换线程、原工具边界
与第二次请求不含旧阶段canary；真实DSH SDK通过本地固定Messages provider验证相同行为，
并验证阶段切换后保留原session恢复。另一个仅适用于/agent/bin/real-codex入口的检查跳过；
不把入口跳过当成已验证。固定provider没有向外部模型请求，不是新的semantic start。

此前曾扩展Team全量，在2265 passed、3 skipped、275 subtests passed时主动中断
（325.97秒，停在无关历史恢复场景），不宣称全量完成；最终以本次影响范围回归收口。
Ruff、Node语法、git diff --check、Delivery skill validator与接口文档同步检查均通过，
新增需求／台账链接可解析。GitNexus旧索引不作为图覆盖证据；无backend/frontend变更，
没有产品服务重启或原Team重载。

030 F3状态为已实现／工程验证通过／真实采用待证，默认配置仍为空；后续获准任务可显式
配置phase_thread_boundaries选择production和/或acceptance，再验证冷启动、交接、补读、
全链／Host及独立语义结果。F4及021状态不变，不把本次代码修复称作净token／账单下降。
