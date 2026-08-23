from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, pstdev

from .models import BacktestConfig, DirectionMode, StrategyType


@dataclass
class Position:
    direction: str
    entry_price: float
    entry_time: int
    quantity: float
    peak: float
    trough: float


def sma(values: list[float], end: int, period: int) -> float:
    return mean(values[end - period + 1:end + 1])


def ema_series(values: list[float], period: int) -> list[float]:
    multiplier = 2 / (period + 1)
    result = [values[0]]
    for value in values[1:]:
        result.append(value * multiplier + result[-1] * (1 - multiplier))
    return result


def rsi(values: list[float], end: int, period: int) -> float:
    changes = [values[index] - values[index - 1] for index in range(end - period + 1, end + 1)]
    gains = mean([max(change, 0) for change in changes])
    losses = mean([max(-change, 0) for change in changes])
    return 100 if losses == 0 else 100 - 100 / (1 + gains / losses)


def signal_at(closes: list[float], index: int, config: BacktestConfig) -> tuple[bool, bool]:
    if config.strategy == StrategyType.SMA_CROSS:
        previous_fast = sma(closes, index - 1, config.fast_period)
        previous_slow = sma(closes, index - 1, config.slow_period)
        fast = sma(closes, index, config.fast_period)
        slow = sma(closes, index, config.slow_period)
        return previous_fast <= previous_slow and fast > slow, previous_fast >= previous_slow and fast < slow
    if config.strategy == StrategyType.RSI:
        previous = rsi(closes, index - 1, config.rsi_period)
        current = rsi(closes, index, config.rsi_period)
        return previous <= config.rsi_oversold < current, previous >= config.rsi_overbought > current
    if config.strategy == StrategyType.MACD:
        fast = ema_series(closes[:index + 1], config.fast_period)
        slow = ema_series(closes[:index + 1], config.slow_period)
        macd = [left - right for left, right in zip(fast, slow)]
        signal = ema_series(macd, 9)
        return macd[-2] <= signal[-2] and macd[-1] > signal[-1], macd[-2] >= signal[-2] and macd[-1] < signal[-1]
    window = closes[index - config.slow_period + 1:index + 1]
    middle = mean(window)
    deviation = pstdev(window)
    previous_window = closes[index - config.slow_period:index]
    previous_middle = mean(previous_window)
    previous_deviation = pstdev(previous_window)
    lower, upper = middle - deviation * 2, middle + deviation * 2
    previous_lower = previous_middle - previous_deviation * 2
    previous_upper = previous_middle + previous_deviation * 2
    return closes[index - 1] <= previous_lower and closes[index] > lower, closes[index - 1] >= previous_upper and closes[index] < upper


