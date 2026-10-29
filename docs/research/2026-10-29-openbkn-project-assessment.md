# OpenBKN 项目调研

调研日期：2026-10-29。状态：**官方资料与关键源码静态调研完成；未部署、未复跑基准测试、未执行独立业务语义验收。**

本记录补存本次对话中的调研结论。研究对象是 [openbkn-ai](https://github.com/openbkn-ai) 的 OpenBKN，
不是 OntoWeave 的组成部分；下文建议不构成产品需求、选型决定或实现授权。

## 1. 判断

**OpenBKN 值得作为 OntoWeave 的重点对标项目。**公开产品范围已覆盖业务建模、数据接入、语义查询、
动作执行、权限治理和证据追踪。关键接口具有对应源码与测试文件，具备继续评估的工程基础。
这些静态证据不证明特定部署可用、业务答案正确或宣传中的成本收益成立。

直接采用时，版本成熟度、商业能力边界、按文件许可和 Kubernetes 部署成本是实际影响因素。
本轮更适合借鉴上下文按需提供、业务模型约束查询、可版本管理的建模文件，以及样例与评价证据的组织方式。

## 2. 定位与组成

BKN 是 Business Knowledge Network（业务知识网络）。OpenBKN 将业务对象、关系、行动、指标等语义，
与数据源和工具连接，供外部 Agent 查询与执行。例如，回答订单延期风险需要连接订单、物料、库存与交付规则，
并在需要时使用绑定的计算或行动能力。[官网][website]

| 层次 | 组件 | 职责 |
| --- | --- | --- |
| 使用入口 | BKN Studio、SDK、CLI、Skills | 可视化管理与外部 Agent 操作 |
| 业务语义 | BKN Engine | 对象、关系、行动、风险等业务概念与数据映射 |
| 上下文 | Context Loader | Schema 检索、实例查询、逻辑属性与行动能力读取 |
| 数据访问 | VEGA | 数据连接、资源发现、查询、全文与向量索引 |
| 执行 | Execution Factory | 接入 OpenAPI、MCP、函数与 Skills |
| 治理 | BKN Safe、BKN Trace | 权限、审计、运行追踪与业务证据；具体能力受版本和商业分层影响 |

架构与组件来源见 [Foundry README][foundry-readme]。后端核心以 Go 为主，部分基础服务使用 Python；
Studio 使用 React、TypeScript、Vite。[Studio README][studio-readme]

| 仓库 | 用途 |
| --- | --- |
| [bkn-foundry](https://github.com/openbkn-ai/bkn-foundry) | 后端基础与各运行服务 |
| [bkn-studio](https://github.com/openbkn-ai/bkn-studio) | Web 工作台 |
| [bkn-sdk](https://github.com/openbkn-ai/bkn-sdk) | TypeScript SDK、统一 CLI 与 Agent Skills |
| [bkn-samples](https://github.com/openbkn-ai/bkn-samples) | 业务模型、样例数据、安装包与评价材料 |
| [openbkn-deploy](https://github.com/openbkn-ai/openbkn-deploy) | 安装、部署、升级与运维脚本 |

Foundry 明确声明自身是 `kweaver-ai/kweaver-core` 的 fork。BKN Engine、Context Loader、VEGA、Dataflow、
Execution Factory 等包含上游来源；研究底层实现时需要同时追踪 KWeaver 与 OpenBKN 的改动归属。[NOTICE][notice]

## 3. 关键技术机制

### 3.1 文本化业务建模

`.bkn` 使用 YAML Frontmatter 加 Markdown 正文，按文件描述业务对象、关系、行动和概念分组。
对象定义包含属性、主键、显示键和数据来源；关系表达端点与映射；行动绑定工具或 MCP。
外部 Agent 可生成目录，再通过 CLI 执行 `validate`、`push`、`pull`。
建模文件描述结构与语义，执行逻辑由绑定能力承担。[建模手册][bkn-manual]、[SDK README][sdk-readme]

这种表示便于人和 Agent 阅读、版本比较与协作，但模型声明本身不证明业务定义正确，
也不证明所有被描述的规则都具有运行时执行语义。

### 3.2 业务模型约束查询

只读 openCypher 子集使用业务对象类作为标签、关系类作为边、逻辑属性名作为字段。
关系型数据路径可以经过解析、语义分析、模型绑定与授权，生成 SQL，再交由 VEGA 查询数据。
SQL 生成器使用资源占位符，由下游解析成物理表；调用方不必直接操作物理表名。
主线查询服务还具有图结果、非 SQL 数据源和 bind-join 等执行分支，不能把全部查询概括为单条 SQL 执行。
[Cypher 手册][cypher-manual]、[查询服务源码][cypher-service]、[SQL 生成源码][sqlgen]

从源码看，查询服务在读取前检查对象、关系与属性授权，并为查询结果截断提供状态。
这支持“模型参与查询约束”的架构判断；本轮没有验证所有查询形状、连接器和权限组合。

### 3.3 渐进式上下文

Context Loader 的基本顺序是先找相关 Schema，再查询实例，随后读取逻辑属性、指标或行动。
大网络可返回骨架，结合概念组、搜索和分页下钻；MCP 提供精简与按需发现入口。
公开接口还区分受管交互与 REST 临时调用，后者不自动获得业务证据链。
[Context Loader 手册][context-manual]、[API 集成说明][context-api]

值得借鉴的是按任务提供充分信息，而不是默认展开整个网络；具体往返、补读和追踪开销仍须实测。

## 4. 版本、许可与部署

### 4.1 版本与样例状态

截至调研时，GitHub 最新正式发布为 **v0.2.0，发布时间 2026-10-16**；已读取的主线 `VERSION` 为 `0.2.1`。
Foundry 约有 1,000 stars、80 余 forks；这些数量只反映公开关注度，不作为成熟度或质量证明。
[正式发布][release]、[主线版本][version]

样例覆盖供应链、世界杯、制造、金融 FIBO、零售 GS1、能源等场景。部分新包要求 `>=0.2.1 <0.3.0`，
并明确标注候选包或平台验收待完成。不能将主线代码、候选样例和正式版已交付能力混为一谈。[样例说明][samples-readme]

### 4.2 许可与商业分层

Foundry 采用按文件来源区分的多许可：上游及其既有文件修改保留 Apache 2.0；
明确引用 OpenBKN License 的净新增文件受附加条件约束。
附加条件涉及商业功能订阅、受限制托管服务、许可校验和前端品牌保留等。
不能统一按全仓纯 Apache 2.0 理解；实际复用需要核对目标版本与具体文件。
SDK 独立仓库当前附带 Apache 2.0，说明跨仓库也不能只套用 Foundry 的概括。[许可总览][license]、[附加条件][license-openbkn]、[SDK 许可][sdk-license]

官网在调研日列出的产品分层如下，实际交付以对应发布版本为准：[官方比较][pricing]

| 版本 | 官网列出的主要边界 |
| --- | --- |
| Community | 免费；核心建模、查询、执行、常见数据源、顶层资源授权与基础审计 |
| Professional | 1,490 美元/月或 14,900 美元/年；增加细粒度对象授权、SQL Server/Oracle、逻辑视图、图探索及 Object Metrics 管理等 |
| Enterprise Standard | 联系销售；增加 SAP HANA、对象行列规则与业务时间线、证据链等 |

“核心支持指标建模”与“Object Metrics 管理、版本及结果查询”的商业分层应按官网细表区分。
运行诊断 Trace 也不能等同于免费获得完整业务证据链。

### 4.3 部署成本

标准安装以 Linux、Kubernetes 与 Helm 为基础，并包含 MariaDB、Redis、Kafka、OpenSearch 等依赖；
可以选择单节点 kubeadm 或较轻的 k3s。官方文档列出的测试最低配置为 4 核、8 GB 内存、200 GB 磁盘，
生产最低推荐为 16 核、32 GB 内存、500 GB 磁盘。这是文档建议，未在本轮测量资源占用或完成安装验收。[部署文档][deploy-readme]

## 5. 质量与降耗证据的边界

README 自报 HR 问答实验通过率 99.31%（144/145），并提供 Schema 预加载、工具精简和路径指引的消融表。
这些数据可以帮助形成验证假设，不能替代独立复现；表中的固定版本、任务、工具和模型条件，
也不等于当前各平台的同条件横向比较。本轮没有复跑或确认宣传中的通用准确率、Token 与 TCO 降幅。[实验表][foundry-readme]

公开 Issue [#2455][precision-issue] 在调研时仍开放：报告者记录了 Context Loader 转发读取和计算结果时，
将 `9007199254740993` 舍入为 `9007199254740992`，并区分后端直连、REST 与 MCP 的结果。
这是报告者在指定部署版本上的复现证据，本轮没有独立复现，也没有据此推断所有数值或当前主线均有相同问题。
它说明业务验收需要比较真实值，HTTP 200 和工具完成状态不足以证明结果正确。

## 6. 与 OntoWeave 的关系与借鉴顺序

| 维度 | OpenBKN 公开实现重心 | OntoWeave 当次比较基线 |
| --- | --- | --- |
| 模型表达 | BKN 文件与业务对象模型、数据绑定 | RDF/Oxigraph 语义图 |
| 数据消费 | 数据源接入、实例查询、模型约束的 Cypher 执行 | 授权语义上下文与外部数据执行边界 |
| 产品范围 | 数据、工具、模型管理与企业治理的一体化平台 | 外部 Agent 建模、确定性应用、受治理检索与证据 |
| 验证 | 项目方实验、样例评价与具体运行问题 | 保留独立语义验收，不以机械通过代替业务正确性 |

OntoWeave 一侧依据 [README](../../README.md)、[仓库规则](../../AGENTS.md)和
[R4.3-030](../requirements/requirements-v4.3.md#r4-3-030)。本轮没有完整审计 OntoWeave 的最新实现，
也没有将上述定位比较当作双方质量或性能排名。

建议优先研究三项机制：

1. **上下文供给。** 比较 Schema 骨架、按需下钻与工具按需发现；复用本项目已有能力，仅研究真实差异。
2. **模型约束查询。** 观察字段、关系路径和授权如何进入确定性查询计划。是否引入新执行能力需另按产品边界讨论。
3. **业务资产与评价组织。** 参考可版本管理的模型目录、样例包、冻结题库和明示的验收范围。

OpenBKN 的上述降耗机制主要作用于检索与消费侧；OntoWeave 当前 R4.3-030 的重点是 Delivery 的推理往返与累计历史。
两个环节需要分别测量，不能用对方检索实验的比例推导本项目 Delivery 的预期节省。
若后续进行运行比较，应固定同一业务范围、输入、模型、工具与评价标准，记录完整任务成本及质量结果。

## 7. 来源快照与本轮范围

以下为本次实际读取内容对应的提交，便于区分主线后续变化：

| 仓库 | 已读取提交 |
| --- | --- |
| bkn-foundry | `1dcc8718224d8ee09a6d269596a22b43dec49f4f` |
| bkn-studio | `c3db18c9528d12622ea39f12aaa77852682d791c` |
| bkn-sdk | `af7ab6feadb60b2ae4dc54fef174db41f9b4423e` |
| bkn-samples | `f4008399a4b922b5a5c8273a0662b7be18950b3e` |
| openbkn-deploy | `b36710fc5ee02485b0a14c09f35e0d5091cef3cc` |

官网价格、GitHub 数量和 Issue 状态是调研日快照，可能随时间变化。
本轮没有安装或启动 OpenBKN，没有调用其业务环境或付费模型，没有修改 OntoWeave 运行代码。
文档与来源检查只证明记录可追溯，不构成运行、性能或语义验收 PASS。

[website]: https://openbkn.ai/
[pricing]: https://openbkn.ai/pricing-and-compare/
[foundry-readme]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/README.zh.md
[studio-readme]: https://github.com/openbkn-ai/bkn-studio/blob/c3db18c9528d12622ea39f12aaa77852682d791c/README.md
[sdk-readme]: https://github.com/openbkn-ai/bkn-sdk/blob/af7ab6feadb60b2ae4dc54fef174db41f9b4423e/README.md
[samples-readme]: https://github.com/openbkn-ai/bkn-samples/blob/f4008399a4b922b5a5c8273a0662b7be18950b3e/README.md
[notice]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/NOTICE
[bkn-manual]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/help/zh/manual/bkn.md
[cypher-manual]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/help/zh/manual/cypher.md
[cypher-service]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/adp/bkn/bkn-backend/server/logics/cypher/query_service.go
[sqlgen]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/adp/bkn/bkn-backend/server/logics/cypher/sqlgen.go
[context-manual]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/help/zh/manual/context-loader.md
[context-api]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/docs/api/context-loader/README.md
[release]: https://github.com/openbkn-ai/bkn-foundry/releases/tag/v0.2.0
[version]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/VERSION
[license]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/LICENSE
[license-openbkn]: https://github.com/openbkn-ai/bkn-foundry/blob/1dcc8718224d8ee09a6d269596a22b43dec49f4f/LICENSE-OPENBKN.txt
[sdk-license]: https://github.com/openbkn-ai/bkn-sdk/blob/af7ab6feadb60b2ae4dc54fef174db41f9b4423e/LICENSE
[deploy-readme]: https://github.com/openbkn-ai/openbkn-deploy/blob/b36710fc5ee02485b0a14c09f35e0d5091cef3cc/README.zh.md
[precision-issue]: https://github.com/openbkn-ai/bkn-foundry/issues/2455
