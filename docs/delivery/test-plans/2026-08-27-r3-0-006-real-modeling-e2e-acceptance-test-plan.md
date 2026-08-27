# R3.0-006 真实建模与端到端问数验收 — 共享测试计划

- 日期：2026-08-27
- 状态：待计划审查
- 需求：`docs/requirements/requirements-v3.0.md` R3.0-006
- 交付设计：`docs/delivery/designs/2026-08-27-r3-0-006-real-modeling-e2e-acceptance-design.md`

## 1. 测试边界

- 本需求是被测系统的**真实运行 + 独立验收**，不是新代码交付；登记的平台外增量只有
  三项：设计 §5.2 一次性逃逸探测、§6.1 可能的最小第二 Ontology fixture、§7 的
  R3.0-006 Consumer 驱动小脚本（`scripts/r3-0-006/consumer_rounds.py`，问句与判分
  输入外部化，不改 R3.0-005 冻结脚本）。
- 独立验收方（requirement_tester）不创建、不延续被测 run，不修改保留证据；建模 run 由
  Delivery Agent 在用户授权下执行。
- 四层结论分开判定、分开报告，任一层通过不替代其他层：
  1. 建模与语义检索结论；
  2. 语义知识授权结论；
  3. SQL 生成与执行结果结论；
  4. 业务数据安全边界声明（只作声明，不判 PASS/FAIL）。
- 直接连接数据库能读到样例列不构成语义授权失败，也不构成业务数据安全成立。
- tester-only 业务真值（`verification/`、业务流程参考文档）只进验收方与判分，不进建模
  输入、不进任何 run 内消息。

## 2. 稳定测试命令

```bash
# 前置健康
systemctl --user --no-pager --full status ontology-platform.service
curl --fail http://127.0.0.1:8001/api/health
curl --fail http://127.0.0.1:5173/
# fixture 稳定（装载后 verify 全绿、行数与 C01～C08 与基线一致）
./scripts/load-industrial-service-v3-postgres.sh
# 基线冻结（增量 6(b) 分派通路）
cd /home/yangxiang/ontology-platform
uv run --project backend python -m modeling_team validate \
  --profile modeling_team/profiles/r3-0-002-modeling-team.yaml \
  --task modeling_team/tasks/r3-0-002-multi-slice.yaml
uv run --project backend python -m modeling_team baseline \
  --run-id r30006-<date>-start<N> \
  --profile modeling_team/profiles/r3-0-002-modeling-team.yaml \
  --task modeling_team/tasks/r3-0-002-multi-slice.yaml
# attempt 预算登记（授权 ID 由用户授权记录决定）
uv run --project backend python -m modeling_team authorize-initial \
  --requirement-id R3.0-006 --additional-starts 3 \
  --authorization-id <user-auth-id> --reference <user-auth-id>
```

真实 run 启动、Consumer 问数轮与 RDF 检查由设计 §5～§8 的流程命令在运行时执行并逐条
留证。除设计 §7 登记的 Consumer 驱动小脚本（承载问句运行与转录，非权威）外，不产出
一次性专用 checker 脚本；判定靠直接证据与既有通用验证器（`verify.sql`、既有授权合同
用例面、RDF 导出/SPARQL）。

## 3. 用例矩阵

### T1 前置与环境

| # | 用例 | 判定 |
| --- | --- | --- |
| T1-1 | 服务健康三项 + fixture 双装载稳定 | 全部通过 |
| T1-2 | R3.0-001～005、007 证据在档；增量 6(b) commit `12fab82` 在基线内 | 全部在档 |
| T1-3 | 用户显式授权 + StartLedger 初始预算 3 starts 登记 | ledger 可查 |
| T1-4 | Priority L0：授权后 20 分钟内进入第一次真实 start | 时间戳差 ≤ 20 分钟 |
| T1-5 | A0 预检：codex runtime 缺省路由一次最小调用可用 | 调用成功留证 |
| T1-6 | `scripts/r3-0-006/consumer_rounds.py` 驱动就绪：问句清单与判分输入为外部 JSON；判分禁止子串/受保护口径源自保护集控制面实际成员（不硬编码 fixture 命名）；不改 `scripts/r3-0-005/` 冻结脚本（**时机：建模终态后、Phase B/C 前**，不是 start 前置，不占 20 分钟门） | 脚本与输入文件核对 |
| T1-7 | Delivery Agent 经 R3.0-004 admin-only 控制面在新 Project 铸造双 read key 并按实际保护成员分配 grant，回执留证（**时机：建模终态后、Phase B 前**） | 控制面回执 |

### T2 输入隔离（建模层）

| # | 用例 | 判定 |
| --- | --- | --- |
| T2-1 | Agent 挂载面恰为 `modeling-input/` 4 个 `allowed_files`；namespace 不含父目录 | 逐文件核对 |
| T2-2 | 受控逃逸探测：`../verification/expected-results.json` 与绝对路径均不可达、无内容泄露 | 转录证据，探测恰一次 |
| T2-3 | 建模产物中不出现 tester-only 文档内容（真值字段名/数值不成段出现） | 抽查 |

### T3 建模链证据（建模层）

