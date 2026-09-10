import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


from src.app import app
from src.models import Candle, Scenario
from src.service import ElliottService


def candle(timestamp=1, close=100):
    return Candle(symbol="BTC-USDT-SWAP", timeframe="M15", timestamp=timestamp,
                  open=100, high=101, low=99, close=close, volume=10)


def test_candle_store_replaces_updates_and_bounds_history():
    service = ElliottService(None)
    for timestamp in range(510):
        service.store_candle(candle(timestamp))
    service.store_candle(candle(509, 101))
    bars = service.candles[("BTC-USDT-SWAP", "M15")]
    assert len(bars) == 500
    assert bars[0].timestamp == 10
    assert bars[-1].close == 101


def test_elliott_signal_persisted_and_published_without_smc_pipeline():
    async def check():
        infra = SimpleNamespace(db=SimpleNamespace(execute=AsyncMock()), publish=AsyncMock())
        service = ElliottService(infra)
        service.trading_config = AsyncMock(return_value={"strategy": "ELLIOTT"})
        signal = Scenario(symbol="BTC-USDT-SWAP", timeframe="M15", direction="LONG",
                          setup_type="ELLIOTT_WAVE3", confidence=1, entry_zone_low=100,
                          entry_zone_high=100, stop_loss_price=99, take_profit_prices=[102],
                          expires_at=100000)
        service.elliott.generate = Mock(return_value=[signal])
        result = await service.process(candle())
        assert result["scenarios_created"] == 1
        infra.db.execute.assert_awaited_once()
        assert infra.publish.call_args.args[:2] == ("scenario.update", "scenario.created")
        assert service.scenarios[signal.id] == signal
        service.elliott.generate.reset_mock()
        await service.process(candle(2), "history-rebuild")
        assert service.elliott.generate.call_args.kwargs["allow_live_emit"] is False
    asyncio.run(check())


def test_only_elliott_analysis_routes_remain():
    routes = app.openapi()["paths"]
    assert "/elliott/patterns" in routes
    assert "/elliott/history" in routes
    assert not any("smart-money" in path or "scenario-templates" in path for path in routes)


def test_historical_paper_replay_is_persisted_outside_live_trade_tables(monkeypatch):
    async def check():
        timestamps={"M15":900_000,"H1":3_600_000,"H4":14_400_000}
        db=SimpleNamespace(execute=AsyncMock())
        async def fetch(_query,_symbol,timeframe,_limit):
            step=timestamps[timeframe]
            return [{"symbol":"BTC-USDT-SWAP","timeframe":timeframe,"timestamp":index*step,
                     "open":100.0,"high":101.0,"low":99.0,"close":100.0,"volume":1000.0,
                     "quote_volume":None,"trades_count":None,"is_closed":True} for index in range(4)]
        db.fetch=AsyncMock(side_effect=fetch)
        service=ElliottService(SimpleNamespace(db=db))
        service.trading_config=AsyncMock(return_value={"strategy":"ELLIOTT","elliott":{
          "entryTimeframe":"M15","structureTimeframe":"H1","macroTimeframe":"H4"}})
        monkeypatch.setattr("backtest_core.elliott.run_elliott_replay",lambda _candles,_config:{
          "elliott_patterns":[],"total_trades":1,"net_profit":10,"win_rate":100,
          "initial_capital":10000,"final_capital":10010,"dataset":{},"trades":[{
            "pattern_id":"pattern","direction":"LONG","entry_time":900_000,"entry_price":100,
            "exit_time":1_800_000,"exit_price":102,"pnl":10,"pnl_percent":1,"reason":"FIXED_RR_TARGET",
            "initial_stop":99,"take_profit_prices":[102]}]})
        result=await service.rebuild_history_snapshot("BTC-USDT-SWAP")
        assert result and result["trades"][0]["origin"]=="HISTORICAL_PAPER"
        queries=[call.args[0] for call in db.execute.await_args_list]
        assert all("closed_trades" not in query and "orders(" not in query for query in queries)
        saved=json.loads(db.execute.await_args_list[-1].args[4])
        assert saved["orders"][0]["status"]=="FILLED" and saved["summary"]["net_pnl"]==10
    asyncio.run(check())
