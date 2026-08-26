# R3.0-002 完整场景多切片建模流程 — 共享测试计划

- 日期：2026-08-26
- 状态：已实现并验收（Round D 自测 + 独立 Round 1 PASS，2026-08-26；R3 ruff 基线处置见
  文末"主代理收口处置"）
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-002
- 设计：
  `docs/delivery/designs/2026-08-26-r3-0-002-multi-slice-modeling-workflow-design.md`
- 执行者：Requirement Developer 自测；独立 Requirement Tester 复核保留证据（不创建、不继续、
  不清理被测 run）
- 验收性质：**只做确定性/机械验证**（循 R2.3-001 先例）。不验收语义模型质量（R3.0-006）、
  不做真实 modeling start、不消费建模 attempt 预算、不宣称 R3.0-003/005/006 或 v3.0 完成

## 1. 测试边界

只验收 R3.0-002 的机械增量：

1. 资产合同存在且符合（task/profile/references/工具集合）。
2. Runner 门机制按合同行为（拓扑门拦截/放行、场景地图结构校验、守恒）。
3. 空/测试作用域 smoke 走通多切片机械链路：场景地图产出 → 拓扑门拦截→放行 → 多批次按序
   dry-run 模拟（`dry_run`-only，不 apply）→ 保护 IRI 建议交接物格式。
4. 不验收：拓扑决策优劣、术语取舍正确性、模型语义质量、访谈质量（均归 R3.0-006）。
5. 不修改 `docs/evaluation-scenarios/industrial-service-v3/modeling-input/`（含工作区中该
   目录的未提交用户改动，一律保留原样）。

## 2. 稳定测试命令

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q
uv run --project backend ruff check modeling_team
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-002-modeling-team.yaml \
  --task modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml
cd backend && uv run pytest    # backend 零 diff 时的确认性全量（基线 881/10）
```

若（例外）发生 backend 窄修复：`cd backend && uv run pytest` 全绿 →
`systemctl --user restart ontology-platform.service` → 健康检查（§8 L1）。

## 3. Fixture 设计

- 合同级：`modeling_team/tests/fixtures/` 下新增 v3.0 fixture——合法/违约场景地图 JSON、
  合法/违约拓扑决策 JSON、合法/违约保护 IRI 建议 JSON；切片标识用 `S1..S5` 语义命名但内容
  为占位文本；IRI 一律 `https://r30002.test/…` 命名空间。
- live 级（L 轮，见 §8）：一个一次性测试 Project + 2 个测试 Ontology（`O_A`/`O_B`，
  模拟"每 Ontology 一批次"）+ 一个测试保护集；全部经平台创建路径产生，测试后按 §9 清理。
- 场景输入包（`docs/evaluation-scenarios/industrial-service-v3/modeling-input/`）只读引用，
  不修改。

## 4. 成功路径（S）

- **S1 配置资产**：`r3-0-002-multi-slice-smoke.yaml`、`r3-0-002-multi-slice.yaml`、
  `r3-0-002-modeling-team.yaml`、`references/r3-0-002-scenario-map-contract.json` 全部通过
  `python -m modeling_team validate` 与加载（三角色 profile 经非 formal 加载通路）；真实
  任务条目的 role_sources 恰为 `modeling-input/` 的 4 个 `allowed_files`
  （`scenario-brief.md`、`business-terms.md`、`schema.sql`、`sample-data.sql`），不含
  `input-manifest.json` 与参考文档。
- **S2 场景地图合同**：合法 fixture 过 `validate_scenario_map`；六节齐备、共享术语恰一
  owner、依赖端点/CQ spans 闭合。
