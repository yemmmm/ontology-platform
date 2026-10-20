# Codex 金额预算首轮故障与窄修复

用户授权一轮 Codex／`glm-5.3-flash`／`low` 建模测试、人民币3元，随后授权定位和修复。
权威范围为 [R4.4-002](../../requirements/requirements-v4.4.md#r4-4-002)；业务仍为
[R4.3-026](../../requirements/requirements-v4.3.md#r4-3-026) 当前通用最小安装链。
原run为 `minimal-chain-20261020-codex-glm-3cny-123453-r1`，金额授权不变。

## 原因与修复

1. 预算持久映射按摘要键排序，重载后把累计快照的映射顺序当成文件顺序，误报
   `cumulative_reset`。预算入口恢复每个数值源的真实字节偏移顺序，再交既有共用核算；
   不按token取最大值，也不按时间重排掩盖真正的源计数回退。
2. Codex共享代理按当前设计只记录传输状态，却被当成必须自带usage的独立数值源。
   runtime现在显式关联该成员的原生数值源和共享代理capture session。成功传输只在同
   capture session／provider／credential alias／model存在已计价原生覆盖、截止点已覆盖
   传输结束且去重样本数足够时免于重复缺数结算。保留原生来源依据，不伪造请求级usage，
   不额外计费，不新增GLM SSE采集器。失败／中断／缺少原生数值／身份不匹配仍保留问题。

T0复核：金额授权和真实缺测仍必须保护，但成功传输行没有token是既定合同，不应当重复
触发缺测暂停。已绑定原生数值和既有核算覆盖成功路径；删除全部缺测保护则会允许真实
未计量消耗，因此只收窄重复判断，保留失败与中断的恢复门。

## 验证

- 新增11项回归：持久映射乱序、真实累计回退、原生／代理结算不重计、三类真实失败、
  不同／缺少credential alias、缺少原生数值、单样本不足及重复通知不能掩盖缺测。
  开发阶段先复现两项实际失败，修复后11 passed。
- 既有预算核心、proxy、CLI、价格及owner集成回归86 passed。
- 修改文件Ruff及编译检查通过。Team全量回归 **3701 passed、12 skipped、
  318 subtests passed**，564.67秒，359项warning，无失败。
- GitNexus索引停留旧提交，新计量符号的impact返回not found／UNKNOWN。
  本轮依据当前TaskBudget、RuntimeBudget及Codex／Delivery实际注册调用点检查影响，
  暂存detect_changes仅返回5文件／0符号／0流程／low；不宣称取得当前图索引的完整覆盖。

## 原任务与证据边界

在原预算的私有副本追加已有运行身份可证明的source关联，再用当前代码读取保留原件
重算，副本阶段没有改写原预算。成功传输的6条缺数误报及累计回退误报
消失，已知本地估算为 **¥0.09438928**，已知部分余额为 **¥2.90561072**。

原Delivery在首次错误暂停期间另有一次 `client_disconnected`，request为
`855347620d044a9a9f81ba7281066812`；代理传输状态、原生数值快照及rollout均未给出该次
调用的token回执。不能把其他成功请求覆盖到这次中断，也没有可信数值上限可暂估。
该真实缺口继续触发 `metering_error`；私有副本上的正式恢复检查返回
`metering_inputs_not_recovered`，新消耗保持关闭，未自行填0／追加预算／开始fresh run。

Host随后沿正常`register_source`／`tick`入口，将相同来源关联和重算结果追加到原预算，
未更换budget_ref或解除暂停；原授权及全部用量源文件的前后SHA256一致。后续检查发现
仍存活的旧代码监视器将数值重新覆盖成¥0.046529，故该写回不记为在线部署成功，正确重算
结果保留在独立原件。本轮未强制停止仍持有原run凭据的旧监督进程，未在费用缺口未结算
时重启收费角色或恢复原链；真实托管续跑修复仍未验证。没有独立语义验收，建模结果
保持PARTIAL。工程测试／离线原件重算与真实恢复、业务语义质量分别记录。

私有证据位于gitignored目录
`workspaces/minimal-chain-20261020-codex-glm-3cny-123453/`：
`metering-blocker.json`、`repair-replay-result.json`、`repair-resume-check.json`、
`repair-live-reconciliation.json`、`repair-live-followup.json`、
`repair-team-regression.log`；原件不由后续成功覆盖。

修改仅在`modeling_team/`，不涉及backend／frontend；不需要重启本地应用服务。
