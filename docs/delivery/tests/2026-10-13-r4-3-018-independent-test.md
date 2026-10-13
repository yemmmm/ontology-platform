# R4.3-018 独立有界工程测试

## 范围与通过标准

依据 requirements-v4.3.md 的 R4.3-018 A1—A9 和详细设计 §7，验证当前工作区工程实现。
本文件是唯一测试记录，后续复测保留历史轮次。独立测试只修改本文件和
`backend/tests/test_r4318_independent.py`；不修产品代码，不提交。

非目标：不调用外部 Jev，不启动／恢复建模，不使用隐藏答案；A10 真实中文检索效果、
Consumer／Judge E2E 和性能目标未授权，不作 PASS 推断。运行服务重启与全量套件由主 Agent 记录。

环境：现有 in_memory_session、test_r4008_context_query DatasetStore 真实 rdflib SPARQL fixture；
Jev 使用 httpx 本地 stub，执行真实输入序列化、批次、响应校验和排序／分页代码。

| 用例 | 验收 | 步骤与期望 |
| --- | --- | --- |
| T01 | A1 | fixed/adaptive 自然语言缺省与显式旧序、IRI、0深度／0页长、无根／空周边；检查回显及周边 HTTP 问题计数 |
| T02 | A2、A4 | 多根共享、环、远端高分、同分／0分，比较同 C 的旧序和新序；身份、完整 data、root_paths 不变，去重候选只评一次 |
| T03 | A3 | 反向连接、typed literal、谓词语义、完整条件／例外／未知、派生引用；检查真实 HTTP 输入、每根规范短路径和 data 同名字段；不虚构边／拓展 predicate或literal |
| T04 | A4、A5 | 三种投影和分页、neighbors.preview_ref；每行分数可读，preview 无评分全文，类型过滤保留内部路径材料 |
| T05 | A6 | fixed/adaptive 应用／禁用／失败多页，stub恢复后续页；禁止新增召回／邻接／评分，完整集合无重漏；match新页保留来源 |
| T06 | A7 | 最后保护解除不改revision、撤权、隐藏授权变更、依赖失败、配置变化及进程内快照丢失；旧cursor准确拒绝，首查复用重新核验 |
| T07 | A8 | 512／513候选、过大完整值、非法分数／缺项、成功批次后失败、模型漂移；整集合旧序，全部null且0新增过滤，原因安全 |
| T08 | A8 | 主命中消耗完共享预算、adaptive partial仍可排名；不新增阶段额度，探索与排名状态分别表达 |
| T09 | A9 | 复用REST/MCP、能力发现、cursor既有测试并补新字段和重放投影检查；仅精确运行元数据归一化，业务同名字段与分数保留 |

通过标准：上述本地可执行行为测试及必要相邻回归全部 PASS；未执行范围明确记录，
实际缺陷标 FAIL，环境或授权导致的不可执行标 BLOCKED，不能用 mock分数自证语义质量。

## 测试轮次

### Round 1 — 测试实现 FAIL；未发现产品缺陷

- 时间：2026-10-13 22:07—22:11 +08；代码基线 `0aa4e14e88390ee1837ac5cfdc7de0a49db02d42`
  加 R4.3-018 未提交产品改动。主 Agent 同期继续开发，未把工作区视作冻结发行版。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4318_independent.py -q --tb=short`。
- 原始结果：**1 failed, 24 passed in 140.02s**。首轮尚未加入 T03 的 statement根／source_only／
  跨Ontology派生引用以及 T07 的512／513、T08共享预算和补齐读取失败反例。
- 唯一失败：`test_projection_ranking_and_neighbor_references[preview]`，`KeyError: root_match_id`。
  测试误将 preview 的既有 `root_index` 投影按 full 读取；经核对
  `semantic_context_query.py::_multi_response::preview_paths`，这是测试缺陷，不是产品回归。
  修正为解析 `primary_matches[root_index].id`，后续同文件复测。
- 已通过：两种模式／不评分边界；多根共享和环去重、远端优先／0分／同分；逆向路径、
  typed literal、谓词定义／不导航、完整值和 data同名字段；full/compact、禁用无根排名快照续页；
  fixed授权最后保护解除／撤权／隐藏控制变化／依赖失败／配置／快照丢失；非法分数、
  部分HTTP批次成功后缺项／模型变更、超大完整值整集合降级。
- A10：未执行（本轮非目标）。本轮不声明工程整体 PASS 或语义效果 PASS。

### Round 2 — FAIL，D01 重复映射缺陷；其余失败为测试 fixture

- 时间：2026-10-13 22:13—22:19 +08；同一未提交工作区，新增 T03、T07、T08反例。
- 命令：同 Round 1，输出保留 `/tmp/r4318-independent-round2.log`。
- 原始结果：**6 failed, 29 passed in 168.68s**。
- 六项失败经实际堆栈与代码核对：statement根两项使用 CamelCase 表达式拆出 root token，
  因而召回多个合法 statement根，不能假定第一路径就是marker根；512/513两项误把
  被排除的 RDFS.label 元数据计入 C，实际 C=511/512；补齐故障两项在主召回阶段已
  触发，完整候选尚未取得，不能期待周边排序降级。修正唯一小写表达式、按真实输出
  C补一个事实、仅在实际周边评分deadline区间注入读取故障，保留本轮原结果。
- 已通过新增跨Ontology派生引用的两个完整定义及各自路径、真实producer的source_only、
  共享预算主命中耗尽等反例。没有把上述6项当作产品缺陷交修。

#### D01 — High：重复 JSON 评分映射被静默接受

- 独立反例命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4318_independent.py::test_duplicate_answer_mapping_in_real_http_json_is_invalid -q --tb=short`。
- 原始结果：**1 failed in 0.16s**，日志 `/tmp/r4318-independent-duplicate.log`。
- 复现：真实 `httpx.Response` 的 JSON `answers` 含两个 `c0`，分别分数0与3；
  `JevReranker.score_context` 使用普通 JSON解析覆盖前一映射。
