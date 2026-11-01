# v5 单一完整模型保留与测试项目清理

日期：2026-11-01。状态：已完成。平台现仅保留 Demo 一个项目、一个本体；
本次删除 37 个测试项目、38 个本体及其 38 张模型图，保留模型及九条 CQ 完整记录不变。

用户授权寻找一个最完整的模型，删除其余测试项目。综合当前业务来源覆盖、实际资源、
表／连接映射、独立验收、已有模型续建和 CQ 接续证据，选定保留当前 Demo：

- Project：`40841ac8-1c93-4cb1-85ba-1a9e8fb7928b`，名称
  `R2.3 team v5-llm-access-lab-20261031-start3`。
- Ontology：`755f1e0e-cf5d-47f2-a2a3-95220f4cba96`，revision 4。
- 14 个实际资源：4 个 Class、3 个关系类型、4 个表映射、3 个连接映射；项目有九条 CQ。
- 原冻结业务源的 v2 续建独立 30/30 PASS；九条新增 CQ 能力核对为 PARTIAL，仍保留 draft
  标准、显式未知和缺少事件来源的边界，不升级为所有问数能力通过。

“最完整”按现有交付链和已确认范围选择，不是跨业务领域的绝对质量排名。工业双切片也有
其冻结范围的独立 PASS；节点数量不作为完整性判断。本次不扩充或修改保留模型。

执行前平台 38 个项目、39 个本体均与上一轮调查身份一致，删除另外 37 个测试项目、38 个本体。
先保存平台 checkpoint-data 模型快照与确定归属 RDF 图，核实没有在途写入、有效 lease 或 fence；
再复用平台删除 API 和原有 RDF 存储删除能力，保存清单及回执。保留原工作空间、检查点、
失败／评价证据、Demo 独立应用及其外部业务数据库，不进行未知归属孤立图全库清理。

来源：[节点数量调查](2026-11-01-v5-model-size-investigation.md)、
[Demo v2 续建记录](2026-11-01-v5-demo-incremental-modeling.md)、
[九题 CQ 接续记录](2026-11-01-v5-demo-cq-live-validation.md)、当前平台元数据、
`backend/app/services/ontology_crud.py`、`backend/app/services/checkpoint_data.py`。
执行原件保存在 `workspaces/v5-single-model-retention-20261101/`。

## 备份和删除结果

操作前取得 37 份待删项目的 checkpoint-data 平台模型快照，逐份校验 snapshot digest 和文件
SHA256；另存 38 张模型图的原文、SHA256 与规范化 RDF 哈希。保留 Demo 也单独保存完整快照、
原模型哈希和九条 CQ 前态。备份合计 **1,840,513 字节（约 1.84 MB）**，位于：

`workspaces/v5-single-model-retention-20261101/backup/`

备份是模型数据和对应元数据，不含服务凭据／有效租约，不是整库备份；本次未演练恢复。
没有删除任何历史运行目录、原生事件、失败候选、检查点或独立评价报告，也未操作独立 Demo
应用的程序或外部业务数据库。已删项目的旧运行绑定不再是可原地续建的活动资源；若未来恢复，
须依据保留快照准备获准范围，不自动重新运行这些旧任务。

37 个项目中，35 个通过原 `DELETE /api/projects/{id}` 获得 HTTP 204；两个检查点来源项目
使用现有 Host 侧 `ontology_crud.delete_project` 服务删除。37 个项目随后均通过 GET 回读 404。
所有 38 张已备份且确定归属的图均删除，对应图 state／revision、旧本体 registry 和派生指针清除。
Oxigraph 有实际内容的命名图从 333 减为 295；其他原有图全部保留，未做未知归属图垃圾回收。

## 归档限制与接续

第一次删除成功 13 个项目后，在 `v5-continuous-20261029-start1` 收到 HTTP 409：
`checkpoint_source_archived`。另一份 `v5-fork-continuation-20261030-source` 同样处于来源归档状态。
两者均属于本次明确授权删除的测试资源，且没有活动 Project Key、写入 fence、有效 lease 或
在途 apply。失败及已完成进度单独保留，没有重复删除已成功的项目。

T0 复核结论：普通写入的来源不可变限制仍有必要，不能全局删除或放宽；本次用户明确要求
删除这些已备份测试项目，因此只对这两个真实 ID 调用已有 Host 删除服务。服务仍执行原有
Project 锁、映射删除及 fence 检查。未先撤销归档标志，未更改归档守卫／API 或新增平台机制。
来源归档元数据与原快照均保留于备份和删除事件中。

第一次失败原件为 `cleanup-result-attempt1.json`、`deletion-events-attempt1.jsonl`、
`deletion-progress-attempt1.json`、`deletion-attempt1.log`；窄处理依据为
`archive-delete-t0-review.json`。最终结果为 `cleanup-result.json`，事件接续保存在
`deletion-events.jsonl`，未以最终成功覆盖首次失败。

## 最终核对

[公开汇总与逐项删除清单](../delivery/evidence/2026-11-01-v5-single-model-retention/summary.json)
保存选择依据、实际删除方式及完成检查。原始最终核对为 `verification-final.json`。

- PostgreSQL 仅剩上述 Demo Project 和 Ontology，各 1 行。
- 37 个目标 Project、38 个目标 Ontology 以及其图 state／revision、registry 和派生指针均为 0。
- 38 张目标实际模型图均不存在；其他原有命名图保留。
- Demo 保持 revision 4，实际 RDF 内容哈希为
  `84f8c969ae75542c4f722eba1ecbb6ea72145451f52c61969b64ec3d7f587c42`，与删除前完全一致。
- Demo workspace ready；实际 resource-list 为 14 个资源，resource-relations 为 13 条声明／引用记录，
  均 complete 且同 revision 4。这是接口记录数，不是画布边数或新增验收结论。
- 九条 CQ 的完整记录逐字段与删除前一致，既有 draft／PARTIAL 边界保留。
- 保留 Project、本体列表、workspace、资源、关系、CQ、后端健康接口均 HTTP 200；前端 HTTP 200。
- 备份、首次删除、接续删除和最终核对四次使用的临时管理凭据全部撤销。

删除窗口为 2026-11-01 13:16:08.923—13:17:26.061 UTC，其中包含首次归档拒绝后的定位与接续，
不是纯执行耗时或完整宿主工时。未调用建模 LLM、启动／恢复建模、修改预算或前后端程序，
无服务重启；本次核对不产生新一轮独立语义 PASS。当前留下的 30/30 结论仍只适用于其
原冻结业务来源和 revision 4。
