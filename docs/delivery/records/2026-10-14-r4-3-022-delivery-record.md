# R4.3-022 实现与开发测试记录

- 权威需求：[R4.3-022](../../requirements/requirements-v4.3.md#r4-3-022)。
- 复用设计：[Delivery决策输入与按需原文读取](../designs/2026-10-14-r4-3-022-delivery-decision-input-design.md)，独立设计Round 1 PASS。
- 本轮授权：2026-10-14“请根据设计完成v4.3-022需求，并通过测试”。
- 基线：`e206828`；实现范围为Delivery、实际加载的两份提示及直接测试。
- 结论：工程已实现；A1—A4开发工程验证与Team全量回归通过。独立工程验收未执行；A5净成本／A6完整独立业务语义验收待证。

## 实现与证据

完整最新observation仍单独原子保存，内部账本读取不受模型2MB全文响应上限限制。
模型采用delivery-decision-input/v1：当前必要状态、未决／未知／拒绝／冲突请求、真实变化、
报告资格绑定和原件入口。已结算请求及稳定有资格operation提供索引；退出、未知、无效
报告和未决控制不合成为成功。仅在已知元数据路径排除噪声，同名业务字段保留。

决策变化先写既有session-events.jsonl，session.json保存cursor及待投递定位。resume、
busy steer和idle send共用投影与明确的attempted／accepted／rejected／unknown记录。
新观察不能覆盖未投递包，分页确认仅覆盖已送达范围；journal与session保存中断后可对账。
接续强制重建必要状态。历史包提供最新current_state定位，要求行动前核对最新状态，
不因投递回执不确定重放平台动作。默认输入32KiB UTF-8，超量显式分页，大值准确引用。

read_delivery_artifact保留path-only全文；增加字节区间及literal JSON字段选择，默认／最大
16KiB分页，返回selection、range、完整性、遗漏、continuation及原件身份。普通文件绑定
完整digest，JSONL绑定捕获前缀；追加不混页，改写或缩短拒绝旧引用。缺字段与null、
损坏与非法参数、不可读与越权分开反馈。事件以源byte_offset／byte_length定位。
只补绑定operation record/log及已有verification原件读取，未开放相邻operation或符号链接。
Host私有内容、引用及变化包不自动发布，原公开投影与材料路由保持。

两份活跃提示指导按当前决策缺口补读必要完整事件、CQ业务依据、公开选定问题的实际
回答／读证／完整反馈，以及报告资格。必要全文、完整问题分母、独立裁决和写入硬门保持。
没有修改模型、窗口／压缩配置、生产角色、backend/frontend或Host公共状态输出。

## 验证

定向测试先后覆盖71、75、77及最终78项通过；新增真实文件／回执与离线dispatch合同测试，
覆盖大于2MB账本、稳定历史、无回执unknown、拒绝正文、digest冲突、遗留无法关联项、
坏行／半行、业务同名字段、中文边界、缺字段／null、JSON大字段、选择参数变化、普通
文件漂移、JSONL追加／改写、原事件源定位、32KiB分页、待投递保全、回执不确定、
session保存中断、接续当前状态及绑定operation权限。原wakeups/session测试同步新合同，
原生runtime与材料隐私回归在Team全量中执行。

最终命令：

```bash
cd backend
env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest ../modeling_team/tests -q
```

Team全量结果：**2903 passed、12 skipped、318 subtests passed**，耗时261.36秒；
356项既有RDFLib弃用警告，无失败。最终补充大阻塞原文的准确packet_path定位后，受影响
Delivery定向回归**78 passed**，耗时21.16秒；其余未变化代码的全量证据复用。
Ruff、Delivery技能validator、022本地链接／锚点／围栏及git diff whitespace检查通过。
GitNexus impact未找到_model_observation／_read_artifact；detect_changes未映射出修改符号。
已用实际call-site和diff检查三个原生输入入口、局部读取handler及既有角色边界；不宣称
图覆盖。未修改backend/frontend，按设计无需该侧全量、服务重启或健康检查。

本轮测试为开发者工程验证，没有独立工程Agent。未调用外部provider、未恢复停止的运行、
未消耗semantic start；没有真实token／账单净成本对照或完整独立业务语义验收。
工程通过与输入字节有界不建立A5／A6 PASS，不关闭真实收益及质量预期。

## 提交范围

仅提交本次代码、测试、活跃提示、022需求状态与跟踪记录。保留其他任务对021的需求／
跟踪文档改动，以及无关docs/presentations/、slide-deck/。共享文档仅暂存022所属差异。
