# R4.0-018～021 宿主运行衔接、配置、持续推进与状态记录共享测试计划

## 1. 测试范围与分层

本计划对应四条相邻需求及其设计：

- [018 生产交接与同源检查点验收](../designs/2026-10-04-r4-0-018-acceptance-startup-handoff-design.md)
- [019 Session 配置一致性](../designs/2026-10-04-r4-0-019-session-configuration-design.md)
- [020 授权内持续推进](../designs/2026-10-04-r4-0-020-authorized-continuation-design.md)
- [021 最新状态与分类耗时](../designs/2026-10-04-r4-0-021-status-and-timing-design.md)

测试必须分别报告四层结果：

| 层级 | 证明对象 | 可否替代真实语义验收 |
| --- | --- | --- |
| M 机械/文档 | 权威链接、文件归属、字段/JSON/CLI 帮助、敏感字段扫描、设计与 runbook 一致 | 不可 |
| D 开发验证 | 开发者新增/更新的 host/runtime/service-level tests 及相关回归 | 不可；不等于独立验证 |
| I 独立功能验收 | 独立 fixture/harness、独立断言和保留失败证据，覆盖需求 A 场景 | 不可；不证明业务语义质量 |
| R 真实 runtime/semantic | 获准运行中的真实进程、平台读写、Modeling 产物、Consumer/Judge 证据 | 是唯一可用于相应 L0/L1 结论的层；仍需按原独立验收合同 |

本设计阶段未执行 D/I/R；后续实施不得把“设计通过”或机械检查写成四条需求完成。

## 2. 固定测试原则

1. 先以 `git rev-parse --show-toplevel` 确认 checkout，检查 `git status`，只使用本轮拥有的文件；不删除用户或其他任务的 dirty work，不修改原 run、freeze、handoff、旧报告或历史失败记录。
2. 复用现有 `modeling_team/tests/test_host_ops_s2.py`、checkpoint/lifecycle 测试和 `get_run_status` 合同；独立验收使用独立临时 fixture/harness，不直接复用开发断言函数。
3. 只读场景应验证树/文件 digest 前后一致。涉及 launch 的 fixture 使用无秘密 env；真实运行前必须有用户授权、记录授权来源/余额和实际消耗。
4. 错误按最窄层归因：`platform-contract`、`collaboration/routing`、`runtime/infrastructure` 或 `modeling-quality`。启动拒绝、配置未核实和记录缺失不能推出模型质量失败。
5. 发现 unknown write、存活 writer、配置漂移或证据不可读时，保留原件并停止危险重试；不删锁、伪改状态、重复 apply 或缩小题集分母。

## 3. M 层机械检查

| ID | 检查 | 预期 |
| --- | --- | --- |
| M-018-01 | 逐条检查设计、runbook、Skill 对 requirements-v4.0 R4.0-018 的链接和锚点 | 链接指向当前版本；三态、stop/exit、同源锁、0 start 和计数边界一致 |
| M-019-01 | 扫描设计/实现/证据示例 | 不出现 API key、token、auth cache、完整环境、hidden 题面/答案；`model_profile` 与三态 `service_tier`（`unset`/`fast`/`default` off）命名一致 |
| M-019-02 | `python -m modeling_team run --help`、`checkpoint resume --help`、`cq-acceptance --help`（实施后） | 只有经设计批准的显式参数；production/acceptance 约束保持，不引入隐式全局默认 |
| M-020-01 | 检查 progress-report/runbook 模板字段 | `completed/remaining/next/authorization/wait/resource/handoff` 可定位，无“阶段完成=整体完成”表述 |
| M-021-01 | 检查 summary/time JSON 示例和链接 | 时间为 UTC，分类、basis、overlap、estimate/unknown 语义明确；历史保留和证据引用明确 |
| M-ALL-01 | `git diff --check`、Markdown 链接/结构检查、只查看本轮新增文件 | 无空白/断链/未闭合代码块；requirements-v4.0 未被本轮设计写入 |

建议的文档检查命令在实施后按仓库现有 validator 执行；没有适用 validator 时使用 `rg`、`git diff --check` 和链接目标存在性脚本，并在交付记录写实际命令。

## 4. D 层开发验证矩阵

### 4.1 R4.0-018

