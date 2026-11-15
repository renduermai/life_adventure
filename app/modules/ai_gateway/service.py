"""Owner-scoped configuration and AI calls; external I/O outside DB transactions."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import delete, func, select
from app.modules.identity.service import lock_user
from app.modules.ai_gateway.models import AIConfig, AIModuleBinding, AICallLog
from app.modules.ai_gateway.adapter import OpenAICompatibleAdapter
from app.modules.ai_gateway.security import AIError, cipher, decrypt, encrypt, key_version, post_json

PURPOSES = {'connection_test', 'startup_state', 'task_analysis', 'breakdown', 'quest_generation', 'review', 'character'}
MODULES = PURPOSES - {'connection_test'}


def now():
    return datetime.now(timezone.utc)


def digest(value, secret):
    return hmac.new(secret.encode(), json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode(), hashlib.sha256).hexdigest()


def public(config):
    return {key: getattr(config, key) for key in (
        'id','name','base_url','model_id','protocol','expires_on','notes','enabled','is_default',
        'config_version','last_test_version','last_test_result','last_test_at','created_at','updated_at')} | {
            'api_key_masked': config.key_mask, 'has_key': bool(config.encrypted_key),
            'test_stale': config.last_test_version != config.config_version}


def get_config(db, user_id, config_id):
    record = db.scalar(select(AIConfig).where(AIConfig.id == config_id, AIConfig.user_id == user_id, AIConfig.deleted_at.is_(None)))
    if record is None:
        raise AIError('not_found', '配置不存在或无权访问', 404)
    return record


def check_version(record, version):
    if record.config_version != version:
        raise AIError('version_conflict', '配置已变化，请刷新后重试', 409)


def validate_key(value):
    if not 8 <= len(value) <= 4096 or any(ord(c)<33 or ord(c)>126 for c in value):
        raise AIError('invalid_key', '模型密钥格式无效', 422)
    return value


def create_config(db, user_id, data, settings):
    lock_user(db, user_id)
    values = data.model_dump(exclude={'request_id','api_key'})
    key = validate_key(data.api_key.get_secret_value())
    fingerprint = digest(values, key)
    old = db.scalar(select(AIConfig).where(AIConfig.user_id == user_id, AIConfig.create_request_id == data.request_id))
    if old:
        if old.create_fingerprint != fingerprint or old.deleted_at:
            raise AIError('request_conflict', '提交编号已使用，请使用新编号', 409)
        return old
    record = AIConfig(user_id=user_id, create_request_id=data.request_id, create_fingerprint=fingerprint,
                      encrypted_key=encrypt(settings,key), key_version=key_version(settings),
                      key_mask='已设置 · ****', **values)
    db.add(record)
    db.flush()
    return record


def edit_config(db, user_id, config_id, data, settings):
    lock_user(db,user_id)
    record=get_config(db,user_id,config_id)
    check_version(record,data.expected_version)
    for key,value in data.model_dump(exclude={'api_key','expected_version'}).items():
        setattr(record,key,value)
    if data.api_key and data.api_key.get_secret_value():
        record.encrypted_key=encrypt(settings,validate_key(data.api_key.get_secret_value()))
        record.key_version=key_version(settings)
    if not record.enabled:
        record.is_default=False
    record.config_version+=1
    db.flush()
    return record


def set_default(db,user_id,config_id,version):
    lock_user(db,user_id)
    target=get_config(db,user_id,config_id)
    check_version(target,version)
    if not target.enabled:
        raise AIError('disabled','请先启用配置',409)
    for item in db.scalars(select(AIConfig).where(AIConfig.user_id==user_id,AIConfig.is_default.is_(True))):
        if item.id != target.id:
            item.is_default=False
            item.config_version+=1
    db.flush()
    if not target.is_default:
        target.is_default=True
        target.config_version+=1
    db.flush()
    return target


def remove_config(db,user_id,config_id,version):
    lock_user(db,user_id)
    item=get_config(db,user_id,config_id)
    check_version(item,version)
    item.is_default=False
    item.enabled=False
    item.encrypted_key=None
    item.key_mask='未设置'
    item.deleted_at=now()
    item.config_version+=1
    db.execute(delete(AIModuleBinding).where(AIModuleBinding.user_id==user_id,AIModuleBinding.config_id==config_id))
    db.flush()


def bind(db,user_id,module,config_id):
    if module not in MODULES:
        raise AIError('invalid_module','模块无效',422)
    lock_user(db,user_id)
    if config_id:
        item=get_config(db,user_id,config_id)
        if not item.enabled:
            raise AIError('disabled','请先启用配置',409)
    old=db.get(AIModuleBinding,(user_id,module))
    if old:
        db.delete(old)
        db.flush()
    if config_id:
        db.add(AIModuleBinding(user_id=user_id,module_key=module,config_id=config_id))


def rotate_keys(db,user_id,settings):
    """Caller must explicitly authorize rotation; all changes share its transaction."""
    lock_user(db,user_id)
    crypt=cipher(settings)
    count=0
    for item in db.scalars(select(AIConfig).where(AIConfig.user_id==user_id,AIConfig.deleted_at.is_(None))):
        decrypt(settings,item.encrypted_key)
        item.encrypted_key=crypt.rotate(item.encrypted_key.encode()).decode()
        item.key_version=key_version(settings)
        count+=1
    return count


class AIService:
    def __init__(self,database,settings):
        self.database,self.settings=database,settings

    def generate(self,user_id,purpose,messages,request_id,output_schema=None,config_id=None,expected_version=None):
        if purpose not in PURPOSES or not isinstance(request_id,UUID):
            raise AIError('invalid_request','用途或提交编号无效',422)
        if (not isinstance(messages,list) or not 1<=len(messages)<=30
                or any(not isinstance(m,dict) or set(m)!={'role','content'} or m.get('role') not in {'system','user','assistant'}
                       or not isinstance(m.get('content'),str) for m in messages)
                or len(json.dumps(messages,ensure_ascii=False))>24000):
            raise AIError('invalid_messages','对话格式无效或超过限制',422)
        started=time.monotonic()
        with self.database.transaction() as db:
            lock_user(db,user_id)
            if config_id is None:
                binding=db.get(AIModuleBinding,(user_id,purpose))
                config_id=binding.config_id if binding else db.scalar(select(AIConfig.id).where(AIConfig.user_id==user_id,AIConfig.is_default.is_(True)))
            if not config_id:
                raise AIError('no_model','请先设置默认模型或模块指定模型',409)
            config=get_config(db,user_id,config_id)
            if not config.enabled:
                raise AIError('disabled','所选模型已停用',409)
            if expected_version is not None:
                check_version(config,expected_version)
            key=decrypt(self.settings,config.encrypted_key)
            fingerprint=digest({'config':str(config.id),'version':config.config_version,'messages':messages,
                                'schema':output_schema.model_json_schema() if output_schema else None},key)
            old=db.scalar(select(AICallLog).where(AICallLog.user_id==user_id,AICallLog.purpose==purpose,AICallLog.request_id==request_id))
            if old:
                raise AIError('request_used','请求已处理或处理中；未再次调用模型',409)
            db.query(AICallLog).filter(AICallLog.user_id==user_id,AICallLog.status=='running',AICallLog.started_at<now()-timedelta(minutes=2)).update({'status':'unknown','error_code':'interrupted'})
            active=db.scalar(select(func.count()).select_from(AICallLog).where(AICallLog.user_id==user_id,AICallLog.status=='running'))
            recent=db.scalar(select(func.count()).select_from(AICallLog).where(AICallLog.user_id==user_id,AICallLog.started_at>now()-timedelta(minutes=1)))
            if active or recent>=20:
                raise AIError('rate_limit','当前有请求执行中或调用过于频繁，请稍后重试',429)
            log=AICallLog(user_id=user_id,config_id=config.id,config_version=config.config_version,
                          model_id=config.model_id,purpose=purpose,request_id=request_id,fingerprint=fingerprint,status='running')
            db.add(log)
            db.flush()
            log_id,version,url,model=log.id,config.config_version,config.base_url,config.model_id
        error=None; content=None; usage=None
        try:
            content,usage=OpenAICompatibleAdapter(post_json).generate(url,key,model,messages,output_schema,max_tokens=1536 if purpose in {'breakdown','task_analysis'} else 512)
        except AIError as exc:
            error=exc
        except Exception:
            error=AIError('invalid_output','模型输出不符合要求，结果未保存到正式业务',502)
        finally:
            key=None
        with self.database.transaction() as db:
            lock_user(db,user_id)
            record=db.get(AICallLog,log_id)
            record.finished_at=now()
            record.elapsed_ms=round((time.monotonic()-started)*1000)
            record.usage=usage
            record.status='succeeded' if error is None else ('unknown' if error.code in {'upstream_timeout','upstream_failed'} else 'failed')
            record.error_code=error.code if error else None
            config=db.get(AIConfig,config_id)
            if purpose=='connection_test' and config.config_version==version and not config.deleted_at:
                config.last_test_at=now()
                config.last_test_version=version
                config.last_test_result=error.code if error else 'succeeded'
        if error:
            raise error
        return {'content':content,'usage':usage,'config_id':config_id,'config_version':version,'model_id':model,'call_id':log_id}
