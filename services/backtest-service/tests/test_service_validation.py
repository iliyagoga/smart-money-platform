import pytest

from src.service import validate_candle_series


def candle(timestamp=0, **changes):
    return {
        "timestamp": timestamp, "open": 100, "high": 101,
        "low": 99, "close": 100, "volume": 10, **changes,
    }


def test_valid_candle_series_is_accepted():
    validate_candle_series("M1", [candle(0), candle(60_000)])


@pytest.mark.parametrize("items, message", [
    ([candle(0), candle(0)], "duplicate or unordered"),
    ([candle(0), candle(120_000)], "internal M1 candle gap"),
    ([candle(0, high=98)], "invalid M1 OHLC"),
    ([candle(0, volume=-1)], "negative M1 volume"),
    ([candle(0, close=0)], "non-positive M1 price"),
])
def test_invalid_candle_series_is_rejected(items, message):
    with pytest.raises(ValueError, match=message):
        validate_candle_series("M1", items)
