# v5 模型访问与次数额度：实际建模测试

日期：2026-10-31。归属：R5.0-001—007、R5.0-009。首 run 与修后无运行时 Host 指导的第三 run 均在 revision 3 独立 **20/20 PASS**；第二 run 未完成，失败及部分模型保留。三次运行均已停止并撤销临时密钥。本轮完成当前构造可运行系统的有界 L1 与修后默认路径验证。

## 授权与当前目标

用户要求“请继续推进建模测试”，并允许压缩时丢弃此前无关内容。本轮继续会话内 v5 持续迭代、最高权限及任意 GLM 授权，沿已用 usage_only 保存用量和身份，不改此前账本。只对已完成的[测试系统](../../examples/llm-access-lab/README.md)开展两切片建模、必要修模及独立只读评价；不扩大成外部客户真值或真实供应商代理。

两个业务切片为模型目录／可用性和调用凭证／模型授权／次数额度。实际模型必须完整表达源规则、例外和必要的 SQLite／API 来源映射；业务行保留在外部 SQLite，不写入 RDF。

## 运行绑定与冻结

- 代码基线：2112c3e；平台健康检查返回 ok。
- 入口：scripts/modeling，LangGraph＋Codex harness，glm-flash-low。实际原生绑定为 glm-direct／glm-5.3-flash。
- task_ref：v5-llm-access-lab-20261031；run：workspaces/v5-runs/llm-access-lab-20261031-start1。
- 首原生线程：01a191f1-ecbf-71e0-8343-0720216a8adc；原生 task_started 为 12:31:54.498 UTC，证据位于 inputs/semantic-start.json。首次启动命令在 12:31:49 UTC 前已发出，未超出授权后二十分钟。
- 输入及 Host 原件：workspaces/v5-runs/llm-access-lab-20261031-inputs。生产只开放 scope、business、api、schema 四项及其 SHA256 manifest。
- business 为原业务文档；OpenAPI 来自真实运行应用；四表 DDL 来自同一实际 SQLite 数据库。Schema 是映射证据，不单独充当业务规则。
- 独立包为 inputs/independent-v1，含同版来源、生产前冻结的 20 项标准及 11 组实际 HTTP 操作观察。生产端不挂载隐藏题、观察或程序测试断言。
- 临时应用使用系统分配的本机端口采集观察后已停止。仅生成自有 oracle.sqlite，管理查询不包含签发凭证原文；没有使用真实供应商账号。
- 初建为第一个建模轮次／第一个 fresh semantic start。任务曾在 ready 时登记，实际 start 已另以原生 turn/started 确认；不能把任务创建算作已完成建模。

## 验证范围与当前边界

独立评价须按实际受治理模型及明确 revision 逐项读取并展开关键关系，不能从源文、运行观察或生产工作笔记补模型缺失。观察覆盖：新调用扣额、跨模型共享额度、额度耗尽、模型停用后的历史回放、提示空格变化冲突、跨凭证请求标识独立、停用凭证拒绝回放及重新启用不补额。

11 组观察来自本次实际 HTTP 操作；二十项标准的冻结登记本身不构成通过，实际独立结果另列。此前程序的 26 项开发测试不替代本轮模型验收。本轮亦不以冻结数据与规则核对宣称已实现在线 SQL Consumer E2E、客户业务盲测、同条件 L2 或净降耗。

## 接续时最小状态

优先读取本记录，以及当前 run 的 status、board、work-tree、questions；只在具体阻塞时读取相应执行事件。监督者不生产候选或代答业务问题。来源已明确的内容由建模 Agent 自行核对，缺失业务决定通过现有 HITL 交给用户；不把最高运行权限解释为代答权。

首 run 与第三 run 分别完成 evaluate，绑定同一 independent-v1、各自固定 evaluation-id 及实际模型版本。后续若需接续，应先核对停止状态与原授权，不重启已封口 run；三次快照、用量、独立报告和权限清理回执已经保存。

