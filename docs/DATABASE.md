# PostgreSQL 与迁移指南

## 当前状态

用户在 2026-11-09 确认数据库“暂未准备”。已完成连接、错误处理、事务入口与 Alembic 基础代码，未连接真实 Supabase、未执行在线迁移。0.4 真实数据库验收未完成。

阶段 0 不建立用户、任务等业务表。`0001_stage0` 是空业务基线；在线 upgrade 会由 Alembic 管理 `alembic_version`，不引入模拟业务数据。

## 配置步骤

1. 准备 Supabase 开发项目，不使用已有生产业务库验证。
2. 在项目根目录将 `.env.example` 复制为 `.env`。只在本地填写实际连接字符串，不能提交到 Git 或粘贴到日志。
3. `DATABASE_URL` 填应用角色连接，`MIGRATION_DATABASE_URL` 填迁移角色连接。代码不会把应用连接静默当作迁移连接使用。
4. 使用 `postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require` 格式；密码特殊字符需要 URL 编码。程序也接受 `postgresql://` 并规范为 psycopg 驱动。
5. 迁移使用直连，IPv4 环境可使用 session pooler。代码拒绝常见 transaction pooler 的 6543 端口。远程连接要求至少 sslmode=require；需要证书身份校验时用 verify-full 与官方 CA 配置。

运行角色按最小权限提供 schema 使用权和必要查询权限，至少需读取 `public.alembic_version` 才能验收 readiness。迁移角色需有该开发库建表权限。当前未创建角色、授予权限或设置 RLS。账号与数据隔离在 1.1 实现，不能将阶段 0 页面当成已具备认证的生产应用。

参考：[Supabase 连接方式](https://supabase.com/docs/guides/database/connecting-to-postgres)、[Alembic 教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)。

## 迁移命令

在项目根目录的 PowerShell 中执行：

```powershell
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
# 以下操作需要本地配置真实 MIGRATION_DATABASE_URL
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

第一条应显示 `0001_stage0 (head)`。离线 SQL 只生成文本，不能证明已连数据库。在线迁移成功后重启应用，访问 `/health/ready` 应为 HTTP 200 / ready；未配置是 503 / not_configured，无法连接是 503 / unavailable，迁移缺失或版本不匹配是 503 / migration_required。

启动服务不会自动执行升级。基础页面不强制查询数据库，设置页需点击检查才读取连接状态。

## 回退

仅当前空业务基线允许直接在开发库运行：

```powershell
.\.venv\Scripts\python.exe -m alembic downgrade base
.\.venv\Scripts\python.exe -m alembic upgrade head
```

`downgrade base` 清除当前版本行，版本表可能保留；不等于删除数据库。未来包含业务数据的迁移须单独评估数据损失与备份，不能照搬此回退策略。

## 真实集成测试（待执行）

将 `TEST_DATABASE_URL` 配置为独立测试库的进程环境变量，再执行：

```powershell
.\.venv\Scripts\python.exe -m pytest -m integration -q
```

该变量不会自动从开发 `.env` 读取，避免把开发库误当测试目标。测试在随机 `ac_test_<uuid>` schema 中验证 upgrade、重复 upgrade、提交后新连接可见、异常回滚及 downgrade，最后只清理该 schema。需要测试角色具备创建 schema 权限。未配置时明确跳过；连接失败应按失败处理，不能跳过冒充通过。

本阶段待补验收：真实 Supabase 连接、在线迁移版本、运行角色权限、集成测试通过，以及服务重启后的连接恢复。
