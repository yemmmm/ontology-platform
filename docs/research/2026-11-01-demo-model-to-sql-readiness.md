# Demo 问数：实际模型能否支撑 SQL 生成

日期：2026-11-01。状态：本次有界消费审查完成。9 条问数问题中，4 条模型信息可直接支撑 SQL，3 条需补充条件，2 条缺少可用事件数据映射。生成并执行了 6 条 SQL，其中 2 条使用额外核实的启用编码；模型未修改。

## 目标与范围

用户要求创建几条问数问题，从模型查找相关信息，判断能否支撑 SQL 生成。
本次以已续建的实际模型为目标：Project `40841ac8-1c93-4cb1-85ba-1a9e8fb7928b`、
Ontology `755f1e0e-cf5d-47f2-a2a3-95220f4cba96`。本次所有实际读取均重新核实为 revision 4。
只查询模型；不恢复原 run、不修模、不把此前独立 PASS 当作本次检索证据。

按 R4.0-010 和 R5.0-009，SQL 生成依据须包括已获准模型中的业务含义、记录粒度、字段、
连接路径、过滤条件与计算口径。原始 Schema／程序只在后续物理验证中使用，不补足模型缺项。
当前宿主已知 Demo 背景，本次是有证据的消费审查，不是隔离盲测。

## 预先登记的问题

| 编号 | 问数问题 | 主要检查点 |
| --- | --- | --- |
| Q1 | 各模型成功新调用次数、历史实际扣额总量和平均扣额是多少？包含暂无调用的模型。 | 成功记录粒度、历史扣额、零调用 |
| Q2 | 每个凭证授权了多少个模型、成功调用多少次、实际扣额多少、当前余额多少？包含零调用凭证。 | 两条一对多关系的重复计数风险 |
| Q3 | 按凭证状态、授权、模型状态和额度条件，哪些凭证—模型组合满足一次新调用的准入条件？ | 完整四条件、当前扣额、授权连接 |
| Q4 | 哪些启用凭证还有正余额，却不足以调用其已授权且启用的模型？ | 正余额不足与当前费用 |
| Q5 | 哪些模型存在历史实际扣额与当前扣额配置不同的成功调用？有多少次、实际扣额合计多少？ | 历史事实与当前配置区别 |
| Q6 | 哪些请求标识曾被两个或更多不同凭证成功使用？ | 请求标识的去重范围 |
| Q7 | 2026-10-31 UTC 当天各模型成功新调用次数与实际扣额总量是多少？ | 时间字段、时区、日期边界 |
| Q8 | 各模型今天被拒绝和历史回放的次数分别是多少？ | 是否有对应事件数据与映射 |
| Q9 | 各模型最近一次调整扣额单位的时间、调整前后数值和操作人是什么？ | 配置变更历史是否可查询 |

## 执行与结论

### 检索方法与实际结果

只读授权来自本次用户指令，临时凭据仅有选定 Project 的 read scope。调用实际
`POST /api/semantic/context:query`，再沿现有受治理 read-model 接口读取实际定义及映射，
没有读取候选／自查笔记来补充模型。原 run 保持 stopped，模型未发生新 apply。

默认自适应展开的首批请求出现 `scoring_unavailable`，约 25 秒后仍返回 partial。
保留原始回执并结束该只读采集；凭据正常撤销。随后用现有参数
`search_mode=lexical`、`expansion_strategy=fixed`、`context_order=graph_distance`、
`depth=2`、`context_detail=full` 对九条自然语言问题统一查询。
九条均 matched，均无分页／截断，固定展开在请求深度内 complete。
这是检索范围状态，不证明语义或 SQL 信息已经完整。

当前完整资源清单为 14 项。通过列表与精确读取核对了 4 个 Class、3 个 relation_type、
4 个 table_mapping、3 个 join_mapping。Q3 的首轮上下文没有返回凭证类／凭证表／授权表
完整正文，后续精确补读取得；其余问题在首轮已返回本次判定所需资源正文。
统计同时检查资源的 `data` 与 literal fact，未将缺少重复 fact 误判为结构化映射缺失。

检索原件与 SHA256 manifest 保存于
`workspaces/v5-runs/demo-sql-readiness-20261101-inputs/`。
汇总见[逐题检索状态](artifacts/2026-11-01-demo-model-to-sql/retrieval-summary.json)；
SQL 依据及准确 IRI 见[逐题判断](artifacts/2026-11-01-demo-model-to-sql/assessment.json)。
两批采集的读取／bootstrap 临时密钥均有撤销回执，没有恢复旧任务凭据。

