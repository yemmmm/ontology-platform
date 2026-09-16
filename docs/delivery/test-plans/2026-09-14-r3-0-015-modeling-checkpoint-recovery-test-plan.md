# R3.0-015 建模阶段检查点与恢复 — 共享测试计划

- 日期：2026-09-14
- 状态：E1 已核验修订；D0/D1 已完成；M Rounds 1–5 与 I Round 1/Round 2 已记录——I 层对
  S1+S2+S4 范围 PASS（3 项错误通道缺陷修复后复测通过）。S3 按设计延后；真实 L0
  Round 1 为 PARTIAL（2026-09-15），L1 仍 NOT RUN。
- 需求：[R3.0-015](../../requirements/requirements-v3.0.md#r30-015-建模阶段检查点与恢复)
- 设计：[交付设计](../designs/2026-09-14-r3-0-015-modeling-checkpoint-recovery-design.md)

本文件是本需求唯一共享测试计划。后续各轮追加日期、实际代码基线、执行者、命令、结果和
证据路径；保留失败与修复历史。文档检查不证明实现或真实建模质量。

## 1. 证据分层

| 层级 | 验证目标 | 当前状态 |
| --- | --- | --- |
| D0 | 主代理核对需求/设计/源码依据、链接和格式 | 已完成，见 §6；不是独立评审 |
| E1 | 用户转交外部审阅，主代理核验并修订；见 §6 和账本依据 | 已处置，未声称外部复审 PASS |
| D1 | 独立专项复核，按下列用例索引核对权威内容身份、阶段接续、尾部写入与 CQ 隔离 | PASS（2026-09-14，S1+S2+S4 范围，见 §6 D1 轮） |
| M | 实现者功能自测和所需回归 | Rounds 1–5 完成（S1/S2/S4/缺陷修复轮），见 §6 |
| I | 独立测试方从文件/进程/真实平台合同核实保存与恢复，不依赖实现者自报 | Round 1 PASS（3 项 Medium/Low 缺陷）→ 修复（M Round 4/5）→ Round 2 PASS；见 §6 |
| L0 Runtime | 获准真实模型线程接续、复用前期成果、推进后续工作、零重复写入 | Round 1 PARTIAL（2026-09-15；S1/S2 与未 apply 通过，CQ/Acceptance 终态缺口；见下文） |
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
| M06 | 同一成果用相同/不同 ID 反复请求；保存事件自身变化 | 不覆盖包；按 kind/范围/成果/实际写入位置去重复用；时间戳和保存事件不能造成无限新包 |
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
| M23 | 源 run 尚无正式语义资源；有有效 checkpoint/待验 handoff，与仅 flag/保存失败对照 | 前者保留 scope/成果并撤钥，后者沿原空 scope 清理；旧流程已删 scope 则 scope_missing，零自动重建 |
| M24 | 恢复 cleanup/启动失败 | 源空/非空 scope 和原证据不删除；只清理本轮所有权资源，保留失败原因 |
| M25 | 恢复 run 再次退出后再恢复，存在同 ordinal 的新/旧 receipt | origin 链可核对，完成索引不重置；依赖按来源解析到正确资源，先前 applied 操作零重复 |
| M26 | 合法历史 Batch 导入；同时出现无法解释的外部 Batch/版本变化 | 继承历史不被误报绕过，外部变化不因 imports 被忽略；报告 scope_drift |

## 5. 审批、验收与授权用例

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| M27 | 业务内容/来源/决定/逻辑角色未变，只换 thread/run | 复用业务批准，保存原审批人和原版本；不伪造当前 Agent 重审 |
| M28 | S3：未执行计划只变恢复身份，新 dry-run 成功；默认值/集合顺序等价 | 用实际后端 `_content` 产生并正式读回的原/新 content_hash 与额外语义绑定判定，当前 apply 检查新 proof/来源；015 本地镜像不能自证 |
| M29 | S3：payload/证据/新输入字段，或 candidate/identity/value/L3/决定之一改变 | 后端内容变化或额外绑定变化均不能迁移；只重审当前受影响内容，镜像 hash 相等不能旁路 |
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

### E1 新增边界用例

| ID | 场景 | 必须观察到的结果 |
| --- | --- | --- |
| M41 | scenario_mapped：已确认访谈，切片/拓扑未定；或拓扑已批但 CQ 未冻结 | 两者均可保存并跨进程继续；不重做已确认访谈，CQ 已批准决定有效、未决仍未决，freeze 不自动产生 |
| M42 | 从未冻结 CQ 的检查点恢复草稿/审核、旧待回复消息 | CQ 私有材料仅 CQ/宿主可读，其他角色仅获批公开投影；已落盘审核复用，待回复用新绑定继续，不重播旧线程消息 |
| M43 | 最小完整对账预计/实际超过 20 分钟，或只初始化 Runtime | 对账计入准备；报告具体量/阻塞并请求明确延长，超时不扩大准备/不放宽写门，初始化不冒充 semantic-start |
| M44 | S2 已交付，S3 未交付；只有 S1 或 S4 已交付 | S2 用当前计划审阅安全继续，业务批准/多本体去重不缺席；S1 不声称可恢复，S4 不依赖 S3；未交付段准确列出 |
| M45 | 原 run 挂死，Lease 已到期但仍有 applying/recovering/fence | 只停可证明归属的写者；显示真实 expiry 与下次重查，不保证固定恢复时间；到期也不能清 fence/重交 |
| M46 | 原/新 Batch 无法精确读回、内容合同不兼容或原批准没有平台 Batch | S3 不自动迁移，回到当前计划审阅；不据本地 hash 放行或让整个 S2 永久失败 |
| M47 | 人工清理包：被活动恢复/验收引用，与无引用临时/废弃包对照 | 保留被依赖包/原失败证据；只在授权与精确所有权内清理，报告数量/大小，无自动 GC 或广域删除 |
| M48 | 上一段验证完成但语义有效时间不足一半 | 不自动推进下一平台/harness 段；记录时间并回到较短语义取证路径，不跳过当前安全对账义务 |

### D1 阅读索引与分段验收

| 评审入口 | 重点正文 | 用例 |
| --- | --- | --- |
| 前期成果、CQ 部分状态与隔离 | 设计 §3.1、§4.2、§7 | M01/M09/M32/M41/M42 |
| 最重要的迁移判断：后端权威内容 + 额外语义绑定 | 设计 §6.1–6.2 | M27–M31/M46 |
| 原/新 Session、尾部与多 Ontology 去重 | 设计 §5 | M13–M26 |
| 20 分钟与挂死处理 | 设计 §4.3、§5.2、§8 | M12/M22/M37/M38/M43/M45 |
| 保留、去重和可停点 | 设计 §3.3–3.4、§9 | M05–M07/M23/M24/M44/M47/M48 |
| 独立验收接续 | 设计 §7 | M33–M36 |

S1 执行保存/inspect/保留/隔离相关用例及 M41/M42 中的序列化读取部分，不能把它记作
跨进程语义接续通过。S2 执行生产恢复、业务批准和所有写入安全用例；M28/M29/M46 的
自动迁移分支归 S3，S2 必须证明正常翻译审阅回退。S4 单独执行 M33–M36 与其隔离/资源
前置。每段独立记录范围、未执行用例与结论，不能把延期段填 PASS。

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

### E1 — 2026-09-14 外部意见核验与修订

用户转交外部 Agent 的 9 点意见；原意见未给出正式 PASS/REVISE verdict。主代理对照
`375eec6`、平台 `_content`/Batch detail、Session/Lease 合同和
[账本核验记录](../records/2026-09-14-r3-0-015-review-evidence.md)处置如下。
这里记录修订，不代替独立 D1 复审；D0 历史检查数字不追溯改写。

| 意见 | 判断与处置 |
| --- | --- |
| 1 前期阶段缺口 | 采纳，新增 scenario_mapped；同时不接受拓扑必在 CQ 前的隐含顺序，支持任一已发布前期成果 |
| 2 P1 与投入 | 采纳账本对照和独立可停点；3 组新运行不等于 3 次可避免重做。业务批准核对/多本体去重留在 S2；S3 延后可用正常计划审阅回退，S4 已有 auth012 现实需求 |
| 3 20 分钟 | 采纳规则澄清；完整窄对账计入准备，超时须申请明确延长。不采纳空建线程或为守时新增只读生产启动路径 |
| 4 审批迁移 | 采纳单一权威内容来源：读回后端自己计算的原/新 Batch content_hash，不在 015 重写比较器；额外绑定仍独立核对，D1 优先看 M28/M29/M46 |
| 5 挂死运维 | 采纳，补受控 stop、实际 expires_at/下次重查和无在途/fence 判定；不承诺租约到期即恢复 |
| 6 保留增长 | 采纳已发布有效 checkpoint/待验 handoff 引用才保留空 scope；补数量/大小和精确人工清理步骤。真实新成果的增长保留为明确限制 |
| 7 频控 | 不加频率硬门；强化同内容跨请求 ID 去重，排除保存事件自触发。没有证据要求限流服务 |
| 8 文档债 | 核实成立；独立小提交同步 012/014 当前状态，保留历史测试/失败边界，不补造独立 PASS |
| 9 可读性 | 采纳，补 D1 用例索引、条件分项和分段验收入口 |

本轮文档检查通过：四份 015 文档（新增账本依据）共 29 个文件/锚点链接，M01–M48 共
48 个唯一用例，五类 kind 在正文/设计一致，围栏与 diff 空白无错误。源码/合同人工核对及
9 项意见处置已记录；没有运行产品测试、服务重启、建模或恢复实验。

### D1 — 2026-09-14 独立专项复核（S1+S2+S4 交付范围）

- 执行者：独立 plan_reviewer 代理（只读；主代理仅记录其结论，未参与评审）。输入代码基线：
  `ae70547`；`modeling_team/`、`backend/` 与设计基线 `ee8f531` 一致，设计 §2 代码事实可直接核对。
- 结论：**PASS**（针对本轮交付范围 S1+S2+S4；S3 按设计延后）。无 Critical/High 发现。
- 设计 §2 代码事实表逐行核对全部属实，含 file:line 证据：prepare 拒绝已有目录与 state.json
  覆盖写；`(build_session_id, client_batch_id)` 键与 Attempt 幂等的 Session 作用域，非 active
  Session 先拒绝；`_existing` 单 Ontology 绑定与 active Session/Lease/Attempt/fence 前置；
  `_content`/`get_modeling_batch` 权威 content_hash 读回（HTTP 与 MCP 同源）及逐 item
  `client_item_id/resource_outputs/evidence_reference_ids/evidence_association_ids`；
  `list_session_modeling_batches`/`list_ontology_modeling_batches` 游标分页；cq-acceptance
  当前将证据输入与新报告输出耦合在 `args.run_root`；生产角色仅挂载
  `competency-questions/public`，`frozen/`、`hidden-batch/`、`reports/` 不挂载；验收入口已
  报告 `consumes_semantic_start: false`。需求与设计在五类 kind、恢复记账、空 scope 保留、
  非目标四方面一致；S3 延后合法且 S2 可回退（`unified_approval_issue` 不依赖审批者身份，
  `unified_translation_issue` 绑定当前 Coordinator/计划）。
- 低于阈值提示 2 条（不改设计合同，作为实现约束带入开发交接）：
  1. `build_sessions.py` 的 `platform_state.modeling_batches`（截 20 条）与 session detail
     （截 50 条）是无游标便捷视图；完成索引必须遍历游标分页端点，不得建在截断视图上（M20 相关）。
  2. `CQWriteAdmission` 阶段单向（open→quiescing→read-only）；§3.3.2 保存期短暂阻止本 run
     写请求不能复用 `begin_quiescing`，需小型可逆 admission barrier。
- 非阻塞假设处置：保存拷贝按 §3.3 做 digest 复查（M05 覆盖）；resume CLI 沿用 `run` 的宿主
  凭据引导并在缺失时准确报错；`modeling_checkpoints: true` 经新 v3 Task `parameters` 块 +
  `contracts.py` 依赖约束实现，符合设计 §9。
- 本轮无代码、测试或运行变化；M/I/L0/L1 状态不变。

### M — Round 1 — 2026-09-14 开发自测（S1 范围）

- 执行者：开发代理（requirement developer）。代码基线：`ae70547` 工作区（S1 实现未提交：
  `modeling_team/checkpoints.py` 新增，`runner.py`/`__main__.py`/`contracts.py`/
  `platform_scope.py`/`tasks/r3-0-015-checkpoint-recovery.yaml`/`skills/modeling-dev-loop/`
  修改）。范围仅为 S1 保存/检查（M01–M09、M23、M41/M42 只读部分、M44 S1 侧、M47 列表）；
  未实现 resume，S2/S4 未交付。
- 命令与结果：

  ```bash
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest \
    modeling_team/tests/test_r30015_checkpoints.py -q
  # 50 passed
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q
  # 1747 passed, 1 skipped, 331 subtests passed in 105.06s
  # （基线 1697 passed + 新增 50 = 1747，无回归）
  ```

  ruff（100 列）对新增/修改文件通过；`runner.py` 保留 4 个与 HEAD 相同的既有
  F401/F841 发现。GitNexus `detect-changes --repo ontology-platform`：11 文件/54 符号/
  5 流程，medium——变更符号均在 S1 预期面（main/prepare/load_task/checkpoint 新码），
  文档差异来自主代理未提交编辑。
- 开发自测发现并已修复的实现缺陷 2 项（先失败后修）：`CHECKPOINT_EVIDENCE_NAME` 带扩展名
  导致证据落成 `checkpoints.jsonl.jsonl`；checkpoint id 模式未允许下划线而拒绝自身生成的
  `cq_frozen-0001` 形 id。修复后全绿。
- 证据路径：`modeling_team/tests/test_r30015_checkpoints.py`（用例↔编号映射见其文件内
  分节注释：module 层 M05/M06/M08/M09/M44/M47、contracts 层 selector 门、runner 层
  M01/M02/M03/M04/M07/M41、D1 可逆 barrier、M23 scope 保留、CLI 层 M08）；运行时证据
  均在 pytest 临时 run root 内产生并随测试清理，未落正式 `workspaces/modeling-runs/`。
- Controlled Runtime stand-in：`CapturingAdapter`（复用既有测试替身，非真实 provider）；
  本轮无真实 LLM/平台写入/服务重启。M 层自评不代表 I/D1/L0 状态。

### M — Round 2 — 2026-09-14 开发自测（S2 范围）

- 执行者：开发代理（requirement developer）。代码基线：`ae70547` 工作区（S1 未提交基础上
  追加 S2，均未提交）。新增 `modeling_team/checkpoint_recovery.py` 与
  `modeling_team/tests/test_r30015_resume.py`；修改 `runner.py`（`prepare_from_checkpoint`
  与恢复物化）、`__main__.py`（`checkpoint resume` CLI）、`platform_scope.py`（checkpoint
  绑定模式与 inherited-retained 清理）、`skills/modeling-dev-loop/`（SKILL.md 与 runbook
  增 S2 宿主操作）。范围仅 S2（§2 硬性要求两条、D1 约束 1、M10–M26、M27、M30–M32、
  M37–M40、M43、M45、M44 S2 侧）；S3 自动迁移、S4 acceptance 续跑仍按边界不交付
  （acceptance 请求得到准确的 `acceptance_continuation_not_delivered` 类型化拒绝）。
- 命令与结果：

  ```bash
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest \
    modeling_team/tests/test_r30015_resume.py -q
  # 26 passed in 1.71s
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q
  # 1773 passed, 1 skipped, 331 subtests passed in 108.44s
  # （Round 1 基线 1747 + 新增 26 = 1773，无回归）
  ```

  ruff（100 列）：新增/修改文件全部通过，仅 `runner.py` 保留 4 个与 HEAD `ae70547`
  完全相同的既有发现（F401×3、F841×1；行号因新增 import 整体 +1），未扩大。
  GitNexus `detect-changes --repo ontology-platform`：11 文件/83 符号/9 流程，high——
  变更符号均在 S1+S2 预期面（`main`/`prepare`/CLI 恢复入口、文档为主代理未提交编辑）；
  untracked 新文件不进 diff-hunk 映射，故 checkpoint_recovery.py 符号未计入该计数。
- §2 硬性要求 1（真实进程边界）：
  `test_s2_real_process_boundary_resume_from_a_terminated_runner`——子进程是真实
  `TeamRunner`（仅模型 provider 用 `CapturingAdapter` 替身，已在文件头声明），
  prepare→CQ 冻结→写原生 exposure 记录→cleanup→`os._exit(0)` 终止；本 pytest 进程
  作为全新 OS 进程从磁盘持久化检查点恢复：recovery 目录 0600、origin/imports/inspection
  内容、冻结池 digest 与子进程打印一致（经 `reload_frozen_pool` 重校验）、
  exposure union 进入恢复 Runner 的实际暴露状态、validators 重算且布尔 gate-open 未还原。
- §2 硬性要求 2（真实服务/DB fixture）：
  `test_m16_real_service_keys_do_not_dedupe_across_sessions_and_the_index_blocks`——
  真实 `ModelingBatchService`/`BuildSessionService` 跑在内存 SQLite（StaticPool，复用
  test_p2a fixture 模式），无全局 dict 去重：同一 client_batch_id+idempotency_key 换新
  Build Session 是全新 Batch（后端幂等键按 Session 作用域），对账回读全部经真实服务
  方法，预提交屏障同时拒绝已完成操作与真实第二 Session 产生的重复 Batch。
- D1 约束 1 证明：对账只读 `GET /api/build-sessions/{id}/modeling-batches`、
  `GET /api/ontologies/{id}/modeling-batches`（limit≤100 + next_cursor 逐页）与
  `GET /api/modeling-batches/{batch_id}`；`FakeCursorPlatform` 把一切越界路径记入
  `unexpected`（断言为空），并断言 `platform_state`/session 详情截断视图从未被读；
  多页遍历以 pages_read/batches_read 计数验证（250+150 条）。
- 开发自测发现并已修复的集成缺陷 6 项（均先失败后修）：裸 `apply` 模式与真实 REST
  模式族（dry_run/apply_atomic/apply_partial）不匹配；`state.json` 实际键为 `state`
  （误读 `status` 致活写者检测永不触发）；冻结池恢复误把存储记录当冻结输入（改经
  `reload_frozen_pool` 重校验）；exposure union 曾写入非原生记录（`read_exposure_evidence`
  会拒绝，改写原生 `question-exposed-to-production` 行并标记来源 run）；合同文件按
  逻辑 id 解析（`r3-0-011` → `r3-0-011-competency-question.yaml`，快照 digest 优先）；
  恢复覆盖 prepare 生成的只读 staged 文件前先 unlink。
- 证据路径：`modeling_team/tests/test_r30015_resume.py`（用例↔编号映射见其文件内分节
  注释：D1×2、M19、M21/M26、M14/M25、M16、M12、M22/M45、M27、M30、M17、M31、M32、
  M10/M39、M40×2、M37/M38、M43、M44-S2×3、M10 新 run id、M13/M23、M24、M11、真实进程
  边界×1、M44 交付边界×1）；运行时证据均在 pytest 临时 run root 内产生并随测试清理，
  未落正式 `workspaces/modeling-runs/`。未遇到需按 design §9 上报的后端接口缺口
  （M16 真实服务证据即为其结论）。M 层自评不代表 I/D1/L0 状态。

### M — Round 3 — 2026-09-14 开发自测（S4 范围）

- 执行者：开发代理（requirement developer）。代码基线：`ae70547` 工作区（S1+S2 未提交
  基础上追加 S4，均未提交）。新增 `modeling_team/tests/test_r30015_acceptance.py`；修改
  `modeling_team/checkpoint_recovery.py`（S4 准备/复核、attempt 分配、origin/收尾记录）、
  `modeling_team/__main__.py`（`checkpoint resume --mode acceptance` 实装入口、
  `_cq_consume_production_handoff`/`_cq_execute_batch` 续跑输入/输出分离参数）、
  `skills/modeling-dev-loop/`（SKILL.md 标题扩为 S1+S2+S4 并增 S4 段、runbook 增
  “验收续跑（R3.0-015 S4）”节并改写 acceptance 占位拒绝描述）。范围仅 S4（design §7
  三段、M33–M37、M44 S4 侧与 handoff/kind 前置行）；S3 自动迁移按设计不交付，S4 不依赖
  S3。原 `acceptance_continuation_not_delivered` 占位拒绝已被真实实现替换
  （`checkpoints.py`/`test_r30015_*` 中 S4 交付标记此前已按交付边界置 delivered）。
- 命令与结果：

  ```bash
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest \
    modeling_team/tests/test_r30015_acceptance.py -q
  # 7 passed（首跑 4 failed，缺陷见下，修复后通过）
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest \
    modeling_team/tests/test_r30015_checkpoints.py \
    modeling_team/tests/test_r30015_resume.py \
    modeling_team/tests/test_r30015_acceptance.py -q
  # 83 passed in 4.76s
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q
  # 1780 passed, 1 skipped, 331 subtests passed in 109.44s
  # （Round 2 基线 1773 + 新增 7 = 1780，无回归）
  ```

  ruff（100 列）：新增/修改文件全部通过，仅 `runner.py` 保留与 `ae70547` 相同的 4 个
  既有发现（F401×3、F841×1），未扩大。GitNexus `detect-changes --repo
  ontology-platform`：11 文件/92 符号/9 流程，high——变更符号均在 S1+S2+S4 预期面
  （`main`/`_run_cq_acceptance`/`_cq_consume_production_handoff`/`_cq_execute_batch`/
  文档为主代理未提交编辑）；untracked 新文件不进 diff-hunk 映射。
- §2 硬性要求 1（真实进程边界，M33）：
  `test_m33_real_cli_continuation_with_the_producer_process_gone`——子进程是真实
  `TeamRunner`（仅模型 provider 用 `CapturingAdapter` 替身，文件头已声明），
  prepare（含 project/ontology scope 绑定）→CQ 冻结→写 staged sources→`cq_handoff_complete`
  发布真实 handoff + 自动 production_handoff 检查点→cleanup→`os._exit(0)` 终止；随后
  两次**真实 CLI 子进程**（`python -m modeling_team checkpoint resume --mode acceptance`）
  完成续跑，平台读只经本地 HTTP stand-in 的 cursor 分页只读端点（全部请求记录断言：
  仅 GET、仅三类只读路径族——零写会话、零生产线程、零死 FIFO 依赖）。第一次 CLI 在无
  `R3011_ACCEPTANCE_PLATFORM_READ_KEY` 下准确 exit 2，收尾记录落输出根
  （`mode: re-executed`/`no-report`），源 run 树 mtime/size 快照逐字节不变；补齐完整
  PASS 报告后第二次 CLI 走 `verification-only-closing`（0 次模型会话、0 次语义开始），
  源 run 与其报告字节再次断言不变，attempt 分配跨源 run 与首个输出根（prior
  attempt-0001，新 attempt-0002）。
- M33–M36 映射（同文件）：M34×2
  （`test_m34_complete_pass_report_means_verification_only_closing` 断言 `_run_cq_acceptance`
  不可触达 + 0 会话/0 start/源树不变；`test_m34_prior_partial_report_is_preserved_and_never_spliced`
  断言判定包携带全分母、旧 partial 字节原样、平台读留存只落输出根、异摘要 full-pass
  报告不可用）；M35×7 场景（冻结池篡改/损坏、发布 handoff 漂移、未结算 staged 写、
  unknown 链写、活写者、平台 scope drift，全部带 §8 五元组且不含隐藏题面/密钥）；M36
  （冻结池经实际 `freeze-NNNN.json` 摘要重校验、`acceptance_target` 不变、hidden 计数、
  检查/origin 无 `placeholder` 题面、readback 仅 cursor 路径族）；M37
  （`semantic_starts: 0`/`consumes_semantic_start: false`、独立尝试挂靠源 run、
  跨根 attempt 空位补齐、准备时间预算单列）；前置行（非 handoff kind →
  `checkpoint_kind_mode_mismatch`、已发布 handoff 缺失/包内副本缺失 →
  `checkpoint_incomplete`、new-run id 占用 → `resume_new_run_exists`）。
- 开发自测发现并已修复的实现缺陷 3 项（均先失败后修）：冻结池定位误按 handoff
  `freeze_id`（批次 id）拼文件名（Runner 实存 `freeze-NNNN.json`），改为按 batch+摘要
  对源 run 存储快照扫描重校验并回传文件路径（CLI `--freeze-id` 传文件 stem）；续跑
  mapping 内嵌 `Path` 导致执行路径 stdout JSON 序列化 TypeError（改 POSIX 字符串、
  消费点 `Path()` 回包）；S4 入口的包内产物摘要拒绝沿用了 S2 的
  `checkpoint-resume` phase（§8 要求 phase 标识入口，`_verify_packaged_digests` 增
  phase 参数）。另有一处测试侧对齐：M33 真实子进程冻结批次改用 `batch-r3011`，
  因复用的 r3012 Examiner/Judge 开发替身把该批次 id 硬编码进报告封套（替身约束，
  非产品约束，测试内已注明）。
- 证据路径：`modeling_team/tests/test_r30015_acceptance.py`（用例↔编号映射见其文件内
  分节注释与 §2 替身声明：FakeCursorPlatform/DualForwarder/_batch_adapter 为受控
  Runtime 替身非真实 provider，真实进程边界用例如上）；运行时证据均在 pytest 临时 run
  root 内产生并随测试清理，未遗留正式 `workspaces/modeling-runs/`。未遇到需按 design
  §9 上报的后端接口缺口（S4 只复用既有 cursor 只读端点与 cq-acceptance 执行路径，
  未新增产品 HTTP/MCP API、无后端迁移）。M 层自评不代表 I/D1/L0 状态。

### I — Round 1 — 2026-09-14 独立功能测试（S1+S2+S4 范围）

- 执行者：独立 requirement-tester 代理（不依赖 M 层自报；未改任何产品代码，本轮唯一仓库写入
  即本记录）。代码基线：`ae70547` 工作区（S1+S2+S4 实现未提交），tracked-diff digest 与
  主代理交接一致，无 stash。
- 结论：**PASS（S1/S2/S4 分段均 PASS；2 Medium + 1 Low 缺陷，均不影响失败关闭、数据
  完整或隔离；S3 按设计延后，未发现其被实现或被宣传）**。
- 基线命令与结果（独立复跑，与 M Round 3 自报一致）：

  ```bash
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q
  # 1780 passed, 1 skipped, 331 subtests passed in 109.47s, exit 0
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest \
    modeling_team/tests/test_r30015_checkpoints.py \
    modeling_team/tests/test_r30015_resume.py \
    modeling_team/tests/test_r30015_acceptance.py -q
  # 83 passed, exit 0（50+26+7）
  ```

- 独立探针（一次性脚本置于 /tmp/r3015_iprobes，测后已按清理规则删除，未进仓库；证据为
  下述命令输出摘录与套件）：
  1. 保存进程探针（独立进程调用真实 `save_checkpoint`，随后 `os._exit(0)`）：M06 去重
     成立——同内容换 request_id 复用同一包（`cq_frozen-0001` manifest 摘要不变），内容
     变化新开 `cq_frozen-0002` 且旧包不动；`secrets/` 来源类型化拒绝
     `checkpoint_invalid_source`（retryable=false）、symlink 来源 `checkpoint_unavailable`
     （retryable=true），均为 §8 风格元组；secrets 文件零入包（`checkpoints/` 全树 grep
     0 命中）。
  2. CLI 黑盒（9 次真实子进程 `checkpoint inspect`，另含无凭据共 10 次）：缺
     `ONTOLOGY_PLATFORM_ADMIN_API_KEY` exit 2 准确报错；列表列出 3 个已发布包（人工半包
     不列出，含 cumulative_size_bytes）；有效包 status ready 且
     `estimated_authorization_consumption.production_resume_semantic_starts:1`、
     `consumes_semantic_start:false`、`delivery_segments.s3_translation_approval_migration:
     deferred_by_design`；篡改包仍按所请求 id 检视、status `incompatible` 并给出
     "packaged artifact 'evidence/stage.json' digest mismatch"，不默默替换；不存在 id /
     半包 / checkpoint-id 路径越界 / run-id 路径越界 / 未知 run 全部 exit 2 且 stderr 为
     类型化 JSON（`checkpoint_not_found` / `checkpoint_invalid_id`）。
     唯一隐藏标记 `I_PROBE_HIDDEN_MARKER_*` 仅出现在 host-private 侧与源 run 原始访谈/
     冻结文件；artifacts 公共侧 0 命中，全部 CLI stdout/stderr 0 命中；9 次 inspect 前后
     源 run 全树逐文件 sha256 一致（严格只读）。
  3. S2/S4 CLI 黑盒与跨进程锁（真实 CLI 子进程 + 独立持锁进程持有 flock）：
     production 模式 + 篡改包 → exit 2 类型化 `artifact_changed`（digest 校验先于任何
     平台调用，base-url 指向不可达端口亦可复现）；production + 已占用 new-run-id →
     exit 2 类型化 `resume_new_run_exists`；acceptance + 非 handoff kind → exit 2
     类型化 `checkpoint_kind_mode_mismatch`（phase=checkpoint-resume-acceptance）。
     M12：持锁进程存活时 production resume exit 2 拒绝（"another production resume
     holds the resume lock for this root run on this machine"），acceptance resume
     **exit 1 未捕获 traceback**（缺陷 D2a，见下）；持锁进程被 kill 后同一 acceptance
     命令通过锁并到达类型化 kind 拒绝——单写者与内核释放均跨进程证实；全部 resume 尝试
     后源 run 全树字节不变，且未创建任何新 run 目录。
  4. M39 selector 探针（真实 `load_task`）：r3-0-015 yaml（五选择器）加载通过；仅去掉
     `unified_semantic_graph` → `TeamConfigurationError: modeling_checkpoints requires
     unified_semantic_graph`；9 个无 parameters 块的旧任务加载不变，叠加全量回归 1780
     通过。
- §2 硬性要求核验：跨进程（探针 2/3 均为真实多进程；另读证 M 层真实子 Runner
  `os._exit(0)` 与 M33 真实 CLI 子进程用例）；真实服务/DB（M16 用例跑真实
  ModelingBatchService/BuildSessionService over SQLite，随套件执行，无全局 dict 去重）；
  隐藏材料（标记经允许目录、包公共侧与全部 CLI 输出三向核查，另 M 层挂载/packet 用例）；
  无历史修改/无残留（源 run 树摘要三次比对一致；探针 run 目录、占用目录与
  `.recovery-locks/<run>.lock` 测后删除，modeling-runs 目录数复原、锁目录清空，
  台账 mtime 未动，git status 与交接一致）。
- 分段结论：
  - S1 PASS：M01–M09（套件 50 用例 + 探针 1/2 独立复核）；M41/M42 序列化读取部分、
    M23 源侧、M47 列表/大小、M44-S1（CLI/文档/help 不越权，S3 列为 deferred）。
  - S2 PASS：M10（不覆盖已存在 new-run-id）、M12（单写者 + 内核释放）、M37/M38（凭据
    缺失 fail-closed；记账 host-recorded、无平台次数硬门）经 CLI/进程级独立证实；
    M13–M26、M27、M30–M32、M40、M43、M45 经套件真实服务 fixture 执行 + 代码核对
    （未另行独立场景重放，见未执行清单）；M44-S2（S3 回退路径存在，
    checkpoint_recovery.py:1308）。
  - S4 PASS：M33 前置（kind 门、真实 CLI 通道）、M34/M35/M36/M37 经套件真实 CLI 子进程
    用例 + 本轮 kind/mismatch 探针；M44-S4（acceptance 仅限 production_handoff）。
- 缺陷（均已实际复现，附 file:line 证据）：
  - **D2（Medium）— 并发恢复锁拒绝未按 §8 类型化送达**：acceptance 模式下
    `_run_checkpoint_resume_acceptance` 于 `modeling_team/__main__.py:2745` 早于 main
    守护区返回，其锁获取 `acquire_root_run_lock`（`__main__.py:2409`）又在函数内类型化
    catch 之外，`checkpoint_recovery.py:198` 构造的类型化 CheckpointError
    （source_active + retry 五元组）以未捕获 traceback 崩出，exit 1 而非约定 exit 2；
    production 模式则落入 `__main__.py:3138` 通用通道，仅输出 "run failed: ..." 文本。
    复现：独立进程持 RootRunLock 后分别运行两种模式 `checkpoint resume`。两种模式均
    失败关闭、单写者成立；但 runbook:316 承诺的类型化五元组（source_active/next_action）
    从未经 CLI 送达。
  - **D1（Medium）— 宣传的 `scope_missing` 类型化拒绝不可达**：
    `REASON_SCOPE_MISSING`（`checkpoint_recovery.py:88` 定义、:2444 再导出）零使用；
    真实缺 scope 路径抛 `PlatformScopeMissingError`（`platform_scope.py:16`，RuntimeError
    子类）→ 经 `__main__.py:3138` 通用通道输出 "run failed: checkpoint scope resources
    are missing: ..."（exit 2）。runbook:316 将 `scope_missing` 列为可交付类型化码。
    失败关闭与"零自动重建空白 scope"仍成立（代码核对）。
  - **D3（Low）— §8 字段命名与设计/文档不一致**：design:381 与 runbook 规定
    `code/object_ref/phase/retryable/reason/next_action`；实现实际输出
    `reason_code/detail/object/phase/retryable/retry`（六义齐备、键名不符；本轮全部
    CLI 类型化输出均可复现）。按文档键名解析的宿主将读不到任何字段。
- 未执行：真实 L0/L1（按计划非本轮）；真实后端服务端到端 production resume（任务约定
  不重启服务——对账/写尾/审批复用行为以真实服务 fixture 套件 + 代码核对为准）；
  M13–M26、M27、M30–M32、M43、M45 未做独立场景重放（证据层=套件执行+代码审读，已在
  分段结论注明）；M28/M29/M46（S3 自动迁移分支，按设计不交付，核实未实现且未宣传）。
- 残留风险：宿主自动化若按 exit 2 + JSON 解析恢复拒绝，会把 acceptance 锁竞争（D2a，
  exit 1 traceback）误判为进程异常崩溃；D1/D3 使 §8 错误通道在两条路径上不可机读。
- 建议：交需求开发 agent 修复 D1/D2（锁获取纳入类型化 catch 并统一 exit 2；为
  `PlatformScopeMissingError` 落 §8 转换或修订 runbook 宣传），并对 D3 统一 §8 字段名；
  修复后 I Round 2 仅窄复测上述通道与受影响回归。

### M — Round 4 — 2026-09-14 修复轮（I — Round 1 确认缺陷 D1/D2/D3）

- 执行者：开发代理（requirement developer）。代码基线：`ae70547` 工作区（S1+S2+S4 未提交基础上
  修复，均未提交）。范围仅独立测试 I — Round 1 确认的 3 个错误输出通道缺陷；单写者与
  fail-closed 行为、非 resume 调用方的平台异常语义均保持不变。每项先写失败复现再修。
- **D2（root-run 锁冲突逃出 §8 通道）**：`__main__.py` 两处锁获取原来不在任何类型化 catch
  内——acceptance 模式未捕获 traceback、exit 1；production 模式落到普通 `run failed:` 文本。
  修复：acceptance 入口（`_run_checkpoint_resume_acceptance`）与 production 入口的
  `checkpoint_root_run_id` + `acquire_root_run_lock` 各自包进 CheckpointError 类型化处理，
  输出 §8 元组、exit 2。回归：`test_d2_acceptance_lock_conflict_is_a_typed_cli_rejection_no_
  traceback`（本进程真实持有 flock，真实 CLI 子进程 → exit 2、`source_active`、无 Traceback、
  拒绝发生在任何输出根工作之前）与 `test_d2_production_lock_conflict_is_a_typed_rejection_
  exit_2`（进程内第二次获取真实冲突 → 同一元组）。
- **D1（`scope_missing` 类型化拒绝不可达）**：缺 scope 资源时 `PlatformScopeMissingError`
  （RuntimeError 族）走通用失败通道，runbook/design 承诺的 `scope_missing` 代码从未出现。
  修复：`checkpoint_recovery.py` 新增 `scope_missing_rejection()`（`REASON_SCOPE_MISSING`、
  `object_ref=scope_binding`、retryable、含恢复指引；不造空白 scope 的语义不变）；
  `__main__.py` 运行流在通用 `(OSError, ValueError, RuntimeError, ...)` 捕获**之前**新增
  `except PlatformScopeMissingError`，仅 `resume_requested` 时转类型化 exit 2（含 handoff
  失败记录、cleanup、ledger 结算），非 resume 调用方原样 re-raise。回归：
  `test_d1_missing_scope_is_a_typed_rejection_exit_2`（终止 Runner 子进程产出的可物化
  检查点 + 真实 `PlatformScopeMissingError` 在 scope 接缝抛出 → exit 2、`scope_missing`
  元组、新 run 状态非运行态）。
- **D3（§8 字段名不符）**：实现输出 `reason_code/detail/object/phase/retryable/retry`，
  设计 §8 与 runbook 规定 `code/object_ref/phase/retryable/reason/next_action`。修复：
  `checkpoints.py` `CheckpointError.data()` 改按 §8 名称投影（六语义不变，`next_action`
  仅在有指引时随行；异常内部属性与其它异常类不受影响，runner 侧 checkpoint-save-failed
  证据记录随 `.data()` 一并对齐）。受影响断言已更新（test_r30015_checkpoints 2 处、
  test_r30015_resume 1 处、test_r30015_acceptance 全部 payload 断言经
  `_assert_public_rejection` 强制精确键集并断言无旧名残留）。
- 命令与结果：

  ```bash
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest \
    modeling_team/tests/test_r30015_checkpoints.py \
    modeling_team/tests/test_r30015_resume.py \
    modeling_team/tests/test_r30015_acceptance.py -q
  # 86 passed in 5.61s（修复前新增 3 个回归用例分别以 exit 1 traceback、
  # 'run failed: another production resume holds...'、旧键名 KeyError 失败）
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q
  # 1783 passed, 1 skipped, 331 subtests passed in 110.55s
  # （Round 3 基线 1780 + 新增 3 = 1783，无回归）
  ```

  ruff（100 列）：全部新增/修改文件通过。运行时证据在 pytest 临时 run root 内产生并随测试
  清理（含 `.recovery-locks/` 测试锁文件），无遗留。M 层自评不代表 I/D1/L0 状态。

### I — Round 2 — 2026-09-14 独立复测（缺陷修复轮）

- 执行者：独立 requirement-tester 代理（未改任何产品代码；本轮唯一仓库写入即本
  记录）。工作区：仍为 `ae70547` 未提交实现，无 stash；本轮 tracked-diff sha256
  前缀 `01f649cbb1daf0e8`（I Round 1 后开发已修改同一工作区）。
- 结论：**PASS。D1 FIXED、D2 FIXED、D3 FIXED；未发现新的 Critical/High/Medium
  缺陷；I 层对 S1+S2+S4 范围通过。**（1 条 Low 观察项，见末尾。）
- 基线命令与结果（独立复跑，与开发自报一致）：

  ```bash
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q
  # 1783 passed, 1 skipped, 331 subtests passed in 110.52s, exit 0
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest \
    modeling_team/tests/test_r30015_checkpoints.py \
    modeling_team/tests/test_r30015_resume.py \
    modeling_team/tests/test_r30015_acceptance.py -q
  # 86 passed in 5.64s（Round 1 为 83，新增 3 条缺陷回归）
  ```

- 独立探针（真实子进程，/tmp/r3015_iprobes2，测后已删；两处数据点因探针自身的
  间歇导入问题改用 `env -i` 干净环境手工执行——为我的测试装置问题，与产品无关，
  下同）：
  - **D2（两模式锁竞争）FIXED**：独立持锁进程持有 RootRunLock（真实 flock），
    另起真实 CLI 子进程分别以 `--mode acceptance` 与 `--mode production` resume：
    两者均 exit 2、stderr 恰一行 `checkpoint failed: {…}`、`code=source_active`、
    `retryable=true`、键集合恰为 `code/object_ref/phase/retryable/reason/next_action`
    六键、reason 含 "resume lock"、无任何 Traceback（Round 1 acceptance 为 exit 1
    未捕获 traceback、production 为无类型 "run failed:" 文本）。拒绝发生在任何
    输出目录创建之前（新 run 目录不存在）。
  - **D2（checkpoint_root_run_id 包裹）FIXED**：acceptance 模式 + 不存在的
    checkpoint id → exit 2 类型化 `checkpoint_not_found`，无 traceback（Round 1
    该路径同样逃逸崩溃）。
  - **D1（scope_missing 类型化送达）FIXED**：真实子 Runner 进程（真实
    TeamRunner.prepare + `_freeze` + exposure 写入后 `os._exit(0)`）产出
    cq_frozen 检查点；随后真实 CLI 子进程 `--mode production` resume，唯一桩为
    HTTP 传输（本地 stub server：游标端点返回空页、
    `/api/projects/{id}/ontologies` 不含绑定 id）。真实 `PlatformScope` 代码执行
    `_checkpoint_binding` 并抛出真实 `PlatformScopeMissingError` → CLI 类型化
    捕获（`__main__.py:3158`，`resume_requested` 门控）→ exit 2、
    `code=scope_missing`、reason 含缺失 ontology id、retryable=true、§8 六键、
    无 traceback；新 run 目录 state.json 终态 `CLEANED`（非 RUNNING/STARTING，
    未伪造空白 scope 充当恢复）。`scope_missing_rejection`（recovery.py:133）与
    非 resume 调用方原样 re-raise 分支均已代码核对。
  - **D3（§8 键名）FIXED**：对四类非锁拒绝逐一验证键集合——
    `artifact_changed`（篡改包 production resume）、`resume_new_run_exists`
    （完整 configuration + 预占 new-run 目录）、`checkpoint_kind_mode_mismatch`
    （acceptance + 非 handoff kind）、`checkpoint_not_found`（inspect 缺失 id，
    phase=null）：全部 exit 2、键 ⊆ §8 契约名且含全部五必填键、
    `reason_code/detail/object/retry` 内部键零出现、无 Traceback。
    `CheckpointError.data()`（checkpoints.py:116-129）仅投影
    `code/object_ref/phase/retryable/reason`（+可选 `next_action`）；runner 的
    checkpoint-save-failed 证据记录 CheckpointError 分支已用 `**error.data()`
    （runner.py:10508-10514）。design:381 与 runbook 的字段名宣传现在与实现一致。
- 新增缺陷回归测试核验（读证 + 随套件执行）：
  - `test_d2_acceptance_lock_conflict_is_a_typed_cli_rejection_no_traceback`
    （acceptance.py:1056）：真实进程内持锁 + 真实 CLI 子进程（`_run_resume_cli`
    为 `subprocess.run([sys.executable, "-m", "modeling_team", …])`），断言
    exit 2、无 Traceback、恰一行前缀、六键精确集合、拒绝先于输出目录——与声称
    一致。
  - `test_d2_production_lock_conflict_is_a_typed_rejection_exit_2`
    （resume.py:1777）：真实持锁 + 进程内 `main()`（argv patch），键集合含
    `_S8_FIELDS` 且显式排除内部键——与声称一致（进程内弱于子进程，但 I 探针已
    用真实子进程独立证实同一通道）。
  - `test_d1_missing_scope_is_a_typed_rejection_exit_2`（resume.py:1820）：真实
    终止子 Runner 产源检查点；HTTP 传输与 PlatformScope 构造为桩，但桩抛的是
    真实 `PlatformScopeMissingError` 类，且该异常从真实
    `PlatformScope._checkpoint_binding` 的产生已由既有
    `test_m13_m23_checkpoint_binding_loads_by_identity_and_never_creates`
    （resume.py:1498，真实 PlatformScope 代码 + 传输桩）证明——桩分层可接受：
    D1 回归补的是此前未证的 CLI 通道转换，raise 本身有同缝证明。完全真实的
    HTTP 级联（真实后端 + 真实 scope raise + 真实 CLI）在仓库内任何地方都未
    覆盖，属既有边界（需真实后端，超出本轮约束），记为残留而非缺陷。
- Low 观察项（新，不阻塞）：runner 的 `checkpoint-save-failed` 证据记录两个分支
  键形不一致——CheckpointError 分支为 §8 名（`**error.data()`），OSError 分支仍
  为内部名 `reason_code/detail`（runner.py:10517-10525）。同一证据事件流中两种
  键形，统一消费者需兼容两种；建议后续轮对齐（OSError 非 §8 拒绝，属实现选择）。
- 探针装置说明：本轮我的子进程封装在 uv-run 环境下出现间歇性
  `No module named model_team`（同一命令 `env -i` 干净环境 10/10 成功、手工执行
  均成功）——已定位为测试装置自身问题，非产品缺陷；受影响的两处数据点
  （resume_new_run_exists、inspect not-found）以 `env -i` 手工执行取证。
- 残留清理：探针 run 目录、占用目录、d1 新 run 目录与 `.recovery-locks` 锁项
  测后删除（modeling-runs 目录数 238→235 复原；锁目录空）；台账 mtime 未动；
  git status 与交接文件集合一致（18 项，无测试侧写入）；/tmp 探针目录已删。
- 轮次结论：D1/D2/D3 全部 FIXED 且有本轮独立证据；I 层对 S1+S2+S4 范围**通过**。
  无需第三轮，除非主代理决定处理 Low 观察项。

### M — Round 5 — 2026-09-14 修复轮（I — Round 2 低危观察：证据记录键形不一致）

- 执行者：开发代理（requirement developer）。代码基线：`ae70547` 工作区（未提交基础上修复）。
  范围仅一处：Runner `checkpoint-save-failed` 证据记录（`runner.py`
  `_save_checkpoint_after_trigger`）两个分支键形不一致——CheckpointError 分支经
  `**error.data()` 已是 §8 键名，OSError 分支仍输出内部名
  `reason_code/detail`。先以失败断言复现（新用例 KeyError: 'code'）再修。
- 修复：OSError 分支对齐同一 §8 键形——`code="checkpoint_write_failed"`、
  `object_ref="checkpoints"`（与 `checkpoints.py` 保存侧同代码的 obj 一致）、
  `phase="checkpoint-save"`（runner.py 保存侧既有 phase 字面量，6 处沿用）、
  `retryable=True`、`reason=type(error).__name__`（只记异常类名，不带路径）、
  `next_action` 给出重试指引；不再出现任何旧键名。CheckpointError 分支未改。
- 回归：新增
  `test_checkpoint_save_failed_evidence_uses_the_s8_shape_for_oserrors`
  （monkeypatch `_save_run_checkpoint` 抛真实 OSError → 记录逐字段断言 §8 键形、
  无旧键名、无残留包）；扩展既有
  `test_phase_complete_claim_without_artifacts_is_refused_with_retry_guidance`
  对 CheckpointError 分支记录补断言 `phase=="checkpoint-save"` 且无旧键名。
- 命令与结果：

  ```bash
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest \
    modeling_team/tests/test_r30015_checkpoints.py -q
  env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team -q
  # 1784 passed, 1 skipped, 331 subtests passed in 109.65s
  # （Round 4 基线 1783 + 新增 1 = 1784，无回归）
  ```

  ruff（100 列）：test_r30015_checkpoints.py 通过；runner.py 仅保留与 `ae70547`
  相同的 4 个既有发现（F401×3、F841×1，符号未变），未扩大。M 层自评不代表
  I/D1/L0 状态。

### L0 Runtime Round 1（2026-09-15，独立复核：PARTIAL）

真实 run `r30015-l0-20260915-cq-start4` 在冻结 CQ 后保存了
`materialization_progress-0001`，旧 Batch 仅有已验证、未 apply 的 dry-run。Claude Code
修复源 run 停止后的状态结算和后续阶段恢复冻结池后，新进程 run
`r30015-l0-20260915-dryrun-resume6` 从该包恢复 51 个 artifact、保留冻结池，使用新 Session、
revision-2 plan、Batch 与 idempotency key；新 Attempt
`b7d70709-2b0e-4404-a13c-49ca916231c9` 为 `dry_run/validated`，仅四条非阻断
`missing_evidence` warning。旧 Batch 未重交，未执行 `apply_atomic` 或
`production_handoff`。Runner 新包 `materialization_progress-0001` 含 54 个 artifact；平台
Session 的 client checkpoint `materialization_progress-0002` 是另一命名空间，UUID 为
`67a5b8fa-8eba-4269-861d-ebc78a4ae04b`。Runner 终态 `CLEANED`；Host 读回平台
Session `b9d6527f-2209-4a07-b58b-f5be8a326add` 已 completed、0 Lease，新 Batch
`6649c60c-05f0-4a68-96e6-00de3003c779` 仍 open，但只含该 validated dry-run。

独立验收核对源包与新包摘要、恢复 origin/imports、实际 Batch/Attempt 和终态后判 S1/S2
及未 apply 的有界结果通过，L0 总体 PARTIAL：CQ Agent 因恢复轮角色工作目录缺少清单中的
公开/freeze artifact 且冻结 Profile 拒绝共享证据路由而报告 `blocked`；Acceptance carrier
cleanup 为 `aborted/runner-cleanup-before-settlement`。原 run6 issue-1/issue-2 的消息路由
拒绝与正式 issue_resolution、随后三位 Agent 的 accepted terminal result 均保留。
三次获准 fresh semantic starts 已用尽；这轮不能再启动复测。CQ 公开投影挂载、宿主专属
冻结文件的恢复 packet 可读清单，以及终态绑定回复提示已由 `be027b0` 局部修复；
代码回归为 1784 passed、23 项已复现的旧 fixture 失败、15 skipped，未宣称全套 PASS。
新授权下仍需真实复核 CQ/Acceptance settlement；不得把本轮机械 dry-run
或检查点恢复计为 L1 语义质量、受治理检索或最终模型接受。

证据保留在 `/home/yangxiang/ontology-platform-checkpoint-l0-20260915/workspaces/modeling-runs/r30015-l0-20260915-dryrun-resume6/` 的 `recovery/`、`checkpoints/`、`evidence/`、`state.json` 与 `acceptance-carrier/evidence/cleanup.json`；Host 授权、资源读回和密钥撤销账本为同 worktree 下 `workspaces/checkpoint-l0-20260915/host-ledger.json`。该轮中为修复源 run 生命周期而延迟首次 semantic start，已按 AGENTS.md 报告，不把补修时间计入语义建模时间。

### 后续功能与真实运行

#### 最小人工场景真实 L0（2026-09-16，进行中）

- 用户要求构建最小场景以走通流程；使用独立的
  [两概念安装位置场景](../../evaluation-scenarios/checkpoint-minimal/README.md)，
  不复用工业售后 21 表范围。业务源是明确标识的人工定义，未改写旧 run 的冻结源。
- Task `r3-0-015-minimal-flow`，CQ profile，`deepseek-flash-max`；代码基线
  `9fcc2e0`。Task 配置校验、文档链接检查及 `git diff --check` 通过。
- `r30015-minimal-20260916-start1` 在 `2026-09-16T00:13:42.681227Z` 记录真实
  semantic start。已保存 `scenario_mapped-0001`（7 artifacts），发布候选
  `service-site-installation-r1` 和 `cq-review-0001` 审核快照；新源的 CQ 代审委托待用户答复。
- 宿主记录：`workspaces/checkpoint-minimal-20260916/host-ledger.json`；运行证据位于隔离
  checkout `/home/yangxiang/ontology-platform-checkpoint-minimal-20260916/workspaces/modeling-runs/`。
  本轮授权账本为 3 次，已确认使用 1 次；旧 run6 恢复授权与失败证据单独保留。
- 计划在首次 dry-run 检查点后安全退出，再 production resume→apply/readback→真实
  production_handoff→原生产进程退出后的 acceptance-only 续跑。当前尚未验证此链，
  不计 apply、生产交接或独立验收 PASS。

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
