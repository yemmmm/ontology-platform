# 最小安装链 Flashx 两组授权与窄修复

范围：[R4.3-024／025／026](../../requirements/requirements-v4.3.md)。
用户先授权三次，指定生产及独立 Consumer/Judge `glm-5.3-flashx/high`，
Delivery `gpt-6.1-sol/medium`；随后明确要求当前组三次用完后修复已发现问题，
再启动另组三次。两组分账，下一组不能沿用前组剩余值、scope、题池或裁决。

## 前组三轮结果

- `r4326-20261016-flashx-start1`：真实开始于 2026-10-15 16:26:37 UTC，
  新加坡时间 00:26:37，距宿主授权登记约 6 分 50 秒。两批已应用，独立公开 1/1、
  隐藏 3/3 通过；端点编码、派生状态及宿主技术补位仍保留，整体 PARTIAL。
- `r4326-20261016-flashx-round2`：16:54:24 UTC 开始；两批已应用，但控制等待后
  发生 300 秒 inactivity timeout，独立验收未执行。第三个纠正 intent 为 rejected，
  以精确 client_batch_id/idempotency_key 只读查询数据库均无 Batch/Attempt；原两批
  均 applied。Session cancelled、租约 released、运行权限 revoked，状态 CLEANED。
- `r4326-20261016-flashx-round3`：17:15:04 UTC 开始；普通冻结等待被提前报告为
  terminal blocked，冻结确认遭 `instruction_recipient_terminal` 拒绝。未写入，取得
  READ_ONLY_WAIT 封口，revision 0、无 Session、无待定或未知写入，原线程保留。

三轮全部消耗，fresh starts 单列为 3。前组台账及逐轮证据位于本机
`workspaces/minimal-chain-20261016-flashx-sol/` 和对应 `workspaces/modeling-runs/`。
第 1 轮 CQ 通过不能证明底层端点正确，也不能外推为重复性通过。原报告不改写。
有效语义、技术和等待时间没有完整区间测量，保留 unknown，不把进程寿命算成有效建模时间。

## 根因、T0 与最小修复

1. 资源引用缺少真实 MCP envelope/完整资源对象示例；read-model 的 `id` 实为 IRI，
   却被解析为平台 ID，造成 domain/range 再编码。明确完整 receipt item 的
   `/structuredContent/data/items/N` 路径及 ID/IRI 区别，不猜 UUID。已应用 receipt 的
   稳定 UUID 可在修订推进后经当前授权读核实同一 IRI 再复用。
2. `resume_waiting_reporter` 把 resume 自行重排队，活跃 turn 收不到持久 resolution，
   最终超时。既有 Runtime 已支持 `turn/steer`，删除重复等待，仍核对原线程和派发回执。
3. handoff 返回缺少实际文件定位，Delivery 混用 Host 与隔离角色路径；返回绝对
   `model_handoff` 和仓库相对路径，提示使用当前配置精确启动值，不换成旧 snapshot。
4. forward 拒绝/未知结果缺少可定位的原请求身份；保留 observation、错误和批次/幂等
   身份，明确拒绝与 unknown 分开，后者仍须对账，不伪造 receipt。
5. 最小角色将普通上游等待当 terminal；权威角色说明明确继续同会话等待实际冻结确认。

T0：作用域、源忠实度、当前资源存在、应用原子性及未知写入核对仍必要。旧 receipt
修订完全相同的限制及活跃 turn 必须先结束的等待并未增加所需保护：前者可用当前受治理
读取验证稳定身份，后者已有原线程 steer 合同。因此收窄/删除冗余限制；没有增加恢复框架、
业务拓扑规则或新的硬门，也没有延长超时来掩盖死锁。历史 run 不热修复。

## 工程验证边界

