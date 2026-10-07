# v4.1 工作台交付记录

## 初始基线与授权

- 2026-10-07：用户授权完成 v4.1 细化、设计、审阅、开发和测试。
- 权威范围：[v4.1](../../requirements/requirements-v4.1.md) 全部 R4.1-001—011；基础版本 v4.0。
- 初始提交 `362b41e`，工作区干净。首次核对：App 只有 build-context 可无 Ontology 进入；
  Brief 完整度为首页核心，旧规则 CRUD/运行仍存在，Context Query 已有双游标合同。
- 本次不启动真实建模、不消耗或增加建模额度、不执行外部 SQL/API 业务调用。
- 设计：[工作台设计](../designs/2026-10-07-v4-1-workbench-design.md)。
- 共享测试：[测试计划](../test-plans/2026-10-07-v4-1-workbench-test-plan.md)。

## 细化决定与证据

- 项目工作不依赖 Ontology；模型范围显式选择，不隐式取首个 binding 或强制 Class。
- 页面为只读模型与协同产物阅读，管理入口复用主体、角色、保护集和 Key 管理 API。
  Brief 既有编辑保留；CQ 审核与运行控制在未有网页适用授权合同前不提供按钮。
- Team 文件是真实源；补项目绑定、受授权、固定产物类型、字段白名单的只读桥接，
  不用旧 workflow artifact API 冒充当前 Team 已接入。
- 旧规则退役作为 R4.1-009 与 R4.0-022 联动工作；按实际调用保留 SHACL/OWL/通用 RDF，
  不删除历史数据库记录，不进行历史业务迁移。
- R4.1-011 仅关联现有反馈/修复记录；R4.0-001/023 未细化，不造自动修复系统或空白页面。
- GitNexus impact(App) 返回 UNKNOWN/target not found；后续使用具体调用点核对并披露限制。
- 两个规则服务的 impact 返回 LOW/0 callers，但文本已发现 REST/MCP/modeling_batches 调用，
  因而该图不构成完整影响覆盖；以真实调用点核对为准，不为此重建全仓库索引。
- 最小实物探测：最新保留 run 的 state.json 不含项目；handoff 的 scope_binding 有明确
  project_id/ontology_ids；host_ops identity 当前 platform_binding 为 None，不能当绑定来源。
  已公开 CQ projection 含 question/answer_points/review_content_version，候选/报告为版本化 JSON。
- 初始运行基线：ontology-platform.service active；8001/api/health 返回 status=ok，5173 HTTP 200。

## 设计审阅

- Round 1：plan_reviewer 返回 REVISE，一项 accepted-high：生产交接前没有持久项目绑定，
  会导致 RUNNING 中 CQ/地图/候选不可读。证据：host_ops._identity_block恒None，Runner._state
  只写state/run_id，cleanup/handoff均在后期。
- 已修订设计与 T10：现有 state.json 附已准备 PlatformScope 的最小 platform_binding，
  历史明确读取cleanup.scope/handoff.scope_binding，检查冲突；不改历史run、不增加运行硬门。
- Round 2：plan_reviewer 返回 PASS，无新增 Critical/High；唯一 High 已消除。
  该结论仅为设计 PASS。单 Ontology 情况从 PlatformScope.ontology_id 补齐集合，
  不复用 _cq_scope_binding 的请求值 fallback。

## 开发交接

- 冻结设计/测试路径如上，基线 `362b41e` 加本次细化文档，尚无产品代码变更。
- 分前端开发与后端接入/退役开发；不改彼此文件，不提交；主 Agent 维护本记录及需求状态。
- frontend 全部页面/交互/样式/类型及 Playwright；backend API/服务/安全/测试、
  modeling_team 最小 state 绑定与当前退役提示/测试、接口文档由后端开发负责。
- 必须先协调 workbench 响应合同，再写消费者。稳定后统一完整测试和重启，
  不在另一开发仍写代码时做独立验收。