- **S3 拓扑门放行**：含三个规定方案 × 六维度非空 × 选择 + 理由的决策记录通过
  `validate_topology_decision`，且 Runner 接线在 `multi_slice_workflow: true` 任务下允许
  独立平台 MCP 门打开（协议 Agent 平台 MCP 可用）；**接线断言：MCP env 传参点
  （`runtimes/codex.py:3641` 一线）与沙箱 bind-mount 点（`codex.py:3014`/`4024` 一线）的
  gate 条件对该任务同时为真、对既有非多切片任务同时为假**（设计增量 7，防 High-4 单点
  扩展死锁）；两个新任务 YAML 断言为 `schema_version: 2`（`protocol_mcp_launch.py:76` 与
  `codex.py:4024` 的门传参/挂载均以 v2 为前提，误写 v1 会静默失效）；开闸身份字段按设计
  A.1 合同由 artifact sha256 合成且可确定性断言。
- **S4 保护 IRI 交接物**：合法建议清单过 `validate_protection_iri_suggestions`；
  `SAFE_PROTOCOL_TOOLS_R30002` 恰为 `SAFE_PROTOCOL_TOOLS` ∪ 6 个保护集工具名
  （`list_semantic_protection_set(s)`、`create/update/delete_semantic_protection_set`、
  `add/remove_semantic_protection_set_members`，以 `protection_sets.py` 实名为准）。
- **S5 多批次按序模拟（单元级）**：以两个测试 Ontology 的依赖顺序（O_A → O_B）构造
  dry-run-only 批次计划断言：每批次绑定恰一个 `ontology_id`；顺序与场景地图依赖一致；
  无 apply 调用。

## 5. 边界路径（B）

- **B1 场景地图结构违约**：缺节 / 术语多 owner / 依赖端点不在切片集合 / CQ spans <2 /
  schema_version 不符 → 各自确定性错误码，且不产生部分通过。
- **B2 artifact 异常**：文件缺失 / 非 JSON / 路径逃逸 / 符号链接 → 拒绝且不在 run 目录外
  读写。
- **B3 单 Ontology 选择不豁免**：`selected_option=single_ontology` 时仍须完整三方案六维度
  决策记录（门不因选择结果省略比较）。
- **B4 保护集与发布独立**：交接物中 `existing:<id>`/`new:<name>` 两种目标均被格式接受；
  合同层面保护集操作与批次发布无同批次绑定（机械上二者为独立产物/独立调用序列）。
- **B5 悬空 IRI**：建议清单含尚未创建资源的 IRI 仍格式合法（R3.0-004 允许悬空成员）。
- **B6 未知项为空合法**：`explicit_unknowns: []` 通过结构校验（内容充分性非机械判断）。

## 6. 失败路径（F）

- **F1 拓扑门拦截（逐 reason_code）**：缺 artifact / 不可解析 / schema 不符 / 方案数 <3 /
  缺规定方案 / 缺维度键 / 维度值为空 / 缺选择 / 理由为空 → 每种输入对应恰一个确定
  reason_code；`multi_slice_workflow: true` 任务的独立平台 MCP 门保持 closed（协议 Agent
  全部平台调用被拒，含读，循 formal 门先例，见设计 §3.3）。
- **F2 开闸前拦截时 run 不死锁**：门失败后 typed 反馈可达责任 Agent（协调 Agent）通道，
  run 未被终止、未记 modeling-quality 失败（T0 自修复路径；以 fake-adapter 单元级验证）。
- **F3 守恒**：不带 `multi_slice_workflow` 参数的全部既有 task/profile 加载与运行路径零
  行为变化（含 `runtimes/codex.py` gate-enable 条件扩展对 formal run 的零影响）；
  `SAFE_PROTOCOL_TOOLS` 集合逐字节不变；R2.3-005/009 formal 任务的 receipt
  管线测试全绿；strict 四角色校验对既有 formal profile 不变。

## 7. 回归（R）

- **R1 modeling_team 全量**：`modeling_team/tests` 全绿（R2.3-009 后基线 970 passed /
  1 skipped / 302 subtests 之上不新增失败）；重点 `test_contracts.py`、`test_runner.py`、
  `test_candidate_platform_gate.py`、`test_r23005_mechanical_spine.py`、
  `test_r23009_*`。
