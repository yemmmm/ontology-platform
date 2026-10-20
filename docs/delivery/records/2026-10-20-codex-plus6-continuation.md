# Codex追加6元与三次机会的接续

用户在上一轮PARTIAL结果后明确授权“继续授权6元＋三次机会”。复用
[R4.4-002](../../requirements/requirements-v4.4.md#r4-4-002)金额预算，原3元追加6元，
总授权9元；历史费用、暂估、未知和失败证据全部保留。模型继续为Codex／
`glm-5.3-flash`／`low`，业务仍为[R4.3-026](../../requirements/requirements-v4.3.md#r4-3-026)
通用最小安装链。上一轮结果见[原记录](2026-10-20-codex-three-starts-repair.md)，不改写其
当时三次耗尽及3元边界。

本轮授权稳定引用为`user-20261020-plus6-three-starts-152240`，Host目录
`workspaces/minimal-chain-20261020-codex-plus6-152240/`。沿原budget_ref追加，而非创建
新预算：`workspaces/minimal-chain-20261020-codex-glm-3cny-123453/budget`。
追加时已计估算3.57404452元，其中暂估2.582974元；追加后估算余额5.42595548元。
本地主账并非供应商实际扣费，Host及其他未接线成本仍在范围外。

## 第一轮接续

为减少重复CQ往返，采用已发布、完整审核冻结的`cq_frozen-0001`生产检查点，
source run为`minimal-chain-20261020-codex-restarts-135307-s3-r1`，实际新run为
`minimal-chain-20261020-codex-plus6-152240-s1-r1`，Delivery session同前缀`-s1`。
source官方stopped、CLEANED，所有原owner已退出；只读inspect显示原写入无unknown，
恢复入口重新核对，无需再登记stale live-writer settlement。旧材料按原权限复用，
不重做CQ、不将隐藏题／答案注入Delivery或生产角色。

生产检查点接续计入本轮第1次机会，实际semantic-start为
`2026-10-20T15:23:47.545747Z`，距授权登记约1分7秒；baseline为
`ed7d9c39320632a49e29108afaf9a1536743cda6f1a05e6461a1c203310121db`。
恢复origin明确绑定原检查点manifest
`sha256:827a95193a0ea9404247d7467ad88e87a04900f3559fa29cca55e9c75c71766a`，
原`glm-flash-low`模型配置继承，未覆盖生产profile。初始已用1／剩余2。

当前目标为完成application、实际受治理读回、自查／交接，再分别执行完整公开1／
隐藏3的独立Consumer／Judge验收。新线程、失败与验收消耗继续计入同一预算；
运行中、冻结成功、工程回归或工具成功都不等于语义PASS。最终结果及预算待原件闭环。


生产应用已取得真实原件：两个Class在Batch `0f22a07f-c831-4e40-9b9e-fd775181cc6d`
原子应用（revision 0→1），有向relation_type在Batch
`2a28460f-13e9-4bd2-883a-8592ed7252ab`原子应用（revision 1→2）。Host已核对
原回执的`batch_status/attempt_status=applied`及索引current；治理读回与最终关联扫描
由生产原角色完成，扫描3资源、21 statements，COMPLETE、无未决引用。生产自查PASS
与后续独立验收分开，不能互相替代。原件在新run的`evidence/platform-responses/`和
`handoff-materials/material-71a6b92081a846bf81d71898f5b9eed2/`。


## 本轮真实缺陷与窄修复

1. checkpoint恢复只还原冻结文件，不在新run重放`cq-freeze`事件；`_cq_pending`只查
   事件，导致已完成生产后Delivery仍等待handoff-ready。Host依据两次周期卡片定位，
   通过有来源的既有Delivery输入通道交付精确freeze技术绑定，正式complete_cq_handoff
   成功，未由Host代写模型或直接给语义PASS。持久修复只在无冻结事件时读取最新实际
   冻结文件，复用`reload_frozen_pool`重验摘要，返回原交接待办；损坏快照保留明确
   limitation，Runner仍负责角色、原子写入、未知和授权的正式复核，不重播事件或再冻结。
2. 隐藏批次多个Consumer共用一个provider-attempts日志，source元数据被最后注册者
   覆盖。旧计量额外要求每条代理记录的session等于文件最后注册者，误报其余已有
   原生用量的Consumer缺测。去掉这一不成立的文件级单成员假设，仍按记录自身的
   capture session／provider／credential alias／model精确匹配原生数值，原数值已计价，
   不再重复收费。另一会话或另一凭据的数值仍不能借用，无真实数值依据仍暂停。

T0复核：交接只读投影缺事件不应阻断已恢复成果；平台正式交接已负责写入及授权安全。
金额与身份守卫保留，但共享文件最后注册者并非全部记录的身份，删除该额外条件不会
削弱原生精确selector与数值核算。没有新增恢复／治理机制或业务特例。

新增回归先复现：恢复后无交接待办、损坏快照未报告，以及共享Consumer日志被末位
注册者覆盖。修复后Host核心94项通过，Host／预算定向151项通过；最终添加另一会话
不能借数回归后，当前Host／计量／owner与proxy相关135项通过。Ruff通过。当前源码
Team全量回归进行中，不以局部结果代替完整回归或独立语义验收。

首次公开／隐藏只读验收operation均因这次计量暂停保留退出1报告，正式停止后再重载
同一Delivery监督session（旧监督退出130，原临时平台凭据撤销）。生产run和revision2
模型保留，完整冻结不变，不重复应用、不扣新的生产启动。新计量重算后coverage缺口
清除，原账本总估算5.05956320元／暂估3.109508元／余额3.94043680元，沿原9元授权
正式恢复。重载只影响Host监督与计量，原生产角色未声称热加载了新代码。


## 原生窗口边界与最终验证

Delivery监督进程重载后，同一native usage文件包含新旧两个线程。各source已声明
`cumulative_segment.start/end`，但解析时未先应用该窗口，旧行被新线程绑定判为冲突，
新行也进入旧线程。修复复用原窗口过滤，再做原身份校验，不关闭真正的窗口内冲突保护。
共享代理source登记则累积本预算明确注册的capture session集合，避免覆盖前一Consumer；
集合外行不进入attempt投影，`not_admitted`仍关闭已有activity而不伪造供应商消耗。

窗口／共享来源问题均以真实原件定位。Host先保存投影，按原已声明窗口对两个受影响
native source重读，原始用量文件SHA256前后一致；来源集合只根据既有原生source注册
和同operation证据目录补齐。只修改可重算投影，不改费用授权、价表、业务材料或真实
用量原件。计量异常解除经原`continue_authorized`入口，并保留所有历史原因／回执。

当前相关回归172 passed；补足已注册但不同会话不能借数的负例后，当前计量17项通过。
最终生产源码Team全量 **3709 passed、12 skipped、318 subtests passed**，583.69秒，
359项warning、0失败；修改文件Ruff、diff及本地链接检查通过。期间中断的较早全量
回归日志单独保留，不冒充最终当前源码结果。只改modeling_team及文档，不涉及本地
backend／frontend应用代码，不需要重启ontology-platform.service。

GitNexus旧索引未解析到`_cq_pending`／`_refresh_summary`，impact为UNKNOWN；暂存
检测6文件／0符号／0流程／low。已检查`pending_items`、Host状态／待办、Delivery观察、
RuntimeBudget注册与计量调用点并运行相应回归，不宣称旧图索引提供完整影响覆盖。

## 独立语义回归结果与收口限制

Host技术补位沿既有`complete_cq_handoff(retry_of="attempt-0001")`建立`attempt-0002`，
原报告未覆盖。生产只读封口、正式stop回执及源owner退出后，Host运行原
`start_evaluation`／`get_evaluation_status`接口组织独立Consumer／Judge，不承担答题
或判分；独立进程只接收原获准问题与平台读能力，没有外层对话／私有修复历史。
近实时计量使用原TaskBudget monitor及EvaluationOwner控制通路，没有新建harness。

首批原生用量再次迟到触及10秒缺数门，数字到齐且当前coverage无问题后，Host正式恢复
同一组只读操作，没有再启动生产或改写报告。最终两组`exit_code=0`，报告资格校验有效、
无validation_errors，具体结果为：

| 组 | 原完整分母 | 执行／通过 | 重检 |
| --- | ---: | ---: | --- |
| 公开 | 1 | 1／1 | 3个响应重放，stable，无drift/unavailable |
| 隐藏 | 3 | 3／3 | 3个响应重放，全部stable，无drift/unavailable |

两份报告`full_pass=true`，model binding digest相同：
`sha256:0e1205ca62de2370ad6553be395473b8967410a37b7af49540baa87317867783`。
原冻结及选题范围一致，无未执行问题、空题集或缺失切片；coverage中的notes是说明而非
缺口。两份报告均带池级 **non-blind-regression** 标签，exposure记录为公开题；不能改称
盲测PASS。结果支持本有界完整业务范围的独立语义回归PASS，不证明较大业务场景质量。

报告原件在新run下：
`acceptance-v3/public-regression/cq-batch-0001/attempt-0002/batch-report.json`
（digest `sha256:c172b575fffe8cd82f9a825a60f994ad2496159207eb4e61d43d0af4792f943d`），
`acceptance-v3/reports/cq-batch-0001/attempt-0002/batch-report.json`
（digest `sha256:96fb540525421ef5a3d2bd80f650afc9a26918ee227fd779abcb8bd3f2ba5ac0`）。

本轮**不是Delivery自主交付PASS**。Host介入了交接、计量修复、监督重载和只读验收。
暂停控制期间Coordinator发生300秒llm-inactivity-timeout，原件保留；生产已完成且只读
封口，不能从该运行失败推导模型质量差。为停止已完成生产角色，Host提前结束源Runner，
因此最终`complete_cq_acceptance`缺少原FIFO，未取得Runner接收回执；没有重建生产来
补机械终态，也未伪造回执。原state保留READ_ONLY_WAIT而非强改CLEANED。自动流程／
正式收口及预算暂停尾差验收继续PARTIAL，与上述独立回归PASS分别记录。

## 最终授权、费用与资源

仅消耗本轮第1次生产检查点接续，**剩余2次机会**。正常只读重验、技术修复和监督重载
没有扣生产次数；没有为用完机会追加实验。原3元加本次6元仍共用同一budget_ref，
历史未知、中断及暂估未清零；价表保持原冻结版本。

| 主账字段 | CNY |
| --- | ---: |
| 累计授权 | 9 |
| 已定价数值小计 | 2.15651932 |
| 暂估 | 3.817436 |
| 累计估算 | 5.97395532 |
| 剩余估算 | 3.02604468 |

相对追加前快照，本轮新增估算2.39991080元；不是供应商实际扣费，Host和未接线成本
仍在范围外。两次监督及手动验收使用的六个临时平台密钥均经数据库核对revoked；
当前生产owner、四个验收operation和监督进程有正式停止／退出记录及精确PID不存在证明，
预算所有owner已退出。非空模型与检查点／原报告均保留，没有批量清理其他任务。
`final-budget.json`、`final-operation-verification.json`、两次监督及手动验收凭据生命周期、
`window-reconciliation-result.json`、`late-native-epoch17-resume.json`及最终测试日志为私有原件。

从本轮授权至语义报告约37分钟，真正生产建模约7分钟，其余主要为交接、计量修复、
等待和验收；不可把累计角色LLM时间当墙钟，也没有精确纯语义时间占比证据。按主目标
停止扩展平台／harness，复用已冻结模型完成最短只读验收；未证明全任务token降耗。