| ID | 场景/断言 | 主要位置 |
| --- | --- | --- |
| D-018-01 | role terminal/handoff ready 但 managed writer 活跃：不能直接 acceptance；stop request、receipt、exit 记录顺序可读 | `host_ops.py`、lifecycle tests |
| D-018-02 | unknown write / source active / checkpoint drift 返回原类型化错误和 next action，源树不变 | checkpoint/lifecycle tests |
| D-018-03 | 同一 root continuation 互斥；前一进程未退出时另一批不启动，退出后可按任意获准顺序接续 | `__main__.py`、S4 tests |
| D-018-04 | acceptance continuation 保持 `semantic_starts=0`、完整分母和新输出根；生产 start 计数不被改变 | acceptance continuation tests |

### 4.2 R4.0-019

| ID | 场景/断言 | 主要位置 |
| --- | --- | --- |
| D-019-01 | start/production resume/acceptance resume 沿现有 profile 路径，并显式传递三态 service-tier；launch record 不含秘密 | `host_ops.py`, `host_ops_mcp.py`, `__main__.py`（仅实际缺口） |
| D-019-02 | `TeamModelProfile` 的 role model/requested/effective effort 与既有 profile snapshot 对应；不被默认 profile 覆盖 | `model_routing.py`, profile tests |
| D-019-03 | ambient normal/unset 下显式 fast：生产四角色及 Source/Platform Examiner/Judge 的实际隔离 TOML 都含 `service_tier=fast`/`fast_mode=true` | `runtimes/codex.py`, `test_r23008_codex_builtin_config.py` |
| D-019-04 | ambient fast 下显式 default/off：仅本次 child env/config 清除 fast；宿主环境、旧 thread 和历史记录不变 | `host_ops.py`, `runtimes/codex.py`, managed-launch/config tests |
| D-019-05 | ambient normal/unset 与 explicit fast 的双向覆盖记录可区分；unsupported/unverified 不自动降档、重启或消耗 start | runbook/progress tests |
| D-019-06 | production checkpoint 当前不能覆盖 `model_profile`：记录限制并保留 source profile effective，不假称新配置生效；acceptance override 单独核对 | checkpoint/continuation tests |
| D-019-07 | repair entry 能引用既有台账中的适用角色/范围，旧线程 immutable | repair contract tests |

### 4.3 R4.0-020

| ID | 场景/断言 | 主要位置 |
| --- | --- | --- |
| D-020-01 | 阶段报告写清已完成/剩余/下一动作/授权依据；仍有明确待办且条件满足时沿已有入口继续 | Skill/runbook/progress 文档检查 |
| D-020-02 | 缺业务决定/权限/兼容性/新额度时只等待受影响动作；独立工作仍可做，不扩权 | progress/runbook 文档检查 |
| D-020-03 | 目标完成/暂停/取消/到期后报告 stop/cleanup；剩余额度不触发 run | progress/runbook 文档检查 |
| D-020-04 | 资源恢复或监督交接说明真实状态；已撤销 key 不恢复，无后台能力不报监控 | runbook/repair 文档检查 |

### 4.4 R4.0-021

| ID | 场景/断言 | 主要位置 |
| --- | --- | --- |
| D-021-01 | 顶部报告摘要能定位 run/checkpoint/process/progress/verdict/blocker/remaining/auth/evidence/observed_at，并链接现有 `get_run_status` | progress/runbook 文档检查 |
| D-021-02 | 缺/冲突/不可读证据保留 unknown/limitations；不从 RUNNING 或 semantic-start 数量猜进展/额度 | progress 文档检查 |
| D-021-03 | 新摘要不改旧 evidence/report/cleanup；旧 status 字段保持原语义 | 记录 diff/链接检查 |
| D-021-04 | 时间记录支持六类、UTC、basis、overlap；墙钟 union、累计 Agent time、估算分别报告 | progress/time-record 文档检查 |

开发回归必须按仓库要求运行：`cd backend && uv run pytest` 仅在 backend executable code 被改动时执行；本组主要代码变化执行 `backend/.venv/bin/python -m pytest modeling_team/tests -q` 或仓库当前固定命令，并记录已知基线失败，不能省略失败清单。

## 5. I 层独立功能验收

独立验收者先阅读四份设计和权威需求，再自建 fixture/断言。测试输入只包含获准的状态、profile、假凭据名和安全示例，不注入隐藏答案或依赖开发实现内部函数。

