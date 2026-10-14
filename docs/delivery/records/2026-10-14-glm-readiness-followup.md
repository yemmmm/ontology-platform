# 2026-10-14 两组复盘后的 GLM 准备与窄修复

授权来源：用户要求“请你主导完成这些事情。不再使用deepseek，下一轮采用智谱
glm-5.3-flash继续”。本次完成启动前准备与已确认窄修复，不启动新的建模轮次或恢复
DeepSeek调用；不改变A/B旧模型、冻结题池、独立裁决和历史消耗。实现基线`64d9950`。

## 范围对齐与信息遗漏纠正

- 当前小链允许在既有定义／文本中表达与该链有关的源结构证据；排除可执行SQL/API
  映射不等于排除这些证据。源结构已知、客户业务含义未确认和表示／交付缺口分别
  保留，物理约束不升级为客户基数、生命周期或业务规则，不复制源表行。
- 必要共享依赖须有具体依据／处置。“不做完整主数据”不能自动排除当前链所需的
  最小依赖；设备型号相关取舍有公开问题依据，业务关系仍只据获准来源或确认。
- Modeling在原阶段交接指出重要依据／依赖的实际候选位置或具体缺口，Coordinator
  在其可读范围核对原位置。沿用原handoff／note，不增加逐列台账、字段或硬门。
- CQ作者在原逐点自查中对齐Task输出与问题范围；实际问题／必答点区分结构证据、
  已确认业务含义及有依据的未知。Judge依冻结内容与实际证据裁决，有歧义按原
  question-answer-review路径处理。没有新packet字段、自动评分或隐藏信息回灌。
- 以上进入小链Task、实际增量生成模板、Modeling／Coordinator／CQ／Judge指令及
  Modeling／CQ技能，既有交接模板同步。只在复盘报告写建议不足以进入下轮。

旧题池／裁决继续作为旧基线保留；本次范围澄清不追改旧成绩、不删除难题、不拼接
不同版本的PASS。下一轮新CQ审核与后续独立裁决仍沿原授权和冻结流程。

## 代理错误与可恢复性

修改共用Responses代理：上游400、402及有界重试后的429／5xx保持真实HTTP状态，
不再统一降为502。错误正文、头、reason phrase继续丢弃；真实传输异常仍是本地502。
SDK将400报告为badRequest时，沿原provider_wait和显式绑定恢复继续同一线程；
不自动重试或换模型，owner／turn校验、未知写入及其他身份／安全错误保护保留。

T0复核：丢弃上游正文保护凭据／输入泄漏，仍需保留；将HTTP状态也抹去没有同等
必要性，却令可纠正错误难以定位。badRequest内容纠正可由宿主完成，原写入原子性、
授权、dry-run/application及显式恢复已保护完整性，无需永久终止run。

开发Agent仅拥有代理、Codex恢复实现及三个归属测试文件；未读取隐藏材料、未调用
真实供应商或修改其他文件。主Agent核对实际diff、运行全Team回归及准备配置检查。
GitNexus impact未找到Python handler；detect_changes为LOW但错映射部分旧符号，
实际影响按代理→GLM／其他路由、SDK错误→provider_wait／显式恢复的调用点及回归
验证，不宣称有效图谱覆盖。未修改backend／frontend，无应用服务重启要求。

## 下一轮模型与入口

[准备配置](../configs/2026-10-14-asset-fault-workorder.yaml)仅read/supervise，全部八个
角色通过现成`glm-flash-high`绑定`glm-direct / glm-5.3-flash / high`，包含Delivery、
Coordinator、Modeling、Protocol、CQ、Platform Examiner、Source Examiner及Judge。
requested／effective effort都为high，无DeepSeek或其他模型fallback。

旧run冻结模型不可热换。下一轮沿R4.0-029现成增量入口保留实际资源身份，登记新的
request/session/run及当前工作窗口。准备配置移除new-scope-create默认入口，不以
从零重建替代已有模型。原B请求与超时窗口不改写，也不恢复其DeepSeek等待项。

