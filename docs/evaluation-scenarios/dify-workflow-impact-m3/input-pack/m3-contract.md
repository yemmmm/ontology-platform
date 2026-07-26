# R2.1-001 M3 净化需求合同

## 目标

在一个全新的空 Project/Ontology 中，由自主建模 Agent 根据业务说明、固定官方资料和平台
确定性反馈，独立形成、验证并应用本体候选。验收比较业务语义行为，不比较既有模型的名称、
IRI、三元组数量或图结构。

## 责任边界

- 建模 Agent 理解资料，选择概念边界、本体结构、约束、公理和查询，并根据平台反馈自主迭代。
- Semantic Platform Core 只保存已提交的模型与事实，执行确定性 dry-run、apply、validation、
  reasoning 和 scoped query，返回事实、来源、推论与明确未知。
- 独立消费 Agent 只依据平台返回的事实形成调用方候选与影响解释。
- 平台与本体不判断高、中、低影响等级，不把路径成员断言为业务上一定受影响。
- Dify 语义是参考本体数据，不得成为平台专属 API、Schema、查询分支或解释逻辑。

## 自主性边界

- 主 Agent 只处理隔离服务、凭据、权限、网络、进程和公开工具合同问题。
- 主 Agent 不选择或修改 Class、Property、Shape、公理、关系结构、IRI、候选查询或最终模型。
- 建模 Agent 可根据本轮自己的 dry-run、validation、reasoning 和查询结果反复调整。
- 如果出现主 Agent `semantic-decision` 介入，本轮不能证明完全自主。

## 正式写入边界

- 所有最终候选必须先通过 immutable Modeling Batch dry-run，再使用 fresh workspace version、
  有效 lease 和 `apply_atomic` 应用。
- 禁止 semantic edit、dataset load、`validate=false`、直接数据库/RDF 写入或领域专属扩展。
- 官方来源与合成 Fixture 使用直接原文 Evidence；建模判断进入 Item `rationale`、Checkpoint
  和执行日志，不创建推断型 Evidence。

## 必须证明的行为

1. 已发布 Output 删除可取回直接和传递调用方以及完整跨 Workflow 数据使用上下文。
2. 相同删除只存在于 Current Draft 时，不混入当前 Latest Version 发布链。
3. 自主 Agent 自己定义的无效结构被已显式激活的 Shapes 稳定拒绝。
4. 至少一个当前平台支持的推理预期成立。
5. 未建模或无法确认的信息作为带说明的显式未知返回。
6. 独立消费 Agent 的结论可逐项追溯到来源事实、合成事实、推论或自身判断。
7. 失败、修正、重试、人工介入、遗留问题和下一轮建议被安全记录。

## 停止条件

- 正式通用命令无法表达必要语义；
- 只有读取既有答案产物才能继续；
- 只有绕过 validation 或 canonical writer 才能继续；
- 输入隔离、完整 transcript 或秘密审计无法证明。

任何停止条件触发时，本轮结论是 `BLOCKED` 或 `INCONCLUSIVE`，不能 PASS。
