# 最小安装位置链（R4.3-026）

本场景仅覆盖“安装资产→现场”：两个概念、区别、一条有方向的安装位置关系及明确未知。
它复用历史人工素材的定义，拥有独立任务、材料版本与题集身份。材料／Task 已交付；
**真实流程、独立语义质量和耗时／用量尚未验证**，未恢复任何暂停运行或追加建模轮次。

唯一业务输入为 [scenario.md](modeling-input/scenario.md)，版本
`minimal-installation-chain-source-v1`；[输入清单](modeling-input/input-manifest.json)记录 SHA256。
历史来源为 [checkpoint-minimal](../checkpoint-minimal/modeling-input/scenario.md)，仅复用定义，
不继承其恢复实验目标或历史结果。新业务版本另行保留，不覆写已冻结运行的输入。

选用以下配对文件，不用通用 Profile 替换精简角色包：

- [Task](../../../modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml)
- [Profile](../../../modeling_team/profiles/r4-3-026-minimal-installation-chain.yaml)

只读配置校验（不启动模型、服务或平台写入；模型 Profile 仍按当时授权另选）：

```sh
env -u DEEPSEEK_API_KEY uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r4-3-026-minimal-installation-chain.yaml \
  --task modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml
```

## 实际输入与职责

| 角色 | 强制初读材料／方法 | 职责与边界 |
| --- | --- | --- |
| Coordinator | 唯一业务说明、精简表示合同、024／025直接提交合同、专用角色说明 | 既有场景图／拓扑选择、业务派单、公开反馈与交接；不等 Protocol |
| Modeling | 同上，加专用 minimal-chain-modeling Skill | 当前统一图、显式变更提交、实际治理读取、自查与资源关闭 |
| CQ | 唯一业务说明、既有 CQ 合同、独立私有草题、专用角色说明 | 正常审阅、版本、公开／隐藏冻结；没有生产 Team Transport 通信边 |

精简表示合同只列当前路径所需的既有场景图、拓扑和候选字段，不挂载通用角色手册、全量
Schema、样例行、映射手册、Batch 底层命令手册或旧翻译审批／dry-run协议。v2 Task 的
`protocol_tools` 依现有 loader 保留一个只读工具名；Profile 无 Protocol，该列表不形成新角色
或运行前置门。运行时仍冻结实际 role_sources、角色包、Skill 与 Task/Profile 摘要，
`source-manifest.json` 和 baseline 是实际加载版本证据，不能仅凭本表声称已执行。

[四道私有草题](cq-private/question-seeds.json)仅挂载给 CQ，分别覆盖概念区别、关系方向／
物理位置含义、所有权误读和未给定事实的处理。它们是未审阅种子，不是冻结答案或 PASS
证据；CQ 使用实际批准切片身份，经原私有通道审阅并新建 freeze。公开题仅经 Runner
public projection 进入生产；隐藏题不进入 Coordinator／Modeling，独立 Consumer 不接收
草题／参考答案。题数为建议，不扩大业务范围、不增加跨切片题来凑覆盖。本场景的隐藏
覆盖仅涉及这份极少材料，不代表复杂业务上的泛化能力。

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
