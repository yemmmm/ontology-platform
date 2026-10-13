# 2026-10-14 小链建模准备独立工程测试

## 需求、范围与非目标

依据 [准备记录](../records/2026-10-14-modeling-readiness.md)、R4.3-003／015、R4.0-029 及当前 AGENTS.md，验证本次窄修改。独立测试 Agent 只记录结果、运行针对性测试；不修改产品实现，不启动真实模型或生产 run，不消费新建模轮次。

工程 PASS 不代表首链公开反馈实际完成、真实建模质量或 L1 语义验收 PASS；旧冻结分母保持原义。主 Agent 负责全 Team 回归，本测试不重复全套。

## 环境与通过标准

工作目录 `/home/yangxiang/ontology-platform`，从 backend 使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`。测试使用临时文件及确定性平台 fixture，不操作现存模型。GitNexus 未找到改动目标，采用 diff 和调用点核对，不宣称图谱覆盖。

通过标准：下列工程用例通过，且没有证据支持的 Critical／High 未解决缺陷；未执行的真实语义证据不得计为工程通过。

## 用例与预期

| ID | 验证步骤 | 预期 |
|---|---|---|
| T1 | 运行 applied reuse 测试并审查 bound intent/receipt/Attempt 路径 | 历史成功计划不因后续版本变化拒绝；未绑定、未完成及变化 projection 不能继承 applied 成功 |
| T2 | 运行 pending reuse、批准与版本漂移负向用例 | 待执行仍要求当前批准、真实身份、授权和版本；planned/dry-run/foreign 输出不能冒充成功 |
| T3 | 运行 Host issue-resolution 成功及 repair-only 字段负向用例 | guidance/abort 错字段给可修正反馈且不提交；合法 guidance 与 repair_completed 原通道可用 |
| T4 | 运行 evaluation 状态及日志边界用例，核对 Delivery operation 归属检查 | 仅选自身 operation 的有界日志、脱敏凭据；symlink／他人 operation 不得任意读取；报告绑定仍有效 |
| T5 | 用现有 CLI validate 校验新 Task，阅读来源与角色合同 diff | 范围仅资产—故障—工单及必要依赖；CQ 题数建议非硬门；隐藏资料隔离；首链交接采用现有 Host 指令与反馈通道 |
| T6 | 检查运行准备参数及历史凭据回归 | 明确只读凭据、session_timeout、实际 MCP 加载版本；checkpoint 使用 run-owned 凭据；工程与真实质量分开 |

## 测试轮次

待执行。最终结果按轮次追加，不覆盖历史。

### Round 1 — 独立工程验收 PASS（2026-10-14）

基线 HEAD：`f02d2568e1702a5ddcbd28afed66983ffc860074`，工作区包含本次未提交实现与提示变更；未修改产品代码、未启动真实 run。独立复核准备记录、需求 R4.3-015／R4.0-029、实现 diff、`applied_attempt_proof` 绑定逻辑及 DeliverySession 调用点。

| 用例 | 结果 | 实际证据 |
|---|---|---|
| T1 | PASS | 历史应用 reuse 保留覆盖；projection 变化、proof response digest 不匹配、recovering 和 unknown intent 均未继承应用成功 |
| T2 | PASS | 待执行陈旧读取、批准内容摘要变化、dry-run／planned／foreign／unbound item、后续漂移负向用例通过 |
| T3 | PASS | guidance／abort 的五种 repair-only 字段在 live 提交前给可重试错误；合法 guidance 与 repair_completed 相邻回归通过 |
| T4 | PASS | 当前 operation 日志尾部、有界与凭据脱敏、他人日志及 symlink 负向用例通过；DeliverySession 拒绝外来 operation；新旧 report／隐藏公开分离相邻回归通过 |
| T5 | PASS | 新 Task 使用既有 Profile／glm-flash-high 校验通过；只挂载四个获准 business-source 与既有合同，未引入隐藏题／答案；阶段交接走 Host delivery_guidance → Coordinator → Protocol，无新 transport edge 或代码硬门 |
| T6 | PASS（工程范围） | run-owned checkpoint 凭据回归通过；准备配置在临时 DeliverySession 成功加载，权限为 read/supervise，真实项目／凭据未伪造。启动消息 `delivery.py` 将完整 config 发给 Delivery，900 为模型可见的显式传参指令，非后端自动注入。实际下一轮 MCP 版本／凭据／feedback 未运行 |

执行命令（工作目录 `backend/`）：

```sh
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_coverage_applied_reuse.py ../modeling_team/tests/test_v43_production_refs.py ../modeling_team/tests/test_host_ops.py ../modeling_team/tests/test_delivery_ops.py ../modeling_team/tests/test_checkpoint_capture_credentials.py -q
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_delivery_session.py -q
```

结果：第一组 **158 passed**（50.12 秒，158 条 rdflib 弃用 warnings，无失败）；第二组 **23 passed**（6.51 秒）。不是全 Team 回归。

Task CLI 校验（仓库根目录）：

```sh
env -u DEEPSEEK_API_KEY uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r3-0-011-competency-question.yaml --task modeling_team/tasks/r4-0-009-asset-fault-workorder.yaml --model-profile glm-flash-high
```

输出绑定新 task_id、四角色 roster、八角色 GLM 5.3 Flash/high。首次测试命令误把 model-profile 文件路径传作 ID，被 CLI 拒绝；改为既有 profile ID 后通过，该测试输入错误不是产品缺陷。

独立配置加载探针：用 `yaml.safe_load` 读取 `docs/delivery/configs/2026-10-14-asset-fault-workorder.yaml`，在 Python `TemporaryDirectory` 内构造 `DeliverySession`；断言四个来源文件存在、task/profile/scope 文件存在、模型为 glm-5.3-flash/high、business_input_role=user、allowed_operations 仅 read/supervise、无 run/operation；尝试 start_run／start_evaluation／start_repair／外来 get_evaluation_status／`/etc/passwd` artifact 均被拒绝，临时目录随后删除。仅构造及被拒绝的调用，无生产写入、模型/API 请求。

配置可见性疑点复核：只搜索后端具体字段读取曾未找到 `delivery_objective`，但实际 bootstrap `runtime.send` 发送完整配置；据此撤销“900 未进入提示路径”的疑点，不列缺陷。

结论：独立工程 **PASS**，0 Critical／High 未决问题。未执行范围为真实 semantic start、真实首链公开反馈、未来 MCP 版本读回、真实项目只读 key 生命周期以及最终业务语义验收；按本次明确非目标保留“未测”，不据工程 PASS 宣称 L1 或真实效果改善。全 Team 回归由主 Agent 单独记录。

### Round 2 — 增量提示与日志隔离核对 PASS（2026-10-14）

工作区延续 Round 1，新增 Protocol 1154 附近五行复用来源说明；无产品实现变更。复核结果：与实现一致，pending 仍核当前版本、候选批准；历史应用保留已批准覆盖；一般 SPARQL、任意 receipt、planned outputs、dry-run 不冒充 bound applied item。

针对新增 evaluation log_tails 的实际输出边界复核：`__main__.py::_cq_execute_batch` 输出仅 run/batch/freeze、report 路径、question IDs、blind/status 和 PASS 元数据；`_run_public_feedback` 输出 status、feedback 路径及 formal_acceptance=false。答案与 Judge 结果落入私有报告；acceptance child 的 stdout/stderr 由 Adapter 的 PIPE、stdout pump 与 stderr drain 消耗，不直接继承到父 CLI 日志。

独立可执行 canary 探针（同一 backend Python 环境）复用现有 `test_r3011_acceptance_cli` helpers，在 TemporaryDirectory 写入隐藏题 `INDEPENDENT-HIDDEN-QUESTION-CANARY`、答案点 `INDEPENDENT-HIDDEN-ANSWER-POINT-CANARY`，以确定性 Adapter 返回 `INDEPENDENT-HIDDEN-CONSUMER-ANSWER-CANARY` 并让 post-read 失败，运行实际 `_run_cq_acceptance` partial 终结路径。断言返回 1、私有 report 确实含 Consumer 答案、stdout JSON 仅既有 summary 白名单，stdout/stderr 均不含三种 canary。结果 **PASS**；无模型、子进程或真实 run。该证据覆盖当前输出合同，不宣称任意未来日志内容自动过滤隐藏语义。

主 Agent 汇总工程结果（独立测试 Agent 不冒充自行执行）：

- 全 Team：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short`，**2820 passed, 11 skipped, 318 subtests passed**，356 warnings，250.73 秒；日志 `/tmp/modeling-readiness-team-tests.log`。skipped 不计为通过。
- 主 Agent 的 checkpoint credentials／Host MCP／v4.3 references 复核：**47 passed**，29.42 秒。
- 主 Agent 报告 JSON/YAML、路径、链接及 diff 检查通过；最后 Protocol 五行提示增量的合同复验仍在执行，由主 Agent追加终态。

最终独立工程结论 **PASS**，0 Critical／High 未决缺陷。真实建模／反馈效果与 L1 语义验收仍未测。本次改动不含 backend/frontend，无需以服务重启建立虚假的 MCP 更新证据；实际新进程加载版本在获准启动时验证。

Round 2 终态追加：主 Agent 在最终 Protocol 提示增量后执行 Host MCP 与 v4.3 references 合同复验，**41 passed**，158 warnings，29.89 秒；日志 `/tmp/modeling-readiness-final-contracts.log`。该增量所需复验已完成，不再扩大测试。Round 2 独立工程 PASS 保持；真实语义未测边界保持。
