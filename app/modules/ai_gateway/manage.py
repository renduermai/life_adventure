"""Local operator commands. Credentials are read only from the ignored .env file."""
import argparse
from datetime import date
from uuid import NAMESPACE_URL, uuid4, uuid5
from dotenv import dotenv_values
from sqlalchemy import select
from app.core.config import ROOT,load_settings
from app.core.database import Database
from app.modules.identity.models import User
from app.modules.ai_gateway import service
from app.modules.ai_gateway.models import AIConfig
from app.modules.ai_gateway.schemas import CreateConfig,EditConfig
from app.modules.ai_gateway.security import AIError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['import-env','test','rotate-keys'])
    args=parser.parse_args()
    database=None
    try:
        settings=load_settings(); database=Database(settings)
        if not database.status().ready:
            raise AIError('database_not_ready','请先确认数据库并执行 Alembic 迁移',503)
        with database.transaction() as db:
            users=list(db.scalars(select(User.id).limit(2)))
        if len(users)!=1:
            raise AIError('account_required','需要先在网页创建唯一角色账号',409)
        owner=users[0]
        if args.command=='import-env':
            values=dotenv_values(ROOT/'.env')
            url,model,key=(values.get(k) for k in ('AI_TEST_BASE_URL','AI_TEST_MODEL','AI_TEST_API_KEY'))
            if not all((url,model,key)):
                raise AIError('config_required','请先填写本地 AI_TEST 配置',409)
            data=CreateConfig(name='百炼开发模型',base_url=url,model_id=model,api_key=key,
                request_id=uuid5(NAMESPACE_URL,'adventure-camp-local-ai:'+url+':'+model),
                expires_on=date.fromisoformat(values['AI_TEST_EXPIRES_ON']) if values.get('AI_TEST_EXPIRES_ON') else None)
            with database.transaction() as db:
                service.lock_user(db,owner)
                old=db.scalar(select(AIConfig).where(AIConfig.user_id==owner,AIConfig.create_request_id==data.request_id))
                if old and not old.deleted_at:
                    record=service.edit_config(db,owner,old.id,EditConfig(**data.model_dump(exclude={'request_id'}),expected_version=old.config_version),settings)
                else:
                    if old: data.request_id=uuid4()
                    record=service.create_config(db,owner,data,settings)
                service.set_default(db,owner,record.id,record.config_version)
            print('Configured encrypted default AI model. No provider call made.')
        elif args.command=='test':
            result=service.AIService(database,settings).generate(owner,'connection_test',[{'role':'user','content':'Reply with OK.'}],uuid4())
            print('Provider connection succeeded. Usage:',result['usage'])
        else:
            with database.transaction() as db:
                count=service.rotate_keys(db,owner,settings)
            print('Re-encrypted configuration count:',count)
        return 0
    except AIError as error:
        print(error.code+': '+str(error))
        return 1
    except Exception:
        print('Operation failed; sensitive details hidden.')
        return 1
    finally:
        if database:
            database.dispose()


if __name__=='__main__':
    raise SystemExit(main())
