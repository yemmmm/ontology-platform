# v5 最小共享记忆与检查点快照交付

## 授权、范围与结果

2026-10-29 用户要求共享记忆先简单设计、验证能力可运行，后续再打磨流程，并增加检查点
快照。本批按[最小设计](../designs/2026-10-29-v5-memory-snapshot-minimal-design.md)实现，
归属 [R5.0-002／008](../../requirements/requirements-v5.0.md#r5-0-002)和 R5.0-001 F10。
沿当前 v5 研发 `usage_only` 授权，所有托管角色为 `glm-direct / glm-5.3-flash / low`。

**已完成当前 task 内共享记忆及命名观察快照。118 项回归及最终 8 项针对性检查通过；
旧通信代码冷启动无宿主修补通过，新记忆任务经一次格式解析窄修后原 run 接续成功；
两轮都只有一次实际应用，治理读回及独立公开工程判据各 1/1 PASS。**
不关闭完整 P1.2／P1.5／v5，不把公开小场景或 P0 历史结果当作完整业务质量、
记忆语义保真或净降耗验收；新记忆代码的无干预冷启动未另开一轮证明。

## 实现内容

- `shared_memory: true` 为生产成员装配 `write_memory`、`read_memory`、`search_memory`。
  同一 task 共享 entry_id、kind、title、body、source_refs，程序保存作者、时间和 revision。
  已知身份读完整记录，未知身份用文字／可选 kind 查找有界预览再展开。kind 不强制枚举，
  不要求额外审批或固定整理步骤。复用现有 PostgreSQL 版本及冲突反馈，相同内容不造新版本。
- 可与协作组合，也可供单成员换会话读取。没有增加数据库表、向量库、自动抽取、摘要服务
  或跨 run 项目迁移。记忆是有来源的理解，不是第二份已应用本体或新增人工确认。
- Host CLI 增加 `snapshot-save/list/show/diff`，记录工作空间冻结内容及版本、任务卡／
  队列、LangGraph checkpoint 身份和当前步骤、执行引用、保存时源码摘要及实际模型引用。
  执行原始输入／输出仍留在原执行库，不在每份快照重复嵌入。名称只作标签，文件身份由程序生成。
- 保存可在 Agent 忙碌时执行；快照不成为运行门。list／show／diff 直接读保存文件，
  无需重新加载原任务、数据库连接、原材料或当前工作流版本。保存时模型读取不可用则
  明确留下错误与已有版本引用；不把它伪装成刚读取的模型。
- 快照是组件各自版本的观察记录，不声称跨存储全局事务；源码摘要是保存时文件状态，
  不是已启动进程的代码证明。本批不恢复旧快照、不回滚／复制已应用模型，不等于完整
  平台数据备份。平台数据 capture／fork 若需要，沿已有 R3.0-017 路径接入。

## 工程检查

最终完整回归命令与锁定环境：

```bash
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 pytest -q \
  -c modeling_team/v5/pyproject.toml modeling_team/v5/tests
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff check \
  modeling_team/v5/src modeling_team/v5/host modeling_team/v5/tests
env UV_PROJECT_ENVIRONMENT=$PWD/workspaces/v5-codex-p0/.venv \
  uv run --locked --project modeling_team/v5 ruff format --check \
  modeling_team/v5/src modeling_team/v5/host modeling_team/v5/tests
```

**118 passed，0 skipped，1 条既有第三方 warning，86.51 秒。** 最后仅收窄单成员记忆
提示，避免提及未启用的协作工具，另跑记忆／快照 **8 passed，6.75 秒**；无需无依据
重跑全套。Ruff check／format 检查覆盖最终代码。日志均保留在
`workspaces/v5-runs/memory-snapshot-20261029-*-tests.log`。
5 份相关 Markdown 的 64 个本地链接和代码围栏检查通过，暂存 diff 无空白错误。

新增验证覆盖未知身份查找、完整正文读取、跨成员版本修订、冲突返回实际内容、旧版本、
task 隔离、实际隔离 Codex MCP 装配、忙碌快照、不可变前后快照与差异、离线只读查看，
以及原回执重解析不重复启动 Actor。隔离装配测试不调用上游模型；确定性 Actor 不作语义证明。

## 真实运行证据

两轮复用[公开演示原文](../../../modeling_team/v5/tests/fixtures/team-source.md)，SHA256
`99de578cdbdca5e276ded24231cc27f38cb18c197fd104499f3701e51e87a328`；仍仅建“演示设备”一个概念。
公开工程判据 `v5-team-public-criterion-20261029`，1 题，SHA256
`efdddd6de59435f11f5d1f36a4adc35679f020c688d311f18801948cad2fe82e`，不作为新的盲测。
独立侧只读原文、冻结题、目标和实际模型，不从生产记忆／快照补模型答案。

| 环节 | 实际证据 |
| --- | --- |
| 冷启动 | `v5-team-cold-20261029-start1`，以 `3ba895f` 通信代码启动；未加宿主技术输入、未修补其运行代码。两次建模、一次 peer、一次自查、一次评价完成，单次 `apply-00001` |
| 共享记忆初建 | `v5-memory-snapshot-20261029-start1` 的 model-00000 读原文，写 `decision-demo-device-concept` revision 1，随后发送含搜索词的请求，不传记录 ID 或全文 |
| 忙碌观察 | busy-observation 的队列记录仍显示 `memory-unit → model-00000` 活跃，记忆已为 revision 1；保存成功，没有要求停稳 |
| 暂停与换进程 | 在自然 turn 边界停稳，decision-before-review 保存 revision 1、模型 revision 0、下一节点 collaborate；新 CLI 接续，model-00000 未重放 |
| 跨成员读取／修订 | peer-reviewer-00000 实际 search_memory → read_memory → read_material → write_memory，把同一记录更新为 revision 2；保留原内容并追加署名复核 |
| 新上下文消费 | model-00001 实际读取原文及 revision 2 后生成变更，只应用一次；自查首回合漏读实际模型，经既有反馈后下一回合实际 query_semantic_context，最终 handoff_ready |
| 快照比较 | after-shared-review 保存 revision 2、模型 revision 1；diff 显示同一记录 1→2，变化字段 author／body／updated_at，流程和模型版本变化；旧快照仍为 revision 1 |
| 独立检查 | 两轮分别取得公开工程判据 1/1 PASS；未升级为完整业务语义或记忆保真验收 |

冷启动运行／输入分别位于 `workspaces/v5-runs/team-cold-20261029-start1/`、
`team-cold-20261029-inputs/`。记忆任务位于对应 `memory-snapshot-20261029-start1/`、
`memory-snapshot-20261029-inputs/`。各 run 的 `runtime-summary.json` 保留执行、工具、
用量、时间和清理汇总；私有连接、凭据、快照和原始产物不提交。

记忆任务保留 prepared、busy-observation、decision-before-review、after-shared-review
四份命名快照；冷启动另有 cold-completed。首次 show 发生在保存进程结束前，返回
snapshot_not_found；宿主等待保存完成后重读成功，原错误保留，未补造或覆盖旧快照。

## 格式阻塞的 T0 复核与窄修

peer 的真实回执是简短说明后接一个合法结果 JSON；全部记忆工具及回复已成功。
旧解析器只接受裸 JSON 或显式代码围栏，返回 result_json_missing_or_ambiguous。
第一阻塞为 platform-contract，源材料和模型质量没有因此失败。

该包装格式限制不保护额外业务或写入不变量：只需能唯一定位符合结果 schema 的值。
现接受说明文字、围栏等包装中的唯一匹配 JSON，不修补字段或发明内容；不同有效结果
仍返回歧义反馈。原结构／目标／源忠实度校验保留，避免用猜测选结果。

修后从原 peer-reviewer-00000 回执重解析并确认消费，复用原执行身份，没有新开 peer
或重做已成功记忆写入；记录最终仍为 revision 2。对应回归实证先旧格式拒绝、再以同一
回执接续至单次应用。没有用手工修改原输出或补业务事实取得通过。

## 资源、时间与用量

| 任务 | Project | Ontology |
| --- | --- | --- |
| 冷启动 | bf31a8ae-d581-4cb4-b651-ee22bd255f96 | 037509c4-2717-4774-98fd-4f45c9f06f4a |
| 记忆／快照 | 6fccaf4c-196b-45f5-9c0a-af0421135fb6 | aadbeeb9-1ddf-49c2-a387-142ae03cba0b |

两轮模型各 revision 1；cleanup 均 written-retained，模型／记忆／快照／原事件保留。
各四个精确 key ID 经后端只读核实已撤销，共八个；最终无在途执行。每轮 semantic-start
1、初建轮次 1，共 2；等待、格式修正和只读自查不另算实质修模。

授权记录 `10:12:22Z`；冷启动首个真实 turn `10:15:15Z`（2 分 53 秒），记忆任务首个
turn `10:29:07Z`（16 分 45 秒），均在 20 分钟内。首个到最后一个原生回合墙钟分别
**6 分 12 秒／16 分 57 秒**；到凭据撤销分别 **13 分 44.107 秒／18 分 0.075 秒**。
冷启动清理与随后开发有重叠，记忆任务含暂停和格式修复，不能直接比较墙钟。
原生累计活动分别 252.289／260.755 秒；记忆任务 paused 模式 138.845 秒。这些时间
互有重叠，不是纯语义建模时间，不能相加；宿主有效开发／文档分类计时 unknown。

按每个原生 thread 的最后累计量统计，包含失败调用及纠正，不重复累计通知：

| 任务／用途 | 原生执行数 | 输入 token | 输出 token | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 冷启动：建模／协作／自查／评价 | 5 | 168710 | 5197 | 173907 |
| 记忆快照：建模／协作／自查／评价 | 6 | 212480 | 5199 | 217679 |
| 合计 | **11** | **381190** | **10396** | **391586** |

逐角色明细在各 runtime-summary.json。冷启动／记忆任务分别 24／29 个上游请求，
均有终态；原生量不是完整上游金额结算，金额计量仍 PARTIAL。外部 Host 用量单列
unknown，不计任务费用。任务目标和额外等待不同，不据此推断记忆带来净降耗。

本批没有 backend／frontend、依赖或共享应用配置变更，不需重启应用服务；新 CLI／MCP
进程加载 v5 改动。GitNexus 对 v5 目标仍 UNKNOWN／not found，采用当前调用点、diff、
针对性和完整测试及真实运行验证，不宣称完整图影响。没有另设独立工程验收角色。
提交前 staged detect_changes 识别 18 个文件、0 个已索引符号／流程，返回 low；
该结果受索引缺口限制，不作为 v5 无影响的证明。
