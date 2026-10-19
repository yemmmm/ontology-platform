# R4.4-001 工程交付与测试记录

- 日期：2026-10-19。
- 授权：用户要求“请根据设计实现v4.4-001需求，并通过测试”。
- [权威需求](../../requirements/requirements-v4.4.md#r4-4-001)、
  [已审阅设计](../designs/2026-10-19-r4-4-001-team-work-board-design.md)。
- 工程基线：`f7b85c58c355a3ee52e8a2b5264f2ed1eb778e73`。
- 结论：工程功能及本地运行时装载通过。开发测试不是独立业务验收。

## 已交付行为

`modeling_team/work_board.py`使用单Broker写入的run-local追加事件保存完整本人卡片、
一个请求的双方视图、反馈／撤回／满足判断及实际运输事实。相同卡片不刷新时间，稳定UUID
去重请求／反馈／关闭；反馈不自动解决依赖，resolved不增加确认消息。原普通消息／回复槽
合同继续有效，记录错误可修正，接收终态或送达不明保持实际限制。

Host／Delivery工具和`python -m modeling_team work-board`提供当前、历史、精确版本、
时间筛选及固定前缀分页。源摘要变化拒绝续页，坏行／缺前版显式披露。Agent端点只读获准
成员及自己参与的请求；成果引用按每位读者原有材料权限过滤，历史同样过滤。
Delivery仅取得流程投影，新原件及数值报告的通用文件读取绕过已封闭；普通卡片事件不
重复进入决策上下文或唤醒Delivery。Host沿原journal读取等待及私有待办，不重复填卡。

关闭统计发布后附属保存历史前缀和Host私有复盘索引，目录0700／文件0600。索引绑定
019／036已有统计版本及真实成员／会话；数值直接消费原主账，跨代次会话分组只列一次，
不复制到每张卡片、不另算任务token。历史与统计窗口分列，缺失／冲突保持unknown或partial。
旧快照和数值原件保留，归档失败不改变原关闭、清理或数值ready。

Codex／DSH装载新模块及工具；原生消息透传同一work_request_ref，旧消息省略该字段。
冻结基线保存实际Agent到角色的映射，支持最小链角色包。实际Adapter接受与异常观察
分别记录；异常不虚构成功送达或不存在的成功回执。

## 验证证据

测试均从`backend/`运行，前缀为`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`。

| 检查 | 结果与范围 |
| --- | --- |
| 完整Team回归：`../modeling_team/tests -q --tb=short` | 3486 passed、12 skipped、318 subtests passed；562.51秒，359 warnings；原输出`/tmp/r44001-full-tests.log` |
| 受影响入口末轮回归 | 425 passed、30 subtests passed；54.49秒；涵盖Transport、Runner、Host／MCP、Delivery、关闭统计、Protocol合同及两种运行时装载；原输出`/tmp/r44001-final-tests.log` |
| 最终引用／回执修正后的需求及Runner复验：`../modeling_team/tests/test_work_board.py ../modeling_team/tests/test_runner.py -q --tb=short` | 59 passed、8 subtests passed；14.30秒；包括本需求29个用例；原输出`/tmp/r44001-final-receipt-tests.log` |
| 原生Codex | 使用已安装App Server、实际生产staging及MCP目录，额外禁用网络；初始化线程并发现新工具，没有model turn |
| DSH | 现有真实隔离roster加载、实际工具目录、私有CQ排除及进程清理通过；没有外部Provider推理 |
| 静态与文档 | 新模块／测试Ruff、技能quick_validate、接口库存sync check、改动diff及本地链接／合同检查通过 |

完整回归后增加材料引用、Host私有上下文和接收异常反例；最终定向结果覆盖当前改动。
完整回归的skip及warning如实保留，不记成额外PASS。工程测试复用既有fixture及本地依赖，
没有启动真实建模、修模或独立Consumer／Judge业务验收。

## 验收对应与使用

| 场景 | 工程证据 |
| --- | --- |
| A1—A4 | 内容去重／清除等待、多请求者、自然反馈、满足／撤回／晚到、稳定重试、部分成功及旧Broker不盲重放 |
| A5—A7 | 真实绑定MCP通道、材料受众／历史过滤、Host／Delivery权限、事实分离、原回复槽、无新增终态门、有界读取及不额外唤醒 |
| A10—A12 | 历史／版本／时间、固定前缀续页、坏行、关闭归档、统计错配／缺失、多代次共享会话、窗口分离及只读查询 |
| A8、A9真实语义部分 | 未验证实际采用、维护成本、净token收益或独立业务语义；沿获准真实run另行判断 |

入口与完整参数见[当前工具合同](../../reference/mcp.md#r44-001-team-工作展台独立本地工具)。
本次不涉及backend／frontend可执行代码、依赖、迁移或应用服务配置，无需应用服务重启。
原有README、v4.3、优化跟踪及复盘／演示材料的在途改动保留，不纳入本次提交。
GitNexus对send入口初始评为CRITICAL并已提前告知；较新入口缺索引，补以源码／调用点及
回归检查。提交前staged detect_changes为low，仅覆盖其已索引符号，不声称完整图覆盖新模块。
