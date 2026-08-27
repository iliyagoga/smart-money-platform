from __future__ import annotations
import asyncio,json
from time import time
from uuid import uuid4
import asyncpg
from redis.asyncio import Redis
from .models import *


class Infrastructure:
    def __init__(self,database_url:str,redis_url:str):self.database_url=database_url;self.redis_url=redis_url;self.db=None;self.redis=None
    async def connect(self):
        self.db=await asyncpg.create_pool(self.database_url,min_size=1,max_size=5)
        self.redis=Redis.from_url(self.redis_url,decode_responses=True)
        await self.redis.ping()
        async with self.db.acquire() as conn:
            await conn.execute("""
              CREATE TABLE IF NOT EXISTS smc_objects(
                id uuid NOT NULL, symbol text NOT NULL, timeframe text NOT NULL, object_type text NOT NULL,
                event_ts timestamptz NOT NULL, data jsonb NOT NULL, PRIMARY KEY(id,event_ts));
              SELECT create_hypertable('smc_objects','event_ts',if_not_exists=>TRUE);
              CREATE INDEX IF NOT EXISTS smc_lookup_idx ON smc_objects(symbol,timeframe,object_type,event_ts DESC);
              CREATE TABLE IF NOT EXISTS algorithm_signals(id uuid PRIMARY KEY,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL);
            """)
    async def close(self):
        if self.redis:await self.redis.aclose()
        if self.db:await self.db.close()
    async def publish(self,topic:str,event_type:str,payload:BaseModel|dict,correlation_id:str|None=None):
        body=payload.model_dump(mode="json") if isinstance(payload,BaseModel) else payload
        envelope={"message_id":str(uuid4()),"correlation_id":correlation_id or str(uuid4()),"timestamp":int(time()*1000),"source":"smc-service","version":"1.0.0","event_type":event_type,"payload":body}
        await self.redis.publish(topic,json.dumps(envelope,separators=(",",":")))
    async def save(self,kind:str,item:BaseModel):
        data=item.model_dump(mode="json"); ts=data.get("timestamp") or data.get("created_at") or int(time()*1000)
        await self.db.execute("INSERT INTO smc_objects(id,symbol,timeframe,object_type,event_ts,data) VALUES($1::uuid,$2,$3,$4,to_timestamp($5/1000.0),$6::jsonb) ON CONFLICT(id,event_ts) DO UPDATE SET data=excluded.data",
          data["id"],data["symbol"],str(data["timeframe"]),kind,ts,json.dumps(data))
    async def cache(self,prefix:str,symbol:str,timeframe:str,items:list[BaseModel]):
        await self.redis.set(f"{prefix}:{symbol}:{timeframe}",json.dumps([x.model_dump(mode='json') for x in items]),ex=604800)


async def resilient_loop(factory):
    while True:
        try:await factory()
        except asyncio.CancelledError:raise
        except Exception:await asyncio.sleep(2)