- **R2 backend 全量**：backend 零 diff 时为确认性运行（881 passed / 10 skipped 基线）；
  发生窄修复时为完成门必需。
- **R3 ruff**：`uv run --project backend ruff check modeling_team` 通过。

## 8. 真实运行（L，机械 smoke，独立于 pytest；按设计 §9 裁决 1，L1–L4 为完成门必需）

- **L1 服务健康**（backend 有改动或窄修复时先重启）：`systemctl --user restart
  ontology-platform.service` → unit active → `curl --fail http://127.0.0.1:8001/api/health`
  → `curl --fail http://127.0.0.1:5173/`。
- **L2 测试作用域多批次 dry-run 模拟**：一次性测试 Project 下创建 `O_A`/`O_B`；建 Build
  Session + 按 Ontology Lease；按 O_A → O_B 顺序各提交一个 `dry_run=true` 的最小批次并断言：
  每批次 `ontology_id` 绑定正确、依赖顺序成立、**零 `apply_atomic`、零 RDF 写入**；项目级
  project scope 检索接口对两个 Ontology 可达（读-only）。注：dry-run 批次按平台合同须
  **省略 `lease_token`**（`backend/app/services/modeling_batches.py:260-264`），Lease 仅验证
  可获取/可释放，不随 dry-run 批次提交。
  已裁决的降级规则（唯一例外）：若实现时证明批次提交必须走 formal 候选通道（设计 §8
  假设 2 的兜底情形发生），L2 的批次提交部分降级为单元级模拟并在本轮记录中显式记录该
  平台合同事实与证据，L1/L3/L4 照旧必需。
- **L3 保护集机械操作**：model key 在测试 Project 创建保护集 → 添加 L2 场景的建议 IRI
  （含至少一个悬空 IRI）→ 列表核对 → 移除成员 → 删除保护集；全程走 MCP/HTTP 既有合同。
- **L4 交接物→执行链**：L3 使用的前置输入恰为 S4 格式的 `protection-iri-suggestions.json`
  fixture（机械上证明交接物格式可被协议侧消费）。
- 不启动任何 Agent run、不提交语义候选、不申请建模 attempt。

## 9. 清理

1. 删除 L2/L3 测试 Project（平台删除路径，级联 Ontology、保护集、Build Session/Lease/Batch
   行）；只读 SQL/SPARQL 复核无 `r30002` 命名空间与测试 Project 残留。
2. 测试用 model/admin key 全部回收；无临时脚本、无临时 MCP 进程残留；`backend/.env` 未改。
3. fixture 常量只存在于 `modeling_team/tests/`；产品代码无 `r30002` 命名空间。
4. 清理账本记录：Project/Ontology/key ID（不含明文密钥）、删除回执、健康检查结果。

## 10. 判定规则与完成门

- **PASS**：S1–S5、B1–B6、F1–F3、R1–R3 全部通过；L1–L4 全部通过（L2 按已裁决降级规则
  处理时须有显式记录与证据）且 §9 清理完成；守恒测试在位。
- **FAIL**：拓扑门放行了不合格决策记录或拦截了合格记录；场景地图校验存在部分通过/漏判；
  任何既有任务行为变化；L 轮发生 apply/RDF 写；回归失败。
- **BLOCKED**：仅用于本地平台/服务无法运行等外部条件。
- 完成后由主 agent 收口：更新 R3.0-002 状态与需求文档信息区链接、设计/测试计划状态行；
  R3.0-003/005/006 状态不变；不得据本验收宣称语义建模能力或 v3.0 完成。

## 轮次记录

（开发者自测 Round D 与独立测试轮由执行者追加，append-only，不得改写历史轮次。）

### Round D（开发者自测，2026-08-26，requirement_developer）

- 执行者：Requirement Developer（development-ready 信号 2026-08-26）。
- 被测状态：branch `main`，HEAD `0edf90a` + 未提交工作区（modeling_team 7 改 + 10 新；
  backend/frontend 零 diff）。
