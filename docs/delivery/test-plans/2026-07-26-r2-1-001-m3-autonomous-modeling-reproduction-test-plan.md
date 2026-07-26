# R2.1-001 M3 自主建模 Agent 复现共享测试计划

- Requirement: `docs/requirements/requirements-v2.1.md` R2.1-001 M3
- Functional contract:
  `docs/evaluation-scenarios/dify-workflow-impact-m3/business-brief.md`
- Delivery record:
  `docs/delivery/records/2026-07-23-r2-1-001-ontology-modeling-workflow-reconstruction-delivery-record.md`
- Status: planned
- Test rounds: append-only

M3 不单独冻结正式技术设计。本需求 M3 条目、业务说明、允许输入、Agent 自己的建模假设与追加式
执行日志共同构成功能合同；验收只比较语义行为，不与 M1/M2 RDF 图同构。

## 输入隔离

自主建模 Agent 只允许读取：

- `docs/evaluation-scenarios/dify-workflow-impact-m3/input-pack/input-manifest.json`
  逐文件列出的净化输入；
- manifest 允许的 live input：隔离平台公开 `/openapi.json`、`/api/` 调用及本次 M3 自己产生的
  确定性反馈。

完整 `requirements-v2.1.md` 不进入 Agent 挂载；它由净化后的 `input-pack/m3-contract.md`
替代。不得读取或复制 M1/M2 的 `ontology.ttl`、`shapes.ttl`、Fixture TTL、答案型 SPARQL、
`run_rehearsal.py`、README、演练日志、runtime record、最终 Batch payload、成功 Project 内容或
独立验收答案。测试方可以读取这些材料形成 withheld 行为断言，但不得把答案反馈给建模 Agent。

冻结 manifest：
`docs/evaluation-scenarios/dify-workflow-impact-m3/input-pack/input-manifest.json`，
SHA-256 `30ba21f0b9331fff394ef42b0449f34f43f7ad8e243e5d25ce50dc9932d12bda`。
定义 `declared mount set = {"input-manifest.json"} ∪ files[].mounted_path`；manifest 本身不作
自引用条目，其哈希由本计划和启动器常量独立固定。

由于当前 OpenAPI/MCP 把 `ModelingItemInput.payload` 暴露为无约束 JSON object，冻结输入包包含
`platform/modeling-command-contract.md`。它只公开当前通用 handler/compiler 已执行的 Batch
envelope、命令字段、`item_ref`、literal/object relation、Shape path 和失败合同，不包含 Dify
资源名、本体结构、IRI、Batch 答案或查询。M3 Agent 可以使用该工具合同，但仍须自主选择所有语义
结构。将来是否把这份合同产品化为 typed OpenAPI/MCP schema，属于 M3 之后的通用平台改进，不是
本轮建模完成门槛。

### 可执行的 Agent 启动合同

自主建模 Agent 不是从当前主 Agent 对话 fork。运行负责人必须用一个全新、非 resume/fork 的
外部 Agent 进程，并同时满足：

1. 初始 prompt 固定为 manifest 中的 `modeling-agent-prompt.md`；不直接传入完整需求、聊天历史
   或额外业务提示；
2. 使用临时 `CODEX_HOME`，其中只提供本次认证所需文件，不包含 memory、history、session、
   rollout、plugin 或项目级旧状态；
3. 使用 `bubblewrap` 或等价 OS 隔离：宿主仓库和宿主 `.codex` 不可见；启动器逐文件校验
   manifest SHA-256 并复制到 staging 后，只读挂载 staging，不得挂载任何源目录；另提供一个
   空白可写工作目录；
4. API key 仅通过进程环境传入，不写入 prompt、命令参数、文件或 transcript；
5. 使用 JSONL 事件模式保存完整 prompt、tool call 和 tool result transcript；结束后以实际 API
   key 做秘密扫描，并断言 manifest 自身哈希等于上述冻结值，保存每个源文件/实际 staged 文件
   哈希、精确 mount 参数和隔离探针结果；
6. transcript 若出现禁止路径访问、答案内容、既有项目内容或主 Agent 的语义提示，本轮作废；
   若无法建立或证明上述技术隔离，只能报告 M3 `INCONCLUSIVE`，不得 PASS。

