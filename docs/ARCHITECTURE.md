# 总体架构

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
