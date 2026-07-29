# v2.2 建模执行架构复用需求

## 文档信息

- 文档状态：规划中
- 基础版本：`docs/requirements/requirements-v2.1.md`
- 关联版本：`docs/requirements/requirements-v1.0.md`、`docs/requirements/requirements-v1.1.md`、
  `docs/requirements/requirements-v2.0.md`
- 当前需求：R2.2-001 建模 Host Workflow 与 Agent Runtime Adapter 解耦
- 更新日期：2026-07-27

## 背景

R2.1-001 M3 已通过一套完整的自主建模流程，覆盖输入隔离、Project/Ontology/Build Session、
Evidence、Modeling Batch dry-run/apply、validation、reasoning、行为查询、独立只读消费和二十环境
mutation 验收。

M5-P0 原计划只把底层 Agent Runtime 从 Codex 替换为 Pi，并复现同一份 M3 静态合同。实际实施中，
Pi 专属场景重新实现了模型代理、平台文件队列、8012 生命周期、Producer 准入、lease recovery，
并准备再次实现 Consumer 和 mutation 编排。由此产生的 JSONL 读取、RPC 背压、长运行 lease 过期
等问题主要属于 Runtime 适配和重复 Host 编排，而不是建模质量问题。

本轮结论是：后续不得继续为每个 Agent Runtime 复制一套完整建模流程。M3 已验证的确定性 Host
Workflow 应成为公共执行层，Codex、Pi 或其他 Runtime 只提供薄 Agent Adapter。

## 需求列表

| ID | 需求 | 优先级 | 当前状态 | 主要依赖 |
| --- | --- | --- | --- | --- |
| R2.2-001 | 建模 Host Workflow 与 Agent Runtime Adapter 解耦 | P0 | 待细化 | R2.1-001 M3、M5-P0 证据；R2.0-001 |

## R2.2-001 建模 Host Workflow 与 Agent Runtime Adapter 解耦

### 现状是什么，需要改成什么

当前：

- M3 的 Codex 场景已经拥有完整 Producer、Consumer、mutation 和平台验收流程；
- M5-P0 的 Pi 场景又单独实现同类 Host 编排，导致底层 Runtime 变化扩大为整套流程重写；
- Runtime-specific launcher、平台编排、验收逻辑和安全门禁混在同一 runner 中，难以判断问题来自
  Agent 能力、建模方法还是 Harness 自身；
- 相同 M3 语义合同在不同 Runtime 下不能直接横向比较。

目标：

- 提取一套 Runtime 无关的公共 Host Workflow，复用 M3 已通过的正式建模和验收路径；
- Codex、Pi 等 Runtime 只通过稳定的 Agent Adapter 接入；
- 更换 Agent Runtime 时，只替换启动、输入装配、事件解析、工具桥接和终态判断，不重新实现
  Producer、Consumer、mutation 或平台业务流程；
- 相同输入、平台反馈、语义门禁和独立验收可在不同 Adapter 下重复执行和比较。

### 责任边界

#### 公共 Host Workflow

公共层负责：

- 净化输入 staging、manifest/hash 和禁止答案材料检查；
- 隔离 backend 生命周期和运行健康检查；
- 本轮 Project、Ontology、Build Session、Evidence 和资源归属；
- 受限平台 gateway、请求/响应/receipt 绑定和凭据注入；
- Modeling Batch dry-run/apply、fresh workspace/lease、validation、reasoning 和行为查询门禁；
- 独立只读 Consumer 的平台响应准备；
- tester-owned mutation specification、二十环境执行和清理；
- 追加式运行证据、失败门定位、准入和最终验收。

公共层不得替 Agent 选择本体结构、生成答案型 Modeling Items 或把测试期望反馈给 Agent。

#### Agent Runtime Adapter

每个 Adapter 只负责：

- 创建新鲜 Runtime/Session 并装配固定 Prompt、输入和公共工具合同；
- 建立 Runtime 所需的模型调用通道，但不暴露 provider credential；
- 把公共文件队列或结构化工具映射为 Runtime 可调用工具；
- 把 Runtime 原生事件规范化为公共事件：启动、消息、工具调用、终态、失败和 settled；
- 提交用户/Host 后续输入并执行有界停止与进程回收；
- 输出 Runtime、模型、参数、Prompt/配置哈希和安全运行元数据。

Adapter 不得复制 Modeling Batch、validation、reasoning、Consumer、mutation 或业务验收逻辑。

### 当前最小范围

1. 以 M3 已通过的 Host 侧流程和测试合同为基线，识别并提取 Runtime 无关部分；
2. 定义一个最小 Agent Adapter 合同，首批实现 Codex Adapter 和 Pi Adapter；
3. 先保证 Producer、Consumer 和 mutation 复用同一公共 Host Workflow，不追求通用插件框架；
4. 复用 M5-P0 已验证的 Pi 二进制 JSONL reader、settled 证据和必要模型通道，但不把当前
   Pi 专属 runner 整体提升为公共架构；
5. lease freshness/recovery 属于公共 Host Workflow，不能仅写入 Agent Prompt，也不能由每个
   Adapter 分别实现；
6. 保留 M3 历史运行证据及 M5-P0 的逐轮状态记录作为迁移对照，不重写既有失败轮次。

### 未来产品化

以下内容可以预留扩展点，但不属于当前完成门槛：

- backend 内嵌或常驻 Agent Runtime；
- 远程执行、分布式调度、并发租户和自动崩溃恢复；
- 通用多供应商模型代理或密钥管理产品；
- Runtime/Adapter 管理 UI、动态插件市场或版本治理平台；
- 生产级 sandbox、危险工具策略和跨机器协调。

### 验收标准

1. 公共 Host Workflow 的 Producer、Consumer、mutation 和平台验收逻辑只有一份权威实现；
2. Codex Adapter 能在公共 Workflow 下保持 M3 已通过的核心行为和隔离合同；
3. Pi Adapter 能在同一公共 Workflow 下完成至少一轮完整 Producer、独立 Consumer 和既有
   二十环境 mutation 验收；
4. 两个 Adapter 使用相同的净化输入、平台反馈、语义完成门和 tester-owned 断言，不复制或注入
   M3 答案型本体、查询或 Batch payload；
5. Runtime-specific 失败能够被定位在 Adapter 层；平台、建模语义和 Harness 错误可以分开报告；
6. fresh workspace/lease、同-items retry、receipt、准入和清理由 Host 强制，不能依赖 Agent
   自觉遵守 Prompt；
7. 迁移后删除或归档重复的 Runtime-specific Host 编排入口，并保留历史证据链接；
8. 独立测试记录 PASS，且常驻服务、8001/5173 和隔离资源清理健康。

### 与既有需求的关系

- v1.0 R-003/R-004/R-008 继续提供 Build Session、Modeling Batch、认证和 Project 隔离；
- v1.1 Harness 继续定位为 repo-local 流程/评测证据，不成为平台事实或正式 API；
- v2.0 R2.0-001 提供 Pi Runtime 能力证据，R2.0-002 的旧完整编排不直接恢复；
- v2.1 M3 提供公共 Host Workflow 的行为基线；
- v2.1 M5-P0 作为问题状态和 Adapter 迁移输入阶段关闭，不要求先完成其重复的 Pi 专属
  Consumer/mutation 实现；逐轮状态见
  `docs/delivery/records/2026-07-29-r2-1-001-m5-test-round-status.md`。
