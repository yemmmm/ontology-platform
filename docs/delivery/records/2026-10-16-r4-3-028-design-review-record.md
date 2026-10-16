# R4.3-028 独立设计审阅记录

## 授权与证据边界

用户要求“请完成设计并独立审阅”。本轮仅设计、独立审阅及必要文档修订，不实施
代码／活跃提示，不运行产品测试／服务／provider或真实建模／语义验收。开始代码
基线`ecffdcb`；无关README及演示材料保留。原输入合同工程证据不扩大到新增能力。

- [权威需求](../../requirements/requirements-v4.3.md#r4-3-028)。
- [详细设计](../designs/2026-10-16-r4-3-028-incremental-model-awareness-design.md)。
- 独立Reviewer：`/root/r4328_design_review`，`plan_reviewer` Agent；非需求／设计作者。
- Reviewer只读核对文档及源码，不编辑设计，不生成／修改被验收模型或运行证据。

## Round 1 — REVISE

结论：**0 Critical／1 High**。关键未决假设为跨图Mapping如何从029当前scope及已
确认依赖接通现有引用激活，方向不能由程序从自由文本猜测。

| 审阅输入 | SHA256 |
| --- | --- |
| requirements-v4.3.md（全文件） | `94f61e59f256d37b1ecfcf6a7654cc82d708ba0c7a9c3d7e4290dd93927f95b5` |
| 028详细设计 | `2ddb53aa6de781ea4e5a1e5ec9ff9a3bf5a6249be9b487bc42760ad633fd51cf` |

**H1 — 跨Ontology映射引用准备遗漏。** 设计原§6及§9.1只覆盖获准多图读取、真实
资源绑定和placement。`semantic_mapping_state.py::mapping_state`仅将owner自己的
图和reference_ontology_ids开放给映射目标解析，`semantic_mapping_integrity.py`会
据此校验TableMapping的mappedClass／mappedDefinition。029的prepare_incremental
未传mapping_reference_direction，Runner原拓扑路径跳过引用激活。O1创建Mapping
引用O2旧Class时，找对身份和位置仍可能invalid_resource_reference，重复补读不能修复。

作者定向核实上述代码后修订设计§6.1及相应需求F7／D13、实施和验收：029透传已有
显式方向；只依据已确认cross_slice_dependencies准备引用；兼顾开门后才发现的依赖，
在原直接Mapping路径给可恢复反馈；复用既有配置接口，保留现有引用及其他owner；
加入“可读未激活→确认激活后成功”集成反例。不放宽平台校验、不泛化普通关系门，
不新增引用管理／恢复框架。修订本身尚不代表独立复审通过。

Reviewer完整读取适用AGENTS、028需求和设计；核对029、007、024／025，增量Task／
入口、Modeling加载、只读工具与代理、ObservedModelBindings、compiler、namespace、
Runner归属／通知／意图重用、Executor及映射校验。未执行产品测试、启动服务或真实
建模，没有GitNexus图覆盖声明。

## Round 2 — REVISE

同一Reviewer重新完整阅读028及全部设计，核对029快照、scope准备、原引用helper、
Mapping校验及原Round 1相关接点。结论：**0 Critical／1 High**。原H1其余部分已闭合，
仍缺“启动时省略方向，之后发现Mapping时如何获得可信方向”的具体接点；当前方向
只在PlatformScope.prepare加载一次，确认新依赖不会改变它，冻结启动请求也不能改写。

| 审阅输入 | SHA256 |
| --- | --- |
| requirements-v4.3.md（全文件） | `619430176e218178731e53df08fa08508af2d3d4f79e7f44582a3121549c6628` |
| 028详细设计 | `c95066ed65c3a7cd4f471b3f96d7b2c509078916dc6849737c651cd10fd7ccfd` |

作者进一步修订§6.1：新Task明确from依赖to的端点约定，prepare_incremental对新请求
始终写入实际方向；省略选项使用该合同默认，反方向仅显式选择，通过原Task提示／
scope通知让角色知晓实际约定。新依赖确认后无需热改scope即可同run继续；历史缺值
run保留配置缺口，不自动修改冻结约定或新增start。补对应默认／反向及晚发现依赖
验收，不添加runtime setter或管理服务。修订等待独立完整复审，不自判PASS。

## Round 3 — PASS

同一Reviewer完整复审当前028及全部设计，结论：**PASS；0 Critical／0 High；关键
未决假设：无**。原H1闭合：新029任务始终绑定明确依赖方向，实际约定对角色可见；
晚发现的Mapping依赖沿既有必要确认和引用配置接通，不改冻结启动文件；历史缺值
不冒称有热修改能力。其余旧身份解析、placement／去重、授权／修订、单批原子与
跨批状态、实际加载及不泄露答案的独立增量验收安排均一致。

| 审阅输入 | SHA256 |
| --- | --- |
| requirements-v4.3.md（全文件） | `7f76bf0a960334ec3187b1a53ad8e8e2304174c69c3a5275dc84fbbc6e25e5a4` |
| 028详细设计 | `6f8b8c8401071d9a8526a7d6bf2c2cf232ff027079aeedf5e5d004a27d7f3943` |

作者在状态同步前独立计算上述摘要，与Reviewer报告一致。Reviewer结合前两轮核对
范围再次核对方向准备及运行接点；只读，未修改文件或执行产品测试／服务／provider／
真实建模。设计通过不代表实现、独立功能、大模型真实增量语义或效率已经通过。

## PASS后同步与文档检查

PASS后仅更新需求顶部／总表／028设计状态及验证边界、设计第10节审阅状态、本记录
和优化台账；未改变F1—F10、D1—D13、A1—A10或设计§1—9行为合同。状态同步后的
整文件摘要不冒称上表审阅原件，无新实质设计变化不重复审阅。

文档链接／明确锚点、围栏、F／D／A连续编号及diff检查通过。未改代码／活跃Skill，
无需产品全套测试或服务重启；这些文档检查不证明工程或真实语义质量。
