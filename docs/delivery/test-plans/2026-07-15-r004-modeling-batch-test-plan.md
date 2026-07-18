# R-004 外部 Agent 建模批次测试计划

**Date:** 2026-07-15
**Requirement:** `docs/requirements/requirements-v1.0.md` R-004
**Design:** `docs/delivery/designs/2026-07-15-r004-modeling-batch-design.md`

## 1. 测试顺序

1. Migration 与模型约束；
2. Handler、引用、依赖、冲突和 Validation Finding 服务级单测；
3. Batch/Attempt/Lease/fence/恢复服务级测试；
4. REST 与 MCP 契约测试；
5. PostgreSQL + Oxigraph 集成测试；
6. 前端 build、R-004 定向 Playwright、全量 Playwright；
7. systemd 重启和真实健康检查。

测试 Agent 应复用本计划，不重新缩小验收范围。

## 2. 持久化与幂等

- `0023`/`0024`/`0025` 从此前 Alembic head 升级成功，约束、索引和已有 Ontology 工作区回填存在；
- 相同 Session + `client_batch_id` + 相同内容返回原 Batch；内容变化返回
  `batch_content_conflict`；
- 相同 Session + idempotency key + 相同 Attempt 请求返回原 Attempt，不增加 audit、revision、
  Evidence 或 RDF 写入；请求变化返回 `idempotency_conflict`；
- 不同 Session 复用全部客户端 ID 时得到不同全局资源 ID；同一 Batch 的多次 Attempt 保持相同 ID；
- 并发相同 key 提交只建立一个 Attempt，并发首次创建相同 Batch 只建立一份 Items；
- Batch 终态后新 apply key 返回已有结果，不重复应用；
- 不可恢复 Attempt 使 Batch 进入 `failed`，普通 apply 不能重新开放它；
- Items、Attempts、Item results 和 terminal findings 不能通过 R-004 API 修改或删除；
- 请求/内容哈希、审计、Finding 和上下文中不出现 Lease token。

## 3. 模式与校验

- dry-run 无 Lease 可成功，保存 Batch/Attempt，但不写 RDF、Rule、Evidence Reference 或
  Evidence Association；
- applying/recovering fence 存在时，新 dry-run 和新 apply 均拒绝；GET 详情只观察，不触发恢复；
- apply 无 Lease、旧 token、过期 Lease、错误 workspace version 均在副作用前失败；
- `apply_atomic` 任一 Item error 时没有 Item 被写入，状态为 failed/not_applied；
- `apply_partial` 只应用稳定成功子集，失败和 blocked Item 不遗留任何副作用；
- warning 不阻断，error 必须阻断；不存在 force/validate=false/ignore_warnings 绕过；
- 顶层错误使用 HTTP/MCP error，Item/Group/Batch Findings 使用正常 Attempt 响应；
- item 数、请求字节、Evidence 数和 excerpt 长度超限返回 actual/limit，且零副作用。

## 4. Handler、目标和引用

- Class、Property、Relation Type、Shape、Entity、Relation、Fact、Mapping 和 Rule Definition
  首版命令均有 create/update/delete 的适用覆盖；不支持的变体返回稳定 Finding；
- payload 中的 ontology/Graph Set/graph IRI/shape graph/actor 覆盖被拒绝；
- 平台按 Ontology Workspace 和命令种类解析目标角色；缺失、重复、locked 或跨 Ontology 工作区
  在写入前失败；
- dry-run 与 apply 为建立项生成相同 resource ID/IRI；相同请求重试不产生新 ID；
- `resource_id`、`item_ref.resource_id` 和 `item_ref.resource_iri` 正确解析；缺失输出、跨 Batch
  或未知 Item ref 返回可归因 Finding；
- 显式 depends_on 与隐式 item_ref 依赖均参与 SCC；数组重排不改变资源 ID、delta hash 或结果顺序。

## 5. 循环、冲突和 partial 固定点

- 自引用和两个/多个 Item 循环在领域有效时可 dry-run/apply；
- 循环 SCC 在 partial 中全成全败，组外独立项不受影响；
- 失败依赖沿 group DAG 传播为 blocked；
- 兼容的同资源不同 slot 合并；完全重复 effect 只写一次并产生 `duplicate_effect`；
- 同单值 slot 不同值及 update/delete 冲突产生 `conflicting_item_effects`，不受数组顺序影响；
- 多值 slot 的不同成员可以合并；通配 delete 和 Entity/Class 级联删除 footprint 能阻止与被删
  属性、入边、出边或从属资源的并发更新；
