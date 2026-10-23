# LLMs4OL：Ontology Learning 的任务拆分与评测实现

## 1. 阅读范围与版本

- 仓库：<https://github.com/HamedBabaei/LLMs4OL>
- 源码快照：`a0bca35d22dd31d37d2ee1ae1150a561a7d256c5`
- 调研日期：2026-10-23；仓库代码许可证：MIT；数据来源和上游本体条款需分别查看。
- 对应 ISWC 2023 的 LLMs4OL 研究与实验代码。README 另链接后续 challenge，但本文没有把其他 challenge 仓库作为本快照实现。
- 本文阅读任务说明、prompt、模型适配、评分和微调入口。未下载模型训练或运行评测。

## 2. 为什么收录一个评测项目

LLMs4OL 不是一个成熟的“上传文档→输出完整本体”服务，而是把 ontology learning 分解成可测的子任务，比较语言模型能否完成这些步骤。它有助于准确描述其他项目究竟学习了哪一层语义。

README 将本体学习概括为语料准备、术语抽取、术语类型化、分类层级、非分类关系和公理发现。但该仓库主要实证研究下面三项，不能把完整概念框架当成已实现全部阶段。[S1]

| 任务 | 对象层次 | 预测目标 | 与其他任务的区别 |
| --- | --- | --- | --- |
| A：Term Typing | 术语→类型 | 给词汇术语预测概括类型 | 不只是发现文本中的实体 span |
| B：Taxonomy Discovery | 类型→类型 | 判断上下位／is-a | 不只是实例之间有关联 |
| C：Non-Taxonomic Relation | 类型之间的语义关系 | 判断给定非 is-a 关系陈述 | 不等于自动生成所有可能谓词 |

## 3. Task A：术语类型化

TaskA 组织词汇、类型及 prompt 模板，适配不同模型的输出，再映射回类型答案集合。来源包括 WordNet、GeoNames、UMLS 的部分词汇体系等，具体任务与数据使用范围在 datasets 中分别说明。[S1] [S2]

术语类型化关注“这个词或概念属于哪类”。已经给定术语时，任务没有同时测量从长文中找出术语的能力，也没有必然测量同名实体的上下文消歧。

`AnswerSetGenerator` 可利用模型为标签生成领域相关同义词集合，辅助答案词汇映射。这是将自由词面回答归入目标类型的一层，而不是直接更新某个本体中的 equivalentClass 公理。[S3]

评分代码提供 precision_at_k、AP@K、MAP@K 等函数；README 主要报告 MAP@1。该指标需要结合每条样本的候选答案和标签映射理解，不能直接拿它与关系抽取三元组 F1 或整图一致率比较。[S4]

## 4. Task B：把分类关系变成判断问题

TaskB 的模板覆盖 superclass/subclass、parent/child、supertype/subtype、ancestor/descendant 等表达。数据样本提供 text_a、text_b 和标签，模型判断相应陈述正确与否。[S5] [S6]

`ZeroShotPromptClassifier` 使用 OpenPrompt：

1. 加载基础语言模型和 tokenizer。
2. `ManualTemplate` 将两个类型名称放入句子。
3. `ManualVerbalizer` 把 correct/incorrect 映射到多个答案词。
4. `PromptForClassification` 在 freeze_plm 模式运行。
5. `PromptDataLoader` 组织样本，取 logits 的 argmax 得到类别。

不同模型家族有不同 tokenizer wrapper、截断和最大长度配置。它们不是同一聊天 API 下简单切换 model 字符串。

这个实现直接测量的是**给定类型对的关系判断**。即使有 build_hierarchy 或数据构建脚本，单个二分类分数也不证明模型已经从任意文档生成了全局无环层级。局部判断可能同时得到 A 是 B 子类、B 是 A 子类，也可能遗漏传递关系；这些全局性质需要额外图处理和评估。

此外 parent 与 ancestor 不完全同义。不同模板可以测量提示敏感性，但其答案范围、是否使用传递闭包，需要结合数据构建方式，而不能把所有模板都理解成“直接父类预测”。

## 5. Task C：实际是候选关系陈述判真

