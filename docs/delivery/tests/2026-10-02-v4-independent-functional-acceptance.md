# v4 独立功能验收：007／008／010／011

日期：2026-10-02；独立执行结束核对时间 22:06 +08。
验收方未参与这四项实现、开发测试生产或方案编写。本轮只读核对权威需求、设计、
既有开发记录与测试断言，独立执行既有测试及隔离平台 fixture。
没有创建、继续、修复、读取真实 semantic modeling run，没有读取真实生产输入或隐藏 CQ／答案，
没有外部业务 API／SQL、模型 provider 调用、产品修改、既有证据修改、需求状态修改、服务重启或提交。

读取依据为 `AGENTS.md`、`docs/requirements/requirements-v4.0.md` 中四项正文、对应四份
`docs/delivery/designs/` 设计及 `docs/delivery/tests/` 开发记录。后者只用于识别测试入口和限制，
不把其中开发 PASS 直接转记为独立 PASS。没有使用历史记忆事实。

## 基线与证据边界

初始 HEAD：`48c065bcf3022142bff20658ce4c204f21a237ab`。
执行期间主 Agent 仅修改模型路由、路由测试和新模型配置，随后 HEAD 为
`8e6a18c360015a7924c778b772a8d73d6e84892b`。所验收平台、协同与映射实现未变化。
本轮没有改动任何既有测试。已有测试由独立验收方重新执行，并核对其实际断言；
这提供独立功能执行证据，仍不等于独立创建的业务 oracle 或真实语义验收。

Round 1 功能结果：008／010 的 A1—A9 在本次有界测试合同内 PASS；007 的 A1—A9 为 PARTIAL，
011 的 A1—A9 为 PARTIAL（共享变更／绑定漂移的业务重审证据不足）。
四项 A10 均未由本验收方执行，四项整体均为 PARTIAL。
Round 1 未发现实证 Critical／High 产品缺陷。其 PARTIAL 项是确切覆盖缺口，不能反推产品失败。
2026-10-03 续验发现的实际失败另列于下方，不用 Round 1 结论覆盖。
续验收口：007 A4／A5／A6 bounded PASS，修复后的独立 backend 全量 1144 passed／54 skipped；
原 High 已经独立定向复验修复。007 A1—A9 在记录的有界功能范围内 PASS，011 A5／A7
仍为 PARTIAL；008／010 原功能结论保持，四项 A10 与整体仍为 PARTIAL。

## Round 1：实际执行

