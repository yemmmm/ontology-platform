# R4.0-006 主体与角色语义访问交付记录

## 范围与状态

用户授权按[设计](../designs/2026-10-01-r4-0-006-subject-role-semantic-access-design.md)
完成开发和测试，权威范围为[需求](../../requirements/requirements-v4.0.md#r40-006-业务角色与主体语义访问控制)
F1—F6／A1—A10；D1／D2 沿用，不重新审批。
实施基线 `a108a18688d68225d3a7a3eb71202eafa362c73d`，初始工作区 clean。
功能实现及验证完成；A1—A10 独立功能 PASS，含真实依赖运行证据；独立验收见[测试记录](../tests/2026-10-01-r4-0-006-subject-semantic-access-test-record.md)。
A11 未授权、未执行；整体 PARTIAL，不把功能 fixture 或真实依赖运行当建模质量。

## 实现

- 扩展 users 为稳定主体（普通用户 Key-only、管理员标志、停用），Key 记录 user_id 和明确服务端
  bootstrap 标记；迁移 0033 添加项目成员、权限角色与分配，复合同项目外键，删除 Key 直接 Grant。
- Org Admin HTTP 管用户和成员，Project Admin 只读本项目最小成员身份、维护角色与分配／Key。
  参数封闭、名称冲突 409；角色集合单事务校验后替换。Project Admin 对不可见或不存在的
  user_id 均收到同一 404，不能借 Key 创建错误探测全局目录。
- HTTP／MCP 共用逐调用 principal_from_key；有归属组织 admin Key 先校验用户启用及管理员
  资格，项目 Key 再查成员与角色并集。用户／Grant 依赖故障为可重试 dependency_error，空角色
  是有效空权限。scope 与 Grant 分开，旧 semantic_grants 明确 422，归属不可转移。
- 权限角色可显式关联同项目声明 business_role 的语义资源，控制面读回映射缺口；授权计算不读
  RDF，不把主体、角色分配或 Grant 加入语义图。Context cursor 加入当前用户／scope／Grant 摘要。
- 移除成员同事务撤销其项目 Key、清分配；角色／项目删除保持级联与跨项目隔离。
  fork 不复制主体链；独立验收发现 Grant 碰巧等于保护集 ID 时被通用 remap 改写，已窄修复为
  原样复制 allowed_grants，保留平台身份／图 IRI 的原重映射路径。

## 验证与发现

- 原有认证、Key、授权、语义受治理 HTTP／MCP 回归：50 passed。
- 新主体专项开发边界：11 passed，覆盖多 Key／scope、Grant 精确字符串、原子替换、cursor
  等价权限、配置损坏与依赖恢复、复合外键／删除级联、业务角色关联、目录不可区分错误。
- 第一轮全量默认命令收集失败：4 个 v4 模块无法导入 modeling_team；使用仓库根目录
  `PYTHONPATH=..` 重跑。后续全量 1059 passed／38 skipped／3 failed 均为接口清单尚未同步，
  同步后轮次在旧模块已加载期间遇 fork 缺陷（1073 passed／38 skipped／1 failed）；保留失败证据。
- fork 修复与主体／独立测试／checkpoint 定向回归：28 passed；独立方另行记录各轮及处置。
- GitNexus create_api_key impact：CRITICAL（109 affected，2 个直接依赖），变更前已告知用户；
  detect_changes：critical（50 changed symbols／267 affected；初检 17 tracked files，
  最终 staged 检查覆盖 27 文件）。索引未识别
  resolve_api_key 和 fork，且含同名字段误归属；结果仅作为提示，不声称完整图覆盖。
  补充直接调用点、API policy、HTTP/MCP 共享路径、cursor、checkpoint fork 与 diff 检查。
- 实现未修改前端，无新增 UI；不需要 frontend build／Playwright。

## 兼容边界与交接

- 0033 只把迁移前的管理员 users 明确标记为管理员；不自动推断历史 Key 归属，不迁移直接 Grant。
  历史无归属 Key 不继续授权（仅服务器明确登记的 bootstrap 例外）；管理员登录继续可用，
  有归属 Key 由管理员按成员与 scope 明确重新发行。
- 管理 API 现在必须 user_id；当前 Team 旧 Key payload 尚未适配。既有建模流程接入归
  R4.0-007，不在本条新增自动创建用户或权限资源生命周期；本轮无 semantic start。
- downgrade 不恢复已删除的直接 Grant；Key-only 用户无 password_hash 时需显式处置才能降级，
  不生成占位密码。未对业务系统／外部数据执行权限做扩展。
- 所有需求文件纳入本次独立提交；最终 commit hash 通过交付消息与 git log 核验，不把暂存当提交。

## 最终验证闭合

- 最终后端全量：`cd backend && env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q`，
  **1075 passed／39 skipped**（141.21s）。skip 包含未开启的 opt-in live 用例；本需求 live
  随后单独执行，不把 skip 当 PASS。最终产品代码未再改变，测试 cleanup 变化由独立 live 复核。
- 独立 A1—A10：PASS，隔离／相邻回归 32 passed，补目录反例 1 passed；真实 HTTP／PG／Oxigraph
  与持续实际 stdio MCP 1 passed（4.33s），补齐清理后 1 passed（5.19s）。F006-01 FIXED。
  精确读取与 RDF 导出含真实引擎证据；其他过滤面复用既有授权 fixture，fork 为隔离功能证据。
- `cd backend && uv run alembic upgrade head`：真实 PostgreSQL 从 0032 升级 0033 成功；
  `alembic current` 为 `0033_subject_semantic_roles (head)`。复核项目成员／角色分配的两个复合外键，
  角色同项目名称／id 唯一约束及旧直接 Grant 列不存在。
- 初次 `systemctl --user restart ontology-platform.service` 报 `Failed to connect to bus: No medium found`；
  当前 shell 缺少用户 bus 环境，确认 UID 1000 的已有 bus 后，使用
  `env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user restart ontology-platform.service`
  成功。unit 在 2026-10-01 21:10:50 +08:00 起 active；启动就绪后 status 与
  `curl --fail http://127.0.0.1:8001/api/health`／`curl --fail http://127.0.0.1:5173/` 均成功。
  start-local 自带 frontend build 通过；无 UI 修改，不额外跑 UI suite。
- 真实用例仅创建测试主体／项目／保护集／角色／图；独立方按确切身份清理用户、Key、Project、
  graph set／registry／state／revision 和 RDF graph，断言无残留；必要审计与失败证据保留。
- Ruff、接口清单 `scripts/sync-interface-docs.py --check`、本地链接／围栏与 diff 检查 PASS。
- 并行 `71d0be3` 只更新 007 设计／需求审阅记录；保留其内容，不纳入 006 修改，不影响已验证
  产品输入。需求文档只修改 006 状态及其条目。
- A11／L1 未授权、未执行；本轮 semantic starts 为 0，整体 PARTIAL。
