# R4.0-013 交付记录

- 权威需求：[R4.0-013](../../requirements/requirements-v4.0.md#r40-013-语义验收分层诊断与-cq-题干评分范围对齐)。
- 已审阅设计：[语义诊断设计](../designs/2026-10-03-r4-0-013-semantic-diagnostics-design.md)。
- 独立测试：[功能验证记录](../test-plans/2026-10-03-r4-0-013-semantic-diagnostics-test-record.md)。
- 用户授权：按设计完成开发与测试。A1—A6、A8—A10 为本次功能范围；A7 后续真实业务语义验收单独授权。
- 实现核对基线：`ef66041`；并发 R4.0-014 需求／设计已由其所属任务提交，未纳入本次修改。
- 当前状态：实现、开发回归及 A1—A6、A8—A10 独立功能验证 PASS；A7 未授权、未执行，需求整体 PARTIAL。
- 提交：本记录随本次实现提交；不可变 hash 可由 `git log -- docs/delivery/records/2026-10-03-r4-0-013-semantic-diagnostics-delivery-record.md` 定位。

## 实现范围

在现有 CQ 草稿／审核 note 记录逐必答点的业务依据、题意对应和处置理由，保持正式修订、
版本绑定和隐藏理由隔离。Consumer 保留影响答案的业务条件与未知，避免无关模板声明。
活跃 v3 Judge、实际注入的 `_CQ_JUDGE_ROLE_INSTRUCTIONS`、旧 v3 提示和挂载 CQ 合同
同步端到端判定及逐点诊断；知识已正确返回而答案错误时诊断 Consumer，空结果不推定模型
缺失，跨题已有响应只作诊断旁证。宿主 runbook 明确引用、逐题读取复核及模型漂移资格检查，
资格不通过保留 Judge 原裁决并说明有效归因未确定；汇总保留完整分母和覆盖缺口。

只改提示／说明、一个 Python 指令常量和测试；报告 Schema、枚举、摘要算法、执行生命周期、
平台读取和历史报告原样复用。未修改 backend/frontend，无需产品全套测试或服务重启。
合成功能案例使用真实隔离 Judge 和既有报告 sink，不创建生产 run，不调用平台，消耗 0 次
fresh semantic starts；实际模型结果仍须独立逐点核对，不由脚本预设 verdict 判为语义 PASS。

## 影响与验证

- GitNexus impact 未找到指令常量，已改用唯一注入调用点和实际 child 装载路径的定向检查；
  不宣称该常量取得图谱影响覆盖。`detect_changes(scope=all)` 返回 LOW，未报告受影响流程；
  图的旧行号将相邻函数标为 touched，但 diff 只修改提示常量，未修改这些函数。
- 两个活跃修改 Skill 的 `quick_validate.py` 均 PASS；Python 编译及 `git diff --check` PASS。
- Team 回归：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`：
  2181 passed、1 skipped、314 subtests passed，168.88 秒；该轮收集早于新增独立测试文件，
  新增测试另行执行并留记录。包括既有 CQ、runtime、CLI、009、partial judging 与隔离回归。
- 变更 Python 和新增测试文件的 Ruff 检查 PASS；最终 7 个 Markdown 文件／归属需求段的
  围栏与 63 个本地链接／锚点 PASS，三轮保留提示快照均与当前资产／注入指令一致。
- 独立功能验证由 `/root/r4013_independent_test` 承担，独占测试及测试记录文件；主 Agent 只维护实现与交付状态。
- 新增独立机械检查 7 passed、1 opt-in live skipped，最终测试代码耗时 0.53 秒，Ruff PASS。
  另执行实际模型调用和独立语义对照，不用默认 skipped 或结构接收代替诊断质量验证。
- A1—A6、A8—A10 独立功能结论 PASS，0 产品缺陷；CQ 四类逐点审核及宿主八类资格反例
  的理由／限制见独立测试记录。A7 不据受控案例改判，无生产启动、写入或额外平台诊断查询。

## 真实 Judge 功能测试运行记录

- Round 1：相同活跃提示／实际注入指令，`openai-sol-medium`，16 道合成题，600 秒上限。
  218.63 秒时 child 提前退出，`ExaminerRuntimeBlocked: binding-rejected`，内部观察为
  `reason_code=child-exited`、`reports=0`。0／16 裁决，不能得出诊断质量结论。
  `workspaces/r4013-functional-tests/round-1/` 保留原 packet、提示快照、空裁决、错误和 teardown；
  child、sink、proxy、私有目录和 socket 清理均已确认。未把失败覆盖成后续成功。
- 运行环境核对：测试 exec 没有 http_proxy／https_proxy／no_proxy；已运行的本机 Codex
  进程使用 `http://127.0.0.1:1080`，监听存在。仅调整第二轮测试调用环境，未改模型、提示、
  产品运行时或用户配置；首轮退出的具体 provider 错误未保存，不能冒称已取得其完整退出原因。
- Round 2：复用现场代理及同一模型／提示、16 题和 600 秒上限，证据另存
  `workspaces/r4013-functional-tests/round-2/`；新增测试错误观察保留类型化失败与 runtime
  failures，不记录敏感 stderr。两轮提示快照均已与当前活跃文件和注入常量核对一致。
  真实调用 1 passed，187.81 秒，16／16 裁决；独立逐题核对原响应、Consumer 答案、来源
  与裁决／诊断均符合设计，所引用 digest／locator／path 均与 packet 匹配，teardown 六项
  全部 true，runtime-failures 为空。此为合成 packet 的真实 Judge 功能结果，不是平台真实
  状态读取或业务语义验收。
- 宿主资格矩阵 H01—H08：复用真实 Q-09 note／响应构建合成已有报告输入，验证两题 stable、
  旁证 drift／unavailable、缺复核、错引用、模型漂移、stable 标签与明细冲突及旁证状态缺失。
  所有原 note／verdict 均保留；资格不通过交付为有效归因未确定。这些输入不冒充实际平台
  稳定性验证；合成完整绑定与原 Judge packet 状态分别列明，CLI 绑定机制由既有回归另证。
- Round 3：从同一 Q-09 实际删除 Q-10 及其他题，过滤 packet 并重算冻结摘要，模型和提示
  不变，不注入预期结论。`workspaces/r4013-functional-tests/round-3-no-corroboration/`
  保留 1／1 真实裁决，调用 1 passed、34.43 秒；独立核对明确原因未确定，未引用已删除
  旁证、不误报模型缺失或 outage。teardown 六项 true，runtime-failures 为空。
- 最终功能验收 PASS；两次成功真实调用共验证 16 题加 1 个去旁证变体，原始端到端 verdict
  分布是合成反例预期结果，不用于提高真实业务通过率或估计知识覆盖率。失败首轮仍保留。
