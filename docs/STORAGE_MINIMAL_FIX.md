# Supabase私有图片最小修复（2026-11-22）

用户明确授权配置与最小修复，未改数据库结构、现有业务数据、文字保存、图片关联或延迟清理规则。

## 根因与修复

实际环境文件位于项目根目录outputs/adventure-camp/.env，由app/core/config.py的ROOT/.env绝对路径加载，不依赖启动时所在目录。原三项均未配置，构造Storage时把缺失桶名当成空字符串并报格式错。

现已配置SUPABASE_URL、SUPABASE_SERVICE_ROLE_KEY和SUPABASE_STORAGE_BUCKET，只报告存在性，不输出值或密钥。项目未使用supabase/storage3 Python包，直接采用Storage REST；sb_secret_只通过apikey头发送，不作为JWT放进Authorization。旧JWT service_role兼容保留。

首次直连失败，诊断为Windows连接重置10054；使用系统代理后HTTP200，密钥有效。原代码强制ProxyHandler({})绕过系统代理；修复为遵循系统代理，仍限制官方HTTPS域名并拒绝重定向，避免转发凭据到其他主机。

缺失桶名返回storage_not_configured，格式错误返回storage_bucket_invalid。兼容Storage以HTTP400包装statusCode404/NoSuchBucket/NoSuchKey的缺失资源响应。status接口分别报告配置、私有桶可用性和脱敏错误；前端在图片字段旁提前告知，并在不可用时阻止上传，仍可保存无图文字记录。

## 验证

- 私有Bucket已通过真实服务端检查，不创建公开桶或开放匿名策略。
- 新增8项配置与新版请求头单测通过。
- 默认测试164 passed、75 skipped、1 warning；跳过不算通过。Alembic check无结构差异，仍为0026_memory_wishes。
- 真实云端+隔离PG合成验收1 passed（80.16秒）：物品与心愿分别上传/读取/替换图片；匿名401、跨用户读取/替换/删除404；公开URL无法读取；关联图片独立删除409；删除合成业务记录后后端图片不可访问。
- 真实物理删除只清理测试schema中随机账号本轮保留的对象路径，逐路径断言所属测试账号，删除后真实GET确认object_missing；未枚举删除真实用户对象。
- 密钥不出现在API响应、捕获测试输出和Git非忽略文件；.env被Git忽略且未跟踪。普通浏览器只调用同源授权后端接口，拿不到Secret Key。

- 修复后的Edge+真实隔离PG回归3 passed、1 warning（165.28秒）：合成图片替换故障/恢复、筛选故障、物品无图录入、心愿价格及纠正流程；此组存储故障使用替身，真实云端由上一组单独验证。

## 仍然存在的边界

服务器需要当前可用的系统代理与网络。服务端Secret具有高权限，所有浏览器请求仍必须经过现有用户归属校验；不得把它放进NEXT_PUBLIC变量、模板或JS。

图片替换和业务删除仍按既有7天保留/手动清理机制执行，测试的即时云删除只限本轮合成对象。独立图片备份目录、备份密钥和异地恢复仍未配置/验收，上传云端不代表已有独立备份。未修改这部分范围，也没有新增后台任务或公开部署。