- 后端首轮调用核对发现退役跨 REST/MCP/compiler/batch/derived/read/projection，
  按开发方建议将此独立范围交另一 requirement_developer，原后端开发专注只读接入/state绑定。
  退役开发拥有旧语义接口/服务/消费分支及对应测试/当前 Team 提示，不碰 workbench 与 runner。
  前端拥有所有 UI/Playwright；没有为角色数量扩范围。
- API 初步交接：项目 run 列表 + 固定 run 详情，白名单 Artifact data 封套携带来源摘要/mtime、
  scope、availability/limitations；显式绑定冲突不关联，未确定当前 run 不猜。
- 开发实物核对确认：CQ 旧 resource_type=rule 专属于旧 SemanticRuleModel；005 新规则是
  普通 instance + semantic_roles=rule。采用既有业务规则角色，不新造平台 kind；
  表单/API/MCP同步退役旧type且准确报不支持，补新规则召回/注解读回测试。
  此为已审阅“按真实语义角色识别、退役旧专用读取”的具体化，无范围扩张。

## 开发期间的合同核对

- 退役方发现真实调用规模大于索引；按 actual callers 清理，不按图返回0推无风险。
  首批定向检查报告46通过/1测试import命名错误，开发方正在修正并继续全量验证。
- 主 Agent 草稿核对交回后端：地图 explicit_unknowns 为对象列表，跨切片CQ使用spans_slices，
  adjustments使用change/approved_by_coordinator；候选value为对象。要求按真实schema保留，
  不因通用scalar helper丢失未物化语义或未知项。
- 安全核对：报告公开ID不能取全部历史projection的并集；必须按本报告freeze_digest对应
  projection.snapshot_digest及版本绑定，缺精确绑定不释放正文。真实公开回归另位于
  acceptance-v3/public-regression，不能遗漏或当隐藏盲测。
- 完整性核对：报告有可读模型绑定时应按既有 workspace/graph digest recipe 比对当前状态，
  区分当前、漂移、缺证，不能把所有报告永久标unknown替代实现。
- 状态绑定须覆盖合法Ontology拓扑变化，避免同项目正常范围更新触发虚假冲突。
  以上仍在开发修订阶段，不是独立验收结果；稳定交接后再核实。
- 前端阶段报告：首次 npm build 通过；35项fixture首轮暴露旧导航/Recall/规则预期，
  正在迁移到新合同并保留SHACL/OWL/通用读写断言，尚无全量Playwright通过结论。
- 管理接口核对：Key仅read/model/admin，unsupported execute已移除；组织级用户/成员操作
  与项目级角色/保护集/Key分别控制与加载，不因/users403导致项目管理整页不可用。
- 首轮后端全量：38 failed/1077 passed/54 skipped，282.22s；代码仍并发修改，
  旧合同迁移/3项接口库存同步待完成，失败记录保留在共享计划，不宣称backend complete。
  退役方随后定向复核269 passed/1 skipped，17.81s；最终稳定全量仍待执行。

## 开发收敛（尚未独立验收）

