# R3.0-017 检查点数据快照与分叉恢复

本次用户已授权开始实现。原地 production/acceptance 接续保持兼容；新增显式 fork
选择，从指定检查点的数据创建新 Project、新 Ontology 和新 Graph Set。

## 实现边界

- 保存的是恢复绑定项目的平台数据，包括 PostgreSQL 的业务元数据、证据、映射、规则、
  保护集，以及 Ontology 所属 RDF 图；不复制外部业务数据库、凭据、活跃租约或在途写入。
- 数据与检查点文件一起在 host-private 发布并校验摘要；不能用恢复时的当前数据库
  冒充保存时的数据。旧检查点没有快照时明确不支持 fork，不能自动补历史快照。
- 保存复用当前 run 的 capture barrier，并在平台侧锁定绑定 Ontology，检查写 fence。
  保存失败保留旧检查点，正常建模可继续。禁止跨 run 全局静默。
  PostgreSQL 使用独立连接先持有 Ontology 行锁，再建立只读 repeatable-read 快照，
  避免等锁期间先建立旧 SQL 快照、随后读取新 RDF。
- fork 创建新平台身份，保留业务资源 IRI；重映射平台 ID、图 IRI、证据外键及图相关
  statement identity。历史审批原件不改，新增来源与目标绑定；旧 dry-run 和写入授权
  不复用，待办重新生成物化计划并走现有审批流程。
- fork 的完成索引以检查点时的数据和写回执为准，不吸收检查点之后的旧链写入。
  旧链 unknown 保留原结论，新项目的快照导入不能被解释为旧写入已清账。
- fork 前确认源 writer 停止；旧项目封存，保留读回证据。源 run 和检查点不覆盖。
  新 run 记录来源 run、checkpoint digest、快照 digest 与平台 ID 映射。
  写请求之前持久化预分配的目标 Project/Ontology ID；数据库 COMMIT 响应丢失时保留
  新图与 pending 台账供读回，不能将“收到异常”当作 SQL 零写入证据并删除新图。
- 派生推理、验证及检索投影在新项目重新计算，不把旧结果声明为当前有效结果。

## 验证

覆盖数据库快照保存后源数据变化、跨项目身份和证据关系、保护集、空/多 Ontology、
快照缺失或损坏、导入失败、旧链 unknown、审批绑定、新项目继续写入，以及默认接续回归。
真实数据库/RDF 依赖验证与纯单元测试分别记录；不以机械通过宣布语义建模通过。

## 宿主使用

保存继续使用原 `save_checkpoint` 接口；绑定平台时自动附带数据。`inspect_checkpoints`
的 `fork_resume` 给出快照引用与可用性。没有快照凭据时保存失败，保留此前检查点。

CLI 在原接续命令中添加 `--fork-reason "旧链悬账无法清账"`；仍需显式给出
`--run-id`、`--checkpoint-id`、`--new-run-id`、`--mode production`、
`--authorization-reference` 和 `--freeze-started-at`。不传 fork 参数保持原地接续。
宿主 MCP 对应 `resume_from_checkpoint` 的可选 `fork_reason` 参数；已启动的旧 MCP
进程需重新加载代码后才会显示新参数。

数据接口为仅组织管理员可用的 `POST /api/checkpoint-data/capture` 与
`POST /api/checkpoint-data/fork`；角色不直接调用。数据文件位于每个检查点的
`host-private/platform-data.json`，不复制到新 run 的角色可读产物目录。

## 2026-09-18 验证记录

- 后端完整 `uv run pytest -q`：1013 passed、37 skipped。新增数据与 HTTP 测试覆盖
  保存后变更、证据和保护集、多 Ontology、自定义 Shape 图、规则外键环、摘要损坏、
  写失败清理、COMMIT 响应丢失保留新图、组织管理员限定、源封存和批量导入拒绝。
- Team 完整 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`
  （backend 目录）：2006 passed、1 skipped、339 subtests passed。Runner 分叉测试使用
  CapturingAdapter，证明保存/恢复、CQ 隔离、新作用域和独立写链，不是 LLM 语义运行。
- `RUN_CHECKPOINT_DATA_LIVE=1 uv run pytest tests/test_checkpoint_data_live.py -q`：PASS。
  真实 PostgreSQL 写锁等待后建立快照，SQL 与 RDF 同代；恢复旧数据及新图继续写入通过。
- 本地服务已重启，backend health 与 frontend HTTP 200。重启后通过
  `RUN_CHECKPOINT_DATA_LIVE=1 CHECKPOINT_DATA_HTTP_BASE_URL=http://127.0.0.1:8001
  uv run pytest tests/test_checkpoint_data_live.py -q` 再验证实际认证 HTTP 保存/fork/封存读写。
  临时 Project、Ontology、图与测试 API Key 均由测试 finally 清理。
- 接口文档同步与新增文件 Ruff 检查通过。Runner 的全文件 Ruff 仍有原有的 3 个未用 import
  和 1 个未用局部变量（HEAD 已存在，本次未扩改）。GitNexus 索引不完整，公共写入口变更
  被标为 Critical；通过直接调用点检查、完整回归和真实接口测试核对影响。