外部修复 Agent 在 `backend/` 使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`：

- 最终相关八文件：137 passed；direct execution 单独 25 passed。
- Team 全套：3048 passed、12 skipped、1 failed，318 subtests passed，452.33 秒。
  唯一失败为 `test_staged_batch_write_forwarder.py::test_timeout_after_dispatch_stays_unknown_and_leaves_no_child`；
  同一 nodeid 单测重跑 1 passed，97.57 秒。保留全套失败，不能声称全套一次性 PASS。
- 触达文件 Ruff、JSON 解析和 diff 空白检查通过。测试原始输出保留于修复 Agent 的
  exec 记录，没有独立原始日志文件。宿主先前误读的 `/tmp/ontoweave-minimal-chain-followup-*`
  日志为 00:05/00:06 的旧版本记录，3044/168 不属于本次验证，不计入本次结果。

触达 `modeling_team` 执行与提示合同，未改 backend/frontend 可执行代码，无应用重启要求。
GitNexus 对目标符号返回 Target not found，采用定向调用点和回归覆盖，不声称图覆盖。
宿主另审阅资源对象示例并修正为完整 receipt item；待修复提交后以全新进程进入下一组。
真实语义质量、正确端点与恢复效果须由新组实际应用、治理读回和独立验收证明。

## 新组启动链补记

新组于 2026-10-15 17:52:08 UTC 激活。首次三次进程启动分别在
`mcpServerStatus/list`、`initialize`、`thread/start` 无响应退出，均未产生 semantic-start，
所以新组仍为 0/3；空 scope 已删除，进程退出与范围权限撤销已核实。私有凭据审计匹配
仍标记 PARTIAL，不宣称整体清理通过。18:12:15 UTC 核对首次 semantic-start 的
20 分钟完成门未达成，原因是上述真实启动失败及其窄诊断，不重置原起点。

直接 CLI 及三 MCP bwrap 握手探针当下正常，资源压力仅为推断，不能唯一归因。
进一步真实三角色探针在 CQ 的 `skills/extraRoots/set` 卡住 15+5 秒。按 T0 复核，
package loader、冻结 baseline、只读技能挂载和首轮精确 `type=skill/name/path` 注入已
共同提供实际输入合同；原生 Skill inventory 的额外注册与列表精确检查不是独立完成门。
删除该重复预检，不扩大作用域、不省略实际技能输入，不延长全局超时，保留 initialize、
thread/start 和必要 MCP 能力核对。

修复后真实三角色 bwrap 的 initialize/thread/start 均成功，显式注入接口成功；没有
执行 turn/start、语义建模或平台写入。Codex 隔离文件 57 passed、55 subtests passed，
随后针对启动不调用 discovery 的回归 1 passed、56 deselected。diff 检查通过。
原生首 turn 实际技能读取仍待新组真实运行核对，探针不替代 semantic-start 或独立验收。

移除 inventory 后 `start1d` 仍在 `thread/start` 的 15 秒窗口失败，无 semantic-start，
表明 discovery 不是全部初始化故障。复核运维等待与正确性边界后，仅将 initialize、
thread/start、mcpServerStatus/list 单次等待改为 60 秒，等待同一 request id、不重放。
首次 turn/start 鉴权屏障和其他业务/控制 RPC 仍为 15 秒；EOF、显式 error、解析失败
立即报错。新增超时观察仅记录 method、耗时、帧数和子进程 poll，不含输入或凭据。
若 60 秒仍无响应，保留初始化阻塞，不继续增加机制或放宽。

该最小变更的隔离文件 60 passed、55 subtests passed；新 RPC focused 3 passed、
鉴权相关 2 passed；Ruff 与 diff 检查通过。尚未证明真实启动恢复，须新进程实测。

## 新组首轮实际输入与技术补齐

`r4326-20261016-postfix-flashx-start1e` 于 18:32:01.700119 UTC 实际开始，
新组已用 1/3，剩余 2，fresh semantic starts=1；启动代码含 `d23846f`。
启动恢复已证实，但首次启动 20 分钟门仍失败，不重置耗时或覆盖前述预启动失败。

原生 transcript 仅有 `type=skill` 元数据而无正文，Modeling 随后确认未读到必需技能。
因此此前显式注入接口成功不能证明实际正文到达；inventory 删除的判断须补此证据缺口。
持久修复在初 turn 显式加入只读 staged Skill 完整原文、路径和摘要，保留原 Skill 元数据，
不恢复易卡住的 inventory；源/staged 摘要漂移在发送前返回原有输入错误。
当前原进程不热更新：沿原 Delivery/Coordinator 通道补发同一获准技能，不新增业务事实。
核对无 intent、receipt 或未知写入后保持普通等待；完整读取确认前不得写入。

完整 staged Skill 为 4835 字节，SHA-256
`4956333945968e8fcad46d2ca346fc67fcd56352923c9ca029db5794e201703f`。
PTY 超长行被截断，改以三片拼接并验证完整摘要；Delivery 已确认拼接一致，截断材料未转发。
此为同轮输入技术补齐，不另扣轮次，也不计 Delivery 无宿主补位的自主交付通过。

持久修复验证：Codex 隔离文件 61 passed、55 subtests passed（1.28 秒）。
该检查验证完整正文进入首次 turn 参数及 staged 漂移拒绝，不替代 live 实际读取或语义验收。


18:40:10 UTC 原 Modeling 通过正式材料读取确认 `read_complete=true`、`truncated=false`，
完整 4835 字节摘要相同；保持同一初建轮继续。两批 applied，revision 2，18:41:55
finish 完成。直接数据库只读核对本轮 Session `37730268-2ffb-4a3a-9537-46bbde863ec4`
为 completed/revision 2，租约于 18:41:55.354752 UTC released；未追加生命周期 mutation。
18:45:41 原 Team 进入 read-only wait，运行写权限撤销、资源保留、无 pending/unknown writes；
18:45:51 正式 CQ handoff ready。原生产摘要端点与 apply 回执/最终读回相反，保留
PARTIAL 及公开证据差异，不凭结构关联 COMPLETE 宣称语义正确。

独立隐藏 Consumer 3/3 完成；18:49:09 attempt-0001 报告 `full_pass=false`、verdicts 为空，
Judge setup 为 `collaboration_binding_changed: invalid scenario map`。此为协作合同失败，
不是模型质量裁决；公开 1 题尚未执行，完整分母仍为 4。原地图、模型与报告不修改。
原 Coordinator 只读定位到 `adjustments[0]` 将普通收尾说明写成 string，而非合同对象。
修复者 T0 复核：此字段仅协作进度，不是 Judge 语义证据，不应以格式缺陷阻断独立语义验收；
仅降级该可恢复字段，保留 source/digest 及关键业务/身份绑定硬门。修复和只读复验不扣建模轮。


Judge 最小修复只匹配 `map_schema_mismatch` + `adjustments[i]: fields`，从其工作副本
省略相应进度条并记录 `collaboration_progress_invalid`；原地图、handoff 和摘要不变。
其他候选/共享定义绑定、plan/identity conflict、review 结构仍硬校验。两套 Coordinator
权威提示补充 closure/audit/status 不属实质业务变更，应放既有 note/progress。
相关验证：r4007 34 passed，partial judging 57 passed，minimal chain 10 passed，
contracts 11 passed、3 subtests；Ruff/diff 检查通过。未做 GitNexus 图分析，定向核对
`_cq_collaboration_context` → map validator/projection → Judge setup 调用点。
真实复验仍待执行；已封存原 attempt，不把工程测试当语义恢复通过。


公开 regression `mic-concepts` 独立 Judge pass，full_pass=true，版本无漂移；仍不能
代表隐藏方向题通过。隐藏恢复的 production_handoff checkpoint 保存返回
`checkpoint_selector_required`：本轮未启 modeling_checkpoints；未手工造包或覆盖报告，
保留三题 Consumer completed、Judge 未裁决。当前运行恢复缺口不扩为新恢复框架。

端点差异经原 intent/receipt 定向核对确认为 Modeling 质量缺陷：Class 回执 item0 为
Installed Asset (`6a6f2854-9556-53c9-9c28-2cd547d5eedc`)，item1 为 Service Site
(`b769ef4d-8d59-50b7-a2d2-65a703b005e0`)；关系意图选 source `/items/1`、target
`/items/0`，平台按完整 Pointer 和对应 resource_outputs 如实执行，并非 UUID 映射错误。
交付摘要自报与真实结构相反，自查未核对实际 domain/range 对应的端点 label。
下一轮仅修正此实际结构与定义一致性，仍沿获准范围/显式未知；新实质修模将另计第 2 轮。
开始前先修复权威技能中的身份匹配及实际结构自查提示，不注入隐藏题/答案。


端点提示修复已落盘于 minimal-chain-modeling Skill 与 paired instructions：根据
client_item_id/元数据和实际 label/IRI 匹配完整 receipt，不按列表位置推断；应用后按
真实 sourceClassId/targetClassId/domain/range 展开端点 label/type，与批准定义逐项核对。
未新增平台业务规则、字段或硬门；未注入历史 UUID 或私有验收答案。
验证：R4.3-026/contracts 21 passed、3 subtests；direct_submission/direct_modeling
29 passed；提示合同检查与 diff 检查通过。新轮实际效果待验证。


## 新组最终状态（PARTIAL）

- 第 2 轮 `r4326-20261016-postfix-flashx-round2` 于 19:03:10.065835 UTC 真实开始，
  新进程代码 `64cf733`。Modeling native user message 已核对包含完整 staged Skill
  5831 字节，SHA-256 `84e7e6bc3e8abbb3c3632641f3047e55c4df4ebbc8e0d740e01364869a2390cb`。
- 19:09:09 冻结公开 1 / 隐藏 3 题，19:11:53 原 Coordinator 转交确认。
  19:12:02 Classes applied；19:13:09 relation applied 后，治理自查再次发现端点反向。
- 第 3 轮为同 run 的实质语义修模：19:13:48.676 原 Modeling 实际提交
  `update-installed-at-endpoints`，19:14:05.550 applied，Batch
  `cf4445f5-7d28-4c43-aabc-1e6e35aa56d2` / Attempt
  `1f4c1b0a-4227-4234-acc6-a987c6410357`。按自查后实质修模口径另计轮，
  不能以同 run 或总体目标免扣。新组最终 **3/3 用尽，fresh semantic starts=2**。
- 最后版本 3，修正结果的原回执/只读对账确认设备到地点端点；未完成最终自查、关联闭环
  或独立语义验收，不能把 applied 推导为最终模型接受。
- 原调用 `call_9f3b36d0c0a1473a89b727fc` 在 native transcript 有 function_call，
  app-server 有 item/started 和已 resolved 的 elicitation，capability 有 ok/applied，
  但无 native function_call_output/item-completed。首个可证断点为既有结果回传链，
  尚不能细分 runner stdout 或 MCP bridge。19:18:48.794396 watchdog idle=300.008557，
  Modeling 退出；与前组同见 inactivity 模式，不能据此断言内部同根。
- 三个 Batch 和三个 Attempt 均经实际数据库对账为 applied，无在途或未知写入；
  19:22:36 Host 使用既有 HTTP cancel API 关闭 owned Session（cancelled/revision 2），
  回读租约 released、run model/read/admin keys revoked。临时 Host key 已撤销。
  原模型、workspace、事件及 runtime-failure state 保留，未伪造 handoff、未重放写入。

新组首轮公开 1/1 PASS、隐藏 Consumer 3/3 completed 但 Judge 未裁决；新组后两轮
没有完整独立验收。源证据与全部分母保持不变，整体结果 PARTIAL。当前额度 0，停止新
semantic start 与实质修模；Delivery 会话保留待命。主机生命周期补位不算 Delivery
自主交付 PASS。清理仅证明上述 Session/lease/run key，不宣称所有私有凭据清理通过。
技术修复、协作等待占本次观察主要时间，有效语义时间未完整计量，保持 unknown；
停止扩展平台/harness，不用更多机制替代缺失语义证据。

本轮相关提交：`27af453` 模型配置、`d357b24` 引用/同线程交接修复、`f488627`
移除重复 inventory、`d23846f` 有界启动等待、`704ead8` 首 turn 正文、`07bf217`
Judge 非语义进度降级、`64cf733` 端点身份/自查提示。工程验证与真实证据边界见上文。


后续用户单独授权定位并修复工具回传问题，已在隔离机械调用中复现并修复 15 秒读超时及
异常丢失请求 ID，详见[技术修复记录](2026-10-16-capability-return-timeout-fix.md)。
该修复没有启动新语义轮或恢复旧 run；上文 PARTIAL 与额度耗尽事实不变。
