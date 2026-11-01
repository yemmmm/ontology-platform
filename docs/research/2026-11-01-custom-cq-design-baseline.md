# 自定义 CQ：现状与设计依据

日期：2026-11-01。状态：现状核对及推荐设计稿完成；尚未实现产品功能或启动真实建模。

## 本次目标

用户希望把 Demo 已有九条问数问题长期保存为自定义能力问题（CQ），供建模与验证使用；
要求设计添加阶段、用户是否必须提供答案，以及公共／切片归属对用户的呈现。
已通过异步问题询问交付深度；本记录先完成不依赖答复的需求与设计，不将未答复视为
开发批准或否决。正式范围见[新增需求](../requirements/requirements-v5.0.md#r5-0-010)和
[功能设计](../delivery/designs/2026-11-01-v5-custom-cq-design.md)。

## 来源与已知边界

- 当前主线：[R5.0-002／003／006](../requirements/requirements-v5.0.md)：持续工作空间、
  增量建模、独立冻结验收与来源变化。
- 已有 CQ 合同：[R3.0-011／012](../requirements/requirements-v3.0.md)：公开／隐藏、
  审核、冻结、逐题证据和 SQL 实际执行分别记录；旧流程不因新能力被追溯修改。
- 当前样例：[九条问数及实际模型检查](2026-11-01-demo-model-to-sql-readiness.md)：
  四题支持、三题条件支持、两题缺少事件映射；这属于有界消费审查，不是隔离盲测。
- 实现核对：`backend/app/api/interview.py`、`backend/app/api/schemas.py`、
  `backend/app/repositories/models.py`、`frontend/src/pages/OverviewPage.tsx`，以及
  `modeling_team/v5/src/ontoweave_modeling/contracts.py`、`acceptance.py`。

## 先行设计原则

1. 用户面对项目中的业务问题；工作单元／切片归属是内部可调整的覆盖关系。
2. 添加问题不要求先知道答案。题干是目标，不自动成为已确认业务事实。
3. 参考答案、判定标准和来源充分性必须分开；材料不足保留待澄清，不能编造标准。
4. 活跃题库可以追加修订；每次执行使用确定版本，保留历史题集和模型版本绑定。
5. 给生产使用的题目可以用于独立回归验证，但不能再宣称隐藏题泛化效果。
6. 语义可回答性、SQL 生成条件及实际执行结果分别记录。

## 当前实现结论

核对基线为 `1e9776b`。平台已有项目 CQ CRUD，但创建及数据库外键均要求 Ontology；
旧验证器执行实体／关系／SPARQL 计数，不能证明问数语义或 SQL 能力。已有来源主要关联
访谈答案和 Brief 字段，编辑使当前验证结果失效，没有本设计所需的内容版本及固定 CQ
身份到 v5 题集的自动对照。

v5 `TaskBinding.prepare` 要求预先绑定 freeze ID、摘要及题数；公开材料按 manifest 固定，
`SourceRevisions.stage/activate` 支持原生回合边界激活下一完整来源包。
`evaluate` 要求 handoff_ready、核对同源材料和 frozen-questions 摘要；实际交给独立只读
上下文的是来源／冻结标准／目标。`validate_report` 校验完整编号和真实治理读取，现有
逐题 `passed` 布尔值不足以完整区分待复核和未运行。它不是旧 v3 的双角色答案盲测。

前端总览读取旧 run 题集／报告投影，目前没有项目自定义题编辑和 v5 选题接线。
GitNexus 查询命中旧 CQ 合同及测试，具体 v5 接点以本次定向源码核对为准，没有声称
完成图影响覆盖。本轮只变更需求、设计、样例数据及文档，没有产品代码变更。

## 产物与验证边界

新增 R5.0-010 和对应设计；将原 Q1—Q9 固定保存为
[设计种子](../../examples/llm-access-lab/competency-questions.json)。种子明确标为
design_only_not_imported，标准为草稿；没有写入实际项目题库，没有重跑旧模型或改变
既有验收。文档／JSON 的检查只证明格式、引用和九题一致性，不证明功能实现或真实语义。

本次定向检查：九条题干与原始 questions.json 完全一致；外部键九个且唯一；参考答案
均为空；18 个相关本地 Markdown 链接、两条种子来源引用、需求锚点及 D1—D8 完整性
检查通过。未运行产品测试或重启服务，因为本轮没有产品代码变更。
