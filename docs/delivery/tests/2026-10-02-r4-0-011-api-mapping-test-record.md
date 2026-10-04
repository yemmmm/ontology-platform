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

## 独立功能补验 Round 1 — 2026-10-04 — A5／A7（计划）

复用上述既定 A5／A7 与详细设计 §6，不另建测试方案。授权为最小泛化受控 fixture、实际隔离角色功能调用；不是真实业务 semantic start。测试方仅新增
`modeling_team/tests/test_r4011_binding_review_functional.py`、追加本记录及 gitignored 原始证据，不修改产品代码、共享需求或保留 run，不提交。

| 用例 | 步骤 | 预期／通过标准 |
| --- | --- | --- |
| B1 选定第二绑定 | 从既有 catalog fixture 裁取完整依赖子图，经真实 HTTP dry-run／apply；实际隔离 Consumer 通过受治理读取回答接口定位 | 选 reserve-v2 的真实定位，不默认 reserve-v1；原始角色报告和读响应可定位 |
| B2 选定绑定删除 | 同 Session 实际 update_operation 删除 reserve-v2，保留备用；Consumer 再读当前图 | 明确精确绑定不可确认／缺口，不自动换备用，不凭缺失推导业务执行失败 |
| B3 选定绑定改名 | 实际 update_operation 将 reserve-v2 改成 reserve-v2-renamed，普通引用暂留原 ID；Consumer 再读 | 明确旧 ID 不匹配，不按版本／相同路径自动认定等价 |
| B4 删除／改名重审 | 新完整候选及真实摘要、旧批准摘要、实际当前读取交给装载 Coordinator 指令的独立隔离模型角色 | 实际输出本候选重审结论、受影响引用／范围／未知和下一步；旧批准不能批准新内容；测试程序不生成结论 |
| B5 清理与边界 | finally 清理自建项目、图／注册、API key；保存子角色 teardown 与原始输入输出 | 无自建资源或活动子会话残留；0 外部业务 API 调用，0 真实业务建模 starts；A10 仍未验收 |

前置：现有本地 PostgreSQL／Oxigraph／HTTP 健康；复用 CodexRuntimeAdapter v3 read-only child、McpReadForwarder 和现有 openai-sol-medium profile。Consumer 与 Coordinator 分别使用独立 child 会话；后者是受控决策验证，不是完整 Team Runner 协作或新的生产建模。
仅收集实际报告，再独立逐项人工核对；脚本不得用关键词或自行对比列表生成语义 PASS。无法运行的条目标 BLOCKED 并记录准确第一阻塞层。各历史结果不覆盖。

### 补验 Round 1 实际结果

