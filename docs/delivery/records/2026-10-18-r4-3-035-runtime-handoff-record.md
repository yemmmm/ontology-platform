# R4.3-035 运行期交接交付与测试记录

权威需求：[R4.3-035](../../requirements/requirements-v4.3.md#r4-3-035)；
[详细设计](../designs/2026-10-18-r4-3-035-dsh-runtime-handoff-design.md)。
本次用户授权细化、设计审阅、开发和工程测试，不授权新的semantic-start、修模或真实验收。

## 交付范围

- DSH Runner复用原HandoffMaterials和write_handoff_output，仅Coordinator三个既有
  scenario-map合同文件自动快照并原字节接入Runner；回执绑定run、actor、版本、摘要与目标。
- 当前同版不重复转存；历史旧版迟到有准确stale和当前material身份，不回退新目标。
  缺失/损坏原件保留现场及替代关系；同内容目标不重写。地图/拓扑/application准入保持。
- Host原CQ审核及freeze后，Runner发布生产获准的不可变公开投影引用和最小freeze事实；
  原生dispatch/message关联稳定delivery_id，区分queued/claimed/settled/unknown/canceled。
  明确未送/取消可重试，unknown等待原响应核对；后续drain推进安全的待交接事项。
- 只改modeling_team及文档；未改backend/frontend、共享运行配置或产品依赖，无需产品
  服务重启。新的Runner进程加载修复，不热改已关闭的建模运行。

## 独立审阅

| 轮次 | 结论与证据 |
| --- | --- |
| 设计 Round 1 | plan_reviewer独立只读PASS；0 Critical/High，无关键未决假设；核对035、原件/Runner、CQ审核及freeze/原生派发接点 |
| 实现 Round 1 | REVISE，1 High：A已接收、B已接收后迟到重试A可回退目标；只有最新摘要去重不足 |
| 实现 Round 2 | PASS；从原journal保留历史版本索引，旧摘要在私有输出/Runner写入前返回stale，原件修复保留现场/关联；无剩余Critical/High或关键未决假设 |

审阅仅证明设计/代码检查；不表示独立工程执行验收或真实L1通过。

## 开发测试

1. 新增接线测试先因缺模块失败；实现后发现私有_bytes调用漏path及测试预期偏差，修正。
2. 首批定向原件/DSH回归23通过；新增固定DSH进程离线测试3通过：原工具自动转存、
   原生产环境读取公开材料、丢失回执/迟到响应/取消沿原身份核对。
3. 审阅High对应A→B→重试A、重载回归及缺失/损坏原件测试先失败，再修复至新增
   接线9项通过。原件恢复没有重复写目标或清除失败现场。
4. 首轮全量因接收审阅修复主动SIGINT中止，保留full-round1-interrupted日志/XML，
   退出1，不能计PASS；中止后的pytest teardown KeyError不作为产品失败或通过证据。
5. 最终全量：**3313 passed、12 skipped、318 subtests passed**，359项既有依赖/fork
   弃用告警，498.60秒，退出0。保留原opt-in跳过边界，不能称全部真实环境覆盖。
6. 全量启动后仅追加两项故障测试（生产代码未变）：目标写入后接收回执持久化失败、
   公开原件缺失再恢复。该文件最终**11 passed**，0.73秒，退出0，见fault-supplement.xml。
   它覆盖其中9项重跑及2项新增，不将11与全量直接相加。

工程用的是本机固定DSH `687f282`、bwrap及本地离线Messages HTTP/SSE fixture，
没有外部模型调用或平台模型写入，不消耗生产轮次。测试不等于自主完整业务交付。

```sh
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q --tb=short \
  --junitxml=../workspaces/r4-3-035-engineering/full.xml
uv run ruff check --select F ../modeling_team/runtime_handoff.py ../modeling_team/runtimes/dsh.py \
  ../modeling_team/tests/test_runtime_handoff.py ../modeling_team/tests/test_dsh_runtime.py
```

全量stdout/stderr保存在同目录full.log，五个受测代码/测试文件的全量起始摘要见
`workspaces/r4-3-035-engineering/tested-source-sha256.json`；全量运行及结束期间生产代码与
原生DSH测试文件摘要保持一致。两项补测后的接线测试文件身份另见
`fault-supplement-source-sha256.json`；最终全部11项已执行通过。四个文件Ruff F类通过；
runner.py的7项既有F类告警与HEAD逐项code/message相同，本次无新增，未顺带清理。
相关文档链接/锚点与git diff --check通过；提交仅纳入035拥有文件及需求内对应hunk，保留其他工作区修改。

## 影响与证据界限

GitNexus impact对DshRuntimeAdapter返回Target not found/UNKNOWN；detect_changes虽报low，
但返回旧README/pi-modeling-agent路径，未覆盖当前DSH代码，不能称图分析覆盖。
实际定向检查了Runner材料初始化、Transport材料调用、CQ投影/freeze、drain重试、
DSH派发/原生事件/晚到回执和恢复接口；Codex与公开内容生成逻辑沿原路径。

| 035判据 | 本次结论 |
| --- | --- |
| A1 | 工程覆盖：真实DSH进程调用原工具、Runner原路径/原字节摘要及新版本；未声称真实获准建模链已执行 |
| A2 | 工程覆盖：真实Host审核/freeze接点的公开筛选、原生产环境原件读取及原生领取，旧版/取消/unknown/迟到有分别身份；不是业务完成 |
| A3 | 工程覆盖：角色/路径/run错误、转存目标失败、原件缺失/损坏、回执丢失、同版/旧版重试、原身份恢复；不扩大权限或永久杀run |
| A4 | 待新授权真实验证：DSH Delivery自主完整公开1/1+隐藏3/3、application、独立L1、收尾及全任务人工介入/费用披露 |

本次没有真实自主交付、独立语义质量或净降耗的新证据。032/034原PARTIAL及历史失败保留，
019/034成本缺口不以工程测试替代；已关闭run及收回的额度不恢复。
