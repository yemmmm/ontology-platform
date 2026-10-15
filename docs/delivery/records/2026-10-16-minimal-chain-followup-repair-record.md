# 最小安装链复盘后续窄修记录

用户授权“直接完成未完成事项”，承接
[2026-10-15复盘](../modeling-retrospectives/2026-10-15-minimal-chain-glm-high-retrospective.md)
中已定位的表示、自查、收尾反馈和协作纠错。归属R4.3-024／025／026及原CQ／Team
Transport合同；基线`6b7d6d9`。原README、演示材料目录不属本次，不纳入提交。

本次已完成工程修正及下述开发验证，不启动生产／验收Agent、不修改原模型或冻结题池。
原三轮额度耗尽、原L1 REVISE继续保留，新的语义效果须在获准运行后独立判断。

## 已实施范围

### 表示与自查

- 精简Skill／Coordinator说明和表示合同明确：当前`entity/create_entity`创建个体，
  无Class或通用标签不会将它变成概念；个体间普通关系断言是实例事实。语义层级由建模
  Agent依据来源选择，平台不自动裁决业务，不新增必须使用Class的硬门。
- 核对并说明025现有字段型定义入口：Class／relation_type创建使用`item_id=null`、
  `target_ref=null`和语义`fields`；没有选中候选item时`candidate_ref=null`合法。
  七类统一候选不新增Class种类，不把概念强塞为个体。Task、Runtime任务正文和角色交付
  要求接受完整不可变的语义变更请求，保持模型内容可定位。
- 字段型Class先创建，再以实际成功回执成员的`existing_resource_ref`建立关系类型；
  明确`definition_ref`选择当前候选item，不能冒用字段型`change_id`。既有编译器无改动，
  合同检查确认上述两阶段定义路径可保留定义／未知、源目标方向，不生成实例命令。
- 自查和Coordinator审核对照源读取实际资源类型、定义和断言，不能只核对名称、方向或
  关联扫描COMPLETE。业务材料、题面、评分与未知口径未变，未加入隐藏验收内容。

### 收尾与最窄T0处理

原问题是不同guard拒绝被统一误报为Protocol检索不足，且cq_semantic被旧联合清单拦住。

1. 旧清单对full_joint仍有实际完整性用途；cq_semantic已有自己的独立交接与判定，
   该清单不是它的业务前置，不能以流程偏好拦截生产收尾。
2. 当前普通等待可恢复，不应要求反复查询以满足无关条件。只删除cq_semantic的旧清单
   依赖，保留full_joint的缺失、损坏JSON和结构错误检查。
3. 活动issue、实际授权、写入排空／不确定结果对账、只读封口与独立语义验收继续保护
   对应不变量；本次不修改apply、资源生命周期或验收分母。
4. 已知guard拒绝沿现有RoutingError返回真实类型与可操作反馈：issue待结算、CQ交接
   未释放、Acceptance未结算、联合清单缺失／不可读／结构错误。Broker不再抹掉原因，
   Codex原生动态工具只透传固定白名单消息；普通布尔Protocol检索守卫仍按原合同处理。
5. 未知guard异常只给出安全的`terminal_guard_failed`，不反射内部异常内容，也不猜测
   是检索缺失。没有新增guard、重试上限、角色、状态机或控制平台。

影响调用链为Runner terminal guard→TeamTransportBroker.report→MCP或Codex原生动态工具。
两参数旧guard回调仍可用；已知拒绝由布尔结果改为现有RoutingError，不改变成功返回。
GitNexus本会话无可调用工具，影响以调用点、差异及回归为证，不宣称图谱覆盖。

### 原有协作路径采用纠正

- 冻结前可准备语义产物，但实际提交等待Host确认；`cq_freeze_pending`属于普通上游
  等待，本身不升级为业务澄清／运行故障issue。真实故障继续沿原恢复通道处理。
- Coordinator、Modeling、CQ和Delivery复制批准的slice_id原拼写；审阅时通过已有
  scope纠正通道解决不一致，不能自行替换连字符／下划线或预批尚未存在的地图。
- 材料引用仅在已发布接收通道有效。Coordinator材料不能直接作为Runner终态通道引用；
  使用获准终态引用或简短正文证据定位，保留原权限检查。

## 开发验证

- 新增收尾反例先在原代码复现：六项失败，分别暴露错误诊断、cq_semantic旧清单门和
  异常被误报检索；修正后通过，并补充full_joint不可解析／结构错误的准确反馈检查。
- 聚焦回归：在backend执行

  ```sh
  env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
    ../modeling_team/tests/test_terminal_report_diagnostics.py \
    ../modeling_team/tests/test_r4326_minimal_chain.py \
    ../modeling_team/tests/test_direct_modeling.py \
    ../modeling_team/tests/test_direct_modeling_wiring.py \
    ../modeling_team/tests/test_r30008b_runner_wiring.py \
    ../modeling_team/tests/test_r23005_c_settlement.py \
    ../modeling_team/tests/test_r30016_issue_control_diagnostics.py \
    ../modeling_team/tests/test_r3011_runner_wiring.py -q --tb=short
  ```

  **136 passed，21.16秒**。涵盖可恢复issue、当前CQ模式与full_joint差别、敏感异常不
  回显、原生工具可辨认原因、现有概念定义编译、精简配置挂载及CQ接线。没有模型调用。
- 两份变更Skill的`quick_validate.py`通过；新增收尾测试Ruff通过。
- Team全量回归：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest
  ../modeling_team/tests -q --tb=short`，首轮**3044 passed、12 skipped、318 subtests passed，
  1 failed，360.74秒**。唯一失败为`test_transport.py`仍把未知guard异常预期成旧Protocol
  检索文案；实际固定反馈已为`terminal_guard_failed`。原行为仍拒绝收尾且不落终态，没有
  写入安全回归。见[首轮完整日志](../../../workspaces/minimal-chain-followup-20261016/team-regression-round1.log)。
- 修正该旧断言，并补充检查异常类型及内部异常内容不回显；随后复测完整Transport模块及
  上述八个受影响模块：**168 passed、7 subtests passed，22.40秒**，见
  [复测日志](../../../workspaces/minimal-chain-followup-20261016/affected-regression-round2.log)。
  首轮全量后生产代码、任务与提示未变，仅纠正测试期望；复用其余3044项通过证据，不
  把两轮拼称一次全量零失败。当前没有未解决的回归失败。
- 当前Task／Profile配置loader校验、JSON／YAML、变更本地链接、Markdown围栏及
  diff空白检查通过。业务源SHA-256仍为
  `ac3d7f91620f292b2a3dcd64d218b4f8d482353b96f5be4c3955e1318a090566`，
  场景、私有题集、原模型和轮次账本均未变。

本次未修改backend／frontend代码或共享服务配置，不要求后端／前端套件或服务重启。
旧生产进程不热加载新角色／代码；下一获准入口须冻结新baseline和实际加载身份。

## 验收边界与下一步

原四题／同一业务范围的独立语义结果仍是三通过、一失败。本次工程通过不能撤销该裁决，
不能宣称提示已改善建模质量、流程自主完成或成本达标。原readonly模型和原件保留。

下一获准轮次核对语义层级、自查是否发现问题及完整四题独立结果，同时观察CQ等待／
收尾反馈是否改善。更大业务范围、Delivery上下文耗尽的输入因果、完整账单及净提速
继续待证，不为这些缺口新增启动前置框架。本次不新增建模额度。
