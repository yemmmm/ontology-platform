# v5 快照分叉的现有能力复用

日期：2026-10-30。范围：当前工程能力验证；不修改后端 capture/fork 合同。

## 来源

- [R5.0-001 F10 与持续工作空间](../requirements/requirements-v5.0.md)。
- [R3.0-017](../requirements/requirements-v3.0.md)：保存时数据、显式分叉、源封存及未知结果纪律。
- [平台数据接口](../../backend/app/api/checkpoint_data.py)及[数据服务](../../backend/app/services/checkpoint_data.py)。
- [Host HTTP 适配](../../modeling_team/checkpoint_data.py)。

## 决定

命名观察快照保持原查看／比较能力；include-platform 另外捕获平台保存时的 SQL／RDF
数据。平台数据与 workspace／checkpoint 各自具有版本和捕获时点，不声称全局事务。
临时组织管理员凭据只在 Host 使用，记录身份并撤销，数据包保存在 Host 私有目录。

现有 fork 会封存源项目的全部 Ontology。v5 以显式 archive-source 参数承接该行为，
操作本轮自有工程项目；不增加另一个 clone API。分叉前等待源活动自然停稳并封口凭据。
预分配目标身份，在请求前落盘；未知响应保留原目标，先读回再决定接续，不自动换目标重试。

新项目以保存时数据启动新的业务接续。授权 task_ref／原 budget_ref 保持，workspace_ref
隔离分叉工作空间和控制；原 run、checkpoint 和失败证据保留。获准材料及认知记录可以导入，
导入记录标为待复核；新执行使用新原生上下文，并重新取得实际模型和独立验收证据。
原生执行、在途控制和旧验收 PASS 不复制成新目标的完成证明。

## 验证边界

基础接线及源控制隔离／未知结果不重试已纳入 v5 回归。第三次完整回归 162 项通过，
含真实 PostgreSQL 和隔离 MCP 的相应用例；数据复制用例中的模拟平台不证明真实 RDF 复制。
真实 capture／fork 和接续结果继续记入[持续开发记录](../delivery/records/2026-10-29-v5-autonomous-progression.md)。