工作区 HEAD `c2593c4b587276f3e9331d70ce72a5d8414b99b0`，实际 prompt-snapshot.json 保留完整 hash；其他 Agent 正在写设计／交付文档。本轮命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. R4011_LIVE_BINDING_REVIEW=1 uv run pytest -q ../modeling_team/tests/test_r4011_binding_review_functional.py --tb=short`。
实际 `1 failed in 22.37s`：测试 fixture 调用 `app.security.auth.create_api_key` 未传 user_id，返回 `ValueError: user_id is required`。初始四阶段真实 dry-run／apply 已完成；尚未启动角色，B1—B4 BLOCKED。B5 自建项目／keys／graphs 清理已完成，证据 `workspaces/r4011-binding-functional/round-1/cleanup.json`。这是测试 fixture 问题，非产品缺陷；复用既有 HTTP 测试的 subject_access_support reader helper 修正并清理测试主体，后续复测仍使用本方案。

### 补验 Round 2 — 2026-10-04 — BLOCKED（runtime/infrastructure）

同一方案，reader fixture 已修正；证据 `workspaces/r4011-binding-functional/round-2/`。命令同上，新增 `R4011_EVIDENCE_DIR=../workspaces/r4011-binding-functional/round-2`。实际 `1 failed in 242.36s`：初始图四阶段 dry-run／apply 成功，Consumer bwrap child、report_sink 和 platform_read_proxy 均实际启动／ready；但模型尚无读请求或报告，随后 `ExaminerRuntimeBlocked: binding-rejected`。原始 error.json 的准确第一层为 `blocked_reason=runtime-infrastructure, reason_code=child-crash`，runtime-failures.json 为 `provider-error-terminal`。同会话 app-server-events.jsonl 保留警告 `Falling back from WebSockets to HTTPS transport. workspace routing discovery timed out`；不能据此推导模型质量结论。

现场环境检查：http_proxy／https_proxy／no_proxy 及对应大写均未设置，`ss -ltn '( sport = :1080 )'` 确认 `127.0.0.1:1080` 有监听。仅恢复既有本机非秘密代理白名单后复测，不修改运行框架／模型／角色业务合同，不在活动 child 上换路由。当前 handle 已终态，teardown.json 六项均 true；cleanup.json 证明测试项目／keys清理及所有自建图drop。B1—B4仍BLOCKED／无报告，B5清理PASS；下一轮保留本失败证据。

### 补验 Round 3 — 2026-10-04 — FAIL（Medium prompt-contract）

同方案；命令增加 `http_proxy=http://127.0.0.1:1080 https_proxy=http://127.0.0.1:1080 no_proxy=127.0.0.1,localhost` 及 `R4011_EVIDENCE_DIR=../workspaces/r4011-binding-functional/round-3`，模型／业务提示未改变。工作区 HEAD 及全文提示在 round-3/prompt-snapshot.json；三个 proxy_presence 均 true。实际收集到真实独立 Consumer 报告与七份成功读取原始响应，但 B1 FAIL：报告为 unanswered，正确识别 reserve-v2，却未能取得 Operation 投影，无法确认系统／接口标识／版本。B2／B3／B4 未执行；不将未正确读取 Operation 的 no_match 判为失效绑定。B5 PASS：子会话 teardown 六项 true，清理后自建 RDF 图 graph_exists=false、测试项目／keys／主体已不存在。真实业务 starts=0、外部业务 API calls=0，A10 未验收。

**M011-01（Medium，Consumer tool-use／prompt-contract）**：按 B1 问题读取真实已物化的两绑定图，期望使用受控 Operation 当前投影选 reserve-v2 并说明 catalog-a／POST /v2/reservations／v2；实际 Consumer 精确 Operation IRI 查询没有指定 resource_types，proxy 默认实例／关系／fact／rule范围不含 operation，返回 no_match；随后添加不存在的 resource_projection 字段收到 read-arguments-schema，最后 semantic_roles=[operation] 仍未指定真实资源类型。现有工具 schema 提供 resource_types，正确读取路径已有 HTTP 功能证据，不是已证实的平台读取缺陷。最终报告准确保留“未取得 Operation 的受控投影及实际 tool_bindings”，未虚报绑定失效或外部执行。建议开发方窄补实际 Consumer／Operation 工具调用方法与正确类型例子，再按 baseline → 删除／改名 → Coordinator 重审复测，不降低 B1。

证据：`round-3/baseline-consumer/reports.json`、该目录 `acceptance/.../platform-read/.../0.json`—`6.json` 的原始请求／响应、`evidence/app-server-events.jsonl` 的实际工具调用和 schema 拒绝、`packet.json`、`role-instructions.json`、`teardown.json`。Consumer 使用 v3 Platform Examiner 真实隔离子角色；Coordinator 尚未启动。后续 Coordinator 使用同一 read-only transport 注入完整活动 Coordinator 合同，证明真实模型决策，不证明持久 Team Runner 协作或平台自动触发器。

pytest 为 `1 failed in 242.24s`，末尾另暴露测试 fixture 序列化错误 `TypeError: Object of type V3ProxyCallReceipt is not JSON serializable`；reports.json 与 teardown.json 已保存，observables/runtime-failures 之后未保存。仅在新增测试内按实际 dataclass合同用 asdict 序列化 receipts，且 baseline unanswered 时停止后续调用，避免重复消耗。原始报告和读响应保留不改；该测试错误不覆盖 M011-01 的实际行为失败，也不算产品缺陷。按主 Agent指示暂停新模型调用，等待开发方修复权威提示后复测。

