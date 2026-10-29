import asyncio
import json
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
from fastapi import HTTPException

from src import app as execution_app


PORTFOLIO_ID=UUID("00000000-0000-0000-0000-000000000001")


def strategy_config():
    return {
        "strategy":"ELLIOTT",
        "initialCapital":10_000,
        "riskPerTradePercent":1,
        "leverage":1,
        "elliott":{},
    }


class Transaction:
    async def __aenter__(self):return self
    async def __aexit__(self,*_):return False


class Connection:
    def __init__(self):self.execute=AsyncMock()
    def transaction(self):return Transaction()


class Acquisition:
    def __init__(self,connection):self.connection=connection
    async def __aenter__(self):return self.connection
    async def __aexit__(self,*_):return False


class PortfolioDb:
    def __init__(self,registered=True):
        self.assets=[
            {"symbol":"BTC-USDT-SWAP","allocation_percent":60,"config":strategy_config()},
            {"symbol":"ETH-USDT-SWAP","allocation_percent":40,"config":strategy_config()},
        ]
        self.registered=registered;self.connection=Connection()

    async def fetchrow(self,*_):return {"assets":self.assets}

    async def fetch(self,*_):
        if "owner_id IS NOT NULL" in _[0]:return []
        if not self.registered:return [{"symbol":"BTC-USDT-SWAP"}]
        return [{"symbol":item["symbol"]} for item in self.assets]

    def acquire(self):return Acquisition(self.connection)


@pytest.mark.parametrize("capital_mode,capitals",[("SEQUENTIAL",[140,140]),("ALLOCATED",[84,56])])
def test_portfolio_live_applies_capital_mode_and_publishes_each_asset(monkeypatch,capital_mode,capitals):
    async def check():
        db=PortfolioDb();monkeypatch.setattr(execution_app.service,"db",db)
        prepare=AsyncMock();validate=AsyncMock();validate_capital=AsyncMock();publish=AsyncMock()
        monkeypatch.setattr(execution_app.service,"prepare_portfolio_assets",prepare)
        monkeypatch.setattr(execution_app.service,"validate_execution_mode",validate)
        monkeypatch.setattr(execution_app.service,"validate_strategy_config",AsyncMock())
        monkeypatch.setattr(execution_app.service,"validate_portfolio_capital",validate_capital)
        monkeypatch.setattr(execution_app.service,"publish_channel",publish)
        result=await execution_app.portfolio_to_live(
            PORTFOLIO_ID,execution_app.PortfolioLiveRequest(mode="PRODUCTION",capital=140,capital_mode=capital_mode),"user-1",
        )
        assert result["capital"]==140
        assert result["capital_mode"]==capital_mode
        assert result["activated_symbols"]==["BTC-USDT-SWAP","ETH-USDT-SWAP"]
        prepare.assert_awaited_once_with(["BTC-USDT-SWAP","ETH-USDT-SWAP"])
        validate_capital.assert_awaited_once_with("PRODUCTION",140)
        assert validate.await_count==2 and publish.await_count==2
        assert db.connection.execute.await_count==3
        assert "status='INACTIVE'" in db.connection.execute.await_args_list[0].args[0]
        configs=[json.loads(call.args[3]) for call in db.connection.execute.await_args_list[1:]]
        assert [item["portfolioAllocationPercent"] for item in configs]==[60,40]
        assert [item["initialCapital"] for item in configs]==capitals
        assert [item["currentCapital"] for item in configs]==capitals
        assert all(item["portfolioCapitalMode"]==capital_mode for item in configs)
        assert all(item["portfolioInitialCapital"]==140 for item in configs)
        assert configs[0]["portfolioActivationId"]==configs[1]["portfolioActivationId"]==configs[0]["activationId"]
        assert all(item["portfolioId"]==str(PORTFOLIO_ID) for item in configs)
    asyncio.run(check())


@pytest.mark.parametrize("capital_mode",["ALLOCATED","SEQUENTIAL"])
def test_live_allocation_sum_is_limited_only_in_parallel_mode(monkeypatch,capital_mode):
    async def check():
        db=PortfolioDb()
        for asset in db.assets:asset["allocation_percent"]=100
        monkeypatch.setattr(execution_app.service,"db",db)
        for name in ("prepare_portfolio_assets","validate_execution_mode","validate_strategy_config",
                     "validate_portfolio_capital","publish_channel"):
            monkeypatch.setattr(execution_app.service,name,AsyncMock())
        request=execution_app.PortfolioLiveRequest(capital=140,capital_mode=capital_mode)
        if capital_mode=="ALLOCATED":
            with pytest.raises(HTTPException,match="must not exceed 100%"):
                await execution_app.portfolio_to_live(PORTFOLIO_ID,request,"user-1")
            db.connection.execute.assert_not_awaited()
        else:
            await execution_app.portfolio_to_live(PORTFOLIO_ID,request,"user-1")
            configs=[json.loads(call.args[3]) for call in db.connection.execute.await_args_list[1:]]
            assert [item["currentCapital"] for item in configs]==[140,140]
    asyncio.run(check())


