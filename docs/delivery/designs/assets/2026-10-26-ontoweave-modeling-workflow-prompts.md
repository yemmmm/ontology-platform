# OntoWeave 建模流程图：图片生成提示词

生成方式：内置 image_gen 图片接口（首次生成，再定向修正返回箭头）。

最终图片：2026-10-26-ontoweave-modeling-workflow.png

## 首次生成

Use case: infographic-diagram.
Create ONE very detailed, highly legible Chinese workflow diagram poster for OntoWeave (织义), a business semantic modeling platform. This is a real technical process chart, not a decorative illustration. Use the highest available resolution, a tall spacious canvas around 3:4 aspect ratio; allocate ample room for 14 structured cards and labeled connector arrows. White background, dark navy Chinese sans-serif text, restrained blue/teal main stages, purple persistent-state panels, amber clarification, orange reconciliation, green acceptance. Crisp vector-like rendering, consistent typography, no gradients, no shadows, no mascots. Chinese text must be accurate and readable. Make title and stage identifiers prominent, body text concise but preserve ALL specified meaning. Do not invent status or claim this workflow is implemented.

Title: “OntoWeave 建模流程全景图”
Subtitle: “业务认知驱动 · 局部与全局交替 · 分层摘要贯穿全过程”
Small caption: “目标架构设计｜按业务工作单元推进，非固定 Agent 流水线”

LAYOUT:
A large central main-process lane covering about 58% width: S0 through S8 flowing from top to bottom, use a neat two-column serpentine layout if needed but make order unmistakable with prominent numbered arrows. Place S9 near the bottom with return routes along outer rails.
Left rail: Q business clarification and R uncertain-write reconciliation, plus a compact routing index.
Right rail: C1 shared business state and C2 hierarchical summaries, spanning the full workflow with purple dotted association lines rather than mandatory sequential arrows.
At bottom include a short legend, key semantic distinctions, and an end/result node. Use orthogonal connectors with clear arrowheads and ample spacing. Never run arrows through text. For long return connections use named destination tags such as “返回 S3”, not a spaghetti of lines.

MAIN STAGE CARDS — each must show identifier, title, 输入, 处理, 输出 in distinct small rows:

S0 目标、范围与基线
输入：业务目标、获准材料、已有模型、任务授权
处理：明确范围、成功判据与可复用成果
输出：任务说明、材料目录、模型基线、公开 CQ
注：独立题集由独立侧准备并在正式生产前冻结

S1 双向拆解业务
输入：目标、材料目录、已有业务结构
处理：目标→场景→事件／决策；材料反向补漏
输出：业务工作单元、共享概念、跨单元依赖
注：工作单元 ≠ 文档／表／Ontology／Agent

S2 捕获完整业务命题
输入：原始材料、上下文、已有命题
处理：保留条件、例外、否定、时间、量词和模态
输出：命题集、材料定位、覆盖记录、上下文缺口
注：未读 ≠ 无知识；计划 ≠ 已发生；许可 ≠ 义务

S3 解释语义与判断粒度
输入：完整命题、业务决定、既有定义
处理：核对身份、含义、适用范围与区分性情境
输出：复用／新增／局部限制／共享修改；未知与冲突
注：同一对象的状态或角色变化不自动拆成新实体

S4 设计局部模型
输入：语义决定、实际模型、关键命题
处理：组装概念、事件、关系、规则和映射
输出：完整局部候选、明确变更、命题—表达对应
注：条件须进入实际模型；候选不代表已应用

S5 跨业务整合
输入：局部候选、共享定义、相邻业务及引用
处理：核对身份、条件、时间、单位和上下游衔接
输出：整合结论、影响范围、安全变更组、验证情境
注：图连通 ≠ 业务成立；只等待受影响部分

S6 确定性应用
输入：明确变更、获准目标、当前基线、真实资源引用
处理：程序校验、绑定身份、原子应用并保存结果
输出：成功回执／可修正错误／结果待对账
注：多 Batch 不天然具有全局原子性；不重复成功写入

S7 真实读取与业务自查
输入：实际模型、公开问题、业务情境与获准依据
处理：受治理读取；核对正常、失败、例外及跨业务路径
输出：有读取依据的结果、覆盖范围、缺口与失败层
注：内部笔记不能补模型答案；检索故障不等于语义错误

S8 独立验收与交付
输入：冻结题集与依据、实际模型、读取条件、验收范围
处理：独立只读作答与裁决；禁止生产修改验收目标
输出：绑定范围和时点的通过／未满足／未完成结论
注：隐藏题和私有诊断不流回生产；局部 PASS ≠ 全项目 PASS

S9 变化与影响分流
输入：新资料、业务决定、模型变化、获准公开反馈
处理：区分重复、限制、纠正、业务变化、冲突和状态变化
输出：影响集、有效成果、待重审项、准确重入点
路由：范围→S0；结构→S1；材料→S2；含义→S3；表达→S4；衔接→S5；应用→S6；检索→S7；仅待验收→S8

MAIN ARROWS:
S0→S1→S2→S3→S4→S5.
S5 “需写入”→S6→S7.
S5 “完整复用，无需写入”→S7 (visible bypass).
S7 “声明范围具备验收条件”→S8.
S7 “仍有未处理范围”→S1／S2.
S8 “目标全部满足”→终点“保留交付结果”.
S8 “需修复且已有授权”→S9→corresponding stage.
External input “新材料／新决定／实际模型变化”→S9.
No automatic reopening after completion without authorization.

