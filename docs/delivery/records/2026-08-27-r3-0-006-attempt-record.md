# R3.0-006 真实建模 attempt 记录（Agent 自维护）

按用户 2026-08-27 方向变更：建模次数不经代码硬门（multi-slice run 无 StartLedger 预留），
由 Delivery Agent 在本文件登记每次授权与消耗。

## 授权记录

| 授权 ID | 时间（本地） | 内容 | 来源 |
| --- | --- | --- | --- |
| auth-r3-0-006-001 | 2026-08-27 20:16 +08:00 | 3 次 fresh start | 用户会话显式授权（选项确认） |
| auth-r3-0-006-002 | 2026-09-10 13:10 +08:00 | 技能职责调整后进行 3 次 fresh start 验证；全部 Team 模型初始指定 `deepseek-v4.1-flash`，13:35 +08:00 用户改为 `deepseek-flash` | 用户本会话明确授权；精确模型 ID 的服务端可用性与后续决定见本轮记录 |

| auth-r3-0-006-003 | 2026-09-10 15:11:52 +08:00 | 新增3次fresh start；按高峰规则Team=gpt-5.6-luna/xhigh，ClaudeCode=glm-5.3-flash/max | 用户本会话明确授权；clock实查07:11:52 UTC，Asia/Shanghai周四15:11:52，高峰；cc-switch已选GLM |

## 消耗记录

| # | run-id | 授权 | 开始（本地） | 终态 | 备注 |
| --- | --- | --- | --- | --- | --- |
| 1 | r30006-20260827-start1 | auth-001 | 2026-08-27 20:18 +08:00 | 失败（collaboration/routing 层） | 三角色启动成功、modeling 提出首个真实访谈问题；Host 经 FIFO 登记问题时 run 因 "outer question project binding is missing" 终止（非 formal multi-slice create run 的访谈通道无项目绑定）。窄修复 commit `77e2b59`（`_project_binding` 从活跃 PlatformScope 解析，含守恒测试）。清理干净：scope `deleted-empty`、Project/Ontology 删除、密钥撤销，无残留。无退款，消耗 1/3。 |
| 2 | r30006-20260827-start2 | auth-001 | 2026-08-27 21:04 +08:00 | 失败（runtime/infrastructure 层：run 输入 staging 缺口），2026-08-27 21:28 +08:00 终态 CLEANED | 访谈通道完全打通：Host 以模拟业务方身份经 FIFO 两步登记并应答 Q1～Q8（outer-question/outer-user 证据各 8 条），coordinator 冻结五切片集合；modeling 产出候选（delivery-23/26/27）后三角色全部 blocked——`candidate_kind` 写为 `platform-neutral-semantic-slice`，protocol 翻译拒 -32014（要求 `platform-neutral-candidate-v2`），根因是 task YAML role_sources 未挂载冻结 instructions 强制要求的 4 份权威契约（R2.3-005 formal 任务有挂载先例）。Agent 行为正确：不猜协议、零平台写。窄修复：task YAML 补挂 4 条 role_sources + 同步白名单测试/设计 §5.2/T2-1（commit 见下）。清理干净：scope deleted-empty、Project/Ontology 删除、密钥撤销、零残留。无退款，消耗 2/3。窄修复 commit：`913e733`。 |
| 3 | r30006-20260827-start3 | auth-001 | 2026-08-27 21:35 +08:00 | 失败（runtime/infrastructure 层：coordinator 场景地图写入通路缺失），2026-08-27 22:55 +08:00 终态 CLEANED | 契约挂载修复生效：protocol/modeling/coordinator 均读到权威契约，modeling 交付三份正确 `platform-neutral-candidate-v2` 候选（core-coverage delivery-19、service-execution delivery-20、parts-logistics delivery-21），零协议错误。访谈 Q1～Q7 全部应答留证（outer-question/outer-user 各 7 条），coordinator 冻结三切片集合与依赖序。新卡点：coordinator 维护 run 根 `scenario-map/` artifact 的写入通路从未实现——冻结 package sandbox read-only、run 根未挂载进任何 Agent 命名空间，`mkdir`/`apply_patch` 均被拒，拓扑门保持 `topology_missing_artifact` 关闭，protocol 排队等门至 idle→fallback 超时。Agent 行为正确：不猜、不重试平台调用、零平台写。窄修复 commit `c540cd6`：multi-slice coordinator 沙箱升 workspace-write + run 根 `scenario-map/` 可写 bind 到 `/agent/work/scenario-map`（runner 预建目录、缺失 fail-closed、其他角色/普通 run 字节不变，守恒接线测试 16 passed；全量 7 failed/1117 passed 与 ruff 基线不变）。清理干净：scope deleted-empty、Project/Ontology 删除、密钥撤销、零残留。无退款，消耗 3/3（授权用尽）。 |

| 4 | r30006-20260910-auth002-start1 | auth-002 | 2026-09-10 14:23 +08:00 | CLEANED；runtime/infrastructure | commit `eb7fd92`；Coordinator/Modeling thread/started 真实绑定 deepseek-flash，但 Protocol app-server 输出关闭，尚无业务 turn。干净 checkout 缺 backend/.venv，Protocol bwrap 绑定依赖目录不存在；以 uv sync --project backend --extra dev 补齐运行依赖，不改代码。scope deleted-empty、Project/Ontology 删除、project/admin keys 撤销，no_in_flight_attempts=true。保留原现场，无退款，计 1/3；剩余 2/3。 |

| 5 | r30006-20260910-auth002-start2 | auth-002 | 2026-09-10 14:26 +08:00 | CLEANED；runtime/infrastructure（platform-contract 接线遗漏） | commit `eb7fd92`；补齐 .venv 后 Protocol 仍 app-server closed its output；定位到非formal staged run 未启动 Protocol capability endpoint，但 namespace_command 必须挂载其 socket。完整副本 namespace/config/initialize 在替身 socket 下通过；无业务 turn，无模型质量结论。原证据与第一轮分开保留，scope deleted-empty、资源已删除、keys已撤销、无在途尝试。累计 2/3，剩余 1/3。 |

| 6 | r30006-20260910-auth002-start3 | auth-002 | 2026-09-10 14:50 +08:00 | CLEANED；platform-contract | commit `ef0dfea`；四角色 thread/started 和 turn/started 全部真实出现，deepseek-flash/deepseek-direct/max。Protocol 原启动失败已越过；开始读材料与访谈/CQ准备。累计 3/3，余额 0；继续当前 run，不再 fresh start。 |

## 退款/异常

（无）

## 当前授权准备（auth-002）

已消耗 3/3，剩余 0/3；第三轮已完成六项授权访谈，因CQ_OPERATION缺失导入停止并清理。2026-09-10 最小模型检查发现官方 `/responses` 对 `deepseek-v4.1-flash` 返回 HTTP 400，
明确支持名为 `deepseek-flash`、`deepseek-v4-pro`；用户于 13:35 +08:00 确认使用 `deepseek-flash`。
模型可用性请求不是语义建模 start。本轮进度见
[角色技能与真实验证记录](2026-09-10-role-scoped-skills-and-real-validation.md)。