| ID | 独立场景 | 预期判定与证据 |
| --- | --- | --- |
| I-018-A1 | role terminal + handoff ready + process alive | **PASS** 仅当宿主识别三者差异，完成 stop/exit 后才 launch；直接 launch 被拒/未调用也有记录 |
| I-018-A2 | public 或 hidden continuation active，另一批待执行 | **PASS** 仅当同 root 互斥且前一退出后可接续；题集顺序不被代码固化 |
| I-018-A3 | unknown write、未退出、source_active、漂移 | **PASS** 仅当首阻塞/原件/next action 保留，未删锁/伪改/重放 |
| I-018-A4 | complete handoff → acceptance-only continuation | **PASS** 仅当新输出根、0 semantic start、完整分母、执行/有效裁决计数和源只读均可核对 |
| I-019-A1 | 用户配置不同于 Skill 默认/跨调度时段，分别记录 `unset`、`fast`、`default`/off | **PASS** 仅当新入口使用既有台账中的最新适用记录，不重复询问或退回默认，并区分未指定与明确 off |
| I-019-A2 | ambient normal/unset → 明确 fast | **PASS** 仅当 production 四角色及 Source/Platform Examiner/Judge 的实际隔离 TOML 都含 fast 字段，且 launch/config 证据可追溯 |
| I-019-A3 | ambient fast → 明确 default/off | **PASS** 仅当本次 child 的 env/config 清除 fast 字段，宿主 ambient、旧 thread TOML 和历史记录不变 |
| I-019-A4 | production/public/hidden/checkpoint/repair 五入口 | **PASS** 仅当 profile/effort 沿现有路径；production checkpoint 不能覆盖 model/profile 时明确报告限制，不能假称新配置已生效 |
| I-019-A5 | unsupported 或无法核实 | **PASS** 仅当不静默替换，既有进度/交接记录保留可操作状态和限制 |
| I-019-A6 | 安全输出 | **PASS** 仅当记录只含白名单，无秘密/隐藏内容，也不从 fast 推导性能/计费/质量 |
| I-020-A1 | 隐藏完成、公开仍待办且已获准 | **PASS** 仅当阶段报告后继续且不报整体完成 |
| I-020-A2 | handoff 后需 stop/exit | **PASS** 仅当停止为内部切换，后续待办/检查点/额度保留 |
| I-020-A3 | 缺业务/权限/兼容性/额度 | **PASS** 仅当只阻塞相关动作并说明影响，不扩授权 |
| I-020-A4 | pause/cancel/deadline/goal complete | **PASS** 仅当停止和清理真实，余额不触发无必要 run |
| I-020-A5 | supervision handoff/resource restore | **PASS** 仅当责任、进程、run/checkpoint、下一动作和资源状态可接续 |
| I-021-A1 | 长记录、多次旧阶段收口 | **PASS** 仅当顶部报告摘要指向最新事实、链接现有 status 且原证据可追溯 |
| I-021-A2 | 新结果、资源重建、旧清理记录 | **PASS** 仅当时点/范围清楚，历史不覆盖 |
| I-021-A3 | 语义与修复/审阅并行 | **PASS** 仅当 wall-clock union 不重复，cumulative/overlap 另列 |
| I-021-A4 | 只有进程窗口/局部 estimate | **PASS** 仅当标 estimate/unknown，不外推有效语义时间 |
| I-021-A5 | 流程改进报告 | **PASS** 仅当六类工作可区分，复用已有记录且无新监控/预检硬门 |

独立测试记录必须列每个用例的输入、观察、证据路径、失败层和限制；不能只写“套件通过”。失败也必须保留，后续通过不能抹去第一失败。

## 6. R 层真实 runtime/semantic 计划与完成门

本层需另行取得用户明确的 fresh semantic start 授权；本轮已有记录显示先前 5/5 已用完，不因本设计新增额度。启动前仅做安全开始所需最小核对，并遵守 20 分钟内第一次真实 start 的项目规则。

### 6.1 Runtime 衔接

- 在已授权的 production handoff 运行中观察真实 role terminal、handoff readiness、写入排空、stop request、managed exit、checkpoint inspect 和 acceptance continuation 的事件顺序。
- 记录 source_active/unknown write 等真实失败及其恢复，不以模拟 fixture 替代；acceptance continuation 的 0 start 与新输出/原源只读边界单独核对。
- 019 仅核对实际新 child 的配置白名单和 profile/effort/service tier 证据；不把一次配置读取当成性能/计费证明。
- 020/021 记录实际阶段继续、等待、资源生命周期、最新摘要和时间区间；没有实际后台监督就如实交接。

