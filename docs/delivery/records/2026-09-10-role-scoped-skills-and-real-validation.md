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

2026-09-10 13:35 +08:00 用户确认“用 deepseek-flash”，三次授权继续有效。按已定位接线缺口，
交外部 Claude Code 复用 Team Model Profile / ProviderSessions 为显式选择的 v3 roster 绑定模型，
不改变 formal coordination 语义或引入新 harness。原模型拒绝及等待已使首次启动超过 20 分钟；
此时仍为 0/3，修复范围仅包含实际模型绑定与必要验证。

13:38–13:41 +08:00 最小可用性复核：`deepseek-flash` `/responses` HTTP 200，完整返回
`response.completed`，返回模型字段包含所选 ID；canonical-mode HTTP 200，`canonical_store=rdf`、
`product_write_mode=rdf_primary`。临时只读检查管理员凭据已撤销。尚无 semantic start。
接线修改前 GitNexus：`prepare` LOW（2 直接调用、1 入口组），`load_team_model_profile` MEDIUM
（5 直接调用、1 入口组），`start_roster` HIGH（4 直接调用、3 入口组），HIGH 已告知用户。
本轮运行将使用 `workspaces/skill-role-20260910/runtime-checkout` 干净 checkout，待修复提交后
切至该提交；backend `.env` 仅使用现有忽略配置的本地链接，不进入冻结业务输入或提交。

## 显式 v3 模型绑定交付

新增 `modeling_team/model-profiles/deepseek-flash-max.yaml`，四个生产角色加 Platform Examiner、
Acceptance Judge 共六个实际角色均为 `deepseek-direct / deepseek-flash / max`。Runner/CLI 接受
v3 multi-slice 显式配置，将其绑定与基线冻结；runtime 将 provider 会话与 formal 协作分离，
模型配置与 thread/start 参数一致，会话结束时按原有机制关闭。旧 formal 配置未改，六角色
完整性要求由 formal prepare 继续执行；未选配置的历史路径不变。

T0：formal-only 模型配置限制属于编排接线偏好，本身不保护业务或写入结果；允许显式绑定并
检查所选 roster 覆盖即可保留模型选择完整性。未引入新治理或 harness。主 Agent 审查补齐了
Platform Examiner 绑定，并要求显式 `role: null` 继续被拒。基线函数影响 CRITICAL、若干
runtime 共享函数 HIGH，均在修改前告知用户。

最终 Team 全量回归：**1417 passed、1 skipped、321 subtests passed，76.31 秒**。
前一轮 1415 passed、1 failed、1 skipped：旧 loader 测试固定要求六角色，按新配置边界调整，
同时新增 formal prepare 缺角色拒绝测试。CLI validate/baseline 及真实配置生成路径检查通过；
后者使用替身进程/RPC与哨兵凭据，不属于真实建模或语义 E2E。Ruff 保留基线原有的三项问题，
无新增告警。外部开发详情保存在本轮 workspace 的 repair-model-binding-result.md。

主 Agent 交付复核另将新增 Runner 测试的本机凭据依赖改成 tmp_path 下的 0600 哨兵文件；
仅测试改动，相关文件 17 tests 通过。该新测试符号尚未索引，impact 返回 UNKNOWN；文本引用
仅有测试定义，无生产调用。未修改 backend/frontend，不需要重启产品服务。
截至代码交付，真实 semantic starts 仍 **0/3**；接线准备明显超时，主要有效时间消耗在共享
runtime 兼容性排查、外部开发与必要回归，真实语义时间为 0。下一动作是冻结提交并直接启动。
