# 宿主待办优先与三分钟巡检兜底

用户要求：“能否做到有消息需要host处理时进行唤醒，没有消息时3分钟（从5分钟改为3分钟）检查一次？”
本次沿[R4.3-029](../../requirements/requirements-v4.3.md#r4-3-029)私有Host交接和
[R4.3-030](../../requirements/requirements-v4.3.md#r4-3-030)按需决策范围实施窄调整。

## 当前行为

- 新增只在当前Host工具调用内运行的`python -m modeling_team.host_wait --session-root <当前私有session目录>`。
  默认180秒等待；已有或新到的CQ审核、平台修复请求及blocked／failed结果提前返回。
  程序约每秒检查本session的journal文件变化，复用`host_action_state`判断实际待办。
- 返回值仅含请求身份、原因、限制和耗时，不输出私有审核／报告正文，不确认、删除或处理请求。
  普通日志、心跳及已完成请求不触发模型，也不重置巡检期限；原件不完整则明确返回观察缺口。
- 无待办180秒到期后，Host读取一次当前角色卡片；已有明确处理者的请求可显式忽略重复提醒，
  不改变原请求状态。等待工具的输出分片不代表巡检到期，应继续同一等待进程。
- `modeling-dev-loop`入口、UI提示和runbook均将默认周期从5分钟改为3分钟。
  原手动run无独立session时保留3分钟卡片兜底；已有真实通知立即处理。

这不是唤醒已结束Codex任务的后台服务。Host必须仍在承载等待工具调用；监督结束后不会自动
重开会话、接管旧run或启动建模。Delivery／Runner、授权、写入、审核及独立验收责任不变。

## 检查与证据边界

- `env -u DEEPSEEK_API_KEY PYTHONPATH=. backend/.venv/bin/python -m pytest modeling_team/tests/test_host_wait.py modeling_team/tests/test_delivery_host_actions.py modeling_team/tests/test_r4329_independent.py -q`
  ：**26 passed**。覆盖等待中新请求、默认180秒、普通事件不唤醒、不重置到期、已完成／受阻请求、
  重复提醒抑制、journal不完整、非法期限及真实CLI调用／错误返回；同时复用原私有交接回归。
- Ruff check／format、skill validator及diff格式检查通过。
- 对已完成的本轮真实session执行`--timeout 0`，返回`periodic_check`，没有新待办，原run不动。
- 新代码仅为独立Host等待入口和对应测试，原`host_action_state`及生产调用点未改；按调用点检查，
  不改变原Delivery／Runner的执行路径。无需重启产品服务。
- 工程检查不证明已接入某个结束会话的后台唤醒，也不证明下一轮端到端响应或成本收益。
  本次未启动真实建模／重验，不消耗剩余2轮；实际监督响应效果待下一次用户授权运行取证。
