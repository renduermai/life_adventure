# 总体架构

## 第10步（2026-11-27）

第10步加入仅本页的Promise串行器，核心/日程/地图的已授权请求统一排队，保持后端每用户限流；跨页仍执行既有限流。场景时钟轮询只更新只读时间区，不重建编辑器。无新后端架构/队列/迁移。

## 第9步（2026-11-27）

attractors模块读取owner-scoped有效事件及有限背景，事务外通过现有Gateway分析，逐字引句/来源与发布时快照复核后保存地图版本。前端SVG稳定布局，事件详情授权后读取完整源。

## 第8步（2026-11-27）

care模块复用登录、事务与用户锁，确定性计算保障进度和成功节点；蓝色模式提供有上限恢复协议上下文，复用核心/日程现有请求，无新增AI调用。

## 人生运行系统第7步

schedule.py独立冻结模式/状态/模板快照，事务外通过life_os_schedule调用现有Gateway；确定性保护叠加后原子保存每日/每周版本。schedule_runs隔离成功与失败历史，按输入指纹缓存；前端明确授权后的事件触发生成，GET不调用AI。

## 人生运行系统第4至6步

later_service集中处理按用户隔离的个人经验、模式版本与原始场景；later_router只认证、校验和委托。既有核心分析成功发布时，在同一发布事务同步更新AI模式建议；手动状态不被覆盖。层次经验只在已有同意和匹配层次条件下限量进入下一次现有模型调用。场景时间判断由Python按用户ZoneInfo确定，页面读取接口显示，无轮询AI/队列/日程写回。无新框架。详情[LIFE_OS_STEPS_4_6](LIFE_OS_STEPS_4_6.md)。

## 人生运行系统第3步

problem_models / schemas / problems / router与核心Service协作，同一次Gateway调用返回核心状态与可选事件，核心先发布、经验独立事务发布。源→事件唯一、事件→问题唯一；SQL按有效已确认事件计数，模型不维护次数。独立失败码、归属/版本复核与操作回执保护手动内容；所有来源仅限本人。页面复用原单一对话入口。详见[LIFE_OS_PROBLEMS](LIFE_OS_PROBLEMS.md)。


## 人生运行系统第2步

life_os.service负责先保存不可变原文，再冻结最多6条近期上下文并在事务外调用Gateway(life_os_core)。严格Schema及来源ID校验后原子发布独立快照；失败只更新尝试状态，不覆盖成功历史。当前状态按消息时间及快照时间取最新成功结果，重分析旧消息不会抢占新消息状态。手动校准新增快照，保留AI旧值。无需队列或新框架。接口和恢复边界见[LIFE_OS_CORE](LIFE_OS_CORE.md)。


灵石区Supabase展示复用卡片样式和登录校验；新增安全摘要GET及同源公开Key复制POST。仅新增配置字段识别，不改变现有Storage/数据库连接。服务端密钥永不进入浏览器，普通摘要不含完整公开Key；无持久化新表、编辑配置或外部请求。详见[只读展示](SUPABASE_DISPLAY.md)。

人物分析沿用现有Gateway：紧凑生成Schema与历史读取Schema兼容，输出预算/显式关闭当前百炼DeepSeek思考均按purpose限定。响应诊断仅存数字/枚举，截断不写入成功结果。无架构重构，见[修复说明](PERSON_ANALYSIS_MINIMAL_FIX.md)。

闪光的回忆第7步核心联调已完成，真实云图片/独立恢复待配置，不能标记整体验收关闭。见[最终验收报告](MEMORY_FINAL_ACCEPTANCE.md)。

心愿单第5步：wishes拆分模型、Schema、业务Service、分类Service和路由；价格/故事由Python处理，分类仅文本通过Gateway，外部I/O在业务事务外。物品与心愿共用图片引用保护。

武器工坊第4步复用shining_memories/items Service与私有media资产；价格/时间与排序为Python Decimal派生值，图片归属使用复合FK。无AI调用。

精神导师第2、3步：shining_memories/people拆分人物事件Service、AI授权上下文/缓存/证据校验和Python评分。主副本及杂念仅按显式选择只读访问；预览指纹包含来源、人物版本、模型版本和提示版本，发布前复核。事件日期与人物手填联系日期是事实，热度/推荐分为派生值；GET不调用模型。

