# 专职建模团队真实合同缺陷修复

日期：2026-11-04。依据：[本轮复盘](../../research/2026-11-04-demo-role-high-retrospective.md)、
[R5.0-012](../../requirements/requirements-v5.0.md#r5-0-012)、公开 CQ 衔接沿
[R5.0-010](../../requirements/requirements-v5.0.md#r5-0-010)，金额投影沿
[R4.4-002](../../requirements/requirements-v4.4.md#r4-4-002)。用户在复盘后明确要求“请修复上述问题”。
本次授权用于工程修复、必要验证和提示/Host 指导同步，不启动新付费建模，不恢复已清理 scope。

**状态：工程修复及适用开发/回归验证通过；修后真实建模与独立语义验收未执行。**

## 实施与边界

| 原失败 | 最小修复 | 保留的约束 |
| --- | --- | --- |
| 成功读取被 JSON 字符串/对象比较误判 | 删除原始参数的重复比较，按服务端成功回执的确切引用及字符区间判断；顶层 MCP isError 回执不计读取 | object_id/revision/digest、成功状态、完整分页正文；失败/部分/错摘要仍拒绝 |
| 既有 cq-public 分派被当作保留名称冲突 | 允许原角色/原父级复用 CQ 身份；已按新范围更新的 CQ 不二次增加 generation | 跨角色/owner 冒用、计划内重复 ID、源范围和依赖约束 |
| 完整 scope-plan 以 waiting_children 返回却未安装 | 完整显式计划先按原基线/来源/owner 规则接纳并安装，再等待子级 | waiting_input 不变；不是只见等待文字就认为阶段完成 |
| basis 错误缺具体纠正依据 | 错误包含 field/expected/received/instruction；source_read_missing 说明本回合读取义务 | 精确基线不被新产物替换，null 原值保持，真实读取不能由旧摘要冒充 |
| 技术拒绝后重做业务正文 | 将本角色未接纳的原生结果保存为既有 team material，下一回合得到精确引用作局部纠错；成功后清除该纠错指针 | 原输出只读保留；拒绝内容不成为有效候选/已接纳产物；不热迁原生线程 |
| 普通公开 seed 被强按项目 snapshot 解析 | seed/v1、design-v1 与完整 snapshot 分别读取；seed external_id 保持为 CQ 身份且仅 draft；prepare/source-revise 及生产校验共用同一解释入口 | 快照摘要/公开性/稳定身份、真实确认来源；seed 附答案不构成确认 |
| 已结算捕获记录导致 unknown 尾差 | 尾差后备分支排除已由原生用量覆盖的 capture attempt | 未被覆盖/未计量仍 unknown；金额、原始用量、授权、结算与自然控制算法不改 |
| 提示/Host 指导使返工扩大 | 三专业包明确输入 basis 与新成果、proposed→安装→等待、当回合来源读取与旧分析复用；CQ 按原文条件/例外检查覆盖；Host 明确原件诊断、必要窄修、预算准备与收口责任 | 不加 demo 答案、题数配额、评分放行、新角色/记忆/恢复框架 |

先前复盘把尾差主要解释为“completed 未排除”；修复进一步核对后选择更窄且安全的条件：
原始捕获记录已由 native_coverage 覆盖才排除。单凭 completed 不能证明用量已知，不能将真正
待结算消耗估价为零。复制旧账本离线重算可验证该差别，原账本缓存/事件不回写。

## 开发与工程验证

使用原 v5 锁定环境、实际 PostgreSQL/checkpoint 临时 schema；执行角色和平台应用为既有
确定性夹具，无付费推理、真实业务模型写入或应用服务重启。新测试使用实际 Demo 九题 seed
与真实 MCP 的字符串参数/对象回执形状；材料原件另做离线重放，不改输入字段制造通过。

1. **修前反例：10 failed、6 passed、9 deselected，27.61s。** 复现读取误判、单/双槽 CQ
   身份冲突、四类无效 seed 未早报、基线反馈不足、计划等待未安装和已知用量尾差误报。
2. **第一轮修后：13 passed、1 failed，51.83s。** 新负例发现成功读取提取器忽略顶层
   MCP isError；原参数比较曾掩盖这一边界。已在成功读取入口补齐，非放宽消费校验。
3. **拒绝正文复用反例：1 failed，3.76s。** 原角色纠错输入没有上一未接纳提案；补既有
   固定材料引用后可读取原内容、纠正基线并接续，成功清除拒绝指针，保留原输出。
4. **主修复定向：31 passed，69.93s，0 skip。** 包含旧 budget 文件及新增真实合同反例；
   单/双槽均完成 scope 安装→Modeler propose→整合→夹具 application→原责任检查→handoff，
   重复 advance 不重放；错误 owner/重复分派、部分读取、错误摘要、MCP 失败、seed 自行确认、
   私有/坏格式/重复身份/损坏 snapshot 和无真实用量仍被拒绝或保持 unknown。
5. **共享预算回归：131 passed，2.34s，0 skip。** 在 backend 环境运行 task_budget、prices、
   usage_capture、usage_report、dsh_usage_report 五个文件；未改后端应用代码。
6. **完整 v5 回归：406 passed、1 failed、1 条既有 warning，799.71s，0 skip。**
   71 个冻结输入执行前后 SHA 相同。唯一失败是原 RoleActors 的双并发完整链：CQ 在首次
   apply 后到达时，夹具仍在 revision 1 再次发同一个 create-one，正确触发
   contribution_already_applied。单项独立复测 1 passed/23.40s 说明原用例受时序影响，
   不是可以忽略的通过证据。新增固定时序（CQ 直到首次 apply 后才返回）准确重现同错误：
   1 failed/22.85s。已有独立 scheduler_case 包装器早已对同一个未变来源返回 no_change；
   基础 RoleActors 缺该分支，现同步其既有语义：有实际 revision 后不重建同一固定含义。
   防重复应用守卫和生产代码保持。随后两个角色模块及全部独立角色文件 **77 passed，446.44s**（0 skip）。
7. **最终兼容性收窄与回归。** 避免显式 CQ 分派 double generation 的初版条件还会跳过
   递归切片的新全景复核；固定反例准确失败 **1 failed/3.94s**。条件收窄为只跳过已经
   显式分派到该 scope 的重复更新，隐式/递归计划保持原有 CQ 刷新。最终三角色测试文件复核 **78 passed，481.57s（8分1秒），0 skip**；71 个最终冻结输入执行前后 SHA 一致。
   本轮覆盖原双并发失败、固定迟到 CQ、递归全景刷新、原责任读回、源变化/局部重入、
   格式修正、真实加载/权限和已有未知执行/应用对账。没有未解决的相关工程测试失败。

定向命令：

```bash
env -u DEEPSEEK_API_KEY UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 pytest -c modeling_team/v5/pyproject.toml \
  modeling_team/v5/tests/test_role_team_live_contracts.py modeling_team/v5/tests/test_budget.py \
  --tb=short -q
```

预算五文件在 backend 下以 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ...` 执行。
完整 v5 使用相同环境/配置，范围为 `modeling_team/v5/tests`，没有过滤器。

## 原件离线复测

`workspaces/v5-runs/demo-role-high-20261104-repair/original-evidence-replay.json`：

- 直接向修后读取校验提交原 role-00004 事件与其原 consumed_refs，4398/2029 字符完整读取通过；
  没有规范化/编辑原事件或改候选。
- 原 public-cq.json 九题被识别为公开 draft seed，保持稳定外部身份及非确认边界。
- 复制原账本，在内存对该副本显式重新计算派生投影（普通无新数据 tick 会复用旧缓存，不冒充
  已重算）。known=12、unknown=0、inflight/pending=0、tail_bound=0，费用仍 1.84794112 CNY。
  原 ledger 的 authorization/state/events、原生读取事件和 seed 哈希前后相同。

这些证据证明原平台技术误拒已消除及计价未改变，不代表生产上下文实际恢复、独立建模质量
或净降耗通过。原生线程跨 round 的全新上下文机制未改；先减少错误触发、提供旧提案精确引用，
不借本次修复建立新恢复/记忆框架。性能收益及 CQ 提示的真实语义效果仍待获准运行。

## 影响、收尾与剩余验证

GitNexus impact 查找 _read_materials、_install_scope、validate_snapshot、successful_reads 和
预算汇总符号均未收录，risk UNKNOWN；因此影响判断依据当前调用点：WorkUnitFlow/角色
接纳、prepare/source-revise、局部检查/总览/独立读取覆盖，以及共享预算投影。没有图谱覆盖声明。

本次仅修改 modeling_team 的运行代码/专业提示和 Host 指导，无 backend/frontend 应用代码、
依赖或服务配置变化，按仓库规则不重启 ontology-platform.service。原失败 run、原件、旧报告
和已清理资源状态保留；没有追加/扣除运行预算，没有新增模型 token 消耗。

R5.0-012 整体仍 PARTIAL：历史真实 L0 失败不被工程修复覆盖，修后真实角色采用、实际模型
application/治理读回、独立 L1/L2 仍待验证。当前结果属于开发/工程合同验证，不冒称新的独立
工程验收或真实业务盲测。

提交前最终 staged detect_changes 已执行：18 文件、0 已索引符号/执行流、risk low。由于新 v5 符号不在旧索引内，此结果不等于图谱影响覆盖。

全量之后仅修改 role_work._install_scope 的上述 CQ 刷新条件、基础角色夹具和两个固定时序/递归刷新用例；其余运行代码、专业包、依赖及预算代码保持全量时 SHA。旧全量中 76 项属于这三个角色文件，剩余 331 项未变通过结果复用；最终三文件78项覆盖该局部差异及两项新增回归。当前409项按上述证据覆盖，不伪称最终单条命令409/409；原406/1失败和中途反例均保留。

末轮角色命令使用相同锁定环境/pytest配置，范围为 test_role_team_flow.py、test_role_team_live_contracts.py 和完整 test_role_team_independent.py，无过滤器。变更 v5 Python 的 Ruff check/format 通过，Host skill validator、相关链接及 diff 检查通过。task_budget.py 的15条既有 Ruff诊断与HEAD一致，无新增诊断，未称整个旧文件Ruff通过。