### 6.2 语义质量边界

真实 runtime 运行顺利只证明 L0/操作合同的一部分。模型来源忠实度、检索质量、Consumer/Judge 有效裁决仍按原 R4.0-009/R3.0-011 独立验收，不由 R4.0-018～021 的启动、配置、持续推进或报表 PASS 推导。未取得语义/检索证据时，四条需求和整体交付均保持 PARTIAL。

## 7. 清理、证据与报告模板

每次实施/独立运行结束后保留：

- 需求/设计版本、checkout commit、测试命令和基线失败清单；
- run/source/new-run/checkpoint/attempt IDs、授权引用、实际 start 消耗；
- 首个阻塞、错误码、原始日志/事件/receipt 和恢复结果；
- 配置三态证据的安全投影及未核实项；
- 最新摘要核实时间、time intervals、wall-clock/cumulative/estimate 口径；
- 资源实际保留/撤销/待核实状态。

报告正文先写语义/运行结果，再写机械/开发/独立证据和限制。任何一层未执行写 `未执行`，未知写 `UNKNOWN`，不把清理成功、进程退出、阶段收口、配置加载或测试全绿写成语义 PASS。

## 8. 当前计划状态

设计阶段：未执行 M/D/I/R。后续开发必须先更新四份设计中确认的实现差异，再执行 D；独立验收使用独立方法和证据，真实 runtime/semantic 运行在单独授权后执行。

## 9. 独立测试 Round 1（2026-10-04，阶段记录）

测试者：独立 requirement tester `test_operations`。核实时间：2026-10-04T15:13:43Z。
代码基线：`c2593c4b587276f3e9331d70ce72a5d8414b99b0` 的 development-ready dirty worktree。
本组输入先冻结在 `/tmp/r4-018-021-independent-round1/snapshot/`，摘要见同目录
`input-hashes.json`；结束机械/配置阶段时九个输入文件 digest 均未变化，见
`post-check-drift.json`。未修改产品、权威需求、交付记录、真实运行或隐藏材料，未重启服务。

### 9.1 实际命令与结果

命令均在当前 checkout 执行；pytest 工作目录为 `backend/`，前缀为
`env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest`。

| 范围 | 实际参数/命令 | 实际结果与证据 |
| --- | --- | --- |
| 019 与相邻宿主回归 | `../modeling_team/tests/test_host_session_configuration.py ../modeling_team/tests/test_host_ops_s2.py ../modeling_team/tests/test_host_ops_mcp.py ../modeling_team/tests/test_managed_launch.py ../modeling_team/tests/test_r23008_codex_builtin_config.py -q` | 独立执行 **119 passed in 23.38s**；这是既有/开发测试重跑，不冒称独立断言 |
| checkpoint/恢复/只读验收相邻回归 | `../modeling_team/tests/test_r30015_acceptance.py ../modeling_team/tests/test_r30015_checkpoints.py ../modeling_team/tests/test_r30015_resume.py -q` | **135 passed in 13.03s**；`/tmp/r4-018-021-independent-round1/checkpoint-result.log` |
| 独立七角色实际配置、旧进程与父环境、production override、root互斥/status | `../modeling_team/tests/test_host_session_configuration_independent.py -q --basetemp=/tmp/r4-018-021-independent-round1/pytest-final` | **19 passed in 19.23s**；`independent-final.log`，每组 `actual/safe-projection.json` 与原隔离 TOML 保留在 `pytest-final/` |
| CLI 合同 | `backend/.venv/bin/python -m modeling_team run --help`、`checkpoint resume --help`、`cq-acceptance --help` | exit 0，帮助保存于同证据目录；没有新增 `--service-tier`，沿 per-command env 路径 |
| 新独立测试静态检查 | `backend/.venv/bin/ruff check modeling_team/tests/test_host_session_configuration_independent.py`、`git diff --check` | PASS |
| 宿主 Skill 格式 | `backend/.venv/bin/python /home/yangxiang/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/modeling-dev-loop` | `Skill is valid!` |
| 本组文档链接/锚点与代码块 | 独立 Python 路径/标题锚点检查 | **80 links, 0 issues**；`mechanical-links.json`，此检查不证明宿主方法有效 |

