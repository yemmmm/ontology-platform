# R3.0-015 建模阶段检查点与恢复 — 交付设计

- 日期：2026-09-14
- 状态：需求/设计外部审阅 E1 已核验修订；独立 D1 专项复核 PASS（2026-09-14，S1+S2+S4 范围，
  见测试计划 D1 轮）。同日按用户确认范围实现 S1+S2+S4（新 `modeling_team/checkpoints.py`、
  `modeling_team/checkpoint_recovery.py` 及 Runner/CLI/scope/skill 接线），独立功能测试
  I Round 1/Round 2 PASS（3 项错误通道缺陷修复后复测通过，含 §8 键形对齐）。S3 按设计
  延后，S2 回退 014 正常翻译审阅。本需求真实 L0/L1 未执行。
- 需求：[R3.0-015](../../requirements/requirements-v3.0.md#r30-015-建模阶段检查点与恢复)
- 测试：[共享测试计划](../test-plans/2026-09-14-r3-0-015-modeling-checkpoint-recovery-test-plan.md)
- 基线：初稿代码 `ee8f531`，E1 核验 checkout `375eec6`（代码未变）；关联 R3.0-006、008B、009、011、012、014，以及
  R2.3 的 existing-scope、原子提交与恢复边界。本文只设计 015 的必要增量。

## 1. 方案与范围

用户本轮已确认首版接受新建角色线程、加载已保存成果继续，优先确保成果可复用。
据此采用“不可变阶段成果 + 新执行 run + 新线程接续”。例如 A、B 两个 Ontology 已应用，
C 的计划已获批但尚未应用，Runner 退出后，新执行先核对 A/B 和 C 的全部 Attempt，再加载
原候选与审批，只执行 C 的剩余工作。若模型已经交接，仅启动独立验收即可。

| 方案 | 能解决的问题 | 取舍 |
| --- | --- | --- |
| 现有 live/provider resume | 进程和线程存活时继续当前步骤 | 继续优先使用；无法覆盖运行环境退出 |
| 阶段成果恢复，新建线程（采用） | 保留前期建模成果，跨 Runner 进程继续 | 需显式保存成果、重建作用域绑定和核对写入；不依赖供应商会话恢复能力 |
| 原线程全状态恢复或数据库快照回滚 | 更细的执行位置恢复/数据还原 | 涉及供应商状态、在途工具与跨存储一致性；本需求首版不承担 |

设计采用同机原作用域接续，覆盖显式启用 `modeling_checkpoints: true` 的 v3 multi-slice +
staged + unified 路径；CQ 检查点还要求原 Task 启用了 CQ。实现时在新冻结的 v3 Task 中选择，
不改旧 run 的 Task，也不把 015 作为其它真实运行的启动前置。

检查点不是 PostgreSQL/Oxigraph 备份，不回滚已写资源、不恢复模型隐含思考、不重播整个消息历史。
不用检查点宣布语义正确；已获批准也可能在后续语义验收中失败。

P1 保持为待办排序，不代表已经证明整包投入的收益。按[账本核验记录](../records/2026-09-14-r3-0-015-review-evidence.md)，
可以确认故障收尾后重启同目标的记录和重复出现的前期阶段，但没有阶段时间/token 对照，
不能宣称“节省几轮/多少小时”。§9 将交付改为独立可停段，优先解决下一次实际恢复所需部分。

## 2. 当前代码事实与缺口

以下来自本轮只读源码检查，未运行所列实现或测试。

| 当前落点 | 已有能力/限制 | 015 最小增量 |
| --- | --- | --- |
| `runner.py:TeamRunner.prepare/start/_state`；`__main__.py:main` | prepare 拒绝已有 run 目录；start 新建 scope、Transport、Runtime；state.json 是覆盖写当前状态，没有恢复入口 | 保留普通 run；新增检查点读取和显式接续入口，不让 prepare 覆盖旧目录 |
| `scenario_map.py`、`staged_decisions.py`、Runner CQ freeze | 有候选、业务决定、版本、计划、不可变 CQ freeze 及公开投影 | 按现有 artifact 引用保存一致的阶段包；重建必要的 Runner 阶段变量 |
| `staged_decisions.py:read_submission_intents/read_submission_receipts` | intent/receipt 已落盘；ordinal、key、session、projection 可关联 | 保存检查点位置，并在恢复时读取检查点之后的完整写入尾部 |
| `runner.py:_handle_staged_submit_modeling_batch_open`、`unified_translation_issue` | 014 已有 apply 的当前计划/Coordinator 翻译门和 dry-run proof | 窄的恢复审批来源校验与新身份迁移，不能直接复制旧 proof 放行 |
| `ModelingBatchService.submit/_get_or_create_batch` | key 和 client_batch_id 均以 Build Session 为作用域；旧 Session 非 active 时先拒绝 | 新 Session 只提交已证明未完成的操作，不能依赖旧 key 跨 Session 去重 |
| `PlatformScope._existing/apply_ontology_plan/cleanup` | existing 入口绑定单一 Ontology，要求无 active Session/Lease/Attempt；非空失败 scope 保留，空 owned scope 可被删除 | 精确重绑全部已记录 Ontology；恢复模式清理保留绑定资源；旧资源须先有据收尾 |
| `runner.py:_cleanup_cq_private`、`competency_questions.py` | CQ freeze/reviews/public 保留，私有草稿和访谈工作目录可删除 | 检查点保留验收所需的批准访谈原文及冻结依据，隔离存储；不依赖临时 private 目录存活 |
| `runner.py:_cq_publish_production_handoff`、`__main__.py` 的 cq-acceptance | 有冻结生产交接、独立验收入口与按 attempt 存报告 | 支持原生产 Runner 已退出的只读接续，分离旧证据输入和新报告输出 |

状态核验：014 的 `b849fcf` 已含顺序增量，012 的 `49b7e51` 已含阶段验收实现。
初稿发现的文档头差异已在 E1 后单独同步；证据层级见
[状态核对依据](../records/2026-09-14-r3-0-015-review-evidence.md#4-012014-状态核对依据)。
015 以这些实际接口为接线依据，需求目标仍由权威正文定义，不从代码存在推定语义验收 PASS。

## 3. 检查点的位置与数据

### 3.1 五类业务阶段边界

| kind | 可重复的范围 | 保存依据 | 恢复后的下一步 |
| --- | --- | --- | --- |
| `scenario_mapped` | 一次已发布访谈/场景/切片决定 | 已确认访谈、场景/切片决定、已有拓扑；CQ 草稿/审核/公开投影及真实阶段 | 从尚未完成的 CQ 审核/切片/拓扑继续，不重复已确认访谈 |
| `cq_frozen` | 一个冻结题池 | 冻结题池/审核、公开投影、批准资料/访谈、已完成场景决定 | 继续尚未完成的拓扑/语义建模；不重新出题和访谈 |
| `semantic_approved` | 候选 revision、切片或 shared scope | 候选、业务审批、源引用、分析结论与已有 unlock | 继续剩余语义、值确认或翻译；未决内容仍未决 |
| `materialization_progress` | 单个 plan/Batch 的确定结果 | plan、有效批准、真实 dry-run/apply Attempt、intent/receipt、关联回执 | dry-run 修正、翻译审阅、未完成 apply 或 Evidence 关联 |
| `production_handoff` | 一次冻结生产交接 | 既有完整 handoff、题池和模型/Evidence 绑定 | 原生产进程退出后只继续独立验收 |

这些是已完成成果的保存位置，不新增全局线性阶段机。一个切片的保存不等待其它切片完成，
CQ 冻结也不强制未到时点的拓扑批准。中间草稿可在原角色工作目录继续使用，但首版只保证
已发布、可绑定成果的跨进程恢复，不保证每个 token 或未发送回复都被保存。

`scenario_mapped` 名称不表示 scenario-map 或拓扑必须全部完成；有一份已确认访谈或场景
决定即可保存。已有 CQ 草稿与评审状态作为该阶段的必要工作成果保留，未审批内容仍 pending。
这覆盖“访谈/场景决定已完成，但题池未冻结”的窗口，不把拓扑与 CQ 的先后固化成新流程。
只有宿主/CQ 角色可恢复私有出题材料；其余生产角色仍只获得已获准的公开投影。

保存触发复用现有访谈/场景决定发布、CQ freeze、候选批准回告、staged receipt/proof 与生产 handoff 的处理点。
Coordinator/宿主也可请求保存已发布成果，Runner 读取实际文件/回执验证；没有完成证据时
返回缺失 artifact 和可重试说明，不把请求当作新的语义批准。

### 3.2 文件布局与字段

仅使用 gitignored 的既有 `workspaces/modeling-runs/`：

```text
<source-run>/checkpoints/<checkpoint-id>/
  manifest.json              # Runner 最后发布的提交标志；存在才可作为检查点
  artifacts/                # 获准、不可变的成果副本，保留原相对路径
  host-private/             # CQ 冻结池、隐藏依据、批准访谈原文等，生产角色不可挂载
<recovery-run>/
  recovery/inspection.json   # 检查和平台读回结果，含原运行尾部绑定
  recovery/origin.json       # source/root run、checkpoint digest、配置差异与授权引用
  recovery/imports.json     # 恢复的成果、历史审批、已完成操作与新身份映射
  recovery/roles/<role>.json # 分角色的公开接续说明
  ...                       # 复用普通 run 的工作目录和新证据
```

目录和文件按现有角色文件权限管理；建模生产角色（Coordinator/Modeling/Protocol，下同）
不获得 manifest、host-private、原 run 根目录或验收目录的挂载。未冻结 CQ 的出题角色只恢复
原合同允许的自身草稿/审核材料，不获得整个私有目录。公开包按当前 `role_sources` 和 artifact
所有权生成投影，不是过滤几个敏感文件名之后复制整个 run。

`manifest.json` 首版 schema 为 `r3-0-015-checkpoint/v1`，最小字段组：

| 字段组 | 内容与用途 |
| --- | --- |
| 身份 | `checkpoint_id, source_run_id, root_run_id, created_at, kind, scope_refs`；scope_refs 指切片、候选或计划，不赋予新业务权限 |
| 配置 | 原 Task/Profile/角色包、工具/运行协议与批准来源的路径和 digest，model profile，acceptance_target；用于恢复兼容性判定 |
| 成果 | `artifacts` 中的原路径、快照路径、digest、逻辑 owner、revision 和既有依赖引用；缺失/未决项另记，不补造 |
| 阶段事实 | CQ freeze 与曝光记录引用，已批准决定、当前计划、已完成项、pending 项和 `next_step`；next_step 是交接建议，Runner 不替 Agent 决定语义 |
| 平台绑定 | Project、完整 Ontology/Graph Set ID 映射、各 workspace version、相关 Session/Batch/Attempt 与资源/Evidence 回读引用 |
| 写入位置 | 每条关联运行的 intent/receipt/evidence 位置和文件摘要；记录的是保存时截面，不声称包含未来操作 |

manifest 不内嵌自己的 hash；其确切字节摘要写入现有 host evidence，恢复时重新计算。新 run 的
`origin.json` 精确绑定它。原审批、CQ、plan 文件保持原样；运行身份变化写到恢复记录，不覆写历史。
运行代码摘要用于追溯，业务/合同兼容性依靠相关字段和 schema，不能要求整个仓库 SHA 永远相同。

### 3.3 保存一致性与失败

1. 使用唯一 checkpoint ID 和临时目录，拷贝明确列出的成果；每个 artifact 使用已发布版本，
   校验内容摘要与候选/决定/plan/freeze 的交叉绑定，并确认拷贝期间源内容未变化。
2. staged 写入口复用现有 admission，在截取写入位置时短暂阻止新的本 run 写请求，等待已准入
   请求落到可辨认状态；不增加跨 LLM 审阅的长锁。候选/审批文件若仍变化，只延后这次保存。
3. 有在途/unknown 操作时不发布一个声称可恢复写入的 checkpoint，返回可观察原因，仍保留
   现有故障证据。已存在的更早 checkpoint 继续可读，但使用它恢复也必须处理后续未知写入。
4. 数据文件落盘后，最后原子发布 manifest 并记录摘要。没有 manifest 的半包不能被列为可用；
   已发布包不覆盖。磁盘错误/摘要冲突只让当前保存失败，不终止无不确定写入的正常建模。
5. suspend/失败清理仍撤销凭据、收尾本轮 Session/Lease 并关闭进程。只有空 scope 被至少
   一个已发布有效 checkpoint 或既有待验收 handoff 引用时，才为恢复保留；只打开 flag、
   保存失败或仅有临时目录均沿原空 scope 清理。非空失败资源和其它既有保留义务保持有效。

### 3.4 去重、磁盘与人工清理

同 kind、scope_refs、artifact digest、阶段决定和实际写入位置不变时返回已有 checkpoint，
即使请求使用新 ID 也不再拷贝。比较保存内容本身，排除时间戳、请求 ID 和 checkpoint-save
事件，防止“保存又改变证据位置”引发无限新包。复用最近同范围包元数据即可，不建内容寻址库
或限流服务；没有新增成果的反复请求不成为新的建模失败门。

宿主 inspect/保存结果给出已发布包数量、累计文件大小及 scope 保留原因。新成果确实较多时
磁盘仍增长；本设计不声称无界增长已完全解决，也不引入自动 GC。容量不足只暂停本次保存。

人工清理操作顺序：先用 `checkpoint inspect --run-id R` 列出具体包及 origin/验收引用；
再核对无活跃写者、无 unknown/fence，并按用户已有清理授权确定不再需要的具体 checkpoint
目录。将其移到指定归档/回收位置，保留原 run 的失败与操作证据及清理记录；若只剩该包引用的
空 owned scope 也可删除，再走既有 Project 删除接口。仍被恢复/验收依赖的包不得删除。
未发布临时包可在源写者已停后按文件归属清理。无删除授权时只给清单和大小，不执行删除；
不提供一键清空 workspaces 或自动删除历史 evidence 的命令。

## 4. 恢复入口与执行

### 4.1 宿主接口（设计新增，当前不能执行）

不新增产品 HTTP/MCP API。扩展既有 Runner CLI 与 host-only outer 分派：

| 入口 | 输入 | 行为 |
| --- | --- | --- |
| outer `action=checkpoint` | 已绑定 run、kind、scope_refs | 让存活 Runner 保存已完成成果；Agent 请求经 Coordinator/宿主转入，无额外 Agent 写权限 |
| `checkpoint inspect --run-id R [--checkpoint-id C]` | source run；省略 C 时列出所有检查点 | 只读生成 JSON 结果：可复用/待办/对账/兼容性/预计授权消耗，状态 `ready`、`needs_reconciliation` 或 `incompatible` |
| `checkpoint resume --run-id R --checkpoint-id C --new-run-id N --mode production` | 明确原检查点、新执行身份和宿主授权引用 | 重验后创建新角色线程，继续生产；不接受任意新的 scope 或悄悄切模型 |
| 同上，`--mode acceptance` | production_handoff 检查点和已授权验收范围 | 仅启动独立验收接续；不启动生产 Runtime 或创建写 Session |

检查命令可读实时平台状态，使用现有宿主认证；诊断产物写入新的恢复检查目录，不修改原运行。
未指定 checkpoint 时只列出建议，不自动恢复。`resume` 必须重新核对 inspect 之后的状态，
检查结果不能长期充当启动凭证。授权引用只供宿主交接/记录，不新增代码内建模次数预算硬门。

### 4.2 生产恢复步骤

```text
只读检查明确的 checkpoint + 源运行完整尾部
  → 原生产进程已停，原写入已对账，授权仍有效
  → 新 run 保存 origin / imports，重新绑定原 Project 与全部 Ontology
  → 新凭据 / Build Session / lease / Transport / 角色线程
  → 分角色交接已完成成果与剩余操作
  → Protocol 对未完成计划重新 dry-run，复用或重审相应批准
  → 后续物化 / 新生产交接 / 独立验收
```

原运行存活时优先走既有 live/provider recovery。跨进程恢复不与原写者并存：同机沿同一
root_run_id 使用一个进程锁，配合既有平台 Session/Lease/Attempt 检查防止重复 resume；
不创建分布式锁、队列或调度服务。只有旧进程 PID 证据不够，仍需核对平台写者状态。

`TeamRunner` 只增加面向阶段成果的 `prepare_from_checkpoint` 接线，不反序列化整个 Python
对象。普通 prepare 的“不覆盖已有目录”保持有效。恢复时需要明确装配的状态如下：

| 状态 | 恢复依据与处理 |
| --- | --- |
| 配置和 role ID | 加载检查点对应合同及已记录的兼容修复；保留逻辑角色身份，新建实际线程 |
| scenario-map / Ontology topology | 恢复已批准映射和全部精确 ID；不按名称再次创建/猜测 Ontology |
| `_cq_freeze`、CQ phase、public projection、曝光记录 | 有 freeze 时验证恢复；scenario_mapped 则恢复实际草稿/审核阶段，freeze 保持为空，私有材料仅交 CQ/宿主，不能重复访谈或假装审核完成 |
| staged 目录、候选/结论/决定/plan | 原格式成果投影到新 run；导入来源写入 host-only imports；门按现有 validator 重算，不能直接恢复布尔 open |
| 已完成操作、dry-run/审批有效性 | 使用 §5 的平台读回和 §6 的批准规则；检查点后的已知完成操作也记入 |
| 未解决问题 | 原 issue 只作为历史原因；新线程需要等待时创建新绑定 issue，不伪造旧 thread 的 resume ack |
| Transport/terminal/deadline | 新 Broker 和 turn，只重建待办交接；不重放 delivery 队列或导入旧 completed 作为本轮新 terminal；超时从本轮有效时间开始 |

角色启动说明包含 `resume_kind`、可读取的成果引用、已完成范围、未决事项、禁止重交的操作及
下一步。不让 Coordinator/Modeling 再执行默认全流程开场。逻辑角色仍按原 Profile 管理，
可以报告已复用成果并完成自己的当前交接；不得为“恢复”新增审阅角色或重复出题。

### 4.3 20 分钟与必要对账

完整读取该恢复链的写入尾部、平台分页、Session/Lease/Attempt 属于安全开始所需最小检查，
因为漏读会重交已应用操作；它仍计入从用户授权时开始的 20 分钟，不能自行从计时中扣除。
只核对本次恢复绑定的资源与证据，不扩大成整个部署或所有历史 run 的审计。

inspect 阶段先报告已知 Batch/页数、未完成核对项及外部阻塞。预计超过剩余准备时间时，
向用户说明具体原因并申请明确的更长准备期；没有得到延长授权就不把慢对账默认为例外。
到 20 分钟仍不能安全开始时，报告已花时间、第一阻塞层和更短通路，停止扩展准备；不会为
守时跳过分页、清 unknown，或把空建线程/运行只读检查记成 semantic start。

本次选择先完成最小对账再建生产线程，不实现“只读生产线程预启动”分支；该分支会改变
现有 prepare/start 与凭据装配，当前没有证据证明需要。宿主可继续已有权限内的只读诊断。
只有真正进入获准语义工作的调用才记 semantic-start；保存检查点、初始化 Runtime 和等待
都不算。功能就绪后，正常小规模接续仍应满足 20 分钟，不预先给所有恢复统一豁免。

## 5. 平台状态与不重复写入

### 5.1 对账包含检查点之后的操作

读取 source run 及其已有 origin 链的完整 intent/receipt、staged proof、Evidence 关联记录、
scope/cleanup 证据，并读回相关平台 Session、每个 Batch 的全部必要 Attempt、内容及结果。
平台枚举必须遍历完整分页，不能把 LIMIT 截断、单个最新 Attempt 或空列表当作完整事实。
继承源历史与本轮新 intent 分别绑定到原/新 Session，现有 staged reconciliation 必须使用
这个已验证基线，不能把继承 Batch 判成“无本 run intent 的越权写入”，也不能忽略新出现的外部 Batch。

完成索引至少按 `(origin_run_id, session_id, batch_id, attempt_id, client_item_id)` 定位，
并保留 command/content/projection digest、结果资源 ID 和 Evidence 关联引用；它只是既有
命令的执行事实，不是新的语义对象 ID。只做同一操作的复用，不能因命令文本相同就把两项
不同业务操作合并。多次接续的 imports 指回原操作，不能重新编号后当作待执行。

| 当前事实 | 恢复处理 |
| --- | --- |
| 精确原 Attempt=applied，内容/范围/结果资源与回执一致 | 登记完成并跳过；缺 Evidence 关联仅继续该关联，不能重交整个 Batch |
| checkpoint 后 applied，或原回执丢失但可按原 Session/key/内容精确读回 applied | 在新恢复证据记录读回事实并跳过；保留原回执缺失，不补写旧 run |
| dry-run=validated，尚未提交 apply | 可复用计划/语义批准，进入新 Session 的新 dry-run；不算已物化 |
| failed 且平台明确 failed_without_side_effects、无在途/fence、对账闭合 | 沿 014 的新 Batch 恢复规则，仅继续未完成项 |
| unknown/部分写入/状态仍在 applying 或 recovering/枚举不可达或不完整 | 保持写门 closed、返回具体身份和对账建议；本次不能继续写 |
| 查不到原请求、只有 Agent 自报 safe_to_retry | 不能证明请求没执行；保持待对账，禁止换 Session/key 绕过 |
| 写入或版本变化无法归入该恢复链 | 返回 `scope_drift`，列出差异；不自动认领、删除或回滚 |

这是恢复入口对明确平台结果的只读确认，不新增通用 unknown adjudication 服务。现有
`adjudicate_unknown_intent` 的按 key 或 client_batch_id 命中/未命中辅助结果不能独自释放恢复门。
对于仍未知的写入，通用认领服务或自动强制恢复不在本需求中；宿主继续使用现有平台恢复/诊断能力。

### 5.2 Session、资源与版本

首版新建 Build Session 和租约，只对尚未完成操作建新 Batch。Session/key 的作用域由后端
现有实现决定：同一个 key 搬到新 Session 会成为新请求，因此必须先对账，再分派剩余工作。
新增恢复 import 与提交前检查共同拒绝已经完成的原操作，不能只依靠提示让 Protocol 自觉跳过。

具体绑定放在 host-owned imports 的计划映射中：`source_plan_ref/digest → current_plan_ref/digest`
及保留的 `client_item_id`，结合已有 projection 中的 candidate ID/revision、decision_bindings
和 identity_bindings 定位原操作。恢复的未完成计划须沿此映射提交；换 Batch/Session/key 不能
把已完成原项变成新项。确需新业务修改，必须产生正常的新候选/决定/计划版本，不能伪装成
原计划接续。既有跨批资源依赖通过导入的原 receipt 与回读资源 ID 解析，不能指向新 run 中
碰巧同 ordinal 的 receipt；必要的身份绑定修改进入相应计划重审，不凭字符串相似猜映射。

原 Session/Lease 不序列化为可用能力；正常 suspend 可沿原所有权收尾。崩溃后由宿主核实
原运行所有权、无在途操作，再使用既有 cancel/release/expire 合同收尾；无法证明时保持等待。
不抢占其它活跃用户会话，也不强清 fence。旧凭据只保存可用于撤销的 ID，不保存明文；新角色
启动前旧运行凭据失效，读写凭据重新签发并继续沿用角色隔离。

原运行挂死时先检查既有 status/control 响应、PID 与启动时间及运行目录归属，再尝试该 run
的现有 stop 通道。无响应不等于已经停止；宿主按现有停止授权对已确认归属的进程受控收尾，
不按模型进程名批量终止。每次等待至多 60 秒，并报告是否仍有原写者。

宿主已受控停止原写者后，fresh 源 run 的 `state.json` 可能永久停留在 possibly-live 状态，
而其 stop 通道（control FIFO）已不存在，"经 stop 通道停止"的指引不可执行。此时且仅此时，
宿主用 `checkpoint settle-source --run-id ... --stop-reference ...` 在 runs root 的
`.recovery-settlements/<run_id>.json` 写入显式 settlement（schema_version、run_id、
observed_state、stop_reference、created_at；命令不创建/恢复 run、Session、Agent 或
start，不改源 run 的 state/evidence）。写入前命令校验：run 无恢复来源、state 仍为
possibly-live、FIFO 不存在、已知 Session（按 write intent 收集）均可读回且为
completed/cancelled 终态、无 active lease、写尾无 unknown/in-flight。恢复入口只接受与
当前 run/state 匹配的 settlement，并在恢复时实时复核 FIFO 与已知 Session 状态；写尾安全
仍由后续对账门负责。没有 settlement 时行为完全不变："无 FIFO、无 session"不能自动推断
进程死亡（未启用 FIFO、尚未建 session 的活跃 fresh run 外观相同）；恢复链 run 仍只认
chain writer lock。

随后读实际 Session/Lease 状态及 `expires_at`，展示最早租约重查时点，不写死 TTL 或保证
“到点即可恢复”。已有合法 token 且无 fence 时可用正常 release；无 token 时沿有权限的
Session cancel/平台到期合同处理，不能从 checkpoint 还原 token。过期后再次读
Session/Lease、全部在途 Attempt 和 fence；只有原写者已停且这些事实闭合才允许新写入。
卡在 applying/recovering/fence 时无法估算恢复完成时间，明确记录阻塞，继续窄诊断；租约
过期本身不是零写入证明，也不是强清 fence 的理由。

复用原 Project 和全部 Ontology/Graph Set ID，扩展 `PlatformScope` 的显式检查点绑定入口，
将已验证的 `ontology_ids` 装入现有多 Ontology 路径；不要调用按名字补建的 topology create。
资源缺失返回 `scope_missing`，不自动建立空白 scope 后伪装成恢复。恢复运行采用 existing
所有权，清理仅处理本轮线程、凭据、Session/Lease；已继承的空/非空 scope 均不删除。

对 checkpoint 之后由原 run 合法写入造成的版本前进，用已核对尾部更新当前基线；对应的
证据状态也须重读。其它漂移不默认接受。如果需要对真实新业务状态重新建模，属于后续明确
目标与授权，不在恢复算法中自动生成修订。

## 6. 成果、审批与兼容性

### 6.1 业务批准复用

源成果字节、候选 revision、来源依据、业务范围与决定绑定都不变，且原逻辑角色仍承担同一
责任时，导入有效业务决定。`imports.json` 由宿主记录原批准路径/digest、审批逻辑身份与
原运行证据、新 run 与适用决定 ID。保留原 approved_by，不伪造新 Agent 审阅消息。

恢复入口校验源 run 的原所有权/批准通道，不能仅检查文件中字符串等于 `coordinator`。
新 run 的当前审批视图只接纳本次确切检查点及已核对尾部的来源；任意文件复制、错误 source
run 或其它 Profile 角色的批准不能成为恢复批准。普通非恢复提交仍只认可本 run 当前批准。

`imports.json` 同时列出不再有效的决定。原 run 在保存后已撤销或替换批准时，以可核对的
后续决定为准，旧 checkpoint 不能复活已撤销批准；记录缺失/冲突时只让受影响项等待澄清。
源码不推理语义等价，候选/来源/业务决定变化必须由责任 Agent 重审对应内容。

### 6.2 翻译批准与新执行身份

新 Session 必须发布有恢复来源的新 plan/client_batch_id/key 并重新 dry-run。原 dry-run
proof 是历史结果，即使 workspace 未变也不直接作为新 Session 的执行凭据。

S2 默认沿 014 让当前 Coordinator 审阅新翻译计划，复用 §6.1 的业务候选与业务批准。
下列自动迁移是独立可停的 S3 优化，尚未交付时不阻断 S2；不能把必要的业务批准核验和
多 Ontology 完成索引也延后。只有具体恢复运行确实需要避免重复翻译审阅时再实施 S3。

为避免同一内容只因线程/Session/Batch 身份变化就重做翻译审阅，015 在恢复路径提供确定性
批准迁移，必须同时满足：

1. 原批准从原 Runner-owned 证据与当前有效决定核实，原/新逻辑 Coordinator 相同；
2. 候选 revision、业务决定、identity_bindings、value traces、L3 bindings 及实际 items 的
   完整规范化内容均不变；
3. 唯一变化是恢复产生的 plan_ref、client_batch_id、Session/key/lease/workspace 等执行绑定；
   实际 items 使用下述平台生成内容身份，候选/决定/value 等额外绑定仍单独精确核对；
4. 新计划已有绑定当前 workspace 的真实成功 dry-run proof，无新 blocking findings；
5. 宿主生成原 plan/批准 → 新 plan 的确切迁移记录，当前 apply 验证这个记录及新 proof。

内容比较固定复用后端自己的计算结果：从原 Batch 与新 dry-run Batch 的正式
`get_modeling_batch` 读回 `content_hash`，确认各自 Session/Batch/Attempt、原/新计划实际提交
绑定和成功状态后比较。该 hash 由 `ModelingBatchService._content` 及平台 hash 实现生成，
015 不重新实现 `_content`，也不以当前 014 的本地 `platform_content_hash` 镜像或 Agent
自报 hash 单独批准迁移。平台字段/规范化变化无法证明兼容时只取消自动迁移、重审当前计划，
不妨碍已复用业务成果继续。原计划尚无可核对平台 Batch 时同样回退到当前计划审阅。

M28/M29 的权威对照使用真实后端 Pydantic 输入与 `_content` 路径产生的 Batch 结果，覆盖
默认值、集合字段顺序/去重、实际 payload/证据/新字段变化；015 不能用另一个同源镜像函数
给自己作正确性证明。D1 首先核对这一证据链以及额外 identity/value/decision 绑定。

迁移只表示复用既有裁决，不记录“当前 Coordinator 已重新审阅”。当前批准视图可由专用恢复
装配路径提供给现有 validator，源 artifact 不修改；不得把 provenance 例外扩展为通用跨 run
审批白名单。重复迁移同一绑定为幂等；不同决定冲突只拒绝当前计划并反馈。

任何业务内容或决定变化都回到 014 正常修正/审阅通路；若原整批需要拆分、删除或改变实际
依赖/命令，不能套用身份变化例外。后端明确归一的 items/集合顺序变化按权威内容身份处理，
不能因文件排版变化要求重新语义审批。已 applied 批次不再提交，也无需迁移批准。

### 6.3 运行修复与材料变化

恢复保留原业务输入、CQ 和模型选择。代码/提示的窄修复可使用新执行基线，但必须在 origin
记录原/新相关文件摘要、修复原因、合同检查结果。只影响日志或某个错误处理的代码变化
不使所有业务审批失效；schema 或语义合同不兼容则返回具体 `contract_incompatible`，
不启用通用自动迁移。已知 prompt-contract 缺陷仍须先修权威提示面再启动新生产线程。

本首版不提供修改业务材料、换模型或换逻辑角色的恢复参数。确有这些需要时，宿主应明确新
范围、受影响审批和授权，再走相应变更流程，不能用恢复命令静默覆盖冻结合同。

## 7. CQ 隔离与仅继续验收

生产角色只拿各自原本获准的 artifact、公开 CQ 和接续说明。全部题池、隐藏答案、审核私有
材料和答案依据只留 host-private，并只向既有验收角色按 011 合同提供；检查点路径、错误
详情与摘要也不能把这些内容泄露进生产日志。获准业务访谈原文与私有出题对话分开保存。
曝光记录沿恢复链取并集，曾向生产角色展示的问题永不因新 run 或新线程重新标为隐藏。

S4 的 `--mode acceptance` 只接受有完整 production_handoff 的检查点，重新验证其模型与 Evidence
绑定、冻结题池、未知写入和生产写者停止状态。读回相同后复用既有 cq-acceptance 执行与 Judge
通路；冻结 `acceptance_target`、问题分母与 non-blind 状态保持不变。

实现需要将该入口的只读 `evidence_run_root` 与新的 `output_root` 分开：旧 handoff/freezes
作为原样输入，新 attempt/report 及宿主结束记录写新恢复目录并关联来源。原 CLI 的默认行为
保持兼容；不能通过改旧 run_id、重写旧 handoff 的 attempt 字段或给旧报告补 PASS 实现接续。
原 Runner 已退出时由当前 Delivery 宿主记录接续终态，无需向死 FIFO 回贴；原运行失败终态保留。

首版验收过程退出后重新执行该冻结批次的独立验收，不恢复 Examiner 内部对话或拼接不完整
答案为一轮新 PASS。保留上一轮 partial/fail/report，新增 attempt 并绑定相同输入。已有完整
合格报告时只做必要核对与宿主收尾，不为了“恢复”重复调用模型。模型/Evidence 漂移时返回
`acceptance_binding_changed`，不能让验收方修复模型；重新交接归生产侧。

## 8. 授权、错误与可观察性

| 动作 | 建模 start 记录 |
| --- | --- |
| 保存/inspect/只读核对 | 不消耗；未启动建模角色 |
| 原存活线程 live/provider continue | 沿 006，不新建 start |
| 新建生产线程从 checkpoint 接续 | 按当前规则计一次 fresh semantic start；复用成果不自动豁免 |
| 仅继续独立验收 | 不计建模 start；仍在既有验收授权内，记录独立 attempt |

宿主 Agent 记录授权引用、root/source/new run、真实 semantic-start 时点与消耗，不能因
inspect/prepare 成功就记作已建模，也不添加平台次数硬门。原授权耗尽、被收回或 scope 不覆盖
原资源时，在模型启动前报告；不自动给恢复追加额度。用户 stop 后先停下，保存成果不意味着
获得继续授权。本次文档工作消耗 0 次 semantic start。

恢复拒绝返回 `code, object_ref, phase, retryable, reason, next_action`，具体引用不得含隐藏
内容或 secret。最小原因包括 `checkpoint_incomplete`、`artifact_changed`、`source_active`、
`contract_incompatible`、`scope_missing`、`scope_drift`、`write_unreconciled`、
`approval_binding_changed`、`acceptance_binding_changed`。磁盘写失败和可修正输入不终止
正常源 run；结果未知仅禁止恢复写入，可继续只读诊断。`retryable` 说明当前操作能否在条件
改变后重试，不代表允许自动重试或自动追加 start。

失败根因仍为 `modeling-quality | platform-contract | collaboration/routing |
runtime/infrastructure` 四类；checkpoint/restore/reconcile 是 phase，不增加第五种归因。
按既有 evidence 记录保存/恢复开始、拒绝、实际分派、已复用项、未完成项和阶段推进。区分
恢复准备时间、后续语义建模时间、验收时间；token 只统计实际供应商用量，缺失就标 unavailable。
检查点数量、导入字节数或 Runner ok 不证明建模质量，也不自动证明节省了固定比例。

T0 复核：保存偏好不成为硬门；artifact 缺失只延后本次保存/受影响恢复；拒绝绕过未知写入是
因为会直接损害已写资源完整性。首版复用现有原子写入、版本与独立验收，不新增自动恢复框架。

## 9. 实现落点、交付顺序与停止条件

| 落点 | 必要修改 |
| --- | --- |
| 新 `modeling_team/checkpoints.py` | 阶段包 manifest、保存/读取/验证、角色投影、恢复绑定；一个具体模块，不建插件体系 |
| `runner.py`、`__main__.py` | 保存处理点、inspect/resume 分派、prepare_from_checkpoint、必要状态装配、源运行停写检查、独立验收接续结束 |
| `platform_scope.py` | 从明确映射恢复多 Ontology，原 Session/Lease 收尾接线，保留 checkpoint scope 的 cleanup |
| `staged_decisions.py` 及 staged forwarder | 导入已核对完成索引、提交前去重、历史基线对账、新 dry-run 与翻译批准迁移 |
| `competency_questions.py`、验收入口 | 冻结/曝光状态恢复，旧证据输入和新报告输出分离；保持原隔离与判定合同 |
| 新 v3 Task 冻结、contracts、角色包与宿主 `skills/modeling-dev-loop/` | selector、resume packet、已完成阶段跳过说明、授权记账/对账操作说明 |
| `modeling_team/tests/` | 共享计划列出的跨进程、隔离和错误场景；复用平台 fixture，避免一次性语义验收脚本 |

不预设 backend migration、平台 API 或 UI 变更；当前平台读回/Session 接口为首选。实现时若
发现无法完成当前必需对账的真实接口缺口，先报告具体证据并收窄补充，不能用文件/布尔值假装
已对账。本文进行的是源码/调用点检查，没有声称图谱影响分析覆盖；实现跨模块接口前仍按
AGENTS.md 做相关影响检查并报告 High/Critical。

交付分段如下，每段是可独立验收、独立停止的边界，不是自动连续执行的工作清单：

| 段 | 最小交付与可停点 | 后续安排 |
| --- | --- | --- |
| S1 | 五类成果保存与 inspect；含未冻结 CQ 隔离和保留条件。只有保存/读取能力，不能宣称跨进程恢复已完成 | 出现具体可复用包及恢复需要，再投入接续；不因 015 登记就额外启动建模 |
| S2 | 无写入/已知写入的新线程生产接续；业务批准来源核对、多 Ontology 对账/去重、角色隔离和失败分支齐全；新翻译计划仍正常审阅 | 完成独立功能验收后，优先在既有真实目标中获得 L0/L1；不以 S3 优化为前置 |
| S3 | 自动迁移翻译批准，按 §6.2 权威内容比较；只优化无需改变的翻译审阅 | 可延后；具体恢复中出现重复翻译成本时再安排，不阻止 S2 使用 |
| S4 | 原生产进程退出后的独立验收接续，输入/输出分离和范围绑定齐全 | auth012 已有实际需求；有可用 handoff 时可在 S1 后优先实施，不依赖 S2/S3 全部完成 |

S1/S2 的阶段完成不等于整项 015 全部交付；未做 S3 明记优化 deferred，未做 S4 明记验收
接续未交付。§4/§6/§7 分别描述这些段的目标合同，未交付入口不能提前对外宣称支持。
每段达到相应验证后停止平台扩展，回到当前真实语义目标。若有效语义时间不足一半，
暂停下一段平台/harness 工作，报告时间来源和较短通路；已有实现/对账义务不能因此跳过。
每步用当前合同 fixture 验证，不把真实建模前置成全面 harness 审计。
实现后运行 Team 回归和改变的 skill validator；若确需 backend/UI 修改，执行各自要求的测试、
服务重启与健康检查。本轮只修改文档；015 共四份（含 E1 账本依据），做链接、格式和合同检查。

独立功能验收、真实 L0 和语义 L1 分别记录。真实授权后 20 分钟内开始第一轮 semantic start；
L0 证明实际新线程从成果接续并推进至少一个后续步骤、已完成写入零重交，L1 再由独立验收
判断质量。L2 重复性和 L3 产品化不作为 L0/L1 前置，015 不阻塞其它已授权语义取证。
