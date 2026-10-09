# v4.3 R4.3-008—012 工程交付记录

权威范围：[需求](../../requirements/requirements-v4.3.md)，[增量设计](../designs/2026-10-09-v4-3-retrieval-design.md)。
用户授权实现；Jev 验证按用户指令暂停，待 API key。真实建模、Consumer/Judge 独立语义
验收仍暂停，未消耗启动额度。本轮开发检查不属于独立功能或独立语义验收。

## 实现

- 008：结构化定义合同字段进入所属资源的词面/向量文本，保留字段依据和原文，JSON Unicode
  转义兼容；不索引其他键、秘密列或业务行。Mapping/Metric 按现有资源种类召回，未指定
  RDF 类型但有定义的普通资源与现有读合同一致。投影/模板 v2，4 个现存本体索引沿原
  coordinator 重建为 current，模型修订 8/4/23/12 全部未推进。
- 009：显式 preview，完整主命中与唯一周边摘要、页内 neighbors 引用、稳定资源身份、
  每根方向/距离及直接关系定位；原始 JSON literal 不绕行带回全文。全局计额、类型路径、
  周边分页和完整内容授权保留。消费者从摘要 IRI 按需取得完整主命中及新的预览。
- 010：单题及连续批次提示均按信息缺口推进，次数仅统计，已有截止/暂停/停止控制保留。
  代理默认 5 主命中、全局 20 周边、深度 1、preview，显式参数保留。
- 011：默认 exact-expression-max-v2 修复拆分词项被误标整句精确；保持可用 max 融合。
  RRF 候选方案与固定公开候选对照工具已实现，显式精确依据优先、不剔除低分节点。
  共同命中造成排序退步的控制样本保留，RRF 不默认启用。Jev 未接入、未调用、未选型。
- 012：进程内有界查询向量复用及请求内共享邻接复用，重新检查授权/模型/游标。
  非法 provider batch 明确降级且不污染缓存，精确 IRI/纯词面仍不调用 Embedding。

## 开发验证与真实依赖边界

证据目录为本机 gitignored `workspaces/v4-3-retrieval-20261009/`。

- 后端全量：从 backend 执行 `uv run pytest -q`；最终结果见下方收口补充。
- Team 全量：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`：
  2580 passed、11 skipped、316 subtests passed（192.13 秒）。Consumer 后续未再改；
  最终读取桥/多 Ontology 代理相关复测 39 passed（9.40 秒），见 team-read-contracts-final.log。
- 新增合同 11 passed（release-contracts.log）；实际 RDF 查询涵盖定义五类内容、投影排除、
  Mapping/Metric 种类、完整授权、共享/环/类型路径、预览分页、完整 IRI 详情、缓存配置/
  凭据/TTL、副本及非法 provider 降级。相关 Context 扩展回归 75 passed，保留原 full/compact。
- 新增模块 Ruff、接口文档同步、需求/设计链接及 git diff 格式检查通过。
  GitNexus MCP 不可用，以当前调用点/差异/合同检查替代，不主张图影响覆盖。
- systemd 按仓库规则重启，backend 8001 health 和 frontend 5173 为健康；最终复验见收口。
  前端未改，无新增 UI 或 Playwright 验收主张。
- 真实 PostgreSQL/Oxigraph/Embedding 的投影与接口检查使用既有合同，不创建语义运行。
  历史配置中的 MCP key 返回401，改用一次性测试身份；每次 finally 删除，未改原账号/key。
  初次重建列表含已不存在 Ontology 的历史 manifest，未发生写入；只选择现存本体后成功，
  未批量清理或修复无关历史记录。

## 实测与尚未证明的效果

1. 保留原冻结 17 道**公开题**，不读隐藏题/答案。旧 c7d334a Context/Retrieval 代码在当前
   相同模型上只读取得完整旧 v1 索引基线 public-baseline.json；新代码/v2 索引结果、完整
   候选及字段值另存 public-after.json、public-ranking-candidates.json，供后续同源对照。
   早期自动 reload 后、索引尚未重建的读取另存 public-before-rebuild.json，明确 degraded，
   不冒充旧代码基线或正常优化收益。每题候选页100，截断仍记录；不是完整 Consumer 答案。
2. compare_semantic_ranking 工具接受固定公开候选，比较 max/RRF 的 Recall@5/10、nDCG、
   必要入口和缺召回；业务 relevance 尚未逐候选确认，17题 graded_cases=0、
   evaluation_status=pending_relevance，不能从 regressions=0 推导质量通过。
3. 首个公开题、相同5主命中/全局20周边/深度1：full **31961 bytes**，最终 preview
   **34157 bytes**（约增加6.9%）；身份、主命中、上下文集合及每根引用一致。
   两种视图均明确返回 candidate_window_incomplete、matches_truncated、context_truncated，
   recall.completeness=degraded；这是同等小页的组织/体积比较，不是完整召回证明。
   早期59368/中间36413 bytes 结果保留，去除重复身份/名称与根信息后下降，最终仍有组织引用
   开销。长篇定义合同样本 preview 小于 full，但短定义真实样本的退步不能被它覆盖。
   分别测得4.29/3.74秒只是单次、有并发测试负载的观察，不能宣称确定提速或 token 收益。
4. 相同公开查询三页、相同模型/范围/结果：禁用复用3次 Embedding、启用1次；Embedding
   累计0.794/0.399秒，总10.380/9.862秒。语义响应、scope、完整性一致，opaque cursor 的
   时间/签名不按逐字相等比较。pagination-measurement.json 保存完整页面。
   首次探针逐字比较包含不同到期时间的cursor，断言失败保留；修正比较口径后通过。
5. 请求内共享邻接在实际 RDF fixture 中降低读取次数，资源/关联/方向/距离及结果一致；
   未据此宣称生产规模性能增益。

结论：工程功能与开发验证交付；008/009/010 的真实召回/Consumer 效果、011 中文/必要
关系入口/最终评分选型、Jev 延迟成本稳定性以及完整27题/120分钟仍待证。Jev 等用户 key；
公开相关性等级与真实 Consumer 效果均未伪造成 PASS，原运行/额度/隐藏隔离保持。

## 最终收口

- 当前最终代码后端全量 **1016 passed、56 skipped**（247.20 秒），见
  backend-release-final.log；全部必需开发检查通过。警告主要为既有 RDFLib 弃用提示。
- 测试通过后重启 ontology-platform.service，状态 active (running)，backend health
  返回 `{"status":"ok"}`，frontend HTTP 200。相关日志为 service-status.log、
  backend-health.json、frontend-health.txt。
- 重启后重新采集17题公开候选页，每题 recall.completeness=complete，候选100条及
  分页截断保持可见；更新 public-after.json、public-ranking-candidates.json 与对照输出。
  固定候选对照仍为0题完成业务评级、pending_relevance、Jev pending_user_api_key。
- 重启后 full/preview 同源检查再次通过资源集合及每根引用校验，体积仍31961/34157 bytes；
  单次3.676/3.686秒，见 preview-runtime-final.json/log，不推导确定性能收益。
- 采集探针最初错误读取 recall.status，随后错误要求小页 completeness=complete；
  失败日志 public-final-probe-error.log、public-preview-equality-error.log、
  public-after-capture.log 保留。改按实际 completeness 与警告合同记录后最终检查通过；
  未修改平台结果或放宽平台校验，临时测试身份全部删除。
- Ruff、接口文档同步、需求/设计/交付链接及 git diff --check 最终通过。
  Jev、真实 Consumer/Judge 与27题/120分钟验收停止于用户指定的暂停边界。
