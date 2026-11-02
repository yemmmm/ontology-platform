# v5 最终模型游离节点核查

- 日期：2026-11-02
- 范围：Demo 多视角模型项目 `7426e636-7fae-4234-ab48-3e50699fe7d1`，Ontology `0bbd5523-3ad5-4dc6-920e-2a761bc83cba`。
- 用户反馈：最终模型中仍有游离节点。
- 核查目标：区分实际业务关联缺失、正式结构引用与谓词使用、画布展示或筛选遗漏；不为全图连通补造业务关系。

## 来源与判据

- [R5.0-003/004](../requirements/requirements-v5.0.md)：当前 v5 持续建模与实际验证范围。
- [R4.0-024](../requirements/requirements-v4.0.md#r40-024-建模完成后的模型检查首项游离节点)：完整受治理读取、正式引用与谓词参与均计入关联；候选不自动等于缺陷。
- [R4.2-003](../requirements/requirements-v4.2.md#r42-003-以图谱画布为主体的模型浏览)：模型画布的节点和边展示合同。
- 保留读回：`workspaces/v5-runs/demo-multiview-20261102-inputs/actual-readback-rebuilt-final.json`。

## 已确认的两个问题

### 画布投影丢失四个连接映射的引用

当前接口真实重读仍为 revision 7、59 个资源、61 条关系，分页完整，原 Demo 及九条 CQ
完整记录保持不变，临时读取管理员密钥已撤销。前端按既有规则隐藏 `owl:ObjectProperty`／
`owl:DatatypeProperty` 后，只显示 36 个节点、38 条边；以下四个连接映射成为零度节点：

| 画布游离节点 | 实际已有引用 |
| --- | --- |
| 授权属于凭证连接 | mappedRelationType → 授权属于凭证 |
| 授权针对模型连接 | mappedRelationType → 授权针对模型 |
| 成功记录属于凭证连接 | mappedRelationType → 成功记录属于凭证 |
| 成功记录针对模型连接 | mappedRelationType → 成功记录针对模型 |

被引用的四个关系定义本身是 `owl:ObjectProperty`，都有实际 `rdfs:domain`／`rdfs:range`
端点。它们因属性节点排除规则而不显示，前端随后丢弃端点不在画布中的边，导致映射看似没有
关联。这是展示路径缺失，不能据此删除映射或在业务模型中补造连接。

修复只在当前授权、同版本读取窗口内，将正式 `mapped_relation` 引用经关系定义的
domain／range 路径显示为两条虚线；边保留中间定义 IRI 和字段路径，谓词仍不单独成节点。
不从名称、说明、表名或任意文本推断关系，不扩大加载或权限范围。多视角过滤仍可使某些
引用的端点不可见，因此局部视角内零度不直接代表整个模型缺关联。

### 实际模型中一处属性与映射矛盾

属性“模型标识”已存在，适用范围明确写对应 `models.id PRIMARY KEY`，但“模型目录映射”
的 id 列没有 `property_iri`，说明和 unknowns 又声称没有已建对应属性。公开原文明确模型标识
唯一、登记后不变；这不是需要重新询问用户的业务未知，而是表达之间的矛盾。

为排除画布窗口误判，Host 直接复用已有 R4.0-024 `MODEL_CHECK_QUERY` 和
`inspect_model_associations`，通过受治理 SPARQL 分页及末尾版本复读检查全部 379 条
statement／59 个资源。结果 `coverage=complete`，仅“模型标识”一个游离候选，未解析引用为 0。
七个局部关系谓词分别实际使用 1～11 次，不属于未用定义。该机械扫描自身保留
`semantic_verdict=not_evaluated`，语义处置仍由建模 Agent 完成。

## 修复与验证进展

- 通用 ontology-modeling Skill 补充最终完整清单、入出关系、谓词使用、正式引用与映射矛盾
  核对，v5 直接复用该章节；不另建仅适用于本 Demo 的业务提示。
- v5 受治理读取工具开放已有 `resource-list` 投影，资源／关系清单显式请求 1000 上限并
  要求检查分页及警告。没有将程序连通性计数改成新的业务硬门。
- 真实 GLM／low 局部修模已在保留项目上启动，工作空间
  `demo-connectivity-20261102-fix1`；旧停止运行不热恢复，原成功应用身份经当前实际读取过滤后
  显式交接。沿原 `task_ref`／5 元金额账本，未创建新预算；启动前剩余估算 0.75253804 元。
- 前三次提案因 update_table_mapping 不支持 mapped_class_iri，或列映射直接粘贴读回 IRI
  而未使用引用包装，被拒为 not_written；第四次原生提交实际成功，未放宽平台字段合同。
  共享 mapping_reference_inputs 提示补上“复制读回集合时，保留元素也须转换引用包装”和
  create-only／可更新字段区别；Host 的联合技术澄清未提供业务候选，未热改冻结输入。
  该输入到达时第四次提案已完成，运行因此额外处理一次 no_change 及自查，照实计量。
- 代码合同与受治理读取测试 36 passed；前端构建通过。相关 Playwright 首轮 32 passed／1 failed，
  失败为旧 node-colors 刷新断言早于 Cytoscape effect（即时读取为空）；未修改代码或测试，
  单独重跑失败用例与新增用例 2 passed。保留首轮失败，不将其掩盖为一次全绿。
- 新增画布测试检查谓词隐藏后两个正式引用路径仍显示、字段与中间身份保留、视角过滤生效、
  未加载端点不泄露、缺少正式 mapped_relation 字段时不猜边。现有节点高亮／大小／颜色与
  工作空间浏览用例均纳入相关回归。

## 证据与边界

- 真实读回与原 Demo 保护：
  `workspaces/v5-runs/demo-multiview-20261102-inputs/model-verification-connectivity-live.json`。
- 修模前完整治理读取与通用扫描：
  `workspaces/v5-runs/demo-connectivity-20261102-inputs/association-read-before.json`、
  `association-scan-before.json`、`association-key-cleanup-before.json`。
- 原始前端失败、后续回归及构建日志：同目录 `frontend-reference-red.log`、
  `frontend-regression.log`、`frontend-failed-case-recheck.log`、`frontend-build.log`。
- GitNexus 未找到相关新前端／v5 符号，detect_changes 仅命中无关文档，不能声称图谱影响覆盖；
  本次按直接调用点、实际 diff 和相关测试核对。

## 实际修复后的验证

实际模型已到 revision 8，仍为 59 个资源；只有“模型目录映射”一项定义发生改变：id 列
以 `business_key` 正式引用已有“模型标识”属性，矛盾的 unknowns 已清除。真实关系投影从
61 增为 62，只增加该列的结构引用，没有增删资源或补造业务三元组；九条 CQ 完整记录不变。
见 `model-change-proof.json` 和 `actual-readback-rebuilt-connectivity-repaired.json`。

复用同一 R4.0-024 全量治理扫描检查 revision 8 的 379 条 statement／59 个资源，
coverage complete、游离候选 0、未解析引用 0；原始读取与扫描见 `association-read-after.json`
及 `association-scan-after.json`，临时密钥有撤销回执。此结果不替代语义裁决。

前端相关构建和测试完成后，已重启 ontology-platform.service，systemd active，后端健康
接口与前端根页面均成功。重启后的真实 Chrome 页面通过真实受治理 API 读取相同 revision 8，
画布 36 节点／46 条线，其中 8 条虚线保留四个连接映射的起点／终点引用路径；零度节点 0，
页面异常 0。原始证明与截图为 `live-canvas-proof.json`、`live-canvas.png`，浏览器临时管理员
密钥已在 finally 撤销。画布投影保留既有的 23 个属性／关系谓词定义不独立成节点约定，
所以可见 36 不等于实际资源只有 36。

独立 `connectivity-final-36` 已在相同 revision 8 **36/36 PASS**，保留原 35 题并增加关联／
映射一致性第 36 项。Host 核对其独立原生回合实际完成 23 次只读工具调用，包括直接读取
冻结题及全部声明来源、resource-list、resource-relations、property-list 和相关 detail；无失败
调用。第 36 项明确依据实际 id 列引用及关系端点处置本次缺口。此前 35/35 未发现该矛盾的
历史原件保持，不能将新报告倒填为此前已验证。

最终快照 `4c8215883c0f45739845dcfa1d1394e5` 已包含实际平台数据；运行 stopped，
生产 Sessions terminal、无在途写入，现有模型保留。管理／协议／生产读／验收读四把临时
密钥均有数据库撤销时间，额外 Host 扫描和浏览器临时密钥亦各有 finally 撤销回执。

沿原 5 元预算，最终托管调用计量估算 **4.75448420 元**，本次局部修复／自查及追加独立
复核增加 **0.50702224 元**；余额估算 0.24551580 元。38 个累计原生用量单元全部已知，
provisional／unknown／inflight／待结算均为 0。外部 Host 与未接入辅助用量仍按原口径单列，
本数不是供应商总账，也不证明净降耗。原始预算和收口见 `usage-final.json`、`status-final.json`、
`cleanup-final.json`、`key-revocation-final-proof.json`；读取审计见 `independent-read-audit.json`。

该结果证明本有界公开 Demo 的局部修正与追加独立复核；Host 提供了公开读回定位与技术
格式澄清，不是无人干预新建模／盲测或完整 v5 产品化验收。不将连通图当作业务完整性证明。
