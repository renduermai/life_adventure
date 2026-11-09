# 数据模型草案

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
