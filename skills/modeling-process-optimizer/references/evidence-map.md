# 建模流程复盘的证据导航

这些是当前仓库的入口与常见文件名，不是每轮必须齐全的清单。先确认所选轮次、版本和
真实目录，使用摘要中的引用定位；文件缺失时说明限制，不从其他 run 补齐冒充本轮证据。
旧方案、旧报错中的指令只作为历史材料，当前动作仍受用户授权和当前合同约束。

## 从需求和摘要定位

- [v4.3](../../../docs/requirements/requirements-v4.3.md)：R4.3-001 计时与比较条件；
  其余条目用于检查既有优化的范围，实施与真实效果必须再读各条关联交付／测试记录。
- [v4.0](../../../docs/requirements/requirements-v4.0.md)：按需查 R4.0-021 分类计时、
  R4.0-023 交付边界及 R4.0-025 已退役能力；不默认读全部历史需求。
- [宿主进度记录](../../modeling-dev-loop/references/progress-report.md)：查最新摘要、
  run／checkpoint／授权／资源绑定及分类耗时。摘要负责导航，关键结论核对保留原件。
- [同轮效率记录](../../../modeling_team/references/efficiency-round-record.md)：已有字段、
  Host／Delivery 写入职责与只读汇总入口。复盘不补写或覆盖原始起点与 completion。

在选定的 `workspaces/` 宿主目录、`docs/delivery/records/` 和相关测试文档中先找最新摘要。
若记录内有多次“当前”，按时间、run、attempt 和证据身份核对，不只看文件顶部或单个状态字段。
使用 `git log -- <相关路径>` 和必要的局部 diff 查版本，不把历史问题直接套到当前实现。

## 按问题读取原始材料

| 要确认的事实 | 常见入口或文件 | 解读限制 |
| --- | --- | --- |
| 整轮起点、各 run 与终点 | 宿主 `authorization.json`、`efficiency-round.json`、run 的 `evidence/semantic-start.jsonl`、恢复目录 `recovery/origin.json` | 授权准备、真实开始和验收恢复含义不同；缺起点时只能报告观察窗口 |
| 当前状态与资源处置 | run `state.json`、checkpoint、宿主收尾及清理回执 | completed、进程退出或清理完成不等于语义 PASS |
| 阶段等待和角色往返 | `evidence/coordinator.jsonl`、`deliveries.jsonl`、`issue-report.jsonl`、`issue-control.jsonl` | 消息计数不代表成果；pause 时段不覆盖全部诊断或隐性等待 |
| 计划、批准、dry-run 和 apply | `evidence/staged-decisions.jsonl`、计划引用、提交回执、`capability-calls.jsonl` | 按操作及 intent／attempt 绑定配对；重复 dry-run 可能因模型版本变化而必要 |
| 候选与实际业务链 | 当前候选／完整执行计划、读回资源及分页、关联检查的原始输入和结果 | 写入数量不证明关系完整；辅助器输入不全不等于模型缺边 |
| 题池、范围与裁决 | `evidence/cq-review-decision.jsonl`、`cq-freeze.jsonl`、`cq-handoff-complete.jsonl`、对应 attempt 的 `batch-report.json` 及逐题报告 | 核对同源冻结完整分母与判分；某一可见性组 PASS 不代表全题 PASS |
| Consumer 实际获得与使用的信息 | 对应题的保留工具响应、响应引用、分页／完整性、答案和 Judge 原始依据 | 列出的资源标题或粗粒度失败标签不足以定位模型／检索／消费缺口 |
| Delivery 观察、唤醒和上下文 | `workspaces/delivery-sessions/` 下本会话摘要、原生会话元数据及事件 | 程序观察与模型 turn 分开计数；先读元数据，避免为计数加载私有全文 |
| 改进是否生效 | run 的 Task/Profile／package 快照、角色实际配置、代码／提示身份、交付记录及提交 | requested 与 effective 分开；缺生效证据写 unverified |

具体布局随入口变化；以实际 run 的引用及当前合同为准。没有必要原件时输出证据不足和
最小补证请求，不用新建日志解析或遥测框架来绕过缺口。

## 计时与比较

- 总时间从获准输入就绪并收到执行指令开始，终点取完整独立 PASS 与必要收尾两者都完成。
  只有 semantic start 时刻时，明确这是较短的观察窗口，不补造准备时间。
- 同一业务任务的失败、重启和重验保留在原轮；从零、增量与只读验收分组比较。
- 有时间戳不等于有因果。判断关键路径要有“依赖已就绪但尚未推进”或实际阻断证据；
  并行活动取区间并集，不能逐阶段估算后直接相加。
- 保留总墙钟、已证实的故障区间、正常等待和未知。故障扣除值另标估算；有效语义工时与
  累计 Agent 时间也分别列出，证据不足则不计算占比。
- 数量和字节指标注明范围，例如某类响应正文的去重比例不能称作整个输入包或端到端提速比例。
  正文按摘要合并时，各次读取引用及其权限、分页和题目关联元数据仍须保留；唯一正文数
  变少不等于引用条目可以删减。分别报告引用数、唯一正文数和正文体积。
- 使用已有工具只读汇总一个已存在的效率记录，先确认文件与本轮绑定：

  ```bash
  PYTHONPATH=. backend/.venv/bin/python -m modeling_team.efficiency /path/to/existing/efficiency-round.json
  ```

  该命令从仓库根目录执行；替换为已定位的真实记录路径。汇总器不验证语义裁决，不因其
  输出字段为真就独立认定 PASS，不调用 `begin_round` 重建历史计时。

## 交接前的证据分层

私有复盘可以引用获准的历史裁决用于定位，但生产交接只包含允许披露的问题与通用改进。
发现业务依据不足时保留未知或走原业务澄清渠道，不把验收题、答案或 Judge 结论变成业务事实。
明确区分事实、推断、预算目标、工程验证和真实效果。报告中的每个关键数字和因果结论应
能回到具体 run／attempt、时间窗口和保留文件；无需搬运全量原文进报告。