## 当前已发生的技术纠错

首四次应用均 not_written，依次暴露引用包装、neutral item_id 选择、未声明 definition_ref 和字段要求。apply-00004／00005 成功，实际模型到 revision 2，含五个 Class 与六个 relation_type。完整目标自查随后明确报告四个 table_mapping 与四个 join_mapping 尚未表达，保持 revise，未把已写入子集判成完整完成。

后续映射重复失败指向冻结提示缺口：原提示只有候选外形和 metric payload，没有表／连接映射的完整载荷与嵌套结构。Host 按真实反馈补齐 contracts.modeling_instructions，并明确字段直接放在 mapping_definition，不套类型名外壳。修复提交 bac011c；新任务 prepare 自动冻结，原 run 的冻结绑定未改动。

原 run 通过既有 input 通道收到 llm-access-mapping-contract-v1，author 为 host-technical。正文仅为通用平台语法，没有业务决定、候选或隐藏标准；它属于运行时技术指导，不能据此宣称无指导默认采用已经通过。入队／delivered 与实际正确采用分别取证。错误、完整候选和平台回执仍归原路径，未覆盖。

后继 model-00010 的原生 final_response 明确将该 message-id 列入 consumed_ids，确认实际消费；它仍出现 mapping_definition 类型外壳问题，后继自行修正，不能把消费回执当作立即正确应用。apply-00013 最终 completed、零错误，revision 3 保有十九个实际资源：五个 Class、六个 relation_type、四个 table_mapping 和四个 join_mapping。

13:16:38 UTC 状态 handoff_ready、无在途生产写入，随后启动 evaluate --evaluation-id v1-full-20。独立目标绑定 Project aa57198c-ffee-4396-824d-15c54b7e0d0f、Ontology 51a06c92-f0ac-4638-8e88-b2d1971437e1、revision 3。评价原生线程为 01a1921b-0d5e-7600-83dc-9dadba9a61e3，实际 glm-direct／glm-5.3-flash，读取七项材料后执行真实模型查询／精确展开。

apply-00012 还出现 ontology_lease_conflict（到期 13:10:27.503156 UTC），回执明确 not_written；这是平台执行／租约问题，不是模型语义结论。原 run 后继提交成功。应用摘要位于 inputs/application-observations.json，保留每次失败，不从 work.round 推算建模轮次。

### 修复验证和边界

- 红测分别得到缺失 table_mapping_payload 的 KeyError，以及 mapping_definition 未限定类型的断言失败；修后定向 15 项通过。
- 首次修复的完整 v5 回归：221 passed、1 条既有 Pydantic lifespan 前向引用提醒，99.30 秒；原件为 inputs/v5-regression-final.log。Ruff format／check 通过；第二次修复后的最终回归见下文。
- GitNexus impact 未找到 modeling_instructions，风险 UNKNOWN；按唯一 TaskBinding.prepare 调用点核对，变化仅作用于新任务冻结。staged 检查 low、四文件、零已索引符号，不构成图上的全调用覆盖。
- 保留必要的映射完整性校验及可恢复反馈，只补充提示合同；没有删除写入安全检查、编排新角色或更改业务语义。未改 backend／frontend，无须重启平台服务。

## 独立语义验收与实际成果

独立报告位于 run/evaluations/v1-full-20/private-report.json，公开回执为同目录 public-feedback.json；冻结身份 v5-llm-access-lab-v1-20-20261031。逐项 index 为 1—20，passed 全部为 true，verdict=PASS，模型版本精确为 revision 3。每题均有实际证据 IRI，合计引用十七个不同 IRI，均属于冻结目标的实际绑定。评价执行包含七次材料读取、六次治理查询和十六次资源精确展开；不复用生产候选或自查结论作为模型证据。

