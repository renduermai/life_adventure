# 总体架构

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
