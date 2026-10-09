# v4.3 R4.3-008—012 工程交付记录

权威范围：[需求](../../requirements/requirements-v4.3.md)，[增量设计](../designs/2026-10-09-v4-3-retrieval-design.md)。
用户授权实现；Jev 验证初始按用户指令暂停，同日提供 key 后恢复但外部推理 HTTP 451，
详见文末后续记录。真实建模、Consumer/Judge 独立语义
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

## Jev 验证恢复与外部阻塞

2026-10-09 用户提供 OpenCode API key，指定 OpenCode 推理入口和 `jev-1.13-free`，
恢复本项有界验证；没有恢复真实建模或 Consumer/Judge，没有消耗启动额度。
key 通过不回显终端输入，仅存在探针进程内存，不写文件、仓库或请求/响应证据。

- [用户指定推理文档](https://opencode.ai/v2/docs/console/api/inference/)没有列出 Jev 专用协议；
  [OpenCode 模型文档](https://opencode.ai/v2/docs/console/models/#jev)列出 System One
  state/questions 协议与 `https://opencode.ai/zen/v1/systemone`。
  [当前路由源码](https://github.com/anomalyco/opencode/blob/dev/packages/console/app/src/lib/inference-proxy.ts)
  明确把该旧路径转发至 `/systemone/v1/systemone`，据此直接测试用户指定的 inference
  base 下 `https://opencode.ai/inference/systemone/v1/systemone`。未调用 TypeSafe 官网。
- 中文受控候选保留完整口径、条件/未知、关系入口以及同名无关项，使用四档相关性 rubric；
  [Score 文档](https://docs.typesafe.ai/primitives/score)说明 score 是等级概率的期望值，
  confidence 是另一个字段，本项不混用两者。请求已冻结，但未取得任何评分。
- 旧 `/zen` 接口：HTTP **451**，0.867 秒；直接 `/inference/systemone/v1/systemone`：
  HTTP **451**，0.863 秒。两者原始错误均为
  `{"error":{"type":"server_error","message":"Upstream request failed: Endpoint is unavailable."}}`。
- 再以单个英文 noul 问题验证最小协议，直接推理仍 HTTP **451**（0.358 秒）。
  同一 key 请求 `/inference/v1/models` 为 HTTP **200**（0.689 秒），列出指定模型。
  模型目录可读不证明推理可用或 key 已通过付费/模型权限校验；不推断错误为 key 无效、
  中文质量差或免费层限制。失败响应延迟也不是模型评分延迟。
- 原始证据：jev-control-request.json、jev-legacy-endpoint-response.json、
  jev-control-response.json、jev-minimal-probe.json；探针脚本保留在同一 gitignored 目录。
  已准备的17道公开题候选未发送做批量评分，不读取隐藏材料，不用模型自评分充当业务评级。

当前结论：**BLOCKED（runtime/infrastructure，OpenCode 上游推理接口不可用）**。
Jev 中文质量、重排收益、推理延迟/成本/稳定性均未取得证据，保持待评估，不接入生产，
保留现有 max 排序。恢复条件为该专用接口恢复可用，或用户提供另一个可用 OpenCode
System One 地址；无需重复提供当前 key，不切换模型或服务商。

### 第二个 key 与付费模型复测

同日用户指定新 key，并授权同时测试 `jev-1.13`。沿同一直接 inference 地址，
保持相同最小英文 noul 请求，仅切换模型；各调用一次，不保存 key。

| 模型 | HTTP | 请求耗时 | 结果 |
| --- | ---: | ---: | --- |
| jev-1.13-free | 451 | 0.857 秒 | Upstream request failed: Endpoint is unavailable. |
| jev-1.13 | 451 | 0.414 秒 | Upstream request failed: Endpoint is unavailable. |

证据：jev-second-key-two-model-results.json 与 jev-two-model-probe.py，仍位于同一
gitignored 目录。两种模型都未取得答案或 usage，无法据此确认推理费用、key 权限或
服务端具体故障点；没有扩大到批量候选评分。原外部接口阻塞结论保持，免费/付费模型
质量均未验证，不改变生产排序或真实建模暂停状态。

### 错误来源进一步定位

用户授权排查后进行有界对照，不修改服务配置或平台代码。证据为
jev-routing-diagnosis.json、jev-workspace-config-diagnosis.json、jev-public-tls-diagnosis.log；
opencode-jev-support-report.md 为可转交服务方的无凭据复现材料，未对外发送。

- 本机无 HTTP(S)/ALL_PROXY 环境变量；HTTPX trust_env=False 直连仍复现。
  curl 连接 opencode.ai 的 TLS 域名及 Google Trust Services WE1 证书校验通过，
  HTTP/2 响应来自 Cloudflare。不是本地 ontology-platform 或代理环境生成的报错。
- 同一 Jev 路径，无 key 为451；故意无效 key 为401 Invalid credential；用户新 key 为451。
  用户 key 读取 `/console/api/v2/config` 为200，确认凭据可以通过鉴权。
  不存在模型名返回400 Model is unavailable，而存在的 Jev 返回451 Endpoint is unavailable，
  把失败收窄到服务端模型端点选择/上游处理，不能据此确认付费模型的余额或全部权限。
- 另一个免费模型 big-pickle 的最小8-token Chat 请求返回403 FreeTierError，明确写
  “OpenCode's free tier can only be used from within OpenCode”。该控制证明普通端点能够
  返回具体策略错误，但没有获得成功推理；没有伪装客户端或绕过该限制。
  Jev 返回不同错误，不能把403的免费层政策当成451的已证实原因。
- 工作区配置为一个 OpenAI-compatible provider、84个模型，全体配置未出现 Jev。
  公共目录却列出两个 Jev ID。该配置面向 OpenCode 客户端，不支持直接推断为缺权限；
  与新 inference 的 System One 端点未接通/未开放的假设相容，尚非根因证明。
- [OpenCode 路由源码](https://github.com/anomalyco/opencode/blob/dev/packages/console/app/src/lib/inference-proxy.ts)
  验证了直接路径与旧 `/zen` 转发关系，新 `oc_sk_` key 由新 inference 服务处理。
  因此改旧URL不能绕开同一服务端失败。已有公开同类报错报告不能证明本次相同根因。
- 本次有效 key 的失败请求：2026-10-09 10:47:15 UTC，
  x-opencode-log-id=`65f7546e-2ad8-4bda-860e-0c738468d35a`，
  cf-ray=`a47cce6258753d78-LAX`，cf-placement=`remote-IAD`。
  边缘节点/执行位置不是用户所在地或地域封锁证明，也不从451数值独自推导法律限制。

结论更新：本地网络/TLS和普通凭据鉴权已排除；故障边界为 **OpenCode 新 inference
服务的 Jev System One 端点选择或其上游处理**。可疑原因是该模型端点配置/协议支持
未就绪，或上游/策略将端点置为不可用；两者须服务方用上述日志ID确认。
没有服务端日志，不能把“缺路由配置”或“TypeSafe宕机”写成已确定根因。
当前保留 BLOCKED，不继续无意义重试、不换key、不改变业务质量结论。

### DeepSeek Flash 推理正对照

同日用户要求测试 OpenCode DeepSeek Flash，使用最近提供的同一 key；公开模型目录
包含 deepseek-v4-flash 和 deepseek-v4.1-flash。各调用一次同一最小 Chat 请求，
关闭 thinking、max_tokens=32，目标返回 OK。

- deepseek-v4-flash：HTTP403，0.845秒，Model access is disabled。
- deepseek-v4.1-flash：HTTP200，1.431秒，真实返回 OK、finish_reason=stop；usage
  为9 input + 2 output = 11 tokens，reasoning_tokens=0。
  x-opencode-endpoint-id=fireworks，upstream model 为
  accounts/fireworks/models/deepseek-v4p1-flash。
- 请求地址为 https://opencode.ai/inference/openai/v1/chat/completions；时间
  2026-10-09 11:16:05 UTC，成功日志ID c0abea11-5f9c-473f-a458-c32ff2de81f3。
  证据为 opencode-deepseek-flash-probe.json/py；key 未持久化。

正对照证明当前 key、网络和 OpenCode 至少一条实际推理链路可用，不能将此前 Jev
失败解释成整个 OpenCode API 或普通凭据故障。Jev 与该成功请求并非同分钟复测，
不据此断言其此刻状态或具体根因；Jev 评分效果仍未验证。