## 当前授权（auth-003）

3/3已消耗，0/3可用；三轮均结束并清理空scope。第一轮错误通知被旧parser误判；
后两轮正确记录流断开并在300秒无输出后终止。第三轮取得实际Runner/child缺少代理的直接
证据，已验证从宿主shell内cd到clean checkout可保留代理，运行参考已补齐。等待新的真实
start授权复测，不以环境presence检查声称语义PASS。继续复用已获业务代答和资料补充授权；
新授权到来时按Skill重新取时确定模型，旧冻结run不换模型。

2026-09-11 平台侧新增 `glm-direct` 路由与 `glm-flash-max` Team Model Profile，Team 高峰档位
由 `gpt-5.6-luna`/xhigh 改为 `glm-5.3-flash`/max；非高峰 `deepseek-flash`/max 不变。这是
调度表与 provider 能力变更，不是新的授权：auth-003 仍 0/3 可用，本次未启动任何真实 run。
下次新授权到来时按 Skill 取时判定高峰/非高峰，再选用对应 profile；已冻结 run 不换模型。
实现、实测证据与 cc-switch 侧的 open-code 工具缺口见
[角色技能与真实验证记录](2026-09-10-role-scoped-skills-and-real-validation.md)。

### auth-002 第三轮收口（15:20 +08:00）

六项访谈经授权代答完成，原始outer-question/outer-user与BS-20260910-01至06保留。CQ草稿
提交第一阻塞为acceptance._dispatch_capability缺少CQ_OPERATION导入，capability-calls记录
NameError，最早06:53:36 UTC；非模型质量失败，尚无候选/业务写入。停止后scope deleted-empty、
Project/Ontology删除、keys撤销、no_in_flight_attempts=true。Runtime的private_credentials_destroyed=false
照原审计保留，不宣称完整runtime清理PASS。stop后宿主stderr出现app-server closed its output、
exit2，state仍为CLEANED；不以这一终止次生现象覆盖先前CQ NameError。auth-003仍0/3。

### auth-003 第一轮启动

`r30006-20260910-auth003-start1` 于2026-09-10 15:30:08 +08:00启动，冻结commit e038955，
profile openai-luna-xhigh（gpt-5.6-luna/xhigh），与本授权取时相差18分16秒。
auth-003累计1/3，余额2/3；状态与实际thread模型证据继续观察，尚未判定L0/L1。

### auth-003 第一轮终态

四角色thread/turn真实启动且各runtime config为gpt-5.6-luna/openai/xhigh；首次模型响应
阶段coordinator/modeling被provider-error-malformed终止（07:31:19 UTC）。原始通知在解析
前未落app-server-events，当前无法据此判定模型/网络原因；Claude Code负责核对当前协议
与错误形状。scope deleted-empty、Project/Ontology已删除、keys撤销、无在途Attempt；
无业务分析/CQ提交/候选写入。auth-003已消耗1/3、剩2/3，修复/定位前不再fresh start。

### auth-003 第二轮启动

`r30006-20260910-auth003-start2`，2026-09-10 15:48:21 +08:00，clean checkout e62e056，
openai-luna-xhigh；累计2/3，剩1/3。原始错误解析和真实CQ发布是否恢复仍需本轮观察，
不把探针或单元测试当作真实建模PASS。

### auth-003 第二轮终态

07:54:20 UTC，连续300秒无模型输出后llm-inactivity-timeout；第一原因保留为此前四角色
responseStreamDisconnected/will_retry=true反复重试，旧malformed解析误杀已实际解除。
未产生业务/tool/CQ发布；当前为runtime/infrastructure，不能评模型质量。有界只读诊断已结束，
冻结错误记录为20条；尚无确证传输修复，剩1/3保留，不重开相同失败路径。

第二轮cleanup回执位于host runtime-failure条目（最终state为TERMINAL_REPORT_COMPLETE，
不再携带cleanup字段）：scope deleted-empty、Project/Ontology删除、admin/protocol keys
撤销、no_in_flight_attempts=true；退出码0只表示终态报告已收口，不表示真实建模通过。


### auth-003 第三轮继续（16:55 +08:00）

用户指出有余额不应停止。宿主承认此前将确证传输修复当成fresh start前置、过度保守保留
额度；这不是平台硬门，也不是用户授权限制。停止扩展排查应当缩短路径进入真实建模。
16:55:02 +08:00启动r30006-20260910-auth003-start3，复用clean e62e056、相同Task/Profile、
openai-luna-xhigh和原300秒无输出边界；四个thread/turn已实际启动。auth-003现3/3、余额0。
已将获准BS-01至06经CQ私有访谈通道送达；业务问题继续按用户既有授权处理，CQ审批不代批。
本轮并未证明底层传输已修复，实际结果持续观察，不能从启动事件推导运行或建模PASS。


### auth003-start3终态与启动环境证据（17:00 +08:00）

本轮自然到达llm-inactivity-timeout并退出0，保留20条responseStreamDisconnected/
will_retry=true。无业务模型输出、CQ发布或候选写入；scope deleted-empty、资源删除、
admin/protocol keys撤销、no_in_flight_attempts=true。runtime秘密残留审计false原样保留，
不声明完整runtime清理PASS。auth-003已耗尽3/3；没有追加第四次start。

这次在进程存活时取得此前缺失的直接证据：Runner python PID2726570、uv2726551和四个
实际codex子进程的6个HTTP(S)/NO_PROXY变量均缺失，父bwrap argv绑定auth003-start3。
同一工具的最小对照：主仓库workdir三小写代理键present；直接指定runtime-checkout
workdir则全部absent。从主仓库shell内cd到该clean checkout，再运行uv python和现有
_minimal_codex_process_env，三个代理键均保留。只保存presence，没有输出密钥或代理值。
安全证据在宿主目录auth003-start3-proxy-presence.json、auth003-launch-env-correction.json。

判定：已证实宿主启动环境交接缺口，不能再以主仓库shell有代理推断Runner有代理；无须
修改现有adapter转发逻辑。下一轮从已验证宿主shell内cd启动并检查实际进程presence即可。
这还不是代理缺失导致所有流错误的因果复测PASS。Claude Code把教训补入现有运行参考，
不加每次启动硬门、配置开关或测试框架。修正后真实语义结果需要新的授权额度才能验证。


## 当前授权（auth-004，2026-09-10 18:07:39 +08:00）

用户明确再授权3次；clock实查10:07:39 UTC，Asia/Shanghai周四18:07:39，非高峰。
本批Team deepseek-flash/max，外部Claude Code deepseek-flash/max；已用cc-switch从GLM
切至deepseek。当前1/3，剩余2/3；使用既有Task/Profile、clean checkout341b1d0，启动工具workdir
保持主仓库、shell内cd到runtime-checkout以保留代理。复用既有业务代答及BS-01至06授权。
本批切换模型是授权时调度规则要求，不能据本批成功单独证明上一批Luna传输原因。