### 无网络工具的公共 API 传输

Codex `workspace-write` sandbox 禁止 Agent tool process 使用 Unix socket，因此 M3 不放宽沙箱，
也不恢复 Agent 网络。公共 API 改由宿主文件队列 RPC 传输：

1. Agent 只能在其可写工作区 `rpc/requests` 原子提交带严格 ID、method、`/openapi.json` 或
   `/api/` path、非 Authorization headers 和 JSON body 的请求文件；
2. 宿主 gateway 仅从固定 spool 目录读取严格命名、大小受限的普通文件，使用 no-follow/
   exclusive-open 或等价机制拒绝 symlink、路径穿越、重复 ID 和非规则文件；
3. gateway 在进程内注入真实 key，转发到 `127.0.0.1:8012`，再把 status、安全 headers 和 body
   原子写入 gateway 独占的宿主 response 目录；该目录在 namespace 内单独只读挂载，覆盖
   Agent 工作区的空 target，Agent 无法预创建、修改、替换或删除 response；Agent 永远不接收
   真实 key；
4. gateway 将处理过的规范 request 字节保存到宿主只读 archive，并在 audit 记录 request 与
   response 文件规范字节的 SHA-256、request ID、method、path、status、策略结果和时间；
   audit 不保存 Authorization 或正文；
5. response 由宿主保留到独立验收结束；独立测试逐项匹配 archive、audit、只读 response、
   Agent transcript/runtime record 的 ID 与 hash，证明 Agent 使用的反馈就是平台实际响应；
6. Agent 不获得 AF_INET/AF_UNIX 平台通道，Codex web/search/browser/plugin/memory 功能保持
   禁用。无法通过文件队列完成时停止，不得切换 `danger-full-access`。

启动器和独立测试必须验证 symlink、路径穿越、超大 body、非 `/api/` path、客户端
Authorization、重复 ID、Agent 预创建/伪造/写后替换/删除 response 均 fail closed，并证明实际
网关调用、规范 request archive、只读 response 与 transcript 中的 Agent 请求/消费逐项对应。

独立消费 Agent 使用第二个全新临时 `CODEX_HOME` 和独立 OS 隔离进程。它只接收业务问题、M3
Project/Ontology 标识、通用只读查询合同和独立只读 file-spool gateway；不接收凭据，也不挂载
业务说明、建模工作目录、
modeling rationale、执行日志、M1/M2 答案或建模 Agent transcript。其完整 JSONL transcript
同样接受输入、访问和秘密审计。

独立测试必须断言启动器实际 staged 文件集合与 `declared mount set` 完全相等、manifest 哈希
等于冻结值、每个条目哈希匹配，实际只读 mount 只包含该 staging 根，并确认完整
`requirements-v2.1.md` 和所有禁止材料在 namespace 中不可见。

## Completion gates

1. 新 Project、Ontology、Build Session 和分层 Evidence 归属一致；隔离服务为 `rdf_primary`，
   常驻服务保持 `legacy_only`。
2. 自主 Agent 没有读取禁止输入，主 Agent 没有作 `semantic-decision` 人工介入。
3. 官方来源与合成 Fixture 使用直接原文 Evidence；建模判断只进入 Item `rationale`、
   Checkpoint 和执行日志，不创建推断型 Evidence。
4. 至少一次 immutable dry-run 决策与修正链可追踪；失败 Attempt 不覆盖、不 apply。
5. 所有成功写入均由 validated Batch 经 lease、fresh workspace version 和 `apply_atomic` 完成。
6. 显式使用 Graph Set 的 `shapes` member；正式数据 conforms，Agent 自己的已知负例被同一约束
   拒绝。
7. reasoning 成功且产生 Agent 预先声明、当前平台支持的推论。
8. 建模 Agent 自己的 competency queries 取得 B/A 候选、完整 C -> B -> A 数据使用上下文、
   draft/latest 分离和显式未知。
9. 独立消费 Agent 只使用 M3 平台事实，形成可追溯解释；不输出平台或本体生成的影响等级。
10. 独立测试以 withheld 行为断言复核结果，不要求资源名称、IRI 或图结构与 M1/M2 相同。
11. 无 semantic edit、dataset load、`validate=false`、直接 DB/RDF 写入或 Dify 专属产品代码。
12. 运行记录无秘密，失败、重试、人工介入、未解决问题和下一轮建议完整。
13. 独立测试 PASS；隔离服务停止；常驻服务、backend 和 frontend 健康。

