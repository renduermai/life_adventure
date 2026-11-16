# 总体架构

V3第5步新增session_service/router/schemas，复用原拆解的Step合同、结构化模型调用及owner-scoped target_context，替换右侧旧页面。GET /api/startup/chat/context返回当前账号/可选真实目标；POST /api/startup/chat/messages接收owner_id、模式、最多6轮有界上下文及当前压力能量。服务端重新验证目标归属，默认不读取其他任务摘要；用户勾选后才发送有效任务摘要。自由模式自然文本，拆解模式JSON对象及Pydantic校验，服务端不保存聊天正文、不写正式任务或独立事项。

V3第4步新增startup_items.analysis及item_analysis.js。前端读取全部有效独立事项分页数据，按用户明确点击依次POST /api/startup/items/{id}/analyze。每项短事务预留请求，事务外AIService(task_analysis)调用，再复查请求、四字段指纹和模型配置后独立提交。模型只读取事项ID与描述/重要/紧急/进展，不接主副本或当前压力能量；错误ID拒绝发布。无任务队列、无自动重发未知模型结果。GET仅读取持久化结果，不调用模型。内容过期保留旧结果但不绘点，部分失败不撤回其他成功项。

V3第2步新增startup_items模块（models/schemas/service/router），通过/api/startup/items的列表、读取、POST新增、PATCH编辑和DELETE软删除为页面提供独立事项。全部查询按用户过滤；写入持用户锁，编辑/删除核对expected_version；新增使用请求UUID和内容指纹避免重试重复。前端只用textContent展示事项，保存失败保留草稿。沿用原导出入口，新增表纳入用户数据导出。

V3第3步复用GET /api/startup/current和POST /api/startup/states；滑杆input只预览，450ms停拖或change后串行保存。以请求UUID支持未知网络结果重试，代次检查阻止旧请求覆盖更新；409后读取代次并保留本地输入待用户重试。新版页面不加载recommendations.js，不请求推荐批次或绘主副本散点。聊天去掉数值建议载入按钮，仍用原有Service；第5步再统一会话。

V3 第1步通过独立manual_focus模块提供PATCH /api/quests/{id}/manual-focus和/api/tasks/{id}/manual-focus。用户锁、归属检查及独立标记版本防止并发覆盖。四个主副本页面不加载旧推荐脚本，拆解入口保留。现有启动状态旧链路留待后续迁移。


第三次改进沿用 `startup_chat` 会话与 `task_recommendation` 的候选/已发布批次。发送消息前在用户事务中读取有效任务摘要、当前推荐和已确认状态；选中目标再次通过归属和可用性校验，最多20项简短摘要进入模型上下文，超出数量明确给出计数。会话仅新增选中目标 key，消息始终附带当前选择；模型调用仍在事务外。前端以同一状态快照显示确认摘要，推荐刷新使用现有 `expected_snapshot_id`，选择任务走原有拆解模式 URL。AI 回复不修改主线、副本或确认状态，数值建议仍需用户载入滑杆后确认。

启动状态四象限散点从既有 `/api/startup/recommendations` 读取最新发布批次；读取服务仅对仍有效且属于当前用户的任务补充标题、描述、类型及所属主线。前端仅给非过期且已分析的目标绘制可点击标记，象限取已保存分类的首项，象限内槽位由目标 key 的稳定哈希决定，用于避免重叠，不声明任务的精确压力/能量坐标。当前状态圆点仍只由压力、能量滑杆控制。待确认项保留在推荐列表，不渲染散点；无新模型调用或数据库迁移。

启动状态推荐可靠性改进：网页刷新调用既有推荐服务；服务逐个调用 AIService，成功特征立刻以目标指纹写入 task_analysis_cache。单项失败只在本批次记录错误，不影响其余目标；最后核对快照代次、任务结构和模型配置后整批发布成功/待分析结果。读取接口用同一批次返回成功数、待分析数与安全原因；仅已分析项取得四色等级。单项重试仍走同一刷新入口并复用缓存。

## V2 第 8 步（2026-11-15）

