"""Build the offline HTML deck from editable content, CSS, JS and subset fonts.

Run: python build.py
Refresh bundled font subsets when adding characters: python build.py --refresh-fonts
"""
from __future__ import annotations

import base64
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SLIDES: list[dict] = []

SOURCES = {
    'rdf': ('W3C · RDF 1.1 Primer', 'https://www.w3.org/TR/rdf11-primer/'),
    'owl': ('W3C · OWL 2 Primer', 'https://www.w3.org/TR/owl2-primer/'),
    'sparql': ('W3C · SPARQL 1.1 Overview', 'https://www.w3.org/TR/sparql11-overview/'),
    'philosophy': ('Stanford Encyclopedia of Philosophy · Logic and Ontology', 'https://plato.stanford.edu/entries/logic-ontology/'),
    'foundry': ('Palantir · Ontology Overview', 'https://www.palantir.com/docs/foundry/ontology/overview/'),
    'mcp': ('Palantir · Ontology MCP', 'https://www.palantir.com/docs/foundry/ontology-mcp/overview/'),
    'project': ('项目名称与技术栈 · 来源摘录', 'sources.html#project'),
    'r4': ('v4.0 多视角与当前能力边界 · 来源摘录', 'sources.html#r4'),
    'acceptance': ('2026-10-06 有界语义验收 · 来源摘录', 'sources.html#acceptance'),
    'retirement': ('R4.0-025 当前退役范围 · 来源摘录', 'sources.html#retirement'),
    'team': ('Modeling Team 职责与建模方法 · 来源摘录', 'sources.html#team'),
    'feedback': ('R4.3-015 写入反馈与信任边界 · 来源摘录', 'sources.html#feedback'),
    'demo': ('虚构教学案例 · 统一政策、事实与边界', 'case-materials.md'),
}


def e(value):
    return html.escape(str(value), quote=True)


def reveal(content, step=1, tag='div', cls=''):
    return f'<{tag} class="reveal {cls}" data-step="{step}">{content}</{tag}>'


def svg(content, width=1696, height=562, label='业务关系示意'):
    return f'<svg class="diagram" viewBox="0 0 {width} {height}" role="img" aria-label="{e(label)}">{content}</svg>'


def text(x, y, lines, cls='small-text', anchor='start', gap=36):
    if isinstance(lines, str):
        lines = lines.split('\n')
    spans = ''.join(f'<tspan x="{x}" dy="{0 if i == 0 else gap}">{e(line)}</tspan>' for i, line in enumerate(lines))
    return f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{spans}</text>'


def node(x, y, w, h, title, sub='', cls='', step=0, attrs=''):
    title_y = y + (h/2 + 11 if not sub else 42)
    content = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="node {cls}"/>'
    content += text(x+w/2, title_y, title, 'node-title' + (' dark-text' if cls == 'dark' else ''), 'middle')
    if sub:
        content += text(x+w/2, y+(80 if h >= 95 else 67), sub, 'node-sub' + (' dark-text' if cls == 'dark' else ''), 'middle', 31)
    return f'<g {attrs}>' + (reveal(content, step, 'g') if step else content) + '</g>'


def edge(x1, y1, x2, y2, label='', step=0, cls='', label_pos=None, path=None):
    d = path or f'M{x1},{y1} L{x2},{y2}'
    content = f'<path d="{d}" class="edge {cls}"/>'
    if label:
        lx, ly = label_pos or ((x1+x2)/2, (y1+y2)/2-15)
        content += text(lx, ly, label, 'edge-label', 'middle')
    return reveal(content, step, 'g') if step else content


def footnote(content):
    return f'<p class="note-strip">{content}</p>'


def topic(number, title, content, step=0):
    markup = f'<section class="topic"><div class="number">{number}</div><h3 class="edit-text">{title}</h3><p class="edit-text">{content}</p></section>'
    return reveal(markup, step) if step else markup


def fact(key, value):
    return f'<div class="fact"><span class="key edit-text">{key}</span><span class="edit-text">{value}</span></div>'


def add(title, lead, body, takeaway='', note='', sources=(), cls='', flag=''):
    SLIDES.append(dict(title=title, lead=lead, body=body, takeaway=takeaway, note=note, sources=list(sources), cls=cls, flag=flag))


def chapter(number, title, prompt, route, demo=False):
    add(title, prompt,
        '<div class="chapter-route">'+''.join(f'<span>{x}</span>' for x in route)+'</div>',
        cls='chapter', sources=('demo',) if demo else (),
        flag='虚构教学案例' if demo else '',
        note='本章围绕一个问题展开：'+prompt)
    SLIDES[-1]['chapter'] = number


def policy_card(compact=False):
    return f'<div class="policy{" compact" if compact else ""}"><h3 class="edit-text">RET-DEMO-v1</h3>' + ''.join(
        f'<div class="policy-row"><span class="edit-text">{a}</span><span class="edit-text">{b}</span></div>'
        for a,b in [
            ('适用对象', '普通商品，单件整件退货'),
            ('申请条件', '客户声明未使用<br>0 ≤ 间隔 ≤ 168 小时'),
            ('退款前提', '退回验收通过、客服批准'),
            ('事实来源', '<code>orders.signed_at</code><br>客户输入、外部售后接口'),
            ('范围与状态', '按权限读取，检查分页／截断<br>缺必要信息时补读或询问'),
        ][:4 if compact else 5]) + '</div>'


def returns_graph(complete=False):
    # The same skeleton is used on P10 and P30.
    s = ''
    s += node(18,190,200,108,'客户',step=0)
    s += node(330,190,220,108,'订单',step=0)
    s += node(670,190,230,108,'订单项','一条商品明细',step=0)
    s += node(1055,190,245,108,'退货申请',cls='soft',step=0)
    s += node(1440,190,235,108,'退款处理',step=0)
    s += node(670,420,230,105,'商品',step=0)
    s += node(1040,0,290,110,'RET-DEMO-v1','一份具体政策',cls='soft',step=1)
    s += edge(218,244,330,244,'下单形成',1)
    s += edge(550,244,670,244,'包含',1)
    s += edge(1055,244,900,244,'针对',1)
    s += edge(1440,244,1300,244,'关联',1)
    s += edge(785,298,785,420,'关联',1,label_pos=(835,365))
    s += edge(1178,110,1178,190,'规定申请条件',2,label_pos=(1300,163))
    s += edge(1330,58,1557,190,'规定退款前提',2,label_pos=(1494,85),path='M1330,58 H1557 V190')
    if complete:
        s += reveal(text(22,368,['普通商品','客户声明未使用','0—168 小时'], 'small-text'),2,'g')
        s += reveal(text(1060,376,['条件与范围：普通业务说明','数据映射：签收时间与商品类别','退款前提：验收通过、客服批准'], 'small-text',gap=42),2,'g')
        s += reveal(text(22,542,'具体订单、声明与状态从外部输入取得；模型不复制订单行','guide'),2,'g')
    else:
        s += reveal(text(22,378,['业务概念：退货申请','具体记录：申请 R001','具体订单记录来自外部系统'], 'small-text',gap=40),2,'g')
        s += reveal(text(1055,430,['先认识关系骨架','第四章再补齐条件与映射'], 'small-text',gap=42),2,'g')
    return svg(s,label='客户、订单、订单项、商品、退货申请、退款及政策的关联')


# 01–07: the business understanding problem
add('本体如何帮助<br>Agent 理解与处理业务', '概念、系统设计与业务案例',
    svg(node(85,0,430,114,'订单','一笔业务，从多个环节理解',cls='soft')
        +node(0,240,270,112,'退货申请')+node(355,430,270,112,'退款处理')
        +edge(220,114,135,240,'针对订单项',label_pos=(140,180))
        +edge(270,296,490,430,'退款另有前提',label_pos=(447,338))
        +text(500,205,['验收','审批'],'small-text','middle',42),640,562,'订单、申请与退款的业务关联'),
    '贯穿问题：这笔订单能退吗？为什么还不能马上退款？',
    '我们讨论的是 Agent 如何获得并使用业务依据。用同一个退货问题，依次理解业务歧义、本体表达、平台分工和消费判断。电商规则全部虚构，不是行业惯例或法律意见。',
    sources=('project','demo'),cls='cover')
SLIDES[-1]['extra'] = '<p class="cover-intro edit-text">OntoWeave（织义）<br><span class="small">原 Ontology Platform</span></p>'

add('目录','四章正文，最后留时间回答建设与维护中的常见问题',
    '<nav class="toc" aria-label="演示目录">'+''.join(
        f'<a href="#{page}" data-go="{page}"><span class="toc-no">{num}</span><b>{title}</b><span class="toc-desc">{desc}</span></a>'
        for num,title,desc,page in [
            ('01','Agent 的业务理解难题','工具调用成功以后，为什么还会答错',3),
            ('02','本体的概念、技术与价值','业务含义怎样表达、查询与复用',8),
            ('03','OntoWeave 与建模方法','平台怎么分工，模型怎样建立',18),
            ('04','电商退货与退款模拟案例','用三笔订单核对完整判断过程',26),
            ('FAQ','常见问题','选型、建设、质量与维护',35),
        ])+'</nav>',
    '看完后，能判断何时值得用本体、Agent 怎样用、由谁建设和验证')

chapter('01','Agent 的<br>业务理解难题','订单已经签收，客户想退货。<br>Agent 应该查什么，又依据什么做判断？',['任务机制','业务歧义','方法与局限'])

