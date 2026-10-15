# R4.3-026 材料与任务实现检查

依据：[权威需求](../../requirements/requirements-v4.3.md#r4-3-026)。用户后续明确要求实施。
基线 HEAD `b6e6c7e`；工作区原有 README.md、docs/presentations/、slide-deck/ 改动不属本次。

已完成材料／Task 交付和开发合同检查；**没有启动真实模型、生产 run、平台写入或独立
语义验收**。没有恢复暂停运行或消耗建模轮次，不把配置检查称为真实 L0／L1 PASS。

## 实现与边界

- [新场景及操作说明](../../evaluation-scenarios/minimal-installation-chain/README.md)：
  唯一自足业务说明，Source ID `minimal-installation-chain-source-v1`，输入清单含 SHA256；
  复用历史人工素材定义，未补写工业服务真值。
- [独立 Task](../../../modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml)与
  [独立 Profile](../../../modeling_team/profiles/r4-3-026-minimal-installation-chain.yaml)：
  复用024／025直接提交及既有CQ生命周期，三个现有角色，未增加Protocol前置门或恢复实验。
- 专用角色包、Modeling Skill和精简表示合同替代通用全量初读；CQ仅接收本任务四道未审阅
  私有草题，业务证据仍引用唯一业务源。正常审阅、新冻结及独立只读 Consumer／Judge不变。
- 场景说明保留“最小链→资产—故障—工单小链→完整工业服务”的独立回归顺序、原checkpoint
  用途及逐层未验证边界，列明既有计时／019用量采集要求，缺值unknown，不设新预算。

初始材料交付阶段未修改平台接口、编排、存储、通用角色包或原场景；本次启动前兼容修复仅改
`modeling_team` 的模型路由与 Runner，无backend/frontend改动，不需要全后端／前端套件或服务重启。
新测试只检验配置、数据合同和离线prepare路径，
不是新验收器或语义裁判。

## 2026-10-15 启动前模型绑定兼容修复

首次 `glm-5.3-flash/high` 预启动在未创建 semantic-start、未写入平台前失败；公开错误记录为
`workspaces/modeling-runs/.host-launches/r4326-20261015-glmhigh-start1.err.log` 中的
`missing roster role bindings: minimal-chain-competency-question, minimal-chain-coordinator, minimal-chain-modeling`。
精简包的 `package.yaml.role` 已声明为 `competency-question`、`coordinator`、`modeling`，而
Model Profile 仍按语义角色键控。修复让 prepare 按该已声明 role 解析现有绑定，并只在 Runtime
入口投影为 canonical package key；原始 package、baseline 和 profile YAML 均保持不变。

修复回归覆盖 `glm-flash-high` 对三项精简包的 prepare 与 Runtime key 投影；validate、baseline
及相关 Runner／Runtime 测试通过。此次是平台路由兼容修复，不计语义建模轮次，也不代表真实
semantic-start、模型质量或独立语义验收已通过。

v2 loader仍要求protocol_tools非空，新Task以一个只读工具名满足现有配置合同；实际
roster没有Protocol，不产生平台写入路径或额外角色。这次仅增加任务，不扩展loader。

## 材料规模

通过既有配置loader读取两个Task/Profile，按角色去重累计：角色说明、声明references、
全部required_skills目录内文件、授予该角色的role_sources。数字是配置可见材料的UTF-8
文件字节，不含Runner动态消息、工具目录、对话、独立验收或Host材料；不是token／费用、
实际初读token或运行耗时，不据此宣称提速已验证。

| 角色 | 原资产—故障—工单配置文件数／字节 | 新配置文件数／字节 |
| --- | ---: | ---: |
| Coordinator | 8／131909 | 4／23238 |
| Modeling | 20／392245 | 5／24706 |
| Protocol | 9／332494 | 未配置 |
| CQ | 8／67289 | 4／19740 |

各角色总字节由923937降至67684，约减少92.7%；角色间共有材料按各自实际挂载重复计数。
这是材料差异证据，真实成本仍待授权运行。既有独立验收Runtime/Skill沿用，未计入这组生产
与CQ材料统计，也未为这次材料缩减修改。

## 开发检查

1. `env -u DEEPSEEK_API_KEY uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r4-3-026-minimal-installation-chain.yaml --task modeling_team/tasks/r4-3-026-minimal-installation-chain.yaml`
   通过；绑定正确task_id/profile_id与Coordinator、Modeling、CQ roster，未绑定模型选择。
2. `python /home/yangxiang/.codex/skills/.system/skill-creator/scripts/quick_validate.py modeling_team/skills/minimal-chain-modeling`
   通过。只证明Skill格式。
3. 在backend执行：

   ```sh
   env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest \
     ../modeling_team/tests/test_r4326_minimal_chain.py \
     ../modeling_team/tests/test_direct_modeling_wiring.py \
     ../modeling_team/tests/test_r3011_g3_cq_routing.py \
     ../modeling_team/tests/test_r3006_unified_binds.py -q --tb=short
   ```

   **31 passed，6.39秒**，日志`/tmp/r4-3-026-contract-tests.log`。其中新测试7项：配对加载与
   源摘要；精简字段与既有合同一致；草题可形成当前CQ草稿；Runner真实prepare的逐角色源
   文件／初读清单／摘要、直接提交能力与版本冻结；三个旧Task仍按原Profile可加载。
   prepare使用CapturingAdapter与临时记录，未启动Agent／模型／平台，不证明OS运行隔离或
   真实应用效果。相邻回归覆盖直接能力接线、CQ路由及统一图挂载。
   新精简合同将owner_slice准确指向slice_id（长参考中的一处说明误写成owner），并通过实际
   scenario-map／topology校验器验证形状与错误归属负例；未修改通用合同或平台行为。
4. JSON／YAML、相对链接、输入SHA256、diff空白及旧Task／场景未改动检查通过。
   新测试Ruff通过，Skill验证通过，提交前检查仅暂存本需求文件。
5. GitNexus `detect_changes(scope=staged, repo=ontology-platform)`：18个文件、1个文档符号、
   0受影响执行流、风险low。新增任务／测试不因此获得完整图谱覆盖；影响边界以配置loader、
   Runner prepare、直接能力及CQ的实际针对性检查为证，不宣称图谱覆盖新的运行流程。

## 验收对应

| 项目 | 当前证据与保留状态 |
| --- | --- |
| A1 | 材料／配置工程通过：独立身份、版本化唯一业务源、专用包及实际prepare挂载清单；真实Agent采用未运行 |
| A2 | 未验证：真实application回执、当前修订治理读取及独立语义验收尚未发生 |
| A3 | 采集口径已交付；真实时间线／用量未产生，数值unknown，不形成性能基线 |
| A4 | 工程通过：三个旧Task及原场景文件未改动，原Profile配置加载通过；未重写任何历史证据／裁决 |
| A5 | 分级说明已交付；各层实际新验收未进行，不关闭原小链／完整场景／27题及时间目标缺口 |

后续真实验证须依当时授权选本Task/Profile，保留独立run、freeze、模型版本、应用／检索／
裁决证据与019用量覆盖；每层单独结论。材料交付不会解除暂停或自动追加运行／修模轮次。
