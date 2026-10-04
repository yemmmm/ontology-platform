# R4.0-019 Session 用户指令与各启动入口的配置一致性设计

## 1. 范围、基线与状态

- 权威范围：[R4.0-019](../../requirements/requirements-v4.0.md#r40-019-session-用户指令与各启动入口的配置一致性)。本设计覆盖用户在当前 session 选择的模型、effort、fast/service tier、适用角色和范围，在 production、public/hidden acceptance、checkpoint continuation、修复入口间的记录、传递和核对。
- 关联合同：[modeling-dev-loop Skill](../../../skills/modeling-dev-loop/SKILL.md#授权时的模型调度)、[runbook 调度段](../../../skills/modeling-dev-loop/references/team-runbook.md#授权时的模型调度)、[R3.0-007 model routing](../../../modeling_team/model_routing.py)。本条不改变模型 catalog、provider 凭据、用户授权、额度、隐藏隔离或默认 profile。
- 当前状态：需求细化与设计；未实施、未完成独立配置验收、未重新启动真实线程。
- 实际基线核对：`modeling_team/host_ops.py:start_run` 已将必填 `model_profile` 写入 `run --model-profile`；checkpoint acceptance 路径和 `modeling_team/__main__.py:_run_checkpoint_resume_acceptance` 已转发 `--model-profile`；`TeamModelProfile`/`RoleModelBinding` 已提供角色级 model、requested effort 和 effective effort；`profile.snapshot.yaml` 可作为 run 级模型绑定来源；`runtimes/codex.py:_builtin_session_service_tier_lines` 和现有 `test_r23008_codex_builtin_config.py` 已证明 ambient `MODELING_TEAM_CODEX_SERVICE_TIER=fast` 能影响新隔离 Codex config。
- 已核对的实际缺口：host-managed `start_run`/checkpoint launch 的 argv 和 launch record 没有显式的 fast/service-tier 输入；当前 fast 只能从宿主环境继承，因而现有记录不能区分“本 session 用户要求 fast”“本次 child 收到 fast”和“生成的隔离 config 实际含 fast”。这就是本条唯一预先确认的代码路径缺口。模型 profile/effort 路径不作为缺陷重做。
- 双向现场证据见[本次运行记录的 normal 模式恢复](../records/2026-10-04-v4-semantic-acceptance-attempt-record.md#s4-attempt-0003-终态与-normal-模式恢复)：ambient fast 存在时用户明确要求 normal/off，production 四角色、Source/Platform Examiner 和 Judge 的新隔离 TOML 均核实为无 `service_tier`/`fast_mode`。这证明 default/off 的 child 清除行为需要被记录和独立回归；它不证明所有 host-managed 入口已经具备该传递。

本设计优先使用现有 session 台账/进度记录、launch record、run snapshots、profile projection 和隔离 config 证据。暂不新增配置中心、`modeling-session-config/v1` 文件、全新错误码、全局默认或强制配置门。

## 2. 最小记录与核对规则

用户最新指令继续记录在既有 session 台账和 [progress report](../../../skills/modeling-dev-loop/references/progress-report.md) 中，至少写：模型/profile、effort、service-tier 三态（`unset`、`fast`、`default`/off）、适用角色/范围、更新时间、授权引用和对存活线程的限制。该记录是宿主交接信息，不是新的平台配置资源。

启动或接续时只需在已有记录中形成三条可定位事实：

| 事实 | 现有来源 | 允许的增量 |
| --- | --- | --- |
| 用户请求 | session 台账、进度报告或当前交接消息 | 统一字段/文字，避免反复询问；不另建 snapshot schema |
| 启动传递 | `host_ops` 的显式 `model_profile`、launch argv/record；本次 child 的 service-tier env/config 处理 | 只补三态的 host→child 传递；不把 ambient 全局值当作用户请求 |
| 实际生效 | `profile.snapshot.yaml`、`TeamModelProfile.as_dict()`、角色绑定、已有隔离 config/安全运行元数据 | 读取必要白名单；读不到时在进度/交接记录写 `unverified`，不增加新平台错误 |

对 Codex built-in route，三态含义固定为：`unset` 不覆盖 child 继承的既有环境，`fast` 在本次 child 写入 `service_tier = "fast"`/`fast_mode = true`，`default`/off 清除本次 child 的 `MODELING_TEAM_CODEX_SERVICE_TIER` 并确保隔离 config 不含 fast 字段。`default` 只改本次 child 的环境副本和配置生成输入，不改宿主环境，也不改已存活 thread 的配置；`unset` 下若 ambient 环境恰好使 child 生效为 fast，记录必须把“用户未指定”和“实际 fast”分开。外部 provider 不使用该 Codex 字段时写 `not_applicable`，不推导 provider 性能。

## 3. 决策表

| 决定 | 选择 | 原因与边界 |
| --- | --- | --- |
| D019-1 | 保留现有 `model_profile` 传递和角色级 requested/effective effort；只在既有台账/进度记录中补清 service tier 与适用范围 | 代码已能显式选择模型 profile，重做模型路由会扩大风险；实际模型和 effort 仍由闭合 catalog/profile 核对 |
| D019-2 | 只为 host-managed 新 launch 补三态 service-tier 传递：`unset`、`fast`、`default`/off；可用本次 child env override 或等价显式参数实现 | 当前已证实的缺口是 ambient fast 没有 per-launch 事实，且明确 normal/off 不能清除 child 继承值；不修改宿主全局环境，不让旧线程读取新值 |
| D019-3 | 复用 launch record、run/profile snapshot 和已生成隔离 config；只有测试证明无法定位 config 时，才在现有记录增加安全白名单字段 | 不新增 session snapshot schema；请求、传递和实际生效仍可在既有记录/文件中分开核对 |
| D019-4 | profile/role 配置 immutable；线程不热切换 | 新指令只约束新启动的 child；旧线程、旧冻结和历史报告保持原配置。重启仍需原授权和恢复合同 |
| D019-5 | 不支持或无法核实时在既有进度/交接记录写 `unsupported`/`unverified` 和 next action | 禁止静默降级或把 fast 配置推导成提速、计费或语义质量结论；不新增平台错误或硬门 |
| D019-6 | 配置按角色和范围引用既有 authorization reference，但不创建额度门 | 用户授权和 start 计数仍由现有 session 台账和运行合同负责；配置一致性是证据，不是新 scheduler/budget gate |

## 4. 入口与传递设计

### 4.1 Production 与 checkpoint continuation

`host_ops.start_run` 继续要求显式 `model_profile`。实施时为 host-managed run 增加三态 service-tier 传递，或在同一 launch 边界构造一次性的 child env override；两者由开发者依据现有 launcher 形态选择最小方案，但必须满足：

1. 现有 launch record 能看出本次是 `unset`、`fast` 还是 `default`/off，不能只读宿主启动时的 ambient env；
2. `unset` 保持现有继承语义，`fast` 只给本次 child 设置 fast，`default`/off 只从本次 child 的环境副本和隔离 config 输入中清除 fast；宿主全局环境和其他存活 run 不变；
3. `checkpoint resume` 的 production/acceptance host 入口使用相同的窄传递；acceptance 仍 `semantic_starts=0`，production 仍按既有 fresh-start 记账；
4. 未提供 service tier 时记为 `unset`，明确 normal/off 时记为 `default`/off；两者不能合并成“默认 fast”或“默认 normal”。

CLI/MCP 是否新增同名参数必须以现有签名和帮助为准，不先实现平行 schema；host-managed 入口不得把 ambient 值冒充为本 session 的显式请求。

production continuation 仍是新 semantic start，按既有授权/额度合同记账；acceptance continuation 仍 `semantic_starts=0`。配置变更不改变这两个计数口径。

当前 production checkpoint resume 没有可覆盖 `model_profile` 的生产参数；它继续使用 checkpoint/source 已绑定的 profile。若最新 session 指令要求另一个 production model/profile，交接记录必须明确“该入口不支持覆盖、当前 effective profile 仍为 source profile”，不能把用户请求或 acceptance 的 model override 当作 production 已生效；是否另开获准 production start 由既有授权和用户选择决定。

### 4.2 Team role 与 Examiner/Judge

`model_routing.load_team_model_profile` 是模型/effort 的权威安全投影。生产四角色（coordinator、modeling、protocol、acceptance）以及 Source/Platform Examiner 和 Judge child 都继续使用已有 profile snapshot、role binding 和各自隔离 config 证据；不新增 per-role 配置存储。实施验证必须读取这些实际生成的 TOML：`fast` 应含 `service_tier = "fast"` 和 `features.fast_mode = true`，`default`/off 不应含任一 fast 字段；`unset` 的请求状态与 ambient 导致的实际 config 分开记录。不可读时在既有进度/交接记录写 `unverified`，不把 profile load PASS 当作 child 已生效。

### 4.3 修复入口与存活线程

修复交接沿用 [claude-repair](../../../skills/modeling-dev-loop/references/claude-repair.md) 和既有 issue resolution：交接消息引用当前台账中的 model/profile、effort、fast、适用角色/范围和“只作用新进程”说明。外部修复线程不读取/输出秘密 settings；修复完成消息只表示入口已修复，不表示旧线程已更换模型。

收到用户对 fast/default(off)/model/effort 的增量指令时：

1. 更新当前 session 台账中对应的适用范围和时间，不覆盖旧线程的实际状态；
2. 仍活跃的 thread 继续使用其创建时的 immutable 配置；
3. 后续新 child 复制最新文字/环境选择；
4. 若指定值不被入口支持，或 production checkpoint 不能覆盖指定 model/profile，留下 `unsupported`/`unverified` 和 `next_action`，不静默换档或假报生效。

## 5. 安全白名单与失败反馈

复用现有 launch/config/evidence 的安全边界，只保留 profile id/digest、provider/model 名称、requested/effective effort、service tier、角色/范围、入口、时间、配置 digest、authorization reference 的非秘密标识和证据路径。禁止写 API key、token、完整环境、Codex auth cache、账户标识、题面或隐藏答案。

参数值不合法时沿现有 CLI/参数验证错误风格处理；入口不支持或实际 config 不能读取时，在既有进度/交接记录写 `unsupported`/`unverified` 和 next action。这里不新增 `session_config_*` 错误合同，不把配置状态做成硬门、自动重启或新 start 消耗。

## 6. 实施文件归属

| 文件 | 计划工作 |
| --- | --- |
| `modeling_team/host_ops.py` | 仅在 `start_run`、`resume_from_checkpoint` 的已有参数/launch record 边界补三态 service-tier 传递和安全记录；已有 model profile 代码不重写；production checkpoint 不伪造 model/profile override |
| `modeling_team/host_ops_mcp.py` | 若 Host MCP 暴露对应 host 入口，转发同一窄值；不暴露完整环境 |
| `modeling_team/__main__.py` | 仅在实际 CLI 子进程需要接收 service-tier 时增加同名显式参数；保留 production/acceptance 现有边界 |
| `modeling_team/runtimes/codex.py` | 复用 `_builtin_session_service_tier_lines` 和隔离 config；只将来源改为本次 child 的显式值；若测试证明现有 env override 已足够，则不重构生成器 |
| `modeling_team/model_routing.py` | 默认不改；只有实际测试显示 profile snapshot 缺少既有 effective model/effort 来源时才补最小读取 |
| `skills/modeling-dev-loop/SKILL.md`、`references/team-runbook.md`、`references/progress-report.md`、`references/claude-repair.md` | 规定台账记录、入口复用、隔离 config 核对和存活线程边界；不创建配置平台 |
| `modeling_team/tests/test_managed_launch.py`、`test_host_ops_s2.py`、`test_r23008_codex_builtin_config.py` 及最小新增测试 | 只验证已证实缺口：ambient fast 下显式 `default` 清 child、ambient normal/unset 下显式 `fast` 覆盖、三态 launch 记录与现有 profile/effort 回归；逐一读取生产四角色及 Source/Platform Examiner/Judge 的隔离 TOML，并验证敏感字段不输出 |

任何代码增量都必须在交付记录中列出对应失败证据：当前 host launch 没有 service-tier 参数/记录，当前 fast 只读 ambient env，当前隔离 config 核对未连接到入口记录。没有新证据的“顺便统一”不属于本条范围。同一文件若已有其他任务改动，实施时只补本条拥有的窄字段，保留无关差异。

## 7. 分层验证计划

共享用例见[测试计划](../test-plans/2026-10-04-r4-0-018-021-operations-coordination-test-plan.md)。核心场景：

| 场景 | 预期证据 |
| --- | --- |
| A1 用户配置覆盖 Skill 默认或跨调度时段 | 既有台账记录最新适用 model/profile、effort、service-tier 三态、角色/范围；新入口复用，不回退或重复询问；旧 thread 保留旧记录 |
| A2 ambient normal/unset → 用户明确 fast | production 四角色及 Source/Platform Examiner/Judge 的实际隔离 TOML 均含 fast 字段；launch/config 证据能区分请求、传递与实际生效 |
| A3 ambient fast → 用户明确 default/off | 仅本次 child env/config 清除 `service_tier`/`fast_mode`；宿主环境和旧 thread 不变，实际 TOML 均无 fast 字段 |
| A4 production、acceptance、checkpoint、repair 入口 | model_profile/effort 沿现有路径；production checkpoint 不能覆盖 model/profile 时明确记录限制，不假称新配置生效 |
| A5 不支持或无法核实 | 在既有进度/交接记录写 `unsupported`/`unverified` 和 next action，不静默降档，不推导提速/计费/语义 PASS；launch/config/evidence 不含 key、token、完整 env、hidden content |

开发测试和独立功能测试只能证明配置传递和记录合同。真实 provider/Codex 线程的实际生效、计费或性能需在用户单独授权的 runtime 中核对；本设计轮不启动它们。

## 8. 设计完成边界

本设计不宣称 R4.0-019 已实现。完成时仍须分别报告用户请求（既有台账）、入口传递（launch/argv/env）和实际生效（profile/隔离 config/运行元数据）；缺证据写 `unverified`，不以配置核对 PASS 替代真实建模质量或独立语义验收。
