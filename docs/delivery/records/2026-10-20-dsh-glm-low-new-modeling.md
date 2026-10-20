# DSH GLM low 新授权最小链建模（2026-10-20）

**初建一轮完成模型，技术修复后独立公开1/1、隐藏3/3非盲L1通过；额度已用1/3、余2。**
没有验收后实质修模或新的生产start。两次只读验收尝试和两次未进入模型调用的错误入口启动
不扣建模轮次。原目标已完成，不为验证优化消耗余量。

## 范围与实际结果

用户授权：“请启动一轮建模任务，agent选择dsh glm-5.3-flash low，授权三次额度”。
沿最近已验收的[R4.3-026](../../requirements/requirements-v4.3.md#r4-3-026)最小安装链Task／DSH Profile，
仅使用原scenario.md业务来源，新建项目及Ontology；没有扩大到工业场景。
Delivery、Coordinator、Modeling、CQ、独立Consumer和Judge均为DSH／glm-5.3-flash／low。
详细原件摘要、完整分母、用量及线程见[数值证据](../evidence/2026-10-20-dsh-glm-low-new-modeling.json)。

- session=`minimal-chain-20261020-dsh-glm-low-new`；run=`minimal-chain-20261020-dsh-glm-low-new-r1`。
- 初始代码`c8a4c8f`；02:49:51.470057Z真实semantic start，符合授权后20分钟启动要求。
- project=`af021b51-fa55-4b84-bde6-aeb1b252a3d4`；ontology=`dbd2a633-5f7e-423d-bbfc-522c0addca5a`。
- 两批原子application：两个owl:Class及一个有向owl:ObjectProperty，revision 0→1→2。
  Modeling自行纠正不支持的字段与缺失name，实际使用correction.request_ref及request_edits；
  首次补丁路径错误也在原线程纠正。没有Host代写语义或静默修参。
- 当前revision治理读回确认关系端点与方向，关联自查COMPLETE、3资源、0 issues，写Session关闭。
  无具名实例事实，保留原未提供的基数及实例未知。
- CQ全景与切片由Host对照来源逐点私审；freeze=`cq-batch-0001`，
  digest=`sha256:6a1e54d6f4ffdc34870e9922c2c61f17ac0e54f12a79b3b2c2e6a5bde4d20837`。
- attempt-0002公开1/1、隐藏3/3逐题pass，未执行题为空，同freeze／model_binding，
  治理读回复核无漂移、无lifecycle error；两组均保留同一协作元数据告警。
  Judge使用新独立进程，未生产或修复原模型。结论为有界L1 **non-blind-regression**。
- 03:14:38.589138Z Runner接受验收`pass`，03:15:09.743574Z接受standby，
  Delivery随后finish_delivery并进入read_only_wait。源模型、原Team和报告保留，未收到stop。
  03:16:29Z本组临时管理及验收read凭据撤销成功；任务完成后Host结束主动监督。

## 第一阻塞、T0复核和恢复

attempt-0001公开及隐藏Consumer已运行，但Judge setup都因
`collaboration_binding_changed: invalid scenario map`未生成裁决，原fail报告完整保留。
实际唯一map问题是`shared_terms[0].candidate_refs[0]: candidate unavailable`：
Coordinator为fields-only交付填写了不存在的候选ID。此时模型与保留读回均无漂移，
缺少的是可相信的协作引用，不能据此判模型语义失败。

按AGENTS T0：手册描述的来源、授权、模型绑定与handoff摘要仍需硬校验；
可选协作引用不是语义证据，其缺失风险已被实际授权读取、模型状态复核和独立Judge覆盖。
最窄修复在`_cq_collaboration_context`现有路径中加入candidate unavailable：仅在模型绑定
稳定时，从Judge工作副本省略该条不可信引用，显式标unknown并保存原位置warning。
未知漂移、handoff摘要变化、map结构错误及身份冲突继续拒绝；冻结原图不改。
Coordinator权威提示及compact合同同步要求：fields-only没有正式候选时candidate_refs为空，
实际请求／application／读回引用放notes，不得编造候选定位。此提示尚未在新的生产start验证。

宿主通过两次当前session私有Host交接回传修复／正确入口。首次重验操作用了旧
production-handoff.json，被`cq_handoff_immutable`准确拒绝，未进入模型调用；
attempt-0002实际已发布于`acceptance-v3/handoffs/attempt-0002.json`。
改用该文件后公开、隐藏两组新进程真实运行通过，未创建第三attempt或重开建模。
正式issue不存在，因此没有伪造issue或调用resolve_issue。

## 工程检查与限制

- 红灯复现：新增单元／真实CLI测试2 failed、1 passed，均指向同一Judge setup硬拒绝。
- 最终相关回归：45 + 122 + 119 = **286 passed**，覆盖Judge启动及报告warning、
  原件不变、未知模型漂移／摘要变化／map结构和身份冲突保护，以及最小链合同。
- Ruff、Task/Profile/model配置和diff检查通过。直接在本轮保留map及真实读响应上重放，
  仅省略已定位引用，原件digest未变。Team代码变化无需产品服务重启；backend/frontend未改。
- GitNexus impact找不到实际函数；detect_changes把未改的post_drift映射至大量流程并给出
  CRITICAL标记，已告知用户。采用实际diff、单一调用点及相关回归，不声称完整图覆盖。
- Host技术补位、平台窄修及错误入口纠正均保留，因此不是自主Delivery PASS。
  Delivery诊断时read_delivery_artifact曾返回私有验收报告正文，此读取隔离缺口未在本轮扩修；
  之后没有生产修模，也没有隐藏内容发送给生产的证据，独立Consumer/Judge身份不受替换。
  技术补充使用旧stdin包装，角色元数据为user但正文明确标Host，不作为业务审批或新增授权。
- 有效语义工时及重叠等待／修复工时无精确证据，不把存活或阶段墙钟冒充有效工时。
  没有扩展harness或额外工程实验。L2、更大业务、自主交付、隐私边界和净降耗未由本次关闭。

## 用量

DSH统计截止2026-10-20T03:16:29Z，覆盖16个实际线程、失败验收及全部重试，原生响应去重无冲突。
input含cache-read；未提供的cache-write／供应商内部工作及账单保持unknown。
Host截止03:16:29.450Z，包含准备、监督、修复测试和此前整理，后续文档／提交／最终答复尾部未计。

| 角色 | input | output | 合计token |
| --- | ---: | ---: | ---: |
| Delivery | 10,426,659 | 46,411 | 10,473,070 |
| Coordinator | 1,028,380 | 15,186 | 1,043,566 |
| Modeling | 2,137,209 | 12,730 | 2,149,939 |
| CQ | 122,495 | 2,720 | 125,215 |
| 独立Consumer | 641,455 | 10,121 | 651,576 |
| 独立Judge | 410,913 | 3,811 | 414,724 |
| DSH全链 | 14,767,111 | 90,979 | 14,858,090 |
| Codex Host | 13,303,434 | 24,720 | 13,328,154 |
| 全任务已知下界 | 28,070,545 | 115,699 | **28,186,244** |

完整任务10M目标本轮未达到，不从成功首轮、缓存率或局部机制采用推导净降耗。