- 退役开发已停止写入：旧定义/DSL/CONSTRUCT/RuleRun 服务、REST/MCP/批次命令及专用结果消费移除；历史模型/checkpoint保留。新增 OWL engine_name/implementation_mode 和 stub warning，不提升为真实 DL 结论。
- Team 全量开发验证：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests`，2468 passed、8 skipped、314 subtests passed，207.93s；日志 `/tmp/retirement-team-full.log`。退役相关最终157 passed/1 skipped，模式回归8 passed，Ruff F401/F821及修改JSON解析通过。
- 前端草稿合同核对发现默认GraphSet不得取首个active、精确下钻不能被旧CQ data遮盖、派生资源不能静默改读asserted；开发方已修正并补非首位GS/compact派生下钻用例。业务确认改读Brief.field_states等来源，不能用CQ审核替代。
- 前端中间轮47项fixture：43 passed/4 failed；确认来源计数、详情遮盖、图容器高度、表单label问题已修，稳定验证仍待完成。

- `detect_changes(scope=all)`：41 indexed changed symbols、267 affected processes、77 changed tracked files，risk=CRITICAL，已向用户报告。共享鉴权、批次、读取模型、推理/模板影响通过实际diff/call-site复核，完整后端及SHACL/OWL/受治理读取回归纳入最终门；旧索引含已退役流程，不能声称完整图覆盖。
- `sync-interface-docs.py --write` 已同步 REST/MCP 自动目录；无参数校验通过。ontology-modeling技能校验、交付四文档链接检查（0缺失）、git diff --check通过。

- 后端增量最终停写：workbench/resource-list/Operation/模板定向34 passed；Runner绑定29 passed/5 subtests（该状态后未改Runner）；新文件Ruff通过。真实保留run与当前DB只读检查：生命周期available；正式分母8/public0，公开回归分母18/public18；两报告摘要batch_report_core匹配，因live_model_binding_changed均stale。源报告未修改。
- 最终兼容真实 `terminal_results:null`；报告摘要按现有producer前像区分batch_report_core/complete_record，追加sessions/full_pass不伪造篡改结论；full_pass_verification明确recorded_only_not_rescored。
- 前端52fixture通过（29.2s），含修正CSS后窄屏、图高、表单label及development_stub提示；最后补真实public_regression_report kind适用性提示，稳定交接待报。
- 从backend启动最终全量命令 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q`，日志 `/tmp/v41-backend-final.log`；运行中，不提前声称PASS。

## 稳定交接与独立验收启动

- 三开发均已停写。前端最终build PASS；完整fixture52 passed，29.2s；真实public_regression_report kind对齐后v4.1定向16 passed，24.0s，最终标题调整T06通过，1.6s。开发方桌面/移动截图、横向溢出与键盘检查通过。
- 独立 requirement_tester 以初始362b41e加当前未提交稳定工作树验收全R4.1-001—011及022，先审阅代码与逐T覆盖，随后等待全量后端/重启/Playwright证据。共享计划仅由测试方追加独立轮次，主Agent不改其验收结论。
- 最终稳定接口同步校验与git diff --check再次通过；未启动新的semantic start或业务执行。

## 独立验收 Round 1 修订

- D01 accepted-high（T07/T10，R4.1-007）：真实producer handoff的applied_batches/not_applied/unknown_writes为对象列表，reader scalars静默丢弃；joint_checklist实际state而reader取status。独立实物证据：r4009-20261003-solmedium-auth01-start4c的63条applied_batches未返回，state=pending变成空对象。Round1保留FAIL，不以fixture/开发测试绿色覆盖。
- 已交原后端开发准备schema匹配的最窄白名单深层投影与真实producer形状回归；先保留当前基线，待独立Round1定向和本轮全后端结束后写入，再稳定交接Round2。

- D02 accepted-high（T06/T07/T10）：真实early-feedback.first_failure为{stage,failure:{status,reason/blocked_layer,blocked_reason,evidence}}，读取仅stage/code/failure_layer导致故障内容丢失。原两份公开反馈以及确定性typed形状复现支持；交后端按真实安全字段投影，不透传私有原日志。
- 独立Round1已停止基线核查，正式定向88 passed/6.75s；首次命令错路径collection error未执行，随后纠正，原错误保留。该88 PASS不覆盖D01/D02，整体FAIL，T12真实运行尚未执行。

- D03 accepted-high（T03/T10）：scenario.adjustments[].review实际含definition_ids/before_refs/after_refs/coverage/coverage_note/references/outcome/reason；真实start2的incomplete/pending整块缺失。与D01/D02一次修白名单，原地图无review不造字段。Round1最终FAIL三High并已冻结。
- 首轮稳定全后端：1 failed/1125 passed/54 skipped，303.90s，日志 `/tmp/v41-backend-final.log`。唯一fail为api.md资源列表示例具体路径被HTTP目录校验视为未登记，主Agent改用实际{model_name}模板+resource-list参数说明；文档同步定向10 passed/6.14s。随后允许三项产品修复，最终全套须对应修后代码。
- T01/T07诚实展示核对：真实host未全范围提供结构化pending_work/next_action，不能由模拟字段冒充已接入；交前端明确剩余工作/下一动作未知或未接入并补真实封套fixture，不新建宿主状态或猜流程动作。