00:45:06Z只读核对原B增量入口：记录仍为WAITING_OWNER及4个provider_wait，原
监督PID已退出、control FIFO不存在。这不是可继续的live监督链；本次没有唤醒或
调用旧provider，也未把“无cleanup记录”称为资源清理完成。下一次沿正常增量入口
核对实际资源／writer／Attempt状态，不修改旧事件或凭空补写收尾。

| 组 | 原收尾保留绑定 | 原消耗／剩余 | 启动前本轮输入 |
| --- | --- | --- | --- |
| A | Project c88ce13a-21db-4927-80b5-e1237b402d5d；Ontology 4dcc39db-c7fa-4807-b4fb-418b869bb534；原revision2 | 已用1/3、余2 | 获准原资料、公开观察及可接受的最小业务补充；客户时间含义仍未知，不采用原被退回的样例推断 |
| B | Project b219fe3f-e89d-4163-860d-a1204e8e7627；Ontology 4344a455-6884-492f-adfe-7fa26c32bf0e；原revision3 | 已用2/3、余1 | 原批准资料、公开型号关系观察及已获准测试约定原文，保留测试来源与客户未知 |

实际GLM fresh start按所选组消耗其下一轮；不能把更换provider称作旧等待项免费
恢复。A/B不互借额度。启动时核对最新授权、源资源修订／writer状态、当前只读凭据
及冻结绑定，不复制旧过期授权或撤销key。用户尚未指定优先A/B，本次两组均保持
可选择的原账本，不自行启动；真实启动仍按现有20分钟优先规则，不重做全面准备。

CQ审核／测试代答沿所选组既有授权；需要新补充时使用独立业务会话和获准公开材料，
已读隐藏资料的宿主不能充当业务代答者。生产Agent不接收旧私有目录或本复盘历史。
首链反馈复用已修freeze file stem／报告schema／checkpoint路径，显式900秒session
timeout及实际Project read key。已有工程结果复用，下一轮观察实际回答与问题处置，
不把checkpoint或operation启动称作反馈完成。

## 本次验证

- 开发Agent：旧基线74 passed；新回归实现前7 failed；修复后三个定向测试文件
  **81 passed**，包括400／402无内部重试、429／503重试与计数、敏感正文／头／
  reason phrase不泄漏、badRequest可观察等待及原线程显式恢复、身份／turn反例。
- 主Agent：小链CLI validate、八角色精确profile绑定、GLM凭据preflight、准备配置
  在临时DeliverySession实际加载通过；read/supervise、无production、无新scope默认。
  小链与真实增量生成模板两份CLI validate均通过，ontology-modeling技能validator通过。
- 一次GLM公开工程连通检查：2026-10-14T00:35:11Z，请求glm-5.3-flash/high，上游
  HTTP200、返回同模型、完整OK响应，约3秒；仅一个上游attempt，无业务资料、工具或
  平台写入。临时loopback session停止、凭据缓冲清空。保留脱敏元数据
  [工程接口检查](../../../workspaces/glm-readiness-20261014/glm-public-provider-check.json)。
  这是实际接口可用证据，不是Consumer工具路径／建模质量／独立L1或性能PASS。
- 主Agent首次全Team：1 failed／2864 passed／11 skipped／318 subtests，失败仅为
  test_model_routing中旧固定502断言；更新为上游500并保留秘密抑制断言后，相关
  路由与三个provider文件**157 passed**。最后完整全Team：**2865 passed、11 skipped、
  318 subtests passed，270.11秒**。旧失败记录留在
  `/tmp/glm-readiness-team-20261014.log`，最终日志为
  `/tmp/glm-readiness-team-final-20261014.log`；最终产品代码期间未继续修改。
- 十二份Markdown围栏、三份YAML及六个新增／记录本地链接检查通过，差异空白检查
  通过；不把开发验证称为独立功能或语义验收。11个跳过沿现有套件条件保留。

本次只产生工程准备／API连通证据，没有semantic start、真实模型修订、CQ新冻结或
独立语义裁决。RETRO-07／08纠正实现后保持已实现待实测；首链反馈早期效果、完整
语义质量和净时间收益须在下一获准运行证明。
