# R2.1-001 M6 建模 Agent 自主业务语义缺口发现共享测试计划

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M6
- Design:
  `docs/delivery/designs/2026-07-28-r2-1-001-m6-autonomous-semantic-gap-discovery-design.md`
- Delivery record:
  `docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`
- Status: implemented — independent test Round 2 PASS
- Test rounds: append-only

## Fixed boundary

M6 uses the same bounded `C -> B -> A` business slice but a new raw multi-document source pack. The Agent
does not receive an ambiguity list, problem count, problem categories, hidden answers, M4/M5 artifacts,
answer model, Batch payload or acceptance query result.

The tester owns a hidden material-gap contract. It is an evaluation mapping, not an Agent prompt. Each
required gap must first pass the source-discoverability gate below.

## Completion gates

1. Independent source review proves every required material gap follows from a visible inconsistency,
   unresolved dependency or required consumer outcome; no arbitrary invisible fact is tested.
2. Static and mount inspection proves no Agent-visible file states or implies the expected gap count,
   category names or question checklist.
3. A fresh Agent performs a source-completeness assessment and asks every material business question
   without receiving the M4 explicit ambiguity list.
4. Every accepted question binds visible source evidence to a concrete model/query impact. Wording and
   ordering are not fixed.
5. Explicit facts are not re-asked. Extra questions pass only when the tester confirms their visible
   evidence and materiality; generic questionnaires or exhaustive enumeration fail.
6. Answers and uncertainty flow through M4's receipt, decision, Batch, validation, reasoning, query and
   blind-consumer evidence chain.
7. A fresh read-only Consumer recovers the applied target/contract, continuity result and explicit
   missing-score gap from public platform facts.
8. M4 regressions pass; no Dify-specific backend branch, persistent interview product or module-expansion
   work is introduced.
9. Independent tester appends a PASS round, cleans only uniquely owned runtime resources and verifies the
   normal service.
10. The modeling-attempt ledger proves no more than three fresh Codex subagents were asked to model.
    Each handoff contains no parent conversation or hidden contract and declares only the frozen input
    directory and permitted interfaces. Reaching attempt three forces a pause and user report.
11. Static review proves M6 does not stage or invoke M4's explicit-gap manifest, business brief,
    modeling prompt or bwrap Codex runner. The Host may create only one empty fresh Project and Ontology
    per attempt through the existing public HTTP API and pass their IDs. Every Build Session and
    semantic request and payload is chosen by the modeling subagent. When the collaboration MCP
    inventory cannot mutate the fresh scope, the Host may attach credentials and relay exactly one
    Agent-selected public HTTP `{method,path,body}` request unchanged. It must not rewrite, synthesize,
    repair or retry semantic content; otherwise the run fails. The Host otherwise only answers one
    eligible question at a time and performs read-only acceptance.

## Planned cases

