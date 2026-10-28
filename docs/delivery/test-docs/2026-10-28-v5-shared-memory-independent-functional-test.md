# v5 共享记忆验证：独立工程功能审查

日期：2026-10-28。关联：[R5.0-002／008](../../requirements/requirements-v5.0.md)、
[v5 实施计划](../implementation-plans/2026-10-28-v5-langgraph-codex-migration-plan.md)。

## 范围与前置条件

用户已授权主任务继续共享记忆验证。本独立测试仅核查新增 `modeling_team/v5/scripts/memory_case.py`
的工程证据、权限、并发和报告绑定，不执行模型、不写平台或业务记录、不干扰进行中的真实阶段。
不读取 `private-question-freeze`、`consumer-answers`、`private-evaluation` 或私有 query 内容。
源码只读；仅维护本文件。没有另建记忆服务、一次性语义评分器或通用验收框架。

本轮基线 HEAD：`1e4fcb8`，新增脚本尚未提交。复用已有 `HostAgent`、版本化工作空间、MCP 材料范围、
原生工具裁剪与 P0 已验证的隔离合同。新 consumer／judge 采用独立新上下文，由主任务各自新进程启动。

## 聚焦用例与通过标准

| 编号 | 验证方式 | 通过标准 |
| --- | --- | --- |
| M1 | 静态核对真实 writer 并行区间、首写基线与冲突证据 | 不凭模型自述声明并发；两个实际原生回合区间重叠，首 put 均以 revision=1，工具实际返回冲突及成功回执。 |
| M2 | 工程对象 fixture 核对先提交内容保留断言 | 已提交项被修改或遗漏时不能给出保留通过；最终含双方贡献。语义正确性另交独立 judge。 |
| M3 | AST／现有工具合同核对 consumer／judge 权限 | consumer 只获问题、不获源文或答案，只有目标 memory 读取且无写权限；judge 有独立获准输入并只读。 |
| M4 | AST 提取真实 `require_reads`，工程事件正反例 | 材料仅可见、自述、失败调用、错误 object／revision 均不能代替实际成功读取；实际目标修订读取成立才能通过。 |
| M5 | 报告完整分母与目标绑定 | consumer 必须覆盖唯一完整题号；judge 调用已有绑定校验，不遗漏、重复、漂移或矛盾 PASS。 |
| M6 | 当前脚本 Ruff／格式及本测试文档检查 | 准确报告当前状态；保留失败轮次，修复后只复测受影响项。 |

## 测试轮次

### 第 1 轮：PASS（聚焦工程范围）

2026-10-28 09:36 UTC 起执行。真实写入、消费与独立评价由主任务执行，本测试未创建或修改其任何记录。
**32 个工程正反例通过，当前脚本 Ruff／格式通过，未发现新的实质工程阻塞。**
公开技术元数据显示独立评价回执为 PASS 6/6、目标 revision=3；本测试没有读取或重新评判其私有语义内容。

#### 方法、命令与结果

使用现有 v5 环境运行内联工程 fixture：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 python - <<'PY'
# AST 提取 memory_case.py 的 tool_items、payload、require_reads，
# 以及原生区间、首写保留、consumer 完整题号的真实断言。
# 以工程 JSONL、条目和报告对象执行正反例；不装载任何真实隐藏输入。
PY
```

fixture 只在内存内提供事件和对象，没有模型调用或业务／平台写入。权限测试构造同一 `material_server`，
以工程 manifest／scope 替换配置读取，并把数据库 connect 设为一旦调用就失败，证明拒绝发生于数据库之前。
初次权限 fixture 因过宽的 `Path.read_text` 替换干扰第三方包的版本元数据读取而初始化失败；
这是测试夹具问题。预加载依赖并将替换限制到两个工程配置路径后，4 项权限反例全部通过，未改产品源码。
读取、保留和分母的先前通过结果保持，另补区间及 judge 绑定反例。

| 组别 | 正反例 | 实际结果 |
| --- | --- | --- |
| 实际读取 11 项 | 工具仅可见、漏材料、材料失败、未读 memory、memory 失败、错误 object、错误 revision、只有 started 事件共 8 个反例；结构化结果、文本 JSON 结果、失败后成功重试 3 个正例 | 反例准确拒绝，正例通过；按实际工具 payload 的 revision 核对目标，不靠模型自报修订。 |
| 首写保留 4 项 | 先提交项完全保留；修改先提交项、遗漏先提交项、缺第二方贡献 | 正例通过，3 个反例被真实脚本断言拒绝。 |
| consumer 分母 5 项 | 完整唯一 1..N；缺题、重复题号、越界题号、空数组 | 完整正例通过，4 个反例拒绝。 |
| 权限 4 项 | consumer 读取原 source、冻结答案、其他私有 memory；尝试写获准只读 memory | 均在工具授权边界拒绝，未调用数据库。 |
| 并发区间 3 项 | 区间实际相交；顺序执行、只在边界相接 | 真相交通过，其他 2 项拒绝。 |
| judge 绑定 5 项 | 完整的负面 REVISE；漏题、重复、目标修订漂移、PASS 与 passed=false 矛盾 | REVISE 原样保留，4 个反例经既有 `validate_evaluation_binding` 拒绝。 |

静态核对报告发布路径：consumer 在写答案前核对 `questions` 实际读取、目标 object 的实际 revision 读取、
自报 revision 与完整唯一题号；judge 在写私有／公开结果前核对全部获准材料、实际目标读取及完整分母／revision／verdict 一致性。

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff check modeling_team/v5/scripts/memory_case.py
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff format --check modeling_team/v5/scripts/memory_case.py
```

