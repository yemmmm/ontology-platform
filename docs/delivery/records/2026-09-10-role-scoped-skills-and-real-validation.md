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

## auth-002 第一轮

14:23 +08:00 在干净 checkout `eb7fd92` 启动 `r30006-20260910-auth002-start1`。
Coordinator 和 Modeling 的 thread/started 都记录 deepseek-flash / deepseek-direct / max；
Protocol 尚未生成 thread 时 app-server 关闭输出，run 随即 CLEANED，未发起业务推理。
第一阻塞 runtime/infrastructure：新 checkout 缺少 backend/.venv，Protocol 的既有 bwrap
挂载 `_protocol_interpreter_mounts` 需要该目录。主 Agent 准备工作漏同步运行依赖；最窄修复是
在 checkout 执行 uv sync --project backend --extra dev，不改平台守卫或业务提示。
已创建的线程不重新利用，按一轮失败计 1/3，剩余 2/3。scope 回执 deleted-empty、资源已删、
密钥已撤销且无在途尝试。运行审计 private_credentials_destroyed=false 保留原值，不宣称
完整 runtime 清理审计 PASS；平台范围删除与凭据撤销有单独回执。原证据保留在该 checkout 的
workspaces/modeling-runs/r30006-20260910-auth002-start1。

## auth-002 第二轮

14:26 +08:00，`r30006-20260910-auth002-start2` 同提交、已补齐 .venv，Protocol 仍报
app-server closed its output。原第一轮的 .venv 缺失是实际准备缺口，但不能据此宣称根因已闭环。
更直接的代码证据：TeamRunner.start 非formal只启用CQ endpoint，未启用staged Protocol endpoint；
CodexRuntimeAdapter.namespace_command 却对其 capability socket 做强制bind。
用失败现场的临时副本与替身socket执行完整bwrap /bin/true，以及仅 initialize/skills-list 的
实际 app-server 均成功，无thread/start、无模型请求、无业务写入；原现场未改。外部Claude负责
在roster启动前补齐既有staged Protocol endpoint的启动及真实socket回归，不增加新harness。
第二轮scope仍deleted-empty、Project/Ontology已删除、protocol/admin keys已撤销、无在途尝试。
累计2/3，剩余1/3；不以机械诊断作真实建模PASS。

## Protocol endpoint 窄修复交付

Claude Code 按用户最新配置 `deepseek-flash --effort max` 完成两处局部修改：
非formal staged run 在 roster 前启动既有 Protocol endpoint；该组合的实际工具面收窄为
已声明的单项 `protocol_staged_submit_modeling_batch`，保留 formal 与非staged 行为。
既有 cleanup 负责关闭 endpoint，不增加恢复或治理框架。GitNexus 对共享 start/carrier
报 CRITICAL，已在编辑前告知用户；范围由真实启动失败和声明/实际工具面冲突约束。

新增两项真实 AF_UNIX socket 测试：roster 启动前端点可连接、tools/list 与声明一致、CQ
同时可用、其他未声明角色端点不启动、cleanup 后socket消失；非staged保持零端点。
分别回退启动补丁/工具面补丁的负向对照均在对应断言失败，恢复后通过。
最终全量：**1419 passed、1 skipped、321 subtests passed，86.43 秒**。
这是机械 socket/接线验证；第三轮真实运行仍需验证原始 Protocol 启动步骤。
完整开发交付位于本轮 workspace 的 `repair-protocol-endpoint-result.md`。

## auth-002 第三轮（进行中）

`r30006-20260910-auth002-start3`，clean checkout `ef0dfea`。四角色 coordinator/modeling/protocol/
competency-question 的 thread/started 及 turn/started 全部真实出现，model=deepseek-flash、
provider=deepseek-direct、reasoningEffort=max；首个Coordinator输出开始读取staged材料。
Protocol原启动失败步骤已越过，当前RUNNING。累计3/3，余额0，继续同一run，不追加fresh start。
真实最终建模/检索质量仍待产物、写入与独立验收证据，不据此宣称整轮L0/L1通过。

### 当前暂停与待办

第三轮现为 `PAUSED`，通过既有 outer pause 中断活动 turn，保留进程与线程；恢复不是另开
start。Modeling 已读材料并列出六项待访谈业务未知，第一问为合同状态、资产覆盖状态、
覆盖日期、SUSPENDED 与空结束日期如何共同决定故障时有效覆盖。原文 delivery-1 已向
用户展示并登记 outer-question；尚无业务回答，不代答、不审批 CQ。

另有 `collaboration/routing` 的 prompt-contract 问题：Coordinator 重复尝试向 CQ 角色
发 Team Transport 消息，收到拒绝后探索其他 recipient；Profile 明确 CQ 无通信边，私有
访谈/审核由 Runner 直达。隔离拒绝本身正确，不应开放通信边。后续由 Claude Code 窄修
权威提示，并通过既有合法反馈恢复当前会话，不能修改已冻结挂载或将隐藏 CQ 送入生产方。

当前证据没有候选写入或语义验收结论，整体 PARTIAL；前两轮失败不是模型质量失败。
本轮时间主要消耗在模型路由与启动接线修复，语义分析占比不足一半；停止扩展平台/harness，
最短后续路径为确认访谈回答、沿既有 CQ 私有通道审核，再继续同一 run。
宿主会话结束不代表后台监控；下次交互须先读取 state、host log 和进程，再输入回答与恢复。
