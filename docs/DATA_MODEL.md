# 数据模型草案

第三次改进的 `0014_chat_target` 在 `startup_conversations` 新增可空 `selected_target_key`（`quest:UUID` 或 `task:UUID`）。这是对话当前关注目标，不复制任务正文或推荐数据；发送/修改选择时均按当前用户有效候选校验，目标失效后不能继续作为有效上下文。已确认压力、能量仍只存于 `startup_state_snapshots`，AI 建议仍在 `startup_chat_turns.response`，正式任务数据未增加字段。

启动状态散点第2次不新增表或迁移。推荐 GET 在现有批次结果上临时补充当前用户有效任务的 `kind`、`title`、`description`、`main_quest` 和 `href`；这些不是新的持久化字段。仅 `analysis_status=analyzed` 且批次非过期的分类可显示标记；`quadrants[0]` 是主要展示象限，并无任务精确压力/能量坐标。

启动状态推荐可靠性改进：`0013_recommendation_reliability` 为 `recommendation_batches` 增加可空 `error_code`，记录系统性失败。`results` JSON 中每个目标增加 `analysis_status`、`error_code` 与 `config_signature`；已分析项引用独立持久化的 `task_analysis_cache`，待分析项 `level=null`。批次仍绑定单一已确认 `snapshot_id`，状态或任务在生成期间变化时不发布该批次。

## V2 第 8 步（2026-11-15）

0012_breakdown 增加 breakdown_plans：同用户目标复合外键、snapshot_id、previous_id、请求/上下文指纹、草稿与revision、模型来源、确认指纹/时间、正式对象mapping、执行关联、清单状态/版本/事件JSON。生命周期 generating/draft/confirmed/failed/superseded；步骤UUID由服务器生成，历史方案保留。

状态快照增加可空 source_plan_id 同用户外键，用于用户确认拆解对话中的状态建议。与计划snapshot_id构成双向引用；迁移先建计划再加来源外键，回退先拆来源。清理时需遵守外键顺序；正式应用不硬删除方案。开发库在线upgrade和ORM check已通过。V2数据导出仍留第9步明确。

## V2 第 7 步（2026-11-15）

0011_startup_chat 新增 startup_conversations（用户、标题、版本）与 startup_chat_turns（用户、会话、顺序、请求号、指纹、输入、结构化回复、pending/succeeded/failed、错误码、基础状态代次、时间）。同用户请求唯一、会话顺序唯一、复合外键约束归属。startup_state_snapshots 增加可空 source_turn_id，复合外键关联同用户轮次；旧手动状态保留空来源。用户确认可以修改建议数值，快照是最终确认值，回复保留原建议。

迁移已在开发库应用，ORM check 通过。对话与状态历史保存在 PostgreSQL，未写浏览器存储；历史分页每页20项。当前旧版数据导出尚不包含 V2 对话/状态，范围在第 9 步统一验收。

## V2 第 6 步（2026-11-15）

第 6 步复用 task_analysis_cache 和 recommendation_batches，不新增表或修改迁移。拆解目标只读原任务、里程碑、子任务及当前状态；不新建拆解会话或正式任务。

## V2 第 5 步（2026-11-15）

0010_recommendations 新增 task_analysis_cache（真实主线/副本归属外键、内容指纹、模型版本、特征及人工覆盖）和 recommendation_batches（用户/快照关联、请求防重、发布状态、结果 JSON）。结果中的任务引用经后端真实候选验证，GET 时再次核对归属、可用性及指纹；不是新任务事实表。

## V2 第 4 步

0009_startup_state 新增 startup_state_snapshots 和 startup_current；数值约束 0–100，当前引用按用户归属复合外键约束。

## V2 第 3 步

页面复用现有 0008_ai_gateway 配置与调用日志，无数据库结构变更。

## 2026-11-15 V2 第 2 步已实施

0008_ai_gateway 新增 ai_configs、ai_module_bindings、ai_call_logs，开发库在线 upgrade 与 ORM 一致性检查通过。加密密钥、唯一默认、版本与创建请求指纹在 ai_configs；绑定和日志用复合外键校验同用户配置；日志不含消息、回复、明文/密文密钥或完整异常。配置软删除时清空密文并移除绑定，日志保留。

当前合计 17 张业务表；本步没有状态/推荐/对话/拆解表，没有修改任务或奖励字段。下面“V2 全部模型待实施”属于第 1 步历史快照；当前以本节和迁移源码为准。

## 2026-11-15 当前模型与 V2 迁移计划

已实施模型为 users、login_sessions、main_quests、milestones、quest_events、tasks、task_events、task_commands、focus_sessions、focus_segments、activity_logs、activity_events、reward_settings、reward_entries。代码期望迁移为 `0007_rewards`；本步只读核对源码和历史记录，未连接数据库或执行迁移。

