# ADR 0005: Modeling Batch 使用持久化计划和向前恢复

## Status

Accepted

R-004 的一次 apply 可能同时修改 RDF Dataset、PostgreSQL Rule/Evidence/审计和图修订，现有部署
不提供跨存储分布式事务。平台决定在任何副作用前固化确定性 operation plan 并建立 Ontology
Write Fence；结果不确定时保留原 Attempt，验证已观察效果后幂等重放或补齐 PostgreSQL 记录，
而不通过删除整图或猜测回滚恢复。

这一选择以更复杂的 plan、fence 和恢复诊断换取稳定标识、可审计幂等性和故障后的确定收敛。
被拒绝的替代方案是把部分失败直接标为普通 validation failure、依赖 RDF/PostgreSQL 双写恰好
同时成功，或无条件回滚 RDF；这些方案会隐藏已发生副作用、破坏并发安全或删除不属于该 Attempt
的内容。