## Planned cases

| ID | Case | Expected evidence |
| --- | --- | --- |
| M3-01 | Input-isolation audit | fresh contexts; OS allowlist; manifest hashes; complete transcripts |
| M3-02 | Runtime mode probes | regular `legacy_only`; isolated `rdf_primary` |
| M3-03 | Fresh workspace | unique workspace; official/synthetic Evidence; separate rationale |
| M3-04 | Autonomous terminology/model hypothesis | Agent rationale without main-agent semantic choice |
| M3-05 | Dry-run decision loop | immutable Batch/Attempt/finding/decision/correction |
| M3-06 | Formal apply | validated candidates applied atomically with fresh version/lease |
| M3-07 | Shapes activation and negative control | explicit `shapes` member; positive conforms; invalid rejected |
| M3-08 | Reasoning | expected supported entailment returned |
| M3-09 | Published callers | exactly B and A as direct/transitive candidates |
| M3-10 | Full propagation context | C input/output through B and A bindings/uses is connected |
| M3-11 | Draft/latest boundary | draft deletion is not current published deletion |
| M3-12 | Explicit gap | missing detail and explanation returned, not treated as no impact |
| M3-13 | Consumer interpretation | source/synthetic/inference/judgment attribution per conclusion |
| M3-14 | Traceability and autonomy | retries/interventions/issues/recommendations recorded |
| M3-15 | No-bypass/product-boundary review | no forbidden path or Dify-specific product change |
| M3-16 | Regression/runtime closure | focused checks, service health, isolated cleanup |

## Required verification

The autonomous Agent must execute its own validation, reasoning, and scoped queries through public platform
interfaces. The independent tester must additionally:

- inspect the stable diff and safe M3 run record;
- read the M3 Project, Evidence, Build Session, Batch/Attempt histories and semantic run records;
- construct withheld queries from the frozen business behavior rather than reuse the Agent's query text;
- 在仅通过正式 Modeling Batch 写入的临时验收 Project 中，对每个必需传播角色分别执行 remove
  与 unrelated-sentinel replace：B 输入 Binding 两端、B 输出 Binding 两端、B 变量使用、
  B 变量/Output 产生、A Binding 两端、A 下游使用；加入正交诱饵分支，并断言同一结果行中的
  Workflow Version、Invocation、Binding、Variable 和 Use 身份共绑定；
- 对建模 Agent 提交的 competency queries 与独立 tester 自建的 withheld queries 分别执行上述
  全链反笛卡尔测试，不复用 M1/M2 查询文本，不直接修改 RDF/数据库；
- reproduce an invalid Invocation rejection against the applied Shapes;
- run the existing M1 and M2 offline behavior suites as regressions;
- run focused backend tests for Modeling Batch, validation, reasoning and scoped semantic query;
- run Ruff over executable M3 artifacts and `git diff --check`;
- verify the regular service and endpoints before and after stopping the isolated backend.

## Test rounds

Initial state: no M3 independent test round had run before the Round 1 record below.

### Round 1 — 2026-07-26 independent acceptance (FAIL)

- Stable state under test: uncommitted M3 scenario package, final run
  `runtime/runs/m3-companion-autonomous-20260726`; retained Project
  `21ba4269-d027-4322-aee1-b911874c4e0a`, Ontology
  `34b493be-c3b4-4ee3-b32e-1286b110f298`, Build Session
  `4afd27ca-089b-48c4-864a-c22737514b0d`; isolated backend `127.0.0.1:8012`.
- Result: `FAIL`. The retained model and all regression gates below are readable/pass, but the
  autonomous-run evidence cannot establish the required one-to-one relationship between Agent
  requests/response consumption and the host gateway evidence. This invalidates the M3 autonomy
  and traceability completion gates; an independent consumer and mutation acceptance cannot turn
  an inadmissible modeling run into a PASS.

