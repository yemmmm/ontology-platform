# R4.0-007 多视角建模协同开发测试与交付记录

- 日期：2026-10-01。
- 权威范围：[R4.0-007](../../requirements/requirements-v4.0.md#r40-007-多视角建模协同与既有流程适配)、[详细设计](../designs/2026-10-01-r4-0-007-multiview-collaboration-design.md)。
- 结论：功能实现与开发验证通过；独立方案复审 PASS；未执行独立功能验收，A10 真实建模／独立语义验收未授权、未执行，整体 **PARTIAL**。
- 本轮没有 semantic modeling start，没有消耗真实运行额度，也没有外部业务调用。

## 实现范围

1. 新增显式版本 `r4-0-007-scenario-map/v1`：切片视角覆盖、稳定 definition_id、含义／范围、确认状态和候选绑定；adjustments 可保存修改前后候选、引用重审范围、未知／冲突与结论。旧版本仍按原合同读取，不改写旧包。
2. 活动 R4 Task、Coordinator／Modeling／Protocol 指令和 ontology-modeling Skill 同步加载新合同；允许视角交错，明确主维护与引用方责任。协同状态保持 Team 工作内容，不加入 RDF、Batch 或平台业务领域模型。
3. 校验候选 revision／item／slice 引用，before_refs 可指向不可变历史修订；提交前检查已有身份不能 create，update/delete 目标必须匹配批准绑定。错误返回可定位反馈，修正后可继续同一 run。
4. 当前定义修改继续复用审批、dry-run、workspace version 与 Batch 原子性。D1 的业务兼容判断、局部差异、完整影响范围由 Modeling／业务确认负责；跨 Batch 的破坏性变化使用新定义过渡或延后，不增加版本固定、自动兼容判断或影响传播服务。
5. 新地图随既有检查点保存／恢复；宿主 handoff 保存地图路径与摘要。Judge 只从本次实际获准读回的可见 IRI 取得确认／未知／冲突及重审状态；新创建定义还须显式 create ID 与实际可见 IRI 精确匹配。缺 ID／不可见不投影，计划／回执不独自证明可见性。不接收地图原文、自由文本或隐藏引用数量；Examiner 和生产 CQ 不取得该协同投影。投影不构成语义事实或 PASS。
6. Team 的 admin／model／read Key 显式归属既有 operator-admin 用户。仅为本轮新建或宿主确认的新 fork Project 登记成员；existing／普通 checkpoint 不修改权限。普通 prepare 移除外来 fork 标记，不创建用户或角色，不复制旧项目权限。

## 独立方案审阅

用户另行要求调用独立方案审阅 Agent 并修订至 PASS。独立 `plan_reviewer` 全程只读，未参与实现、测试、服务操作或真实建模。

| 轮次 | 结论 | 处置 |
| --- | --- | --- |
| 开发轮初审 | REVISE，0 Critical／1 High | H007-01：fork 不复制成员且以 checkpoint 模式接续，遗漏新 fork 的成员登记会阻断项目 Key 创建 |
| 同轮复审 | PASS，0 Critical／0 High；无待确认关键假设 | 仅在成功 fork 的宿主回执后记录新项目标记，并移除普通输入外来标记；新 fork 加既有 operator 用户，既有项目权限保持。问题在方案层关闭 |
| 新建定义投影增量复核 | PASS，0 Critical／0 High；无待确认关键假设 | 同一独立 plan_reviewer 核对新定义 receipt_ref 的显式 ID／实际读回匹配及不可见时不投影，CQ／Examiner 隔离保持 |

方案 PASS 不代表独立功能验收或 L1 语义验收。

## 开发测试轮次与结果

新增 [Team 测试](../../../modeling_team/tests/test_r4007_multiview.py) 16 项及 [身份接入测试](../../../backend/tests/test_r4007_team_identity.py) 4 项。身份测试使用真实 FastAPI 认证、成员／Key API 和 SQLite 持久化；Ontology 创建／fork 生命周期使用站位实现，不证明真实 PostgreSQL fork 数据完整性。Runner、CQ CLI、检查点组装使用实际代码路径，模型 provider 和平台写入转发使用现有测试适配器，未启动真实模型。

| 轮次／命令 | 结果 | 证据范围 |
| --- | --- | --- |
| 首轮 Team 全量 | 10 failed，2039 passed，1 skipped，308 subtests passed | 9 项旧 mock 对成员 API 错用 200 而非 201；1 项 spy 未接收新增可选参数。均修正测试适配，不放宽生产合同；原日志 `/tmp/r4007-team-tests.log` 保留 |
| 修正后定向回归 | 46 passed，16 subtests passed | 覆盖上述适配与受影响旧路径；此后补充了同 run 修正成功及外来 fork 标记测试 |
| 新定义投影定向回归 | 16 passed，0.99s | 已有／新建定义均经实际 CQ CLI 组装，空授权读回均无协同定义 |
| `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q` | **2049 passed，1 skipped，314 subtests passed**，167.67s | 最终 Team 全量，含新定义投影修正；日志 `/tmp/r4007-team-tests-final.log` |
| `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q` | **1079 passed，39 skipped**，138.40s | 后端全量；日志 `/tmp/r4007-backend-tests.log`；1100 条现有库弃用等 warning，无失败 |

Skipped 项不计为通过；未启用的真实 PostgreSQL／live stores／外部 SQL 场景保持未验证，不把本轮结果称为全依赖真实运行 PASS。

## A1—A10 证据对应与限制

| 条款 | 开发证据 | 限制 |
| --- | --- | --- |
| A1 | 真实活动 Task 配置与 Runner `_task_text` 组装，三个生产角色加载新地图合同，CQ 无隐藏验收输入；角色／Skill 对齐 | 未证明模型实际按方法完成多视角分析 |
| A2 | 同名异义的稳定键独立；已有 IRI 的 create 在实际 staged submit 前拒绝，改为匹配 IRI 的 update 后同 run 成功转发 | 同义和含义范围由业务确认，非平台推断 |
| A3 | unknown／conflict／deferred 可保存与投影；既有 R4.0-004 局部调用修订保留共享 Action 的回归通过 | 是否正确识别业务局部条件／脚本冲突留待真实语义验证 |
| A4 | 候选／revision／item／slice 闭合；incomplete／unknown 的重审范围可表达；既有流程参数绑定反例回归通过 | 无自动完整依赖分析；实际间接影响覆盖仍由 Agent 明确检查 |
| A5 | D1 在活动角色及 Skill 中落实；未完成重审可 deferred 并保存旧、新不可变候选引用 | 新定义过渡是 Agent 应用策略；本轮未执行真实业务跨 Batch 迁移或历史版本固定 |
| A6 | 复用后端 Batch 原子性、失败恢复及 Team 提交回归；新增目标绑定校验没有新增跨 Batch 原子性承诺 | live PostgreSQL 并发／跨 Ontology 实写场景未在本轮启用 |
| A7 | 可定位字段错误、旧候选引用拒绝；实际 staged submission 拒绝误 create 后修正成功；旧审批摘要／漂移回归通过 | 测试转发适配器不等于真实 apply／读回语义验收 |
| A8 | 实际 checkpoint 打包恢复后新／旧地图原始字节一致，owner／未完成重审保留；fork 宿主标记回归；真实成员／Key API 四种模式测试 | 新字段未重建恢复框架；真实 fork 数据复制沿用既有能力，未新作 live 验证 |
| A9 | 实际 CQ CLI Judge 组装只投影获准可见 IRI 的工作状态，Examiner 无协同上下文；私密名称／自由文本／数量不投影，地图摘要漂移拒绝 | 本轮为开发测试，非独立方对真实 run 的语义验收 |
| A10 | 未授权、未执行 | 待 R4.0-009 统一真实建模与独立语义验收；不得用上述机械／功能证据推导 L1 PASS |

## 合同、影响与运行检查

- 新 reference JSON、Task 配置、旧／新地图分派、角色输入和必要链接／格式检查通过；ontology-modeling Skill 的 `quick_validate.py` 返回 `Skill is valid!`。
- GitNexus 索引落后当前源码且部分返回符号乱码，不能声称当前代码具有完整图覆盖。最后一次 `detect_changes` 返回 medium，38 个已索引符号、4 条流程；未返回 HIGH／CRITICAL。结合当前调用点及 diff 核对实际影响：宿主身份 bootstrap、Project scope／read Key、活动 staged submission、地图校验／检查点及 Judge 组装。新定义复用已存在的显式资源 ID→IRI 合同并与实际授权读回匹配；没有重索引或扩展平台 API。
- 后端生产源码和前端未修改；后端增加测试。按仓库运行核对要求于 22:07:53（Asia/Singapore）重启 `ontology-platform.service`；unit active，`GET http://127.0.0.1:8001/api/health` 返回 `{"status":"ok"}`，前端 `http://127.0.0.1:5173/` 返回 200。没有 UI 改动，不要求新增 build／Playwright 轮次。
- 初次裸 `systemctl --user` 因当前进程未配置 user bus 返回 `Failed to connect to bus: No medium found`；确认 `/run/user/1000/bus` 后使用 `XDG_RUNTIME_DIR=/run/user/1000` 与 `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus` 完成状态／重启核对，非服务故障。
- 本轮工作属于实现、基础设施核对、方案复审及文档；真实语义建模用时为 0，符合本轮未授予真实运行的边界。未开展额外平台机制或建模 harness 扩建。

开发范围已完成；保留整体 PARTIAL、独立功能验收未执行与 A10 未执行，不将开发者自测写成独立验收。