### auth004-start1启动与首次进展

18:08:27 +08:00，r30006-20260910-auth004-start1启动，距授权48秒；完整既有入口、
deepseek-flash-max模型profile，工具workdir主仓库+shell内cd runtime-checkout。
实际uv/runner/bwrap进程链3个代理键均present，证据auth004-start1-proxy-presence.json。
已通过CQ私有访谈复用六项业务补充。18:09观察到大量真实reasoning/agentMessage/tool输出，
Coordinator开始读取阶段合同与材料、分派工作；没有前轮“无首个业务输出”的表现。
本批模型依授权时调度切至DeepSeek，因此不把本轮输出当作Luna代理因果复测PASS。
当前1/3、剩2/3，运行持续观察。


### auth004-start1第一阻塞与同轮恢复尝试

CQ真实tools/call初始cq_id=r3-0-011，两次被AcceptanceContractError拒绝，提示未说明
cq_id是角色身份。Host在同一CQ私有通道给出技术反馈（明确不是业务定义或审批），CQ随后
改成competency-question，越过身份检查。Claude Code补齐权威instructions中的精确字面值，
相关包加载/链接和现有单项回归通过；没有放开身份隔离。

10:15:57UTC，正确身份的CQ提交触发TypeError 'NoneType' object is not iterable。
已定位真实接线：carrier把args.get("draft")传callback，真实Runner handler却再次读取
arguments.get("draft")。先前synthetic handler回归没有覆盖真正Runner，漏检此不一致。
本次只修CQ分派传完整args，补真实socket->Runner->不可变draft/review持久化测试。
GitNexus dispatcher无法解析UNKNOWN，人工确认endpoint唯一分派引用及CQcallback分支；
Runner handler索引LOW但不捕捉动态回调，不据此虚报完整低风险。

Host已stop保留证据，state CLEANED，scope deleted-empty、资源删除、admin/protocol keys
撤销、no_in_flight_attempts=true；runtime private credentials审计false保留。stop次生stderr
app-server closed its output/exit2不覆盖先前CQ payload合同错误。无CQ成功发布/候选/业务写入。
本批仍1/3已用、2/3剩余，窄修复通过后继续下一次，不能安全热换现有Runner会话。


### CQ信封修复验证

Claude Code将CQ分支回调参数改为完整args，保持身份/operation/token和真实Runner原合同。
旧代码通过真实AF_UNIX socket->carrier->TeamRunner发布handler复现TypeError；修复后
不可变draft、review snapshot及review等待窗口均真实生成。合成fixture不含真实业务/隐藏题。
CQ合同子集116 passed；Team全量1429 passed、1 skipped、321 subtests passed（最终81.67s）。
测试fixture引用的一处F811 lint问题已修正，最终文件2 tests通过且lint通过，旧分派行再次
使真实接线测试失败。未改backend/frontend，不重启产品服务。下一次真实CQ发布仍待验证。


### auth004-start2启动

18:25:57 +08:00，r30006-20260910-auth004-start2在clean checkout9f9097a启动，
修复后的CQ信封分派与身份提示已冻结；沿用deepseek-flash-max和宿主shell内cd启动。
原获准六项业务补充已通过CQ私有访谈送达。本批累计2/3、剩1/3，优先验证真实草稿发布。


### auth004-start2真实CQ发布与工具名阻塞

10:29:51UTC，CQ在同一会话修正unknown类型与evidence_refs格式后，真实capability审计ok；
成功保存draft-0001与cq-review-0001，8个panorama/public问题（CQ-P-01至08），含业务答案
要点、来源与未知项。旧cq_id/NoneType接线错误均未再出现。已将具体审核请求交用户，尚未
获得批准，未发布公开投影/冻结题池。Host仅按review snapshot读取关联草稿，不把问题输入
生产角色或当业务写入。模型语义质量/最终验收仍未完成。

Coordinator旧权威提示要求fully-qualified MCP工具名，而本run实际广告native动态工具。
实际rollout function_call仍为mcp__team_transport__send_team_message并unsupported，前轮
相同入口的send_team_message裸名曾成功。Host两次经现有nonformal question/user绑定发送
技术反馈（host-runtime-tool-names-001/002，明确不是Modeling业务问题、CQ批准或用户定义），
第二次包含pause/resume与同thread新turn；实际调用仍重复旧名，未出现成功分派。
此为prompt-contract/collaboration-routing，不是语义质量失败。

### 用户中断后的资源收口与同源提示闭合

用户要求继续后，实际进程已不存在，工具会话ID失效；保存state仍RUNNING，是中断前快照。
不重写该历史状态，不伪称恢复同一语义会话。Host以原run/project名字与metadata复核唯一
owned Project及Ontology，使用现有PlatformScope.cleanup得到deleted-empty、无在途Attempt、
Project/Ontology删除、Protocol key撤销；临时清理admin也撤销。原run admin通过唯一同名
创建记录（比Project创建早30ms、启动时点一致）定位并撤销。原CQ/原始事件保留，回执在
宿主auth004-start2-external-cleanup.json；metadata为auth004-start2-interruption-resource-metadata.json。
没有新增semantic start，当前仍2/3、剩1/3。

仅改Coordinator提示尚不足：Runner._task_text和其余生产角色同一命名段落还强制旧前缀。
Claude Code继续最窄同源闭合，只改命名字符串/段落和过时测试，不增alias/运行机制。
_task_text预编辑GitNexus CRITICAL（2直接caller、119关联符号/98宽泛间接流程），已告知；
对应旧命名测试LOW0caller。完整修复验证后使用最后一次，不重复已知矛盾。


### 工具名提示合同修复验证

四个既有生产/验收角色的同一命名段落及Runner._task_text命名字符串统一按当前tool catalog
解析（native裸名、MCP模式广告限定名），无运行/权限/业务逻辑改动。过时固定限定名测试
改为验证两模式及现有角色边界，并覆盖实际生成的任务文本。相关21 tests通过，Team全量
1429 passed、1 skipped、321 subtests passed（81.64s）。未修改backend/frontend，无服务重启。
下一轮验证真实Coordinator分派；原8题草稿及待审核请求保留，不擅自审批。


### auth004-start3启动（20:49 +08:00）

20:49:04 +08:00，r30006-20260910-auth004-start3在clean checkout042a4a9启动，
统一工具命名提示已冻结；仍为本授权的deepseek-flash/max，工具workdir主仓库+shell内cd。
原六项业务补充已送CQ私有访谈；不将上一轮未审核草稿当成已获准公共投影。
本批已用3/3、剩0/3，继续观察本轮并处理可恢复问题；不能再自行fresh start。

### auth004-start3：协作恢复、CQ审核等待

