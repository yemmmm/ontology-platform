# R2.2-001 本体建模团队 L0 设计

## 1. 目标

L0 用一次可复核的真实 Codex 运行证明：

1. 交付 Agent 可以启动一个不继承当前对话历史的建模协调 Codex Session；
2. 建模协调 Agent 可以分别调度建模 Agent 和平台协议 Agent；
3. 平台协议 Agent 可以使用只读平台 MCP，建模 Agent 不负责协议调用；
4. 建模协调 Session 可以在外部回答后按同一 Session ID 继续；
5. 三 Agent 只能访问冻结输入和本轮工作目录，看不到宿主仓库、交付 Session 状态和测试方隐藏材料。

L0 不执行本体写入，不验证建模质量，也不选择最终 Runtime。

## 2. 已确认边界

权威角色定义见 `docs/requirements/requirements-v2.2.md`。实现只增加测试期 launcher、冻结输入、
Agent 配置、审计和测试，不增加 Host Workflow、Runtime Adapter、平台 API、数据库表或产品 UI。

当前 Session 是团队外的交付 Agent；新鲜 Codex Session 是团队内建模协调 Agent。交付 Agent只传递
冻结任务、用户原始回答、环境状态和控制指令，不把隐藏验收内容放入模型上下文。

## 3. 场景布局

提交到仓库的 L0 场景位于：

```text
docs/evaluation-scenarios/ontology-modeling-team-l0/
├── README.md
├── agent-input/
│   ├── manifest.json
│   ├── coordinator-task.md
│   └── modeling-source.md
├── agent-config/
│   ├── modeling-agent.toml
│   └── platform-protocol-agent.toml
├── tester-only/
│   └── isolation-sentinel.txt
├── run_l0.py
└── tests/
    ├── fixtures/fake-codex
    └── test_run_l0.py
```

真实运行产生的 gitignored 数据位于该场景的 `runtime/runs/<run-id>/`：

```text
staging/                 # agent-visible 的逐文件冻结副本，只读挂载为 /opt
team-work/               # 团队可写，挂载为 /work
temporary-codex-home/    # 只含认证、Session 和必要状态
transcripts/             # 交付 Agent保存的 JSONL
audit/                   # manifest、隔离探针、Session/角色/MCP/恢复证据
```

`tester-only/` 和宿主仓库不挂载进入 namespace。测试只用 sentinel 证明不可见，不把真实秘密写入
运行日志。

## 4. 运行机制

### 4.1 准备

`run_l0.py start --run-id <id>`：

1. 拒绝已存在或不符合命名规则的 run；
2. 校验提交的 agent-input manifest、精确文件集合和 SHA-256；
3. 复制允许文件及两个已审阅的 Agent 配置到 staging；
4. 创建空白 team-work 和临时 `CODEX_HOME`，只复制宿主 `auth.json`；
5. 由测试 launcher 在宿主侧解析已配置且有效的 project-scoped read principal，只复用其
   `project_id`，再通过现有 backend security helper 创建一个本轮唯一、同 Project、`read`
   scope 的临时 API key；长期 key 本身不进入隔离进程，把新 key 与唯一允许的
   `check_platform_health` server/tool 写入 run-local 根 MCP 配置，不挂载 `backend/.env`
   或宿主 Codex 配置；
6. 生成 run-local 配置，不复制用户 Memory、Session、plugin、hook 或项目配置；
7. 执行 bubblewrap 探针；
8. 在 bubblewrap 中运行持久化的 `codex --ask-for-approval never exec --json
   --sandbox workspace-write`，不使用 `--ephemeral`；根 MCP 配置把唯一 health server 标为
   `required=true` 且 `default_tools_approval_mode="approve"`，不得使用全量 sandbox bypass；
   启动真实会话前必须对生成后的完整 run-local 配置执行
   `codex --strict-config doctor`（或等价严格解析检查），配置无效时禁止启动；
9. 从 JSONL 的 thread/session start 事件提取并保存 coordinator Session ID。

### 4.2 Agent 配置

建模协调 Agent通过冻结 prompt 只能启动两个命名角色：

- `modeling_agent`：读取 `/opt/modeling-source.md`，产生固定、非答案型建模描述，不调用平台 MCP；
- `platform_protocol_agent`：调用 `ontology_platform.check_platform_health` 一次并返回规范结果。

两个 spawn 必须显式使用对应 `agent_type` 和 `fork_turns="none"`，不继承协调 Session 的对话。
Codex 0.146.0 的真实探针已证明自定义 Agent TOML 中的 `mcp_servers` 不会给该 child provision
角色专属 MCP。L0 因此在 run-local 根配置中向团队统一暴露且只暴露
`check_platform_health`；本轮 read-only key 不具有 model/admin scope，不能执行平台写入。
协调和建模 Agent虽然能看见同一个只读工具，但 Prompt 禁止调用，验收必须从三个 rollout 证明
只有 protocol child 实际调用。L0 只证明职责路由，不宣称角色级工具安全隔离。

任何写 MCP 都不得按这个共享方式开放。L1 在启用 Build Session、Lease 或 Modeling Batch 前，
必须先证明当前 Codex 可提供角色专属 MCP，或选择能够提供该边界的 Runtime；不能把 L0 的只读
共享例外扩展到写工具。

两个子 Agent 的最终输出必须带固定机器可读 marker。审计必须从协调 thread 的 collab tool item
取得两个 child thread ID，再读取临时 `CODEX_HOME` 中对应 child rollout，证明实际 agent_type、
`fork_turns="none"` 和 protocol child 内的真实 MCP item。协调 Agent最终消息中的 marker 只用于
快速定位，不能替代 child rollout 证据。L0 不依赖隐藏 chain-of-thought。

### 4.3 第一次终态

