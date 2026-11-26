# 人生冒险之旅｜电脑损坏后的完整恢复指南

核对日期：2026-11-23。代码目标：https://github.com/renduermai/life_adventure ，分支为数字`1`。本指南准备完成不代表远程已推送、备份已建立或灾难演练已通过。

## 先保留哪些东西

需要四份独立材料：①GitHub代码/迁移/依赖；②数据库备份；③Storage对象备份；④环境变量与密钥恢复渠道。至少一份数据备份应离开当前电脑和原Supabase项目，使用加密介质、可信密码管理器或独立存储。备份密钥与备份文件分开保管。

| 配置 | 从哪里获取/保管 | 作用与注意 |
| --- | --- | --- |
| DATABASE_URL | Supabase Connect中的连接信息及数据库密码 | 应用运行；SQLAlchemy postgresql+psycopg URL，远程加sslmode=require |
| MIGRATION_DATABASE_URL | 同项目迁移权限连接；直连或session pooler | 明确迁移，不用transaction pooler；核对项目后才执行升级 |
| AI_ENCRYPTION_KEYS | 原.env的值另存可信密码管理器 | 保留原Fernet密钥及顺序才能解密旧AI配置，不能随意重新生成代替 |
| SUPABASE_URL | 项目设置中的API URL | API地址，不是Dashboard地址 |
| SUPABASE_SERVICE_ROLE_KEY | 原服务端密钥或项目服务端API设置 | 当前Storage实际读取此字段；可为sb_secret_或旧service_role，绝不发浏览器 |
| SUPABASE_STORAGE_BUCKET | 原配置和Storage控制台 | 必须是原私有桶，不自动创建公开桶 |
| 可选Publishable/anon/Secret字段 | 项目API设置 | 只读配置展示；没有则留空，不是Storage替代配置 |
| MEMORY_BACKUP_DIR | 外置盘/NAS或独立备份介质 | 已存在的项目外绝对目录 |
| MEMORY_BACKUP_KEY | 单独保管的32字节URL-safe Base64密钥 | 解密.acmedia必须用原备份密钥 |
| AI_TEST_*、TEST_DATABASE_URL | 单独测试环境 | 仅显式测试使用；不需要在恢复生产时启用。TEST_DATABASE_URL须显式设置进程环境，单写.env不会自动启用测试 |

AI配置密文在数据库，但解密主密钥不在数据库。遗失主密钥时，旧凭据不能凭代码恢复，须恢复原密钥或在灵石区重新填写供应商凭据。自有账号/密码散列在public.users，不依赖Supabase Auth；完整数据库迁移需保留原用户ID和所有关联。恢复后可重新登录，不要求恢复浏览器会话。

## 场景A：电脑损坏，GitHub和原Supabase仍正常

1. 安装Git、Python 3.11（已验证3.11.9）、可选Edge及编辑器。先保证可访问PyPI、GitHub和云服务；当前电脑的代理设置不会被Git自动恢复。
2. 按README克隆`1`、创建.venv、安装requirements-dev.txt并pip check。完整pytest收集还需requirements-browser.txt；运行网站不需要浏览器测试包。运行不需要单独前端服务。
3. 从.env.example复制.env，用上表渠道恢复真实值；不要将密钥粘贴到公开问题、提交或聊天记录。
4. 运行alembic current与heads。原数据库0027、代码head0027时不执行迁移；不降级、不重建、不初始化原数据。
5. 用只读检查验证私有桶和健康状态：

```powershell
.\.venv\Scripts\python.exe scripts/memory_media.py check-storage
.\Start-AdventureCamp.cmd
Invoke-RestMethod http://127.0.0.1:8000/health/ready
```

check-storage检查原私有桶，不创建桶。不要把init-bucket、cleanup当作恢复检查命令，后者会执行清理。
6. 用原账号登录，检查任务、历练、人物、武器、心愿及图片。只查看，不用新增/删除私人数据证明连接。需要验证AI时用户另行确认费用与发送范围。
7. 新建桌面快捷方式指向新路径的Start-AdventureCamp.cmd；原Windows快捷方式、.venv和日志不迁移。

## 场景B：迁移到新Supabase项目

这是独立的数据迁移操作，不能只改DATABASE_URL。先取得数据库、图片、环境配置的完整快照，在隔离目标试恢复；不得对原库执行--clean、drop或覆盖导入。

### 数据库

人生运行系统完整数据必须包含全部life_os_*表（当前0028–0033），并保留原AI_ENCRYPTION_KEYS。页面固定名单导出不包含全部模块，不能用作完整恢复。

需要兼容源PostgreSQL版本的pg_dump/pg_restore。当前电脑审计时两者不在PATH，须另行安装匹配客户端。不要把SQLAlchemy的+psycopg URL原样交给PostgreSQL命令。

使用Supabase给出的原生连接参数，设置PGHOST/PGPORT/PGDATABASE/PGUSER/PGSSLMODE及PGPASSFILE，密码文件放项目外并限制权限。PowerShell示意（占位值必须替换，不要提交密码文件）：

```powershell
$env:PGHOST = 'SOURCE_HOST'
$env:PGPORT = '5432'
$env:PGDATABASE = 'postgres'
$env:PGUSER = 'SOURCE_USER'
$env:PGSSLMODE = 'require'
$env:PGPASSFILE = 'X:\private-keys\pgpass.conf'
pg_dump --format=custom --schema=public --no-owner --no-privileges --file='X:\private-backups\adventure-public.dump'
if ($LASTEXITCODE -ne 0) { throw '数据库备份失败，不能继续恢复' }
pg_restore --list 'X:\private-backups\adventure-public.dump'
```

