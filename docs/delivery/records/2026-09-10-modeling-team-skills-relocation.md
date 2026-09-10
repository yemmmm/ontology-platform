# Modeling Team 技能目录迁移

状态：PASS（目录迁移与机械回归）。

用户要求：将 `ontology-modeling` 移出项目 skill 目录，减少与宿主开发技能的混淆，集中存放
其他 Team 成员的技能。

适用合同：R2.3-001 的 Team Package / Runtime 加载合同与 R3.0-011 批量验收资产选择。
本次仅调整资产布局、引用和导航；角色、Task/Profile、技能内容及授权边界保持原合同。

## 目录与成员

- Team 内部的六套技能集中在 [`modeling_team/skills/`](../../../modeling_team/skills/README.md)。
  五套原位于根 `skills/`，`v3-acceptance-batch` 原位于同名 `agent-packages/`。
- Modeling、Coordinator、Protocol、Competency Question、Source Specialist 共用
  `ontology-modeling`；其他验收成员按目录表使用对应技能。角色提示仍在 `agent-packages/`。
- 宿主使用根 `skills/modeling-dev-loop/`，保留其 `.agents/skills/` 发现链接。
  移除 `ontology-modeling` 的发现链接及 gitignore 例外，不保留旧位置重定向技能。
- 更新包声明、Runner 基线资产路径、验收子会话资产选择、共享技能验证器的仓库定位及活动导航。
  历史记录的命令与结果保留为原始证据；此前宿主 Skill 测试记录增加迁移说明。

## 影响与验证

修改前 GitNexus 上游分析：`_baseline_manifest` 为 LOW，2 个直接调用者（`prepare`、
`preview_baseline`）、1 条 CLI 流程；`_child_package_assets` 为 LOW，1 个直接调用者
（`_launch_acceptance_child_impl`）；三个修改的测试符号均为 LOW、无上游调用者。

- 初次 pytest 控制台入口未将仓库根加入模块路径，收集报 `ModuleNotFoundError: modeling_team`；
  改用 `uv run --project backend python -m pytest` 后正常收集，无产品代码调整。
- 第一轮 Team 全量测试：1404 passed、1 failed、1 skipped、318 subtests passed。
  唯一失败为 `test_acceptance_package_and_skill_describe_only_runner_owned_retry` 仍直接读取
  原 `skills/acceptance/SKILL.md`；修正为新目录。
- 官方 `quick_validate.py`：5 套标准 Team 技能、宿主技能和 5 个废弃入口共 11 项通过。
  对 `lean-acceptance-examiner` 的首次通用校验报 `No YAML frontmatter found`；核对旧版后确认
  原本就是无元数据的专用提示，保持字节一致，由既有验收 Runtime 路径测试覆盖，不计为标准
  Skill 校验 PASS。迁移后的 `ontology-modeling/evals/validate_skill.py` 通过。
- 10 个迁移内容文件与提交前逐字节一致，验证器仅调整路径常量；9 个包技能引用、46 个相关
  相对链接、宿主发现链接及 Team 技能不再出现在项目发现目录的检查通过。
- 当前配置加载通过：
  `uv run --project backend python -m modeling_team validate --profile modeling_team/profiles/r3-0-011-competency-question.yaml --task modeling_team/tasks/r3-0-006-real-full.yaml`。
- 最终全量测试：
  `env -u DEEPSEEK_API_KEY uv run --project backend python -m pytest modeling_team/tests -q`
  → **1405 passed、1 skipped、318 subtests passed**（73.15 秒）。命令仅在测试子进程中移除宿主
  DeepSeek 环境变量，避免影响旧适配器的缺凭据 fixture，不修改配置或使用真实模型调用。
- `git diff --cached --check` 通过；GitNexus `detect_changes(scope=staged)` 为 medium，两个受影响
  流程均经过预期的 `_baseline_manifest`（Main → Manifest、Main → As_dict），代码符号限于
  两个加载方法、对应父类和三个测试。迁移文件经 Git 识别为重命名，无其他产品逻辑变化。
- 提交仅包含本次迁移与导航改动；保留原有 `AGENTS.md` / `CLAUDE.md` 的 GitNexus 索引统计
  未提交修改及未跟踪 `.codex/agents/`。

本次未启动或继续真实 semantic modeling，fresh starts 消耗为 0；目录和机械测试不构成
建模质量或真实语义验收 PASS。未修改 backend/frontend，无需服务重启。