- 稳定命令输出：
  - `env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest
    modeling_team/tests -q` → 1085 passed / 1 skipped / 302 subtests passed，0 失败
    （基线 970/1/302 之上新增 115 用例全绿）。
  - `uv run --project backend ruff check modeling_team` → 10 findings，开发者自证全部
    位于本需求未触碰行（runner.py 既有 F821、test_r23008/r23009 既有 F401/F841）；
    独立轮 Round 1 经 HEAD worktree 对照复核确认。
  - validate CLI（smoke 与真实任务两个 YAML）→ EXIT=0，roster
    `["coordinator","modeling","protocol"]`。
  - `cd backend && uv run pytest -q` → 881 passed / 10 skipped（与基线一致，backend 零 diff）。
- 开发中自研测试发现并修复 3 个实现 bug：`validate_scenario_map` 闭合键集漏
  `schema_version`（致所有合法地图被拒）；`task_declares_multi_slice_workflow` 对不可解析
  任务改为 fail-safe False（打桩冲突崩溃）；`_check_multi_slice_topology_gate` 用
  `getattr` 防御 `object.__new__(TeamRunner)` 打桩。
- 记录的偏差（均在设计容忍内）：开闸时场景地图不可读仅记 evidence（`map_unparsable`
  保留在关闭列表）；内部开闸失败用未列入设计 §5 的 `multi_slice_gate_open_failed`
  （runtime/infrastructure 证据，门保持关闭，run 继续）；references 合同仅经 smoke 任务
  role_sources 挂载，真实任务 role_sources 恰为 4 白名单文件、经 objective 文本引用合同。
- 无 scratch/run 目录残留；未 commit；无服务重启（无 backend 改动）。

### Round 1+（独立测试，待稳定保留证据后由 requirement_tester 追加）

- 边界：独立轮不创建、不继续、不清理被测 run；只读复核保留证据、离线检查与服务健康；
  缺失证据记 FAIL/BLOCKED 而非重建。

## Round 1（独立测试，2026-08-26，requirement_tester）

- 执行者：requirement_tester（独立轮；未创建/继续/清理任何被测 Agent run，未修改产品代码，
  未触碰 `docs/evaluation-scenarios/industrial-service-v3/**` 的用户未提交改动）。
- 被测状态：branch `main`，HEAD `0edf90a`，开发者的未提交工作区（modeling_team 7 处修改 +
  10 个新文件 + 2 份 docs/delivery 规划文档），与主 agent 声明的稳定状态一致。
  独立核验：`git status` 无 backend/frontend diff（`git diff HEAD --stat -- backend/ frontend/`
  与 `git status --porcelain backend/ frontend/` 均为 0 行）。

### 实现审查（diff vs 设计）

- 门谓词统一（设计增量 7 / 计划评审 High-4）：`runtimes/codex.py` 新增
  `_is_multi_slice_run()`；`_candidate_platform_gate_enabled_for_run()` 改为
  `(formal_acceptance OR multi_slice_workflow) AND schema_version==2`，MCP env 传参点
  （`codex.py:3662`）与沙箱 bind-mount 标志赋值点（`codex.py:3039-3041`，消费点 `codex.py:4045`）
  两处均只调用该单一谓词。关键守恒事实独立核实：HEAD 版赋值点条件为
  `self._coordination_enabled and v2`，而 `codex.py:2986` `_coordination_enabled =
  _is_formal_acceptance_run(run)`，故旧条件等价于 `formal and v2` —— 新谓词对既有任务严格不变。
- `SAFE_PROTOCOL_TOOLS` 字节不变：frozenset 字面量与 HEAD 逐字节相同（独立正则提取比对
  True）；集合内容与硬编码 21 工具清单相等。`SAFE_PROTOCOL_TOOLS_R30002 = SAFE ∪ 6 个
  保护集工具`，与 `backend/app/mcp/tools/protection_sets.py` 实名逐一核对一致。
