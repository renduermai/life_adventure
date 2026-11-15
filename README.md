# 人生冒险之旅 · Adventure Camp

当前已完成启动状态推荐可靠性改进第1次，数据库版本 `0013_recommendation_reliability`。刷新推荐会逐项缓存任务特征，允许部分成功并显示待分析原因；可以单独重试失败项。压力/能量变化仅重算适配度。四象限任务散点和右侧对话整合属于后续两次开发，尚未实施。

V2 第 8 步交付时的数据库版本为 `0012_breakdown`。主线/副本可进入 AI 拆解，编辑并选择步骤，经确认保存为关联副本、里程碑或行动清单，再进入原有专注入口。操作、限制与测试命令见 [第 8 步说明](docs/V2_STEP_8.md)；当前版本及验收证据见 docs/ACCEPTANCE.md 最新记录。

当前实现至 **V2 第 7 步**：启动状态支持多轮 AI 对话、可修改建议、确认后刷新统一推荐、对话与状态历史。数据库版本 `0011_startup_chat`。打开 `/startup`：描述感受 → 载入建议 → 拖动压力/能量滑杆 → 确认保存 → 刷新象限与推荐。操作、接口与验收见 [第 7 步说明](docs/V2_STEP_7.md)。下文为各阶段交付记录，以本节及 PROGRESS.md 最新记录为准。

当前实现至 V2 第 6 步：主线和副本页面显示统一推荐与拆解导航；拆解 AI 功能尚未接入。数据库迁移目标为 `0010_recommendations`。下面各阶段说明为交付时记录，当前进度见 docs/PROGRESS.md。

将目标、真实行动与复盘连接起来的个人成长应用。

**阶段 1.1–1.9 已接入账号、主线、里程碑、副本任务、专注计时、历练手记、奖励、首页仪表盘及数据导出与恢复，等待用户验收。** Supabase 已连接并执行迁移。公网部署尚未实现。

V2 第 2 步灵石区后端已实现；配置、迁移及命令说明见 [本步指南](docs/V2_STEP_2.md)。网页在第 3 步实施。当前数据库迁移目标为 `0008_ai_gateway`。

## 快速启动（Windows PowerShell）

进入项目根目录后执行；本机 `.venv` 已准备好：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

访问 http://127.0.0.1:8000 ，按 Ctrl+C 停止。若端口已占用，使用 `--port 8001` 并访问对应地址。此地址仅供本机访问，不是公网网址。

从干净环境安装：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

仅运行时可安装 requirements.txt；开发测试安装 requirements-dev.txt。应用不依赖 CDN，基础页面、CSS、JavaScript 和插画都由本地服务提供。

## 当前可验收内容

- 通过「角色账号」创建单用户账号、登录、修改昵称和时区、退出登录。
- 通过「主线任务」创建、修改、暂停、完成、归档、软删除和恢复主线。
- 在主线详情创建、编辑、完成、撤销完成、删除和恢复里程碑，查看主线历史。
- 副本任务支持创建、编辑、分类、优先级、截止日期、关联、子任务、重复、批量操作和删除恢复。主线进度按有效末级任务计算；没有任务时按里程碑计算。
- 专注沙漏支持正计时、倒计时、暂停、恢复、刷新恢复、结束保存和确认实际投入时长。
- 历练手记支持自动记录、手工补录、日周月查询、任务与分类筛选、修改历史及删除恢复。
- 成长与奖励页面提供经验、等级、金币、可配置奖励规则和奖励流水。
- 数据与恢复页面提供当前账号 JSON/CSV ZIP 导出与误删恢复入口；暂不提供从导出文件自动导入。
- 首页、冒险地图、营地设置三个页面及导航。
- 浅色/深色主题与当前浏览器偏好保存；390px 响应式导航。
- `/health/live`：进程存活返回 200。
- `/health/ready`：真实数据库及迁移状态；未配置明确返回 503。
- 环境配置校验、PostgreSQL 连接和事务基础、Alembic 空业务基线。
- 请求 ID、结构化日志、错误脱敏、pytest 测试与本地 Git 基线。

业务数据不存储在浏览器；localStorage 只保存主题偏好。页面显示的是功能建设说明，不是个人完成情况。

## 数据库配置

当前开发环境已连接 Supabase 并执行至 `0008_ai_gateway`。新环境需复制 `.env.example` 为 `.env`，在本地填写 DATABASE_URL 和 MIGRATION_DATABASE_URL，然后按 [数据库指南](docs/DATABASE.md) 执行迁移。不要提交密钥。

## 文档

| 文档 | 用途 |
|---|---|
| [开发规范](AGENTS.md) | 授权范围与工程规则 |
| [进度](docs/PROGRESS.md) | 已完成和待办 |
| [路线图](docs/ROADMAP.md) | 0–5 阶段顺序 |
| [架构](docs/ARCHITECTURE.md) | 模块边界和工程结构 |
| [数据模型](docs/DATA_MODEL.md) | 业务草案及迁移记录 |
| [决策](docs/DECISIONS.md) | 已定与未决事项 |
| [环境说明](docs/ENVIRONMENT.md) | 安装、重建、macOS 指引 |
| [验收记录](docs/ACCEPTANCE.md) | 实测结果与限制 |

## 下一步

V2 第 2 步完成验收后停止，第 3 步前端需单独批准。阶段 1 未验证项仍按验收记录保留。
