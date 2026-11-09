# 开发环境与运行说明

## 当前基线

已实测 Windows、CPython 3.11.9、pip 24.0。macOS 尚未实测。使用项目 .venv，不升级系统 Python 或安装全局包。

- [requirements.txt](../requirements.txt)：8 个直接运行依赖。
- [requirements-dev.txt](../requirements-dev.txt)：运行依赖与 pytest、httpx 两个测试工具。
- [constraints.txt](../constraints.txt)：23 个传递依赖版本约束；全量开发环境共 33 个包，不含 pip/setuptools。
- `.python-version` 记录本地验证版本，不自动安装解释器。未来生产部署前复核解释器与安全补丁。

## Windows

在项目根目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip --isolated install --index-url https://pypi.org/simple -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

现有 .venv 无需重复创建。不要求执行激活脚本，也不更改 PowerShell 执行策略。开发时可加 `--reload`；预览完按 Ctrl+C 关闭。

`--no-access-log` 避免 Uvicorn 默认访问日志记录完整查询字符串；应用自身记录方法、状态、请求 ID，不记录请求体、URL 查询或数据库异常详情。日志输出到终端，不写包含密钥的日志文件。

## macOS（指引，未实测）

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip --isolated install --index-url https://pypi.org/simple -r requirements-dev.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

不要跨操作系统复制 .venv。首次 macOS 安装应记录机器架构、Python 补丁版本及平台相关依赖，不能把 Windows 重建成功当成 macOS 已通过。

## 配置

`.env` 从项目根路径读取，不依赖终端当前目录；环境变量优先于 .env。应用名称、IANA 时区、日志级别及两种数据库连接见 `.env.example`。错误配置拒绝启动，并隐藏原始配置值。

远程数据库必须启用 SSL；空数据库配置允许基础页面预览。修改配置后重启服务。完整迁移、权限和测试说明见 [DATABASE.md](DATABASE.md)。

## 重建与回滚

0.2 的 16 包双环境验证为历史记录；当前 stage 0 使用项目外 work/stage0-final-env 重新创建环境，按更新后的 requirements-dev.txt 验证。下载缓存不等于继承系统包。固定版本提高可重复性，但没有宣称离线可安装或哈希锁定。

后续依赖变更需同步直接清单与传递约束，再运行 pip check 和测试。Git 基线保存源码，不包含 .venv、.env、缓存或 work/ 验证产物。代码恢复优先用 git revert 产生可追踪的反向提交，勿将数据库迁移回退等同于数据恢复。

## 已知限制

Starlette TestClient 对现有 httpx 适配发出一条弃用警告；当前测试可通过。后续维护时评估官方推荐适配，不将警告隐藏或误报为业务失败。真实数据库、macOS、手机真机及公网部署均未验收。