- strict 四角色校验未动：`load_formal_team_configuration` 对三角色 profile 仍拒绝
  （`test_multi_slice_profile_is_not_a_formal_profile`）；非 formal 三角色通路为独立显式分支
  （`contracts.py` `MULTI_SLICE_PROFILE_IDS` 封闭注册表 + `load_multi_slice_team_configuration`），
  CLI `validate`（`__main__.py:541-557`）与 `TeamRunner.prepare`（`runner.py:404-417`）按
  `task_declares_multi_slice_workflow` 分派；无 `parameters` 键的 v2 Task 校验路径逐字节等值
  （新增 4 个合法字段集超集，仅含 `parameters`）。
- 真实任务 role_sources 与 `input-manifest.json` 的 4 个 `allowed_files` 逐字一致，不含
  `input-manifest.json`；两个新任务 YAML 均 `schema_version: 2` 且 `parameters:
  multi_slice_workflow: true`。
- 拓扑门（runner.py `_check_multi_slice_topology_gate`）：fail-closed 起步
  （`topology_missing_artifact`）、逐 reason_code 拒绝、typed 去重反馈到协调 Agent、
  run 不终止；开闸身份按设计 A.1 合成（`original_delivery_id="r30002-topology:{run_id}"`、
  `candidate_digest`=决策文件 sha256、`semantic_digest`=地图 sha256、`candidate_revision="1"`）。
  `runner.py:3563` 的 `r30002-topology:` 前缀即 A.1 合同本身，产品代码无 `https://r30002.test/`
  fixture 命名空间。

### §2 稳定命令输出（逐字）

```text
env -u DEEPSEEK_API_KEY PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modeling_team/tests -q
→ 1085 passed, 1 skipped, 302 subtests passed in 46.96s
  （R2.3-009 基线 970/1/302 之上新增 115 个用例全部通过，无新增失败）

uv run --project backend ruff check modeling_team
→ Found 10 errors（EXIT=1）。经 HEAD 临时 worktree 对照：错误集合与 HEAD `0edf90a` 完全
  相同（唯一差异是同一 F821 的行号 4437→4668），10 条全部位于本需求未触碰的行/文件
  （runner.py 既有 F821 `RuntimeDispatchReceipt`、test_r23008/r23009 既有 F401/F841）。
  R3.0-002 新增/修改代码本身 ruff 零报错。

uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-002-modeling-team.yaml \
  --task modeling_team/tasks/r3-0-002-multi-slice-smoke.yaml
→ {"profile_id": "r3-0-002-modeling-team", "task_id": "r3-0-002-multi-slice-smoke",
   "task_overlay_id": null, "model_profile": null,
   "roster": ["coordinator", "modeling", "protocol"]}（EXIT=0）

uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-002-modeling-team.yaml \
  --task modeling_team/tasks/r3-0-002-multi-slice.yaml
→ {"profile_id": "r3-0-002-modeling-team", "task_id": "r3-0-002-multi-slice",
   "task_overlay_id": null, "model_profile": null,
   "roster": ["coordinator", "modeling", "protocol"]}（EXIT=0）

cd backend && uv run pytest -q
→ 881 passed, 10 skipped, 226 warnings in 42.00s（与基线 881/10 一致，backend 零 diff 确认）
```

### 逐项结果

