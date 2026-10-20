# Delivery阶段交接与只读重验窄修

用户在[耗时与成本复核](../modeling-retrospectives/2026-10-20-runtime-compare-cost-regression.md)
后授权“请修复已定位问题”。归属R4.3-030 F3、032共用Delivery工具／反馈及原优化03／07。
本次只修已定位合同，不新增生产、修模或独立语义调用；此前两组的模型、失败和验收证据保留。

## 修改与T0复核

- **已清理的启动失败阻断F3**：原守卫要求所有历史run都有完整请求账本。仅对状态读取成功、
  `CLEANED`、存在cleanup记录、semantic_start_count为0、无unknown／writing／applying，
  且账本错误为`artifact_unavailable`的旧run，取消账本存在性前置条件。原run、错误和
  原始观察仍保留；不伪造空账本、不删除历史、不重启生产，也不改变额度。
  在共享判断中返回具体run／code，现有`core.phase_thread_handoff`提供deferred与纠正动作。
  状态不可读、其他账本错误、coverage不完整、未决请求和不确定写入继续阻止切换。
  同一未变阻塞不新增唤醒。
- **旧handoff／已发布attempt重复启动**：沿现有冻结与cq-handoff-complete原件识别当前
  attempt；旧输入在启动前返回`evaluation_handoff_stale`及真实新绑定，不静默替换参数。
  当前所选组已发布报告返回可恢复`cq_handoff_immutable`、retry_of和原只读重验动作。
  仅这两个明确的启动前拒绝撤回本次新增owner，未知启动仍保留绑定。公开／隐藏组分别
  检查，内容相同的handoff副本按attempt识别，不因路径不同拒绝。
- **准确错误被精简视图过滤**：发布竞态仍可能由CLI拒绝；状态工具将已知不可变冲突投影为
  类型化error及next_action，沿既有模型侧状态送达。任意stderr及私有验收正文继续不展开。
  启动记录同时保留实际acceptance_attempt_id。
- **权威提示冲突与宿主监督**：Delivery技能区分初次production-handoff和重验attempt文件，
  使用真实新绑定。宿主技能删除F3“未实施”的旧说法，在原周期检查中核对实际switched及
  身份；已有资源风险时启动前做一次有界核对，仅按明确stop授权清理原owner／临时凭据。
  复用已有180秒异步等待，不新增监控、自动停团队或资源框架。

T0结论：账本与写入保护确实必要；已证语义开始前失败且已清理的run没有待消费账本，
强求其存在不能增加资源／写入完整性，却永久阻断另一run的上下文切换，应收窄该前置。
未知状态仍由原保护、原子application及独立验收覆盖。重验报告不可变性保留；把已发生的
CLI拒绝前移为准确、可恢复的参数反馈，不把它扩成run死亡或自动修模。

## 验证

先添加并运行回归，确认旧实现下两个production／acceptance场景被阻断、八种应延后场景
没有具体反馈；修复后相关56项通过。重验用例再复现两个无效启动未被提前识别、所选
attempt未记录、CLI错误在模型投影丢失；修复后包括副本与组别边界的相关用例通过。

直接相关回归：131 passed，18.21秒，范围为delivery_ops、delivery_session、phase_threads、
request_identity、token_reduction和tuning_regressions。随后仅重命名共用私有清理方法，
在下列全量回归中复核最终代码。

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run --no-sync pytest -q ../modeling_team/tests --tb=short
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run --no-sync ruff check ../modeling_team/delivery.py ../modeling_team/delivery_ops.py ../modeling_team/tests/test_delivery_phase_threads.py ../modeling_team/tests/test_delivery_ops.py ../modeling_team/tests/test_delivery_session.py
```

最终代码的Team全量结果：**3595 passed、12 skipped、318 subtests passed，585.26秒**；
无失败。359条warning来自既有rdflib弃用及多线程fork等提示，未在本窄修中扩展处理。
12项跳过不计为通过。Ruff检查通过；两份修改Skill的quick_validate通过，新增文档与
修改行的23处本地链接、证据JSON格式及git diff格式检查通过。
GitNexus上轮300秒超时，本次使用聚焦调用点检查：maybe_switch_phase_thread仅由原监督
循环执行；start_evaluation经原Host MCP调用；状态新增error沿原精简字段传递，预启动
拒绝清理复用原owner登记逻辑。不宣称图谱影响覆盖。

本次不修改backend／frontend或服务配置，不重启应用或已完成的建模会话。工程通过只能
证明本次合同修复；F3真实采用、净token／全任务10M目标、完全自主交付和重复性仍待获准
真实运行，整条030／032不关闭。此前Codex输出读取竞态修复f4d762b继续保留。
