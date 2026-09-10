# Modeling Team 内部技能

此目录集中保存 Team 成员使用的技能，由角色包或验收 Runtime 按当前 Task/Profile 加载。
不链接到项目的 `.agents/skills/`；宿主 Delivery Agent 使用
[`modeling-dev-loop`](../../skills/modeling-dev-loop/SKILL.md) 推进建模、观察和修复。

| 成员 / 执行模式 | 使用的技能 | 角色合同 |
| --- | --- | --- |
| Modeling | [ontology-modeling](ontology-modeling/SKILL.md) | [modeling](../agent-packages/modeling/package.yaml) |
| Coordinator | [ontology-modeling](ontology-modeling/SKILL.md) | [coordinator](../agent-packages/coordinator/package.yaml) |
| Protocol | [ontology-modeling](ontology-modeling/SKILL.md) | [protocol](../agent-packages/protocol/package.yaml) |
| Competency Question | [ontology-modeling](ontology-modeling/SKILL.md) | [competency-question](../agent-packages/competency-question/package.yaml) |
| Source Specialist | [ontology-modeling](ontology-modeling/SKILL.md) | [source-specialist](../agent-packages/source-specialist/package.yaml) |
| Acceptance（生产 Team 中的角色） | [acceptance](acceptance/SKILL.md) | [acceptance](../agent-packages/acceptance/package.yaml) |
| Source Examiner（单题验收） | [source-examiner](source-examiner/SKILL.md) | [source-examiner](../agent-packages/source-examiner/package.yaml) |
| Platform Examiner（单题验收） | [platform-examiner](platform-examiner/SKILL.md) | [platform-examiner](../agent-packages/platform-examiner/package.yaml) |
| Acceptance Examiner（单题验收） | [lean-acceptance-examiner](lean-acceptance-examiner/SKILL.md) | [acceptance-examiner](../agent-packages/acceptance-examiner/package.yaml) |
| Platform Examiner / 独立 Acceptance Judge（R3.0-011 批量验收） | [v3-acceptance-batch](v3-acceptance-batch/SKILL.md) | [v3-acceptance-batch](../agent-packages/v3-acceptance-batch/package.yaml) |

前五个成员共用建模方法，职责差异由 `agent-packages/` 中各自的角色提示定义；无需为每个成员
复制一份技能。选择哪些成员、谁负责平台调用、采用单题还是批量验收，以本次 Task/Profile 为准。

普通角色通过 `package.yaml` 的 `required_skills` 引用本目录；隔离验收子会话由
`CodexRuntimeAdapter._child_package_assets` 选取对应技能。Runtime 仍以原技能名挂载到成员自己的
技能目录；`lean-acceptance-examiner` 保留原有无 YAML frontmatter 的专用提示格式，由验收
Runtime 加载，其他技能具有标准元数据。历史交付记录中的旧路径保留为当时证据，当前维护以
本目录和加载配置为准。
