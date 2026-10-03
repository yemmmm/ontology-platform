# start3 检查点重启独立验收

## 范围与证据边界

本会话的 r3 指第三次实际 semantic start，即
`r4009-20261003-solmedium-auth01-start3`。本验收只读审查其
`materialization_progress-0022` 到 `r4009-20261003-solmedium-auth01-start4c` 的恢复，
对应 R3.0-015 恢复与审批合同、设计 §6.1；不创建、继续或修复真实 run，不修改源证据，
不调用业务 SQL，不读取 CQ 题目／答案。CQ 仅使用 manifest metadata 与不解析内容的文件哈希。
验收方没有执行本次恢复，也没有生产恢复证据；产品运行与语义验收分别判定。

当前结论：**真实接续与安全续写 bounded L0 runtime PASS；旧包自动完整恢复 REVISE**。
Round 4 已核对新 Session、lease、writer、新 dry-run 和两批实际 apply。High
H-R3-ARCHIVE-01 的捕获缺陷在当前代码已获独立有界功能修复复验，旧检查点的缺包及人工
补充事实仍保留。最新已核对 `state.json=RUNNING`；Round 1 的 WAITING_REPAIR 是当时
状态。没有据此判定语义建模／CQ 质量 PASS。

## Round 1 — 来源、对账索引与恢复产物只读核对

读取位置均位于 `workspaces/modeling-runs/`，未改动原件：

- source：`r4009-20261003-solmedium-auth01-start3/`；
- package：source 下 `checkpoints/materialization_progress-0022/`；
- restored：`r4009-20261003-solmedium-auth01-start4c/`，重点为 `recovery/{origin,inspection,imports}.json`、中性角色 packet 和相关 evidence metadata。

执行方式：Python 标准库 `json` 仅解析获准 metadata／普通建模产物；`hashlib.file_digest`
逐文件计算 SHA-256，不解析 CQ 文件；`rg` 只查已知平台合同符号和路径。没有打开任何模型
rollout、CQ private/review/public 的题目文本。读取中的两次探针因把不同 metadata 字段误按
list 类型输出而 TypeError，中止后按实际类型重新读取；未修改文件，不计为产品故障。

| 范围 | 当前独立结果 |
| --- | --- |
| 1 来源／checkpoint digest／保留 | bounded PASS（当前字节）：origin 指向 source 及确切 checkpoint，manifest 原始字节 SHA-256 为 `b3c41586e8f468f62754ae1a764a3f387d434de8b26456f8c84c57028c1e9260`，与 origin 一致；160 个包装 artifact 的 hash 全部匹配 manifest。源 run 终态仍 `TERMINAL_REPORT_COMPLETE`；不据此证明从保存至今所有时间点绝无改动 |
| 2 相同 Project／Ontology、新 Session、sole writer | PARTIAL：包装绑定 Project `8f9ccb1a-0a07-4246-a5cc-8a5a2f58efdf`、Ontology `ca3a04bd-b2ec-4455-98a1-23c574536934`；origin 的恢复准备 metadata 记录原 writer 已退出，旧 Session `ed9537a7-1ad5-453e-ba36-07f96f5009b6` 为 cancelled、lease released。尚待当前平台权威 readback／新 Session＋writer 锁证据，不能用继承身份映射冒充新 Session |
| 3 全链完成索引、防重复 | bounded PASS（索引／交接）：inspection 的 chain_runs 为 start2、start3，readback metadata 为 13 batches／1 session／2 pages；imports 有 221 个唯一 command key、11 个唯一平台 Batch，均 `apply_atomic`，11 个 completed_client_batches。Modeling／Protocol 的 forbidden_resubmissions 与 11 个完成 client batch 集合完全一致。真实平台逐 Batch applied/readback 及恢复后无重复写入仍 PARTIAL |
| 4 pending 新 dry-run | PARTIAL：恢复识别 3 项 pending_new_dry_run：一项原 dry-run 未到平台，另两项 validated 从未 apply；未将它们计作 completed。实际新 Session 重建、重新 dry-run、当前 Coordinator 翻译审阅尚待证据 |
| 5 candidate／conclusions／archive／unlock／批准保真 | REVISE：包装所含非 CQ artifact 在恢复目录当前均 byte-equal，含 candidate、最新 conclusions、unlock、approval 原件；imports 有 8 个有效最新批准、0 invalidated。但必需 conclusion archive 根本没进包，详见 High；忠实复制不完整包不能称可用恢复 PASS |
| 6 frozen CQ 连续性 | bounded PASS（字节）：source freeze、checkpoint host-private freeze、restored freeze 三者原始字节 hash 均 `3004b3d1d3814473341face50280b4b8f59b3187665bd2cbe31e73ed8621bfd5`；resume-prepared metadata `cq_freeze_restored=true`。尚待 16 public／8 hidden 的权威计数与冻结语义 digest metadata；不解析题目来补计数，不声称 CQ 质量 PASS |

