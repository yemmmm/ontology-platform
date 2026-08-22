# 业务术语（初始、待访谈）

以下解释保持简短，只用于启动业务访谈。括号中的来源列是发现线索，不是最终语义定义。

| 术语 | 初始解释 | 发现线索 |
| --- | --- | --- |
| 客户 | 接受设备服务的组织 | `customers` |
| 现场 | 客户设备安装地点 | `service_sites` |
| 资产 | 现场内可被服务的已安装设备 | `assets` |
| 故障事件 | 客户或服务方记录的一次设备问题 | `incidents` |
| 服务工单 | 为处理故障而执行的服务工作 | `work_orders` |
| 严重度 | 故障处理优先级 | `incidents.severity` |
| 服务合同 | 客户和服务方约定服务范围与期限的记录 | `service_contracts` |
| 覆盖 | 合同在一段时间内适用于某项资产 | `contract_assets` |
| SLA 目标 | 按服务策略和严重度约定的时间目标 | `sla_targets` |
| 延迟事件 | 工单执行中被记录的一段延迟及其原因 | `work_order_delay_events` |
| 备件申请 | 工单对某种备件的需求 | `part_requests` |
| 发运 | 仓库向申请分配并发送备件的记录 | `part_shipments` |
| 兼容性 | 备件与设备型号之间的适配关系 | `part_compatibilities` |
| 库存变动 | 仓库中备件数量的一次变化 | `inventory_movements` |
| 标准成本 | 备件主数据上的成本参考值；可见角色待确认 | `spare_parts.standard_cost` |

待确认词汇包括“有效合同”“SLA 达标”“解决”“一次修复”“重复故障”“备件短缺”“延迟原因未知”
和“服务绩效”。这些词不能仅由 Schema 或样例行决定。
