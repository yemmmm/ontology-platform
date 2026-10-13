# R4.3-017 独立工程测试

## 范围和前置条件

复用主 agent 指定方案，覆盖 [需求 A1–A9](../../requirements/requirements-v4.3.md#r43-017-jev-参与分支选择的自适应相关子图扩展) 和 [设计](../designs/2026-10-13-r4-3-017-adaptive-context-expansion-design.md)。测试拥有者仅修改本文件与 `backend/tests/test_r4317_adaptive_context.py`，不修改生产实现，不提交，不回滚其他工作。

使用现有 `test_r4008_context_query.context`、真实 rdflib DatasetStore/SPARQL、内存 SQL session 和确定性双评分 stub。记录实际邻接 SPARQL 的 anchor，证明裁剪发生在读取前。执行前等待主 agent 的 ready 通知。外部 Jev、真实建模与 Consumer/Judge A10、运行时重启和全量开发交付由主 agent 负责，本测试不将它们视为已通过。

## 既定测试用例

| 用例 | 验收 | 步骤 | 期望及通过标准 |
| --- | --- | --- | --- |
| T1 | A1/A9 | 自然语言缺省、fixed、显式 depth、IRI、context_limit=0 | 实际策略/深度一致，IRI 不分支评分，显式一跳无无用途评分 |
| T2 | A2/A3 | root→桥梁/普通背景→规则→未知；记录 anchor 与完整评分输入 | 一跳保留，背景不读取第二层；低回答桥梁保留真实连接；第三跳未知得分 1 可保留；不读第四跳 |
| T3 | A4 | 同名双根、共享节点、新入边、自环/回边、跨 Ontology | 稳定身份去重，根来源保留，新上下文可重判；共享邻接只读取一次；环不无限任务 |
| T4 | A4 | 第二层 TableMapping 明确 field_path→规则 | 深层结构化引用参与第三层，保留 source/target/path，不造 RDF 边 |
| T5 | A5 | 受限中间节点、谓词、嵌套引用；仅 fact 输出 | 隐藏内容无评分、推进、计额或提示；合法内部关系继续遍历，输出声明 filtered |
| T6 | A6 | 小/大 context 页、第二根页续页、重复首查；Jev 关闭/失败 | 冻结集合无重复遗漏、根页恢复正确，正常续页与重复首查不再评分或读邻接 |
| T7 | A5/A7 | X/Y 均隐藏后 X 解限不修订；纯隐藏成员变动；核验读取失败 | 实际源可见性变化失效旧 match/context cursor 且首查重算；纯隐藏变化复用；核验不完整 dependency_error |
| T8 | A8 | 小评分/工作/宽度/时间预算，评分故障/模型漂移 | 全请求累计、第一跳/已读结果保留，partial/degraded/null 与首原因可读，停止额外推进 |
| T9 | A9 | full/compact/preview，实际关系拆页与 fixed 回归 | 选择状态可读，preview 不带全文，实际身份/路径一致，fixed 行为兼容 |

通过标准：本轮可执行用例全部 PASS 且无确认需求缺陷；不能执行的覆盖明确 BLOCKED。工程 PASS 只证明上述确定性合同，A10 仍待授权与独立真实质量证据。

## 测试轮次

准备阶段：2026-10-13；基线 `c8356db8a80501782d3c04ff190f7eae8782e01c`，生产与原测试文件正在由其他 agent 修改。尚未执行，不作 PASS 判断。

### Round 1 — 2026-10-13

- 工作区：上述基线加其他 agent 当前未提交的 R4.3-017 实现；获得 ready 通知后执行。测试过程中其他 agent 仍在补充实现，因此最终交付还须由主 agent 在冻结工作区执行全量与运行时验证。
- 命令：`cd backend && uv run pytest tests/test_r4317_adaptive_context.py -q --tb=short`。
- 实际结果：**21 passed，80.22 秒**；只有既有 FastAPI/Starlette/rdflib deprecation warnings。
- T1–T9 已有核心场景 PASS；邻接断言记录 root、bridge、rule 各读取一次，普通背景/第四跳无邻接读取；跨根共享节点只读取一次，实际自环保留；低回答桥梁与第三跳 1 分未知保留；第二层结构化 source/field_path 连接返回第三层。
- 双页 enabled/disabled/failed 均 PASS；第二根页 context 续页保持根页且读取/评分次数不增加；同绑定重复首查复用。无修订 X 解限使旧 match/context cursor 失效，fresh 首查可返回 X；无源受限 IRI 增量复用；授权对照超时抛 dependency_error。
- 评分/工作/时间预算、全根共用宽度与桥梁预留、三投影、fact-only 内部遍历与隐藏完整值核验 PASS。无确认产品缺陷。
- 未执行：新增真实 HTTP stub 模型漂移及深层 RDF 超时用例尚未在本轮收集；REST/MCP/cursor/原固定路径相邻回归待下一轮。A10 未授权、BLOCKED；解除条件为后续真实效果授权与独立 Consumer/Judge 证据。
- 结论：本轮已执行范围 PASS；工程总验收待补充场景及相邻回归，不能据此声明真实质量 PASS。

### Round 2 — 2026-10-13

- 工作区：同基线未提交实现；执行期间生产文件和旧回归断言仍由其他 agent 更新，因此本轮失败保留原始输出并按当前代码复测。
- 命令：`cd backend && uv run pytest tests/test_r4317_adaptive_context.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py tests/test_semantic_context_cursor.py tests/test_semantic_jev.py tests/test_r4008_context_query.py -q --tb=short`。
- 实际结果：**3 failed，116 passed，214.26 秒**。新增独立 **23 场景全部 PASS**，REST/MCP/cursor/Jev 相关合同通过；HTTP stub 模型漂移保留实际绑定模型、未评分为 null、第一跳保留且无深层读取；选中 RDF 超时返回 partial 并保留合法 base。
- 失败原始证据：`test_fact_output_traverses_relation_without_returning_it` 未找到 literal 42；`test_budget_partial_is_distinct_from_terminal_page_and_hidden_rows` 精确等式左侧新增 `strategy/completeness_scope/selection_status/path_projection`；`test_cycle_and_overlapping_roots_keep_shortest_root_paths` 左侧 root_paths 新增 `root_ontology_id`。
- 核对结论：上述三个用例为旧缺省策略/精确字段合同未同步，不构成已确认生产缺陷。fact-only 旧测试已改为显式 fixed；另两项已按权威新增元数据更新。当前执行进程已加载旧版本，修订后必须独立复测，不抹除本轮 FAIL。
- 附加检查：独立测试 Ruff PASS；`git diff --check` PASS。
- 本轮总体 **FAIL（回归断言未同步）**，建议主 agent 保留其既有测试合同更新后复测，不建议仅凭这些断言修改产品实现。A10 BLOCKED；保护集 mutation/resolver 的全部 OR 组合不在本增量测试中，本层直接验证有效授权视图转换；主 agent 的后端全量/运行时验证仍待执行。

### Round 3 — 2026-10-13 21:12 +08:00

- 主 agent 授权第三轮并要求补充主命中 HTTP 故障测试。生产四个核心文件 SHA-256 在该轮开始后记录与结束时相同：
  - `semantic_context_adaptive.py`：`c66de34c18de9c2487688caa28790478764608a7d4ccb4074e89cf0730651070`。
  - `semantic_context_query.py`：`ef64623157b1ffc0083808e727f50c5995f1e2c1f1628678bce77240cfbd4fa8`。
  - `semantic_jev.py`：`c0c7f03561c4e32ed36d02c678c9b083162ba28a9796e97712140f88bb4d648f`。
  - `semantic_context_cursor.py`：`a951a7a8d6d99e7ccb8f0702a1ca66f8e2b7d46ec6041ad5316ed70894718831`。
- 主命令：`cd backend && uv run pytest tests/test_r4317_adaptive_context.py tests/test_semantic_jev.py tests/test_r4008_context_query.py::test_fact_output_traverses_relation_without_returning_it tests/test_r4008_context_query.py::test_budget_partial_is_distinct_from_terminal_page_and_hidden_rows tests/test_r4008_context_query.py::test_cycle_and_overlapping_roots_keep_shortest_root_paths -q --tb=short`。
- 实际结果：**50 passed，120.57 秒**，其中原独立 23 场景、24 个 Jev 合同、Round 2 三个失败回归均通过。
- 补充命令：`cd backend && uv run pytest tests/test_r4317_adaptive_context.py::test_primary_http_failure_does_not_retry_provider_for_branch_selection -q --tb=short`；**1 passed，2.60 秒**。主命中 `http_error` 后 score_branches 调用次数 0，邻接仅 root 一次，base 桥梁保留而远端未读，degraded/scoring_unavailable 保留。

| 范围 | 本轮状态 | 证据 |
| --- | --- | --- |
| T1 默认/fixed/IRI/不展开 | PASS | 明确策略与 depth，IRI/显式一跳无分支评分 |
| T2 桥梁/未知/逐层裁剪 | PASS | root/bridge/rule 各一次；背景无深层邻接，第三跳未知保留 |
| T3 新入边/共享/环/同名跨 Ontology | PASS | 拒绝后新根入边可推进，共享邻接一次，自环保留，无重复身份 |
| T4 深层结构化引用 | PASS | 实际 source/target/field_path 与第三跳距离 |
| T5 完整授权/fact 投影 | PASS | 隐藏 URI 不进响应/评分/frontier，fact-only 可获深层事实且 filtered |
| T6 双分页/失败/关闭/重复首查 | PASS | 正常 context 续页和重复首查不增加邻接/评分，第二根页恢复 |
| T7 授权视图转换 | PASS | 无修订解限同时失效 match/context；纯隐藏无源变动复用；核验超时 dependency_error |
| T8 累计预算/模型漂移/评分/RDF 故障 | PASS | 累计限额、桥梁预留、partial/null、已读内容保留、停止新推进 |
| T9 full/compact/preview 与 fixed | PASS | 三投影保留选择状态，preview 不带全文，原主命中分数 2 不变 |
| Round 2 三个旧回归失败 | FIXED | 显式 fixed 与新增 metadata/root_ontology_id 合同修订后均通过；无 REGRESSION |
| 外部 Jev、真实建模、Consumer/Judge A10 | BLOCKED | 不在本次工程测试授权内；需要后续真实效果授权与独立语义证据 |

结论：**独立工程测试 PASS，0 个确认产品缺陷，不建议新增修复轮次**。无外部 Jev 调用；测试文件最终共 24 个独立场景，Ruff 与 `git diff --check` PASS。REST/MCP/cursor 未改部分复用 Round 2 已通过结果；全量后端、运行时重启及健康验证由主 agent 执行。本层不证明外部评分效果、完整保护集 mutation/OR 组合或 A10 真实质量。
