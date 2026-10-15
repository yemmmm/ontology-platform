# R4.3-024／025 实现与测试记录

## 范围与授权

用户要求完成 R4.3-024 实现与测试，并明确确认一并完成 R4.3-025 必要能力。
权威范围为 [024](../../requirements/requirements-v4.3.md#r4-3-024)、
[025](../../requirements/requirements-v4.3.md#r4-3-025) 及两条已验收设计。
025 按后续提交 `db90f8e`、`f10bd28` 明确的 compiler／Executor／Runner 绑定边界对齐。
本轮工程测试使用隔离合成资源，不调用建模 provider、不恢复暂停生产、不消费建模轮次。
真实 Modeling 自查效果、最终独立 Consumer／Judge 语义验收及提速仍需另有运行授权。

工作区无关 `docs/presentations/`、`slide-deck/` 保留。并行设计文档提交不与本轮代码混合。

## 实现范围

- REST／MCP 新模型 Batch 仅允许 apply；服务在编译／持久化前拒绝 dry_run。
  保留历史 Batch／Attempt／Finding、数据库历史 mode 值、迁移／投影自己的 dry-run。
- 当前统一图不可变候选及显式变更意图由纯 compiler 生成有序批次与字段 source_map；
  不经过旧候选翻译、Agent 手写计划或翻译审批／dry proof 门。
- Modeling 原生私有能力负责身份、获准候选／资源引用及真实拓扑绑定；执行器通过现有
  Session／lease、Batch apply、intent／receipt／Attempt 保存单批原子应用事实。
- 三个 Modeling 只读工具限定当前 Project 与 run 实际获准 Ontology 集合，支持现行
  查询参数、多次问题及 IRI 展开；后端校验游标、修订、索引与权限。
- 最终关联检查复用完整治理分页与既有辅助；成功回执、自查、未交付缺口和独立验收分开。
  Task／角色／Skill／reference 同步当前路径；历史暂停 run 不热切或自动恢复。

## 开发测试轮次

以下是开发验证，不是独立功能或业务语义验收。

| 轮次 | 范围 | 结果与处置 |
| --- | --- | --- |
| R0 | 只读代理前置改动 | 定向 9 passed；当时 Team 2970 passed、12 skipped、318 subtests passed。后续代码已变化，不能作为最终全量证据 |
| R1 | 新路径接入中的 Team 全量 | 77 failed、2912 passed、12 skipped、316 subtests passed；主要为仍期待新 dry-run 成功／隐藏双执行／旧角色提示的活跃断言，另有新增 Task 引用 YAML 格式问题；正在按新合同更新与回归 |
| R2 | 后端退役聚焦 | 159 passed、35 skipped；REST／MCP／service 拒绝、历史读取和合法 apply 无隐藏 dry-run；全量最终结果待集成完成后复验 |
| R3 | 原生 Modeling 能力到真实应用服务 | SQLite 持久化与实际 rdflib Dataset；2 passed：原子 apply、真实资源及修订、未知说明进入 RDF、NL／IRI 治理读取、索引失败与写入分离、成功不重放、空标签写前拒绝及同目标修正。后续跨批绑定重构后须复验 |
| R4 | 新建 create scope 与真实工具目录 | 2 passed：不从尚未绑定的 run.scope 猜身份，使用已准备真实范围；原生 Modeling catalog 与 Runtime descriptor 一致，其他角色不能调用 Modeling 私有能力 |

集成中保留的首层问题：私有 schema 缺 type 导致写前拒绝；执行器将非阻塞
missing_rationale 提示误作执行失败；空 label 未在转换期拒绝。均已据实际反馈修正，
没有据此推导建模质量。旧测试的预期变化不改变历史已保留裁决。

## 最终验证与状态

工程实现与开发验证 PASS。最终 Team 全量 3017 passed、12 skipped（349.39s），
日志 `/tmp/r4324-team-final-verified.log`；后端全量 1204 passed、56 skipped，
后续新增／更新的 core 与真实应用服务联合回归 59 passed。

2026-10-15 08:58 +08 按仓库要求重启 `ontology-platform.service`，单元 active；
后端 `/api/health` HTTP 200，前端 `5173/` HTTP 200。重启脚本中的前端构建完成；
未改前端源码，不要求另跑 UI suite。匿名 `/openapi.json` 与 `/api/modeling/batches`
均 HTTP 401，保留既有鉴权；以当前运行 checkout 的 `app.openapi()` 核对
`ModelingBatchSubmit.mode` 仅含 `apply_atomic`／`apply_partial`，实际 REST／MCP
拒绝和历史读取另由上述开发回归证明，没有写入本地生产模型做探针。
不以当前开发测试或设计 PASS 宣称 024 A8／A9、025 A10 的真实采用、语义质量或提速通过。

## 后续回归与实际边界修正

- 后端全量 `cd backend && uv run pytest`：1204 passed、56 skipped（849.98s）；
  日志 `/tmp/r4324-backend-full.log`。外部依赖／live 条件跳过保持，不宣称其运行验收。
- Team 回归从 77 failed 收敛至 42 failed、再至 20 failed；保留日志
  `/tmp/r4324-team-current.log`、`/tmp/r4324-subagent-team.log`、
  `/tmp/r4324-subagent-team-final.log`。旧 dry-run 正向断言改为 apply／拒绝断言，
  历史 proof 解析继续验证；未删除历史证据。最后一轮暴露合法 v1 Task 的
  `parameters=None` 在新 baseline 代码上报错，修复为按既有可空合同读取。
- 真实应用服务集成增至 10 passed（`/tmp/r4324-integration-latest.log`，后续 fact
  读取适配单项又通过 `/tmp/r4324-fact.log`）；包括实际两 Ontology 跨批关系、
  真实 IRI 治理周边及最终完整关联扫描；容量跨批；实际 receipt Pointer 更新、
  旧修订／伪造引用拒绝；同批末项失败不产生部分 RDF 写入；成功 update/delete
  重复调用复用原编译计划和回执；删除前完整 incident statement 读与既有 impact
  receipt；先创建属性再用实际 IRI 绑定 properties 键，IRI 文本仍为 RDF literal。
- 补齐真实 `PlatformScope` 的范围语义：`authorized_ontology_ids` 是初始集合，
  当前准备完成的 `ontology_ids`／单 Ontology 才包含本轮已获准创建的拓扑结果。
  执行器不得因初始列表为空或不含新增 Ontology 拒绝合法范围。
- compiler 保留 `schema_source=null` 的既有语义，区分当前资源技术身份和合法关联
  资源引用；引用仅在声明槽位解析。不能同批引用的动态属性键通过 sidecar 保留，
  依赖成功后在 Runner 绑定真实 key，Executor 不解析资源引用。
- 相同 candidate reference 或同 candidate_id/revision 变更内容写前拒绝；变更以
  新不可变修订继续。相同提交重试先复用已留存绑定计划，防止自己的成功更新／删除
  使原目标读取变旧后阻断成功缓存。新提交仍作当前获准绑定及修订校验。
- API 核心使用现有数据库与 rdflib DatasetStore，不调用 provider；fixture 的
  wildcard delete 已按 RDF 模板修正，不能用只加入新 label 的断言掩盖旧值残留。


## 最后集成回归与独立代码复核

- 中间稳定版本 Team 全量 3016 passed、12 skipped、318 subtests passed，
  日志 `/tmp/r4324-team-verified.log`；随后发现的真实配置边界继续修复，最终结果另列。
- 当前 core／native 联合回归 59 passed（28.50s），日志
  `/tmp/r4324-core-native-final.log`；其中真实应用服务用例 12 项，覆盖七类 kind、
  两 Ontology／容量拆批、source_map 原字段定位、真实 RDF 读回、原子拒绝、
  工具持有删除影响回执、动态属性键、成功 update/delete 不重放，以及应用成功但回包
  丢失时通过原 Batch／Attempt 对账，不新建重试身份。
- Task/profile 邻接回归 245 passed、gate 聚焦 121 passed／16 subtests、
  Task 邻接 73 passed。九个现行统一图 Task 的 objective 与资料引用已同步直接提交，
  保留其业务、CQ、授权及恢复边界。
- 独立代码复核先指出宿主 `McpReadForwarder` 未接受对账所需 get/list Batch。
  已新增精确的宿主内部读取 schema，未加入 Modeling／Examiner 公共目录；
  实际 MCP inventory 与隔离回归 37 passed，窄复核 PASS。
- 后续独立复核指出可选 Protocol Profile 与原 Task 资料角色冲突。现行 loader 仅对
  direct selector 接受可选 Protocol 资料声明；角色、通信及能力仍来自真实 Profile。
  源材料装载、manifest 与可见性探针仅使用实际角色交集，不创建缺席 Protocol 的目录。
  两角色回归直接使用真实 Task 的全部 role_sources，含实际 prepare／probe，4 passed，
  日志 `/tmp/r4324-optional-role.log`；legacy 三角色依赖仍保留。独立窄复核 PASS，关闭该 High；无新增 Critical／High 阻断。
- GitNexus 已做影响及变更分析；Batch／读转发与 loader 影响风险已提前提示。
  最后变更汇总为 critical（72 changed symbols、267 affected、81 files），但索引陈旧且
  尚未覆盖新增模块，并存在 diff 符号归属偏差。该结果只作风险导航；通过定向调用点、
  完整 diff、开发回归及独立窄复核补充，不能宣称完整图覆盖。
- 新模块及变更合同的 Ruff、`git diff --check`、JSON／YAML 解析、文档本地链接与
  `ontology-modeling` skill validator 已通过；没有前端代码变更。


所有本轮实现、相关测试与文档按拥有路径提交；无关未跟踪目录保留。
独立代码复核与工程开发验证不替代业务语义验收；024 A8／A9、025 A10 保持 UNVERIFIED。
