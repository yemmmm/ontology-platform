# R2.2-001 本体建模团队 L0 共享测试计划

## 1. 范围

本计划验证 `docs/requirements/requirements-v2.2.md` 的 L0，不验证真实本体写入、建模质量、
Consumer/Judge/mutation、Pi 兼容或产品化 Runtime。

设计基线：
`docs/delivery/designs/2026-07-29-r2-2-001-ontology-modeling-team-l0-design.md`。

所有独立测试轮次追加在本文末尾，不创建第二份 L0 测试文档。

## 2. 完成门

| ID | 完成门 |
| --- | --- |
| L0-01 | 输入 manifest 精确集合和 SHA-256 校验，未知、缺失或变化文件 fail closed。 |
| L0-02 | 全新非 fork/resume coordinator Session；start 阶段提取真实 Session ID。 |
| L0-03 | 两次 spawn 均显式 `agent_type` + `fork_turns=none`，两个 child rollout 可区分。 |
| L0-04 | 建模 Agent 产生固定非答案型描述；其 child rollout 无平台 MCP 调用。 |
| L0-05 | 全团队工具面只有 global-safe health MCP；只有协议 Agent实际调用并取得真实响应。 |
| L0-06 | 协调 Agent产生唯一问题，run 进入 WAITING_FOR_ANSWER。 |
| L0-07 | resume 使用原 coordinator Session ID，原始回答被路由给建模 Agent并完成。 |
| L0-08 | `/opt` 只读、`/work` 可写；仓库、宿主 `.codex`、历史 run 和 tester-only 不可见。 |
| L0-09 | 临时 CODEX_HOME 不含宿主 Session、Memory、plugin、hook 或历史状态。 |
| L0-10 | 根 JSONL、child rollout、hash、隔离探针、角色、MCP、问题/回答和终态审计完整。 |
| L0-11 | terminal/provider/MCP/超时失败快速结束并保留真实失败分类。 |
| L0-12 | run 资源和临时 key 可清理/撤销；常驻 backend/frontend 保持健康。 |

## 3. 离线自动化

使用 fake Codex JSONL fixture，不调用模型：

1. start 成功事件解析、Session ID 保存和 WAITING 状态；
2. resume 必须复用保存 ID，不能传入另一个 ID；
3. 缺角色、角色重复、缺 MCP、协调/模型 Agent调用 MCP、缺问题或伪 COMPLETE 被拒绝；
4. provider/turn/tool failure 映射到真实失败分类；
5. manifest 缺失、额外文件、hash 变化和 symlink 被拒绝；
6. run ID、路径和重复 run fail closed；
7. tester-only sentinel 和宿主路径不出现在 Agent mount set；
8. audit 不写入 auth 内容或完整宿主配置；
9. start 不使用 `--ephemeral`，resume 使用同一临时 CODEX_HOME；
10. timeout 终止 Codex 子进程并产生 INCONCLUSIVE 证据。
11. Agent prompt 必须显式生成两个 `agent_type` 且 `fork_turns="none"` 的 spawn；
12. 根 marker 不能代替 child rollout；缺 child thread/rollout/MCP item 必须失败；
13. 临时 key 不是 read-only、复用长期 key、进入 transcript/audit 或结束后未撤销必须失败。
14. Codex argv 必须保留 `workspace-write` sandbox，使用全局 `--ask-for-approval never`；根 MCP
    必须 `required=true` 且 health tool approval 为 `approve`。生成完整 run-local 配置后，
    `codex --strict-config doctor` 或等价严格解析检查必须通过。出现全量 bypass、Agent执行
    curl/wget/socket/额外 MCP/平台调用必须失败。

建议命令：

```bash
uv run python -m unittest discover \
  docs/evaluation-scenarios/ontology-modeling-team-l0/tests
```

## 4. 真实 L0

前置：

- `bwrap --version` 成功；
- `codex --version` 成功且 `multi_agent` enabled；
- `curl --fail http://127.0.0.1:8001/api/health` 成功；
- 宿主 Codex auth 可用；
- 宿主已配置一个有效 project-scoped read key；launcher 只复用其 `project_id`，能创建并在
  cleanup 撤销一个同 Project、仅 `read` scope 的临时 API key；
- 工作树中的冻结 input/config hash 与 manifest 一致。

执行：

