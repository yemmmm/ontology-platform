# 当前 Demo 图谱节点与稀疏显示核对

日期：2026-11-01。状态：已定位展示层缺口；未修改代码或模型。

用户询问当前唯一保留模型的节点少且稀疏是否属于前端显示 bug。
本次只读核对实际接口、节点／关系过滤与浏览器显示，不修改模型或界面。

保留 Project `40841ac8-1c93-4cb1-85ba-1a9e8fb7928b`，Ontology
`755f1e0e-cf5d-47f2-a2a3-95220f4cba96`，revision 4。
先复用同代码／环境的既有实际核对证据，再针对浏览器显示与边丢失原因补充验证。

来源：[清理后最终核对](../delivery/evidence/2026-11-01-v5-single-model-retention/summary.json)、
[此前全量调查](2026-11-01-v5-model-size-investigation.md)、
`docs/requirements/requirements-v4.2.md` R4.2-003、当前 `ModelBrowserPage.tsx`、
`workspaceApi.ts` 与 `ForceGraphCanvas.tsx`。

## 结论与计数

“节点数量少”部分来自模型的实际规模；“稀疏、缺少业务关系”主要来自图谱投影缺口。
它不是清理造成的资源丢失，也没有证据显示本例是分页截断。

| 层次 | 当前 Demo 的计数 |
| --- | --- |
| 实际模型资源 | 14：4 个 Class、3 个关系类型、4 个表映射、3 个连接映射 |
| 前端保留的画布节点 | 11，按约定隐藏三个 ObjectProperty 关系定义 |
| 接口关系记录 | 13，含模式声明和映射引用 |
| 隐藏节点后过滤的记录 | 9：6 条 domain／range 声明＋3 条映射指向关系类型的引用 |
| 剩余画布边 | 4，均为表映射指向所映射 Class 的 mappedClass 关系 |
| 图连通分量 | 四对节点＋三个孤立连接映射节点，共七个分量 |

逐条去向与连通分量见 [summary.json](../delivery/evidence/2026-11-01-demo-graph-display-diagnosis/summary.json)。
计数使用实际 API 原件和前端源码投影，清理后再次核实的 revision 4、资源／关系计数和
实际 RDF 哈希与这些原件一致；相关代码与模型未变化，复用已有读回结果。

## 稀疏形成的具体原因

实际模型声明 `issued call` 的 domain 为 ApiKey、range 为 CallRecord；
`call of model` 的 domain 为 CallRecord、range 为 Model；`granted access to` 的
domain 为 ApiKey、range 为 Model。

当前读取返回“关系定义 → domain／range 类”的原始声明。
`ModelBrowserPage.tsx:51` 过滤 ObjectProperty 定义节点后，`:79` 又过滤任何一端
不可见的边。这使上述六条声明全部消失，没有另外展示三个已声明的类间关系模式。
三个 join mapping 指向这些关系定义的 mappedRelationType 引用也同时被过滤。
因此只剩四条 table mapping → Class 的边。

隐藏属性／谓词作为独立节点符合 R4.2-003 的既定约定；缺口是隐藏之后没有可读地呈现
关系模式和其映射引用，导致业务模型画布不完整。不是要求重新把所有属性画成独立节点。
domain／range 是模式约束，修显示时应区别于业务实例间已断言的事实，保留依据，不补造事实。

`ForceGraphCanvas` 按传入节点和边创建图，并执行 fcose 布局及 fit。
在输入已是七个互不连通分量时，布局会将这些分量分开摆放；仅缩放或压紧布局无法恢复缺失关系。
该结论定位的是投影阶段原因，不声称已经排除所有用户特定布局或筛选状态问题。

## 为什么总节点数也不多

模型的业务概念类只有四个；其余资源主要是关系和外部数据库映射。
字段、计算条件、例外及规则内容保存在资源语义定义／映射载荷中，不逐项生成画布节点。
业务数据行保留在外部数据库，九条 CQ 也是能力目标，不是九个新增业务节点。
“原冻结业务范围完整”不代表本体会有大量节点，更不表示新增九题问数能力均通过。

清除视角过滤后，当前代码的预期输入是 **11 个节点、4 条边**。
选择对象／流程／数据映射等视角还会进一步减少可见节点或边。

## 浏览器与验证边界

本次通过 Chrome DevTools 打开独立检查页，静态应用 HTTP 200，部署包
`/assets/index-jZmx5MR0.js` 中仍有同一 DatatypeProperty／ObjectProperty 过滤逻辑，
确认该逻辑存在于当前实际交付的前端包。
该检查浏览器没有用户登录态，`/api/auth/me` 返回 401 并正常显示登录页；未登录、未修改会话、
未读取用户当时的视角设置，因而没有声称完成已登录图谱渲染或用户会话布局复现。

本次只生成调查文件和关系过滤汇总；没有新增建模调用、修改模型／CQ、修改前后端或重启服务。
修复目标应为已声明关系模式及映射引用的只读呈现，不以新增业务实例或增加节点数掩盖展示问题。
