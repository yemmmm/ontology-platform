# Delivery 消耗问题工程修复（102259）

授权：用户在分析后要求“请修复这些问题”。归属：R4.3-030 F1/F2、R4.3-022、R4.3-029；沿原优化项追加本次子问题，不新建通用编排机制或真实建模测试。

## 问题与修复

1. **补读与自动分页分离。** 已返回的冻结decision-view字节被自动再次推送。现只对同一输入身份、文件摘要及连续字节范围，在原生Codex turn/completed或DSH正常turn/end完成后确认接收；沿原delivery_input_dispatch持久回执推进。读取结果自身不代表原生接收或业务消费；失败／中断／unknown、未读间隙、JSON字段选择、改写的view及恢复前未确认的读取均不能跳过。
2. **正文重复及例行启动唤醒。** 新增run的事件仅在独立events变化处表达；已知成功的provider ready、thread started及目录／能力端点启动保留原件而不驱动额外决策，错误优先保留。未知事件与真正状态／授权／写入变化继续按原合同送达。
3. **等待身份、读取参数与旧状态纠错。** 对真实已保留的run/request误加Host或operation身份的调用，返回corrected_waiting_for供Agent显式重试，不自动改请求或扩权。Delivery实际角色提示要求检查后续accepted终态回执、整池完成条件、原continuation与字节上限，避免将已恢复历史错误报为当前平台故障。
4. **完成后旧页继续唤醒。** 当前待办中已完成、无可用动作的cq_acceptance_closure为收尾事实，不再阻止已有completed结果进入静止；未完成对象、未知写入、未决控制、Host待办、读取失败及必要异常仍保持唤醒。

T0复核：不移除授权、源忠实度、写入原子性或独立验收。分页确认是可观察接收事实，不能以“工具成功”制造consume/apply/语义PASS；没有新增次数或永久拒绝门。已完成closure无需再等待，不代表通过裁决。原错误引用拒绝属于真实权限边界，已由原角色自行纠正，不需要削弱权限守卫。

## 影响与验证

改动在modeling_team/delivery.py及实际Delivery角色包／Skill；调用路径为模型工具读取、原生poll完成回执、自动输入投递、恢复、阶段换线程及完成后的静止判断。底层Host公开工具和生产写入／语义裁决不变。GitNexus索引无法找到相关方法，本次采用具体调用点、diff和回归检查，不声称图谱影响覆盖。

测试先复现缺陷，再实施修复；新增专项17项覆盖连续接收、保留新状态、失败／未知／恢复、摘要变化／字段选择／未读间隙、事件去重与错误保留、已完成closure、精确等待纠正，以及两种原生完成事件的程序接线。原投影回归两项断言随单处events合同调整，继续检查原始事件／未决信息完整及噪声排除。

- 开发专项先有16 passed；随后补充Provider失败与正常完成同批到达的失败优先用例，先复现再修复，全部17个专项用例包含在最终增量回归中。
- 完整建模Team回归：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m pytest ../modeling_team -q --tb=short`，**3778 passed、12 skipped、318 subtests passed**，556.64秒。保留359条测试warning，进程退出码0。日志：`workspaces/delivery-consumption-repair-20261021/modeling-full.log`。
- 全量运行过程中最后补齐Provider失败优先分支；最终代码的受影响调用路径再跑专项、session、paged phase、phase threads及Codex/DSH runtime：**130 passed、2 skipped**，59.38秒。主体全量与最终增量的覆盖分开记录，不声称最后分支已被此前加载的全量覆盖。日志：`workspaces/delivery-consumption-repair-20261021/final-incremental.log`。
- Ruff：改动Python文件通过；`git diff --check`通过。
- Delivery Skill的`quick_validate.py`通过；相关文档本地链接检查通过；实际`r4-3-026-minimal-installation-chain` Task/Profile及`glm-flash-low`装载检查通过，未启动任何模型。

## 生效与保留边界

新建Delivery进程会加载新实现与实际角色提示；已保留的102259运行不热替换、不擅自恢复、不修改冻结原件或历史裁决。未修改backend/frontend，不需要应用服务重启。完整任务10M与自主交付原PARTIAL不变；本次没有新增金额、semantic start或收费模型调用，真实token节省与独立语义无退步仍待另获授权的有界运行。
