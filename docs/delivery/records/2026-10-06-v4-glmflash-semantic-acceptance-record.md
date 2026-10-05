# V4 GLM5.3Flash 建模与有界语义验收记录

## 最新结果：SCO-001 v2 已批准，最终24/26，REVISE

用户回复“同意”后，新增授权的第3次生产接续为 `r4009-20261006-glmflashhigh-add03-start3`，
真实 semantic start 于 **2026-10-05 22:00:34.424206 UTC**（Asia/Singapore 次日06:00）确认。
新增3/3、累计6/6已用，余额0；独立只读验收不额外消耗启动次数。

- 通过既有 `cq_review modify` 处理 SCO-001 v2，CQ 角色后续 `cq-review-0008` 与批准草案逐字一致，经审核冻结最终 `freeze-0003` / `cq-batch-0003`。
- 完整26题逐项核对：只变 SCO-001 的 question 与 content_version，其四必答点、unknown、evidence_refs、scope及其他25题完全不变。原 freeze-0001、过程 freeze-0002、旧 FAIL 均保留。
- 最终冻结摘要：`sha256:4e491c729e36361376ba23d9beb7685da7c20ace35344ab74628d5df35846651`。
- 15份候选与源 run 逐字节一致；本轮零新 apply。Protocol 对空 Session 零提交/零写入取消，三生产角色完成，handoff ready、read-only、无 pending/unknown writes。
- **公开18/18、隐藏6/8，同轮24/26，REVISE**。26题均执行且具有有效独立 Judge 裁决，未拼接旧轮通过题。
- 公开71条、隐藏40条读取响应复核稳定，工具/请求/响应/文件/分页绑定核对通过，验收前后无模型漂移。Consumer 与 Judge 的实际配置均为 `glm-5.3-flash` / `high`。
- 隐藏2题为 `model-recall-insufficient`，具体原因尚未定位；有效读取绑定不证明模型缺失或 Consumer 过错。其内容、评分依据和原裁决仅保存在私有证据中，不回流生产或修复者。
- 空 failure_layer 格式错误曾被类型化拒收，角色同线程修正后完成完整报告；没有放宽报告合同或使用非法裁决。
- `complete_cq_acceptance` 与 stop 回执 accepted；Runner **CLEANED**、PID不存在，全部验收子进程/私有根目录已清理，3个临时验收身份密钥已撤销，模型与治理资源保留。未安排后台观察。

### 本轮检查点与宿主缺陷

宿主原 launcher 在异步 launch 返回后立即投递 guidance，FIFO 尚未创建而异常进入 finally，
提前撤销了 Runner 继承的 bootstrap。Host 同 run 修正投递后正常推进，不增加一次 start；
但两次 `cq_frozen` 及 `production_handoff` 自动检查点捕获返回 **HTTP401 / invalid_authentication**。
本 run 没有新发布的有效检查点，不能将角色完成或 handoff ready 称为当前 checkpoint 保存成功。
源 run 的 `materialization_progress-0002` 再次检查 ready、0 issues，当前候选/模型未变；
新 CQ 冻结与独立报告保留在本 run，不假称包含于源检查点。
此宿主生命周期失败与隐藏2题语义未满足分别记录，不能互相归因。

退出监控线程随原 launcher 异常丢失，旧 managed record 仍为 launched；实际 stop/CLEANED/PID消失证据已另存，
退出码无法核实，不倒改旧记录。宿主路径窄修复由 Claude Code `glm-5.3` / `high` 执行，
仅修复版 launcher 与权威运行指引；不重新启动 Team、不改旧冻结/报告、不覆盖原401。
修复版等待FIFO并窄重发，将存活或无PID等不可核实状态的凭据保留待对账，只在确切退出后撤销。
最终隔离验证19/19、重试分支3/3及py_compile通过；原脚本保留，新版在宿主目录 `launch-start6-safe.py`。
权威运行指引补充10行；未真实重跑该路径，因此尚不证明下一次真实启动的检查点捕获已恢复。

后续生产修订需先定位剩余失败，并取得新的 semantic-start 授权。V4整体仍为 PARTIAL；
该结果不能代替全部 A1—A12、映射执行、L2/L3或真实DL推理证据，`development_stub` 限制保持。
详细凭据清理、资格核对、回执和检查点限制见宿主目录的 `start6-*`、`final-acceptance-resource-cleanup.json`。

## 以下为用户批准v2之前的历史中间态

截至 2026-10-06 03:55（Asia/Singapore），R4.0-009 本轮结论为 **REVISE**；V4 整体仍为 **PARTIAL**。
范围为 `industrial-service-v3` 四切片、冻结公开18题与隐藏8题的核心 CQ L0/L1，未覆盖全部 A1—A12、数据库/API 映射执行、L2 或 L3。

