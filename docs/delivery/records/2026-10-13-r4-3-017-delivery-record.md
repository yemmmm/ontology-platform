# R4.3-017 自适应上下文扩展交付记录

权威范围：[需求](../../requirements/requirements-v4.3.md#r43-017-jev-参与分支选择的自适应相关子图扩展)、
[独立复审通过的设计](../designs/2026-10-13-r4-3-017-adaptive-context-expansion-design.md)。
实现基线：`c8356db8a80501782d3c04ff190f7eae8782e01c`。
本次用户授权按设计实现和测试。工程实现、独立定向测试、全量及重启/实际接口验证完成。

## 实现

- REST/MCP 自然语言默认 adaptive，上限三跳；显式 fixed 默认一跳，显式 depth 不被抬高，
  精确 IRI 保持 fixed；零深度或零 context_limit 不展开。能力目录与真实工具 schema 同步。
- 一跳基础内容先授权保留；独立回答与探索量表在读取下一层前选择入口。深层阈值均为 1，
  全根页共享 32/16 推进宽度及 8/4 桥梁预留、5000 可见工作项、512 分支评分上下文。
  主命中与分支共享 Jev 时间，新增探索使用查询入口起的 30 秒软截止。
- 结构化引用沿原明确字段逐层推进。真实节点和边按稳定身份合并，共享完整邻接读取，
  新入边可重判，环不追加循环任务；最终源距离只在保留的实际连接中计算。
- 保留深层证据所需连接及评分失败后的已读合法内容。评分状态、预算、结束原因、获准
  定向读取提示穿过 full/compact/preview；preview 不带回完整定义。主命中分数含义保持。
- 根排序与子图共用进程内 64 项/TTL 快照。cursor 升至 v4，context 续页恢复冻结根页和
  后继 match cursor，不重新召回、评分或读邻接；关闭或失败的 Jev 仍冻结合法结果。
- 私有快照保存有效授权视图。无权集合变化时按同修订实际 RDF 完整分块及非 RDF 映射
  原值核验可见性；新增可见内容使旧页失效，纯隐藏变化不单独失效。核验失败保持
  dependency_error，响应前再次核对授权和修订，差异身份/数量不进入公开输出。

本期不修改前端、数据库迁移、Consumer 显式深度、业务模型或相邻 R4.3-018。
评分初值是工程配置，未经真实中文样本校准，不把子图变小称为质量提升。

## 验证

| 范围 | 当前证据 |
| --- | --- |
| 独立工程 | [Round 3](../tests/2026-10-13-r4-3-017-independent-test.md)：50 项通过，另补 1 项通过；最终 24 个独立场景；历史 Round 2 三个旧合同断言失败保留并复测 FIXED |
| 相邻固定及多表达式回归 | `uv run pytest tests/test_semantic_context_query.py tests/test_r4008_context_query.py -q`：64 passed |
| API/MCP/cursor | 真实工具目录 schema、默认解析、v4 完整性/绑定与授权 hook；定向测试通过，详见独立记录 |
| Jev client | 24 passed；真实 HTTP stub 验证完整候选、双量表、共享时间、整批校验、先前成功批次保留、模型漂移和业务同名字段忠实度 |
| 格式与接口文档 | 所有改动 Python 文件 Ruff、`git diff --check`、接口文档同步检查通过 |
| 后端全量 | `cd backend && uv run pytest -q --disable-warnings --tb=short`：**1120 passed，56 skipped，359.94 秒**；跳过项保持真实状态，不计通过；既有弃用告警保留 |
| 重启与实际端点 | 2026-10-13 21:28 +08 重启 `ontology-platform.service` 后 active/running；后端 `/api/health` 为 ok，前端 5173 为 200；鉴权能力目录/OpenAPI/REST 检查全部 200 |
| A10 实际效果 | 未执行，待后续授权的公开中文 fixed 一跳/三跳/adaptive 对照及独立 Consumer/Judge；不恢复暂停的建模或消费验收 |

首次全量为 4 failed／1116 passed／56 skipped：三项是 API 自动清单已有一行 summary 与运行时
不同，文档同步测试自动修复该生成行；另一项旧邻接缓存对照被 adaptive 的重复首查快照复用，
因此明确选择 fixed 继续验证原固定遍历的邻接复用，不修改产品缓存行为。
随后 `uv run python ../scripts/sync-interface-docs.py --check` 及 10 项文档测试通过，再次全量通过。
该文档同步修正不增加平台行为。测试全局清理进程快照，隔离同 Project/revision ID 的不同内存源 fixture。

实际端点检查使用已有启用用户的临时项目 read Key，结束后已删除该 Key；不暴露凭据，
不创建/修改模型。能力目录实际默认 adaptive/3、cursor v4，MCP 参数目录包含策略字段，
REST OpenAPI 的 depth 可省略/null。单个随机自然语言查询零主命中，分别得到 adaptive/3
和显式 fixed/1；随机精确 IRI 得到 fixed/1。所有请求 200，不运行外部 Jev。
该检查证明重启后的入口合同，不证明多跳质量、真实外部评分或 A10。
本机开发日志：`/tmp/r4317-backend-full.log`、`/tmp/r4317-backend-final.log`、
`/tmp/r4317-runtime-check.log`；关键结果已记录于本文，不以临时文件存在作为交付门。

## 影响检查与边界

GitNexus `query_multi`、`score` 定位为 UNKNOWN/not found；API impact 为 LOW，但无已定位
直接消费者。detect_changes 报告 CRITICAL/232 affected，实际映射到未改的 `match_fields`、
发现 schema 等大量无关旧符号，已向用户说明；精确 Context 服务 Class upstream 仍为 LOW/0。
这不构成有效图谱覆盖。采用实际调用点/diff 核对：生产入口只有 REST/MCP 的 Context Query，
已有 Consumer 显式 depth=1 仍最多一跳，既有前端显式零深度检索不启动扩展。
全量回归和独立测试验证受影响合同，不重建索引或扩展产品范围。

独立工程 PASS 与实际语义/性能结论分开；正常外部 Jev 可用性、完整真实问题效果和提升幅度
仍待证。未调用外部评分、建模、Consumer/Judge，不消耗新的建模额度。