add('Agent 怎样完成一个业务任务','用户：订单 A101 能退吗？',
    '<div class="flow">'+''.join(
        reveal(f'<div class="step"><small>{n}</small><b class="edit-text">{title}</b><p class="edit-text">{desc}</p></div>',step)
        for n,title,desc,step in [
            ('01','理解请求','语言模型识别目标<br>拆出所需信息',0),('02','查订单','工具返回状态、商品<br>以及签收时刻',1),
            ('03','查政策','取得适用范围<br>时间窗与例外',2),('04','核对条件','调用计算工具<br>比较事实与条件',3),('05','解释与继续','回答资格<br>说明下一步',4)])+'</div>'
    +reveal('<div class="reading" style="margin-top:65px"><p class="edit-text"><b>语言模型</b>负责理解与规划。<b>工具</b>提供事实、计算或业务操作能力。<br>查到“已签收”，仍不足以判断是否符合退货条件。</p></div>',4),
    '调用成功说明工具完成了请求，业务判断还需要正确的含义与口径',
    '这里的 Agent 是围绕目标组织任务、调用工具并根据结果继续工作的 AI 程序。大模型可拆解任务，订单工具提供事实，政策提供依据，计算工具比较时刻。完成一次工具调用不代表答案成立。')

add('“能退货”包含哪些业务判断','同一组事实，不同的解释会改变答案',
    '<div class="timeline"><div class="time-point" style="left:12%"><b>付款</b><span>09-28 10:00</span></div>'
    '<div class="time-point" style="left:40%"><b>签收</b><span>10-01 10:00</span></div>'
    '<div class="time-point" style="left:87%"><b>拟申请</b><span>10-06 10:00<br>2026 年 · UTC+08:00</span></div></div>'
    '<div class="time-choice"><span class="pill demo" id="timeOrigin">付款起算 · 待确认假设</span><button data-time-choice="paid" aria-pressed="true">付款起算</button><button data-time-choice="signed" aria-pressed="false">签收起算</button><span class="small">点击比较，业务口径尚待确认</span></div>'
    '<div class="time-result screen-only"><div id="timeHours" class="result-number">192 小时</div><p id="timeMeaning">按付款起算，超过 168 小时。起点不同，结论就变了。</p></div>'
    '<div class="print-only" style="margin-top:48px"><p class="statement">付款起算 <b>192 小时</b> ／ 签收起算 <b>120 小时</b></p><p class="small" style="margin-top:18px">前者超过 168 小时，后者处于时间窗内。两种解释在此均为待确认假设。</p></div>'
    +footnote('还需确认：自然日还是连续小时？普通还是定制？可申请是否等于可退款？'),
    '第一步先确认业务含义，再让 Agent 计算与回答',sources=('demo',),flag='虚构教学输入',
    note='本页两种起算口径是用于暴露歧义的假设。付款时刻只是本页对照输入，案例最终规则在 P28 由模拟商家确认：从签收时刻起算连续 168 小时，包含边界。付款到拟申请为 192 小时，签收到拟申请为 120 小时。')

METHODS=[('提示词与示例','当前任务、示例','交代本次目标','多应用各自维护，定义容易分叉'),
         ('文档检索 RAG','政策、说明材料','找到相关依据','仍需确认版本、范围与例外'),
         ('微调','训练样本','改善任务适配','难充当随时更新的精确政策库'),
         ('业务工具','查询与操作接口','取得事实或执行','字段与状态的业务含义仍需解释'),
         ('专家澄清','歧义与冲突问题','确认业务口径','确认结论需要继续沉淀与维护'),
         ('本体','定义、关系与条件','复用共同语义','依赖正确建模、充分读取与维护')]