def test_live_capital_mode_is_validated_and_legacy_requests_remain_sequential():
    from pydantic import ValidationError
    assert execution_app.PortfolioLiveRequest(capital=140).capital_mode=="SEQUENTIAL"
    with pytest.raises(ValidationError):
        execution_app.PortfolioLiveRequest(capital=140,capital_mode="PARALLELL")


@pytest.mark.parametrize("patch",[
    {"initialCapital":140},{"currentCapital":140},{"portfolioAllocationPercent":100},
    {"portfolioCapitalMode":"SEQUENTIAL"},{"portfolioId":"other"},
    {"portfolioActivationId":"other"},{"portfolioInitialCapital":10000},
])
def test_editing_an_asset_cannot_bypass_its_allocated_portfolio_budget(monkeypatch,patch):
    async def check():
        config={**strategy_config(),"initialCapital":84,"currentCapital":84,
          "portfolioCapitalMode":"ALLOCATED","portfolioId":str(PORTFOLIO_ID),"portfolioAllocationPercent":60,
          "portfolioInitialCapital":140,"portfolioActivationId":"portfolio-start","activationId":"asset-start"}
        db=AsyncMock();db.fetchval.return_value="user-1"
        db.fetchrow.return_value={"mode":"PRODUCTION","config":config}
        monkeypatch.setattr(execution_app.service,"db",db)
        prepare=AsyncMock();monkeypatch.setattr(execution_app.service,"prepare_portfolio_assets",prepare)
        request=execution_app.TradingConfigCreate(symbol="AVAX-USDT-SWAP",mode="PRODUCTION",config={**config,**patch})
        with pytest.raises(HTTPException,match="reactivating the portfolio"):
            await execution_app.save_trading_config(request,"user-1")
        prepare.assert_not_awaited()
        assert db.fetchrow.await_count==1
    asyncio.run(check())


def test_allocated_strategy_can_be_edited_without_changing_budget_or_mode(monkeypatch):
    async def check():
        config={**strategy_config(),"initialCapital":84,"currentCapital":84,
          "portfolioCapitalMode":"ALLOCATED","portfolioId":str(PORTFOLIO_ID),"portfolioAllocationPercent":60,
          "portfolioInitialCapital":140,"portfolioActivationId":"portfolio-start","activationId":"asset-start"}
        db=AsyncMock();db.fetchval.return_value="user-1"
        db.fetchrow.side_effect=[{"mode":"PRODUCTION","config":config},{"symbol":"AVAX-USDT-SWAP","config":config}]
        monkeypatch.setattr(execution_app.service,"db",db)
        for name in ("prepare_portfolio_assets","validate_execution_mode","validate_strategy_config",
                     "validate_portfolio_capital","publish_channel"):
            monkeypatch.setattr(execution_app.service,name,AsyncMock())
        request=execution_app.TradingConfigCreate(symbol="AVAX-USDT-SWAP",mode="PRODUCTION",config={**config,"riskPerTradePercent":.5})
        await execution_app.save_trading_config(request,"user-1")
        saved=json.loads(db.fetchrow.await_args.args[3])
        assert saved["currentCapital"]==84 and saved["riskPerTradePercent"]==.5
        assert saved["portfolioCapitalMode"]=="ALLOCATED"
        assert saved["portfolioActivationId"]=="portfolio-start" and saved["activationId"]!="asset-start"
    asyncio.run(check())


def test_portfolio_live_rejects_asset_without_active_local_metadata(monkeypatch):
    async def check():
        db=PortfolioDb(registered=False);monkeypatch.setattr(execution_app.service,"db",db)
        monkeypatch.setattr(execution_app.service,"prepare_portfolio_assets",AsyncMock())
        with pytest.raises(HTTPException,match="ETH-USDT-SWAP") as raised:
            await execution_app.portfolio_to_live(
                PORTFOLIO_ID,execution_app.PortfolioLiveRequest(mode="PRODUCTION",capital=140),"user-1",
            )
        assert raised.value.status_code==409
        assert db.connection.execute.await_count==0
    asyncio.run(check())


