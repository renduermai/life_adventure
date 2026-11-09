# 总体架构

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
