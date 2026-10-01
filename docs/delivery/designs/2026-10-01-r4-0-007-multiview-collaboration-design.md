# R4.0-007 多视角建模协同与既有流程适配设计

- 日期：2026-10-01。
- 状态：需求细化与设计完成；D1 已由用户明确确认，其余设计按本轮授权形成。
- 权威范围：[v4.0 R4.0-007](../../requirements/requirements-v4.0.md#r40-007-多视角建模协同与既有流程适配)。决策主表在该条目。
- 基线：定向核对 `41e14a3` 的活动合同、场景地图、统一候选、Protocol、Batch、检查点和交接入口；
  006 有并行实现，本文仅把其授权行为作为依赖，不接管该实现。
- 本轮不实施、不启动服务或真实建模、不执行独立审阅或功能／语义验收。

## 1. 目标与最小方案

“关闭工单”同时被现场服务与返修流程引用。返修流程希望增加关闭原因时，先判断它是局部
限制还是共享动作合同变化：前者只调整该调用；后者交主维护方检查两个流程的参数、条件和
规则，形成完整修订再交 Protocol。不能在返修视角另造一份同义动作，不能修改共享动作后
仍称旧流程已兼容，也不能因为另一个无关切片尚未完成而停止已确认内容的工作。

复用当前 Coordinator、Modeling、Protocol、CQ 与独立验收职责，在现有场景地图上补充协同
信息；不新增逐视角 Agent、版本服务、流程调度器、共享注册中心或新的运行阶段。
用户确认 D1 为“引用当前定义＋变更前重审”；破坏性变更必要时建立经确认的新定义，
本期不纳入同一身份的多个可用版本及版本固定读取。

## 2. 现有基础与已确认缺口

| 入口 | 已有能力 | 本条实际增量 |
| --- | --- | --- |
| [场景地图合同](../../../modeling_team/references/r3-0-002-scenario-map-contract.json)、[校验器](../../../modeling_team/scenario_map.py) | 切片、共享术语及唯一 owner_slice、跨切片依赖、问题和调整 | 当前以 term 判重；补稳定 definition_id、确认状态、视角覆盖和重审记录，允许同名异义 |
| [活动 Task](../../../modeling_team/tasks/r4-0-012-tracing-suspension.yaml)、[Modeling 合同](../../../modeling_team/references/r4-0-012-modeling-contract.json) | 选择现有多切片、统一语义图和 CQ 路径，明确无追溯义务 | 选择新场景地图合同，说明多视角交错分析及责任交接；继续使用现有运行路径 |
| [统一候选和审批](../../../modeling_team/staged_decisions.py) | 完整候选、item 内容摘要、业务决定与翻译审批绑定 | 候选字段不为协同元数据扩容；复用内容绑定来使旧批准不能批准新内容 |
| [Protocol mechanics](../../../modeling_team/protocol_mechanics.py) | definition_ref、既有资源绑定、统一投影与回执校验 | 核对跨候选共享身份到已批准物化计划的唯一绑定；缺失返回可修正问题，不能按名称猜测 |
| [Batch](../../../backend/app/services/modeling_batches.py) | expected_workspace_version、dry-run、apply_atomic 和恢复 | 不增加语义兼容判断；工作区漂移需重新读取、重审、dry-run |
| [受治理读取](../../../backend/app/api/semantic.py)、[read model](../../../backend/app/services/semantic_read_model.py) | 资源、关系／statement-list、graph-set 范围及授权过滤 | 本条用现有读取补查已有引用；不声称现有接口已有跨视角影响分析服务 |
| [Runner](../../../modeling_team/runner.py)、[checkpoints](../../../modeling_team/checkpoints.py) | 场景产物打包、摘要校验、原地接续、production_handoff | 让新场景地图版本随原文件保存恢复；验收资料组装包含获准协同内容，不能只改静态模板 |

`build_unified_entity_binding_receipt` 支持统一图的既有实体绑定；R2.3-003 专用的
`build_existing_entity_binding_receipt` 有需求限制，不能直接当作 R4 通路调用。
`build_identity_binding` 中的 `evidence_ref` 是 Protocol 的获准读取技术凭据，与已停用的
平台 Evidence 资源不同；沿用其技术用途，不向 Modeling 增加引用原文或留存证据任务。

## 3. 责任与分析顺序

| 责任 | 输入与输出 |
| --- | --- |
| Modeling／共享定义主维护方 | 使用获准材料和公开 CQ，提出业务定义、局部含义、冲突与修改方案；将视角覆盖及重审结论交 Coordinator；不猜 IRI、不维护 Batch |
| Coordinator | 维护场景地图、唯一主维护切片及其负责人，协调引用方意见；确认来源充分时按现有审批批准，否则向业务负责人提问；不能以流程批准制造业务事实 |
| 引用方 | 在当前切片语境检查对象身份、参数来源、条件、规则、映射和公开 CQ；可由同一 Modeling Agent 承担，不要求新增角色 |
| Protocol | 读取批准内容，解析语义身份与回执／已读资源的绑定，生成和提交计划，报告准确的合同、版本、写入与读回结果；不决定同义或兼容 |
| CQ／独立验收 | CQ 保持公开问题与隐藏题池隔离；独立验收读取冻结资料和实际语义结果，不参与生产修复，不把协同记录当作语义 PASS |

建议从流程轮廓开始，再分析对象和角色、Action 与规则、流程绑定与分支；数据库／接口盘点
可提前辅助访谈。依赖已满足的部分可交错推进，源字段名不能直接确定业务含义。视角覆盖
记录属于切片，不规定每次七个视角都有产物，不改变 Ontology 拓扑决定权。

## 4. 场景地图的最小合同增量

下列是待实施合同，当前代码仍只接受旧字段。实施时在现有 reference 中明确新增
`r4-0-007-scenario-map/v1`，按 schema_version 分派旧、新地图；活动 R4 Task 选择新版本，
已有保存包按原版本读回，不迁移、不改写历史产物。不引入泛化 Schema 插件系统。

顶层沿用原来的 scenario_id、slices、shared_terms、cross_slice_dependencies、
cross_slice_competency_questions、explicit_unknowns、adjustments、topology_decision_ref。
只改变以下三个既有条目的封闭字段合同；其他部分仍用原校验。

### 4.1 切片视角覆盖

`slices[]` 保留原字段，增加 `viewpoints` 数组，元素只有 `viewpoint`、`status`、`note`。
`viewpoint` 为 object、behavior、rule、role、process、data_mapping、interface_mapping；
`status` 为 pending、modeled、unknown、not_applicable。note 说明当前范围、缺口或不适用理由。
同一切片同一视角不重复，未登记视角表示尚未评估，不等于不适用。无需为凑齐七项制造空模型。
这是建模覆盖说明，不是给 RDF 资源新增视角标签，不承担正式语义角色声明的功能。

### 4.2 共享定义登记

`shared_terms[]` 保留 `term`、`used_by_slices`、`owner_slice`、可选 `notes`，增加：

| 字段 | 含义 |
| --- | --- |
| definition_id | 当前场景／获准 Project 内稳定、非 IRI 的语义键；按此唯一登记，不再按名称判重 |
| meaning_scope | 简短业务含义及适用范围，用于区分同名异义；权威完整含义仍在语义候选及模型 |
| status | proposed、confirmed、unknown 或 conflict；是业务确认状态，不是已写入／验收状态 |
| candidate_refs | 数组；每项为 candidate_id、revision、item_id，绑定当前完整统一候选中的定义位置；尚无候选时可为空 |

definition_id 由 Coordinator 从已批准共享身份中沿用或分配；Modeling 在候选中继续使用原有
item_id／definition_ref，Coordinator 明确登记二者对应。一个定义可在多个完整候选中被带入，
但必须由主维护方确认同一含义，Protocol 绑定同一已有身份，不重复 create。若内容不同，先
形成 conflict，不能靠 definition_id 强行合并。term 相同、meaning_scope 不同可以登记多个键；
同义是否合并由业务判断，平台不从文本相似度推断。

主维护方用 owner_slice 连接 slices[].owner，不另加 Agent roster 或权限角色字段。负责人
调整沿用 adjustments；业务含义不变时 definition_id 与已有 IRI 不变。维护责任本身不授予权限。
跨新 run 复用时读取已有场景地图／检查点与获准模型重新绑定；不从名称重建身份。缺少可信绑定
时保留待确认，不能把新 run 的同名 item 当作既有定义。

### 4.3 变更与引用重审

`adjustments[]` 保留 change、approved_by_coordinator；增加可选 `review` 对象。
普通切片调整仍只用原字段，共享语义修改才记录 review，不建立独立变更数据库。

| 字段 | 约束与用途 |
| --- | --- |
| definition_ids | 本次修改涉及的已登记共享定义键，可多项，包括被引用的参数／规则定义 |
| before_refs、after_refs | 与 candidate_refs 同形，准确指向修订前后候选；首次新建 before_refs 可为空；既有定义需先取得获准基线 |
| coverage | complete 或 incomplete；仅针对本次已声明的业务／授权范围，不表示全 Project 无隐藏引用 |
| coverage_note | 本次范围、检查来源、读回限制及未闭合依赖的文字说明，不复制受限内容 |
| references | 本次实际检查的引用项数组，见下文 |
| outcome | pending、ready、deferred 或 conflict；由 Coordinator 记录实际业务处理结果 |
| reason | 为什么可采用、需推迟或存在冲突，不把 dry-run 成功当兼容理由 |

`references[]` 每项只有 `candidate_id`、`revision`、`item_id`、`slice_id`、`result`、`note`。
result 为 unchanged、revised、unknown、conflict；revised 指向 after 修订，其余指向检查过的
当前修订，note 说明影响及旧位置。尚无候选的已存模型由 Modeling 在获准读取后纳入完整
基线候选，再由 Protocol 保留平台绑定；不能把平台 IRI 填进 Modeling 的中立字段。
与外部消费者有关但未能定位为候选项的影响写入 coverage_note／显式未知，coverage 不得标 complete。

这是当前工作内容和决定的协同记录，不是来源追溯或逐资源证据包。候选摘要、读取凭据、Batch
和回执继续由既有宿主／Protocol 保存，不在这里重复设计技术凭证字段。
approved_by_coordinator 只表示该调整记录获协调确认；outcome=deferred/conflict 不代表允许
应用破坏性修改。真正允许 apply 的依据仍是现有绑定内容的业务决定和翻译审批。

## 5. 修改与物化路径

### 5.1 初次建模与候选修订

1. Coordinator 确定切片与共享身份；Modeling 在每个获准切片内交付完整候选，标明局部差异、
   unknowns 与 conflicting_meanings。确认身份后跨候选引用统一登记，不能传 patch 让 Protocol 猜最终含义。
2. 复用 002—005 的实体声明和普通关系。行动调用、参数、规则输入输出属于依赖图的一部分；
   场景地图只协调整体状态，不复制这些结构形成第二套模型。
3. Coordinator 对实际内容作原有决定；Protocol 翻译与绑定。定义先于其引用物化，平台 ID
   来自既有资源的获准读取或先前正式回执。顺序是写入依赖，不是业务流程执行顺序。
4. 每个 Batch 走 dry-run／apply_atomic 与读回，未知写入沿既有恢复路径核实后继续；不增加
   整个场景一次原子写入的要求。读回核对共享资源只有一个身份及每个局部引用的含义。

### 5.2 已有共享定义修改（D1 已确认）

候选修订号描述一次产物，图／workspace version 描述技术状态，规则 script_version 描述脚本
自身版本；它们均不是引用固定版本，也不能证明向后兼容。本期继续引用当前受治理定义。

Modeling 比较完整旧、新含义及实际引用，至少检查：对象／参数身份、必填与基数、值类型和
单位／时间／空值、前置条件与效果、规则脚本与说明／输入输出／适用范围、外部 Operation
及映射对应。纯措辞调整也需说明含义未变；平台不自动给出 compatible=true。

查找范围是本次获准模型的明确引用和已知业务依赖：先沿候选关系、参数和调用绑定定位
直接引用，再沿这些引用的已知依赖扩展到会改变解释的流程、规则、映射和公开 CQ；无影响
则记录理由终止，存在环时对身份去重。不是无界扫描整个仓库／外部系统，也不能只看一跳
后宣称所有间接消费者均兼容。脚本／自然语言内的隐含依赖由 Modeling 判断，缺乏依据时记未知。

Protocol 用受治理的资源／statement-list、获准 graph set 与必要的现有查询补查已存关系。
statement-list 有界且不是自动分页影响索引；返回限制、截断、范围缺失或读取过期时
coverage=incomplete。按已知 graph set／查询范围有界补读可缩小缺口；仍不完整则不能
声称全局兼容，更不能为查全而绕过授权。读取绑定的技术版本在申请写入前重新核对。

| 判断 | 处理 |
| --- | --- |
| 含义相同，只补充已确认解释 | 保留共享身份，重审后原位更新；不要求无关引用改变 |
| 变化只属于某个调用上下文 | 修订局部绑定／附加条件，保留共享定义 |
| 共享变化影响的引用都可同步修订 | 同一 Ontology 可进入同一个原子 Batch 时共同提交；dry-run 后仍核对真实语义，不能以结构通过作兼容证明 |
| 破坏性变化需要跨 Batch／Ontology，或不能证明旧引用仍安全 | 不原位覆盖旧定义。经业务确认建立新定义，先写新定义及必要参数／规则，再逐组切换受影响引用；旧定义保持旧含义，未切换引用继续有效 |
| 信息不足、已知冲突或写入状态未知 | 延后受影响修改，保留旧定义，继续独立内容；无旧定义时只交付明确未知／冲突，不伪装成已确认业务断言 |

新定义是经确认的不同合同／适用范围，必须写明与旧定义的差异，不是每次编辑自动复制一份。
不自动清理旧定义，不宣称支持同身份版本选择；删除已有定义也先检查引用，不能以强制删除
绕过重审。多个 Batch 之间没有原子性，不能把写后补审或暂时错误的旧引用作为正常中间状态。
本条不建设并发发布或版本固定能力；未来若业务必须同身份保留多个可用版本，另行明确需求范围。

重审结论不得跨候选修订直接复用。after_refs 更新时，引用方重新判断实际差异；已有
candidate_content_digests／projection_digest 绑定确保旧业务批准和旧翻译批准不能释放新内容。
场景地图不新增覆盖所有请求的总开关；可修正合同错误只拒绝对应不安全提交，返回字段／条目位置。

## 6. 授权、冲突与恢复边界

- owner 是工作责任，不是语义读取 Grant。006 的主体／角色适配不得改变本条这一边界。
- 受限对象不存在性合同保持既有 404／空结果和宽查询过滤；不能向无权 Consumer 暴露受限
  引用数量、名称或“存在隐藏影响”的信号。内部重审仅在已授予的职责范围内进行；公开交接
  可声明“结论仅适用于本次范围”，不得投影私有地图原文或隐藏 CQ。
- 已知业务冲突写入现有 unknowns／conflicting_meanings 和对应 review；Protocol 只报告
  可定位的结构、引用、版本或翻译冲突，允许完整修订后重试。不新增 Agent 数量／协作顺序硬门。
- v4 地图字段或引用错误沿 ScenarioMapIssue 可修正反馈处理；错误包含条目和字段路径。
  合同校验检查字段、身份唯一性、切片和候选引用闭合，不判定自然语言兼容或全局业务正确性。
- checkpoint 保存原场景地图及已有候选、审批、计划和回执；接续时保留 owner、未知与
  pending/deferred，已确认内容不重做。版本或实际资源漂移时仅重审受影响内容。
- fork-to-new-project 保留中立语义键，平台绑定随既有 fork 合同重建；旧 Project IRI／
  workspace version 不能直接用于新项目。不增加自动恢复服务或改变现有不确定写入处理。

## 7. 实施交接及验收

授权开发后，在现有文件上做必要差异：

1. 场景地图 reference／validator：增加明确的新版本和三处字段增量；增加同名异义、身份
   重复、候选引用、修订过期及新旧版本分派的合同测试。
2. 活动 Task 的 role_sources、Coordinator／Modeling／Protocol 指令、Modeling Skill 的相关
   方法和 Runner 实际组装输入：同步覆盖、维护、冲突、引用重审与完整候选要求。CQ 仍只接收
   公开资料，不能因协同内容扩展获知隐藏验收信息；不向 Modeling 下发技术凭据要求。
3. Protocol：以既有 unified identity binding 和已批准 materialization plan 对齐共享定义；
   如发现共享 item 被误当 create，修复最窄绑定层。不新增中立 update 指令、业务兼容服务。
4. Runner 检查点打包／接续和验收资料组装：确认新地图被保留且权限可见性正确；production_handoff
   沿用既有写入 readiness 语义，不把视角数／review 行数作为不可恢复终态门。
5. 后端读写路径优先不改；若实际实施发现无法保持身份／读取引用的合同缺口，先给出现有
   失败证据再做最小适配，不能以本设计授权任意新增接口。008 的上下文召回仍独立交付。

功能验收对应需求 A1—A9，必须使用真实活动输入组装和候选→审批→翻译→写入／读回的合同，
不能只断言 Markdown 含某个单词。尤其用同名异义与“新增必填参数但旧流程漏绑”反例验证。
检查点验证保存／接续后仍保留未完成重审，fork 不能复用旧平台绑定。

若仅修改 Team 可执行代码，运行相关 Team 合同／回归；若改 backend，补行为测试并运行
`cd backend && uv run pytest`；若改 frontend，执行规定 build／Playwright。后两类代码变更
按仓库要求重启服务并验证端点。文档阶段只检查链接、格式及需求—设计—验收一致性。
真实语义 A10 留待 009 统一授权；功能证据不得代替真实语义质量，也不得由生产修复方独立验收自身。

## 8. 决策及当前边界

D1 已由用户明确确认，D2—D7 已按需求主表形成方案，本轮没有待定的必要决策。006、008、
010、011 后续字段变化仅按相邻职责机械对齐，不重新打开已经确认的业务边界。
本次授权止于需求细化与设计，开发和验收按后续授权执行。

本轮完成静态代码核对与需求／设计文档，没有执行功能测试、真实建模或独立审阅；文档检查结果在
本轮交付回复记录，不将设计完整性写成实现或语义 PASS。
