# v4/v5 harness差异与大量输出修复方案评估

日期：2026-11-05（Asia/Singapore）。状态：离线评估完成；下述新增方案未实施、未真实验证。

问题：先核对实际harness差异是否影响本轮输出，再提出针对大量输出的最小修复方案。关联[R5.0-012](../requirements/requirements-v5.0.md#r5-0-012)、[R5.0-002](../requirements/requirements-v5.0.md#r5-0-002)及[既有输出归因](2026-11-05-v5-output-attribution-and-smooth-run-budget.md)。使用建模复盘方法，不启动新模型调用、不追加预算、不更改生产流程；原run保持暂停。私有36题、答案和评分正文未读，业务／独立验收约束保持。

## 1. 先判断harness差异

**底层Codex版本更换不是本组证据支持的解释；项目层的会话、提示、工具和成果交付合同存在明确差异，已定位会增加重建、长序列化及纠错回合的路径。无法据不同范围样本量化其独立贡献比例。**

这里区分两层：底层是Codex App Server、RPC／SDK和provider传输；项目层是阶段会话、提示供给、工具、成果与恢复协议。v4是最小链4题，v5是完整Demo36题且尚未应用，二者的总量不能直接作为harness因果实验。

实际参考为`r4326-20261016-parallel-flash-high-start1`与`demo-role-high-20261105-start1`。不从源码注释的历史版本号推定旧run使用版本，而从各自原生rollout的session_meta核对。元数据／哈希／工具名投影保存在[本地harness审计](../../workspaces/v5-runs/demo-role-high-20261105-inputs/harness-comparison-audit.json)，不保存凭据、完整请求体、私有题或推理正文。

| 维度 | v4实际参考 | v5本轮 | 判断及边界 |
| --- | --- | --- | --- |
| CLI／模型／provider | Codex 0.163.0、glm-5.3-flash、glm-direct、high | 相同 | 已核对3个v4生产角色及6个v5初始会话；无CLI版本或high被换成max的反例 |
| API与指令基底 | Responses；base_instructions为空，summary=none | 相同 | 无“新默认编码系统提示灌入”或reasoning摘要等级抬高证据。不能据此声称全部wire请求逐字相同 |
| 客户端与代理 | 手工App Server RPC；共享Responses provider路径 | openai-codex SDK驱动同App Server；复用ResponsesProviderSession，另投影工具清单 | SDK是调用／事件接收层。源码未见它另调用模型写报告或增加推理回合；v5代理的投影剔除3个通用资源工具，不重写reasoning／text为更高档 |
| Modeler实际developer提示 | 12,712字符 | intake 51,888；propose 52,895字符 | propose约4.16倍。仅描述提示长度，不能换算为4.16倍输出或同范围净增幅 |
| 其他角色提示 | Coordinator 12,672；CQ 9,140字符 | Coordinator 8,488；CQ 7,218字符 | v5提示膨胀集中在Modeler，不是所有角色统一更长 |
| 会话生命周期 | Modeler一个thread跨3个turn；Coordinator跨7个turn；CQ跨9个turn | Modeler intake、首提案、新CQ重评为3个不同thread；四次技术纠错复用第三个thread | 正常阶段／新基线仍重建，已有修复只覆盖技术纠错。新业务仍须重评，但不等于全部旧事实必须重新读取／生成 |
| 成果通道 | Modeler真实调用write_handoff_output 3次、modeling_submit_model_changes 2次、report_task_result 1次；有exec_command | read-only且shell关闭；完整candidate／changes嵌于最终专业JSON；结束后再decode | 工具提交与文本终态交付的差异已定位。v4仅3个资源，不能按其短结果直接预测完整Demo成本；不建议为此开放宿主shell |
| 结构化输出 | 主要成果通过工具；没有发现turn outputSchema调用 | run_turn有output_schema参数，生产调用未传；result_schema仅写进prompt，末尾再校验 | v5目前没有实际启用该接口约束最终信封。启用前须验证GLM路由，不能用OpenAI文档替代GLM兼容证据 |
| 重试／压缩 | Modeler无压缩；Delivery有2次压缩 | 91次请求均HTTP200，无记录在案的重传；Modeler技术纠错线程有1次压缩 | 请求或累计usage重复相加未复现。首份100,914输出发生在压缩之前，压缩无法解释首次膨胀；单次压缩的独立token仍未可靠分离 |

原件：v4的`runtime/{modeling,coordinator,competency-question}/home/config.toml`及`sessions/**/*.jsonl`；v5逐执行`agent/home/config.toml`、rollout和thread-binding；[请求级审计](2026-11-05-v4-v5-activity-throughput-audit.md)。

实现定位：[v4调用层](../../modeling_team/runtimes/codex.py)、[v5调用层](../../modeling_team/v5/src/ontoweave_modeling/codex_agent.py)、[v5阶段调用](../../modeling_team/v5/src/ontoweave_modeling/execution.py)、[v5代理工具投影](../../modeling_team/v5/host/worker.py)、[共享provider](../../modeling_team/deepseek_provider_proxy.py)。当前源码用于解释已观测合同，不能替代历史进程的实际版本证据。

官方资料只用于核对可用接口：App Server支持每turn的outputSchema与effort配置；config reference将model_verbosity描述为GPT-5 Responses可选项，不能据此承诺对本轮GLM有效。[App Server官方文档](https://learn.chatgpt.com/docs/app-server)、[配置官方文档](https://learn.chatgpt.com/docs/config-file/config-reference)。本次先核对本地代码／原件，再以官方资料补接口语义；未以现代文档推定旧进程的有效设置。

## 2. 对既有修复的判断

- 同线程技术续接、累计usage差分和确切正文引用已采用；不能把3个正常阶段新thread误报成7次纠错均未复用。最后一次引用交付缩至2,452字符最终消息／2,818字符全回合消息，证明局部成果复用有效。
- 仍存在49.47万输出，其中推理27.87万。四次技术纠错为12.91万；扣除后仍有36.56万输出，并未应用、自查或验收。旧修复不覆盖完整正常路径成本，019/030完整净效果与R5.0-012 PARTIAL边界保持。
- 本轮Modeler冻结包49,861字符，其中技术表示合同块43,783字符。该块在intake也全量提供，而intake明确禁止产candidate／changes。若仅移除这块并保留阶段方法和运行提示，该次developer供给可由51,888减到8,105字符；这是可计算的提示尺寸差，**尚不是已实施变化，更不是输出节省证据**。
- 53.88%的推理计量发生在最后发出读取动作的请求中；其中可能包含必要业务分析。不能从工具类型得出这些推理都可删，也不能用“请简洁”保证消除它们。

## 3. 推荐修复：分两批，先缩小确定性返工

### 第一批A：按实际阶段供给提示

**当前 → 建议**：所有Modeler阶段都带整份表示合同 → source_intake只含完整来源理解、未知、权限、职责和intake输出合同；propose供给统一图／显式变更语法；self_check只含实际治理读回与检查合同，相关表达规则按需可取。共同的源忠实、条件／例外／否定、未知、作用域与版本要求继续保留。

- 最小责任面：`role_team.freeze_team`冻结阶段提示，`CodexInvocation`按phase选用；阶段上下文必须在冻结包内确定，不在旧run偷偷替换方法。已有只含整份instructions的旧冻结包维持其供给，真实旧任务继续其绑定合同。
- 预期：直接去掉intake不执行的约4.38万字符表示合同，减少无关规则处理及阶段混淆。propose需要的完整表达语义不删；不承诺推理同比减少。
- 验证：离线渲染三阶段提示，核对源忠实／授权／职责保留，intake与self_check不夹带候选交付指令；覆盖旧冻结包读取。后续真实验证看相同阶段输出／耗时及命题完整性，不用字符缩短替代质量。

### 第一批B：成果用工具提交，最终只交小信封

**当前 → 建议**：LLM在最后输出约7.5万字符JSON，结束后才发现格式错误 → 原作者通过窄的`submit_role_artifact`工具提交candidate／changes，复用现有仓储和validator，返回精确不可变引用；最终只交状态、当前basis、引用、source_refs／consumed_ids及必要issues。工具不直接应用本体，不代Agent改业务含义。

- 工具形状问题在当前native turn返回item/key/path等准确反馈，Agent就地纠正；沿用已有可恢复错误、原始失败证据和金额计量。大候选首次仍要表达一次，工具并不会让这些业务token消失；收益主要是降低长文本信封风险、避免正文再次复制和turn结束后的整轮重交。
- 使用已有`WorkspaceRepository.put_reference`、候选纯校验、原作者／基线与application边界；最终引用指向实际提交成果，不接受任意同伴或过期工件。现有`role_work`的检查移到相应最窄入口，不叠加一套审批、翻译或通用patch系统。
- `CodexAgent.run_turn(output_schema=...)`接口已存在，可给**小信封**传实际schema。先在既有GLM路由做有界兼容检查；支持与否按实测决定，不能把schema写进prompt当启用。即使工具／结构化输出可用，仍保留准确可恢复反馈，不宣称供应商永不生成坏JSON。
- 最小责任面：`material_tools`增加窄提交入口、`role_work`接纳已提交成果引用、`execution`传小信封schema；沿原平台编译／原子application，不改后端业务语义。
- 验证：复用原75K语法／信封／缺键反例及已保留116项正文，证明提交对象摘要与接纳内容一致、包装纠正不重交正文、错误仍在当前回合可修、他人／过期／未提交引用仍准确拒绝。后续真实看是否少发生纠错turn，不能直接承诺去掉全部12.91万输出。

### 第二批C：连续工作复用会话与真实读取，业务适用性重新判断

**当前 → 建议**：只有同基线技术纠错复用原上下文 → 同一actor的连续intake／提案／CQ修订优先延续原生上下文；工作空间仍是业务持久权威，职责或授权／来源不兼容时新建上下文。新phase／CQ基线明确投递，旧候选和旧确认不会自动升级。

- 读证据按原作者、精确材料版本／摘要、当前授权和已完成读取事实复用；CQ变化要求重判影响，不让“CQ版本变了”自动抹去原来源确实读过的事实。复用读取与认定旧业务仍适用分开，继续使用现有依赖／适用性状态。
- Coordinator在初次完整propose前优先让已在途的CQ正式就绪；期间继续有效source_intake。它是本轮有依据的任务安排建议，不增加固定角色顺序、超时或不可恢复的CQ硬门。后到真实业务问题仍由原责任方重评。
- 先限定正常连续提案和精确未变读取，复用已有resume／baseline差分／材料证据；不建立跨角色共享原生聊天或自动语义patch框架。
- 验证：相同材料／新CQ需重新给出CQ处置，但未变来源不强制重读；来源实际变化、权限不兼容、真实未读仍不能复用。对照不同thread数、读取量、推理输出及独立质量；上下文过长时沿现有压缩／新上下文能力处理。

### 第二批D：正文只存一次，交接先读贡献与变化导航

**当前 → 建议**：工作记录、候选、changes及交接多处展开 → 完整命题／解释保留唯一署名原件；后续记录写新增决定、未知和实际表达对应。候选必须自足的业务字段继续保留，工作记录不再复写整份候选。首次必要正文仍实际读取，后续交接以精确成果引用、范围覆盖、版本变化、共享冲突及依赖导航起步。

- `role_work._publish`不默认复制全部历史正文；协调者按责任与变化展开。原owner治理自查、Coordinator整体审查及独立验收照常读所需原件／实际模型，不把导航当事实或已读证明。
- 当前F5对实际交接读取有明确约束。实现时须同步明确“读了哪份清单／正文”，不能只读索引却冒称整份候选已消费；必要共享语义仍须展开判断。先消除旧版和未变正文重复展开，不直接取消所有阅读要求。
- 验证：新消费者能定位完整判断，条件／例外／否定与未知未丢；同义字段不被程序擅自合并；共享真实变化使相关处置失效；对比总输入／推理／非推理输出和全任务用量。

## 4. 方案取舍与验证次序

| 选择 | 本次判断 | 原因 |
| --- | --- | --- |
| 更换Codex／LangGraph | 当前不优先 | 同CLI同provider已有反证；有明确的项目合同问题可先窄修 |
| 所有角色改low | 不作为本次默认修复 | 用户选择high，且无同质量对照；不能用降模型配置掩盖协议返工 |
| 调model_verbosity=low | 不当确定性方案 | GLM有效性未证；即使影响可见文本，也不自动解决27.87万推理输出 |
| 硬截max_output_tokens或固定纠错次数 | 不优先 | 当前是大文本信封的可修问题；截断可能制造不完整JSON、丢业务及新一轮返工 |
| A＋B先落地，C＋D再做最小切口 | 推荐 | A有直接可删的阶段无关供给；B针对已复现格式／大信封失败；C/D需同步适用性与阅读事实，分开验证归因 |

先做原件离线回放、冻结提示／对象哈希和准确反馈检查；按受影响v5模块运行必要工程测试。后续真实验证仅在获得相应授权后使用同Demo、同模型／high、同冻结36题和同计量口径，分列初建、纠错、过程评价、治理检查、正式验收与Host成本。工程通过、局部采用、整任务净降耗和独立语义质量分别结论。

之前8—13M总token／50—65万输出是沿现有流程的条件容量估算，描述现状，不设为修复后目标。当前能明确定位成本池：四次技术纠错12.91万输出、读动作请求推理15.02万、工作记录非推理4.13万、新CQ重评8.33万；这些相互交叉，不能相加成保证收益。修复后token范围须由同完成度样本重新校准。

## 5. 本次验证、状态与缺口

本次完成：9个原生生产会话的元数据、developer长度／哈希、工具名和config投影；v4/v5阶段生命周期、指令拼接、成果解析及provider调用的源码核对；复用前报告91次请求／usage对账。本地审计不保存推理正文、凭据或私有题。文档链接／格式和元数据断言另作检查，不运行模型或重跑未改代码的回归。

R5.0-012仍PARTIAL，L0未闭环、L1为0/36、L2未执行；R5.0-002持续记录存在不等于正常阶段已高效复用，既有质量／净效果边界保持。019计量核对增加，030净效果仍待证，024/025未触发范围不据此回退或关闭。未新增确认优化编号；上述A—D是本次可评审修复建议，未实施或启动付费验证。

仍无法量化：同范围同完成度下项目harness各因素的独立收益、供应商响应内部等待，以及GLM对实际outputSchema的兼容行为。已有证据足以先选A/B，无需先扩展成全面压测或新增监控平台。
