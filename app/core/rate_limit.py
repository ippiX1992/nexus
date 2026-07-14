import hashlib
import time
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.models import RateLimitModel


async def enforce_rate_limit(db,identity:str,limit:int,window_seconds:int)->None:
    window=int(time.time())//window_seconds; key=hashlib.sha256(f"{identity}:{window}".encode()).hexdigest(); expires=datetime.now(UTC)+timedelta(seconds=window_seconds)
    stmt=insert(RateLimitModel).values(key=key,count=1,expires_at=expires).on_conflict_do_update(index_elements=[RateLimitModel.key],set_={"count":RateLimitModel.count+1}).returning(RateLimitModel.count)
    count=await db.scalar(stmt)
    if count and count>limit: raise HTTPException(429,"Too many requests",headers={"Retry-After":str(window_seconds)})