V2 第 1 步仅完成设计。下表均为后续拟新增模型，字段、复合外键、约束、请求幂等和导出规则详见 [V2_STARTUP_DESIGN.md](V2_STARTUP_DESIGN.md)。

| 首次步骤 | 逻辑表 | 主要约束 |
|---|---|---|
| V2-2 | ai_configs、ai_module_bindings、ai_call_logs | 加密密钥、用户归属、唯一默认、用途/请求号幂等、日志无凭据 |
| V2-4 | startup_state_snapshots、startup_current | 压力/能量 0–100、确认来源、同用户当前状态 |
| V2-5 | task_analysis_cache、recommendation_batches、recommendation_items | 原目标归属外键、内容/规则版本、每批每目标唯一、完整发布 |
| V2-5 | 扩展 startup_current | 当前批次与状态匹配、代次防旧请求覆盖 |
| V2-7 | startup_conversations、startup_messages | 同用户会话、消息去重、目标/状态上下文 |
| V2-8 | breakdown_plans | 草稿版本、步骤稳定 ID、确认防重、真实对象映射 |

主线/副本目标引用使用 quest_id/task_id 二选一并校验所有权，不另建任务事实表，不在 tasks 或 main_quests 增加永久颜色。主线没有整数版本，需将自身、里程碑和关联任务组成内容指纹；副本 version 结合关联变化使用。缺失的时长/依赖保持未知，AI 估计单独标明来源。

当前无上述 V2 表；迁移按各步骤单独创建和执行，须同步 ORM 注册和应用期望版本。第 6 步复用第 5 步批次基础，不重复建表。第 9 步明确私密数据导出选项及字段白名单，永不导出 API Key 明文/密文或主密钥；不承诺 ZIP 自动导入。

以下是阶段交付及原始概念设计历史，旧 profiles/time_sessions/xp_events/coin_transactions 名称不等于当前真实表。实际表以上述列表和源码为准。

## 阶段 1.9 更新

1.9 不新增表。导出包含已有业务表及用户基础资料，不包含凭据和会话。


## 阶段 1.8 更新

1.8 是只读聚合，无新增数据表或迁移；主线进度及奖励余额继续使用所属领域查询。


## 阶段 1.7 更新

0007_rewards 新增 reward_settings 与 reward_entries，并为 task_events 增加 (id,user_id) 唯一约束。奖励引用任务与事件，冲正引用同用户原始流水；迁移事务补发当前完成轮次。


## 阶段 1.6 更新

0006_activity 在 activity_logs 增加版本与用户归属唯一约束，并新增 activity_events 审计表。原始计时会话、区间与修改后的手记记录分别保留。


## 阶段 1.5 更新

0005_focus 新增 focus_sessions、focus_segments、activity_logs。每位用户最多一个活动会话，每会话至多一条行动记录。确认有效时长可小于系统计时，原始会话和区间保留，记录备注保留确认依据。


## 2026-11-10 阶段 1.4 更新

0004_tasks 新增 tasks、task_events、task_commands 和里程碑复合唯一约束；含归属外键、任务版本、完成轮次、软删除、重复来源唯一约束和完成事件唯一索引。详细字段和规则见 STAGE_1_4.md。

下文历史状态以本节和 PROGRESS.md 为准。

## 2026-11-10 已实施：1.1–1.3

- `users` 存储唯一用户名、Argon2 密码散列、昵称与时区；当前合并基础 profile，不单独创建 profiles 表。
- `login_sessions` 只保存会话 token 的 SHA-256 散列、所属用户和到期时间。
- `main_quests`、`milestones` 保存用户归属、标题、描述、状态、日期和软删除时间；里程碑使用复合外键限制跨用户关联。
- `quest_events` 保存主线及里程碑的操作历史，复合外键限定主线和用户一致。
- 迁移 0002_identity_quests、0003_quest_events 已在 Supabase 开发库在线执行，当前版本为 0003。业务表以外的下文为未来规划。
- 暂定进度等权按未删除里程碑计算；没有里程碑显示尚未配置。副本阶段的关联和进度规则需在 1.4 批准时明确。

## 原始设计记录

状态：业务实体仍为概念设计。已有 ORM Base 与 Alembic 0001_stage0 空业务基线，未连接真实数据库或创建业务表。字段在所属模块批准时细化，不能把本文件视为已实施 schema。

## 通用约束

- 业务主键使用 UUID；具体生成方式在实现时确定。
- 用户拥有的数据有 user_id 外键；用户自身为租户根。
- 业务记录具有 created_at、updated_at；重要实体使用 deleted_at 软删除，审计流水原则上只追加。
- 时刻用 PostgreSQL timestamptz 表达，统一按 UTC 处理；纯日期使用 date，展示使用用户 IANA 时区。
- 关联同时保证对象存在和用户归属一致：服务端校验，重要关系补充复合唯一键/外键或等效数据库约束。
- 约束、索引、表与字段变化均由 Alembic 管理，不通过启动时 create_all 冒充迁移。
- 删除与恢复遵循关联规则；父记录已删除时不能静默恢复子记录到不可用状态。具体恢复顺序随所属模块确定。

