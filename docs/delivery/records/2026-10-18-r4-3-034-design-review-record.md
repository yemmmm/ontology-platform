# R4.3-034 独立设计审阅记录

用户授权：“请完成R4.3-034需求的细化和设计工作，通过独立审阅”。

- [权威需求](../../requirements/requirements-v4.3.md#r4-3-034)：F1—F7、D1—D8、A1—A7。
- [详细设计](../designs/2026-10-18-r4-3-034-dsh-usage-and-cutover-design.md)。
- OntoWeave源码基线`f34fe1f`；DSH固定接口源码基线
  `687f282e8625c6b8d11ff58211a90524be2e4317`。
- 本轮仅文档／独立设计审阅，不实施、不修改默认、不启动服务、外部模型、建模／
  修模或真实验收，不追加轮次。既有未提交需求／README／复盘／演示工作保留。

## 独立审阅

独立Reviewer：`/root/r434_design_review`，角色`plan_reviewer`，非设计作者，全程只读。

**Round 1 — PASS：0 Critical／0 High；关键未决假设：无。无需实质修订。**

Reviewer对照HEAD原登记及019／030／031—033合同，定向核对usage_report／capture、
Messages代理、DSH Adapter、CLI／Delivery入口及固定Harness字段、adapter、压缩与
累计投影。确认以下关键边界：

- DSH互斥桶、presence、终结输出及缓存写入计价明确，不继承默认零。
- provider请求主账与原生事件／累计／压缩不重复相加，失败压缩／重试不因缺summary遗漏。
- numeric-only SSE有界、不改变原流／不追加请求；计量失败不阻断运行。
- 原生session／进程／注册归属可接入，恢复不伪填Codex身份或重算历史。
- 026所选当前链与原034范围无实质偏差；032／033旧缺省及显式Codex选择保留，
  外层Host残余及成本披露，不宣称零Codex或全自主。
- 独立Consumer／Judge、治理读回、完整分母、Host成本及对照混杂保持；工程、
  L0／L1、切换、净降耗与账单分开结论。

作者在审阅期间自查纠正启动命令为实际`python -m modeling_team delivery --config …`，
并澄清message_start初始output=0不能冒充终结输出，Reviewer最终已覆盖最新原件。

| 实际审阅快照（状态同步前） | 字节数 | SHA256 |
| --- | ---: | --- |
| 034正文，从三级标题首字节至下一`## 初始阶段预算与推进顺序`首字节前，含尾空白 | 11864 | `d69a5bacf5c37f840cc61b32b2a3c5ffb3dfac57582e4e68f3160bdfddb733ab` |
| 详细设计全文 | 22814 | `ca0d3ec8c91d0ea595d2088dd9b287c631b82b04cdf5b9d2ec9e9c7a132c34a9` |

作者独立计算与Reviewer回报一致。此后仅同步034、索引／适配组、设计§7状态及本记录，
F1—F7、D1—D8、A1—A7与设计§1—6行为未变。上表不冒称状态同步后整文件摘要。
本次PASS不替代工程、真实L0／独立L1、默认已切换、净降耗或费用对账。

## 文档检查与提交

本轮本地相对链接／显式锚点、围栏、连续F／D／A编号、需求—设计—验收一致性及
diff检查通过；只提交034正文／索引／适配状态、本设计和本记录，不混入同一需求文件
既有复盘及其他未提交工作。无可执行代码／活跃技能变更，不运行产品测试或重启服务。
提交结果以git实际hash为准；文档检查不构成独立功能或真实语义验收。
