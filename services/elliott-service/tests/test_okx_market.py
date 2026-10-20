import asyncio
import json

import httpx

from src.okx_market import OkxMarketDataUnavailable,OkxMarketSource


def okx_row(timestamp:int,closed:bool=True):
    return [str(timestamp),"100","101","99","100","10","10","1000","1" if closed else "0"]


def test_loads_complete_direct_okx_window_and_reuses_older_cache():
    async def check():
        calls=[]
        async def handler(request:httpx.Request):
            calls.append(request)
            after=request.url.params.get("after")
            newest=60_000_000 if after is None else int(after)-60_000
            rows=[okx_row(newest-index*60_000) for index in range(300)]
            return httpx.Response(200,json={"code":"0","data":rows})
        client=httpx.AsyncClient(base_url="https://www.okx.com",transport=httpx.MockTransport(handler))
        source=OkxMarketSource("https://www.okx.com",client)
        first=await source.load("BTC-USDT-SWAP",{"M1":500},"M1",60_000_000)
        assert len(first[("BTC-USDT-SWAP","M1")])==500
        assert len(calls)==2
        await source.load("BTC-USDT-SWAP",{"M1":500},"M1",60_000_000)
        assert len(calls)==3
        await client.aclose()
    asyncio.run(check())


def test_rejects_a_gap_in_the_okx_analysis_window():
    async def check():
        async def handler(request:httpx.Request):
            after=request.url.params.get("after")
            newest=60_000_000 if after is None else int(after)-120_000
            return httpx.Response(200,json={"code":"0","data":[okx_row(newest-index*120_000) for index in range(300)]})
        client=httpx.AsyncClient(base_url="https://www.okx.com",transport=httpx.MockTransport(handler))
        source=OkxMarketSource("https://www.okx.com",client)
        try:
            await source.load("BTC-USDT-SWAP",{"M1":500},"M1",60_000_000)
            raise AssertionError("incomplete series was accepted")
        except OkxMarketDataUnavailable:
            pass
        await client.aclose()
    asyncio.run(check())