## 核心实体

| 实体 | 所属模块 / 首次阶段 | 核心字段草案 | 关系与约束 |
|---|---|---|---|
| users | identity / 1.1 | id、身份状态、时间戳 | 身份根；凭据或外部认证映射待认证决策 |
| profiles | identity / 1.1 | id、user_id、display_name、timezone | user_id 唯一；初期基础资料，不提前实现 AI 身份卡 |
| main_quests | quests / 1.2 | id、user_id、title、description、status、start_date、due_date、deleted_at | 用户一对多主线；日期与状态校验 |
| milestones | quests / 1.3 | id、user_id、main_quest_id、title、sort_order、due_date、deleted_at | 主线一对多里程碑 |
| tasks | tasks / 1.4 | id、user_id、main_quest_id?、milestone_id?、parent_task_id?、title、status、priority、due_at?、completed_at?、deleted_at | 独立任务允许无主线；里程碑必须属于指定主线；禁止父子循环 |
| time_sessions | timer / 1.5 | id、user_id、task_id?、mode、status、started_at、ended_at?、effective_seconds | 有效时长非负；暂停明细的表/字段方案待定 |
| activity_logs | activity / 1.5 最小接口、1.6 完整管理 | id、user_id、kind、task_id?、session_id?、occurred_at、duration_seconds?、source_event_id? | session_id 对自动时间记录唯一；事件与时间记录通过 kind 区分 |
| xp_events | growth / 1.7 | id、user_id、source_event_id、delta、rule_version、reversal_of?、created_at | 奖励来源唯一；冲正引用原流水且最多一次 |
| coin_transactions | economy / 1.7 | id、user_id、source_event_id、delta、kind、rule_version、reversal_of?、created_at | 虚拟金币整数；来源唯一；冲正保留原始凭证 |
| app_settings | 相关领域 / 逐步 | id、user_id、key、value、updated_at | (user_id,key) 唯一；结构化校验；不得存放明文 API Key |

各实体适用通用时间戳约定，追加流水无需伪造业务编辑能力。状态变化历史需要持久化：初期可通过 activity_logs 的结构化状态事件承载，是否增加独立历史表由对应模块提案说明。

## 关系概览

```text
users ──1:1── profiles
  ├──1:N── main_quests ──1:N── milestones
  ├──1:N── tasks ──可选关联── main_quests / milestones / 父任务
  ├──1:N── time_sessions ──可选关联── tasks
  ├──1:N── activity_logs ──可选关联── tasks / time_sessions
  ├──1:N── xp_events
  ├──1:N── coin_transactions
  └──1:N── app_settings
```

## 关键业务规则

1. 任务状态转换由 tasks 控制，页面不直接写状态或奖励金额。完成轮次与请求幂等记录的具体持久化结构在 1.4/1.7 明确，不能仅依靠随机事件 ID 防重。
2. 任务完成事件与经验、金币流水在一个事务内保存；奖励额度按服务端规则确定，并记录规则版本或快照，历史不随设置变化重算。
3. 对同一完成轮次重复请求返回已有结果。撤销关联原奖励作冲正；再次合法完成产生新轮次。
4. 软删除已完成任务默认不隐式撤销奖励；是否撤销必须是明确业务操作。进度分母与历史统计对软删除的处理，在 1.4 形成可测试规则。
5. 主线进度和金币余额先从事实聚合，不新增跨页面维护的余额或进度副本。
6. 自动时间记录引用会话，手动修订保留原始会话事实及修订来源；统计只读取有效 activity 时间记录。任务完成事件不能被统计为另一份专注时间。
7. 子任务计数、重复任务实例化、批量操作原子性、归档关联规则均为后续决策，不在本模块提前确定 schema。
8. 兑换后撤销奖励可能影响余额；负余额与冲正策略须在 1.7/3.5 明确，不以删除流水解决。

## 后续实体，仅记录需求

阶段 2：weekly_reviews、ai_conversations，以及 AI 配置和草稿的必要结构。

阶段 3：skill_dimensions、skill_assessments、achievements、user_achievements、wishes、wish_redemptions、notes。

阶段 4：equipment、扩展笔记与现实收支等。具体表随模块提案决定；此处不授权建表。

## 迁移记录

2026-11-09：新增 0001_stage0 空业务基线，仅由 Alembic 管理版本表；离线 SQL 验证通过，在线 upgrade/downgrade 尚未执行。业务表按 1.1 起的模块顺序新增。迁移测试应使用开发/测试数据库并验证 upgrade、适用的 downgrade 和备份恢复限制；有损迁移不能将 downgrade 等同于数据恢复。
