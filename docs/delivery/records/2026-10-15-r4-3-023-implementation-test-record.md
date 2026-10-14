# R4.3-023 实现与测试记录

- 权威范围：[R4.3-023](../../requirements/requirements-v4.3.md#r4-3-023)。
- 设计：[权威任务派单与模型表示边界](../designs/2026-10-15-r4-3-023-authoritative-dispatch-design.md)。
- 本次授权：“请完成R4.3-023需求的实现并进行测试”。代码起点 `6f39c46e74df1afd5b07043e50ecb8bb33226c99`。
- 工作区原有未跟踪 `docs/presentations/`、`slide-deck/` 保留，不纳入提交。

## 实现范围

Runner 在 v2 生产角色输入的可变尾部追加真实 `Task identity`，原始 objective 仍逐字保留；
v1、隔离 Acceptance 分支、提示静态前缀、checkpoint continuation 和角色源过滤沿用原合同。
Coordinator 派单引用同一 task_id，只补充阶段、必要依赖、剩余范围和真实业务确认，不取代 Task。

Modeling 指令、ontology-modeling Skill 及其既有参考统一为：必要已知事实进入模型的允许
定义／文本或普通节点／关系，说明源结构适用范围；技术文件／行号及 item 定位留既有交接。
保留具体客户未知、源时间／空值条件及必要依赖，不把源唯一性等提升为客户业务规则。
派单冲突和格式错误沿原通道纠正，真实扩范围等原授权方决定，表示不足明确未交付。
未新增字段、来源追溯、平台语义裁判、审核角色或不可恢复硬门。

仅小链 Task 移除 API／SQL 映射参考；Coordinator／Modeling／Protocol 和 Skill 的相关读取
改为任务包含且实际挂载才适用。完整映射 Task 保留参考。小链明确选择统一图候选合同，
避免两个可见参考被理解为任选 envelope；该增量来自本轮受控输出反证，属于 F3 的合同对齐。
未实施 R4.3-024／025，未修改 backend／frontend，无需产品服务重启。

GitNexus 对 `_task_text` 的定向查询未命中 Runner 方法，不能声称有其图影响覆盖；
已检查唯一调用 `TeamRunner.start → adapter.start_task`、所有 return 分支及相关回归。
`detect_changes(scope=all)` 返回 low、0 affected processes，但索引遗漏上述方法，结论仅作参考。

## 工程检查

1. 新增 `test_r4323_authoritative_dispatch.py`，先复现缺少身份与不适用参考仍挂载的失败，
   再验证真实 prepare/start 传给 capture adapter 的输入、两种 objective、源文件字节／角色
   私有挂载、所选候选合同、必要参考、其他 Task、可变尾部及续跑内容；不调用 provider／平台。
2. 定向四文件回归：`test_r4323_authoritative_dispatch.py`、`test_prompt_cache_contract.py`、
   `test_r23002.py`、`test_r4007_multiview.py`，**102 passed、18 subtests passed**。
   显式候选合同补充后，身份／缓存两文件 **31 passed**。
3. 首次 Team 全量：**2966 passed、2 failed、12 skipped、318 subtests passed**。
   两项均为 Coordinator 既有恢复提示的旧文字断言；让相同测试读取 HEAD 原指令亦复现两项失败。
   只把断言更新为现行 self_resumed、原 gates／Host 证据、其他报告者的定向恢复合同，
   没有改变恢复程序或恢复提示。两项定向复测 **2 passed**。
4. 最终 Team 全量：**2968 passed、12 skipped、318 subtests passed**，332.27秒，
   exit 0；356项为既有 rdflib deprecation warnings。补充合同选择后的定向测试亦通过。
5. `ontology-modeling/evals/validate_skill.py`、新增测试 Ruff 和 `git diff --check` 通过；
   本轮新增链接／锚点及需求、实现记录与跟踪状态检查通过。

Team 命令从 `backend/` 执行：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q
```

最终完整输出保留于
`workspaces/r4323-controlled/team-regression-final.log`，测试跳过不当作已执行通过。

## 有界角色输出与反证

使用本次实现／测试授权进行隔离上下文的 Coordinator／Modeling 调用；只读取各自获准材料，
使用公开 delivery-10 摘要及 delivery-26 错误派单片段，不输入 r2／r3 修正答案或隐藏题。
这是当前协作运行时的受控角色输出，不是原 GLM 同模型／effort 复跑，也不是实际 Team Transport。
冻结／阶段前提为测试假设；无真实平台读写或生产 semantic start，未消耗生产建模轮次。

证据目录：`workspaces/r4323-controlled/`（按仓库约定 gitignored，不提交生成候选）。

- `coordinator-task.txt`、`coordinator-output.md`：首版派单引用实际 task_id，将必要源事实
  放入候选、技术定位留交接，保留未知及小链边界；Coordinator 未读 schema 私有源。
- 第一轮 `modeling-task.txt` 未在 objective 明确选择统一图。实际首版选 ordinary envelope，
  统一图校验返回 `candidate is not r3-0-009-unified-graph/v2`；不能记首版 PASS。
  调用方明确请求统一图且 Coordinator 引用了统一图，角色仍优先采用通用 ordinary 说明。
  原始 ordinary 文件被子 Agent 在纠错时删除；`modeling-candidate-observed-ordinary.json`
  为重构证据视图，不能证明与原始约 32K 文件逐字一致。`modeling-candidate-r1.json` 是纠错中
  暂存的统一图版本，`modeling-candidate-r2.json` 为后续修正；两者都不是最初 ordinary 首版。
  r2 的现有统一图 validator 通过（39 items、10 unknowns），不以此覆盖首版失败。
- 已将所选 `r3-0-009-unified-graph/v2` 写入小链 objective，沿真实 prepare 生成
  `modeling-task-selected.txt`。新隔离上下文只接收更新输入、原获准来源与派单，不接收
  第一轮候选或失败答案。`selected-modeling-candidate-r1.json` 为该新上下文的真实首版，
  **现有统一图 validator 返回空 issues**（13 items、5组具体 unknowns）；
  `selected-modeling-candidate-first-observed.json` 保留首次观察字节，终态 SHA256 相同：
  `f73ccd0f18d1ae36e4d9b2016812ab752b8bd33a551d41f7c97e17bd3825f0ef`。
  数量仅定位产物，不是覆盖或质量通过依据。
- 人工对照指定反例：`entity-asset` 及现场／型号关系保留非空外键；`entity-fault-event`
  保留资产外键、报告／发生／关闭条件；`entity-work-order` 及故障关系保留非空、唯一、
  外键和响应／到场／恢复／解决四项时间条件及空值分支。源枚举明确限定到源列；
  `unknown-work-order-fault-cardinality` 等保留客户关系、派工及生命周期未知。
  必要现场／型号定义仍在，未复制样本业务行或新增可执行映射／第二业务链。
  这些内容存在于候选 `value`、`business_meaning`、普通关系和既有 unknown 字段内，
  技术文件／行定位留交接；没有增加顶层／item 字段或追溯字段。
  `value.source_structure` 为该候选的业务值内容；本轮没有翻译／写入，不能据候选存在
  推断实际持久化或检索可消费，也不裁决整份模型的最小性／完整质量。
- `selected-modeling-output.md`：四种追加输入的实际拟回复保留必要事实、按定位修复格式、
  不擅自扩范围／确认业务基数，真实表示不足保留未交付与影响；没有要求新审核或永久终止。
  这些是受控响应文本，不是实际 Team Transport／恢复执行证据。

初始及变更输入摘要分别保留于 `input-sha256.json`、`final-input-sha256.json`；最终
所选合同输入保留于 `selected-input-sha256.json`，产物摘要及通用校验结果为
`selected-schema-check.json`；已核对终态输入字节与 manifest 一致，不能把较早摘要当作
最后加载版本。角色调用标识：`r4323_coordinator_probe`、`r4323_modeling_probe`、
`r4323_selected_contract_probe`；首轮失败与修正后新上下文结果分别保留。

## 验收边界

| 条目 | 本轮证据边界 |
| --- | --- |
| A1 | 真实 Runner 组装／capture adapter、源字节及既有隔离／缓存回归；没有启动真实 provider sandbox |
| A2／A3 | 首轮失败保留；更新后新上下文首版格式及指定反例的事实／未知／依赖保留检查通过；模型写入及读回未执行 |
| A4 | 受控角色对冲突、格式反馈、真实扩范围、假设表示不足的拟回复；不冒称实际传输／运行恢复验收 |
| A5 | 实际加载清单、必要参考与完整映射 Task 回归；不从字节减量推导费用／时间收益 |
| A6 | 未执行：本次不恢复暂停生产运行，真实模型写入／治理读取、同条件改善及独立 Consumer／Judge 待后续授权任务 |

本次真实语义建模有效时间为 0；工程测试、提示修改及受控输出不计为真实语义建模，
未测量可用于提速比较的有效工时。实现／受控输出通过不能关闭真实质量与提速验证。