闪光的回忆第1步：shining_memories共享认证和页面；shared/images负责解码与去元数据，storage为私有Supabase REST适配器，service负责资产/对象状态机，backup为流式AES-GCM图片快照。上传先持久化pending再外部I/O，发布检查版本，旧对象保留7天，手动清理与备份共用锁。人物、物品和心愿业务按后续步骤增加，不新建聊天系统。详见[模块说明](SHINING_MEMORIES.md)。

藏经阁第5步：四个真实任务入口、真实Clipboard API、数据库计数及新应用持久化联调通过；切换筛选时清空旧视图，失败只显示错误，防止旧资源归属误导。使用/备份见[LIBRARY.md](LIBRARY.md)。


## 藏经阁第3、4步

manual_focus公共宏为主线/副本列表及详情提供书架入口，/library?target_type=quest|task&target_id=UUID只传类型及ID。页面读取本人有效targets再预选，错误/越权目标明确提示，不回退为全部。列表查询按main_quest_id或task_id，归属下拉PATCH成功后重读当前筛选，移走的链接消失；筛选保存在URL，刷新保持。

复制按钮位于每条记录左侧，clipboard.writeText成功后才POST /api/library/links/{id}/copies。剪贴板失败不请求计数；复制成功后计数结果未知时保留操作UUID，显示重试计数，不再次复制。后端身份/归属/可用性检查，同事务保存操作凭据和原子click_count+1；重复操作UUID幂等，同UUID用于另一链接409。普通GET、打开和改归属不加次数。计数不改关联version，避免无关版本冲突。排序重新由数据库返回。


藏经阁第2步：/library共享导航，独立模板、CSS、JS读取本人targets/links；URL文本只作为HTTP/HTTPS新标签链接渲染，noopener noreferrer，不计数。保存不确定时以同一UUID重试，成功保留选择。主题关联筛选/改挂与复制计数分别留第3/4步。


## 藏经阁第1步

library只管理链接，复用identity.current_user、lock_user、quests.same_origin及主副本真实数据/可用性查询，不导入AI模块。GET /api/library/targets、GET/POST /api/library/links、GET/PATCH/DELETE /api/library/links/{id}。分页20条，按click_count降序/created_at降序/id降序。筛选main_quest_id或task_id仅匹配直接关联，不聚合子副本。JSON写入限制32768字节；认证、同源与错误提示不含原始输入。

关联任务软删除/不可用时，默认列表隐藏其链接，但数据库保留；本人详情可读取target_available=false，仍可重新关联或删除。任务恢复后重新出现。标题实时查询。副本可用性沿用现有unavailable_reasons（关联主线删除/归档、里程碑删除、父任务删除）。永久删除受外键RESTRICT/NO ACTION约束，不改变原任务删除语义。


杂念第5步联调：浏览器经真实HTTP与PostgreSQL验证完整输入→归类→主题→原文历史→刷新流程；可控模型用于确定性端到端，真实Kimi语义另见第3步验收。备份范围和容量边界见[DISTRACTIONS.md](DISTRACTIONS.md)。


杂念第4步：页面显式触发已有分类接口，展示已发布主题、待归类和待确认；主题原文通过校验用户及当前run版本的entries接口分页读取，按当前有效原文显示和删除。


## 杂念第3步：分类版本发布

`POST /api/distractions/notes/classifications` 接收request_id；`GET /api/distractions/notes/classification/current`读取保存的分类、数据库次数、待归类/明确未归类ID、最近尝试状态与错误码。只在显式POST调用模型。distraction_classification用途复用Gateway配置/绑定/安全出站与Pydantic校验，单次输出4096 tokens、90秒，无自动重试。原文集合、模型配置版本与thoughts-v2提示词组成缓存指纹。事务外调用，发布前锁用户并复核有效原文/配置/运行状态；全量ID去重且完全覆盖才原子发布，旧版标记superseded保留。失败独立记录错误码，不清除旧版。

大批数据按约16000字符/20条分批，候选主题生成临时UUID，再统一语义合并、展开回原始ID并校验。不超过12次调用；超过11个原文批次或候选主题超过合并窗口明确classification_limit，不截断输入，不发布部分批次。这个同步预算有意限制超大记录集，后续按真实规模再调整。主题次数与最近日期只查询未删除原文，空主题不返回；needs_reclassification标记新增或删除导致的快照变化。页面按钮第4步才接通。


