# 第 7 步：AI 状态对话与确认刷新

已实现，待用户验收。数据库版本 `0011_startup_chat`。完整任务拆解仍在第 8 步。

## 使用方法

1. 登录后打开「启动状态」，在右侧描述当前感受，点击「发送」。默认模型或 `startup_state` 模块指定模型来自灵石区。
2. 信息不足时，AI 会追问。形成建议后，显示压力、能量、象限、主要困难、可能阻力和行动目标。数值是建议。
3. 点击「载入建议，调整后确认」。两个滑杆继续可拖动，困难也可以编辑。
4. 点击「确认并保存状态」；此时「刷新象限与推荐」启用。也可以完全通过滑杆手动确认。
5. 刷新后，右侧显示同一批结果中最多三项绿色任务及理由；象限和主线/副本列表、详情读取相同批次。点击真实任务进入原详情与执行入口。
6. 重开页面可读回已确认状态和最近对话；下拉切换历史对话，「新对话」开始新的上下文。「状态历史」查看确认记录。超过20项时可继续读取更早记录。

聊天、快照和推荐均保存在 PostgreSQL。聊天不会替你完成任务、修改奖励或自动创建子任务。对话内容不会写入调用日志，但会保存到当前账号的对话历史；浏览器存储只延用既有主题偏好。

## 失败和冲突

- 网络未知结果时重试同一提交编号，只读取原轮次；不自动重复调用。已失败的消息仍保留，可明确重新发送。
- AI 输出无效或供应商失败不会改变当前状态；缺少模型时可到灵石区配置，手动状态仍可使用。
- 旧建议、其他页面更新状态或当前对话已有新消息时，确认可能返回冲突；重新获取建议，或读取最新状态后手动确认。
- 刷新失败保留上一批已发布数据；如果状态或任务已经变化，旧数据会明确标为过期并撤下有效颜色。
- 当前继承第5步最多10个有效主线和副本的分析上限，超出会明确提示。
- 任务页面在获得焦点、重新可见或每30秒重读推荐，不是推送式即时同步。

## API 和存储

| API | 作用 |
|---|---|
| `GET /api/startup/chat/conversations?offset=0` | 本用户会话，每页20项 |
| `GET /api/startup/chat/conversations/{id}?before=N` | 消息历史和最新会话版本 |
| `POST /api/startup/chat/messages` | 请求UUID、可选会话UUID、expected_version、message |
| `GET /api/startup/history?offset=0` | 已确认状态历史 |
| `POST /api/startup/states` | 原确认接口增加可选 source_turn_id，保留幂等与代次校验 |
| `POST /api/startup/refresh` | 增加可选 expected_snapshot_id，网页必传 |

写接口复用会话认证及同源检查。聊天和状态输入限制32KiB请求体；消息最多2000字。AI只读取最近六个成功轮次、当前输入和必要的上次确认状态，不读取整个聊天库或任意任务内容。AIService 原有调用限制、512输出token预算和超时继续适用。

新表为 `startup_conversations` 与 `startup_chat_turns`，状态快照增加同用户来源轮次外键。每轮记录输入、结构化回复、处理状态和基础状态代次。外部模型请求不占有数据库事务。未完成请求超过两分钟后，在下一次明确发送时标记中断，不做后台自动重发。

## 验证与运行

日常启动不变：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

新环境先通过本地 `.env` 配置数据库及模型主密钥，再显式执行 `python -m alembic upgrade head`；启动进程不自动迁移。现有开发库已应用本步迁移。

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 真实 PostgreSQL 集成测试只在显式 TEST_DATABASE_URL 下运行，使用唯一隔离 schema。
.\.venv\Scripts\python.exe -m pytest tests/test_startup_chat_postgres.py -q
# 可选无头浏览器验收，需要本机已有 Microsoft Edge；合成HTTP，不发模型请求。
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple -r requirements-browser.txt
.\.venv\Scripts\python.exe tests/browser_startup_chat.py
```

本步实测：默认99通过、38跳过；另5项真实PostgreSQL集成通过；真实模型+数据库+无头浏览器主流程通过；可重复的合成HTTP浏览器测试通过。证据和范围见 [验收记录](ACCEPTANCE.md)。真实模型一次成功调用为645 tokens，费用未查询，开发工时和本次编码Token无法准确获取。

手机真机、跨设备、旧业务完整回归和V2数据导出范围在后续验收，不能以无头窄屏测试代替。第8步完整拆解未实施。