## Round 1 修复开发验证

- 后端仅修改modeling_workbench服务/测试，D01—D03一次修复后停写：定向10 passed（原7+3回归）、Ruff与whitespace通过。真实源只读回放D01保留63 apply/1 not_applied/0 unknown与joint pending；D03完整review八字段及incomplete/pending；D02无精确公开freeze时保留FAILED/原因代码并标withheld_without_public_binding，绑定明确时才释放获准reason正文/typed层及安全evidence机器代码。隐藏/凭据sentinel均排除，实际源bytes未变。
- 启动修后最终全后端同一命令，日志 `/tmp/v41-backend-final-round2.log`，运行中；不复用修前PASS声称当前全套通过。Team未再修改，先前2468/8skip/314subtests证据仍对应当前Team代码。

## 独立验收 Round 2 进行中

- 修后所有产品代码停写：前端Overview从获准available host/handoff真实字段读取剩余工作与下一动作，没有来源分别显式未知，宿主全字段为折叠详情；build和T01/T07两项通过。
- 独立测试方D01/D03实际产物回放FIXED，源SHA未变；D02最初把早期反馈所有文件数当失败文件数的测试断言错误已纠正，仅核对两份first_failure后FIXED，原测试错误保留。独立定向91 passed/6.95s，日志 `/tmp/v41-independent-round2-focused.log`。
- Round2尚待完整backend、重启健康、包含live的全Playwright和独立真实HTTP/浏览器/清理检查，未提前写整体PASS。

## 最终运行验证进行中

