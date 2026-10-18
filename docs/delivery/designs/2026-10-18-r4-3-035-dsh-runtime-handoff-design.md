# R4.3-035 DSH运行期产物与公开输入交接设计

权威范围：[R4.3-035](../../requirements/requirements-v4.3.md#r4-3-035)。本次授权细化、
审阅、开发及工程测试；不启动真实建模、修模或语义验收。复用031/032隔离、013原件
交接、029 Host CQ审核；不增加工具、Endpoint、角色、shell或任意文件权限。

## 核对与决定

当前Coordinator的write_handoff_output仅写私有目录，Runner消费run/scenario-map；
公开CQ写入public目录，但DSH只有静态read_role_material。现有Team Transport已经支持
write/publish/list/read_handoff_material，RuntimeDelivery支持material_refs，DSH原生事件
已经区分queued、claimed、settled、canceled、unknown。这些接口直接复用。

| 决策 | 最小实现及边界 |
| --- | --- |
| D1 | 仅DSH Runner使用HandoffMaterials的窄子类；Coordinator写scenario-map/下三个既有合同文件时，自动快照并将原字节接入Runner既有路径。其他角色不能写这些目标；其他私有输出保持原行为 |
| D2 | 接收回执含run、actor、源路径、不可变material版本、SHA256、目标和received；已接收同版重试核对目标，不重复覆盖；新内容为新版本。历史已用摘要迟到返回可恢复stale及原/当前身份，不回退目标；原件缺失/损坏保留现场，以同内容替代快照关联旧版本，目标不重复写。原件及尝试保留于既有handoff包和evidence目录 |
| D3 | Runner完成Host审核后原projection写入接点为公开生产角色发布固定handoff包；通知带run、投影文件版本、摘要、material_ref，正文不重抄CQ。freeze只发送已成功冻结的batch_id及snapshot_digest，不发送私有快照或隐藏题数量/内容 |
| D4 | 通知通过现有DSH消息通道发送；稳定delivery_id关联原native message/dispatch。重试先查原身份：queued/claimed/settled不重送，unknown等待原响应核对；明确未送达或canceled可重试。原事件区分领取与业务完成；材料可读不代表已读 |
| D5 | 公开输入发布/发送失败保留准确可恢复证据，由Runner后续drain重试未送事项。暂停/Provider等待期间保留待交接；不杀run，不重复已证效果；未知状态不自动重投。晚到旧版本保留原版本身份，不能伪称最新 |
| D6 | 继续由既有地图/拓扑、授权和application合同检查正文；转存不解析或改写业务语义。冻结只从Runner真实freeze状态产生，Delivery没有审核权限。无额外平台防御门 |

## 改动与影响

新增modeling_team/runtime_handoff.py承载DSH专用接线；Runner只替换DSH材料存储并接入
projection发布与drain重试。DSH适配器仅对cq-public-input保留稳定交接ID及去重，更新实际
加载提示。Codex、CQ私有工具、公开投影内容生成及application行为不变。
GitNexus对DshRuntimeAdapter返回Target not found/UNKNOWN；改用Runner材料初始化、
CQ写入/freeze、drain、Transport材料调用和DSH派发/晚到响应定向调用检查。

## 验证与完成界限

工程测试覆盖真实固定DSH+bwrap+离线Messages服务：Coordinator原工具写入、Runner原路径
及摘要、版本更新；公开投影原件读取及freeze通知、无隐藏泄露；跨角色/路径/run绑定、
缺原件/损坏/目标失败修正、回执丢失、queued与claimed分离、unknown/迟到/取消和重试。
运行modeling_team全量回归、相关静态检查、文档链接和diff检查。只改modeling_team及
文档，不改backend/frontend服务代码，因此不要求产品服务重启。

A1—A3仅报告本次工程覆盖；A4真实DSH Delivery四题完整交付、application、独立L1及
净降耗仍待届时授权，不能用离线fixture或设计审阅PASS替代。
