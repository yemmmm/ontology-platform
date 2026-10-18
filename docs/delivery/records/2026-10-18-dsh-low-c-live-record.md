# DSH low C组：最小安装链建模、独立验收与关闭

用户授权：“请开启一轮建模任务，授权三次，agent选用dsh deepseek-flash low，完成后关闭任务”。
复用 [R4.3-026](../../requirements/requirements-v4.3.md#r4-3-026) 最小安装链及当前
031／032／033／034／035 运行路径，不恢复已关闭的前组。

## 范围、配置与轮次

- Session：`minimal-chain-20261018-dsh-low-c`。
- Run：`minimal-chain-20261018-dsh-low-c-r1`；代码 `94f325f1d249c0dfcb30c9a0969233e0afd02e2e`。
- Delivery、Coordinator、Modeling、CQ、四个独立 Consumer、两个独立 Judge 均实际使用
  DSH、`deepseek-flash / low`；生产 profile 为 `dsh-deepseek-flash-low`，
  验收为 `dsh-acceptance-deepseek-flash-low`。
- 唯一业务源为 [scenario.md](../../evaluation-scenarios/minimal-installation-chain/modeling-input/scenario.md)。
  新项目新 scope，仅两概念及一条安装位置关系；无实例、基数或 SQL/API 映射推断。
- **实际初建1轮，fresh semantic-start 1次，无额外实质修模；剩余2轮已撤回。**
  真实开始 `12:49:31.528258Z`，授权记录 `12:48:51.137079Z`，相隔约40秒。

## 实际交付与独立验收

Host沿现有私有入口逐点审核全景及切片问题，两次审核请求均记录真实 accepted 回执。
Delivery完成整池冻结并回告原Coordinator；公开1题、隐藏3题，冻结摘要
`sha256:ef5b985b533bdce6d7461348f9f247fe5476fd923909183c3844876aba44ae22`。
地图、拓扑及公开CQ经035原通道交接，无Host手工复制或语义代写。

两批 `apply_atomic` 于 `12:52:46.753471Z`、`12:53:11.922665Z` applied，至revision2。
原团队完成实际治理读回、关联自查及资源收尾。Delivery对账后于 `12:56:08.927460Z`
完成正式handoff：无待处理/未知写入、只读封口，再启动公开及隐藏独立验收。
当前024／025路径不要求模型dry-run，不将其缺席记为未通过。

| 原始报告 | 完整分母 | 结果 |
| --- | --- | --- |
| `acceptance-v3/public-regression/cq-batch-0001/attempt-0001/batch-report.json` | 公开1/1 | `full_pass=true` |
| `acceptance-v3/reports/cq-batch-0001/attempt-0001/batch-report.json` | 隐藏3/3 | `full_pass=true` |

两报告同freeze及model binding，未执行题为空、模型漂移及证据重验漂移均为空。
源Runner于 `12:58:39.360239Z` 接受 `complete_cq_acceptance`，`cq_verdict=pass`。
**仅本人工最小链的有界独立语义回归PASS。两份原报告的blind_status均为
non-blind-regression**；Delivery对外称隐藏组为盲评不准确，以原报告为准。
不外推完整工业服务场景、盲测、L2或净降耗。

## 关闭与限制

Delivery完成 `finish_delivery` 后仍待命。Host依据原“完成后关闭”授权，向原业务入口发送
stop控制，无新增授权或建模调用；现有程序撤回生产/验收权限并停止本session对象。
最终Delivery为stopped、源run为CLEANED、FIFO移除，两组owner为stopped且retained成员为空。
关闭核查登记的48个进程全部不在 `/proc`，4把项目/Host临时key数据库读回均已revoked；
DSH cleanup为complete、无residual。模型与冻结池、报告和原事件保留。

本次建模、交接及验收由Delivery推进，Host承担两次私有CQ审核及最终显式stop。
因此不称“自动关闭”或零宿主介入；原配置operation前缀及900秒timeout未被Delivery沿用，
实际operation为`cq-acceptance-public-0001`／`cq-acceptance-hidden-0001`、timeout1200秒。
两组只读验收并行执行；实际没有触发timeout，不改写原参数或结果。

用量沿019原离线生成器汇总，238个已知响应总输入29,508,056、输出134,901；
其中Delivery 88响应、输入23,374,584、输出30,921。缓存、未缓存及各角色分项保留。
Host/scoring/推理细分与账单缺口仍unknown，整体usage/attribution/timing为partial，
billing为NOT_PROVIDED；不由缓存率或本次成功推导净降耗。有效语义/技术/等待工时未可靠拆分。

原件位于gitignored `workspaces/minimal-chain-20261018-dsh-low-c/`：
`authorization.json`、`final-report-verification.json`、`final-lifecycle-verification.json`、
`final-process-verification.json`、`final-key-verification.json`、`usage-scope.json`及
`usage-report/report.json`／`report.md`。本次未修改平台代码，不需产品服务重启或工程全量测试；
验证为本轮真实运行、独立语义验收、实际收尾核对及本记录链接/格式检查。
