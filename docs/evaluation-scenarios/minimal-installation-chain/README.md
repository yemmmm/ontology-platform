# 最小安装位置链（R4.3-026）

本场景仅覆盖“安装资产→现场”：两个概念、区别、一条有方向的安装位置关系及明确未知。
2026-10-20 起作为**通用建模的业务测试基线**，使用同一套通用角色指令、Skill 和共享
技术合同。旧精简角色运行的模型、冻结输入及裁决保留原义，不作为新组合的通过证据。
本次配置更新不启动真实建模，也不追加任何运行轮次。

唯一业务输入为 [scenario.md](modeling-input/scenario.md)，版本
`minimal-installation-chain-source-v1`；[输入清单](modeling-input/input-manifest.json)记录 SHA256。
历史来源为 [checkpoint-minimal](../checkpoint-minimal/modeling-input/scenario.md)，仅复用定义，
不继承其恢复实验目标或历史结果。新业务版本另行保留，不覆写已冻结运行的输入。

选择同一通用 Profile，Task 只选择当前业务范围、资料及独立题集：

- [最小链 Task](../../../modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml)
- [通用 Codex Profile](../../../modeling_team/profiles/unified-modeling.yaml)
- [通用 DSH Profile](../../../modeling_team/profiles/unified-modeling-dsh.yaml)

原 `r4-3-026-minimal-installation-chain` 两个 Profile 文件名仍可使用，均已改为相同的
通用角色配置。旧 minimal-chain-* 角色包、专用 Skill 和 compact 合同仅保留为历史
对照，当前基线不加载。共同方法或缺陷修复只更新通用提示面，不再维护最小链特例。

只读配置校验（不启动模型、服务或平台写入；模型 Profile 按当时授权另选）：

```sh
env -u DEEPSEEK_API_KEY uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/unified-modeling.yaml \
  --task modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml
```

## 实际输入与职责

| 角色 | 方法与业务输入 | 职责与边界 |
| --- | --- | --- |
| Coordinator | 通用 coordinator 指令、场景图／拓扑和当前共享合同、唯一业务说明 | 范围／拓扑决定、业务派单、公开反馈与交接；当前路径不等 Protocol |
| Modeling | 通用 modeling 指令、ontology-modeling Skill、共享表示／直接提交合同、唯一业务说明 | 忠实表达语义层级及角色、完整候选或合法字段型定义提交、治理读取、自查及关闭资源 |
| CQ | 通用 competency-question 指令和出题 Skill、既有 CQ 合同、唯一业务说明、独立私有草题 | 正常审阅、版本及公开／隐藏冻结；私有内容不进入生产角色 |

与其他业务任务使用同一通用角色时，角色指令、Skill 及其参考文件来自同一路径和字节；
Task 身份、业务目标、源路径和运行授权范围按实际任务变化。共享技术合同使用通用源，
三类任务的流程参数也一致，包括可用的检查点能力；不自动开展检查点实验。
不把完整工业服务业务资料引入最小链。运行时仍冻结实际 role_sources、角色包、Skill
与 Task/Profile 摘要；source-manifest 和 baseline 是加载版本证据，配置表不代替实际执行。
工程验证及全量回归限制见[对齐记录](../../delivery/records/2026-10-20-unified-minimal-baseline.md)。

[四道私有草题](cq-private/question-seeds.json)只交给 CQ，分别覆盖概念区别、关系方向／
物理位置含义、所有权误读和未给定事实处理。通用 CQ 方法将其作为待审阅输入，不当作
业务真值、冻结答案或 PASS 证据。公开题仅经 Runner public projection 进入生产；隐藏题
不进入 Coordinator／Modeling，独立 Consumer 不接收草题／参考答案。题数按业务范围和
正式审阅决定，不凑通用建议数量，也不增加虚构跨切片义务。

## 获准运行时的最小闭环

使用现有 Host／Delivery 运行及 CQ 工具，不新增启动器、验收器或角色。输入就绪且用户
授权后，保留真实开始时间；正常 CQ 审阅冻结、Agent 自主决定拓扑，Modeling 按 024／025
提交，程序确定性转换并原子应用。成功回执按 015 信任，未知写入先按原身份对账；不加
Protocol翻译审批、独立模型dry-run或成功后例行重复核验写入。

取得当前修订上的真实治理读取／业务回答，记录 scope、修订、索引状态、授权与完整性
限制；执行已有关联自查和资源关闭后交接。独立 Consumer／Judge 使用本任务新冻结题集
及实际运行证据，只读验收，不能继续／修复生产或修改保留证据。材料格式通过、apply成功、
公开反馈或自查均不能单独给出独立语义 PASS。首阻塞按 modeling-quality、platform-contract、
collaboration/routing 或 runtime/infrastructure 归因；保留失败、返工及原始证据。

时间线复用每次运行自己的记录与既有事件，至少包含：输入就绪时间、当前用户授权引用与
时间、两者均具备的起点、semantic-start、首次真实成功写入、首个有实际治理证据且经核对
有效的回答、独立验收结论或截止点。分别记录从同一起点到写入／首答／验收的墙钟耗时，
语义工作、技术处理、等待及返工的区间与依据；重叠区间不重复累计，无法分摊写 unknown。
不能将 Host 看到日志的时间冒充模型回答／应用发生时间。失败或未结束不称成功性能基线。

用量复用 [R4.3-019 Host报告](../../../modeling_team/references/model-usage-report.md)：记录
角色、模型、原始 usage 引用、输入／输出、缓存读写与覆盖缺口，缺值为 unknown，累计
输入不等于费用。未调用角色写“未启动”，已调用但缺失统计写 unknown，二者区分；账单／
价格依据未覆盖时不估算真实费用。不为补统计增加启动硬门，不设新的分钟数或token额度。

## 保留与逐级回归

| 顺序 | 独立选择与业务范围 | 后续验证边界 |
| --- | --- | --- |
| 1 | 本最小 Task／Profile | 两概念一关系的实际应用、治理回答、独立语义验收及成本；当前未运行 |
| 2 | [资产—故障—工单小链 Task](../../../modeling_team/tasks/r4-0-009-asset-fault-workorder.yaml) | 沿原范围、原适用题集与各自运行证据继续验证；本次不关闭历史缺口 |
| 3 | [完整工业服务场景](../industrial-service-v3/README.md)及[完整 Task](../../../modeling_team/tasks/r4-0-009-multiview-semantic-acceptance.yaml) | 保留原题池／裁决，R4.3-001的27题及120／60分钟目标须有各自真实证据 |

[历史 checkpoint Task](../../../modeling_team/tasks/r3-0-015-minimal-flow.yaml)及其
[恢复实验说明](../checkpoint-minimal/README.md)继续保留原用途。所有旧材料、模型、题集、
运行证据均不删除、不就地裁剪或改名。各级结果独立记录；最小链PASS只说明此最小范围，
不替代原小链、完整业务或恢复实验的验收。后续运行仍遵守当时授权与剩余轮次。
