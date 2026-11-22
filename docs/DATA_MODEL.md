# 数据模型

0027_item_entitlements仅新增memory_items.is_entitlement Boolean NOT NULL DEFAULT false与expires_at Date NULL；CHECK要求权益日期非空且>=purchase_date，普通日期为空。旧记录false/null。剩余天数按用户时区读取计算，不入库，原成本字段和公式不变。见[实施记录](ITEM_ENTITLEMENTS.md)。

人物分析最小修复无表结构变更，仍为0026。新生成结果保持原字段结构，历史宽Schema继续可读；现有ai_call_logs.usage JSON增加人物专属脱敏数字诊断，包括截断用量。无正式人物、任务、事件或杂念原文数据迁移。

0026_memory_wishes新增memory_wishes、memory_wish_prices、memory_wish_classifications。价格历史kind为initial/update/correction，保留previous_price和纠正原因；请求幂等、用户复合FK。当前价和纠正后首价由事务维护，原历史不覆盖；分类失败与成功记录独立。

0025_memory_items新增memory_items：user_id、名称、购买日期、Numeric(14,2) CNY价格、自由类别、可空image_asset_id、版本、幂等创建编号和软删除；图片复合FK同用户且每资产唯一。

0023_memory_people新增memory_people、memory_person_events：用户归属、版本和软删除，人物手填联系日期独立于事件最新实际联系日期；事件分真实联系/回忆。0024_person_analysis新增memory_person_analyses：用户/人物复合FK、请求幂等编号、授权范围、输入指纹、状态与错误码、结构化结果和评分规则版本。失败不删除旧成功分析。精确热度和分数由Python计算，不存AI随意返回的数字。

0022_memory_assets新增memory_assets与memory_asset_objects。稳定资产含user_id、版本、幂等创建编号、软删除；不可变对象含资产归属复合FK、Bucket/相对对象路径、SHA-256、尺寸与pending/active/retired/deleted状态、清理时间及脱敏错误码。唯一部分索引限定每资产一个active。数据库不存图片二进制、Windows路径和原文件名。其余三类业务表未提前创建。

## 藏经阁0021_library_copies

library_links增加(id,user_id)唯一约束，library_copy_receipts以(user_id,request_id)主键保存link_id及创建时间，复合FK限定同用户链接。只保存复制操作ID，不存剪贴板内容。凭据与原子计数在同一事务，锁用户串行化重试检查，SQL执行click_count=click_count+1。失败不留半次计数。


## 藏经阁：0020_library_links

新增library_links：UUID id/user_id，原始description最多500字符、url最多2048字符；可空main_quest_id/task_id二选一；BigInteger click_count默认0；version默认1；create_request_id和SHA256指纹、UTC时间与deleted_at。描述/URL长度、计数非负/版本正数、恰好一个目标CHECK；复合FK保证主线/副本同用户，用户/请求UUID唯一防重复创建；归属及排序索引。无复制/点击流水表，第4步另行批准实施成功复制计数。


## 杂念第3步数据库版本0019_distraction_classification

新增distraction_classification_runs（用户/请求唯一、输入指纹、状态、脱敏错误码及时间）、distraction_topics（版本归属、类别/具体主题摘要）、distraction_memberships（run_id/note_id唯一、nullable topic_id表示明确未归类）。复合外键约束同一用户和批次的主题、原文归属。主题次数不存模型猜测值，SQL聚合未删除记录；新原文不在旧版membership中，显示为待归类。只有成功完整批次published，旧版superseded保留，失败版本failed。无原文内容回写或其他业务表关联。回退保留新表及历史版本，不能通过真实库降级删表恢复。


## 杂念 V1 第1步

新增迁移`0018_distraction_notes`，仅增加`distraction_notes`：UUID id/user_id/create_request_id，TEXT content，version，create_fingerprint，UTC created_at/updated_at/deleted_at。只外键关联users；(user_id,create_request_id)及(id,user_id)唯一，(user_id,created_at,id)索引，长度1–5000及version>=1约束。应用另拒绝空白和NUL，不修剪原文。不含分类/主题表。


V3交付时数据库版本：`0017_item_analysis`。V3第5、6步没有数据库迁移，未删除历史表、字段或记录。

## 当前业务

- users/login_sessions：用户与登录会话，凭据不进入导出。
- main_quests/milestones/tasks：长期目标、里程碑和副本。人工五色manual_focus_status为recommended/normal/not_recommended/deferred/routine_practice，默认normal；manual_focus_version独立于任务业务version。
- activity/growth相关表：原计时、历练、经验、金币和审计流水保留。
- startup_items：只外键关联users，四项内容为description、importance、urgency、progress；包含version、创建请求UUID/指纹、时间与deleted_at。重要/紧急为0–100整数，描述与进展各最多2000字。新增请求幂等，删除软删除。
- startup_items分析字段：analysis_result保存真实item_id、keyword、单一quadrant或null、reason、action；analysis_fingerprint只含四项内容，analysis_config包含模型/提示版本。analysis_error与最近attempt_id/fingerprint/status/started_at独立保存，不覆盖最后成功JSON。内容变化失效，状态滑杆变化不失效。
- startup_state_snapshots/startup_current：手动压力/能量快照与当前引用；仍保留历史source_turn_id/source_plan_id，但新接口不接受旧AI建议来源字段。

## 临时会话与历史保留

新会话不写startup_conversations、startup_chat_turns或breakdown_plans。标签页sessionStorage按账号隔离保存最多12轮显示，发送最多6轮/12000字符历史。刷新恢复，新对话清空，退出清理；浏览器恢复标签页可能恢复会话。服务端仅存AI调用元数据，不存新会话正文。

task_analysis_cache、recommendation_batches、startup_conversations、startup_chat_turns、breakdown_plans均为历史保留表。状态快照与旧聊天/拆解存在外键，部分相互引用；ORM和历史Alembic文件保留以维持迁移与引用完整性，不挂载旧服务。若将来删除数据或表，需要单独批准、完整备份和恢复验证。

导出包含主副本人工字段和独立事项/分析结果；不等于完整数据库备份，尚不提供导入恢复。回退应用应保留用户新数据，不能把有数据的downgrade当普通回退。阶段回退标签见DECISIONS.md。
