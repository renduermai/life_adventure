# 人生冒险之旅 · Adventure Camp

当前版本为 V3：主线/副本手动五色、独立事项管理、压力×能量四象限、事项 AI 分类与散点，以及右侧自由对话/主副本拆解。数据库版本 `0017_item_analysis`。V3第0–6步均已交付，最终验证见 [验收记录](docs/ACCEPTANCE.md)。

## 使用方式

- 主线、副本列表和详情可手动选择五色；选择自动保存，与完成状态、优先级、AI分析独立。
- `/startup` 手动记录事情的描述、重要程度、紧急程度和目前进展。事项与主副本无关联，支持编辑和确认软删除。
- 拖动心理压力、当前能量，圆点立即移动，停拖自动保存；滑杆不会调用AI。
- 点击“开始分析”，通过灵石区模型逐项分类；未变化内容复用缓存，失败可单项重试，信息不足待确认。悬停散点看详情，点击编辑；位置仅代表适配象限与排版。
- 右侧默认自由对话。主线或副本点击“拆解”会载入目标，必要时澄清，再给具体步骤、完成标志和最小动作。可继续反馈“第一步太难”，复制步骤后手动新增事项。AI 不直接创建或修改任务、事项、五色状态。
- 对话仅在当前标签页会话中保存：刷新恢复、新对话清空、退出清理，换账号不复用旧上下文；浏览器恢复标签页可能恢复会话。API Key只在服务端。

原有账号、主线、里程碑、副本、专注计时、历练手记、经验/金币、仪表盘、数据导出和误删恢复功能保留。旧自动推荐和永久聊天入口已停用；历史表/记录保留，不自动删除。

## 本机启动（Windows PowerShell）

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

访问 http://127.0.0.1:8000 。按 Ctrl+C 停止；端口已占用时可改用8001。这是本机地址，未部署公网。

全新环境安装与基础验证：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

本地 `.env` 配置数据库和AI加密密钥，勿提交到Git。数据库变更通过 Alembic 明确执行，不在启动时自动迁移。模型从灵石区设置默认或用途绑定；新会话拆解使用 JSON 对象格式，当前 Kimi 已验证；供应商拒绝或超时会明确提示，不自动重发。

## 验证与数据保护

真实数据库测试需显式设置 `TEST_DATABASE_URL`，测试会建立并清理隔离 schema；默认跳过不等于通过。可选浏览器依赖见 requirements-browser.txt，使用本机 Edge。

```powershell
.\.venv\Scripts\python.exe tests/browser_session_assistant.py
.\.venv\Scripts\python.exe tests/browser_item_analysis.py
.\.venv\Scripts\python.exe tests/browser_startup_items.py
.\.venv\Scripts\python.exe tests/browser_v3_startup.py
```

这些浏览器脚本使用合成HTTP响应；实际模型/数据库验收另见 ACCEPTANCE.md。模型调用可能产生费用。任务数据保存在PostgreSQL，已保存事项可导出；现有导出不等于全库备份，也不提供自动导入。历史数据破坏性迁移须单独批准。详细历史进度见 PROGRESS.md。「杂念」的使用、验收和完整数据库备份注意事项见 docs/DISTRACTIONS.md。
