import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from src.models import RiskConfig,Scenario
from src.resolver import ConflictResolver
from src.service import DecisionService


def signal(symbol="ETH-USDT-SWAP",created_at=1000):
    item=Scenario(id=str(uuid4()),symbol=symbol,timeframe="M1",direction="LONG",setup_type="ELLIOTT_WAVE3",
      confidence=1,entry_zone_low=100,entry_zone_high=100,entry_type="MARKET",stop_loss_price=99,
      take_profit_prices=[102],created_at=created_at,expires_at=9999999999999)
    return ConflictResolver().signal(item).model_copy(update={"created_at":created_at})


def service(capital_mode="ALLOCATED",active=(),execution_mode="PRODUCTION",recent=()):
    item=DecisionService("unused","unused")
    item.config=AsyncMock(return_value=RiskConfig())
    item.redis=AsyncMock();item.redis.scard.return_value=99
    item.db=AsyncMock();item.stream=AsyncMock()
    item.db.fetchrow.return_value={"config":{
      "initialCapital":1000,"currentCapital":1000,"riskPerTradePercent":1,
      "portfolioAllocationPercent":50,"portfolioId":"portfolio","portfolioCapitalMode":capital_mode,
      "elliott":{"useMargin":False,"reinvestProfits":True},
    },"mode":execution_mode,"lot_size":.01,"minimum_order_size":.01}
    async def fetch(query,*args):
        if "FROM closed_trades" in query:return list(recent)
        if "UNION ALL" in query:return list(active)
        return []
    item.db.fetch.side_effect=fetch
    item.http=AsyncMock();item.http.get.return_value=httpx.Response(200,json={"available":1000},
      request=httpx.Request("GET","http://exchange/account/capacity"))
    return item


@pytest.mark.parametrize("mode",["PAPER","DEMO","PRODUCTION"])
def test_parallel_avax_position_allows_another_asset_with_its_full_allocated_budget(mode):
    async def check():
        item=service(active=[{"symbol":"AVAX-USDT-SWAP","capital_mode":"ALLOCATED"}],execution_mode=mode)
        decision=await item.assess(signal())
        assert decision.approved and decision.position_size==10 and decision.risk_amount==10
        assert item.stream.await_args.args[1]=="risk.approved"
        assert item.stream.await_args.args[2]["portfolio_capital_mode"]=="ALLOCATED"
        # The budget has already been split at activation; it must not be halved again.
        history=next(call for call in item.db.fetch.await_args_list if "FROM closed_trades" in call.args[0])
        assert history.args[1:]==(mode,"portfolio","ETH-USDT-SWAP")
    asyncio.run(check())


@pytest.mark.parametrize("capital_mode,active_mode,symbol",[
    ("ALLOCATED","ALLOCATED","ETH-USDT-SWAP"),
    ("SEQUENTIAL","ALLOCATED","AVAX-USDT-SWAP"),
    ("ALLOCATED",None,"AVAX-USDT-SWAP"),
    ("ALLOCATED","SEQUENTIAL","AVAX-USDT-SWAP"),
])
def test_same_asset_and_sequential_or_legacy_trades_keep_their_slot(capital_mode,active_mode,symbol):
    async def check():
        item=service(capital_mode,active=[{"symbol":symbol,"capital_mode":active_mode}])
        decision=await item.assess(signal())
        assert not decision.approved and decision.rejection_reason=="Another trade is still active"
        assert item.stream.await_args.args[1]=="risk.rejected"
    asyncio.run(check())


@pytest.mark.parametrize("symbols,approved",[
    (["AVAX-USDT-SWAP","ETH-USDT-SWAP"],2),
    (["AVAX-USDT-SWAP","AVAX-USDT-SWAP"],1),
])
def test_concurrent_approvals_reserve_each_asset_until_an_order_is_persisted(symbols,approved):
    async def check():
        item=service()
        decisions=await asyncio.gather(*(item.assess(signal(symbol)) for symbol in symbols))
        assert sum(decision.approved for decision in decisions)==approved
        assert len(item.reserved_signals)==approved
    asyncio.run(check())


def test_sequential_reservation_blocks_other_assets_before_the_first_order_exists():
    async def check():
        item=service("SEQUENTIAL")
        first,second=await asyncio.gather(item.assess(signal("AVAX-USDT-SWAP")),item.assess(signal()))
        assert first.approved and not second.approved
        approval=next(call for call in item.stream.await_args_list if call.args[1]=="risk.approved")
        assert approval.args[2]["portfolio_capital_mode"]=="SEQUENTIAL"
    asyncio.run(check())


def test_waiting_on_avax_does_not_starve_a_free_asset():
    async def check():
        item=service(active=[{"symbol":"AVAX-USDT-SWAP","capital_mode":"ALLOCATED"}])
        busy=signal("AVAX-USDT-SWAP",1000);free=signal(created_at=2000)
        item.signals={busy.signal_id:busy,free.signal_id:free};item.waiting=set(item.signals)
        await item.retry_waiting()
        assert item.waiting=={busy.signal_id}
        assert set(item.reserved_signals)=={free.signal_id}
    asyncio.run(check())