12:53UTC，Coordinator真实Team Transport发送成功，delivery-1到Modeling、delivery-2到Protocol。
实际rollout成功function_call.name为send_team_message；其文字叙述称::限定形式，不以叙述
替代实际调用证据。此前仍有旧前缀unsupported，但本轮能够自行恢复，不再判整个run死亡。
CQ连续收到unknown/evidence_refs/content_version的可恢复字段反馈后，于12:53:21UTC发布成功。
本轮cq-review-0001绑定draft-0001、content_version=2，digest为
sha256:099f784f9cb0e895ade8a81224dac51cb45410d75a33792d0277336bc361577c。
PAN-01至PAN-07拟公开，PAN-08拟隐藏，具体问题/答案仅保留CQ审核原件，不写入本公开记录或
生产角色输入。旧run的待审八题不是本轮审批。Host已按当前review引用读取草案，不能担任
该题池的盲测验收者。当前仍未获得用户CQ批准，未发布公共投影、未冻结、未有语义模型写入。
Host通过既有outer-input action=pause，已确认state=PAUSED，保留同run等待用户具体审核。
本授权3/3已用，0次剩余；暂停不是语义质量失败，也不是验收PASS。后续优先恢复同run。

### 用户委托Host审核后继续同run

用户明确答复“可以由你自行决定”，授权Host完成CQ审核与后续推进。Host按既有业务材料、
六份授权补充和各题证据/未知项审核8题。发现原draft phase=panorama-draft不会触发审核后
公开投影，经CQ私有访谈反馈请求发布panorama-review后继版，保持问题内容不变；没有改
保留证据或生产运行代码。该phase使用歧义记录为prompt-contract待持久修复项，后续fresh
start前需闭合，当前允许同run自修复。
CQ发布cq-review-0002、content_version=3，draft-0002与原8题逐项完全相同，phase已修正；
digest sha256:b30e49a8c6b3a677081d6a269632d33a899ed5e2ae4d92fb455b083b624897fe。
Host通过8次现有cq_review接口逐题approve，8份decision保存，公共投影0008仅含7道公开题。
Coordinator真实读取最高序号投影并通知Modeling推进切片；未向生产角色透露隐藏内容。
Modeling先后提出覆盖/SLA计时问题delivery-3/6，Host依BS-01/03回答，经Coordinator原文转交，
最终在delivery-9/10提交6个逻辑切片与共享术语/跨切片依赖。当前仍同run，已resume到RUNNING，
未新增start。下一步为场景图及切片CQ审核，尚未模型验收。

切片CQ完成20题草案后，Host按材料/原业务定义复核，退回3项答案准确性修正；反馈只经CQ
私有通道，不进入共享记录/生产角色。CQ发布正式slice-review后继版cq-review-0004，version5，
digest sha256:c059c33f459fcc18f6a0ab3446e2758fa8832c139d043a90436a613dc42cbe60。
变更3题递增content_version，其他17题完全相同；Host复核后逐题批准20题，累计28份决定。
既有cq_freeze成功：cq-batch-0001，snapshot_digest
sha256:79b4534521b932d87d1e6faee6fc6f23177544fabc75d00b9084a7860b1e856e，20公开/8隐藏；
最高公开投影0029，仅公开20题。Host通过既有外部消息告知Coordinator冻结成功及公开投影路径，
推进阶段3；不把隐藏题内容、答案或私有冻结文件交生产角色。模型质量尚待实际产物与独立验收。

Claude Code在同一授权模型deepseek-flash/max完成CQ阶段提示持久修复，仅改该角色Lifecycle
说明：准备阶段与正式提交审核phase分清，全景/切片分别用panorama-review/slice-review，
返修发布不可变后继版本。没有改运行逻辑/守卫或当前run冻结提示。diff --check、合同字段/
挂载引用与角色包加载核对通过（详见repair-cq-review-phase-result.md）；纯说明不跑后端/
前端套件、不重启。该prompt-contract项已关闭，当前真实模型工作继续。

阶段3真实产物：6个候选文件、142条neutral items、候选汇总与41项analyzed值结论已落盘；
Coordinator收到18项commonality决策建议，Modeling向Protocol交付6份候选与digest（delivery-17）。
拓扑选择由Coordinator决定shared_core_plus_domain并记录ontology_plan，未由Host指定。
重复topology_schema_mismatch后Host用既有纯校验器只读定位：approvals/slot/map当前结构均通过，
topology options用了dimensions键，而实际要求{option_id,assessment}。Host通过现有question/user
技术消息host-topology-schema-001告知，保留原业务判断并由Coordinator修正自己的文件。
这是挂载合同没有option项精确字段的prompt-contract缺漏。Claude Code仅向权威r3-0-002合同
增加option_fields及assessment形状规则2行，未改运行代码/守卫，JSON、diff --check与既有
校验器形状对照通过。当前冻结sources不重写。未把结构检查称为语义验收。

随后relation_scope_ambiguous由Host只读既有validator定位为scope数组/对象类型差异：6项共性
关系决策scope必须非空Mapping，其他项null。Host通过host-scope-type-001仅说明类型，未替代
业务范围决策；Coordinator自行改为非空对象、保留其范围，随后审批闭合推进。
Claude Code仅补009合同既有scope规则一句类型说明，JSON/diff/实现类型核对通过，无运行代码
修改。41项结论已confirmed，Coordinator发布materialize unlock并交Protocol计划生成；截至本
记录尚无实际batch提交回执。完整模型与独立语义验收未完成。

Protocol工具入口停顿进一步定位：Host之前仅摘取function_call.name，遗漏namespace，故“裸名
成功”的结论不完整。实际Coordinator/Modeling成功调用为name=send_team_message同时带
namespace=mcp__team_transport；Protocol两次失败均未带namespace（旧拼接名/裸名均失败）。
四个MCP服务器ready。Host经Coordinator转交host-protocol-namespace-001精确身份技术反馈，
Protocol自行修正后delivery-25成功确认，随后get_project_build_context及get_ontology_workspace_context
真实调用成功。该协作阻塞已在同run恢复，原始失败保留；尚无batch提交。
Claude Code修正四角色命名段落及CQ终态入口说明，保留目录兼容/权限边界，无运行逻辑变更。
现有测试2项旧文字断言失败（19项通过）后，Root对两个函数impact均LOW0caller/0flows，CC仅
更新对应测试的命名断言，21/21复验与ruff通过；未将处理器侧字符串归一化测试误称App Server
namespace验证。当前真实Protocol成功调用提供运行证据。冻结提示仍不改写。
另发现Protocol被要求读取仅挂载Coordinator的scenario-map路径。Host通过既有技术消息
host-protocol-topology-handoff-001请Coordinator转交其已决定的ontology_plan，业务选择不变，
无新增mount。该交接提示缺漏记录待闭合；当前优先继续真实转换，不扩展平台机制。

### auth004-start3 首批提交的真实平台阻塞与收口

