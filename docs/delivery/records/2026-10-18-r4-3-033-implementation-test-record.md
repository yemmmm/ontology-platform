# R4.3-033 开发与测试记录

授权：2026-10-18“请根据设计完成R4.3-033需求的开发与测试”。
权威范围：[需求F1—F7／A1—A6](../../requirements/requirements-v4.3.md#r4-3-033)；
[已独立审阅的设计](../designs/2026-10-18-r4-3-033-dsh-acceptance-runtime-design.md)。
基线：`84a3aa9`，生产031和Delivery032已提交。本次不追加真实模型调用、semantic start、
修模或真实独立验收授权；本机测试使用假凭据及本地HTTP/SSE响应。

## 实施范围

- 显式 `runtime=codex|dsh` 贯通 Host、Delivery、CLI、正式CQ、公开早期反馈和当前只读
  验收接续。默认Codex；Delivery用独立 `evaluation_runtime`／`evaluation_model_profile`。
  新operation／报告核对runtime；旧报告缺字段只按Codex解释。同operation改runtime仍按
  原已占用合同拒绝；只读接续不能用旧Codex PASS冒称DSH已执行。
- 新增 `DshAcceptanceRuntime`，组合复用031的固定构建、SDK事件、namespace及实际进程
  控制；不启动生产roster，不依赖Codex app-server。每题Consumer／每Judge组独立进程、
  session及私有树；原v3首输入和无损响应传输提为共用小函数，Codex兼容导出保留。
- 复用原packet、ScopedReadProxy、ReportSinkServer和V3BatchReportContract，不改评分／
  全分母。Consumer不装答案和原业务资料，Judge无平台查询／写入／生产控制。实际工具
  名称与schema按原MCP清单全量比对，不装shell、编辑器、动态subagent或任意路径读工具。
- 新独立验收Profile为 `dsh-acceptance-deepseek-flash-low`，只声明platform-examiner／
  acceptance，精确provider/model/requested及effective effort；生产三角色Profile不能
  自动补验收绑定。DSH显式fast可定位拒绝，unset/default不继承Codex fast。
- 复用三题调度及后置顺序Judge分组；公开早期反馈同样逐题隔离，本地p0按所属题的
  回执解析。DSH保持007体积分组，但不套Codex特有原生turn输入上限。
- 原owner以实际session／进程代次操作DSH；暂停控制当前及保留成员和后代，晚绑定在
  首prompt前受控，继续保留身份。报告后关闭原sink、Consumer保留只读咨询，原报告不变。
- 格式错误在同session修正。报告接纳与关闭共享资源锁；报告、queued/claimed、活动结束、
  会话保留及进程退出分别取证，部分报告不因技术未完成丢失。记录原生事件／用量原件，
  缺值unknown。收尾仅清本次进程／shim／socket／代理凭据，原生历史、失败及部分证据保留。
  进程失效不自动重放未知请求；当前只读接续继续使用独立新attempt，不重新启动生产。

## 验证记录

**开发测试PASS**。完整Team回归：**3224 passed、12 skipped、318 subtests passed**，
454.36s；pytest报告359条warning（包含当前Python 3.14环境的多线程fork弃用提示），无失败。
命令为 `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`。
最终差异专项补测：**320 passed in 59.51s**。两者有重叠，不相加统计；工程检查不构成
真实L0／独立语义L1。完整回归及专项原始输出分别在本机
`/tmp/r4-3-033-modeling-tests.log`、`/tmp/r4-3-033-final-focused-tests.log`。

- 首轮原CQ并发、部分Judge、Delivery operation及DSH事件回归：87 passed。
- 本机固定Harness提交 `687f282e8625c6b8d11ff58211a90524be2e4317`，真实bwrap、Node、
  MCP和Unix socket；外部模型由本地Messages/SSE测试服务替代，真实凭据读取被测试替换。
- 专项涵盖实际角色装载及拒绝多余工具、namespace内仓库／宿主HOME／真key不可见、
  实际治理代理请求与回执、错误报告同session纠正、Judge冻结原文回执、独立组身份、
  部分报告留存、活跃与晚绑定暂停／继续、保留追问、Host绑定及旧Codex报告兼容。
- 载体fixture覆盖五题完整分母和单题无报告，及公开早期反馈无Judge。fixture使用原确定性
  评分和模型／响应重验合同，不能据此推导真实模型回答质量。
- GitNexus impact未找到新入口；detect_changes返回旧索引与不完整符号，未作为图影响覆盖。
  使用定向调用点检查：Host schema → operation argv／请求 → CLI → Consumer／Judge →
  owner／proxy／sink／teardown。涉及正式CQ、公开反馈及只读验收接续；平台写入路径不变。

### 最终差异补测与静态检查

最终差异补测命令（在 `backend/` 执行）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_dsh_acceptance.py \
  ../modeling_team/tests/test_dsh_acceptance_routing.py \
  ../modeling_team/tests/test_r4327_parallel_cq.py \
  ../modeling_team/tests/test_r3011_acceptance_runtime.py \
  ../modeling_team/tests/test_r3012_partial_judging.py \
  ../modeling_team/tests/test_r3012_platform_responses.py \
  ../modeling_team/tests/test_v43_judge_references.py \
  ../modeling_team/tests/test_r4313_acceptance_refs.py \
  ../modeling_team/tests/test_r4015_public_feedback.py \
  ../modeling_team/tests/test_r30015_acceptance.py \
  ../modeling_team/tests/test_host_ops_s2.py \
  ../modeling_team/tests/test_host_ops_mcp.py \
  ../modeling_team/tests/test_delivery_session.py -q
uv run python ../scripts/sync-interface-docs.py --check
```

该补测覆盖全量回归启动后的公开反馈逐题隔离、只读接续runtime匹配、报告接纳记录顺序、
启动失败资源归属及新增负例；旧输入不变的验证复用，不重复全量。
`ruff check`覆盖本次全部修改及新增Python文件，`ruff format --check`覆盖新增模块与测试；
均通过。`git diff --check`及README／MCP／本记录的本地链接检查通过；接口文档同步检查通过。
语义建模与真实语义验收有效时间均为0；本地测试耗时见pytest终态，实现／文档未独立计时，
不推导净效率。

## 分阶段结论与保留边界

工程实现与开发测试PASS，本地真实进程／SDK／MCP装载及控制有确定性证据。真实provider绑定／L0、对031产出模型的独立
DSH Consumer／Judge最小链L1、更大业务、L2、034整任务用量／净效率均未执行、未验证；
未宣称独立工程验收或独立语义PASS。既有独立设计PASS仅是设计结论。

代码只在modeling_team及相关文档／配置，未改backend/frontend或本地应用启动配置；不
重启ontology-platform.service。工作区原有README、其他需求条目、复盘及演示变更保留，
提交只包括本需求文件及requirements-v4.3的033状态增量。