虽然任务名使用 Relation Extraction，当前 `TaskC/src/models.py` 的样本已经包含 h、r、t 和 label。`build_dataset()` 把它们拼成自然语言陈述，再交给模型判断 correct/incorrect。[S7]

因此该实验没有直接要求模型从零写出任意关系名称，也不完整涵盖原始文本的关系 span 抽取。候选关系由数据提供，模型完成关系成立与否的判断。

这一点对理解论文指标非常重要：固定候选空间、负样本构造、答案词映射都会影响 F1；它不能直接代表开放世界下从长文抽取所有非分类关系的精确率和召回率。

## 6. 模型接口与微调

本地模型路径使用 OpenPrompt 的模板／verbalizer 分类。GPT 系列适配器则把判断任务写成自然语言提示，保存 prompt、response 和输入记录，供后处理及 evaluator 评分。[S6] [S7]

这些 API 代码使用当时的 `openai.Completion.create`、`ChatCompletion.create` 等旧接口。仓库记录的是特定时期实验环境，不应不经依赖核对就把它当成当前 SDK 的可直接运行示例。

部分 API 测试循环会不断重试尚未完成的样本，遇错 sleep 后继续，未看到统一最大重试次数。这是实验脚本的恢复方式，不是有严格成本预算的生产任务调度。

`tuning/trainer.py` 使用 Transformers 的 Seq2SeqTrainer：将 prompt 文本和标签 token 化，padding 标签改成 -100，训练 seq2seq 模型并保存权重和 tokenizer。这里的 few-shot 包含少量样本微调研究，不应一律理解成只在 prompt 中放几个例子。[S8]

## 7. 评测结果怎样读

Task B/C 的 EvaluationMetrics 调用 sklearn accuracy_score 和 classification_report，后者提供 precision、recall、F1 和汇总指标。实际报告应说明使用哪个类别或哪一种 average，不能只说“F1”就认为所有表格完全可比。[S9]

本仓库的模型、数据、模板和结果是历史研究快照，不是 2026 年最新模型排行榜。README 中个别模型规模描述也不是本文采用的事实依据；这里关注的是任务定义和代码实现。

几个尚未由这些子任务分数直接覆盖的能力包括：跨文档同义词合并、类型层级全局一致性、n 元关系与事件表示、复杂 OWL 公理、证据来源、增量撤销、人工修改流程，以及 Agent 协作。

## 8. 与其余调研项目的概念对应

- AutoSchemaKG 的概念化与 Task A 部分相关，但其开放短语生成没有固定同样的标签空间。
- OntoGen 的分类图重建与 Task B 接近，但还包括投票、图连接和去环等全局处理。
- EDC 侧重实例三元组的谓词规范化，与 Task C 的类型关系陈述判真不同。
- OntoGPT 主要按已有 schema 填充实例并链接已有术语，不以从零学习分类体系为默认任务。
- GraphRAG／LightRAG 的检索图及问答指标，不能直接替代上述 ontology learning 指标。

这里仅用于解释研究任务的差别，不构成各项目效果排名。

## 9. 固定版本源码索引

- [S1：研究范式和任务范围](https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/README.md)
- [S2：Task A 数据与模型入口](https://github.com/HamedBabaei/LLMs4OL/tree/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskA)
- [S3：答案集合生成器](https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskA/src/answer_set_generator.py)
- [S4：Task A 指标](https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskA/src/evaluation.py)
- [S5：分类关系提示模板](https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/datasets/TaskB/templates.txt)
- [S6：Task B 模型实现](https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskB/src/models.py)
- [S7：Task C 模型实现](https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskC/src/models.py)
- [S8：微调 Trainer](https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/tuning/trainer.py)
- [S9：Task B 评分](https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskB/src/evaluate.py)

[S1]: https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/README.md
[S2]: https://github.com/HamedBabaei/LLMs4OL/tree/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskA
[S3]: https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskA/src/answer_set_generator.py
[S4]: https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskA/src/evaluation.py
[S5]: https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/datasets/TaskB/templates.txt
[S6]: https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskB/src/models.py
[S7]: https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskC/src/models.py
[S8]: https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/tuning/trainer.py
[S9]: https://github.com/HamedBabaei/LLMs4OL/blob/a0bca35d22dd31d37d2ee1ae1150a561a7d256c5/TaskB/src/evaluate.py