- 修后全后端：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q`，1129 passed、54 skipped，281.50s，日志 `/tmp/v41-backend-final-round2.log`。此为当前所有后端修复后的全量，不覆盖新L1建模质量。
- `env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user restart ontology-platform.service`成功；启动完成后status active(running)，backend 8001/api/health={status:ok}，frontend 5173 HTTP200。启动期间curl连接拒绝重试后成功，不是终态故障。系统startup再次build生产dist并完成后端/前端ready。
- 从frontend运行最终 `npx playwright test --workers=4`（包括semantic live-contract），日志 `/tmp/v41-playwright-final.log`；独立Round2已收到重启健康信号，开始精确同源鉴权的只读页面/API及唯一自有临时资源验证，等待结论。

- 首次重启后全Playwright：2 failed/54 passed，33.9s，日志 `/tmp/v41-playwright-final.log`。独立核对归因均为测试合同：旧 blanket 禁止graph_iri与合法图位置合同冲突；原seed Alice缺NamedIndividual+op:id平台稳定身份。交前端仅修测试，不修改产品合同，保留正常授权图位置、SHACL/OWL及退役404断言后复验全套。
- 独立真实HTTP定向通过；正式/公开回归真实报告stale(live_model_binding_changed)且原full_pass仅记录，源SHA未变；已删除旧项目准确404，缺绑定run不挂项目。独立浏览器先段无Ontology/四态/未知/小屏/键盘通过，后续核查进行中，原测试重复选择器错误也由测试方保留纠正。

## 独立验收 Round 2 冻结与 D04

- Round2整体FAIL，D01—D03 FIXED、91定向PASS、实际HTTP和浏览器有界功能/隐私边界通过；测试方已保留错误选择器/同步等待尝试及源SHA证据，自有唯一fixture留至Round3并最终清理。
- D04 accepted-high（001/004及已审设计）：实际截图确认Overview四态卡直接展开完整slices/field_states/应用entries且主卡技术binding占先；模型详情locations图位ID列在业务ResourceCard前，违反“可读事实摘要在前、技术记录次级”“先含义scopeunknown再IRI/图位”，不是可选美化。主Agent也实际读取T12 desktop图确认。
- 交前端最窄修：各权威来源事实摘要，不以Brief字段/地图modeled/旧报告推完整完成；原结构/binding/配置放details。模型先业务含义/范围/未知与必要七视角字段/脚本，纯技术身份/分类/图位details，保留可读Ontology位置选择及精确Operation/binding业务关系。CurrentWorkSummary明确未知保持。后端/Team产品代码不变，既有全量证据仍对应现状态。
- live合同迁移后4 passed/11.6s，`/tmp/v41-live-contract-fixed.log`；原两失败已复现并保留`/tmp/v41-live-contract-reproduce.log`。此次仅测试fixture/追溯字段断言修正，保留图IRI服务端授权范围验证。最终全56将在D04稳定后运行。

- 022权威合同同步：当前005/009正文中旧平台执行适配、rule-result继续有效、自动业务物化后续待交付的表述按022明确收敛；D1/D2/D6历史决策表不改写，注记当前由022替代，原交付/独立语义PARTIAL不提升。当前Team tasks/profiles/packages/skills/references检索只见两份已修改contract明确retired说明，无旧执行引导。该文档修订履行022范围，不增加平台能力。

## 最终开发验证 Round 3

- D04 最窄前端修订完成并停写：build PASS；聚焦35项34 PASS/1旧文案断言FAIL，改为实际说明后该单项复测PASS。新增摘要可展开与业务信息排序两测试，最终全套58项。
- 再次按用户systemd单元重启，启动build期间端口尚未ready的curl exit7保留；随后服务active、backend health ok、frontend HTTP200。产品代码已稳定。
- 完整 `npx playwright test --workers=4` **58 passed / 44.1s**，退出0，`/tmp/v41-playwright-final-round3.log`。包含真实服务live合同、旧规则退役、保留SHACL/OWL、工作台全部页面、权限与桌面/移动/键盘。
- 当前指南同步项目导航、管理员只读运行投影、旧规则和Evidence/lineage退役边界；修正相对链接并指向对应v4.0/v4.1权威需求，不以历史v1缺口替代当前目标。六份当前文档本地链接PASS；interface inventory同步PASS，文档校验10 passed/6.25s，diff --check PASS。
- 提交前GitNexus detect_changes(all)报告CRITICAL、41 symbols/232 affected/78 files；已向用户提示。图索引含已退役流程且不覆盖新增全部符号，不作为全覆盖证明；实际调用点与diff、1129后端全量、2468 Team和独立授权/只读实物检查共同覆盖当前变更。
- 独立验收Round3获稳定信号，正在复核D04以及自有资源最终清理；未提前给出整体PASS。

## 最终独立验收与交付结论

- requirement_tester 独立Round3 **PASS**，全R4.1-001—011及关联022逐T矩阵已落入共享计划；D01—D03维持FIXED，D04实际桌面/390px/键盘复验FIXED，没有当前必需项BLOCKED或REGRESSION。主Agent也实际查看最终overview-desktop/model-mobile截图核对信息层级。
- 独立真实浏览器退出0，`/tmp/v41-independent-round3-browser.log`；GET+受治理只读Context POST，无退役/建模/自动修复请求，响应/存储无Key或私有sentinel。
- 唯一fixture清理退出0并再次只读核验：2项目HTTP404、3Key及1User行不存在、自有图ASK=false、test-only run目录不存在；`/tmp/v41-independent-round3-cleanup.log`和`cleanup-verify.log`。原有项目/运行/材料未处理。
- 设计、开发验证、独立功能验收及本地运行健康分别通过；所有此前失败与修复保留。需求状态同步完成。当前功能PASS不改写v4.0原L1质量/SQL/API/DL/L2/L3缺口；本轮无新的semantic start或外部业务执行。
- 最终提交仅纳入本次拥有的代码、测试、合同与文档；不包含凭据、临时fixture、日志截图或生成dist。提交标识以实际git提交结果为准。
