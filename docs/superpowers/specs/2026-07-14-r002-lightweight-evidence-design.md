# R-002 轻量证据引用设计

## 目标

外部建模 Agent 自行读取知识文档并做知识提取。平台只接收 Agent 实际引用的文档名和原文
片段，将其作为项目级 Evidence Reference 留存，并把它关联到具体建模结果。平台不上传、
解析、分块或版本化完整文档。

## 领域模型

### Evidence Reference

项目共享、不可修改的引用片段：

- `project_id`
- `document_name` / `normalized_document_name`
- `excerpt` / `excerpt_hash`
- `created_by` / `created_at`

幂等键为 `(project_id, normalized_document_name, excerpt_hash)`。文档名和片段去除首尾空白，
片段换行统一为 LF，正文内部不做改写；哈希为规范化片段 UTF-8 字节的 SHA-256。

### Evidence Association

Evidence Reference 与具体建模结果之间的多对多关联：

- 项目、本体和可选 Graph Set 作用域
- `target_type` + `target_id` 标识建模结果
- 可选 `client_item_id` 和 `edit_audit_id` 连接 Agent 批次与编辑审计
- `evidence_reference_id`

不存在独立的“Ontology 拥有文档”关系；Ontology 对证据的使用从具体关联派生。

## 后端流程

### 独立引用

`POST /projects/{project_id}/evidence-references` 创建或复用引用。`GET` 列表支持文档名和片段
搜索；详情可读取完整片段、哈希和关联数量。引用不可修改或物理删除。

### 预解析与 dry-run

`POST /projects/{project_id}/evidence-references:resolve` 接收已有 ID 和内联片段。dry-run 只返回
已有引用或待创建候选及其幂等键；apply 在一个数据库事务内创建所有候选。

### 建模关联

`POST /projects/{project_id}/evidence-associations` 原子地解析内联证据并建立具体建模结果关联。
关联唯一键防止网络重试生成重复记录。引用、本体和 Graph Set 必须属于同一 Project；跨项目
资源统一表现为不可用。

`POST /projects/{project_id}/evidence-associations:batch` 提供后续建模批次可直接复用的逐项协议：
dry-run 返回规范化候选且不落库；默认模式先校验全部项目并原子应用；只有显式
`allow_partial=true` 时才使用逐项 savepoint，失败项不会遗留孤立引用。

canonical write 接口额外接受 `evidence_reference_ids`、`evidence`、`client_item_id` 和可选
`evidence_target_id`。证据先完成只读校验，语义写入成功后与同一编辑审计关联并提交数据库事务。
当前 RDF 与 Postgres 仍是两个存储系统；R-004 的批量协议需要在此服务原语之上补充跨存储恢复
记录，才能对多项批次提供完整的失败恢复保证。

事实证据接口保留现有兼容形状。当调用方提交 `document_filename + text` 时，同时创建或复用
Evidence Reference 和通用 Evidence Association，并在旧事实绑定上保存新引用 ID。

## MCP

提供四个轻量工具：

- `create_evidence_reference`
- `list_evidence_references`
- `get_evidence_reference`
- `associate_evidence_reference`

MCP 与 REST 复用同一服务、规范化、项目隔离和幂等规则。

## 前端

Overview 下新增 Evidence 页面。页面属于当前项目而非当前本体：

- 顶部明确说明项目共享以及不上传完整文件。
- 创建区只收集文档名和准确原文片段。
- 左侧台账支持按文档名/片段检索。
- 右侧详情展示完整片段、哈希、创建信息和建模关联。
- 当前打开本体的关联使用独立状态标记，但不会过滤掉项目内其他本体的关联。
- 工作区锁定时仍可读取，不能创建新引用。

## 兼容与迁移

旧 `evidence_artifacts`、`evidence_chunks` 和只读接口暂时保留，避免破坏现有调用方，但不再代表
v1 R-002 目标。旧事实证据表新增可空 `evidence_reference_id`；历史绑定不强制回填，因为缺少
可靠文档名时平台不能伪造 Evidence Reference。

## 验证

- 后端服务与 REST：规范化、去重、搜索、dry-run、跨项目拒绝、事务回滚和关联幂等。
- 事实兼容：带文档名的事实证据同时生成新引用和关联。
- MCP：注册表、工具分类和输入契约。
- 前端：构建、Evidence 深链、创建、详情和当前本体关联展示。
- 全量 backend pytest 与 frontend Playwright 作为交付门槛。