Round 3 保留 SHA256：Coordinator全文 `dd7fc4d7838b7c0a224de6f529e0b4439ecf61cd2a6f97ddabf4cb77e5b39fad`；实际Consumer包 `eb1c016edf86feb94b2e9702d1134225f204927839be9b0e9821bf3697464a8c`；实际Skill `f4dd45cee0dff8ac8397723992cf941a9ecc325cf301815956eb9e2117b52855`；prompt-snapshot.json `f2fc2b7a39c8fd86f27f34d05485e27f765265efcd346e359cc82947ac2722df`；baseline packet `4e65d51daeb02bf083f75138010f9274ad882bcd32e723597dfe0dee7dae356f`；role-instructions.json `41e26a553dea795f99dc949e2dfd161d7f61c3e7e050dd895fe4b610242ab4bb`；实际 reports.json `59103c404a3a9b235007bdd13f1d156415d96410f42678de76a5de8d6a1f3271`。

测试修正后窄验证：`uv run ruff check ../modeling_team/tests/test_r4011_binding_review_functional.py` 全部通过；同目录 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests/test_r4011_binding_review_functional.py ../modeling_team/tests/test_r4011_api_mapping_contract.py` 为 `7 passed, 1 skipped in 0.57s`（实际模型用例未重新启用）；只读 Python 构造实际 V3ProxyCallReceipt，含嵌套 ontologies，经 asdict→JSON往返通过；git diff --check通过。该窄验证仅证明fixture序列化修正与现有合同无回归，不证明 M011-01已修或A5／A7已通过。没有产品代码修改，不重启服务，不提交。

### 补验 Round 4 — 2026-10-04 — M011-01修复复测（进行中）

复用同一 B1—B5 方案。开发方仅补活动 Consumer 包的真实 resource_types／semantic_roles区别、合法Operation读取示例及缺失绑定边界；无 fixture答案，无 __main__／平台实现变化。测试方已独立审 diff，活动包 SHA256=`44af702c061d2743720105555a99bfcb17c99aedd3ee58f496e6a62439d7ab0a` 与交接一致，HEAD=`c2593c4b587276f3e9331d70ce72a5d8414b99b0`＋当前提示修复／同测试修正；host_ops另组工作不属本调用路径。现场再次确认1080监听，使用已核实的三个非秘密代理变量；记录新全文snapshot，不覆盖Round1—3。

命令：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. http_proxy=http://127.0.0.1:1080 https_proxy=http://127.0.0.1:1080 no_proxy=127.0.0.1,localhost R4011_LIVE_BINDING_REVIEW=1 R4011_EVIDENCE_DIR=../workspaces/r4011-binding-functional/round-4 uv run pytest -q ../modeling_team/tests/test_r4011_binding_review_functional.py --tb=short`。
先复验B1，unanswered即停止后续，不降低要求；只有实际获得Operation当前tool_bindings并确认第二绑定后，继续删除／改名Consumer与两个独立Coordinator重审。每child300秒，原始报告及当前绑定读取由独立人工逐项核对，不以机械 completed 状态或 pytest绿灯推导A5／A7 PASS。本轮不新增真实业务start，A10仍未验收。

#### Round 4 B1独立核对

B1 PASS，M011-01正常读取分支 FIXED：实际角色p3请求使用 `resource_types=[operation]`／`context_detail=full`，原始响应返回两个Tool Bindings；正式报告精确选择 reserve-v2→catalog-a／POST /v2/reservations／v2，明确首项reserve-v1不能代替当前选择。接口usesBinding→bindingId／forOperation的真实图边与投影分别读取，普通邻域分页补完，报告仅确认模型内定位，不宣称在线可调用或执行成功。证据 `round-4/baseline-consumer/reports.json`、原始平台p0—p5及teardown／observables。后续B2—B4仍进行中。

#### Round 4 B2独立核对

