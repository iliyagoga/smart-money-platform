import asyncio,json,logging
from datetime import datetime,timezone
from time import time
import asyncpg,httpx
from redis.asyncio import Redis
from .metrics import equity_curve,drawdown,statistics

log=logging.getLogger(__name__)
def decode(v):return json.loads(v) if isinstance(v,str) else v
class AnalyticsService:
    def __init__(self,db_url,redis_url,initial):self.db_url=db_url;self.redis_url=redis_url;self.initial=initial;self.db=None;self.redis=None;self.task=None
    async def start(self):
        self.db=await asyncpg.create_pool(self.db_url,min_size=1,max_size=8);self.redis=Redis.from_url(self.redis_url,decode_responses=True);await self.redis.ping()
        await self.db.execute("""CREATE TABLE IF NOT EXISTS event_store(message_id uuid NOT NULL,event_ts timestamptz NOT NULL,event_type text NOT NULL,source text NOT NULL,correlation_id text,payload jsonb NOT NULL,PRIMARY KEY(message_id,event_ts));SELECT create_hypertable('event_store','event_ts',if_not_exists=>TRUE);ALTER TABLE event_store ALTER COLUMN correlation_id TYPE text USING correlation_id::text;CREATE INDEX IF NOT EXISTS event_store_lookup ON event_store(event_type,event_ts DESC);""")
        await self.sync_portfolio();self.task=asyncio.create_task(self.listen())
    async def stop(self):
        if self.task:self.task.cancel()
        if self.redis:await self.redis.aclose()
        if self.db:await self.db.close()
    async def listen(self):
        while True:
            ps=self.redis.pubsub();await ps.psubscribe("*")
            try:
                async for msg in ps.listen():
                    if msg["type"]!="pmessage":continue
                    try:
                        event=json.loads(msg["data"])
                        if not all(x in event for x in ("message_id","event_type","source","payload")):continue
                        await self.persist_event(event)
                        if event["event_type"] in {"position.opened","position.closed","position.updated"}:await self.sync_portfolio()
                    except Exception:log.exception("Failed to persist analytics event")
            except asyncio.CancelledError:await ps.aclose();raise
            except Exception:await ps.aclose();await asyncio.sleep(2)
    async def persist_event(self,event):
        if event.get("source")=="data-service" and event["event_type"] in {
                "candle.update","trade.executed","orderbook.updated"}:
            return
        await self.db.execute("INSERT INTO event_store(message_id,event_ts,event_type,source,correlation_id,payload) VALUES($1::uuid,to_timestamp($2/1000.0),$3,$4,$5,$6::jsonb) ON CONFLICT DO NOTHING",event["message_id"],event["timestamp"],event["event_type"],event["source"],event.get("correlation_id"),json.dumps(event["payload"]))
    async def trades(self,symbol=None,from_ts=None,to_ts=None):
        rows=await self.db.fetch("SELECT data FROM closed_trades WHERE ($1::text IS NULL OR symbol=$1) AND ($2::bigint IS NULL OR closed_at>=to_timestamp($2/1000.0)) AND ($3::bigint IS NULL OR closed_at<=to_timestamp($3/1000.0)) ORDER BY closed_at",symbol.upper() if symbol else None,from_ts,to_ts)
        return [decode(x["data"]) for x in rows]
    async def active_portfolio_context(self):
        try:row=await self.db.fetchrow("""SELECT mode,config FROM trading_configs WHERE status='ACTIVE'
          AND coalesce(config->>'portfolioId',config->>'portfolio_id') IS NOT NULL ORDER BY updated_at DESC LIMIT 1""")
        except asyncpg.UndefinedTableError:return None
        if not row:return None
        config=decode(row["config"]);initial=float(config.get("initialCapital",config.get("initial_capital",self.initial)))
        current=float(config.get("currentCapital",config.get("current_capital",initial)))
        return {"mode":str(row["mode"]).upper(),"portfolio_id":config.get("portfolioId",config.get("portfolio_id")),
                "initial":initial,"current":current}
    async def sync_portfolio(self):
        context=await self.active_portfolio_context()
        if context:
            rows=await self.db.fetch("""SELECT data FROM closed_trades WHERE data->>'execution_mode'=$1
              AND data->>'portfolio_id'=$2 ORDER BY closed_at""",context["mode"],context["portfolio_id"])
            trades=[decode(row["data"]) for row in rows];equity=context["current"]
        else:
            trades=await self.trades();total=sum(float(x["pnl"]) for x in trades);equity=self.initial+total
        today=datetime.now(timezone.utc).date();today_pnl=sum(float(x["pnl"]) for x in trades if datetime.fromtimestamp(x["closed_at"]/1000,timezone.utc).date()==today)
        await self.redis.set("portfolio:equity",equity);await self.redis.set("portfolio:daily_pnl",today_pnl)
        return equity,today_pnl
    async def snapshot(self):
        equity,today=await self.sync_portfolio();rows=await self.db.fetch("SELECT data FROM positions WHERE status!='CLOSED'");positions=[decode(x["data"]) for x in rows]
        unrealized=sum((p["current_price"]-p["entry_price"])*p["quantity"]*(1 if p["direction"]=="LONG" else -1)
          -p["entry_price"]*p["quantity"]*p.get("entry_fee_percent",0)/100 for p in positions)
        open_realized=sum(float(p.get("realized_pnl",0)) for p in positions)
        locked=sum(p["entry_price"]*p["quantity"]/max(p.get("leverage",1),1) for p in positions)
        return {"total_equity":equity+open_realized+unrealized,
          "available_balance":max(0,equity+open_realized-locked),"locked_margin":locked,
          "unrealized_pnl":unrealized,"realized_pnl_today":today+open_realized}
    async def report(self,symbol=None,from_ts=None,to_ts=None):
        trades=await self.trades(symbol,from_ts,to_ts);curve=equity_curve(self.initial,trades);return trades,curve,{**statistics(trades),**drawdown(curve)}
