# v4 当前运行独立功能验收

日期：2026-10-04。权威范围为 [v4.0 需求](../../requirements/requirements-v4.0.md)，本次只读验收绑定
`r4009-20261004-solmedium-auth02-start1`，由独立验收者在正式 `ready=true` 生产交接后执行。
本记录覆盖当前模型上的有界功能和语义知识授权；业务 CQ 质量由另一独立 CLI Examiner／Judge
判定，不由本记录替代。

结论：**已实际覆盖的授权与有界检索功能 PASS；本轮完整功能范围 PARTIAL，L1 CQ 不由本记录判定。**
一次 depth=3 宽查询超时仍是运行证据缺口。宿主在初次交接时报告 CQ CLI 在 Examiner／Judge 启动前因
`cq_batch_scope_unauthorized: production handoff lists no authorized Ontology` 阻断；本验收者独立
读取的原 handoff 确有 `scope_binding.ontology_ids=[]`。这是验收启动资格问题，不能据此推导
模型质量失败。后续宿主若恢复 CQ，须另记其实际独立结果，不能把本功能记录升级为全 v4 PASS。

## 范围与隔离

- Project：`58c637eb-a425-413b-9328-14af4db48954`；Ontology：`a1a417a2-5179-43e6-9081-350d38fbeb2c`。
- Graph Set 由两主体当前 `scopes:discover` 独立取得：`ae4df685-2e2c-566c-b121-89b23dc01f26`。
- 普通与财务主体均为非管理员、绑定本项目、仅 `read` scope；没有使用管理员或修改 Grant、保护集、资源。
- 保护集：`8baa9026-d48a-4397-80c1-766dcb9b84e8`。四项预先登记的保护资源独立重新读取，
  不复用生产 finance 读回或生产 owner 判定。
- 私钥仅本地构造 Bearer 请求，未打印、复制到记录或注入生产。未读取隐藏 CQ、答案、冻结私有资料或旧 Judge findings；
  未参与生产修复、续跑、业务批准、服务启动／重启或提交 commit。未执行外部 SQL／业务 API／业务脚本。
- 不开发／验收 R4.0-001、015。既往功能测试记录仅用于选择当前合同和界定覆盖，不算本 run 的独立 PASS。

原始新请求与响应保存在 gitignored
`workspaces/v4-acceptance-20261004/independent-functional/`，共 68 条 HTTP 响应，另含超时请求及确定性核对摘要。
请求记录不含 Authorization。全部 Context 响应的模型版本一致：
`ccb355bc8ae5671edd6b14d38e3e756a303e8c07fac7c5e023fdf2606d79ec6d`；
读模型 source signature 一致：`3194b1028a4764284f75ff39ca028bb3`。

## 实际独立验证

| 项目及适用条款 | 当前证据 | 本次结论／边界 |
| --- | --- | --- |
| 生产交接，009 A11；014 当前地图绑定 | handoff 为 ready=true、read-only、pending_writes=false、unknown_writes=[]，三个角色 completed；保存了 11 个 Batch 各 dry_run／apply_atomic 摘要；地图 SHA-256 与 handoff 的 `9bd0efb5d05bb587c7a5ce0c637bc6d2614b0c815b397055f6ad9b0b65009faf` 一致 | 交接和绑定核对通过；Batch 摘要不是独立重做写入／SHACL／真实推理证据；原 handoff 的空 Ontology 选择仍阻断 CQ 资格 |
| 精确授权：002 A6、003 A8、004 A10、005 A9、006 A7、008 A5、009 A8 的当前保护资源专项 | ordinary 对四项保护资源 GET 均 404、Context 均 no_match、0 主命中／0 上下文；finance GET 均 200、Context 均 exact、1 主命中，depth=1 展开 complete；真实不存在对照两主体均 404／no_match | PASS。GET 状态／body shape 一致，差别仅是调用者提供的 IRI 回显；Context 去掉请求表达式回显后，无权与不存在响应完全相同 |
| 宽读取授权，006 A7、008 A5、010／011 A8 的子范围 | 两主体独立宽 Context 和 entity／table-mapping／join-mapping／enum-meaning 列表；普通主体所有结果行扫描未出现四保护 IRI、名称及取得的确切敏感正文；普通 entity 207／table mapping 3，finance 209／4，其他两类列表分别 2／18 | 已观测路径 PASS；不声称任意文本敏感含义、所有导出／SPARQL 路径或保护集变更场景已穷尽 |
| 主命中分页，008 A6 | lexical `[工单,关闭,成本,备件]`，depth=0、context_limit=0；limit=10 各六页，ordinary 52／finance 54 项，与 limit=100 的有序集合完全一致、无重复 | PASS；depth=0 显式 not_requested，不把召回 complete 当业务完整 |
| 非首匹配页上下文续页，008 A6 | lexical `工单`，limit=5、context_limit=20、depth=1；第二主命中页五个根、69 关联项，共四个上下文页；仅携带 context_cursor 保持同根，最终返回的 match cursor 可进入真实第三页；与独立大 context 页集合一致且无重复 | PASS；原响应见 `ordinary-dual-*`，摘要 `dual-cursor-check.json` |
| 角色／身份／普通资源，002 A7、008 A1／A7 的子范围 | behavior 筛选只保留六个声明 behavior 的主命中，96 关联行仍含参数／规则／职责等其他角色；未知角色正常空；已取得普通 NamedIndividual 及参数等身份；换主体或角色续游标均 400 context_cursor_mismatch | PASS；未修改身份、Grant、保护成员或图版本，不声称生命周期／撤权动态回归已覆盖 |
| full／compact，008 A4；012 A3／A4 | act-evaluate 两投影均 22 关联行；full 返回关联规则正文，compact 删除关联 `script_source` 并标 `projection.omitted_fields`，关联 JSON 无正文旁路；规则作为主命中时仍 full；显式未知、scope、recall、expansion 可读 | PASS；仅保存／读取脚本，无脚本执行或业务一致性裁决 |
| 通用映射读取，010／011 当前功能子范围 | 普通与财务主体经 canonical read-model 读取表／join／枚举；Context 读回 interface_mapping、api_message／api_field 等开放语义角色和明确未知 | 可读功能 PASS；未取得业务映射／接口执行质量证据，不宣称 010／011 A10 通过 |
| 当前地图，014 A1／A2／A3／A7／A9 的有界证据 | 四个切片共 15 modeled、13 pending；modeled note 定位 revision 4 item，15 项 note 的全部资源标识均在 finance 新 canonical 列表找到；地图保留 22 explicit_unknowns，区分候选表达／应用／独立接受，未把所有视角标完整 | 当前交接地图定位／状态功能 PASS；只证明资源可定位，不证明相应业务含义正确，也不替代历史恢复或完整 A9 质量验证 |
| 当前 HTTP 健康 | `/api/health` 200／status=ok；frontend 5173 返回 200 | 已观测 HTTP 存活；未启动或重启服务 |

关键原响应为 `ordinary-exact-*-{resource,context}.json`、`finance-exact-*`、`*-wide-small-*`、
`ordinary-dual-*`、`ordinary-action-anchor-*`、`*-cursor-*-negative.json`、`*-*-list.json`。
`independent-check-summary.json`、`ordinary-leak-scan.json`、`handoff-map-check.json`、
`map-live-locators.json` 记录本次确定性比较；这些核对摘要不是 CQ 答案或语义裁判。

