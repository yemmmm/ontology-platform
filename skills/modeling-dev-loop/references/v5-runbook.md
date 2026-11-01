# v5 Host 启动与接续

归属：[R5.0-001—007](../../../docs/requirements/requirements-v5.0.md)、
[v5 入口](../../../modeling_team/v5/README.md)。本文件不授予真实运行、额度或测试代答权限。

## 选择任务与准备

1. 核对当次目标、授权、模型／effort、获准原始材料、实际资源及独立冻结题集。默认模型沿
   `glm-flash-low`；默认新任务金额沿 AGENTS 的 3 元，Host 先创建稳定金额账本并在 Task
   写入 amount／budget_ref。本轮明确不限额的研发任务可沿其既有 usage_only 特例。
2. 创建 v5 Task，形状见 v5 README。instructions 只需本任务补充：prepare 会冻结当前
   v5 方法、ontology-modeling 的可复用业务分析／多视角章节与既有动作／流程／规则／接口
   语义合同；这些内容固定进入新 binding，不依赖环境 Skill 自动发现，也不恢复旧执行路由。
   不要手工复制旧角色包。新任务建议
   semantic_workspace/shared_memory/work_management=true，按业务需要委派，简单任务无需子级。
3. 获准材料按 manifest 固定 ID／路径／SHA256；生产只拿公开投影，隐藏题另存独立包。
   scope 使用 create 或明确 existing Project／Ontology IDs。新建项目在实际创建后自动
   关联项目工作空间，无需提前猜 Project UUID。多个获准本体的创建变更用 ontology_targets
   明确放置；现有资源更新沿实际验证目标。当前入口不承诺任意自动扩展项目或授权范围。

已有 Operation 的精确读取使用 `operation-detail`；映射精确读取使用
`table-mapping-detail`／`join-mapping-detail`，普通
`entity-detail` 不覆盖这些资源。`model-read:<family>:<ontology_id>` 引用使用该真实 family。
实际关系核对可使用 `resource-relations`，返回整个获准 Ontology 的关系图；它不按传入
anchor 过滤。按返回端点核对所需关联，并保留 paging／completeness 限制。
若读取只返回 IRI，更新还须有已核实的原生身份；可由 Host 将同 revision 平台快照中的
显式 `v:id`／资源类型与实际应用回执交叉核对，交接到原有 `applied-bindings.json`。
保留快照、核对及交接回执，不猜 IRI 后缀、不改候选，也不把一次人工技术交接称作
自动 existing 初始化已经验证。当前该初始化仍需后续单独闭环。

```bash
scripts/modeling start --task /absolute/task.json \
  --postgres-config /absolute/postgres-private.json \
  --run-dir workspaces/v5-runs/unique-run
scripts/modeling status --run-dir workspaces/v5-runs/unique-run
scripts/modeling work-tree --run-dir workspaces/v5-runs/unique-run
scripts/modeling board --run-dir workspaces/v5-runs/unique-run
scripts/modeling questions --run-dir workspaces/v5-runs/unique-run
```

## 输入、控制与故障

有问题时沿 reply 关联 request-id；主动输入使用 input，保留真实 author 和适用范围。
测试代答仅在用户明确授权时构造并署名，不记录为用户本人业务确认。暂停／停止在当前
原生回合自然结束后停稳；恢复使用原 run。单次工具完成不代表原生 turn 完成。
预算追加只接受 Host 真实授权文件，不改变用户暂停；五小时限额或上游 429 需按实际
证据处理，不换模型绕过。原始用量、失败及未知不能补零。

blocked/recoverable_issue 先定位第一层，能安全修复就继续原目标。不确定写入先沿原
operation／Batch／Attempt／receipt 对账。正常 resume 复用原编译计划与执行身份；
不能因无回执盲重发新操作。只修真实失败层，不另建监督框架或替 Agent 写业务答案。