Coordinator已通过delivery-26转交完整ontology_plan；Protocol停止寻找不可见scenario-map。
Host随后要求优先首个依赖闭合计划，Coordinator选择service-network根批次（delivery-27）。
Protocol发布plan-service-network-r1.json，Coordinator核对投影并记录translation approval，
delivery-30允许提交。Protocol也向Modeling确认统一图候选无需旧v2 candidate receipt。
13:59:39UTC，protocol_staged_submit_modeling_batch首次请求在CapabilityServer入口被
schema_or_operation_rejected拒绝；原始参数带protocol_id=protocol、batch、value_traces、
l3_nodes及009强制plan_ref，身份正确。权威009合同要求plan_ref，Runner内部也读取校验它，
但capability_mcp.CAPABILITY_TOOL_SCHEMAS properties遗漏plan_ref且additionalProperties=false，
所以正确请求无法抵达业务校验。未创建submission intent/receipt、无Modeling Batch写入。
这是platform-contract实现缺口，不是modeling-quality结论；Host拒绝去掉plan_ref绕过审批。
Host暂停后核对既有resume为no-op、不重载进程模块；未增加热补/恢复机制，未自行追加start。

14:03UTC请求既有stop清理。Runner已停止、scope API keys及原admin已撤销，Session取消/Lease
释放，但scope清理错误地要求失败会话覆盖全部三个计划Ontology，返回Build Session Ontology
coverage drifted。Host只读核对准确run/project名字、三个owned Ontology、所有batch列表为空，
唯一Session已cancelled且无batch、Lease released；随后通过既有HTTP DELETE删除该空Project。
重读证实Project、三个Ontology、Session均404，project keys revoked、临时admin撤销，无在途
Attempt。原Runner CLEANED/cleanup_blocker保留，不覆盖为全PASS；补充回执为
workspaces/skill-role-20260910/auth004-start3-external-cleanup.json，预核对为同前缀cleanup-precheck.json。
Runtime private_credentials_destroyed审计仍为false，不宣称凭据文件清理PASS。CQ cleanup按既有
策略删除7个私有草稿/访谈文件，但frozen题池、公开投影、28份审核决定、原始运行事件、候选及
首批计划保留；不可再引用已删private草案路径作为当前可读证据。
本授权3/3已用、剩0；本轮语义状态PARTIAL，执行状态BLOCKED(platform-contract)。

Claude Code完成plan_ref入口修复：只在该操作properties加入可选string字段（008B仍可省略，
009必需性/路径/投影审批仍由既有Runner合同检查），additionalProperties=false保持。
新增4个真实AF_UNIX capability入口测试并复用已有Runner fixtures/受控下游forwarder；原实现
1 failed/3 passed，修复后4 passed，相关链路39 passed。全Team1433 passed、1 skipped、
321 subtests passed（62.50s），ruff/diff check通过；这些是功能回归，不替代语义真实验收。
仅modeling_team修改，无backend/frontend变更，不需服务重启。修复只在新Runner进程加载，
现有受支持同run热重载/持久恢复入口不存在；未添加新恢复机制或偷偷追加启动。
最终保留6切片142候选条目、41已确认值、28题冻结池（20公开/8隐藏）、已批准首批转换计划；
0次模型apply、0次真实语义检索验收。下一轮真实启动须新授权，并继续跟踪已记录的交接提示与
失败清理覆盖条件缺口，不将本次平台失败归因于模型质量。

## 2026-09-10 auth-r3-0-006-005 — 缓存优化后单次真实建模

用户于15:19:58UTC明确授权“一次真实建模执行”，本授权额度1，不按默认3扩张。
15:20:36UTC取时，北京时间周四23:20非高峰：Team deepseek-flash/max，
model-profile deepseek-flash-max；Claude Code provider现场为deepseek，修复同模型/max。
沿用r3-0-006-real-full Task、r3-0-011-competency-question Profile、industrial-service-v3
四份原始获准材料及BS-20260910-01..06授权补充；保留此前业务代答和CQ审核代理授权，
不向生产角色注入旧隐藏题、旧模型候选或旧拓扑。目标仍为真实建模/检索证据；缓存指标只观察
现有usage，不增加预热或探针。用户缓存优化提交b03a936已有全Team1459 passed/1 skipped
记录，本轮复用；plan_ref入口修复71542b5也纳入新进程。主工作区用户未提交修改保留。
启动前由Claude Code仅补齐Coordinator指令中的既有topology计划消息交接，消除auth004-start3
Protocol寻找不可见scenario-map路径的已证实prompt-contract缺漏，不扩mount或选择业务拓扑。
启动证据及宿主记录位于workspaces/skill-role-20260910/auth005-*。

本轮run r30006-20260910-auth005-start1于15:23:02.541278UTC实际semantic start，
距授权约3分钟；隔离checkout 05f9bb5（含b03a936与71542b5），baseline hash
1ec64a172b0dccdc77757182cc1925215742a0d8d04f9621b7af43ca2ee55651。
四角色thread/turn均started，deepseek-flash/max；本授权已消耗1/1、剩0。
入口session由宿主持续观察。BS六份补充已经CQ私有cq_interview通道接收，未含旧CQ题目。
交接提示仅6行，Claude Code合同/挂载核对、diff check通过；GitNexus staged LOW、0流程，
无backend/frontend更改或重启。当前处于初始源读取/全景CQ阶段，尚不构成L0/L1 PASS。

15:27:25UTC首版8题全景CQ发布成功；unknown类型、evidence_refs形状两次输入错误由CQ根据
类型化反馈同run自行修正。Host按已有代理审核授权核对材料，批准7题、修改CQ-PAN-08中
旧BS-06的forbidden技术短语，明确只要求受保护语义不可见、不得绕过授权上下文；勘误
经CQ私有interview-0002及Coordinator→Modeling/Protocol分别转交，业务受众与定义不变。
CQ随后发布后继版，Host逐字段比对与已批准有效内容一致，8题再次绑定当前review审批；
两版共16份决定、最高public-projection-0016，未向生产注入私有问题。
15:35:01UTC场景图登记触发cq-slices-approved真实交付；6切片、11共享术语、7跨片依赖。
Coordinator自行决定shared_core_plus_domain（4个Ontology标签），Host未选择拓扑；
delivery-12真实转交标签/逐片绑定/依赖顺序到Protocol，验证05f9bb5提示修复生效。
切片登记快照的四角色累计输入缓存比例96.889%至97.371%，暂无contextCompaction记录；
保留auth005-usage-initial-slices.json，仅阶段性usage，不作整轮或受控前后提升结论。

15:37:42UTC切片CQ一次提交成功：28题、6切片，22公开/6隐藏。Host逐题核对，25项批准、
3项按已有业务来源澄清未知与可证明边界（具体私有修改留在Runner审核决定，不进入生产消息）。
44份累计审核决定均接收，随后cq_freeze成功：cq-batch-0001，snapshot digest
sha256:9ab95b861dd29d99f0e539a9c69df5cf44f0aacfdeb1ed36b504b722d852faa5。
全池36题（8全景+28切片），30公开/6隐藏，最高public-projection-0045。Host通知生产仅消费
公开投影并继续中立候选；向CQ说明已冻结、无需重复发布逐字段相同的已审核问题。
Coordinator对场景图公开问题改写收到可恢复一致性反馈，正在以最新公开原文修正；没有新start。
Host参与CQ私有审核，不能担任后续独立盲测裁判；最终语义验收仍须独立于生产/修复。