协调 Agent收齐两个子 Agent结果后输出：

```text
L0_NEEDS_ANSWER
question_id=l0-confirm-modeling-intent
question=<冻结测试问题>
```

`start` 命令成功条件是实际 coordinator thread ID、两个不同 child thread ID、child rollout 中
匹配的角色与 fork 合同、一次 protocol child MCP tool call，以及唯一的 `L0_NEEDS_ANSWER`。不满足
时状态为 `INCONCLUSIVE` 或 `FAIL`，不得用根摘要或伪造 Session 补足。

### 4.4 恢复

`run_l0.py resume --run-id <id> --answer <text>`：

1. 读取 start 阶段保存的 coordinator Session ID；
2. 使用相同临时 `CODEX_HOME`、相同 bubblewrap mount 和
   `codex exec resume <session-id> --json`；
3. 发送只含 question ID 和原始回答的 follow-up；
4. 协调 Agent把回答路由给建模 Agent，取得确认 marker；
5. 输出 `L0_COMPLETE`、原 Session ID、路由目标和结论。

恢复阶段不得启动新的 coordinator Session，也不得读取交付 Session 或 tester-only。

## 5. 隔离

bubblewrap namespace：

- `--ro-bind` Codex 二进制、系统 Runtime、冻结 staging 和平台 MCP 所需 backend Runtime；
- `--bind` team-work 与临时 `CODEX_HOME`；
- 不挂载仓库根、宿主 `~/.codex`、tester-only 或历史 run；
- 使用 `--clearenv`，仅恢复运行所需环境；
- 禁用 apps、browser、web search、plugins、memory 和 hooks；
- 保留 Codex `workspace-write` 内层 sandbox，保护临时 `CODEX_HOME/auth.json`；bubblewrap 继续
  作为宿主文件允许列表；
- 使用全局 `--ask-for-approval never` 和 MCP server 级 `approve` 消除 noninteractive approval，
  但不得使用 `--dangerously-bypass-approvals-and-sandbox`；
- namespace 为模型 provider 和本地平台 MCP 保留宿主网络，角色 Prompt 与 rollout 审计仍禁止
  任意 curl/wget/socket、额外 MCP 或平台调用。

隔离探针必须证明：

- `/opt` 可读不可写；
- `/work` 可写；
- 宿主仓库路径、宿主 `~/.codex` 和 tester-only sentinel 不存在；
- 临时 `CODEX_HOME` 在 start 前只含允许认证与配置材料；
- 团队共享 health MCP 能启动且只有 protocol child 实际调用；本轮 key 经数据库记录验证只有
  `read` scope，且未进入 prompt、Agent 输出、JSONL tool 参数/结果或审计正文。

## 6. 审计和失败

每个阶段保存原始 JSONL、退出码、耗时、实际 bwrap argv 的脱敏形式、输入/配置哈希和解析摘要。
child rollout 作为原始 Codex 证据保存在临时 `CODEX_HOME`，审计只记录其 thread ID、相对路径、
角色、关键 item 类型和文件哈希，不复制隐藏推理。

稳定状态：

- `PREPARED`：输入和隔离探针通过；
- `WAITING_FOR_ANSWER`：start 的三个角色/MCP/问题证据完整；
- `COMPLETE`：同 Session resume 和回答路由完成；
- `FAIL`：合同明确被违反；
- `INCONCLUSIVE`：Codex/provider/MCP/事件格式等基础设施阻止结论。

任何 provider 或 Agent terminal failure 必须立即停止，不用大超时掩盖。失败 run 保留证据，不在原
run 上重启 start；只有合法 WAITING run 可以 resume 一次。无论 PASS、FAIL 或 INCONCLUSIVE，
cleanup 都撤销本轮 read-only key；无法证明 key 已撤销时不得完成 L0。

## 7. 当前最小安全决定

- L0 创建并撤销一个绑定到当前授权 Project、只有 `read` scope 的临时 MCP key；宿主长期 key
  只用于解析授权 Project，不进入 Agent namespace、prompt、配置或 transcript，也不挂载
  backend `.env`；
- L0 不声称同一 Codex/bubblewrap OS 身份内具备生产级角色间秘密或只读工具可见性隔离；
- Codex 0.146.0 不提供已验证的 per-agent MCP provisioning；L0 只允许共享一个 global-safe
  read health tool，并以 rollout 证明只有协议 Agent实际调用；
- L0 使用窄化的 noninteractive approval `never` 和 MCP approval `approve` 并保留内层 sandbox；长期 Codex auth 与宿主
  网络同时存在时严禁全量 sandbox bypass；
- 不实现通用秘密代理、远程执行或 Runtime 插件框架；
- Agent 配置和 input manifest 是提交、可审阅、可哈希的测试材料；
- `tester-only` 是测试分类，不进入产品术语；
- Pi、Consumer、Judge、mutation 和真实 Modeling Batch 留给后续需求。

## 8. 验收

共享测试计划：
`docs/delivery/test-plans/2026-07-29-r2-2-001-ontology-modeling-team-l0-test-plan.md`。

完成需要离线 launcher/解析/隔离测试、真实 Codex start/resume、真实平台 health MCP、独立测试、
资源清理和常驻服务健康。任何一项无法证明时，R2.2-001 L0 保持未完成。

实现结果（2026-07-30）：权威 fresh run `l0-r22-real-20260730o` 完成 start、唯一问题、同一
coordinator Session resume 和终态 audit；协议 child 唯一调用真实 health MCP 并获得 PostgreSQL
`status=ok`，建模 child 与 coordinator 无平台调用。临时 Project-scoped `read` key 已撤销，
21 项自动化测试及独立测试 Round 4 PASS。L1 的 per-agent write MCP provisioning 仍是后续前置门。
