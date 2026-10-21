# CQ 准备顺序与审核转交改进

用户确认上一轮耗时分析并授权改进。归属 R4.3-030／022／029，沿既有优化项记录，
不新增角色、工具、平台守卫或建模授权。

## 依据与改动

同范围、Codex／glm-5.3-flash／low 的 102259 与 124810 两组，从真实启动至验收回交
分别为 15分07秒与19分36秒。其中 CQ 冻结前增加约3分33秒，约占新增时间79%。
全景审核通过至切片派发从31秒增至3分49秒；切片实际起草均约21秒。
切片稿至Host审核请求另增加约45秒，接单后的审核均约15秒。
保留原件与对照：[时间对照](../../../workspaces/minimal-chain-20261021-codex-glm-5cny-124810/timing-comparison.json)。
两组代码和角色行为不同，不把该对照当作控制变量实验或承诺可节省的时长。

- [Coordinator 权威指令](../../../modeling_team/agent-packages/coordinator/instructions.md)：
  完整初读和初次有界派单后，先完成有源依据的场景地图及拓扑；复用未变资料，
  避免重复全文补读。明确 CQ 切片依赖这些产物，不能反过来等待整池冻结才准备；
  普通审核等待或冻结前缺投影本身不构成 issue，不暂停可独立完成的准备。
- [Delivery 权威指令](../../../modeling_team/agent-packages/delivery/instructions.md)与
  [Delivery Skill](../../../modeling_team/skills/delivery/SKILL.md)：
  当前正式审核绑定齐备后，先提交私有 Host 请求，再做可选补读、进度说明或等待；
  即时用户／预算控制及未知写入对账仍优先。缺绑定仅补查相应元数据。
  等待切片时核对现有地图／拓扑依赖，确实缺失则沿原通道一次指导原 Coordinator，
  保留请求身份，不重复催办，不替其选择业务拓扑。

必读源仍须完整初读；有依据的业务决定、正式模型写入前的完整冻结、私有 CQ 隔离、
原子应用、治理读回、自查及独立语义验收保持原合同。业务资料不足仍保留未知或澄清。

## 检查及生效边界

仅修改角色／Skill 指令及交付说明，未改程序调用关系、HTTP／MCP 合同或平台代码；
本次不需要符号影响分析、应用服务重启或全量后端／前端回归。

- 在 backend 执行 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest`
  并选取 `test_contracts.py`、`test_prompt_cache_contract.py`、`test_delivery_host_actions.py`、
  `test_delivery_session.py`、`test_r3011_cq_lifecycle.py`、`test_r4007_multiview.py`：
  **129 passed，3 subtests passed，13.86秒**。覆盖配置／提示合同、原始必读约束、私有审核
  通道、整池完成后才可冻结及场景地图合同。这些检查不证明 Agent 实际遵循新顺序。
- Delivery Skill 的 `quick_validate.py`、最小链 Task／Profile 与 `glm-flash-low` 的
  CLI validate、改动 diff／链接检查通过；装载指向实际通用 Coordinator 与 Delivery 入口。

指令改进已完成，新建角色会话加载时生效；已保留的 124810 会话不热替换、不恢复或重开。
没有新增模型调用、semantic start、金额授权、模型修订或独立裁决。
真实采用、净 token／耗时改善仍待下一次另获授权运行验证，R4.3-030 完整任务10M
未达及整体部分验证结论保留。后续按同范围起止核对切片派发、审核请求、全链时间和
完整公开／隐藏验收，不把工作转移给其他角色当作净优化。
