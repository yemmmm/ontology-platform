# Delivery剩余输入与收尾关联优化

用户在串行三轮复盘后明确“请实现这些优化项”，对应三项：已知非决策事件降噪、
稳定历史改索引、程序收尾请求关联。归属R4.3-005／022／029及既有Host请求合同，
不扩大为压缩器、监控／编排框架或新建模。本次保持021暂缓、既有模型／effort不变。

## 实现与边界

- `_is_decision_event_noise`增加已实证的无错误MCP starting／ready及remoteControl
  disabled。先执行既有异常判断，错误、未知／失败状态、损坏／截断仍是决策事件；
  原始观察和事件保留。已有同等待状态不变、心跳／日志不唤醒的规则继续复用，不
  引入等待次数、超时或关闭异常反馈的新门。
- `_model_observation`沿已有changes判断Host请求／结果是否变化；稳定completed
  从重复的completed／requests／results正文移入`completed_index`，保留精确原packet
  引用。pending、blocked／unresolved与新结果继续送达。当前run状态、授权、待办、
  首阻塞及变化正文不裁剪，不新增差分同步状态或丢弃排队输入。
- 既有operation历史规则支持`work_state=completed,lifecycle=standby`，不等进程
  退出；合法报告／验证、无未决控制仍是条件。旧consult回复不再阻碍稳定历史收纳，
  新回复／绑定变化通过现有changed_operations先送达。失败读取、无效报告和未决
  控制保留当前输入；索引不是语义PASS、停止进程或删除原件。
- Delivery调用`standby_run`（包括finish_delivery）及`complete_cq_acceptance`未给
  request_id时自动补齐，提交结果返回原ID及既有get_request_result查询指引。
  同一原生call_identity与同一参数重投使用同一ID；无原生身份的直接调用使用新ID，
  显式ID不覆盖。finish_delivery沿原调用身份传给其内部standby，原Host提交／幂等
  账本和回执判据继续复用，不新增生命周期。submitted不等于consumed或standby。
- Delivery实际instructions、skill与[Host接口说明](../../reference/mcp.md#r43-029-deliveryhost-私有接单)
  同步，明确索引按需补读及使用返回ID核对真实消费，不例行重读整个账本。

只改`modeling_team/`及相关文档，未改backend/frontend或共享部署配置，不需应用
systemd重启。新Delivery进程加载；保留运行不热改、不停止，不追加semantic start。
GitNexus impact未找到相关Delivery方法，风险UNKNOWN；已用调用点核对
`record_observation→_model_observation→busy/idle dispatch→journal恢复`以及
`finish_delivery→standby_run→FIFO/请求账本/回执查询`，不声称图完整覆盖。
暂存detect_changes返回low、0符号／0流程；索引未覆盖本次Delivery符号，不能将0当作无影响证据。

## 测试记录

- RED：新增三类行为用例后，旧实现6 failed／91 deselected，分别为三种成功状态
  误唤醒、稳定Host结果重复输入、standby操作旧回复阻碍收纳、收尾request_id为空。
- GREEN：Delivery wakeups／decision_input／session／029 independent四文件，
  **129 passed**。覆盖异常仍唤醒、首次完成先送达、稳定历史精确读回、报告变坏重新
  送达、unknown控制保留、真实FIFO与请求账本关联、同原生调用重投不重复提交；
  原有授权变化／未知写入、分页、busy steer及恢复回归继续通过。
- Team全量：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest
  ../modeling_team/tests -q`，**3145 passed、12 skipped、318 subtests passed**，
  289.48秒，0 failed；359条依赖弃用／多线程fork警告与上次范围相同。
- Delivery skill quick_validate通过；Ruff与HEAD逐文件比较无新增诊断；diff格式检查通过。

## 保留记录的新旧格式对照

使用启动前基线`82cc819`与当前formatter，离线读取三轮原始session journal，共240个
保留decision packet。原方法从该提交AST提取；每个packet独立渲染至完整分页，相同
输入不改排队顺序。原件读前／后hash一致。脚本及仅数值结果位于
`workspaces/delivery-input-optimization-20261017/replay.py`、`replay-summary.json`。

| 轮次 | packet | 原输入字节 | 新输入字节 | 减少 | 原／新展示页 |
| --- | ---: | ---: | ---: | ---: | ---: |
| low | 70 | 1,318,743 | 1,060,715 | 19.57% | 81／78 |
| high | 91 | 1,837,658 | 1,445,746 | 21.33% | 104／100 |
| max | 79 | 1,737,610 | 1,446,603 | 16.75% | 96／88 |
| 合计 | 240 | 4,894,011 | 3,953,064 | 19.23% | 281／266 |

逐packet核对session、first_blockers、runs及changes完全一致，Host pending、unresolved、
limitations及history_complete一致；完整保留关键决策输入。各run原始事件另有32条
无错误MCP启动状态、9条remoteControl disabled可被新过滤器排除，共123条。事件可能
与必要决策同批到达，**123条不等于少123次唤醒**；上表仅比较历史收纳，不把事件
过滤潜在收益重复相加。字节／页减少不是token、压缩次数、费用或墙钟改善的实测。

## 当前结论

本次局部工程／保留记录机械对照通过；022本次采用纠正改为已实现待实测。原独立
工程验收与全业务语义验收边界保留，新Agent自主采用、同范围净token／压缩／效率
仍待后续获准运行，不因离线对照关闭整条022／029。没有新运行、平台写入或模型授权。
