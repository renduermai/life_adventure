from decimal import Decimal,ROUND_HALF_UP
from sqlalchemy import select
from app.modules.identity.service import lock_user
from ..people.service import today,now,fingerprint
from ..shared.images import MediaError
from ..shared.models import MemoryAsset,MemoryObject
from ..shared.service import get_asset,current_object,retire
from .models import MemoryItem

def cost(price,purchased,current):
    days=max(1,(current-purchased).days)
    return days,price/Decimal(days)

def get(db,uid,iid):
    row=db.scalar(select(MemoryItem).where(MemoryItem.id==iid,MemoryItem.user_id==uid,MemoryItem.deleted_at.is_(None)))
    if not row:raise MediaError('not_found','物品不存在或无权访问',404)
    return row

def validate(db,uid,data,item_id=None):
    if data.purchase_date>today(db,uid):raise MediaError('future_date','购买日期不能晚于今天')
    if data.image_asset_id:
        from ..shared.references import validate_image
        validate_image(db,uid,data.image_asset_id,'item',item_id)
        get_asset(db,uid,data.image_asset_id);current_object(db,uid,data.image_asset_id)
        used=db.scalar(select(MemoryItem.id).where(MemoryItem.image_asset_id==data.image_asset_id,MemoryItem.id!=item_id if item_id else MemoryItem.id.is_not(None)))
        if used:raise MediaError('image_in_use','图片已关联其他物品',409)

def release(db,uid,asset_id):
    if not asset_id:return
    asset=get_asset(db,uid,asset_id);asset.deleted_at=now();asset.version+=1
    for obj in db.scalars(select(MemoryObject).where(MemoryObject.asset_id==asset_id,MemoryObject.user_id==uid,MemoryObject.state.in_(['pending','active']))):retire(obj)

def public(row,current):
    days,value=cost(row.purchase_price,row.purchase_date,current)
    return {'id':row.id,'name':row.name,'purchase_date':row.purchase_date,'purchase_price':str(row.purchase_price),'currency':'CNY',
        'is_entitlement':row.is_entitlement,'expires_at':row.expires_at,
        'remaining_days':(row.expires_at-current).days if row.is_entitlement and row.expires_at else None,
        'category':row.category,'image_asset_id':row.image_asset_id,'image_url':'/api/shining-memories/assets/'+str(row.image_asset_id) if row.image_asset_id else None,
        'days':days,'daily_cost':str(value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)),'version':row.version,'created_at':row.created_at}

def listing(db,uid,category='',offset=0):
    current=today(db,uid);rows=list(db.scalars(select(MemoryItem).where(MemoryItem.user_id==uid,MemoryItem.deleted_at.is_(None))))
    categories=sorted({r.category for r in rows if r.category})
    if category:rows=[r for r in rows if r.category==category]
    rows.sort(key=lambda r:(cost(r.purchase_price,r.purchase_date,current)[1],r.created_at,str(r.id)))
    values=[public(r,current) for r in rows]
    raw=[cost(r.purchase_price,r.purchase_date,current)[1] for r in rows]
    for index,value in enumerate(values):
        value['cost_band']='neutral' if len(set(raw))<3 else ('low' if raw[index]<=raw[(len(raw)-1)//3] else 'high' if raw[index]>raw[(2*(len(raw)-1))//3] else 'medium')
    return {'items':values[offset:offset+20],'next_offset':offset+20 if len(values)>offset+20 else None,'categories':categories,'total':len(values),'today':current}

def create(db,uid,data):
    lock_user(db,uid);values=data.model_dump(exclude={'request_id'})
    fp=fingerprint(values if data.is_entitlement else {k:v for k,v in values.items() if k not in {'is_entitlement','expires_at'}})
    old=db.scalar(select(MemoryItem).where(MemoryItem.user_id==uid,MemoryItem.create_request_id==data.request_id))
    if old:
        if old.create_fingerprint!=fp or old.deleted_at:raise MediaError('request_conflict','保存编号已被使用',409)
        return public(old,today(db,uid))
    validate(db,uid,data);row=MemoryItem(user_id=uid,create_request_id=data.request_id,create_fingerprint=fp,**values)
    db.add(row);db.flush();return public(row,today(db,uid))

def mutate(db,uid,iid,data,delete=False):
    lock_user(db,uid);row=get(db,uid,iid)
    if row.version!=data.expected_version:raise MediaError('version_conflict','物品已变化，请重新读取',409)
    if delete:row.deleted_at=now();release(db,uid,row.image_asset_id)
    else:
        validate(db,uid,data,iid);old=row.image_asset_id
        for k,v in data.model_dump(exclude={'expected_version'}).items():setattr(row,k,v)
        if old!=row.image_asset_id:release(db,uid,old)
    row.version+=1;row.updated_at=now();db.flush()
    return {'deleted':True} if delete else public(row,today(db,uid))