LEFT SUPPORT:
Q 业务澄清
输入：具体歧义、上下文、不同解释的后果、原步骤
处理：复用已有确认；向合适业务负责人提问
输出：确认／新材料／明确未决／范围决定
返回：新材料→S2；业务决定→S3；范围变化→S0
提示：未回复不默认确认；无关工作继续
Show amber branch S3→Q and return tags. Any stage may invoke Q.

R 写入结果对账
输入：原提交身份、Batch／Attempt、已有回执
处理：核对实际效果，保留已成功部分
返回：已应用→S7；确定无效果且可重试→原身份 S6
仍不确定：暂停相关写入，保留现场
提示：不能因超时复制节点或更换身份重试
Show orange branch S6→R.

Compact “发现问题时回哪里” routing key:
漏抽→S2｜理解错→S3｜表达缺陷→S4
跨业务冲突→S5｜检索故障→修复后 S7

RIGHT PERSISTENT SUPPORT:
C1 共享业务状态
输入：各步骤实际内容与结果
维护：稳定身份、当前判断、依据、候选、实际模型引用、未知、冲突、依赖、下一步
分开记录：
业务认知｜模型表达｜实际应用｜工作进度｜独立验收
输出：可跨会话接续的共同认知
原则：不另写一份已应用本体；并发修改先核对基线
Dotted association to stages, and C1→C2.

C2 分层业务总览
输入：获准模型＋可见工作状态＋允许展示的结果
层级 visualization:
项目总览
↓ 业务领域／流程
↓ 业务专题
↓ 具体定义与记录
每层保留：主线、未知／冲突、关键例外、跨主题依赖、深入入口
更新：相关变化→标记待刷新→按需或阶段刷新
原则：先授权后汇总；摘要不是事实依据；标明范围与时点
Output arrow back to stage selection labeled “导航到实际内容，不直接修改模型”
Small note: “摘要暂不可用不阻止安全建模；明确要求的总览仍是交付项”

BOTTOM:
“关键区分：已确认 ≠ 已表达 ≠ 已应用 ≠ 已验收”
“交接六问：当前单元与步骤｜依据｜改变内容｜实际完成｜剩余输入｜下一步”
Legend: 蓝色实线＝主流程；橙色回路＝纠错／恢复；紫色虚线＝持续状态与总览.
Make the final result architecturally precise, information-rich, beautifully aligned, and zoom-readable.

## 返回箭头修订

Use case: infographic-diagram, precise edit.
Input image 1 is the edit target: a detailed Chinese OntoWeave technical process poster. Preserve its title, typography, all stage cards and their Chinese input/process/output text, all C1/C2 purple panels, all blue main arrows, all green acceptance arrows, its overall layout and high legibility. Change ONLY the misleading orange/amber return connector routing, and improve the clarity of the relevant short route labels. Do not add new steps or remove information.

The required correction is connector accuracy:
1. REMOVE COMPLETELY the orange line at the bottom that currently goes from below S9 across to the far right and points UP into the green terminal node “保留交付结果”. There must be NO line or arrow at all between S9 and the green terminal. The ONLY incoming arrow to that terminal must remain the GREEN arrow from S8, labeled “目标全部满足”.
2. S9 already has a complete route index inside its card. Use that index as the return destination legend. Under S9 replace the removed orange horizontal rail with a short, standalone orange annotation WITHOUT any connecting line: “按卡内路由返回对应步骤；不直接结束流程”. Do not draw a giant return loop from S9 around the page. Retain external red input into S9 and retain S8→S9 orange arrow.
3. Clean up the orange/amber connectors in the narrow left corridor, between Q/R panels and the main lane. Remove ALL existing ambiguous orange/amber connectors in that corridor. Redraw exactly TWO separate one-way branch connectors with no intersections and no shared segment:
   - A short AMBER arrow from the LEFT edge of S3 pointing LEFT into Q, with label “需要业务澄清”. It can use a neat elbow if needed. It must point INTO Q.
   - A short ORANGE arrow from the LEFT edge of S6 pointing LEFT into R, with label “写入结果不确定”. It can use a neat elbow. It must point INTO R.
   Return destinations are already written inside Q and R and must stay legible. Do NOT draw physical return arrows from Q or R into the stages. Do NOT connect Q to R. Do NOT connect R to S3. Do NOT merge these support branches into the blue main spine. If there is not enough routing space, use matching source/destination badges in the corridor (e.g. “S3 → Q”, “S6 → R”) instead of a long arrow. The card text is authoritative.
4. Keep the blue S0→S1→S2→S3→S4→S5 chain; S5→S6→S7; S5 bypass→S7; S7→S8; S8→terminal completely intact. Preserve the S7 unfinished-work return destination S1/S2. Purple dashed lines are associations, not acceptance paths.
5. Bottom small handoff text should read clearly as six numbered questions: “1. 当前单元与步骤；2. 依据；3. 改变内容；4. 实际完成；5. 剩余输入；6. 下一步”. Preserve all other technical meaning.

Output ONE corrected high-resolution Chinese poster. White background, same restrained navy/blue/purple/amber/green visual style. Maximize accurate Chinese readability. No commentary outside image.