def test_stale_redis_markers_cannot_block_a_free_asset_and_unknown_orders_are_counted():
    async def check():
        item=service()
        assert (await item.assess(signal())).approved
        item.redis.scard.assert_not_awaited()
        activity=next(call.args[0] for call in item.db.fetch.await_args_list if "UNION ALL" in call.args[0])
        assert "'UNKNOWN'" in activity and "status!='CLOSED'" in activity
    asyncio.run(check())


def test_recovery_releases_only_persisted_or_expired_reservations():
    async def check():
        item=service();first=signal("AVAX-USDT-SWAP");second=signal()
        expired=signal("BTC-USDT-SWAP").model_copy(update={"expires_at":1})
        item.signals={s.signal_id:s for s in (first,second,expired)}
        item.reserved_signals={s.signal_id:(s.symbol,"ALLOCATED") for s in (first,second,expired)}
        item.db.fetch.side_effect=[[{"signal_id":first.signal_id}],
          [{"symbol":s.symbol,"config":{}} for s in (second,expired)]]
        await item.release_reservations()
        assert item.reserved_signals=={second.signal_id:(second.symbol,"ALLOCATED")}
    asyncio.run(check())


def test_reactivation_releases_an_approved_but_unpersisted_old_signal():
    async def check():
        item=service("SEQUENTIAL");old=signal("AVAX-USDT-SWAP",1000)
        assert (await item.assess(old)).approved
        item.db.fetch.side_effect=[[],[{"symbol":old.symbol,"config":{"activatedAt":2000}}]]
        await item.release_reservations()
        assert not item.reserved_signals
        item.db.fetch.side_effect=None;item.db.fetch.return_value=[]
        assert (await item.assess(signal(created_at=3000))).approved
    asyncio.run(check())


def test_restart_restores_unpersisted_approvals_before_admitting_new_signals():
    async def check():
        item=service();old=signal("AVAX-USDT-SWAP")
        item.db.fetch.side_effect=None;item.db.fetch.return_value=[{
          "data":old.model_dump(),"config":{"portfolioCapitalMode":"ALLOCATED"}}]
        await item.restore_reservations()
        item.db.fetch.return_value=[]
        assert not (await item.assess(signal(old.symbol))).approved
        assert (await item.assess(signal())).approved
    asyncio.run(check())


def test_first_install_can_start_before_execution_tables_exist():
    async def check():
        import asyncpg
        item=service();item.db.fetch.side_effect=asyncpg.UndefinedTableError("orders")
        await item.restore_reservations()
        assert not item.reserved_signals
    asyncio.run(check())


def test_allocated_budget_still_obeys_daily_loss_and_cooldown_limits():
    async def check():
        from src.models import now_ms
        item=service(recent=[{"pnl":-60,"closed_at_ms":now_ms()}])
        decision=await item.assess(signal())
        assert not decision.approved and decision.rejection_reason=="Daily loss limit exceeded"
        item=service(recent=[{"pnl":-1,"closed_at_ms":now_ms()}]*2)
        decision=await item.assess(signal())
        assert not decision.approved and "Loss-streak cooldown" in decision.rejection_reason
    asyncio.run(check())


@pytest.mark.parametrize("reinvest,expected",[(True,10),(False,5)])
def test_risk_api_override_cannot_increase_an_allocated_budget(reinvest,expected):
    async def check():
        item=service();config=item.db.fetchrow.return_value["config"]
        config["initialCapital"]=500;config["elliott"]["reinvestProfits"]=reinvest
        decision=await item.assess(signal(),capital=10000)
        assert decision.approved and decision.position_size==expected
    asyncio.run(check())


def test_exhausted_first_asset_does_not_block_a_funded_asset():
    async def check():
        from src.models import now_ms
        item=service(recent=[{"pnl":-1000,"closed_at_ms":now_ms()}])
        funded=item.db.fetchrow.return_value
        exhausted={**funded,"config":{**funded["config"],"currentCapital":0}}
        async def strategy(query,symbol):return exhausted if symbol=="AVAX-USDT-SWAP" else funded
        item.db.fetchrow.side_effect=strategy
        busy=signal("AVAX-USDT-SWAP",1000);free=signal(created_at=2000)
        # Only the exhausted asset has losses; the second asset has its own history.
        async def fetch(query,*args):
            return [{"pnl":-1000,"closed_at_ms":now_ms()}] if "closed_trades" in query and args[-1]==busy.symbol else []
        item.db.fetch.side_effect=fetch
        item.signals={busy.signal_id:busy,free.signal_id:free};item.waiting=set(item.signals)
        await item.retry_waiting()
        assert not item.waiting and set(item.reserved_signals)=={free.signal_id}
        assert item.stream.await_args_list[0].args[2]["rejection_reason"]=="Trading capital must be positive"
    asyncio.run(check())


def test_error_on_one_waiting_asset_does_not_block_another_or_revive_expired_signals():
    async def check():
        from src.models import RiskDecision
        item=service();broken=signal("AVAX-USDT-SWAP",1000);free=signal(created_at=2000)
        expired=signal("BTC-USDT-SWAP").model_copy(update={"expires_at":1})
        item.signals={s.signal_id:s for s in (broken,free,expired)};item.waiting=set(item.signals)
        item.assess=AsyncMock(side_effect=[ValueError("bad asset config"),RiskDecision(signal_id=free.signal_id,approved=True)])
        await item.retry_waiting()
        assert [call.args[0] for call in item.assess.await_args_list]==[broken,free]
        assert expired.signal_id not in item.waiting
    asyncio.run(check())
