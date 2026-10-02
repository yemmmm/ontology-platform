# R4.0-010 数据映射开发与测试记录

日期：2026-10-02。权威范围为 [R4.0-010](../../requirements/requirements-v4.0.md#r40-010-数据映射视角与外部数据库关联)
及[详细设计](../designs/2026-10-02-r4-0-010-relational-data-mapping-design.md)。用户授权按设计完成开发和测试。
开发基线为 `6558ab5`，工作树开始时干净；本轮使用独立的 PostgreSQL／Oxigraph fixture，不读取外部业务行，不运行业务 SQL，
不启动真实 semantic modeling run。功能开发验证与独立功能／A10 语义验收分开记录，整体保持 PARTIAL。

## 实现与验证边界

- 复用四类既有映射资源及 CRUD，增加封闭的 mapping_definition 和 semantic_definition；
  TableMapping 支持普通共享定义，技术列不必声明业务属性，身份未知保持 null。
- 引用式 JoinMapping 明确表映射、复合列和角色；旧表名路径只有在来源及表唯一时可定位。
  编码含义按表映射、字段、属性和代码区分；指标保存选择的路径、统计身份、重复处理及转换规则，
  不生成 SQL、不默认 DISTINCT、不执行转换。JSON 对象键稳定排序，使 JSONB 重编译与原计划一致。
- 同一纯确定性检查用于 Batch 和 canonical write：检查引用、列／角色闭合、重复与反向依赖。
  最终写入取得 Project→Ontology→Attempt/fence 锁并重验；跨图范围只使用明确登记的引用 Graph Set。
  直接写入映射及其依赖必须进入既有 Batch；未知写入保留 fence，允许同一 Attempt 恢复。
- Graph Set 范围收缩及 supersedes 同样取得 Project／Ontology 锁、检查 fence 和最终引用完整性；
  有存量依赖时返回 mapping_reference_scope_in_use，先通过 Batch 修订依赖后可继续。
- 两种候选格式、统一审批投影、递归 definition_ref、拓扑排序及实际资源 kind 绑定同步更新。
  活动 Protocol MCP／Team Runner 使用新增合同；归档 p2a runner 保持 ARCHIVAL_ONLY。
  modeling-context→PlatformScope→Protocol prompt 提供实际 semantic_base_iri，活动工具使用宿主参数生成
  当前 namespace 的引用。跨切片范围桥接需要宿主显式选择 mapping_reference_direction；自由文本
  direction 不被自动解释成业务依赖方向，未选择桥接的既有 run 继续使用原范围。
- 四类列表／精确读模型、REST exact resource、Ontology MCP、Context Query full／compact 和导出
  保留新增结构；嵌套引用成为有方向的派生关联，复用现有访问过滤，不添加权限模型。
  精确资源优先使用完整的专属映射投影；entity-list／detail 排除四种映射类型，防止通用标签匹配
  遗漏 mapping_definition 与其嵌套引用授权检查。

## 开发验证覆盖

| 条款 | 证据与限制 |
| --- | --- |
| A1—A6 | 编译器与纯完整性测试覆盖普通定义／Class、两源同名表、技术列、复合键、自关联角色、作用域枚举、指标上下文、规则引用、单位／时间含义、未知／冲突、omit／replace／null 及准确主体。只证明合同与保存值，不证明业务数值语义 |
| A7 | 隔离 PostgreSQL／Oxigraph 测试覆盖获准／未获准跨图引用、删除反向依赖、预检查后依赖变更、两个 apply 交错、直接编辑／validate=false、Ontology 删除、范围收缩与 supersedes；RDF 已写但响应丢失时，其他映射写入被 fence 阻止，同一 Attempt 恢复后可继续 |
| A8 | 精确读、Context Query、MCP 与导出授权回归覆盖受限嵌套 IRI、隐藏端点不进入关联和分页计额；未修改 semantic_access 的权限语义 |
| A9 | 活动候选翻译／审批／读取合同、四类实际 RDF 主体与回执、公开 HTTP 读回／Context／导出；同步 REST／MCP 与活动 Skill／Task |
| A10 | 未执行。归 R4.0-009 后续统一授权的真实建模与独立语义验收；不以本轮 fixture 或平台合同 PASS 替代 |

主要新增测试：[应用边界](../../../backend/tests/test_relational_mapping_application.py)、
[公开 HTTP](../../../backend/tests/test_relational_mapping_http.py)、
[纯完整性](../../../backend/tests/test_semantic_mapping_integrity.py)、
[Team 合同](../../../modeling_team/tests/test_r4010_mapping_contract.py)。

## 回归与修订

首次后端全量为 1123 passed、47 skipped、5 failed。修复旧单图测试桩、semanticValue 反馈兼容、
被更新的残留错误不能被差分消掉，以及注解主体选择和候选属性 IRI 的兼容问题。
第二次为 1130 passed、49 skipped、2 failed，继续定位后两项准确主体／属性引用问题。
新增真实恢复测试发现 JSONB 重排导致 RDF JSON literal 不同，修复稳定序列化，保留故障注入回归。
独立只读代码审查指出活动回执入口、Graph Set 修改边界与 namespace 接线；修订后 Round 3
PASS，无 Critical／High。代码审查不算独立功能或语义验收。
公开 HTTP 测试初始化曾因缺少 project_id／bootstrap 参数失败；补齐隔离 Key 初始化。
fixture 曾遗漏既有指标必需字段及误用 entity_iri 查询参数，按现行合同修正。
实际 HTTP 发现精确读泛化模板遮蔽映射定义，修复专属投影优先及通用模板的类型排除；
35 项当前读取／授权定向检查通过，包含真实 SPARQL 执行和重复投影竞争回归。

## 最终结果

A1—A9 的实现与开发侧合同／功能验证 PASS。独立只读代码审查无 Critical／High；
独立功能验收与 A10 未执行，整体 PARTIAL。此处开发验证包含真实平台依赖和运行接口，
不包含业务数据语义判断或真实建模质量结论。

| 验证 | 当前结果 |
| --- | --- |
| 后端全量 | 1136 passed、51 skipped；256.89 秒。跳过项含默认关闭的外部／真实运行检查，不视为通过 |
| Team 全量 | 2106 passed、1 skipped、314 subtests passed；134.39 秒 |
| 最终 Runner／PlatformScope／R4.0-010 定向回归 | 64 passed、21 subtests passed；覆盖全量后最后的范围桥接条件修订 |
| 隔离 PostgreSQL／Oxigraph 应用边界 | 15 passed、1 skipped；72.39 秒。内存分支跳过行锁并发，真实 PostgreSQL 分支验证该行为 |
| 重启后的公开 HTTP 闭环 | 1 passed；24.57 秒。一个完整用例包含四类映射、普通资源共存、Batch 回放、Context、导出及活动回执工具 |
| 真实 checkpoint 存储回归 | 1 passed；1.68 秒 |
| 最终读取／授权定向检查 | 35 passed；包含真实 SPARQL 及四类精确读取竞争 |

可复用命令如下（从仓库根执行；后端运行目录为 `backend/`）：

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short --disable-warnings
env -u DEEPSEEK_API_KEY PYTHONPATH=.. RUN_RELATIONAL_MAPPING_LIVE=1 uv run pytest -q tests/test_relational_mapping_application.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. RUN_RELATIONAL_MAPPING_HTTP=1 uv run pytest -q tests/test_relational_mapping_http.py
env -u DEEPSEEK_API_KEY PYTHONPATH=.. RUN_CHECKPOINT_DATA_LIVE=1 uv run pytest -q tests/test_checkpoint_data_live.py
cd ..
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q modeling_team/tests
```

临时原始日志保留在 `/tmp/r4010-backend-final-final.txt`、`/tmp/r4010-team-closure.txt`、
`/tmp/r4010-runner-focused.txt`、`/tmp/r4010-application-final.txt`、
`/tmp/r4010-http-final.txt`、`/tmp/r4010-checkpoint-final.txt`、`/tmp/r4010-read-final2.txt`。
真实用例清理各自的 Project、Ontology、Graph Set、API Key、RDF 图及对应注册／版本行，
不清理他人资源，不把故障注入与恢复证据覆盖成无故障运行。

接口文档同步检查、Skill validator、修改的 JSON 解析、文档链接／围栏及 `git diff --check`
通过。修改后的后端 Python Ruff 检查通过；Team 三个既有文件仍有与 `6558ab5` 相同的
8 项 Ruff 问题（未使用的 import／local），没有借本需求修复，不声称全仓 Ruff 通过。

最终后端全量通过后重启 `ontology-platform.service`；2026-10-02 19:03:43 +08 起 active，
启动完成后 `/api/health` 返回 `{"status":"ok"}`，前端 5173 返回 HTTP 200。
最后公开 HTTP 用例在该次重启后的运行环境执行；之后仅整理测试格式与交付文档。
提交包含本需求代码、测试、活动合同与文档；提交 hash 以最终交付回复和 git 记录为准。

## 影响分析

GitNexus 的共享读取影响及 detect_changes 给出 CRITICAL；已向用户说明风险。
索引落后当前代码，部分符号与流程关联不可信，因此不声称图影响覆盖。
实际验证使用定向调用点检查、diff、完整后端及 Team 回归和真实依赖边界测试。
没有前端代码或迁移变更，不新增 UI／业务连接器／数据授权产品。