- 移除首轮失败组后重新校验产生的二次失败继续收敛；
- 无法归因的 batch SHACL error 阻止 partial 猜测应用。

## 6. Evidence、能力问题和 Rule

- 已有及内联 Evidence 在 dry-run 只解析候选，在 apply 只绑定 applied Item；
- failed、blocked、not_applied Item 不创建 Evidence Reference/Association；
- 同一 Evidence 支持多个 Item 时分别关联 `modeling_item`；
- Evidence 不存在、跨 Project、格式错误是 error；无 Evidence 是 warning；
- 两个 Ontology 并发解析相同内联 Evidence 时按 project 内容唯一键 upsert，最终只存在一个
  Evidence Reference，两个 Item Association 均指向实际 Reference ID；
- rationale 与 Evidence 分开返回和审计；无 rationale 是 info；
- 能力问题不存在、跨 Project 或显式 Ontology 范围不匹配是 error；
- Rule create 绑定 Ontology；可执行内容 update 形成新版本并保留旧版本；delete 标记 inactive；
- 逻辑 Rule ID 在版本更新中稳定，current definition 原子切换，旧 Definition 为 superseded；
- Rule 与 RDF Item 混合批次遵守 atomic/partial 和恢复语义。

## 7. 写入栅栏和恢复

- Attempt 进入 applying 前已持久化 plan、delta hash、最终 Item 集和 fence；
- fence 存在时 Lease acquire/rotate/release、Session complete/cancel 和其他 canonical write 被拒绝；
- apply 开始后 Lease 自然到期，原 Attempt 仍可完成或恢复，其他 Session 不能穿透；
- 正常终态释放 fence；
- 进程停在 `applying` 后重启：未过期 claim 不并发重放，claim 超时后相同 key 串行接管；
- fence 与其他直接 canonical write 并发时只有所属 Attempt 可写；
- 模拟 RDF 未写、已完整写、部分可幂等收敛、SQL commit 丢失四种故障，相同 key 恢复原 Attempt；
- 恢复不重新编译、不生成新 audit/resource/association ID、不无条件清图；
- 发现计划外 revision/语句时保持 recovering 并返回人工处置诊断；
- Build Context、Batch detail 和 Modeling Context 能观察 recovering/fenced 状态。

## 8. 当前上下文和查询

- Modeling Context 只从当前工作区/读模型计算版本、计数和 stale 状态，不回放 Batch；
- Rule-only 变更也改变组合 `workspace_version`；Build Context、Modeling Context 和 apply guard
  返回同一版本算法的结果；
- Batch 按 Session 和 Ontology 跨 Session 分页，状态/时间过滤稳定且无重复漏项；
- Batch detail 同时返回 client/platform IDs、全部 Attempts、Items、Groups、Findings 和恢复历史；
- submit/detail 的完整诊断返回目标 graph IRI、角色、逐图前后 revision 和前后 source signature；
- Ontology-scoped read-model endpoint/MCP 工具无需调用方提供 Graph Set ID，且结果与现有固定
  read-model service 一致；
- 成功 apply 更新 workspace version、图修订、来源签名、Build Session activity，并将相关派生
  pointers 标记 stale，但不执行推理、Rule run 或投影 rebuild；
- 普通 Modeling Context/列表不返回 Lease token、Graph Set ID 或 graph IRI；完整 Batch audit 中
  只读目标诊断按设计返回。

## 9. REST、MCP 和前端

- REST 和 MCP 的 submit/get/list/context 状态、Finding code 和幂等结果一致；
- MCP catalog 只新增一个建模写工具，其余为读工具；
- Build Context Debug 可从 Workspace 展开 Modeling Context，并查看真实 Batch/Attempt/Finding 摘要；
- Debug 页面无 POST/PATCH/DELETE、apply/retry/edit 按钮；
- raw JSON 递归过滤 token、凭证、Graph Set ID 和 graph IRI；
- 加载、空状态、分页、错误状态和 recovering/stale 诊断有 Playwright 覆盖。
- 请求 payload 不能伪造 actor；R-008 未实现时响应/审计使用内部未归因 actor，并且文档明确
  该端点尚不可作为不受信网络的生产授权边界。

## 10. 必跑命令

```bash
cd backend && uv run alembic upgrade head
cd backend && uv run pytest
cd frontend && npm run build
cd frontend && npx playwright test tests/build-context-debug.spec.ts
cd frontend && npx playwright test
git diff --check
systemctl --user restart ontology-platform.service
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
```

若外部依赖导致某项无法运行，必须记录原始错误、已运行的较窄检查和未覆盖风险，不能把未执行项
写成通过。
