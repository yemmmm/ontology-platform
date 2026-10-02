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

功能结果：008／010 的 A1—A9 在本次有界测试合同内 PASS；007 的 A1—A9 为 PARTIAL，
011 的 A1—A9 为 PARTIAL（共享变更／绑定漂移的业务重审证据不足）。
四项 A10 均未由本验收方执行，四项整体均为 PARTIAL。
未发现实证 Critical／High 产品缺陷。PARTIAL 项是确切覆盖缺口，不能反推产品失败。

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
