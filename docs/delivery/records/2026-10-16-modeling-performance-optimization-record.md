# 建模性能优化：读写合同、Consumer查询与Delivery衔接

用户先逐项确认整体调优第一、四、五项，要求追查第二项的skill来源；第三项解释后，
进一步要求“同意，开始优化。先将第四条落为需求”。第四项先登记为
[R4.3-028](../../requirements/requirements-v4.3.md#r4-3-028)，提交`c306c63`。
本轮其余改动沿R4.0-025、R4.3-009／010／005／022及现有生命周期合同实施。
模型继续GLM high；用户说明仅有low／high／max，low实测留待后续决定。
不启动真实建模或验收，不修改E组授权、模型、冻结、报告和原生事件。

## 最窄改动及边界

| 优化项 | 本轮实现 | 仍未证明的效果 |
| --- | --- | --- |
| 1 读工具合同 | Modeling／Consumer工具schema列出现行七种resource_types、hybrid／lexical枚举；删除专用rules读模型，省略类型不再注入已退役rule且包含概念定义；参数拒绝保留字段和合法枚举detail | 真实新Consumer首次成功率、外部查询耗时和净效率 |
| 2 切片编号查询 | 核对原生实际developer提示和加载路径，纠正实际v3提示与Examiner方法skill，明确scope.slice_ids是流程绑定，从题目业务用语查询并沿实际IRI补读 | 原Agent选择编号的内部因果仅部分定位；新线程实际采用与质量 |
| 3 重复读取／报告纠错 | 保留已有信息缺口／充分即答、必要分页、方向和限定核对，删除过期读取指导；正常完成优先省略可选failure_layer，报告schema已有结构化能力继续复用 | 不设置调用硬上限；原语义覆盖和减少重复读取须真实独立验证 |
| 4 写入结构（028） | 工具宣告固定六字段及现有action／resource_kind，字段名从既有compiler表生成；semantic_definition从既有权威参考生成；实际加载合同增加完整Class例子和关系引用模板。编译器对漏字段／错误层级给明确反馈，unsupported语义字段在生成批次前定位 | 其他操作仍由原compiler权威校验，不新增语义推理／表示／前向引用；首次正确率及总时间待实测 |
| 5 衔接与摘要 | readiness按当前绑定的Attempt proof区分applied与not_applied，保留历史legacy apply读取；Delivery实际指令与skill明确公开／隐藏完整分母、completed与standby、后续独立验收入口和连续执行已决定步骤 | 没有新自动编排器，没有取消声明的CQ阶段或自动做业务批准；完整自主交付和净时间收益未证明 |

第二项不是已经找到一条“必须拿slice_id作query”的错误指令：原实际提示未明确区分
流程标识与检索词，工具字段枚举不足且宣告旧rule，原Agent发生误用。明确发现的提示
错误是旧资源类型与默认；编号选择属于真实行为及合同表述缺口，不能伪造更强内部因果。
真正加载的是`agent-packages/v3-acceptance-batch/platform-examiner.md`，仅修改另一份
`platform-examiner/instructions-v3.md`不能证明实际路径生效，因此本轮直接修实际路径。

### 可修正反馈与超时

T0复核：字段／引用／授权和写入原子性仍保护真实不变量；但更完整的对外schema不应
将原本能由compiler定位的内层输入错误变成broker不透明认证拒绝。因此broker保持
原闭合请求信封校验，内层change仍进入原compiler获得not_written及具体路径反馈；
不加另一层永久硬门。schema主要让模型首次就看到正确结构，不替代compiler。

原桥接socket将连接和回传都限为5秒，而Host canonical forwarder本来等待至多30秒。
本轮保持连接5秒，回传允许35秒（包含Host原30秒及传输余量），不改变Host预算，
避免合法在途读取被较短外层截断。真实本地socket在5.1秒回复：修前稳定TimeoutError，
修后正常返回；它不证明平台查询本身变快，也不是外部服务或真实语义检索验收。

### 输入体积取舍

实际v3 Consumer指导由16454字节变为16047字节，主要是删除过期指导与澄清，不宣称
已大幅压缩上下文。写入工具schema增加了当前字段结构，紧凑JSON约9438字节、包含
81个跨操作字段名；它减少猜结构，但增加初始工具描述。字段列表沿既有compiler表
生成，操作组合仍由compiler验证；不维护另一份完整业务schema。净token／时间收益
必须在同模型／同题范围实测，不能由schema更完整或提示更短直接推导。

## 开发验证记录

- 新增5项合同回归先失败，修复后通过；之后补充完整例子编译、内层错误可恢复、
  unsupported语义字段前置定位及5秒截断的真实socket反例。
- 第一批聚焦：77 passed、23 subtests passed；扩大受影响模块：142 passed。
  最后compiler／新增合同聚焦：35 passed（含5.1秒socket回复）。不同轮次有重叠，不相加。
- readiness回归先复现validation_failed回执误入applied；修后包含隔离及未知写入测试
  的28项通过。对状态投影不增加写入门或自动裁决。
- Team全量首轮主动中断于588 passed、2 skipped、62 subtests passed，以补充上述
  socket和unsupported语义字段反例；该轮不是全量PASS。最终全量结果见后续追加。
- 两份修改Skill的quick_validate均通过；Python 3.11 compileall及git diff --check通过。
  文档／参考合同链接、JSON格式和实际工具schema例子另核对。

没有修改backend／frontend执行代码、迁移或共享服务配置，无需应用服务重启。
变更进入后续新Team／Consumer进程，旧进程的冻结提示不回写；当前工程验证不冒称
旧运行已采用、独立语义PASS、简单题20—30秒或全流程实用性能已达标。
已有独立语义裁决／失败保留，后续真实验证按原授权和完整分母另执行。

## 最终工程证据与检查范围

完整Team Round 2：**3072 passed、12 skipped、318 subtests passed，1 failed**，
耗时388.83秒。唯一失败为旧`test_active_consumer_operation_read_example_matches_actual_v3_schema`：
测试从热提示提取已移除的Operation专用示例，并保留“省略筛选排除Operation”的旧预期。
本次决策已明确默认包含全部现行合法类型。测试改为验证实际v3加载路径、显式Operation
查询和当前省略筛选行为，授权范围断言继续保留；没有降低业务判分或隐藏失败。

该测试及Consumer答案合同、新增输入／socket回归复测：**20 passed，5.91秒**。
修正后没有改变生产Python代码，其他未变输入复用Round 2结果；不是将两轮拼成一次
全量零失败，也不另外宣称3073项单次全量PASS。没有未处理的当前测试失败。
上述9项新增性能合同测试包含原E组参数／结构反例及真实本地socket，不含LLM调用。

两份Skill验证、Python 3.11.15编译及diff／JSON／链接检查通过。接口说明同步
`docs/reference/mcp.md`，028及相关读合同的验证边界已回写权威需求，优化台账保持
真实效果待证，没有新增未确认优化项。

GitNexus upstream对读参数校验报CRITICAL，修改前已告知；直接调用点为ScopedReadProxy
请求校验，readiness影响生产交接和状态摘要。detect_changes也已执行，但其返回仍含
不匹配当前diff的历史文件，不能作为当前完整影响证明；复用当前源码调用点、diff及
上述回归核对，没有为了文档／局部修复重建整个索引。