B2 PASS：同Session实际update_operation经dry-run／apply删除reserve-v2；新独立Consumer的p2受控完整投影仅有reserve-v1，绑定节点仍选reserve-v2。正式报告明确指定ID无法确认系统／标识／版本、reserve-v1只属于另一个绑定且不能代替，active状态不能修复不匹配。角色没有拿baseline旧报告／旧投影作为当前事实，也未虚报外部执行失败；其不知道历史删除操作，准确不从当前缺口推断曾被删除。证据 `round-4/deleted-dry-run.json`／`deleted-apply.json`、`deleted-consumer/reports.json`及p0—p5。删除重审及改名仍待核对。

#### Round 4 B4删除重审、终态与生命周期阻塞

B4删除分支 PASS：独立Coordinator实际读到当前Operation仅reserve-v1及旧bindingId=reserve-v2，读取直接引用与其分页、谓词和目标Class；正式报告不批准revision=2／当前实际candidate_digest的受影响绑定内容，明确旧revision=1／旧digest批准不沿用、不得切到备用或猜v2位置，保留安全独立内容。报告记录实际直接引用覆盖范围、未查清间接／跨Ontology影响、Modeling／业务责任方确认后修订、Protocol核实漂移与翻译、Coordinator重新绑定内容审查的下一步；没有平台写入或外部调用。证据 `round-4/deleted-coordinator/reports.json`及p0—p10。角色另外准确识别本既有fixture的token前缀声明bindingId谓词与普通values实际使用通用bindingId谓词不同，交Protocol核实，不按标签合并；这项额外技术未知不作为全候选审批PASS，也不改变被验证的重审结论。

同handle终态pytest=`1 failed in 522.09s`：三份真实报告采集完成；改名dry-run为validated，但apply返回HTTP409 `{"detail":{"code":"lease_expired","message":"Ontology lease has expired"}}`。原300秒租约跨多个只读模型会话后已过期，写入被安全拒绝。B3及B4改名分支BLOCKED／未启动；这是测试fixture租约管理问题，无新产品缺陷，不将其归模型质量。三个子会话teardown六项均true，自建项目／keys／主体／RDF图已清理，Round4输出保留不改。

主Agent同意仅在每次apply前读取Build Session当前revision并按既有acquire合同取得当前租约，不加heartbeat或平台机制；复用前三份已通过报告，不重复模型调用，下一轮只补改名Consumer／Coordinator，仍用本记录及原B1—B5标准。测试脚本增加显式 `R4011_BINDING_CASE=renamed` 定向复测选项；默认仍为完整方案。

### 补验 Round 5 — 2026-10-04 — 仅改名范围（进行中）

提示未改，活动Consumer包SHA256仍为 `44af702c061d2743720105555a99bfcb17c99aedd3ee58f496e6a62439d7ab0a`；复用Round4正常／删除报告，不将其重计新执行数。新隔离fixture由r1完整图改为r3改名当前图，原引用仍指reserve-v2；未重放先前Project／write，仅复用相同已有定义fixture。命令同Round4，另设 `R4011_BINDING_CASE=renamed R4011_EVIDENCE_DIR=../workspaces/r4011-binding-functional/round-5`。每次apply前立即按当前session_revision获取租约，记录无token的lease状态；不放宽业务断言、角色300秒边界或真实治理读取。本轮实际子会话目标仅2个。

#### Round 5 B3独立核对

B3 PASS：rename实际dry-run／apply均通过；新Consumer的p2完整Operation投影含reserve-v1和reserve-v2-renamed，普通绑定节点仍指定reserve-v2。正式报告明确旧ID没有匹配，v2-renamed的同系统／路径／版本不构成旧ID已确认定位，不自动替换也不回退首项，保留绑定迁移／等价关系未确认；active状态不修复不匹配，不宣称外部执行。原始投影、图边／普通属性分页与正式报告一致，未使用前轮报告作为本项目当前事实。证据 `round-5/renamed-dry-run.json`／`renamed-apply.json`、`renamed-consumer/reports.json`及p0—p5。Coordinator改名重审与全清理仍待结束。

#### Round 5 B4改名重审、清理与最终结论