startup_chat 新增 breakdown_models/schemas/service/router，按目标隔离拆解方案和反馈历史。首次入口点击附带生成操作UUID，页面通过POST调用；成功后移除导航操作参数，刷新读取历史，不重新生成。再次进入已有方案优先复用，明确反馈/重生成建立新版本。

模型调用在事务外，结果发布前复查目标上下文、状态快照及原草稿revision。确认使用同一用户锁/事务调用原 tasks.execute；里程碑创建从原路由提取到 quests.create_milestone，旧页面复用该服务并保留事件。清单勾选仅更新计划独立状态，不触发完成或奖励。执行准备验证真实副本，返回原 /focus?task=UUID，计时仍需用户在原入口开始。

主线保存副本/里程碑/清单；普通副本保存一层子任务/清单；重复副本或已有子任务仅清单。反馈中的新状态建议通过 source_plan_id 走原状态确认接口，不能自动修改状态。

## V2 第 7 步（2026-11-15）

新增 startup_chat（models/schemas/service/router）。用户行锁下预留会话轮次并提交，事务外调用统一 AIService 的 startup_state 用途，再以短事务写回回复。一次 ChatTurn 保存一条用户消息及一条结构化回复，包含状态/请求指纹和基础状态代次；不是运行日志。只传最近六个成功轮次和必要已确认状态。

确认复用 startup_state 写入接口，附带可选 source_turn_id；服务端复查同用户、成功且足够完整、最新会话轮次与状态代次，随后写快照来源。推荐仍经 task_recommendation 发布；前端传 expected_snapshot_id 阻止刷新其他页面刚改过的状态。右侧行动建议由共享推荐响应筛选前三项绿色任务，不独立调用 AI 生成另一组任务。

## V2 第 6 步（2026-11-15）

第 6 步旧页面通过共享模板宏和静态脚本读取 /api/startup/recommendations，同一响应更新整页。启动状态象限同步加入焦点/可见性/30秒重读；失败清除可点击旧标签。新增只读 /api/startup/target，复用任务可用性、归属、主线进度查询；加载上下文后显示拆解占位，不调用模型。上下文也在状态或批次刷新及30秒检查时更新。

## V2 第 5 步（2026-11-15）

新增 task_recommendation 领域，使用当前状态快照、任务特征缓存和推荐批次。外部模型请求在事务外执行；发布前复查用户代次、任务结构、模型版本和人工修改版本。失败不覆盖已发布结果。当前快照变化或任务变化时，读取显示过期，禁止把旧颜色当最新。

## V2 第 4 步

启动状态采用独立快照和当前引用；用户行锁、请求编号和代次检查保障用户隔离及并发一致性。滑杆在浏览器同步更新坐标预览，确认后服务端保存。

## V2 第 3 步页面

灵石区使用服务端模板及同源静态 JavaScript，通过既有 /api/ai 接口管理配置，动态文字使用 textContent；API Key 仅经 HTTPS/本机请求提交，编辑框不回填，未使用浏览器存储。本步未新增业务表。浏览器验收待完成。

## 2026-11-15 V2 第 2 步实现

ai_gateway 已实现 models/schemas/security/adapter/service/router/manage；FastAPI 挂载 /api/ai JSON 接口，继续使用数据库会话及同源写入校验。OpenAICompatibleAdapter 隔离协议，AIService 选择本用户配置并用短事务记录调用，模型请求不持有数据库连接。公网地址验证绑定实际 TLS 连接，禁代理/重定向/自动重试。密钥仅在服务端 Fernet 加密解密，默认模型和调用防重以用户锁和数据库唯一约束协调。

本步没有灵石区页面；后续 startup_state/task_recommendation/startup_chat 尚未实施。当前能力及限制见 [V2_STEP_2.md](V2_STEP_2.md)，旧第 1 步“尚无 AI 模块”是交付时历史。

## 2026-11-15 当前架构与 V2 第 1 步设计

实际代码已到阶段 1.9：FastAPI 模块化单体、SQLAlchemy/Alembic、Supabase PostgreSQL、Jinja2、普通 CSS 与少量 JavaScript；已有 identity、quests、tasks、activity、growth、dashboard、data_tools。现有主题、侧栏、会话、权限、事务、任务命令、计时及奖励复用。HTMX 仍为可选后续工具，不是当前已使用依赖。