首个独立 probe 执行曾为 **17 failed / 1 passed**：16 个子进程因临时 cwd 与相对
`PYTHONPATH=..` 无法 import checkout，另一个断言误用 `process_observation.observation`
而现有合同为 `basis`。这是独立测试夹具错误（`runtime/infrastructure` 测试层），没有
产品失败证据；原 stderr/注册记录保留在 `pytest/`。修正测试的绝对模块定位与字段后
`pytest-fixed/` 为 **18 passed**，再补真实存活旧 Python 子进程隔离用例后为上述 19 passed。
未通过修改产品或删除首轮产物获得绿灯。

### 9.2 当前逐项观察及边界

| 用例 | 输入/观察/证据 | 阶段结论 |
| --- | --- | --- |
| M-018/019/020/021 与 M-ALL | 独立读权威条款、四设计、当前 diff；冻结 Skill/reference；核对所有字段、UTC/unknown/overlap、安全白名单及入口限制；80链接/格式检查 | PASS（机械/合同） |
| I-018-A1 | stop/FIFO/lifecycle 与 managed reaper 既有合同回归通过；当前尚未完成独立冻结指令角色对 terminal/handoff/exit 三态的动作判断 | 仍待宿主泛化案例；真实生产未执行 |
| I-018-A2 | 新独立 fixture 同 root 第二锁返回 retryable `source_active`；独立 root 可并行；释放第一锁后同 root 可重获；无 public-first 硬规则；checkpoint 回归另覆盖进程退出释放 | PASS（锁功能）；实际批次接续未执行 |
| I-018-A3 | checkpoint回归覆盖 unknown/pending write、writer/source-active、漂移；独立 status/root fixture 前后源树 digest一致；未删锁、改state或重放写入 | PASS（既有边界回归）；独立宿主决策待验证 |
| I-018-A4 | checkpoint suite覆盖源只读、新根、完整公开/隐藏分母与有效裁决、0 semantic starts；独立四入口探针核对 acceptance 0 / production 1 说明和源树 digest | PASS（确定性合同）；真实handoff顺序与语义未执行 |
| I-019-A1/A4 | 四入口×`unset/no ambient`、`unset/ambient fast`、`fast/no ambient`、`default/ambient fast` 共16真实隔离Python子进程；production无profile覆盖参数、public/hidden有显式profile；不支持production override在launch前可重试拒绝且无文件写入 | PASS（入口功能）；台账/跨时段/repair推理待案例 |
| I-019-A2/A3 | 16组均直接调用真实runtime配置生成路径，不导入开发test helper；读取112份实际TOML，七角色皆 `gpt-6.1-sol/medium/openai` 且fast双字段与预期相符；父env和源树不变 | PASS（配置生成） |
| I-019-A3 旧进程 | 另生成旧七角色fast TOML后保持旧Python子进程alive；新default子进程七角色无fast字段；旧树digest不变；旧进程仍alive并随后报告自身env仍fast；父env全量内部比较不变、不输出环境 | PASS（Python进程/config隔离）；非native Codex线程热切换证据 |
| I-019-A5/A6 | launch record仅记录请求，不保存env；假凭据不在record；无实测计费/性能/语义声明；非法值及MCP传递回归PASS | PASS（安全/错误边界）；unverified宿主报告待案例 |
| I-020-A1～A5 | 当前Skill/reference明确阶段继续、单动作等待、暂停/取消/到期、按生命周期资源与真实交接；尚未验证隔离角色能正确遵守这些方法 | 仅机械PASS；独立功能未完成 |
| I-021-A1/A2/A4 | 独立缺证据fixture中RUNNING不推出terminal/pass；process basis=unknown，limitations非空，observed_at存在；读status前后源树digest一致；summary/time模板unknown与来源语义明确 | PASS（status事实合同）；宿主摘要生成待案例 |
| I-021-A3/A5 | 六类/union/cumulative/overlap/estimate文档完整；尚未独立验证宿主对重叠时间的计算与报告 | 仅机械PASS；独立功能未完成 |
| R-ALL | 未获新production start授权；不启动真实业务Team/provider/native模型线程/外部业务调用 | **BLOCKED/未执行**；解除条件是另行明确授权及获准真实运行路径 |

### 9.3 阶段结论与后续