通过范围包括：模型启用与调用授权的区别；凭证内请求去重；同内容回放与新请求的不同准入；模型停用、凭证停用、额度耗尽及重新启用的差异；一次成功扣一单位、拒绝不扣额、跨模型共享／跨凭证独立；持久化、原子性／并发规则的忠实表达；四表字段、四条连接和实际端点；外部业务行保留；用实际 HTTP 观察核对规则解释。

来源未规定的三项仍按未知保留：显示名称可否修改、撤销授权的操作语义、回放冲突的具体拒绝码／响应形态。观察到某次 HTTP 状态不自动等于已定义所有版本的业务接口政策。

首 run 共一个 fresh semantic start，十四次候选提交，三次应用成功（五个类、六个关系、八个映射依赖顺序补齐），十一次明确 not_written；该 run 没有独立验收后再修模。连续补齐原计划范围与技术纠错不按候选数重计。生产自查实际在 revision 1／2 保持 revise，在 revision 3 才 ready；另保留一次自查 JSON 缺 issues 的原始失败及修正，不能用机械成功覆盖。

生产 work.semantic_acceptance 仍为 unverified；独立报告单独保有判决，没有回写生产笔记或把 handoff_ready 冒充独立 PASS。最终语义结论以绑定 revision 的独立原件为准。

## 首 run 用量与时间

复用既有 distinct-thread 原生累计统计脚本，按每个不同原生线程的最后累计值求和，不叠加累计样本。十九个原生线程均有终态用量，含全部失败／纠正和独立评价。

| 阶段 | 输入 token | 输出 token | 原生线程 | 原生区间并集 |
| --- | ---: | ---: | ---: | ---: |
| 生产建模与纠错 | 1,972,661 | 95,168 | 14 | 35 分 02.976 秒 |
| 生产自查 | 449,705 | 9,490 | 4 | 6 分 33.827 秒 |
| 独立验收 | 331,643 | 7,319 | 1 | 5 分 55.979 秒 |
| 合计 | 2,754,009 | 111,977 | 19 | 47 分 32.782 秒 |

输入＋输出合计 **2,865,986**；缓存输入 **2,219,648** 已包含在输入内。首原生开始 12:31:54.498 UTC，末原生结束 13:22:45.495 UTC，首末窗口 50 分 50.997 秒。首 run 原件为 inputs/observed-usage-first-run.json，known-native coverage 完整；三 run 总表另见下文。

原生区间包含推理、格式纠错、提供商和工具等待，不是纯有效语义劳动。Host 的准备／修复／文档劳动未独立精确计时，外部 Host 用量单列 unknown 且不计任务金额；平台内部排序用量未完整归集，全任务计量仍 PARTIAL。没有提供商最终账单，不能从缓存率或不同业务的历史 token 总量推导净降耗。后续只在同一小场景内作两次有界默认路径验证，共三个 fresh starts；不扩大业务量或开发新的平台／harness 机制。

## 首 run 资源封口与完成边界

完整平台快照 v1-accepted：7272238bc23f41cc8db14bcd538628a4，model_read_error=null。stop 后 control.mode=stopped、active 为空。cleanup 返回 sessions_terminal=true、no_in_flight_attempts=true、aggregate_keys_non_active=true，protocol／admin 临时密钥均 revoked；scope_disposition=written-retained，项目与 Ontology 51a06c92-f0ac-4638-8e88-b2d1971437e1 保留。单本体路径的 ontology_id 与多目标 ontology_ids 分开记录，不把空的多目标数组解释为模型已删除。

原始 start／evaluation 日志、十四次应用及失败、已知用量、验收报告、快照和清理回执均留在原 run／inputs。最终摘要为 inputs/acceptance-summary.json 与 resource-closure-summary.json。

首 run 完成当前构造可运行系统的规则与映射 L1，但使用过运行时技术指导；修后默认路径由第三 run 单独验证。完整 v5、客户／独立开源业务盲测、在线 SQL Consumer E2E、同条件 L2 与净降耗仍未验证。测试项目的程序代码未变，先前二十六项开发测试证据与本轮二十项独立模型验收分开。