V2 第 1 步仅整理设计，没有新增模块或改动运行时。完整契约见 [V2_STARTUP_DESIGN.md](V2_STARTUP_DESIGN.md)。拟新增 ai_gateway（统一模型与密钥）、startup_state（确认状态）、task_recommendation（特征/规则/批次）、startup_chat（状态对话/拆解确认），按 V2 第 2–8 步分别实施。

新模块通过原 quests/tasks 查询与命令服务接入，不复制主线、副本、进度或奖励事实。现有 quests 的部分写入仍在 router 中，按需要小范围提取；tasks.execute 作为确认后创建任务入口。公共身份/同源辅助函数按需整理，不重构整个项目。

一致性契约：用户确认输入 → 读取真实候选及指纹 → 事务外 AI/规则计算 → 发布前检查代次与目标变化 → 短事务保存整批结果及当前状态/批次引用。页面统一读取该批次，任务变更显示过期；正常 AI 失败保留上次完整结果。仅手动保存新状态时清空当前推荐引用，不能配旧颜色。

跨页面只传类型与 UUID；每次进入、对话、生成和确认都复查所有权与有效性。草稿和正式对象分离，确认事务复用旧业务服务、事件和幂等；行动清单不自动增加任务进度或奖励。外部 AI 请求不持有数据库事务/用户锁，不采纳模型生成的 URL 或任意业务命令。

API Key 由服务端认证加密并通过环境主密钥解密；配置查询仅掩码；出站统一做地址和实际连接验证。上述安全能力尚未实现。当前认证是受控本地基线，正式部署仍需 HTTPS、可信代理、限流及最小权限等验收。

下文为原阶段交付和设计历史。涉及“尚无 modules/业务表/认证”“数据库未连接”的旧段落已被本节及各阶段更新取代，不代表当前源码状态；不删除原验收证据。

## 阶段 1.9 更新

1.9 采用只读一致性快照导出当前用户的数据，恢复入口复用原有领域路由；导出不含密码散列、会话或数据库密钥。


## 阶段 1.8 更新

1.8 首页通过 dashboard 查询服务按用户归属聚合现有主线进度、任务、历练和奖励事实，不复制业务数据。


## 阶段 1.7 更新

1.7 奖励服务与任务完成、撤销操作共享事务；用户行锁、任务事件唯一约束和奖励来源唯一约束确保重复提交不会重复发奖。余额与等级从流水汇总。


## 阶段 1.6 更新

1.6 手记使用 activity 现有记录作为统计唯一来源，服务端处理手工记录、筛选、权限及版本检查，审计事件与记录在同一事务写入。


## 阶段 1.5 更新

1.5 计时由 activity 服务端维护专注会话及区间；结束与行动记录在同一事务，用户行锁及会话唯一约束保证重复结束不重复记录。页面仅显示计时，权威时长在服务端计算。


## 2026-11-10 阶段 1.4 更新

新增 tasks 领域模型、服务及服务端页面。任务写入、事件、下一期和请求幂等记录在同一事务；用户行锁与版本检查协调并发。主线通过任务查询服务聚合有效末级任务。

下文历史状态以本节和 PROGRESS.md 为准。

## 2026-11-10 变更

新增 identity、quests 领域模型与服务，使用单用户本地账号、Argon2 密码散列、服务端数据库会话和 HttpOnly/SameSite Cookie；表单写入校验同源 Origin。查询与更新必须限制用户归属。主线及里程碑由服务端处理，使用同一数据库事务记录 quest_events。数据库迁移执行至 0003_quest_events。此为本机运行基线，尚无登录限流、密码重置与公网生产加固，不能直接公网部署。

下文保留阶段 0 架构设计历史，实际阶段状态见 PROGRESS.md。

0.1 架构基线已验收；当前工程实施到 0.6，基础页面与健康接口已运行验证。业务功能和公网部署尚未实现，真实数据库连接与在线迁移尚未验收。

## 技术栈与运行形态

