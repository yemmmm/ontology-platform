# R4.0-025 专用校验、推理与规则合同退役

## 范围与结论边界

权威范围：[R4.0-025](../../requirements/requirements-v4.0.md#r40-025-校验推理与业务规则专用建模能力阶段性退役)。
按 `requirement-delivery` 的标准交付执行。开发功能、当前合同与真实接口验证分别记录；
这些证据不等于独立业务语义验收，不提升历史 PASS／PARTIAL／REVISE。
本轮没有真实 semantic modeling start、LLM 建模或外部业务调用。HTTP 验证使用隔离测试资源。

## 实施决策与实际变更

1. 删除 SHACL／OWL 引擎及 Shape CRUD、生成／合并／指导服务、专用业务规则注解适配器，
   删除相应 REST／MCP 入口、DTO、工具策略、调用分支、运行配置和 `pyshacl` 依赖。
   通用图导出、读取、Context Query 和投影不再拼接 Shape／推理结果图。
   当前 `assertion_types` 仅接受 `asserted`；自动推理读取模式和专用读取模型不可用。
2. 普通业务规则继续使用已有概念／实体、`semantic_definition`、属性和关系表达。
   条件、阈值、计算口径、范围、例外和未知仍是业务内容。
   专用 `rule_definition` 写入或候选转换返回可定位错误，不静默丢弃。
   存储中的普通 RDF 词汇、显式类／层级／关系与原始脚本说明不按名称删除；
   历史脚本字面量可按普通受治理事实读取，compact 不再作脚本专用省略。
3. 保留原有必要字段／格式／引用检查、权限、版本、lease、确定性 dry-run／apply、
   原子写入、审计、实际读回、checkpoint／恢复与独立业务语义判断。
   原 `CanonicalShaclViolation` 同时承载映射合同错误，因此改名为
   `CanonicalValidationError` 并保留映射错误反馈，未连同 SHACL 删除基础合同校验。
4. 当前 Team Task／Profile／角色／Skill、候选、Protocol、工具目录、代理目录、
   启动和隔离配置同步退役。交接 schema 改为
   `r2-3-005-acceptance-stage-handoff/v2`，仅绑定 dry-run、apply、readback；
   显式选择和自动选择均保留原有 scope、nonce、候选、状态、回执及篡改校验。
   完成检查用 `deterministic_write_readback` 代替专用验证／推理检查。
   Protocol 无旧 OWL 脚本挂载、环境变量或启动前文件依赖。
5. R2.3-003／005／008 acceptance standard 的 v1 文件保留原字节，
   当前 Task／Profile 和正式运行合同改用独立 v2 文件。CQ 内容及顺序保持一致。
   冻结旧票据不会被改写或自动当作新合同的完成证据。

## 保留／删除依据

| 对象 | 本次决定 | 依据 |
| --- | --- | --- |
| 引擎、专用 Shape／规则适配器、运行入口与专用 DTO | 删除 | 属于明确退役能力，当前读取与写入无保留调用需求 |
| validation／reasoning run、derived pointer 等数据库模型和既有迁移 | 保留 | 历史记录、checkpoint、来源追溯及资源清理仍依赖它们；不创建新引擎运行、不提升有效指针 |
| GraphSet、成员、图版本与共享失效／资源清理机制 | 保留 | 当前写入版本、投影、恢复仍依赖；R4.0-026 单图剥离是另一条需求 |
| 默认四成员工作区中的历史 Shape 成员 | 保留结构，新建成员不可直接编辑 | 避免改写共享恢复结构；图类别写守卫拒绝专用 Shape 图维护，当前读取排除其内容 |
| 旧指针／投影记录 | 保留存储 | 当前 describe／scope 不暴露专用有效指针，新投影输入为空；含退役派生输入的旧投影不当作当前来源投影 |
| 冻结 fixture、业务材料、旧标准、历史报告与工作区证据 | 保留 | 不改写题集分母、原始证据或验收结论；现行测试仅在内存中投影保留能力 |

未执行数据库迁移、历史模型清理、全库 RDF 删除或单图迁移。未新增替代引擎或兼容模式。

## 影响与检查边界

GitNexus 索引为旧快照，落后当前 checkout 233 个提交。
`SemanticValidationService` 初始影响为 LOW；`validate_compiled_command` 为 CRITICAL。
提交前 `detect_changes(scope=staged)` 也返回 CRITICAL（99 个索引符号、270 个受影响流程，
156 个检测文件）。已在编辑／提交前向用户说明。
主要路径包括普通语义编辑／canonical write、图导出、Context Query／投影与 Team 交接。
旧索引仍含已删除的 reasoning 入口，因此用当前调用点、diff、完整回归和真实接口核对，
不宣称完整图影响覆盖；不为本次退役重建索引。

## 验证与失败保留

日志位于本机 `/tmp/r4025-*.log`。早期轮次包含旧正向合同断言失败和实际遗漏：
共享 ID 输出绑定方法误删后恢复；启动与隔离依赖、代理目录、显式交接 schema、
投影输入及导出拼接分支遗漏均已修正。保留这些失败记录，不以末轮结果覆盖失败原因。
测试更新移除退役能力的正向要求，并增加不可调用、普通业务内容与必要防护对照。

- 后端：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q`。
  最后完整轮次：1026 passed、55 skipped；含原始脚本说明与导出分支退役对照。
  此前额外定向检查 2 passed，末轮已收录这些测试。
  skipped 是未启用的既有 opt-in／环境相关测试，不代表已通过。
- Team：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests`。
  最后完整轮次：2478 passed、10 skipped、310 subtests passed。
- 真实接口：`RUN_R4025_HTTP=1` 的隔离 PostgreSQL／Oxigraph／HTTP 测试通过。
  验证旧运行入口 404、退役读取模型／推理模式不可用，普通工单规则含条件与未知可保存、
  原子坏批次无写入、修正后 dry-run／apply、重复 apply 幂等、实际读回／Context Query、
  保护集不泄露及只读 key 拒绝写入。最终服务重启后复测：1 passed。
  API key、用户、Project、GraphSet、registry／revision
  与命名图在 finally 中清理。
- Skill validator：`python modeling_team/skills/ontology-modeling/evals/validate_skill.py` 通过。
- 接口文档：`scripts/sync-interface-docs.py --check` 通过；JSON／YAML／Python 格式及
  `git diff --check` 均通过；后端 `ruff check app --select F` 通过。
- 服务：后端完整测试通过后于 2026-10-08 17:13:43 +08 重启
  `ontology-platform.service`；状态为 active，后端 8001 `/api/health` 返回 `ok`，
  前端 5173 返回 HTTP 200。未修改前端代码，不增加前端测试范围。

A1–A5 的证据为上述开发合同／回归和隔离真实接口验证。未运行真实建模，
未做独立功能验收或独立业务语义验收，不声明模型质量 PASS。