以下全部从 `/home/yangxiang/ontology-platform/backend` 执行。

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short --disable-warnings tests/test_r4007_team_identity.py tests/test_r4008_context_query.py tests/test_r4008_vector_recall.py tests/test_semantic_mapping_integrity.py tests/test_r4011_api_mapping.py ../modeling_team/tests/test_r4007_multiview.py ../modeling_team/tests/test_r4008_context_contract.py ../modeling_team/tests/test_r4010_mapping_contract.py ../modeling_team/tests/test_r4011_api_mapping_contract.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short --disable-warnings tests/test_r4004_process_binding.py tests/test_modeling_batches_service.py tests/test_modeling_batches_delete_recovery.py tests/test_modeling_batches_relational_mapping.py tests/test_semantic_context_query_api.py tests/test_semantic_context_query_mcp.py tests/test_semantic_context_cursor.py tests/test_semantic_access_authorization.py ../modeling_team/tests/test_r30008b_staged_decisions.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. ONTOLOGY_LIVE_CONTEXT_TEST=1 RUN_RELATIONAL_MAPPING_LIVE=1 RUN_RELATIONAL_MAPPING_HTTP=1 RUN_API_MAPPING_HTTP=1 uv run pytest -q --tb=short --disable-warnings tests/test_r4008_live_context.py tests/test_relational_mapping_application.py tests/test_relational_mapping_http.py tests/test_r4011_api_mapping_http.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. RUN_CHECKPOINT_DATA_LIVE=1 uv run pytest -q --tb=short --disable-warnings tests/test_checkpoint_data_live.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short --disable-warnings tests/test_semantic_command_compiler_r3003.py tests/test_semantic_access_http.py
```

| 检查 | 独立实际结果 | 原始日志 |
| --- | --- | --- |
| 需求定向 | 77 passed，9050 warnings，108.86 秒 | `/tmp/v4-independent-functional-focused.log` |
| 审批、流程绑定、Batch、查询／cursor／授权支持回归 | 186 passed，1857 warnings，19.73 秒 | `/tmp/v4-independent-functional-support.log` |
| PostgreSQL／Oxigraph／HTTP 隔离功能 | 20 passed，1 skipped，93 warnings，127.44 秒 | `/tmp/v4-independent-functional-live.log` |
| PostgreSQL／Oxigraph snapshot／fork | 1 passed，3 warnings，0.69 秒 | `/tmp/v4-independent-functional-checkpoint.log` |
| 映射编译器、专属精确读取、授权与分页 | 40 passed，41 warnings，5.41 秒 | `/tmp/v4-independent-functional-read-compiler.log` |

合计 324 passed／1 skipped，未将 skipped 或 warnings 记为 PASS。
唯一 skipped 是应用边界 suite 中 memory fixture 的行锁并发检查；同名 live PostgreSQL
分支已执行，实际覆盖两个 apply 交错、最终重校验、未决 fence 与同 Attempt 恢复。
测试总运行时间为各 suite 累计 262.13 秒；部分独立 suite 同时执行，不是墙钟耗时。
真实语义建模有效时间为 0；本任务是独立功能验收，不占用生产 semantic start 额度。

执行前 `curl --fail --silent http://127.0.0.1:8001/api/health` 返回 `{"status":"ok"}`。
真实 HTTP fixture 使用当前已启动服务及其 PostgreSQL／Oxigraph，均以 uuid 唯一资源隔离，
finally 清理各自 Project、Ontology、Key／测试主体、Graph Set、图注册／版本及 RDF 图。
008 fixture 对其清理结果另有无残留断言；其他 fixture 的清理成功由测试成功证明，
本验收没有为其增加额外全库扫描，不能宣称完成了环境全局无残留审计。
snapshot／fork 使用服务层真实存储往返，未设置 HTTP 模式，不代表 fork HTTP 新轮验证。

## 逐项覆盖

### R4.0-007

| 条款 | 本轮独立证据及结论 |
| --- | --- |
| A1 | PASS（活动合同）：实际 Task／Runner 三角色组装、新地图加载、生产 CQ 隔离，角色职责与交错方法可用；不证明模型实际分析质量 |
| A2 | PASS（身份合同）：同名异义稳定键可独立；已有身份重复 create 被 staged submit 拒绝，改为正确 update 后同 run 继续；业务同义判定未验证 |
| A3 | PASS（表达／局部绑定功能）：unknown／conflict／deferred 保存及获准投影，004 局部绑定回归；实际脚本／说明冲突是否识别正确归 A10 |
| A4 | PARTIAL：候选 revision／item／slice 闭合、incomplete／unknown、漏绑反例有证据；未以实际多流程变更证明直接及已知间接引用重审完整 |
| A5 | PARTIAL：D1 方法与延后状态／不可变前后候选可用；未实做新增必填参数且旧流程不能同步修改的新定义／跨 Batch 切换案例 |
| A6 | PARTIAL：既有 Batch 原子／失败恢复通过，010 live 跨图依赖及 fence 恢复通过；不代替本条新定义过渡中跨 Ontology 部分失败后旧引用持续有效的业务案例 |
| A7 | PASS（功能）：错字段定位、误 create 修正、旧审批摘要拒绝新内容、候选修订／workspace version 漂移回归 |
| A8 | PASS（有界恢复）：新旧地图原字节保存接续、owner／pending 保留、fork 标记与成员 API；新增真实 checkpoint snapshot／fork 存储往返。未把此组合证据写成新地图端到端真实 Team fork run |
| A9 | PASS（功能隔离）：Judge 仅投影获准 IRI 状态，私密名称／数量／原文不下发，隐藏输入隔离，交接状态不提供语义 PASS |
| A10 | 未执行；真实业务兼容、间接影响完整性和隐含覆盖仍需独立语义证据 |

