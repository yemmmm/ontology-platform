# Delivery 观察分页与阶段交接组合修复

用户在本轮高消耗定位后授权“请定位并修复该问题”，随后追问是否曾出现。
本次沿 R4.3-030 F1/F2/F3、R4.3-022 的既有输入和接续合同修复，不扩展建模范围、
角色或运行框架，不启动新建模、恢复保留 run、追加金额或调用收费 Provider。
基线 `0f330e8`；保留用户原有未提交文档及所有运行原件。

## 历史与本轮根因

“已申请却未换线程、历史持续增长”的现象此前出现过，但触发条件不同：

- [2026-10-19 跨轮复盘](../modeling-retrospectives/2026-10-19-delivery-multirun-cost-review.md)
  发现普通 yield 覆盖交接意图；[对应修复](2026-10-19-delivery-runtime-parity-fixes.md)
  独立保存 pending_thread_handoff，但明确保留“全部待送输入落定”的条件。
- [2026-10-20 对照复盘](../modeling-retrospectives/2026-10-20-runtime-compare-cost-regression.md)
  发现已清理、语义开始前失败的旧 run 缺账本阻断其他 run；后续收窄了该条件。
- [2026-10-21 旧高消耗修复](2026-10-21-delivery-cost-fixes.md)处理了缺省请求身份、
  已拒绝误等待及 read_remaining 原件回退。它们不等于验证过大分页与实际切换的组合。

本轮 `minimal-chain-20261021-codex-glm-5cny-065018` 的保留原生记录显示：
132 个唯一响应，43 个自然完成 turn，Delivery 输入 27,485,750／输出 45,219；
7 个观察 input_id 被分成 42 页，全部 bootstrap。5 次显式 thread_boundary 后仍有
4／1／2／2／1 个待送输入，零切换尝试。完成工作后还处理了5个等待 turn，输入增加
3,685,288。单次输入从34,347升至381,145，逐响应与线程末次累计一致，未重复计量。

完整私有定位及逐行证据在
`workspaces/minimal-chain-20261021-codex-glm-5cny-065018/delivery-high-usage-analysis.md`
及同名JSON；未把旧语义裁决或冻结材料改写为本次修复的验证结果。

## 修复与T0复核

| 真实缺口 | 最小修改 | 保留的边界 |
|---|---|---|
| 普通观察合并强制 bootstrap，快照与变化重复进入长页 | 只有合并内容本身含首次／恢复 bootstrap 时才保留 bootstrap；普通更新继续 changes，并保留所有未送变化、错误和回执 | bootstrap仅确认自身；部分送达、unknown和原事件身份不清零 |
| core阶段提示随新观察消失，同input续页改变正文 | 每个input_id保留一份固定精简投影；恢复及后续页使用同一正文、digest和offset，动态送达／当前状态摘要留在正文外 | 原始journal不修改；原件与视图的来源边界保持 |
| 历史页追新状态仍指回原始journal | current_state指向最新input的同类精简投影，新operation读取错误直接进入当前摘要 | 完整内部原件仍可用于明确的技术诊断；补读不冒充送达确认 |
| 任意待送页都阻断阶段交接 | 已知未送观察可随原任务接续到新线程，旧input和未确认范围保留；已送给模型的新输入仍须有最新yield | 在途推理、用户控制、未知／尝试中原生送达、恢复、未知写入和未结算请求继续延后；只接受真实accepted的阶段回执 |
| 交付完成后旧页继续产生等待推理 | 已记录work_result且当前资源／请求已收口时，保留旧页但不为其启动等待turn；程序仍持续观察 | 不标记旧页已消费、不销毁Team；Host待办、未知写入／回执、未确认控制、真实错误及用户输入继续可处理 |

“有任意观察页”并不等于写入、授权或控制不确定；保留原账本并在新线程重建当前事实，
已有请求／写入／授权检查继续保护实际安全。未直接删除这些检查，也未通过更多提示、
角色、轮次硬门或新恢复框架绕过失败。Delivery实际加载Skill同步说明接续与完成静止合同。

## 验证

新增组合回归先在旧实现复现5类失败，再验证修复，覆盖：

- 已知快照后的连续更新保持增量，完整未送变化不丢失。
- 大分页中阶段提示变化、进程恢复后的投影／引用／中文正文一致。
- 显式阶段申请与部分送达旧页、新状态同时存在时实际调用新线程；原队列身份和最新事实保留。
- 未知／尝试中原生送达、未知写入／请求、用户控制及既有安全守卫继续延后；新未送观察
  不会绕过已收输入尚缺最新yield的检查，最近已收身份沿原journal恢复。
- 原生循环中的完成后静止，以及新错误在下一次观察输入的当前摘要中可见。
- 完成后的Host待办、未结算请求、未知写入、未确认控制及未知原生送达继续处理。

定向最终结果：**103 passed**，6.30秒。
命令：从 `backend/` 执行 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest
../modeling_team/tests/test_delivery_paged_phase_handoff.py
../modeling_team/tests/test_delivery_phase_threads.py
../modeling_team/tests/test_delivery_token_reduction.py
../modeling_team/tests/test_delivery_decision_input.py -q --tb=short`。

共享Delivery核心最终全量：**3759 passed、12 skipped、318 subtests passed**，
573.37秒，359项warning，无失败，进程退出码0。命令为从`backend/`执行
`env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest ../modeling_team/tests -q --tb=short`。
此前两次全量分别在补齐新错误即时摘要与最近已收输入身份检查前主动中断，保留日志，
不把中断计为通过。最终全量和定向原件均在
`workspaces/delivery-paged-phase-repair-20261021/`。
Ruff、修改Skill的quick_validate、diff格式及文档本地链接检查通过；提交仅暂存本次
运行代码、两个测试文件、Delivery Skill及本记录，其他原有未提交文件保持。
GitNexus旧索引对当前阶段方法返回not found／UNKNOWN，使用直接调用点与相关回归补足，
不宣称取得完整图影响覆盖。

## 结论边界

本次证明确定性程序合同和安全边界的工程修复，不证明真实模型切换后的净token降幅、
完整任务10M达标或新独立语义验收。未重放原本轮的模型应用、冻结、验收或剩余金额；
保留原公开1／隐藏3的non-blind-regression通过及费用／用量历史。
只改modeling_team运行代码、测试和说明，不涉及backend／frontend应用代码或配置，
不需要重启ontology-platform.service；已存活的保留进程不视为已热加载新代码。