```bash
python docs/evaluation-scenarios/ontology-modeling-team-l0/run_l0.py \
  start --run-id <fresh-id>
python docs/evaluation-scenarios/ontology-modeling-team-l0/run_l0.py \
  resume --run-id <same-id> --answer accepted
python docs/evaluation-scenarios/ontology-modeling-team-l0/run_l0.py \
  audit --run-id <same-id>
```

实际命令以实现后的 `--help` 为准，测试记录必须保存精确命令。

真实检查：

- Session ID 来自 Codex start JSONL；
- start/resume transcript 具有相同根 Session ID；
- 两个 spawn 的 `agent_type` 正确且 `fork_turns="none"`，并有不同 child thread ID；
- 两个 child rollout 均存在且 hash 被审计；
- MCP tool name 固定为 `check_platform_health`，调用 item 只位于 protocol child rollout，结果为
  当前平台真实响应；coordinator/modeling rollout 均无 MCP call；
- 临时 API key 数据库记录只有 `read` scope，JSONL/输出/审计不含 plaintext，cleanup 后 revoked；
- Codex 内层 sandbox 保持启用，MCP approval 配置精确允许唯一 health tool；三个 rollout 无任意
  外部网络命令或额外 MCP/平台调用；
- 问题与回答不包含 tester-only sentinel；
- audit 状态为 COMPLETE，所有 L0-01 至 L0-12 有证据或明确不适用。

## 5. 隔离负向检查

必须由 launcher 探针和独立测试分别证明：

- `/home/yangxiang/projects/ontology-platform` 不存在；
- `/home/yangxiang/.codex` 不存在；
- tester-only sentinel 绝对路径和内容均不可读取；
- `/opt` 写入失败；
- `/work` 写入成功；
- 不能通过 symlink、`..`、额外 bind 或环境变量取得禁止路径；
- 临时 Codex home 除认证、配置和本轮 Session 外没有宿主状态；
- Agent 输出若出现 sentinel 或禁止路径读取成功证据，真实 run 作废。

L0 使用同一 OS 身份的 Codex 多 Agent，不宣称临时配置对其他角色构成生产级秘密隔离。负向测试
要求没有 Agent 实际读取或输出 key，并以 read-only scope 和结束撤销限制影响；更强凭据隔离属于
后续产品化范围。

Codex 0.146.0 下，L0 的 run-local MCP 配置会让三个角色都看见唯一的 global-safe health 工具；
这只验证行为职责，不验证角色级工具可见性。测试必须拒绝 coordinator/modeling child 的任何 MCP
调用。L1 不得共享写 MCP，并在进入真实写入前把 per-agent MCP 作为独立前置门。

L0 使用全局 noninteractive approval `never` 和 MCP server/tool `approve`，但保留 Codex 内层 sandbox。
长期 Codex auth 与宿主网络同时存在时，全量 bypass 是失败条件；rollout 中除唯一 health MCP 外的
网络或平台行为同样失败。

## 6. 回归、清理和健康

- 文档/脚本执行 `git diff --check`；
- Python 文件执行 Ruff；
- 如实现未修改 `backend/` 或 `frontend/`，不要求全量 backend/frontend 回归和 service restart；
- 仍必须在真实 run 前后检查 `8001/api/health` 和 `5173/`；
- 只清理可由 run ID 唯一证明归属的临时进程和 runtime 数据；
- PASS/FAIL/INCONCLUSIVE 都必须撤销本轮临时 key；
- 失败证据保留，认证副本在测试完成后删除或权限保持 `0600` 并由清理命令删除。

## 7. 结果规则

- `PASS`：L0-01 至 L0-12 全部通过，真实 start/resume 和独立测试均有证据；
- `FAIL`：可重复的合同违例或隔离失败；
- `BLOCKED`：外部依赖明确不可用，且离线结果不能替代真实门；
- `INCONCLUSIVE`：真实运行没有形成足以判断合同的完整证据。

不得用 fake Codex、单 Agent 输出、不同 coordinator Session、Host 代写 marker 或仅 Prompt 声明隔离
替代真实 PASS。

## 8. 独立测试轮次

### Round 1 — 2026-07-30T01:17:01+08:00 — FAIL

测试对象为冻结的未提交工作树；本轮不修改产品实现。真实运行证据使用开发交接保留的
`l0-r22-real-20260730o`（不使用前一轮 `n`）。