### R4.0-008

| 条款 | 本轮独立证据及结论 |
| --- | --- |
| A1 | PASS：显式大小写／OR 角色主命中筛选；普通非 Class 身份不合并；词法／向量窗口被隐藏／非目标占满后稳定补读；实际 pgvector 续页 |
| A2 | PASS：共享 Action 的两次调用、不同绑定和 typed literal full／compact 对照，身份及方向不丢失 |
| A3 | PASS：跨获准 Ontology、隐藏桥接、fact-only traversal、statement 锚点、环和多根最短路径有界去重 |
| A4 | PASS：结构化注解／未知／冲突、非法 JSON／多值歧义；compact 正文省略标记与 raw literal 防旁路，full 精确补读；真实 HTTP 对照 |
| A5 | PASS：隐藏与不存在同形、嵌套引用和 bridge 不泄露；授权前计额、隐藏集合变化不触发可见 cursor／完整性差异；真实保护集读取复用 011 live |
| A6 | PASS：不同页大小集合相同、预算 partial 与终页分离、depth=0／context_limit=0；第二主命中页 context-only 续完后到第三页，真实 HTTP 亦执行 |
| A7 | PASS：角色／主体／源版本 cursor 绑定与当前授权变化；游标／访问回归验证撤销与范围漂移 |
| A8 | PASS：非工单普通模型、四种映射／指标／Operation 明确关联投影；未调用数据库业务查询或 API |
| A9 | PASS：REST／MCP／能力目录与 Team 冻结／透传，partial 不当 complete，依赖失败不伪装完整空结果；无追溯读依赖 |
| A10 | 未执行；fixture 返回正确不证明真实 Consumer 的跨视角解释正确 |

### R4.0-010

| 条款 | 本轮独立证据及结论 |
| --- | --- |
| A1 | PASS：普通定义／Class、技术列与共享映射；真实 HTTP 四种资源保存、专属精确读、Context 和导出 |
| A2 | PASS：记录键／业务身份／作用域、复合列及未知可表达，编译器不强制虚构 business_key |
| A3 | PASS：引用式 join、自关联角色、列／路径闭合与准确错误，跨图引用与修正继续；不同来源同名表不按名称混合 |
| A4 | PASS：字段作用域编码唯一性、不同字段同码并存、L3 引用及反向删除保护；获准读回和嵌套授权检查 |
| A5 | PASS（保存合同）：指标 contexts、counted_identity、duplicate_handling 和未知闭合，未知不自动 count／DISTINCT；没有执行真实数值 SQL |
| A6 | PASS（保存合同）：转换引用／时间单位说明、null／unknown、omit／replace／clear 语义和规范 JSON 实际主体；不执行转换 |
| A7 | PASS：真实 PostgreSQL／Oxigraph 同批／跨图、删除、直接编辑、validate=false、最终重验、交错 apply、范围收缩、fence／同 Attempt 恢复 |
| A8 | PASS：专属四种精确读、列表、Context／MCP 合同及导出授权回归；嵌套隐藏 IRI、过滤后计数／分页；技术映射而非业务行 |
| A9 | PASS：两种活动候选、拓扑翻译、审批投影、kind-aware 回执及实际 HTTP 读回；旧合法编译输入兼容 |
| A10 | 未执行；真实业务键、基数、编码及 SQL 数值反例未由本轮证明 |

### R4.0-011

