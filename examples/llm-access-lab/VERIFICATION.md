# 开发验证记录

日期：2026-10-31。本记录证明测试项目的程序行为，不是 OntoWeave 的模型质量验收。

## 实际结果

- 独立环境：uv sync --extra test 成功，生成并保留 uv.lock；Python 3.14.3，FastAPI 0.137.1，Uvicorn 0.49.0，pytest 9.1.0，httpx 0.28.1。
- 最终测试：uv run --locked --extra test pytest -q --tb=short，**26 passed，1 warning，2.76 秒**。
- 静态检查：仓库现有 Ruff 0.15.17 对本项目执行 format 和 check，通过。
- GitNexus staged 检查为 low，识别 10 个变更文件、0 个已索引符号；新增示例未获得图上的调用覆盖。另按路径和 diff 确认变更只涉及独立示例及两份调研记录，没有修改平台调用关系。
- 真实 HTTP：测试启动实际 app.py 子进程，在本机动态端口执行健康、API 文档、模型登记、凭证签发、新调用扣额、同请求回放、额度耗尽拒绝及成功记录读取；测试结束后停止子进程。没有保留后台服务。
- 持久化与并发：使用真实 SQLite 文件，重建应用仍能回放；并发新请求只能成功一次；并发相同请求只扣一次额度。

唯一提醒来自 Starlette TestClient：Using httpx with starlette.testclient is deprecated; install httpx2 instead。没有屏蔽提醒，也没有为了测试项目修改平台依赖；实际 CLI／HTTP 用例使用真实 httpx 客户端。

## 开发迭代保留

1. 先编写 24 项业务行为用例，对只有空 FastAPI 的骨架执行，24 项均因模型管理等功能缺失而失败；随后实现，24 项通过。
2. 补充提示文本空格保持用例，实际发现公共输入配置自动去空格，使不同内容错误回放，得到 200 而非 409；移除自动裁剪并明确业务说明后通过。
3. 加入实际 CLI／HTTP 闭环，最终在项目独立环境运行全部 26 项，通过。

## 证据边界

- 本项目核心实现为 265 行 Python、四张业务表，包含模型状态、凭证授权、次数额度、成功记录及请求回放。运行数据和虚拟环境不进入 Git。
- 开发者编写业务材料、程序及以上测试，未进行独立工程验收或独立模型语义验收。
- 没有启动新 semantic modeling，没有创建平台模型或调用真实 LLM；不宣称净降耗、客户真值、真实开源业务一致性或上游模型生成质量。
- 未修改 backend/、frontend/ 或平台共享运行配置，无须重启 ontology-platform.service。
- Python 3.14.3 已实际验证，其他 Python 版本未实测。