| Case | Result | Actual result and evidence |
| --- | --- | --- |
| M3-01 | FAIL | Frozen manifest SHA-256 is `30ba21f0b9331fff394ef42b0449f34f43f7ad8e243e5d25ce50dc9932d12bda`; all 14 declared source hashes and the 15-file declared mount set (including the manifest) match staging. `audit-recheck-3.json` also reports no secret/forbidden Agent-controlled host path. However, `gateway.jsonl` has 161 `forwarded` entries and both archive/response file sets have 161 files with matching recorded SHA-256, while **all 161 request IDs are absent from `agent-transcript.jsonl`**. `work/runtime-record.json` lists only 20 calls and no request/response hashes. Therefore the plan's required archive/audit/read-only-response/transcript/runtime-record per-ID correspondence is not proven. |
| M3-02 | PASS | `curl --fail http://127.0.0.1:8001/api/health`, `curl --fail http://127.0.0.1:8012/api/health`, and `curl --fail http://127.0.0.1:5173/` all succeeded. Isolated audit records `product_write_mode=rdf_primary`; the ordinary service remains separately healthy. |
| M3-03–M3-08 | PASS with linked traceability defect | Public retained resources are readable: the Project was created at `2026-07-26T10:10:54.515807Z`; the completed Build Session has the expected Project and Ontology IDs; five Evidence References separate four official/synthetic excerpts plus the explicit-gap excerpt. Two Batches are `applied`, and the negative dry-run Batch has three findings including `shacl_violation`. The Graph Set has an explicit `shapes` member. `runtime-record.json` records `conforms=true` and successful reasoning. Its `run_tag` is nevertheless `m3-autonomous-20260726`, not its enclosing final-run tag `m3-companion-autonomous-20260726`, which is a secondary traceability inconsistency. |
| M3-09–M3-12 | NOT EXECUTED | Withheld query and nine-link remove/sentinel/decoy mutation tests require an admissible, fully traceable baseline. They were not run after M3-01 invalidated that prerequisite; they must run on the fresh repaired run, through formal Modeling Batch only. |
| M3-13 | NOT EXECUTED | The required fresh consumer Agent was not launched because M3-01 means its allowed platform response spool cannot be linked to an admissible autonomous-modeling evidence chain. A fresh repaired producer run must precede the independently isolated, read-only consumer test. |
| M3-14–M3-15 | FAIL | The run retains retries and the tool-contract intervention, and no product Dify customization was found in the M3 source diff. But missing request-consumption receipts and the runtime-record run-tag mismatch mean the required complete traceability/autonomy record is not satisfied. |
| M3-16 | PASS (partial closure) | `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py`: 13/13; M2 scenario: 5/5; M3 launcher: 8/8. `cd backend && uv run pytest tests/test_modeling_batches_service.py tests/test_semantic_validation.py tests/test_semantic_reasoning.py tests/test_semantic_context_query_api.py`: 69/69 (five non-failing dependency deprecation warnings). `cd backend && uv run ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m3` and `git diff --check` passed. Isolated-backend stopping/after-stop checks are deferred to final acceptance. |

#### Defects

1. **High — gateway evidence does not prove Agent request/response consumption.**
   - Reproduction: parse `runtime/runs/m3-companion-autonomous-20260726/gateway.jsonl` for
     `policy=forwarded`, then search each `request_id` in
     `agent-transcript.jsonl` and `work/runtime-record.json`.
   - Expected: every forwarded request ID, canonical archive SHA-256 and response SHA-256 is
     represented in Agent-controlled request/response-consumption evidence and the safe runtime
     record, as required by Input Isolation / file-spool clauses 4–5.
   - Actual: 161/161 IDs are missing from the transcript; the runtime record retains only 20 call
     summaries and neither set of hashes. Archive/host response hashes alone show gateway activity,
     not that the Agent consumed those replies.
   - Evidence: `gateway.jsonl`, `gateway-request-archive/`, `gateway-responses/`,
     `agent-transcript.jsonl`, `work/runtime-record.json`, and the command/result recorded above.
   - Required repair: make the isolated client append an Agent-controlled receipt for every request
     and response it consumes (ID plus canonical request/response SHA-256), make the launcher fail
     closed unless it exactly matches archive/audit/host response, then launch a **new** fresh Agent;
     do not retrofit the old transcript.

