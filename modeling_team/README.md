# Modeling Team Host 工具

## 整轮用量与账单对账（Host离线）

R4.3-019提供 `python -m modeling_team.usage_report --scope <scope.json> --output-dir <新目录>`，
读取显式绑定原件，输出数值JSON及Markdown。覆盖Delivery、生产／验收、恢复／修模及
辅助模型缺口；响应去重、线程累计不重复相加，unknown不补零，任务与账单窗口分开。
使用方式、scope／价格／时间合同和最小采集位置见
[Host用量报告](references/model-usage-report.md)。工程测试不等于真实账单或语义质量验收；
报告不进入生产模型或独立盲测输入，不改变建模授权。
收尾将Consumer的`batch_report`快照和实际绑定线程的最终`rollout`一并列入scope，
输出独立终态用量差异；同线程不重复相加，缺原件保留partial，原语义报告不修改。
