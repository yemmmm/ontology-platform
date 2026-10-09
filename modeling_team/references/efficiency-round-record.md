# R4.3 同轮效率记录

本文件供 Host 私有 Delivery 使用，不能作为生产建模输入或额外启动许可。
真实运行仍按当前授权／暂停状态。复用本轮已有记录，不另建逐工具计时平台。

原生 Delivery 没有 shell。技术 Host 将下面 `begin_round` 的三个参数写入 session 配置
`efficiency_round`；DeliverySession 创建一次 `efficiency-round.json`，resume 校验并保留
原起点。原生 Delivery 用 `record_efficiency_progress` 追加 intervals、counts、题池冻结
身份 question_set 及已核对 completion，通过 `read_delivery_artifact` 读本会话记录。
没有该 Host 配置时返回可操作反馈，不自动假定输入已就绪或重置计时。
下面 Python／CLI 仅供技术 Host 操作同格式的既有本地记录，不授予 Delivery shell。

获准资料就绪且收到开始执行指令时，**在准备／资料分析之前**创建一个本地记录：

```python
from pathlib import Path
from modeling_team.efficiency import begin_round

begin_round(Path("workspaces/<authorized-round>/efficiency-round.json"),
    started_at="<真实输入就绪且收到执行指令的带时区时间>",
    start_reference="<已有用户执行授权及输入就绪证据引用>",
    identity={
        "materials_digest": "<资料版本、获准访谈及摘要>",
        "question_set": "<审核冻结题集版本/摘要与公开17隐藏10身份>",
        "scope": "<industrial-service-v3 同等完整范围>",
        "model_effort": "<各角色模型、effort>",
        "configuration": "<Task/Profile/配置身份>",
        "code_commit": "<代码commit及必要dirty diff身份>",
    })
```

题池尚未冻结时在 identity.question_set 写已审核版本及“待冻结”，冻结后补充真实摘要；
不因此延迟计时或准备一轮全面预检。文件已存在时 `begin_round` 拒绝覆盖：修模、重验、
同轮 fresh start 均追加 `run_ids` 并保留起点。配置改变另建对照记录，不混算收益。

在同一 JSON 补充 `intervals`。每个区间包含 category、started_at、ended_at、
evidence_reference，带显式时区；有证据阻断关键路径的平台合同或基础设施故障才设
`blocks_critical_path: true`。正常模型推理、工具读取、调度、输入纠错与质量返工不归入
故障扣除；人工答复等待以 human-wait 单列，保留在总墙钟中。区间未知时缺省结束或
依据，工具保留未知；分类可重叠，各自按并集计算，不相加冒充总量或有效 Agent 时间。

复用已有记录填写语义分析与修订、独立 Consumer、Judge、等待、故障修复／测试、
审核／文档及收尾的时间窗口。`active_work_seconds` 缺省为未知；估算须另附口径。
`counts` 可记录原生 turn、提交批次、dry-run 重复原因、角色往返、输入字节和观察／唤醒
次数；没有证据的字段保持未知，不根据进程寿命猜有效工作量。

只有当前同轮完整独立验收及必要收尾已由 Delivery 核对，才能补充 completion：

```json
{
  "independent_full_pass": true,
  "acceptance_references": ["<完整公开题独立报告引用/摘要>", "<完整隐藏题独立报告引用/摘要>"],
  "cleanup_reference": "<该轮必要收尾实际回执引用/摘要>",
  "completed_at": "<最后完成事实的真实带时区时间>"
}
```

逐项核对：同一冻结完整分母、原评分、实际 Consumer 读取、Judge 全题 PASS、稳定绑定及
实际清理；不能只看 exit、报告落盘或 full_pass 字段，也不能缩小题池或复用旧模型。
工具只计算已记录窗口，不验证原文或裁决，不构成性能验收器。

```sh
PYTHONPATH=. backend/.venv/bin/python -m modeling_team.efficiency workspaces/<authorized-round>/efficiency-round.json
```

报告同时保留总墙钟、故障并集、扣除后的估算及未知。声明 ≤120 分钟实测还需要当前完整
独立 PASS、收尾和无平台故障的真实证据；扣除故障的估算不能当无故障实测。60 分钟仅为
后续产品目标，预算不自动停止、降低评分或通过运行。
