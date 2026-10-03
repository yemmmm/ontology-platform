# R4.0-014 交付记录

- 权威范围：[R4.0-014](../../requirements/requirements-v4.0.md#r40-014-场景地图进度与实际产物同步)。
- 已审阅设计：[场景地图进度同步设计](../designs/2026-10-03-r4-0-014-scenario-map-progress-design.md)。
- 独立验证：[测试记录](../test-plans/2026-10-03-r4-0-014-scenario-map-progress-test-record.md)。
- 用户授权：按设计完成开发与测试；本轮不追加真实 semantic start，A9 留待后续授权。
- 实现基线：`96b90c5e1eea318a776484cae9ff43003a5c6b49`，起始工作区干净。
- 状态：实现及开发回归完成，A1—A8 受控独立功能最终 Round 4 PASS；A9 未授权、未执行，整体 PARTIAL。
- 提交：本记录随实现提交；不可变 hash 可通过 `git log -- docs/delivery/records/2026-10-03-r4-0-014-scenario-map-progress-delivery-record.md` 定位。

## 实现与范围

保留 `r4-0-007-scenario-map/v1`、四个 viewpoint 状态与原封闭字段。007 reference 增补状态
含义和维护说明，Coordinator 指令明确实际候选核对、部分范围／修订、唯一写图、生产 terminal
前同步；Modeling 指令及 Skill 补齐已有消息交接信息；CQ 明确同范围进度通知不重开冻结池。
宿主 Skill/runbook 衔接计划／紧急保存、生产或只读恢复、fork、绑定后差异说明。

不改 Runner、校验器、mount、checkpoint／recovery、摘要或后端接口；新增测试复用现有入口，
证明四态和封闭字段不变、普通 note 过期不是新硬门、合法 note 修改仍受 handoff digest 保护、
语义阶段保存能恢复地图和候选且可写副本更新不覆盖源。没有 backend/frontend 改动，不运行
产品套件或重启服务；没有保留 run、历史地图或平台资源写入。

## 验证及证据边界

开发回归从 `backend/` 执行：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_r4007_scenario_map_contract.py \
  ../modeling_team/tests/test_r4007_multiview.py \
  ../modeling_team/tests/test_r4012_role_contract.py \
  ../modeling_team/tests/test_r30015_checkpoints.py \
  ../modeling_team/tests/test_r30017_checkpoint_data.py \
  ../modeling_team/tests/test_r30002_runner_wiring.py \
  ../modeling_team/tests/test_r3006_unified_binds.py \
  ../modeling_team/tests/test_r3011_runner_wiring.py -q
```

结果 `160 passed in 11.75s`。首轮新增恢复 fixture 误用不含候选的 cq_frozen 阶段，
`34 passed, 1 failed`；修正为 semantic_approved＋既有审批 fixture 后通过，未修改恢复引擎。
两个 Skill 的 `quick_validate.py`、Modeling Skill evaluator、变更测试 Ruff 和 diff 检查通过。
GitNexus `detect_changes(scope=all)` 为 LOW，无 affected_processes；索引映射旧章节，不能据此
证明角色语义或完整图谱覆盖。未修改调用关系、公开接口或跨模块运行行为，使用定向现有挂载
和装载测试核对影响。

受控测试使用独立子 Agent 加载实际 Modeling／Coordinator／CQ 指令、已有 reference 与获准
合成输入；真实 LLM 产生消息及地图，独立测试者对照实际候选内容，不用预写输出判 PASS。
这是指令加载后的有界行为测试，目录权限由任务交接约定，不是完整 Team Runtime／bwrap／
真实 Team Transport 集成运行。装载、挂载、保存、恢复和摘要边界另由既有机械合同回归验证。
全部输出在 `workspaces/r4014-controlled-20261003/`，不是生产 run，消耗 0 semantic starts。

首轮实际行为发现 M014-01：Modeling 将缺失候选文件误称 explicit_unknowns，Coordinator
也将其抄入地图。保留首轮消息／地图，持久修正 Modeling 指令、Skill、Coordinator 指令和
007 reference，明确文件／审批／应用／计划缺口属于进度或证据待办，只有真实业务未决含义
进入 explicit_unknowns；proposal 本身不证明语义歧义。修复不新增结构或平台校验。

修后第二轮 Modeling 正确区分当前 r2 和源 r1，第三轮同 oral 缺文件分支也不再声称业务
unknown。Coordinator 第二轮正确处理表达失效与无关内容，但仍保留旧图误分类条目，且正常
交接消息混淆角色 terminal 与宿主摘要绑定顺序；保留第二轮输出，再补清恢复时校正已有
误分类而不删真实未知，以及“Coordinator 同步并 terminal → 宿主静默／排空 → 发布绑定”的
职责顺序。仍只修 Coordinator／reference 的现有说明，不增加自动校验或硬门。

## 最终独立结论与停止边界

独立测试由 `/root/r4014_independent_test` 承担，只写测试记录，不创建或修改受测角色输出。
独立执行机械回归 98 passed in 10.76s，修后结构回归 8 passed in 0.11s；最终受控行为
Round 4 PASS，M014-01／M014-02 均经实际同分支输出核对 FIXED，无剩余已知缺陷。
修后开发直接相关回归 35 passed in 0.95s；未变的保存／恢复机制复用前述 160／98 项证据。

[稳定行为证据](../evidence/2026-10-03-r4-0-014/manifest.json)保存 15 个获准合成输入、
逐轮消息／地图及当前指令摘要；独立检查确认全部与工作目录源逐字节一致、最终五个指令
摘要匹配，失败快照未变。第三轮 Coordinator 正确清理旧图误归类而保留两项真实 trigger
未知，流程当前表达缺失为 pending，仍有效规则和对象为 modeled，shared-a 仍 proposed。
正常顺序明确为同步地图 → Coordinator terminal → 宿主静默／写排空 → handoff 摘要绑定；
绑定后只作宿主差异说明，获准生产恢复更新可写副本，源回执不触发重放或授权 fork apply。

A1—A8 的结论限于受控指令行为＋现有机械合同：没有完整 Team Runner／真实平台写入或
恢复 E2E，不能据此宣称模型质量或真实语义 PASS。A9 按权威需求单独等待后续真实运行授权，
整体 PARTIAL。当前开发／测试授权范围已完成，不继续增加机制或追加运行。

最终 JSON／Markdown 围栏与 70 个本地链接／锚点检查通过，Ruff通过。两份原始 Modeling
消息的末尾空行按源字节保留；暂存差异检查仅忽略 blank-at-eof，其他空白问题仍检查。
