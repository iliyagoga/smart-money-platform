from src.engine import run_backtest
from src.models import BacktestConfig, DirectionMode, StrategyType


def candles(closes, spread=0):
    return [
        {"timestamp": index * 60_000, "open": close, "high": close + spread,
         "low": close - spread, "close": close, "volume": 100}
        for index, close in enumerate(closes)
    ]


def config(**changes):
    values = {
        "initial_capital": 10_000, "position_size_percent": 100, "fast_period": 2, "slow_period": 3,
        "stop_loss_percent": 5, "take_profit_percent": 10, "fee_percent": 0, "slippage_percent": 0,
        "direction_mode": DirectionMode.BOTH,
        "strategy": StrategyType.SMA_CROSS,
    }
    return BacktestConfig(**{**values, **changes})


def test_flat_market_has_no_trades():
    result = run_backtest(candles([100] * 20), config())
    assert result["total_trades"] == 0
    assert result["final_capital"] == 10_000


def test_signal_uses_next_candle_open_without_lookahead():
    data = candles([10, 9, 10, 12, 14, 13, 11, 9, 8, 10])
    result = run_backtest(data, config(stop_loss_percent=50, take_profit_percent=50))
    assert result["total_trades"] > 0
    first = result["trades"][0]
    entry_index = first["entry_time"] // 60_000
    assert first["entry_price"] == data[entry_index]["open"]


def test_stop_loss_uses_intrabar_low_and_conservative_order():
    data = candles([10, 9, 10, 12, 12, 12, 12, 12, 12], spread=0)
    data[5]["low"] = 5
    data[5]["high"] = 20
    result = run_backtest(data, config(stop_loss_percent=5, take_profit_percent=5, direction_mode="LONG"))
    assert result["trades"][0]["reason"] == "STOP_LOSS"


def test_entry_candle_can_stop_position_and_uses_stop_before_target():
    data = candles([10, 9, 10, 12, 12, 12, 12, 12, 12], spread=0)
    # The cross is confirmed by candle 3 and entry is at candle 4 open.
    data[4]["low"] = 5
    data[4]["high"] = 20

    result = run_backtest(data, config(stop_loss_percent=5, take_profit_percent=5, direction_mode="LONG"))

    assert result["trades"][0]["entry_time"] == data[4]["timestamp"]
    assert result["trades"][0]["exit_time"] == data[4]["timestamp"]
    assert result["trades"][0]["reason"] == "STOP_LOSS"


def test_fees_slippage_and_funding_reduce_capital():
    data = candles([10, 9, 10, 12, 14, 13, 11, 9, 8, 10])
    baseline = run_backtest(data, config(stop_loss_percent=50, take_profit_percent=50))
    costs = run_backtest(data, config(
        stop_loss_percent=50, take_profit_percent=50, fee_percent=.2,
        slippage_percent=.1, funding_percent_per_day=.5,
    ))
    assert costs["final_capital"] < baseline["final_capital"]


def test_supported_strategies_return_finite_metrics():
    data = candles([100 + (index % 12) - 6 for index in range(80)], spread=1)
    for strategy in StrategyType:
        result = run_backtest(data, config(strategy=strategy, fast_period=5, slow_period=20))
        assert result["max_drawdown_percent"] >= 0
        assert "benchmark_return_percent" in result
