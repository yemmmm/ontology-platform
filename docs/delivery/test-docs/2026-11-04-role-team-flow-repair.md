# R5.0-012 流程纠错设计修订与工程验证

日期：2026-11-04。用户授权：调整建模流程设计并修复上一份复盘中的问题。
状态：**修订设计/实现完成；独立有界工程复核R2 PASS；完整v5 428项、补充边界12项、旧编译链83项通过。真实L0接续、L1/L2与净提速未验证。**
基线：7e8b8dc；[修订设计](../designs/2026-11-04-role-team-flow-repair-design.md)；
[原运行复盘](../../research/2026-11-04-demo-role-high-flow-retrospective.md)。

本轮是设计/实现/工程验证，不新增预算、semantic start、生产写入或独立语义验收。
原run `demo-role-high-20261104-start1` 保持暂停，原模型revision2/143项绑定与36项冻结分母不变。

## 交付范围

1. 原作者交付边界规范化两个中立包装字段、复用同一候选validator；编译错误保留实际item及JSON Pointer。
2. 单目标放置默认及原结果qualified ID/空变更责任在权威提示中明确，placement错误返回准确坏key。
3. 同角色/phase/generation/来源/scope/CQ/shared/model基线的技术纠错，复用真实完整读取证明和自身精确artifact引用；有真实绑定时沿现有Codex resume/usage baseline继续上下文。
4. CQ model_support证据槽与原业务题义分开，纯证据更新入self_check队列；真实业务变化的model队列先由原责任消费，再整体检查。
5. MCP卡片、record依赖/source引用显式类型；程序处理reported_at及可省略的已绑定SHA，保留非法身份/来源/依赖反馈。

无通用patch协议、新角色框架、dry-run/技术审批恢复或隐藏答案回灌。单次原子执行、授权、源忠实度、完整业务范围和独立验收保持。

## 定位与T0

- 自身review冗余项已在3d481c3修复，本次保留既有证明，不重复实现。
- 空包装及reported_at由程序补/盖章，不扩大语义；真实必需字段、关系端点、共享标签不猜造。
- 同版本来源/交接实际读取是源忠实度证据；技术纠错不强迫同样正文每turn重读。只复用程序列明的本作者执行，分页缺口/错误摘要/基线变化不得升级为完整证明。
- 新设计不将“发消息”或“HTTP completed”当业务完成。旧输出、事件、版本材料、失败/未写入回执保留。

GitNexus对v5主符号未找到，索引落后；对validate_unified_candidate返回LOW。已用实际role_work/compose_integration/Host compiler、工具注册及预算/恢复调用点补充影响检查；不声称v5图覆盖。

## 测试轮次

日志目录：`workspaces/v5-runs/demo-role-high-20261104-inputs/`。测试用临时PostgreSQL schema、确定性actor和现有SDK边界，均无模型请求。

| 轮次 | 范围/原件 | 结果与含义 |
| --- | --- | --- |
| RED 1 | flow-repair-initial-red.log | 6失败：旧主流程无成果/真实读证明复用及CQ证据槽，实际完整链未到预期 |
| Core 2 | flow-repair-core-round2.log | 5通过/1失败：真实CQ变化仍可被先做自查绕过，补充等待model队列的必要依赖 |
| Core 3 | flow-repair-core-round3.log | 5通过/1失败：夹具仍有初版CQ待处理消息，不是纯证据场景；改为预置与真实应用前一致的公开目标，不删除合法变化通知 |
| Core 4 | flow-repair-core-round4.log | 6通过：相同基线复用、过期/错digest拒绝、纯证据与真实未知变化分流 |
| Compiler RED | test_direct_modeling新反例 | 实际入口item_id仍为None，证明第二层映射丢失validator定位；已修映射 |
| Compiler GREEN | flow-repair-compiler-regression.log | 83通过，含direct_modeling、wiring和staged_decisions完整受影响文件；改用已有backend环境消除worker临时环境缺sqlalchemy问题 |
| Tools | test_team.py/test_semantic_workspace.py | worker先RED后实现，30通过/1依赖警告，覆盖真实MCP schema/调用及兼容字段 |
| Candidate | test_role_candidates及staged定向 | worker 52通过；规范化143项只补缺失neutral null，不改原对象/已存在语义 |