**阶段结论：PARTIAL**。M及配置/锁/status独立探针PASS，未发现产品缺陷，不建议产品修复。
冻结指令下的独立宿主泛化响应尚待执行，输入已经保存在
`/tmp/r4-018-021-independent-round1/host-scenario-input.md`，覆盖12个安全合成案例；后续
在同一 Round 1 追加评分与原回答证据，不另建重复测试方案。不将文档字段存在或开发套件
全绿当作宿主方法有效，不将Python配置/确定性回归当作真实production L0/L1或语义PASS。

### 9.4 同轮追加：冻结指令下的独立宿主响应验收

由于系统拒绝新增 agent thread，主 Agent 将实际案例响应委派给既有 `test_binding` 角色。
该角色没有参与018—021实现/测试、未见评分答案，只读取 `host-scenario-input.md` 与本轮
冻结 Skill/三 references。原回答由该角色独立写入
`/tmp/r4-018-021-independent-round1/host-scenario-response.md`，本测试者未改写回答，
只对照共享计划、原合成输入及权威条款独立评分；内容摘要保留于 `host-response-digest.json`。
角色响应是实际隔离指令理解/方法应用证据，所描述的业务/进程操作全部为模拟，没有真实
stop/launch/apply。它不等于真实production运行或模型语义验收。

| 原回答 | 覆盖用例 | 实际观察与评分 |
| --- | --- | --- |
| C1 | I-018-A1/A4、I-020-A2 | 正确区分terminal/handoff/managed exit；沿stop request→receipt→实际exit→inspect/resume顺序，unknown不升级，0 start与实际题/裁决分开，未固化public-first；**PASS** |
| C2 | I-018-A2、I-020-A1/A2 | 活跃hidden时不并发同root public；退出后无需重复授权接续public，未由hidden exit推verdict/整体完成，连续资源不误删；**PASS** |
| C3 | I-018-A3、I-020-A3 | uncertain receipt作为首阻塞，source_active/漂移后续保留；未知写入先对账、不删锁/伪改/replay；根因未知不推modeling-quality；**PASS** |
| C4 | I-020-A1/A4/A5 | production5/5耗尽仍继续原授权public acceptance，0start不等0模型调用；结束进程临时key撤销、继续使用主体保留、完整分母不缩水；**PASS** |
| C5 | I-020-A3 | 缺业务定义与额度仅阻塞生产依赖动作，完成独立证据/链接整理，不猜业务定义或扩权，等待理由可执行；**PASS** |
| C6 | I-020-A4 | 完整报告与目标达到分开；原目标完成不为耗尽余额新start；暂停不继续生产，receipt/exit各自核实并保留产物、处理资源；**PASS** |
| C7 | I-020-A5 | alive与有效进展分开，旧key不复活；重新签发等待必要批准/credential；下一观察者未安排如实交接，无虚假后台监控；**PASS** |
| C8 | I-019-A1/A4、I-020-A3 | 最新用户配置跨默认时段保持；四入口及repair显式选择；ambientfast下default仅清新child；旧线程fast保持，production override unsupported且effective仍source，0/1计数分开；**PASS** |
| C9 | I-019-A5/A6 | requested/transmitted fast与effective unverified分开，不支持model不静默换档/重启；仅读白名单，不宣称提速/计费/质量；**PASS** |
| C10 | I-021-A1/A2 | 顶部引用新report PARTIAL10/20、旧撤销与新重签批准时点分开，issued/process/authorization unknown；保留旧报告/cleanup，无PASS或额度猜测；**PASS** |
| C11 | I-021-A4 | 2400秒仅进程窗口，局部60%估计360秒不外推全程，不将剩余时间全归等待；不能确认全程有效语义比例；**PASS** |
| C12 | I-021-A3/A5 | 六类秒数600/420/180/300/120/120，墙钟union960秒、累计1740秒；三重叠与成对重叠区别正确；生产62.5%和消费43.75%不能相加当互斥总量，语义/消费union720秒75%；**PASS** |

本轮独立功能层结论：**PASS（受控配置/进程/锁/status＋冻结宿主方法应用）**，0产品缺陷。
真实production/provider业务语义层仍未执行：整体四条需求保持 **PARTIAL**，不得由本轮
受控功能结果写成真实L0/L1或CQ语义PASS。无需开发者修复，真实层解除条件仍为获准实际
业务运行和对应独立验收。本轮原失败记录、旧snapshot、原角色回答均保留。
