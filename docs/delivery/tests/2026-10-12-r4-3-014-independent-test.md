# R4.3-014 独立工程验收

## 范围与边界

权威范围：`docs/requirements/requirements-v4.3.md` R4.3-014，基础恢复合同为
`docs/requirements/requirements-v3.0.md` R3.0-015。复用主代理提供的验收范围；
独立测试者未参与产品实现，仅拥有本文档及 gitignored `independent-*` 探针和日志。

非目标：外部模型、真实生产 run 创建/恢复、live 平台写入、业务语义等价自动判断、
真实 Agent 是否自主正确决定覆盖范围、端到端提速、独立业务语义验收。
本次工程 PASS 不证明上述非目标。

## 环境与通过标准

仓库 `/home/yangxiang/ontology-platform`，backend uv Python；执行时移除
`DEEPSEEK_API_KEY` 并设置 `PYTHONPATH=..`。原生 Unix socket、临时 Team fixture、
SQLite 实际服务和保留 RDF 三元组的受控 RDF fixture 可用；不调用本机 live 服务。
产品必须对各受验场景保持真实状态、写入身份及历史证据；全部工程用例通过且无严重残留缺陷，
才给工程 PASS。未执行用例按实际原因记 BLOCKED，不折算为 PASS。

| ID | 用例与步骤 | 期望结果 |
| --- | --- | --- |
| I01 | 保存当前 projection plans；读完成索引，测试全部和部分完成 | 准确映射 items/candidate/bindings；全部完成禁止重提交，部分完成不全部跳过 |
| I02 | historical dry-run pending + 成功后继，读平台尾部并构建恢复角色包 | 保留原始 pending/回执；生产角色得到准确资源/Attempt 事实；由 Agent 核对覆盖，审阅仅针对剩余 |
| I03 | 原生工具先完成一计划，再撤销另一计划翻译批准，恢复后再批准执行剩余 | 完成计划不重新 dry-run/apply；剩余保持业务批准、翻译批准和当前自身 dry-run/apply |
| I04 | 原生 staged 通道进入 applying/recovering，重复提交确切原请求 | 原 Batch/Attempt、key/content/session/lease 不变；旧回执保留，后续回执追加；终态拒绝重放 |
| I05 | 原件丢失、请求变化、返回新身份、新建标志、拒绝、unknown | 不伪报 applied、不抹掉不确定写入；拒绝保留原未决状态，unknown 禁止继续新写 |
| I06 | 实际 ModelingBatchService + SQLite + RDF 写后失响应，经原生工具恢复 | 通过原服务确定性恢复原 Attempt；RDF 只写一次，模型 revision 只增加一次，fence 清理，终态不重放 |
| I07 | 检查准确生产工具描述、权威提示和相邻既有恢复测试 | 调用指引与实际入口一致；现有身份、权限、当前 dry-run 和审批边界保留 |

## 测试轮次

### Round 1 — 2026-10-12（执行前登记）

- 基线 HEAD：`bc9aaf1894bb361a4a0492060de77ca6b858aa0b`；R4.3-014 产品及测试为主代理未提交改动。
- 产品输入：7 个文件 SHA 与 `workspaces/r4-3-014-engineering-20261012/product-sha-round1.txt`
  一致，结束时 `sha256sum -c` 全部 OK；`git diff --check` PASS。没有产品代码写入。
- 独立探针最终命令（工作目录 backend）：

  ```bash
  env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
    ../workspaces/r4-3-014-engineering-20261012/independent-probes.py -q -s
  ```

  结果：**1 failed、14 passed**，日志
  `workspaces/r4-3-014-engineering-20261012/independent-round1-final.log`。
- 相邻测试命令（工作目录 backend）：

  ```bash
  env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
    ../modeling_team/tests/test_r4314_recovery.py \
    ../modeling_team/tests/test_r30015_resume.py \
    ../modeling_team/tests/test_v43_production_refs.py -q \
    -k 'receipted_recovering or recovery_failure or recovery_packet or successor_readback or current_projection or same_attempt or pending or completed_plans or m16_real_service or classification_table or d1_readback or native_plan_refs or reference_dry_run_does_not_require_translation or apply_after_reference or second_plan_obtains'
  ```

  结果：**21 passed、76 deselected**，日志
  `workspaces/r4-3-014-engineering-20261012/independent-adjacent-round1.log`。