def test_portfolio_live_reports_exchange_instrument_preparation_failure(monkeypatch):
    async def check():
        db=PortfolioDb();monkeypatch.setattr(execution_app.service,"db",db)
        prepare=AsyncMock(side_effect=ValueError("OKX instrument metadata is unavailable: ETH-USDT-SWAP"))
        monkeypatch.setattr(execution_app.service,"prepare_portfolio_assets",prepare)
        with pytest.raises(HTTPException,match="ETH-USDT-SWAP") as raised:
            await execution_app.portfolio_to_live(
                PORTFOLIO_ID,execution_app.PortfolioLiveRequest(mode="PRODUCTION",capital=140),"user-1",
            )
        assert raised.value.status_code==409
        assert db.connection.execute.await_count==0
    asyncio.run(check())


def test_portfolio_preparation_timeout_has_actionable_error(monkeypatch):
    async def check():
        client=AsyncMock();client.post.side_effect=httpx.ReadTimeout("")
        monkeypatch.setattr(execution_app.service,"http",client)
        with pytest.raises(ValueError,match=r"exchange gateway timeout \(ReadTimeout\)"):
            await execution_app.service.prepare_portfolio_assets(["AVAX-USDT-SWAP"])
    asyncio.run(check())


def test_manual_live_asset_prepares_exchange_metadata_and_checks_equity(monkeypatch):
    async def check():
        db=AsyncMock();db.fetchval.return_value=None
        db.fetchrow.return_value={"symbol":"AVAX-USDT-SWAP","mode":"PRODUCTION","status":"ACTIVE",
                                  "config":strategy_config()}
        monkeypatch.setattr(execution_app.service,"db",db)
        monkeypatch.setattr(execution_app.service,"orders",{})
        monkeypatch.setattr(execution_app.service,"positions",{})
        prepare=AsyncMock();validate=AsyncMock();capital=AsyncMock();publish=AsyncMock()
        monkeypatch.setattr(execution_app.service,"prepare_portfolio_assets",prepare)
        monkeypatch.setattr(execution_app.service,"validate_strategy_config",validate)
        monkeypatch.setattr(execution_app.service,"validate_execution_mode",validate)
        monkeypatch.setattr(execution_app.service,"validate_portfolio_capital",capital)
        monkeypatch.setattr(execution_app.service,"publish_channel",publish)
        result=await execution_app.save_trading_config(execution_app.TradingConfigCreate(
          symbol="AVAX-USDT-SWAP",mode="PRODUCTION",config=strategy_config()),"user-1")
        assert result["status"]=="ACTIVE"
        prepare.assert_awaited_once_with(["AVAX-USDT-SWAP"])
        capital.assert_awaited_once_with("PRODUCTION",10_000)
        assert validate.await_count==2
        publish.assert_awaited_once()
    asyncio.run(check())


def test_removing_active_asset_disables_entries_and_requests_exit(monkeypatch):
    from src.models import Order,Position

    async def check():
        db=AsyncMock();db.fetchval.return_value="BTC-USDT-SWAP"
        monkeypatch.setattr(execution_app.service,"db",db)
        order=Order(symbol="BTC-USDT-SWAP",side="BUY",type="MARKET",quantity=1,
                    execution_mode="PRODUCTION",status="SUBMITTING")
        position=Position(order_id=order.id,symbol=order.symbol,direction="LONG",entry_price=100,
                          current_price=100,quantity=1,initial_quantity=1,execution_mode="PRODUCTION")
        monkeypatch.setattr(execution_app.service,"orders",{order.id:order})
        monkeypatch.setattr(execution_app.service,"positions",{position.id:position})
        cancel=AsyncMock();close=AsyncMock();publish=AsyncMock()
        monkeypatch.setattr(execution_app.service,"request_cancel",cancel)
        monkeypatch.setattr(execution_app.service,"request_position_close",close)
        monkeypatch.setattr(execution_app.service,"publish_channel",publish)
        result=await execution_app.delete_trading_config(order.symbol,"user-1")
        assert result["status"]=="STOPPING"
        assert "status='INACTIVE'" in db.fetchval.await_args.args[0]
        cancel.assert_awaited_once_with(order)
        close.assert_awaited_once_with(position,1,"ASSET_REMOVED")
        publish.assert_awaited_once()
    asyncio.run(check())