2. **Medium — final runtime record misidentifies its run tag.**
   - Reproduction: compare `work/runtime-record.json` (`run_tag=m3-autonomous-20260726`) with its
     enclosing run directory and `audit-recheck-3.json` (`m3-companion-autonomous-20260726`).
   - Expected: one immutable run identity across runtime record, transcript/audit and directory.
   - Actual: the record carries an earlier/non-final tag, so it cannot by itself identify the final
     isolated execution.
   - Required repair: generate the record from the launcher-supplied run tag and test equality.

Recommendation: return both confirmed defects to the requirement developer, require a fresh
producer run after the receipt/identity repair, then repeat this same plan as Round 2 starting with
M3-01 and continuing through the consumer and formal anti-Cartesian mutation gates.

### Round 2 — 2026-07-26 independent acceptance (FAIL)

- Stable state under test: fresh Cycle 4 producer run
  `runtime/runs/m3-receipts-cycle4-rerun-20260726`; Project
  `22226ade-e3f7-4746-ba63-b486620a2115`, Ontology
  `f3ca5853-4d99-43ca-aacc-03d31034a147`, Build Session
  `c4f7a809-769a-4fa6-9d15-05b244ffe1d8`; manifest SHA-256
  `febdc765818a63d02ce68e7341b51d01c2ed52e334b2194540a769cb252356ab`.
- Result: `FAIL`. Round 1 receipt/run-identity defects are fixed, and the retained formal model
  evidence/read-only runtime gates are readable. The fresh producer nevertheless left its Build
  Session active with no Checkpoint or completion. M3's frozen contract requires the Agent's model
  decisions/progress to be recorded through Item rationale, Build Checkpoint and execution log; a
  main/developer-side post-hoc completion would not prove autonomous recording. This is a core
  traceability failure, so the fresh consumer and temporary-project mutation gates cannot accept it.

| Case | Result | Actual result and evidence |
| --- | --- | --- |
| M3-01 | PASS | Independent `receipt_audit` returned `passed=true`, `forwarded_count=74`, `receipt_count=74`, receipt-log SHA-256 `fff770872bb6938f4a19ac21c5156e307f264a18e32c3ae4535b8c2327bd3335`, no errors. This verifies the exact ID set plus archive request hash, raw host-response hash, status, injected run tag, runtime mirror and `M3_RECEIPT_SUMMARY`. `audit.json`/`audit-recheck.json` report no secret or forbidden Agent-controlled host paths; staged declared mount set has 15 files and manifest hash matches. |
| M3-02 | PASS | 8001, 8012 and 5173 health checks pass. The isolated audit records `product_write_mode=rdf_primary`. |
| M3-03–M3-08 | FAIL | Project and Ontology are fresh and readable; nine Evidence References separate official and synthetic excerpts. TBox/fixture dry-runs and `apply_atomic` Attempts are retained; invalid Invocation Batch `45a15485-4c1e-467e-9b3e-cb2bdfa3e023` is dry-run/`validation_failed` with `shacl_violation`; Graph Set explicitly contains `shapes`; runtime record reports validation `conforms=true` and reasoning `succeeded`. But `GET /api/build-sessions/c4f7a809-769a-4fa6-9d15-05b244ffe1d8` returns `status=active`, `completed_at=null`, `latest_checkpoint=null`, `unresolved_items=[]`; the producer transcript contains no Build Checkpoint or `:complete` request. |
| M3-09–M3-13 | NOT EXECUTED | The required formal temporary-Project nine-link remove/sentinel/decoy tests and the independently isolated read-only consumer cannot turn an incompletely recorded producer process into acceptance. They must execute against a fresh producer run that itself records Agent-authored checkpoints/completion. |
| M3-14–M3-15 | FAIL | Receipts, correction and tool-contract intervention are retained, and no forbidden write path was observed. The required Build Checkpoint/progress record is absent, so traceability is incomplete. |
| M3-16 | PASS (partial closure) | M1 offline suite 13/13, M2 suite 5/5, M3 launcher suite 11/11, focused backend suite 69/69, M3 Ruff and `git diff --check` all pass. The backend suite emitted five non-failing dependency deprecation warnings. |

#### Defect