15:42:32UTC Coordinator delivery-14正式交接阶段3；15:47:23UTC Modeling delivery-15
交付6份中立候选与stage3槽位，实际读取计数143项（entity36/property47/relation45/shape15）。
共性分析7节点、7成员关系、5共性关系，候选记录10项明确未知；尚未落库，不作为语义验收PASS。
Coordinator开始候选审核与逐项摘要绑定，approvals.json已写；Protocol转换计划尚未发布。

15:48:54UTC审批条目触发approvals_schema_mismatch；根因为stage3_slot entry缺revision。
Coordinator先猜null仍不合法，Host用现有validate_approvals(unified=True)只读定位detail=revision，
经host-approval-revision-001回传“正整数且保留009顶层schema”；Coordinator补revision:1恢复。
Host最初进度误称confirmed_enum_value也必需，随即按实际校验纠正为该字段可省略/null。
prompt-contract缺漏由Claude Code仅在008B reference approvals.rules新增1条现有类型说明；
JSON与diff检查、实际校验器12项有界输入核对通过，无运行代码更改，不改当前冻结提示。
Protocol已真实完成读取四个空Ontology、create session/checkpoint/lease，Session
363bf4fe-df0c-4055-9027-1dce115b309c；发布b01-cov-sc-predicates-r1（6项）与
b02-cov-ops-properties-r1（13项）两计划，delivery-18申请翻译批准。Modeling delivery-19
提出mapped_property绝对IRI需真实来源，Host未猜平台标识，待Coordinator/Protocol衔接回执。

16:01:43UTC 首次 staged submit 返回原始 AttributeError（list 无 values），未生成 intent/receipt、
未转发批次。只读定位：计划 candidate_content_digests 错为列表，候选有非法 scope 字段，
且三项闭合校验以 eager tuple 执行，后续异常掩盖更早的类型化反馈。第一失败层为
platform-contract，不据此判定建模质量失败。T0复核：绑定与完整性校验保护实际写入，必须保留；
不可恢复异常并非必要防御，应降为可定位、可重试的输入反馈，无需新增恢复机制。
Claude Code窄修复：计划入口复用已有 binding 校验，digest map 非对象返回类型化字段错误；
闭合校验按原顺序短路，保留第一阻塞层；009权威合同补充同一对象形状说明。
新增3项机械测试通过，其中1项经真实 AF_UNIX capability 证明错误输入零写入后，修正输入可在
同一 runner/capability 成功；另2项覆盖短路顺序和存储 intent 边界。相关测试103通过；
完整 modeling_team 套件1462通过、1既有真实Codex opt-in跳过、321 subtests通过。
Ruff 新测试和 staged_decisions 干净，runner 仅保留HEAD既有3项问题，无新增。
本修复未改 backend/frontend，无需服务重启；当前run仍使用冻结05f9bb5，不热替换运行代码。

16:10:18UTC Modeling delivery-27发布六片r2，宿主复用实际 validate_unified_candidate 校验全部
通过；仍143项。非法顶层scope移除，5项非空范围保留到合法shared_scope，前序r1保留。
16:11UTC Coordinator delivery-28/29完成19项决策revision2及摘要重批，通知Protocol发布新计划。
截至16:17UTC尚无模型批次写入回执，等待修正计划翻译批准与原run继续；不构成L0/L1 PASS。

16:20:14.834459UTC修正计划真实进入staged submit，通过此前输入校验后，出现新的第一阻塞：
staged_batch_forward_failed: no host-side write forwarder is configured for this run。
CLI main构造TeamRunner未注入staged_batch_forwarder，生产路径始终None；本次写入接线缺口归
platform-contract。已写本地intent-1（dry_run/status=submitted），尚未调用平台，无receipt。
Host通知停止重复提交、禁止绕过staged边界；16:22前后pause确认。Claude Code只读确认无现成
同run重新接线路径，pause/resume不能重载；不能借修复启动新run（本授权1/1已用尽）。
宿主实际GET四Ontology modeling-batches均为空且next_cursor=null，Session也无batch，
原始响应保留auth005-platform-precheck.json；临时查询admin立即撤销。
16:25:33UTC停止并清理Team（首次semantic start→stop约62.5分钟；到首次实际提交约57分钟）。
Runner标CLEANED但scope实际blocked=Build Session Ontology coverage drifted，此既有清理
限制不能被CLEANED掩盖；平台protocol/admin keys已撤销。Host按实际零批次取消唯一session、
核对lease全部released，然后删除本轮空project；project/4Ontology/session逐个GET404。
独立收尾证据auth005-external-cleanup.json，原Runner失败记录未改。运行残留secret-audit仍记
private_credentials_destroyed=false，不能宣称全部私有留证已无凭据；不删除原始运行留证。
当前L0 Runtime=BLOCKED（无真实dry-run/apply），L1=PARTIAL（6片143候选、36冻结CQ，尚无
落库验证/推理/受治理检索及独立语义验收），L2/L3未验收。不得由接线失败推导模型质量失败。

缓存观察auth005-usage-paused.json：四角色累计input44,801,063，cached43,604,608，
加权命中97.329%；Modeling97.945%、CQ97.787%、Protocol97.473%、Coordinator95.987%。
期间contextCompaction：Coordinator2、Protocol2、Modeling1。该数是app-server累计usage，
不是受控前后对照，也不证明整体时延或成本改善；流程耗时仍受反复合同核对与接线缺口影响。
语义/源读取→首版六片候选约24分钟；之后约38分钟主要用于审批、输入修订、计划与平台阻塞。
这些为阶段墙钟，不冒充精确角色有效工时；未证明语义有效时间过半，因此停止扩展harness，
仅修复本次实际写转发缺口，随后交回授权边界。

写转发缺口由Claude Code实现最小独立函数：每批次以本轮Protocol key创建/关闭一次canonical
stdio MCP连接，固定调用submit_modeling_batch，批次参数原样转发，返回真实backend data。
CLI在prepare后为staged任务绑定函数、调用时读取当前run key；基线登记新模块。不增加常驻
队列/线程、恢复入口或旁路提交，不复用/扩大Acceptance只读转发器，无backend/frontend更改。
宿主复核纠正两点：(1) _run_tool可在提交后把内部异常包装ok:false，因此只将已证实的前置
拒绝作为definite，其余内部/依赖/无可识别结果保留unknown并使用现有不确定写入处置；
(2)本地.env推理器路径已失效，host转发环境按现有Protocol合同映射到当前checkout真实脚本，
不修改.env或服务部署。UNKNOWN不能因idempotency而声称无写入。
验证：23项新增测试通过；真实AF_UNIX capability→stdio MCP fixture→Runner receipt链路成功，
非真实业务写入；覆盖CLI staged绑定、参数/环境、前置拒绝、未知结果及子进程退出。
另对真实backend MCP作缺字段零写入请求，确认实际工具参数及错误信封。完整modeling_team
回归1485通过、1既有opt-in跳过、321 subtests通过（82.03秒）；新增模块/CLI/测试Ruff通过，
runner保留原有3项告警。未追加semantic start，不将本次机械验证写成建模或受治理检索PASS。

