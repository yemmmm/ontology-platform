# OntoGen：从科学术语到分类层级的生成流程

## 1. 项目身份与阅读边界

- 仓库：<https://github.com/schwallergroup/ontorag>，本次研究的是其中 `src/OntoGen/`，不要与其他同名 OntoGen 项目混淆。
- 快照：`4d54c8aa08c3e22958e3dab7c0a28e04162261da`
- 调研日期：2026-10-23；仓库许可证：MIT。
- 论文：[Scientific knowledge graph and ontology generation using open large language models](https://doi.org/10.1039/D5DD00275C)。
- 阅读内容包含文档预处理、TERMO、类别生成、taxonomy 主算法、Tree 数据结构和评测脚本；未执行模型或复现科学领域实验。

## 2. 建模理念：先确定术语，再组织层级

OntoGen 将知识整理拆成显式中间产物：原文、术语、缩写展开、定义、关系、类别种子和分类层级。分类生成不是直接把全文一次性翻译为 Turtle。

论文描述的流程包括词汇提取、初始类别生成、taxonomy 生成、知识图谱实例化、词汇间关系抽取。公开代码则是若干 CLI 脚本、研究数据与 notebook 的组合。尤其 `generate_taxonomy.py` 的主要持久化结果是 Python 的 Tree／wordmap pickle，不能把这个脚本直接称为完整 OWL 导出器。[S1] [S2]

## 3. 源材料整理

### 3.1 PDF 与文本预处理

`extract_plain_text.py` 包含 PyMuPDF 和 Nougat 相关路径，以及重复行、页脚／脚注、异常长行、连续换行等处理函数；`extract_sections.py` 提供摘要和引言提取。它们针对科学文献布局做准备，目标是减少版面噪声进入术语提取。

类别生成提示重点使用摘要和引言来识别领域主要主题；细粒度术语、定义和关系则可以从正文分块抽取。两类输入承担不同建模职责，不能假定“只读摘要”就覆盖全文知识。[S1] [S3]

### 3.2 TERMO 的数据结构

`Termo` 继承 `dict`，保存 `terms`、`acronyms`、`relationships`、`definitions`。提取操作由不同方法完成：

| 方法 | 结果 | 后处理 |
| --- | --- | --- |
| `extract_terms()` | 术语及匹配信息 | 去重、子串过滤、可选原文出现校验 |
| `extract_acronyms()` | 缩写到全称映射 | 与词表和上下文对照 |
| `extract_definitions()` | 术语到定义 | 过滤未知术语 |
| `extract_relationships()` | 术语间三元组 | 两端必须在术语／缩写列表中 |

`_build_chunks()` 按文本行与字符长度组块，默认相关方法的分块参数为 2000 字符。不同抽取任务可以设置不同长度。[S4]

关系输出提示采用可解析的文本行，解析器要求形如 `- term1 > relation > term2` 的三个部分，再清理星号和空白。端点词表检查能够减少凭空生成新名词，但**端点在原文出现，不代表两者之间的关系已被原文证明**。

## 4. 同义词与缩写怎样进入分类体系

`process_vocabulary()` 会排序词汇和缩写，处理星号、括号内缩写、连字符与大小写，并维护 `id_to_synonyms`。通过统一 ID 及同义词列表，把多个词面挂到同一个 Tree 节点。`wordmap` 再提供“词面 → 节点”的快速查找。[S2]

这解决了一部分文本规范化问题，但不是通用的语义实体链接服务。缩写展开是否正确依赖抽取；同名异义也不会仅凭大小写或连字符处理自动消失。代码中重复 ID／词面处理应结合具体领域词汇检查。

`Tree` 持有 `value`、`children`、`synonyms`，提供节点查找、路径、层级、叶子、祖先和修剪操作。虽然类名为 Tree，复用同一个节点对象到多个父节点下会形成共享子节点结构；分析时应按实际图连接理解，而非默认每个节点只有一个父类。[S5]

## 5. 类别种子：多次生成与综合

`generate_categories()` 包含三个可分别指定模型的职责：

1. generation model 阅读多个文本，生成主类别及子类别；
2. format model 将输出整理为指定的两层文本格式；
3. synthesis model 综合多次结果，提炼反复出现的类别。

函数默认参数包含 `num_retries_consistency=20` 和 `num_generated_seed=20`，应与具体 CLI 参数及调用配置区分。这里的 consistency 表示多次采样及综合，并不是形式逻辑一致性证明。[S6]

提示要求类别简短、避免把两个概念用“and”拼在一个名称中；格式化函数将更深层子类别去掉，只保留前两层。这说明初始类别承担的是粗粒度骨架，而完整细化发生在下一阶段。

生成结果写入 `categories/`。多候选、格式整理和综合是明确的脚本步骤；代码并没有把它们实现为会自主创建新 Agent 的协作团队。

## 6. Taxonomy 主算法

### 6.1 初始化

`generate_taxonomy()` 读取类别种子，建立根 `Thing`；再读取每篇文章对应的 `.terms.csv`、`.acronyms.csv` 和原文，构造跨文档词表、同义词映射和 `wordmap`。

初始类别进入树，领域词汇对应的节点则准备好但未必已经连接到树中。分类过程需要把它们挂到有意义的父类别下。[S2]

### 6.2 逐文档、逐轮分类

每一轮按文档遍历：读取当前 taxonomy 的词和路径、当前文档词汇及原文，然后让模型输出词到父类别的 `isA` 关系。

`prompt_include_path` 控制是否在候选词后附加路径信息；当前代码选用路径中的一个近邻层次，而非把所有祖先路径无限展开。其目的是给已有类别补充语境，同时控制提示长度。

每篇文档进行 `sc_retry` 次采样，默认主函数为 3 次；`majority_voting_answers()` 对 `(child, parent)` 计数，默认要求超过半数。投票只在词表中存在、头尾不同的关系之间进行，不会把未知词直接接受为新类别。[S2]

### 6.3 结构检查

`add_asnwers()`（保留源码中的拼写）在写入前检查：

- 两端是否存在于 `wordmap`；
- 是否指向同一个节点；
- 新父节点是否已经是子节点的后代，避免成环；
- 该连接或直接反向连接是否已存在。

当前主路径使用 `destructive=False`，倾向于增加连接而非每次删除旧位置重新挂载。之后调用 `remove_self_loops_tree()`，并保存每轮的 `wordmap_N.pkl` 与 `tree_N.pkl`。[S2]

这些检查保证一部分结构性质，但不证明“某词确实是另一词的子类”。例如 part-of 与 is-a 的混淆，仍可能在结构无环的情况下通过。

## 7. 实现中需要保留的细节

| 观察 | 具体含义 |
| --- | --- |
| 文档顺序使用 `seed + iteration` 进行局部随机排序 | 有意识减少输入顺序偏差，但不等于整个运行完全确定 |
| 某些词表／候选列表仍调用全局 `random.shuffle` | 复现还需控制其他随机状态 |
| 已计算叶子过滤列表，但主流程赋回语句被注释 | 不能根据注释宣称模型只看到非叶子类别 |
| 解析支持 `isA`、冒号或 `is` | 输出协议宽松，但词面包含分隔符时需留意误解析 |
| 同一 child 的投票结果最终存进字典 | 冲突父类的实际选择受投票阈值及字典写入影响 |
| `Termo` 有 backend 选择，但部分关系抽取直接调用 `query_ollama` | 不能仅凭构造参数断定所有方法都通过统一后端路由 |

以上为快照静态分析，不是已动态复现的故障报告。它们对理解论文方法如何被研究代码具体实现很重要。[S2] [S4]

## 8. 评测方式

`ElementKG/eval_reconstruction.py` 包含词汇覆盖、缺失术语、层级 precision／recall、祖先集合和共同祖先等评估函数。它将“词抽到了没有”和“层级放对了没有”分开衡量，适合观察 taxonomy 的结构质量。[S7]

仓库还包含领域数据、不同模型产物和对照实现。论文中的科学知识图谱结果不能直接视作任意企业文档、中文文本或复杂业务规则上的验证。本次没有运行这些评估函数，也未验证所需本体／数据依赖是否完整。

## 9. 能力边界

OntoGen 具体实现了术语整理、类别采样综合、层级关系预测、投票和结构去环。它最鲜明的资产是这些可单独观察和替换的中间步骤。

以下能力不能仅凭“ontology generation”名称推断已有：完整 OWL 公理学习、SHACL 验证闭环、生产级事务更新、跨团队本体版本合并、权限建模、自治 Agent 动态创建。主分类脚本输出的 Python 对象也需要进一步处理才能进入其他图数据库或本体编辑器。

## 10. 源码索引

- [S1]：`README.md`
- [S2]：`generate_taxonomy.py`
- [S3]：`extract_plain_text.py`
- [S4]：`termo.py`
- [S5]：`tree.py`
- [S6]：`generate_categories.py`
- [S7]：`eval_reconstruction.py`

[S1]: https://github.com/schwallergroup/ontorag/blob/4d54c8aa08c3e22958e3dab7c0a28e04162261da/src/OntoGen/README.md
[S2]: https://github.com/schwallergroup/ontorag/blob/4d54c8aa08c3e22958e3dab7c0a28e04162261da/src/OntoGen/generate_taxonomy.py
[S3]: https://github.com/schwallergroup/ontorag/blob/4d54c8aa08c3e22958e3dab7c0a28e04162261da/src/OntoGen/extract_plain_text.py
[S4]: https://github.com/schwallergroup/ontorag/blob/4d54c8aa08c3e22958e3dab7c0a28e04162261da/src/OntoGen/termo/termo.py
[S5]: https://github.com/schwallergroup/ontorag/blob/4d54c8aa08c3e22958e3dab7c0a28e04162261da/src/OntoGen/tree.py
[S6]: https://github.com/schwallergroup/ontorag/blob/4d54c8aa08c3e22958e3dab7c0a28e04162261da/src/OntoGen/generate_categories.py
[S7]: https://github.com/schwallergroup/ontorag/blob/4d54c8aa08c3e22958e3dab7c0a28e04162261da/src/OntoGen/ElementKG/eval_reconstruction.py
