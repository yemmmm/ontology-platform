# 重复发参失败：显式小范围纠错修复

**工程、历史回放及三组隔离原生Agent纠错采用通过；完整首轮重复性仍待验证。**
用户要求重点攻克多个首轮中反复尝试仍失败的问题。归属R4.3-025／028及原
OPT-20261019-DSH-05，不新立业务范围；原建模额度3/3已耗尽，本次没有新真实建模、平台写入或独立语义验收。工程回归后，
另做三组有界Provider诊断测试，记录于下节；原失败、r2首次成功及r3引用实测证据保持。

## 已定位缺口与本次责任面

原生错误、正确原件与执行参数脱节，已有六键提示实际加载仍复发，见
[跨轮调查](../modeling-retrospectives/2026-10-20-first-round-failures-comparison.md)。
2c65731的request_ref已解决“正确原件还需再次转录”；但原件或内联输入被拒后，
仍缺少可直接使用的被拒正文引用与小范围纠错入口。修几键仍要让模型重生成整份JSON，
故纠错说明正确不保证实际发参正确。该工程恢复缺口可直接修复。

这不是对供应商内部生成失败的唯一因果结论；schema复杂度、历史和effort的影响仍
未通过单因素实测区分。没有移位桥接的证据，不静默修正业务语义来掩盖发参错误。

按T0复核，现有字段／scope／冻结／授权／原子应用校验直接保护实际写入，应保留；
它们已经返回可恢复未写入，不应增加失败次数门、永久终止或fresh重开。新增的是
Agent显式选择后可确定性执行的输入纠错，不是新的Ontology修改类型或自动恢复框架。

## 实现

- 静态compiler拒绝返回correction.request_ref，精确保留实际被拒对象。内联正文由
  程序沿既有Modeling→Runner材料授权发布；同内容复用稳定引用。已有引用直接复用。
- request_ref可附request_edits：JSON Patch子集add／replace／remove／move，路径直接
  指向请求正文。程序仅在副本执行Agent明确指定的补丁；任一错误拒绝整个补丁列表。
  JSON原件、原尝试及证据不变。无根替换；数组索引与JSON Pointer转义准确验证。
- suggested_edits只建议移动内层已有控制键到缺失外层，或移除与外层完全相同的
  重复控制键。不同值不代选，不推断缺失语义，不删不支持的业务字段；建议不自动应用。
  field_contracts复用原compiler当前资源／操作的允许字段，帮助Agent作具体修改。
- 派生完整内容继续原编译、scope／冻结、原子application、成功去重和未知写入对账。
  相同最终内容从内联、原件引用或补丁进入具有相同提交身份；新通路不能绕过未知写入。
  若派生请求仍不合法，新的correction引用绑定本次编辑后正文，避免沿旧base丢失修改。
- tools/list、Runner派单、通用及实际minimal-chain-modeling包、可执行合同、MCP说明
  及025设计增量已同步。旧内联方式保留；没有新工具数／角色／尝试计数门或Provider配置。
  新Team进程加载生效，原只读待命run不热载、不自动恢复。

示意（复制真实返回引用，不重抄请求）：

```json
{
  "modeling_id": "modeling",
  "request_ref": {"material_id": "<correction.request_ref的实际身份>"},
  "request_edits": [
    {"op": "move", "from": "/changes/0/fields/item_id", "path": "/changes/0/item_id"}
  ]
}
```

Agent仍须检查建议与业务含义，选择实际修改；unsupported字段中有业务含义时须显式
保留到支持的字段，不能以减少错误为由删除源内容或降低独立验收标准。

## 证据与测试

新增18项首先在旧实现失败，均因缺少correction／request_edits通路；首次实现27项通过，
5项暴露纠错引用目录未建立，补齐后32项通过。进一步补充派生引用、JSON Pointer／数组
操作及14份历史原件回放，最后请求引用套件48项通过，其中34项为本次新增。

历史回放导航见[原件摘要与逐调用结果](../evidence/2026-10-20-modeling-input-correction-replay.json)：

| 历史run | 含可无损修正控制键形状的实际调用 | 显式选择补丁后原compiler通过 |
| --- | ---: | ---: |
| minimal-chain-20261019-dsh-input-fixes-r1 | 17 | 17 |
| minimal-chain-20261019-dsh-glm-low-140728-r1 | 19 | 19 |
| minimal-chain-20261020-dsh-glm-low-r1 | 12 | 12 |
| 合计 | 48 | 48 |