| ID | Case | Expected evidence |
| --- | --- | --- |
| M6-01 | Raw-source pack | Separate realistic documents; hashes and mounts contain no explicit ambiguity list, count, categories or hidden answer. |
| M6-02 | Gap discoverability | Tester maps each required gap to visible source tension or an underdetermined required consumer outcome before Agent launch. |
| M6-03 | Autonomous completeness review | Agent records its own source-completeness assessment before principal schema modeling. |
| M6-04 | Invocation binding discovery | Agent notices that published versions exist while B's selected C version/binding rule is unresolved and asks a material business question. |
| M6-05 | Output identity discovery | Agent notices old/new contract fields lack an identity or evolution mapping and asks whether continuity is confirmed. |
| M6-06 | Missing-score discovery | Agent notices score absence is possible while downstream behavior is underdetermined and asks rather than inventing a fallback. |
| M6-07 | Question quality | Every required/extra question cites visible evidence and model/query impact; explicit facts, generic barrage and ontology-design delegation fail. |
| M6-08 | Serial clarification | One open question at a time; responses and receipts are bound without exposing hidden categories or answer count. |
| M6-09 | Answer-to-model chain | Confirmed decisions and uncertainty become immutable Batch rationale/model facts or named explicit gaps. |
| M6-10 | Formal semantic path | Shape dry-run/apply, invalid-instance rejection, candidate ABox or one eligible correction, validation, reasoning, governed query and completion pass. |
| M6-11 | Blind consumer | Fresh Consumer derives target contract, continuity/discontinuity and explicit unknown only from public semantic facts. |
| M6-12 | Isolation and regression | No inherited conversation, undeclared repository file, M4/M5 answer artifact or Dify-specific platform code is exposed; focused M4 and applicable platform regressions pass. |
| M6-13 | Runtime closure | Owned isolated resources are removed; regular backend/frontend health checks pass. |
| M6-14 | Attempt budget | Append-only ledger contains 1–3 unique modeling subagents/run roots; a fourth launch is rejected and attempt three forces pause/report. |
| M6-15 | Collaboration adapter | `fork_turns=none` handoff, Host-only empty Project/Ontology creation, sequential question/answer evidence and Agent-selected request hashes are recorded; relay evidence proves Host added only credentials, did not rewrite/retry payloads, and used no M4 runner or extra Runtime. |

## Negative controls

- Replace the raw pack with a fixture containing the explicit M4 question list: isolation gate must fail
  before Agent launch.
- Add an expected count or category hint to a staged prompt: manifest/static gate must fail.
- Include an evaluator-required gap with no visible source tension or consumer consequence: the
  discoverability gate must reject the test itself.
- Submit one combined questionnaire or a generic “tell me everything uncertain” request: it cannot satisfy
  the three material cases.
- Ask the user to choose classes, properties, IRIs or Shapes: question-quality gate fails.
- Proceed using a default latest-version, successor mapping or missing-score fallback without a confirmed
  answer: final semantic audit fails.
- Produce a correct decision log without corresponding applied facts and consumer result: acceptance fails.

## Execution order

1. Freeze the raw source pack, hidden material-gap contract and hashes.
2. Run source-discoverability review independently of the modeling Agent.
3. Run static/mount/no-prior-artifact checks.
4. Host-create one empty Project/Ontology, record their empty baseline and pass only their IDs; start
   one fresh autonomous discovery Producer using a Codex subagent with no inherited turns and only the
   staged directory plus the permitted ontology-platform public-call interface. Prefer the connected
   MCP when it exposes the required mutation tools; otherwise use the exact-request credential relay
   without changing the modeling attempt or preparing another Runtime.
5. Answer one eligible, source-grounded question at a time through collaboration follow-ups; append the
   question/answer evidence without disclosing hidden categories or remaining count.
6. If an attempt fails, preserve it and optionally start another fresh Producer; never exceed three.
7. If an attempt completes, run independent semantic assertions and one fresh blind Consumer.
8. Run focused M4 and relevant platform regressions, Ruff and `git diff --check`.
9. Clean uniquely owned isolated runtime resources and verify `ontology-platform.service`, `:8001` and
   `:5173`.

For the accepted live run, the immutable Agent-visible task still records the initially expected MCP
transport. Capability inspection showed that the connected collaboration MCP inventory was read-only,
so the same isolated Agent received only the generic public-call contract and continued through the
credential relay. This historical input is not rewritten after execution; the correction and exact
request hashes are recorded in `runtime/m6-run-1/relay-evidence.json`.

No live M6 Agent is authorized by this planning document alone. Execution requires reviewed
implementation and a separate independent-test handoff, but is not gated on M5 completion.

## 测试轮次 1 — 2026-07-28T16:11:14+08:00

### 基线与范围

- 代码基线：`HEAD=314a1a7`；工作区含本 M6 文档/场景的未提交实现，以及与本轮无关的既有 M5、迁移和
  顶层说明变更。未修改产品代码、语义数据或运行资源；本轮只追加此记录。
