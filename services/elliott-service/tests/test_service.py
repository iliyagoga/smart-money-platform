import asyncio
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