def run_backtest(candles: list[dict], config: BacktestConfig) -> dict:
    ordered = sorted(candles, key=lambda item: item["timestamp"])
    if len(ordered) <= config.slow_period + 2:
        raise ValueError("not enough candles for selected periods")
    closes = [float(item["close"]) for item in ordered]
    fee_rate = config.fee_percent / 100
    slippage_rate = config.slippage_percent / 100
    funding_rate = config.funding_percent_per_day / 100
    capital = config.initial_capital
    position: Position | None = None
    trades: list[dict] = []
    equity: list[dict] = [{"timestamp": ordered[0]["timestamp"], "equity": capital}]

    def close(raw_price: float, timestamp: int, reason: str):
        nonlocal capital, position
        if position is None:
            return
        exit_price = raw_price * (1 - slippage_rate if position.direction == "LONG" else 1 + slippage_rate)
        multiplier = 1 if position.direction == "LONG" else -1
        gross = (exit_price - position.entry_price) * position.quantity * multiplier
        fees = (position.entry_price + exit_price) * position.quantity * fee_rate
        days = max(0, timestamp - position.entry_time) / 86_400_000
        funding = position.entry_price * position.quantity * funding_rate * days * multiplier
        pnl = gross - fees - funding
        capital += pnl
        trades.append({
            "id": len(trades) + 1, "direction": position.direction, "entry_time": position.entry_time,
            "exit_time": timestamp, "entry_price": position.entry_price, "exit_price": exit_price,
            "quantity": position.quantity, "pnl": pnl,
            "pnl_percent": pnl / (position.entry_price * position.quantity / config.leverage) * 100,
            "fees": fees, "funding": funding, "reason": reason,
        })
        position = None

    def open_position(direction: str, raw_price: float, timestamp: int):
        nonlocal position
        price = raw_price * (1 + slippage_rate if direction == "LONG" else 1 - slippage_rate)
        notional = capital * config.position_size_percent / 100 * config.leverage
        position = Position(direction, price, timestamp, notional / price, price, price)

    for index in range(config.slow_period + 1, len(ordered)):
        candle = ordered[index]
        timestamp = int(candle["timestamp"])
        candle_open, high, low, close_price = map(float, (candle["open"], candle["high"], candle["low"], candle["close"]))
        long_signal, short_signal = signal_at(closes, index - 1, config)
        if position:
            position.peak = max(position.peak, high)
            position.trough = min(position.trough, low)
            if position.direction == "LONG":
                stop = position.entry_price * (1 - config.stop_loss_percent / 100)
                if config.trailing_stop_percent:
                    stop = max(stop, position.peak * (1 - config.trailing_stop_percent / 100))
                target = position.entry_price * (1 + config.take_profit_percent / 100)
                if candle_open <= stop or low <= stop:
                    close(min(candle_open, stop), timestamp, "STOP_LOSS")
                elif candle_open >= target or high >= target:
                    close(max(candle_open, target), timestamp, "TAKE_PROFIT")
                elif short_signal:
                    close(candle_open, timestamp, "SIGNAL")
            else:
                stop = position.entry_price * (1 + config.stop_loss_percent / 100)
                if config.trailing_stop_percent:
                    stop = min(stop, position.trough * (1 + config.trailing_stop_percent / 100))
                target = position.entry_price * (1 - config.take_profit_percent / 100)
                if candle_open >= stop or high >= stop:
                    close(max(candle_open, stop), timestamp, "STOP_LOSS")
                elif candle_open <= target or low <= target:
                    close(min(candle_open, target), timestamp, "TAKE_PROFIT")
                elif long_signal:
                    close(candle_open, timestamp, "SIGNAL")
        if position is None:
            if long_signal and config.direction_mode != DirectionMode.SHORT:
                open_position("LONG", candle_open, timestamp)
            elif short_signal and config.direction_mode != DirectionMode.LONG:
                open_position("SHORT", candle_open, timestamp)
        unrealized = 0
        if position:
            unrealized = (close_price - position.entry_price) * position.quantity * (1 if position.direction == "LONG" else -1)
        equity.append({"timestamp": timestamp, "equity": capital + unrealized})

    last = ordered[-1]
    if position:
        close(float(last["close"]), int(last["timestamp"]), "END_OF_DATA")
        equity.append({"timestamp": int(last["timestamp"]), "equity": capital})
    peak, max_drawdown = config.initial_capital, 0.0
    for point in equity:
        peak = max(peak, point["equity"])
        max_drawdown = max(max_drawdown, (peak - point["equity"]) / peak * 100)
    wins = [item for item in trades if item["pnl"] > 0]
    gross_profit = sum(item["pnl"] for item in wins)
    gross_loss = abs(sum(item["pnl"] for item in trades if item["pnl"] < 0))
    returns = [(equity[index]["equity"] / equity[index - 1]["equity"] - 1) for index in range(1, len(equity))]
    sharpe = mean(returns) / pstdev(returns) * sqrt(252) if len(returns) > 1 and pstdev(returns) else 0
    net_profit = capital - config.initial_capital
    benchmark = (closes[-1] / closes[0] - 1) * 100
    return {
        "initial_capital": config.initial_capital, "final_capital": capital, "net_profit": net_profit,
        "total_return_percent": net_profit / config.initial_capital * 100, "max_drawdown_percent": max_drawdown,
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None, "total_trades": len(trades),
        "average_trade": net_profit / len(trades) if trades else 0, "sharpe_ratio": sharpe,
        "benchmark_return_percent": benchmark, "trades": trades, "equity": equity,
    }
