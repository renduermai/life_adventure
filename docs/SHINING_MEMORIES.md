# 闪光的回忆：第1步（2026-11-22）

本页记载第1步基础设施。第2、3步现已获批并交付人物与AI分析，详见[人物功能说明](MEMORY_PEOPLE.md)。物品、心愿和后续优化尚未批准；Storage真实验收仍待配置。

入口 `/shining-memories` 默认精神导师；三个子路径为 `/shining-memories/people`、`/items`、`/wishes`。沿用现有导航、主题、登录和PostgreSQL。日期和价格计算留到对应步骤。

## 图片配置

本地 `.env` 需要配置以下变量，值不得提交Git或发送到聊天：

```dotenv
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=SERVER_ONLY_SECRET
SUPABASE_STORAGE_BUCKET=memory-private
MEMORY_BACKUP_DIR=ABSOLUTE_EXISTING_EXTERNAL_BACKUP_DIRECTORY
MEMORY_BACKUP_KEY=SEPARATE_32_BYTE_URLSAFE_BASE64_KEY
```

服务端接受标准Supabase项目域名。未配置则图片操作明确503，没有本地文件存储回退；普通业务和基础页面仍可使用。程序不会启动时创建Bucket或执行迁移。配置完成后，显式执行：

```powershell
.\.venv\Scripts\python.exe scripts/memory_media.py init-bucket
.\.venv\Scripts\python.exe scripts/memory_media.py check-storage
```

Bucket必须私有；若发现公开Bucket则拒绝操作，不擅自修改已有桶。新桶不添加任何匿名或前端用户开放策略；应同时核查Supabase项目现有storage.objects策略，没有授予匿名或其他用户访问该桶的宽泛策略。真实匿名策略验收尚待凭据准备后执行。

现有系统使用camp_session而非Supabase Auth，全部图片经FastAPI校验所属用户。服务端凭据可能绕过RLS，不能发送到前端。没有公开URL或签名URL写入数据库。新secret key通过apikey请求头发送；旧JWT service_role还通过Bearer发送；拒绝HTTP重定向以避免凭据转发。

## 数据与接口

`0022_memory_assets`新增memory_assets（稳定资产ID、归属、创建幂等编号、版本和删除时间）与memory_asset_objects（每次上传独立对象、校验和、尺寸、状态、清理时间）。两张表用于可靠处理替换、未知超时与清理；不混入人物、物品或心愿业务字段。复合外键约束同一用户，部分唯一索引保证每张资产至多一个有效版本。

- `GET /api/shining-memories/status`：认证后返回是否配置，不等于已经通过真实云端连接验证。
- `POST /api/shining-memories/assets?request_id=UUID&filename=x.png`：请求体是原始图片字节，不是multipart。
- `PUT /api/shining-memories/assets/{id}?request_id=UUID&filename=x.png&expected_version=N`：替换。
- `GET /api/shining-memories/assets/{id}`：认证读取图片；响应no-store。
- `GET /api/shining-memories/assets/{id}/metadata`：本人元数据。
- `DELETE /api/shining-memories/assets/{id}?expected_version=N`：立即撤销业务访问，延迟清理对象。

写入检查同源，文件体边读边限制5MB。真实解码JPG/PNG/WebP，拒绝损坏、格式伪装、动画、超过1200万像素或不安全文件名，重新编码WebP并去除EXIF等元数据。对象键为用户UUID/对象UUID.webp。数据库不保存二进制、本地绝对路径和原始文件名。图片不会发送AI。

上传前先提交pending对象记录，进程崩溃也可追踪。上传成功后事务切换有效版本；失败保留旧图。相同操作编号不重复上传，冲突返回409。退役对象保留7天，删除不立即物理抹除；备份副本按独立保留策略管理。

```powershell
.\.venv\Scripts\python.exe scripts/memory_media.py cleanup
```

