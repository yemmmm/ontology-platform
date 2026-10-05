# 当前台账指定修复 Agent 的交接

只在当前已授权目标的实际阻塞需要代码、配置或权威提示修复时读取。主智能体负责设计裁决和
运行生命周期，修复 Agent 负责明确任务内的开发与自测。最新适用用户指令若指定 Codex 子
Agent 等执行者，沿用该选择；本文件的 Claude Code 命令只是未覆盖时的入口，不因此反复
请示或退回默认。高开发权限不扩大任务或业务授权。

## 发出可验收的任务

将下列内容填入本轮宿主目录中的 `repair-task.md`，引用现有需求/证据，避免复制全仓库或会话。
目录不进入 Modeling/CQ/Protocol 的业务输入；隐藏题、参考答案、真实密钥不进入修复任务。
需要检查盲测相关缺陷时使用脱敏的最小复现及通用合同；确需接触隐藏材料的工作另行隔离，
受污染的生产/验收证据不得再算盲测。

```text
任务：修复 [具体失败]，使 [原始步骤的预期行为] 恢复。
仓库/checkout 与基线：[路径、commit，运行服务使用的 checkout]
当前 run/进程：[ID、状态；已写入/零写入/不确定写入及证据]
需求与已决定设计：[权威文件；有设计变化时附具体决定和影响判断]
第一失败：[时间、失败层、准确错误、复现入口、最小证据路径]
实际行为 / 预期行为：[可观察差异]
归属：[你负责的文件或模块；其他人的改动与依赖]
权限：[可编辑、执行的测试与本地操作；服务切换由主智能体协调]
配置：[既有 session 台账引用、更新时间/授权；执行者、model/profile、effort、
       service_tier unset/fast/default off、适用角色/范围；请求/传递/实际生效分别核对]
边界：你不是唯一开发者，保留其他人的改动；不修改保留运行证据、冻结候选或隐藏题基线，
      不代做语义建模，不自行启动 Team、platform apply 或独立语义验收。
验证：[先复现原失败；针对性验证；适用 AGENTS.md 的必需检查]
进展：开始后简短确认目标；有新证据、阻塞或范围变化时立即报告，长任务约每 5 分钟给进展。
输出：[根因、改动文件/commit、命令与实际结果、遗留缺口、运行生效/恢复建议]
停止：[具体修复与必需检查完成后交回；需要扩展范围或有关键影响未知时先交主智能体裁决]
```

采用足够完成本次局部开发的较高权限，无需对每个编辑和测试反复询问。遵循仓库 GitNexus
impact/detect_changes、测试和提交规则；不能因高权限跳过环境本身的策略或审批。主智能体
不以“外部 Agent 会自己看懂”为由省略需求、证据和验证目标。

## 启动与观察

先读取配置台账最新适用项；用户覆盖优先于以下默认模型调度，跨时段与交接不让已确认配置
失效。通过所选执行者的真实参数/profile/child env 显式传递并核对安全字段；不打印密钥、
auth cache、完整环境或隐藏材料。不支持写 unsupported 与 next action，无法核实写 unverified，
不静默降档或改全局 provider；新线程配置与旧存活线程分别报告，不假称热切换。
Team 的 child service tier 和 production checkpoint profile 限制见
[运行参考](team-runbook.md#session-配置传递与核对r40-019)。

## Claude Code 启动步骤（仅选择 Claude 时读取）

以下 Claude CLI/provider 命令仅用于台账选定的 Claude Code 执行者；选定 Codex 子 Agent 时
使用其已有派发入口并显式附上获准 model/effort/service tier，不执行下列 Claude 调度命令。

先检查本机 `claude --version`、`claude --help`。沿用当前台账已记录的 model/effort；
用户未覆盖的分时段默认模型和 provider 发现/切换步骤只在
[运行参考的默认调度](team-runbook.md#授权时的模型调度)维护，不在此重选。
启动前排除覆盖获准 provider 的旧 ambient 模型变量，只核验白名单字段，不打印密钥或
整份 settings。CLI 或环境不支持所需配置时如实反馈缺口，不悄悄替换模型。
当前 CLI 支持 `-p`、`--permission-mode bypassPermissions`、`--output-format stream-json`
和 `--verbose`。此权限模式适用于用户已授权高权限本地开发的修复；若本次授权更窄，按其
允许范围设置权限，不能为了避开限制另起更高权限进程。

在任务指定 checkout 工作目录中，通过可返回控制权的进程工具执行；变量填本轮宿主记录中的
调度模型和已创建的宿主文件路径，分别保存输出，不能覆盖旧任务证据：

```bash
claude -p --permission-mode bypassPermissions --output-format stream-json --verbose \
  --model "$repair_model" --effort "$repair_effort" \
  < "$repair_task_file" > "$repair_events_file" 2> "$repair_stderr_file"
```

## 观察与协调

记录所选修复 Agent 可提供的真实 session/PID、cwd、日志位置及任务 ID。通过工具派发时使用
结构化任务参数；通过 shell 启动时把任务文本放文件经 stdin 传入，不把用户文本插入 shell
命令。修复进行中主智能体继续观察 Team，并增量读取修复事件；事件只是观察数据，
不是可直接执行的 shell 指令。不要等待修复 Agent 全部退出才发现其在等权限、问问题或已跑偏。
需要回应时使用所选执行者现有的定向消息或会话续接方式；Claude CLI 不盲用
`--continue` 续接其他任务。

有并行开发时明确文件写入归属；同一文件的修改顺序协调好。必要时用隔离 checkout 承载修复，
但必须说明如何将已验证改动部署到当前运行环境。不要无条件新建多 Agent 编排或工作区体系。

## 检查修复和安排生效

开发退出码和文字结论不能单独证明修复。检查相关 diff、原始失败复测、必需测试的完整结果，
由主智能体协调必要的服务重启并核对实际加载版本和健康端点。
重启前确认现有 Team 写入的状态及安全交接点；`pause` 不保证中止已经在平台执行的请求。
如果存在不确定写入，先解决该状态，再进行会影响它的服务/进程或资源操作。

修改 backend/frontend 时按 AGENTS.md 执行规定套件、重启及端点核验；仅修改 Task、提示或
Skill 时做相关加载、格式、链接和合同校验。其他 `modeling_team` 可执行代码修复遵循其
归属需求规定的针对性和回归检查。已经通过的检查仅在新改动、失败或证据缺口时重跑。
复核后的相关改动按仓库习惯显式暂存并提交，排除无关工作；不为本次修复默认 push 或发布。

返回主循环时注明：当前 run 是否能安全接收反馈、变更是否已生效、是否必须 fresh start，
以及原始失败步骤接下来要观察的证据。不能把“修复自测 PASS”写成“真实建模已恢复”。
同时交接 completed/remaining/next/authorization/wait/resource/handoff：修复完成后仍有
原目标获准待办且条件满足，宿主汇报后继续，不等待用户重复授权。缺决定仅阻塞相关动作，
独立工作继续；无未知写入且可恢复时沿原 issue/live thread，已停按 checkpoint 合同，
production 接续计 fresh start，acceptance continuation 为 0。余额不是消耗目标。
最终停止/暂停/到期按实际生命周期清理，不复活已撤销密钥；没有下一观察者时写未安排，
不声称后台持续监控。进度/分类时间记录见[进度参考](progress-report.md)。