## 未覆盖与运行限制

ordinary 请求 `POST /api/semantic/context:query`，lexical `[工单,关闭,成本,备件]`、depth=3、
limit=100、context_limit=1000、full，客户端 55 秒超时，未取得响应体。
保留 `ordinary-wide-full-timeout.json`；根因未确定，不归因为模型缺失。
随后缩到 depth=0／1 的上述调用均成功；没有重复大预算查询、修复、重启或增加平台机制。
因此不宣称完整 008 A3／A5／A6／A9 PASS。

本轮没有写入以制造反例，未重新覆盖 dry-run／apply 错误恢复、跨图原子性边界、身份生命周期、
保护集／Grant 动态更新、候选窗口占满补读、内部 5000 预算 partial、全部 REST／MCP／导出路径、
另一领域 fixture、UI 及停用追溯入口的完整回归。正常读取未依赖 Evidence／lineage，
但这不能单独升级 012 全部条款或 A8。

探针的两处假设已纠正并保留原响应：limit=10 的工单匹配只有两页，
`ordinary-order-page3.json` 中 null 游标回到首屏不算第三页证据；随后用 limit=5 完成真实三页路径。
Context 续页返回的 match cursor 会更新签发时间，不能要求 token 字符串恒等；本次通过实际续读
验证继承根和第三页位置。跨主体负控的预期 400 已保留，探针初次把非 200 统一抛出异常不算产品失败。

L0 当前有界功能已取得独立证据，但完整运行／CQ 启动资格仍有缺口；L1 CQ 结论等待独立
Examiner／Judge；L2／L3 未执行。不得以当前数量、地图 modeled、原开发报告或本次 HTTP PASS
宣布 009 或全 v4 PASS。

## Round 2：范围恢复合同独立审查（首个修复 diff，REVISE）

按宿主新交接，仅只读审查 `modeling_team/runner.py`、`__main__.py` 及两个通用合同测试文件，
不参与生产／语义修复，不读取实际 CQ 或受禁止的生产资料。下列检查全部使用测试替身及临时目录，
没有启动真实 Team／CQ CLI、外部服务或平台资源。

首轮代码基线：`runner.py` SHA-256 `7a056bbc77983d06321011803373cf85f348fa0b26349904ab006bd8ada7908a`；
`__main__.py` SHA-256 `c34cc436b4e1cbead34f1c15929450187121cc2a12db3cab63bac8c73d4f0aa3`。
开发者仍在工作，后续修改须另核对差异，不能沿用该审查作最终 PASS。

实际命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r3012_handoff.py \
  modeling_team/tests/test_r3012_partial_judging.py \
  -k 'scope_binding or single_ontology or empty_scope or recorded_scope' \
  --basetemp=/tmp/v4-independent-scope-contract-round2
```

结果为 **28 passed、29 deselected，0.84 秒**；这仅证明现有 fixture 的合同路径，未覆盖下列反例。
另通过 `backend/.venv/bin/python` 的 stdin 脚本，在 `tempfile.TemporaryDirectory` 下调用仓库通用
`_write_run_root`／`_production_handoff`／`_write_handoff_checkpoint`／`_consume`，只测试消费资格函数，
三项结果保存在 `independent-functional/scope-round2-generic-probes.json`；发布 handoff 字节全部保持不变。

首轮初报两项关注。T0 精确性复核后，**当前仅第 2 项保留为 High blocker**：

1. **源 checkpoint 对象校验关注：撤回 High／不阻断。**
   `__main__.py:1723–1748` 校验 manifest 的 kind／run／freeze／attempt／project 和文件摘要后直接
   从 platform bindings 恢复授权，没有核对保存的源 production-handoff 对象或 packaged artifact。
   通用 fixture 只提供 kind、source_run_id、scope_refs、platform_bindings，没有保存源 handoff／artifacts，
   仍被 `_consume` 接受并授权 `ontology-1`。外层仅检查当前发布 handoff 的 ready/read-only，
   这是初报关注，事实保留，但它本身不足以证明错误授权。
   T0 复核：checkpoint publication event 及 manifest 是 Runner-owned 身份记录，不是生产 Agent 输入；
   外层已经比对真正发布的 handoff 对象、run／freeze、ready／read-only，恢复又绑定该 run 的事件、
   manifest 摘要及 freeze／attempt／project。没有找到不伪造这组受信 Runner 记录即可造成错误范围接受
   或源身份漂移的具体路径。消费只恢复身份集合，不恢复业务包，因此不要求整包业务 artifact 校验成为
   新硬门；缺少包字段的通用 fixture 不能单独建立 High。真实 run／freeze／attempt／project 不匹配仍须 typed 拒绝。
2. **非法 scope 被空集合 fallback 或字符串转换放行。**
   `__main__.py:1892–1905` 先过滤非法列表项，随后把 `ontology_ids=[42]` 当空集合恢复成 `ontology-1`；
   另在 manifest 的 `ontology_ids=[42]` 情形，调用的 `production_resume_bindings` 转成字符串 `"42"`，
   恢复函数因其已经是非空字符串而接受，并向模型绑定提供 `"42"`。两项均已在通用临时 fixture 复现，
   违反“仅恢复明确的空发布集合；非法 scope 保持 typed 拒绝”的边界，不能升级为独立合同 PASS。

本轮结果仍为 **REVISE**（仅第 2 项阻断），等待开发者最终 diff 交接后再独立核对。既有模型、权限、live source／workspace
未因本轮审查修改；Round 1 的有界 HTTP 功能结果可复用，但不消除 depth=3 超时或真实 CQ 未判定的限制。

### Round 2 最终 diff 复审：范围恢复合同 PASS

开发者结束第二轮修订后，重新只读核对四个 owned 文件。最终 `runner.py` 与首轮基线相同；
`__main__.py` SHA-256 为 `28fa921d60c9cd1a2699b0cc01a42a6b45071f999a5c6eb566ecd306a2d04994`；
`test_r3012_partial_judging.py` 为 `1dc0c7cb46f0939e7898d04783cdacd46c12da66934f34b84906ed2e7c60fdfb`。
完整四文件基线保存到 `independent-functional/scope-round2-final-probes.json`。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r3012_handoff.py \
  modeling_team/tests/test_r3012_partial_judging.py \
  -k 'scope_binding or single_ontology or empty_scope or recorded_scope or invalid_non_empty_scope or coerced_manifest_identity' \
  --basetemp=/tmp/v4-independent-scope-contract-round2-final
```

结果：**42 passed、29 deselected，0.91 秒**。覆盖 single／multi／frozen scope、当前有记录的空集合恢复、
不并集已有显式授权、错误 run／freeze／project／digest／缺 checkpoint 拒绝，以及新增非法列表／原始身份拒绝。
另独立重放五个临时目录探针：合法空集合仅恢复 `ontology-1`；原 handoff `[42]`、manifest `[42]`、
checkpoint event 错 attempt、manifest 错 attempt 均返回 `TeamConfigurationError` 的
`cq_batch_scope_unauthorized`，不再产生授权集合；五项 published handoff 与 manifest 字节均保持原样。
前一轮 High 已关闭。原成功／失败探针记录保留，未覆盖成后续结果。

