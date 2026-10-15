# R4.3-026 材料与任务实现检查

依据：[权威需求](../../requirements/requirements-v4.3.md#r4-3-026)。用户后续明确要求实施。
基线 HEAD `b6e6c7e`；工作区原有 README.md、docs/presentations/、slide-deck/ 改动不属本次。

已完成材料／Task 交付和开发合同检查；**没有启动真实模型、生产 run、平台写入或独立
语义验收**。没有恢复暂停运行或消耗建模轮次，不把配置检查称为真实 L0／L1 PASS。

## 实现与边界

- [新场景及操作说明](../../evaluation-scenarios/minimal-installation-chain/README.md)：
  唯一自足业务说明，Source ID `minimal-installation-chain-source-v1`，输入清单含 SHA256；
  复用历史人工素材定义，未补写工业服务真值。
- [独立 Task](../../../modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml)与
  [独立 Profile](../../../modeling_team/profiles/r4-3-026-minimal-installation-chain.yaml)：
  复用024／025直接提交及既有CQ生命周期，三个现有角色，未增加Protocol前置门或恢复实验。
- 专用角色包、Modeling Skill和精简表示合同替代通用全量初读；CQ仅接收本任务四道未审阅
  私有草题，业务证据仍引用唯一业务源。正常审阅、新冻结及独立只读 Consumer／Judge不变。
- 场景说明保留“最小链→资产—故障—工单小链→完整工业服务”的独立回归顺序、原checkpoint
  用途及逐层未验证边界，列明既有计时／019用量采集要求，缺值unknown，不设新预算。

初始材料交付阶段未修改平台接口、编排、存储、通用角色包或原场景；本次启动前兼容修复仅改
`modeling_team` 的模型路由与 Runner，无backend/frontend改动，不需要全后端／前端套件或服务重启。
新测试只检验配置、数据合同和离线prepare路径，
不是新验收器或语义裁判。

## 2026-10-15 启动前模型绑定兼容修复

首次 `glm-5.3-flash/high` 预启动在未创建 semantic-start、未写入平台前失败；公开错误记录为
`workspaces/modeling-runs/.host-launches/r4326-20261015-glmhigh-start1.err.log` 中的
`missing roster role bindings: minimal-chain-competency-question, minimal-chain-coordinator, minimal-chain-modeling`。
精简包的 `package.yaml.role` 已声明为 `competency-question`、`coordinator`、`modeling`，而
Model Profile 仍按语义角色键控。修复让 prepare 按该已声明 role 解析现有绑定，并只在 Runtime
入口投影为 canonical package key；原始 package、baseline 和 profile YAML 均保持不变。

修复回归覆盖 `glm-flash-high` 对三项精简包的 prepare 与 Runtime key 投影；validate、baseline
及相关 Runner／Runtime 测试通过。此次是平台路由兼容修复，不计语义建模轮次，也不代表真实
semantic-start、模型质量或独立语义验收已通过。

## 2026-10-15 start1b Runtime capability endpoint 修复

绑定兼容修复后的 `start1b` 已创建隔离 scope，但 modeling app-server 在
`semantic-start` 前退出，公开错误为 `app-server closed its output`。公开运行证据显示
coordinator 已按 `glm-5.3-flash/high` 建立 thread，而 modeling 只有进程 PID、没有 thread 或
app-server event。定位到 unified + staged 的非 formal 路径只启动 Protocol capability endpoint；
直接 Modeling 已由现有 descriptor 配置 Runner capability，namespace 随后 bind 一个尚未启动的
Modeling socket，导致 app-server 启动失败。

修复在既有 staged 启动段按 `capability_descriptors["modeling"]` 的非空 operations 调用现有
`capability_endpoint("modeling").start()`，并保留原 descriptor 工具面；没有新增模型、权限、审计、
重试或业务写入机制。新增真实 `TeamRunner` 配置回归在 roster 边界读取 Modeling AF_UNIX socket
及 `tools/list`，与 descriptor 完全一致。`start1b` 的 secret audit 发生在进程退出后的 cleanup，
不作为主动 kill 根因。

本修复仍未启动真实建模、未产生 semantic-start 或语义质量证据；由 Delivery 负责下一次真实
启动。相关提交为后续 capability endpoint 修复提交。

## 2026-10-15 start1c CQ review phase 提示修复

`start1c` 已产生一次真实 `semantic-start`，但在任何模型应用前，Host 触发 CQ freeze 被
Runner 以 `cq_freeze_schema_mismatch` 拒绝。公开 stdout 的完整反馈为 `phase=slice-draft`
以及 `publish and review at least one question first`；公开的 review acknowledgements
同样显示了 `panorama-draft` 与 `slice-draft`。Runner 的冻结题池只纳入
`panorama-review`／`slice-review`，所以 preparation draft 虽被接受为 review 输入，最终题池
为空；没有冻结消费或业务模型写入。

持久修复只收窄两个运行提示：精简 CQ 角色必须用 `phase` exactly
`panorama-review`／`slice-review` 发布正式 review，preparation phase 只能更正并重新发布；
Delivery 在提交 review 或 freeze 前核对这两个 exact 值，发现 draft phase 时要求 CQ 角色
以新 review 版本更正，不批准或循环重试 freeze。没有增加 Runner 拒绝门、模型配置、重试或
平台机制。当前运行由 Delivery 通过既有 Host 私有 CQ 通道纠正并沿原 thread 继续。

v2 loader仍要求protocol_tools非空，新Task以一个只读工具名满足现有配置合同；实际
roster没有Protocol，不产生平台写入路径或额外角色。这次仅增加任务，不扩展loader。

## 材料规模

通过既有配置loader读取两个Task/Profile，按角色去重累计：角色说明、声明references、
全部required_skills目录内文件、授予该角色的role_sources。数字是配置可见材料的UTF-8
文件字节，不含Runner动态消息、工具目录、对话、独立验收或Host材料；不是token／费用、
实际初读token或运行耗时，不据此宣称提速已验证。

| 角色 | 原资产—故障—工单配置文件数／字节 | 新配置文件数／字节 |
| --- | ---: | ---: |
| Coordinator | 8／131909 | 4／23238 |
| Modeling | 20／392245 | 5／24706 |
| Protocol | 9／332494 | 未配置 |
| CQ | 8／67289 | 4／19740 |

各角色总字节由923937降至67684，约减少92.7%；角色间共有材料按各自实际挂载重复计数。
这是材料差异证据，真实成本仍待授权运行。既有独立验收Runtime/Skill沿用，未计入这组生产
与CQ材料统计，也未为这次材料缩减修改。

## 开发检查

1. `env -u DEEPSEEK_API_KEY uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r4-3-026-minimal-installation-chain.yaml --task modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml`
   通过；绑定正确task_id/profile_id与Coordinator、Modeling、CQ roster，未绑定模型选择。
2. `python /home/yangxiang/.codex/skills/.system/skill-creator/scripts/quick_validate.py modeling_team/skills/minimal-chain-modeling`
   通过。只证明Skill格式。
3. 在backend执行：

   ```sh
   env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
     ../modeling_team/tests/test_r4326_minimal_chain.py \
     ../modeling_team/tests/test_direct_modeling_wiring.py \
     ../modeling_team/tests/test_r3011_g3_cq_routing.py \
     ../modeling_team/tests/test_r3006_unified_binds.py -q --tb=short
   ```

   **31 passed，6.39秒**，日志`/tmp/r4-3-026-contract-tests.log`。其中新测试7项：配对加载与
   源摘要；精简字段与既有合同一致；草题可形成当前CQ草稿；Runner真实prepare的逐角色源
   文件／初读清单／摘要、直接提交能力与版本冻结；三个旧Task仍按原Profile可加载。
   prepare使用CapturingAdapter与临时记录，未启动Agent／模型／平台，不证明OS运行隔离或
   真实应用效果。相邻回归覆盖直接能力接线、CQ路由及统一图挂载。
   新精简合同将owner_slice准确指向slice_id（长参考中的一处说明误写成owner），并通过实际
   scenario-map／topology校验器验证形状与错误归属负例；未修改通用合同或平台行为。
4. JSON／YAML、相对链接、输入SHA256、diff空白及旧Task／场景未改动检查通过。
   新测试Ruff通过，Skill验证通过，提交前检查仅暂存本需求文件。
5. GitNexus `detect_changes(scope=staged, repo=ontology-platform)`：18个文件、1个文档符号、
   0受影响执行流、风险low。新增任务／测试不因此获得完整图谱覆盖；影响边界以配置loader、
   Runner prepare、直接能力及CQ的实际针对性检查为证，不宣称图谱覆盖新的运行流程。

## 验收对应

| 项目 | 当前证据与保留状态 |
| --- | --- |
| A1 | 材料／配置工程通过：独立身份、版本化唯一业务源、专用包及实际prepare挂载清单；真实Agent采用未运行 |
| A2 | 未验证：真实application回执、当前修订治理读取及独立语义验收尚未发生 |
| A3 | 采集口径已交付；真实时间线／用量未产生，数值unknown，不形成性能基线 |
| A4 | 工程通过：三个旧Task及原场景文件未改动，原Profile配置加载通过；未重写任何历史证据／裁决 |
| A5 | 分级说明已交付；各层实际新验收未进行，不关闭原小链／完整场景／27题及时间目标缺口 |

后续真实验证须依当时授权选本Task/Profile，保留独立run、freeze、模型版本、应用／检索／
裁决证据与019用量覆盖；每层单独结论。材料交付不会解除暂停或自动追加运行／修模轮次。

## 2026-10-15 issue resolution 提示纠偏

公开运行证据显示，Runner 的既有 `issue_resolution` 路径会先持久化 resolution，再通过同一
broker 自动发出绑定的 `issue_control` `resume`／`abort` 并唤醒原 reporter。原 issue 的
`resume` 已由该路径在 05:08:43 结算；随后再次手动 `resume` 属于 stale control，不能当作
持久化丢失或新 issue。此前指导 Coordinator 在 resolution 后重复 resume，造成了错误的新
issue 观测。

本次持久修复只更新精简 Coordinator 与 Delivery 提示：缺字段、普通格式错误及 review／上游
等待保持可恢复等待，不上报 runtime issue；真实 typed issue 按现有 pause／resolution 绑定
处理，Host resolution 后等待 Runner 自动 settle/wake，先核对回执再判断异常。没有新增 Runner
硬门、issue 控制或重试机制；当前 live run 不因此新启或扣除 semantic-start。

## 2026-10-15 unified direct apply 的 legacy stage3 门修复

公开 `start1c` 的 `candidate-gate/state.json` 仍为 `closed/topology_missing_artifact`，而
`evidence/staged-decisions.jsonl` 记录的首个阻塞是 `stage3_missing_artifact`；同一公开 run 的
`scenario-map.json` 与 `topology-decision.json` 经现有 `validate_scenario_map`／
`validate_topology_decision` 校验均无问题。Runner 原先在每个 drain tick 先执行旧 stage3 slot
前置检查，只有该检查通过才进入已确认拓扑的 gate，导致当前 R4.3-024/025 direct
`modeling_submit_model_changes` 在 scope/topology 绑定前被 legacy slot 阻塞。

修复仅让未挂载旧 `r3-0-009-unified-graph-contract.json` 的 unified direct Task 跳过该 legacy
slot 检查；旧 unified Task 仍保留原 stage3 前置。写完整性、审批跨件检查、scenario-map／
topology 校验、candidate/scope binding 以及 direct intent/receipt 完整性均保留。没有修改
模型、平台接口或运行时重试机制；当前进程不能安全热加载，下一次 fresh start 由 Delivery
按既有授权计为 round2，旧 run 保留且无模型写入。

## 2026-10-15 round2 Coordinator provider-wait 投递修复

公开 round2 证据显示，Coordinator 因 provider `rateLimitExceeded` 进入 `coordinator:1`
等待；随后 Modeling 报告 `business_clarification`／`cq_freeze_pending`，状态为
`not_written`，没有 batch、receipt 或资源写入。Runner 原 issue-report 投递异常分支只对
`runtime_recovery` 延迟，业务 issue 在 Coordinator provider wait 期间误走
`fail_issue_rebind`，最终形成 `issue Coordinator delivery failed`。

修复复用现有 provider-wait deferral：任意 issue category 在该可恢复等待下均保留 issue
ledger、回队同一 issue report，进入 `WAITING_OWNER`，待 provider 恢复后再次投递；非
provider 的普通业务投递失败仍保留原 typed failure，未放宽写完整性。新增回归覆盖业务 issue
在 provider wait 下延迟及恢复投递。未新增 cleanup、重试框架或安全控制，未启动新的
semantic-start。round2 现有 Runner／MCP／bwrap 进程的收口仅做只读诊断；FIFO 已消失且
主进程仍在等待，后续应由 Root/Delivery 使用既有显式 stop、revoke、empty-scope 接口并
保留公开证据，本修复不自行 kill 或清理。
