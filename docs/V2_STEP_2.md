# V2 第 2 步：灵石区后端

日期：2026-11-15（Asia/Shanghai）。用户“开始第二步”授权本步，随后明确授权使用百炼配置执行连接测试。范围为后端与安全、迁移、自动化测试；第 3 步网页尚未批准。默认测试 71 passed、33 skipped；另 4 项真实数据库后端集成测试通过。在线迁移和真实模型连接已完成，旧核心流程本轮因网络连接超时未完成回归；详见 PROGRESS 和 ACCEPTANCE 顶部。

## 实现与使用

新增 app/modules/ai_gateway：models.py、schemas.py、security.py、adapter.py、service.py、router.py、manage.py。新增 0008_ai_gateway 迁移，创建 ai_configs、ai_module_bindings、ai_call_logs；现有任务、计时、奖励表不变。FastAPI 装配路由，配置增加 AI_ENCRYPTION_KEYS，运行依赖增加 cryptography==50.0.2。密钥保存在未跟踪的 .env 及数据库密文中，普通数据导出白名单未加入这些表。

应用仍按 README 启动。没有新增灵石区网页，使用以下本地管理命令；凭据从项目根 .env 读取，不作为命令参数：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.modules.ai_gateway.manage import-env
.\.venv\Scripts\python.exe -m app.modules.ai_gateway.manage test
```

迁移需 MIGRATION_DATABASE_URL；import-env/test 需要已创建唯一角色账号和可用 DATABASE_URL。import-env 从 AI_TEST_BASE_URL、AI_TEST_MODEL、AI_TEST_API_KEY 及可选 AI_TEST_EXPIRES_ON 导入当前账号，设为默认；反复导入更新同一入口。test 只发送“Reply with OK.”，会产生供应商实际调用费用，不发送用户任务或对话。不把任何真实凭据写入本说明。

AI_ENCRYPTION_KEYS 为逗号分隔的 Fernet 密钥列表，第一把用于加密，其余用于读取旧密文。缺失/无效主密钥时拒绝密钥保存和调用，不阻碍原有任务模块。请独立保管主密钥，丢失后无法从数据库解密供应商密钥。轮换先配置“新密钥,旧密钥”，执行以下命令并核对后再移除旧钥：

```powershell
.\.venv\Scripts\python.exe -m app.modules.ai_gateway.manage rotate-keys
```

本步已在本地 .env 保存用户提供的测试配置及生成的加密主密钥。到期日 2026-11-17 来自用户填写，不代表查询到了供应商真实到期日。

## 已实现接口

所有接口位于 /api/ai，要求现有 camp_session。写入同时要求同源 Origin，JSON 请求体最多 32 KiB。输入错误使用统一安全文案，不回显原请求值。

| 方法/路径 | 行为 |
|---|---|
| GET /configs | 当前用户未删除配置，密钥只返回 has_key 和固定掩码 |
| POST /configs | CreateConfig 全字段、api_key、UUID request_id；相同输入重复提交不新增 |
| GET /configs/{id} | 单项脱敏配置和版本、最近测试及是否过期 |
| PATCH /configs/{id} | 全量非密钥字段和 expected_version；空 api_key 保留旧值；enabled 控制启停 |
| DELETE /configs/{id} | expected_version；清空密文、移除绑定并软删除元数据 |
| POST /configs/{id}/default | expected_version；用户行锁协调唯一默认；禁用配置不能设默认 |
| POST /configs/{id}/test | expected_version、UUID request_id；固定短文本测试，返回用量和调用编号 |
| GET /module-bindings | 当前用户模块选择 |
| PUT /module-bindings/{module} | config_id 或 null；null 删除绑定并使用默认 |
| GET /calls | 最近 100 条调用元数据，不返回提示词、回复、指纹或密钥 |

模块白名单为 startup_state、task_analysis、breakdown、quest_generation、review、character。后续模块按公开 AIService.generate 调用，可指定配置或使用模块绑定/默认；选中配置不可用时明确失败，不静默回退。

编辑字段为 name、base_url、model_id、protocol、expires_on、notes、enabled；协议仅 openai_compatible。编辑和默认切换增加版本，旧连接测试显示 stale；到期日仅用于展示提醒，不声称能自动判断供应商有效期。默认入口停用后要求重新选择，模块指定已停用入口同样明确失败。

## 调用、安全与成本边界

采用标准库 HTTPS 客户端，所有请求统一经过公网目标校验。只接受 HTTPS/443，无 URL 凭据、查询或片段；校验全部 DNS IPv4/IPv6 地址，拒绝内网、回环、元数据、保留与映射地址。连接固定到验证后的数值 IP，TLS SNI/证书仍校验原主机。关闭重定向，无环境代理、无发送后自动重试；优先 IPv4，不自动换地址重发已发送请求。DNS 有 10 秒等待及至多 4 个解析工作线程，网络套接字 10 秒超时，另设 60 秒总截止检查/关闭计时器；底层关闭/调度可能有少量延迟，不能视为实时强终止。

多轮消息最多 30 条、序列化正文 24000 字符；单次 max_tokens=512、响应最多 1 MiB、回复最多 32000 字符。结构化输出采用 schema 提示和 Pydantic 最终校验，不假定所有兼容供应商都支持原生 JSON 模式，也不自动发第二次修复请求。未通过校验的输出不进入正式任务。

每用户最多一个运行请求、每分钟最多 20 次；用户行锁和调用请求唯一约束跨进程防重复。超过两分钟仍 running 的请求在后续新请求中标 unknown。重复编号返回 409 并不再调用；完整回复不存调用日志，因此本步不提供按旧编号重放完整回复。发送后超时/连接断开可能已经计费，标 unknown，用户主动新编号重试。多用户全局出站并发上限尚未单独实现，当前应用只允许创建一个角色账号；未来多用户开放时需补充全局预算。

外部请求前提交 running 日志并释放数据库连接，返回后新事务更新状态、时长、可获得 token 用量与安全错误码。配置在请求期间被修改时，不把旧版本测试结果写成新版本结果。完整对话/回复均不写日志；usage 只采纳非负整数字段，缺失为 null，金额未知不伪称零费用。

加密使用 Fernet/MultiFernet；可执行同事务轮换。密文不返回前端，主密钥不入库，删除配置清除可调用密文并保留非敏感调用历史。未来页面还需安全渲染、部署还需 HTTPS/可信代理/限流等原定加固；本步不宣称生产部署验收完成。

## 验收与测试方法

1. 运行默认 pytest 和 pip check，记录实际通过/跳过数。
2. 显式 TEST_DATABASE_URL 的隔离 schema 验证迁移往返、ORM 一致性、配置持久化、版本、默认、绑定、越权、密钥轮换与并发请求防重。
3. 使用本地管理命令导入并测试百炼；查看 GET /api/ai/configs 和 /calls，不应出现 API Key/密文。
4. 用错误版本重复编辑、无 Origin 写入、其他用户读取目标，均应被拒绝。
5. 无效地址、混合公网/内网 DNS、IPv6 映射、重定向和超大响应由自动化测试覆盖；公网 DNS 重绑定通过固定 IP/TLS 主机测试验证实现边界，不宣称完成外部渗透测试。

首次单元测试发现并修复了内网 URL 异常被当作域名解析异常吞掉的问题；首次离线迁移发现并修复外键类型未解析产生 NullType 的问题。网络验证曾遇到 DNS 失败、数据库部分地址超时、模型首次超时；后续重试结果以验收记录为准。测试模拟与真实供应商调用分开，跳过不算通过。

本步不实现灵石区页面、象限、推荐或拆解；不开始第 3 步。实际工时/Token 没有可靠全程统计，无法准确获取。