B4改名分支 PASS：实际独立Coordinator报告“不批准当前完整候选 revision=3／新candidate_digest 的受影响绑定变更”，明确旧revision=1／旧摘要批准不能沿用；根据当前受控投影及普通选择ID，识别reserve-v2不在reserve-v1／reserve-v2-renamed中，拒绝按名称／相同v2路径自动替代。报告给出binding选择合同、forOperation及reserve-api位置链的具体影响，保留未验证的间接／跨Ontology范围，要求业务／Modeling确认、Protocol核实漂移与翻译、Coordinator重审完整修订，不重置无关内容或自写平台。原始报告中的当前／旧摘要均与相应完整候选机械复算一致；判断是实际模型输出，不由测试程序比较绑定列表生成。证据 `round-5/renamed-coordinator/reports.json`及p0—p7。

Round5实际命令结果=`1 passed in 349.85s`（仅2个真实子会话）；前置每次apply按当前Session revision获取租约已实际通过，后续无需heartbeat或服务重启。B5 PASS：Round4三个与Round5两个子会话各自teardown六项全true、runtime-failures均空；两轮cleanup都执行自建Project／keys／主体／Graph Set／RDF图／注册版本行清理，并检查Project／keys／主体不存在、RDF graph_exists=false。没有活动子会话、未决写入或外部业务调用。

最终独立机械取证：复用既有 `_cq_load_platform_read_artifact` 对五个角色合计37份真实读取逐一验证request／response digest；每份回执都属于各自packet授权Project／Ontology，每个报告batch／question及所有p句柄均绑定本角色真实回执。当前／旧候选摘要核对通过。两轮实际Consumer与Coordinator全文hash一致，活动源文件当前hash仍一致；两个prompt-snapshot.json SHA256同为 `aa0d216d5d0e27c404c4fc1c5041bb1ac0c3bfebd62b4d2d797f8fce73eadf15`。五份正式报告、37份原始读响应及输入／teardown等共71个文件hash保存在 `workspaces/r4011-binding-functional/round-4-5-manifest.json`；失败Round1—3及Round4过期租约结果保留。

相关回归：独立执行当前 `test_r4011_api_mapping_contract.py` 为 `8 passed in 0.12s`；最终关闭live选项执行原两测试文件为 `8 passed, 1 skipped in 0.65s`，skip不计新真实执行。仓库根既有Team命令对live文件默认跳过也可正常收集（1 skipped）；Ruff及git diff --check通过。测试中仅改自身lease前置和定向复测选项，产品实现及已验证角色提示没有再变化，不要求Backend全量或重启。

| 本次补验项 | 最终独立结论 | 范围 |
| --- | --- | --- |
| B1／M011-01 | PASS／FIXED | 实际受控Operation读回，精确选择第二binding并说明真实定位 |
| B2 | PASS | 真实删除后Consumer明确缺口、不自动切备用 |
| B3 | PASS | 真实改名后Consumer保持旧选择未解析，不凭相同路径自动换ID |
| B4 | PASS | 两个实际独立Coordinator对真实当前图、新完整候选／摘要作绑定重审，拒绝不安全内容、旧批准不沿用，保留范围与下一责任人 |
| B5 | PASS | 原始输入输出及37个受治理读取回执保留，全部临时资源／会话清理 |
| A10 | 未验收 | 无真实业务semantic modeling start、隐藏业务资料或外部API调用；受控角色功能不能替代真实映射语义PASS |

总体：**R4.0-011 A5／A7历史缺失项的本期受控独立功能补验PASS**，M011-01已实际复验FIXED；无剩余本轮产品缺陷，不建议新增修复或重复已通过范围。结合原独立记录已通过的其余A5／A7功能范围，可补齐这两项有界功能证据；仍不证明全Team Runner协作、自动重审触发器、当前候选完整业务正确性、在线调用／执行结果或A10语义质量。真实语义建模有效时间为0；Round4／5的522.09s／349.85s为功能fixture／真实角色读取决策／等待的合计墙钟时间，不将等待或文档时间冒充建模有效时间。没有产品代码修改或提交。
