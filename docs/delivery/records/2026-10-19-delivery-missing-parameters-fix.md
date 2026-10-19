# 2026-10-19 Delivery缺参数反馈窄修

用户最初要求删除DSH GLM用量采集并修复缺参数反馈，随后明确调整为“先修复缺参数反馈，
GLM用量问题手动卸载插件”。本次最终只交付缺参数反馈；已撤回本次临时GLM采集代码及
测试改动，保留它们修改前已有的工作区改动，不执行插件卸载或新的模型／验收请求。
归属R4.3-029／030／032既有工具反馈与减少无效往返，不新增需求或运行编排。

## 问题与修改

前次DSH GLM的start_evaluation四次漏必填mode，真实schema保留required字段，
但jsonschema.ValidationError落入兜底，仅返回delivery_tool_failed和笼统提示。
本次在Delivery共用工具参数校验处处理required错误，返回：

- code=delivery_arguments_missing，以及实际tool和完整missing_parameters清单；
- reason明确指出缺少字段，object定位参数所在路径；
- retryable=true，next_action要求按该工具schema补齐后重试。

例如漏mode时返回missing_parameters=["mode"]，不包含提交实例或私有handoff路径。
缺参数在Host操作调用及owner登记前返回；补齐后同一session可直接重试。既有授权、
运行绑定和参数校验继续执行，原yield与原件读取的其他错误合同不变。
修改位于共用DeliverySession，Codex与DSH工具桥均复用，不增加runtime分支。

GitNexus对_call_tool_raw／DeliverySession无符号结果，采用直接调用点检查；
两种runtime均将工具参数交给同一个call_tool，再原样返回结构化结果。本次没有
backend/frontend代码或共享运行配置变更，无需重启产品服务，不重载已保留的旧run。

## 验证

新增两种反例：仅漏mode，同时漏freeze_id和mode。先观察到原实现均返回
delivery_tool_failed而失败，再应用窄修；验证完整缺失清单、可恢复反馈、私有值
不出现在错误中、错误调用不登记owner，以及补齐后仅实际启动一次。

相关回归使用：

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
  ../modeling_team/tests/test_delivery_session.py \
  ../modeling_team/tests/test_delivery_decision_input.py \
  ../modeling_team/tests/test_delivery_token_reduction.py \
  ../modeling_team/tests/test_delivery_wakeups.py \
  ../modeling_team/tests/test_delivery_host_actions.py \
  ../modeling_team/tests/test_dsh_delivery.py -q --tb=short
```

结果：**231 passed，50.38秒**。其中DSH原生进程测试使用本地确定性Messages fixture，
没有外部模型调用。这证明工程错误反馈和相关合同，未证明真实Agent已自行修正、
实际token下降或新的独立语义验收；030净目标及032其他剩余范围保持原结论。