## 授权与配置

原三次建模授权已使用；用户新增三次授权，本轮使用2次，剩余1次。只读独立验收不消耗 semantic starts。
生产角色、Consumer 与 Judge 实际配置核对为 `glm-5.3-flash` / `high`；修复通过外部 Claude Code `glm-5.3` / `high` 执行。
首轮从零建模的原始运行、失败与写入证据保留；新增两次从可恢复生产检查点接续，没有重复应用已成功写入。

| 本轮运行 | 真实启动 UTC | 公开题 | 隐藏题 | 同轮全分母 |
| --- | --- | --- | --- | --- |
| `r4009-20261006-glmflashhigh-add03-start1` | 2026-10-05 16:44:35 | 11/18 | 8/8 | 19/26，REVISE |
| `r4009-20261006-glmflashhigh-add03-start2` | 2026-10-05 18:41:53 | 17/18 | 5/8 | 22/26，REVISE |

不拼接不同运行的通过题。第二轮全部26题均执行并具有独立 Judge 裁决，4题为 `model-recall-insufficient`；这不是模型知识缺失率。

## 建模、写入与验证

第一轮保留原模型并补充7项关闭资格/修订复审表达。第二轮 Modeling 根据获准来源复核已有表达，保留原核心候选108项，增加4项库存事件属性声明（时间、数量、引用类型、引用标识），完整候选112项。
Schema/样本仍作为映射证据；没有把关系数据库业务行复制成 RDF 实例，生命周期、库存推导及引用等价性等未确认含义保留为未知。

第二轮当前 plan 经自身 dry-run 与 application 成功，0 findings；属性20→24，其余资源计数不变，新增4项逐一回读完整。Build Session 已正常完成、lease 释放，handoff ready、read-only、没有 pending/unknown writes。
原生 asserted-only 验证通过；推理返回 `development_stub`，不证明真实 DL 一致性。生产角色完成与机械验证均不代替语义验收。

## 独立验收与诊断边界

第二轮公开62条、隐藏46条响应重放稳定，文件/请求/响应/分页绑定核对通过，验收前后无模型漂移。两个验收子进程及其私有根目录均已清理。
Runner 接受隐藏8题报告的 `complete_cq_acceptance` 收口；该结果不能覆盖公开18题，也不能使全26题变为 PASS。

公开唯一失败为 SCO-001：题目询问对象关系与身份区分，必答点另要求来源行/RDF边界；该边界已有表达且出现在其他题读取中，没有出现在本题回答和读取中。
Claude Code 复核指出题意与必答点范围不一致，已准备保留四必答点的 v2 问题草案，尚待用户确认；没有修改原冻结 v1、原评分、Consumer 提示或生产模型以迎合评分。
隐藏3题失败的根因尚未定位；有效读取绑定只证明诊断证据可用，不能证明模型缺失或 Consumer 过错。隐藏题、评分依据与原 note 保存在私有证据中，不回流生产角色或修复者。

## 收尾与下一动作

第二轮 source stop 请求 accepted，PID 已消失；`materialization_progress-0002` 停止后核对 ready、0 issues、允许生产恢复。
宿主 daemon 重启使 launcher/reaper 丢失，旧 managed launch record 仍为 launched，退出码无法核实；不伪造 exited 或退出码。
按启动时间和名称核对残留的本轮临时 bootstrap key，通过既有生命周期 helper 撤销并记录；Runner 自身临时 key 已撤销。模型、失败证据、检查点及后续验收需要的普通身份保留。

下一动作是处理 SCO-001 v2 的明确 CQ 审核决定；任何新冻结版本走既有修订/批准/冻结合同并重新独立验收。剩余1次生产启动不能自动追加，也不能仅为消耗授权重建已有正确表达。
R4.0-023 仍仅登记，待细化设计，本轮没有实现诊断 Agent 编排。

本记录对应证据目录 `workspaces/v4-acceptance-20261005/`（授权台账、配置核对、资格诊断、收口/停止回执、检查点与 cleanup）和上述 run 的 `acceptance-v3/`（公开 `public-regression`、隐藏 `reports`）；本地证据未作为源代码提交。
相关修复提交为 `ea8bbd7`、`d00ddb8`、`2e7c4ef`、`4fb2866`、`7384ed2`。运行合同修复的全量 Team 回归2465 passed / 8 skipped / 314 subtests passed；最新交接指令225项针对性验证通过。此记录与索引更新仅进行 diff、链接和格式检查，不重启服务，也不将这些检查列为模型质量证据。