- 期望：设计§4“缺项／重复映射均无效”，重复键应导致无效响应和整批不可用，服务
  据此整集合沿旧序且全部null。实际：adapter 返回 `status=applied`，分数3。
- 已第一时间向主 Agent报告；主 Agent修正 `context_ranking` 外部 JSON解析，使用
  `object_pairs_hook` 拒绝重复键，并保留正常读取可恢复降级。独立复测见 Round 3。
- 此次工程缺陷不推导模型质量结论；A10仍未执行。

### Round 3 — 定向修复与合同复测

- 时间：2026-10-13 22:19—22:23 +08；主 Agent已修D01和补齐故障降级；当前工作区未提交。
- 命令与原始证据：
  - `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4318_independent.py::test_duplicate_answer_mapping_in_real_http_json_is_invalid tests/test_r4318_independent.py::test_adaptive_partial_selection_can_have_applied_context_ranking tests/test_r4318_independent.py::test_match_next_page_gets_its_own_context_ranking_and_shared_origin tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py tests/test_semantic_context_cursor.py tests/test_r4318_related_context.py::test_fixed_relevance_visibility_and_configuration_binding tests/test_r4318_related_context.py::test_v4_signed_cursor_is_rejected -q --tb=short`。
    **61 passed in 33.53s**，`/tmp/r4318-independent-round3-contracts.log`。
  - 同环境 `uv run pytest ../modeling_team/tests/test_r3012_platform_responses.py -k r4318 -q --tb=short`。
    **2 passed, 55 deselected in 0.34s**，`/tmp/r4318-independent-round3-replay.log`。
  - 同环境 `uv run pytest tests/test_r4318_independent.py -k 'statement_root or candidate_budget_boundary or hydration_failure' -q --tb=short`。
    原始 **2 failed, 4 passed, 33 deselected in 21.64s**，`/tmp/r4318-independent-round3-retest.log`。
    statement根和512／513为 **FIXED**。两个剩余失败 `assert hits`：谓词定义已被较早读取缓存，
    评分阶段未再读，故故障注入未发生。为执行“引用尚未缓存的补齐读取”合同，测试仅在
    实际评分补齐入口移除该引用缓存，随后保留真实SPARQL读取并注入超时／不完整chunk。
    该修正属于fixture，无产品改动。
  - 同环境 `uv run pytest tests/test_r4318_independent.py -k hydration_failure -q --tb=short`。
    **2 passed, 37 deselected in 5.23s**，`/tmp/r4318-independent-round3-hydration.log`，两项 **FIXED**。
  - 同环境 `uv run pytest tests/test_r4318_independent.py -k 'snapshot_changes and (ttl or revision or index)' -q --tb=short`。
    **3 passed, 39 deselected in 8.28s**，`/tmp/r4318-independent-round3-source-changes.log`。
- D01：**FIXED**，真实重复键不再返回applied；合法普通stub评分及REST/MCP/cursor没有REGRESSION。
- adaptive partial探索仍可应用排名、match新根页独立评分且共享资源保留当前根来源 **PASS**。
- A9精确重放：只归一化context_page.ranking.snapshot_reused；data内同名布尔值、
  行分数及ranking.status变化仍为drift，bare/API envelope均 **PASS**。
- 工具检查：`cd backend && uv run ruff check tests/test_r4318_independent.py`及两自有文件
  `git diff --check` **PASS**。不报告图影响覆盖（GitNexus索引不可用，沿主Agent说明使用focused代码／diff）。