已通过：

- `uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l0/tests`：17 tests PASS。
- `uv run --directory backend ruff check ../docs/evaluation-scenarios/ontology-modeling-team-l0`：PASS。
- `git diff --check`：PASS；`curl --fail http://127.0.0.1:8001/api/health` 返回 `{"status":"ok"}`，
  frontend `5173/` 可达（测试前后均检查）。
- `o` 的 `strict-config-pre-key.json` 和 `strict-config.json` 均为 `passed=true`；state 为
  `COMPLETE`，同一 coordinator session ID 出现在 start/resume；两个不同 child rollout 分别证明
  `modeling_agent`、`platform_protocol_agent` 的显式 `agent_type` 与 `fork_turns="none"`。
- coordinator/modeling rollout 的平台 MCP 调用数为 0；protocol child 仅一次
  `check_platform_health`，真实结果为 PostgreSQL `status=ok`。临时 key 的数据库记录为同 Project、
  仅 `read` scope 且已 revoked；证据中未发现 tester-only、宿主路径、curl/wget/socket 或全量 sandbox
  bypass。`auth.json` 保持 `0600`，`final-audit.json` 为 `0400`。

缺陷：

| ID | 严重度 | 复现步骤 | 期望 | 实际与证据 |
| --- | --- | --- | --- | --- |
| T-R2.2-001-L0-01 | High | 对已完成的 `l0-r22-real-20260730o` 执行 `uv run --directory backend python ../docs/evaluation-scenarios/ontology-modeling-team-l0/run_l0.py audit --run-id l0-r22-real-20260730o`。 | 独立验收可安全重算/覆盖同一 `final-audit.json`，继续保持 `0400`；若不能执行，应以有界 `L0Error` 报告。 | 命令在 `write_audit()` 覆盖已有 `audit/final-audit.json` 时抛出未捕获 `PermissionError: [Errno 13] Permission denied`。该文件由首次审计设置为 `0400`，而 `audit()` 未像 `save_state()` 一样临时恢复写权限。本计划第 4 节规定的独立 `audit` 命令无法复验，故 L0-10/L0-12 的独立完成门未通过。 |

未执行：未启动新的真实 run；现有 `o` 已提供完整 start/resume/协议调用证据，失败仅发生在该运行的
独立终态 audit 重跑。待开发者修复后，优先复测 T-R2.2-001-L0-01，再重跑 17 tests、Ruff、diff/health
及 `audit`。

### Round 2 — 2026-07-30T01:20:31+08:00 — FAIL

复测同一冻结工作树和 `l0-r22-real-20260730o`；本轮不修改产品实现。

- **FIXED — T-R2.2-001-L0-01（正常重审计路径）**：连续两次执行既有 `audit` 命令均 exit 0；每次
  `final-audit.json` 均包含正确 run ID、`COMPLETE`、`read` scope 与 coordinator Session ID，最终 mode
  为 `0400`。`write_audit()` 已在已有文件时先临时设为 `0600`，并将普通 I/O 错误归一为 `L0Error`。
- `uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l0/tests`：18 tests PASS。
- `uv run --directory backend ruff check ../docs/evaluation-scenarios/ontology-modeling-team-l0`、`git diff --check`、
  `curl --fail http://127.0.0.1:8001/api/health` 与 frontend `5173/`：PASS。
- Round 1 已复核的完整 L0 真实运行证据继续有效：两份 strict-config receipt、同一 coordinator
  start/resume、两个显式角色 child rollout、protocol child 唯一 `check_platform_health` / PostgreSQL ok、
  read/project-scoped/revoked temporary key、无禁止路径/外部网络命令/全量 bypass。

缺陷：

| ID | 严重度 | 复现步骤 | 期望 | 实际与证据 |
| --- | --- | --- | --- | --- |
| T-R2.2-001-L0-02 | High | 在临时目录先以 `write_audit(..., "final-audit.json", ...)` 创建 `0400` receipt；mock `Path.write_bytes` 抛出 `OSError` 后再次写同一文件。 | 失败应为有界 `L0Error`，且既有 receipt 无论成功或失败均恢复 `0400`。 | 已正确抛出 `L0Error("audit evidence write failed: final-audit.json")`，但因先 `chmod 0600` 后写入失败、没有 `finally` 恢复，receipt 实测遗留 mode `0600`。现有第 18 个测试只覆盖不存在的 `io-failure.json`，未覆盖已有只读 receipt 的失败回滚。 |