| 条款 | 本轮独立证据及结论 |
| --- | --- |
| A1 | PASS：无 Class／Action 查询节点、共享 Action／Operation、不同系统及版本身份，真实 neutral／unified HTTP 往返 |
| A2 | PASS：path/body/query 同名字段、嵌套数组位置独立；所有 entity 注解与 parameter 定义精确比较读回 |
| A3 | PASS（表达／绑定合同）：同类两个参数及两次使用、复合成员、ID 对应未知；错业务对象位置结构合法反例明确不算语义正确 |
| A4 | PASS（保存合同）：同字段范围代码含义、共享参考值、定向转换字段／位置／规则、未知与冲突保存及读取；不执行转换 |
| A5 | PARTIAL：Operation 两绑定保留且选 reserve-v2、替代／步骤／部分能力方法及候选有证据；失效 binding 反例仅证明平台不会自动换绑，未实际证明 Consumer 报告缺口 |
| A6 | PASS（表达／读取合同）：202 受理不等于完成／task ID 非对象、200 拒绝、204 none、unknown body、分页说明等原注解读回；不证明真实接口行为 |
| A7 | PARTIAL：两候选审批／翻译／真实分阶段 dry-run/apply／回执／重放、改名、显式边删除恢复通过；binding 漂移测试只对计划差异断言，未执行真实重审并记录结果 |
| A8 | PASS（授权合同）：真实保护集／server identity、隐藏 exact 404、列表计数／分页／导出、角色筛选及有界上下文。任意自然语言秘密识别不是现有能力；没有把 IRI 过滤当作通用文本保密证明 |
| A9 | PASS（功能）：catalog 中性场景、Operation／数据库映射复用、活动 Task／角色方法加载，真实平台依赖与机械测试分列 |
| A10 | 未执行；真实资料／脱敏样例的独立解释、在线可用与实际业务执行均未验证 |

## 收口

本轮没有产品失败，不新增修复建议或平台机制。007 A4—A6、011 A5／A7 的不足需要有界
共享变更／绑定漂移重审实例或后续独立真实语义取证；不能用本轮开发 fixture 的结构合法
消除该缺口。A10 保持待独立真实证据，不读取生产过程中的隐藏答案补全。
本记录不改权威需求状态、不提交。只检查新记录的格式与空白，不重复全量套件或重启。

## Round 2：2026-10-03 未覆盖点续验

用户取消时间限制后，独立验收方继续 007 A4／A5／A6 与 011 A5／A7；仍不参与真实
建模 run 的创建、继续、修复，不读生产输入、CQ 或隐藏答案，不修改平台实现、业务资料或模型。
唯一新增可执行文件为 `backend/tests/test_v4_independent_change_acceptance.py`。
使用已有 UUID 隔离的 `mapping_application` fixture、BuildSession／lease、Batch 服务与
PostgreSQL／Oxigraph；引用重审使用现有 Context Query 服务和真实 RDFLib SPARQL。
没有临时业务执行器、通用影响分析器或 Consumer 自动判定实现。

### 轮次与失败保留

| 轮次 | 实际结果与原因 | 原始日志 |
| --- | --- | --- |
| 新测试 Round 1 | 3 failed；两项测试误用不存在的 `SemanticNamespace.data_graph` 方法；查询 fixture 缺谓词 label，RDFLib 聚合比较抛 TypeError。均是本轮 fixture 问题，不归因产品或建模质量 | `/tmp/v4-independent-change-round1.log` |
| Round 2 | 修订命令工作目录错，修改未执行；旧测试再次 3 failed。保留执行错误，不声称已修订或获得新行为证据 | `/tmp/v4-independent-change-round2.log` |
| Round 3 | 修正为既有 `graph("data", ontology)` 并声明测试谓词 label 后：2 failed、1 passed、4405 warnings，23.76 秒。memory 和真实 PG／Oxigraph 的原子引用切换均被 `conflicting_item_effects` 拒绝；A4 有界间接链／漏绑检查通过 | `/tmp/v4-independent-change-round3.log` |
| Round 4 精确诊断 | 1 failed、2 deselected、15 warnings，1.71 秒；独立重跑 memory 用例，记录完整 finding。失败发生在第一次切换，后续第二 Ontology 失败／修正路径尚未执行 | `/tmp/v4-independent-change-round4.log` |
| Round 2 后端全量 | 1 failed、1141 passed、54 skipped、17783 warnings，294.98 秒；唯一失败为新独立 memory 原子切换测试，live 变体在未启用 opt-in 的全量中跳过（其真实依赖失败已由 Round 3 单独证明） | `/tmp/v4-independent-change-backend-full-round1.log` |
| 修复后 fixture 前提复核 | 修复责任方解除 effect 冲突后，原 test 进入后续步骤，`missing-action` 绝对 IRI 被 applied；原失败注入假设不属于通用 RDF 关系合同。此为测试前提问题，不扩大为目标本地声明的新平台硬门 | 修复责任方 `/tmp/h007-repro-after.log`，本验收仅接收该复现交接、另行核对当前编译合同 |
| Round 5 独立复验 | 将 B 的非法 target 改为明确拒绝的相对 IRI，成功切换／旧引用／同 session 修正断言保持：3 passed、4421 warnings，22.40 秒，包含 memory、真实 PostgreSQL／Oxigraph 与有界链查询 | `/tmp/v4-independent-change-round5.log` |
| Round 6 最终定向 | 补实际新参数 `parameterDefinition.required=true`、新 Action 关联参数、旧 Action 无新参数三项读回：3 passed、4421 warnings，24.22 秒 | `/tmp/v4-independent-change-round6.log` |
| 修复后独立后端全量 | 1144 passed、54 skipped、17791 warnings，247.19 秒；当前新增独立测试与修复方回归均纳入，live opt-in 仍单列 Round 6，不把 skipped 当 PASS | `/tmp/v4-independent-change-backend-full-round2.log` |