48次去重14份完整请求，原样保留在tests/fixtures/modeling-misnested-requests.json。
回放先确认原请求不能编译，再显式选取建议并通过原compiler，逐字段比较未编辑业务内容。
140728中的部分错误形状当时先被上游就绪门挡住，不能把19次都追称为当时字段错误回执；
这也不是全历史失败分母，其他字段／非对象错误不由无损建议自动修复。离线测试替Agent
明确选了补丁，不能证明真实Agent必定选用，也不是48次新建模或首轮成功率。

最终相关回归命令从backend运行，`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest`：
请求引用、direct_modeling、direct_submission、direct_execution、wiring、performance
输入合同、capability socket、DSH runtime及minimal-chain共 **145 passed，0 skipped，
110.31秒**。覆盖真实AF_UNIX MCP静态拒绝→纠错引用→显式补丁→原编译执行；平台HTTP
边界为隔离替身，无真实模型写入。成功去重、未知写入、材料越权／摘要、conflict不代选、
Unicode业务正文、补丁全有或全无及原scope／freeze门均保留。

变更模块Ruff通过；Runner完整Ruff仍为HEAD相同的7项既有问题，code/message/count一致，
无新增。JSON／fixture、链接／diff检查通过。GitNexus对当前入口及schema函数未索引，
detect_changes仅给有限low结果；采用定向调用点检查，不宣称全图影响覆盖。
未改backend/frontend或共享运行配置，无产品服务重启要求。
本地过程原件：workspaces/modeling-input-correction-20261020/{red,green,green-final,
related,contracts,final}.log、final.xml、historical-replay.json、runner-lint.json。

## 有界真实Agent纠错采用

为避免再启动一轮完整业务建模，仅沿既有DSH原生会话能力进行三组Provider诊断。
三组均为DSH／glm-5.3-flash／low，分别从上述三个历史run选取一份不同的真实错误请求。
先要求Agent重现拒绝，再按实际工具反馈纠正，最多4次工具调用／180秒；未提供正确补丁
答案。模型自行选择correction.request_ref和request_edits。

三组均为2次实际工具调用：第一次not_written，第二次引用＋显式补丁completed。
前两组首次正文与历史原件对象相同；第三组首次调用又自行把两个控制键复制到外层，
但保留了内层重复键，仍被准确拒绝。该偏差保留，不能追称3/3严格原样重现；随后
Agent用小补丁同时移动缺键／移除重复完成。三组最终业务内容均与历史输入相同，
原件不变，Host没有改写实际发参。耗时22.38／25.11／28.31秒，原生技术会话随后关闭。

每组后续结束响应一并计账，累计9个原生数值响应：**input45,099、output1,969、
合计47,068 token**。cache已含，Provider内部账单与本次Host研发成本另列未知，不称为
全任务净成本或节省金额。原GLM辅助SSE计量观察器没有恢复。
证据及会话身份／原件前缀见[原生采用证据](../evidence/2026-10-20-modeling-input-correction-native.json)。

该测试复用DSHDeliveryRuntime隔离技术工具会话和现有capability/compiler/executor，
平台HTTP写入为隔离替身；没有真实平台凭据或业务模型写入，不是Team semantic start，
不扣原建模轮次。它不是完整Modeling roster，也不是恢复旧run长上下文，不能作为业务
L1、全任务首轮重复性、单因素净收益或所有供应商行为已解决的证明。有限结果表明：
真实Agent实际采用了无需重生成全文的纠错通路，三份选定输入均没有继续重复错误请求。

## 关闭边界与下一项验证

025该纠错增量工程及有界原生纠错采用通过；025整体部分验证，05整体待调整，030净
降耗未通过保持。不给稳定一次完成、独立语义或token因果PASS，也不以又一个fresh成功
覆盖原重复失败。

必要下一切口是一次获准真实运行：沿当前DSH／glm-5.3-flash／low、原最小链及原四题，
观察若发生静态拒绝，Agent实际是否使用correction引用与小补丁、是否保留未编辑内容、
同轮是否继续并独立验收。若无静态拒绝，则只证明预防正例，纠错采用仍未触发；不故意
向业务模型写诊断概念。原授权余额0，新增semantic start须用户追加明确授权。
