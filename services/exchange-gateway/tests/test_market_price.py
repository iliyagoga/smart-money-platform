import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from src.service import ExchangeGateway
from src.settings import Settings


SYMBOL="BTC-USDT-SWAP"


def gateway(body,status=200):
    service=ExchangeGateway(Settings(_env_file=None))
    service.okx_client=AsyncMock()
    service.okx_client.get.return_value=httpx.Response(status,json=body,
      request=httpx.Request("GET","https://www.okx.com/api/v5/market/ticker"))
    return service


def test_market_price_requests_current_public_ticker_every_time():
    async def check():
        service=gateway({"code":"0","data":[{"instId":SYMBOL,"last":"100.123456789"}]})
        for _ in range(2):
            assert await service.market_price(SYMBOL)=={"symbol":SYMBOL,"price":"100.123456789"}
        assert service.okx_client.get.await_count==2
        assert service.okx_client.get.await_args.args[0].endswith("/api/v5/market/ticker")
        assert service.okx_client.get.await_args.kwargs=={"params":{"instId":SYMBOL}}
    asyncio.run(check())


@pytest.mark.parametrize("body",[
    {"code":"50011","data":[]}, {"code":"0","data":[]},
    *[{"code":"0","data":[{"instId":SYMBOL,"last":price}]}
      for price in [None,"","0","-1","NaN","Infinity"]],
    {"code":"0","data":[{"instId":"ETH-USDT-SWAP","last":"100"}]},
])
def test_missing_or_invalid_ticker_is_rejected(body):
    with pytest.raises(ValueError):asyncio.run(gateway(body).market_price(SYMBOL))


def test_http_failure_is_not_treated_as_a_price():
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(gateway({},status=503).market_price(SYMBOL))


def test_market_price_route_normalizes_symbol_and_rejects_invalid_symbol(monkeypatch):
    from src import app as exchange_app
    from fastapi import HTTPException
    async def check():
        get_price=AsyncMock(return_value={"symbol":SYMBOL,"price":"100"})
        monkeypatch.setattr(exchange_app.service,"market_price",get_price)
        assert await exchange_app.market_price(" btc-usdt-swap ")=={"symbol":SYMBOL,"price":"100"}
        get_price.assert_awaited_once_with(SYMBOL)
        with pytest.raises(HTTPException) as error:await exchange_app.market_price("invalid")
        assert error.value.status_code==422
        get_price.side_effect=ValueError("Ticker unavailable")
        with pytest.raises(HTTPException) as error:await exchange_app.market_price(SYMBOL)
        assert error.value.status_code==502
    asyncio.run(check())
