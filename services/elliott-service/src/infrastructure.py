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
              CREATE TABLE IF NOT EXISTS scenarios(id uuid PRIMARY KEY,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL);
              CREATE TABLE IF NOT EXISTS elliott_history_snapshots(
                symbol text PRIMARY KEY,
                status text NOT NULL,
                config_hash text NOT NULL,
                data jsonb NOT NULL DEFAULT '{}'::jsonb,
                error text,
                updated_at timestamptz NOT NULL DEFAULT now()
              );
              CREATE TABLE IF NOT EXISTS elliott_scenario_outbox(
                scenario_id uuid PRIMARY KEY REFERENCES scenarios(id) ON DELETE CASCADE,
                correlation_id text,
                published_at timestamptz,
                created_at timestamptz NOT NULL DEFAULT now()
              );
            """)
    async def close(self):
        if self.redis:await self.redis.aclose()
        if self.db:await self.db.close()
    async def publish(self,topic:str,event_type:str,payload:BaseModel|dict,correlation_id:str|None=None):
        body=payload.model_dump(mode="json") if isinstance(payload,BaseModel) else payload
        envelope={"message_id":str(uuid4()),"correlation_id":correlation_id or str(uuid4()),"timestamp":int(time()*1000),"source":"elliott-service","version":"1.0.0","event_type":event_type,"payload":body}
        await self.redis.publish(topic,json.dumps(envelope,separators=(",",":")))


async def resilient_loop(factory):
    while True:
        try:await factory()
        except asyncio.CancelledError:raise
        except Exception:await asyncio.sleep(2)