- 探针适配过程的中间日志保留：最初长 ontology ID 不符合实际 backend 长度、
  直接 service 返回的 datetime 尚未按 HTTP/MCP JSON 编码、缺既有 forwarder 必做的
  get_batch content_hash 读回合并、完成索引身份在 `key`、默认分页 limit 为 100。
  已只修隔离探针以符合已有真实合同；这些 fixture 适配错误不列产品缺陷。
  最终 SQLite 联测复用生产 `_merge_verified_attempt`，不伪造服务 Attempt/content_hash。

| ID | Round 1 | 实际证据 |
| --- | --- | --- |
| I01 | PASS | 当前 projection 的两计划仅完成一项；精确 items/candidate/identity 映射；仅完成项禁止重提交。相邻测试覆盖多 batch 计划部分完成 |
| I02 | PASS | 207 个实际分页返回的 batch，成功后继位于最后页；保留旧 pending；资源输出为 actual-id/实际 IRI，Attempt/Batch 可定位；恢复角色得到完成明细；源文件逐字节不变 |
| I03 | PASS | 首计划完成；剩余翻译批准缺失时无新提交，恢复批准后仅剩余计划自身 dry-run/apply；旧完成项返回 already_applied |
| I04 | PASS | applying 与 recovering 均可原请求恢复；追加同 intent 的回执；终态不重新 dry-run/apply |
| I05 | FAIL | session/client/items/plan_ref 改变、新 Batch/创建标志、unknown 均正确阻断；但仅更换 key 能触达 forwarder 并创建新 submitted intent，见 D01 |
| I06 | PASS | 原生 socket→实际 SQLite ModelingBatchService→权威 Batch/Attempt 读回→原请求恢复；RDF write_calls=1、revision 0→1、fence 清理、3 张回执，原2张逐字节不变；DB 仅2个Attempt（dry-run/apply），终态重放阻止 |
| I07 | PASS | 工具准确注明原请求恢复；Protocol 原件恢复与终态边界提示、JSON 合同一致；21 项相邻测试通过 |

#### D01 — HIGH：新执行 key 绕过原 recovering 请求的提交前边界

复现：独立探针 `test_independent_modified_request_cannot_recover[idempotency_key]`，
先通过原生 `protocol_execute_approved_plans` 得到 Runner 已 receipted、平台 recovering 的
apply；再通过 `protocol_staged_submit_modeling_batch` 提交相同 session/plan/items/version/lease，
仅把原 apply 的 `idempotency_key` 改为 `replacement`。

期望：在新增 intent 和转发前拒绝，准确提示原 Attempt 未决、应提交确切原请求或 Host 对账；
原2个 intent 及原回执保持，不产生新执行身份。

实际：apply dispatches **1→2**，intent statuses 从 `[receipted, receipted]` 变成
`[receipted, receipted, submitted]`；返回 `staged_batch_forward_failed`。
仅因本探针 forwarder 明确断言收到的请求必须与原件一致，才阻止后端写入；产品门本身未阻止
新 key 的 dispatch。该风险与是否存在后端 fence 兜底不同，Runner 已违反原身份恢复合同。
代码关联：`runner.py` 仅按新请求 key 查找 `recovery_intent`，新 key 不进入原件核对，
后续仅检查 `unknown` intent 而未阻止同范围的未决 receipted Attempt。

证据：最终日志的 JSON 诊断以及失败栈；对照四种原件变更均返回
`staged_recovery_request_mismatch`、apply dispatches 保持 1、原 intent 保持 receipted。

建议：开发在最窄的受影响原 Attempt/Ontology 范围补上提交前未决判断，保留原请求恢复通路，
不把其它不依赖未决写入的安全工作扩大为全局硬拒绝；修后用同文档 Round 2 复测。

- 工程结论：**FAIL**，D01 是交付阻塞；其它已执行工程范围 PASS。
- 真实恢复行为：NOT RUN，未授权创建或恢复生产 run。
- 独立语义验收：NOT RUN，工程 fixture 不构成业务语义证据。
- 写入停止：Round 1 日志和本文登记完成后停止探针/测试写入，等待主代理明确修复输入交接。