复现命令（目录 `backend/`）：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. RUN_RELATIONAL_MAPPING_LIVE=1 uv run pytest -q --tb=short --disable-warnings tests/test_v4_independent_change_acceptance.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short --disable-warnings tests/test_v4_independent_change_acceptance.py -k memory
```

新增测试 Ruff format／check 已通过。因为新增 backend 可执行测试，已按仓库要求执行
`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short --disable-warnings`
全量测试，日志 `/tmp/v4-independent-change-backend-full-round1.log`；终态为上述 1 failed。
修复前该轮不报告 backend 完成或全量 PASS。
修复后的当前后端全量另在 `/tmp/v4-independent-change-backend-full-round2.log`，
1144 passed／54 skipped。最终定向、全量与新增测试 Ruff／空白检查通过；到此停止扩展检查。
没有服务重启：本验收只补测试，不修改被运行平台；另有明确不重启的任务边界。

### H007-CHANGE-01：安全原子引用切换被误拒绝（High，原始失败；定向复验已修复）

独立 fixture 已保存旧 Action（无必填 reason）、新 Action（新合同）及新 mandatory reason 参数。
call-a／call-b 各自仍引用旧 Action。对 a 的同一 Batch 提交：

- `delete_relation(call-a, related, old-action)`；
- `create_relation(call-a, related, new-action)`。

两个不同对象的精确关系删除／新增应可在原子 Batch 最终态替换。当前实际返回
`attempt_status=validation_failed`，blocking finding `conflicting_item_effects`，消息为
`Items contain incompatible writes to the same semantic target`，归属两个 item。
memory 与真实 PostgreSQL／Oxigraph 都复现；失败保留了 Attempt／findings，未发生不确定写入。
代码定位：`backend/app/services/modeling_batches.py` 的 effect overlap 分支（续验时 893—909 行），
遇任一 delete 即拒绝该重叠；普通关系没有 `update_relation` 替代入口。
这阻断 007 A5／A6 规定的同 Batch 引用安全切换。拆成先删／后建不提供同一 Batch 原子性，
不能用它绕过要求或把结果写成 PASS。
已报告主 Agent，由独立于本验收方的修复责任方处理；验收方不修改守卫、不放宽失败断言。
随后独立复验原成功切换断言通过。后续失败注入改用合同明确非法的相对 IRI；不假设普通
RDF object 必须先在本地 declare，亦不新增目标声明完整性机制。保留所有修复前的 Attempt、
findings、失败日志与实际测试轮次；没有把修复后的结果覆盖回原失败轮。

### 当前逐条结论

| 条款 | 续验状态与精确边界 |
| --- | --- |
| 007 A4 | bounded PASS（声明链的有界功能）：从 mandatory parameter 沿共享 Action／两次 usage 到两个 flow，depth=3、全页 drain 后两条间接链可读；独立 fixture oracle 检出移除 usage-2 的 binding，flow-2 仍可到达。小页／depth=1 返回 cursor 和 truncated，不返回全局 compatible。真实 Agent 是否识别全部隐含业务影响仍为 PARTIAL／A10，不以本测试判断模型质量 |
| 007 A5 | bounded PASS：真实 PostgreSQL／Oxigraph 先物化新合同与必填 reason；原定义全部 outbound triples 不变、未切换 B 仍指旧定义；不引入同身份版本固定。实际客户业务是否同义／兼容仍留 A10 |
| 007 A6 | bounded PASS（预写失败）：A 删除旧关系／创建新关系在同 Batch 成功，B 同 Batch 中非法相对 IRI 被定位拒绝，删除旧关系没有先落地，B 仍旧、A 仍新；修正后复用原 BuildSession／lease 完成 B 切换，旧定义始终不变。保留各 Attempt／findings；没有对不确定 RDF 写入作故障注入，也不宣称跨 Batch 原子性 |
| 011 A5 | PARTIAL：原绑定选择／读取证据继续有效；本期使用普通节点的 bindingId＋Operation 图边，平台无 Consumer 的确定性失效绑定响应器，不能靠测试方自行比较列表冒充真实 Consumer 报缺口 |
| 011 A7 | PARTIAL：旧 fixture 仅构造删 binding 后的合法图／计划并确认不会自动换绑；尚无实际 Consumer／Coordinator 对真实 drift 发起、保存重审结论的证据。当前 Coordinator 指令明确要求该重审，但指令存在不是执行证据 |

011 的不足不是已证明的产品缺陷：权威设计明确局部 JSON bindingId 不由平台自动保证完整性。
要补实际 Consumer 语义行为需要独立获准的模型 Consumer 或真实语义取证，本任务不得
自行创建／继续真实 run，也不能新建“只比较 binding ID”的测试解释器来伪造产品行为。
四项 A10 仍未由本功能验收方执行。Round 2 以上结论不能替代独立语义验收。
本轮真实依赖测试直接导入当前 service，与隔离 PostgreSQL／Oxigraph 往返；本验收没有重启，
不据此声称正在运行的 HTTP 服务已经加载该修复。服务重启与运行端点验证由交付宿主负责。
本轮不提交、不回退其他工作者的文件，不修改需求状态或保留运行证据。

## Round 3 — native sleep 与明确零写入拒绝的独立有界运行功能验收

时间：2026-10-03 07:12 +08:00。责任边界：验收方只新增
`modeling_team/tests/test_v4_independent_runtime_acceptance.py` 并追加本文；修复由另一责任方
完成于 `modeling_team/runtimes/codex.py`、`modeling_team/runner.py`、
`modeling_team/staged_decisions.py`。未创建、继续或修复真实建模 run；未读取真实 CQ 内容、
隐藏题或业务输入；未修改原始运行证据，未调用业务 API／SQL，未重启服务或提交。
本轮测试没有 LLM 进程。真实 run 的事故原因由交付方报告，本验收不把该报告计为独立复现。

### 实际命令与结果

以下命令在 `backend/` 执行；代码输入在修复方声明 ready 后才开始测试。

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_v4_independent_runtime_acceptance.py -q > /tmp/v4-independent-runtime-round1.log 2>&1
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_v4_independent_runtime_acceptance.py -q > /tmp/v4-independent-runtime-round2.log 2>&1
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run ruff format ../modeling_team/tests/test_v4_independent_runtime_acceptance.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run ruff check ../modeling_team/tests/test_v4_independent_runtime_acceptance.py
```

