# R4.0-011 接口映射开发与测试记录

日期：2026-10-02。权威范围为 [R4.0-011](../../requirements/requirements-v4.0.md#r40-011-接口映射视角与外部-api-关联)
及[详细设计](../designs/2026-10-02-r4-0-011-api-mapping-design.md)。用户授权按设计完成开发和测试。
开发基线 `597587b`，开始时工作树干净。本轮不启动真实 semantic modeling run，不调用外部业务 API。

## 实现范围

- 采用设计 D1／D7：新增活动接口映射方法与两种完整候选示例，使用普通 entity／predicate／relation、
  semantic_definition 和既有参数注解。不新增平台类型、专属 CRUD、执行 DSL、迁移或管理 UI。
- Modeling／Protocol／Coordinator 指令、两份活动建模合同、012 当前 Task 和 009 验收 Task 同步。
  示例采用无工单概念的 catalog 模型，资料与报文均为隔离定义，不能当成工业服务客户事实。
- 无 Class 查询接口独立定位；能力路径精确绑定 Operation＋bindingId，不重复维护权威定位。
  消息／字段／集合元素各有身份；两个对象参数和重复调用分别关联。API ID、业务编号、数据库键
  不自动等同；编码以字段为范围，数据库与 API 引用共同参考值；转换保留方向、未知及冲突。
- 现有 R4.0-010 的 kind-aware 回执机制用于既有 Operation／TableMapping；工具的
  requirement_id 保持其现有机械合同，未新建 011 回执或修改翻译器。
- 统一候选示例使用既有闭合字段，Protocol 编写完整 materialization plan，审批摘要覆盖完整
  payload。测试里的统一候选到计划转换仅是该示例的机械交接，不是新增生产转换服务。
- 本轮未发现必须修复的通用生产代码缺口。平台不会自动判定错绑同类对象、普通图中的 bindingId
  是否仍存在或两种接口是否等价；用反例明确这些需要语义重审，未宣称平台已经自动拦截。

## 开发验证覆盖

| 验收 | 实际证据与边界 |
| --- | --- |
| A1／A2 | 无 Class 查询接口、同路径不同系统／v1-v2 并存；path/body/query 同名字段、嵌套数组与 supplier.id 各有身份；参数方向、集合、出现条件和缺失／null 含义完整读回 |
| A3／A4 | 两个业务参数及重复调用上下文、复合标识逐成员、API／DB 身份未知、字段范围同代码不同意义、数据库不同编码共享值；定向验证转换字段／对象位置／属性／规则及方向；保留冲突，不执行转换 |
| A5／A6 | 两 Tool Binding 保留且选择第二项；替代／组合步骤／部分能力可区分；202 受理、task ID、200 业务拒绝、部分完成、204 无正文、未知正文和分页说明保存。结构合法的错误参数／失效 binding 反例不被写成语义 PASS |
| A7 | 两种候选合同／审批投影、确定性翻译、真实分阶段 dry-run／apply／回执及幂等重放；字段改名保持身份、显式关系删除后恢复；版本并存及 binding 漂移的重审边界有测试 |
| A8 | RDF 查询、精确读、列表、Context full／compact、角色过滤、分页截断、受限主体和导出；使用真实 HTTP 身份解析与保护集。跨 Ontology／隐藏桥接／过滤后游标继续复用 008 通用回归，不声称本条新增权限机制或自动检测任意文本秘密 |
| A9 | catalog 场景、既有 Operation／数据库映射兼容；实际 PostgreSQL／Oxigraph／HTTP 往返与机械检查分列；不复制业务行、真实消息、凭证或 Evidence |
| A10 | 未执行。已将方法输入同步到 009 Task；后续仍需冻结真实业务资料、接口版本与获准脱敏样例，由独立方验收身份、编码、方向、分页和异步反例。在线可用和执行成功也未验证 |

主要测试：[Team 合同](../../../modeling_team/tests/test_r4011_api_mapping_contract.py)、
[RDF／读取](../../../backend/tests/test_r4011_api_mapping.py)、
[真实 HTTP](../../../backend/tests/test_r4011_api_mapping_http.py)。

## 测试轮次与修正

- RDF Round 1：2 failed、2 passed。复用测试桩的 graphs 内容为占位符 `nonempty`，导出无法解析；
  在本条测试中序列化真实 RDF Dataset，Round 2 为 4 passed。没有修改生产导出代码。
- HTTP Round 1：2 failed。完整 fixture 超过现有 100 Items／Batch 限制；改为翻译器给出的阶段，
  每阶段 dry-run／apply，不修改平台限制、不宣称跨 Batch 原子性。
- HTTP Round 2—4：每轮 2 failed。依次修正测试的 Operation 读取入口、Context 返回字段和普通
  statement 字段：Operation 使用受控 Context 投影，主结果为 primary_matches，完整性在 recall／
  context_page，普通 statement 是 subject／predicate／object。未为测试假设修改平台合同。
- HTTP Round 5：2 passed；81.72 秒。后续补真实回执复用、引用删除／恢复和授权分页检查。
- Team Round 1：2111 passed、1 skipped、314 subtests passed、2 failed。同步 009 Task 的方法
  输入，并让旧场景中性检查与现有其他 v4 语义扩展同样处理 interface_mapping。
  定向 60 passed、3 subtests passed；Team 第二轮全量通过。
- 最后核对补齐时间转换示例的字段、对象位置与共享属性引用；对变化 fixture 再做定向和真实往返。

## 最终验证

开发侧 A1—A9 合同／功能验证 PASS；独立功能验收和 A10 真实映射语义验收未执行，整体 PARTIAL。
本轮无外部业务调用，不能据此判断在线接口可用、业务执行成功或真实建模质量。

| 检查 | 结果 |
| --- | --- |
| 后端全量 | 1140 passed、53 skipped；264.14 秒。跳过的外部／真实运行项不视为 PASS |
| Team 第二轮全量 | 2113 passed、1 skipped、314 subtests passed；169.09 秒 |
| 最终后端定向 | 35 passed；107.06 秒。覆盖当前完整 fixture、008 跨图／隐藏桥接／分页、受控 Operation 合同 |
| 最终 Team 定向 | 60 passed、3 subtests passed；5.24 秒。覆盖当前两候选、审批、Task 接线和场景中性合同 |
| 真实依赖／HTTP 最终 | 2 passed；137.38 秒。两种当前完整候选分别使用真实隔离 PostgreSQL／Oxigraph／服务 HTTP；含回执复用、引用删除恢复、保护集及授权分页 |
| 指令／格式 | Skill validator、JSON 解析、本地链接与围栏检查、新增 Python Ruff、git diff --check 通过 |

全量与最终定向分别列出；最后只补齐 fixture 中的转换字段引用和测试接线，未修改平台可执行
代码。用当前定向和真实往返补足变化范围，不把旧 fixture 的结果当成新示例的独立语义证明。

完成后端全量后重启服务。首次 systemctl 因宿主未注入用户 bus 环境返回
`Failed to connect to bus: No medium found`；确认 UID 1000 的 `/run/user/1000/bus` 后，
显式设置 XDG_RUNTIME_DIR／DBUS_SESSION_BUS_ADDRESS，2026-10-02 21:40:21 +08 起 active。
启动后 `/api/health` 为 `{"status":"ok"}`、前端 5173 为 HTTP 200。最终真实往返在此运行环境执行。
本轮无前端实现变化，不要求前端 build／Playwright 作为额外完成门。

可复用命令（从仓库根执行；后端命令目录为 backend）：

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short --disable-warnings
env -u DEEPSEEK_API_KEY PYTHONPATH=.. RUN_API_MAPPING_HTTP=1 uv run pytest -q tests/test_r4011_api_mapping_http.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q tests/test_r4011_api_mapping.py tests/test_r4008_context_query.py tests/test_operation_semantics.py
cd ..
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q modeling_team/tests
python modeling_team/skills/ontology-modeling/evals/validate_skill.py
```

真实用例仅清理自建 Project、Ontology、Graph Set、API Key、测试主体、RDF 图和注册／版本行；
所有失败轮次保留在 `/tmp/r4011-*-round*.txt`，全量和最终结果在 `/tmp/r4011-backend-full.txt`、
`/tmp/r4011-team-final.txt`、`/tmp/r4011-backend-focused-final.txt`、
`/tmp/r4011-team-focused-final.txt`、`/tmp/r4011-http-final.txt`、`/tmp/r4011-http-current.txt`。

GitNexus 最终 detect_changes 返回 low、2 touched test symbols、0 affected processes；本轮生产差异是
指令／合同，无生产调用关系变更。该结果不提供未索引新测试的图覆盖，实际使用 diff、活动
Task 加载、合同检查与测试验证。无 REST／MCP 合同变更，无需同步接口字段文档。