### 逐题判断

| 问题 | 实际模型提供的信息 | SQL 支撑判断 | 本次执行验证 |
| --- | --- | --- | --- |
| Q1 模型调用次数、历史扣额与平均扣额 | calls 是成功记录；charged_units 保留调用时实际扣额；calls.model_id→models.id | **支持**。COUNT 成功行、SUM／AVG 历史 charged_units；LEFT JOIN 保留零调用模型，平均值无定义时为 NULL | 4 行，与接口数据一致 |
| Q2 凭证授权数、调用数、扣额与余额 | 授权对唯一、请求在凭证内去重；凭证→授权、凭证→调用均为一对多 | **支持**。两个明细集先各自按 key_id 预聚合，再连接凭证，避免计数／金额相乘 | 9 行，与接口数据一致 |
| Q3 当前可发起新调用的凭证—模型组合 | 凭证启用、已授权、模型启用、余额≥当前 quota_cost 四条件，及完整连接路径 | **条件支持**。models.enabled 明确 1/0；api_keys.enabled 仅有启用含义，缺数值编码。SQL 保留 :key_enabled_value | 额外核实 1=凭证启用后返回 3 行；仍不升级为模型本身完备 |
| Q4 正余额却不足一次扣额 | 明确正余额也可不足；需比较 remaining_quota 与当前 quota_cost | **条件支持**。与 Q3 同一编码缺口 | 额外编码条件下返回 2 行，与接口数据一致 |
| Q5 历史实际扣额与当前配置不同 | 历史 charged_units 不改写；当前 quota_cost 只影响新调用 | **支持**。直接比较两列，不能用当前配置重算历史 | 2 行，与接口数据一致 |
| Q6 多个凭证曾使用相同请求标识 | 去重键为 (key_id, request_id)，不是全局 request_id | **支持**。按 request_id 分组，COUNT(DISTINCT key_id)≥2 | 1 行，与接口数据一致 |
| Q7 UTC 当天成功调用与扣额 | created_at 字段存在，但模型明确“时区／格式未由业务源声明”“精度与时区未知” | **条件支持**。缺少 UTC 边界／解析依据，不能靠字段名或当前样本补齐 | 未生成可执行 SQL |
| Q8 今天的拒绝次数和回放次数 | 拒绝不产生成功记录；回放返回原记录、历史扣额不改写；拒绝持久化方式为未知 | **不支持**。当前模型没有拒绝／回放事件的 SQL 映射，不能把成功记录当调用尝试日志 | 真实回放与拒绝均未增加成功表行数，不能统计成 0 |
| Q9 最近调价时间、前后值、操作人 | 只有当前 quota_cost 和调用时扣额，没有调价事件映射 | **不支持**。调用时间和建模更新时间均不能替代业务调价时间 | 两次实际改价后恢复原值，最终业务数据相同，历史操作不可由当前表还原 |

全部六条生成结果保存在 [queries.sql](artifacts/2026-11-01-demo-model-to-sql/queries.sql)。
Q3／Q4 的参数值没有写入生成依据；它来自 SQL 冻结后的额外物理核查，判断始终为条件支持。
Q7—Q9 未编造字段、表或可执行 SQL。

### 关键依据和计算选择

- **历史统计**：`C_CALL` 描述回放响应扣额为 0、原成功记录不改写；`T_CALLS` 映射
  `charged_units` 和成功记录粒度。因此使用 `SUM(calls.charged_units)`，不使用
  `COUNT(*) * models.quota_cost`。本次验证中 deep-lab 有 4 条成功记录，历史实际扣额为 6、
  平均为 1.5；当前费用为 3，按当前费用重算会错误得到 12。
- **防止连接膨胀**：`J_GRANTS` 提供 api_keys.id→model_grants.key_id→models.id；
  `J_KEY_CALLS` 提供 api_keys.id→calls.key_id，并声明一对多。问题 Q2 需先预聚合。
  实际 application-A 有 2 个授权、2 次调用，直接连接两张明细表会得到 4 个授权／4 次调用，
  本次 SQL 正确返回 2／2；application-C、D 也观察到直接连接的错误。
- **准入条件**：`C_MODEL`、`C_CALL` 的规则与 `T_MODELS.quota_cost` 共同约束 Q3／Q4，
  授权集合不能替代模型状态和余额条件。当前 SQL 只是数据库快照下的资格查询，实际调用仍
  由 API 原子校验。七组独立数据库副本上的真实 /calls 请求全部符合 SQL 预测，覆盖
  费用 1／3、停用模型、余额不足、零额度、停用凭证。
