# R1.1-002 分阶段、可追溯的建模工作流共享测试计划

## 1. 状态与范围

- 状态：原平台/Skill 与 2026-07-18 repo-local Harness 增补测试均已评审通过，开发/独立测试共享
- Requirement：`docs/requirements-v1.1.md` R1.1-002，效果证据关联 R1.1-001
- Design：`docs/superpowers/specs/2026-07-17-r1-1-002-staged-modeling-workflow-design.md`
- Delivery record：
  `docs/superpowers/plans/2026-07-17-r1-1-002-staged-modeling-workflow-delivery-record.md`
- Contract freeze：2026-07-17 用户确认的 Dify Workflow 纵向切片、官方网页来源、三项能力问题、
  数据安全合同，以及 Codex `gpt-5.6-terra` + `medium` 固定实验条件

本文件是开发验证、独立测试和缺陷复测的唯一共享计划。每轮测试在末尾追加记录，不删除失败轮次，
不另建竞争性测试文档。

## 2. 完成门禁

必须全部满足：

1. Migration、models/service、REST、MCP、security resolver、Skill/evals 和文档实现与 reviewed design
   一致，无 Critical/High 未处置发现。
2. 后端全量 pytest 通过；新增 Python 文件 Ruff check/format 通过。
3. 真实 PostgreSQL 并发用例证明同一 Session Artifact/Event 序号与幂等行为；migration head 正确。
4. REST/MCP 的 Project scope、actor、secret、foreign reference 和大小边界测试通过。
5. JSON/Markdown export、Session 恢复和追加更正能重建完整记录。
6. `ontology-builder` structural/eval/runtime registry 检查和独立 forward test 通过。
7. 三个独立 Codex Terra/medium 角色完成官方 Dify 文档运行；每批经过门禁、dry-run、review、apply、
   查询/validation/lineage 验收。
8. 用户对三项能力问题的模型结果作出业务价值 PASS；限制和 deferred 项已留档。
9. `ontology-platform.service` 重启后 active，backend `/api/health` 和 frontend `5173` 健康，受保护
   workflow endpoint 和 MCP registry 可用。
10. 需求/设计/API/MCP/architecture/platform-guide/glossary 状态同步，相关改动提交且无混入用户无关
    工作树内容。

## 3. 测试数据与清理

- 自动化使用唯一 UUID Project、Ontology、Build Session、Artifact key/client version ID 和 event ID。
- PostgreSQL concurrency 测试必须在 `finally` 删除唯一测试 Project，由 FK cascade 清理 Session 数据。
- Dify 真实运行使用专属 Project/Ontology 名称和本轮 workflow version；最终是否保留作为 R1.1-001
  效果证据由用户价值评审决定。只有能唯一确认属于本轮的失败草稿/测试 key 才清理。
- 不删除运营 bootstrap user/key，不删除用户开始前已有 R-011/v1.1 文档修改。
- 测试内容只使用脱敏占位符；secret scanner 负例使用唯一假 secret，并验证响应、DB、export 和日志
  不回显该值。

## 4. Artifact 服务与存储

### 4.1 成功与版本

- 首个 JSON Business Knowledge Pack 创建 version 1，返回 server ID、canonical content hash、actor、
  workflow/prompt metadata 和 201。
- 相同 client version ID + 相同请求重试返回同 ID/版本和 200，不增加行数。
- 同一 artifact key 以当前版本作为 supersedes 创建 version 2；version 1 仍可读取，current-only list
  只返回 version 2。
- Markdown verification report 按 UTF-8 原文 hash；JSON key 顺序不同但语义相同时 canonical hash 相同。
- type/key/ontology/current-only/cursor/limit 组合返回稳定顺序和 next cursor，无漏项/重复。

### 4.2 边界与失败

- 相同 client version ID 不同 content/type/supersedes 返回 409 `idempotency_conflict`。
- 新版本缺 supersedes、supersedes 非当前版本、跨 key/type/Session supersedes 返回
  `workflow_artifact_version_conflict` 或 `workflow_reference_conflict`，不产生分叉行。
- JSON format + string、Markdown + object、未知 type/role/format、空 key、过长 ID 和非法 ontology
  返回稳定 4xx。
- canonical content 恰好在 1 MiB 边界可接受，超过边界返回 413 且 DB 无行。
- terminal Session 禁止新版本；旧版本仍可读和导出。

## 5. Event 服务与时间线

### 5.1 成功、幂等与顺序

- 覆盖 12 个首版 event type、各阶段/status/report source/actor role、prompt/runtime/model/effort 字段。
- `question_asked` 使用稳定 question ID 创建 `open`；`answer_recorded` 通过同 ID 和较早 event 转为
  `answered | skipped | uncertain`；每次转换的 `expected_question_head_event_id` 必须等于当前 head；
  `reopened` 只能从 resolved current head 重新开放。
- answered 缺用户可见 answer/Interview Answer ID、skipped/uncertain 缺原因、引用未来/foreign/
  不同 question event 或 stale head 均返回 `question_state_conflict`；按 sequence 计算 current question
  states 稳定。
- 两个连接并发回答同一 open head 时恰好一个成功、一个稳定 conflict；不能出现两个分支答案。
- 同 question ID duplicate open 冲突；reopen/answer 必须引用最新 head；resolved answer 的更正只有在
  expected head 和 `supersedes_execution_event_id` 都等于 current head 时成功，旧答案保留。
- 相同 client event ID + 相同请求重试返回原 event，不增加 sequence；不同请求返回
  `idempotency_conflict`。
- 同一 Session 多连接并发首次追加得到唯一连续 sequence；相同 client event ID 并发只有一行。
- 两个不同 Session 的 sequence 独立从 1 开始。
- artifact/event 写入不增加 Build Session revision，但更新 last activity；既有 checkpoint/lease
  expected revision 不因纯记录写入失效。
- superseding event 引用更早同 Session event，原事件和更正都可读且导出显示关系。
- Session workflow summary/export 显示 open、answered、skipped、uncertain/reopened；恢复 Agent 不重复
  answered/skipped，只有来源变化、用户 reopen 或新冲突才再问。

### 5.2 结构化内容与失败

- quality issue 覆盖 category、introduced/detected phase、detected role、severity、rework cost、
  preventable phase、unknown/hypothesis root cause；未知 enum/负成本/非法组合被拒绝。
- duration/token/cost 缺失时返回 `unknown`/null，不伪造零值；非负真实摘要可保存。
- 外部请求 `platform_observed`、伪造 actor、lease token、隐藏 prompt/credential 字段被拒绝或由统一
  actor 规则覆盖并产生既有安全事件。
