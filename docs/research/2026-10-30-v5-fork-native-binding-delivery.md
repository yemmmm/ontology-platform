# v5 fork 后原生身份交接修复

日期：2026-10-30；起点 `5d798e2`。用户同意继续优先补 fork 后正确续建。归属 [R5.0-001 F10、R5.0-004 F2—F4、R5.0-007](../requirements/requirements-v5.0.md)；对应[前次检查点核查](2026-10-30-v5-checkpoint-fork-test-audit.md)中的增量引用风险。

本项采用独立 task_ref=`v5-fork-continuation-20261030`／稳定 3 CNY 账本；本项的源建立、fork、来源修订、故障与评价共用本账本，均不清账；之前任务的账本不重置或混用，默认 GLM Flash／low。公开两概念工程 fixture，非客户业务确认；最终五项标准在首次生产前冻结，生产不挂载验证题。无关工作区修改保留。

## 核查与最小路径

当前 governed read 的 id=IRI 不能作为原生执行 ID。fork 只导入语义／记忆，没有将确定性的资源身份交给新 run，既有无本地回执用例会拒绝新关系端点绑定。

当前 platform-data/v3 的资源 ID 存在 RDF `vocab/id` 显式字面量，资源 IRI 和这些 ID 在单图 fork 中保留；Project／Ontology／图等平台身份另按 fork 回执映射。不能假定所有 ID 都随项目变化，也不从 IRI 后缀猜原生 ID。

最小修复已在 Host 解析已验证的保存时资源 ID 声明，并按实际 fork 目标本体归属交给新 run 的现有 bindings；保留来源摘要及 fork 标识，不伪造新 run 的应用回执。只复制明确的类型和唯一 ID 字面量；不具有安全执行身份的普通 RDF 内容仍可复制／读取，后续不安全引用沿既有准确反馈处理。

不改变后端 capture／fork 合同，不另建恢复框架。原源归档、未知结果保留预分配目标／不盲重放、原预算、新上下文和独立验收保持。先证实失败再修复并做真实 fork 后更新原类／增加关系／换进程接续，相关检查与最终结论按实证追加。

GitNexus 对 SnapshotFork 返回 Target not found／UNKNOWN；当前源码中检查 SnapshotFork→HostBridge.fork_data→PlatformWorker 和 read_binding／compile_model_changes 调用点，测试及真实平台补证，不声称调用图覆盖。提交前 staged detect_changes 识别 13 个改动文件，但 changed_symbols／affected_processes 均为 0（工具风险 low）；v5 未被索引，不能据此宣称图谱影响完整。

## 开发与真实执行记录

- 红测：新增快照交接测试在目标 bindings 文件不存在处失败；Host 解析测试因没有 `resource_bindings` 失败。真实源模型治理读取的 `id=IRI`、无本地 bindings 的编译探针返回 `binding_identity_missing`，只读／编译探针未应用变更，不记成一次失败的真实 fork。
- 初次定向回归：17 passed。补充 copied 状态下中断再接续的参数化案例；最终检查见后续记录。
- 首次源 GLM 已在授权 20 分钟内实际开始，源模型 revision 1、两个 Class，原上下文已交接。
- 保存快照 `b85a805235e94b6987a4fcb0cac1d7d0`，平台摘要 `d26e1fe68d2e2aeb890573421bd40de3acb058fbfd85617951c4c7572e228a2f`。
- 实际 fork 源项目 `396a6166-7723-4a39-ba24-1b904252d91a`／本体 `6a9e4c4f-cff6-4091-b8cf-116f68f1733a` → 目标项目 `99ceda58-191d-4d39-914e-0e83b9bf21a7`／本体 `30155d24-e6ae-56b2-97e2-dad4b16d68df`。回执源已归档、新上下文、两个归属原件已导入；原两类 native ID／IRI 保留，新 run 的 Host bindings 已落盘。
- 目标在首次执行前显式激活完整 v2 来源包，新增编号含义及记录→设备关系。保留 v1 原包和 binding 版本，生产未挂载冻结题。
- 目标首轮执行期间排队 pause，待原生终态自然结束后使用新 CLI 进程 resume；该路径是已知终态接续检查，不宣称缺少原生终态时的未知恢复已验证。

证据根：`workspaces/v5-runs/fork-continuation-20261030-inputs/`；源／目标 run 位于同级 `fork-continuation-20261030-source`、`fork-continuation-20261030-target`。私有配置及运行原件均不入 git。