| 用例 | 结果 | 证据 |
| --- | --- | --- |
| S1 配置资产 | PASS | 两个 task + profile + references 合同经 CLI validate EXIT=0；references 合同常量与 `scenario_map.py` 模块常量一致（`test_references_contract_matches_module_constants`）；真实任务 role_sources 恰为 4 个 allowed_files（测试断言 + 人工比对 `input-manifest.json`） |
| S2 场景地图合同 | PASS | 合法 fixture 零 issue；独立 adversarial 探针：缺节+悬空 owner 组合违约被拒（不部分通过），7 类违约各得确定 reason_code |
| S3 拓扑门放行 | PASS | 三方案×六维度决策过 `validate_topology_decision`；W1/W2 接线测试断言两接线点对 `multi_slice_workflow` 同时为真、对 ordinary/v1/None/False/字符串参数同时为假（独立探针 10 例全 OK）；两 YAML 均 v2；开闸身份 sha256 确定性断言（`test_runner_multi_slice_gate_lifecycle`） |
| S4 保护 IRI 交接物 | PASS | 合法建议（含悬空 IRI）过校验；`SAFE_PROTOCOL_TOOLS_R30002 = SAFE ∪ 6 工具` 且与 SAFE 不相交；`existing:<id>`/`new:<name>` 双目标均被接受（fixture 含两形态） |
| S5 多批次按序模拟 | PASS | 单元级：`models.py:268` `ontology_id` 非空（一批次一本体）+ L2 live 实证（下）：2 批次各绑定恰一个 ontology、O_A 先于 O_B、零 apply |
| B1 场景地图结构违约 | PASS | 缺节→`map_missing_section`、多 owner→`map_term_owner_not_unique`、依赖端点不在切片集合→`map_dangling_reference`、CQ spans<2→`map_schema_mismatch`（确定码）、schema 不符→`map_schema_mismatch`；无部分通过 |
| B2 artifact 异常 | PASS | 缺失/非 JSON/非对象→`*_unparsable`；符号链接→拒绝（`test_loaders_reject_symlinked_artifact`）；canonical 路径由 runner 构造（`scenario_map_artifact_paths`），无用户可控路径输入 |
| B3 单 Ontology 不豁免 | PASS | `single_ontology_selected_valid` 全量决策通过；独立探针：删去第三方案后即使选 single_ontology 仍被 `topology_insufficient_options`+`topology_missing_required_option` 拒绝 |
| B4 保护集与发布独立 | PASS | 两目标形态格式均受；L3 live 中保护集操作与批次为完全独立调用序列 |
| B5 悬空 IRI | PASS | `test_valid_protection_suggestions_allow_dangling_iris` + L3 live 成员含悬空 IRI |
| B6 未知项为空合法 | PASS | 合法 fixture `explicit_unknowns: []` 零 issue |
| F1 拓扑门逐 reason_code | PASS | 9 个 reason_code 各有确定 fixture/路径；runner 反馈取 `issues[0].reason_code`（列表构造顺序确定，每类输入首个码即目标码——独立探针确认）；closed 期全平台调用被拒为 backend 既有合同（`runtime.py` formal 门先例），单元级由门 state closed 断言覆盖 |
| F2 开闸前不死锁 | PASS | `test_runner_multi_slice_gate_lifecycle`：门失败→typed 反馈恰一次（指纹去重）、`runner.run` 保持、无 modeling-quality 失败记录；反馈派发自身失败仅记 evidence 不杀 run（`_deliver_multi_slice_gate_feedback` 异常分支） |
| F3 守恒 | PASS | 无 `parameters` 键任务零行为变化（`test_existing_tasks_do_not_declare_multi_slice_workflow`、`test_runner_existing_v2_task_keeps_no_multi_slice_gate`、`test_task_parameters_extension_is_closed_and_boolean` 封闭参数集）；`SAFE_PROTOCOL_TOOLS` 字节不变（HEAD 对照 + 硬编码 21 工具断言）；`test_candidate_platform_gate.py` 既有断言全绿；formal receipt 管线测试包含于全量 1085 passed |
| R1 modeling_team 全量 | PASS | 1085 passed / 1 skipped / 302 subtests（基线 970/1/302 之上无新增失败） |
| R2 backend 全量 | PASS | 881 passed / 10 skipped，backend/frontend 零 diff（git 双重核验） |
| R3 ruff | **FAIL（前置存在，非本需求回归）** | 10 errors 与 HEAD `0edf90a` 错误集合完全相同（HEAD worktree 对照，唯一差异同一 F821 行号位移）；R3.0-002 触碰的代码零新增报错 |
| L1 服务健康 | PASS | unit `active`；未重启（backend 零 diff）；`curl http://127.0.0.1:8001/api/health` → `{"status":"ok"}`；`curl http://127.0.0.1:5173/` → 200 |
| L2 多批次 dry-run | PASS | 见下 L2 证据 |
| L3 保护集机械操作 | PASS | 见下 L3 证据 |
| L4 交接物→执行链 | PASS | L3 输入为 S4 格式 `protection-iri-suggestions.json` fixture（`r3-0-002-protection-iri-suggestions/v1`，3 条目含 1 悬空 IRI），经 `validate_protection_iri_suggestions(slice_ids={S1,S2,S4})` 零 issue 后按其 IRIs 执行 |