结果：`All checks passed!`、`1 file already formatted`。
复用 `1e4fcb8` 的未变 P0 包测试结果，不因新探针重复运行整个 47 项回归。

#### 公共技术证据核对

证据根目录：`workspaces/v5-codex-p0/shared-memory-live-001/`。只读检查下列允许的工程元数据：

- `summary-write.json`：两个不同 writer 原生 thread；A 首基线 1、1 次 put、0 次冲突；
  B 首基线 1、2 次 put、1 次冲突；最终 revision=3、首写保留、私有对象读取拒绝。
- `concurrency-proof.json` 与两个 writer 的 `evidence/close-statistics-capture/activity.jsonl`：
  独立从首个 llm_start 及同 call_id 的 llm_end 复算，实际原生区间重叠 **19.597371557 秒**，与 sidecar 完全一致。
  这证明两个真实 Agent 原生执行区间重叠，不声称数据库事务同时提交。
- `summary-consume.json`、`target.json`：consumer 是不同于两个 writer 的新原生 thread，目标均为 revision=3，回答数为 6。
- `consumer-materials/manifest.json`：只有 `questions`。源码投影只复制 index／question，不复制 expected。
  `consumer-source-denials.json` 对 `scenario`、`frozen-questions` 均有 `isError=true`。
- `public-feedback.json`：公开回执为 PASS 6/6，revision=3，声明仅覆盖 exact-ID shared memory／fresh consumer，
  不覆盖完整 R5.0-008 或平台 L1。本测试只核对该公开元数据，不替独立 judge 自评语义。

原 `summary-write.json` 没有 overlap 字段。并发检查是在首次 write 启动后加入当前脚本，
主任务保留原 summary，另从原 append-only activity 生成 sidecar。本测试没有回写原件，
不追称当前源码中的新增 overlap 断言在首轮已执行过；实际并发结论以复算的原活动区间为据。

主任务明确披露 B 通过冲突回执中的完整 `actual` 内容和 revision=2 合并，而非额外调用一次
`read_workspace_object` 获取当前版本。这是已有准确反馈通道的合法使用，不应为形式上的重读多加一次模型往返，
也不能声称额外重读实际发生。工程证明覆盖的是基线版本冲突及保留先提交内容，不冒充业务含义矛盾的解决测试。

#### 权限与独立性结论

- writer 只有公开 source 及指定 shared-memory 的读写范围，不挂载父目录的冻结题集或评价材料。
- consumer 的 manifest 只有问题，workspace `write_ids=[]`，原生允许清单只有 `read_material`／`read_workspace_object`；
  接入继续复用已验过的 namespace、关闭宿主输入及原生文件／Shell 能力的合同。
- judge 使用自己的新 HostAgent、三项获准私有材料和同一 memory 的只读配置，不能修改 writer、consumer 或 memory。
  `require_reads` 读取实际工具成功事件与返回修订，不能从工具清单或自述推导已读。

#### 结果与边界

M1—M6 在上述工程范围 PASS，无需修复后复测。`first_commit_preserved` 的确定性检查能验证先提交条目仍按 ID／内容保留，
但不能代替完整业务意义、未知或例外的独立判断。

本次真实链覆盖：两个 writer 的乐观版本冲突、共享内容合并、精确 ID／revision 的换上下文消费，以及独立评价接线。
没有验证未知位置检索、全文／向量召回、记忆摘要、长期增量维护、来源撤回、业务含义矛盾解决、规模与净降耗；
不据此关闭完整 R5.0-002／008，也不把候选工作空间等同于已应用本体或平台 L1 语义模型。
本测试未读真实私有题目、答案、评价理由或 query；没有创建一次性语义评分器。

取证时脚本 SHA-256：`2ece319ecf976c4eb345bc75c4934d45197d23ed647824c269212f58278634de`。