### High H-R3-ARCHIVE-01 — checkpoint 没有捕获 conclusion 必需 revision 链

实证：

1. source `value-semantics/conclusions-archive/` 存在 28 个 revision 1—4 的原件；
2. checkpoint manifest 没有任何 `conclusions-archive/` 条目，package 的相应目录有 0 个原件；
3. start4c 相应恢复目录同样有 0 个；
4. source／package／restored 的 `analysis-conclusions.json` 均有 7 个 revision 5 conclusion，当前字节一致；
5. `staged_decisions.validate_analysis_conclusions` 明确将 revision > 1 且无 archive 判为
   `conclusions_revision_regression`；实际恢复首报同一 reason；
6. `runner.py` 的 checkpoint `add_staged_material` 收集 candidate、plan、当前 conclusions、
   unlock、approvals 等，没有枚举 `conclusions_archive_dir`。

归因：**平台 checkpoint 捕获依赖遗漏**；restore 忠实复制了不完整包，并非当前 Agent 自己
丢弃了 archive，也不能把该错误当作建模质量失败。R3.0-015 要求复用不变的有效业务批准及
阶段成果；此处恢复后必需历史校验无法通过。验收方已报告主 Agent，不修产品／真实 run，
也不往旧 checkpoint 追加原件。修复和安全恢复方案必须保留原包缺失这一事实。

### stale scenario-map review 的独立归因

source／package／restored 的 scenario-map 字节 hash 均为
`c761ee6ef1e13335b05af1636e2c4c7e6e85253e2d9f18bd4c57934efb28c13f`。
三处 `adjustments[1].review.after_refs[0]` 都指 `service-flow` revision 2；三处实际候选最高
revision 均为 service-flow 5、service-mappings 4、service-core 3、closure-governance 4。
`scenario_map.py` 对 after_refs 要求当前 revision，因此恢复前源状态已存在 stale review。
这不是恢复／Session rebase 改坏引用。需责任 Agent 按实际候选更新 review；允许它沿现有
可修正反馈继续。尚未独立核验其完成，不称修复成功，也不由宿主代替语义审阅。

### Round 1 补充 — 宿主 canonical retirement 与全链 readback 记录

追加只读核对 `workspaces/v4-acceptance-20261002/host-session-retirement-start3.json`
和 `start3-readonly-reconciliation.json`：旧 Session 在 2026-10-02T23:45:55.939165Z 经
canonical 操作由 active revision 1 转为 cancelled revision 2，HTTP 200；这是宿主生产的
实际操作记录，本验收没有执行该操作。与 origin 的 released lease／旧 writer 已退出记录
一致，仍不能证明尚未创建的新 Session 和当前唯一 writer。

