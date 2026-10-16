# 关系引用、租约接续与修模授权边界修复

用户授权按[最近三组复盘](../modeling-retrospectives/2026-10-16-last-three-groups-retrospective.md)
继续排查及修复。归属R4.3-024／025／026及AGENTS既有轮次授权规则；基线1519641。
本次不启动语义建模／验收，不修改历史模型、授权账本、冻结题池、裁决或staged运行输入。
README与演示材料的既有工作不在本次范围。

## 1. 方向反复建反：两个数组顺序不同，回执引用需要程序给准

在`r4326-20261016-flash-c-round3`中，02:10:10 UTC原请求先创建Service Site，后创建
Installed Asset。02:10:15原生工具实际返回的resource_bindings也保持这个顺序；但它指向的
原回执`b52b3ec1…-3caa1b9b….json`的items顺序为Installed Asset、Service Site。
02:11:06被接受的关系意图使用原回执items/1作source、items/0作target，实际反向；
02:14:40纠正意图反过来选items/0和items/1。两端定义文字始终正确，不能用文字证明端点。

可证原因是跨响应视图使用位置推算身份，已知提示虽告诫不要按位置，但提交结果没有给
绑定成员对应的原回执Pointer。它不是传输丢掉技能，也不是平台擅自反转字段。对该run
的诊断已从笼统“身份匹配不稳定”收窄；不据此声称所有历史方向错误内部机制相同。

最窄改动：Executor按client_item_id匹配实际result.items并保留其原下标；Runner用已注册
的实际receipt_ref生成每个resource_bindings成员的existing_resource_ref。Agent按既有
change_id/item_id选择成员并复制引用，不再手算另一个数组的Pointer。程序不判断业务
方向，不重排历史回执，不新增语义规则／工具／平台字段。025引用合同及Modeling两份
实际权威提示同步说明这两个顺序可能不同，并要求提交前对照源选择具名变更对应的端点。

## 2. 过期lease：保持保护，修复缓存及正常收尾

T0复核：有效租约保护真实并发写入与资源所有权，不能删除；但原`_ensure_lease`只要
缓存非空就直接使用，永久沿用过期token并非该不变量要求。平台现成acquire会检查当前
Session、范围、fence与他人有效租约；未知写入的原身份对账也已有独立保护。

实现保留真实expires_at及快照期限；新批准备前复用尚有效的缓存，已过期或旧快照无期限
则刷新原Session revision并调用原acquire取得新token，不建立新run/Session。未知写入
检查仍在新上下文准备之前，未知/已成功原请求不换token重放。平台拒绝越权或他人租约
仍按原合同返回，不新增续租后台任务、自动业务恢复或新硬门。

原close_session先release过期lease也会失败；现在对已知过期lease直接交由原Session正常
complete/cancel统一释放。若边界上release已返回准确lease_expired，同样继续正常终态
操作；其他释放错误、Session终态错误不吞掉。只有终态成功后才清空本地lease与ownership。
不为收尾重新acquire，不补偿或重放模型写入。

## 3. 额度越界：通知已到达，纠错分类与确认执行需要收紧

原Modeling原生输入在02:05:28 UTC已收到Coordinator逐字转发的余额0／不得第4轮指令，
02:09:52收到的freeze确认也明确“不启动新轮”。02:13后的治理自查／关联检查之后，
仍于02:14:40提交correct-installed-at-endpoints。因此已排除“通知未到达”的解释；
该调用确是自查后的实质修模，不能因原定义正确、只换Pointer改成免费技术纠错。
不将这段可观察动作冒称为已证实的模型内部唯一动机。

修复落在原Modeling skill／instructions、Coordinator instructions、Delivery skill／
instructions及宿主modeling-dev-loop：派单/恢复携带当前轮目标及余额，原Modeling实际
确认；自查后发现应用端点错误先报告，Coordinator经Delivery确认仍有获准修模轮才继续。
余额0可完成当前初建及连续批次，自查发现语义缺口则只读检查、资源收口、保留缺口并
独立交接，不“修好再交”。宿主在自查转换处跟进实际确认与行为，再沿现有控制封存。
余额可用仍直接沿既有用户授权推进，不重复申请；不新增平台次数硬门。

## 影响与验证

GitNexus的_ensure_lease、DirectModelExecutor及_handle_direct_modeling均Target/Symbol
not found；因此采用定向调用点和真实回归，不声称图影响覆盖。实际链为
Runner direct capability→compiler/binding→Executor→平台Build Session／Batch服务；
返回引用继续进入现有ObservedModelBindings权限／版本／资源身份校验，没有绕过它。

- 新增四项反例在旧码实际4 failed：缺返回引用、复用过期token、release过期阻断收尾、
  真实服务暂停后不能继续。首次修复后33 passed、1 failed，过期lease的收尾仍未成功；
  改为已知过期lease直接交正常Session终态释放后，两文件34 passed，14.31秒。
- 新引用反例使用真实Unix socket capability、Batch服务、SQLite及RDF Dataset：请求和
  原回执顺序相反，直接复制返回引用建立Device→Location，实际SPARQL domain读回吻合。
  租约反例推进真实服务时钟超过TTL，原Executor/Session成功提交后批，再次过期后正常
  complete。均为合成隔离数据，不是生产语义运行或新semantic-start。
- 六个直接建模／能力／配置相关文件74 passed，10.27秒，涵盖原请求幂等、未知写入、
  依赖绑定、权限与实际能力合同。更大范围检查结果见后续追加。
- 三份变更Skill的quick_validate均通过。改动Python文件Ruff通过；runner保留与HEAD
  完全相同的6条既有Ruff问题，没有新增；没有顺手修旧导入/局部变量。

本次工程证据不证明下一次Agent必定首次选对方向或服从轮次边界。历史越界不追认，
原start1不因修复自动恢复，真实独立语义重验及提示采用效果仍需另有运行授权。

## 最终验证与运行核验

- 后端完整`env -u DEEPSEEK_API_KEY PYTHONPATH=.. uv run pytest -q --tb=short`：
  **1232 passed、56 skipped，924.47秒**，退出0。上述Team六文件**74 passed，10.27秒**。
  原始完整日志保存在本机gitignored
  [后端日志](../../../workspaces/modeling-direction-lease-repair-20261016/backend-regression.log)与
  [Team日志](../../../workspaces/modeling-direction-lease-repair-20261016/team-regression.log)。
- 按仓库要求正常重启`ontology-platform.service`，unit active/running、WorkingDirectory
  为当前checkout；curl --fail确认后端`8001/api/health`返回status ok、前端5173返回200。
  启动初期连接拒绝经既定有界重试后成功；没有修改启动器、延长永久超时或覆盖失败记录。
  本次运行代码改动在Team进程，后端仅新增测试，前端无源码改动；不声称重启会热更新
  保留Team的冻结代码／提示，也未恢复任何旧建模run。
- GitNexus detect_changes主要返回过期文档符号、未覆盖实际执行器；定向代码及回归
  为本次影响证据。变更JSON解析、Markdown围栏／新增本地链接及git diff空白检查通过。

结论：本次窄修工程验证通过；真实首次方向选择、修模授权实际遵守和自主交付仍待
后续获准运行验证。没有新semantic-start、实质修模轮或独立语义裁决，不追认旧越界。
