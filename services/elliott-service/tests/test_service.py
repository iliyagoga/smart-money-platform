import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


from src.app import app, rebuild_elliott_history
from src.models import Candle, Scenario, Timeframe
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
        signal = Scenario(symbol="BTC-USDT-SWAP", timeframe="M15", direction="LONG",
                          setup_type="ELLIOTT_WAVE3", confidence=1, entry_zone_low=100,
                          entry_zone_high=100, stop_loss_price=99, take_profit_prices=[102],
                          expires_at=100000)
        db=SimpleNamespace(execute=AsyncMock(),fetch=AsyncMock(return_value=[{
          "data":signal.model_dump(mode="json"),"correlation_id":None,
        }]))
        infra = SimpleNamespace(db=db, publish=AsyncMock())
        service = ElliottService(infra)
        service.trading_config = AsyncMock(return_value={"strategy": "ELLIOTT"})
        service.elliott.generate = Mock(return_value=[signal])
        result = await service.process(candle())
        assert result["scenarios_created"] == 1
        assert infra.db.execute.await_count==2
        assert infra.publish.call_args.args[:2] == ("scenario.update", "scenario.created")
        assert service.scenarios[signal.id] == signal
        assert signal.id in service.elliott.emitted
        service.elliott.generate.reset_mock()
        await service.process(candle(2), "history-rebuild")
        assert service.elliott.generate.call_args.kwargs["allow_live_emit"] is False
    asyncio.run(check())


def test_live_portfolio_analysis_loads_every_configured_timeframe_from_okx():
    async def check():
        service=ElliottService(SimpleNamespace(db=SimpleNamespace(execute=AsyncMock())))
        service.trading_config=AsyncMock(return_value={"strategy":"ELLIOTT","elliott":{
          "entryTimeframe":"M15","structureTimeframe":"H1","macroTimeframe":"H4",
        }})
        source={
          ("BTC-USDT-SWAP",Timeframe.M15):[candle(900_000)],
          ("BTC-USDT-SWAP",Timeframe.H1):[candle(3_600_000)],
          ("BTC-USDT-SWAP",Timeframe.H4):[candle(14_400_000)],
        }
        service.live_market=SimpleNamespace(load=AsyncMock(return_value=source))
        service.elliott.generate=Mock(return_value=[])
        await service.process(candle(900_000),"live-correlation")
        args=service.live_market.load.await_args.args
        assert args[0]=="BTC-USDT-SWAP"
        assert set(args[1])=={"M15","H1","H4"}
        assert args[2:]==("M15",900_000)
        assert service.elliott.generate.call_args.args[2] is source
    asyncio.run(check())


def test_only_elliott_analysis_routes_remain():
    routes = app.openapi()["paths"]
    assert "/elliott/patterns" in routes
    assert "/elliott/history" in routes
    assert not any("smart-money" in path or "scenario-templates" in path for path in routes)


def test_history_rebuild_endpoint_starts_a_background_calculation(monkeypatch):
    async def check():
        from src.app import service
        config=AsyncMock(return_value={"strategy":"ELLIOTT"})
        schedule=Mock()
        monkeypatch.setattr(service,"trading_config",config)
        monkeypatch.setattr(service,"schedule_history_snapshot",schedule)
        result=await rebuild_elliott_history("btc-usdt-swap")
        assert result=={"symbol":"BTC-USDT-SWAP","status":"BUILDING"}
        config.assert_awaited_once_with("BTC-USDT-SWAP")
        schedule.assert_called_once_with("BTC-USDT-SWAP")
    asyncio.run(check())


def test_candle_rebuild_restarts_historical_calculation():
    async def check():
        service=ElliottService(SimpleNamespace(db=SimpleNamespace(fetch=AsyncMock(return_value=[]))))
        service.schedule_history_snapshot=Mock()
        result=await service.rebuild("btc-usdt-swap",[Timeframe.M15,Timeframe.H1])
        assert result["symbol"]=="BTC-USDT-SWAP"
        service.schedule_history_snapshot.assert_called_once_with("BTC-USDT-SWAP")
    asyncio.run(check())


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
        monkeypatch.setattr("backtest_core.elliott.run_elliott_replay",lambda _candles,_config,*_progress:{
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
