from sqlalchemy import select
from .images import MediaError
from .service import get_asset,current_object

def validate_image(db,uid,asset_id,kind,record_id=None):
    if not asset_id:return
    from ..items.models import MemoryItem
    from ..wishes.models import MemoryWish
    get_asset(db,uid,asset_id);current_object(db,uid,asset_id)
    for model,label in [(MemoryItem,'item'),(MemoryWish,'wish')]:
        stmt=select(model.id).where(model.image_asset_id==asset_id)
        if kind==label and record_id:stmt=stmt.where(model.id!=record_id)
        if db.scalar(stmt):raise MediaError('image_in_use','图片已关联其他物品或心愿',409)
