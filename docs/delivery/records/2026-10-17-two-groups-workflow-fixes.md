# 2026-10-17 两组建模复盘缺陷修复

授权：用户在[两组复盘](../modeling-retrospectives/2026-10-17-two-groups-defect-review.md)后
明确“请你修复上面识别到的问题”。基线`c30a3d9`。本次仅修Team流程与离线工具，
无provider调用、真实建模start、业务模型写入或验收重跑；原流程保持关闭。

## 修改与质量边界

| 问题 | 最小修改及实际责任面 | 保留边界 |
| --- | --- | --- |
| 单切片假跨切片补修 | Runner把地图实际slice_ids交给`cross_slice_projection_issues`；只有一个实际切片时，正确的空列表不再生成coverage_gap或修复通知。范围未知／真实多切片仍保留反馈，非空条目的字段／题目身份／文字仍核对 | 不改旧地图、不替Agent预选切片、不新增唯一性硬拒绝；generic/compact合同与实际Coordinator提示明确panorama不等于跨切片，不重复slice或发明第二slice |
| 短交接重包装、截断重读 | 通用及minimal-chain Coordinator实际加载说明建议一次行内交齐短派单／终态总结；大材料保留原文件通道，读取大合同／报告从开始即分段 | 保留原Task、scope、来源、决定、轮次余额、实际Modeling确认、最终地图同步和完整原件；不按字数强制方式选择，不承诺把整个等待窗口删掉 |
| Consumer快照漏末段用量 | 复用`modeling_team.usage_report`，添加显式`batch_report`完整JSON源；仅投影task线程与数值快照，按实际task/provider/key_ref/thread和已绑定响应／累计记录核对，输出独立JSON／Markdown差异 | 同线程不相加；原生仍沿原去重／累计基线合同；缺原件仅fresh快照partial，冲突字段unknown，快照不作账单匹配；不修改原语义报告及digest，不把TTFT当provider计时 |

Delivery实际角色说明补充向宿主提供真实任务／线程及报告／rollout定位；宿主按
[既有离线入口](../../../modeling_team/references/model-usage-report.md)完成最终汇总，
不等待账单、不为统计重新启动模型。快照本身仍表示其生成截点，不伪装成全程终态。
未改压缩架构、effort、平台API、数据库或前端；残余Delivery输入收敛继续先验证既有唤醒修复。

## 开发验证

先以失败用例复现单切片错误反馈及缺失的快照归并，再实现修复。反例覆盖单切片、
重复slice身份不扩范围、真实多切片空列表、非空题目伪造、晚到响应、不重复累计副本、
线程绑定冲突、继承基线、不合法数值／截断、原报告只读、隐藏正文不进入数值报告及
partial快照不形成账单MATCHED。新增用量源只是离线证据适配，不增加语义裁判或运行守卫。

- 最终定向相关回归：**134 passed**（8个相关模块）；含最后补充的空线程输入边界。
- 从backend执行`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q`：
  **3138 passed、12 skipped、318 subtests passed**，287.45秒。末次空线程保护／测试
  由上述最终134项组合覆盖；全量其余输入不变。359条既有弃用／fork警告保留。
- Ruff增量检查无新增问题；`runner.py`原有7项、CQ生命周期测试原有2项告警保留，
  与HEAD逐项对照，未借本次修复清理无关代码。
- JSON合同解析、8条新增Markdown链接及工作区／暂存`git diff --check`通过；
  compact／canonical字段合同由相关测试核对。

仅`modeling_team/`及文档变更，不需backend/frontend套件或应用服务重启。
新Runner／角色会话会加载新代码和提示；没有声称旧会话热更新或取得新语义验收。

## 保留真实原件的离线复算

复用35线程统计的实际绑定，只核对其中Consumer：旧组9线程、新组4线程；每个
batch源按其task真实fresh_thread_id绑定，新组再加入对应已保留rollout。没有按
时间邻近猜配，也不将请求模型伪造成实际返回模型。scope和独立报告保存在原Host私有目录。

| 范围 | 最终已知输入／输出 | 修复效果及限制 |
| --- | --- | --- |
| flashx-low-b的9个Consumer | 390,953／5,668 | 无对应原生日志，partial快照小计与既有统计一致，不补零、不升级完整性 |
| flash-retro的4个Consumer | 357,397／7,706 | 原生已绑定记录补回88,192输入／248输出；快照仅作核对，不再相加 |

新报告见`workspaces/two-groups-usage-20261017/`下两组各自的
`*-final-consumer-report/report.json`、`report.md`及对应`*-final-scope.json`。
全部读取的原batch-report SHA256前后相同；新统计与上次独立直接求和一致。
缺宿主／辅助模型／供应商等覆盖，整体仍partial；这关闭本次离线归并问题，
不关闭整条R4.3-019或历史账单差额，不改独立语义裁决。

## 影响分析与剩余验证

GitNexus对CQ函数返回CRITICAL（已在编辑前告知）：直接边缺定位，并混入93条无关
后端流程，图结果不能作为完整影响证明。实际文本核对只有Runner的投影核验调用，
分别用于可恢复通知和生产handoff；新参数可选，原直接调用兼容。用量模块新符号不在
索引，聚焦检查`_read_sources→build_report→write_report/main`及测试；其余运行调用不变。
暂存差异检测为low、3个已索引符号、0条受影响流程，但漏掉新增用量符号及部分Runner
方法；已补上述调用点／diff核对，不把0条视为无影响或宣称具备完整图覆盖。

单切片反馈和短交接提示的实际Agent采用、完整新Runner自主交付及净成本仍待后续获准
运行；不为本次修复消耗建模额度。旧失败和介入历史保留，工程通过不替代这些实测。
