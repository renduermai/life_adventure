# 人生冒险之旅 / Life Adventure

Adventure Camp 是一套个人 Python Web 系统：将人生目标拆成可执行行动，把日常行动记录为历练，并将成长、回忆、思绪和心愿放在同一处。当前使用方式是本机访问；数据库和私人图片在 Supabase。公网部署及完整多设备部署尚未完成。

本次归档目标为 https://github.com/renduermai/life_adventure 的 **`1` 分支**。文档和本地提交准备不等于已经上传；远程结果以本次最终汇报为准。电脑损坏后的操作见 [恢复指南](docs/RECOVERY.md)。GitHub只保存代码和必要开发资料，私人数据与密钥独立保管。

## 技术与入口

- 已验证 Windows、CPython **3.11.9**；具体依赖以 requirements.txt 和 constraints.txt 为准。
- FastAPI入口 `app/main.py`，模块化单体；SQLAlchemy + psycopg连接PostgreSQL，Alembic管理迁移。
- Jinja2模板、原生CSS/JavaScript，没有需要单独启动的前端开发服务器。
- 数据库位于Supabase PostgreSQL，当前迁移 **0027_item_entitlements**。应用启动只检查版本，不自动迁移。
- 私人图片为Supabase Storage私有对象；PostgreSQL保存用户归属、对象路径和元数据，不保存图片二进制。图片通过用户授权的后端接口读取。
- 统一AI Gateway管理模型、用途绑定、加密凭据和调用状态；REST OpenAI-compatible调用，无LangChain依赖。AI Key用Fernet加密存数据库，主密钥在服务端环境变量。
- pytest用于默认及显式启用的隔离PostgreSQL测试；可选Playwright使用本机Microsoft Edge。

## 当前功能

下表表示代码实现范围，不能等同于所有设备和外部服务均已验收。逐次测试结果和边界见 [ACCEPTANCE](docs/ACCEPTANCE.md)、[PROGRESS](docs/PROGRESS.md)。

| 模块 | 状态 | 实际范围 |
| --- | --- | --- |
| 营地门牌 | 已实现 | 登录后仪表盘及行动、成长概览 |
| 主线与副本 | 已实现 | 主线、里程碑、副本、状态、人工五色、编辑和软删除 |
| 专注沙漏、历练手记 | 已实现 | 计时、分段、行动记录与手记 |
| 成长与奖励 | 已实现 | Python规则计算经验/金币，奖励流水及撤销冲正 |
| 灵石区 | 已实现 | 模型配置、默认/用途绑定、主动连接测试、Supabase只读配置展示 |
| 启动状态 | 已实现 | 压力/能量滑杆、独立事项、AI分类和散点；自由对话与主副本拆解 |
| 杂念 | 已实现 | 原文记录、语义归类、主题与历史，失败保留原记录 |
| 藏经阁 | 已实现 | 链接书架、主副本关联、成功复制计数 |
| 精神导师 | 已实现 | 人物/事件、热度、授权来源分析和联系评分，失败保留旧分析 |
| 武器工坊 | 已实现 | 物品、分类、私有图片、持有日均成本、权益到期管理 |
| 心愿单 | 已实现 | 心愿、估价历史、首价纠正、故事、主动AI分类和私有图片 |
| 账号与设置 | 部分实现 | 自有账号登录、用户时区及外观；不是完整系统管理后台 |
| 数据与恢复 | 部分实现 | 部分业务表导出、部分误删找回；没有全库通用导入 |
| 图片独立备份 | 部分实现 | 加密备份/校验/空桶恢复工具已实现，独立备份与异地恢复尚未完成 |
| 冒险地图 | 部分实现 | 静态建设路线展示，阶段文案不代表实时完成度 |
| 公网部署、自动备份、完整灾难演练 | 规划中 | 当前未建立完整持续保护体系 |

## 数据关系与边界

主线下有里程碑，副本可关联主线/里程碑。专注与行动模块记录计时、分段及历练；奖励模块按业务事件生成流水，撤销使用冲正。历练与奖励不是AI随意生成的数字。

灵石区是统一模型入口。启动状态的独立事项与主副本分离，事项分类结果用于象限散点；人工五色不由AI推荐覆盖。右侧对话可在用户授权时参考任务摘要，选中主副本进入拆解，生成建议不直接修改任务。当前自由对话上下文主要在浏览器sessionStorage中，不能当作跨电脑云端历史。

杂念保存原文并做版本化AI归类。藏经阁以真实主副本ID关联链接，复制成功才增加点击数。精神导师只使用用户确认预览的材料及获授权的任务/杂念ID，逐字证据和来源校验后保存分析，不写回来源。

武器和心愿关联图片资产；新图片上传成功后切换关联，旧对象按原延迟清理规则处理。权益剩余天数按用户时区当天日期计算，不入库；日均价格仍是购买价除以已持有天数，最低1天，不改为权益总期限。