## auth006（2026-09-10/11，glm-5.3-flash max ×9 次授权）

用户授权9次fresh starts，Team模型glm-5.3-flash/max（profile glm-flash-max，glm-direct路由，
用户指定优先于非高峰调度表），ClaudeCode保持默认provider。本轮共10次真实启动尝试，全部
终态失败且平台建模批次写入始终为零；失败层仅runtime/infrastructure与collaboration/routing，
无任何模型质量结论依据。完整台账、逐次第一异常、13个修复提交（6c78523..cd8d252：GLM长推
理看门狗300→1200s、上游read_timeout 330→1250s、连续上游失败阈值、非formal两步owner
answer权威合同、task补挂验收交接合同源、run_fallback_timeout 5400→10800、staged run协作
issue通道及其表面/schema/gate缺陷修复）与两种额度口径的诚实核算见
workspaces/skill-role-20260911/SESSION-HANDOFF-20260911-auth006.md（原始每轮证据保留于
同目录各runtime-checkout，临时平台资源已删净并404核验，原Runner状态未改写）。
L0 Runtime仍BLOCKED（最接近点：start6已到达已批准172项物质化计划，差一次staged submit）；
L1仍PARTIAL（每轮合格候选/CQ，无落库验证/推理/受治理检索及独立语义验收）；L2/L3未验收。
每步修复均经modeling_team全量回归（最终1502通过/1既有跳过/321 subtests）；无backend/
frontend产品代码改动，无服务重启要求。额度口径歧义（保守10/9 vs 字面9/9）需用户裁决；
新授权到达前不再启动。

## auth007/auth008（2026-09-11，glm-5.3-flash max，两次授权各 ×3）

auth-r3-0-006-007（07:52 +08:00 授权 3 次 fresh starts）start1 于 07:53 启动
（runtime-checkout-auth007-1，runtime commit f62a782）；auth-r3-0-006-008（17:41 授权
3 次）start1 于 17:42 启动（runtime-checkout-auth008-1，同一 commit，授权注记确认
auth007 终态后无可恢复 live run，按 fresh start 使用）。两次 run 均无平台建模写入，
终态均为 run fallback timeout 10800 active seconds → TERMINAL_FAILURE_CLEANED
（auth007 11:17，auth008 20:52），资源清理完成、无残留进程、控制 FIFO 已清空；
auth008 额度仅消耗 1/3，剩 2 次 fresh starts 未使用。

auth007 进展：CQ 冻结与 staged 链路走通，gate 反馈共 4 次（07:53 stage3_missing_artifact、
09:20 conclusions_schema_mismatch、09:37 conclusions_approval_missing、09:50
unlock_code_mismatch，均只发一次），最后输出 09:52，此后约 85 分钟无任何活动直至超时。
auth008 进展为本任务历次最远：issue-1 业务澄清 pause/resume 走通（f62a782 新恢复链路
首次实战）、CQ 冻结、stage3 决策、候选 r2（175 项 + 7 显式）、24 条 conclusion 全部
analyzed→confirmed r2（r1 逐条归档）、unlock/checklist 就绪、staged submit 端点已武装；
gate 反馈 4 次（18:08:41 conclusions_schema_mismatch、18:17:03
conclusions_invalid_status_fields + conclusions_approval_missing、18:17:47
approvals_schema_mismatch），coordinator 18:19:34 修复 approvals（补 note 字段）后
18:19:42 turn 正常完成，四角色线程全部 idle，此后 2 小时 33 分零活动直至超时。

### 停滞根因（2026-09-11 深夜对保留工件的 forensic 复盘）

用主仓 f62a782 校验器对 auth008 保留工件现场重跑，`staged_artifact_issues(unified=True)`
返回 74 个 issue：26× conclusions_schema_mismatch（text fields）+ 24×
conclusions_invalid_status_fields（:confirmed）+ 24× approvals_schema_mismatch
（confirmed_enum_value）。逐字段核对确认全部同源：四个角色把 candidate_value 与
confirmed_enum_value 写成 JSON 数组（与 CQ 枚举集合语义一致），而确定性校验器 `_nonempty`
只接受非空字符串（runner 测试夹具即字符串形态；r3-0-008b-staged-decisions-contract.json
声明了字段名与状态机规则但从未声明字段类型）。类型分歧自 r1 起就存在，因此这批 issue
在整轮 run 中持续为真。

停滞机制为四层叠加，缺一不会致死：

1. gate 反馈按 `recipient:reason_code:artifact` 指纹永久去重且对内容不敏感
  （runner.py `_deliver_staged_gate_feedback`）：每个 reason code 只投递一次，工件重写后
   同码 issue 不再发声——18:17:47 之后每 0.1s tick 都重新验出同一批 issue 但全部被吞。
2. 反馈 detail 只有字段名（无 expected/actual、无类型提示），coordinator 按提示把
   approvals 误诊为缺 note 字段并"修复"，gate 实际抱怨的类型分歧从未被在轮内识别。
3. 工件合法→沉默、非法→一次性反馈的门禁设计使"修复后谁来派发下一 turn"无人 owns：
   coordinator 修复完等 Runner 复查，Runner 复查发现 issue 却被指纹去重静音，Broker 无
   待投递、无 open reply slot，routing 无从派发。
4. 本应兜底的 `_check_cooperative_idle`（300s 全 idle 询问机制）被
   `_formal_coordination_enabled()` 的 r2-3-003/005 硬编码白名单挡住（r3-0-006 task 与
   r3-0-011 profile 均不在列），整个窗口零询问、零 nudge，只剩 10800s fallback 单点。

auth007 的 85 分钟死寂为同构停滞（最后一条 gate 反馈后被去重静音至超时；其工件已随
清理删除，类型分歧无法直接复核，但 09:20 的 conclusions_schema_mismatch 与 auth008
首码一致）。两次失败分类 collaboration/routing 均成立，仍无任何模型质量结论依据。

### 下次启动前的候选修复（2026-09-11 深夜已按最窄层实施，auth008-start2 前生效）

实施决策（全部 TDD，先测后码；GitNexus detect_changes 风险 LOW、受影响流程 0）：
类型约定选"接受非空字符串或非空字符串数组"（后端
`compile_create_enum_meaning` 每个 enum code 编译一条 create_enum_meaning，数组是
自然结论形态）；失败层定位为 platform-contract（校验器/反馈实现未对齐合同），
不动 `_formal_coordination_enabled` 白名单本身。