1. **High — autonomous producer did not record or complete its Build Session.**
   - Reproduction: `GET /api/build-sessions/c4f7a809-769a-4fa6-9d15-05b244ffe1d8` on isolated 8012.
   - Expected: Agent-authored checkpoint(s) recording the formal dry-run/apply/validation/reasoning
     progress and a completed session with the safe completion summary/unresolved item, matching the
     runtime record and transcript.
   - Actual: public state is `active`, `completed_at=null`, `latest_checkpoint=null`; no producer
     transcript request writes a checkpoint or calls `:complete`.
   - Evidence: fresh run `agent-transcript.jsonl`, `work/runtime-record.json`, and the public GET
     result above.
   - Required repair: update the autonomous Agent procedure to create its own checkpoint(s) and
     complete its own Build Session before declaring `DEVELOPMENT_READY`; assert this in the launcher
     audit and start a new fresh producer run. Do not have the operator append the missing records.

Round 1's two defects are **FIXED** by the exact receipt audit and run-tag mirror. Round 2 remains
`FAIL`; after the fresh-process repair, Round 3 must first retest the Build Session evidence and then
execute the previously unexecuted formal nine-link/decoy mutation tests and blind consumer-Agent test.

### Round 3 — 2026-07-26 independent acceptance (FAIL)

- Stable state under test: `runtime/runs/m3-session-cycle5-rerun-20260726`, Project
  `8c9e0e2c-1a36-415f-a677-0082151ef5e4`, Ontology
  `3999db8b-845c-4d1b-a99b-401889669059`, Build Session
  `006f4f0a-863b-4186-8357-c16b16b6911f`, checkpoint
  `4aab29a9-b17f-43d8-bfb8-a31ee022ba6b`.
- Result: `FAIL`. The three previous producer evidence defects are fixed: the public Build Session
  is completed with the Agent-authored handoff checkpoint, receipt audit is 40/40 exact, and the
  re-audit proves the 150 Agent artifacts retained fingerprint
  `42fe9a7c88014edcab99689f525e47206c78c589a7b20833439528c437e11d86` before/after its host read.
  Required independent consumer execution and the temporary-Project formal nine-role mutation suite
  are still absent from the delivered M3 test surface and were not executed in this round. The
  requirement does not permit replacing them with the producer's own queries or M1 offline tests.

| Case | Result | Actual result and evidence |
| --- | --- | --- |
| M3-01–M3-08 | PASS | Public Session is `completed` with non-null completion time and expected latest checkpoint; re-audit is `DEVELOPMENT_READY`. Independent receipt audit is 40 forwarded/40 receipts with no errors. Public negative Batch is dry-run `validation_failed` with `shacl_violation`; runtime record reports explicit-shapes `conforms=true` and successful consistent RDFS reasoning. M3 launcher tests pass 14/14, including vanished-entry and session/receipt negative coverage. |
| M3-09–M3-12 | NOT EXECUTED | No M3 test helper or retained test run creates a temporary Project solely through Modeling Batch and performs the required nine roles × remove/sentinel replacement, orthogonal decoys and same-row identity checks, for both producer and tester-withheld queries. |
| M3-13 | NOT EXECUTED | No second fresh isolated consumer process/read-only gateway/transcript/receipt artifacts exist. The producer run cannot substitute for this mandatory blind consumer check. |
| M3-14–M3-15 | PASS | The completed Agent checkpoint preserves hypothesis, accepted/rejected batches, validation/reasoning/query outcomes, retries, interventions, unresolved items and next recommendation; no forbidden Agent-controlled host-path or secret was found. |
| M3-16 | PASS (partial closure) | M1 13/13, M2 5/5, focused backend 69/69, M3 launcher 14/14, Ruff, diff check and 8001/8012/5173 health all passed. Backend warnings are five non-failing dependency deprecations. |

#### Remaining acceptance blocker

1. **High — mandatory independent behavior gates have no executed evidence.**
   - Expected: a tester-owned, formal-Modeling-Batch temporary Project proves all nine critical
     propagation roles through remove and unrelated-sentinel mutations plus decoys for producer and
     withheld queries; a second fresh, isolated read-only consumer Agent returns source/synthetic/
     inference/judgment-attributed explanation without a risk level.
   - Actual: no consumer or mutation test artifact/run is present under the M3 scenario package or
     Cycle5 runtime. Existing producer queries, M1 offline mutations and backend unit tests do not
     exercise either M3-specific independent gate.
   - Required repair: implement tester-owned M3 acceptance helpers, execute them against a fresh
     temporary Project through public Modeling Batch only, retain their audit/receipt/transcript
     evidence, then append a retest round without relaxing either gate.

