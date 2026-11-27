from decimal import Decimal,ROUND_HALF_UP
from zoneinfo import ZoneInfo
from sqlalchemy import select,func
from app.modules.identity.service import lock_user
from app.modules.identity.models import User
from ..people.service import now,fingerprint
from ..shared.images import MediaError
from ..shared.references import validate_image
from ..items.service import release
from .models import MemoryWish,WishPrice,WishClassification

def get(db,uid,wid):
    row=db.scalar(select(MemoryWish).where(MemoryWish.id==wid,MemoryWish.user_id==uid,MemoryWish.deleted_at.is_(None)))
    if not row:raise MediaError('not_found','心愿不存在或无权访问',404)
    return row

def change(initial,current,has_updates):
    if not has_updates:return {'direction':'none','amount':None,'percentage':None,'text':'暂无价格变化记录'}
    amount=current-initial;direction='up' if amount>0 else 'down' if amount<0 else 'same'
    ratio=None if initial==0 else (abs(amount)/initial*100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    label={'up':'上涨','down':'下降','same':'未变化'}[direction]
    return {'direction':direction,'amount':str(abs(amount)),'percentage':str(ratio) if ratio is not None else None,
        'text':f'{label} ¥{abs(amount):.2f}，'+(f'{ratio}%' if ratio is not None else '首次价格为零，比例无法计算')}

def public(db,row):
    updated=bool(db.scalar(select(WishPrice.id).where(WishPrice.wish_id==row.id,WishPrice.kind=='update').limit(1)))
    diff=change(row.initial_price,row.current_price,updated)
    date=row.created_at.astimezone(ZoneInfo(db.get(User,row.user_id).timezone)).date()
    cause='当时记录的原因是：'+row.reason if row.reason else '你尚未记录想拥有它的原因。'
    corrected=bool(db.scalar(select(WishPrice.id).where(WishPrice.wish_id==row.id,WishPrice.kind=='correction').limit(1)))
    initial_label='纠正后的首次价格' if corrected else '首次记录价格'
    last=db.scalar(select(WishClassification).where(WishClassification.wish_id==row.id,WishClassification.user_id==row.user_id).order_by(WishClassification.created_at.desc()).limit(1))
    result={k:getattr(row,k) for k in ('id','name','description','reason','category','category_source','version','image_asset_id','created_at')}
    return result|{'initial_price':format(row.initial_price,'.2f'),'current_price':format(row.current_price,'.2f'),'currency':'CNY','price_change':diff,
        'story':f'你在 {date} 记录了这个心愿。{cause} {initial_label}为 ¥{row.initial_price:.2f}，最新手动估价为 ¥{row.current_price:.2f}。{diff["text"]}。',
        'image_url':'/api/shining-memories/assets/'+str(row.image_asset_id) if row.image_asset_id else None,
        'classification':{'state':last.state,'error_code':last.error_code,'reason':(last.result or {}).get('reason')} if last else None}

def listing(db,uid,category='',offset=0):
    rows=list(db.scalars(select(MemoryWish).where(MemoryWish.user_id==uid,MemoryWish.deleted_at.is_(None)).order_by(MemoryWish.created_at.desc(),MemoryWish.id)))
    categories=sorted({r.category for r in rows if r.category})
    if category:rows=[r for r in rows if r.category==category]
    return {'items':[public(db,r) for r in rows[offset:offset+20]],'next_offset':offset+20 if len(rows)>offset+20 else None,'categories':categories}

def create(db,uid,data):
    lock_user(db,uid);values=data.model_dump(exclude={'request_id','price'});fp=fingerprint(data.model_dump(exclude={'request_id'}))
    old=db.scalar(select(MemoryWish).where(MemoryWish.user_id==uid,MemoryWish.create_request_id==data.request_id))
    if old:
        if old.create_fingerprint!=fp or old.deleted_at:raise MediaError('request_conflict','保存编号已使用',409)
        return public(db,old)
    validate_image(db,uid,data.image_asset_id,'wish')
    row=MemoryWish(user_id=uid,create_request_id=data.request_id,create_fingerprint=fp,initial_price=data.price,current_price=data.price,**values)
    db.add(row);db.flush()
    db.add(WishPrice(wish_id=row.id,user_id=uid,request_id=data.request_id,fingerprint=fp,kind='initial',price=data.price))
    db.flush();return public(db,row)

def mutate(db,uid,wid,data,delete=False):
    lock_user(db,uid);row=get(db,uid,wid)
    if row.version!=data.expected_version:raise MediaError('version_conflict','心愿已变化，请重新读取',409)
    if delete:row.deleted_at=now();release(db,uid,row.image_asset_id)
    else:
        validate_image(db,uid,data.image_asset_id,'wish',wid);old=row.image_asset_id
        if row.category!=data.category:row.category_source='manual'
        for k,v in data.model_dump(exclude={'expected_version'}).items():setattr(row,k,v)
        if old!=row.image_asset_id:release(db,uid,old)
    row.version+=1;db.flush()
    return {'deleted':True} if delete else public(db,row)

def price(db,uid,wid,data,correct=False):
    lock_user(db,uid);row=get(db,uid,wid);kind='correction' if correct else 'update'
    fp=fingerprint({'wish_id':wid,'kind':kind,**data.model_dump(exclude={'request_id'})})
    old=db.scalar(select(WishPrice).where(WishPrice.user_id==uid,WishPrice.request_id==data.request_id))
    if old:
        if old.fingerprint!=fp:raise MediaError('request_conflict','价格操作编号已使用',409)
        return public(db,row)
    if row.version!=data.expected_version:raise MediaError('version_conflict','心愿已变化，请重新读取',409)
    previous=row.initial_price if correct else row.current_price
    if correct:
        has_updates=db.scalar(select(WishPrice.id).where(WishPrice.wish_id==wid,WishPrice.kind=='update').limit(1))
        row.initial_price=data.price
        if not has_updates:row.current_price=data.price
    else:row.current_price=data.price
    db.add(WishPrice(wish_id=wid,user_id=uid,request_id=data.request_id,fingerprint=fp,kind=kind,price=data.price,
        previous_price=previous,note=data.note if correct else ''))
    row.version+=1;db.flush();return public(db,row)

def history(db,uid,wid,offset=0):
    get(db,uid,wid)
    rows=list(db.scalars(select(WishPrice).where(WishPrice.wish_id==wid,WishPrice.user_id==uid).order_by(WishPrice.recorded_at.desc(),WishPrice.id).offset(offset).limit(21)))
    return {'items':[{k:getattr(r,k) for k in ('id','kind','price','previous_price','note','recorded_at')} for r in rows[:20]],'next_offset':offset+20 if len(rows)>20 else None}