全链记录有 221 完成项、11 completed Batch、3 pending dry-run、11 settled non-write，
blocked／scope_drift／recoverable_new_batch 均为 0；其 readback counters 为 13 batches、
2 pages、0 sessions（恢复 inspection 另记录 1 session，不能混为同一次读取）。完成项
序列化为 `CompletedOperation(...)` repr，使用 Python `ast.parse` 与 `literal_eval` 只解出
metadata，不执行字符串代码；221 个完整 key 集合与 start4c imports 完全相同，
content_hash／projection_digest／idempotency_key／client_batch_id／mode 均无差异，11 个
client→Batch 映射也完全相同。因而实际旧链 readback 结果到恢复完成索引的传递为
**bounded PASS**；本验收未独立重发平台读请求，恢复后新 Session 没有重复应用仍 PARTIAL。

## Round 2 — 人工补充 provenance 与冻结 CQ metadata

生产方于 `2026-10-02T23:57:28.798614Z` 进行
`verified-source-archive-supplement`，证据为 current run 下
`recovery/archive-supplement.json`；这是交付方操作，本验收没有参与复制、指导或正式
issue resolution。独立复核 source／current archive 均为 28 个文件，逐文件 SHA-256 全同，
当前 conclusions 与源仍为 `471185cb79834cfb597c0bfd37126af3cd1e0515e9de8cab421fbc4b1c1cc951`。
provenance 声明 `source_and_checkpoint_mutated=false`；本验收重新计算旧 manifest hash，仍
为上述 `b3c415...`，未把新增 archive 写回旧 checkpoint 或覆盖原始缺包证据。

在 `backend/` 使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run python`，直接调用只读
`staged_artifact_issues(current_root, unified=True)`，实际返回 **0 issues**。
同时调用 `validate_scenario_map(..., run_root=current_root)`，仍返回 **226 个 stale
reference issue**，首项仍为 `adjustments[1].review.after_refs[0].revision: stale`。
当次 current state 为 RUNNING。恢复 gate／业务图 review 是否完成仍待后续证据，不能以
staged 一类问题清零推导全部恢复可续写。High H-R3-ARCHIVE-01 的旧包缺失事实保留；
人工补充正确性为 bounded PASS，**自动完整恢复仍 REVISE**。

读取宿主专门生成的 `workspaces/v4-acceptance-20261002/cq-recovery-metadata.json`，只含
run/source_path、freeze_id、snapshot_digest、raw_sha256、public_count／hidden_count 与
字段映射，不含题面。source／current 都是：

- freeze_id：`cq-batch-0001`（源字段 `batch_id`）；
- snapshot_digest：`sha256:2ebd142138906f8ca9ec0088b1a640accab08e0b5d706da39bf7b9df7e419a3d`；
- public_count=16、hidden_count=8（抽取映射 `questions[].visibility`）；
- raw_sha256：`3004b3d1d3814473341face50280b4b8f59b3187665bd2cbe31e73ed8621bfd5`。

raw hash 与本验收此前独立二进制 hash、checkpoint manifest 三方一致；因此 scope 6 的
冻结连续性为 **bounded PASS（metadata／bytes）**。计数由获准宿主抽取，本验收未重读
questions 内容；没有裁决任何 CQ 的语义正确性、隐藏题内容或答案。

## Round 3 — 持久 archive 捕获修复的独立临时 fixture 复验

修复由另一责任方完成，验收方不修改 `runner.py`。新增独占测试
`modeling_team/tests/test_v4_independent_checkpoint_archive_acceptance.py`，复用既有中性
checkpoint Runner fixture，仅操作新的临时 run 与临时恢复目录，不启动模型或生产 run。
与开发方的 existing regression 不共享测试入口；结果来自本验收实际运行。

在 `backend/` 执行：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_v4_independent_checkpoint_archive_acceptance.py -q > /tmp/v4-independent-checkpoint-archive-round1.log 2>&1
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run ruff format ../modeling_team/tests/test_v4_independent_checkpoint_archive_acceptance.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run ruff check ../modeling_team/tests/test_v4_independent_checkpoint_archive_acceptance.py
```