| 实际轮次 | 结果 | 变化及证据 |
| --- | --- | --- |
| runtime R1 | 9 passed，1.59s | `/tmp/v4-independent-runtime-round1.log`；当前真实 notification、watchdog 线程、decoder、Runner、checkpoint 文件路径 |
| runtime R2 | 11 passed，1.90s | `/tmp/v4-independent-runtime-round2.log`；新增同 ID／不同 thread 与 turn 的 completion 边界，其余断言保留 |
| 格式与静态检查 | PASS | Ruff format 无进一步差异；Ruff check `All checks passed!` |

新文件不修改 backend 可执行代码。本轮没有再次执行整个 Team／backend suite：交付方正在
另行执行其完整回归，主 Agent 明确要求本验收采用独立新文件 scope，避免重复全套。
开发方完整回归结果不计入本文的独立 PASS 依据。

### 逐项覆盖与边界

| 功能点 | 独立结果及实际行为 |
| --- | --- |
| native sleep 暂停 | bounded PASS：直接输入脱敏实际 native shape，`item/started` 的 `item` 仅含 `type=sleep`、中性 `id`、`durationMs=43200000`，带中性 thread／turn；实际 watchdog 线程在已逾期 1201 秒的时钟下经过多个 tick，未锁存失败。错误 item ID 的 completion 不结束暂停 |
| matching completion 重计时 | bounded PASS：匹配 `item/completed` 后 `last_output_monotonic` 重置到事件时刻，立即检查仍存活；随后没有模型输出，实际 watchdog 在短测试预算后锁存 `llm-inactivity-timeout`。没有永久关闭 watchdog |
| sleep 归属 | bounded PASS：其他 thread、其他 turn 的 sleep start，以及普通 `commandExecution` item 均不暂停 timeout；同 ID 的其他 thread／turn completion 不得清除当前暂停，正确 completion 才解除 |
| 最终 timeout 锁存竞态 | bounded PASS：在真实 `_latch_runtime_failure` 入口启动第二通知线程，其非阻塞获取同一 `state_lock` 失败，通知不能在最终资格检查与 latch 之间完成；timeout 先取得锁时合法失败。另一个真实第二线程先完成 sleep 通知的用例，timeout 返回 False、无失败队列，继续保留 watchdog。没有使用同线程 RLock 重入注入来制造生产中不可达的交错 |
| typed 明确拒绝后的保存 | bounded PASS：结构化 `ok=false,error_code=batch_limit_exceeded` 经真实 `_decode_tool_result` 分类及 Runner 提交路径，intent 持久化为 `rejected`；没有该 intent 的 receipt。真实 `materialization_progress` checkpoint 保存成功，位置为 `rejected`、batch_id／receipt_ordinal 均为空；检查结果不把它列为 applied 或未决写入 |
| unknown 仍阻断 | bounded PASS：相同结构化 envelope 改为 `internal_error`，经真实 decoder 进入 unknown 路径，intent 为 `unknown`，保存拒绝 `checkpoint_write_unreconciled` |
| 普通异常仍阻断 | bounded PASS：普通 RuntimeError 即使文字含 `batch_limit_exceeded` 也不充当零写入证明；intent 仍 `submitted`，checkpoint 保存拒绝 `checkpoint_write_unreconciled` |

