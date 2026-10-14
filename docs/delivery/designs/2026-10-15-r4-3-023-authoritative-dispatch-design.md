# R4.3-023 权威任务派单与模型表示边界设计

## 1. 范围与事实基线

权威范围：[R4.3-023](../../requirements/requirements-v4.3.md#r4-3-023)。2026-10-15用户要求
“请细化并设计R4.3-023需求，通过独立验收”。本轮交付需求、设计和独立设计验收，
不实施活跃指令／代码，不启动服务，不调用业务建模provider或恢复暂停运行。
代码基线：`efc4d7aa0a58c1a58bea9a46881e1d9465b004df`。开始时只有无关未跟踪
`docs/presentations/`、`slide-deck/`；不纳入本条。独立设计验收Round 1 PASS，0 Critical／High，无未决关键假设；工程及真实效果未验证。

问题例子：源表工单的故障引用非空、唯一且有外键；客户是否允许多次派工仍待确认。
候选没有source-locator字段，不妨碍在允许文本中表达这一源声明。技术文件定位在交接
材料，事实内容在模型；客户派工基数未知亦在模型明确保留。写成业务一对一、把已知内容
只放handoff、或把整件事改称未知，都是不同的错误。

事实依据为[GLM小链根因分析](../modeling-retrospectives/2026-10-14-glm-smallchain-retrospective.md#后续根因分析输入表示理解与流程负担)：
delivery-10识别源事实，delivery-26要求另放handoff，delivery-30的r1遗漏；没有新业务
答案加入后，明确纠正表达任务使r2／r3补齐更多事实。历史r5未应用、正式独立语义验收
未开始，保持PARTIAL；不将该根因分析升级为完整模型质量裁决。

## 2. 当前入口与最小增量

| 入口 | 当前可核对行为／缺口 | 后续最小改动 |
| --- | --- | --- |
| `modeling_team/runner.py::TeamRunner._task_text` | v2从`configuration.task.objective`原样生成尾部`Task objective:`；任务身份未在此明确给出，角色私有源由`role_sources`列出且要求完整初读 | 对生产角色在尾部可变任务区给出真实`task.task_id`，保留原objective逐字和角色源过滤；不重复注入完整YAML |
| `TeamRunner.start`的`adapter.start_task`调用 | 每个实际Profile角色直接接收`_task_text(role)`、required_skills、roster，不必经Coordinator转述 | 沿用此直接路径；任务绑定测试检查实际传给adapter的输入 |
| `modeling_team/runtimes/codex.py` | 使用package的instructions，按角色准备运行材料；现有baseline记录Task／指令／Skill摘要 | 保留隔离和摘要证据，不新增Task注册表、read acknowledgement或访问全仓的工具 |
| `tasks/r4-0-009-asset-fault-workorder.yaml` | objective已要求保留必要源结构、未知和依赖，但仍为各角色挂载排除的API／SQL映射合同 | 强化事实内容与技术定位的分别去向；仅移除此Task的两项不适用参考 |
| `agent-packages/coordinator/instructions.md` | 阶段派单有链／依赖要求，内容核对仅限其可读源；现有范围检查不能阻止实际转述偏移 | 在现有派单／阶段核对位置明确Task引用、已确认补充及冲突纠正，不授权Coordinator另定语义或字段 |
| `agent-packages/modeling/instructions.md` | 当前阶段段落允许在definitions/text **or** handoff保留源声明和locator，可能将事实一起移出模型 | 改为必要事实模型内表达；technical locator在既有handoff，真实业务未知单独保留 |
| `skills/ontology-modeling/SKILL.md` | 已要求源结构进入允许定义／文本；既有源反查与候选反查足够 | 与角色段落同一边界，补冲突处理；无关映射章节按Task／实际挂载适用 |
| `references/r4-0-012-modeling-contract.json`、`platform-neutral-candidate-authoring.json` | 已列统一图／普通候选、未知、semantic_definition及禁止追溯字段 | 复用字段合同，不增加source字段或新候选版本 |

这不是“Modeling原来收不到Task”的结论：原始objective已直接注入。缺口是运行身份
显式可得及后续派单／表示文本有歧义。`task.snapshot.yaml`是Host留存原件，不直接
给Modeling整个文件，避免附带其他角色源与执行配置。表示合同必须仍为Modeling获准
可读材料，不能只发一条文件名而不挂载。D1—D6主决策表在权威需求，不复制理由表。

本轮只改文档，未进行GitNexus符号影响分析，也不宣称图覆盖。后续涉及`_task_text`
跨角色行为时检查全部调用和提示缓存测试；工具不可用时按AGENTS做聚焦call-site检查。

## 3. 权威输入、派单与冲突

### 3.1 直接任务输入

权威业务范围由当前已选Task的原objective及实际用户授权补充共同确定；可用字段由
当前获准表示合同确定。不能用Task的自然语言例子放宽closed schema，也不能用角色
历史路线上不适用的说明排除Task已经允许的内容。真实未决冲突沿原通道澄清。

身份展示采用尾部可变任务区中的`Task identity: <configuration.task.task_id>`，保持
原`\n\nTask objective:\n`及逐字objective作为任务正文；有原checkpoint continuation
时保留其现有追加内容。不要把task_id写进候选语义字段，不要求从objective或名称猜测。
仅对Coordinator／Modeling／Protocol等实际生产输入补充身份，保留v1及隔离Acceptance
专用分支的行为，不向后者追加生产范围或材料。沿用`test_prompt_cache_contract.py`
检查仅objective变化时静态前缀字节相同；身份属于可变任务区，不引入动态提示生成器。

### 3.2 Coordinator派单

初始分工仍服从当前roster／通信边和CQ冻结顺序；资料分析不冒充semantic modeling。
在原阶段派单正文中引用实际task_id，指出：当前链与必要共享依赖、全局剩余范围、
本阶段所需成果、已收到的真实业务决定。引用原Task而不是重新拼一份“精简权威任务”。
业务答案保留原文与既有reply_to_delivery_id；不重复转发或混同Delivery guidance为业务确认。

Coordinator只能用自己获准已读资料与Modeling交接中的实际item／缺口核对范围及依赖。
schema未对它挂载时，不为本条扩大授权；请Modeling处理语义及给定位。不能因自己看不到
原schema宣布事实不存在，不能把handoff只有描述判作模型已有表达。来源定位可在交接，
但不允许“closed item无locator，所以把必要事实都另放模型外”的派单。

### 3.3 Modeling收到冲突

用原Team Transport正文报告：原Task条款、冲突派单内容、影响的事实／候选item、拟按
权威允许字段进行的修正。内容是自然语言说明，不新增专用冲突schema／工具／审核状态。
例如：“Task允许文本保留工单故障引用源声明；派单要求仅留handoff会使模型缺少此事实。
本阶段将源声明写入允许说明，技术路径留交接；客户派工基数保持未知。”

已有允许范围内的转述纠错无需新业务批准；推进不受影响部分，Coordinator纠正同一
阶段指令。模型候选的既有审批／执行授权并不因此跳过。真正扩大范围、争议业务结论或
实际字段合同无法表达时，经Coordinator／Delivery请求有权方决定，并明确保留缺口。
用现有issue／状态反馈具体阻塞，不新建永久run拒绝、固定尝试上限或审核角色。

## 4. 模型内表达与技术定位

| 内容 | 位置与要求 |
| --- | --- |
| 当前链所需已知源字段、声明值、约束和条件 | 实际候选允许的定义／文本、必要普通节点／关系；语义说明明确其为当前源结构声明及适用对象，不自动升格为业务规则 |
| 客户生命周期、业务基数、状态含义等尚未确认内容 | 现有explicit_unknowns／definition unknowns，写出具体未决问题，不抹去同一对象的已知部分 |
| 技术文件路径、行号、approved source locator | 既有handoff／场景地图note，连同候选revision／item定位；不增设候选追溯字段，模型内无需逐条技术引文 |
| 已分析但本阶段未交付，或实际表示缺口 | 同一交接的明确未交付内容、影响和下一责任／输入；地图按R4.0-014反映局部表达及剩余工作，不能宣称全完成 |

不固定实体数、Class数、谓词名或逐字段清单。普通候选`semantic_definition`放在
`semantic`内；统一图候选用现有item可选`semantic_definition`。统一图的
`business_meaning`亦可承接允许文本。普通匿名relation不直接加semantic_definition，
需要局部关系含义时用已有普通语义节点和显式关联；不更改候选／平台schema。

以下是**语义措辞示意，不是完整可执行候选或新增字段合同**：

> 源结构声明：当前工单源的故障引用声明为非空、唯一，并引用故障标识。
> 该声明描述此源表的约束；客户是否允许对同一故障多次派工尚未确认。

该内容可放在支持它的定义说明中并关联相关对象。源唯一性不能直接写成“一次故障
业务上只允许一个工单”，外键也不直接证明真实客户关系方向／基数。时间CHECK保留
真实布尔条件与空值分支；只写“遵循时间顺序”不足以替代必要具体条件。样本出现几个
状态不证明合法值全集；源枚举声明描述的是该源列允许值，客户状态语义另保留未知。

不编制table_mapping／join_mapping，不导入资产／故障／工单业务行，不写OWL／SHACL
或专用规则脚本来执行源约束。必要设备型号／现场等共享定义按批准来源或范围内澄清
处理，保留未知，不因整片主数据排除便丢掉当前链依赖。

建模流程继续用选定Task已有候选、执行及治理读取合同。023不把旧dry-run／Protocol
流程确认为新目标，也不提前落实024；024交付后，本条只机械对齐表示入口、角色和验收
产物称谓，以上内容／授权／未知边界保持。不得仅为验证023重建即将退役的写入流程。

## 5. 读取减量与实施交接

小链明确排除API／SQL可执行映射；从它的`role_sources`删除
`r4-0-011-api-mapping-contract.json`及`r4-0-010-relational-mapping-contract.json`两项。
这只去掉该Task的coordination参考挂载，不删除文件、不改变其他Task的映射能力。
保留四份业务source、r4-0-012表示合同、neutral authoring、scenario-map、staged/unified
执行合同、CQ及r4-0-024关联检查等角色当前确实使用的材料。各角色仍仅获取自己的清单。
原初读政策不泛化修改，必要sources仍完整初读，重复未变材料继续复用原合同。

角色和Skill中的API／SQL映射章节只有Task包括相关范围且实际挂载对应参考才适用；
没有挂载不要求读该固定路径，不找替代私有来源。本期不整体重写701行Modeling提示、
历史正式任务分支或Profile，不拆出通用条件编排／动态source选择系统。

后续开发范围：上述Task、两个活跃角色指令、ontology-modeling Skill、Runner任务身份
注入和对应既有Team测试；若必要，在相关reference的既有说明中机械对齐术语，不扩展
schema。仅原角色指令／Skill和选定小链Task产生语义增量。复用
`modeling_team/tests/test_prompt_cache_contract.py`、`test_r23002.py`、
`test_r4007_multiview.py`的真实任务组装／源清单测试，加本条小链反例测试；不写一次性
语义裁判脚本。Skill变化运行已有`ontology-modeling/evals/validate_skill.py`。
Runner行为变化按仓库Team回归要求从backend运行
`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests`，若改backend
则额外遵循backend全量与重启规则。本轮无执行代码／活跃Skill变更，无需这些产品测试。

## 6. 验证、独立性与停止条件

A1—A6以[需求验收表](../../requirements/requirements-v4.3.md#r4-3-023)为准。

- 设计验收：独立Agent读取权威需求、设计、必要当前代码／活跃合同，核对能否按最小
  改动实施、有无范围或兼容阻断，记录Critical／High及未决关键假设。独立设计PASS
  只证明方案可交接，不意味着新提示已加载或真实质量提升。
- A1／A5工程合同：检查真实adapter输入、精确task_id／objective、角色可读清单、
  缓存兼容和其他Task保留映射；不是实际Modeling行为。
- A2—A4受控行为：后续获得有界Agent调用授权后，以原delivery-10／26／30的
  公开失败片段和当前可见源构造对照，不给r2／r3修正答案或隐藏题。检查改后派单与
  Modeling真实首版输出。静态字符串检查或作者手写示例不能独立证明输出覆盖。
- A6真实效果：仅后续获准任务，从现有baseline／semantic-start／交接保留实际加载
  身份和派单，检查候选中的必要内容、写入回执及受治理读取。失败定位须区分源表达
  漏项、转换丢失、检索返回不足、Consumer答案遗漏与runtime阻塞。非空／唯一／
  外键／时间条件可消费，客户未知不被猜定，才有本条真实质量证据。

比较先只改派单／表示提示，后独立比较无关参考减量；同范围、源、模型／effort保持。
024写入路径变化需另记，不能并改后把所有收益归023。记录逐项追补、语义有效耗时和
流程／基础设施耗时；无同条件比较不声称定量提速／成本收益。正常成功信任回执，
读取为业务解释目的，不新增每条写入校对；最终Consumer／Judge不得创建或修复生产run。

设计必要选择全部关闭、独立设计验收PASS且文档检查通过即结束本轮。RETRO-07／08
只更新设计进度，实施／真实效果仍待验证；不将既有额度当成本轮恢复授权。

## 7. 独立验收与文档检查

独立设计验收**Round 1 PASS，0 Critical／High，无未决关键假设**。输入摘要、核对范围
及独立结论见[验收记录](../records/2026-10-15-r4-3-023-design-review-record.md)。
审阅期间共享需求文件由另一任务登记025、调整024程序能力归属；Reviewer补读后确认
023正文未变且无设计阻断。本设计仍只负责派单与表示边界，024流程所依赖的确定性
转换执行由025承接，未接管两条实施。工程A1—A5与真实A6均未执行。

文档检查：本次新增本地链接／锚点、Markdown围栏及表格、F1—F6／D1—D6／A1—A6、
状态与diff检查通过；只提交023所属修改，保留另一任务的024／025变更。无代码或
活跃Skill改动，无产品测试或重启；机械检查不证明实际角色行为或建模质量。