- 已执行：M6 冻结输入/隐藏合同静态审查、可发现性映射、尝试账本、问题质量、M6 已记录运行 ID 的
  数据库只读核验、M6/M4 聚焦回归、Ruff、`git diff --check` 和正常服务健康检查。
- 未执行：未启动新的建模 Agent、未创建/删除 Project、Ontology、Build Session 或语义数据；未因
  文档偏差启动第二次尝试（账本仍为 `1/3`）。

### 实际命令与结果

1. `PYTHONDONTWRITEBYTECODE=1 uv run --directory backend pytest -p no:cacheprovider ../docs/evaluation-scenarios/dify-workflow-impact-m6/tests`：`5 passed`。
2. `PYTHONDONTWRITEBYTECODE=1 uv run --directory backend pytest -p no:cacheprovider ../docs/evaluation-scenarios/dify-workflow-impact-m4/tests/test_m4_clarification.py`：`123 passed`。
3. `uv run --directory backend ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m6 ../docs/evaluation-scenarios/dify-workflow-impact-m4` 与 `git diff --check`：均通过。
4. 只读 SQL 核验 `89b67fef-e82a-470c-9eb9-928078a8b206`：Build Session 为
   `completed`、revision `3`；schema Batch `ac96ecb3-6b65-4c8b-862c-d18760a44e91` 和实例 Batch
   `849a6350-14cc-48c0-9252-1ac8ef41d725` 均为 `applied`；负例 Batch
   `93410be3-6404-4f18-9b86-5fd5351152fe` dry-run 为 `validation_failed`，含
   `shacl_violation`；validation `d548889a-67de-465e-a1f1-d4064408cc8a` 为
   `succeeded/conforms=true`，reasoning `219c3361-c674-4fbc-9d80-76065c3a1002` 为
   `succeeded/consistent=true`。Checkpoint 保留了一个绑定、字段连续性和 `explicit_unknown` 的完整查询结论。
5. `curl --fail http://127.0.0.1:8001/api/health`、`curl --fail http://127.0.0.1:5173/` 与
   `systemctl --user is-active ontology-platform.service`：后端 `{\"status\":\"ok\"}`、前端 `200`、服务 `active`。

### 用例结果与证据

| 用例 | 本轮结果 | 证据/结论 |
| --- | --- | --- |
| M6-01、M6-12 | PASS | `agent-input/manifest.json` 覆盖全部可见文件且哈希有效；M6 静态测试确认未泄露隐藏合同、问题数或类别，任务文件禁止读取仓库/M4/M5/隐藏材料。 |
| M6-02 | PASS | 三项 host-only gap 均映射至少两份可见资料：版本绑定（workflow/release）、字段身份（release/interface）及缺失评分（exception/consumer outcome）；静态测试通过。 |
| M6-03 至 M6-08 | PASS | `attempts.jsonl` 的唯一 `fork_turns=none` 运行按串行顺序提出三项资料驱动且具业务影响的问题；没有重问明确事实、问题轰炸或本体设计委托。 |
| M6-09 至 M6-11 | PASS | 应用实例的 rationale 将最新发布版、字段连续性及缺失评分的 `explicit_unknown` 写入模型；只读数据库的 checkpoint、validation、reasoning 与 README 所列 blind Consumer 结果相互一致。 |
| M6-10 | PASS | 已核验 Shape schema/实例两次 `apply_atomic`、一个含 `shacl_violation` 的负例、最终 validation/reasoning 与 Build Session completion。早期两个 schema dry-run 的 `validation_failed` 保留为未应用证据；未发生额外 ABox 修正。 |
| M6-13 | PASS | 正常服务存活且 8001/5173 健康；本轮未拥有或变更任何运行资源。 |
| M6-14 | PASS | append-only ledger 仅含 `m6-run-1`，唯一 Agent 为 `/root/m6_modeling_attempt_1`、`fork_turns=none`；静态测试同时证明三次后拒绝第四次。 |
| M6-15 | FAIL | 实际证据 `runtime/m6-run-1/next-request.json` 与 README 显示：协作子代理发出逐条 `{method,path,body}` HTTP 请求，由 Host 附加凭证后原样转发。设计 v3、需求与 README 已反映该受限 MCP 清单导致的 credential relay；但本共享计划第 45–47 行和第 68、91 行仍规定“existing MCP / connector-side modeling calls”。因此计划的固定验收合同与实际运行不一致，不能在未同步计划前判定 M6 PASS。 |