规划采用 Python + FastAPI、SQLAlchemy 2.x、Alembic、Supabase PostgreSQL、Jinja2 + HTMX、普通 CSS、少量 JavaScript、pytest 和 Git。0.2 实测 Windows Python 3.11.9、FastAPI 0.162.2、Uvicorn 0.54.0、Jinja2 3.1.6；0.4/0.6 已加入 SQLAlchemy 2.1.8、Alembic 1.20.1、psycopg 3.3.8、pydantic-settings 2.16.2 与 pytest 9.2.0；HTMX 在出现需要局部交互的业务页面时再引入，当前普通导航与少量 JavaScript 已足够。依赖按 requirements.txt 和 constraints.txt 固定，详见 [环境说明](ENVIRONMENT.md)。

模块化单体部署：浏览器 → FastAPI 路由/模板 → 应用服务 → 领域服务/Repository → PostgreSQL。前端不直接写业务数据库。Python 优先适合表单、任务管理与统计；复杂计时展示和图表保留少量 JavaScript。此阶段无需 SPA、微服务、Redis 或消息队列。

当前以 Windows/macOS 本地服务为目标；云端数据库需要网络。未来服务器运行同一应用，域名、HTTPS、反向代理和生产运维在阶段 5 实施。手机布局在基础 UI 中考虑，在部署阶段实机验收。

## 目录规划

当前已有 app/main.py、core/config.py、core/database.py、core/logging.py、templates/、static/css/、static/js/、migrations/、tests/、配置样例及三份依赖清单。尚未创建 modules/、shared/ 或任何业务表；core/security.py 和 events.py 按业务需要后续实现。下方为总体目录规划，并非所有文件都已存在：

```text
app/
  main.py
  core/           # 配置、数据库会话、身份上下文、内部事件基础
  modules/        # 按获批领域逐步添加
  shared/
    services/     # 必要的跨模块用例协调；禁止堆放所有业务
    schemas/
    utils/
  templates/
  static/{css,js,images}/
migrations/
tests/
docs/
.env.example
.gitignore
requirements.txt
```

领域模块按需要建立 models.py、schemas.py、repository.py、service.py、router.py 和 events.py，不机械创建空文件。测试规划置于根 tests/，按 modules/ 和 integration/ 分组；该组织方案随 0.1 验收确认，0.6 已创建 pytest 框架与基础测试。

## 模块责任与数据所有权

| 模块 | 唯一写入责任 | 其他模块使用方式 |
|---|---|---|
| identity | 用户、角色基础资料 | 获取经过认证的用户上下文 |
| quests | 主线、里程碑及状态历史 | 主线查询与进度服务 |
| tasks | 任务、关联、状态转换 | 任务命令和查询接口 |
| timer | 专注会话、暂停与恢复 | 会话生命周期接口 |
| activity | 行动与手工时间记录 | 记录和时间汇总接口 |
| growth | 经验流水、等级规则 | 奖励、冲正和等级查询 |
| economy | 虚拟金币流水与兑换 | 入账、冲正及余额查询 |
| calendar / analytics | 日历与聚合查询 | 读取已有事实，不复制维护完成状态 |
| sprint / ai | 复盘计划 / 统一模型调用 | 使用已授权数据与正式业务命令 |
| equipment / notes / achievements | 物品 / 内容 / 成就 | 各自服务接口，按阶段增加 |

设置按所属领域管理；设置中心聚合入口，不绕开领域规则。跨模块用例协调器可以依赖多个公开 Service；Service 不反向依赖协调器，Repository 不导入其他领域内部实现。应用启动处负责装配依赖。

## 任务完成事务（接口草案）

公开命令草案：CompleteTask(user_context, task_id, request_id)。不是已实现 API，具体 HTTP 路径待 1.4 提案确认。

1. 校验身份、任务归属、有效关联、软删除和当前状态。
2. 在同一数据库事务中锁定目标任务，确认请求是否已处理。
3. tasks 执行状态变更，记录 completion_event_id、完成轮次和时间。
4. 应用层分发 TaskCompleted；activity 保存行动，growth 与 economy 按服务端规则写奖励流水。
5. 各处理器共享事务会话，仅 flush，不独立 commit；任一失败则全部回滚。
6. 最外层提交后返回成功。主线和首页按统一查询规则读取最新进度与余额。

