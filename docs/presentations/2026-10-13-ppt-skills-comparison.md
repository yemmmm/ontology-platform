# PPT skills 社区调研与第一部分演示

调研日期：2026-10-13。制作依据：[2026-10-12 演示草稿](2026-10-12-ontology-agent-ppt-text-draft.md)。

选取有明确上游、可核验使用量或社区关注度的四个代表方案，覆盖图片、原生 PPTX 和网页演示三条路线。下表为本次查询时的约数，安装量来自 skills.sh，星标为整个 GitHub 仓库的星标，不能视为单个 skill 的效果评分。

## 四个代表方案

| Skill | 查询时的社区信号 | 产物与优势 | 对这份草稿的适配判断 |
| --- | --- | --- | --- |
| [Anthropic `pptx`](https://www.skills.sh/anthropics/skills/pptx) | 约 234.6K 安装；仓库约 180.7K 星 | 创建、读取、修改 PPTX；适合原生文字、表格、图表与演讲者备注 | 如果重点是继续用 PowerPoint 修改，优先考虑。视觉效果仍依赖版式设计，不会因安装量高就自动精致 |
| [Baoyu `baoyu-slide-deck`](https://www.skills.sh/jimliu/baoyu-skills/baoyu-slide-deck) | 约 30.7K 安装；仓库约 26.6K 星 | 根据大纲和提示生成逐页图片，再合成 PPTX/PDF；风格选择丰富 | 适合图像风格统一的阅读和分享材料。现有版本采用这条路线，但整页图片中文字不方便局部修改 |
| [Zara Zhang `frontend-slides`](https://www.skills.sh/zarazhangrui/frontend-slides/frontend-slides) | 约 1.0K 安装；仓库约 30.5K 星 | 单 HTML，内联 CSS/JS；逐步展示、交互、现场文字编辑与 PDF 导出 | **最适合本次要求：更有表现力的网页演示，同时增加解释内容。此次实际采用此方案** |
| [Slidev 官方 `slidev`](https://www.skills.sh/slidevjs/slidev/slidev) | 约 12.4K 安装；仓库约 49.0K 星 | Markdown + Vue；代码演示、组件、演讲者模式，可导出 PDF/PNG/PPTX | 对技术培训和可运行代码演示很合适；这四页面向混合受众，当前没有需要 Vue 工具链的内容 |

能力说明依据各方案的上游文件：[Anthropic PPTX skill](https://github.com/anthropics/skills/blob/main/skills/pptx/SKILL.md)、[Baoyu Slide Deck skill](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-slide-deck/SKILL.md)、[Frontend Slides skill](https://github.com/zarazhangrui/frontend-slides/blob/main/SKILL.md)、[Slidev skill](https://github.com/slidevjs/slidev/blob/main/skills/slidev/SKILL.md)。

许可证需要准确区分：Frontend Slides、Baoyu 和 Slidev 的上游为 MIT；Anthropic 在仓库说明中将 `pptx` 等文档技能明确归为 **source-available，非严格意义的开源**。[Anthropic 上游说明](https://github.com/anthropics/skills#about-this-repository)、[Frontend Slides](https://github.com/zarazhangrui/frontend-slides#license)、[Baoyu](https://github.com/JimLiu/baoyu-skills)、[Slidev](https://github.com/slidevjs/slidev#license)。

## 选型与实际制作

Baoyu 上游说明主要面向阅读和分享；这份草稿则安排了约 6 分钟的现场讲解，并要求流程分步出现。用户进一步明确希望网页更有表现力、文字更充实，因此此次采用 Frontend Slides 的固定 16:9 舞台、逐步展示和现场编辑方法。[Baoyu 的用途说明](https://github.com/JimLiu/baoyu-skills/blob/main/skills/baoyu-slide-deck/SKILL.md)、[Frontend Slides 方法](https://github.com/zarazhangrui/frontend-slides/blob/main/SKILL.md)。

实际产物均使用 Frontend Slides 路线，包含三个完整视觉版本；它们不是分别运行三个 skill 的效果实验。Anthropic、Baoyu、Slidev 本次按上游能力进行比较。

| 视觉版本 | 网页 | 静态 PDF |
| --- | --- | --- |
| 深色演讲版：深青底、明亮文字、黄绿色强调；建议首先查看 | [四页演示](../../slide-deck/ontology-agent-part1-web-20261013/keynote.html) | [PDF](../../slide-deck/ontology-agent-part1-web-20261013/keynote.pdf) |
| 商务编辑版：暖白底、森林绿、宋体封面标题 | [四页演示](../../slide-deck/ontology-agent-part1-web-20261013/editorial.html) | [PDF](../../slide-deck/ontology-agent-part1-web-20261013/editorial.pdf) |
| 蓝白简报版：蓝白配色、无衬线标题、正式汇报结构 | [四页演示](../../slide-deck/ontology-agent-part1-web-20261013/blue.html) | [PDF](../../slide-deck/ontology-agent-part1-web-20261013/blue.pdf) |

[打开三种版本的总入口](../../slide-deck/ontology-agent-part1-web-20261013/index.html)。

## 内容与互动

- 第 1 页：保留原题、副标题和工业服务案例，补充演示关注的问题；业务概念图分步进入。
- 第 2 页：保留模型、工具、上下文和反馈的分工；增加“查工单、读合同、缺失时继续查询或提问”的任务示例，流程与路径按步骤出现。
- 第 3 页：保留适用目标、计时、暂停、空值与信息位置四个待确认点；可以点击“首次响应／恢复服务”切换关注事件。教学交互不计算或虚构实际 SLA 达标结果。
- 第 4 页：保留四行四列方法对比，补充各方法作用于什么，逐行展示；保留方法可以组合的结论。

原稿的讲解备注与来源保存在网页备注面板和 `speaker-notes.json` 中。新增解释来自原稿正文和备注的整理，业务问题及关系图保留示意标记。

## 验证范围

此次实际验证的是三个本地网页版本及其导出文件：

- 12 页逐页渲染，无舞台越界、表格与结论重叠或容器文字溢出；PDF 经 Poppler 再渲染目视核对。
- Chrome 离线模式下可打开，字体内嵌；无外部脚本或运行时安装要求。
- 键盘导航、逐步显示、备注、SLA 指标切换、文字编辑、浏览器内保存及修改版 HTML 下载通过检查。
- 1280×720 与 390×844 视口保持 16:9，整体缩放，无内容重排。
- 三份 PDF 均为 4 页，静态导出显示全部内容，文字可选择；动画和交互保留在 HTML 中。

这些检查证明演示文件可用，不构成 Ontology Platform 的建模、产品能力或语义验收结论。

## 安装入口

本次通过读取上游技能说明完成制作；下面是社区标准安装入口，供后续选择使用。

```bash
npx skills add anthropics/skills --skill pptx
npx skills add JimLiu/baoyu-skills --skill baoyu-slide-deck
npx skills add zarazhangrui/frontend-slides --skill frontend-slides
npx skills add slidevjs/slidev --skill slidev
```
