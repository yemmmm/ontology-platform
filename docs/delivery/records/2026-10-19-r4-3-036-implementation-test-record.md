# R4.3-036 实现与开发测试记录

- 授权：用户“请根据设计实现R4.3-036，并通过测试”。
- 权威范围：[需求](../../requirements/requirements-v4.3.md#r4-3-036)、
  [已独立审阅的设计](../designs/2026-10-19-r4-3-036-team-close-statistics-design.md)。
- 本轮为工程实现／开发验证，不是独立工程验收或真实 A9；不调用外部 Provider，
  不恢复建模／修模，不扣建模轮次或 semantic-start。
- 基线为当前 checkout，实施期间 HEAD 为 `dfc9efa`。保留 README、029／复盘／演示
  及需求文件其他条目的并行工作；Delivery 的缺参反馈修复及其测试也不属于本提交。

## 实现

1. `close_statistics.py` 是具体的 Host 数值采集／核算／发布辅助，复用 019／034 的
   `usage_report.py` cost units、归属、去重、累计、缓存／推理／压缩及价表合同。
   新 `activity` 来源与旧四类 numeric capture 分开，旧 scope／CLI 保持可读。
2. 启动前登记 process instance、来源和身份；实际原生会话绑定后才记录 native ID。
   失败实例、同 session 跨代次、未完成请求、无 usage 的失败 attempt 均保留。
   Node／Python 使用本机 kernel monotonic 时钟及 boot 绑定的 `clock_ref`。
3. DSH 共用 `tools/execute` 在 `next()` 的 `try/finally` 周围观察；不修改信号、权限、
   参数／结果、并发或重试。prepare 拒绝单列，根／嵌套按 callId／rootCallId 去重。
   Codex 在实际 Host handler／受控 MCP 服务端边界采集；无法观察的内部请求和原生
   工具保留 unknown。完整覆盖矩阵见[操作说明](../../../modeling_team/references/model-usage-report.md#team-close-statistics)。
4. Runner、独立 CQ owner、公开反馈及 Delivery 在原收尾分支发布；原 stop outcome
   和清理状态不改变。Delivery 先关闭 runtime、记录 `native_runtime_closed`、刷新
   provider，再发布 task 报告／ready 事件，早期 stopped 的统计仍 pending。
5. `get_run_status`、`get_request_result`、`get_evaluation_status` 及原 Delivery session／
   conversation 状态附只读引用；查询不重新生成报告。run 成员与 task 截至 cutoff 的
   其他成员分开，仍在线 Delivery 不计入 run 已退出成员。
6. 私有临时目录中完成来源副本、scope、JSON／Markdown 后原子发布；相同快照复用
   报告，迟到来源另发新版本并保留前版引用。数值写失败、队列满、flush 超时或报告
   失败只影响覆盖／可用性；资源未清与报告不可用分开，原 cleanup 异常原样保留。

数值采集与注册文件放在 `evidence/close-statistics-capture/`，不进入默认 run 进度
事件流；新 `host/activity` 通知只进数值采集，不复制进 DSH wire。曾以两项反例实际
复现旧落点会产生额外 progress／decision event，再改为私有子目录，避免统计触发
Delivery 决策或扩大默认上下文。原业务 wire、失败回执和语义证据不删除或过滤。

输出包括逐成员、角色／runtime／模型／effort 分组、四项时间、Team 活动并集、墙钟
与 basis、覆盖、已知 token 份额及分母、加权缓存率、根工具 Top 5、实际请求／attempt
计数、失败／取消／unfinished、压缩子集、明确暂停、退出状态及原件定位。无价表金额
unknown；生命周期减已观察活动只叫 other/uncovered，不推断为 idle／等待。

## 影响核对

初次 GitNexus 对 `cleanup`、`get_request_result`、`build_report` 返回 target not found／
UNKNOWN，因此定向核对实际调用方、原查询返回和 diff，未把 UNKNOWN 当零影响。
后续对 `ModelingReadProxy.handle` 返回 CRITICAL（2 个直接节点，93 条广义 process
关联、20 个 module），已向用户披露。可定位的直接调用是该类 `_serve`，
另一个直接图节点缺符号／路径；不能把该图输出当作完整、可靠的实际业务调用覆盖。
暂存后 `detect_changes(scope=staged)` 识别 26 个文件／23 个既有符号，返回 low、0 条
affected process；该结果不覆盖新符号及前述索引缺口，不用于取消前述风险提示。

实际变更是可选 recorder 包围原 handler，原 token／read key／scope 校验、锁、返回和
异常仍在 `_handle_request`；DSH 不再叠加 Codex 服务端观察，避免双计。原只读／授权、
运行时、生命周期、恢复、写入、代理及 CQ 合同由 Team 回归覆盖。无 backend／frontend
代码、共享应用配置、依赖或迁移变更，本次不需要应用服务重启或前后端套件。

## 开发验证

命令统一在 `backend/` 执行，清除宿主 `DEEPSEEK_API_KEY`：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_close_statistics.py -q
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_close_statistics.py \
  ../modeling_team/tests/test_dsh_runtime.py ../modeling_team/tests/test_dsh_delivery.py \
  ../modeling_team/tests/test_usage_capture.py \
  ../modeling_team/tests/test_delivery_token_reduction.py -q --tb=short
```

- 新增专项：**27 项全部通过**，包含在最终私有采集增量的 89 项回归中。
- 首次 Team 全量：**3381 passed、12 skipped、318 subtests passed**，约 521 秒。
  此后补全来源范围、失败分支及专项反例，最终全量结论待下项完成后同步。
- 后续全量：8 failed、3392 passed、12 skipped、318 subtests passed，约 521 秒。
  八项均为原公开反馈不允许 `--owner-root` 的同一兼容性断言；本实现为复用统计目录
  错用该参数。修正为公开反馈 `--statistics-root`，CQ 继续原 `--owner-root`，不更改
  旧断言或公开反馈的无 owner 生命周期。相关公开反馈／并行 CQ／Host／统计回归：
  **67 passed、1 skipped**，约 9 秒。
- 公开反馈参数修复后 Team 全量：**3400 passed、12 skipped、318 subtests passed**，
  约 518 秒；日志 `/tmp/r436-team-after-fix.log`。
- 随后收窄数值采集目录／wire 落点，两项反例先红后绿；最终差异仅涉及
  `close_statistics.py`、Codex／DSH／DSH Delivery 及新增专项。对这些差异与固定运行时、
  数值采集、Delivery 降噪执行最终增量回归：**89 passed**，约 104 秒；日志
  `/tmp/r436-private-capture-tests.log`。其余代码／测试输入摘要无漂移，复用前项全量
  结果；不把两个重叠测试集合相加，也不把末次增量说成又一次全量。
- Ruff 对本轮涉及 Python 文件与 HEAD 比较：历史 8 项，当前 8 项，**新增 0 项**。
  未扩修历史 lint；对整个 Team 的扫描另有既存诊断，不声称全仓 Ruff clean。
- 本地相对链接／显式锚点、围栏及 diff 格式检查通过（4 个文档范围、16 个相对链接）；
  冻结 scope 复算包含在专项中。综合结论为**开发工程 PASS**；不是独立工程或真实 A9。

| 验收 | 本轮工程证据／边界 |
| --- | --- |
| A1 | 实际 Runner prepare／cleanup cache、owner 提前完成子任务、Delivery pending→native closed→ready、原 run 状态／请求回执只读返回；固定 runtime 的原 lifecycle 回归 |
| A2 | 20 秒请求＋10 秒工具、重叠 5 秒得到 active 25；两个并行工具累计 20／并集 10；跨 Agent 累计与 Team 并集分列 |
| A3 | 固定 Harness 真 `tools/execute`／guard：短调用先结束，按序结果不污染计时；嵌套／副本只加根；原 DSH 各角色、取消及错误合同回归；Codex 可观察子集如实声明 |
| A4 | 无 usage 的失败请求与成功重试分开计时；logical request／attempt 分开；019／034 原用量副本、累计、压缩与末段测试继续执行 |
| A5 | 跨代次生命周期 30 秒、跨度 50／离线 20；同一任务在线 Delivery 独立为 cutoff 行；无原生身份的失败实例不合并成伪 session；明确暂停及原清理合同回归 |
| A6 | 缺起止、unfinished 下界、跨 clock、倒退、生命周期冲突与活动截断不补零；来源 byte locator、已知小计与 null 保留；Host／辅助缺口明确 |
| A7 | 采集失败仍原样返回 callback 结果／原异常，清理失败保留首异常并发布 incomplete；报告失败不发布半份 ready；已有 Messages 队列满／阻塞 collector、固定 DSH SIGKILL／恢复及末段回归 |
| A8 | 同快照重复关闭／查询、冻结 scope 离线复算、迟到新版与报告失败后前版链接；JSON／Markdown 同源，原报告不改，正文／参数／结果不进入新数值记录；旧 scope 兼容 |
| A9 | **未执行**。本轮没有真实外部模型任务、账单或全链统计对账；工程 fixture PASS 不等于真实覆盖、独立 L1、净降耗或费用结论 |

专项中的 Node 时钟探针实测 `Python before <= Node hrtime <= Python after`；固定 Harness
测试直接加载当前声明的 pinned build。其他 native 回归使用既有本地 Messages／Codex
fixture，不以机械或本地 runtime 结果推导真实语义质量。

## 发布与提交

实现说明见[Host 用量报告](../../../modeling_team/references/model-usage-report.md)。
需求 F1—F5／D1—D8／A1—A9 未缩减；Codex 不可观察路径及缺 Host 成本保持 unknown，
整体统计覆盖不预先提升为 complete。未热切／恢复任何历史 run，未覆盖语义报告或 digest。
只暂存本需求代码、专项测试、说明、036 状态及本记录；提交 hash 以实际 Git 结果为准。