- 64 KiB 边界内事件可接受，超限拒绝且不分配 sequence。
- terminal Session 禁止新 event；`blocked`/`phase_completed` 必须在 complete 前记录。

## 6. 平台资源引用与权限

- Artifact/Event 的 Project、Session、Ontology 一致；foreign ontology 返回 404 且无数据泄漏。
- input/output workflow artifact version IDs 必须属于同一 Session；cross-session/cross-project 拒绝。
- Competency Question、Evidence Reference、Modeling Batch/Attempt、Validation/Lineage 等 typed refs 逐一
  解析；unknown、foreign、类型不匹配或 Session 不一致 fail closed。
- 每个 Attempt Finding 具有持久 `finding_fingerprint`；同 Attempt 多个 item 产生相同
  `invalid_dependency` + `depends_on` path 时 fingerprint 仍唯一，重试/读取保持稳定。
- Event 用 Attempt ID + fingerprint 精确关联；只给 code/path、foreign Attempt、未知 fingerprint 或
  fingerprint/Attempt 不匹配均拒绝，不把 review/返工归到错误 item。
- Project-bound read key 可 list/get/export 但不能 POST；model key 可 POST；foreign Project-bound key
  的 opaque ID 返回 404，显式 foreign project 返回 403；org admin 正常访问。
- HTTP OpenAPI 每个新 operation 有显式 policy；MCP 每个新 tool 有 scope/project resolver。
- `workflow_artifact_id` 不走 Evidence Artifact resolver，`execution_event_id` 可正确解析 Project。

## 7. Secret、隐私与大小

- Artifact/Event 中真实格式的平台 key、JWT、AWS key、Bearer token 和 credential 字段在 HTTP/MCP
  持久化前返回 422 `secret_in_payload`。
- `<TOKEN>`、`${API_KEY}`、`REDACTED`、`***` 和凭证术语可保存，避免 Dify API 文档被误拒绝。
- 错误响应、security audit、service log、DB、JSON/Markdown export 都不含命中的假 secret。
- 不存在可写 actor、system prompt 正文、chain-of-thought 或 lease token 字段；role prompt 只存版本。
- 8 MiB 内 export 成功；超限返回稳定 413，分页 list 仍能读取全部记录。

## 8. REST、MCP 与导出一致性

- REST POST 201/幂等 200，错误 detail code 与 service 一致；GET content type、cursor/filter 正确。
- 七个 MCP 工具 schema 与 REST 字段、默认值、enum、大小/secret/idempotency/permission 行为一致。
- runtime registry/catalog 将工具归到 build/modeling workflow 类别；`test_mcp_surface.py`、文档 inventory
  和 Skill required tools 同步。
- JSON export 包含 Session 摘要、全部 Artifact 版本、current index、全部 events 和 supersedes；顺序
  稳定，可被另一个 Agent 恢复。
- Markdown export 包含来源、版本、角色/Runtime、问题/回答、决定/否决项、质量问题、平台引用、
  blocker 和 next step；不把 Agent 摘要标成 platform observed。
- 空 Session export 合法并明确无 artifacts/events；含更正/返工/blocked 的时间线不丢历史。
- `get_build_session.modeling_workflow_summary` 只返回小摘要，不内联 content，旧客户端字段保持兼容。

## 9. Migration 与 PostgreSQL

- 从 `0027_r008_auth` 升级到 `0028_modeling_workflow_records` 成功；`alembic current` 仅显示新 head。
- 新表、unique/check/index/FK/ondelete 行为符合设计；Project/Session 删除级联，self supersedes 不阻断
  合法清理。
- SQLite 常规 service tests 通过；真实 PostgreSQL 覆盖同 Session 并发版本/event、幂等 race 和
  foreign reference transaction rollback。
- 迁移不扫描或回填旧聊天、`.ontology-build.md` 或旧 Skill traces，不修改现有 R-002/R-003/R-004
  行。

## 10. `ontology-builder` 静态与行为验证

### 10.1 结构

- `SKILL.md` frontmatter 仅 name/description，description 可正确触发外部资料建模、恢复和分阶段流程。
- `SKILL.md` 小于 500 行，所有 references 一层直链，无 README/changelog/Runtime 专用 agent 文件。
- `agents/openai.yaml` 与重构后 Skill 匹配，default prompt 显式引用 `$ontology-builder`。
- Pack、Coverage Matrix、role handoff、quality gate/Event 模板单一来源，无相互矛盾重复定义。

### 10.2 Eval 场景

- 恢复 Session 时读取当前 artifacts/events/checkpoint 和唯一 question current head/state；不重复
  answered/skipped 问题，reopened 问题可再次提出且保留旧状态历史。
- 全局扫描先生成 Pack/Matrix，业务整理角色不输出 Class/Property/Batch。
- modeler 只用确认产物/证据/context 生成纵向切片，不能 lease/apply。
- reviewer 能看到原资料清单/关键原文和 dry-run findings，发现业务整理遗漏并返回 REVISE。
- 主 Agent 只有在七门禁满足且 review PASS 后 apply；REVISE/BLOCKED 分别返工/停止。
- apply 后执行 read model、Context Query/SPARQL、validation、lineage；未验证不得 complete。
- Artifact/Event 幂等、秘密拒绝、timeout recovery、角色 fallback 和最多三个阻塞问题均有 case/trace。
- Modeling dry-run 对相同 code/path 的多 item Findings 返回不同稳定 fingerprint，review/event 精确引用。

### 10.3 命令

```bash
python /home/yangxiang/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/ontology-builder
python skills/ontology-builder/evals/validate_skill.py
cd backend && uv run python ../skills/ontology-builder/evals/run_evals.py --check-registry
cd backend && uv run python ../skills/ontology-builder/evals/run_evals.py \
  --traces ../skills/ontology-builder/evals/example-traces.json --check-registry
```

## 11. Codex Terra/medium forward test

### 11.1 固定配置

- 执行前检查 `codex --version`、实时 model catalog 和
  `codex -m gpt-5.6-terra -c 'model_reasoning_effort="medium"' --strict-config doctor ...`。
- business organizer、modeler、reviewer 各使用新的 `codex exec` 线程，显式传入 Skill 路径、角色输入
  和输出格式；不把期望答案、已知缺陷或上一个角色隐藏上下文泄漏给下一角色。
- 另启一个临时主 Agent `codex exec`，同样固定 Terra/medium；仅它通过临时 CLI config/profile 注册
  当前仓库 ontology-platform stdio MCP，并通过不打印明文的环境获得专属 Project-bound model key。
