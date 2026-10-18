# R4.3-031 开发与测试记录

- 用户授权：根据已审阅设计完成 R4.3-031 开发与测试。
- 权威范围：[需求031](../../requirements/requirements-v4.3.md#r4-3-031)、
  [详细设计](../designs/2026-10-17-r4-3-031-dsh-production-runtime-design.md)、
  [独立设计审阅](2026-10-17-r4-3-031-design-review-record.md)。
- 实现基于已有工作区，保留 README、029、复盘、优化跟踪、演示及相邻需求的未提交工作。
- 本轮为工程交付及开发测试；未调用外部模型、未启动真实生产建模／修模／独立验收。
  本地工程 fixture 的 HTTP/SSE 输入由确定性程序产生，不计作真实 semantic-start。

## 实现与边界

| 范围 | 实现与证据 |
| --- | --- |
| F1 显式配置 | v1 Profile 支持 codex/dsh；Package 分别声明有效 sandbox；新增026专用DSH Profile与精确原生模型配置，原Codex默认保持。原baseline增加DSH文件，实际装载另存Harness提交、构建文件／锁／SDK摘要、插件、源材料、最终schema及请求／有效绑定。 |
| F2 身份与事件 | 每角色独立进程/session；Host dispatch ID、SDK messageId、进程代次及真实turn seq分开。持续事件泵与RPC响应分流；通知先到、busy队列、快idle、取消、seq去重／缺口／冲突、未知回执及迟到RPC分别处理。无messageId的未知请求保持null；只有原RPC ID与进程代次能补绑。broker ack仍只代表交给运行时。 |
| F3 控制 | Runner直接执行暂停／继续，关闭新写入准入；SIGSTOP／CONT后逐一核对DSH及MCP后代，包括独立进程组。保留原session；Host在途回执与实际冻结分开。新输入保留在broker；未知写入沿原核对门处理，暂停不承诺供应商取消。 |
| F4 等待恢复 | 沿用provider等待与issue账本；入队记录submitted，实际claimed后才生效／结案。再遇原额度错误保持等待。禁用本组合的自动provider重放；120秒stream idle有界等待。Host可在写入核清后显式恢复原持久session，失败不创建替代session；没有自动fresh start。 |
| F5 隔离 | 白名单Cordis插件，不走默认sdk组合／全局发现。真实角色MCP与schema全集比对，按manifest ID读取冻结原文，CQ私有源及兄弟／宿主文件不可见。无shell、编辑器或动态subagent工具。 |
| F6 Messages | 独立deepseek-official精确模型／effort映射；窄Host代理固定TLS上游`https://api.deepseek.com/anthropic/v1/messages`，注入真key，仅下发随机代理凭据。保留必要协议／关联头及首HTTP错误，中断流不重试；拒绝旧Responses管理器接原生Messages路由。 |
| F7 清理 | 关闭准入，只停止本轮角色、MCP、代理及token；保留原日志／失败目录，沿原retain_nonempty／scope生命周期。逐PID启动身份检查及有界等待后核对残留，未完成不标CLEANED；不覆盖第一失败。 |

跨运行时仅抽取已重复的Skill staging／基础隔离小块；未改产品backend/frontend、
平台API或存储，不要求产品服务重启。暂停等待复用了现有CQ时间账本，并补齐其已有
调用所使用但未登记的`user-flow-wait`种类，没有新增计费／治理或轮次硬门。

## 开发测试

测试命令均在`backend/`运行，移除环境中的`DEEPSEEK_API_KEY`并设`PYTHONPATH=..`。
本地DSH装载使用临时测试凭据；真实Harness仅向本地确定性Messages服务发请求。

- 首轮全量：`uv run pytest ../modeling_team/tests -q`：3167 passed、12 skipped、
  318 subtests passed，3 failed。两项失败为provider目录扩展后的旧Responses-only断言，
  一项为暂停中终止后过早检查子进程的退出竞态。相应合同断言及有界残留核对已修正。
- 定向回归覆盖真实隔离roster、原capability／read MCP装载、请求工具全集、原文读取、
  busy入队、活跃／空闲暂停、同session继续、暂停中停止、402等待／恢复再失败、
  原持久session恢复且不发新prompt，以及Host issue结案必须等原消息实际领取。
- Messages代理测试覆盖原字节流、真key替换、版本／beta／request-id、401/402/429/503、
  错误凭据、body上限、无效JSON及中断流只发一次。
- 确定性事件测试覆盖通知早于RPC、两条相邻输入、取消、idle反例、序号重读／缺口／
  冲突、null未知messageId与准确晚回执绑定；材料读取覆盖分页、UTF-8、越权ID和变更摘要。
- 第二轮全量：3189 passed、12 skipped、318 subtests passed；后续新增工程用例及
  Host issue延迟结案接点分别定向通过。一次重跑没有产生完整终态，partial日志保留，不计PASS。
- 凭据修复补测：Host重新校验原私有凭据文件，替换代理内key时保留URL、角色代理凭据及原session；
  原等待在实际领取恢复输入前不解除，再失败仍保持等待。
- 最终全量：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q
  --tb=short --junitxml=../workspaces/r4-3-031-engineering-20261018/team-tests.xml`，
  **3193 passed、12 skipped、318 subtests passed**，359 warnings，430.16秒，退出码0。
  `team-tests.log`／`team-tests.xml`保留完整结果；测试冻结的27个代码／配置文件
  与最终工作区摘要逐一一致，清单为`tested-source-sha256.json`。
- 静态检查通过：新增运行时／代理及测试的`ruff check --select F`、
  `python -m compileall -q modeling_team`、`node --check modeling_team/runtimes/dsh_node/entry.mjs`、
  配置`validate`、相关文档本地链接／代码块配对／需求锚点及`git diff --cached --check`。
  配置校验在仓库根目录通过`backend/.venv/bin/python -m modeling_team validate`执行，
  Profile／Task／model-profile参数同README示例；不发provider请求。

工程原件目录：`workspaces/r4-3-031-engineering-20261018/`（gitignored），保留全量日志与
JUnit；不将测试凭据、临时session、生成日志或外部Harness文件提交。

## 影响与验证层级

GitNexus原索引将`RuntimeDispatchReceipt`上游评为CRITICAL（119个潜在符号、6个直接
依赖），`load_profile`评为HIGH（13个潜在符号、4个直接依赖）。已告知用户；旧构造、
Codex默认及正式Protocol turn屏障保留，生产装配及当前直接建模路径才使用DSH扩展。
新模块尚无图索引覆盖，辅以实际调用点、diff和回归检查，不以旧索引声称新代码图覆盖。
提交前`detect_changes(scope=staged)`：MEDIUM，51个索引符号、1个关联流程、31个文件；
原索引对新模块及已移动行号的覆盖有限，结论以本轮实际diff和工程测试为准。

本轮不要求另建独立工程Agent；已有独立设计PASS不扩写为独立工程／语义PASS。
A1／A2工程及A3本地运行控制／恢复测试与A4真实模型写入分开记录。
真实平台暂停前application迟到、未知写入对账和长暂停网络故障的联合实测仍须随真实L0取证；
本轮的写入准入／迟到回执用例和本地HTTP故障用例不冒充这些平台实测。**A4、外部provider真实模型
绑定、真实application／治理自查、独立L1、更大业务、L2、完整DSH切换及净降耗均待单独
有效运行授权和实际证据。** Delivery和独立验收仍使用Codex，032—034未在本次实现。
