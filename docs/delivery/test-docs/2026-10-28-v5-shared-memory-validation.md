# v5 多 Agent 共享记忆验证

日期：2026-10-28。归属：[R5.0-002 F2／F6](../../requirements/requirements-v5.0.md#r5-0-002)、
[R5.0-008 F3／F4](../../requirements/requirements-v5.0.md#r5-0-008)。
前序：[P0 集成验证](2026-10-28-v5-codex-p0-validation.md)、
[记忆方案调研](../../research/2026-10-28-modeling-team-memory-options.md)。

**结论：当前精确 ID 共享记忆路径的有界试验通过。** 两个真实 Agent 基于同一版本写同一记录，
发生实际版本冲突后保留双方贡献；新消费者只从记忆读取并回答，独立评价 **6/6 PASS**。
不据此宣布完整记忆模块、R5.0-008、P1 或平台模型语义验收通过。

## 授权与边界

用户询问记忆是否需要测试、多 Agent 能否同时管理一份记忆后，明确要求继续推进。
沿原任务 `v5-codex-p0-20261028` 和本任务 `usage_only` 授权执行，未创建新预算或更改原预算。
全部托管角色继续为 Codex SDK／CLI 0.163.0、`glm-direct / glm-5.3-flash / low`。

本轮复用现有 PostgreSQL 工作空间和 MCP 读写工具，新增一个可复跑的
[共享记忆探针](../../../modeling_team/v5/scripts/memory_case.py)，没有新增记忆服务、向量库、
自动事实抽取、费用主账、平台 API 或默认启动入口。原 GraphRAG 未提交变更保持。
后端、前端及共享运行配置未变，不需要服务重启。

业务材料仍是最小安装链的公开原文，不添加新业务事实。复用生产写入前已独立冻结的 6 题，
仅评价侧可见问题／答案；两名写作者只读原文。该题集用于已知场景回归，不外推为新的大范围盲测。
共享记忆的权威是 `candidate_workspace`，没有创建或修改平台已应用模型。

## 范围与预先确定的判据

| 环节 | 必须看到的实际行为 |
| --- | --- |
| 共同基线 | A、B 均实际读取原文和同一对象 revision 1；各自第一次 put 使用该基线。 |
| 并发与冲突 | native turn 区间重叠；一个提交成功，另一个实际收到 `version_conflict`，不能只看最终摘要。 |
| 合并 | 使用当前实际内容合并；先提交条目的身份和正文原样保留，双方贡献进入最终版本。程序不裁决业务含义。 |
| 权限 | 写作者不能读取私有对象；新消费者无法通过材料工具读取原文或预期答案。只读角色无记忆写权限。 |
| 新上下文消费 | 在另一个进程创建全新 native thread，只获得问题投影和冻结记忆读取权限，答案引用实际条目。 |
| 独立评价 | 另一个独立只读上下文读取原始依据、冻结题、消费者输出及实际记忆；核对全部题目、目标版本和语义支撑。 |

当前材料没有彼此矛盾的业务资料或业务决定。这里发生的是**版本冲突与互补贡献合并**，
不把它称为业务真值冲突已解决。当前路径为按已知对象 ID／版本读取，没有检验未知位置的关键词或向量召回。

## 实际运行

gitignored 原件：`workspaces/v5-codex-p0/shared-memory-live-001/`。
`authorization.json`、`target.json` 保留授权、来源和冻结题哈希；各角色目录保留生效配置、
执行绑定、真实出站、原生工具事件、结果和用量。

### 两个写作者共管同一记录

- 对象：`shared-memory-live-001:shared-memory`，初始 revision 1 仅含空 entries。
- A 负责定义与概念区别，native thread `01a181da-329b-7e21-9395-678f3c265f42`。
- B 负责关系、明确否定及范围／未知，native thread `01a181da-385e-72e0-b74f-c515341584d8`。
- 首次 native turn 实际重叠 **19.597 秒**。

| 写作者 | 实际工具顺序 | 结果 |
| --- | --- | --- |
| A | 读 scenario → 读 revision 1 → put expected_revision=1 | 实际记录 revision 2，包含 A 的三个条目。 |
| B | 读 scenario → 读 revision 1 → put expected_revision=1 → 根据冲突返回的实际 revision 2 合并 → put expected_revision=2 | 第一次收到 `version_conflict`，第二次实际记录 revision 3，保留 A 的条目并追加 B 的三个条目。 |

B **没有额外调用读取工具取得当前版本**：冲突回执已提供完整 `actual` 内容，足以合并；
下一次写入仍受 revision 比较保护。既不能声称发生了额外重读，也无需为满足固定步骤增加一次读取。
B 首轮结果格式未满足结果 schema，沿原 thread 追加一次格式纠正；实际写入没有因此重复。

按工具回执与 PostgreSQL 最终版本核对，A 先提交的条目均原样保留，最终版本为 **3**。
写作者对私有对象的实际读取被拒。`summary-write.json` 保留原运行输出，
`frozen-memory.json` 保留冻结内容。

首段启动后才加入自动重叠断言；该段未重跑或改写原摘要。`concurrency-proof.json`
根据原 append-only activity 事后计算重叠，独立侧复算一致。最终脚本包含同一计算，
新运行会直接执行该检查；本段证据范围按这一差别披露。

### 新消费者与独立评价

`consume` 与 `evaluate` 分别以独立进程启动：

- 消费者创建新 thread `01a181de-679e-7e70-b445-ebe5fd74bdba`，不恢复或 fork 写作者历史。
  挂载材料 manifest 仅含 `questions`，没有预期答案；对 `scenario` 和 `frozen-questions`
  的实际 MCP 读取均被拒。workspace 配置只允许读取冻结对象，write_ids 为空。
- 消费者实际读取 revision 3，返回全部 6 题，引用的 6 个记忆条目 ID 均存在于该版本。
  程序仅核对身份和覆盖，不给业务答案评分。
- 独立 Judge 使用另一上下文与只读工具，实际读取 scenario、frozen-questions、consumer-answers
  和记忆 revision 3。它核对记忆保真及消费者答案的记忆支撑，最终 **6/6 PASS**。
  `private-evaluation.json` 留在独立侧；公开投影只给结论、分母和目标修订。
- 写作者、消费者和 Judge 的配置／历史分别隔离，评价侧没有创建、继续或修复写作者的能力。

写作者只获得公开来源；消费者只获得无预期答案的问题投影和记忆；完整题集／答案与消费者输出
进入独立评价侧。消费者可见的原文引用只是记忆中的来源定位，不等于拥有原始材料读取能力。

## 工程核查与命令

此前针对存储、历史修订、并发防覆盖、幂等、checkpoint 分离和真实隔离读取补跑的 **8 项测试**通过。
工作空间、MCP、SDK 及其依赖本轮未修改，复用原 **47 项**开发回归；没有无依据重复全套。

新增探针由另一工程测试 Agent 独立只读核查，聚焦 32 个工程 fixture、并发实际区间、
权限配置、读取身份、完整分母和首写保留；不读取隐藏答案或私有语义报告，不启动模型或写业务资源。
详见[独立工程记录](2026-10-28-v5-shared-memory-independent-functional-test.md)。
最终脚本 Ruff／格式检查通过，6 份相关 Markdown 的 92 个本地链接／21 个锚点检查通过。
GitNexus 索引仍滞后，本轮按新增探针的实际调用、diff、真实回执及上述独立核查确认影响，
不宣称图索引覆盖。只提交本轮自有脚本和记录，不包含无关 GraphRAG 改动。

实际执行命令（仓库根目录，复跑需使用新的自有证据目录）：

```bash
export UV_PROJECT_ENVIRONMENT="$PWD/workspaces/v5-codex-p0/.venv"
uv run --locked --project modeling_team/v5 python modeling_team/v5/scripts/memory_case.py write \
  --output-dir workspaces/v5-codex-p0/shared-memory-live-001
uv run --locked --project modeling_team/v5 python modeling_team/v5/scripts/memory_case.py consume \
  --output-dir workspaces/v5-codex-p0/shared-memory-live-001
uv run --locked --project modeling_team/v5 python modeling_team/v5/scripts/memory_case.py evaluate \
  --output-dir workspaces/v5-codex-p0/shared-memory-live-001
uv run --locked --project modeling_team/v5 ruff check modeling_team/v5/scripts/memory_case.py
uv run --locked --project modeling_team/v5 ruff format --check modeling_team/v5/scripts/memory_case.py
```

阶段输出不覆盖；若阶段中止，保留其目录和未知状态，不盲目从 write 重放同一目标。
全部本轮 native turn 已自然完成，4 个 SDK／provider owner 均已退出。
未创建平台临时 key；原共享 GLM 凭据不属于本轮可撤销资源。业务记忆及历史版本保留供后续读取。

## 用量、耗时与尚未覆盖范围

本轮托管运行区间为 **2026-10-28 09:32:02—09:37:55 UTC**，墙钟 **5 分 52 秒**；
native 活动区间合并约 **90.4 秒**，包含工具与结果格式纠正，不等于净业务推理时间。
工程实现、检查和文档时间另外发生，不混入语义有效时间。

| 参与者 | 已知输入 token | 已知输出 token | native turn |
| --- | ---: | ---: | ---: |
| 写作者 A | 5,615 | 381 | 1 |
| 写作者 B（含格式纠正） | 14,301 | 1,380 | 2 |
| 新消费者 | 3,191 | 388 | 1 |
| 独立 Judge | 4,729 | 404 | 1 |
| 合计 | **27,836** | **2,553** | **5** |

已知输入加输出 **30,389 token**；按每条原生 thread 的累计快照去重。
缓存输入是输入子集，不额外相加。外部 Host 与工程测试 Agent 的用量在本任务观察中为 unknown，
单列且不计任务金额。来源：本目录 `usage-observation.json` 及原始 usage/activity 文件。

本轮没有“无记忆”同条件对照，不宣称净降耗。仍待后续相应功能实现与验证：
真正矛盾的来源／决定、资料修订与撤回、摘要过期刷新、未知位置检索、权限变化、跨任务复用，
以及完整任务质量和成本比较。以上缺口不能被本次 6/6 或 P0 平台小链 6/6 关闭。