## 第二 run：首次修补后的无指导确认，未完成并保留

为验证此次提示修复的实际默认效果，同 task_ref／usage_only 授权启动 llm-access-lab-20261031-start2；task-cold2.json 只更换 run_id 与 workspace_ref。相同四份材料 SHA256、二十项 freeze、GLM Flash／low、目标和新建资源范围均不变，prepare 冻结 bac011c。新的空项目／原生上下文不继承原候选、模型、评价或运行时技术输入。

13:35:59 UTC 前已发出启动命令，13:36:51 UTC 确认原生 turn/started，thread_id=01a1922c-ad0d-7203-9e30-688defcd2270，实际 glm-direct／glm-5.3-flash；控制消息为空。此项是修后默认采用验证，不是与首轮受指导且旧提示运行之间的同条件 L2；也不会用后继成功覆盖首轮失败成本。

首批五类直接应用成功，但后继在 item_id 选择、引用包装、business_key 属性要求和必填中立字段上反复失败，仅有五类实际写入。典型错误包括缺 shared_scope、mapped_class_iri／mapped_definition_iri 均未放入 value、relation_type_iri 直接返回 IRI 字符串。不能把这些执行／合同错误归因于业务模型质量，也不把最后一个尚未应用的提案记成已落地。

Host 先自然暂停，再 stop；停稳时 work.activity=apply，未执行最后提案，没有强制中断原生回合或修改候选。已保存 cold2-stopped-partial 完整平台快照并 cleanup：aggregate_keys_non_active=true、no_in_flight_attempts=true、scope_disposition=written-retained，部分模型和所有失败保留；没有独立完整范围 PASS。

### 第二次持久修复与 T0 复核

实际矛盾是冻结给 Agent 的表／连接映射字段沿用了 API 的 string/absolute-rdf-iri 描述，而候选输入的同一字段必须是 definition_ref／existing_resource_ref 对象。缺少完整中立候选示例也使 Agent 漏掉 shared_scope 等强制元数据。

保留引用校验：它要求来源是已选候选项或真实授权读取／应用回执，直接保护资源身份、授权及确定性引用；没有不可恢复终止 run。删除会允许未经证明的字面 IRI，原子应用和语义验收不能替代实际引用来源。当前可由准确候选类型与完整示例自修复，因此修补输入描述，不放宽校验、不新增次数硬门或恢复框架。

提交 80aef87 将候选引用字段投影为 object，compiled_format 单列后端 IRI；增加通用 table_mapping／join_mapping 候选与变更片段，明确八个必填字段、value 内目标、item_id 选择及 role 条件。示例不含本次业务答案，且经现有真实 validate_unified_candidate 校验器通过。新红测确认旧类型 string 与候选 object 冲突；修后定向 16 项及完整 v5 **222 passed、1 条既有 warning、211.72 秒**，Ruff 通过。未改 backend／frontend，不重启平台。

## 第三 run：第二次修补后的无指导确认，独立 20/20 PASS

同 task_ref、相同四来源／SHA、原二十项标准、相同 GLM Flash／low，task-cold3.json 仅换隔离 run／workspace 身份。14:13:33 UTC 前启动，thread_id=01a1924f-0ff5-70c2-91a4-75cfdf255d86；实际绑定确认包含新引用 object 描述及完整 relational_request_example，生产输入仍只有四项。全程没有运行时 Host 技术输入、业务代答或来源修订；建模 Agent 自行发出的内部消息按实际作者保留。

五次实际应用中三次 completed、两次明确 not_written：四个 Class 到 revision 1；三种关系与四个表映射到 revision 2；三个连接映射到 revision 3。两次失败分别为语义字段不一致和 fields-only create 缺候选项，后继自行修正。最后实际保有 **14 个资源：4 Class、3 relation_type、4 table_mapping、3 join_mapping**。其分组与首 run 不同，授权关系的多步连接覆盖关联表外键路径；验收依据业务完整性，不要求资源数量等同。

