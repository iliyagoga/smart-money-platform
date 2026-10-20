import asyncio
import json
from unittest.mock import AsyncMock
from uuid import UUID

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
        if not self.registered:return [{"symbol":"BTC-USDT-SWAP"}]
        return [{"symbol":item["symbol"]} for item in self.assets]

    def acquire(self):return Acquisition(self.connection)


def test_portfolio_live_uses_explicit_shared_capital_and_publishes_each_asset(monkeypatch):
    async def check():
        db=PortfolioDb();monkeypatch.setattr(execution_app.service,"db",db)
        validate=AsyncMock();validate_capital=AsyncMock();publish=AsyncMock()
        monkeypatch.setattr(execution_app.service,"validate_execution_mode",validate)
        monkeypatch.setattr(execution_app.service,"validate_portfolio_capital",validate_capital)
        monkeypatch.setattr(execution_app.service,"publish_channel",publish)
        result=await execution_app.portfolio_to_live(
            PORTFOLIO_ID,execution_app.PortfolioLiveRequest(mode="PRODUCTION",capital=140),"user-1",
        )
        assert result["capital"]==140
        assert result["activated_symbols"]==["BTC-USDT-SWAP","ETH-USDT-SWAP"]
        validate_capital.assert_awaited_once_with("PRODUCTION",140)
        assert validate.await_count==2 and publish.await_count==2
        assert db.connection.execute.await_count==3
        assert "status='INACTIVE'" in db.connection.execute.await_args_list[0].args[0]
        configs=[json.loads(call.args[3]) for call in db.connection.execute.await_args_list[1:]]
        assert [item["portfolioAllocationPercent"] for item in configs]==[60,40]
        assert all(item["initialCapital"]==140 and item["currentCapital"]==140 for item in configs)
        assert all(item["portfolioId"]==str(PORTFOLIO_ID) for item in configs)
    asyncio.run(check())


def test_portfolio_live_rejects_asset_without_active_local_metadata(monkeypatch):
    async def check():
        db=PortfolioDb(registered=False);monkeypatch.setattr(execution_app.service,"db",db)
        with pytest.raises(HTTPException,match="ETH-USDT-SWAP") as raised:
            await execution_app.portfolio_to_live(
                PORTFOLIO_ID,execution_app.PortfolioLiveRequest(mode="PRODUCTION",capital=140),"user-1",
            )
        assert raised.value.status_code==409
        assert db.connection.execute.await_count==0
    asyncio.run(check())
