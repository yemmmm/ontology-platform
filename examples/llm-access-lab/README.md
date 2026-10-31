# 模型访问与额度管理测试系统

一个用于 OntoWeave 建模试验的独立小项目：两个业务切片、一个 Python 服务、一个 SQLite 文件、四张业务表。调用结果由本地确定性生成器返回，不需要供应商账号或真实模型调用。

业务规则见 [business.md](business.md)。本项目是构造的可运行参考系统，不能作为独立开源业务或客户业务真值。

## 运行

从仓库根目录进入示例：

```bash
cd examples/llm-access-lab
uv sync
uv run python app.py --port 8787
```

启动后访问 http://127.0.0.1:8787/docs 操作交互 API，http://127.0.0.1:8787/openapi.json 获取合同。
端口由操作者指定；若已有服务使用该端口，改用其他端口。默认数据库为当前目录的 data/lab.sqlite。
可以用 --db data/another.sqlite 创建另一套独立试验数据；停止后使用同一文件重启会保留数据。
服务只监听本机；管理 API 无登录，供试验操作者准备和检查数据，调用凭证只保护 /calls。

最小调用例子，在另一个终端执行：

```bash
curl -s http://127.0.0.1:8787/admin/models \
  -H 'Content-Type: application/json' \
  -d '{"id":"flash","name":"快速模型","enabled":true}'

curl -s http://127.0.0.1:8787/admin/keys \
  -H 'Content-Type: application/json' \
  -d '{"name":"测试应用","allowed_models":["flash"],"quota":2}'

# 将下面的占位符替换为签发结果中的 token。
curl -s http://127.0.0.1:8787/calls \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <签发的token>' \
  -d '{"request_id":"demo-1","model_id":"flash","prompt":"你好"}'
```

相同调用再提交一次会返回同一 call_id、replayed=true、charged_units=0。
修改请求标识才是新调用；同一请求标识改提示文本或模型会返回冲突。

## 接口与数据

| 接口 | 操作 |
| --- | --- |
| GET /health | 健康状态 |
| POST /admin/models | 登记模型 |
| GET /admin/models | 查看模型及状态 |
| PATCH /admin/models/{model_id} | 启用或停用模型 |
| POST /admin/keys | 签发凭证；原文只在此次响应出现 |
| GET /admin/keys、GET /admin/keys/{key_id} | 查看授权与剩余额度，不返回凭证原文 |
| PATCH /admin/keys/{key_id} | 启用或停用凭证 |
| POST /calls | 提交新调用或回放成功结果 |
| GET /admin/calls | 查看成功调用记录 |

四张表是 models、api_keys、model_grants、calls，DDL 在 [app.py](app.py) 的初始化部分。
额度单位是“成功新调用次数”，不是 token 或金额。重试、拒绝与回放的规则以业务说明为准。

## 验证与建模输入

```bash
uv run --extra test pytest -q
```

[开发验证记录](VERIFICATION.md)区分程序行为通过和独立模型验收。本项目没有创建 Ontology，也没有启动新的 GLM 建模任务。

建议给建模 Agent 的首轮输入为 business.md、实际 OpenAPI 合同、四张表的 Schema 及获准样例数据。
tests/、VERIFICATION.md 及后续隐藏验收题不作为生产输入，避免把测试断言当作业务理解。
验收方可以独立操作该应用形成行为证据；最终语义验收仍须读取平台实际模型，不从本文件或程序补全模型遗漏。
业务行保留在本系统，不复制进 RDF 来凑问答答案。

本示例不接入或替代 OntoWeave 生产功能；不新增平台专用业务接口。开源候选比较见[调研记录](../../docs/research/2026-10-31-v5-llm-project-benchmark-selection.md)。