### 缺陷与结论

- **M6-DOC-001（P1，文档/验收合同不一致）**
  - 复现：比较本计划 M6-15/完成门槛中“建模子代理通过 existing MCP”的表述，与
    `docs/evaluation-scenarios/dify-workflow-impact-m6/runtime/m6-run-1/next-request.json` 的 REST
    completion 请求及 README/设计 v3 中的逐请求 Host credential relay。
  - 期望：共享测试计划、设计、Agent-visible 任务和实际协作传输使用同一明确合同，并可检查 Host
    只附凭证/原样转发、不选择或修复语义 payload。
  - 实际：设计、需求和 README 已切换到 relay；共享测试计划仍要求 MCP，且没有 relay 原样转发的
    专项断言。
  - 建议：主 agent 先将**同一份**共享测试计划的 M6-15、完成门槛与执行步骤同步为实际 credential
    relay 合同，并补足其不可改写/不可重试的可验证证据；随后进行无需新建模尝试的文档与静态复测。

**本轮结论：FAIL。** 产品语义路径、隔离静态检查、问题发现、`1/3` 尝试预算、批次、validation、
reasoning、Build Session 与 M4 回归均通过；但 M6 的权威共享测试计划尚未与实际 Host credential relay
传输对齐，不能据此给出独立 PASS。

## 测试轮次 2 — 2026-07-28T16:11:14+08:00（M6-DOC-001 静态复测）

### 范围与实际命令

- 本轮只复测 Round 1 的 M6-DOC-001；未启动建模/消费 Agent，未调用任何语义写接口，`attempts.jsonl`
  仍为唯一的 `m6-run-1`（`1/3`）。
- `PYTHONDONTWRITEBYTECODE=1 uv run --directory backend pytest -p no:cacheprovider ../docs/evaluation-scenarios/dify-workflow-impact-m6/tests`：`5 passed`。
- `uv run --directory backend ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m6` 与
  `git diff --check`：均通过。

### 复测结果

| 用例/缺陷 | 本轮结果 | 证据 |
| --- | --- | --- |
| M6-DOC-001 / M6-15 | FIXED / PASS | 计划完成门槛、M6-15 和执行步骤现在一致规定：MCP 无写权限时，Host 仅附凭证并原样转发一条由 Agent 选择的 `{method,path,body}` 请求，禁止改写、补造、修复或重试。`runtime/m6-run-1/relay-evidence.json` 记录 allow/forbid 策略、`host_initiated_retries=0`、语义 ID 和最终请求 SHA-256；其 `3e262d…ede4a` 与 `next-request.json` 实际 SHA-256 一致。 |
| 历史输入隔离 | PASS | `agent-input/task.md` 仍保留当时的 MCP 原始指令及 manifest 哈希 `728235…8291c`；计划明确将后来发现的只读 MCP 能力与 relay 记录在运行证据中，不倒改 Agent 可见历史输入。 |
| M6-01、M6-14 | PASS | 静态测试 `5 passed`，且账本仍为 8 行、一个 `fork_turns=none` 的 modeling start；没有新增尝试。 |

**本轮结论：PASS。** M6-DOC-001 已修复；Round 1 的产品语义、隔离和运行证据继续有效。本轮没有发现
新的缺陷，也不需要需求开发 agent 再修复或消耗新的建模尝试。
