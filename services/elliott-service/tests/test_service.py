from types import SimpleNamespace
from src.models import Candle, Timeframe
from src.service import ElliottService
from src.elliott_live import ElliottLiveEngine


def candle(timestamp, close=100):
    return Candle(symbol="BTC-USDT", timeframe="M15", timestamp=timestamp,
                  open=100, high=101, low=99, close=close, volume=10)


def test_buffer_replaces_current_candle_and_rejects_out_of_order_history():
    service = ElliottService(SimpleNamespace())
    assert service.remember(candle(100))
    assert service.remember(candle(100, 101))
    assert not service.remember(candle(99))
    assert [item.close for item in service.candles[("BTC-USDT", Timeframe.M15)]] == [101]


def test_live_engine_uses_shared_elliott_config_without_model_dependencies():
    assert ElliottLiveEngine().generate("BTC-USDT", candle(100), {}, {"strategy": "ELLIOTT"}) == []