def methods_graph(limits=False):
    center_title='申请、验收、退款' if limits else '订单 A101 能退吗？'
    center_sub='客服、仓库与财务共同引用？' if limits else '围绕同一业务问题，组合不同方法'
    s=node(615,218,465,123,center_title,center_sub,cls='soft')
    positions=[(0,0),(0,210),(0,420),(1196,0),(1196,210),(1196,420)]
    input_lines=[['输入：任务与示例','补足：本次任务目标'],['输入：政策与说明材料','补足：可引用的相关依据'],['输入：训练样本','补足：任务适配（训练阶段）'],['输入：查询与操作接口','补足：业务事实或执行能力'],['输入：业务歧义与冲突','补足：经确认的业务口径'],['输入：定义、关系与条件','补足：可复用的共同语义']]
    limit_lines=[['多应用各自维护','定义容易分叉'],['找到片段后仍需确认','版本、范围与例外'],['难充当随时更新','且精确引用的政策库'],['得到字段和状态','仍需解释它们的含义'],['确认结论还需沉淀','并持续维护'],['依赖正确建模','充分读取与持续维护']]
    for i,((x,y),(title,*_)) in enumerate(zip(positions,METHODS)):
        side=i>=3
        s+=node(x,y,500,140,title,'\n'.join(limit_lines[i] if limits else input_lines[i]),step=(i//2+1 if limits else 0))
        target_y=245+(i%3)*35
        start_x=1196 if side else 500
        end_x=1080 if side else 615
        mid_x=1138 if side else 558
        s+=edge(start_x,y+70,end_x,target_y,'支持',step=(i//2+1 if limits else 0),label_pos=(mid_x,y+48),path=f'M{start_x},{y+70} H{mid_x} V{target_y} H{end_x}')
    return svg(s,label='六种方法围绕同一退货问题提供不同输入与支持')


add('帮助 Agent 理解业务的六种方法','这些方法可以组合，它们补足的内容并不相同',
    methods_graph(),
    'RAG 可以检索本体，工具也可以执行已经编码的业务规则',
    note='六种方法粒度不同，不是互斥选型。提示词聚焦任务，RAG 查找资料，微调改变参数，工具查事实或执行，专家补足业务决策，本体维护显式定义及关联。微调发生在训练阶段，不是每次提问的在线调用。')

add('不同方法的局限性','客服、仓库和财务，能否共同引用“申请、验收、退款”的含义？',
    methods_graph(True),
    '共享文档和词典也能统一口径；是否需要本体，还要看关联与复用的价值',
    note='这里没有证明本体是唯一方案。统一文档、业务词典、共享配置和规则服务也能解决共同口径。后面继续考察：跨对象、跨任务、跨系统的显式关系能否改善知识复用，收益是否值得维护投入。RAG 不局限于关键词匹配，本体也不能消除所有错误。')

# 08–17: ontology and its mechanisms
chapter('02','本体的<br>概念、技术与价值','先说清业务里有什么、各自是什么意思、怎样关联，<br>再讨论 Agent 如何使用。',['定义与表达','使用机制','标准与适用性'])

add('什么是本体（Ontology）','先用一个业务例子理解，再补上专业表达',
    '<div class="split"><div><p class="quote edit-text">把一块业务中重要的<br><span class="em">对象、含义、关系</span><br>及适用条件整理成<br>可共同使用、机器可处理的模型。</p></div><div>'
    +svg(node(35,12,590,95,'订单','一次购买形成的业务记录')
         +node(35,212,590,95,'退货申请','客户提出退回某个订单项的请求',cls='soft')
         +node(35,412,590,95,'退款单','记录退款请求及其处理状态')
         +edge(330,212,330,107,'针对订单中的明细',1,label_pos=(490,165))
         +edge(330,412,330,307,'关联退货申请',2,label_pos=(480,365)),700,540,'订单、退货申请与退款单的含义及关联')+'</div></div>',
    '专业表述：显式的领域概念化表达。定义、身份与关系共同支持复用。',
    note='显式，指含义和关系被明确表达。领域，指有界的一块业务。共同使用，指不同人和程序可引用同一身份及定义。自然语言说明帮助理解，稳定身份和结构化关系支持定位与关联。只将制度文档改名为本体不会自动得到这些能力。',sources=('rdf',))

add('用本体描述退货业务','先认识对象和关系骨架，稍后补齐条件、事实来源与动作前提',returns_graph(),
    '订单项是一条商品明细；“退货申请”这个概念与“申请 R001”这条记录分别表达',sources=('demo',),flag='业务模型示意')

add('本体中的基本表达','在同一小段业务中，读懂类别、个体、属性、关系和分类',
    '<div class="split wide-left"><div>'+svg(
        node(20,15,350,95,'售后申请')+node(20,207,350,95,'退货申请',cls='soft')
        +node(20,412,350,95,'申请 R001')+node(620,412,325,95,'订单项')
        +edge(195,207,195,110,'是其子类',1,'dashed',label_pos=(335,166))
        +edge(195,412,195,302,'属于该类',2,'dashed',label_pos=(335,367))
        +edge(370,460,620,460,'针对',3)
        +reveal(text(620,215,['属性：申请时间','一个日期时间值'],'small-text'),3,'g')
        +reveal(text(620,310,['RET-DEMO-v1','一份具体政策，也可作为个体'],'small-text'),4,'g'),970,540,'类别、子类、个体、属性与业务关系')+'</div><div class="stack">'
    +'<div class="rule-top"><p class="statement edit-text"><b>类</b>描述一类对象<br><b>个体</b>指一个具体资源</p></div>'
    +reveal('<p class="statement edit-text"><b>属性</b>连接值<br><b>关系</b>连接资源</p>',3)
    +reveal('<p class="small edit-text">虚线表示分类／类型关系<br>实线表示业务关系<br>业务说明同时保留范围、例外与未知</p>',4)+'</div></div>',
    '名字相似不等于含义相同；同一资源需要稳定身份',
    note='业务角色不等于登录权限。正式分类按实际需要使用，不把每个名词强行设为类。语义层可以包含政策等知识个体，但本项目不为 SQL 问答搬入业务表行。',sources=('rdf','demo'))

add('本体、知识图谱与数据库的分工','同一业务，在定义、知识连接和记录存储三个层面表达',
    svg(
        text(0,35,'本体：约定含义与关系','label')
        +text(0,85,'定义对象与可用关系','small-text')
        +node(500,0,310,95,'退货申请',cls='soft')
        +node(1180,0,310,95,'订单项',cls='soft')
        +edge(810,48,1180,48,'针对')
        +edge(655,95,420,265,'使用共同定义',1,label_pos=(535,175),path='M655,95 V155 H420 V265')
        +edge(1335,95,1335,265,'映射到字段与连接',1,label_pos=(1500,175))
        +reveal(text(0,235,'知识图谱：连接具体知识','label'),1,'g')
        +node(0,290,330,100,'RET-DEMO-v1','一份具体政策',step=1)
        +node(550,290,250,100,'普通商品',step=1)
        +node(0,470,330,75,'退货政策',step=1)
        +edge(330,340,550,340,'适用于',1)
        +edge(165,390,165,470,'属于该类',1,'dashed',label_pos=(275,440))
        +reveal(text(430,494,['概念定义也可保存在图中','图数据库可存储知识图谱'],'small-text',gap=40),2,'g')
        +reveal(text(955,235,'数据库：存储与查询记录','label')
            +text(955,278,'orders（虚构数据片段）','guide')
            +'<rect x="955" y="300" width="740" height="210" class="thin"/>'
            +'<path d="M955,355 H1695 M955,430 H1695 M1140,300 V510" class="thin"/>'
            +text(985,335,'id','small-text')+text(1180,335,'signed_at','small-text')
            +text(985,402,'A101','small-text')+text(1180,402,'2026-10-01 10:00+08:00','small-text')
            +text(985,477,'A102','small-text')+text(1180,477,'2026-09-27 10:00+08:00','small-text')
            +text(955,550,'业务行留在外部，schema 也可表达约束','guide'),1,'g'),label='上方本体定义、左下知识关系与右下外部订单表的关联'),
    '本项目将订单等业务行保留在外部数据库，平台保存业务语义及映射',
    note='知识图谱是知识组织方式，数据库是存储与查询系统，层次不同，技术并不互斥。本体可作为图中的概念定义，图数据库也可保存知识图谱，关系型 schema 也有约束表达能力。',sources=('rdf','r4'))

add('本体怎样帮助 Agent 工作','相关定义、关系和必要说明，合起来形成“语义上下文”',
    svg(
        node(610,0,500,115,'业务语义模型','政策、关系、条件与映射',cls='soft')
        +node(40,215,360,130,'用户问题','这笔订单能退吗？')
        +node(620,225,480,130,'消费 Agent','组织任务、核对条件、解释结果',cls='dark')
        +node(1320,220,350,140,'业务答案','问答／分析／操作建议')
        +node(470,460,330,100,'数据库与 API','取得实时事实')
        +node(930,460,360,100,'原始资料 RAG','需要时补充说明')
        +edge(400,280,620,280,'提出任务',1)
        +edge(850,225,850,115,'按权限读取',1,label_pos=(1000,175))
        +edge(720,355,635,460,'查询事实',2,label_pos=(600,410))
        +edge(1000,355,1100,460,'查原始依据',2,label_pos=(1170,408))
        +edge(1100,290,1320,290,'计算并解释',3),label='消费 Agent 读取语义、查询事实与组织答案'),
    '本体提供依据，Agent 组织任务与解释，外部系统提供事实并执行操作',
    note='数据映射说明业务含义对应哪个字段或连接。消费 Agent 是读取已建语义来完成任务的 Agent。知道动作前提不等于具有执行权限。语义访问控制与业务系统授权需要分别验证。',sources=('r4','demo'))

add('业务含义怎样表达与查询','RDF、RDFS、OWL 与 SPARQL 各有职责',
    '<div class="split wide-left"><div>'+svg(
        node(0,130,330,120,'RET-DEMO-v1','主体 subject',cls='soft')
        +node(620,130,300,120,'普通商品','客体 object')
        +edge(330,190,620,190,'适用于',label_pos=(475,165))
        +text(0,80,'RDF 以“主体、谓词、客体”表达陈述','label')
        +text(390,257,'谓词 predicate','guide')
        +text(0,370,['IRI：为资源提供可稳定引用的身份','Turtle：RDF 的一种书写格式'],'small-text',gap=50)
        +text(0,520,'教学词汇示意，不代表专用业务规则执行合同','guide'),950,562,'RDF 三元组示意')+'</div><div class="stack">'
    +'<div class="rule-top"><p class="statement edit-text"><b>RDFS</b>　基础类型与层级</p><p class="small"><code>rdf:type</code>　属于某类<br><code>rdfs:subClassOf</code>　子类</p></div>'
    +reveal('<div><p class="statement edit-text"><b>OWL</b>　更丰富的形式语义</p><p class="small edit-text">表达形式化公理及其含义</p></div>',1)
    +reveal('<div><p class="statement edit-text"><b>SPARQL</b>　查询 RDF 图</p><p class="small edit-text">找到符合图关系的资源与值</p></div>',2)+'</div></div>',
    '能机器读取业务说明，不等于其中所有条件已经形式化或能够自动执行',
    note='RDF 是图数据模型，RDFS 是基础类型及层级词汇，OWL 提供更丰富的形式化语义，SPARQL 查询 RDF。OWL 可以有 RDF 表示，但所有 RDF 并不都是 OWL 2 DL 本体。\n\nTurtle 教学代码：\n@prefix ex: <https://example.org/returns/> .\n@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\nex:ReturnRequest rdfs:subClassOf ex:AfterSalesRequest .\nex:RET-DEMO-v1 rdf:type ex:ReturnPolicy ; ex:appliesTo ex:StandardProduct .\n\n这里只表达类型和关系。168 小时时间窗仍作为普通业务条件说明保留。',sources=('rdf','owl','sparql'))

add('形式推理的作用与边界','由明确的形式前提推出隐含结论，与退款资格计算分别理解',
    '<div class="split wide-left"><div>'+svg(
        node(35,0,420,95,'业务申请')+node(35,205,420,95,'售后申请')
        +node(35,410,420,95,'退货申请',cls='soft')
        +edge(245,205,245,95,'子类',1,'dashed',label_pos=(345,160))
        +edge(245,410,245,300,'子类',1,'dashed',label_pos=(345,365))
        +edge(455,458,455,48,'可推出：子类',2,'ochre-edge',label_pos=(705,255),path='M455,458 H610 V48 H455')
        +text(645,350,['推导线独立显示','分类传递可由 RDFS 支持'],'small-text'),940,540,'分类层级与子类传递推导')+'</div><div class="stack">'
    +'<div class="rule-top"><p class="eyebrow">原理示意</p><p class="statement edit-text" style="margin-top:20px">显式前提<br>形式规则<br>隐含结论</p></div>'
    +reveal('<p class="small edit-text">时间比较与金额计算需计算能力。<br>业务流程由对应系统执行。<br>缺少事实，不自动意味着事实为假。</p>',2)
    +'<span class="pill demo">OntoWeave 当前不提供自动推理运行</span></div></div>',
    '分类推导不能单独证明某张订单可以退款',sources=('owl','rdf','retirement'),flag='原理示意',
    note='本页分类传递可由 RDFS 支持，OWL 能表达更丰富的公理。开放世界下未声明不等于为假。退款需要时间、类别、声明、验收、审批等事实，以及相应计算和业务系统。当前项目已退役自动推理运行，不展示或承诺推理回执。')

add('Ontology 的思想来源与工程应用','相关思想、表示方法与产品实践，有联系，也有各自的边界',
    svg(
        node(0,35,460,195,'思想来源','哲学：存在、类别与关系\n工程本体并非哲学问题的直接答案')
        +node(615,35,460,195,'知识表示','知识工程：显式领域模型\nRDF／RDFS／OWL 等提供表达方式',cls='soft')
        +edge(460,128,615,128,'概念借鉴',1,label_pos=(539,96))
        +node(1225,35,470,195,'企业应用','Foundry：连接数据、对象与操作\nOntology MCP：向 Agent 暴露能力')
        +edge(1075,128,1225,128,'工程应用',2,label_pos=(1150,96))
        +reveal(text(0,343,['哲学 ontology 关注存在。','工程 ontology 将领域概念显式表达。'],'small-text',gap=44),1,'g')
        +reveal(text(900,343,['Palantir 是重要产品应用案例，并非 ontology 的发明者。','Foundry 产品体系不等同于 OWL 本体或 OntoWeave。'],'small-text',gap=44),2,'g')
        +reveal(text(0,510,'“本体驱动 Agent”是利用显式业务语义的可选架构思路','label'),3,'g'),label='哲学、知识工程、语义技术与企业 Agent 应用的联系'),
    '这是一条理解联系的线索，不代表唯一或必经的技术演进路线',
    note='Palantir Foundry 将 Ontology 用作连接数据、业务对象和操作的组织运行层。Ontology MCP 是让 Agent 接入对象、动作与查询能力的官方实例。“本体驱动 Agent 架构”是本演示对设计思路的归纳，不声称行业已形成统一标准。OntoWeave 的业务执行仍在外部系统。',sources=('philosophy','foundry','mcp'))

add('本体的优势与适用条件','用“为什么还不能退款”连接客服、仓库与财务的任务',
    '<div class="split"><div><div class="rule-top"><h3 class="statement edit-text">共享口径已有轻量方案</h3><p class="statement edit-text" style="margin-top:30px">统一文档、业务词典、<br>共享配置与规则服务，<br>都能帮助多个应用复用定义。</p></div><p class="small edit-text" style="margin-top:40px">固定、简单的任务，可以继续使用更轻的方案。</p></div><div>'
    +svg(node(245,175,370,115,'同一业务语义模型','政策、订单项、验收与审批',cls='soft')
         +node(0,0,260,100,'客服 Agent','申请资格')+node(590,0,260,100,'仓库 Agent','验收要求')
         +node(270,420,310,100,'财务 Agent','退款前提')
         +edge(130,100,290,175,'引用适用条件',1,label_pos=(90,150))
         +edge(720,100,575,175,'引用验收含义',2,label_pos=(720,155))
         +edge(425,420,425,290,'引用审批与状态',3,label_pos=(605,370)),860,540,'三个消费 Agent 复用同一业务语义模型')+'</div></div>',
    '值得建模的地方，在于跨对象、跨任务、跨系统的显式关联能否改善实际复用',
    note='收益依赖定义准确、读取充分、持续维护和消费正确。先选择一个跨环节问题，同条件比较正确性、维护与人工确认成本，不许诺必然优于 RAG 或自动消除幻觉。',sources=('demo',))

# 18–25: platform and modeling method
chapter('03','OntoWeave<br>与建模方法','如何把业务材料变成可用的模型，<br>并让 Agent 可靠地取得它。',['系统分工','建模方法','自动建模','读取验证'])

add('OntoWeave 的定位与责任边界','平台保存与提供业务语义，业务判断和业务执行各有负责人',
    svg(
        node(0,35,360,125,'业务人员','确认含义、范围与歧义')
        +node(0,340,360,125,'建模 Agent','整理资料、提出模型')
        +node(610,195,480,150,'OntoWeave','保存业务语义模型\n管理写入与访问',cls='soft')
        +node(1320,35,375,125,'消费 Agent','读语义、查事实、处理任务')
        +node(1320,340,375,125,'外部业务系统','提供业务数据并执行操作')
        +edge(180,160,180,340,'确认与澄清',1,label_pos=(270,260))
        +edge(360,400,610,275,'提交语义模型',1,label_pos=(465,320))
        +edge(1320,95,1090,244,'按权限读取',2,label_pos=(1185,140))
        +edge(1510,160,1510,340,'独立业务授权',3,label_pos=(1400,265))
        +reveal(text(610,415,['平台边界：确定性检查、存储与读取','外部系统边界：数据访问、业务执行与回执'],'small-text',gap=45),3,'g'),label='业务人员、建模 Agent、平台、消费 Agent 与外部系统的责任分工'),
    '平台检查可执行性与资源完整性，业务含义仍由建模与独立验证确认',
    note='业务角色知识与应用访问控制是不同问题。消费 Agent 是使用已建知识完成业务任务的 Agent。平台不会因为保存了退款动作定义就拥有执行退款的权限或能力。',sources=('project','r4','retirement'))

architecture = (
    node(0,0,330,95,'管理界面','React / Vite')
    +node(445,0,345,95,'建模 Team','外部 Agent')
    +node(925,0,345,95,'消费 Agent','外部 Agent')
    +'<path d="M0,135 H1270 V595 H0 Z" class="thin" style="stroke-dasharray:7 6"/>'
    +text(22,164,'OntoWeave 平台边界','guide')
    +node(25,205,450,100,'页面／应用接口','FastAPI HTTP')
    +node(665,205,580,100,'Agent 工具接口','FastMCP')
    +node(25,370,1220,95,'共同应用服务','身份与范围授权　　写入前检查与应用　　语义查询与读取',cls='soft')
    +node(25,505,545,80,'PostgreSQL','元数据与工作状态')
    +node(705,505,540,80,'RDF / Oxigraph','业务语义图')
    +edge(165,95,250,205,'管理',path='M165,95 V180 H250 V205',label_pos=(210,125))
    +edge(620,95,790,205,'建模工具调用',path='M620,95 V180 H790 V205',label_pos=(620,125))
    +edge(1097,95,1097,205,'语义工具调用',label_pos=(1090,125))
    +edge(250,305,250,370,'')+edge(955,305,955,370,'')
    +edge(298,465,298,505,'')+edge(975,465,975,505,'')
    +node(1355,205,340,150,'外部业务库','订单、商品等业务行',cls='ochre')
    +node(1355,440,340,150,'外部业务 API','状态查询与业务执行',cls='ochre')
    +edge(1270,48,1525,205,'消费 Agent 独立访问',label_pos=(1490,140),path='M1270,48 H1525 V205')
    +edge(1270,75,1355,515,'独立业务授权',label_pos=(1525,402),path='M1270,75 H1310 V515 H1355')
    +'<g data-path-group="write">'+edge(790,305,790,370,'dry-run / apply',cls='ochre-edge',label_pos=(685,345))+'</g>'
    +'<g data-path-group="read">'+edge(1110,370,1110,305,'读取语义',label_pos=(1110,345))+'</g>'
)
add('系统架构','两个接口入口复用应用服务，外部业务库与业务 API 保持独立',
    '<div class="path-control"><button data-path="all" aria-pressed="true">全部</button><button data-path="write" aria-pressed="false">写入路径</button><button data-path="read" aria-pressed="false">读取路径</button></div>'
    +svg(architecture,1696,600,'OntoWeave 管理界面、HTTP、MCP、应用服务与双存储架构'),
    '业务数据与执行仍在平台外；dry-run 检查待写内容，apply 应用已确认的写入',
    note='MCP 是连接 Agent 与工具、数据的协议，当前由 FastMCP 提供入口。FastAPI HTTP 与 MCP 复用服务职责。PostgreSQL 保存元数据和工作状态，Oxigraph 保存 RDF 语义图。建模写入和消费读取是不同路径。外部业务库和 API 没有被平台存储层包住。',sources=('project','r4','retirement'))

add('建模方法论：先完成一条可验证的业务链','从问题确定范围，再逐步扩展，保留项目级共享定义与依赖',
    '<div class="flow" style="grid-template-columns:repeat(4,1fr)">'+''.join(
        reveal(f'<div class="step"><small>0{i+1}</small><b class="edit-text">{a}</b><p class="edit-text">{b}</p></div>',i)
        for i,(a,b) in enumerate([
            ('典型业务问题','“能申请，是否就能退款？”<br>这类问题称为能力问题 CQ'),
            ('逻辑切片','按业务目标、生命周期与依赖<br>分步分析和验证'),
            ('业务语义模型','先完成最小完整链<br>用七个视角检查覆盖'),
            ('实际读取与回答','检查消费者是否正确使用<br>再扩展相邻切片'),
        ]))+'</div>'
    +reveal('<div class="reading" style="margin-top:68px"><p class="edit-text">项目级始终保留：<b>共享术语、跨切片依赖、数据与接口映射、跨切片问题。</b><br>读取和回答中的缺口，返回业务澄清与语义修订。</p></div>',4),
    '切片是组织分析与验证的方式；不按表数量直接决定有几个本体',
    note='能力问题 Competency Question 是模型应当支持回答的业务问题。全面指在当前有界范围内处理重要概念、条件、例外和未知，不是一次建完整个企业。一个逻辑切片不自动对应一个 Ontology 或一个 Agent。',sources=('team','r4'))

VIEWS = [
    dict(title='对象：业务中讨论什么', description='订单、订单项、商品与退货申请。确认每个对象的含义、身份和必要关系。', nodes=['order','item','application']),
    dict(title='行为：有哪些业务动作', description='提交申请、审核和退款。明确动作作用对象与前提，不把动作定义当作已经执行。', nodes=['application','refund']),
    dict(title='规则：在什么条件下成立', description='普通商品、客户未使用声明、0—168 小时时间窗，以及退款所需验收与审批。', nodes=['policy','application','refund']),
    dict(title='角色：谁参与这段业务', description='客户、客服、仓库分别提出申请、确认审批、检查退回商品。业务角色不等于登录权限。', nodes=['application','refund']),
    dict(title='流程：前后阶段怎样衔接', description='申请、退回、验收与退款各有状态。申请可受理与退款完成分别由对应事实支持。', nodes=['application','refund']),
    dict(title='数据映射：含义对应哪个字段', description='签收时刻来自 orders.signed_at，商品类别来自 products.category，表间连接有明确业务含义。', nodes=['order','item','data']),
    dict(title='接口映射：哪个系统提供能力', description='售后状态查询、提交退货申请与执行退款分别对应外部接口，前提、权限和回执分别确认。', nodes=['application','refund','api']),
]
add('七个视角检查同一业务模型','同一模型，从含义、参与者、条件与系统连接等角度检查覆盖',
    '<div class="split wide-left"><div id="viewsGraph">'+svg(
        node(25,175,240,105,'订单',attrs='data-view-node="order"')
        +node(355,175,240,105,'订单项',attrs='data-view-node="item"')
        +node(710,175,250,105,'退货申请',cls='soft',attrs='data-view-node="application"')
        +node(340,0,270,105,'政策与条件',attrs='data-view-node="policy"')
        +node(710,405,250,105,'退款',attrs='data-view-node="refund"')
        +node(15,405,270,105,'数据映射',attrs='data-view-node="data"')
        +node(365,405,260,105,'接口映射',attrs='data-view-node="api"')
        +edge(265,228,355,228,'包含')+edge(710,228,595,228,'针对')
        +edge(475,105,835,175,'规定条件',label_pos=(760,110),path='M475,105 V135 H835 V175')
        +edge(835,405,835,280,'关联',label_pos=(900,350))
        +edge(150,405,150,280,'对应字段',label_pos=(235,350))
        +edge(625,457,710,457,'对应能力',label_pos=(670,365)),985,540,'从七个视角观察相同退货业务模型')+'</div><div>'
    +'<div class="view-buttons">'+''.join(f'<button data-view="{i}" aria-pressed="{"true" if i==0 else "false"}">{title}</button>' for i,title in enumerate(['对象','行为','规则','角色','流程','数据映射','接口映射']))+'</div>'
    +f'<div class="view-copy"><h3 class="edit-text" id="viewTitle">{VIEWS[0]["title"]}</h3><p class="edit-text" id="viewDescription">{VIEWS[0]["description"]}</p></div>'
    +'<p class="small" style="margin-top:30px"><span class="screen-only">点击视角查看。<br></span>各视角记录：<br>已确认／待澄清／本范围不适用。</p>'
    +'<p class="print-only small" style="margin-top:20px">行为：提交、审核、退款。规则：条件、范围与未知。角色：客户、客服、仓库。流程：申请至退款。映射：数据字段与外部能力。</p></div></div>',
    '七个视角检查同一业务，不要求七个 Ontology 或七个 Agent',
    note='规则视角保留完整业务条件，但当前不要求生成规则脚本。每个视角以源材料与业务确认作依据，明确已确认、待澄清或不适用，不能用表字段或编码样例猜测业务含义。',sources=('team','retirement','demo'))

add('Agent Team 的自动建模方式','生产协作与独立验收分别承担职责，业务歧义仍需业务确认',
    svg(
        text(0,30,'生产协作','label')
        +node(0,85,330,135,'建模 Modeling','读材料、澄清、提出模型')
        +node(445,85,345,135,'协调 Coordinator','切片、共享定义与反馈',cls='soft')
        +node(910,85,320,135,'出题 CQ','准备能力问题')
        +node(1355,85,340,135,'写入 Protocol','检查并应用')
        +edge(330,152,445,152,'协作',1)
        +edge(790,152,910,152,'核对',1)
        +edge(1230,152,1355,152,'提交',2)
        +text(0,290,'宿主监督 Delivery：授权、进度、交付与失败跟进','small-text')
        +'<path d="M0,335 H1696" class="thin"/>'
        +text(0,390,'独立验收','label')
        +node(500,420,400,105,'独立消费 Agent','只读已写入模型',step=3)
        +node(1160,420,400,105,'独立判定','核对业务依据与答案',step=3)
        +edge(900,472,1160,472,'提交业务答案',3)
        +reveal(text(0,466,['公开反馈可用于修订','隐藏答案保持隔离'],'small-text',gap=38),3,'g'),label='当前建模 Team 职责与生产外独立消费判定泳道'),
    '自动整理、建模和调用不替代业务确认；成功写入与业务语义通过分别证明',
    note='这里介绍当前 Team 的职责配置，不宣称所有场景都需要固定数量或顺序的 Agent。生产链可以按依赖协作。独立验收不能创建、继续或修复被验收的 run，也不能修改保留证据。正常成功写入信任平台回执，实际读取用于消费和语义验证。',sources=('team','feedback'))

add('消费 Agent 实际需要读到什么','把“语义上下文”展开为能支撑业务判断的内容',
    '<div class="split wide-left"><div>'+svg(
        node(230,185,390,115,'RET-DEMO-v1','政策身份与说明',cls='soft')
        +node(0,0,270,100,'普通商品','适用对象')+node(580,0,320,100,'申请与退款','条件与前提')
        +node(0,425,300,100,'数据映射','签收、类别、售后状态')
        +node(580,425,320,100,'范围与未知','声明、例外、必要事实')
        +edge(230,185,140,100,'适用于')+edge(620,185,740,100,'规定条件')
        +edge(230,300,150,425,'关联来源')+edge(620,300,740,425,'明确范围'),920,550,'语义读取需要关联政策、对象、条件与数据映射')+'</div><div>'+policy_card()+'</div></div>',
    '按权限读到必需内容，并检查分页与截断；读取状态不保证答案正确',
    note='本页是虚构内容与人可读展示形式，非真实接口响应，也不新增 API 字段。读取还应显示查询的授权范围、返回的相关定义及分页／截断提示。必要内容未读全时继续补读。权限过滤先于候选计数与遍历。平台读取受限、读取失败和外部事实缺失分别处理，不把它们都解释成事实不存在。',sources=('r4','demo'),flag='虚构内容与展示形式，非真实接口响应')

add('当前能力与验证边界','截至 2026-10-14，按需求及保留交付记录陈述',
    '<div class="status-rows">'
    '<div class="status"><div><h3 class="edit-text">已实现能力</h3><p class="date">当前需求与交付范围</p></div><p class="edit-text">多视角语义表达、共享定义、确定性写入、受治理读取，<br>以及数据与接口映射表达。<strong>工程检查通过，不等于业务效果已证明。</strong></p></div>'
    '<div class="status"><div><h3 class="edit-text">已有有界证据</h3><p class="date">2026-10-06 · 工业服务四切片</p></div><p class="edit-text">冻结题集独立验收：<strong>公开 18/18、隐藏 8/8</strong>。<br>仅覆盖当时获准模型与题集，不能作为当前通用准确率。</p></div>'
    '<div class="status"><div><h3 class="edit-text">仍待验证范围</h3><p class="date">10 月 13—14 日后续场景</p></div><p class="edit-text">后续运行存在未通过或未完成验收，R4.0-009 整体仍为 <strong class="partial">PARTIAL</strong>。<br>全范围、SQL/API 联合验收、跨场景重复性与产品化尚未完成。</p></div></div>'
    +footnote('当前不提供 OWL 自动推理、SHACL 专用校验、规则脚本或业务流程执行引擎。'),
    '历史有界通过保留原义，当前部分验证保留边界；本次没有重跑平台验收',
    note='2026-10-06 的两份完整公开／隐藏报告来自同生产状态和 freeze，互斥题集覆盖 26 题，157 引用重放稳定。这是有界历史结果，不代表全场景通过。10 月 13—14 日增量记录包含未完整通过、未完成及平台／运行阻断，不能一概归因于模型质量。R4.0-009 整体仍为 PARTIAL。L0 Runtime、L1 Modeling quality、L2 Repeatability、L3 Productization 分阶段判断。',sources=('r4','acceptance','retirement'),flag='已有记录摘要，本次未重新验收')

# 26–34: one complete, explicitly fictional case
chapter('04','电商退货与退款<br>模拟案例','一家小型电商，希望让客服 Agent 判断退货资格，<br>并说明退款的下一步。',['公开材料','确认口径','建立语义','取得事实','解释与验证'],demo=True)

add('模拟业务背景与输入材料','A 店 · 单件商品整件退货 · 商品款整额退款',
    '<div class="split"><div><p class="statement edit-text">政策与业务确认<br>术语解释<br>数据库字段与编码说明<br>售后接口合同<br>客户本次声明</p><p class="small edit-text" style="margin-top:28px">不涉及运费、促销分摊、部分退货、<br>跨境业务或法律解释。</p></div><div><p class="eyebrow">三个对照订单</p>'
    +fact('A101','10-01 10:00 签收<br>普通商品，声明未使用')
    +fact('A102','09-27 10:00 签收<br>普通商品，声明未使用')
    +fact('A103','签收时刻缺失<br>普通商品，声明未使用')
    +'<p class="small" style="margin-top:25px">拟申请／判断时点：<b>2026-10-06 10:00</b><br>全部时间为 UTC+08:00</p></div></div>',
    '先公开范围、政策与事实来源，后续每个判断才能逐项核对',
    note='模拟政策 RET-DEMO-v1 对三个订单均适用。假设订单归属、当前业务可访问范围和无重复申请已由业务系统确认；这不是语义授权的替代品。所有案例均为教学输入，不是实际平台运行。',sources=('demo',),flag='全部材料与订单均为虚构')

add('建模前的业务确认','字段名和样例值是映射线索，业务确认决定政策含义',
    '<div class="three-cols">'
    +topic('01','“七天内”','需要问：从哪一刻起算？<br>按日历日还是连续小时？<br><br><b class="em">确认：提交减签收，<br>0—168 小时，包含等号。</b>')
    +topic('02','“没使用就能退”','需要问：申请时怎样确认？<br>定制商品是否适用？<br><br><b class="em">确认：普通商品，<br>申请时采用客户未使用声明。</b>',1)
    +topic('03','“申请后退款”','需要问：还有哪些前提？<br>信息缺失怎样处理？<br><br><b class="em">确认：验收通过、客服批准。<br>缺必要事实时保留未知。</b>',2)+'</div>',
    '客户声明与实际验收分别记录；申请受理、具备退款条件和退款完成分别判断',
    note='created_at 不能仅凭名字解释为签收时刻。签收对应 orders.signed_at，类别编码 STANDARD/CUSTOM 的含义也由字段说明与业务确认给出。真实提交时由业务系统按真实时刻重检，教学比较用拟申请时刻。',sources=('demo',),flag='模拟商家已确认的教学口径')

add('业务切片与共享定义','把 P21 的方法具体化为三段范围，逐步完成同一业务链',
    '<div class="three-cols">'
    +topic('01','退货资格','确认适用商品、声明与时间窗。<br><br>首先回答：<br><b class="em">是否允许提出申请？</b>')
    +topic('02','退货处理','表达申请、退回与验收状态。<br><br>继续回答：<br><b class="em">商品实际状态如何确认？</b>',1)
    +topic('03','退款处理','表达审批、退款前提与接口。<br><br>跨环节回答：<br><b class="em">何时具备退款条件？</b>',2)+'</div>'
    +reveal('<div class="reading" style="margin-top:62px"><p class="edit-text">共同引用：<b>客户、订单项、商品、政策、状态含义，以及必要数据与接口映射。</b><br>首条链也需保留“可以申请与退款完成是不同阶段”这一共同语义。</p></div>',2),
    '三个逻辑切片是分析组织方式，不预设三套本体或三个 Agent',sources=('team','demo'),flag='案例建模设计')

add('退货与退款的语义模型','沿用 P10 的骨架，补上已经确认的条件、前提与映射',returns_graph(True),
    '关系用于定位相关知识，普通业务说明保留条件、范围、例外和未知',
    note='RET-DEMO-v1 适用于普通商品，申请条件为未使用声明及 0—168 小时。退款需验收通过、客服批准，执行仍受外部权限和防重复约束。这张图表达业务语义，不计算 A101 的资格，也不把 A101 行数据写入平台。',sources=('demo','retirement'),flag='教学语义模型，不是运行截图')

add('语义怎样连接 SQL 与 API','先按获准语义取得事实，再由外部系统控制业务执行',
    '<div class="split"><div class="stack"><div class="rule-top"><p class="eyebrow">查询事实</p><p class="statement edit-text" style="margin-top:20px">签收时刻 → <code>orders.signed_at</code><br>商品类别 → <code>products.category</code></p><p class="small" style="margin-top:24px">订单项通过 <code>order_id</code> 与 <code>product_id</code><br>连接订单和商品。语义映射约束 SQL。</p></div>'
    +'<div class="reading"><p class="edit-text">声明来自<b>客户本次输入</b>。<br>验收、审批与退款状态来自<b>外部售后查询接口</b>。</p></div></div><div class="stack">'
    +'<div class="rule-top"><p class="eyebrow">执行动作</p><p class="statement edit-text" style="margin-top:20px">提交申请 → <code>POST /returns</code><br>执行退款 → <code>POST /refunds</code></p><p class="small" style="margin-top:24px">外部系统检查条件、业务权限与防重复。<br>语义知识中的前提，不授予操作权限。</p></div>'
    +'<div class="reading"><p class="edit-text"><code>ACCEPTED</code> 只表示退款请求受理。<br><code>SUCCEEDED</code> 才表示系统确认完成。</p></div></div></div>',
    'SQL、时间计算工具和 API 都是教学设计，本次没有接入或调用退款系统',
    note='先读取获准语义和真实 schema，才能在定义、连接与口径约束下生成 SQL。业务库行列访问控制由外部系统负责。示例查询：\nSELECT o.signed_at, p.category\nFROM order_items oi\nJOIN orders o ON oi.order_id = o.id\nJOIN products p ON oi.product_id = p.id\nWHERE o.id = :order_id AND oi.id = :item_id;\n\n售后事实来自 GET /order-items/{id}/after-sales-context，三字段是 inspection_status、approval_status、refund_status。时间差由日期计算工具给出。真正提交由外部系统重检，操作受理不等于完成。上述接口不是 OntoWeave 新增接口。',sources=('demo','r4'),flag='虚构外部字段与接口')

add('案例一：能申请，为什么不能马上退款','A101 · RET-DEMO-v1 · 2026-10-06 10:00+08:00 的模拟判断',
    '<div style="display:grid;grid-template-columns:480px 560px 1fr;gap:45px;height:100%">'
    +'<div>'+policy_card(True)+'</div><div>'
    +'<p class="eyebrow">取得具体事实</p>'
    +fact('订单库','10-01 10:00 签收<br>普通商品')
    +fact('客户输入','声明未使用')
    +fact('计算工具','间隔 <b class="em">120 小时</b><br>0 ≤ 120 ≤ 168')
    +fact('售后接口','验收尚未开始<br>审批尚未申请<br>无退款记录')+'</div><div>'
    +reveal('<div class="result-panel"><h3 class="edit-text">按当前政策和您的未使用声明，<br>可以申请退货。</h3><p class="edit-text">实际商品状态仍待验收。<br>当前尚未验收，也尚未获客服批准，<br><b>不能立即退款。</b></p></div>',1)
    +reveal('<p class="small edit-text" style="margin-top:28px">下一步：如决定申请，由业务系统<br>在实际提交时重检条件与权限。</p>',2)+'</div></div>',
    '可申请、已提交、具备退款条件、退款完成是不同阶段',
    note='签收与类别来自模拟订单库，声明来自客户，时间差来自计算工具。售后接口明确返回 inspection_status=NOT_STARTED、approval_status=NOT_REQUESTED、refund_status=NONE，所以“尚未”有明确依据，不是从空结果猜测。若值缺失或查询失败，则改为暂无法确认并指出待补事实。未进行实际提交或退款。',sources=('demo',),flag='教学推演，非真实运行结果')

add('案例二：超时与信息不足','相同政策，对明确不满足与无法判断分别回答',
    '<div class="split">'
    +'<div class="topic"><p class="eyebrow">A102 · 超时</p><div class="stat" style="margin-top:26px">216 <small>小时</small></div>'
    +'<p class="small" style="margin-top:20px">09-27 10:00 签收，10-06 10:00 拟申请。<br>普通商品，客户声明未使用。</p>'
    +reveal('<div class="result-panel" style="margin-top:30px;border-color:var(--ochre);background:var(--light-ochre)"><h3 class="edit-text">超过 168 小时，<br>不符合本例政策时间条件。</h3><p class="edit-text">解释明确不满足的条件，<br>不编造退款阶段事实。</p></div>',1)+'</div>'
    +'<div class="topic"><p class="eyebrow">A103 · 必要信息缺失</p><div class="stat" style="margin-top:26px;color:var(--muted)">未知</div>'
    +'<p class="small" style="margin-top:20px">签收时刻缺失，无法计算间隔。<br>普通商品，客户声明未使用。</p>'
    +reveal('<div class="result-panel" style="margin-top:30px"><h3 class="edit-text">暂无法判定时间条件，<br>需要补充签收时刻。</h3><p class="edit-text">保留未知并提出补问，<br>不将未知改写成允许或拒绝。</p></div>',2)+'</div></div>',
    '明确不满足的条件可以支持否定结论；必要条件尚未确定时保留相应未知',
    note='A102 有明确超时事实，可解释该条件不满足。A103 只缺少签收时刻，不能据此宣称被拒绝或仍在时间窗内。材料冲突、平台读取失败、权限拒绝与外部事实缺失应分别说明。',sources=('demo',),flag='教学预期，未运行真实验收')

add('怎样验证建模效果','独立检查含义、实际读取与业务回答，避免把写入成功当作质量证明',
    '<div class="check-line">'+''.join(f'<div class="check-stage"><b class="edit-text">{a}</b><p class="edit-text">{b}</p></div>' for a,b in [
        ('资料依据','先确定能力问题、适用范围<br>和可核对的判定依据'),
        ('模型表达','概念、关系、条件、例外<br>与未知是否忠于资料'),
        ('实际检索','在真实授权接口读取<br>必需内容是否取得'),
        ('业务答案','独立消费 Agent 回答<br>独立判定核对依据'),
    ])+'</div>'
    +'<div class="compare-note"><b>同条件比较</b><p class="edit-text">RAG 与本体辅助方案共用相同资料、澄清结果、政策版本、数据快照、题目、工具与权限。<br>尽量固定语言模型及调用条件，改变知识组织与读取方式。</p></div>'
    +'<div class="expected"><span>A101：可申请，不能立即退款</span><span>A102：超时</span><span>A103：补问</span><span>168 小时：含等号</span></div>'
    +footnote('分别记录错误允许、错误拒绝、应补问却强答与合理未知，以及建模、维护、确认和运行成本。'),
    '显式语义连接依据，外部事实支持结论，业务系统控制执行，独立验证检查整条链',
    note='正式验证覆盖正常、边界、未知、跨切片和权限。边界还包括负间隔、0、168 小时加 1 秒、定制、已使用／声明缺失、审批缺失、重复退款及 ACCEPTED/SUCCEEDED 区别。这些只是待验证设计。不能只给本体方案补全业务规则，再将所有收益归因于本体。本页无真实提升比例。',sources=('demo','r4'),flag='验证设计与教学预期')

# 35–37: FAQ, outside the four chapters
def faq(items, cls=''):
    return f'<div class="qa {cls}">'+''.join(
        f'<details open {"id="+chr(34)+"maintenanceQuestion"+chr(34) if maintenance else ""}><summary class="edit-text">{q}</summary><div class="answer edit-text">{a}</div></details>'
        for q,a,maintenance in items)+'</div>'


add('FAQ：什么时候值得使用本体','先看当前任务与已有方案，再决定是否增加显式语义建模',
    faq([
        ('已经有 RAG，还需要本体吗？','文档检索已能稳定回答时，可以继续使用。跨对象、跨任务的关系需要明确复用时，可试用本体并做同条件比较。',False),
        ('直接把业务规则写进提示词不行吗？','小范围任务可以。文档、词典和规则服务也能共享口径。显式关联带来的复用收益值得投入时，再进一步建模。',False),
        ('本体会替代数据库或业务系统吗？','业务记录与操作仍留在原系统。本体提供业务含义、关系、条件及系统映射。',False),
        ('所有业务都要先建本体吗？','优先选择含义歧义多、跨系统关系多、同一定义被反复使用的场景。简单固定任务可以采用更轻的方案。',False),
    ],'full')+'<nav class="backlinks"><a href="#7" data-go="7">回看方法局限 P07</a><a href="#12" data-go="12">回看系统分工 P12</a><a href="#17" data-go="17">回看适用条件 P17</a></nav>',
    '从一个有代表性的跨环节问题试起，比较正确性与实际投入',
    note='本页四问可点击问题收起或展开。收益比较应共用材料、业务澄清、语言模型、题目、数据与工具条件。选择本体的依据是实际复用、理解和维护收益，而不是仅因为它看起来更结构化。')

add('FAQ：怎么建，哪些工作需要人参与','从一条有界业务链开始，按实际依赖安排分工',
    faq([
        ('必须先学会 RDF 和 OWL 吗？','业务人员先确认概念与口径，技术人员选择表达及查询方式。理解本体不要求先写 OWL，当前项目也不要求自动推理。',False),
        ('七个视角意味着七个本体或七个 Agent 吗？','它们是检查同一业务的不同角度。切片、存储和人员分工按实际依赖安排。',False),
        ('Agent 能全自动把模型建好吗？','可以自动整理资料、提出模型并调用平台。资料缺失、口径冲突与授权仍需确认，质量由独立验证判断。',False),
        ('是否需要一次建完整个企业？','先完成一条有代表性、可验证的业务链，再维护共享定义，并逐步扩展相邻切片。',False),
    ],'full')+'<nav class="backlinks"><a href="#21" data-go="21">建模方法 P21</a><a href="#22" data-go="22">七个视角 P22</a><a href="#23" data-go="23">Team 分工 P23</a></nav>',
    '自动化承担整理与调用，业务人员确认含义，独立验证判断是否可用',sources=('team','retirement'))

add('FAQ：怎样保证质量并持续维护','定义、事实、检索和使用都需要检查；政策变更还需外部系统对齐',
    '<div class="faq-layout"><div>'+faq([
        ('有了本体就不会产生幻觉了吗？','源材料、模型、检索与 Agent 使用都可能出错。需要逐环节验证，也允许合理回答未知。',False),
        ('业务规则变了，是否要全部重建？','业务负责人确认新口径、生效时间和范围，再修订相关定义及映射，检查受影响问题。修改范围由实际依赖决定。',True),
        ('怎样评估成本与收益？','同资料、同澄清、同工具比较正确性和完整性，分别记录建模、维护、人工确认与调用成本。',False),
        ('本体权限能保护数据库和退款吗？','语义权限控制语义知识。数据库行列访问与退款操作权限由外部系统执行，必须分别验证。',False),
    ],'full')+'</div><aside class="faq-aside"><div class="maintenance visible" id="maintenanceDiagram"><h3>政策变更示例</h3><p class="version">168 → 240 小时</p><p>自 <b>2026-11-01 00:00+08:00</b><br>起提交的申请采用 v2。<br>此前提交的仍按 v1。</p><p>业务负责人确认<br>维护者修订语义<br>系统负责人对齐执行<br>独立验证新旧边界</p><p class="micro">独立教学变更，不改变前三例。<br>不代表自动影响分析或任意历史版本读取功能。</p></div></aside></div>',
    '结合你的业务继续讨论：哪些含义、关系与判断，最需要共同引用？',
    note='v2 假设只将时间窗从 168 改为 240 小时，以提交申请时刻决定新旧政策，而非签收时刻。维护者保留解释旧申请所需的 v1 定义，检查相关条件与数据／接口映射，外部系统负责人对齐实际执行，再独立验证新旧适用范围、240 小时及加 1 秒、缺提交时刻等问题。这是人和 Agent 的维护工作，不承诺平台自动计算影响或固定读取同一资源任意历史版本。A101—A103 的 v1 结论保持原义。',sources=('demo','r4'),flag='v2 为独立教学维护示例')


def section_name(n):
    if n <= 2:
        return '概念、系统设计与业务案例'
    if n <= 7:
        return '01 / Agent 的业务理解难题'
    if n <= 17:
        return '02 / 本体的概念、技术与价值'
    if n <= 25:
        return '03 / OntoWeave 与建模方法'
    if n <= 34:
        return '04 / 电商退货与退款模拟案例'
    return '常见问题 FAQ'


def plain(s):
    return html.unescape(re.sub('<[^>]+>', '', s.replace('<br>', ' ')))


def make_sources():
    cache = HERE / 'project-sources.json'
    if not cache.exists() or '--refresh-sources' in sys.argv:
        excerpts = {}
        specs = [
            ('project','README.md','## Project Name','## Repository Layout'),
            ('r4','docs/requirements/requirements-v4.0.md','### R4.0-009 ','**后续授权收回**'),
            ('acceptance','docs/delivery/records/2026-10-06-v4-glmflash-semantic-acceptance-record.md','## 最新：','## '),
            ('retirement','docs/requirements/requirements-v4.0.md','### R4.0-025 ','#### 2.'),
            ('team','modeling_team/skills/README.md',None,None),
            ('feedback','docs/requirements/requirements-v4.3.md','### R4.3-015 ','### R4.3-016 '),
        ]
        for key,path,start,end in specs:
            content=(ROOT/path).read_text()
            if start:
                content=content[content.index(start):]
                # Search beyond the first heading, even when end is a generic heading.
                stop=content.find(end,len(start)) if end else -1
                if stop>=0:
                    content=content[:stop]
            excerpts[key]=dict(path=path,text=content[:15000].rstrip())
        cache.write_text(json.dumps(excerpts,ensure_ascii=False,indent=2)+'\n')
    excerpts=json.loads(cache.read_text())
    content=''.join(f'<section id="{key}"><h2>{e(SOURCES[key][0])}</h2><p class="origin">原始路径：<code>{e(item["path"])}</code> · 2026-10-14 内容摘录</p><details open><summary>查看原文摘录</summary><pre>{e(item["text"])}</pre></details></section>' for key,item in excerpts.items())
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>来源与项目证据 · 本体与 Agent</title><style>body{max-width:1100px;margin:60px auto;padding:0 30px;background:#f5f3ec;color:#16382e;font:18px/1.8 sans-serif}h1{font-size:38px}h2{font-size:27px;margin-top:60px}a{color:#2c7053}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.8 monospace;background:#e9ede2;padding:25px}.origin{color:#617068;font-size:15px}section{scroll-margin-top:30px}</style><a href="index.html">返回演示入口</a><h1>来源与项目证据</h1><p>以下为制作时的项目文件摘录。历史通过、当前部分验证与教学案例分别保留。外部标准及产品事实的原始来源见逐页讲解备注。</p>'+content+'</html>'
    (HERE/'sources.html').write_text(page.replace('<meta charset="utf-8">','<meta charset="utf-8"><link rel="icon" href="data:,">',1))
    return page


def font_css(body):
    if '--refresh-fonts' in sys.argv:
        from fontTools import subset
        from fontTools.ttLib import TTFont
        for dest,src in [
            ('sans-regular.woff','NotoSansCJK-Regular.ttc'),
            ('sans-bold.woff','NotoSansCJK-Bold.ttc'),
            ('serif-bold.woff','NotoSerifCJK-Bold.ttc'),
        ]:
            font=TTFont('/usr/share/fonts/opentype/noto/'+src,fontNumber=2)
            options=subset.Options()
            options.flavor='woff'
            sub=subset.Subsetter(options=options)
            sub.populate(text=body+'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz＋−／→≤≥？—·×')
            sub.subset(font)
            font.flavor='woff'
            font.save(HERE/'assets'/dest)
    css=(HERE/'deck.css').read_text()
    for token,name in [('SANS_REGULAR','sans-regular.woff'),('SANS_BOLD','sans-bold.woff'),('SERIF_BOLD','serif-bold.woff')]:
        data=base64.b64encode((HERE/'assets'/name).read_bytes()).decode()
        css=css.replace('__'+token+'__','data:font/woff;base64,'+data)
    return css


def write_index():
    groups=[('封面与目录',1,2),('01 · Agent 的业务理解难题',3,7),('02 · 本体的概念、技术与价值',8,17),('03 · OntoWeave 与建模方法',18,25),('04 · 电商退货与退款模拟案例',26,34),('常见问题 FAQ',35,37)]
    sections=''
    for title,start,end in groups:
        cards=''.join(f'<a class="page" href="editorial.html#{i}"><img loading="lazy" src="previews/{i:02}.png" alt="第 {i} 页：{e(plain(SLIDES[i-1]["title"]))}"><span><em>{i:02}</em>{e(plain(SLIDES[i-1]["title"]))}</span></a>' for i in range(start,end+1))
        sections+=f'<section><h2>{e(title)}</h2><div class="grid">{cards}</div></section>'
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>本体与 Agent · OntoWeave 演示</title><style>
    *{box-sizing:border-box}body{margin:0;background:#f5f3ec;color:#16382e;font:18px/1.6 'Noto Sans CJK SC',sans-serif}main{max-width:1480px;margin:0 auto;padding:55px 55px 80px}header{border-top:2px solid #73927e;padding-top:20px}header small{letter-spacing:2px;color:#617068}h1{font-family:'Noto Serif CJK SC',serif;font-size:52px;line-height:1.5;margin:40px 0 15px}header p{color:#617068}nav{display:flex;gap:15px;flex-wrap:wrap;margin-top:32px}nav a{padding:12px 23px;color:#16382e;border:1px solid #73927e;text-decoration:none}nav a.primary{background:#16382e;color:#f5f3ec}section{margin-top:70px}h2{font-size:25px;font-weight:400;border-bottom:1px solid #bfccbf;padding-bottom:18px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:28px}.page{color:inherit;text-decoration:none;display:block}.page img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#e1e9dc;border:1px solid #d2dacb}.page span{display:flex;gap:13px;line-height:1.6;font-size:16px;margin-top:10px}.page em{font-style:normal;color:#73927e;font-variant-numeric:tabular-nums}.page:hover img{outline:2px solid #2c7053}.usage{font-size:16px;color:#617068;border-top:1px solid #bfccbf;padding-top:28px;margin-top:60px}a:focus-visible{outline:3px solid #9c6c36}@media(max-width:800px){main{padding:25px}.grid{grid-template-columns:repeat(2,1fr)}h1{font-size:35px}}@media(max-width:500px){.grid{grid-template-columns:1fr}}
    </style><main><header><small>ONTOWEAVE · 2026.10.14</small><h1>本体如何帮助 Agent<br>理解与处理业务</h1><p>概念、系统设计与业务案例 · 37 页，四章正文与 12 个 FAQ</p><nav><a class="primary" href="editorial.html">开始演示</a><a href="editorial.pdf">阅读 PDF</a><a href="speaker-notes.md">逐页讲解备注</a><a href="case-materials.md">教学材料</a><a href="sources.html">项目来源摘录</a></nav></header>'''+sections+'''<div class="usage">方向键或空格分步展示。A 展开当前页，N 讲解备注，G 返回目录，F 全屏，E 编辑正文，Ctrl+S 下载修改后的 HTML。<br>电商案例为虚构教学推演，未接入真实订单或退款系统。项目状态按 2026-10-14 保留记录陈述。</div></main></html>'''
    (HERE/'index.html').write_text(page.replace('<meta charset="utf-8">','<meta charset="utf-8"><link rel="icon" href="data:,">',1))


def main():
    assert len(SLIDES)==37, len(SLIDES)
    plan_path=HERE/'source-plan.md'
    if not plan_path.exists():
        plan_path.write_bytes((ROOT/'docs/presentations/2026-10-14-ontology-agent-next-version-plan.md').read_bytes())
    plan=plan_path.read_text()
    case=plan.split('## 四、模拟业务的一致性底稿\n',1)[1].split('## 五、',1)[0]
    (HERE/'case-materials.md').write_text('# 电商退货与退款：虚构教学材料\n\n本文件用于核对演示 P24、P27—P34 及 P37 的统一口径。不是平台运行报告，也不是行业或法律规定。\n\n'+case)
    notes=[]
    for n,slide in enumerate(SLIDES,1):
        match=re.search(rf'### P{n:02}｜[^\n]+\n(.*?)(?=\n### P|\n## |\Z)',plan,re.S)
        extra=[]
        if match:
            for label in ('讲解深度','技术备注','承接下一页'):
                line=re.search(rf'- \*\*{label}：\*\* (.*)',match.group(1))
                if line:
                    extra.append(('转场：' if label=='承接下一页' else '')+re.sub(r'\[([^]]+)\]\([^)]+\)',r'\1',line.group(1)).replace('**',''))
        note=slide['note']+'\n\n'+'\n\n'.join(extra)
        notes.append(dict(page=n,title=plain(slide['title']),text=note.strip(),sources=[dict(title=SOURCES[x][0],href=SOURCES[x][1]) for x in slide['sources']]))
    (HERE/'speaker-notes.json').write_text(json.dumps(notes,ensure_ascii=False,indent=2)+'\n')
    note_md='# 本体与 Agent：逐页讲解备注\n\n37 页，四章正文与 FAQ。案例为虚构教学推演，项目状态为 2026-10-14 记录摘要。\n\n'
    for item in notes:
        note_md+=f'## P{item["page"]:02} · {item["title"]}\n\n{item["text"]}\n\n'
        if item['sources']:
            note_md+='来源：'+'、'.join(f'[{x["title"]}]({x["href"]})' for x in item['sources'])+'\n\n'
    (HERE/'speaker-notes.md').write_text(note_md)
    sources_page=make_sources()
    parts=[]
    for n,slide in enumerate(SLIDES,1):
        long=' long' if len(plain(slide['title']))>26 else ''
        chapter_markup=f'<div class="chapter-no" aria-hidden="true">{slide["chapter"]}</div><div class="chapter-kicker">第 {int(slide["chapter"])} 章</div>' if 'chapter' in slide else ''
        parts.append(f'''<section class="slide {slide['cls']}" id="slide-{n}" aria-label="第 {n} 页：{e(plain(slide['title']))}">
<div class="mast"><span>OntoWeave <span style="font-weight:400">／ 织义</span></span><span class="section-name">{section_name(n)}</span></div>{chapter_markup}
<h1 class="page-title edit-text{long}">{slide['title']}</h1><p class="lead edit-text">{slide['lead']}</p>
<div class="body">{slide['body']}</div>{slide.get('extra','')}
<p class="takeaway edit-text">{slide['takeaway']}</p><div class="footer"><span class="flag">{slide['flag'] or '本体与 Agent'}</span><span>{n:02} / 37</span></div></section>''')
    markup='\n'.join(parts)
    css=font_css(markup+note_md+plan+sources_page+(HERE/'deck.js').read_text())
    definitions='''<svg width="0" height="0" aria-hidden="true" style="position:absolute"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" stroke="#73927e" stroke-width="1.6"/></marker><marker id="type-arrow" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="9" markerHeight="9" orient="auto-start-reverse"><path d="M1,1 L11,6 L1,11 Z" fill="#f5f3ec" stroke="#73927e" stroke-width="1.4"/></marker><marker id="ochre-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M1,1 L9,5 L1,9" fill="none" stroke="#9c6c36" stroke-width="1.6"/></marker></defs></svg>'''
    controls='''<nav id="toolbar" aria-label="演示控制"><button id="prevButton" title="上一步">←</button><input id="pageInput" type="number" min="1" max="37" value="1" aria-label="跳转到页码"><span class="total">/ 37</span><button id="nextButton" title="下一步">→</button><button id="contentsButton">目录</button><button id="expandButton">展开</button><button id="notesButton">备注</button><button class="optional" id="editButton" aria-pressed="false">编辑</button><button class="optional" id="saveButton">保存</button><button class="optional" id="fullscreenButton">全屏</button><button id="helpButton" aria-label="快捷键帮助">?</button></nav><div class="progress-track" aria-hidden="true"><i id="progress"></i></div>
<aside id="notesPanel" aria-label="讲解备注与来源" hidden><button id="closeNotes" aria-label="关闭备注">×</button><h2 id="noteTitle"></h2><div id="noteText" class="notes-copy"></div><div id="noteSources" class="note-sources"></div></aside>
<aside id="helpPanel" aria-label="演示快捷键" hidden><button id="closeHelp" aria-label="关闭帮助">×</button><h2>演示快捷键</h2><p><kbd>→</kbd> <kbd>空格</kbd> 下一步或下一页<br><kbd>←</kbd> 上一步或上一页<br><kbd>A</kbd> 展开本页　<kbd>N</kbd> 讲解备注<br><kbd>G</kbd> 目录　<kbd>F</kbd> 全屏<br><kbd>E</kbd> 编辑正文　<kbd>Ctrl+S</kbd> 下载 HTML<br><kbd>Home</kbd> 首页　<kbd>End</kbd> 末页<br><kbd>Esc</kbd> 关闭面板或退出编辑<br>手机横屏可左右滑动翻页。</p></aside><div id="toast" role="status" hidden></div>'''
    safe_json=lambda obj:json.dumps(obj,ensure_ascii=False).replace('</','<\\/')
    page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="本体如何帮助 Agent 理解与处理业务。37 页互动演示，四章正文与 FAQ。OntoWeave（织义）。"><title>本体与 Agent · OntoWeave</title><style>{css}</style></head><body>{definitions}<main id="viewport"><div id="stage">{markup}</div></main>{controls}<script type="application/json" id="speakerNotes">{safe_json(notes)}</script><script type="application/json" id="viewData">{safe_json(VIEWS)}</script><script>{(HERE/'deck.js').read_text()}</script></body></html>'''
    (HERE/'editorial.html').write_text(page.replace('<meta charset="utf-8">','<meta charset="utf-8"><link rel="icon" href="data:,">',1))
    write_index()
    manifest=dict(title='本体如何帮助 Agent 理解与处理业务',date='2026-10-14',slides=37,chapters=4,faq=12,pages=[dict(page=i,title=plain(x['title']),section=section_name(i)) for i,x in enumerate(SLIDES,1)])
    (HERE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(f'Built {len(SLIDES)} slides · {len(page.encode()):,} bytes · offline fonts embedded')


if __name__=='__main__':
    main()
