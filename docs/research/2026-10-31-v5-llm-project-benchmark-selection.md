# v5 测试系统：大模型开源项目与临时管理系统

日期：2026-10-31。用户先要求比较 Langfuse、LiteLLM、Mem0 等熟悉的大模型项目，随后提出直接编写一个具有简单逻辑的测试管理系统。本次沿后一项指示实现独立示例，保留开源比较供下一阶段使用。

## 选择结论

当前先做小型、可运行的“模型访问与额度管理”系统，作为有确定操作结果的构造业务基线。它比继续增加文字模拟材料更容易核对数据、拒绝条件和变化结果；但源材料、实现和开发测试均由我们构造，不能宣称外部真实业务验证或独立语义验收已经通过。

若下一阶段必须使用独立开源产品，优先复核 New API 的最小单机测试范围；若只要轻量 SDK 业务，优先 Mem0 OSS 库。LiteLLM 只考虑有数据库的有界 Proxy 范围；Langfuse 留到已经有可用实例或可以接受较多依赖时。

## 开源项目比较

以下规模、文档评价与优先级是当次官方资料支持的定性判断，未部署或测量启动耗时。仓库 size 含历史等因素，不是代码行数或模型所需上下文，不据此单独排序。

| 项目 | 最小可运行范围与部署事实 | 文档评价及实际限制 | 当前建议 |
| --- | --- | --- | --- |
| Langfuse | 当前 v4 官方 Compose 含 web、worker、PostgreSQL、ClickHouse、Redis、MinIO 六服务 | 概念、部署、API、Prompt 与评估资料齐；完整平台覆盖面与存储链较多 | 文档好，但新建试验环境偏重；已有实例时可选 Prompt 版本＋关联调用追踪 |
| LiteLLM | SDK 与 Proxy 不同；当前 Proxy quickstart 为网关＋PostgreSQL 两服务 | 配置、密钥、预算、路由文档齐；整体项目广；虚拟密钥与消费跟踪需要数据库，不能以无数据库模式宣称覆盖 | 可选有界模型目录／路由＋虚拟密钥访问，不把整个仓库称为小项目 |
| Mem0 OSS | 库默认本地 Qdrant、SQLite 历史，另需 LLM 和 embedding；完整 server 为 API、pgvector/Postgres、dashboard 三服务 | SDK、配置和自托管说明齐；必须分开 OSS／云端及版本；抽取和检索含模型波动 | 三个指定候选中，库模式启动较轻；适合记忆写入／生命周期＋主体范围内检索，实际效果验收较难 |
| One API | README 支持单容器 SQLite 测试模式 | 中文部署与功能说明清楚；仓库管理 API 文档仅约 53 行，规则说明粒度不及完整参考站 | 体量小，但不能仅凭 README 宣称建模材料已完整；暂不首选 |
| New API | 官方支持单容器 SQLite 临时测试；仓库默认 Compose 为应用、Redis、PostgreSQL | 有部署、渠道、令牌和 API 站点；部分业务页以截图为主，完整产品包含更多能力 | 独立产品下一候选，先冻结“渠道／模型＋令牌访问”小范围；不启动订阅、支付、插件等范围 |

资料：

- Langfuse：[部署手册](https://langfuse.com/self-hosting/deployment/docker-compose)、[冻结 Compose](https://github.com/langfuse/langfuse/blob/bbbe1c2b5e2ab607154be01e7d2a99f19cb0791c/docker-compose.yml)、[README](https://github.com/langfuse/langfuse/blob/bbbe1c2b5e2ab607154be01e7d2a99f19cb0791c/README.md)。
- LiteLLM：[快速开始](https://docs.litellm.ai/docs/proxy/docker_quick_start)、[虚拟密钥](https://docs.litellm.ai/docs/proxy/virtual_keys)、[请求过程](https://docs.litellm.ai/docs/proxy/architecture)、[冻结 quickstart Compose](https://github.com/BerriAI/litellm/blob/a713ed6bab40bac7a12d6ab5f52550aa82663cac/docker/docker-compose.quickstart.yml)。
- Mem0：[开源概览](https://docs.mem0.ai/open-source/overview)、[自托管](https://docs.mem0.ai/open-source/setup)、[冻结 Compose](https://github.com/mem0ai/mem0/blob/753496cf1435d76c3a711f3af51303f7fdcb6420/server/docker-compose.yaml)、[README](https://github.com/mem0ai/mem0/blob/753496cf1435d76c3a711f3af51303f7fdcb6420/README.md)。README 明确云端结果含 OSS 未提供的专有优化，不能将该宣传分数当作本地 OSS 预期。
- One API：[README](https://github.com/songquanpeng/one-api/blob/8df4a2670b98266bd287c698243fff327d9748cf/README.md)、[管理 API](https://github.com/songquanpeng/one-api/blob/8df4a2670b98266bd287c698243fff327d9748cf/docs/API.md)。
- New API：[快速开始](https://docs.newapi.pro/en/docs)、[SQLite 测试部署](https://docs.newapi.pro/en/docs/installation/deployment-methods/docker-installation)、[渠道](https://docs.newapi.pro/en/docs/guide/console/channel-management)、[令牌](https://docs.newapi.pro/en/docs/guide/console/api-token)、[冻结 Compose](https://github.com/QuantumNous/new-api/blob/ea343c4a81151bfd537d33b66527c25fa21a1112/docker-compose.yml)。

检索说明：MiniMax 返回余额不足后采用官方仓库连接器与网页工具。只读取上游资料，没有运行其初始化脚本、注册账号、执行源码指令或使用真实供应商密钥。Mem0 首次读取 .yml 路径为 404，目录核实后成功读取实际 .yaml 文件。

## 临时测试项目的最小设计与实施步骤

目标：实现 [llm-access-lab](../../examples/llm-access-lab/README.md)，提供模型可用性、凭证授权与次数额度两个关联切片。一次成功新调用扣一个额度单位；本地生成确定性结果，不调用真实模型、不计算 token 或金额。

实现只新增 examples/llm-access-lab；FastAPI 提供交互 API 文档，SQLite 存模型、凭证、模型授权及成功调用。管理面向本机试验操作者开放，调用接口验证独立测试凭证；这不是生产级管理后台或真实供应商代理。

- [x] 写业务文档，明确检查次序、重复请求、失败不扣额、启停与持久化；编写 HTTP 行为测试，先验证缺失功能导致失败。
- [x] 实现模型／凭证管理与真实 SQLite 写入，验证两个切片组合及请求幂等；不新增 OntoWeave API、适配器或框架。
- [x] 运行项目测试与一次临时端口真实 HTTP 闭环，结束服务并保留结果；不重启平台服务。
- [x] 保存开发验证记录和生产侧输入边界。后续建模仅获得业务文档、API 合同、Schema 和获准数据，测试断言／隐藏评价资料不得混入生产输入。

实际结果见[开发验证记录](../../examples/llm-access-lab/VERIFICATION.md)：核心实现 265 行 Python，四张业务表；项目独立环境 26 项测试通过，含真实 CLI／HTTP、SQLite 持久化、并发扣额与请求幂等。保留一条 Starlette TestClient 对 httpx 的弃用提醒。未启动新建模或独立语义验收。

当前需求依据为用户本轮临时项目指示；平台验收边界延用 [v5 需求](../requirements/requirements-v5.0.md)及[已完成两切片证据](2026-10-31-v5-two-slice-service-progression.md)。本示例开发通过不关闭新的 v5 建模质量验收、真实开源一致性或净降耗。