杂念第2步：`/distractions` 使用共享导航和独立模板、JS/CSS；以已登录用户时区展示时间，接口失败保留输入，相同不确定请求复用UUID，输出均使用textContent。主题分类按钮禁用；原文详情侧栏独立滚动，窄屏纵向排列。


## 杂念 V1：独立原文服务

`distractions`仅关联身份模块，复用认证、同源JSON检查、事务及错误响应。POST/GET `/api/distractions/notes`、GET/DELETE `/{note_id}`。原文不可编辑，保留空格换行；请求UUID+SHA256防止重复保存，用户行锁串行化新增与删除。列表按created_at/id倒序，每页20条，next_offset用于继续读取。删除校验expected_version并软删除。不使用浏览器存储持久化，不调用AI，不注册页面或导航。


项目采用 Python/FastAPI 模块化单体、Jinja模板、本地 JavaScript/CSS、SQLAlchemy、Alembic和PostgreSQL。Gateway统一提供AI配置加密、用途绑定、安全出站、调用预算及只含元数据的调用记录。

## 人生运行系统第1步

`life_os` 目前仅提供 `/life-os` 页面骨架和日期/时钟展示。页面布局与样式独立于原业务模块；导航仍复用 `PAGES` 与 `base.html`。页面时区读取已登录用户设置，未登录或数据库不可用时回退到应用时区。时钟由浏览器本地 JavaScript 每秒刷新，不轮询服务器。当前八个区域均为空态或静态说明，没有表、API、AI调用、输入提交或个人分析数据；后续步骤逐步接入真实功能。

## V3 数据流

1. 主线/副本模块继续负责长期任务；manual_focus服务保存人工五色和独立标记版本，不触发完成事件或奖励。
2. startup_items仅关联用户，保存四项输入；CRUD按归属过滤，新增幂等，编辑/删除检查版本，删除采用软删除。
3. startup_state保存手动压力/能量快照和当前引用。滑杆预览后串行自动保存；不依赖AI建议或推荐批次。
4. startup_items.analysis只读取独立事项，逐项在事务外调用AIService(task_analysis)，复查请求/内容/配置后独立提交。缓存与最后尝试分离，失败保留旧结果；过期结果不绘点，信息不足不强行分类。
5. item_analysis.js读取全部事项分页，使用稳定布局绘点，密集时扩展高度。当前状态只影响象限和匹配高亮，移动滑杆不调用模型。
6. startup_chat/session_service提供统一临时会话。GET /api/startup/chat/context检查当前账号与可选目标；POST /api/startup/chat/messages接受模式、最多6轮上下文和状态。会话历史位于标签页sessionStorage，最多12轮显示；不写旧聊天表或正式业务表。
7. 自由对话直接使用自然文本；拆解使用原步骤合同与结构化生成，先澄清再返回1–5步。目标由startup_state/context只读查询并在模型返回后复核；其他任务摘要需用户勾选授权。复制步骤由用户手动录入独立事项。

新会话请求在服务端核对owner_id，退出/换账号清理标签页记录。未知网络结果使用同请求编号，Gateway拒绝重复计费，不自动重发；当前Kimi已验证拆解JSON对象格式和会话90秒预算。事项分类保留原预算与策略。

## 运行入口与退役边界

有效入口包括 /api/quests/{id}/manual-focus、/api/tasks/{id}/manual-focus、/api/startup/current、/api/startup/states、/api/startup/items及其分析子路由，以及新的chat/context、chat/messages。主副本“拆解”通过task_type/task_id进入同一右侧窗口，不创建正式任务。

旧 /api/startup/recommendations、refresh、target、history、chat/conversations、breakdowns及写回子路由已退役；原推荐Service/专属脚本模板和旧永久聊天/拆解写回Service已删除。历史ORM模型仅用于已有表、外键和迁移，显式保留映射，未注册旧业务路由。历史数据库数据没有清理。

原identity、quests/tasks、activity、growth、dashboard、data_tools仍承担唯一业务责任。事项和会话不改经验、金币、计时或完成状态。历史架构演进与证据见 PROGRESS.md、DECISIONS.md和Git标签。
