# 人生运行系统第2步交付（2026-11-26）

## 使用

登录后打开 http://127.0.0.1:8000/life-os ，输入发生的事情，勾选向当前模型发送本轮及必要近期对话的授权，点击“保存并分析”。原文先独立提交；失败后可从原记录手动重试，不重复保存原文。刷新读取持久化历史，不调用模型。状态三项可留空（未知）或填0–100，保存校准会保留旧快照。每条记录可查看分析与校准历史。

## 已实现

- 原文保存、时间、用户归属、提交编号幂等、历史20条分页。
- 多轮上下文来自本人最近最多6条消息及对应回复，总内容有字符上限；不会发送全部历史、主副本、杂念或其他用户数据。
- 核心回复、能量/带宽/秩序（可为空）、理由、矛盾、诱因、可能行为、行为贡献、长远/当下方案、层次和建议模式、后续更新标志。
- 灵石区默认模型/用途绑定通过现有Gateway选取。life_os_core单独4096输出预算和90秒超时；当前百炼deepseek-v4.1-flash关闭思考，其他用途原预算保持。
- 外部调用不占数据库事务；Pydantic严格校验及真实来源ID白名单，截断拒绝。失败保留原文、此前成功快照与失败原因。
- 每用户串行分析，3分钟未结束的尝试可明确手动重试；同一请求编号不再次计费，无自动重试或轮询。
- AI建议模式与调度标志仅保存，不自动执行后续模块。用户校准新增独立快照，后续分析可读到。

## 文件与接口

`app/modules/life_os/{models,schemas,service,router}.py`；`app/templates/life_os/page.html`；`app/static/{js/life_os.js,css/life_os.css}`。

- GET /api/life-os/messages?offset=0
- POST /api/life-os/messages
- POST /api/life-os/messages/{id}/analyze
- GET /api/life-os/messages/{id}/analyses?offset=0
- POST /api/life-os/analyses/{id}/state

所有数据接口校验登录和归属，写入复用同源检查；日志仅错误码与异常类型。原文只返回本人授权接口，前端使用textContent。

## 数据与恢复

Alembic 0028_life_os_core 从0027增量建立life_os_messages、life_os_analyses两表；无原表删除/字段改写。readiness常量同步，媒体备份接受0028是因为本次未改变媒体结构，媒体快照仍不包含聊天。

完整恢复需 PostgreSQL 全表备份和原 .env 的 AI_ENCRYPTION_KEYS。既有应用JSON/CSV导出仍不包含本模块，不能当作完整备份。迁移前生成同电脑加密检查点于用户adventure-camp-private-backups目录，密钥在keys目录；它不是异地备份，也没有完成全库恢复演练。迁移前后原40张表数据逐表规范化比较一致；在线0028，Alembic check无差异。

## 验证与边界

完整默认测试187 passed、83 skipped；跳过为未显式配置的真实数据库/模型/云端测试，不算通过。既有Starlette/httpx弃用警告1条。真实PostgreSQL随机schema初轮3 passed，含当前默认模型合成调用；输出完整合法，来源ID有效且保存读回。模型deepseek-v4.1-flash，prompt_tokens=1081、completion_tokens=272、total_tokens=1353；仅单个合成样例，不保证任意私人输入永不失败。

隔离PG+Edge专项验证原文幂等、跨用户拒绝、校准、上下文、非法来源、超时/截断保留、刷新、390px和无JS异常。迁移在测试schema执行check及降级再升级。线上服务健康和页面实际HTTP检查；无私人原文发往模型，未改写原有任务、人物和杂念。

此处保留第2步交付时的阶段记录。问题库见[LIFE_OS_PROBLEMS](LIFE_OS_PROBLEMS.md)，第4–6步当前状态见[LIFE_OS_STEPS_4_6](LIFE_OS_STEPS_4_6.md)；第7–10步未开发。实时钟表沿用第1步。实际Codex Token、费用和工时无法准确获取。