#### Round 1 文件 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| modeling_team/checkpoint_recovery.py | 8c146214fc03ea67b2f36fa85b6686740c5e2c28305f70d200cc092993133696 |
| modeling_team/runner.py | da0d1eb9a2fa9085d57993da56ad2986889a6e8d8cbb91392d06bf99eb29fe25 |
| modeling_team/capability_mcp.py | 1fde7e783f89c62d0d55d5ce8d7c20242c72953fff0d39799be7a2260a658e85 |
| modeling_team/agent-packages/protocol/instructions.md | 52609f999400cf5b9e0318e09eacaac40c459a7ee65a450ff200ed683902cfc4 |
| modeling_team/references/r3-0-008b-staged-decisions-contract.json | 12f496ff1199c8d9028772fe94af8c72e9278e2e56bee75740ee732b8b5d04f0 |
| modeling_team/tests/test_r4314_recovery.py | d96bd4787904840155ee20469a719a33986c45318b7faf1e438883c6b551862e |
| modeling_team/tests/test_r30015_resume.py | c6a1def37e6f072d2312b01e7203444bbc8084b5dcb1089b04d3715c26f2914e |

### Round 2 — 2026-10-12（执行前登记）

- 主代理交接 D01 修复：只增加已知 applying/recovering Attempt 的同 Ontology 查找，
  即使新请求换 key 也先进入原件核对；拒绝发生于 intent 创建和 forwarder 之前。
- 本轮产品基线：`product-sha-round2.txt`，启动核对 7 项全部 OK；原独立 15 项探针
  SHA `461f07dba138ac8ef248ed0c9d4f5591b77a8e5ce0793e0de061f5772169ae66`，不修改原探针。
- 复测：优先 D01，再原样覆盖全部 15 项及必要相邻回归；追加独立 Ontology 继续工作的
  探针，明确选择已批准 shared 资源，不依赖未决写入的资源事实，并核对原未决回执不变、
  之后原 Attempt 仍可确切恢复。
- 产品状态：HEAD 仍 `bc9aaf1894bb361a4a0492060de77ca6b858aa0b`；本轮 R4.3-014
  产品修复为主代理未提交改动。启动和结束时 `sha256sum -c product-sha-round2.txt`
  均 7 项 OK；原探针 SHA 不变；`git diff --check` PASS。
- 实际命令（工作目录 backend）：

  ```bash
  env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
    ../workspaces/r4-3-014-engineering-20261012/independent-probes.py -q -s
  env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
    ../workspaces/r4-3-014-engineering-20261012/independent-scope-probes.py -q -s
  env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
    ../modeling_team/tests/test_r4314_recovery.py \
    ../modeling_team/tests/test_r30015_resume.py \
    ../modeling_team/tests/test_v43_production_refs.py -q \
    -k 'receipted_recovering or recovery_failure or recovery_packet or successor_readback or current_projection or same_attempt or unrelated_ontology or pending or completed_plans or m16_real_service or classification_table or d1_readback or native_plan_refs or reference_dry_run_does_not_require_translation or apply_after_reference or second_plan_obtains'
  ```

- 原 15 项独立探针：**15 passed**，15.20 秒；日志 `independent-round2-original.log`。
- 新增独立范围探针：**2 passed**，2.84 秒；日志 `independent-round2-scope.log`；
  SHA `3f79063a0326c1d487663286e4f03b136e1271e4c3ead09f30aa5ad9a5f28e92`。
- 必要相邻回归含本次 12 项产品测试：**23 passed、76 deselected**，13.92 秒；
  日志 `independent-adjacent-round2.log`。日志均位于
  `workspaces/r4-3-014-engineering-20261012/`；不重复主代理的完整 Team suite。