### Round 4 — 2026-07-26 independent acceptance (FAIL)

- Purpose: execute the newly supplied tester-owned mutation and blind-consumer harnesses against the
  accepted Cycle5 producer.
- Result: `FAIL` before behavior acceptance. Both new harnesses contain independently reproducible
  contract defects, so they cannot establish their required gates.

| Case | Result | Actual result and evidence |
| --- | --- | --- |
| Consumer isolation/attribution | FAIL | Fresh consumer run `m3-consumer-round4-20260726` had a fresh home, OS isolation and a three-file allowlist. It exited with 0 requests/0 receipts because the launcher mounts its inputs at `/opt`, while `consumer-prompt.md` never tells the Agent to read `/opt`; the Agent searched `/mnt` and honestly reported missing input. `audit.json` is `INCONCLUSIVE` because `gateway.jsonl` never existed. This is a harness contract failure, not a consumer answer. |
| Formal nine-role mutation harness | FAIL (static acceptance-tool review) | `tests/m3_acceptance_mutations.py` validates the number of roles and records `expected`, actual query responses and identity columns, but it never evaluates expected versus actual, same-row identity, remove/sentinel effect or decoy exclusion and never returns nonzero on semantic assertion failure. Its output therefore cannot prove the mandatory mutations even if all 18 variants run. |
| Tool safety review | PASS | The mutation runner contains no embedded ontology/query/expected answer; consumer gateway restricts writes to GET plus scoped SPARQL query. `tests/test_m3_acceptance_tools.py` covers its nine-role shape, read-only policy and consumer staging/write rejection. |

#### Defects

1. **High — consumer prompt omits its actual staged input path.**
   The launcher uses `/opt`; prompt must explicitly require `/opt/consumer-request.json` and
   `/opt/consumer-read-query-contract.md`, then a new isolated consumer tag must run.
2. **High — mutation runner has no assertion evaluator.**
   It must compare tester-specified expected row/identity and mutation effects to actual results,
   identify per-variant PASS/FAIL, and exit nonzero on any mismatch before it is usable for M3-09–12.

### Round 7 — 2026-07-26 independent acceptance (PASS)

- Stable producer under test: retained Cycle5 run
  `runtime/runs/m3-session-cycle5-rerun-20260726`, Project
  `8c9e0e2c-1a36-415f-a677-0082151ef5e4`, Ontology
  `3999db8b-845c-4d1b-a99b-401889669059`, Build Session
  `006f4f0a-863b-4186-8357-c16b16b6911f`, checkpoint
  `4aab29a9-b17f-43d8-bfb8-a31ee022ba6b`. Workspace remained uncommitted during the test.
- Result: `PASS`. Earlier receipt/run-tag, Build Session, consumer staging/receipt/terminal parsing,
  Modeling Batch invocation, and mutation-observation defects were retested on fresh evidence and
  closed. The temporary acceptance Projects were created and mutated only through public formal
  Modeling Batch endpoints; no production implementation was changed by the tester.