最终审查 **0 Critical／0 High，可提交本次范围修复**。第一项 T0 撤回仍保留，不要求额外整包业务校验。
宿主另报告开发侧完整 Team 回归为 2237 passed、2 skipped、314 subtests passed；本验收者未重跑该全量，
不把转述当作独立全量验证。上述 PASS 只证明范围恢复合同，不代表真实 CQ 已启动或语义质量通过。

影响范围由当前 diff 与直接调用点核对：writer `_cq_scope_binding` 仅用于 `_cq_publish_production_handoff`；
consumer `_cq_consume_production_handoff` 仅由 `_run_cq_acceptance` 调用；新恢复 helper 仅被 consumer 调用。
宿主报告 GitNexus `detect_changes(all)` 给出 CRITICAL／253 affected，但包含当前 diff 未修改的符号，
疑似索引行号偏移或重名污染；本验收者不声称图覆盖，采用实际 diff／调用点和聚焦合同验证，不重建索引。
未修改 backend、模型、权限或生产证据，未追加 live 测试、真实 Team／CQ CLI 或服务操作。

## Round 3：opaque pagination token 投影最终合同复审 PASS

按最新授权，只读核对 Codex 开发者结束的 `modeling_team/__main__.py` 与
`tests/test_r3012_platform_responses.py` 最终 diff；没有调用 Claude、发起 live 请求、读取隐藏题／Judge 答案、
创建／继续／修复 run 或改动保留报告。此轮仅验证通用重读比较合同。

最终基线：`__main__.py` SHA-256 `eb4833eb5c977e5405707b3076e0176c500476675dc81a97c2f097e39125d4da`；
测试文件 SHA-256 `f5337db1e365c47ebc844aed4c9e2ec354dbd3e53e200b4ffd633ad0b3e3db75`。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r3012_platform_responses.py \
  --basetemp=/tmp/v4-independent-cursor-contract-round3
```

结果：**43 passed，0.36 秒**。包含真实保留响应合同的 `data.matches_page.next_match_cursor`／
`data.context_page.next_context_cursor` 包装路径以及明确支持的裸 service payload。
仅 `query_semantic_context` 的这两槽位把非空字符串比较成 continuation presence；
None、空串、非法类型、returned／truncated／expansion、scope／source／workspace、资源身份和内容继续比较。
不递归屏蔽业务资源内部的同名字段，不屏蔽其他工具或包装顶层的同名业务字段。

另用 stdin 通用脚本和 fake forwarder 独立验证 canonical `ok: true, data: {...}` 形状的 13 项案例，
再加一项裸 payload，共 **14 项探针通过**：token 重签发保持 stable；项目范围、workspace、source signature、
资源 IRI、业务内容内的 cursor 同名字段、包装的 ok 状态、两个 continuation 的 None 切换、分页 returned／truncated、
expansion 及布尔型非法 cursor 均保持 drift。13 项包装案例比较前后 retained／reread／entry 的 JSON 摘要一致；
原 request_digest／response_digest 字段及原始对象不变。证据保存于
`independent-functional/cursor-round3-generic-probes.json`，没有使用真实查询响应或私有生产资料。

**独立合同复审 0 Critical／0 High，可提交本次窄修复。** 改动仅新增比较专用投影，并用于
`_cq_recheck_evidence_responses`；不修改已有 `_cq_semantic_projection`、原 HTTP 保留对象／摘要或 Judge 输入内容。
开发者另报告完整 Team 回归 2262 passed、2 skipped、314 subtests passed、165.52 秒；
该全量为开发者证据，本验收者只独立执行上述 43 项及 14 个探针。

宿主后续报告首次真实 CQ 已执行 10／10，9 pass／1 fail，终态 **PARTIAL**；本验收者未读取隐藏题或其判题依据，
没有据此确认 H01 具体根因，也未把此轮机械合同 PASS 回填成旧 CQ PASS。后续 start2 的生产更新／额度属于宿主
运行记录，不属于本轮合同验收。Round 1 的 live 功能证据仍绑定其明确的 `ccb355…` 模型版本，
不得用于声称更新后的模型状态或新的语义运行已通过。depth=3 原超时及历史失败证据保留。

## Round 4：start2／r5 新状态最小只读功能验收 PASS

本轮绑定 `r4009-20261004-solmedium-auth02-start2` 的正式生产交接，独立读取确认 ready=true、
write_phase=read-only、pending_writes=false、unknown_writes=[]、三个角色 completed；
scope_binding 明确列出既有 Project 与单 Ontology，没有空授权集合。
代码提交为 `80ae6d8`；本轮未修改代码、模型、权限、run 或报告，未调用 Claude／真实 CQ CLI。

当前数据状态与前轮分开记录：

- workspace：`3d734d03a5e4c233d1cc0ce7496fac78ed1ed9a74180a2e6fc1fca3832c2cc02`。
- source signature：`05c8168eebfa635f4d47096ae62d51b1`。
- Project／Ontology／Graph Set 继承原身份；两非管理员 read Key 的当前 scope discovery 均成功并返回该 workspace。
- 宿主交接称本次仅公开 `semantic-access-policy` 的语义更新；本验收者只核对该资源的当前读取状态／边界，
  不据此评价更新内容的业务正确性。

复用 Round 1 的 canonical HTTP 路径：`GET /api/semantic/resources/{resource_iri}?graph_set_id=...`
（内部沿当前受治理 read-model 读取）、`POST /api/semantic/context:query` 和 scope discovery。
所有请求依次执行，单请求 timeout=15 秒，没有并行压负荷或重复 depth=3 查询。
新证据仅写入 `workspaces/v4-acceptance-20261004/independent-functional-start2/`，
包含 **28 条新 HTTP 响应**和 `round4-check-summary.json`；最长实际请求 **2.183 秒**。

| 当前 r5 最小验证 | 独立结果 |
| --- | --- |
| 四保护资源的两主体精确资源读取／lexical exact IRI depth=1 Context | ordinary GET 全部 404，Context 全部 no_match／0 主命中／0 上下文；finance GET 全部 200，Context 各 1 exact 主命中，depth=1 展开 complete，关联分别 7／4／7／15 项 |
| 一项真实不存在控制，两主体 GET／Context | GET 404、Context no_match；普通四项无权 Context 去掉请求表达式回显后与不存在响应完全一致，GET 状态／body shape 同形，不存在资源未被 finance 判为可读 |
| 两主体 bounded lexical `[成本,备件]`，depth=0、context_limit=0 | ordinary 10／finance 12 主命中；recall complete、展开 not_requested，仅覆盖当前查询可见范围，不宣称业务完整 |
| 公开 `http://ontology-platform.local/semantic/entity/semantic-access-policy` exact IRI | 两主体 GET 200 且响应体相同；Context 各 1 主命中／3 关联项、展开 complete；实际返回绑定上述新 workspace/source，无业务意义评分 |
| 普通主体成本保护内容边界 | 在本轮所有普通成功响应的资源 properties／label 及 primary_matches／related_context 中扫描四保护 IRI、finance 新读回的四个名称及取得的确切正文，均无命中；不依靠请求回显判断泄漏，不声称检测了任意文本的敏感语义 |
| 状态一致性与凭据边界 | 所有 Context workspace 只有上述 `3d734…`，所有精确 GET source signature 只有上述 `05c816…`；私钥权限仍 0600，仅本地构造 Bearer，不写入响应记录／文档 |