新增partial-source、原生上下文选择、Modeling/Coordinator/Acceptance差分计费及真实null no_change/自身review用例；flow-repair-context-regression.log记录12项通过（80.82秒），并单独验证新业务答复会使旧成果失效。技术通知/真实request答复的最终反例另记flow-repair-final-boundaries.log。

- 受影响角色/预算回归：flow-repair-affected-regression.log，101通过（576.76秒）。
- 完整v5 Round 1：272通过/1失败时主动SIGINT停止以定位，299.80秒；原件flow-repair-full-round1-import-failure.log。失败为共享纯validator顶层导入污染启动隔离测试，并非业务模型错误。
- 导入修复：只在非空候选实际规范化时加载纯合同；preflight保留原不加载旧包/Runner的两条断言，放入新进程验证启动，避免被同进程业务测试的合法机械函数调用影响。候选+preflight 13通过（flow-repair-import-regression.log）。不是删除原断言换绿。
- 最终全量在明确modeling_team/v5/tests目录执行，设置--maxfail=1及时暴露实际失败；**428 passed, 1 warning in 961.36s**，原件flow-repair-full-regression.log。唯一warning为既有pydantic_settings lifespan前向引用。已停止Round 1不算全量通过。
- flow-repair-final-boundaries.log：**12 passed in 91.96s**。它包含全量收集之后新增的三项纯技术通知/真实request答复区分，和9个邻近用例；实现逻辑未因新增测试变化，因此复用全量结果，不相加宣称440项不同用例。
- 最终collect-only清点为431项（flow-repair-final-collected-tests.log）；428项完整运行与上述新增3项的覆盖并集为431，不将重叠的9项重复累计。
- 本次修改的v5文件Ruff检查通过，git diff --check通过。额外全目录Ruff检查有4个未改文件中的既有问题（test_custom_cq.py三项、test_process_evaluation_independent.py一项），见flow-repair-full-ruff.log；没有为本修复清理无关文件。

## 原143项载荷离线复核

flow-repair-actual-candidate-verification.json记录原快照中的Modeler 143项/143变更。规范化仅补两个缺键null，业务正文、70个实际端点及13个非空shared_scope完整保留；原快照/候选文件SHA前后不变。静态compiler 0错误、2批100/43项。未调用Host/API/apply、未读取私有36题。该证据证明本次机械差异处理，不证明业务语义验收或实际提速。

## 独立只读工程复核

按requesting-code-review对本次设计/实现做独立只读检查，不运行模型/测试、不修改文件。

- R1确认新业务答复未改变文件版本仍可影响语义的High路径已由当前窄修覆盖：业务答复进入correction basis，变化清除旧成果和自动读取复用；对应changed=human先RED后GREEN。
- 一个Medium建议无条件排除host-technical已在R2撤回：HumanInput.submit校验真实request及版本，带request_id的输入仍可能是业务答复，必须使旧成果失效；只有明确技术通知且未回答业务request才排除。设计§3与实现保持该更窄规则。
- R2有界结论PASS，无未解决Critical/High；不等于独立语义L1或真实高effort验收。

## 完成边界

工程通过只能证明所改合同、路由、恢复与确定性执行行为；真实高effort下的流程时长、原run剩余链、独立L1及L2仍需获准执行。本次不冒充已完成这些真实验证，也不承诺将历史返工分钟等额省去。

本次只变更建模CLI/Host纯编译器、专业提示及合同文档，不改backend/frontend、依赖或应用服务配置。Host compiler每次由新进程加载，不需重启应用服务；原暂停run只有未来获准的新CLI续接才加载程序修复，其冻结专业提示不热改。无真实模型请求、生产apply或预算追加，原run/模型/私有标准保持。