1. 已实施：`_enum_code_set`（staged_decisions.py）——candidate_value/confirmed_enum_value
   接受非空字符串或非空字符串列表；create/update_enum_meaning 的 trace 匹配由全等改为
   逐码成员判断（每码一条 create_enum_meaning）；合同 JSON 同步声明该类型与逐码物化规则；
2. 已实施：gate 反馈指纹加入 details 的 sha256 摘要——同内容仍去重，内容变化即重新武装；
3. 已实施：notice 携带 `details` 数组；校验器 detail 串写明字段名、期望形态与
   实际类型（trace mismatch 附 payload 码与合法码集合）；
4. 已实施：`_check_cooperative_idle` 入口放宽为 formal 协调 **或** `_staged_decisions`，
   staged r3 run 同样获得 300s 有界 idle 询问（白名单本身未改）。

新增测试：`test_r30008b_staged_decisions.py`（多码合法/非法形态 typed/逐码成员/
detail 内容断言）、`test_r30008b_gate_feedback_rearm.py`（同内容去重/变更重武装/
notice 携带 details）、`test_cooperative_idle_inquiry.py`（staged run 获得询问 +
非 formal 非 staged 不询问守护）。全量回归 1513 passed / 1 skipped / 328 subtests；
`test_deepseek_codex_runtime.py` 7 个失败为 HEAD 既有环境相关失败（已用干净
worktree 在 f62a782 复现），与本次修改无关。

原候选清单：1. 在 r3-0-008b 合同中显式声明 candidate_value/confirmed_enum_value 的类型（沿用校验器
   字符串约定，或校验器改为接受非空字符串数组，二选一并同步测试夹具与提示面）；
2. gate 反馈去重指纹加入工件内容摘要（工件变更即重新武装）或加 TTL/升级通道；
3. 反馈 detail 携带 expected-vs-actual（至少写明期望类型）；
4. 将 `_check_cooperative_idle` 与 r2 白名单解耦，覆盖 staged r3 run。

原始证据保留于 workspaces/skill-role-20260911/（auth006-start1..9、auth007、auth008
各 checkout 的 evidence/ 与 staged 工件；auth008 保留 conclusions r1 归档链、approvals
r2 与全部 gate 反馈账本）。本节为首次将 auth007/auth008 记入本台账。

## auth008-start2（2026-09-11 夜—09-12 凌晨，HOST_STOPPED_INTERIM）

用户 21:1x +08 指示"本次建模结束后暂停任务，完成中间结果归档，收回剩下的一次建模
次数"（收回记录 fresh_starts_remaining=0）；随后指示"请先完成修复，然后继续建模流程，
使用剩余的两次授权"。start2 于 21:59:48+08 启动（worktree
runtime-checkout-auth008-2，runtime commit 27d337d，4 项修复在位，全角色 glm-flash-max）。
运行约 2.5 小时后用户于 09-12 00:24+08 指示"停止本轮建模，完成临时收尾"，run 在
WAITING_OWNER（issue-3）状态下被停止：FIFO stop 动作后 runner 卡在 poll 未清理
（13 个 codex 子进程不变、无 SIGTERM 处理），最终对进程组 SIGTERM（exit 143）。
授权关账：3 = start1 消耗 + start2 消耗（HOST_STOPPED_INTERIM）+ 1 次收回未用，无 start3。

进展为本系列首次走通双轮 CQ 审查机制：全景 cq-review-0001（7 题，decision-0001..0007
+ public-projection-0001..0007）与分片 cq-review-0002（16 题，SCC/IWO/DEL/PRT 各 4，
每片 2 公开 + 2 隐藏；decision-0008..0023 + projection-0008..0023），23 项决策全部
按业务包 BS-20260910-01..08 逐题引用批准。staged 链路推进至 approvals：coordinator
创作共享 scenario-map.json（bind 归属经 issue-2 澄清后由 coordinator 在专属 bind 内
创作，与 start1 先例一致），13 条结论全部 analyzed 且 coordinator 全部批准写入
approvals.json；unlock/ledger/stage3 candidates 为空，无枚举物化、无平台写入污染。

issue 处置序列（evidence/issue-control.jsonl）：issue-1（protocol 报，等 public
projection）pause 14:04:29 → guidance 决议 resume 14:33:30；issue-2（coordinator 报，
scenario-map 共享不可见，实为 namespace 隔离设计）pause 14:38:27 → 澄清决议 resume
14:57:01；issue-3（coordinator 报，15:07:40"等 >0007 public projection 出现"）pause
15:07:45 —— host 以 16 项 CQ 批准 + question/user 便签回应，**未发 issue-3 的
issue_resolution 信封**，此后 coordinator 进入固化等待循环（认为 issue 仍暂停、
两次派发 transport 受理但未解锁），直至停止。

### 关键发现（候选修复，需授权轮 + TDD）

1. **host 决议不回送 coordinator 自报 issue**：`_apply_issue_control` 的
   `self_resumed` 分支（runner.py ~6750）假定"报告者自己持有决议"而跳过向 reporter
   派发 resolution delivery——对 coordinator 自报、host 决议的场景为假，是 start2
   固化循环的直接根因。
2. **host 操作教训**：对 coordinator 报告的 issue 必须用严格
   issue_resolution 信封（issue_id/reporter_id/control_epoch）；question/user 便签只被
   steer 进当前 turn，不解锁 WAITING_OWNER 语义。
3. **idle 询问真实运行仍被抑制**：fix 4（staged 覆盖）单测通过，但 start1/start2
   真实运行均未触发，疑似 `acceptance.has_live_children` 等真实形态条件在单测中缺席
   （单测 acceptance=None）。需补真实形态用例。
4. **scenario-map bind 归属**：`/agent/work/scenario-map` 为 coordinator 专属可写
   bind（`runtimes/codex.py _coordinator_scenario_map_bind`）；modeling 写同名路径只落
   私有沙箱 `runtime/<role>/work/`，应写入团队指引避免复发。
5. **FIFO 陷阱**：outer FIFO 固定 `<run-root>/control/outer-input.fifo`
   （`__main__.py:1848`）；shell 重定向到不存在路径会静默创建普通文件。
6. **stop 语义**：FIFO `{"action":"stop"}` 在 runner 深入 poll 时可能不生效（无信号
   处理），需 SIGTERM 兜底；deliveries.jsonl 存在证据缺口（16:05:30/16:19:03 coordinator
   →modeling 派发 transport 受理 sequence 20 但未落账）。

4 项修复实测：fix1（枚举数组形态）推进至 approvals 后 analyzed→confirmed 未执行即
停止，未在真实链路走完（仅单测覆盖）；fix2/fix3（重武装 + details）未触发（本轮无
gate feedback）；fix4 真实运行未触发（见发现 3）。

start2 完整时间线与证据清单见
`workspaces/skill-role-20260911/auth008-start2-interim-record.md`（run 现场整体保留于
runtime-checkout-auth008-2 worktree，56M 证据 + staged 工件）。