**当前 r5 的上述有界功能／授权专项 PASS；整体 v4 功能范围仍 PARTIAL，CQ／L1 不由本轮判定。**
原分页、semantic_roles、full／compact 的实现合同证据仍可参考 Round 1／Round 3，
但 Round 1 的 live 行为明确属于旧 `ccb355…` 状态，本轮没有把它当作 r5 的全量实测。
未重复角色、完整分页、投影、撤权／生命周期、跨图故障、全部读面或 depth=3 运行验证；
历史 depth=3 超时和首次 CQ PARTIAL 保留。没有读取隐藏题／Judge 报告／原生产 finance 读回，
不对当前 CQ 结果或 L1 语义质量作结论。本轮只读测试不消耗 semantic modeling start。

## Round 5：历史 review 降级与 S4 显式模型合同复审 PASS

本轮遵循 [R4.0-014 F3／F4／F5](../../requirements/requirements-v4.0.md#r40-014-场景地图进度与实际产物同步)
与 AGENTS.md T0，只读审查开发者交接的九个文件：`__main__.py`、`host_ops.py`、`host_ops_mcp.py`、
四个对应通用测试、S2 设计和 team runbook。没有读取实际隐藏题／Judge 业务答案／生产 finance 历史，
没有修改实际 run/map/handoff/checkpoint、代码或测试，也未新增 live 查询／调用 Claude。
同时进行的 fast 配置任务不在本轮范围，不检查其在途 diff。

T0 判断：旧 revision 的历史 review 作为工作上下文，不能证明当前 ready／complete，
但把它的普通过期当作阻断 Judge 的硬门会迫使改写已经绑定的历史地图。
当前候选、结构、来源摘要、身份和受治理读取由原有更高层校验保护，因此只对精确 typed
`map_dangling_reference` 且路径为 `adjustments[i].review.after_refs[j].revision: stale` 或
`adjustments[i].review.references[j].revision: stale` 的情形，省略比较副本中的对应整份 review。
不是跳过地图验证，也不以旧批准授权当前内容；其他错误继续拒绝，原件保持原摘要。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r4007_multiview.py \
  modeling_team/tests/test_r30015_acceptance.py \
  modeling_team/tests/test_host_ops_s2.py \
  modeling_team/tests/test_host_ops_mcp.py \
  --basetemp=/tmp/v4-independent-round5-contract
```

结果：**80 passed，6.77 秒**。使用通用 fixture、fake launcher/forwarder 与受控 MCP/CLI 参数 seam，
没有启动真正 semantic Team／验收会话或修改平台资源。主要证据包括：

- after_refs／references 分别或共同 stale 时，旧 complete／ready review 从 Judge 工作副本整体消失，
  当前 definition 的原 unknown 状态不提升；无获准可见 IRI 时无 definition 投影，原地图与 handoff 字节不改。
- 非 stale 的 missing candidate／missing item／slice scope／schema／shared-term stale 均保留 typed 拒绝；
  既有 handoff digest/path、plan parse/identity guards 的通用回归继续通过。
- CLI/MCP/Host Ops 可选 `model_profile` 原值传入 S4 `cq_args`；受控 `test_m44` 确认 Examiner 与 Judge
  两个会话均绑定 `openai-sol-medium`。省略保持既有默认，不修改源模型配置。
- 非法参数在 launcher 前拒绝；凭据仍由既有 Host 环境通道传入，不增加 argv 或语义上下文中的凭据。

另以 stdin 脚本执行 **9 组独立泛化探针**，均在临时目录：三种精确 stale 组合省略旧 review、
当前有效 review 保留、stale 与 wrong-item 同时存在仍拒绝、五种非法 profile 不启动、默认与显式 profile
argv 精确、production 模式传 profile 拒绝、缺 Host credential 拒绝。
地图探针均验证原 map/handoff 字节不变且私有范围被过滤；模型参数探针使用 fake launcher，
测试凭据不出现在 argv／JSON 启动记录中。结果及九文件最终 SHA-256 基线保存在
`independent-functional/round5-generic-probes.json`，不包含实际隐藏题或真实凭据。

**本轮独立通用合同复审 PASS，0 Critical／0 High，可提交本范围九文件修复。**
这只解除上述比较副本和参数传递合同的阻断，不构成新的模型批准、当前 review ready/complete 或
真实语义 PASS；实际失败／未执行题、历史报告及第一阻塞层继续保留。既有 Round 4 的有界 r5
语义知识授权功能结果可以按其原状态复用，本轮没有再做 live 查询或作最终语义 Judge。

## Round 6：显式 session fast 配置投影合同复审 PASS

只读核对冻结的 `modeling_team/runtimes/codex.py` 与
`modeling_team/tests/test_r23008_codex_builtin_config.py`。本轮仅检查 Host session 环境
`MODELING_TEAM_CODEX_SERVICE_TIER=fast` 对内建 OpenAI 配置的局部投影，
不启动真正模型、Team／CQ CLI 或新增 live 查询，不读取隐藏题／Judge 业务答案，
不修改代码、测试或实际 run 原件，不调用 Claude。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r23008_codex_builtin_config.py \
  --basetemp=/tmp/v4-independent-round6-config
```

结果：**19 passed，2.75 秒**。通用 fixture 直接解析实际配置写入路径产出的 TOML；
生产 coordinator／modeling／protocol／acceptance 与 Source／Platform Examiner、Judge
均验证 `gpt-6.1-sol`／`medium`、内建 `openai` 路由。子配置使用预启动 sentinel，
在 process factory 前终止，不启动真实 app-server；只使用合成源与合成凭据。

- 显式 `fast` 在根级生成唯一 `service_tier = "fast"`，在既有 `[features]` 表内
  生成唯一 `fast_mode = true`；原 sandbox、web_search、功能 flags、MCP 表与 shell policy 保持。
  `tomllib` 解析验证无重复键与表边界漂移，无自定义 OpenAI provider 表／额外凭据通道。
- 默认与 `unknown` 的上述生产／验收配置不增加 fast 键，不制造新的配置硬拒绝。
  deepseek-direct／glm-direct 的生产与子配置路径均不投影 fast 设置。
- focused call-site 检查确认 helper 仅在两处内建 provider 分支调用，外部 provider 分支不调用；
  内部固定模板均含唯一 `[features]`，本轮不为未知 session 值增加验证机制。

另执行 **9 个独立泛化探针**：未设置、空串、unknown、FAST、前后空格、priority、flex
均保持原列表与完整 TOML；精确 fast 的解析差异只有上述两个键，原输入不变。
结果与两文件 SHA-256 基线保存在 `independent-functional/round6-generic-probes.json`。
两文件冻结基线、`git diff --check` 与本记录链接／格式检查通过。

**本轮通用配置合同复审 PASS，0 Critical／0 High，可提交这两个文件。**
完整 Team 回归由开发者持有，本轮不重复或将其计为独立执行证据。
这证明生成配置合同，不证明真实模型服务已按 fast 计费／执行，也不改变旧 CQ PARTIAL
或给予当前模型 L1 语义 PASS；Round 4 的 live 结果仍只绑定其已记录的 r5 状态。

## Round 7：既有 FIFO write-stall fixture 容量修复 PASS

只读检查 `modeling_team/tests/test_host_ops.py` 的新增 `fcntl` import 和原 write-stall case：
由固定 `FIFO_MAX_LINE_BYTES - 64` 改为实际 fd 的 `F_GETPIPE_SZ - 64`，并参数化默认容量与 4096。
生产 `host_ops.py` 的 SHA-256 与已验收 Round 5 基线一致；没有降低生产门或改动生产写入逻辑。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_host_ops.py \
  -k test_a06_5_write_stall_is_typed_without_zero_write_claims \
  --basetemp=/tmp/v4-independent-round7-fifo
```

结果：**2 passed，70 deselected，0.96 秒**。保留原 0.3 秒写超时 deadline、答复长度，
并验证原 `outer_input_write_timeout`、`partial line may`、`do not blindly resend` 和无请求 ledger 断言。
没有通过放宽断言或提升生产超时绕过错误，fixture 不再要求写入超过真实 FIFO 容量。
另以临时目录合成 FIFO 检查默认 fd 实际容量 8192／填充 8128，以及指定容量 4096／填充 4032，
两次完整填充均返回；证据与该测试文件 SHA-256 保存在
`independent-functional/round7-fifo-fixture-probes.json`。最终基线、diff 与文档格式检查通过。

**本窄 fixture 修复独立 PASS，0 Critical／0 High。**
此前 full 回归在 fixture 阻塞后被 SIGINT 中止，宿主报告 exit 2／247 passed／63 subtests／404.96 秒，
继续保留为未通过的运行记录；不能以本定向 PASS 替代完整回归重跑结果。
该问题归入测试 runtime／infrastructure，不由此推导 fast 配置或模型质量失败。
本轮未启动真实模型、服务／Team／CQ CLI、live 请求或 Claude，也未读取隐藏题／Judge 答案。

## Round 8：S4 Judge 使用已验 checkpoint 访谈副本合同复审 PASS

只读检查冻结的 `modeling_team/__main__.py` 与 `test_r30015_acceptance.py`。
内部可选 `interview_checkpoint` 参数把 `prepare_acceptance_continuation` 已验的 plan
经 S4 → CQ execution → Judge evidence bundle 传递；不加入 CLI、JSON continuation、Consumer 输入，
不改 checkpoint recovery／Runner cleanup，普通 live 默认路径不变。
本轮只使用通用 fixture，不读取实际隐藏 CQ、评分、业务访谈正文、私钥或生产历史读回。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r30015_acceptance.py \
  --basetemp=/tmp/v4-independent-round8-interview
```

结果：**26 passed，4.49 秒**。其中三种公开 locator 形式经过真实 Runner private cleanup
方法后，受控 S4／Judge bundle 仍读取 manifest 声明的 host-private archive 原字节；
普通无 plan 的 live 路径仍 unresolved，source 树不改，Examiner packet 不含访谈文本。
fake adapter／readback／forwarder 保持无真实模型与平台访问。
11 类负例覆盖 record／manifest digest、source／checkpoint binding、文件／目录 symlink、
未声明条目、schema／空文本、路径 escape、archive 缺失但 live 尚存在；均 unresolved 且空 bundle。

另执行 **6 个独立泛化探针**：错误 source root、错误 checkpoint kind、重复 archive 条目、
非 host-private 条目、live 文本不同而已验 archive 保持权威、archive 缺失禁止 live fallback。
全部通过；每次验证 source 树字节状态不变，后两项分别确认原 archive 内容不改写、
缺失时无 entries 且题有 unresolved。证据与两文件 SHA-256 基线保存在
`independent-functional/round8-archive-interview-probes.json`。

T0 判断：正常 cleanup 不能迫使回填 source 或关闭盲隔离；复用已验 package 是当前最窄读取差异。
manifest／entry digest、source／checkpoint／kind binding 和 path／symlink 检查仍保留，
显式 archive 异常不能择优切换 live，schema／text 校验继续使用既有合同。
原 unresolved 阻止相关题判定的执行路径不改，不以 missing／skip 产生假 PASS。

**本轮通用合同独立 PASS，0 Critical／0 High，可提交这两个文件。**
两文件冻结基线、diff 与本记录链接／格式检查通过；开发者完整 Team 回归不重复，
本轮 26 项独立结果不冒充宿主报告的 75 项组合 GREEN。
未启动真实 run／模型／live 查询，未修改实际 run、source、report 或访谈原件，也未调用 Claude。
该 PASS 只解除 archive 证据读取合同缺口，不改旧报告或对实际未裁决题、模型质量作语义判定。

## Round 9：Consumer 通用证据消费规则合同复审 PASS

只读审查 `modeling_team/agent-packages/v3-acceptance-batch/platform-examiner.md` 的最终 8 行新增。
规则要求结论／必要条件由当前获准读取支持，并区分语义定义与评审／采用状态、执行能力、
实际执行与观察结果；只有读取证明依赖时，才能把一种状态的缺口作为另一状态完成的前提。
明确保留证据中的条件、unknown、既有授权与写入门。没有指定业务答案、资源或题目，
没有把未评审当作已采用或把可执行当作已发生，不赋予 Consumer 新权限。
这是一项通用提示合同补充，不改变平台校验或语义裁判职责。

实际路由检查：`CodexRuntimeAdapter._child_package_assets(v3_batch=True)` 对 platform
直接选择该文件；真实 child 分支从 batch packet 构建合同后读取其 bytes 并传入隔离树。
Judge 仍选独立 `acceptance-judge.md`，非 v3 子角色仍选 legacy package。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_v4_consumer_answer_contract.py \
  modeling_team/tests/test_r3011_contracts.py \
  modeling_team/tests/test_r3012_contracts.py \
  --basetemp=/tmp/v4-independent-round9-consumer
```

结果：**28 passed，1.15 秒**。另 4 个独立静态探针确认恰为通用 8 行新增且原合同逐字保持，
v3 platform 真实资产选择、Judge 分离与 legacy 路由不变；记录与单文件 SHA-256 基线保存在
`independent-functional/round9-consumer-contract-probes.json`。diff 与本记录链接／格式检查通过。

**本轮独立提示／路由合同 PASS，0 Critical／0 High，可提交本文件。**
未修改代码／测试，未提交，未读隐藏 QA、实际私有访谈或 Judge 答案，未启动／修复 run、
模型或 live 查询，也未使用 Claude。本合同与后续正常模式／fast 关闭、sol/medium 要求兼容，
但本轮未启动会话或验证运行时服务档位。静态规则和合同测试不能证明真实 Consumer 已遵循规则，
不回填旧报告、不将本轮 PASS 替代新的独立语义裁决。

## 最终交付元数据与总体边界

以下仅为宿主转交的语义报告／运行与清理元数据；独立功能审核者没有读取该次 run、
隐藏题或业务答案，也没有亲自作语义裁决，不以转交信息替代独立功能证据。
宿主报告正常 S4 `attempt-0004` 绑定 Start2／`production_handoff-0001`，
于 `2026-10-04T02:00:31.378318Z` 启动、`02:06:27.569803Z` 结束：exit 0、
`full_pass=true`，10 题执行／10 个有效 Judge 裁决／10 pass；11 个保留响应与 11 次 recheck
均 stable，无模型漂移，两 child 与 forwarder 清理成功。
实际 Examiner／Judge native model 均为 `gpt-6.1-sol`／`medium`，两份生成 TOML 均无 fast 启用。
这项宿主报告的非盲有界语义回归 PASS 不覆盖全部 v4。

宿主同时转交清理结果：两枚测试密钥撤销后均 401、测试用户停用、项目成员与财务临时角色移除；
project／ontology／workspace／Protection Set 管理 GET 仍 200，四个保护成员保留，
管理测试凭据亦已撤销。独立审核者未为本节重新执行清理或 live 请求。

**当前 v4 总体仍 PARTIAL。** 本记录中的各轮合同与有界功能 PASS 按各自代码／状态绑定成立；
宿主转交的最终回归元数据不覆盖外部 SQL／API 实际执行、OWL 真实推理或 L2／L3，
也不抹去历史失败、depth=3 超时与未覆盖范围。本次只追加交付元数据，未重新审代码或测试、
未改其他文件、未提交。

## Round 10：完整冻结公开集选择与 S4 缓存隔离合同复审 PASS

只读核对开发者 16 文件最终差异（不将宿主交付 record 算入开发范围）：既有 CQ／S4 CLI、
Host Ops／MCP、checkpoint acceptance plan、报告／完成守卫、Consumer package 及对应测试，
以及 009 权威需求／设计、Host S2 设计与 runbook。显式 `--question-visibility hidden|public`
默认 hidden，public 选择整个原冻结公开集，不提供任意单题／子集参数。
不改 visibility、冻结、生产权限或外部执行边界，不实现 015。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r30015_acceptance.py \
  modeling_team/tests/test_r3012_completion.py \
  modeling_team/tests/test_host_ops.py \
  modeling_team/tests/test_host_ops_s2.py \
  modeling_team/tests/test_host_ops_mcp.py \
  --basetemp=/tmp/v4-independent-round10-public
```

结果：**157 passed，11.36 秒**。仅运行通用 fixture、fake adapter／forwarder／launcher，
没有真实 semantic run／模型／live 查询。默认 hidden 路径与原完成行为继续通过；
public S4 在已有 hidden PASS 后仍启动受控批次，按冻结 ordering 收到完整公开分母，
Consumer question 字段仅 question_id／content_version／question／scope，不含答点和依据；
Judge 同时收到对应所选题及既有核验响应／批准资料路径。
原 archive 读取校验和 source 树逐字不变测试继续通过。

公开报告显式 `question_selection`／`non-blind-regression`，使用 public coverage 字段；
直 CQ 输出隔离到 public-regression，S4 写入新的 output attempt。
hidden Host／Runner completion guard 拒绝 public 报告，不能以其关闭生产 hidden 完成门。
S4 缓存绑定 freeze、选择及完整 ID 集，hidden 完成缓存不会跳过 public，反向也不复用。
生产模式传 public 被拒绝，scope/profile 与既有读代理合同不扩大。

另 **10 组独立泛化负控**验证所选 ID 缺失／错误类型／数字、Judge 缺项／额外项、未执行题、
错误 blind 标记、空公开集及模型漂移均无完整 PASS 且不可作为缓存；仅精确完整 public 集
可命中 public 缓存，默认 hidden 与子集请求不能复用。证据及开发者 16 文件 SHA-256 基线
保存在 `independent-functional/round10-public-selection-probes.json`。
初读期间两报告 helper 追加所选 ID 类型校验，已告知宿主并以追加后的最终源码运行负控、封存基线；
若之后再变更，需要对新差异复核。本记录不宣称早先输入与最终输入完全一致。

**本轮独立合同 PASS，0 Critical／0 High，可提交本范围。**
冻结基线、diff 与本记录链接／格式检查通过；完整 Team 回归由开发者持有，不在此重复。
此处只证明公开只读验收入口与隔离／缓存／分母合同，不证明实际公开 11 题的语义结果。
未读取实际 hidden、业务私有访谈／答案，未修复 run 或回写源报告，未调用 Claude，未提交。
既有 hidden10 slice 非盲 PASS、公开／全景及映射消费缺口仍按原范围记录，v4 总体仍 PARTIAL。

## Round 11：native startup 首阻塞证据保留合同复审 PASS

只读检查冻结的 `modeling_team/runtimes/codex.py` 与 `test_r3011_acceptance_runtime.py`。
本次只修可观察性：native startup 已产生并清理资源的固定 failure_evidence，不再被
`batch-contract-unavailable` 次级错误覆盖。启动 stage 限为 initialize／thread-start／
mcp-preflight／turn-start；原 RPC、MCP 发现、模型、超时与启动策略不变。
宿主说明旧日志没有可回溯底层异常，因此真实启动原因仍未确定，不能称已修复真实启动问题。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r3011_acceptance_runtime.py \
  --basetemp=/tmp/v4-independent-round11-startup
```

结果：**24 passed，4.75 秒**。受控 native process／RPC 与真实本地 Unix report sink
覆盖启动 MCP discovery 失败保留 first blocker，以及 11 题全量实际 sink 提交成功与清理。
未启动真实模型／验收；其余既有 batch 合同、授权与 runtime fixture 回归保持。
另 **7 组独立泛化探针**确认四个 allowlisted stage 只输出固定安全 meta，任意私有 sentinel
stage 被省略；spec 中 raw-packet sentinel 不进入 evidence；已有 startup failure 保留，
没有 failure_evidence 且缺真实 batch contract 仍 typed 阻塞、不产生 PASS，资源仍销毁。
证据及最终两文件 SHA-256 基线保存在 `independent-functional/round11-startup-blocker-probes.json`。

**固定 stage 中间版本独立可观察性合同 PASS，0 Critical／0 High；最终结论见下方 typed RPC 补充。**
最终冻结基线、diff 与本记录链接／格式检查通过；后续若加入新的 typed code 需单独复核差异。
不由该 PASS 推断旧 public Judge 可启动、公开题通过或模型质量失败；第一层实际原因仍待新运行证据。
本轮保持 sol/medium／normal 要求，未切模型、未读旧宿主日志或实际 private／hidden 答案，
未改 run／证据或代码，未调用 Claude，未提交。

### Round 11 最终差异：既有 typed RPC 安全元数据 PASS

开发冻结后仅复核新增差异：startup catch 只对既有 `CodexRuntimeRPCError` 保存
其已归一化的闭集 category 与 integer／null code；原 server_message、data、method、
active turn ID 不进入 failure_evidence。普通错误无细码，仅保留固定 code／stage。
该 typed error 构造器原有类别闭集与排除 bool／非整数 code 的合同保持，未新增诊断文字。
内部 spec 字段仅由该 catch 构建，未新增外部 packet 字段或凭据渠道。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r3011_acceptance_runtime.py \
  -k native_public_judge_startup_failure_preserves_first_blocker \
  --basetemp=/tmp/v4-independent-round11-final-rpc
```

结果：**3 passed，22 deselected，1.22 秒**，覆盖 plain startup failure、typed RPC -32603
和 11 题完整真实本地 sink 提交。另 **6 组独立负控**验证两种整数、None、bool、字符串 code
经既有 typed 合同处理，以及普通错误没有 rpc_error；任意 category 降为闭集 rpc_error，
message／method／turn／data 私有 sentinel 均未进入固定 evidence。
结果与最终两文件 SHA-256 基线在 `independent-functional/round11-final-typed-rpc-probes.json`。
之前 24 项／7 组只属固定 stage 中间版本证据；本最终差异测试不冒充整模块或完整 Team 回归。
宿主转交补码前 full 中断 exit 2／494 passed／66 subtests／38.96 秒，只记中间未完成运行，不能称 PASS。

**Round 11 最终可观察性合同独立 PASS，0 Critical／0 High。**
最终冻结 hash、diff 与文档链接／格式检查通过。真实 startup 原因仍不可回溯，
本改动不修启动机制、不证明新 public 批次可运行或语义通过；完整回归由宿主唯一执行。
本补充仍无实际模型／验收、live、hidden／私有答案、运行或证据修改、Claude 或 commit。

## Round 12：V3 预算与超限 Judge 无损输送合同复审 PASS

只读审核最终冻结的 acceptance_runtime.py／runtimes/codex.py／test_r3011_acceptance_runtime.py。
V3 batch metrics 的 max_inference_steps 为 None，保留步数与 token 记账、session deadline、
report sink 整批合同和失败保留；legacy 默认 30 不变。
仅超过原生 text aggregate 上限的 V3 Judge first-turn 使用 lossless result-body registry：
完整 canonical result 以摘要索引去重，每一条原 retained response 保留自己的 metadata／ref。
原 packet、_packet、sink、private input、freeze 和证据身份不改，索引不成为业务 IRI 或新证据。
未超限 Judge 保持原首轮字节，Consumer 不走该 Judge 输送分支。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r3011_acceptance_runtime.py \
  modeling_team/tests/test_r23009_examiner_step_budget.py \
  --basetemp=/tmp/v4-independent-round12-native
```

结果：**31 passed，6.05 秒**。受控 factory／RPC／真实本地 Unix sink 验证 11 条报告完整提交，
超限正文有两种完整 unique result，逐条展开 canonical bytes 与原 packet 完全相同、digest 一致，
private input 仍为原 canonical bytes；V3 第 31 步不阻断且继续记账，legacy30 相关合同通过。
首次命令误用了不存在的 test_r3011_step_budget.py，exit 4、无测试运行；已更正为上方既有路径。

另 **4 组独立泛化探针**覆盖重复 body 的键顺序、Unicode、null、逐条不同 response_digest／
artifact_path／page metadata 的无损保留；冻结原 packet 不变、registry digest 正确、展开逐字相同；
legacy30 与 None31 的预算差别；未超限首轮文本逐字兼容、原 private input／packet／timeout 保持。
初始探针传普通可变 list，不符合 helper 唯一生产调用传入的已冻结 packet 合同，断言失败；
已改用既有 _freeze_packet 验证真实输入不变量，不将该探针失配推断为生产缺陷。
结果与三文件 SHA-256 基线在 `independent-functional/round12-lossless-budget-probes.json`。

**本轮独立合同 PASS，0 Critical／0 High。** 最终 diff SHA-256 与开发交接
`bdd12866e3e23ea15264b4e6844f9e9e7a0228f67eba21d4572546f56ef959ab` 一致，
冻结基线、diff 和文档链接／格式检查通过。原生 loopback 输入边界探针和更广回归为开发侧证据，
本轮未自行执行原生探针或完整 Team，不把其结果作为语义裁决。
该输送只消除完整正文重复，仍不能保证任意唯一大内容低于原生上限；没有截断或分段绕过。
未启动真实模型／验收／live、读取 actual private／hidden 或作语义 Judge，未改生产证据、
代码／测试、模型档位，未调用 Claude，未提交；实际公开结果仍需后续独立真实执行。

### Round 12 实际完整公开输入完成门：REVISE／High

宿主后续转交纯大小元数据 `retained-judge-transport-size-verification.json`：
public1 完整 11 题 actual first-turn 经 whole-body registry 后仍为 **1,607,354 chars**，
超过已验证 native aggregate cap **1,048,576 chars**；unique body 总量 **1,434,719 chars**。
public2 只有 9 题，输送 **574,823 chars** 在门内，不能以删题／不完整分母代替整批完成。
两次检查的逐字重建、digest 与原 packet 不变均为 true，但它们只证明无损性，不证明可启动。
独立审核者仅接收上述纯 meta，没有读取 actual 私有 packet、题目答案或发起真实运行。

**High：当前完整公开 11 题 native Judge 启动仍被输入上限阻断；实际 whole11 readiness 为 REVISE。**
三文件未变，前述独立 generic 合同 PASS 继续成立，但不能称完整公开输送已解决。
宿主最终 full 结果 2320 passed／2 skipped／314 subtests／172.21 秒／exit 0 仅为合同回归证据，
不覆盖该 actual cap 缺口或提供语义 PASS。
宿主正在按 T0 评估是否在同一完整分母下作有序 Judge 分组，每题冻结资料与读取结果仍完整；
此处仅记录评估状态，没有代码变更、新运行或对该后续方案的审核／批准。

## Round 13：超限 Judge 物理分组合同复审 PASS；实际运行待证

独立核对开发者冻结九文件（排除宿主 record 与本记录）：main、acceptance_runtime、codex、
两个相关测试、v3 011 需求与设计、009 设计及 runbook。按获准 T0 结论，单 Consumer 仍连续
处理完整批次；仅 Judge 完整 first-turn 超限时，按冻结顺序贪心连续分组，在同一 attempt
逐组披露，不宣称单 Judge 会话。全局所选 11 题分母与完成门不变，单题完整输入超限仍 typed 拒绝。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r3011_acceptance_runtime.py \
  modeling_team/tests/test_r3012_partial_judging.py \
  --basetemp=/tmp/v4-independent-round13-groups
```

结果：**80 passed，8.36 秒**。真实本地 Unix sink／default factory 采用受控 process／RPC，
验证整 11 题聚合、首组失败后后续组继续且整体不 PASS、每组独立报告列表与 teardown、
冻结原件不变、无前组 verdict 进入新输入；未启动真实模型或平台查询。
组 packet 复用原 builder／sink，按 question_id 选取本题完整 frozen 资料、Examiner report 和
retained responses，保持同 freeze/model binding；报告披露 ordinal、题 ID、packet digest、
实际 input chars、有效裁决数、失败和清理。原未超限路径保持原 packet 与单组 shape。

另 **4 组独立泛化探针**验证完整有序连续题集不漏／不重、每组实际序列化门内与逐字段资料保真，
确定性 group digest／原 packet 不变／无旧 verdict，未超限原 packet identity，以及单题超限拒绝。
证据与九文件 hash 在 `independent-functional/round13-physical-judge-group-probes.json`。
最终 diff SHA-256 与交接 `928d0c259e4160e810cd771db39bb5b795046600e9c9fa2b36d37ef2d27c5b39`
一致，冻结 hash、diff 与文档链接／格式检查通过。

宿主转交纯统计 `retained-judge-grouped-input-verification.json`：实际 public1 whole11 计划为
P01–P03／565,640 chars，P04–P05／1,012,708，P06–P07 与 S01–S04／289,930，
三组均低于 1,048,576；本题 frozen／完整 entries／results 保真、同 freeze/model binding，
real children／platform queries 为 0。独立审核者没有读取 actual 私有 packet。
宿主统计初先错误要求未分组的 9 题原 bundle 从 31 entries 过滤为 25，改按原 single packet
保持后通过；这是统计断言失配，不据此判平台 fidelity 故障。

**独立分组合同 PASS，0 新 Critical／High；actual whole11 runtime readiness 仍待真实运行。**
Round 12 的旧 1,607,354 chars 超限 High 原证据保留，新计划大小已门内不等于实际 child 能启动、
完整裁决或语义通过，因此本次不提前关闭实运完成门 blocker，也不称最终公开 PASS。
未重复父完整 Team，不读取 hidden／实际私有访谈或答案、不改 run／证据或代码、
不实际模型／live／语义 Judge／Claude，不提交；sol/medium／normal 要求不变。

## Round 14：逐题超限局部失败与通用窄读取指导合同 PASS

只读核对最终冻结七文件：main、partial-judging test、实际 v3 Consumer package、011 需求／
设计、009 设计与 runbook。完整单题超 native cap 时记录本题 `judge-input-too-large` 与
`runtime/infrastructure`、input_chars／max_chars，只跳过该题，完整全局所选分母不改。
其他完整合格题按原冻结顺序继续；单个剩余组传筛后的完整 packet，全部超限不启动 Judge，
cleanup 只列实际调用的 child。默认未超限路径保留，不压缩业务含义或修改 frozen 资料。

实际独立命令：

```bash
env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest -q \
  modeling_team/tests/test_r3012_partial_judging.py \
  modeling_team/tests/test_v4_consumer_answer_contract.py \
  --basetemp=/tmp/v4-independent-round14-local-skip
```

结果：**59 passed，6.84 秒**。真实本地 Unix sink／default factory 使用受控 process／RPC，
覆盖单题超限、全部超限、只剩单个 eligible、分组启动失败后继续及 normal 分组兼容；
全局 11 题缺任一有效裁决均不完整 PASS，无 Judge 时无虚构 cleanup child，冻结原件不变。
另 **5 组独立泛化负控**覆盖中间题超限、首尾超限、全部超限、仅末题可判和提示合同：
每题 typed failure 正确，余下题有序完整，原 packet 不变；通用提示保留逐题 evidence gap、
必要分页、完整原始返回及原 host handles，没有题 ID、答点或具体业务答案。
结果与七文件最终 hash 在 `independent-functional/round14-local-input-failure-probes.json`。

新增 13 行指导限制重复宽读而不限制必要读取：复用仅限当前题相关证据，不从旧题／旧 attempt
补齐答案，不因输入大小省略证据、裁剪返回、合并／伪造 handles；不足时报告 unresolved。
并未在平台压缩／删改结果或扩权，也不改变独立 Judge 裁决责任。

**本轮合同独立 PASS，0 新 Critical／High。** 最终 diff SHA-256 与交接
`53ce7109d0aa7a0a49ccc9d4901e0a5f7a1b84adc63cc1ca6046bbc228976f42` 一致，
冻结 hash、diff 与文档链接／格式检查通过。父完整 Team 不重复；不以开发测试或这次合同 PASS
宣称 actual 11 题可裁决／语义通过，先前真实启动／单题超限证据继续保留，actual 完成门不提前关闭。
本轮无真实 run／模型／live，无实际 private corpus／hidden 答案读取，未改 code／源／旧报告，
未调用 Claude 或提交；sol/medium／normal、fast 关闭要求保持。

## Round 15：最终宿主安全元数据与证据边界审查 PASS；公开实际阶段 PARTIAL

本轮只读取宿主安全文件 outcome、diagnostic-qualification、配置／native-thread observations、
public test-subject cleanup、final retained-resource verification 和 source/report digests final。
只检查分母、状态、摘要、引用身份资格、白名单配置／资源 labels／status 与保护成员数；
没有打开 actual result/body、私有 corpus、隐藏答案或业务访谈，也没有新模型调用／真实查询。
这里的语义结论是独立 native Judge 已有结果的元数据，不是本审核者新增裁决。

public4 `r4009-20261004-solmedium-auth02-start2-public4`／`attempt-0008`：
`2026-10-04T06:03:20.896734Z` → `06:16:01.898748Z`，managed exit 1。
完整有序公开分母 11，执行 11／有效裁决 11／unexecuted 0；宿主转交 skip 0。
**7 pass；P01／P02／P06 为 model-recall-insufficient；S01 为 question-answer-review；full_pass=false。**
报告 SHA-256 为 `960b098b405b66dd04672aab2524eff001348f5d578521735e4a855a679bc6b6`，
outcome、diagnostic qualification 与最终 digest 清单绑定一致，旧报告不变。

27 次 replays、全 11 个 question status stable，无 unavailable／drift，前后 binding 一致，
lifecycle_errors 空。实际 Consumer／Judge 两 child，生成配置与 native thread 均
OpenAI／gpt-6.1-sol／medium、service_tier 与 fast_mode 无启用；child 销毁与 forwarder 停止
均成功，bootstrap revoked=true。当前批次已取得真实全裁决运行证据；旧 startup／input-cap
失败原件和诊断保留，不以当前运行回填旧版本成功。

P01／P02／P06／S01 的宿主诊断引用资格均 true，unique_match／raw_artifact_matches／stable
及 original_verdict_preserved 均 true。本轮只核对这些已有身份资格，不读 root_cause 正文，
不据旁证补成本题作答或提高通过率，不以粗粒度 modeling-quality／insufficient 宣称模型知识不存在。
S01 新版本 proposal 由宿主负责，本轮未评审业务含义或改冻结／旧判定。

清理安全记录有 11 HTTP receipts：测试两密钥撤销后 401，用户停用、membership 和临时角色
移除；保留 project／ontology／workspace／Protection Set 管理读取均 200，保护成员 4／4，
最终管理凭据也撤销。source 四原件、public1–public4 四报告 final digest all_unchanged=true。
本轮依据清理记录核对，不重新清理／发请求，不展开业务字段。

**本轮元数据一致性／证据边界审查 PASS，0 新 Critical／High；实际公开阶段 PARTIAL。**
旧 hidden10 slice 非盲 PASS 与 public7/11 分别保留，不能合并为整体验收 PASS。
宿主转交最终 full 2328 passed／2 skipped／314 subtests／177.71 秒／exit 0，以及代码提交
`e994526`，均只作为机械／交付元数据；本轮没有重复测试或把它当语义通过证据。
fresh starts 仍 2/5、剩余 3，不为重复已正确模型新开 start、不暗改 freeze 重算。
v4 总体仍 PARTIAL；L2／L3、外部实际 SQL／API／脚本执行和真实 OWL 推理未验收。
本次只追加本记录，链接／格式检查通过，没有修改源／报告／代码、调用 Claude 或提交。

宿主最终台账补充：当前阶段为 `bounded-validation-finished`，overall／bounded_cq 均 PARTIAL，
hidden_cq_status 单独记录 10/10 PASS，public_cq_status 单独记录 7/11＋3 insufficient＋1 review，
消除旧 hidden-only bounded_cq PASS 的范围歧义；2/5 starts、剩余 3、无 active。
本轮完成的是当前有界验证阶段，不以“完成”要求全部 v4 PASS，也不修改旧冻结／历史结果。
