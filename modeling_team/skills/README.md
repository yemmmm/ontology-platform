# Modeling Team 内部技能

Team 与 Host 的引用式交接见 [材料工具合同](../references/handoff-materials.md)。

此目录集中保存 Team 成员使用的技能，由角色包或验收 Runtime 按当前 Task/Profile 加载。
不链接到项目的 `.agents/skills/`；宿主 Delivery Agent 使用
独立 [delivery](delivery/SKILL.md) 技能和受限 Host 工具推进建模、观察和修复；
外部技术宿主使用 [`modeling-dev-loop`](../../skills/modeling-dev-loop/SKILL.md) 选择模式、准备并
接入 Delivery 会话，或继续已有手动监督。测试代答者不加载这两个技能，不接收私有历史或工具。

| 成员 / 执行模式 | 使用的技能 | 角色合同 |
| --- | --- | --- |
| 独立 Delivery（Host 私有会话） | [delivery](delivery/SKILL.md) | [delivery](../agent-packages/delivery/package.yaml) |
| Modeling | [ontology-modeling](ontology-modeling/SKILL.md) | [modeling](../agent-packages/modeling/package.yaml) |
| Coordinator | 仅角色提示与声明的参考合同 | [coordinator](../agent-packages/coordinator/package.yaml) |
| Protocol | 仅角色提示与声明的参考合同 | [protocol](../agent-packages/protocol/package.yaml) |
| Competency Question | [competency-question-authoring](competency-question-authoring/SKILL.md) | [competency-question](../agent-packages/competency-question/package.yaml) |
| Source Specialist（互操作 smoke） | 仅角色提示 | [source-specialist](../agent-packages/source-specialist/package.yaml) |
| Acceptance（生产 Team 中的角色） | [acceptance](acceptance/SKILL.md) | [acceptance](../agent-packages/acceptance/package.yaml) |
| Source Examiner（单题验收） | [source-examiner](source-examiner/SKILL.md) | [source-examiner](../agent-packages/source-examiner/package.yaml) |
| Platform Examiner（单题验收） | [platform-examiner](platform-examiner/SKILL.md) | [platform-examiner](../agent-packages/platform-examiner/package.yaml) |
| Acceptance Examiner（旧 R2.3 单题裁判） | [lean-acceptance-examiner](lean-acceptance-examiner/SKILL.md) | [acceptance-examiner](../agent-packages/acceptance-examiner/package.yaml) |
| Platform Examiner / 独立 Acceptance Judge（R3.0-011 批量验收） | [v3-acceptance-batch](v3-acceptance-batch/SKILL.md) | [v3-acceptance-batch](../agent-packages/v3-acceptance-batch/package.yaml) |

角色提示规定职责、权限、输入输出和协作，Skill 提供可复用的专业方法。Modeling 与 CQ 分别加载
建模和出题方法；Coordinator、Protocol、smoke Source Specialist 的 `required_skills: []` 是
合法配置，不为满足数量要求创建空壳技能。当前 v3 建模 roster 是 Coordinator、Modeling、Protocol
和 CQ；独立批量验收另行启动 Platform Examiner 与 Acceptance Judge。选择哪些成员、谁负责
平台调用、采用旧单题还是 v3 批量验收，以本次 Task/Profile 为准。
当前直接建模可选通用 [Codex Profile](../profiles/unified-modeling.yaml) 或
[DSH Profile](../profiles/unified-modeling-dsh.yaml)，仅含 Coordinator、Modeling、CQ，
加载上表相同的通用角色指令和 Skill。R4.3-026 最小链是这套方法的业务测试输入；
其既有 Profile 文件名也已切到相同角色。场景只选择业务范围、材料和独立题集，
不再提供另一套建模或出题方法。旧 minimal-chain-* 角色包、Skill 和 compact 合同
仅保留为历史对照，当前基线不加载；修复共同问题时只维护通用提示面。

普通角色通过 `package.yaml` 的 `required_skills` 引用本目录；隔离验收子会话由
`CodexRuntimeAdapter._child_package_assets` 选取对应技能。Runtime 仍以原技能名挂载到成员自己的
技能目录；`lean-acceptance-examiner` 保留原有无 YAML frontmatter 的专用提示格式，由验收
Runtime 加载，其他技能具有标准元数据。历史交付记录中的旧路径保留为当时证据，当前维护以
本目录和加载配置为准。

Skill 的启动合同由 package loader、冻结 baseline、只读 `/skills` 挂载和首轮精确路径注入共同
保证。Codex 原生 `skills/extraRoots/set`／`skills/list` 只是可选 inventory 发现，不是角色
启动硬门；原生发现不可用时仍按已加载并冻结的 package Skill 继续 `thread/start`。