| ID | Round 2 | 结论与证据 |
| --- | --- | --- |
| I01 | PASS | 原映射及部分完成独立探针复验通过，完成项阻止重提、剩余项保持可提交 |
| I02 | PASS | 原207批分页/历史pending/角色事实/源字节保留探针复验通过 |
| I03 | PASS | 原部分完成、剩余翻译批准及当前自身dry-run/apply探针复验通过；其它范围正常推进也是自身批准和dry-run/apply |
| I04 | PASS | applying/recovering原请求恢复及终态拒绝原样复验通过；另范围成功后原Attempt仍可同身份恢复 |
| I05 / D01 | FIXED | 新key现在返回staged_recovery_request_mismatch，apply_dispatches保持1、intent_statuses仍[receipted,receipted]，原回执不变；其它四种变更、unknown及新身份拒绝无回归 |
| I06 | PASS | 实际SQLite后端再次恢复成功，RDF写1次、revision 0→1、fence清理、原2张回执逐字节保留并追加第3张；仅2个Attempt，终态重放阻止 |
| I07 | PASS | 产品提示/工具面未变，必要23项相邻回归通过 |
| 新范围边界 | PASS | applying/recovering各1项：另Ontology的两个relation endpoints均为既有approved shared资源，避免依赖未决内容；正常自身dry-run/apply；原scope版本不增加，原回执字节保留，原proof仍是未决状态；之后原请求同Attempt恢复；最终两计划均already_applied、无重放dispatch |

- 工程结论：**PASS**，D01 已 FIXED，无 STILL FAILING／REGRESSION／BLOCKED 工程用例。
- 真实生产恢复行为：**NOT RUN**，本轮不创建或恢复生产 run，不消耗 semantic start。
- 独立业务语义验收：**NOT RUN**。这里的 SQLite/RDF、共享资源和批准都是隔离工程
  fixture；不证明真实 Agent 会自主正确判定历史内容覆盖，不证明完整业务质量或提速。
- 历史保持：Round 1 FAIL、D01 原复现及所有中间日志均保留；本轮不改原探针、产品、
  权威需求、原生产运行证据。
- 写入停止：本轮命令均已退出、临时fixture已收尾；记录完成后停止验收探针/日志写入。

#### Round 2 文件 SHA-256

仅 `runner.py` 与 `test_r4314_recovery.py` 相对 Round 1 改变，其余5项与前轮一致。

| 文件 | SHA-256 |
| --- | --- |
| modeling_team/runner.py | 6fa07a8c2bf0ddbe2d04c89b090306f0553110c194ab74dd75084865e9f657bd |
| modeling_team/tests/test_r4314_recovery.py | e50a0abb49fbcdc11fc22d171a68828999cd4412d6f9c3bc43baf37bda855f06 |

#### Round 2 收尾元数据增量 — 独立静态 PASS

主代理仅把已实现并已测试的 `staged_recovery_request_mismatch` 加入
`staged_decisions.py` 的 `STAGED_REASON_CODES` 和 JSON 的
`staged_submission_capability.failure_reason_codes`；原规则文字本已说明该码。
实际执行分支、Runner、packet、工具及角色提示未改，不新开行为测试轮次。

- 独立实际检查：`git diff -- modeling_team/staged_decisions.py
  modeling_team/references/r3-0-008b-staged-decisions-contract.json` 确认目录增量；
  backend 下 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run python -` 以 AST
  提取元组、`json.loads` 解析合同，并逐项断言新码在两处各出现一次；
  读 `independent-round2-original.log` 核对新 key 的实际反馈同码且转发次数仍为1。
- 结果：**PASS**，JSON有效，新码与实际已测反馈一致。共享元组既有的
  `staged_evidence_forward_failed/unknown` 是同级 Evidence capability 的目录项，
  不属于 staged batch submission 目录；该既有范围差异保持，没有把两份完整目录
  错称为完全相同。
- 已测本体的6项 SHA（Runner、checkpoint、capability、Protocol提示与两份测试）
  和 Round 2 一致；`git diff --check` PASS。目录文件最新 SHA：
  `staged_decisions.py` 为 `865fcb1945ef532253545793a28a4f0cf04f39ee9821881489e0580458e44d27`；
  JSON 为 `a6984b9c351c4c7f6caddf4de9bd4c40f7ddcffd75e77477c8d4ed6074038901`。
- 工程 **PASS** 复用 Round 2，真实生产恢复/独立业务语义仍 **NOT RUN**。
  元数据检查和本文补记后再次停止验收写入；未改产品或原运行证据。