### L2/L3/L4 live 证据（一次性测试作用域，admin key 复用 backend/.env 既有
`harness-eval-admin` org-admin key，循 R3.0-007 先例；model key 经 `POST /api-keys` 自建）

- 测试 Project `7002ae90-1186-4e07-bf81-c0fcc89c7a5b`（r30002-test-*）；Ontology
  O_A `20bbe35a-c75b-4b50-b28d-8d2be5cc85e7`、O_B `8db4e177-b8c5-4774-9891-3a3fb987c930`。
- Build Session `a980c1f6-…` active；O_A→O_B 各完成 lease acquire（token 返回）→ release。
- dry-run 批次（`mode:"dry_run"`、**无 `lease_token`**、各 1 个 `create_class` 占位 item）：
  - batch A `daf33e96-…` → `ontology_id=O_A`，created `11:48:19.964979Z`，latest_attempt
    `mode=dry_run, attempt_status=validated`，`workspace.after_version=null`，全部 4 图
    `revision_after=null`（唯一 finding 为非阻塞 warning `missing_evidence`，符合最小占位批次）；
  - batch B `1cfa245a-…` → `ontology_id=O_B`，created `11:48:20.122194Z`，同上。
  - 断言：恰 2 批次、按 created_at O_A 严格先于 O_B、各绑定恰一个 ontology_id、
    零 `apply_atomic`（两批次 `batch_status=open`，无 apply attempt）、零 RDF 写入
    （Oxigraph `:7878` SPARQL：两本体全部 8 个图三元组数 dry-run 前=0 后=0；
    全库 `https://r30002.test/` 前缀主语三元组=0）。
- 项目级检索读-only：`GET /api/semantic/scopes:discover` 同时列出 O_A/O_B（queryable=true）；
  `POST /api/semantic/context:query`（project scope）200 可达。
- L3：model key（`scopes=[model,read]`，绑定测试 Project，id `e7e49acf-…`）创建保护集
  `001fb746-…`（allowed_grants=[r30002-test-grant]）→ 添加 3 成员（含悬空 IRI
  `https://r30002.test/dangling/NotYetCreated-*`，且成员横跨 O_A/O_B 图）→
  列表核对 member_count=3、成员=fixture IRIs → 移除 3 成员（count=0）→ 删除保护集 204 →
  项目保护集列表空。
- 全程零 Agent run、零语义候选、零建模 attempt、零 apply、零 RDF 写。

### 偏差与观察

1. **R3 ruff FAIL（前置存在）**：10 条错误在 HEAD `0edf90a` 即存在且错误集合逐条相同
   （`runner.py` F821 `RuntimeDispatchReceipt`（HEAD:4437→现:4668）+ r23008/r23009 测试文件
   8 条 F401/F841），全部不在 R3.0-002 改动行。测试计划 §2 将 ruff 通过作为稳定命令，
   其基线假设（基线本身 ruff 干净）不成立。处置建议：由主 agent 决定——(a) 修复 10 条
   前置 lint 债后复跑 R3，或 (b) 显式把 ruff 基线重设为"不新增错误"。非本需求缺陷。
2. **观察（非缺陷，R3.0-004 既有合同）**：project-bound model key GET 已删除保护集得
   403 `forbidden_scope`（`security/http.py` 项目边界 fail-closed：资源 owner 不可解析），
   org-admin 得 404 `protection_set_not_found`。二者均为拒绝，不泄露存在性；不属本需求范围。