该导出覆盖应用public表和数据，包括账号、AI密文及图片元数据；不是整个Supabase平台备份，不包含Storage对象二进制、平台设置和角色。导出文件本身未加密，需要立即用可信加密备份工具保护。为一致性暂停源应用写入和图片变更，协调同一时间的数据库及图片快照。

在**新的隔离项目、无现有应用表**的目标中，先检查导出清单、兼容版本和目标地址，再用目标PG连接参数：

```powershell
pg_restore --no-owner --no-privileges --exit-on-error --dbname=postgres 'X:\private-backups\adventure-public.dump'
if ($LASTEXITCODE -ne 0) { throw '恢复未完成，保留原备份并排查，不启动写入' }
```

Supabase自带扩展和权限可能造成冲突，须在测试目标验证，不删除平台schema解决冲突。完整dump已含结构和alembic_version，不能先建同名应用表再盲目导入。恢复后检查备份所记录的版本；当前项目要求0033_life_os_attractors；如需要从纯空库只建结构才执行alembic upgrade head，但这不会还原私人数据。不要导入系统角色或随意覆盖Supabase托管schema。

### 图片

项目工具只备份当前有效图片及资产清单，不含全部历史退役/已删除对象；保留多个快照才有历史恢复能力。当前独立备份尚未配置。

```powershell
.\.venv\Scripts\python.exe scripts/memory_media.py keygen --out X:\separate-keys\memory.key
```

keygen只用于首次建立新备份体系，文件必须在项目外且不存在；恢复旧备份时不得生成替代密钥。将该值安全配置为MEMORY_BACKUP_KEY，配置MEMORY_BACKUP_DIR后：

```powershell
.\.venv\Scripts\python.exe scripts/memory_media.py backup
.\.venv\Scripts\python.exe scripts/memory_media.py verify X:\private-backups\memory-TIMESTAMP.acmedia
```

本次归档不执行这些备份写操作。迁移图片时使用独立恢复配置：数据库仍只读连接快照来源，SUPABASE_URL和服务端凭据指向**目标新项目**，选一个不同于清单原桶名的空私有测试桶：

```powershell
.\.venv\Scripts\python.exe scripts/memory_media.py restore X:\private-backups\memory-TIMESTAMP.acmedia --bucket memory-restore-test --create-bucket
```

工具拒绝原桶名和非空桶，上传后重新读取校验hash，**不修改数据库**。目标库memory_asset_objects中的bucket需要在独立审批的目标库迁移中映射到新桶名；object_path、用户ID及资产关联必须保持一致。不得把这一步直接用于原库，不得仅恢复图片却忽略数据库映射。完成映射并改目标运行配置后，验证跨用户拒绝和已登录读取。保持私有桶，不为修复图片可见性开启公开访问。

目标项目的应用数据库角色、权限、网络和Storage设置须另行建立核对，应用自有账号表完整恢复即可保留账号身份；不是复制Supabase Auth用户的流程。原项目保留至验收完成。

## 场景C：代码尚在，但Supabase数据丢失

GitHub无法生成已经丢失的个人资料、任务、AI配置密文或照片。需要独立数据库备份和对应对象备份。如果只有数据库dump，图片路径不能变成图片；只有图片也不能重建全部业务关联。

本次审计确认云上私有桶及对象存在，但没有管理平台备份权限/证据确认可用恢复点；不能把Supabase有云端存储等同于已验证备份。应在控制台检查项目实际备份、保留期及恢复功能，并单独安排演练。现有MEMORY_BACKUP_DIR/KEY未配置，暂无已验证的独立图片备份。

应用“数据与恢复”只导出部分业务表，并没有通用导入；不包含完整人物、物品、心愿、杂念、链接和凭据，不能替代全库dump。本机历史.enc检查点也不是最新持续全量备份，且同电脑损坏时会一起丢失。

## 场景D：GitHub代码丢失，本地数据存在

从另一台电脑、独立备份盘或可信Git副本恢复完整仓库，检查代码head与数据库alembic_version兼容。不要用空项目重建覆盖原表。只有数据库通常无法恢复模板、JS、CSS、业务规则和迁移源文件。

仓库仍存在的电脑可另行授权制作git bundle及其hash，放独立介质；它包含已提交历史，不含未提交文件、.env或数据。外部服务丢失时先保留现存副本，再建立新远程；不要强推现有历史。

## 恢复验收

- [ ] 当前代码来自预期仓库和分支1，提交hash已核对。
- [ ] Python依赖安装完成、pip check通过，版本与README匹配。
- [ ] 正确数据库连接、迁移版本0027；没有重复迁移或覆盖原表。
- [ ] 服务、health/ready、主要页面可访问。
- [ ] 原账号可登录，用户时区正确。
- [ ] 主线、副本、历练、专注、奖励和独立事项记录存在。
- [ ] 杂念、藏经阁、精神导师资料和关联存在。
- [ ] 武器、权益日期、心愿及价格历史存在。
- [ ] 私有图片可读，匿名/其他账号不能读取不属于自己的图片。
- [ ] 原AI加密主密钥可解密配置；未经同意不自动进行收费测试。
- [ ] 没有把任何真实密钥、数据库dump或私人图片提交GitHub。
- [ ] 独立数据库和对象备份均已验证；失败时仍保留原来源。

## 本次演练边界

本次先准备代码归档和文档。只做无生产凭据的干净代码导出安装、默认测试和启动检查，不迁移、清空或写入真实库。即使完成Push，也只能证明代码快照到达GitHub；新电脑完整重装、平台备份恢复、跨Supabase迁移、独立图片备份及异地全量恢复仍须单独验证。

.env缺失、原AI主密钥未另存、独立数据备份不足或外部服务不可访问，都会影响最终恢复能力。优先保管环境配置和密钥，再建立并演练两类独立数据备份。