实际 **2 passed in 0.58s**，日志 `/tmp/v4-independent-checkpoint-archive-round1.log`；Ruff
format／check 通过。定向独立验证已覆盖本次窄改，不重复交付方完整 suite，其开发回归不
计为本验收 PASS 依据。

| 独立分支 | 结果与边界 |
| --- | --- |
| 七个 r5＋28 个原 archive | bounded PASS：真实 collector 经真实 `_save_run_checkpoint` 包装 `materialization_progress`，manifest 精确列出 28 个 archive，owner=modeling、非 host-private、digest 与原件一致；实际 `restore_checkpoint_artifacts` 恢复全部原 bytes，`staged_artifact_issues` 完整检查返回空，无人工补充 |
| Modeling 角色可读 | bounded PASS：实际 `public_role_projection(manifest, "modeling")` 包含全部 28 个 archive 的路径／digest，符合当前 staged material 可见性合同；没有直接复制整份源 run 到角色 home，也不声称实际模型已经阅读 |
| symlink 排除 | bounded PASS：形似高 revision 的 archive symlink 没进 manifest、没出现在恢复目录，不能代替历史原件 |
| 没有原历史 | bounded PASS（准确拒绝）：七个 r5 但无 archive 的独立分支保存／恢复均未制造 archive；实际恢复 guard 准确返回七个 `conclusions_revision_regression`。不引入新硬门或假造前驱来让测试通过 |
| 源／包保留 | bounded PASS：恢复前后整个 fixture 源树完全相同、原 conclusions 与 28 个 archive bytes 完全相同。另只读重新核对真实旧 checkpoint：160 artifacts 的 hash 仍全匹配，manifest 仍 `b3c415...`，source 最新 conclusions 仍 `471185...`、source archive 仍 28 个；旧包未被本次代码或独立测试补写 |

限定结论：**当前代码的 staged archive 自动捕获与恢复有界功能 PASS**。H-R3-ARCHIVE-01
对未来新保存包的缺陷已在此范围独立验证修复；实际 start4c 基线没有热加载该改动，其
恢复仍依赖 Round 2 记录的人工补充，不能改写成自动完整恢复 PASS。旧包缺失事实、首报、
人工操作 provenance 和相应时间线全部保留。真实新 Session／sole writer／pending 新
dry-run／续写仍未由本轮证明，整个实际断点重启验收继续 PARTIAL。

## Round 4 — 真实新 Session、重新 dry-run 与安全续写

只读证据：宿主 canonical API 脱敏 readback
`workspaces/v4-acceptance-20261002/start4c-session-readback.json`、
`start4c-session-readback-round2.json`、`start4c-batch-session-readback-round4.json`；
最后一份 observed_at 为 **2026-10-03T00:17:43.886191Z**，不含题面、commands 或 RDF delta
内容。另对 current 的 staged-decisions proof metadata、intent／receipt、plan 的普通 command
身份、Coordinator translation approval 及链 writer 锁只读交叉核对。没有发 API 写请求或
参与平台重试、真实 issue resolution、模型指导。此轮没有新增代码／测试，只更新本文。