- **否定问题**：调用成功表没有新增行不等于没有发生重放／拒绝事件。一次新调用、一次
  实际回放、一次拒绝后，成功行数依次为 8、8、8；`charged_units=0` 的成功行数为 0，
  但真实回放发生了 1 次。Q8 不能据此生成“回放为 0”的错误答案。

`C_`、`T_`、`J_` 代号及完整模型 IRI 对照均在 assessment.json，原始模型字段正文在
inputs 下 governed-model-details.json，方便逐项追查而不依赖本报告摘要。

### SQL 执行与取证范围

先按实际模型生成 SQL 并保存 SHA256 冻结，再打开本轮业务数据库与应用代码。
SQL 目标由 Host 显式绑定到获准 Demo SQLite 的独立副本；没有从逻辑 source_key 推断 DSN。
原数据文件以只读方式备份，最后 SHA256 不变。副本通过真实 Demo API 增加零调用、零额度、
余额不足、停用凭证及停用模型等边界样例，业务行仍在 SQLite。

实际 SQL 用只读连接执行；六条全部执行成功，且逐行与 Demo API 返回的授权集合、成功记录、
模型配置和余额独立计算结果一致。进一步用每次独立副本的七组真实调用验证准入预测。
实际执行的 SQL 语句与模型未在物理验证后回填或更改；规范 SQL 保存在冻结的 assessment.json。
展示文件 queries.sql 发布时仅规范末尾空行，原始文件及前后 SHA256 另存 inputs/publication-normalization.json。
原始执行行、API 观察和 SQL 生成冻结均在 inputs；
可审阅汇总为 [verification.json](artifacts/2026-11-01-demo-model-to-sql/verification.json)。

这证明当前绑定的小场景中，已有模型能约束人工 SQL 生成并得到正确结果；不证明自动 NL2SQL
整体通过、隔离盲测、其他数据库方言、多源自动定位或业务数据授权。语义读取授权和外部数据库
行列权限分开，本次只访问自有 Demo 副本。未修改 backend／frontend 或模型，不需重启服务。

### 另外发现的模型表达问题

1. **额度单位残留旧词**：api_keys.remaining_quota 的 source_unit 仍为“次（调用次数）”，
   Model／CallRecord 已表达可配置扣额单位。余额不能直接解释为“还可调用多少次”，应统一单位。
2. **存储字段和响应字段混写**：calls.charged_units 的说明提到“回放调用为 0”，但完整
   CallRecord 规则明确这是回放响应扣额，历史成功行不改写。独立消费不能只取这一局部短句。
3. **来源版本定位不足**：四表 source_key 各为表名，schema_version 为 null；schema_source
   仍引用旧 `@2112c3e`，虽然模型已经增加 quota_cost。本次明确绑定单个当前 Demo SQLite
   后可执行，但没有证明自动定位数据库／Schema 版本。
4. **基数声明状态不一致**：部分文字 unknowns 仍写基数未明确，而 JoinMapping.step_semantics
   已给 one_to_many／many_to_one。本次用实际键、路径和预聚合避免推测，后续应整理一致性。

本轮记录这些缺口，没有进行修模。Q7 需要补充并确认时间语义；Q3／Q4 需要明确凭证启用编码；
Q8／Q9 若需要问数，先要有对应事件数据及映射。先前 Demo 的业务语义 PASS 保持其原范围，
不能替代本轮新增问数条件的完备性判断。

## 来源与原件

- [R4.0-010](../requirements/requirements-v4.0.md#r40-010-数据映射视角与外部数据库关联)：语义先于 SQL、粒度、连接、编码、时间与数据源边界。
- [R5.0-009](../requirements/requirements-v5.0.md#r5-0-009)：Schema 输入与消费反馈验证。
- [先前 Demo 功能扩展与建模记录](2026-11-01-v5-demo-incremental-modeling.md)：只用于定位真实目标与历史范围。
- 实际检索：inputs/retrieval/*.json、retrieval-manifest-initial.json、retrieval-manifest-fixed.json。
- 凭据收尾：inputs/credential-lifecycle-initial.json、credential-lifecycle-fixed.json；临时读取和 bootstrap 密钥均撤销。
- SQL 冻结：inputs/sql-generation-freeze.json；执行原件：inputs/sql-execution-results.json。

本轮未启动生产建模或新 GLM 评价；Context Query 使用了服务已有的评分能力，其 token 未归集，
外部 Host 用量同样未知，不将未统计用量记为零。当前结论是本次模型消费和 SQLite 验证的有界结果。
