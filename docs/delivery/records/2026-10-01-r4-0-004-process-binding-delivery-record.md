# R4.0-004 流程语义与参数绑定：交付记录

- 权威范围：[v4.0 R4.0-004](../../requirements/requirements-v4.0.md#r40-004-流程语义动作调用与参数绑定) F1—F8、A1—A11；[已确认设计](../designs/2026-10-01-r4-0-004-process-binding-design.md)。
- 用户授权：根据设计调用 skill 完成 004 开发和测试。使用 `requirement-delivery` 标准交付，并按设计执行独立功能测试；不新增设计审批或形式化计划评审。
- 开发基线：`d04a8bd`；开始时工作区干净。随后出现其他会话的 005 设计文档，保留、不纳入 004 提交。
- A12 真实建模与独立资料语义验收未授权、未执行，不启动 semantic modeling start，不消费真实建模额度。整体语义状态保持 PARTIAL。

## 实现与开发验证

003 最终交付 `42d8933` 已提供普通 Entity 上的 Action／参数注解、Operation 定义及普通关系的定义引用。本条未发现需要新字段、命令、表、资源类型、REST／MCP 路由或执行引擎的缺口。

实施增量集中于实际加载的 Modeling／Protocol 指令和两份现有角色可见 reference：普通节点角色、关系方向、标量谓词声明、完整绑定及未知说明、条件路径、集合／条件／嵌套循环、前轮传递与循环外选择、局部能力组合、治理读回及修订边界。新增完整中性候选示例，说明它与当前 unified envelope 的区别，沿现有批准物化计划翻译。修正旧 Modeling 指令把业务绑定定义与运行实参混淆的表述。

开发测试覆盖完整示例的正式回执／翻译及实际 Task 的 mounted 输入，普通 RDF 和 HTTP 读回、共享 Action／参数与重复调用、五类值来源、属性定义引用、循环作用域及前轮传递、条目重排、错误引用修正、局部关系修订、授权过滤与计数。对象错绑对照允许结构写入，但业务断言识别不符合目标，避免把平台结构校验当语义裁决。

- 首轮相关回归：27 PASS（8.46 秒）。
- Team 合同回归曾遇到一项旧测试限制：完整 reference 一律禁止 `business` 字样，误把新增合法 `business_meaning`／业务方法说明当场景泄露。仅按原测试对 002 的既有处理方式扩展合法 R4 声明／示例的例外，所有场景专属词、猜测平台身份和隐藏答案禁令保留；修正后 45 PASS、3 subtests PASS（0.62 秒）。
- 后端全套与独立功能测试：待追加实际结果。

## 独立测试交接与结论

按设计 §8，由独立测试角色使用自建业务输入和断言，调用既有真实 PostgreSQL／Oxigraph 与 HTTP Batch／治理读取；不得复用开发候选作为独立语义依据，不改产品实现，不启动 LLM 建模或外部业务执行。测试方案与轮次由测试角色维护在本条唯一[测试文档](../test-plans/2026-10-01-r4-0-004-process-binding-test-plan.md)，失败和清理结果保留。

独立测试结论与提交收尾待完成后追加。

### 开发冻结与真实依赖测试启动

- 后端全套：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q`，1033 PASS／38 既有 SKIP（126.14 秒），日志 `/tmp/r4004-backend-full.log`。只新增测试，未改后端产品实现。
- 用户 systemd 在缺少 D-Bus 环境的首次调用返回 `Failed to connect to bus: No medium found`，未发生重启；核对当前 UID 1000 与 `/run/user/1000/bus` 后，使用 `XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus` 重试成功。
- 重启生效时间：2026-10-01 19:36:19 +08；unit active。启动脚本完成既有前端 build；等待端点就绪后，`/api/health` 返回 `{"status":"ok"}`、前端 5173 返回 HTTP 200。
- 冻结产品输入并交独立测试角色。Team 全套尚在运行；独立角色拥有测试文档与自有临时探针，主 Agent 拥有需求状态／设计结果与本记录。
- GitNexus `detect_changes(scope=all)`：low，仅命中调整的旧 Team 测试符号，无受影响执行流程。该工具尚不覆盖未跟踪的新测试；新测试和 reference／prompt diff 另做直接检查，不声称图覆盖业务语义。

- Team 全套：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q ../modeling_team/tests --tb=short`，2031 PASS／1 既有 SKIP／314 subtests PASS（169.86 秒），日志 `/tmp/r4004-team-full.log`。
- 新测试 Ruff 检查通过。JSON／围栏及本条设计、交付记录和测试文档的 14 个本地链接检查通过。
- 独立前 3 轮保留在测试文档：参数字段误用、149 条关系超出单 Batch 100 条上限、将截断时的 `visible_count` 下界误判为总量，均属测试输入／断言问题，不修改产品来迁就 fixture。第 3 轮已取得 517 项成功功能断言，临时资源清理通过；后续仍需完成修订／治理和最终独立判定。

### 独立功能验收与收尾

- 第 4 轮：A1—A11 独立功能验收 PASS，567 项断言；75 个普通 Entity、487 个 statement 全量限定读回。真实翻译后的定义及 149 条关系分为既有五个 Batch（Class 1／Property 45／Entity 含 Operation 77／Relation 100＋49），逐 Batch dry-run／apply_atomic／幂等回放成功。
- 三类结构合法但业务错误对照（对象错绑、错误调用输出、去掉必要条件）由独立业务断言检出，不通过新平台硬编码语义校验来拒绝普通合法图。局部关系修订未改变共享 Action／参数，共享参数变更后的已知缺口保持未知，不生成兼容结论。
- 同 reader、同 IRI 的未创建／受保护精确响应一致。保护调用、参数、规则、来源和 fact predicate 后，entity-list 75→71、entity-relations 144→126、statement-list 487→450；实际结果与独立过滤预期集合完全相等。limit=1 返回可见首项与完整可见计数，不泄露隐藏关系／标量／名称；可见绑定的声明保留，缺边未改写为“无约束”或模型未知。
- 失败 atomic Batch 返回 validation_failed 且版本不变，修正后 dry-run／apply 可继续。Operation 原有外部能力合同保持独立，没有真实调用、业务行、运行实例或 Evidence 副作用。
- 本轮日志 `/tmp/r4004-independent-round4.log`，JSON `/tmp/r4004-independent-result-r4004-67b29f4a6c144c329070ea8fc23bee52.json`，`result=PASS`、`cleanup=true`。前轮资源也全部清理，测试方案保留所有失败历史。
- 需求索引／状态、设计实施结果与本记录同步。REST／MCP 的字段与行为未改变，无需虚构 API 增量；不运行与本条无关的前端 Playwright。服务重启及健康证据见上。
- 交付判断：授权范围内开发与独立功能测试完成，无未解决产品缺陷；A12 未授权／未执行，整体 PARTIAL。提交仅包含 004 及相关合同测试，不纳入并行 005 文档。

- 独立第 5 轮仅补分页实际采样，26 断言 PASS／清理 PASS；JSON `/tmp/r4004-independent-result-r4004-513b22953b4548e991cf10616da9d070.json` 保留实际首行、page/full paging 和数量。本次 fixture 均低于现有模板 ceiling（entity 500、relation/statement 1000），full complete=true；不把 requested limit=2000 当作突破 ceiling 的能力。
- 外部会话期间提交 `11f757c` 的 005 需求／设计；已核对只涉及文档，未改变本条冻结的产品／角色输入。保留其提交，004 diff 不包含其增量，不为无关文档变更重复功能测试。
- 独立测试已最终交接，无需产品修复或追加功能复测。最终 diff／本地链接／JSON 检查通过后，提交主题为 `Add process semantics and parameter binding guidance`；`git log -- docs/delivery/records/2026-10-01-r4-0-004-process-binding-delivery-record.md` 可解析本记录对应提交。
