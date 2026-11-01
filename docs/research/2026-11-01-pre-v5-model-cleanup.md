# v5 之前建模模型清理

日期：2026-11-01。状态：已完成当前平台中可确认属于 v5 之前的模型清理。
删除 77 个旧项目、83 个本体；保留 38 个 v5 项目、39 个本体，所有实际模型哈希一致，
Demo 九条 CQ 完整记录不变。操作前已备份，未进行全库孤立图垃圾回收。
[可审阅汇总](../delivery/evidence/2026-11-01-pre-v5-model-cleanup/summary.json)。

用户授权清理 v5 之前的建模模型。本次按实际平台项目／本体及运行归属清理，保留 v5
创建或接续的项目、当前 Demo 九条 CQ，以及仓库历史运行、失败和验收原件。

先读取实际 PostgreSQL 元数据、既有 v5 工作空间绑定及平台生命周期实现；不能只按创建日期
或项目名中的 R2.3 前缀判断版本，因为 v5 也复用同一资源创建器。尤其 platform-normal-001
虽然名称没有 v5，但属于 v5-codex-p0，必须保留。

清理使用现有平台能力，操作前为确定归属的旧项目保存模型数据快照和原图依据，核实没有
在途写入或活动执行；实际删除后检查平台行、命名图和保留范围。原件保存于
`workspaces/pre-v5-model-cleanup-20261101/`，最终追加范围、回执、异常与验证限制。

参考：`skills/modeling-dev-loop/SKILL.md`、v5 runbook、`backend/app/api/ontologies.py`、
`backend/app/services/ontology_crud.py`、`backend/app/services/checkpoint_data.py`。

## 实际范围

清理前实际为 115 个项目、122 个本体。根据 `workspaces/v5-runs/`、v5-codex-p0 等已有
binding／scope 记录和当前平台身份匹配，保护 38 个项目／39 个本体；未仅按日期筛选。
其中 `R2.3 team platform-normal-001` 是 v5 早期验证资源，名称没有 v5 仍保留。
剩余 77 个均为旧 Team 建模或 R006 历史测试项目，涉及 83 个本体；目标 ID 和分类依据
保存在 inventory-before.json、scope-classification.json 及备份计划。

实际核实目标没有在途 apply、写入 fence 或仍有效的 lease，且没有 v5 本体引用目标旧本体。
未发现旧建模进程。三个仍标 active 的旧 Session 最后活动分别为 10 月 8、10、14 日（UTC），
沿原 API、实际 revision 注销后再删除，没有强行清除 fence 或重放模型操作。

## 备份与删除

操作前保存了 75 份现有 checkpoint-data 平台模型快照，逐份验证 snapshot digest；另存两份
无本体旧项目的元数据，共 77 份项目备份。保存 88 个确定归属的关联图名的原文／空状态、
SHA256 和规范化 RDF 哈希，及四个旧派生指针。备份共 **5,117,549 字节（约 5.1 MB）**，
位于 `workspaces/pre-v5-model-cleanup-20261101/backup/`，没有提交数据库／RDF 原文到 Git。
删除前重新核实备份文件摘要、目标版本和图哈希；38 个 v5 项目及 Demo CQ 也保存了前态。

首个备份探针发现旧派生指针指向的图已经不存在，直接导出返回缺图错误。该轮没有删除
任何模型；保留 backup.log 和 cleanup-plan-backup-failed-01.json，撤销临时权限。
随后先核实实际图是否含数据，按缺失／空状态记录，不将不存在的旧图当作成功导出内容。
另有一份未登记的旧 data 图，经已核实的旧本体原生 ID 和平台 namespace 生成的精确 URI
匹配后补充备份；没有从 IRI 后缀猜原生身份或扩大到任意孤立图。

77 个项目沿现有 `DELETE /api/projects/{id}` 删除，全部取得 HTTP 204，逐项 GET 回读 404。
平台项目删除本身不移除 Oxigraph 图及字符串归属的图登记，因此只对上述已备份图执行现有
RdfStore 图删除，再清理对应图 revision／state、旧本体 registry 和 current derived pointer。
历史运行文件、原生事件、检查点及报告原件保留。没有更改平台程序或新增清理框架。

88 个图名中 77 个原本有实际数据，其余为已经缺失或空的旧图；实际命名图从 **410→333**，
减少 77 个。其余原有图全部保留，没有对无法确认版本归属的历史／辅助图做全库清理。
平台项目 API 会级联移除其在线会话／批次记录；本次保留的是模型数据快照与历史运行目录
内的原件，不是整库备份。当前本体业务数据已经删除，恢复须依据保留快照另行准备获准
scope；本次没有演练恢复，不把冷备份称为已验证的原 SQL 执行身份恢复。

## 完成验证

删除后平台仅剩上述 38 个 v5 项目／39 个本体。实际逐项核对：

- 目标旧 Project、Ontology、图 registry、图 revision／state 和 current derived pointer 均为 0。
- 39 个 v5 本体的 revision、原模型 content_hash、图 IRI、引用范围及实际 RDF 内容哈希均未变化。
- Demo Project `40841ac8-1c93-4cb1-85ba-1a9e8fb7928b`、Ontology
  `755f1e0e-cf5d-47f2-a2a3-95220f4cba96` 保留 revision 4，九条 CQ 的完整记录逐字段一致。
- 前后端实际 HTTP 健康检查均为 200。所有本轮临时管理员凭据均已撤销。

实际删除／验证窗口为 2026-11-01 06:02:59.512—06:03:11.596 UTC，约 12.08 秒；
不包含此前范围识别与备份时间，不冒充完整宿主有效工时。没有调用建模 LLM、追加预算、
修改 backend／frontend 或重启服务，也不产生新的建模质量 PASS。

主要原件：cleanup-plan-backed-up.json、deletion-events.jsonl、cleanup-result.json、
verification-final.json。工作树既有无关文档改动保持，未清理旧运行目录或覆盖历史结论。