自查曾因 JSON 形状，以及只读笔记却缺少实际治理读回而失败；原始失败保留。后继 self-check-00004-002 实际查询模型后才 ready，未放宽读回守卫。14:30:56 UTC 确认 handoff_ready，生产无在途写入。

独立 cold3-full-20 于 14:31:17 UTC 启动，绑定 Project 40841ac8-1c93-4cb1-85ba-1a9e8fb7928b／Ontology 755f1e0e-cf5d-47f2-a2a3-95220f4cba96／revision 3，沿原 freeze v5-llm-access-lab-v1-20-20261031 判定 **20/20 PASS**。逐项索引完整、每题均有非空实际证据，引用十四个不同 IRI，均属于目标实际资源。评价包含七次材料读取、两次治理查询与十六次精确资源展开；原生末回合结束于 14:36:00.340 UTC。报告位于 start3/evaluations/cold3-full-20/private-report.json，公开回执为同目录 public-feedback.json。

完整平台快照 cold3-default-accepted：0038e38d8ead4301882448cdc7f1ddbf，model_read_error=null。stop 后 control.mode=stopped、status=settled、active 为空；cleanup 的 sessions_terminal、no_in_flight_attempts、aggregate_keys_non_active 均为 true，scope_disposition=written-retained。模型与原件保留。第二 run 的未完成结论与失败成本不被此次通过覆盖。

## 三次运行总用量与最终边界

| 运行 | 独立完整范围结论 | 输入 token | 输出 token | 输入＋输出 | 原生线程 |
| --- | --- | ---: | ---: | ---: | ---: |
| start1，运行时技术指导 | 20/20 PASS | 2,754,009 | 111,977 | 2,865,986 | 19 |
| start2，首次修后默认 | 未完成，部分模型保留 | 1,538,734 | 82,250 | 1,620,984 | 15 |
| start3，最终修后默认 | 20/20 PASS | 1,374,213 | 44,034 | 1,418,247 | 11 |
| 合计 | 两份独立 PASS、一份未完成 | **5,666,956** | **238,261** | **5,905,217** | **45** |

总表为 inputs/observed-usage-summary.json，四十五个独立原生线程终态用量齐全：三十三个建模、十个生产自查、两个独立评价，包含全部已知失败／纠正成本。缓存输入 4,347,456 已含在输入内。首末原生窗口为 12:31:54.498—14:36:00.340 UTC，共 2 小时 04 分 05.842 秒；原生执行区间并集为 1 小时 31 分 36.518 秒，仍含工具及提供商等待。最终默认 run 的描述性用量较少，但提示、拓扑及运行条件不同，不作为因果降耗百分比或同条件 L2 证据。

三次均在同一 task_ref／usage_only 授权下运行，不创建／重置金额预算。外部 Host 用量及有效劳动时间、平台内部排序用量仍未完整归集，全任务计量保持 PARTIAL，不补零、不折算最终费用。源码只修复两处有真实失败证据的提示合同，完整 v5 开发回归最终为 222 passed；未新增治理、恢复或验收框架。

最终封口复核已确认三个 run 都 stopped／settled、无活跃执行、无在途 Attempt、所有临时密钥非活动，写入模型全部保留。inputs/final-task-summary.json 汇总实际已应用回执、平台快照、验收目标、用量和清理回执；第二 run 的计划引用不计作实际已应用资源。当前验证完成后停止，不继续增加范围或新启动。

结论只覆盖本构造可运行小系统的两个切片、规则与必要映射，以及修后默认方法的实际采用。程序开发测试、生产自查、独立模型验收、真实 HTTP 观察及最终费用各按证据边界记录；外部真实业务盲测、在线 SQL Consumer E2E、同条件 L2、任意规模和净降耗未获证明。