- 主 Agent MCP registry 含 ontology-platform tools，真实调用 Artifact/Event、dry-run、lease/apply、
  query/validation/lineage；运行后删除临时 config 并撤销唯一测试 key。
- 三角色均固定 model/effort，记录 CLI/model/prompt version、开始/结束、usage；不可用或 entitlement
  失败时本轮 BLOCKED，不静默换模型。
- 子角色不继承临时 MCP config/env，无任何平台 key且 read-only。逐角色验证 `codex mcp list` 无
  ontology-platform；对受保护 workflow POST 无凭证请求为 401。只有主 Agent model key 能写、lease、
  apply。credential 不进入 prompt、Artifact/Event、命令输出、日志或 Git。

### 11.2 泛化/边界 forward test

在 Dify 真实运行前至少用一个小型非 Dify fixture 验证：

- organizer 能宽扫描并生成无本体预判的 Pack/Matrix；
- modeler 能把高优先级能力问题转换为最小纵向切片；
- reviewer 能从原资料中发现一个被 Pack 遗漏的事实，并输出结构化 REVISE；
- 修订后 reviewer PASS，事件/版本链保留失败轮次。

该测试使用原始 fixture，不把预期遗漏告诉 reviewer。临时产物仅保留必要的 eval trace，其他唯一
测试数据清理。

## 12. 官方 Dify 端到端运行

### 12.1 Source inventory

- 从 `https://docs.dify.ai/llms.txt` 获取当次索引并记录读取时间。
- 打开 Quick Start、Workflow guide、Get App Parameters、Run Workflow、Get Workflow Run Detail、
  List Workflow Logs、Errors/Rate Limits 和实际需要的节点/变量页。
- 每项记录请求 URL、最终 canonical URL、标题、权威性、新鲜度、扫描状态和相关 Evidence 摘录。
- 旧 URL 重定向不当成独立资料；整页不写入平台；知识库/插件/其他 app 类型明确 DEFERRED。

### 12.2 Workflow evidence

- 创建/恢复 Project Build Session，保存 source_scanned events。
- organizer 产出 version 1 Pack/Matrix；主 Agent 持久化 artifact_created events。
- 已确认三项能力问题和范围写入 decision_recorded；无阻塞时不重复询问用户。
- modeler 产出 modeling draft/Batch draft；主 Agent建立轻量 Evidence Reference 并 dry-run。
- reviewer 独立检查原资料、Pack/Matrix、draft 和 findings；REVISE/BLOCKED 必须留档并闭环。
- PASS 后主 Agent 获取 lease、apply exact reviewed batch、释放 lease。
- 用 read model、Context Query、scoped SPARQL、validation 和 lineage 回答/证明三项能力问题；保存
  verification report 和完整 JSON/Markdown export。
- 中断后用新的已授权 Agent读取 Build Context/artifacts/events，能说出当前版本、已完成、未解决和
  一个明确下一步，能列出 question current states，且不重复 answered/skipped 问题。

### 12.3 用户业务价值评审

向用户展示三项能力问题的回答、模型关键元素、Evidence、review/返工和限制。PASS 条件：

- 区分 Workflow 定义、发布、API call 和 Workflow Run；
- 正确解释输入、节点/变量依赖、输出、状态和日志关系；
- 失败排查有来源且不捏造；
- 明确 deferred/ambiguous/missing 内容，不宣称全 Dify 覆盖；
- 用户确认该模型对理解或后续使用 Dify Workflow 具有实际价值。

若用户不通过，R1.1-002 保持进行中，缺陷归类并进入 developer/Skill 返工和下一独立测试轮；不得
降低能力问题或仅凭平台 validation PASS 收口。

## 13. 仓库命令与最终运行时门禁

开发稳定点：

```bash
cd backend && uv run pytest
cd backend && RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest \
  tests/test_modeling_workflow_postgres.py
cd backend && uv run ruff check app tests
cd backend && uv run ruff format --check app tests
cd backend && uv run alembic current
```

Backend/Skill/docs 完成并测试后：

