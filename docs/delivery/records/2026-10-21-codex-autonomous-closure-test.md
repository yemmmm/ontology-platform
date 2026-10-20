# Codex 最小安装链：Host 技术补位修复与自主交付重测

## 范围与授权

用户要求先解决上一轮需要 Host 技术补位的问题，再新启动一轮测试。沿用
`2026-10-20-codex-plus6-continuation.md` 的原授权：原3元加追加6元累计9元，
共享原 budget_ref，不清零历史费用或暂估；追加三次机会已用1次、剩余2次。
本次只申请执行其中一次，实际 semantic-start 才扣账。不自动增加金额或新机会。
所有角色保持 Codex / glm-5.3-flash / low / default，复用 R4.3-026 Task/Profile
及唯一获准 scenario.md，新建 project/scope。正常私有 CQ Host 审核属于既有职责，
手工推进交接、验收、计量恢复或最终确认才计入技术补位。

## 第一阻塞与最小修复

归因为 runtime/infrastructure 的计量生命周期错误。原生 Codex 一个 turn 包含多次
代理接口请求；第一次接口返回后，原生 turn 仍在处理后续推理/工具，首份原生 token
数值尚未产生。原预算却从中间 HTTP 请求结束起计10秒缺数门，误暂停正常在途工作，
之后需 Host 核对晚到记录并恢复。R4.4-002 F5/F6 明确正常在途不适用10秒截止。

沿已注册 native capture 的同 thread/provider/key/model，及实际 llm_start/llm_end
区间绑定成功的代理请求：原生 turn 在途时待结算；已结束则从真实 turn 结束开始原有
10秒宽限。失败代理、身份不匹配、无生命周期依据及 turn 结束后持续缺数仍暂停。
这不生成 token 数字，不增加授权，不自动清除既有暂停原因，不绕过金额硬边界。

前轮最后缺少 FIFO 的原因是 Host 在验收确认之前提前结束生产 Runner。
Delivery 权威技能补充保持源 Runner 至 complete_cq_acceptance 接收回执，再正常
standby_run / finish_delivery；本次不增加离线补回执或新恢复机制。
预算控制 turn 期间 Coordinator 的历史300秒超时证据保留，未单独改动 watchdog；
本次验证消除误暂停后能否沿原链完整收口，不能声称历史所有超时已被修复。

## 工程验证

新增回归先复现两处失败，再通过：当前 Codex 专项及 TaskBudget 64 passed；
连同预算 runtime/proxy 集成与 usage capture 的相关集共102 passed。
两个改动 Python 文件 Ruff PASS。共享计量内核 Team 全量3713 passed、12 skipped、318 subtests passed（585.74秒）。
GitNexus 未收录 _refresh_summary，返回 UNKNOWN，采用现有调用点和测试检查，
没有宣称图覆盖。未改 backend/frontend，不要求应用服务重启。

## 真实重测

Host目录 `workspaces/minimal-chain-20261020-codex-plus6-152240/`，
session `minimal-chain-20261020-codex-plus6-152240-s2`，
计划 run `minimal-chain-20261020-codex-plus6-152240-s2-r1`。
Delivery 使用原 Host 工具自行启动、冻结、application、交接、组织独立公开/隐藏验收
及收口；外层只执行获准私有 CQ 审核和周期卡片观察。实际结果、金额和技术介入待补，
工程回归 PASS 不代替独立语义或自主交付 PASS。


实际 semantic-start 为 2026-10-20T16:15:53.552659Z，baseline
`67c1f2f05ef0b78cc5beb3cfb1825774b679b6f5f29b202884599fcebb185da4`。
本授权已用2次、剩1次。Host按实际来源审核了 cq-review-0001（全景公开mic-concepts），
正式回执保留，不等于完整池已批准。

本次首次启动命令遗漏 tty=true，使 stdin EOF。在16:20:28监督正常静止等待时，
程序依原合同以 business input closed 返回2，关闭原生Delivery与预算监视；
16:20:38存活Runner发现监视失联，正确暂停。第一故障层是Host启动配置，不是模型质量，
也不是本次修复后的“原生回合误判结束”。这属于本轮技术介入，自主交付必须PARTIAL。
原生进程有exit0回执，但监督退出码2，不能混写成功。原启动临时凭据已由finally撤销。

启动手册新增Codex exec_command使用tty=true和日志重定向不能保持stdin开放的说明。
Host按原预算tick重新读取既有证据，current coverage issues为空后，沿既有continue_authorized
恢复，不新增金额、不清历史。同run重载监督使用resume=True和tty=true，重新准备只读凭据；
没有再次semantic-start或扣次数。中间一次上下文管理器调用错误及一次监视租约冲突均未启动
模型；保留预算monitor事件。恢复后出现两个httpConnectionFailed provider_wait，交原Delivery
按真实状态处理；不将技术恢复视为自主PASS。16:28:27预算估算7.42218772、剩1.57781228，
监视active，暂停原因空；后续结果待补。


