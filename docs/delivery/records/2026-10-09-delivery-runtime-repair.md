# 2026-10-09 Delivery 真实运行故障修复

归属：[R4.0-023](../../requirements/requirements-v4.0.md#r40-023-独立-delivery-agent-与统一用户交互)、
[原实施记录](2026-10-08-r4-0-023-delivery-agent.md)及既有 R3.0-009 投影合同。
本轮用户授权最多五次真实建模，首次从零；建模指定 `glm-5.3-flash/high`，
技术修复指定 Claude Code `glm-5.3/high`。本文时间均为 UTC。

## 第一阻塞与最窄修复

| 已观察问题 | 修复对象与结果 |
| --- | --- |
| 原生 `thread/start` 接受并忽略 `default_tools_enabled=false`，Delivery 实际调用了 shell 和 sleep | 使用安装版本支持的 feature/tool 配置关闭这些原生能力，并在开始 turn 前查询实际线程 feature 状态；保留未知或未关闭状态的准确错误 |
| Delivery 初始 turn 长期活动，已经接受的普通输入仍排队等待 idle | 忙时经现有 `turn/steer` 向同一线程、同一实际 turn 转交原始来源包；idle 时沿用 `turn/start`；结束竞态保留队列；控制仍优先处理 |
| 全景七题先冻结，后续二十个切片题未进入同一验收池 | Delivery 技能明确选定草拟／审核阶段完成后主动冻结完整池；当前 run 发布新 27 题冻结，保留旧七题原件 |
| Protocol 需要 author task_id，却从平台查找或猜测 | Delivery 从冻结 Task 的 `identity.task_id` 转交原值，使用已有指导通道 |
| Protocol 提示错误地要求每个对象属性必须有正式 Class range | 修正原有矛盾语句：`create_property` 的正式 domain/range 可选，不据此发明业务父类或拆分关系；使用真实 dry-run 反馈 |
| Protocol 将历史 token 总量或估计视为整轮输出预算，要求新增输送能力 | 未实施新输送工具。既有分组路径保持逐 item 原文与批准；后续同线程 turn 正常完成，当前按实际大小与依赖分组 |
| 单项分片仍用原批次 `command_index=1`，Runner 在写 intent 前抛 `IndexError` | 计划加载和实际身份 close check 返回定位到字段与有效范围的类型化拒绝；保持原 shared intent/receipt 合同。新增回归覆盖越界、错误类型、合法索引及非 list 绑定 |
| Protocol 普通回复声明“后续 turn 继续”，未触发下一段执行 | 明确通过已有 Team 消息给 Coordinator 完成范围、回执引用和下一动作，由它接续；不新增调度器或固定每批 item 数量 |

索引校验保护批准决定与实际命令的对应，不能直接删除。可重试输入错误只拒绝当前内容，
不终止整个目标。当前 run 通过修正新分片元数据继续，未靠代码热加载绕过失败。

## 实际修复执行与隔离

平台代码和角色提示由独立外部 Claude Code 会话修复，CLI 选择 `glm-5.3/high`，
模型初始化及结果记录为 `glm-5.3`。复用已有 bubblewrap 文件挂载机制；只允许获准文件写入，
公开代码／Python 运行时只读，Host 原 HOME、私有 run、隐藏 CQ、Delivery 历史与管理员环境
不进入修复者。每次结束删除临时 provider 设置，保留修复结果、退出和隔离证明。

当前受限 `start_repair` 尚不支持 Claude，返回 `repair_isolation_unavailable`。
外层技术宿主因此使用另行证明的隔离 Claude 入口补位，未冒充 Host 自主修复记录。
外层还经同一实际 turn 的 `turn/steer` 转交公开技术诊断；这些动作均记录为技术补位，
本轮不能作为 Delivery 完全自主的 A13 PASS。

## 验证与生效边界

- 先前 Delivery 修复全套 Team 回归：2516 passed、11 skipped、304 subtests passed。
- 加入最终索引及提示修复后的全套 Team 回归：**2520 passed、11 skipped、304 subtests passed**，
  `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`，退出 0。
- 最终小反馈前的 unified／Protocol 身份／Runner wiring／gate rearm／binding 聚焦测试：59 passed；
  最终新增回归已包含于上面的全量结果。
- 所有修改的 Python 文件 Ruff 与 `git diff --check` 通过。
- 实际安装的 Codex App Server 使用 loopback canary 捕获，未调用真实模型、未消耗 semantic start。
  2026-10-08 18:41:13 的 `glm-5.3-flash` 出站请求只提供注册的 `emit_user_message`，
  六个受检查的原生 feature 均关闭。通用目录模型可能强制附加其他工具，未据此宣称所有模型的完整隔离。
- 新代码未热加载到当前 Delivery／Runner；提示未替换已冻结的生产角色输入。
  新会话加载修复，同一存活 run 继续使用现有正式反馈通道和原保留输入。
- 本轮没有修改 backend/frontend 应用代码，因此未重启应用服务；Team 检查不代替产品、L0 或 L1 验收。
- GitNexus diff 检查为 low，但新 Delivery 符号缺失、部分函数定位存在旧行号漂移；
  采用实际调用点、完整 diff 与上述回归核对，未声称图谱覆盖了全部影响。

## 建模与证据边界

当前 run：`r4009-20261009-delivery-glmflashhigh-start1`；实际 semantic start 为
2026-10-08 16:43:39，从零创建新项目，使用批准的工业服务资料，没有复用旧候选或 checkpoint。
截至本记录，授权已用 1／5、剩余 4。完整池为 `freeze-0002`：27 题，17 公开、10 隐藏；
旧 `freeze-0001` 七题保留，不能作为完整分母。

现有 Ontology 和 dry-run Batch/Attempt 是真实已创建的资源／技术记录；
dry-run 的零业务模型修改不表示数据库完全无写入。当前实际业务模型 apply、读回、
完整 27 题独立 Consumer/Judge 及 L0/L1 结论仍待原流程完成，不能由本文机械检查代替。

可读运行与技术修复原始证据位于 gitignored 的
`workspaces/v4-delivery-20261009/`、`workspaces/delivery-sessions/industrial-service-fresh-20261009/`
和本 run 的 `evidence/`。失败事件、旧候选、旧冻结、各次回执保留，后续成功不覆盖它们。
