# LangGraph 并行协作与恢复实验

这是 [v5 两项风险验证](../../docs/delivery/test-docs/2026-10-27-v5-langgraph-risk-validation.md)
的可复跑实验，使用真实 LangGraph 和确定性 Agent 替身，不是生产 Team 实现。

依赖独立于后端／前端。已测试 Python 3.12.3、LangGraph 1.2.18、
`langgraph-checkpoint` 4.3.1、`langgraph-checkpoint-sqlite` 3.1.2。
`requirements.txt` 固定本次实际安装的依赖版本。

在仓库根目录执行：

```bash
uv venv workspaces/v5-langgraph-risk-validation/.venv --python 3.12
uv pip install --python workspaces/v5-langgraph-risk-validation/.venv/bin/python -r scripts/v5_langgraph_risks/requirements.txt
export LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false
probe_python=workspaces/v5-langgraph-risk-validation/.venv/bin/python
probe_run=$(mktemp -d workspaces/v5-langgraph-risk-validation/manual-XXXXXX)
"$probe_python" scripts/v5_langgraph_risks/parallel_probe.py --output-dir "$probe_run/parallel"
"$probe_python" scripts/v5_langgraph_risks/recovery_probe.py run --output-dir "$probe_run/recovery"
"$probe_python" -m pytest -q scripts/v5_langgraph_risks --basetemp "$probe_run/pytest"
```

恢复实验需要支持 `SIGKILL` 的系统，本次在 Linux 上执行。它只终止自己启动的实验子进程，
只写入指定输出目录中的 SQLite 数据库和事件文件。每次使用新目录以保留原证据。

`parallel_probe.py` 测动态分派、同图等待边界、独立运行与实际成果交换；
`recovery_probe.py` 测提交与 checkpoint 之间进程退出、同身份对账及未知结果。
负对照以“准确观察到限制或重复效果”为测试通过，不能把它读成生产行为通过。

LangGraph 提供节点执行、分派、条件路由、中断和 checkpoint。跨独立运行的启动／唤醒、
业务消息适用范围、共享内容以及外部写入的幂等／对账由实验应用代码提供。
SQLite 应用账本不代表已接入 OntoWeave 的实际 application API；
本轮也不证明真实模型协作质量、PostgreSQL 部署、完整 v5 交付或成本收益。

测试记录包含每轮结论、原始证据目录和独立检查结果。无需重启本地应用服务。