清理只处理7天前遗留pending或到期retired对象，每次最多100项；失败保留错误码供重跑，不删除active对象，不设任务队列或定时自启。未来物品/心愿步骤接入资产引用时，还须加入对应业务引用约束。

## 独立备份与恢复

本工具备份当前有效图片和对应资产元数据，不是全项目/全数据库备份，也不包含已删除图片或历史退役版本。需另外保留完整数据库、代码迁移及加密环境配置；历史图片通过保留多个备份快照恢复。Supabase数据库备份不含图片对象：https://supabase.com/docs/guides/platform/backups 。

先生成独立密钥文件，放在项目外且与备份分开保管。命令不会打印密钥。Windows文件权限仍应通过账户ACL和加密介质保护；恢复密钥丢失会导致备份无法解密。

```powershell
.\.venv\Scripts\python.exe scripts/memory_media.py keygen --out X:\separate-keys\memory.key
```

将密钥文件内容安全配置为MEMORY_BACKUP_KEY，备份目标配置为已存在的项目外绝对目录。建议外置盘/NAS，并保留另一地点副本；工具无法确认目录是否真正异地，因此不会宣称已完成独立副本。

```powershell
.\.venv\Scripts\python.exe scripts/memory_media.py backup
.\.venv\Scripts\python.exe scripts/memory_media.py verify X:\backups\memory-TIMESTAMP.acmedia
.\.venv\Scripts\python.exe scripts/memory_media.py restore X:\backups\memory-TIMESTAMP.acmedia --bucket memory-restore-test --create-bucket
```

数据库使用一致性只读快照，下载不可变对象并核对大小/SHA-256；与物理清理共用数据库锁。ZIP内容流式AES-256-GCM加密，只有完成后才产生正式.acmedia文件，不留下明文备份包。每次使用新随机nonce；密钥不进入归档。

恢复先认证解密、验证全部清单与图片，再上传到独立空私有Bucket，禁止覆盖当前配置Bucket及备份来源Bucket，上传后再次读取校验。失败可能留下部分测试对象，需人工核对清理或使用新的空测试桶重试，原备份和线上数据不变。

恢复解密过程使用关闭即删除的临时明文文件，不解压用户提供路径到文件系统；建议恢复电脑使用加密系统盘。默认单次最多10000张图片。当前恢复工具只恢复对象并返回校验结果，不修改正式数据库、不自动切换业务引用。灾难恢复时应先恢复匹配的数据库快照，再核对资产ID、所属用户和对象路径，确认后人工调整桶映射；不应直接用图片工具恢复任意其他模块数据。

未配置定时备份或自动云端上传。必须实际执行备份并验证外置副本和恢复后，才能宣称有独立备份。

## 当前验收状态

已通过默认图片/备份测试及真实PostgreSQL隔离schema测试。数据库迁移前首次恢复演练因旧表循环外键失败；改为延迟校验循环外键后，32表322行逐表COPY二进制哈希恢复一致。只保留本机加密检查点，不代表已具备异地备份。

用户确认Storage凭据及备份目标暂未准备：真实Supabase上传、匿名访问拒绝、跨用户云端访问、真实Bucket替换/删除以及异地备份恢复尚未验收。当前测试中的Storage替身不能替代这些检查。手机访问还需要网站自身具备可访问的HTTPS地址，本步没有部署公网。

## 第6步界面优化（2026-11-22）

三个标签统一卡片、布局、筛选、表单、焦点及手机样式；精神导师保持桌面人物与右侧分析分栏。初次读取展示加载，错误展示重读提示。编辑表单输入后切换页面、取消或切换目标会提示未保存内容，关闭或刷新浏览器使用浏览器内置离开确认；完成保存后清除提示。图片上传成功但未关联时，原有保存重试行为保留，离开提示说明可能有未关联对象。

此保护只在当前标签页生效，不是草稿持久化；浏览器进程异常终止仍可能丢失未保存输入。图片与异地备份真实验收仍待Storage配置，详见上文。第7步完整联调待单独批准。