| Case | Result | Actual result and evidence |
| --- | --- | --- |
| M3-01–M3-08 | PASS | Cycle5 public Build Session is completed with the expected Agent-authored checkpoint. `runtime/runs/m3-session-cycle5-rerun-20260726/audit-recheck.json` records the exact receipt/host archive re-audit and retained-artifact fingerprint `42fe9a7c88014edcab99689f525e47206c78c589a7b20833439528c437e11d86` before/after inspection. The retained formal batches, explicit Shapes, validation and reasoning records remain readable. |
| M3-09–M3-12 | PASS | Tester-owned specification `docs/evaluation-scenarios/dify-workflow-impact-m3/tests/acceptance-artifacts/round6-mutation-spec.json` defines all nine required roles: both B input Binding ends, both B output Binding ends, B variable use, B variable/output production, both A Binding ends, and A downstream use. Final run `round7-mutations-cycle14.json` has `20` isolated variants, `9/9` evaluations PASS, no Batch failures and no query failures. Baseline and a valid orthogonal `gap-explanation` decoy retain one identity-bound row; all 18 formal remove/unrelated-sentinel `update_fact` mutations validate and apply, then break both the producer-behavior query and independently structured withheld query. |
| M3-13 | PASS | Fresh isolated consumer `runtime/consumer-runs/m3-consumer-round7-cycle12-20260726/audit.json` is `CONSUMER_READY` with a fresh Codex home, passing isolation probe, `10/10` receipt-to-gateway operations, operation audit, artifact/secret audit and process-argv audit. Its transcript returns the required source/synthetic/inference/judgment-attributed B/A explanation, distinguishes published from draft-only change, records unknowns, and assigns no risk level. |
| M3-14–M3-15 | PASS | Producer and consumer records retain fresh isolated execution, receipt mirrors, no forbidden Agent-controlled host path, and no secret exposure. Consumer terminal parsing now parses `agent_message.text` from JSONL rather than raw escaped JSONL text; `CONSUMER_RESULT CONSUMER_READY` is proven by the Cycle12 audit and transcript. |
| M3-16 | PASS | Commands actually run: `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m1/tests/test_scenario.py` (13/13); `uv run --directory backend python ../docs/evaluation-scenarios/dify-workflow-impact-m2/tests/test_scenario_m2.py` (5/5); `uv run --directory backend pytest ../docs/evaluation-scenarios/dify-workflow-impact-m3/tests` (27/27); `uv run --directory backend pytest tests/test_modeling_batches_service.py tests/test_semantic_validation.py tests/test_semantic_reasoning.py tests/test_semantic_context_query_api.py` (69/69; five non-failing deprecation warnings); `uv run --directory backend ruff check ../docs/evaluation-scenarios/dify-workflow-impact-m3`; and `git diff --check`. The regular and isolated backends plus frontend were healthy through `curl --fail` at `8001/api/health`, `8012/api/health`, and `5173/`. |

#### Round result and defects

- `PASS`: all required M3 acceptance gates, the independent consumer, formal nine-role anti-Cartesian
  mutations, necessary adjacent regressions and runtime health checks passed.
- No active product defect remains from this round. The intermediate harness defects discovered in
  this round (Modeling Batch body `session_id`, consumer terminal JSONL parsing, SPARQL response
  envelope extraction, canonical `http_status`, and raw temporary-Project decoy comparison) are
  covered by the final passing M3 test suite and Cycle14 evidence; preserve the earlier artifacts as
  historical failed-round evidence rather than overwriting them.

### Round 5 — historical retrospective (BLOCKED)

- Historical run tag: `runtime/consumer-runs/m3-consumer-round5-20260726`.
- Result: `BLOCKED`. The fresh consumer was launched but did not reach a terminal Agent result;
  its recorded `audit.json` remains `INCONCLUSIVE` with no Codex exit code, no receipt audit and no
  operation audit. It was manually stopped after the consumer could not use the intended staged
  read-only client path.
- Evidence and defect: `agent-transcript.jsonl`, `gateway.jsonl`, and `audit.json` retain the
  blocked execution. The missing mounted-client/consumer-path contract prevented a valid answer or
  receipt audit. Unblock condition was an explicit staged `/opt/m3_readonly_rpc.py` contract and a
  new fresh consumer tag; this was subsequently exercised in Round 6 and fully closed in Round 7.

### Round 6 — historical retrospective (FAIL)

- Historical run tag: `runtime/consumer-runs/m3-consumer-round6-20260726`.
- Result: `FAIL`. The fresh read-only consumer completed with exit code `0`, made eight allowed
  forwarded reads, and produced a fact-attributed B/A answer; however, `audit.json` is
  `INCONCLUSIVE` because `receipt_audit.passed=false`.
- Defect: the consumer wrote the runtime-record receipt-log field as a string/path rather than the
  required structured `{path, sha256, count}` object, yielding `runtime record receipt log summary
  differs from Agent receipt log` despite eight receipts with SHA-256
  `5871d577a0f37c92f692533a470fffd9a64c1eb20eed814185a41c912c9e32fe`.
- Required repair and later status: write the structured receipt-log mirror and relaunch a fresh
  consumer. This defect was fixed and independently verified by the Round 7 Cycle12 consumer
  evidence; these historical records are retained without modification.