## 新电脑安装与启动（Windows PowerShell）

正式推送完成后使用下列命令。如果远程`1`尚未建立，克隆该分支会失败，应先完成归档。

```powershell
git clone --branch 1 --single-branch https://github.com/renduermai/life_adventure.git
Set-Location .\life_adventure
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
Copy-Item .env.example .env
notepad .env
```

填写环境变量的获取方式见 [恢复指南](docs/RECOVERY.md)。不要把真实值提交到Git。重新接入原Supabase时保留原AI_ENCRYPTION_KEYS，不要随意生成替代值，否则旧AI凭据无法解密。

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
```

两者均为0027时无需迁移。只有明确连接了正确数据库、已有备份且确认待升级后，才手动执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

启动现有单个FastAPI服务：

```powershell
.\Start-AdventureCamp.cmd
```

也可在终端运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

访问 http://127.0.0.1:8000 ，readiness为 http://127.0.0.1:8000/health/ready 。启动器检查端口及服务身份，不误杀其他进程。桌面快捷方式不随Git迁移，在新电脑手工指向克隆目录的Start-AdventureCamp.cmd。没有开机自启。

## 配置与测试

.env由项目绝对ROOT路径加载，不依赖终端当前盘符。DATABASE_URL用于运行，MIGRATION_DATABASE_URL用于明确迁移；远程PostgreSQL需要sslmode=require或更严格校验。配置值是SQLAlchemy URL，特殊密码需URL编码。

SUPABASE_URL为项目API地址，控制台网址是另一个地址。当前图片实现读取SUPABASE_SERVICE_ROLE_KEY，兼容新版sb_secret_和旧service_role；只在服务器使用。可选Publishable/anon/Secret字段用于只读展示，其中SUPABASE_SECRET_KEY不会替代现有Storage连接字段。不要为了显示卡片更换连接。

完整测试收集会导入Playwright。只运行网站不需要它；执行完整pytest前先安装requirements-browser.txt（包含开发依赖），本机Edge仅在启用实际浏览器测试时需要。

```powershell
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple -r requirements-browser.txt
.\.venv\Scripts\python.exe -m pytest -q
```

默认跳过数据库测试不等于通过。集成测试须显式设置TEST_DATABASE_URL（建议独立测试库），会创建并清理随机schema。可选浏览器依赖：

```powershell
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple -r requirements-browser.txt
```

真实AI及云图片测试需要额外显式开关，可能产生费用或写入合成资源；不要在新电脑恢复演练时自动启用。没有Supabase配置时可查看页面壳，readiness会如实报告未配置。

## 实际目录

```text
app/
  main.py                   FastAPI入口
  core/                     配置、数据库、日志
  modules/                  identity/quests/tasks/activity/growth/dashboard
                            ai_gateway/startup_state/startup_items/startup_chat
                            distractions/library/data_tools/shining_memories
  templates/                Jinja页面
  static/                   CSS、JS、程序资源
migrations/versions/        0001–0027迁移
scripts/                    Windows启动器、私有图片备份工具
tests/                     自动化测试
docs/                       架构、进度、决策、验收及恢复说明
.env.example                无真实值的配置模板
requirements*.txt           运行、开发及可选浏览器依赖
constraints.txt             版本约束
AGENTS.md                   后续Codex开发纪律
Start-AdventureCamp.cmd     Windows启动入口
```

## 可核实的发展记录

- 2026-11-09：Git初始基础工程提交。
- 2026-11-10：Git提交账号、主副本、计时、历练、奖励、仪表盘、部分导出与恢复。
- 2026-11-15至16日：Git提交灵石区、启动状态及后续重构、杂念与藏经阁。
- 2026-11-16：此前最新本地提交fe1b711；其后的闪光的回忆等变更在本次归档前仍未提交。
- 2026-11-22：项目进度/验收文档记录精神导师、武器、心愿、私有Storage实测及局部优化完成。
- 2026-11-23：文档和本次操作记录确认权益到期管理、迁移0027、GitHub备份准备。

以上区分Git提交日期和文档记录的完成日期。需求参考时间线不是完成凭据，没有依据文件修改时间补造开发日期，也未声称读取全部聊天历史。

## 后续开发和保护

尚待完成独立全库备份、图片备份、异地恢复演练、公网部署和多设备验收。历史ROADMAP中的部分下一步文字已经落后，按最新PROGRESS/ACCEPTANCE及代码确认，不据此自动开工。

后续建议：一个功能完成 → 测试 → 更新文档 → 本地Commit → 用户明确批准后Push。可按功能使用短分支，验收后保留稳定标签；不需要复杂GitFlow，不自动Push，不重写历史或覆盖远程main。

代码恢复不等于数据恢复；完整条件和风险见 [RECOVERY](docs/RECOVERY.md)。本项目的历史加密快照、.env和私人数据不应出现在公开仓库中。