材料变化使用 source-revise 的完整新包，声明 change_id、reason、affected_units 及必要的
affected_records；旧材料、成果和验收保留。变化在自然边界激活，未变单元复用。
来源撤回只标待重审，由 Agent 判断语义影响，不自动判原陈述为假。

## 总览、快照与验收

生产用 get_modeling_context、精确记录和材料引用续接；消费者／用户总览由
overview-refresh 的独立只读上下文从实际模型生成。overview-show 重新核对当前范围及
模型版本；needs_review 仍能导航到原依据，但不得视为当前确认。sections 可按业务需要用 children
逐层展开，共享定义在多个专题引用同一实际 IRI；每层引用均须来自真实读取。消费者总览仍只含
已应用模型，不代表候选／工作／验收多截止点视图已经实现。精确问题回读实际定义。
根级／局部自查提供已有 workspace_context 导航；local／project_local 同时覆盖分配给本单元
及本单元署名的记录。后续页保持 scope、unit_id、include_authored=true 和 next_offset，
不要把有界首页当作全量。状态和正文仍由 Agent 据原文及实际模型更新，不自动置为完成。

snapshot-save 的默认观察模式可在 busy 时保存；include-platform 另存真实平台数据。
snapshot-fork 复用平台分叉，会归档源项目全部本体，必须显式 archive-source，并先让
共用该项目的运行停稳封口。它创建全新原生上下文；不热恢复旧会话或继承旧验收 PASS。
未知分叉结果保留预分配目标，先读回，不换目标重试。

handoff_ready 只表明生产可交接。evaluate 使用独立输入、凭据及只读上下文，绑定冻结实际
目标；公开小场景不冒充业务盲测。大型业务可用 scope-file 指定冻结子范围，保留原主标准及
scope_id/base_freeze_id；父级仍读取原始整体条件和实际模型独立判断，不只合计子级分数。
required-artifact 的记忆／摘要为待验对象，不能补成模型本身缺失的事实。
独立提示的 source_ids 同时列入自动产生的 human-inputs；必须直接读冻结题和每项来源，
不能以别的工件引用代替。历史读取明确标观察者，原单元检查按确切执行／代次／模型版本
核对；旧证明、预期动作或 Host 观察不能冒充后继实际检查。

父级整合子级后，可在建模提案的可选 review_units 声明需要实际读回的已就绪直接子级；
程序在应用或 no_change 后、父级整体自查前调用原单元。中间单元可在自身提案声明直接子级，
按该声明自下而上检查，本层证明绑定实际子级检查引用。下级需修模时先回原单元及祖先，
不伪造中间层 ready，也不强制所有子级或固定层数。旧自查结果的 review_units 路径保留。
Host 可用 check-unit --unit-id 显式安排有界生产自查；依据原候选／来源、代次及实际模型
版本复用或更新证明，不新开应用写入方。非 ready 结果重开原单元及祖先，沿原预算修订。
检查证明的 governed_read_material_ref 指向原始治理读取材料，随结果一同交给父级；
父级需要核对时通过 read_handoff_material 分段读取，保留其确切模型版本。
这仍是生产闭环，后续 evaluate 的上下文、冻结与只读隔离要求保持。

验收结束后保存必要快照及用量，stop 并 cleanup；实际写入的工程模型默认保留，临时
读取／协议／组织管理员密钥须有撤销回执。历史原件不覆盖。

## 历史迁移与回退

旧 `python -m modeling_team` 不读取 v5 checkpoint；`scripts/modeling --legacy` 保留该路径。
迁移旧业务时，先自然停稳并核对原操作，再将获准原文、地图／决定及来源作为显式材料，
以 existing 绑定真实模型。Agent 复核后写新工作空间；缺原依据、未表达及未知准确保留。
原 task_ref／budget_ref 保持，不因新 run 清零。旧原生会话和旧 PASS 不热迁。
回退默认入口只影响后续新任务，已写入的 v5 run 仍沿原版本接续，不回滚实际模型。
