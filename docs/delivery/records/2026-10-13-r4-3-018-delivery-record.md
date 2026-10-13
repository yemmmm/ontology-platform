# R4.3-018 周边上下文回答相关度排序交付记录

权威范围：[需求](../../requirements/requirements-v4.3.md#r43-018-related_context-按回答相关度排序)、
[设计](../designs/2026-10-13-r4-3-018-related-context-ranking-design.md)。
实现基线：`0aa4e14e88390ee1837ac5cfdc7de0a49db02d42`。
本次用户授权按设计实现及测试；工程实现、独立工程、最终全量与重启入口验证完成。

## 实现

- REST/MCP 自然语言缺省 `context_order=relevance`，可选 `graph_distance`，独立于扩展策略；
  精确 IRI 实际为 graph_distance。零深度、零页长、无根／空周边不评分。
- 当前主命中页的获准输出集合按 `(ontology_id,kind,id)` 去重，各候选只评分一次。
  成功按分数降序，同分用原完整稳定键；0分保留，不继承主命中精确优先或过滤阈值。
- fixed 在既有读取中保留输出筛选前的完整获准材料；adaptive 导出保留图。
  评分使用完整资源／事实／真实关系／派生引用、每根一条最短稳定路径及实际端点／谓词定义。
  逆向 RDF 保留 s/p/o，literal 和 predicate不作为该边的到达节点；source_only不造边。
  多Ontology同IRI保留各自值；两种排序采用相同资源变体集合。评分envelope清理不修改业务data。
- `score_context` 是具体answer-only适配，复用分批／HTTP／数值与模型校验。
  量表为 `jev-evidence-relevance-v1`，周边输入版本为 `related-context-relevance-v1`。
  512评分候选、5000可见工作项、30000／60000 UTF-8字节、共享默认15秒Jev额度和
  查询入口起30秒软截止保持有界，不截必要语义或追加重试／阶段额度。
- 无配置、超时、过大、补齐故障、非法／缺项／重复映射、实际模型漂移均整集合旧序降级；
  全部行分数null／unavailable，原因安全，成功计数如实记录。源修订和授权错误不被降级掩盖。
- relevance 的 fixed/adaptive（包括关闭／降级）冻结完整集合、根页、分数、状态和来源；
  续页不召回、扩图或评分。复用64项／TTL快照，旧授权视图与实际可见源核验沿017合同。
  新增可见／撤权使旧页失效；纯隐藏变化不单独失效，首查复用也核验。
- cursor升v5，绑定顺序／排序配置、根页、投影、主体、修订和索引；v4要求无cursor首查。
  full/compact/preview保留独立relevance和context_page.ranking；preview不返回评分全文，
  neighbors引用重排截页后的页内下标。重放仅归一化确切snapshot_reused运行字段。

不改前端、数据库结构、业务模型、Consumer配置或运行授权；不调用外部Jev，不恢复建模。

## 验证

| 范围 | 当前证据 |
| --- | --- |
| 开发排序／Jev回归 | `uv run pytest tests/test_r4318_related_context.py tests/test_semantic_jev.py -q`：53 passed，162.47秒 |
| 独立工程 | [同一独立记录](../tests/2026-10-13-r4-3-018-independent-test.md)：Round 4 PASS：42 passed，186.12秒；历史轮次及D01原始失败保留 |
| API/MCP/cursor及分页 | 独立定向61 passed；开发相邻复测67 passed（修补齐及重复JSON键前的历史轮次，最终代码由后续全量覆盖） |
| Team重放 | `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r3012_platform_responses.py -q`：57 passed；独立新字段复测2 passed |
| 格式与接口文档 | 改动Python文件Ruff、git diff --check、sync-interface-docs.py --check通过 |
| 后端全量 | `cd backend && uv run pytest -q --disable-warnings --tb=short`：**1194 passed，56 skipped，712.47秒**；跳过项不计通过，既有弃用告警保留；/tmp/r4318-backend-final4.log |
| 重启与实际端点 | 2026-10-13 22:51:57 +08 重启后active/running；backend health为ok，frontend 200；鉴权能力目录、OpenAPI和4种REST请求全部200；/tmp/r4318-runtime-check.log |
| A10真实效果 | 未执行；待后续授权的同集公开中文排序对照及独立Consumer/Judge，不从工程PASS推导效果 |

独立D01复现真实HTTP JSON重复c0被普通解析静默覆盖，导致错误applied。现仅周边评分
用object_pairs_hook拒绝重复键，沿无效响应整集合降级；原始FAIL、修复与复测见独立记录。
主命中／分支适配协议不因此变更。

开发第一轮相邻回归为3 failed／117 passed：一项同步新增root_ontology_id；两项仅验证
旧cursor/服务重建的测试使用不真实空索引stub，显式graph_distance继续测试原确定性路径。
新冻结路径使用真实SPARQL和实际索引状态；上述三项复测通过。
三次全量在代码／独立fixture仍修正时主动中断，分别488／450／463 passed，无产品失败；
不计为全量PASS，原日志保留 /tmp/r4318-backend-full.log、/tmp/r4318-backend-final.log、
/tmp/r4318-backend-final2.log。独立测试源码冻结后的首个完整全量为2 failed／1192 passed／56 skipped，717.82秒，
原日志 /tmp/r4318-backend-final3.log。两项历史测试同样显式选graph_distance：
`test_multi_expression_match_cursor_continues_global_stream` 使用不真实空索引stub，
`test_type_paths_and_shared_adjacency_keep_root_distances` 比较旧固定邻接缓存而非新冻结快照。
只修正测试输入，不改产品；两项定向复测2 passed，6.84秒，最终全量全部通过。

实际端点使用已有启用用户的临时Project read Key，结束后确认删除；不打印／保存Key。
随机无主命中自然语言分别验证adaptive默认／fixed／显式graph_distance，随机精确IRI
验证fixed／graph_distance；能力目录和OpenAPI实际声明context_order及cursor v5。
这些请求均无主命中、ranking=not_requested，不调用外部评分、不创建／修改业务模型。
该检查证明重启入口合同，不证明外部Jev可用性、真实排序质量或A10。

## 影响与边界

GitNexus impact返回含乱码的符号路径；detect_changes报CRITICAL（首轮262／后续232／最终暂存253 affected），映射包括
当前文件不存在的match_fields等旧符号，已向用户披露。这些结果不构成有效图覆盖。
使用真实调用点／diff核对REST、MCP、双cursor、三种投影、快照授权和Team响应重放；
不为本次交付重建图索引。仓库中其他演示未跟踪文件保留，不纳入提交。

独立工程、重启入口合同与真实语义／性能结论分别记录。未消耗建模额度，A10待证。
