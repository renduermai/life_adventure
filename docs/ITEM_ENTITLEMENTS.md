# 武器工坊：权益到期管理（2026-11-23）

新增物品默认不勾选权益类，购买日期使用列表接口返回的用户时区当天日期。勾选后填写到期日期，不能早于购买日期；允许历史过期权益。编辑支持转换和续期，原权益转普通物品在保存时确认清除原到期日期，取消确认保留输入和数据库原值。未保存的日期输入可随勾选暂时隐藏，普通物品提交null。

权益卡片显示标签、到期日期及26px到期状态：距离到期还有N天/今天到期/已过期N天。普通卡片不新增信息。剩余天数由Python按现有用户时区today函数计算，读取时更新，不持久化。原cost函数、日均价格精度、排序和颜色分档保持原样；图片操作、分类和删除沿用原实现。

## 数据与兼容

Alembic 0027_item_entitlements继承0026_memory_wishes，仅在memory_items新增非空Boolean is_entitlement（server default false）及可空Date expires_at。CHECK保证权益必填日期且>=购买日期，普通物品日期为空。旧记录自动为false/null，不替换物品表，不改原字段。回滚迁移会删除这两个新增字段及权益信息，不应用于已有权益数据的日常恢复。

新增和编辑继续使用原接口，Pydantic严格Boolean及字段组合校验、HTML必填与日期下限共同校验。普通物品创建指纹仍按原字段生成，保留旧幂等请求兼容。列表响应额外返回today；单个物品额外返回is_entitlement、expires_at和remaining_days，不增加接口或AI调用。

## 修改文件

- app/modules/shining_memories/items/models.py、schemas.py、service.py
- app/templates/shining_memories/items.html
- app/static/js/memory_items.js、app/static/css/shining_memories.css
- migrations/versions/0027_item_entitlements.py
- tests/test_item_entitlements.py、tests/test_item_entitlements_postgres.py

另同步app/core/database.py的EXPECTED_REVISION到0027，以满足项目既有readiness版本检查；不改变连接逻辑。

没有修改精神导师、心愿单或其他模块实现。CSS新增规则限定物品列表与到期表单，不改变图片逻辑。没有新增依赖或更换凭据。

## 验证范围

六组输入校验覆盖普通空日期、权益缺日期、普通带日期、到期早于购买、相同日期、合法历史日期。真实PostgreSQL隔离schema验证0026往返升级的原字段保留、旧请求重试、CHECK约束、编辑续期、剩余/当天/已过期、上海与洛杉矶跨日及日均成本不变。

Edge使用合成账号验证默认今天、动态日期显隐/必填、取消和确认清除原到期日期、保存与刷新读回、普通卡片不显示到期信息，以及320/390/1366px布局和无新增JS错误。原物品数据库与浏览器回归包含分类/排序/图片引用及原流程；图片测试使用现有存储替身，不称为新增真实云端上传验证。

## 结果与运行

默认180 passed/79 skipped；最终版本常量调整后的基础26 passed；新增权益专项真实PG+Edge 1 passed（107.38秒），原物品PG/浏览器3 passed。首次组合运行中专项测试误写输入错误为400而实际项目标准为422，产生1 failed/3 passed；修正测试断言后专项重跑通过，没有修改接口状态码。各组有既有Starlette/httpx弃用警告。Node语法和修改文件diff检查通过。

真实开发库已事务升级0027，迁移前后原2条物品的全部原字段逐项相等，新字段均false/null；Alembic check无差异。现有启动器已重启当前项目，readiness及武器工坊页面均HTTP200。测试只操作隔离schema，正式库仅执行已批准的字段迁移。未发送AI请求、未修改.env或服务密钥。开发总Token与费用无法准确获取。

访问 http://127.0.0.1:8000/shining-memories/items ，刷新页面后使用。本轮完成并停止待用户验收。