checkpoint 测试复用已验收的中性 unified plan／approval fixture，通过临时 Task 参数启用
checkpoint 合同。测试先创建一条独立的已结算 intent／receipt 作为历史 stand-in；断言
`completed_operations` 只有该历史 `idem-1`，没有把拒绝或未知结果伪造为完成。平台范围使用
既有 ScopeClient stand-in，平台快照 capture 使用既有临时 fixture；没有实际业务存储写入。
这里的保存 PASS 证明 Runner／文件包／检查合同，不能证明真实平台数据快照、恢复重放、
网络故障或服务端写入结果。

### 当前结论与确切缺口

以上运行功能边界均为 bounded PASS，未发现新的实证 High／Critical 缺陷。本轮没有等待
真实 12 小时 sleep：仅保留真实 native duration metadata，用实际线程和短计时验证生命周期。
实际 App Server／模型进程在重启后收到通知、长时间挂起与恢复、真实 silent provider timeout、
实际 run checkpoint 全链 reconciliation 和随后恢复，均未由本验收执行，保留 PARTIAL。
本功能证据不得替代语义验收；007／008／010 的已有有界功能结论不变，011 A5／A7 及四项
A10 仍保持上文的 PARTIAL，不据此宣布真实建模质量或 CQ 语义 PASS。
