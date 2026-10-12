# R4.0-001 独立召回反馈交付记录

权威范围：[需求](../../requirements/requirements-v4.0.md#r40-001-基于真实使用反馈的本体持续改进)
及[设计](../designs/2026-10-12-r4-0-001-semantic-feedback-design.md)。本轮用户授权按设计实现并测试；
基线 382968c。未新增真实建模次数，未运行 A10。

## 实现

- PostgreSQL 单表 semantic_feedback，迁移 0036；原始 query／说明／旧快照保留，
  主体和时间由服务器绑定，同次 ID 重试幂等，处理历史追加，时间／ID 稳定分页。
- 独立 REST／MCP submit/list/get/resolution 共用服务；提交 read，内部 admin + 项目归属。
  快照为私有客户端报告，不能用于受保护资源探测；闭门/Team 停止不妨碍操作记录保存，
  现有模型写门不变。超限/参数拒绝可修正，存储错误有重试反馈。
- 召回页空结果也可反馈；冻结每页实际请求/响应和修订，草稿隔离，同 ID 同正文未知重试，
  400/413/422 明确拒绝后保留草稿允许修改；提示仅“反馈已保存”。
- 029 默认按 Host 显式选择 feedback_ids 读取持久记录，只投影获准的查询、观察与限制声明，
  不向生产转交私有快照/处理历史；仍沿原增量授权与 Runner，不自动启动。
- 已解决/无需改动必须附范围、当前修订和实际复核引用；已解决另需独立验证引用。
  接口校验结构、归属和修订，引用内容真实性及业务语义仍由实际复核/独立验证证明。
- REST/MCP 接口文档及实际生成目录同步；未新增管理 Tab、队列、调度器或模型写能力。

## 验证与归因

独立功能证据见[唯一验收文档](../tests/2026-10-12-r4-0-001-independent-functional-acceptance.md)。
独立测试发现并推动修复 received_at 双端格式差异及可选快照默认引发的跨端幂等冲突；
网页还补齐明确拒绝后可编辑重交。旧失败轮次保留，不以成功覆盖。

初次 `cd backend && uv run pytest` 读取本机 `.env` 中启用的外部 JEV 排序，固定排序的
既有召回测试失败且发起外部排序请求。以未改代码 HEAD worktree 和相同 `.env` 重现
`test_context_only_cursor_restores_second_match_page_and_next_match` 失败；关闭仅测试进程的
`SEMANTIC_JEV_ENABLED=false` 后同基线用例 PASS。未改服务配置或召回代码。初轮中还发现
新工具缺少目录 category/source 映射，已补齐并同步文档；最终回归使用受控测试配置。

GitNexus 的 required_scope 定点影响为 LOW（3 个符号）。提交前 detect_changes 报 CRITICAL
（262 流程），但含将 models.py 文件末尾新增表映射到旧 migration_run 的偏移及已退役流程；
029 prepare_incremental 不在索引中。已向用户告知，采用实际 diff/局部调用点及回归补证，
不宣称该旧图提供完整影响覆盖。

最终开发回归：

| 检查 | 当前结果 |
| --- | --- |
| `cd backend && SEMANTIC_JEV_ENABLED=false uv run pytest` | 1079 passed，56 skipped，276.74s；其中 JEV 专用测试显式配置并自行验证，不靠禁用略过 |
| `cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests/test_r4029_incremental.py ../modeling_team/tests/test_r4029_independent_acceptance.py -q` | 48 passed |
| `cd frontend && npm run build` | PASS |
| `cd frontend && npx playwright test` | 52 passed，含 7 条反馈浏览器用例；反馈 UI 使用真实 Chrome + HTTP fixture |
| 独立后端反馈与既有候选写门回归 | 21 个反馈测试 + 6 个写门测试 PASS |
| 独立重跑反馈浏览器用例 | 7 passed |
| changed Python Ruff／文档生成 `--write` 后 `--check`／新增改动本地链接／diff | PASS |
| `uv run alembic upgrade head`／`alembic current` | PostgreSQL 0036_semantic_feedback (head) |
| user systemd 统一重启／健康检查 | active；8001/api/health 200、5173/ 200 |

新增/改动本地链接检查 PASS。扩大扫描整个 v4.0 历史文档时发现 FactAuditPage.tsx、
GraphGovernancePage.tsx、BuildContextDebugPage.tsx 三处已退役页面链接；在基线 HEAD 中
也不存在对应文件，未在本次需求中修改历史引用或扩大修复范围。

56 skipped 为既有可选环境用例，不视为其实际集成验证。真实 PostgreSQL 与外部 MCP
transport 的反馈合同由独立测试方在同一验收文档 Round 7–8 记录；最终 Round 8 PASS（exit 0）。
真实 REST read 提交及 MCP stdio（ClientSession + app.mcp.server，read/admin Key）重试原回执、
内部权限/追加历史/列表，独立 PostgreSQL Session 原话与 raw query/主体/单记录/历史读回、
029 私有快照/历史不外流均通过；无 BuildSession 或语义启动。仅本次测试项目/反馈已删除，
read/admin/adapter 临时凭据均撤销，独立 DB 确认无活动临时 Key 或测试项目残留。

功能交付及独立功能验证 PASS；A10 真实改进与独立语义验收未授权/未执行，整体 PARTIAL。
功能测试和处理记录不证明真实模型改善，不改旧 Judge 报告或隐藏题集。
