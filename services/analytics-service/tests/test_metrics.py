import asyncio
from unittest.mock import AsyncMock
import pytest

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
           "event_type":"order.updated","source":"execution-service",
           "correlation_id":"okx-1789110956575","payload":{"symbol":"BTC-USDT-SWAP"}}
    asyncio.run(service.persist_event(event))
    assert service.db.execute.await_args.args[5]=="okx-1789110956575"

def test_market_events_are_kept_in_market_tables_without_duplicate_event_log_writes():
    service=AnalyticsService("database","redis",10000);service.db=AsyncMock()
    asyncio.run(service.persist_event({"event_type":"candle.update","source":"data-service"}))
    service.db.execute.assert_not_awaited()

def test_live_portfolio_snapshot_uses_its_140_capital_and_scoped_trades():
    async def check():
        service=AnalyticsService("database","redis",10000);service.db=AsyncMock();service.redis=AsyncMock()
        service.db.fetchrow.return_value={"mode":"PRODUCTION","config":{
          "portfolioId":"portfolio-1","initialCapital":140,"currentCapital":145,
        }}
        service.db.fetch.return_value=[]
        equity,daily=await service.sync_portfolio()
        assert equity==145 and daily==0
        assert service.db.fetch.await_args.args[1:]==("PRODUCTION","portfolio-1")
        service.redis.set.assert_any_await("portfolio:equity",145)
    asyncio.run(check())


@pytest.mark.parametrize("pnl,locked",[(0,0),(0,14),(5,0),(-3,0)])
def test_snapshot_uses_budgets_of_all_active_assets(pnl,locked):
    async def check():
        service=AnalyticsService("database","redis",10000);service.db=AsyncMock();service.redis=AsyncMock()
        # The latest asset has only 15% of $140. Another 35% is idle cash.
        config={"portfolioId":"portfolio-1","portfolioCapitalMode":"ALLOCATED",
          "portfolioInitialCapital":140,"portfolioActivationId":"run-1","activationId":"edited-asset",
          "initialCapital":21,"currentCapital":21+pnl}
        service.db.fetchrow.return_value={"mode":"PRODUCTION","config":config}
        async def fetch(query,*args):
            if "SELECT mode,config FROM trading_configs" in query:
                assert "status='ACTIVE'" in query
                return [{"mode":"PRODUCTION","config":config},
                        {"mode":"PRODUCTION","config":{"initialCapital":70,"currentCapital":70}}]
            if "SELECT config FROM trading_configs" in query:
                assert args==("PRODUCTION","portfolio-1","run-1")
                assert "IS NOT DISTINCT FROM" in query and "portfolioActivationId" in query
                assert "status='ACTIVE'" not in query
                return [{"config":config},{"config":{"initialCapital":70,"currentCapital":70}}]
            if "FROM positions" in query:
                return [{"data":{"entry_price":locked,"current_price":locked,"quantity":1,
                  "direction":"LONG","leverage":1}}] if locked else []
            assert args==("PRODUCTION","portfolio-1")
            return []
        service.db.fetch.side_effect=fetch
        snapshot=await service.snapshot()
        assert snapshot["total_equity"]==91+pnl
        assert snapshot["available_balance"]==91+pnl-locked
        assert snapshot["locked_margin"]==locked
    asyncio.run(check())


def test_snapshot_sums_manual_assets_and_shared_portfolio_only_once():
    async def check():
        service=AnalyticsService("database","redis",10000);service.db=AsyncMock();service.redis=AsyncMock()
        service.db.fetchrow.return_value=None
        shared={"portfolioId":"p1","portfolioCapitalMode":"SEQUENTIAL",
                "portfolioActivationId":"run","initialCapital":100,"currentCapital":105}
        async def fetch(query,*args):
            if "SELECT mode,config FROM trading_configs" in query:
                return [{"mode":"PRODUCTION","config":{"initialCapital":20,"currentCapital":22}},
                        {"mode":"PRODUCTION","config":{"initial_capital":30,"current_capital":27}},
                        {"mode":"PRODUCTION","config":shared},
                        {"mode":"PRODUCTION","config":{**shared,"activationId":"edited-asset"}}]
            return []
        service.db.fetch.side_effect=fetch
        snapshot=await service.snapshot()
        assert snapshot["total_equity"]==154
        assert snapshot["available_balance"]==154
    asyncio.run(check())


def test_sequential_portfolio_does_not_sum_shared_capital_across_assets():
    async def check():
        service=AnalyticsService("database","redis",10000);service.db=AsyncMock()
        service.db.fetchrow.return_value={"mode":"PRODUCTION","config":{
          "portfolioId":"portfolio-1","portfolioCapitalMode":"SEQUENTIAL",
          "initialCapital":140,"currentCapital":145}}
        context=await service.active_portfolio_context()
        assert context["initial"]==140 and context["current"]==145
        service.db.fetch.assert_not_awaited()
    asyncio.run(check())