事件草案包含 event_id、event_type、schema_version、user_id、aggregate_id、occurred_at、payload；payload 只带必要信息。内部事件为同进程同步处理，不宣称可靠异步投递。将来若出现提交后必须可靠执行的外部操作，再单独评审 outbox；目前不建相关设施。

唯一约束负责最终幂等保障，不能只依赖按钮禁用或内存集合。已完成任务换 request_id 重试也不能再次奖励。撤销使用 TaskCompletionReversed，引用原完成事件并产生唯一冲正；再完成采用新的合法完成轮次，重复完成和重复撤销均应幂等。

## 进度、计时与统计

- 进度由 quests 的统一查询服务提供，根据真实任务聚合；零任务的主线显示“尚未配置”，不伪装为 100%。任务权重、子任务计入和归档处理在对应模块确定。
- timer 在服务端保存开始、暂停、恢复、结束状态；前端仅显示，不作为有效时长权威来源。暂停区间存储方式与同用户活动会话约束在 1.5 决定。
- 一条结束会话对应至多一条自动时间记录；activity 是时间统计的统一入口，不能同时累加会话和它生成的记录。
- 异常中断补录保留来源和修订记录；客户端断开不能自动当作有效投入或自动完成任务。
- 时间使用 UTC 时刻和用户 IANA 时区；本地日期边界转为 UTC 区间查询。跨日记录如何拆分在 1.6 确认。
- 等级由经验规则与净经验计算，金币余额由有效流水求和；未来缓存须可从流水重建。

## 身份、安全和异常

身份认证方案尚待选定，候选为 Supabase Auth 或后端本地账号认证，不在 0.1 实现。业务服务使用统一 UserContext，不能信任客户端提交的 user_id。数据库查询和关联同时校验归属，防止跨用户关联。

浏览器会话需要安全 Cookie、适当 CSRF 防护与服务端输入校验；具体机制随 1.1 确认。数据库最小权限运行角色与迁移角色分离。ORM 直连不会自动继承 Supabase Auth 的 RLS 用户上下文，不能将启用 RLS 当作应用权限校验已完成；是否采用 RLS 纵深保护需单独决策。

连接失败返回可理解的错误，不回显密钥、SQL 或连接字符串；事务失败不报告已保存。日志使用请求标识关联错误并脱敏。迁移与应用连接分开配置，直连或会话连接池根据实际网络验证；不擅自降级为 SQLite。

## AI 与未来扩展

AIService 统一管理提供商、模型、超时、结构校验和可获得的用量数据。AI 草稿与正式任务分离；用户确认后的保存通过业务服务执行，不能绕过权限和事务。Agent、RAG、第三方日历及通知未来以新模块接入，不提前实现。

## 官方参考

- [FastAPI 模板](https://fastapi.tiangolo.com/advanced/templates/)
- [SQLAlchemy 事务](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [Supabase PostgreSQL 连接](https://supabase.com/docs/guides/database/connecting-to-postgres)

上述资料于 2026-11-09 在首次提案时查阅。0.3–0.6 已验证 HTTP 与页面交互；数据库状态映射使用明确标注的单元模拟测试，真实 PostgreSQL 集成测试未配置而跳过。业务运行时尚未实现。

## 阶段 0 已实现接口与边界

- GET /、/journey、/settings：服务端 Jinja2 完整页面，当前不提供数据写入。
- GET /health/live：进程状态，独立于数据库。
- GET /health/ready：执行真实 SELECT 1 与 public.alembic_version 版本核对；未配置或未准备好返回 503。
- Database.transaction()：上下文管理事务，正常退出提交、异常回滚；尚未接入业务模块。
- 应用从不自动建表或执行迁移；Alembic 使用单独迁移连接。
- 日志只记录请求方法、状态和新生成的请求 ID；不记录查询字符串和数据库异常详情。
- 当前无身份认证，仅绑定 127.0.0.1 作本地基础验证；阶段 1.1 才加入账号能力。