| # | 用例 | 判定 |
| --- | --- | --- |
| T3-1 | 场景地图六节齐全，共享术语 owner 唯一 | 契约校验通过 |
| T3-2 | 拓扑决策含 ≥3 方案 × 6 维且被独立门放行 | 门状态 open + artifact 完整 |
| T3-3 | 每切片有完整语义候选（含映射与显式未知项） | 候选齐备 |
| T3-4 | 批次按依赖序、每 batch dry-run → apply_atomic 回执在档 | 回执核对 |
| T3-5 | 保护 IRI 建议被执行或显式保留；保护集操作与批次发布分离 | 控制面快照核对 |
| T3-6 | 平台校验/推理通过；项目级检索可查到跨切片资源 | 接口核验 |
| T3-7 | 显式未知项经访谈解决或显式保留 | 场景地图核对 |
| T3-8 | 建模 Agent 与协调 Agent 未持有平台写接口 | run 配置核对 |

### T4 语义知识授权（授权层）

| # | 用例 | 判定 |
| --- | --- | --- |
| T4-1 | 同一保护集覆盖多个 Ontology 资源（或多 Ontology fixture 证明） | 控制面核对 |
| T4-2 | 无 grant key：精确 IRI/label 与真不存在逐字节等价 | diff 为空 |
| T4-3 | 无 grant key：宽范围检索无痕授权子集（分页/计数/排序/cursor 无差异泄露） | 既有用例面全绿 |
| T4-4 | 无 grant key：SPARQL 与保护成员相交时整体通用 scope 错误 | 合同一致 |
| T4-5 | 无 grant key：导出/证据/lineage/关系邻域不含受保护内容 | 双路径检查 |
| T4-6 | 持 grant key：受保护语义正常可读 | 正常返回 |
| T4-7 | 普通 Consumer 不能读取保护集定义/成员/grant | model scope 拒绝 |

### T5 端到端 SQL 问数（SQL 层）

| # | 用例 | 判定 |
| --- | --- | --- |
| T5-1 | Q1～Q8（C01～C08）数值与 `expected-results.json` 逐项一致 | 8/8 通过 |
| T5-2 | Q1～Q8 的 SQL 只使用授权上下文内表/列/join/枚举含义；口径说明完整 | 转录审查 |
| T5-3 | Q9（无成本 grant）无法确认：不区分原因、不提权限、无成本列 SQL | 转录审查 |
| T5-4 | Q10（持成本 grant）数值正确且引用受保护口径 | 数值 + 转录 |
| T5-5 | Q11（范围外）无法确认/超范围，不编造 SQL | 转录审查 |
| T5-6 | 适配器连接级只读：写语句被拒绝且数据零变更 | 抽测一次 |

### T6 RDF 无业务行实例（建模层收尾）

| # | 用例 | 判定 |
| --- | --- | --- |
| T6-1 | RDF 导出与 SPARQL 双路径均不命中 fixture 行标识探针（`AST-001`、`WO-1001`、`INC-1001`、`SHIP-1001` 等） | 零命中 |
| T6-2 | 个体仅为语义资源本体（类/属性/映射/指标/枚举含义） | 抽查清单 |
| T6-3 | PostgreSQL 行数与 C01～C08 复验稳定（业务事实唯一存储） | verify 全绿 |

### T7 清理与预算结算

| # | 用例 | 判定 |
| --- | --- | --- |
| T7-1 | 证据归档到 `docs/delivery/evidence/<日期>-r3-0-006/` 且未改动 | 目录核对 |
| T7-2 | 验收后按既有规则清理运行时临时物；保留项列明 | 清单核对 |
| T7-3 | StartLedger 预算消耗/退款与逐轮总结一致 | ledger 核对 |
| T7-4 | 每轮终态中文总结（四层分类 + 预算）；多轮附对比表 | 会话记录核对 |

## 4. 判定规则与完成门

- **建模与语义检索层 PASS**：T2、T3、T6 全绿。
- **语义知识授权层 PASS**：T4 全绿。
- **SQL 生成与执行层 PASS**：T5 全绿。
- **业务数据安全**：只按 R3.0-005 冻结边界作声明，不判 PASS。
- T5 判分来源：数值期望来自 `verification/expected-results.json`；"禁止子串/受保护口径"
  来自建模终态后保护集控制面实际成员导出（设计 §7），不得使用 R3.0-005 fixture 的
  硬编码命名（`PS_COST`、`spare_parts` 等）。
- R3.0-006 完成 = 三层全部 PASS + 四层结论报告归档 + 用户确认。
- 单轮真实建模失败不判需求 FAIL：按四类分层记录，窄修复后在剩余预算内重试；三轮预算
  耗尽仍未达标时，需求保持未完成并输出逐轮对比表与卡死层分析。

## 5. 真实运行记录（L 轮，独立于机械用例）

每轮记录：run-id、起止时间、走到哪一步、卡死层（建模质量/平台合同/协作路由/运行基础
设施）、Agent 行为是否正确、窄修复（含 commit）、预算消耗/退款。多轮结束时附逐轮对比表。

### 轮次记录

（待真实运行后追加；独立验收 Round 记录由 requirement_tester 填写。）

## 6. 清理

- 测试过程中的临时过程文件在完成后删除；证据目录、run workspace（保留期内）与
  StartLedger 记录为保留项。
- 若创建最小第二 Ontology fixture（设计 §6.1），验收结束后从保护集移除并删除该
  fixture Ontology，清理动作留证。
