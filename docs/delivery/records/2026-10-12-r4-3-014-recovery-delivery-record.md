# R4.3-014 恢复覆盖核对与原 Attempt 接续交付

日期：2026-10-12。权威范围为 [R4.3-014](../../requirements/requirements-v4.3.md#r43-014-恢复前核对实际完成内容并只推进剩余工作)，
沿用 R3.0-015 检查点及平台已有原请求恢复合同。基线为 `bc9aaf1`；此前工作区的
R4.3-016 修改已由原会话提交，本次不接管该需求。

## 范围和决定

- 完成当前 unified/staged 恢复路径的工程缺口；不启动、恢复真实建模、Consumer/Judge
  或历史平台写入，不变更运行授权。工程检查、真实恢复行为及独立语义结论分别记录。
- 复用 `b8a8deb` 的 review-first 提示及现有 checkpoint/readback/intent/receipt。
  不自动判断历史计划与后继计划的业务等价，不删除 pending，不创建新的恢复或审批框架。
- T0：已有回执的硬拒绝保护终态不重放，但回执并不证明 Attempt 已应用。
  对 applying/recovering 的确切原请求，平台既有 `_resume_attempt` 已负责图观察、修订守卫、
  执行 claim 和原身份；保留不确定写入及终态重放边界，取消该情形的不可恢复拒绝。

## 已证实缺口和最小修正

1. 恢复包 `translation_review.note` 仍无条件要求重发计划和重新审阅，与已存在的
   review-first 指导冲突。改为先核对完成事实，只有真正剩余内容才重绑、新 dry-run 和审阅。
2. 当前计划将 batch/item/candidate/decision 绑定放在 `projection`，恢复映射仍读旧格式。
   读取当前字段并保留既有旧包支持；所有自身 batch 完成才将整计划标为完成。
   完成计划的完整引用与 basename 都受到已有不重放检查保护。
3. 完成索引枚举 `resource_outputs` 字典时误保留字段名。改为保留实际资源定位；
   已完成 item/Batch/Attempt/资源/Evidence 身份供 Host 与原生产角色核对，CQ 不接收新增明细。
   这些是平台写入事实，不是业务覆盖结论，也不替代必要受治理语义读取。
4. Runner 无条件拒绝 receipted key，阻断仍 recovering 的同 Attempt 恢复。
   既有 staged submit 入口允许 Runner-bound applying/recovering 的确切原请求接续；
   原请求从既有不可变平台结果 registry 取得，session/key/payload/version/lease 不变，
   原计划的正常批准及 dry-run 校验保持。返回必须保持 Batch/Attempt/content_hash，
   `created_batch`/`created_attempt` 均为 false，否则按 unknown 对账。
   原 intent 身份及旧 receipt 保留，恢复 receipt 追加；引用执行选择最新绑定回执。
   已完成、原件缺失、变化和未知写入不能据此重放或伪造完成。
5. 定向恢复被明确拒绝时，原不确定写入仍保留，而不被重标成“未写入 rejected”。
   同步工具说明、Protocol 实际加载指令及 staged 合同；不靠临时指导代替实现。

## 工程证据

- 本项测试先复现旧拒绝和恢复映射错误：原样 recovering 请求被拒绝为 already materialized，
  当前 projection 计划误报 unfinished、部分完成旧包误报 completed，资源索引误给字段名。
  本记录保留失败原因，未回填成 PASS。
- 新增 `test_r4314_recovery.py`：10 passed（7.17 秒），包含原生 AF_UNIX 工具请求、
  完成/部分完成、后继事实、原身份恢复、终态不重放、请求变化、缺原件、换 Attempt
  及恢复拒绝。原生 Runner、审批、dry-run 和回执是真实现；平台响应为受控 fixture，
  不声称实际 Agent 自主判断业务覆盖。
- 相关恢复/引用执行回归：94 passed（35.22 秒），未变输入结果复用；既有 RDFLib
  deprecation warnings 不作为新失败。新增/受影响独立检查另记。
- 完整 Team Round 1：2670 passed、11 skipped、316 subtests passed（235.46 秒），
  日志 `workspaces/r4-3-014-engineering-20261012/team-regression-round1.log`。
- 后端既有实际 ModelingBatchService + SQLite/RDF fixture 恢复测试：4 passed、
  59 deselected（0.66 秒）；`SEMANTIC_JEV_ENABLED=false uv run pytest
  tests/test_modeling_batches_service.py -q -k recovery`。本次未改后端代码。
- `checkpoint_recovery.py`、`capability_mcp.py`、新增测试 Ruff 通过，diff 格式通过。
  runner.py 的四项、旧恢复测试的 Mapping F821 均与 `bc9aaf1` 基线一致，未扩大旧代码清理。
- GitNexus 对恢复映射/包 LOW，对写尾核对 LOW，影响 `prepare_recovery_plan` 和验收接续；
  Runner 新入口未被索引，采用当前调用点、diff 和原生回归补足，不主张完整图覆盖。
- 未修改 backend/frontend、迁移或服务配置，因此不重启应用；当前改动适用于新加载
  Runner/角色提示的获准执行，不声称旧原生进程已自动升级。

## 独立 Round 1 FAIL 与 D01 窄修

- 独立测试者仅拥有测试文档和隔离探针；15 项独立探针 14 passed／1 failed，
  相邻原生/恢复/服务测试 21 passed。唯一 HIGH D01：原 Attempt recovering 时仅换 key
  可触达 forwarder，apply dispatches 1→2，新增第三个 submitted intent。
  即使完整 Team suite 通过，也不将独立工程结果改为 PASS。
- 原探针、首次 fixture 参数/forwarder 读回适配错误和最终失败日志分别保留，见独立记录。
  独立 native broker→实际 SQLite ModelingBatchService→RDF 恢复已验证一次 RDF 写入、
  一次修订推进、原 Batch/Attempt、不变旧回执及 fence 收尾；独立 207 批分页读回通过。
  这些是隔离工程证据，不是生产 Agent 的真实恢复行为或语义质量。
- 测试者停止写入后，主代理将 D01 纳入本项回归，先确认转发与新 intent 的失败现象；
  然后只在当前受影响 Ontology 的已知 applying/recovering 操作中查找原 intent。
  新 key 仍须匹配该操作的确切原请求，因而在新 intent/转发前拒绝；其它 Ontology
  的正常批准、dry-run/apply 可继续，没有全局永久拒绝或新业务等价裁判。
- 修后本项 12 passed（9.42 秒），含新 key 负向及不相关 Ontology 正向；Ruff/diff 通过。
  后续完整及独立结果见下方，不覆盖首轮失败。

## 最终工程验收

- 完整 Team Round 2：2672 passed、11 skipped、316 subtests passed（239.78 秒），
  `team-regression-round2.log` 保留。跳过项不计作 PASS，RDFLib 既有警告如实保留。
- 独立 Round 2 工程 PASS：原 15 项独立探针不改即通过（15.20 秒），D01 FIXED；
  2 项新独立 Ontology 推进探针通过（2.84 秒），必要相邻 23 passed（13.92 秒）。
  实际 SQLite/RDF 原身份恢复与历史回执保留再通过，未发现残余阻塞。
  测试者确认产品 SHA 无漂移并停止写入；原失败／fixture 修正历史保留。
- 收尾同步新 `staged_recovery_request_mismatch` 到 Python 和 JSON 错误码清单；
  仅清单增项，不改变已验收的执行分支。直接清单断言、JSON 格式、核心/新增 Ruff 及 diff
  检查 PASS；本项和既有 staged 合同收尾回归 50 passed（9.95 秒），见
  `catalog-final-tests.log`。完整 Team 结果复用未变执行分支，不因清单增项重复整套运行。
  独立测试者对两份目录及实际反馈另做静态复核 PASS，确认已验收执行分支 SHA 不变，
  在同一独立文档补记最终目录 SHA 后停止写入。
- 本次提交包含实现、测试、角色/工具合同、需求与 R4.3-014 台账状态。
  提交主题 `Reconcile completed work and resume original attempts`；本记录同次提交，
  `git log -1 -- docs/delivery/records/2026-10-12-r4-3-014-recovery-delivery-record.md`
  可取得最终不可变 hash。

## 验收边界

工程实现与独立功能验收 PASS。原运行、检查点和失败材料保持不变，未执行本次修复后的真实
Agent 恢复，也未进行独立业务语义验收或验证端到端提速；上述部分保持待证。
独立工程验收见 [测试记录](../tests/2026-10-12-r4-3-014-independent-test.md)。
