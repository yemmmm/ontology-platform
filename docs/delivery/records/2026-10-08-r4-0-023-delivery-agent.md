# R4.0-023 独立 Delivery Agent 实施记录

权威范围：[R4.0-023](../../requirements/requirements-v4.0.md#r40-023-独立-delivery-agent-与统一用户交互)。
设计：[独立 Delivery](../designs/2026-10-08-r4-0-023-delivery-agent-design.md)。
独立功能验收：[测试记录](../tests/2026-10-08-r4-0-023-delivery-agent-acceptance.md)。

2026-10-08 用户授权实施；本轮不包含真实 LLM 或 semantic modeling start 授权。
实施完成，独立功能验收 Round 6 PASS（A1—A12 离线合同与实际接线，
0 Critical／0 未关闭 High）；真实 A13／L0／L1 保持未验收。

## 已实现入口与边界

- `modeling_team delivery` 使用独立 Codex App Server Thread，显式绑定模型与 effort；
  未声明 Delivery binding 时继承所选 Coordinator，记录来源。Delivery 不进入生产 roster。
- 原生默认工具关闭，只注册当前交付的 Host 工具。Host root、访问 endpoint 和
  `host_session_ref` 由宿主控制；密钥不进入原生进程环境或工具参数。
- stdin 只接收业务输入；stdout 只显示 Delivery 明确发布的业务消息正文。原始回答、
  来源、问题绑定、CQ 与工具返回保存在 `workspaces/delivery-sessions/<session_id>/` 私有侧。
  测试代答身份为独立 `test-answerer` 输入方，不共享 Delivery 原生历史、工具或隐藏答案。
- 回答使用真实 pending question binding；主动补充与运行指导使用独立 `instruction`
  通路，保留原文、来源、授权和消费回执。Coordinator 继续负责内部唯一转发。
- CQ 委托审核保留题目版本／摘要、资料依据和 Agent 审核理由，不冒称逐题人工批准。
  独立 Consumer/Judge 与只用已有证据的 Judge 诊断方案 A 继续保留。
- Host 托管现有验收 CLI 与指定修复执行者，记录真实 PID、退出及本次报告绑定；
  零退出码、旧报告和未执行报告都不能证明本次语义验收通过。
- 使用已有 Batch／Attempt／资源／回执进行明确 scope 内的只读写入对账，工具不提供 apply/delete。
- `--resume` 首先观察实际 run／operation 状态，不重发未知请求；监督中断历史追加保留。
  本地 OS owner lock 拒绝同一 session 的第二监督者。恢复不复活已撤回的启动权限。

## 启动

部署方准备 YAML 配置。业务用户不填写 run ID、问题 ID 或内部工具参数。

```yaml
session_id: business-delivery-001
authorization_reference: user-approved-delivery-reference
model_profile: openai-sol-medium
business_input_role: user # 测试时为 test-answerer
allowed_operations: [read, supervise, production, evaluation]
task: modeling_team/tasks/<approved-task>.yaml
profile: modeling_team/profiles/<approved-profile>.yaml
scope: workspaces/<approved-scope>.yaml
allowed_sources:
  - docs/<approved-business-source>.md
service_tier: default
```

配置中的 `production` 仅允许使用既有已获准启动台账，不增加额度。未包含的 evaluation／repair
动作不能执行。`allowed_sources` 是已确认资料，不得配置凭据、私有答案或任意仓库目录。
修复需另声明指定 `repair.executor/model/effort`、`repair_owned_paths` 与公开证据引用；
Delivery 自行生成窄 repair-task，无需业务用户编写技术任务。

当前隔离修复执行者为 Codex；Claude 返回类型化 unavailable，不降级到未隔离的仓库根。
修复进程仅挂载指定的公开文件与获准代码文件，私有 HOME 可写，源材料只读，Host 的
workspaces、隐藏 CQ、Delivery 历史、原 HOME 与凭据目录不挂载。已有文件的获准写入直接
作用于原 checkout，保存限定 diff 与结果；私有认证 staging 按既有生命周期清理。

Delivery 的 `verify_repair`／`get_repair_verification_status` 专用 Host 接线只运行固定
repo 检查。backend／frontend 修改需要配置 `repair.allow_deployment: true`，且先对
绑定 run 做成功的只读写入对账，才可重启当前 checkout 的固定本地服务并核对两端健康。
耗时检查结束、重启前再次对账；unknown write 或 scope 漂移阻止部署。
验证异步运行，不接受模型提供的任意 shell；保留 PID、命令、检查退出码、目标摘要与结果。
同一修复核验失败后可重新核验，逐次保留原日志与结果；活跃或仍有效的成功核验不重复启动。
失败、未获准部署、健康失败或目标漂移不能支持 `repair_completed`；成功后仍需独立语义续验。

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m modeling_team delivery \
  --config ../workspaces/delivery-config.yaml
# 宿主退出后，先核对同一 session 的实际状态再接续
env -u DEEPSEEK_API_KEY PYTHONPATH=.. .venv/bin/python -m modeling_team delivery \
  --config ../workspaces/delivery-config.yaml --resume
```

业务入口识别原文 `暂停`／`取消`／`撤回预算`，优先撤回新的启动权限，再执行获准的
对应 Host 控制。Ctrl-C 或 stdin 关闭记录监督中断及真实子进程观察，不冒充成功或自动监控。
CLI 的非零退出不会删除 run 或证据。授权扩大时新建明确授权的 Delivery 配置／session；
不能通过复用旧 session 恢复被撤回的预算。

## 验证与限制

本轮使用原生 stdio 协议、FIFO、真实离线 OS 子进程和现有 Team 合同测试，未调用模型。
独立测试发现并跟踪报告错误绑定、修复文件可见性和重复监督者问题，修复与复测记录见测试文档。
首次全套 Team 回归：2496 passed、10 skipped、3 failed，失败为在途报告测试和提示断行断言；
不能以该轮结果声明完成。终版全量 Team：**2510 passed、10 skipped、304 subtests passed**，
170.28 秒；独立测试者终版 focused：**48 passed**，1.54 秒。D01—D10 原反例均已关闭，
旧失败、真实离线进程与 FIFO／回执证据完整保留在独立测试记录。

开发者另执行 backend 全套：995 passed、55 skipped；没有 backend 源码变更。
Delivery skill 校验、新增本地文档链接／围栏与 diff 检查通过。其余改变的 Python 文件
Ruff 通过；Runner 的 Ruff 全文件检查保留 HEAD 已有的四处 F401/F841，无新增诊断。
全文件链接扫描保留需求文档六处既有前端路径失效，没有本轮新增失效链接。
GitNexus detect_changes 返回 LOW，现有索引识别 18 处变更符号、无受影响流程；新增文件
与未被索引识别的 Runner 入口通过实际调用点及测试核对，不声称完整图级覆盖。

backend／frontend 可执行代码未变更；本轮不要求应用服务重启。功能验证不能证明真实
Delivery 自主建模效果、L0 真实运行或独立 L1 业务语义质量；A13 须获得真实运行授权后另行取证。

## 2026-10-09 宿主技能适配补记

只读核对发现：独立 Delivery 已实现，但 `skills/modeling-dev-loop/` 未随实施提交同步，
仍指导外层直接推进、兼任测试代答及注册宿主通知为问题。归为 prompt-contract 遗漏；
用户随后授权补齐，本次不改变运行代码、生产资源或既有独立验收记录。

- [主技能](../../../skills/modeling-dev-loop/SKILL.md#先选择交付模式r40-023)及发现元数据明确
  独立 Delivery／旧手动模式分流、技术职责归属、隔离测试代答和 CQ 委托审核。
- [运行参考](../../../skills/modeling-dev-loop/references/team-runbook.md#独立-delivery-启动与接续r40-023)
  接入实际 `delivery --config/--resume`、配置／生命周期和 Host 工具；主动补充使用
  `submit_instruction`，保留真实问题注册，移除“恰好 20 个工具”的过时判据。
- 修复参考对齐隔离执行者与异步核验；进展参考区分私有运行记录与业务消息；Team 技能目录
  明确外层只准备／接入独立会话。外层技术补位不能作为 A13 自主交付 PASS。

本次开发者检查：`quick_validate.py skills/modeling-dev-loop` 通过；
`env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m modeling_team delivery --help`
确认 `--config`／`--resume`；对六个技能／目录文件完成 96 个本地链接及锚点、Markdown 围栏、
UI YAML 元数据、`.agents/skills/modeling-dev-loop` 软链接与 18 个引用工具的目录核对，均通过。
工具目录检查只调用 `tools/list` 并读取本地声明，未调用生命周期／模型工具；`git diff --check`
通过。这些是文档及现有合同检查，不是独立行为验收或真实运行证据；本次不运行后端／前端套件、
不重启服务、不启动真实模型，A13／L0／L1 保持未验收。
