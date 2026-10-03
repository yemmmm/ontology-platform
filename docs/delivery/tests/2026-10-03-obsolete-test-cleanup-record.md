# 过期测试清理记录

日期：2026-10-03。用户授权排查当前用例冗余并删除过期需求测试。

## 判定依据

权威范围为 [R4.0-012](../../requirements/requirements-v4.0.md#r40-012-证据追溯能力阶段性停用与多视角建模解耦)：专用 Evidence／lineage REST、MCP、补证能力和纯追溯采集已停用；本期不承担历史数据读写兼容。生产路由／工具注册与此一致。

仅删除验证已停用正向能力、历史兼容行为的测试；保留接口不可调用、证据字段拒绝、无追溯采集、共享 statement identity、受治理写入／检索、授权和恢复测试。测试文件版本编号、opt-in 跳过或名称含 evidence 均不单独构成删除依据。数据库／API 映射依据仍是有效业务内容。

## 清理范围

| 文件 | 删除测试函数数 | 原测试要求及处理 |
| --- | ---: | --- |
| backend/tests/test_evidence_references.py | 8 | 单独挂载停用路由，要求创建、解析、搜索和绑定 Evidence 成功；保留 canonical write 无 inline evidence 检查 |
| backend/tests/test_fact_evidence_repository.py | 7 | 专用事实证据绑定的创建、历史读取、覆盖率统计和删除；删除该测试文件，保留存储实现及当前恢复测试 |
| backend/tests/test_lineage_service.py | 5 | 独立追溯记录生命周期、证据上下文、历史兼容和专用 lineage 范围查询；保留共享身份及禁止自动采集检查 |
| backend/tests/test_r005_independent_acceptance.py | 1 | 历史追溯查询返回失效审计详情；保留命令停用和规则不采集检查 |
| backend/tests/test_evidence_rest_surface.py | 1 | 已排除的历史数据保留兼容；撤掉无关数据库种子，保留真实生产注册下的 404 检查 |
| backend/tests/test_semantic_access_authorization.py | 1 | 已停用 Evidence Reference 的列表／关联读取授权；保留普通资源、statement、quad 及身份授权检查 |
| backend/tests/test_semantic_stage4_e2e.py | 1 | 绕过公共 dispatcher 调用旧 evidence composer；保留公共入口拒绝 evidence field set 检查 |
| modeling_team/tests/test_staged_associate_evidence_forwarder.py | 11 | 停用工具的成功调用、参数镜像及专用转发分类；保留退役 capability 不触发子进程、不锁死 run、CLI 不绑定旧 forwarder 检查 |
| backend/tests/test_v1_full_chain_acceptance.py | 0 | 从混合用例移除 Evidence 提交字段及专用 REST／MCP 成功断言；保留正常写入、重试、恢复、部分应用和授权隔离 |

合计删除 **35 个测试函数**，另删混合用例中的过期字段／断言及失去用途的 fixture、helper、import。函数数量不等同于参数化后的 pytest case 数量。

## 冗余检查及保留项

- 对 backend、modeling_team、pi-modeling-agent 顶层 Python 测试函数做 AST 函数体完全相同扫描，没有发现可据此直接删除的重复函数；此检查不证明不存在语义重复。
- service／REST／MCP／前端、开发／独立验收层验证不同边界，不因覆盖同一需求就删除。
- Pi／Claude 历史运行路径没有明确退役依据，v2.2 明确不退役历史路径，保持其测试。
- 前端 Evidence 测试已经验证退役 URL／存储 tab 回到 Overview 且不发起追溯请求，继续保留。
- 历史需求、设计、测试记录及其中的旧路径属于当时交付记录，未改写。

## 验证

- 首次裸 `uv run pytest -q` 因 `ModuleNotFoundError: modeling_team` 在收集阶段失败；改用仓库既有 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest` 路径。
- 最终受影响后端模块、forwarder 与关联 staged capability 回归：**64 passed, 1 skipped**。跳过的是真实服务 opt-in 全链路测试，未改动 systemd 环境或运行真实建模。
- 变更模块的 Ruff F401／F821 检查及 `git diff --check`：通过。
- 最终 checkout 后端收集：1174 tests collected，0 收集错误；须使用上述 PYTHONPATH，裸 collect-only 同样缺少 modeling_team。
- 后端全量初轮回归：**1122 passed, 54 skipped**（293.03 秒）。该轮在首次删除 22 个函数后收集；运行期间又删除 Stage 4／Evidence 读取授权两项旧函数、修订 opt-in 混合用例和清理 Team forwarder。最终受影响范围由上述 64 passed／1 skipped 的定向复验覆盖，其余代码与用例复用全量初轮结果。未把初轮数量表述为最终 checkout 的全量 case 数量。

本轮仅变更测试及本记录，无产品代码变更，无服务重启、真实依赖 opt-in 验收或独立语义验收。语义验收尝试记录及其他并行任务的提交不属于本次清理，未修改或纳入本次提交。
