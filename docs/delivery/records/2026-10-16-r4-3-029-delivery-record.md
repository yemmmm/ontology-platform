# R4.3-029 实现与验证记录

范围依据[需求029](../../requirements/requirements-v4.3.md#r4-3-029)及[已审设计](../designs/2026-10-16-r4-3-029-delivery-responsibility-design.md)。实现前基线为 `7dd96b181ad7235371e221a84b04e0c3347e7cf4`。保留既有 README、需求、复盘和演示材料改动；未启动 Provider、semantic start 或修模，未消耗生产轮次。

## 实现

- Delivery 只保留流程、绑定核对及必要技术定位；移除模型侧 `submit_cq_review`、`prepare_repair_task`、`start_repair`、`verify_repair`。历史 repair owner 仍可观察、停止及清理；底层 Host 修复接口保留。
- 沿用 005／022 的观察、32KiB 决策分页、16KiB 补读与送达确认。已知普通消息、进度、用量和部分明确成功工具事件不单独唤醒；失败、不完整、未知写入、未知事件及坏事件仍可定位。CQ 正文、候选与普通消息正文留原件引用，宿主请求默认只投递身份／待办／状态／引用。
- `request_host_action` 在当前 run 真实 pending／issue 绑定下发起私有 CQ 审核或平台修复交接。请求幂等、冲突可更正；非 issue 技术异常不强造 issue。公开 material 沿既有授权检查，未知和私有 CQ material 不进入修复交接。
- `delivery_host_actions` 复用私有 session journal。宿主 CLI 只追加绑定请求的 `host_action_result`，不启动修复，不将结果当审核回执或正式恢复。Host 与 Delivery 同锁追加并在锁内取真实 byte offset；恢复读取共享锁快照。结果原件限当前 session `host-results/`，Delivery 只补读 journal 已绑定且 digest 一致的原件。
- 通用／最小 Coordinator、CQ、Delivery、宿主 skill/runbook 及 MCP 文档对齐职责。Host 私有审核后 Delivery 检查实际回执／digest 再冻结；平台修复后 Host 直接用原 `resolve_issue(repair_completed)`，不依赖 Delivery 本地 verification IDs。Coordinator 按源／候选／提交／应用／治理读取／回答局部定位，保留未知和隐藏资料边界。

## 验证与边界

开发及独立测试结果见[独立工程记录](2026-10-16-r4-3-029-test-record.md)。开发首轮 Delivery 回归99项通过，最终开发定向回归262项通过；独立综合314项及58个子测试通过。独立测试包含真实 Runner／FIFO 的 CQ 审核到冻结、未审与旧 digest 拒绝、完整公开／隐藏题分母、Host 正式 issue 恢复、多进程 journal offset、未确认输入恢复、结果原件及 material 授权反例；不属于真实模型语义验收。

GitNexus `impact` 未找到当前 Delivery 符号；`detect_changes` 返回 low，但列出过期索引中的符号，不能作为本次图覆盖证据。已定向核对 `DeliverySession`／`run_delivery` CLI 调用、事件投影、Host 接口及恢复／资料调用点，并检查 diff；未为此重建索引。

本次没有 backend/frontend、依赖、迁移或启动脚本改动，不适用平台后端／前端套件及服务重启要求。实际角色加载／隔离由现有 Team 回归覆盖。

工程测试通过只证明上述代码和合同；A2／A3 的真实生产语义定位、A5 的实际宿主修复效果、A6 的独立真实完整语义及 A7 同条件全链成本／效率仍待获准运行，不宣称 L1 或净效率 PASS。宿主审核／诊断／修复及补读成本沿019既有口径记录，无完整数据不填节省比例。

### 回归轮次

所有 pytest 在 `backend/` 使用 `env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`。

- 首次 Team 全量：3107 passed、12 skipped、318 subtests passed、1 failed（290.59s）。唯一失败是 `test_v43_production_refs.py::test_role_contracts_preserve_coverage_and_existing_bounded_public_feedback` 直接匹配 `not executed`，Coordinator 文本换行切开该短语。调整换行后保留“未执行／PARTIAL，不把已应用写入回滚或当验收通过”的原语义，重新执行全量，最终通过。
- 最终 Team 全量：`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`，**3113 passed、12 skipped、318 subtests passed**（277.57s，exit 0；359条依赖弃用／fork相关warning）。无失败。
- 最终开发定向：10个 Delivery／Host／CQ／issue 测试模块，262 passed（24.48s）。
- 独立工程：具体轮次、材料授权反例修复及最终代码身份见独立测试记录；不以自测替代独立验证。
- 两个活跃 Skill 的 `quick_validate.py`、本地链接／锚点与围栏检查通过；`git diff --cached --check` 通过。新 Host module 用 Ruff 格式化，格式化前后 AST 完全相同。

## 提交边界

本轮提交代码、活跃角色／技能合同、Host接口说明和实现／独立工程测试记录。需求文件含既存复盘等混合变更，029状态与022覆盖说明在工作区同步，不整文件纳入提交；前序设计、设计评审、量级基线及其他既有文档／演示材料保留原工作区边界。未将未负责的历史证据并入本轮提交。
