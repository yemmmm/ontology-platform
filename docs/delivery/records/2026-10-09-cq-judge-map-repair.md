# CQ Judge 场景地图引用窄修复

本记录属于 R4.0-009 / R4.0-023 的真实工业服务建模交付。授权仍为五次 fresh semantic starts，已消费一次；本次修复与只读验收不新增 semantic start。

## 第一阻塞与保留证据

生产 run 为 `r4009-20261009-delivery-glmflashhigh-start1`。`freeze-0002` 的批次 ID 为 `cq-batch-0002`，冻结摘要为 `sha256:b84cc871bc237f025d64f35c397910eb084770022bd3be778fa7c7185594aa53`。生产交接后模型只读。

`cq-acceptance-attempt-0002-hidden10-blind` 与 `cq-acceptance-attempt-0002-public17-nonblind` 均完成全部 Consumer 报告，分别为 10/10 与 17/17；均以 exit 1 退出，`acceptance-judge-setup` 报错 `collaboration_binding_changed: invalid scenario map`，有效 Judge verdict 为零。不能推导模型质量结论。

公开技术复现发现 12 处 `shared_terms[].candidate_refs[].revision: stale` 及一处 `candidate/item binding`。冻结场景地图、生产交接、两份失败批报告及读证据均原样保留，未向生产或修复者提供隐藏题文本、答案或判分依据。

第二个已发生的合同缺陷是隐藏操作在自己的报告尚未发布时误绑定同时发布的公开回归报告；该错误绑定保留为原操作证据，不回写成功。

## T0 与最小行为变更

Delivery 形成修复任务。陈旧协作引用不直接证明模型、冻结池或治理读结果漂移；用不可恢复的 Judge 设置失败阻断整批语义评审，超出了当前风险。交接文件内容摘要、模型状态变化检查、真实读取证据重放和题目覆盖合同继续保护验收绑定。

- 仅在模型绑定稳定时，把指定的共享术语候选引用过期/条目绑定错误降为结构化 `lifecycle_warnings`。
- 从 Judge 的工作副本省略这些无法验证的引用，并显式说明未知；不修改源地图，不据它们确认协作状态。
- 交接内容摘要变化、其他地图错误、身份冲突、缺失读取证据及模型漂移保持原合同。
- Delivery 报告扫描按当前操作 visibility 排除另一可见性报告。同一可见性的外部身份仍须校验；多个不能区分的候选仍不猜测归属。

变更只涉及 `modeling_team/__main__.py`、`modeling_team/delivery_ops.py` 及两处测试。backend/frontend 未变，无应用服务重启要求。验收 CLI 新进程读取新代码；已经存活的 Delivery 不应被声称自动加载新模块。

## 执行者与验证

内置 `start_repair` 两次返回可恢复的 `repair_isolation_unavailable`。宿主执行 Delivery 已形成的原任务，复用本轮已证明的 bwrap 隔离，实际 Claude Code `glm-5.3 / high`，独立 home，限定四个可写文件。隔离探针证明宿主 home、私有建模目录及管理员环境变量不可见；未替换为 Codex 修复者。这属于技术补位，不能记为 A13 Delivery 自主交付 PASS。

GitNexus impact 未找到 `_cq_collaboration_context`，风险为 UNKNOWN；使用聚焦调用点和 diff 检查，不主张图覆盖。

宿主在四个文件摘要不变期间运行：

```sh
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q
```

结果：2527 passed、11 skipped、304 subtests passed，176.99 秒。Ruff 与 `git diff --check` 通过。针对原始未修改地图执行只读设置复测，函数返回 13 条警告、无硬失败，源地图字节不变；未进行语义判分。

隔离开发环境存在未挂载的场景 fixture 与 Codex 可执行文件缺失；宿主完整套件结果用于验证当前最终 diff。旧失败报告不能改写成 PASS。新的独立 Consumer/Judge 实际结果、当前绑定和生命周期收口仍待 Delivery 完成。