未执行：未启动新的真实 run；失败是本地可控 I/O 边界，不能用正常路径的两次 audit 成功替代。建议开发者在
`write_audit()` 中以 `finally` 恢复既有 receipt 的 `0400`，增加该情形的回归测试，然后以同一计划进行
Round 3 复测。

### Round 3 — 2026-07-30T01:23:54+08:00 — FAIL

复测同一冻结工作树和 `l0-r22-real-20260730o`；本轮不修改产品实现。

- **FIXED — T-R2.2-001-L0-01 / T-R2.2-001-L0-02（入口失败路径）**：`o` 连续两次 `audit` 成功，
  receipt 内容有效且最终 mode `0400`；已有 receipt 的 `write_bytes` 入口 `OSError` 后旧 JSON 保留、
  mode 恢复 `0400`，错误为有界 `L0Error`。
- 恢复保护权限本身失败时，新增回归证明返回有界 `L0Error`（`audit evidence write failed and
  protection restore failed`），不泄漏底层异常。
- `uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l0/tests`：20 tests PASS。
  Ruff、`git diff --check`、backend health 和 frontend health：PASS。Round 1 的 strict-config、角色、
  MCP、same-session、key/隔离证据仍适用。

缺陷：

| ID | 严重度 | 复现步骤 | 期望 | 实际与证据 |
| --- | --- | --- | --- | --- |
| T-R2.2-001-L0-03 | High | 先创建已有 `0400` receipt；将 `Path.write_bytes` 替换为“以 `wb` 原地写入部分 JSON 后抛出 `OSError`”的受控 side effect，再重写同一 receipt。 | 写入失败不得破坏既有审计证据；旧内容应保持完整、可解析，错误为有界 `L0Error`。 | `L0Error` 和 `0400` 恢复均成立，但旧内容不保留、receipt JSON 不可解析。`Path.write_bytes` 是原地截断写，入口即抛错的测试不能证明中途/部分写失败安全。测试计划要求失败证据保留，且本仓库 Agent 运行约束要求确定性文件采用 atomic publication。 |

未执行：未启动新的真实 run；该缺陷在临时目录受控复现，不能由正常 audit 成功或权限恢复测试替代。建议
开发者以同目录临时文件写入、flush/fsync 并原子 replace（或等价机制）发布审计收据；失败时保留旧收据，
再进行 Round 4 复测。

### Round 4 — 2026-07-30T01:27:41+08:00 — PASS

复测同一冻结工作树和 `l0-r22-real-20260730o`；本轮不修改产品实现。

- **FIXED — T-R2.2-001-L0-03**：`write_audit()` 现以同目录 `mkstemp` 写入、循环 `os.write`、
  `fsync`、设置 `0400` 后 `os.replace` 发布，并 fsync 父目录。21 项回归覆盖 partial-write、replace
  failure 与 temporary-protection failure：每条失败路径均返回有界 `L0Error`、保持旧 receipt 内容和
  `0400`，且无 `.final-audit.json.*` 临时残留。
- 对 `o` 连续两次 `audit` 成功；`final-audit.json` 内容有效，mode 为 `0400`。
- `uv run python -m unittest discover docs/evaluation-scenarios/ontology-modeling-team-l0/tests`：21 tests PASS；
  backend Ruff、`git diff --check`、backend health 和 frontend health：PASS。
- 全部 L0 证据复核通过：两份 strict-config receipt 为 `passed=true`；state 为 `COMPLETE`；start/resume
  使用同一 coordinator Session；modeling/protocol child rollout 与 explicit `agent_type`/
  `fork_turns="none"` 证据完整；protocol child 唯一 `check_platform_health`，modeling/coordinator 无平台
  MCP；temporary key 为 project-scoped `read` 且已 revoked；transcript/audit/rollout 中无禁止宿主路径、
  tester-only、curl/wget/socket 或全量 sandbox bypass。

结论：L0-01 至 L0-12 的独立完成门通过；Round 1–3 的 High 缺陷均已复测修复。本轮无 Critical/High
缺陷，未启动新的真实 run。