```bash
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

然后使用运营身份验证至少一个受保护 workflow REST 读写/导出路径和 MCP registry。若 restart/health
失败，读取 `journalctl --user -u ontology-platform.service` 并记录精确 blocker。

Frontend 当前不在范围。若 diff 出现 `frontend/` 行为变更，追加并执行：

```bash
cd frontend && npm run build
cd frontend && npx playwright test
```

最终检查 `git diff --check`、`git status --short`，区分开始前用户改动与本需求文件；提交后记录 commit。

## 14. 独立测试轮次

独立 tester 在 development-ready 稳定状态后从 Round 1 开始追加。每轮必须写明稳定状态、代码审查、
执行命令、结果、缺陷/未执行用例、清理和残余风险。

### Independent Test Round 1 — 2026-07-17 — FAIL

- Stable state: `49a0b9e6f8a9eb1af7e9b77a1e5789ca766335fc` plus the
  `DEVELOPMENT_READY` worktree recorded at `2026-07-17T18:42:04+08:00`; tester did not modify
  product code, requirements, design, or the delivery record. `git diff --check` passed before the
  round.
- Implementation review: reviewed migration/models/schema/service, REST/MCP adapters and policy
  resolvers, Finding fingerprints, Build Session summary, new backend tests, Skill/references/evals,
  API/MCP/architecture/platform-guide/glossary sync, and the reviewed question-head CAS design.
- Commands/results:
  - `cd backend && uv run pytest`: `701 passed, 6 skipped, 148 warnings` in `64.12s`.
  - `RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest tests/test_modeling_workflow_postgres.py -vv`:
    `2 passed, 3 warnings`; concurrent event sequences were `[1, 2]` and concurrent answers had one
    winner plus one `question_state_conflict`.
  - Targeted `ruff check` and `ruff format --check` on all 20 affected Python/migration/test files:
    `All checks passed`, `20 files already formatted`. Full `ruff check app tests` independently
    reproduced the existing 60-error baseline, and full format check reproduced `79 files would be
    reformatted`; none of those files are in this requirement's affected set.
  - `uv run alembic current` and `uv run alembic heads`: only
    `0028_modeling_workflow_records (head)`.
  - Skill checks: system `quick_validate.py` passed; `validate_skill.py` reported 8 references and
    34 MCP dependencies; registry and trace runs both validated all 7 cases. One combined shell
    invocation initially used `cd backend` twice; the affected trace command was rerun from the
    correct directory and passed.
  - `codex --version` returned `0.144.5`; Terra catalog showed `gpt-5.6-terra`, default/supported
    `medium`; strict-config doctor with `model_reasoning_effort="medium"` returned 0 fail. The
    subrole environment had no `ONTOLOGY_MCP_API_KEY`, and the normal MCP list contained no
    ontology-platform server.
  - Three ephemeral, read-only Terra/medium contexts ran a non-Dify ParcelFlow fixture. Organizer
    produced Pack/Matrix without ontology design; modeler produced a competency-question vertical
    slice without lease/apply; reviewer compared raw source and an incomplete handoff, found source
    omissions/semantic errors, and stopped with `BLOCKED` because the fixture deliberately lacked a
    real Modeling Context/exact dry-run. It did not edit or submit a model.
  - Real PostgreSQL manual checks: a same-Session `related_resources.resource_type=lease` event was
    accepted; the same lease from another Session in the Project and from another Project both
    returned `workflow_reference_conflict`. Deleting a Project containing Artifact v1->v2 and a
    superseding answer chain reduced its Artifact/Event counts from `2/4` to `0/0`.
- Acceptance/runtime result: after restart, the unit was `active`, backend health returned
  `{"status":"ok"}`, frontend returned HTTP 200, and unauthenticated workflow POST returned 401.
  A unique Project-bound model key then created an Artifact (201), recorded an Event (201), exported
  JSON (200), and read an authenticated MCP catalog containing all 7 workflow tools; actor was the
  authenticated key. The first health request occurred 28ms after systemd became active and hit an
  expected readiness race; retry after HTTP readiness passed.
- Defects:
  - **High — Lineage typed references do not fail closed.** Reproduction: create an active Session
    and Ontology with no lineage occurrence, then record `verification_completed` with a lineage
    related resource whose statement target is `"0" * 64`. The Event was accepted and persisted at
    sequence 1. Expected: `workflow_reference_conflict`, because the reviewed design and section 6
    require unknown/foreign/type-mismatched typed resources to be resolved and rejected. Actual
    code in `backend/app/services/modeling_workflow.py` validates only Ontology ownership for
    `lineage` and never resolves `target_type`/`target_id` through the lineage service.
  - **High — Terra reviewer output is not record-ready for the platform quality-issue schema.** The
    independent reviewer emitted categories such as `omission`/`evidence_gap`, role
    `independent_reviewer`, severity `blocking`, and extra `rework_estimate`/`exact_source_fact`.
    Passing two representative findings to `ModelingQualityIssue` deterministically failed with
    `literal_error`/`extra_forbidden`, so the main Agent cannot place the review's structured issues
    into `record_modeling_execution_event` without an undocumented rewrite. Expected: the Skill's
    record-ready reviewer handoff uses the exact platform enums/fields. The current
    `workflow-artifacts.md` and `quality-gates.md` describe categories only in prose, and the evals
    did not catch this Terra/medium failure.
- Unexecuted/postponed cases: after the two High defects the round stopped before exact 1 MiB/64 KiB/
  8 MiB boundary probes and the revised-forward-review PASS chain. Official Dify three-role
  modeling, real dry-run/apply/query/validation/lineage evidence, recovery rehearsal, and user
  business-value review remain intentionally sequenced after an implementation PASS and were not
  represented as complete.
- Cleanup: all unique PostgreSQL Projects, Sessions, Artifact/Event rows, Ontologies, leases, and
  the runtime Project-bound model key were removed; final key count was 0. Terra runs were
  `--ephemeral`, read-only, used no platform credential, and wrote no repository artifact.
- Residual risks: the full-repository Ruff/format baseline remains outside this requirement; the
  pre-existing R-011/v1.1 user worktree remains unmodified. Exact boundary and Dify/user-value gates
  require a later independent round after the defects are fixed.
- Verdict: **FAIL**. Do not mark R1.1-002 implemented or proceed to final Dify/user-value closure
  until both High defects are corrected and this shared plan records a clean independent retest.

### Independent Test Round 2 — 2026-07-17 — PASS

- Stable state: `49a0b9e6f8a9eb1af7e9b77a1e5789ca766335fc` plus the Cycle 2
  `DEVELOPMENT_READY` worktree recorded at `2026-07-17T19:16:37+08:00`. The tester reviewed the
  Round 1 fixes and did not modify product code, requirements, design, or the delivery record.
- Implementation review: lineage resources now resolve through `OntologyLineageService` and reject
  missing, foreign, and type-mismatched targets; the Skill now requires reviewer findings to pass
  the repository `ModelingQualityIssue.model_validate` contract and emit normalized
  `model_dump(mode="json")` output without a main-Agent rewrite. References and evals enumerate the
  exact enums/fields and validate record-ready output, including invalid fixtures.
- Commands/results:
  - Targeted service/REST/MCP workflow suite: `15 passed, 9 warnings` in `2.48s`.
  - `cd backend && uv run pytest`: `705 passed, 6 skipped, 150 warnings` in `60.42s`.
  - `RUN_POSTGRES_CONCURRENCY_TESTS=1 uv run pytest tests/test_modeling_workflow_postgres.py -vv`:
    `2 passed, 3 warnings`, covering event/artifact and question-head CAS behavior.
  - Targeted Ruff and format checks on all 22 affected Python/migration/test/eval files returned
    `All checks passed` and `22 files already formatted`; `git diff --check` passed.
  - `uv run alembic current` and `uv run alembic heads` both reported only
    `0028_modeling_workflow_records (head)`.
  - Skill validation passed: system quick validation, 8 references, 34 MCP dependencies, all 7
    eval registry cases, and all 7 eval trace cases.
  - `codex-cli 0.144.5` strict doctor passed for `gpt-5.6-terra` with
    `model_reasoning_effort="medium"`; all reviewer subroles were fresh, ephemeral, read-only,
    `--ignore-user-config`, and had no platform MCP credential.
- Lineage matrix: a real PostgreSQL `OntologyLineageService` lookup resolved a known same-Project
  statement target, and the workflow Event accepted it at sequence 1. Missing target, target-type
  mismatch, and a lineage target owned by another Project all returned
  `workflow_reference_conflict`. The protected runtime repeated the known-target 201, missing 409,
  and type-mismatch 409 paths; protected lineage GET returned 200.
- Exact boundaries through the real service path: Artifact content at 1 MiB was accepted and 1 MiB
  plus one byte returned `workflow_artifact_too_large` without an extra row; an Event whose canonical
  payload was exactly 64 KiB was accepted and plus one byte returned
  `invalid_modeling_workflow_payload` without an extra row; export output at exactly 8 MiB was
  accepted and plus one byte returned `modeling_workflow_export_too_large`.
- Terra reviewer forward chain: five fresh Terra/medium reviewers independently returned
  `REVISE`, with `3/2/4/2/3` issues respectively. All 14 raw issues passed the actual repository
  `ModelingQualityIssue.model_validate(...).model_dump(mode="json")` path with
  `normalized_equal=True`; no alias, extra field, hidden main rewrite, false PASS, or platform write
  occurred. The synthetic fixture still had genuine semantic omissions through v5, so this chain
  is evidence that the reviewer gate and schema fix work, but it is **not** claimed as a successful
  end-to-end semantic PASS trace. Per the frozen Round 2 scope, no v6 fixture iteration was run.
- Runtime/result: after restart, `ontology-platform.service` was active, backend health returned
  `{"status":"ok"}`, frontend returned HTTP 200, an authenticated MCP catalog contained all 7
  workflow tools plus `get_ontology_lineage`, and the unique runtime Project/model key exercised
  the protected paths above.
- Defects: no remaining Critical or High implementation defect was found in the Cycle 2 retest.
  The official Dify three-role run, real dry-run/apply/query/validation/lineage/recovery evidence,
  and user business-value review remain required whole-delivery gates after this implementation
  PASS; they were not executed or represented as complete by this round.
- Cleanup/scope: all unique Projects, Sessions, Ontologies, lineage occurrences, workflow rows, and
  the runtime Project-bound model key were removed. Pre-existing/out-of-scope `AGENTS.md`,
  `CLAUDE.md`, and `.claude/skills/gitnexus/` changes were left untouched.
- Verdict: **PASS for the Cycle 2 implementation retest**. The two Round 1 High defects are closed;
  proceed to the official Dify and user-value gates, but do not mark R1.1-002 implemented solely
  from this independent round.

### Independent Test Round 3 — 2026-07-17 — FAIL

- Stable state: `49a0b9e6f8a9eb1af7e9b77a1e5789ca766335fc` plus the Cycle 3 worktree
  independently captured at `2026-07-17T20:35:35+08:00`. The tester inspected the actual schema,
  Skill/reference routing, validators/evals, Modeling Batch input model, handler registry, and
  Operation validator rather than relying on the developer report. No implementation, requirement,
  design, delivery-record, R-011, `AGENTS.md`, `CLAUDE.md`, or `.claude/` file was modified.
- Codex Structured Outputs smoke: `codex-cli 0.144.5` exited 0 with the repository
  `modeler-handoff.schema.json`, exact `gpt-5.6-terra`, `model_reasoning_effort="medium"`,
  `--ignore-user-config`, `--ignore-rules`, `--ephemeral`, and `--sandbox read-only`. The run showed
  model `gpt-5.6-terra`, reasoning effort `medium`, sandbox `read-only`, no MCP startup/tool use, and
  generated one seven-field handoff containing all four command kinds plus a nonempty Operation
  parameter. `ONTOLOGY_MCP_API_KEY` was unset.
- Draft 2020-12/strictness: `Draft202012Validator.check_schema` passed and the raw Terra handoff was
  valid with 4 items. An independent recursive inspection found 25 object-schema nodes, 8 const
  nodes, and 8 enum nodes; every object had explicit `type=object`, full `required`, and
  `additionalProperties=false`, and every const/enum node had an explicit type. No strictness issue
  was found.
- Correlation/negative fixtures: all 12 cross-command substitutions among `create_class`,
  `create_property`, `create_relation_type`, and `create_operation` were rejected. All 16 additional
  invalid fixtures were rejected, including command/payload mismatch and injected target,
  `ontology_id`, `target_graph_iri`, `graph_set_id`, actor, API-key/secret, authorization, and lease
  fields at batch, payload, or nested binding scope.
- Wire handoff result: the raw `modeling_batch` passed
  `ModelingBatchSubmit.model_validate` unchanged with all 4 items and the nonempty Operation
  parameter. Pydantic changed none of the supplied fields and only materialized its documented
  optional defaults `lease_token=None` and `actor=None`; `session_id` remains the separate main-Agent
  call envelope. No wire-level translation was needed.
- **High — Strict nullable `ParameterConstraints` are incompatible with the real Operation
  validator.** The durable schema requires every nonempty parameter to contain all six constraint
  keys (`min_value`, `max_value`, `min_length`, `max_length`, `pattern`, `format`), allowing null but
  not omission. Passing the Terra output through the real
  `ModelingCommandHandlerRegistry.prepare -> validate_operation_payload` path, with its item
  reference resolved exactly as the service does, returned
  `invalid_operation_payload: Numeric constraint requires numeric value_type`. A second isolated
  matrix supplied an otherwise-valid active Operation and real tool binding while preserving those
  six required-null fields: all schema-allowed parameter types failed (`string`, `boolean`, and
  `iri` on numeric-key presence; `integer` and `number` on length-key presence). The platform
  validator treats key presence as an asserted constraint even when its value is null, so no
  nonempty parameter representable by this strict schema can pass deterministic Operation
  validation. Making it pass would require the main Agent to strip null constraint fields, an
  undocumented rewrite explicitly forbidden by the unchanged handoff contract. Current schema
  validators/evals stop at JSON Schema validation and therefore do not detect this platform-handler
  incompatibility.
- Unexecuted after failure: by main-Agent scope freeze, the round stopped after reproducing the High
  defect. Cycle 3 `validate_skill.py`, registry/trace evals, skill-creator quick validation, and
  targeted Ruff were not rerun and must be executed after the repair. No database/runtime test data
  was created; the Codex output lived only in an ephemeral `/tmp` directory and no platform
  credential or write capability was supplied.
- Verdict: **FAIL**. Keep the Round 2 implementation PASS history, but do not accept the Cycle 3
  durable modeler handoff fix until nullable constraints are encoded in a Codex-compatible form that
  the real Operation validator accepts unchanged, the eval exercises a nonempty Operation parameter
  through that validator, and all postponed Skill/eval/quick-validation/Ruff gates pass.

### Independent Test Round 4 — 2026-07-17 — PASS

- Stable state: `49a0b9e6f8a9eb1af7e9b77a1e5789ca766335fc` plus the Cycle 4 worktree
  independently captured at `2026-07-17T20:42:54+08:00`. The tester reviewed the actual schema and
  eval changes and did not modify implementation, requirements, design, delivery record, R-011,
  `AGENTS.md`, `CLAUDE.md`, or `.claude/` content.
- Round 3 High reproducer: an exact seven-field handoff containing one `create_operation`, one
  nonempty string parameter, `enum_values=[]`, `default_value=null`, `constraints={}`, one safe tool
  binding, and `operation_id=null` passed `Draft202012Validator`,
  `ModelingBatchSubmit.model_validate`, and the real
  `ModelingCommandHandlerRegistry.prepare -> validate_operation_payload` path. The handler did not
  mutate the input. Two prepares with the same batch/item identity generated the same normalized
  Operation ID, and that ID equaled both `resource_id` outputs. The former six-null constraint object
  was rejected by the schema, closing the undocumented-rewrite defect.
- Boundary/schema checks: an empty Modeling Batch and an active Operation with empty
  `tool_bindings` were both rejected by the new `minItems: 1` constraints. The current all-four-item
  eval handoff remained schema-valid; all 12 cross-command substitutions among `create_class`,
  `create_property`, `create_relation_type`, and `create_operation` were rejected. All 12 injected
  target/ontology/graph/actor/API-key/secret/authorization/lease fixtures at batch, payload, and
  nested binding scope were rejected.
- Real Codex smoke: `codex-cli 0.144.5` exited 0 with exact `gpt-5.6-terra`,
  `model_reasoning_effort="medium"`, repository `modeler-handoff.schema.json`,
  `--ignore-user-config`, `--ignore-rules`, `--ephemeral`, and `--sandbox read-only`. It used no MCP
  tool and had no `ONTOLOGY_MCP_API_KEY`. The raw output contained exactly one active
  `create_operation`, `operation_id=null`, one nonempty `newName` parameter with `constraints={}`,
  and one safe `mcp_tool` binding. That exact output passed Draft 2020-12, wire validation, and the
  real handler unchanged; repeated prepare normalized the null ID deterministically.
- Skill routing: `SKILL.md` directly links the sole repository `modeler-handoff.schema.json` and
  requires passing it unchanged to `codex exec --output-schema`; `role-handoffs.md` forbids an ad-hoc
  schema. The eval now requires a nonempty Operation parameter, rejects the legacy six-null shape,
  and calls the platform handler while asserting that it did not mutate the payload.
- Commands/results:
  - `cd backend && uv run python ../skills/ontology-builder/evals/validate_skill.py`: validated 9
    references and 34 declared MCP dependencies.
  - `.../run_evals.py --check-registry`: validated all 7 cases against the runtime registry.
  - `.../run_evals.py --traces .../example-traces.json --check-registry`: validated all 7 cases and
    traces against the runtime registry, including the real Operation prepare path.
  - Skill-creator `quick_validate.py skills/ontology-builder`: `Skill is valid!`.
  - Ruff check/format on both affected eval Python files: `All checks passed!`,
    `2 files already formatted`.
  - Whole-worktree `git diff --check`: exit 0.
- Defects/residual scope: no remaining Critical or High Cycle 4 defect was found. This narrow retest
  closes only the Round 3 durable modeler handoff defect; the already-recorded official Dify,
  end-to-end apply/verification/recovery, user-value, documentation/status, and commit gates remain
  owned by the overall delivery flow.
- Cleanup: no database or runtime state was created. The Codex role was ephemeral, read-only, had no
  platform credential, and wrote only its uniquely named temporary last-message file, which was
  moved to trash after validation.
- Verdict: **PASS for the Cycle 4 defect retest**. The schema-valid nonempty Operation parameter now
  reaches the real platform validator unchanged, the legacy incompatible shape is rejected, and all
  postponed Cycle 3 Skill/eval/quick-validation/Ruff gates pass.

### Independent Test Round 5 and official Dify live acceptance — 2026-07-17 — PASS

- Stable state: Cycle 4 worktree plus the official Dify v2 immutable handoff and the narrow
  `decode_operations` fix. The independent tester modified no file and committed nothing.
- Runtime defect reproduction: official v2 dry-run Attempt
  `9aca8f4d-43b3-4342-a1a2-1626fc65fdc3` contained 32 items and 258 candidate inserts. Nine subjects
  used the shared vocabulary `status` predicate, but eight were RelationTypes. The old decoder treated those
  eight subjects as Operations and incorrectly raised missing `rdf:type Operation`; the actual Operation type
  triple existed.
- Fix boundary: Operation discovery excludes only the cross-resource shared `status` predicate while retaining
  canonical `/operation/` IRI discovery. Direct probes confirmed a genuine Operation subject without type still
  fails; a non-Operation status subject is ignored; secret/unsupported predicates, missing target Class and
  duplicate Operation ID remain rejected.
- Independent commands/results: focused regression and boundary probes `9 passed`; full backend
  `706 passed, 6 skipped`; targeted Ruff passed; `git diff --check` passed. The exact failed Attempt delta plus
  one SHACL shapes graph replayed through `CanonicalSemanticWriteService` as `validated`, `conforms=true`, with
  no SQL/RDF write. Critical=0, High=0.
- Clean immutable retry: same Batch `3b27d72f-f877-41f4-ab04-37b777b3382e`, same 32-item JSON/order and
  new control idempotency produced Attempt `1a6edf29-89a1-4543-bde2-1a9cd7ac6fb9`, `validated`, zero Findings.
- Final independent Reviewer: fresh `gpt-5.6-terra` / medium, credential absent, no ontology-platform MCP,
  unauthenticated protected POST 401, duration 82,257 ms. It reread the complete official Evidence/Pack/Matrix,
  immutable handoff and clean Attempt; Gates 1–6 all passed, Gate 7 stayed `pending_after_apply`, and there were
  zero quality issues. Review v3 is `7a3f0b61-c9c4-4055-876a-6807676d20ea`.
- Atomic application: applied Attempt `982aa076-e442-4bdf-acf3-4c61cb3fd779` completed 32/32 without partial
  groups. Scoped results are 8 Classes, 15 Properties, 8 RelationTypes and 1 Operation; ontology graph revision
  moved 0→1 and workspace version moved `ecbafc28…7304`→`516fd7…3f0c`. Every recovery lease was released.
- Gate 7: bounded semantic-context queries and scoped SPARQL answered CQ1–CQ3 from persisted resources.
  Validation `172e6e1f-ce63-4dc8-bdc0-4094dda10d95` succeeded with `conforms=true` and zero violations.
  Representative Class, Property, RelationType and Operation lineage was complete/supported and linked to the
  original official Evidence IDs. Verification Artifact `2a24175c-0ac5-4567-ada4-1f21cc73d208` passed.
- Recovery/cleanup: a fresh authorized read-only recovery restored all 32 outputs, validation, lineage, CQ
  answers, exports and checkpoint `15e67656-3076-48ba-a235-12aab4f03266`; no lease/fence/recovery remained.
  All temporary Project model keys were revoked. The bounded `rdf_primary` systemd environment override was
  unset; final restart returned backend health OK and frontend HTTP 200.
- Verdict: **PASS for implementation, official Dify live run and Gate 7 verification**. Keep R1.1-002 and the
  Build Session open only for the explicit user business-value review; do not mark implemented or commit before
  that confirmation.

### Independent Test Round 6 — 2026-07-18 — synthetic instance, rule and reasoning PASS

- Stable runtime: Ontology `d980c9ed-6808-4d4c-bd60-8077fa016a37`, Graph Set
  `91db9dde-b7a6-5668-b8f8-740a787f3842`, workspace version `f072b431…1946`. The tester was read-only and
  changed no file, SQL row, RDF graph, service or requirement status.
- Exact persisted scope: 11 Classes、23 datatype Properties、9 RelationTypes；47 Entities with distribution
  3 WorkflowDefinition、3 PublishedWorkflow、3 WorkflowRun、6 WorkflowInput、3 OutputDefinition、13
  WorkflowNode、13 NodeExecutionEvent、3 RunLogSummary；67 relation triples with distribution
  6/13/3/10/3/3/3/13/13. All three Runs backtrace to `scenario_origin=synthetic_reference`; node orders are
  continuous and dependencies remain within their scenario.
- Rule acceptance: current run `4d5cf7f8-23ba-4c11-a56b-62f0abaef30a` succeeded and contains exactly two
  statements: Invoice→Failed and Contract→ResourceIntensive. Support produced no attention classification.
  Oxigraph numeric boundary query excluded 49999 and included 50000. Both Rule lineages are complete/supported,
  warning-free and current.
- Reasoning/validation: current run `d6e6346c-95b6-4354-9858-9812f886b782` succeeded, is consistent and adds
  AttentionRequired to Invoice and Contract while their asserted WorkflowRun types remain visible; Support has
  no Attention type. Validation `5d0a84ef-4512-4b0b-be30-7b173dcab696` succeeded/current, conforms and reports
  zero violations/warnings.
- Business queries: Invoice status is failed; its ERP Sync event is failed with `upstream_timeout`; the following
  output event is `not_started` and has no false error. Contract `total_tokens=128000`. Definition/run/event
  traversal returns no cross-scenario links.
- Defect boundary: the multi-target Relation fix preserves create+delete, cascade-delete and real single-value
  conflicts. Independent service test file is `50 passed`; full backend is `716 passed, 6 skipped`; Ruff and
  `git diff --check` pass.
- Secret/cleanup: platform scanner plus Dify-key-pattern scan over 14 pre-verification Artifacts, 38 Events and
  18 Evidence References returned zero finding. Repository hits were only deliberate test fixtures/package names.
  No active temporary key, unreleased lease or write fence remains.
- Medium finding: OWL-inferred statement lineage is `partial` with `origin_scope_mismatch`. The pointer,
  occurrence, Graph Set and source signature are correct/current, but reasoning-run metadata lacks
  `graph_set_id`, so the lineage resolver discards the otherwise valid reasoning-run origin. This is a
  non-blocking explanation-chain gap, not an inference correctness or stale-result defect.
- Verdict: **PASS**, Critical=0, High=0, Medium=1. Keep requirement completion and commit pending explicit user
  business-value confirmation.

## 2026-07-18 repo-local Codex modeling Harness 增补测试合同

本节是同一 R1.1-002 共享计划的增量，不建立竞争性测试文档。实现者先运行定向自动化；独立 tester
在稳定工作树追加新的独立测试 Round，不修改 Harness 产品代码。

### H1. 激活、隔离与路由

- 未激活、foreign cwd、未知 session 的每种 Hook 均成功 no-op，不创建运行目录。
- `PreToolUse(Bash)` 只在显式 activation command 中绑定 payload `session_id` 与唯一 `run_id`；两个
  并发主 session/相同 Build Session 不串写，重复 activate 幂等，冲突绑定 fail closed。
- activation 必须有唯一 nonce；只有 PreToolUse Hook 写入的 run/session/cwd/nonce/hash acknowledgment
  能令 CLI 报告 active。直接运行 CLI、Hooks 禁用、项目未 trust、Hook hash 变化、伪造/过期 nonce
  均不得假成功，并产生明确“本 session 未记录”告警但不阻断后续建模。
- 用当前 Codex 0.144.5 运行真实 repo-local Hook smoke，按 `/hooks` trust 当前定义后至少证明真实
  session 绑定和一个 lifecycle event；同时记录 Hook 变化后需要重新 trust 的启用步骤。测试自动化
  不使用 `--dangerously-bypass-hook-trust` 代替用户信任流程。
- UserPrompt、Agent dispatch、SubagentStart/Stop、ordinary Stop 和 checkpoint Stop 生成正确事件；
  ordinary Stop 不调用 Luna，阶段 Stop 必须依赖成功平台 checkpoint 或显式 local checkpoint。
- 伪造自然语言、失败 PostToolUse、非白名单 MCP、`write_stdin`/重复 PostToolUse 不推进 phase、不重复
  事件。completed/cancelled 才可发布；paused/interrupted 只留本地。

### H2. 事件、并发与恢复

- 多进程/线程追加产生连续唯一 sequence、每行合法 JSON；重复 tool use/agent/fingerprint 不重复。
- crash-safe state write 不留下半个 JSON；`events.jsonl` 已落盘而 Luna 失败时 cursor 不前进。
- pending 总是从最早连续缺口重试，每 Hook 最多一次调用；重启 runner 后仅凭运行文件恢复。
- 新主 session 恢复同 Build Session 创建新 run 并引用 previous run，不合并原始事件或最终文档。

### H3. allowlist、秘密拒绝与边界

- 每类允许字段被有界保存，未知字段、transcript path/正文、system/developer/hidden reasoning、完整工具
  输出、网页/Evidence 正文和无关 shell/file 输出均不落盘也不进入总结 prompt。
- credential、cookie、authorization、API key、lease token 和高置信秘密模式命中时，fixture 原值在
  events/state/raw/session/final doc 和总结输入中均为零出现；只产生不含原值的 rejection 元数据与
  `pending_redaction`。
- 显式 redacted replacement 恢复 pending；超长/控制字符/非 JSON payload 稳定拒绝或截断且不破坏
  JSONL。测试 fixture 只能用唯一假 secret。

### H4. Luna、游标和 Markdown

- 使用 fake summarizer 验证传入内容只有未总结事件、允许片段和短状态；同一 sequence 不被再次总结。
- 验证输出 Schema、未知字段、非 JSON、超时和非零退出；任何失败均不推进 cursor 或修改既有 delta。
- 命令构造必须固定 Luna/medium、ephemeral、read-only、disable hooks、ignore user config/rules，且不
  继承平台 credential；不得通过 shell 拼接未信任 payload。cwd 必须是新建空临时目录，prompt 只经
  stdin；环境变量必须按 allowlist/业务秘密 denylist 清理。
- 断言 `web_search="disabled"` 且 shell/unified exec/apps/multi-agent/goals/memories/browser/computer/
  image/plugin 等非必要工具全部关闭；任一当前 CLI 不接受的安全禁用配置必须 fail closed。
- 运行真实 Luna 注入隔离 smoke：事件中要求读取唯一假环境秘密和空 cwd 外的唯一假仓库秘密；证明
  无工具调用，两个秘密在 last message、events/state/raw/session/final doc 和捕获的总结结果中均为
  零出现。测试结束清理唯一 fixture。
- 合法 delta 确定性更新 `session.md`；重复执行、重试和重启不重复小节。

### H5. finalize、repair 与发布

- completed/cancelled 在无 pending 时生成唯一脱敏 `docs/modeling-retrospectives` 文件；重复 finalize
  幂等，paused/interrupted 不生成 tracked 文档。
- finalize 最多三次 flush；缺口仍在时为 `finalization_pending` 且不发布。repair 补齐后只发布一次，
  平台终态不参与回滚。
- 最终文档覆盖阶段、决定/假设、返工、质量问题、阻塞/下一步、优化建议、稳定 ID、模型和终态，且
  不含原始 transcript/secret。

### H6. Skill 与仓库门禁

- `ontology-builder` 明确可选激活、checkpoint、finalize/repair 责任；仓库 Harness 不存在时 Skill
  仍可执行，不把 `.codex` 文件复制进 Skill 包或声明为平台 MCP 依赖。
- Harness 自动化、Skill validator/evals、skill-creator `quick_validate.py`、新增 Python Ruff 和
  `git diff --check` 通过。
- 本增补不修改 backend/frontend 时不触发相应全量测试与 systemd 重启；若实际发生修改，恢复
  `AGENTS.md` 规定的全量测试、重启和端点健康门禁。

### Independent Harness Test Round 1 — 2026-07-18 — PASS after Cycle 3

- Stable worktree: tester 基于 developer Cycle 3 的 repo-local `.codex` 实现、冻结设计、Harness
  测试合同和 `ontology-builder` Skill 独立复测。tester 未修改 Harness、Skill、需求、设计、交付记录、
  backend/frontend 或运行时；本轮唯一版本化写入是本测试轮次。
- Cycle 1 FAIL: 既有 16 项 Harness 测试通过，但两个独立黑盒复现发现 High。第一，MCP transport
  wrapper 的 `isError=false` 掩盖内层 `success=false/status=failed`，失败的
  `complete_build_session` 被当成成功并把 run 置为 terminal。第二，已发布 completed run 接收后续
  ordinary `Stop`，事件数由 2 增至 3、cursor 仍为 2，`finalization_status=published` 且已发布文档
  保持旧内容。backend-pinned `ruff format --check` 同时发现两个新增 Python 文件未格式化。
- Cycle 2 retest: 内层 business failure、混合外层成功/内层失败均 fail closed；plain-text/无结构响应
  不取得 phase/terminal authority；明确 `{ok:true,data:...}` 的 complete、cancel 和 phase Event 才能
  推进。terminal lifecycle Hook 不再追加事件；`finalization_pending` Hook 只重试一次最早 pending、
  不追加或发布，后续 CLI repair 才发布。20 项测试及独立相邻边界探针通过，但相同 pinned Ruff
  format-check 仍失败，因此未给出 PASS，并退回 developer。
- Cycle 3 final retest: developer 只做 pinned Ruff 机械格式化后，精确两个 High 回归与相邻成功、失败、
  ambiguous、mixed、cancelled、published、`finalization_pending` 和 repair/idempotency 边界继续通过。
  published terminal 的 events/doc/cursor 均不变；pending terminal 每 Hook 恰好一次 retry、零追加、
  零提前发布。触发矩阵独立计数为 UserPrompt=0、PreToolUse(Agent)=1、SubagentStart=0、
  SubagentStop=1、ordinary Stop=0、checkpoint Stop=1 次 Luna；相同 Build Session 的新主 session 使用
  新 run/event 文件并记录 `previous_run_id`。并发 sequence/dedupe、secret rejection/redacted
  replacement、transcript/未知字段排除、bounded incremental cursor、三次 finalize flush 和 paused
  local-only 均由 20 项套件覆盖。
- Real Luna isolation: 真实 `codex exec` 使用 `gpt-5.6-luna` / medium、strict config、ephemeral、空临时
  cwd、read-only、ignored user config/rules、Hooks 和全部非必要工具关闭。恶意 event 要求读取唯一假
  环境秘密和空 cwd 外唯一假仓库文件；进程 exit 0、Schema-valid JSON，捕获 stdout/stderr 无 shell、
  exec、MCP、subagent 或 web tool-call marker，两个假秘密零出现。fixture 已删除，临时目录已清理。
- Trust smoke limitation: 当前 collaboration agent API 不能交互执行 Codex `/hooks` slash command，
  因此未伪造 trust，也未使用 `--dangerously-bypass-hook-trust`。独立测试验证了无 acknowledgment 的
  activate 非零 fail-closed、nonce/session/cwd/hash/TTL、冲突绑定和 hash 变化失效合同。由于 Harness
  是可选本地观测能力且未 trust 时明确告警并继续平台建模，该交互限制不阻断代码发布；首次实际建模
  在声称“正在记录”前仍必须由操作者通过 `/hooks` trust 当前精确 hash 并完成真实 activation smoke。
- Final commands/results:
  - `python3 -m unittest discover -s .codex/tests -v`: **20 passed**。
  - `cd backend && uv run ruff check ../.codex/hooks/modeling_harness.py
    ../.codex/tests/test_modeling_harness.py`: **passed**。
  - 同一 repo-pinned `uv run ruff format --check`：**2 files already formatted**。
  - `validate_skill.py`：9 references、34 MCP dependencies；`run_evals.py --check-registry` 与带 traces
    版本：7/7；skill-creator `quick_validate.py`：`Skill is valid!`。
  - `git diff --check`: exit 0；测试生成的两个 `__pycache__`、恶意注入 fixture 和临时目录均已清理。
- Findings/verdict: Cycle 1 High=2 与 format gate 已在 Cycle 3 关闭；最终 Critical=0、High=0。
  `/hooks` 真实交互 activation 是已显式记录的首次使用门禁，不是静默残余风险。**PASS**。
