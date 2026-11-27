# 灵石区：Supabase只读配置展示（2026-11-22）

## 使用与实际配置

登录后打开 `/spirit-stones`，原大模型列表下方显示「Supabase 云端服务」。点击卡片或「查看配置」展开详情；Project URL是项目API地址，Dashboard是管理控制台，分别展示。Project URL可复制；已配置的公开Key默认全遮罩，通过专用按钮复制。控制台在新标签页打开。

本轮检查实际项目根.env由app/core/config.py的ROOT/.env绝对路径加载：SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY、SUPABASE_STORAGE_BUCKET均已配置；Publishable、anon、单独Secret变量未配置。当前页面整体显示已配置，公开API Key显示未配置且复制按钮禁用，服务端密钥仅显示已配置。可可靠识别当前Project Ref，Dashboard指向对应项目。

没有为展示填写或生成任何Key，没有修改.env或连接。配置状态表示项目URL有效、服务端密钥及桶配置存在，不是实时数据库或Storage连接测试。不要求公开Key存在才显示已配置。未知Project Ref使用控制台首页；无效或含认证/查询信息的项目URL不会回显。

## 范围与安全

修改4个业务文件：app/core/config.py、app/modules/ai_gateway/router.py、app/templates/spirit_stones.html、app/static/js/spirit_stones.js。新增tests/test_supabase_display.py、tests/test_supabase_display_postgres.py及受影响文档。复用ai-grid/ai-card/card/form-stack及现有登录、Origin校验；不新增CSS或依赖。

- Settings仅新增三个SecretStr字段用于识别Publishable/anon/Secret；已有service_role读取、Storage调用、数据库连接和模型服务不变，不把新增Secret字段接入连接逻辑。
- GET /api/ai/supabase仅返回URL、状态、Key类型及全遮罩；无完整公开Key或任何服务端Key。响应no-store、Vary:Cookie，不序列化Settings。
- POST /api/ai/supabase/public-key/copy复用登录和同源Origin校验，只返回可公开Key，no-store；缺失或不符合公开类型返回409。无在线编辑、密钥查看或服务端密钥复制接口。
- 优先已有Publishable配置，其次已有anon配置。识别sb_publishable_格式或JWT载荷role=anon，并拒绝与服务端配置相同的值；sb_secret_和role=service_role即使误放公开配置也不可复制。JWT角色识别仅用于防止误展示，不承担签名验证/用户认证。
- 完整公开Key只在明确复制操作的响应与临时剪贴板写入中出现，不放入DOM、HTML源代码、脚本常量、持久化浏览器存储或日志。服务端Key始终不返回浏览器。
- 所有登录用户沿用现有权限可查看这份部署级服务的安全摘要；没有增加管理员或多项目切换体系。

## 验证范围

针对性测试覆盖缺失配置、Publishable优先和anon回退、服务端误填拒绝、Dashboard可靠识别/首页回退、URL安全过滤、普通响应脱敏、复制操作同源与登录拒绝、HTML/脚本/日志无Key。合成账号下使用Edge真实剪贴板验证两类复制，检查原模型卡片可见且编辑正常、未配置按钮禁用及390px无横向溢出。

PostgreSQL测试只写随机隔离schema，不修改正式用户数据。物品/心愿回归的图片存储采用现有替身，不将其称为本轮真实云图片上传验证；本轮只读UI不进行新的AI调用或真实图片上传/删除。

## 本轮结果

- 针对性7 passed；完整默认174 passed/78 skipped（6.46秒）。
- 隔离PostgreSQL+Edge及原Gateway、物品、心愿回归10 passed/1 skipped（263.84秒）。跳过的是未显式启用的真实模型心愿分类；本轮不需要付费模型调用，跳过不算通过。
- 各测试组有1条既有Starlette/httpx弃用警告。Node语法、pip check及修改文件git diff --check通过（既有CRLF转换提示无错误）。.env继续被Git忽略。
- 现有Windows启动脚本已重启本项目服务；/health/live、/health/ready和/spirit-stones均HTTP200，未登录/api/ai/supabase为401。当前实际配置显示已配置、公开Key未配置、服务端Key已配置及项目Dashboard可识别。
- 无数据库迁移，未修改.env、现有凭据、业务表、数据库/图片连接或AI调用逻辑。实际开发总Token无法准确获取。

交付后停止，等待用户验收。入口 http://127.0.0.1:8000/spirit-stones 。
