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
