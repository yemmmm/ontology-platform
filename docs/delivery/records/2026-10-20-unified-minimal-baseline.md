# 通用建模与最小链测试基线对齐

日期：2026-10-20。所属需求：R4.3-026，相关 R4.0-002、R4.3-024／025。
用户授权：新建 worktree，补齐通用建模与最小链业务；测试基线共用通用提示，
业务输入独立；一并处理发现的严重问题。本次没有授权或执行真实建模。

## 变更范围

- 基于 `5135bff` 创建分支 `codex/unified-minimal-baseline-20261020`，
  worktree 为 `/home/yangxiang/.codex/worktrees/79e5/ontology-platform`。
  原工作区未提交的文档和其他材料没有复制、修改或提交。
- 新增通用 `unified-modeling`／`unified-modeling-dsh` Profile。
  Coordinator、Modeling、CQ 直接使用通用角色包；Modeling 和 CQ 使用通用 Skill。
  原最小链两个 Profile 文件名也选择同一配置，旧 compact 包仅保留历史对照。
- 最小链、资产—故障—工单和完整场景使用相同共享技术合同与流程参数。
  检查点能力与通用任务一致，但不自动执行检查点实验。独立业务资料、任务身份、
  目标、CQ 私有草题及实际授权范围保留；挂载映射技术合同不扩大业务范围。
- 通用方法补齐：字段型 Class／relation_type 完整交付、语义角色正确字段、
  纠错时保留声明、资源种类与业务角色区分、概念／实例含义、真实引用与方向核对、
  自查后的修模授权。继续允许受支持的普通语义节点和扩展角色，不强制全模型有 Class，
  不增加七角色枚举硬门或自动业务推断。
- 通用 CQ 接收获准场景的私有草题作为待审阅输入，继续沿原审阅／冻结通道处理。
  私有草题和隐藏内容没有进入 Coordinator／Modeling。

## 发现并处理的问题

1. 通用表示合同一旦出现在 role_sources，Runner 就重新要求旧 Stage 3 slot，
   阻断当前直接提交的拓扑检查。删除这个“文件名选择执行政策”的条件，仅非 unified
   历史路径保留原 slot 前置；当前路径继续执行写入 intent／receipt 完整性检查。
2. 通用 Coordinator 的首动作要求与 Runner 强制先读材料冲突，统一为完成初读后先派工。
3. 通用场景图合同错误地将 owner_slice 指向角色名；修正为实际 slice_id，并补充
   无统一候选时记录真实字段型请求、apply／read 引用的方式。
4. 通用材料中旧 Protocol／slot／plan／dry-run 要求缺少当前路径边界；
   明确当前直接执行和 cq_semantic 交接范围，保留历史格式供读取。

Stage 3 防御按 AGENTS T0 复核：它原本保护历史候选和审批的关联完整性；
当前直接路径允许无候选的字段型定义，缺旧 slot 本身没有不安全写入；
因此不能因加载一个语法参考而阻断 run。删除这个触发条件后，当前提交的显式内容、
授权范围、拓扑、引用、版本、原子 apply 和写入完整性仍由现有边界保护；
普通字段错误仍可修正。没有放宽未知写入处理或独立验收。

## 验证与限制

- 修改前，原最小链配置／DSH 合同检查：15 passed。
- 新增跨场景加载检查先复现缺口，随后验证两种 Runtime、三类业务场景加载同一路径
  的通用指令、Skill、共享合同及参数；冻结的角色／Skill 摘要一致。
- 通用合同挂载回归曾失败于旧 Stage 3 前置；修复后相关 57 项通过。
- 最终代码上的相关回归：**206 passed，58 subtests passed**。覆盖当前／历史 staged
  检查、损坏回执拒绝、字段型声明编译、Role/Skill 及源隔离、提示组装、Codex 加载、
  DSH 配置与真实离线隔离 roster 加载／进程控制、场景图校验。
- 此前 DSH 全模块离线检查也已执行，12 个真实运行时工程用例通过；最终相关回归再次
  核对三角色实际加载的指令／Skill SHA256 和私有题隔离。没有调用真实模型或写业务模型。
- Skill validator、JSON／YAML 解析、Codex／DSH CLI 配置校验、变更测试文件的 Ruff
  和 diff 检查通过。Runner 整文件 Ruff 仍有 7 项原有 F401／F811／F841；
  通过读取基准提交逐项比较 code／message／line，确认本次没有新增诊断。
  DSH CLI 校验显式选择已有 `dsh-glm-flash-low`，只是配置校验，不确定未来运行选型。
- 已执行一次 modeling_team 全量：**3540 passed，24 skipped，28 failed，
  304 subtests passed**。其中 4 个属于旧材料／参数预期，已按新目标更新并由最终
  相关回归覆盖；另行复核剩余环境依赖得到 **24 failed，5 passed，30 subtests passed**。
  **全量回归没有通过**，不将这些分次结果拼成一次全量 PASS。

剩余 24 项来自未修改的两个测试范围：

- `test_host_ops_mcp.py::test_config_json_registers_the_stdio_command_for_this_checkout`：
  仓库中的本机 MCP 注册固定指向原工作区，断言却要求它指向新 worktree。
- `test_r23006_acceptance_operation.py` 的旧留存验收及相关子测试：
  缺少 `workspaces/modeling-acceptance/r23003-acceptance-only-start20-1/runtime/acceptance-ticket.json`。
  原工作区有该历史票据，新 worktree 未携带 gitignored 运行数据；随后出现的
  `KeyError: 'host'` 是准备失败的连带结果。相关测试、生产操作和本机配置均与基准提交相同。

这些历史输入没有复制或伪造，未修改旧票据、历史裁决或本机 MCP 注册。
本次变更未触及 backend／frontend，不需要重启原工作区应用服务。

GitNexus 对当前 Runner 符号未命中；指定本 worktree 的 detect_changes 返回 low，
但索引没有覆盖本次 Runner 变更，不能据此声称完整图分析。
已直接核对调用点：检查在 Runner 轮询中控制拓扑检查，写入完整性位于该条件之前；
以当前／历史 staged 回归和 modeling_team 全量补充覆盖。

工程相关验证已完成；尚未取得新组合的真实建模、独立语义验收或成本改善证据。
未来获准实验必须使用本基线及独立冻结题集记录新结果，不能继承旧 compact 运行的 PASS。
