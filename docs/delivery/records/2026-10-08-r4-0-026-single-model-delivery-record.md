# R4.0-026 Ontology 单图存储与 GraphSet 退役

## 范围与结论边界

权威范围：[R4.0-026](../../requirements/requirements-v4.0.md#r40-026-ontology-单图存储与-graphset-和来源图概念剥离)。
按 `requirement-delivery` 标准交付实施；本记录区分开发功能回归、真实本地迁移和接口验证。
未启动 semantic modeling run，未执行独立功能验收或独立业务语义验收；
不声明源忠实度、业务覆盖或问答质量已经通过，不改写历史冻结证据。

## 实施与最小设计

- Ontology 直接保存内部模型图位置、模型修订、内容哈希及显式跨 Ontology 引用范围。
  当前模型图由 Ontology 身份确定。Class、普通节点、定义、关系、映射和业务条件共用一张图。
  无 GraphSet 实体、默认 GraphSet、成员表或成员角色运行依赖。
- REST／MCP 的工作区、读模型、导出、查询、投影、Batch／Attempt 和恢复绑定 Ontology。
  旧 GraphSet／图管理入口删除；写入方无需选图，旧选择字段被拒绝。
  普通资源返回稳定 IRI 与 `ontology_id`，模型浏览用 Ontology 名称区分读取位置。
  七视角、关系、分页、不完整读取和版本一致性提示保留。
- 查询的授权过滤仍先于候选计数与关系遍历；跨 Ontology 映射引用只来自同一 Project
  的显式 `reference_ontology_ids`。缩小范围或删除仍被使用的共享定义返回可修正冲突。
- 单图中删除实体仅删除该实体的主体陈述，避免旧多图删除策略连带清除引用定义。
  同批次新增引用与删除冲突仍被检查；未知写入恢复按实际预期保留陈述核对。
  基础合同、lease／fence、确定性 dry-run／apply、读回与原子性机制继续保留。
- 当前候选、Protocol、关联自查、Task／角色／Skill、工具目录和交接状态按 Ontology 同步。
  旧冻结票据仅在测试读取边界作内存转换，原始文件不改写。
- 技术图注册／修订、审计和写入回执可保留内部图位置，供原子写入与历史恢复使用；
  它们不是业务图集合管理层。没有恢复 SHACL／OWL 或可执行规则能力。
  R4.0-027 的统一版本编号和重复版本机制清理未纳入本次改造。

## 迁移与恢复

迁移 `0034_ontology_single_model` 继承 `0033_subject_semantic_roles`。
先检查未收敛写入、同一业务定义冲突、目标位置冲突及跨 Ontology 引用归属，
完成全部合并校验后才写 RDF；冲突附资源、谓词、值及原存储位置，不任选一份。
仅合并显式业务类别 ontology／data／policy，不合并 Shape 或历史推理／规则派生结果。
写入后对实际 RDF 的规范化内容哈希核对，再提交 SQL；原 RDF 和受保护备份留作恢复依据。

- 隔离 PostgreSQL／Oxigraph 迁移演练两轮通过：从原 SQL 备份恢复、迁移、实际读回及清理。
- 本地实际迁移于 2026-10-08 完成，Alembic 为 `0034_ontology_single_model`，
  `semantic_graph_sets` 与 `semantic_graph_set_members` 已删除。
- 保留 Ontology `dbef2380-21c1-40ac-85c5-1c4013d8b7e9` 的当前业务图有 **1,428 个三元组**，
  模型修订为 **23**，只有一条当前 Ontology 图注册；业务资源 IRI 与归属保留。
  实际读回规范化哈希：`d21f7766491f731d1ca4d81a6423edc25badb1d32f743b63e28e489b8453d44d`。
- 旧可丢弃检索文档失效；新索引实际重建成功并为 current。
  job：`5927e81c-25b5-45d4-8a38-1af4f75137d3`，kind：`vector`，version：`semantic-retrieval-v1`，
  workspace version：`27cfb74e7cfc83e95fd7cc8c3cc293970032968ceb7992dbf0fd73e4727f01e7`。
- 本地受保护备份：`backend/.local/r4-0-026-migration/before-live-single-model.dump`，
  及该目录下按数据库／Ontology 保存的原 RDF JSON，文件权限 600；均不提交。
  迁移不支持自动 downgrade；回退须用留存 SQL／RDF 备份。
- 检查点格式改为 `r4-0-026-platform-data/v3`，保存当前模型图及 Ontology 状态；
  已验证旧 v2 文件先在内存中转换，再进行分叉。分叉按新 Ontology 重定位并保留业务 IRI。

## 验证与影响边界

- 后端：`cd backend && uv run pytest -q --tb=short`，最后完整轮次 **995 passed、55 skipped**，
  日志 `/tmp/r4026-full10.log`。新增单图创建／修复、合并冲突、引用范围、旧合同退役测试；
  原写入、授权、映射、恢复与检查点测试按直接 Ontology 运行。55 项跳过不记为通过。
- Team：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests --tb=short`，
  最后完整轮次 **2476 passed、10 skipped、304 subtests passed**，日志 `/tmp/r4026-team9.log`。
- 前端：`cd frontend && npm run build` 通过；`npx playwright test` **42 passed**，
  日志 `/tmp/r4026-frontend-build4.log` 与重启后 `/tmp/r4026-playwright4.log`。
  包括七视角／多读取位置／分页状态 UI 检查，以及真实 PostgreSQL／Oxigraph 的 Ontology
  写入、版本更新、受治理查询、资源列表、旧入口不可用和非法 graph selector 拒绝。
- Skill validator、接口文档同步、194 个改动 Python 文件语法、8 个 JSON 文件解析及
  `git diff --check` 通过；后端 `ruff check app --select F` 通过。
- 最终代码于 **2026-10-08 18:52:31 +08** 重启 `ontology-platform.service`，
  服务 active，8001 `/api/health` 为 `ok`，5173 为 HTTP 200。
  重启后实际保留模型的 workspace／resource-list／精确 IRI Context Query 均通过，
  返回正确 Ontology 位置且不含来源图字段；实际索引 manifest 为 current。
  日志 `/tmp/r4026-runtime-read3.log`。最初 probe 把投影版本误写为 kind，
  修正为现有 `vector` kind 后复核，不修改索引或平台以迎合错误断言。

测试日志保留在本机 `/tmp/r4026-*.log`。
早期失败包含旧成员角色、旧范围 fixture、候选摘要和共享图删除／恢复假设；
按退役合同更新断言，并修复真实单图删除和恢复遗漏，没有用后续成功覆盖原失败日志。
历史 start38 child-input fixture 恢复为 HEAD 原始字节，仅在测试内存中移除已退役绑定；
当前字段／摘要合同继续严格验证。对应测试文件复核 12 passed，
日志 `/tmp/r4026-retained-fixture2.log`。

GitNexus 索引落后当前代码 234 个提交，初始局部影响为 LOW。
提交前 `detect_changes(scope=staged)` 报告 CRITICAL（308 个符号、278 个流程、219 个检测文件），
同时返回损坏的符号 ID；编辑前已向用户说明，不能视为完整图影响覆盖。
以当前调用点、diff、完整回归、隔离迁移和真实接口核对读写、授权、检索、检查点和恢复路径。


A1–A6 的开发功能证据由以上回归、实际接口、迁移读回与检查点测试提供。
独立功能验收和独立业务语义验收未执行；此记录不将功能 PASS 等同于模型质量 PASS。