| 范围 | 本轮独立结论及实际证据 |
| --- | --- |
| 相同业务平台身份 | bounded PASS：新 Session `6837e6df-5532-4c1d-92fc-598764c1e046` 为 active revision 1，Project 仍 `8f9ccb1a-0a07-4246-a5cc-8a5a2f58efdf`，涉及 Ontology 仍 `ca3a04bd-b2ec-4455-98a1-23c574536934`；三个新 Batch 都绑定该 Session 和相同 Project／Ontology |
| sole writer／lease | bounded PASS（观测时）：round2 active_sessions 仅该新 Session；round4 lease 为 active revision 9、build_session_id 相同，expires_at `00:18:43.331440Z`，晚于读回时刻。只读 `.recovery-locks/r4009-20261003-solmedium-auth01-start3.lock` holder PID=3606037，root_run_id=start3；独立检查 `/proc/3606037` 存在。旧 start2 锁不是本次恢复 origin 所绑锁；不修改／重新获取 flock，不声称之后永久唯一 |
| 全链完成索引未重放 | bounded PASS（已观察提交）：旧完成索引继续为 221 command／11 Batch；新 Session 所有新增 intent 与原 completed_client_batch 集合、原 command digest 集合均零交集。进一步对普通 `command_kind＋payload` 作规范 JSON 比较，旧 221 已 apply projection 与新 129 command（128 关系＋1 cost）精确内容零交集，不仅靠换 client ID 判断防重复 |
| pending 新身份保真 | bounded PASS：source post-checkpoint 的两个 64-item pending 关系计划与 current 两个 r2 计划组成的规范 command 多重集完全相同，128 项全部唯一；历史 r1 的 Session 字段没有作为新授权复用。恢复的新 plan projection 绑定新 Session，Coordinator 对两个新 plan_ref／projection_digest 的 translation decision=approved |
| 新 dry-run | bounded PASS：flow1 `dff8d819-7008-40f0-8561-73a3eae343d8`（64）、flow2 `da493ca9-bc85-4bf4-ae28-bbab629e4414`（64）、cost `d99eb680-f004-4640-aa31-5f9338cfb70e`（1）均有真实 validated dry-run，全部 item validated，HTTP 200；不把 cost validated 当 applied |
| workspace 变化后重验 | bounded PASS：flow1 apply 的 after_version 为 `37f344...`；flow2 dry-v2／proof 27 的 before_version 和随后 apply before_version 都是该新 workspace，而非最初 dry-v1 的 `ed1f01...`。flow2 apply 后 `1d937f...`，cost dry-v2／proof29 又按此新 workspace validated，未拿旧 dry-run proof 写入 |
| 真实安全续写及回执 | bounded PASS：flow1、flow2 各有一个 `apply_atomic/applied` Attempt，全部各 64 item applied；平台 Batch 状态为 applied。两个 apply 均在 validated dry-run 之后、同新 Session 同 Batch、权威 content_hash 不变。平台 readback 到本地 proof／receipt 的 batch_id、attempt_id、mode/status、idempotency_key、content_hash、workspace_before_version、response_digest 逐项交叉一致，0 correlation errors；receipt26／28 分别对应实际两次 apply |
| 源与冻结连续性 | bounded PASS（当前字节）：旧 manifest 仍 `b3c415...`，160 个原 package artifact hash 无差异；source/current freeze raw hash 仍同 `3004b3...`，沿用 Round2 脱敏冻结 metadata。没有修改旧 run、旧包或 CQ |

上述比较只确认 command 身份和运行合同，未判断业务模型是否正确。没有读取 CQ private／
模型 rollout 或隐藏答案。live 已继续产生状态，结论以明确 readback 时刻及当次已读 intent
范围为界；不能推导未来所有计划、授权或写入永久正确。

**限定验收结果：从第三轮断点重新接续、重新挂接作用域、新 Session／writer、新 dry-run
及实际安全续写，已取得真实证据，bounded L0 runtime PASS。** 旧 checkpoint 的 archive
依赖缺失和 post-checkpoint pending-plan reference 均曾由生产方显式补充，旧包自动完整
恢复仍 REVISE；当前代码对未来 archive 捕获的独立功能 PASS 保持 Round3 的范围。真实
接续成功不覆盖旧失败，不替代 L1 模型质量、CQ 语义检索或最终 A10 验收。

## 尚待复验

实际 start4c 仍在运行，本专项已经获得有界 L0 接续证据；后续全部计划完成、语义质量、
CQ 语义检索、未知写入或新故障不在本轮结论内。旧包自动完整恢复缺口不会随本轮续写成功
消失；若有新的获准证据再按具体边界复验，不为当前专项扩展平台机制或另起运行。
