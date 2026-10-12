# R4.3-015 实现与验证记录

- 权威范围：[R4.3-015](../../requirements/requirements-v4.3.md#r43-015-分阶段建模反馈与成功写入信任边界)。
- 复用[已独立审阅的设计](../designs/2026-10-12-r4-3-015-staged-feedback-write-trust-design.md)，D1—D8 无新增业务取舍。
- 本轮用户授权：实现 v4.3-015 并通过测试；基线 `a26261a`，开始时工作树干净。
- 状态：工程实现／开发全量回归 PASS；独立功能验收 Round 1／2 PASS。真实效果未验证。
- 未启动／恢复生产建模、修复或业务验收，不消耗 semantic starts；真实语义效果及提速待证。

## 实现与保留边界

1. Runner 正常 applied／already_applied 单项及顶层 resource_readback_status 为 not_evaluated；
   原应用／Attempt／版本证明保留，成功下一步是依真实依赖继续、择有价值节点公开反馈、
   整轮完成全局与关联检查。dry_run 保持 validated／not_applied，语义结论仍 not_evaluated。
2. Delivery 既有正文工具加入绑定 run 的 early-feedback 目录；反馈及平台响应返回真实原文
   和 content_digest，保留原路径／普通文件／大小限制。报告业务资格仍需原 operation 的
   有效 report_binding 及 digest 对照，不把可读旧文件或状态摘要当成当前反馈。
3. 工具说明、四个活跃角色、Modeling 方法、Host runbook 和当前 Task 对齐分阶段范围、
   成功信任、反馈窗口、只暂停真实依赖及应用／质量分账。窗口沿现有 guidance／Team
   消息暂停新提交，准备可继续；原 operation 结束后解除正常等待，未知写入／用户暂停
   保留。没有新增平台写门、锁、调度器、快照或恢复机制。
4. 保留原审批、精确 projection、有效 dry-run、Batch／Attempt 身份及终态、版本确认、
   幂等性、不确定写入恢复、实际治理分页／共享目标／最终关联检查和完整只读独立验收。
   旧 formal ticket／ordinary retrieval 交接合同未取消，历史运行证据不回写。

## 验证轮次

- 开发 Round 1：定向回归旧成功状态触发 2 failed、43 passed；证明新增状态断言能捕获原缺口。
- 开发 Round 2：实现后 1 failed、44 passed；新增断言遗漏 fixture 中保留的
  submit_modeling_batch 原回执，修正为允许该回执及 get_modeling_context 版本读取，仍禁止
  资源／关系扫描。产品实现无额外修改。
- 开发 Round 3：当前定向回归 45 passed（35.36 秒）。
- 全量 Round 1：2676 passed、11 skipped、316 subtests passed，2 failed（242.13 秒）。
  一项是全量开始时已收集的旧回执断言（Round 3 已复测通过）；另一项为 transport 的旧
  提示合同强制每次 apply 后核对全部 SPO，与 R4.3-015 冲突。仅更新该断言为“正常成功
  无逐条核验，业务读取／必要恢复仍完整分页”，保留 missing／extra／delete／binding、
  unknown write、重复 SPO 的计数和不重放反例。产品代码／指令未再次改变。
- 修正后完整 transport＋production_refs 定向回归：58 passed、7 subtests passed（40.04 秒）。
- 全量 Round 2 PASS：2694 passed、11 skipped、316 subtests passed（242.18 秒），覆盖
  最终新增 16 项独立用例；356 条 rdflib 既有弃用警告，无失败。命令在 backend/ 执行：
  `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`。
  产品代码／指令与已验证范围一致；没有 STILL FAILING／REGRESSION／BLOCKED。
- 独立功能验收 Round 1／2 PASS：131 passed、1 deselected（live Oxigraph）、最终验收
  相邻回归 11 passed、新独立用例最终 16 passed、更新提示合同独立复测 1 passed；
  无产品缺陷。它们不是主 Agent 自测或真实业务结论。独立测试见[独立功能记录](../tests/2026-10-12-r4-3-015-independent-test.md)。
- ontology-modeling skill validator 通过；79 个本地链接、围栏／空白和 git diff --check
  通过；R4.3-016 正文与原 HEAD 一致。

## 影响与证据边界

实际调用点：Runner 在初始化 Acceptance carrier 时注册原 handler，capability 输入／授权
合同保持；Delivery 正文仍由 read_delivery_artifact 调用原 reader。全仓搜索未发现生产代码
使用 resource_readback_status 打开交接门。GitNexus impact 未找到上述两个当前符号，返回
UNKNOWN；detect_changes 只定位 RunnerCapabilityEndpoint 类，risk low，不能据此声称完整
图覆盖。本次以实际调用点、diff 和 Team 回归验证影响。

只修改 Team／指令／测试及文档，未改 backend、frontend 或共享运行配置；按设计不重启
平台。fixture、独立功能及指令合同通过不证明实际 Agent 按约定暂停提交、反馈修模成功、
真实模型质量或性能提升。V6 须在新的获准运行验证，保留现有暂停及额度边界。