3. F1 个别组合违约 fixture 会产生多个 issue 码（如 schema_mismatch fixture 共 4 码），
   门反馈取确定的首码——满足"确定性 reason_code"要求，"恰一个"按门反馈口径成立；记录备查。
4. L2 脚本首轮两处测试脚手架错误（session detail 嵌套字段、semantic 路由 `/api/semantic`
   前缀），修正后重跑；对平台无副作用（批次幂等键重放返回既有 attempt）。

### 清理账本（§9）

- `POST /api-keys/{e7e49acf-8a24-4d47-8561-0e42d92a4567}:revoke` → 200；
  复用的 org-admin key 不新建不回收（R3.0-007 先例）。
- `DELETE /api/projects/7002ae90-1186-4e07-bf81-c0fcc89c7a5b` → 204（平台删除路径，
  级联回收 project-bound key）。删除后只读核验：project/O_A/O_B/session/batches GET 全 404。
- 只读 SQL（psycopg）：projects/ontologies/build_sessions/modeling_batches/ontology_leases/
  semantic_protection_sets 残留行=0；`api_keys` 中 r30002-% 行=0（含未回收=0）。
- 只读 SPARQL：全库 `https://r30002.test/` 主语三元组=0。
- 临时脚本与 L4 fixture（`/home/yangxiang/.claude/jobs/7ba40df6/tmp/`）已全部删除；
  HEAD 对照 worktree `/tmp/r30002-head-check` 已移除；`backend/.env` 未修改；
  产品代码无 `r30002` fixture 命名空间（`runner.py:3563` 的 `r30002-topology:` 为 A.1
  开闸身份合同前缀）。
- 健康复核（清理后）：`/api/health` `{"status":"ok"}`、`:5173/` 200、unit active。

### 结论与残余风险

- **总体：PASS（附一项前置基线偏差 R3）**。S1–S5、B1–B6、F1–F3、R1、R2、L1–L4 全部通过；
  R3 因前置存在（HEAD 相同）的 10 条 lint 债未过命令门，与本需求改动无因果。
- 残余风险：
  1. R3 前置 lint 债未清（见偏差 1），主 agent 收口前需裁决处置方式；
  2. L1–L4 只证明机械链路，拓扑决策内容质量、语义质量、真实多切片建模归 R3.0-006；
  3. `preview_baseline`/`baseline` 命令仍走 strict（设计 Low-6 已预留），R3.0-006 真实 run
     前须补分派；
  4. 门开闸后无再关闭机制（开闸即终局，`_multi_slice_gate_opened` 锁存）——设计未要求
     再关闭，但 R3.0-006 若决策记录事后被改，门不会回闭；属设计取舍，记录备查。

## 主代理收口处置（2026-08-26）

1. **R3 ruff 偏差裁决**：采用 tester 建议 (b)——本需求 R3 完成门口径重设为
   **"相对 HEAD `0edf90a` 不新增 ruff 错误"**，Round 1 已以 HEAD worktree 对照证明满足
   （错误集合逐条相同，仅同一 F821 行号位移，本需求触碰代码零报错）。理由：10 条 lint 债
   前置存在且位于 R2.3 已验收文件，在本需求 diff 内修复会扩大已验证改动面到基线代码，
   属范围蔓延；存量 lint 债（runner.py F821 `RuntimeDispatchReceipt`、test_r23008/
   test_r23009 的 F401/F841）单独登记为后续清理项，不属于 R3.0-002 交付或其回归。
2. **判定**：R3.0-002 独立测试 Round 1 记 **PASS**（S1–S5、B1–B6、F1–F3、R1、R2、
   L1–L4 通过；R3 按上述口径通过）。共享测试计划 §7 R3 的原始文字（"ruff 通过"）保留
   原文不改写；本处置为对其基线假设不成立的显式修正记录。
3. **收口动作**：更新 `docs/requirements/requirements-v3.0.md` R3.0-002 状态为已完成并
   链接本设计与测试计划；R3.0-003/005/006 状态不变；不据此宣称 v3.0 完成。