- 剩余：当前版本全部独立项的最终合并复测，见 Round 4；A10未执行。

### Round 4 — 独立有界工程 PASS

- 时间：2026-10-13 22:22:44—22:25:51 +08；基线提交仍为
  `0aa4e14e88390ee1837ac5cfdc7de0a49db02d42`，加当前未提交 R4.3-018 改动。
  测试源码本轮开始前冻结，SHA-256 `2272d9afa1bba2e6315a73944e019912997a8ec7436d81b6f1ccdf6534c14180`。
- 命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest tests/test_r4318_independent.py -q --tb=short`。
- 原始结果：**42 passed in 186.12s**，日志 `/tmp/r4318-independent-final.log`；只有既有
  FastAPI/Starlette/rdflib弃用警告。无外部调用、真实建模或产品源码修改。
- 追加只读能力验证：`cd backend && uv run python -`调用实际
  `context_query_capabilities(Settings())`及`SemanticContextQueryRequest.model_fields`，
  断言默认relevance、两选项、IRI沿graph_distance、两策略冻结、先排序／无额外过滤、
  512／30初值及REST模型默认值，输出 `R4.3-018 capability/schema defaults PASS`。
  两自有文件newline／trailing whitespace及文档引用文件／围栏检查 **PASS**；Ruff **PASS**。
- 测试开始附近与结束时下列产品文件摘要一致：
  - semantic_context_query.py：`eb70959f0cbf6dcd126edadee2bb1f58e6b2064af432bf3644b7903c4af20ba0`。
  - semantic_context_relevance.py：`0dc26fa8c4ac65d56aeae3a778fabfd6e404d70d6dfaab3eceefaf46f3535550`。
  - semantic_jev.py：`83f44f8e384cdb71c483ce3391e8bb6c79eef7d29014cf4a6ec521f4222d46ce`。
  - semantic_context_cursor.py：`795cffe2ac92759b99d42bdd5427f98f802487f82bc4674f53fdebba28736c2d`。

| 范围 | 状态 | 实际证据 |
| --- | --- | --- |
| T01/A1 默认／fixed／adaptive／旧序／不评分边界 | PASS | 周边真实问题计数、请求与有效顺序；旧序／新序同集合 |
| T02/A2 多根共享／环／远端高分／0分／同分 | PASS | 去重候选一次周边评分，分数优先，同分旧序，完整data/root_paths不变 |
| T03/A3 完整语义与实际路径 | PASS | HTTP实际序列化输入保留例外／未知／同名业务字段、逆向s/p/o、typed literal和谓词定义；statement根、derived field_path、source_only、各Ontology完整定义及各自路径 |
| T04/A4–A5 投影与真实连接分页 | PASS | full/compact/preview均保留独立relevance；preview无全文，页内引用准确；fact-only内部路径保留、filtered准确；partial探索和applied排名独立 |
| T05/A6 冻结与双分页 | PASS | 两策略排名／禁用快照续页无重漏；重复首查无新读取评分；新根页独立评分、共享资源保留来源 |
| T06/A7 授权／源／快照边界 | PASS | 最后保护解除不改revision使旧页失效且新首查含新可见值；撤权、核验依赖失败、配置／修订／索引变化、TTL／缓存丢失；隐藏控制变动复用 |
| T07/A8 预算与无效响应 | PASS | 真实C=512全部评分，C=513原集合不丢且不部分评分；过大完整值不截断；布尔／NaN／越界／非数字／null、缺项、后批次失败／模型漂移全部null回退；D01 FIXED |
| T08/A8 共享成本与补齐故障 | PASS | 主命中耗完Jev请求额度后周边无新调用；uncached引用真实读取超时／不完整chunk为hydration_unavailable；原结果保留 |
| T09/A9 REST/MCP／cursor／重放 | PASS | 复用Round3当前接口61项及重放2项；v4重查、排序绑定与能力字段一致；只归一化精确运行slot，业务同名字段／分数／状态保持drift判定 |
| 历史失败 | FIXED | Round1 preview读取、Round2/3 fixture假设均复测通过；D01产品缺陷修后通过，无STILL FAILING／REGRESSION |
| A10真实质量／性能 | BLOCKED | 未在本独立工程授权内执行；解除条件是后续同集合公开中文对照与独立Consumer/Judge授权及真实证据 |

结论：**独立有界工程测试 PASS，0个未修产品缺陷，不建议新增产品修复轮次**。
没有单独压测最大5000工作项或64快照LRU全过程，也没有测试所有保护集mutation/OR组合；
本层覆盖有效授权视图及实际源核验，快照丢失用进程内存清空模拟。服务重启／健康端点、
后端全量套件和提交由主Agent记录；本层不据此宣称它们已经通过，也不宣称A10效果PASS。