- 原生候选完成后自然暂停在 `activity=apply`，当时目标仍 revision 1、无应用回执。新 CLI 进程沿原 `model-00000` 候选执行唯一 `apply-00000`，Batch `f212457d-ef49-4154-9996-036758539b3d`／Attempt `840788ea-4b8d-4c55-bc75-9689472bf031`，目标 1→2。两次 update 复用原类，新增关系 native ID `577bfcb2-8b35-5592-afea-109c0b473dc0`，无重建类。
- 原生产 `self-check-00000-000` 自查 ready，随后新进程再次 resume 已完成 handoff：目标仍 revision 2、仍一个应用，原模型候选和自查结果文件摘要均未变化。真实源再捕获：原图 10 triples 同构不变、revision 1、status=archived；临时 capture 凭据撤销。
- 最终定向 18 passed，包含复制完成后在目标工作空间 setup 处中断的参数化恢复：pending 保留 copied 和身份原件，删除本地交接文件后可从 pending 重建，不重做平台 fork。完整回归 216 passed／1 条既有 Pydantic warning／189.78 秒，另行最终定向覆盖新增中断参数分支；Ruff check／format check 均通过。未修改应用后端／前端，无应用服务重启。
- 独立评价 `fork-continuation-five` 已启动，使用原生产前冻结五题和完整 v2 原材料，新隔离只读 GLM 上下文。Host 原件导出、实际 Host 读回与生产原生自查读取分别署名；独立结果后续已返回，见下节。此次四份必读工程原件合计约 169 KB，保留原始阶段及回执，不据此宣称降耗。

## 最终结果与保留边界

独立全新只读 GLM 对原五题在目标 revision 2 返回 **5/5 PASS**，实际治理读取两个 Class 及关系的真实端点，原模型／原始资料／冻结题均有本轮直接读取。`evaluations/fork-continuation-five/private-report.json` 为原件，Host 没有参与语义评分。报告第 4 题把跨进程阶段概述为 “at handoff”，该措辞不精确：owner_pid 的变化对应**候选终态后、apply 前**的两进程；另有 handoff 完成后的新进程 resume。按上述真实暂停状态、原候选摘要、唯一操作和实际版本认定本有界判据，不据报告措辞宣称验证过额外崩溃窗口。

最终数据快照 `06c3d80bfb6a4881b568748297c7161e`。目标已 stop／cleanup，`aggregate_keys_non_active=true`、`no_in_flight_attempts=true`，现有模型保留；源在 fork 前已 stop／cleanup，原封存回执及实际 archived、原图不变证据保留。源 3 次、目标 1 次 capture／fork 临时凭据均有 revoked=true。

收尾曾**多余地重复调用已封存源的 cleanup**，返回 `host_operation_failed`，私有日志定位为 `platform_scope.py:_ok` 的 `PlatformScopeError: admin key unavailable`，尚未发出撤销请求或新建凭据；原 cleanup 原件未被覆盖。已封存源的重复 cleanup 目前不具备完整幂等反馈，登记为后续窄缺口。本项不为该非阻塞反馈再扩建恢复流程，也不把这次重复调用记为成功；实际源封存依据为原回执，后续单独 capture 的临时凭据也确已撤销。

| 计量角色 | 输入 token | 输出 token | 其中缓存输入 | 已计价 CNY |
| --- | ---: | ---: | ---: | ---: |
| 建模（含原生产自查，4 段） | 290,015 | 7,564 | 217,920 | 0.10670940 |
| 独立验收（1 段） | 306,833 | 2,373 | 262,400 | 0.05917300 |
| 合计 | 596,848 | 9,937 | 480,320 | **0.16588240** |

稳定 3 元账本余额 **2.83411760 CNY**，5 个已知计量单元、无暂估、inflight=0、覆盖 complete；提供商最终账单未另行核对。缓存包含在输入中。外部 Host 单列 unknown，不扣任务金额；没有未申报的额外模型角色。原始 `budget-final.json`、`observed-usage-summary.json` 保留。

原生时间口径：首段 12:53:45.313 UTC，末段 13:07:01.881 UTC，窗口 796.57 秒；生产建模 134.07 秒、自查 108.47 秒、独立验收 122.26 秒，原生区间合计 364.80 秒。区间含工具和提供商等待，不是纯有效语义劳动；Host 准备／修复／测试／文档的有效劳动未独立计时，不补造比例。生产原生区间仅占窗口约 30.4%，加独立验收约 45.8%；据 AGENTS **停止进一步平台／harness 扩展**。本项完成后按更短通路验证持久提示冷启动和取证正反例，优先压缩已有重复原件与阶段交接，净降耗仍未验证。

本次交付只关闭**显式捕获原生身份的新 fork 复用已有类、增加关系及已知终态后换进程接续**的有界缺口。不回填已 ready 的历史 fork；不证明无唯一 ID 的任意外部 RDF 可安全写入；未实注原生终态丢失、COMMIT 回应未知、复制后部分认知记录导入中断，相关 T03.1 仍待验证。完整 v5 方法、无临时补充冷启动、客户盲测、L2 重复性及净降耗均保持未完成。
