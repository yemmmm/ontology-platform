# 角色技能职责收窄与真实建模验证

用户授权：按已讨论方案收窄共享技能、补充 CQ 专业方法，再以全部 Team 角色使用
`deepseek-v4.1-flash` 进行三次 fresh semantic modeling starts。授权时间 2026-09-10 13:10 +08:00；
登记于 R3.0-006 `auth-r3-0-006-002`。业务场景沿用当前工业售后服务 v3 全链 Task。

## 变更范围

- `ontology-modeling` 仅指导 Modeling：业务理解、澄清、统一图/共性判断、受控值分析、语义候选
  和基于回执的修订；移除宿主运行/额度管理及单 Agent 直接请求转发模式。
- 参考文件保留现有路径，改为语义交接/证据说明，明确 Build Session、lease、Batch envelope
  和平台调用属于 Protocol，独立裁决属于验收者。
- 新增 `competency-question-authoring`：问题覆盖、答案必要业务要点、证据与未知、歧义、公开/
  隐藏边界；审核流程和工具字段继续由 CQ 角色提示与已挂载合同定义。
- Coordinator、Protocol、smoke Source Specialist 使用空 Skill 列表及各自角色提示；保留
  Modeling 与 CQ 的专业方法，现有验收技能不改。导航明确 Acceptance Examiner 是旧 R2.3
  单题裁判，当前 v3 使用独立 Acceptance Judge。

## 实际平台阻塞与 T0

`_load_package` 把空 Skill 列表判为非法，阻止角色仅使用现有完整 instructions。
非空列表限制不直接保护语义、来源、授权或写入完整性；删除该限制的后果是角色可以没有附加
Skill，由既有角色提示、工具权限及实际产物校验覆盖。故只允许 `[]`，继续拒绝缺字段、非列表、
无效路径、重复项和废弃资产。外部 Claude Code 负责这一行及合同测试，主智能体负责 Skill/包。
修改前 GitNexus 上游分析为 HIGH：1 直接调用者、11 影响符号、3 组入口，已在修改前告知用户。
技能发现测试符号上游为 LOW、无调用者。

## 验证记录

- 两个专业 Skill 官方格式校验及原 `ontology-modeling` 自带验证器通过。
- Claude 针对合同测试：8 passed、3 subtests passed；修改前空技能包真实加载测试失败，修改后通过。
- 主智能体角色加载/发现/CQ 合同检查：75 passed、51 subtests passed。
- Team 全量回归：`env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team/tests -q`
  → **1407 passed、1 skipped、321 subtests passed**，72.95 秒。
- 当前 `r3-0-011-competency-question` Profile + `r3-0-006-real-full` Task 的 CLI validate 通过；
  29 个相关相对链接与 `git diff --check` 通过。
- 技能/配置修改为机械回归 PASS；真实验证仍 BLOCKED / 未启动，不据此宣称语义质量通过。

## 模型选择与启动额度

官方 `GET https://api.deepseek.com/models` 返回 HTTP 200，模型列表是 `deepseek-flash`、
`deepseek-v4-pro`。以指定的 `deepseek-v4.1-flash` 请求官方 `/responses` 返回 HTTP 400：
`The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed deepseek-v4.1-flash.`
已向用户提交替代模型/服务地址问题，未擅自替换。该最小可用性检查不属于 semantic start。

当前消耗 **0/3**；未创建新的平台模型资源。业务访谈和 CQ 审核仍遵守用户确认边界，建模额度
不等于宿主代答或代批授权。启动后记录 run、实际模型绑定、有效时间、第一阻塞与资源处置。

额外已定位的现有接线限制：v3 multi-slice 入口当前拒绝显式 `--model-profile`（只接受 formal
run contract）；已有 formal 模型绑定列表也不包含 CQ。模型名/服务选择确认后，应复用已有模型
配置和 provider session 路径补齐所选 v3 角色的实际绑定，不能靠 CLI 参数或配置文本宣称模型
已经生效，更不能让 v3 静默回退到默认 OpenAI 模型。本次尚未修改该选择相关代码。

截至 13:20 +08:00：授权后约 10 分钟用于技能调整、已证实的加载限制修复、模型可用性核对与
机械验证（Claude 工作并行）；真实语义建模有效时间 0，原因是精确模型 ID 被官方拒绝且替代
选择待用户回复。准备工作已收口，不追加 harness/控制机制或消耗 start 来重复证明该错误。
