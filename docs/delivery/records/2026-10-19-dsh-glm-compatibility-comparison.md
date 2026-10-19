# 2026-10-19 DSH GLM 兼容与 Codex 同场景对比

用户要求在 DSH 中以 `glm-5.3-flash low` 执行一组任务，与最近 Codex 建模对比；
发现原隔离适配仅支持 DeepSeek 后，用户明确授权“补齐 GLM 兼容后运行”。
本次沿 R4.3-031／032／033／034 扩展精确 provider 接线，不改变建模业务含义或验收合同。

## 最小兼容范围

- 新增独立 `glm-messages` 目录路由，仅接受本次获准的 `glm-5.3-flash / low`；
  原 `glm-direct` Responses 路由及 Codex 默认保留。无自动回退、模型重命名或档位降级。
- 固定上游 `https://open.bigmodel.cn/api/anthropic/v1/messages`，复用宿主持钥、
  TLS、流式原字节转发、失败分类、凭据销毁及数值用量记录。官方兼容地址依据
  [智谱 Claude Code 文档](https://docs.bigmodel.cn/cn/coding-plan/tool/claude)。
- 复用固定 DSH Messages codec，单独注册 GLM provider；冻结本地 composition 摘要与
  实际有效绑定。原 DeepSeek 插件、工具集合／schema、资料隔离、控制与独立验收保持。
- Delivery、生产及独立 Consumer/Judge 全部显式 DSH／GLM。GLM credential 复用平台已有
  私有文件，只给隔离角色临时代理 token；没有复制 DSH 网页保存的另一份密钥。
  真实上游小请求 HTTP 200、响应模型精确，low 原样发送；不由响应推断供应商内部推理预算。
- 已核对用户 DSH 网页 provider `zai-coding-cn` 及默认 `glm-5.3-flash`，本地模型目录列出
  `glm-5.3`／`glm-5.3-flash`／`glm-5.3-highspeed`／`glm-4.6v`，前三者支持 low。
  网页既有 pi-ai 配置不注入隔离 Team，不修改 DSH 全局设置或密钥。

GitNexus 未收录新符号，impact 返回 UNKNOWN／target not found；本次采用直接调用点检查，
不声称图覆盖。受影响入口为 Delivery、生产 roster、验收 child 及生产凭据恢复。
未修改 backend/frontend，无产品服务重启。保留工作区此前无关未提交变更。

## 对比合同与原件

基线 `minimal-chain-20261019-token-opt-c-r1`；本组
`minimal-chain-20261019-dsh-glm-low-r1`，使用同一最小安装链源与 Task、同语义 Profile 的
DSH 版本、新项目新 scope。独立验收保持原公开1题／隐藏3题完整分母；本人工场景为
非盲回归，生产不接收私有答案或旧模型。Host 仅按既有职责逐点私审 CQ，不代写模型。

工程准备耗时与真实 semantic-start 至完整独立验收墙钟分开。对比全部绑定角色用量，
缓存是输入子集，推理是输出子集，缺失值及账单保持 unknown。不同协议、运行时及窗口
是实际差异，单次样本不做因果或完整费用结论。新增兼容成本单列，不隐藏到运行收益。

私有原件：`workspaces/minimal-chain-20261019-dsh-glm-low/`；保留授权、工程各轮日志、
上游探测摘要、Codex 基线数值、配置和真实运行证据。默认按一次任务的三轮上限管理，
fresh-start 与实质修模分开；成功后不为耗尽额度追加建模。当前任务未另发用户 stop，
正常完成按原合同保留只读 standby。

## 验证进度

新覆盖先红；GLM profile／原生 Delivery／生产隔离三项通过；当前 Consumer/Judge 两路
共20项通过。初轮曾发现验收 child 的 provider 检查依赖生产 run 属性，已收窄为传入
当前真实 binding；原失败日志保留。目录新增路由的原封闭集合断言已更新。
全量 Team 回归及真实运行结果随后追加；工程通过不代替真实 L0 或独立语义 L1。

当前最终专项验证：`test_dsh_glm`＋`test_messages_provider_proxy`共21通过；
`test_dsh_acceptance`两provider共20通过；`test_model_routing`77通过。
广泛Team套件按本次有界目标中止于612通过／2跳过／62项子测试，明确不是全量PASS；
另外生产／Delivery控制的相关回归保留完整日志，不与有交叉的轮次相加。
未运行backend/frontend套件，因为本次没有修改其代码。