## 后续窄修复与最后一次重测

Delivery正式提交`host-repair-r1-fifo-20261021-02`。查到原CLI stderr已记录
`run failed: runtime failure is latched`；PID尚在是遗留线程/子进程，不代表原foreground
控制循环仍存活。不能创建一个新FIFO冒充原Runner恢复。Host将该请求以blocked回执关闭，
说明当前run不能安全同线程恢复，同时保留已修复代码与失败证据。

实际Coordinator失败发生于恢复控制回合：budget control的turn/start分支没有像正常
send_message的turn/start一样重置活动时钟，因此上一回合最后活动到现在的369秒被
错误当成新控制回合的静默时长。窄修复只在该分支复用_reset_activity_clock，位于RPC前，
避免原生turn/start通知把状态置running时仍使用旧时钟。原300秒真实不活跃检测保持。
修改既有集成回归先复现失败，再连同Codex计量用例39 passed；Ruff PASS，新的Team
全量3713 passed、12 skipped、318 subtests passed（599.63秒）。GitNexus同样未收录control_budget，采用正常start分支/调用点对照。

Host沿绑定PID和/proc启动身份，仅停止s2的14个所属进程（无live残留），保留原project、
模型和事件；撤销该project的4个临时key；监督退出130，未把WAITING_OWNER强改CLEANED。
预算快照`s2-final-budget.json`累计估算7.72819192、剩1.27180808，未追加金额。

沿原“遇到问题修复后重新启动”及追加三次机会授权，最后一次建立
`minimal-chain-20261020-codex-plus6-152240-s3` / `...-s3-r1`，使用tty=true和同一
Task/Profile、全角色Codex glm-5.3-flash low、同一总额9元预算。实际semantic-start后
本授权已用3次、剩0次；不再启动。s3只验证本次修复后原流程，结果待补。


## 最终结果与边界

修复提交`7ae8dea`。最后一轮已取得panorama及slice两个正式Host审核回执，实际公开1题、
隐藏3题均获批准；关系问题沿seed原ID`mic-direction`，没有跨阶段复制题目或缩小分母。
这属于正常私有CQ审核，不能当独立Consumer/Judge语义验收。

2026-10-20T16:41:12.245875Z预算在累计估算9.00685216元触发budget_exhausted。
各执行方仅有instruction_delivered，未全部effective确认，不能把pause_pending写成
“全部已暂停”。Host据原有限实验的必要安全收口，通过原stop_run/FIFO提交
`host-s3-budget-safe-close-20261021`，取得accepted/stopped正式回执；run实际CLEANED，
PID3348146已不存在。监督随后退出130，原生exit回执保留，没有伪造finish_delivery。

本轮尚未freeze，无模型application、无独立验收报告；`runtime-failure.jsonl`没有新增
inactivity失败。第一停止原因是预算，不能据此推导建模质量失败，也不能宣称Host技术
补位已在完整交付链消除。最终 **Delivery自主交付／真实语义重测均PARTIAL**。
窄修复的工程回归PASS与上轮既有模型语义回归PASS分别保留。

最终共享预算`s3-final-budget.json`：授权9元；已定价数值小计3.21217784元；
暂估6.459104元；累计估算9.67128184元，估算尾差0.67128184元。不是供应商账单，
暂估不是确定上界；Host与未接线辅助成本仍范围外。没有追加授权或清除历史费用，
暂停原因budget_exhausted保持。三次机会已用完，未再启动。

预算所有owner经正式停止/精确退出证据标为exited，监视已停止。七个启动/恢复临时凭据
数据库核对均revoked或随所属空project删除而absent；s2保留project的4个key全部revoked，
Ontology实际revision0。s3空project由Runner正常cleanup删除，故其read-key cleanup
返回false表示记录已随project级联消失，不能误报凭据仍有效。失败workspace、CQ回执、
运行事件与原报告保留；未触碰旧s1的已验收模型。资源验证原件为
`s2-s3-final-resource-verification.json`、`s3-budget-stop-result.json`及`s3-terminal-status.json`。

本轮主要耗时仍在CQ准备、技术定位、监督恢复与等待，未取得新的实际语义写入；不能
给出全任务token降耗或完整自动交付结论。后续如获新授权，应直接复用修复后的原入口，
不扩展harness或另建兜底机制。本次停止时不申请或推定新增额度。
