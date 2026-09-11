import asyncio
from unittest.mock import AsyncMock

from src.metrics import *
from src.service import AnalyticsService
def trades():return [{"closed_at":1,"pnl":100,"pnl_percent":1},{"closed_at":2,"pnl":-50,"pnl_percent":-.5},{"closed_at":3,"pnl":150,"pnl_percent":1.5}]
def test_equity_curve():assert equity_curve(10000,trades())[-1]["value"]==10200
def test_drawdown():assert drawdown(equity_curve(10000,trades()))["max_drawdown_value"]==50
def test_statistics():
    result=statistics(trades());assert result["win_rate"]==2/3*100 and result["profit_factor"]==5

def test_event_store_accepts_non_uuid_correlation_ids():
    service=AnalyticsService("database","redis",10000);service.db=AsyncMock()
    event={"message_id":"00000000-0000-0000-0000-000000000001","timestamp":1,
           "event_type":"candle.update","source":"data-service",
           "correlation_id":"okx-1789110956575","payload":{"symbol":"BTC-USDT-SWAP"}}
    asyncio.run(service.persist_event(event))
    assert service.db.execute.await_args.args[5]=="okx-1789110956575"
