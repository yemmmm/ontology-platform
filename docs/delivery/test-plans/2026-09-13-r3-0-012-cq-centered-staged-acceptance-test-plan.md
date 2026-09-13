# R3.0-012 CQ 为核心的阶段验收 — 共享测试计划

- 日期：2026-09-13
- 状态：独立机械测试轮 Round 2 **PASS（机械层）**（2026-09-13，D1/D2 均关闭，见 §6）；隔离测试、
  真实 L0/L1、SQL、授权、清理复核仍 **NOT RUN**。历史：独立 Round 1 FAIL（D1/D2）、开发侧缺陷
  修复 Round 1、外部 Round 3 REVISE 后修订、独立计划评审 Round 4 专项复核 PASS、文档检查 PASS，
  记录均保留于 §6；开发侧任务 A–E 机械轮记录亦见 §6。
- 需求：[requirements-v3.0.md 的 R3.0-012](../../requirements/requirements-v3.0.md#r30-012-cq-为核心的阶段验收)
- 设计：[R3.0-012 交付设计](../designs/2026-09-13-r3-0-012-cq-centered-staged-acceptance-design.md)
- 相关测试基线：[R3.0-011 共享计划](2026-09-08-r3-0-011-competency-question-batch-acceptance-test-plan.md)、
  [R3.0-006 共享计划](2026-08-27-r3-0-006-real-modeling-e2e-acceptance-test-plan.md)。

## 1. 测试边界

本计划验证 R3.0-012 在 R3.0-011 已有 CQ 题池、freeze、`cq-acceptance`、v3 batch packet、
只读代理和报告路径上的最窄增量：

- `acceptance_target=full_joint|cq_semantic` 的选择、冻结和报告分流；省略值为 `full_joint`。
- 宿主从既有 run 状态、Batch/Attempt、receipt、回读、在途写状态和完整 Ontology 列表生成并
  验证最小 production handoff；不信任单独的 `ready`/`pending_writes` 布尔值。
- 在 checklist 仍为 pending 时，只要交接证据足够，`cq_semantic` 可以开始隐藏 CQ。
- 平台实际只读响应由 CQ proxy 新增的宿主留存回调保存，按既有 receipt 定位、校验后进入独立 Judge；Judge 不
  访问平台，不以 Examiner 自报答案或 IRI 代替真实响应。
- 部分批次保留已完成题的逐题裁决，未执行题保留在原始分母中；漂移、缺证和失败不会被缩小
  分母或改写为 PASS。

R3.0-013（各 Agent 上下文占用缩减）本计划不覆盖；它目前只登记待细化。R3.0-006 的 SQL
实际执行、完整语义授权专项、完整资源 lineage 覆盖、L2 Repeatability 与 L3 Productization
分别取证，CQ 结果不能替代这些结论。旧 R2.3 的逐题 fresh Examiner 合同与历史证据保持不变。

独立测试者不得创建、继续、修复被验收的生产 run，不修改保留 evidence，不使用历史 auth010/
auth011 的授权或资源。真实 run 仍需新的用户授权；本文件中的真实用例在本轮全部为 NOT RUN。

## 2. 状态和执行层级

| 层级 | 目标 | 本轮状态 | 通过含义 |
| --- | --- | --- | --- |
| 文档/合同 | 需求、设计、计划链接和字段口径一致 | 文档检查 PASS；独立计划评审见 §6 | 文档检查通过，不代表代码或运行通过 |
| T0 机械 | 参数、交接、绑定、packet、报告、错误和旧路径回归 | 独立机械轮 Round 2：四个套件通过（72/222/1636+预先存在 7 失败/1007+36），D1/D2 关闭（见 §6） | 单元/合同/fixture 证据通过 |
| I 隔离 | hidden、参考答案、tester-only、平台写能力和只读 scope 隔离 | NOT RUN | 正向和逃逸负例均通过 |
| L0 Runtime | 真实生产交接、只读 proxy、Examiner、Judge、前后状态和清理 | NOT RUN | 所选 scope 的运行链证据完整 |
| L1 CQ quality | 真实隐藏题回答与冻结依据逐题比较 | NOT RUN | 全部应验收题有效裁决且 CQ hard gate 通过 |
| L2/L3 | 重复性和产品化 | NOT RUN | 不属于 R3.0-012 前置 |

推荐的机械命令（实现完成后的独立测试阶段执行，当前不执行）：

```bash
uv run --project backend python -m pytest -q modeling_team/tests/test_r3012_*.py
uv run --project backend python -m pytest -q modeling_team/tests/test_r3011_*.py \
  modeling_team/tests/test_r30002_*.py modeling_team/tests/test_r30008b_*.py \
  modeling_team/tests/test_r30009_*.py modeling_team/tests/test_r23006_*.py
```

若实现没有按上述文件拆分，测试者应选择实际新增的窄测试模块，并在本计划追加执行命令和
结果；不得以 backend pytest 或静态检查单独代替 modeling_team 合同和真实 runtime 证据。

## 3. 用例矩阵

### T0 — 范围选择、冻结和兼容

| ID | 用例 | 预期 |
| --- | --- | --- |
| T0-1 | v3 Task 省略 `acceptance_target` | Runner 在 `run-contract.json` 记录 `full_joint`；既有完整验收路径行为不变 |
| T0-2 | v3 Task 显式选择 `acceptance_target: cq_semantic` 且同时启用 011 | 配置加载成功，快照写入选择值，`cq-acceptance` 使用 CQ scope |
| T0-3 | 未知值、非字符串值、未选 011 时选择 `cq_semantic` | 类型化拒绝；不产生 acceptance report，不消耗 semantic start |
| T0-4 | run 已 start、已有 issue 或已有 handoff 后改 scope | 拒绝修改；原 run 的 scope、freeze 和历史报告保持不变 |
| T0-5 | `acceptance_mode=read-only-acceptance`、`blind_status` 与 `acceptance_target` 同时出现 | 三者分别校验和记录，不相互覆盖或混用 |
| T0-6 | `full_joint` 回归 | 仍经过既有通用 terminal、SQL、授权和完整联合验收门；不因新增 scope 放宽 |
| T0-7 | 旧 R2.3 Task/Profile/run root 调用新入口 | 被 selector/版本合同拒绝；旧逐题 fresh 路径和历史 evidence 不变 |
| T0-8 | CQ scope report、full joint report、R3.0-006 交付状态同时存在 | 报告分别命名和汇总；CQ PASS 不被转换成 R3.0-006 full PASS |
| T0-9 | 旧 continuation carrier 的顶层 `acceptance_scope` 对象，与新 Task `parameters.acceptance_target` 分别加载 | 旧 carrier 字节/结构/验证不变；不展平合并、不推导新枚举；草案 `parameters.acceptance_scope` 不作为新选择器别名 |

### T1 — 最小 production handoff 和就绪判定

| ID | 用例 | 预期 |
| --- | --- | --- |
| T1-1 | 完整获批 Ontology 集合、每项 state、Batch/Attempt/receipt/readback/validation/reasoning 均闭合，checklist 为 pending | `cq_semantic` 可以开始；handoff 记录 checklist pending，不等待七项 PASS |
| T1-2 | handoff 只有 `ready=true`、`pending_writes=false`，缺少来源和 digest | 类型化拒绝；修改布尔值不能绕过 |
| T1-3 | 任一已声明 applied 的 Batch 缺 receipt、合法 dry-run、Attempt/权威回读或状态冲突；另设历史失败已成功重验对照 | 不闭合时不交接；历史失败已被修正不阻断，原始失败记录保留 |
| T1-4 | 一个获准 Ontology 从 handoff/model binding 中漏掉，或出现未授权 Ontology | 拒绝；绑定集合必须覆盖完整交付集合且不含越权项 |
| T1-5 | 生产 Agent 处于 `blocked`，但其阻断是已知 terminal 包装问题，所有写入状态确定且无在途操作 | 可按 partial/blocked-safe 交接，并记录阻断原因；不把 blocked 一律视为 ready |
| T1-6 | 生产 Agent 处于 `blocked`，存在 unknown write、实际在途写或未知 apply 结果 | 不可开始 CQ；闲置有效 lease 对照可继续，不把未知写入当作已知未应用 |
| T1-7 | 已知部分 item `not_applied`，但 applied 部分有确定回读 | 可以使用完整 hidden 分母取证，报告记录 partial delivery 和未应用项；不能缩小题集或声称完整模型交付 |
| T1-8 | 实际在途 mutation、未排空 stdout/io lock；对照纯终态 advisory issue/无写状态消息 | 不确定写与未排空调用不交接；纯 advisory 不阻断，保留 I/O 防护 |
| T1-9 | 生产状态、handoff run/freeze digest 或 task/profile digest 不一致 | 类型化拒绝；不继续执行只读 batch |
| T1-10 | handoff 在开始后被替换或旧文件被修改 | digest/来源校验失败；不覆盖原 handoff 或旧报告 |
| T1-11 | 以线程同步点分别构造 staged batch/evidence mutation 先准入、handoff 先切 quiescing；再覆盖已返回但 unknown write | 同一 run 锁/condition 统一准入；先准入写在途未归零或结果未知均不得发布 handoff，后到写可恢复拒绝；无持锁等网络/永久死锁，验收期间生产静默 |
| T1-12 | 生产 roster 全终态但 CQ 验收尚未交回；随后交回完整/部分结果或用户 stop | 正常情况下保留验收所需凭据与代理至结果回交，不提前 cleanup；stop 可立即中止；部分结果也能正常收尾 |
| T1-13 | 真实前台 FIFO 分派 `cq_acceptance_complete`；无 LLM 输出但 acceptance_pending，随后正常/partial/failure 回交 | 两个 action 集与 Runner handler 均可达；主循环继续接收消息，无生产派发/提前 terminal/无输出 T3 误杀；三种结果都经相同 cleanup_once 收尾 |
| T1-14 | stale run/freeze/attempt、未登记 attempt、伪造 report digest/verdict、含隐藏文本或自选路径；对照合法重复消息 | 非法可恢复拒绝，不收尾不污染当前结果；合法完整 envelope 按固定报告校验，相同重复消息只确认 |
| T1-15 | CLI 退出无完整报告、CLI 失败、完成消息暂缺、Delivery 失联及用户 stop | Delivery 对 CLI 失败保留 incomplete 报告后回交；暂缺显示 pending 不伪造 PASS；失联保留可观察状态与 stop/宿主退出，不承诺自动恢复；清理不重复且保留部分证据 |
| T1-16 | 注入 monotonic clock：生产 active 为 10799 秒时成功 handoff，pending 再跨 10800 秒墙钟，期间无 LLM 输出；正常回交后推进 active 到阈值 | handoff 成功即打开验收等待窗口，pending 持续轮询且不 latch/cleanup；关闭后保留已扣等待，生产 active 不清零/不补算等待，原超时仍在真正 active 到阈值时生效；full_joint 对照不变 |
| T1-17 | acceptance wait 与 review/handoff/issue 等待重叠、重复完成消息、stop 和异常退出 | 重叠区间只扣一次，新窗口 kind 通过既有闭集校验；退出时关闭窗口且保留累计证据，无残留等待/重复清理或全局禁用 T3 |

### T2 — 模型绑定、Evidence 和真实响应

| ID | 用例 | 预期 |
| --- | --- | --- |
| T2-1 | pre/post binding 覆盖每个获准 Ontology 的 Project、workspace、graph、授权工具和状态 digest | packet scope 完整闭合；无缺项即可启动 |
| T2-2 | 对本批实际引用的资源只改 Evidence association/原文、等量替换引用，workspace/graph revision 不变 | 本批初读与收尾回读的语义投影识别 drift；不只比数量，不新增全库摘要接口 |
| T2-3 | 实际引用的 evidence/lineage 回读不可用；对照仅请求 ID、耗时、排序噪声变化 | 前者标记 runtime incomplete，不声明稳定；后者不误报语义漂移 |
| T2-4 | Platform Examiner 试图访问 reference answer、answer_points、tester-only 文件或生产历史 | packet/隔离拒绝；内容不进入 Examiner 上下文或 report |
| T2-5 | Examiner 使用授权 `platform_read_proxy` 查询并返回 receipt locator | host 校验 tool、ticket、model state、request/response digest、artifact path、page chain 后才交 Judge |
| T2-6 | child 提交绝对路径、`..`、根外/伪造 artifact、不存在文件、错误 digest/scope；对照合法 Runner 相对 locator 与跨题复用 | 前者拒绝；后者校验后可复用；宿主内部绝对路径解析不扩大 child 路径合同 |
| T2-7 | 真实 response artifact 与 `response_digest` 不一致，或 response 不含支撑答案的必要语义事实 | 分别记录 artifact/runtime failure 或 `model-recall-insufficient`；不得把参考答案相等当成 PASS |
| T2-8 | Judge packet 包含校验后的必要 response bytes/投影、原 digest、request/tool/page binding | Judge 无平台 key/读代理/写接口，能够只按 packet 对照实际响应与冻结依据 |
| T2-9 | 实际平台业务语义与冻结获批原文相符，但资源因技术结构三元组无注释而 evidence_status=missing | 必要业务主张可核对时允许 CQ PASS，结构缺口 advisory；原始 missing 不改写 |
| T2-10 | 必要业务事实缺少实际查询或获批来源支持，或 Agent/host/Judge 虚构 `supported` | 该题不可 PASS；后端 Evidence 状态和原始缺口原样保留 |
| T2-11 | Examiner 使用 raw schema、答案包、数据库样例或自然语言常识替代平台只读查询 | 隔离/判定失败；不得生成有效 CQ 证据 |
| T2-12 | read proxy 请求超出授权 Ontology 或包含写工具 | 请求拒绝；不扩大 scope、不写平台、不产生 CQ PASS |
| T2-13 | 全量/不存在断言需要的分页未完成；对照已返回单项事实足够支持该题但无关页仍截断 | 前者不能证明完整/不存在；后者由 Judge 按所需证据判断，警告原样保留，不建立所有查询必须无截断的门 |
| T2-14 | 成功查询后 child teardown；对照留存失败、仅有逻辑 locator、envelope 格式变化 | 成功路径仍能读取留存的规范化请求/result，按既有 canonical 算法校验摘要；失败不能取得有效证据，不能误用整文件 hash |

### T3 — 逐题判定、部分批次和覆盖

| ID | 用例 | 预期 |
| --- | --- | --- |
| T3-1 | 全部 hidden 题均返回有效 `completed` report，响应和 Judge verdict 全部闭合 | 逐题 PASS 后才可产生完整 CQ PASS（其他硬门也须通过） |
| T3-2 | 前几题有效，后一题 `runtime-incomplete` 或无 report | 已完成题交 Judge；后一题留在 `unexecuted`/失败集合；整批不 PASS |
| T3-3 | 单题平台语义不足，但后续题仍可查询 | 该题为 `model-recall-insufficient`，后续题继续；不终止或缩小分母 |
| T3-4 | 所有题已执行且除一题外均 pass，该题 frozen reference 与批准材料冲突、关键歧义或材料不支持 | 该题为 `question-answer-review`；即使没有未执行/运行失败题，整批仍不得 PASS，不归因 modeling-quality、不抹掉题目 |
| T3-5 | 冻结答案明确 `unknown`，Examiner 保留 unknown 且无冲突支持事实 | Judge 可判 PASS；补猜为确定事实不得 PASS |
| T3-6 | Examiner 幻觉、使用未返回资源、把缺失当确定或捏造映射 | Judge 判不通过并保留实际 response/locator；不得接受与答案文字相似的幻觉 |
| T3-7 | 获批 hidden 为空，或运行时遗漏获批题/承诺的切片覆盖、事后缩题集 | 保留空集/真实缺口，不发完整 CQ PASS；不把空集伪装成已有语义证据，也不终止可继续的生产流程 |
| T3-8 | hidden 题曾暴露给生产角色后再冻结/验收 | 标为 non-blind regression 或拒绝；该题/整批不能取得 blind full PASS，暴露证据保留 |
| T3-9 | post-batch workspace、graph 或 evidence/lineage 状态漂移 | 已有 Examiner/Judge 报告保留；该批完整 PASS 取消；不能复用旧 binding |
| T3-10 | post-batch state read 失败 | 已有逐题报告保留；记录 `runtime/infrastructure`，不生成有效完整 PASS |
| T3-11 | 已完成题与未执行题混合时建立 Judge packet | packet 只含 host 已校验的有效题；未执行题仍在完整 hidden 分母中，不用空 answer 或 unknown 假装完成 |
| T3-12 | 同一 `batch_id` 重复只读验收 | 使用新的 child session/host attempt 目录；旧 `batch-report.json` 不被覆盖；路径冲突类型化拒绝 |
| T3-13 | 合法空查询、`unanswered` 语义缺失与服务故障三类对照 | 前两类交 Judge 判断允许的 unknown/模型召回不足，服务故障记运行未完成，不把语义失败算未执行 |
| T3-14 | 交付部分模型但全体 hidden 均获有效 PASS；对照只有部分题通过 | 前者可 CQ PASS 且 model_delivery=partial/full_joint未通过；后者保持批次 PARTIAL，分母不变 |
| T3-15 | 某切片零专属 hidden 题但被跨切片题覆盖；或用户冻结前明确批准本批排除该切片，获批题集非空 | 不因题数为零拒绝；获批题集全 pass 可发该批 CQ PASS。真正被排除的场景覆盖单列未覆盖，不能声称全场景隐藏覆盖通过；运行后追认排除不能洗绿 |
| T3-16 | 原题要求数据库实际数值，本阶段只取得正确指标口径/映射，未执行 SQL | 原题 `question-answer-review`、layer=null、note 标记 `sql-result-outside-cq-scope`，保留已有语义证据与分母；整批不 PASS，其他题继续，不记模型/基础设施故障 |
| T3-17 | 可直接查询的业务阈值/时限数值；冻结前获批的独立口径题；验收后擅删原题数值要求 | 前两类按普通四态和真实查询证据可判 pass，SQL 结果仍另记未验收；后者拒绝旧 freeze 改写，须用户批准新版本，不自动新增第五态 |
| T3-18 | 前次 attempt 失败后新 attempt 成功；两次并发占用同一目标；对已发布 batch report 再次写入 | 旧报告/原始响应/receipts/handoff/清理证据逐字节不变，最终报告只发布一次；冲突可恢复登记新 attempt，不能借原子 replace 覆盖 |

### T4 — 只读、隔离、清理和停止

| ID | 用例 | 预期 |
| --- | --- | --- |
| T4-1 | `cq-acceptance` 运行期间检查 StartLedger 和 semantic start 计数 | 无写入、无新 semantic start、无生产 run continue/repair |
| T4-2 | Examiner/Acceptance 尝试 Team Transport、平台写工具、创建或修复生产 run | 能力不存在或被拒绝；不改变模型 |
| T4-3 | hidden question、answer_points、参考答案和 tester-only 真值检查 source/bind/message/log/history | Examiner 可见 hidden 题干而不可见答案/依据包/生产历史；Judge 可见冻结答案、获批原文和实际查询响应；生产角色仅见公开投影，tester-only 不混入任一未获准输入 |
| T4-4 | 直接连接数据库、读取 raw schema 或 SQL 结果 | 不被当作语义授权或 CQ 证据；SQL 状态另记，RDF 仍不复制业务行 |
| T4-5 | 用户在 Examiner/Judge 运行中 stop | 只停止本批 child/proxy，保留 run、已写资源、reports、receipts 和失败写入证据，不自动追加 start |
| T4-6 | child/proxy 正常完成或异常完成后的清理 | 本次拥有的 key/socket/child/private temp 按既有策略清理；保留 report、receipt、drift、failure evidence |
| T4-7 | cleanup/retry 重复执行或旧 report 目录存在 | 幂等或明确拒绝，不删除无法证明归属的保留资源，不覆盖历史结果 |
| T4-8 | full_joint 与 cq_semantic 并行/相邻执行 | 各自 scope、batch、attempt 和报告边界清楚；一个 scope 的结果不改写另一个 scope |

### T5 — 真实 L0/L1 验收

| ID | 用例 | 预期 |
| --- | --- | --- |
| L0-1 | 在新的用户授权下，以固定 Task/Profile/Scope 启动 `cq_semantic`，按 verified handoff 进入 CQ | 记录 run、scope、freeze、handoff、pre/post binding、proxy receipts、child cleanup 和报告；不复用历史授权 |
| L0-2 | 真实 Platform Examiner 使用授权只读 proxy 完成可继续的隐藏批次 | 每题报告真实落 sink；一题失败不阻塞后续题；未执行题和第一阻塞层可核对 |
| L0-3 | 真实 Acceptance Judge 只消费冻结依据和 host 校验后的 response packet | 逐题 verdict、evidence refs、drift、coverage 和 cleanup 完整；Judge 未访问平台 |
| L0-4 | 真实只读查询前后模型/evidence 状态保持稳定 | 才具备有效完整 PASS 资格；状态漂移或重验失败保持 PARTIAL/BLOCKED |
| L0-5 | checklist pending、通用 terminal 未 PASS，但最小交接已验证 | CQ 可以开始；报告明确完整 joint checklist/terminal 未验收 |
| L1-1 | 真实隐藏题按获批全景/切片覆盖决定取证，答案含关系、规则、值或映射 | 每题对照冻结依据；缺证不能 PASS，不强制每切片独立题数；批准排除保留且不宣称全场景隐藏覆盖 |
| L1-2 | 真实题目/参考答案错误或关键歧义 | 判为 `question-answer-review` 并保留依据；不将题目问题计为模型质量失败 |
| L1-3 | 真实模型缺关系/规则/值语义/映射 | 判为 `model-recall-insufficient`；其余题继续，CQ 整批按完整分母判定 |
| L1-4 | 真实 partial applied | 披露实际未应用项与模型缺口；完整 hidden 仍执行，CQ结论与模型交付分开，不能解释为完整模型交付或 R3.0-006 full PASS |
| L1-5 | 真实 evidence-only 改变 | 前后 binding 识别漂移，报告保留但不得沿用旧完整 PASS |

T5 需要真实服务、真实模型、用户授权和独立测试交接；本轮不执行，不能用 fixture 或 mock
结果填充 L0/L1。

## 4. 判定规则

`cq_semantic` 完整 PASS 的必要条件是：

1. scope、run、freeze、完整获准 Ontology 集合和 verified production handoff 闭合；
2. 无 unknown write、在途写入、未授权读取、scope 漂移或前后 model/evidence drift；
3. Platform Examiner 与 Judge 的职责隔离和 response receipt 绑定成立；
4. 所有 hidden 题均有有效裁决，无未执行、待复核、模型召回不足或 runtime incomplete；
5. 无空 hidden 集、遗漏获批题/承诺覆盖或 hidden exposure；事先获批排除单列，不是实际漏题，
   批次 PASS 不代表被排除切片已验收；
6. 每个必要业务主张由实际平台响应和可核对获批业务来源支撑，所需 Evidence/Lineage 如实保留。

已完成题的逐题 PASS 可以出现在 partial report 中；它不抵消未执行题、漂移或必要业务缺证，
也不缩小整批分母。`full_joint` 仍按 R3.0-006 的完整三层通过门判定。文档检查、T0/I、L0、
L1、SQL、授权、L2/L3 分开报告。

failure layer 只使用 `modeling-quality`、`platform-contract`、`collaboration/routing`、
`runtime/infrastructure`；`question-answer-review` 是题目状态，不是第五种平台失败层。

## 5. 本轮结果和后续记录规则

- 设计和本计划：修订完成，独立计划评审 Round 4 PASS，历史与处置见 §6。
- 代码实现：任务 A–E 已在工作区完成（基线 `c18e8e1`，未提交；范围见 §6 实现轮记录）。
- 机械测试与回归：开发侧机械轮已完成（见 §6）；结果仅证明机械合同，不构成语义 PASS。
- 独立测试轮：机械轮 Round 1 完成（2026-09-13，独立 `requirement_tester`）：四个机械套件全部
  复现开发轮结果，抽查的判定边界在产品代码真实编码；但 T3-18 并发占用条款被证伪（D1，
  Medium），另有 T0-5 覆盖声明不实（D2，Low），本轮总体 **FAIL**，详见 §6。
- 缺陷处置：D1、D2 均经独立机械轮 Round 2 复测关闭（FIXED，见 §6）；Round 1 失败记录保留。
- 隔离测试、真实 L0、真实 L1、SQL、授权、清理复核：NOT RUN。
- 后续每一轮测试追加日期、代码基线、命令、结果、失败用例、证据路径、缺陷处置和重测结果；
  不删除失败轮次，不把文档 PASS、代码测试 PASS 或宿主自评写成语义 PASS。
- 计划评审、开发和独立测试由主代理分别交接；本文件不预先填写不存在的测试证据。

## 6. 本轮文档交付记录

### 文档检查 Round 1（2026-09-13）

- 范围：权威需求、交付设计、共享测试计划；代码基线 `bf5ab85`，仅文档增量。
- `git diff --check`：PASS。
- 只读 Node 文档检查：3 个文件、24 个本地链接及其 Markdown 锚点均存在；代码围栏配对，
  R3.0-012/013 需求标题唯一，PASS。
- 主代理源码核对纠正响应留存假设：现有 proxy 有 receipt/逻辑 locator，但没有在 `handle`
  落盘响应；设计增加 CQ scope 留存回调，保留相对 locator 与 canonical result digest，
  测试计划新增 T2-14。此为设计修订，不是产品缺陷已修复或真实证据已留存。
- 本轮未执行产品代码、隔离、L0/L1、SQL 或授权测试；未启动、恢复或修改任何真实 run。

### 独立计划评审 Round 1（2026-09-13）

- 评审者：独立 `plan_review`；结论 **REVISE**，两项 High，主代理均确认。
- H1：handoff 与 CapabilityBroker 写入跨线程，原设计缺明确原子准入。已在设计 §4.4 增加
  本 run 共用锁/condition、quiescing 和在途调用登记，等结果确定后发布 handoff；T1-11 覆盖
  两种竞争顺序、unknown write 与死锁边界。不新增通用协调框架。
- H2：当前 Runner 没有完成 action、pending 生命周期与独立 CLI 回交接线。已明确 host-only
  envelope、既有 FIFO/action 注册、Runner 登记 attempt、pending 主循环与 T3 等待口径、
  Delivery 监看子进程并回交，以及正常/partial/failure/stop 的唯一 cleanup；T1-13～15 覆盖。
- 以上为设计修订；代码仍未修改。修订后提交同一评审者专项复核，结果见下轮。

### 独立计划评审 Round 2（2026-09-13）

- 同一独立评审者仅复核 Round 1 H1/H2：**PASS**，两项均关闭，无残余 Critical/High。
- H1 关闭依据：设计明确原子准入、在途登记、锁外执行、unknown-write/receipt 重验；T1-11
  覆盖两种竞争顺序与未知写入。
- H2 关闭依据：完成 envelope、action/FIFO/handler、attempt、pending 主循环与结果回交、
  partial/failure/stop 收尾已接线到具体改动面；T1-12～15 覆盖对应生命周期。
- 主代理接受复核结论；本轮是计划评审，不是代码测试或真实语义验收。后续实现和独立测试
  仍使用本文件，所有产品用例保持 NOT RUN。

### 文档收口检查（2026-09-13）

- 修订后重查 3 个文件的 24 个本地链接/锚点与围栏：PASS；需求、设计、测试计划状态一致。
- `git diff --cached --check`：PASS。暂存范围仅本需求的三个文档，未纳入其他工作区改动。
- GitNexus `detect_changes(scope=staged)`：3 个文档、0 个受影响执行流程、low 风险。
- 本轮无需 backend/frontend 测试或服务重启，未清理真实资源，未消费任何建模额度。

### 外部评审 Round 3 与主代理处置（2026-09-13）

- 输入：用户提供另一审阅 Agent 的 **REVISE**。核对基线 `ba6df9e`，仅文档修订，
  原 Round 1/2 结论和证据保留，不视为新修订已获复核。
- 源码核实：`runner.py::_check_run_fallback_timeout` 默认 10800 秒且只扣既有等待，
  `cq-handoff-request` 在成功时关闭；`__main__.py` 同 batch 目录可复用且 writer 使用
  `os.replace`；`ScopedReadProxy.handle` 仅生成 receipt/locator，Judge packet 未带留存响应。

| 外部项 | 主代理判断 | 正文与同步修订 | 计划覆盖 |
| --- | --- | --- | --- |
| H1 验收等待生命周期 | accepted-high：正文缺少可验收义务，当前交接窗口不覆盖验收 | 功能合同 8：pending 窗口、T3 扣时、轮询、结果绑定和退出；设计 §4.4 明确窗口切换 | T1-12～17 |
| H2 报告不可覆盖 | accepted-high：原文泛指历史 verdict 不足以约束实际报告文件 | 功能合同 9：唯一 attempt、最终报告首次发布、冲突可恢复、所有旧证据不覆盖 | T3-12/18、T4-7 |
| H3 真实响应不可伪造 | accepted-high：结果描述不能替代可信来源与核验合同 | 功能合同 3：读时留存、receipt/digest/scope 校验、拒绝自报 locator；设计 §4.1 对齐 | T2-5～8/14 |
| 同名 acceptance_scope | downgraded-low：旧 carrier 顶层与新 Task 参数是不同 envelope，未证明直接类型冲突；代码只核 envelope 闭集，不能声称已验证对象每个子键 | 未实现的新字段改名 acceptance_target；旧 carrier 不迁移、不展平、不设草案别名 | T0-9 |
| B1 PASS 尾句矛盾 | accepted-high：尾句确会错误放过 review/语义失败，不能由前句抵消 | 删除“只有 partial batch 才阻断”，明确所有非 pass 均阻断 | T3-3/4、判定规则 |
| B2 零隐藏题与覆盖 | accepted-medium：原 T3-7 把建议题数提升成硬门 | 功能合同 5 与设计 §3.3 区分获批覆盖排除、跨切片覆盖和实际漏题；批次与全场景分开 | T3-7/15、L1-1 |
| B3 数值题裁决 | accepted-medium：原题结果证据未闭合而无状态，需补合同 | SQL 结果不在本阶段时记 question-answer-review，layer=null，note 标明范围原因；不改四态 | T3-16/17 |
| B4 准入活性 | accepted-medium：设计已具备，但正文仅不变量不足 | 功能合同 2：两入口共用原子准入、不持锁等网络、可恢复、stop 通路 | T1-11 |
| B5 012 完成门归类 | accepted-low：非全量前置的意图未显式写出 | 版本 §6：012 为可选阶段能力，不加全量完成门；选择后须满足自身实现/独立测试/L0/L1 合同 | 文档合同检查 |

- 用户引用的 continuation 示例未在当前根目录找到；旧 carrier 字段由源码及
  `test_r23005_mechanical_spine.py` 的对象 fixture 证实，不据此推断根目录缺失文件的具体内容。
- 本轮不重启服务、不执行建模/验收、不更改产品代码或 R3.0-013 登记范围。修订后进行专项
  独立计划复核；产品用例全部仍为 NOT RUN。

### 独立计划评审 Round 4（2026-09-13）

- 评审者：独立 `plan_review`；限定复核外部 Round 3 九项处置，结论 **PASS**，无残余
  Critical/High、无待主代理确认的关键假设。主代理接受该专项结论。
- H1/H2/H3 的等待、保留、响应可信链义务已进入权威正文并有设计/测试映射；新旧参数、
  PASS 条件、获批覆盖排除、数值题四态、准入活性与版本完成门已在三份文档中对齐。
- 本轮没有运行产品测试，不代表代码实现、L0/L1 或完整联合验收通过。

### 修订后文档检查 Round 2（2026-09-13）

- 基线 `ba6df9e`，仅三个归属文档变更；R3.0-013 登记内容保持不变。
- 文档链接/锚点/围栏检查：3 文件、24 个本地链接，0 错误；正文九项关键义务存在性检查通过。
  关键词检查只辅助核漏，合同正确性由本轮逐项核对与独立专项评审证明。
- `git diff --cached --check` PASS；GitNexus 暂存变更检查仅三个文档、0 受影响执行流程、low 风险。
- 无产品测试、服务重启、真实运行或授权消耗；其他未提交文件不纳入本次提交。

### 开发侧实现与机械回归 Round 1（2026-09-13）

- 代码基线 `c18e8e1` 加未提交工作区；实现范围（任务 A–E）：`modeling_team/contracts.py`
  （acceptance_target 参数合同）、`modeling_team/runner.py`（最小生产交接、共享写准入/排空、
  verified handoff 发布、完成回交通路与等待窗口）、`modeling_team/acceptance_runtime.py` 与
  `modeling_team/runtimes/codex.py`（读时响应留存 seam 与 observables）、
  `modeling_team/__main__.py`（v012 handoff 消费、§4.3 逐题判定、attempt 唯一报告目录、
  evidence_recheck 投影、SQL 范围外裁决说明）、`modeling_team/competency_questions.py`
  （full-pass 判定覆盖门）。
- 新增 5 个机械测试文件：`test_r3012_contracts.py`（T0-1..T0-5、T0-9）、
  `test_r3012_handoff.py`（T1 准入/quiesce/handoff 子集）、
  `test_r3012_platform_responses.py`（设计 §4.1/§4.2 留存、receipt 校验、recheck、投影）、
  `test_r3012_completion.py`（T1-12..T1-17 完成回交子集）、
  `test_r3012_partial_judging.py`（T3-2/T3-4/T3-11/T3-12/T3-13/T3-16/T3-18）；
  另更新 3 个 011 测试文件的期望（tuple 返回、逐题 skip、隐藏序 executed、tg47 judge 运行）。
- 命令与结果（仓库根）：
  - `uv run --project backend python -m pytest -q modeling_team/tests/test_r3012_*.py`
    → 68 passed。
  - `uv run --project backend python -m pytest -q modeling_team/tests/ -k "r3012 or r3011"`
    → 218 passed。
  - `uv run --project backend python -m pytest -q modeling_team` → 1632 passed / 1 skipped /
    331 subtests passed；7 failed 全部位于 `test_deepseek_codex_runtime.py`（fallback 文件
    权限/畸形用例，已在干净 HEAD 上复现确认预先存在，与本需求无关）。
  - `cd backend && uv run pytest -q` → 1007 passed / 36 skipped。
- GitNexus `detect_changes(scope=compare, base=main)`：12 文件、117 符号、5 条受影响执行流程
  （均在 `main`→`_run_cq_acceptance` 派发链内），medium 风险，无 HIGH/CRITICAL。
- 本轮边界：仅开发侧机械测试；未运行隔离测试、真实 L0/L1、SQL、授权或清理复核，未重启服务
  （未触及 backend 运行时代码），未创建/恢复/修改任何真实 run，read key/凭据不落任何输出面。
  本轮 PASS 只代表机械合同通过，不写成语义 PASS；独立测试轮仍待执行并单独追加记录。

### 独立测试 Round 1 — 机械（2026-09-13）

- 测试者：独立 `requirement_tester`；仅 T0–T4 机械项。隔离、真实 L0/L1、SQL、授权、清理复核
  本轮仍 NOT RUN（真实 run 需新用户授权，未使用任何历史 auth010/auth011 授权或资源）。
- 代码基线：`c18e8e1` + 未提交工作区（任务 A–E 实现与 5 个新测试文件，与开发轮记录的
  `git status` 一致）。本轮未提交、未回退、未修改任何产品代码或既有测试。
- 套件复跑（仓库根，四项全部复现开发轮结果）：
  - 5 个 r3012 机械文件 → 68 passed。
  - `modeling_team/tests/ -k "r3012 or r3011"` → 218 passed。
  - `modeling_team` 全量 → 1632 passed / 1 skipped / 331 subtests passed；7 failed 全部位于
    `test_deepseek_codex_runtime.py`（fallback 文件权限/畸形用例，失败集合与开发轮记录逐例一致；
    按主代理交接不调查不修复，测试者未另行在干净 HEAD 独立复现，采信为预先存在）。
  - `cd backend && uv run pytest -q` → 1007 passed / 36 skipped。
- 超出绿灯的合同抽查（对照本计划用例行核对断言与产品代码锚点）：
  - T3-2/T3-11/T3-13：`test_r3012_partial_judging.py:161`（judgeable 只含已执行且带 host 校验
    响应的题：questions/examiner_reports/platform_read_responses 三处一致，:179-186）、
    :198-201（executed 含 `runtime-incomplete` 的已执行服务失败，unexecuted 仅无报告题）、
    :218/:248-249（unanswered 带成功查询证据与合法空查询均可判，语义缺失不并入未执行）；
    产品锚点 `modeling_team/__main__.py:1617-1622`（executed/unexecuted 语义）、
    `:1703-1742`（四类 skip 原因的 judgeable 划分）、`:1780-1795`（Judge packet 仅带
    judgeable 题的响应投影）。
  - T3-4/T3-16：`test_r3012_partial_judging.py:256-287`（全部题已执行且无生命周期错误，单个
    `question-answer-review` 仍阻断整批 PASS，`failure_layer=null`、note=
    `sql-result-outside-cq-scope`，Judge 角色说明含该标记）；产品锚点
    `modeling_team/competency_questions.py:1597-1665`（full-pass 分母=executed+unexecuted、
    任一非 pass 裁决阻断、pass 裁决需 host 校验响应、drift/不可回读阻断、空 hidden 集阻断）。
  - T3-12/T3-18（顺序部分）与 handoff 绑定：`test_r3012_partial_judging.py:373-395`（attempt
    唯一目录、attempt 保留 handoff 副本、无 batch 级报告）、:398-438（同 attempt 重跑为类型化
    `cq_handoff_immutable` 冲突，旧报告/handoff 副本逐字节不变，新 attempt 可恢复）、
    :441-486（提交 handoff 必须等于 Runner 发布记录；未落定/未知写/目录不匹配均类型化拒绝且
    不产生任何报告目录）；产品锚点 `modeling_team/__main__.py:1363-1368`、`:1413-1420`。
  - T2-5/T2-14：`test_r3012_platform_responses.py:132-172`（真实 `ScopedReadProxy` 读时留存
    规范化请求/result，canonical digest 重算，0600/0700，无 key/token/socket 落盘）、
    :217-234（teardown 后重排格式仍按解析内容校验 digest，非整文件 hash）、
    :175-203（留存失败可观察、不追加 receipt，故不能成为证据）、:207-214（locator 逃逸拒绝）。
  - T2-6/T2-7/T2-8：`test_r3012_platform_responses.py:318-352`（同 receipt 跨题复用合法、
    分页/截断标记原样保留）、:355-397（绝对路径、`..`、伪造 locator、不匹配 digest、越权
    tool、形状漂移全部类型化拒绝）、:399-423（缺 artifact 与篡改 result 均无证据价值）、
    :543-563（无 host 校验响应时 pass 裁决失效；drift/不可回读阻断整批）、:606-631（Judge
    packet 投影六字段闭集，无 request 字节/绝对路径，写工具与畸形输入抛 `ChildRuntimeError`）、
    端到端 :847-898（Judge 收到的投影与报告投影一致）。T2-7 的 `model-recall-insufficient`
    语义判定侧属 L1，本轮机械面仅覆盖缺证 fail-closed 与 artifact/runtime 失败侧。
  - 相邻回归：3 个 011 测试文件的期望更新经 diff 核对为设计 §4.3 的逐题化重定位（judge
    evidence 失败从整批 lifecycle error 改为逐题 skip、tg47 已落盘报告可判且清理计数 1→2、
    闭集 action 增加 `cq_acceptance_complete`），未削弱既有判定边界，`full_pass` 失败断言保留。
- 缺陷（本轮发现，未修改产品代码，修复归开发侧）：
  - **D1（Medium，T3-18 并发占用条款证伪）**：两个写入方并发占用同一 attempt 时，后完成者经
    `os.replace` 静默覆盖先发布者的 `batch-report.json`，违反功能合同 9 与设计 §4.5「已发布
    路径不得被 `_write_host_only_json` 的 `os.replace` 覆盖」。产品锚点：
    `modeling_team/__main__.py:1413-1419`（仅准入时 `exists()` 检查 + `mkdir(exist_ok=True)`）
    → `:1910` 最终写经 `_write_host_only_json`（`:2178-2186`，`os.replace` 无条件替换目标，
    临时文件名 `batch-report.tmp` 亦为共享路径）；legacy 路径 `:2014-2024` → `:2146` 同类。
    检查与写入之间隔着整个批次运行窗口（准入 → examiner/judge → 发布）。复现（机械、仅在
    /tmp、脚本已清理）：用 012 测试夹具驱动真实 `_run_cq_acceptance`，在 examiner 会话期间向
    attempt 目录写入第三方已发布报告字节（模拟另一进程在双方均通过准入检查后完成发布），
    CLI 结束时无 `cq_handoff_immutable` 冲突，第三方字节被替换（观察输出：
    `process-B published bytes survived: False`，退出码 1）。既有测试只覆盖顺序重跑（正确
    拒绝）。建议：最终报告首次发布改为排他创建（如 `O_CREAT|O_EXCL` 的占位/最终文件）并在
    发布时复查，补并发交错的机械用例。
  - **D2（Low，T0-5 覆盖声明不实）**：`test_r3012_contracts.py` 文件 docstring 与开发轮 §6
    记录均声称覆盖「T0-1..T0-5、T0-9」，但该文件及全部 011/012 测试中没有任何
    `acceptance_mode=read-only-acceptance`、`blind_status` 与 `acceptance_target` 三字段共现
    的校验/记录测试（grep 证实；`acceptance_mode` 在产品代码中为报告常量
    `modeling_team/competency_questions.py:42/1539`，与 Task 参数结构上正交，当前无相互覆盖
    路径，但 T0-5 回归锁缺失）。建议补共现机械断言并更正两处覆盖声明。
- 本轮边界：未重启服务（未触及 backend 运行时代码）、未创建/继续/修复任何生产 run、未修改
  保留 evidence 或历史冻结/verdict、未消费建模额度、未提交任何变更。
- 本轮结论：四个机械套件全部复现通过；抽查的判定边界（executed/unexecuted、review 阻断、
  顺序不可覆盖、handoff 等于 Runner 发布记录、留存响应与 Judge 投影校验）除 D1 所涉并发条款
  外均在产品代码真实编码。因 D1 证伪 T3-18 并发占用条款，本轮总体记 **FAIL**（机械层；非语义
  结论，机械通过亦不写成语义 PASS）。建议主代理安排开发侧修复 D1、处理 D2 后进行第二轮独立
  复测（优先 D1 修复验证与受影响回归）。

### 开发侧缺陷修复 Round 1（2026-09-13，独立测试 Round 1 D1/D2 处置）

- D1 修复（T3-18 并发条款）：`_write_host_only_json` 增加 `immutable=True` 排他发布——内容写
  入每进程唯一临时名后经原子硬链接（`os.link`）发布；目标已存在（另一进程在本命令准入检查后
  抢先发布）时抛类型化 `cq_handoff_immutable`，不替换任何字节。临时名从共享的
  `batch-report.tmp` 改为每进程唯一，并发双方的暂存字节亦不再互踩。两处报告首次发布（执行路径
  `_cq_execute_batch` 与 `--unexecuted-report` 路径）均改走排他发布；attribution/batch-packet/
  handoff 副本保持既有 replace 语义（报告是不可变锚点，竞争失败方在报告写入即抛错，不会再写
  伴随件）。准入时 `exists()` 检查保留为快失败前置，不再承担并发正确性。
- D1 回归用例：`test_r3012_partial_judging.py::test_a_mid_run_publication_of_the_same_attempt_is_a_typed_conflict`
  ——examiner 会话期间由第三方写入同 attempt 的已发布报告字节（复现双方均通过准入检查的交错），
  断言退出码 2、stderr 含 `cq_handoff_immutable`、第三方字节逐字节存活、无 `.tmp` 残留。修复前
  该用例失败（退出 0、`full_pass:true`、字节被替换），即独立轮复现的 D1。
- D2 处置（T0-5 覆盖声明）：补三处共现回归锁——contracts 文件两个 loader/snapshot 用例
  （`acceptance_mode`/`blind_status` 作为 Task 参数被闭集拒绝；cq_semantic 快照只记录 selector
  对，不含报告名字段）、partial_judging 一个执行面用例（一次 cq_semantic run 中 stdout 的
  `acceptance_mode`+`blind_status`、attribution 双字段、report `blind_status`、run-contract
  `acceptance_target` 与 attempt 保留 handoff 副本 `acceptance_target` 各归其位、互不覆盖）。
  `test_r3012_contracts.py` docstring 的「T0-1..T0-5、T0-9」声明至此为实；开发轮 §6 同一声明当时
  不实，以本轮记录为准更正（历史轮次不删改）。
- 影响面：GitNexus `impact(_write_host_only_json, upstream)` = LOW（直接调用者仅
  `_cq_execute_batch`/`_run_cq_acceptance`，均在 cq-acceptance 派发链内）；`detect_changes
  (unstaged)` 13 文件/121 符号/5 受影响流程，medium，无 HIGH/CRITICAL，与开发轮范围一致
  （新增本测试计划文档与 4 个新用例）。
- 回归（仓库根）：`test_r3012_*.py` 5 文件 → 72 passed（contracts 13、partial_judging 13）；
  `-k "r3012 or r3011"` → 222 passed；`modeling_team` 全量 → 1636 passed / 1 skipped /
  331 subtests passed，7 failed 仍全部为预先存在的 `test_deepseek_codex_runtime.py` 用例；
  `cd backend && uv run pytest -q` → 1007 passed / 36 skipped。未重启服务（未触及 backend
  运行时代码），未创建/恢复/修改任何真实 run，未提交任何变更。
- 本轮为开发侧修复记录，不改变独立 Round 1 的 FAIL 结论；D1/D2 处置待第二轮独立复测验证
  （优先 D1 并发交错复测与顺序回归）。

### 独立测试 Round 2 — 机械（2026-09-13）

- 测试者：独立 `requirement_tester`；复测范围：D1/D2 修复验证 + 必要回归。仍仅 T0–T4 机械项；
  隔离、真实 L0/L1、SQL、授权、清理复核 NOT RUN（未使用历史 auth010/auth011 授权或资源）。
- 代码基线：`c18e8e1` + 未提交工作区（开发侧缺陷修复 Round 1 后状态）。本轮未提交、未回退、
  未修改任何产品代码或测试。
- **D1 复测（FIXED）**：
  - 独立复现路径重放：以 Round 1 相同交错（用 012 测试夹具驱动真实 `_run_cq_acceptance`，
    examiner 会话期间向同 attempt 目录写入第三方已发布报告字节，脚本仅在 /tmp、已清理）重放，
    观察结果：退出码 2、stderr 含类型化 `cq_handoff_immutable: this attempt's batch report was
    published by another acceptance process...`、第三方字节逐字节存活、无 `.tmp` 残留 —— Round 1
    的静默覆盖（`process-B published bytes survived: False`）不再出现。
  - 开发者新用例审查：`test_r3012_partial_judging.py:498` 起的
    `test_a_mid_run_publication_of_the_same_attempt_is_a_typed_conflict`（断言退出 2、
    `cq_handoff_immutable`、第三方字节逐字节存活、无暂存残留）与上述独立交错一致；其
    「修复前失败」声明与独立 Round 1 复现结果吻合。
  - 顺序回归不回退：`test_r3012_partial_judging.py:410-450`（同 attempt 重跑类型化冲突、旧报告/
    handoff 副本字节不变、attempt-0002 不存在、新 attempt 可恢复）与 :582 起 legacy 路径用例的
    断言与 Round 1 版本逐行一致，未削弱。
  - 实现审查：`modeling_team/__main__.py:2180-2209`——`immutable=True` 以每进程唯一临时名
    （`<name>.<pid>.tmp`）+ `os.link` 原子硬链接排他发布，目标已存在（含符号链接）抛
    `FileExistsError` 转类型化 `cq_handoff_immutable`，`finally` 清理临时名（发布后数据经目标
    链接存活）；两处报告首次发布（`:1912` 执行路径、`:2148` `--unexecuted-report` 路径）均排他，
    且先于 attribution/batch-packet 伴随件写入，竞争失败方不会写伴随件；准入 `exists()` 保留为
    快失败前置（`:1413-1419`）。未发现新引入边界（`os.link` 语义、临时清理、非 immutable 伴随件
    的 replace 语义在报告锚点排他之后，均闭合）。
- **D2 复测（FIXED）**：三处新用例真实编码 T0-5「三字段分别校验和记录、不相互覆盖或混用」——
  `test_r3012_contracts.py:171`（`acceptance_mode`/`blind_status` 冒充 Task 参数被闭集类型化拒绝，
  不能遮蔽或别名 `acceptance_target`）、:187（cq_semantic 快照只记录 selector 对，报告名字段
  不进入）、`test_r3012_partial_judging.py:453`（一次 cq_semantic run 中 stdout 的 mode+blind、
  attribution 双字段、report `blind_status`、run-contract 与 handoff 副本中 `acceptance_target`
  各归其位且 run-contract 不被改写）。docstring「T0-1..T0-5、T0-9」声明至此为实；开发轮 §6 当时
  的不实声明已由开发侧修复轮记录更正，历史不删改。
- 套件复跑（仓库根，四项全部符合预期）：
  - 5 个 r3012 机械文件 → 72 passed（较 Round 1 新增 4 用例）。
  - `-k "r3012 or r3011"` → 222 passed。
  - `modeling_team` 全量 → 1636 passed / 1 skipped / 331 subtests passed；7 failed 仍全部为
    `test_deepseek_codex_runtime.py` 预先存在用例（失败集合与 Round 1 逐例一致，按交接不调查）。
  - `cd backend && uv run pytest -q` → 1007 passed / 36 skipped。
- 本轮边界：未重启服务（未触及 backend 运行时代码）、未创建/继续/修复任何生产 run、未修改保留
  evidence 或历史冻结/verdict、未消费建模额度、未提交任何变更；临时复现脚本已删除。
- 本轮结论：D1 FIXED、D2 FIXED，四个套件无回归，机械层总体 **PASS（机械层，非语义结论）**。
  R3.0-012 的机械验收至此通过；隔离测试、真实 L0/L1、SQL、授权、清理复核仍 NOT RUN，须按计划
  另行取证后方可声明对应层级通过。
