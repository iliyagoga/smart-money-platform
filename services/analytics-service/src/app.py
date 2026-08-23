from contextlib import asynccontextmanager
from datetime import datetime,timezone,timedelta
from fastapi import FastAPI,Query
from .metrics import *
from .service import AnalyticsService,decode
from .settings import settings
service=AnalyticsService(settings.database_url,settings.redis_url,settings.initial_capital)
@asynccontextmanager
async def lifespan(app):await service.start();yield;await service.stop()
app=FastAPI(title="Portfolio, Analytics and Monitoring Service",version="1.0.0",lifespan=lifespan)
def since(period):
    days={"day":1,"week":7,"month":30,"all":None}.get(period)
    return int((datetime.now(timezone.utc)-timedelta(days=days)).timestamp()*1000) if days else None
@app.get("/health")
async def health():await service.redis.ping();await service.db.fetchval("SELECT 1");return {"status":"UP"}
@app.get("/portfolio")
async def portfolio():return await service.snapshot()
@app.get("/portfolio/balance")
async def balance():
    x=await service.snapshot();return {"balances":[{"currency":settings.base_currency,"available":x["available_balance"],"locked":x["locked_margin"],"total":x["total_equity"]}]}
@app.get("/portfolio/equity")
async def portfolio_equity(period:str="all"):
    _,curve,_=await service.report(from_ts=since(period));return {"equity":curve}
@app.get("/portfolio/statistics")
async def portfolio_stats():
    _,_,m=await service.report();return {"total_trades":m["total_trades"],"win_rate":m["win_rate"],"profit_factor":m["profit_factor"],"max_drawdown":m["max_drawdown_value"],"sharpe_ratio":m["sharpe_ratio"]}
@app.get("/analytics/dashboard")
async def dashboard():
    snap=await service.snapshot();_,_,m=await service.report();open_count=await service.db.fetchval("SELECT count(*) FROM positions WHERE status!='CLOSED'");active=await service.db.fetchval("SELECT count(*) FROM scenarios WHERE status='ACTIVE'")
    return {"total_pnl":m["total_pnl"],"open_positions":open_count,"active_scenarios":active,"win_rate":m["win_rate"],"today_pnl":snap["realized_pnl_today"],"total_equity":snap["total_equity"]}
@app.get("/analytics/performance")
async def performance(period:str="all",symbol:str|None=None):
    _,curve,m=await service.report(symbol,since(period));return {"equity_curve":curve,"metrics":m}
@app.get("/analytics/winrate")
async def winrate(period:str="all",symbol:str|None=None):
    trades=await service.trades(symbol,since(period));groups={}
    for x in trades:
        key=x.get("symbol","unknown");g=groups.setdefault(key,[0,0]);g[0 if x["pnl"]>0 else 1]+=1
    return {"winrate":[{"group":k,"win_count":v[0],"loss_count":v[1],"rate":v[0]/sum(v)*100} for k,v in groups.items()]}
@app.get("/analytics/profit-factor")
async def profit_factor(period:str="all",symbol:str|None=None):
    _,_,m=await service.report(symbol,since(period));return {"profit_factor":m["profit_factor"]}
@app.get("/analytics/drawdown")
async def analytics_drawdown(period:str="all",symbol:str|None=None):
    _,curve,_=await service.report(symbol,since(period));return drawdown(curve)
@app.get("/analytics/sharpe")
async def sharpe(period:str="all",symbol:str|None=None):
    _,_,m=await service.report(symbol,since(period));return {"sharpe_ratio":m["sharpe_ratio"]}
@app.get("/monitoring/events")
async def events(limit:int=Query(100,ge=1,le=1000),type:str|None=None):
    rows=await service.db.fetch("SELECT (extract(epoch FROM event_ts)*1000)::bigint timestamp,event_type,source,payload FROM event_store WHERE ($1::text IS NULL OR event_type=$1) ORDER BY event_ts DESC LIMIT $2",type,limit);return {"events":[{"timestamp":r["timestamp"],"type":r["event_type"],"source":r["source"],"payload":decode(r["payload"])} for r in rows]}
@app.get("/monitoring/services")
async def services():
    import asyncio,httpx
    targets={"data-service":"http://data-service:8000/actuator/health","smc-service":"http://smc-service:8010/health","decision-service":"http://decision-service:8020/health","execution-service":"http://execution-service:8030/health"}
    async with httpx.AsyncClient(timeout=2) as client:
        async def check(name,url):
            try:r=await client.get(url);return {"name":name,"status":"UP" if r.is_success else "DOWN","uptime":None,"processed_events":0,"error_rate":0}
            except Exception:return {"name":name,"status":"DOWN","uptime":None,"processed_events":0,"error_rate":1}
        return {"services":await asyncio.gather(*(check(*x) for x in targets.items()))}
@app.get("/monitoring")
async def monitoring():
    result=await services();up=sum(x["status"]=="UP" for x in result["services"]);status="HEALTHY" if up==len(result["services"]) else "DEGRADED" if up else "DOWN";return {"status":status,"services":result["services"],"alerts":[]}
@app.get("/monitoring/performance")
async def monitoring_performance(service_name:str|None=None):return {"cpu_usage":None,"memory_usage":None,"queue_size":await service.redis.xlen("trading.command"),"processing_latency":None}
