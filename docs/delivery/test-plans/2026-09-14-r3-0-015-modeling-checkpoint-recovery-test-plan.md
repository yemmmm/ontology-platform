# R3.0-015 建模阶段检查点与恢复 — 共享测试计划

- 日期：2026-09-14
- 状态：设计与用例已形成；D0 文档自检，独立设计评审待执行；实现、独立功能验收、真实 L0/L1 均 NOT RUN。
- 需求：[R3.0-015](../../requirements/requirements-v3.0.md#r30-015-建模阶段检查点与恢复)
- 设计：[交付设计](../designs/2026-09-14-r3-0-015-modeling-checkpoint-recovery-design.md)

本文件是本需求唯一共享测试计划。后续各轮追加日期、实际代码基线、执行者、命令、结果和
证据路径；保留失败与修复历史。文档检查不证明实现或真实建模质量。

## 1. 证据分层

| 层级 | 验证目标 | 当前状态 |
| --- | --- | --- |
| D0 | 主代理核对需求/设计/源码依据、链接和格式 | 已完成，见 §6；不是独立评审 |
| D1 | 独立设计评审，重点核对 Session 幂等、审批迁移、尾部写入与 CQ 隔离 | 待执行 |
| M | 实现者功能自测和所需回归 | NOT RUN |
| I | 独立测试方从文件/进程/真实平台合同核实保存与恢复，不依赖实现者自报 | NOT RUN |
| L0 Runtime | 获准真实模型线程接续、复用前期成果、推进后续工作、零重复写入 | NOT RUN |
| L1 Modeling quality | 独立验收方判断源忠实度、语义/检索及所选验收范围 | NOT RUN |
| L2/L3 | 重复性、产品化 | 不作为本轮前置 |

## 2. 测试数据与隔离

- 使用临时 run root 和独立平台 fixture；至少两个逻辑切片/两个 Ontology，一个共享语义候选，
  含已批准与待确认值结论、公开/隐藏 CQ、已 applied Batch、未 applied plan 和 Evidence 关联。
- 保存源 run/检查点摘要，在恢复前后核对未被覆盖；源失败、丢回执、恢复事件和新报告分别保留。
- 独立功能测试至少一例真正结束旧 Runner 测试进程后用新进程读取持久化检查点，不能仅在同一
  Python 对象上调用 resume。Runtime 可以用受控替身，但必须标记不是真实供应商恢复。
- 平台关键用例使用现有真实服务/数据库 fixture 的 Batch、Attempt、Session 和 key 作用域，
  不能用全局内存 dict 的去重结果模拟跨 Session 正确性。
- 隐藏材料放唯一标记，用允许目录/文件挂载、角色启动 packet、消息、可见日志实际检查隔离。
  测试标记不得进入正式建模资料；不修改历史 run 或其平台资源。
- 真正 L1 的 Acceptance 不参与创建、继续或修复被验收 run；I 功能测试与 L1 独立性分开记录。

## 3. 保存与读取用例

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| M01 | CQ freeze 后保存 cq_frozen，拓扑尚未决定 | freeze/公开投影与审核依据一致；拓扑仍为待办，恢复不重复出题 |
| M02 | 仅切片 A 已批准，B 未完成；含 analyzed_not_materialized | 可保存 A，B/值确认保持 pending，不增加全场景完成门 |
| M03 | dry-run validated、翻译批准及 apply 完成分别保存 | 可区分阶段，dry-run 不记 applied；每个确定批次可保存 |
| M04 | production_handoff 保存 | 绑定 freeze/acceptance_target/模型与 Evidence 状态，不能凭 ready 布尔值保存 |
| M05 | 写文件中断、缺 manifest、坏 digest、保存期间文件变化 | 半包不可恢复；旧检查点保持可用；正常建模不被保存失败终止 |
| M06 | 同一 ID 重复请求、检查点已发布后源文件改变 | 不覆盖已发布包；同一完成事实可幂等返回；新内容形成新检查点 |
| M07 | apply/关联正在执行或存在 unknown 时请求保存 | 返回具体等待原因；不把在途状态包装成可恢复写入的快照 |
| M08 | inspect 无 ID、指定不存在/损坏 ID、检查点来源路径越界 | 列表或准确拒绝，无 Agent/平台写入；不默默换旧检查点 |
| M09 | 检查点原文含允许访谈、私有出题材料与旧 key 文件 | 只保存所需获准材料；secret 不进入包，私有答案和依据不进生产投影 |

## 4. 跨进程恢复与写入用例

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| M10 | 保存后正常退出旧 Runner，再启动新的生产恢复 | 新 run/thread/Transport，原 run/检查点不变；候选/CQ/批准未重新生成，实际推进后续步骤 |
| M11 | 新线程恢复阶段状态 | CQ freeze、拓扑、staged validator 和已完成范围重建；不恢复旧 gate open、消息队列、terminal 或旧 deadline |
| M12 | 原 run 存活、同机同时两次 resume、inspect 后源又写入 | 不产生两个活跃生产写者；resume 重读状态，已有读回不被当长期凭据 |
| M13 | 两 Ontology，A 已应用、B 待应用 | 全部精确 ID 保持；A 零重交，B 成功推进；不按名称再建 Ontology |
| M14 | checkpoint 后原 run 又 applied 一批才退出 | 对账尾部后该批也跳过；选择早 checkpoint 不回退平台或重交尾部 |
| M15 | apply 已提交成功但回执未落盘即退出 | 精确读回原 Session/key/Attempt/内容与资源后记录完成；新恢复证据保留回执缺失事实 |
| M16 | 原 Session 已结束，在新 Session 复用旧 key，或给已完成原计划换 Batch ID | 证明后端 key 不跨 Session 去重；计划来源映射和提交前索引阻止已完成原操作再次提交 |
| M17 | validated 但未 apply 的旧计划进入新 Session | 新 plan/client_batch_id/key，新真实 dry-run proof；不能拿旧 proof 直接 apply |
| M18 | failed_without_side_effects 且对账闭合 | 按 014 新 Batch 恢复；普通 failed/仅 safe_to_retry 不够 |
| M19 | unknown、部分写入、recovering、fence、读平台失败 | 写门 closed，可只读诊断；不靠重建 Runner/Session 或更早检查点放行 |
| M20 | 查不到原 Batch、分页截断、同 client ID 不同 Session/content | 不认定零写入或错误认领；完整分页和全身份匹配后才分类 |
| M21 | Batch applied、Evidence 关联一部分完成 | 只继续缺失关联；既有关联通过精确 readback 去重，unknown 关联仍阻塞写入 |
| M22 | 原 run 的 active Session/Lease 与无在途操作；另一个用户活跃会话 | 仅原所有权资源可按既有合同收尾；不抢占其它会话/强清 fence |
| M23 | 支持检查点的源 run 尚无正式语义资源即退出 | 原空 scope/成果保留、凭据撤销；恢复可复用 ID。旧流程已删 scope 则准确 scope_missing，零自动重建 |
| M24 | 恢复 cleanup/启动失败 | 源空/非空 scope 和原证据不删除；只清理本轮所有权资源，保留失败原因 |
| M25 | 恢复 run 再次退出后再恢复，存在同 ordinal 的新/旧 receipt | origin 链可核对，完成索引不重置；依赖按来源解析到正确资源，先前 applied 操作零重复 |
| M26 | 合法历史 Batch 导入；同时出现无法解释的外部 Batch/版本变化 | 继承历史不被误报绕过，外部变化不因 imports 被忽略；报告 scope_drift |

## 5. 审批、验收与授权用例

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| M27 | 业务内容/来源/决定/逻辑角色未变，只换 thread/run | 复用业务批准，保存原审批人和原版本；不伪造当前 Agent 重审 |
| M28 | 未执行计划只变恢复身份，新 dry-run 成功 | 精确比较内容与所有语义绑定后迁移翻译批准；当前 apply 检查新 proof 和迁移来源 |
| M29 | commands、candidate revision、identity_bindings、value traces、L3、业务决定之一改变 | 无法通过身份迁移；仅重审受影响内容，不重做未变阶段 |
| M30 | 任意外 run approved 文件、相同 coordinator 字符串、错误 origin、旧批准撤销 | 不被导入为有效批准；旧 checkpoint 不复活撤销决定；可修正冲突不杀正常源 run |
| M31 | 代码/提示窄修复与 schema/业务来源/模型选择变化 | 相关修复差异有证据可继续；不把 Git SHA 漂移当业务失效；不兼容项准确拒绝，不静默换合同 |
| M32 | CQ freeze/reviews/public 与历史曝光跨恢复 | 生产只得角色获准成果；隐藏正文/答案/依据不泄露；曝光并集不会被新线程清零 |
| M33 | 原 Producer 已退出，从 production_handoff 仅继续验收 | 新独立 attempt，原证据输入/新报告输出分离，零生产线程/写 Session，不需要死 FIFO |
| M34 | 旧验收 partial/fail/完整报告 | 重验保留旧结果与全题分母；完整可用报告仅核对收尾，不拼接不完整答案为新 PASS |
| M35 | 验收模型或 Evidence 绑定变化、pending/unknown 写入、生产角色仍写 | 拒绝使用旧 handoff，验收方不修模；保持独立验收边界 |
| M36 | cq_semantic/full_joint、隐藏答案、报告拒绝路径 | 冻结范围不变，不将 CQ PASS 报成完整验收；错误路径不泄露私有内容 |
| M37 | inspect/save、live resume、新生产恢复、acceptance-only | 分别按 0/沿用/1 次 fresh/非建模计数；宿主记录实际启动，无平台次数硬门 |
| M38 | 授权耗尽/收回、用户 stop 后检查点仍存在 | 允许查看；无新授权不得派发生产线程。恢复失败也不自动追加新 start |
| M39 | 未启用 selector 的普通 v3/旧 R2.3、既有 live/provider resume | 原入口/审批/清理合同保持，不能从无 checkpoint 的旧目录自动假造恢复能力 |
| M40 | 恢复耗时/token/结论输出 | 区分准备、语义、验收、供应商等待及 unavailable 用量；不虚报节省比例或语义 PASS |

## 6. 本轮记录及后续执行

### D0 — 2026-09-14 主代理需求与设计核对

- 输入代码基线：`ee8f531`。读取 Runner 创建/阶段/提交/交接、Session 幂等、scope 清理和
  CQ 持久化/隔离代码；只读检查，没有执行产品测试或调用平台写接口。
- 收敛关键合同：原线程存活走 006；新线程恢复关联原目标并按一次 fresh start 记账；
  原平台状态不回滚；恢复读入检查点后的写入；新 Session 不依赖旧 key 去重；翻译批准只能
  在语义内容未变且新 dry-run 成功时迁移；独立验收接续不唤醒 Producer。
- 用户本轮明确接受“新建角色线程，加载已保存的阶段成果继续”，已同步需求与设计。
- 文档检查通过：3 份文件的 24 个相对文件/锚点链接、Markdown 围栏和空白检查均无错误；
  M01–M40 共 40 项且无重复/缺号，四类 checkpoint 在需求与设计中齐全；`git diff --check`
  通过。源码/合同人工核对涵盖上述恢复边界；该层不包含独立设计评审或任何运行质量结论。
- 已知状态差异仅记录：012/014 正文头部与当前已有实现提交不同步；本轮没有扩展为其它
  需求状态修订，也未推定其验收 PASS。

### 后续功能与真实运行

实现后先执行改变模块的针对性测试和完整 Team 回归：

```bash
env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q
```

按修改范围运行现有 skill/合同 validator；若涉及 backend/UI，再执行 AGENTS.md 对应完整
测试与服务重启健康检查。D1/I 由独立执行者填写实际结果，不能复制 D0/M 自评。

真实 L0 使用明确的 R3.0-006 授权，提前把源生产与新线程接续需要的 start 消耗说明清楚；
可以复用已有有效检查点，不能擅自占用历史已撤销授权。最小证据为真实线程身份变化、同一
批准成果摘要、至少一个已完成阶段未重做、一个后续操作成功、已完成 Batch 零重复提交及
完整资源状态。另一条 acceptance-only 证据可直接使用有效生产交接，不强制多开生产 start。

L1 交独立验收方按冻结范围检查实际模型与检索；SQL、语义授权、RDF 业务行边界分别按
006/008B 报告。L0 恢复成功、单元测试或 imported approval 数量不能替代 L1；失败写入和旧
partial/fail 保留。用户授权后遵守 20 分钟 semantic start 要求，有效语义工作不足一半时
停止扩展平台/harness，报告原因并使用更短通路。
