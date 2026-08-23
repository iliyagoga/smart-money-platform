from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from statistics import mean, pstdev
from math import exp

from smc_core.engines import AnalysisPipeline
from smc_core.models import Candle, Timeframe
from smc_core.scenarios import ScenarioManager, TemplateStore

from .models import BacktestConfig, DirectionMode


@dataclass
class VirtualPosition:
    direction: str
    entry_price: float
    entry_time: int
    quantity: float
    stop: float
    targets: list[float]
    scenario_id: str
    template_id: str
    confidence: float
    initial_quantity: float
    realized: float = 0
    fees: float = 0


@dataclass
class TemplateModel:
    outcomes: dict[str, list[int]] = field(default_factory=dict)

    def probability(self, template_id: str, fallback: float) -> float:
        values = self.outcomes.get(template_id, [])
        return (sum(values) + 2 * fallback) / (len(values) + 2)

    def learn(self, template_id: str, outcome: int):
        self.outcomes.setdefault(template_id, []).append(outcome)


@dataclass
class FrozenModel:
    version: str
    feature_names: list[str]
    weights: list[float]
    bias: float

    def probability(self, template_id: str, fallback: float) -> float:
        features = {
            "confidence": fallback,
            "risk_reward": 2,
            "pnl_excursion_ratio": 0,
            "duration_log": 0,
            "direction_long": 0,
        }
        score = self.bias + sum(weight * features.get(name, 0) for name, weight in zip(self.feature_names, self.weights))
        predicted = 1 / (1 + exp(-max(-30, min(30, score))))
        return fallback * .65 + predicted * .35


def _candle(item: dict) -> Candle:
    return Candle.model_validate({**item, "timeframe": item["timeframe"]})


def _scenario_outcome(scenario, future: list[Candle]) -> int:
    entered = False
    for candle in future:
        if candle.timestamp <= scenario.created_at:
            continue
        if not entered:
            entered = candle.low <= scenario.entry_zone_high and candle.high >= scenario.entry_zone_low
            if not entered:
                continue
        stop_hit = candle.low <= scenario.stop_loss_price if scenario.direction == "LONG" else candle.high >= scenario.stop_loss_price
        target = scenario.take_profit_prices[0]
        target_hit = candle.high >= target if scenario.direction == "LONG" else candle.low <= target
        if stop_hit:
            return 0
        if target_hit:
            return 1
    return 0


def train_local_model(
    candles_by_tf: dict[str, list[dict]], primary_timeframe: str, config: BacktestConfig, template_dir: str,
) -> TemplateModel:
    pipeline = AnalysisPipeline()
    manager = ScenarioManager(TemplateStore(template_dir))
    model = TemplateModel()
    primary = [_candle(item) for item in candles_by_tf[primary_timeframe]]
    events = sorted((_candle(item) for values in candles_by_tf.values() for item in values), key=lambda item: item.timestamp)
    for candle in events:
        pipeline.process(candle)
        key = (candle.symbol, candle.timeframe)
        generated = manager.generate(
            candle.symbol, candle.timeframe, pipeline.obs[key], pipeline.fvgs[key], pipeline.liquidity[key],
            set(config.template_ids) or None, candle.timestamp,
        )
        for scenario in generated:
            future = [item for item in primary if item.timestamp > scenario.created_at]
            model.learn(scenario.setup_type, _scenario_outcome(scenario, future))
    return model


def run_smc_replay(
    candles_by_tf: dict[str, list[dict]],
    primary_timeframe: str,
    config: BacktestConfig,
    template_dir: str,
    model: TemplateModel | FrozenModel | None = None,
) -> dict:
    pipeline = AnalysisPipeline()
    manager = ScenarioManager(TemplateStore(template_dir))
    events = sorted((_candle(item) for values in candles_by_tf.values() for item in values), key=lambda item: (item.timestamp, item.timeframe))
    primary = {item.timestamp: item for item in (_candle(value) for value in candles_by_tf[primary_timeframe])}
    capital = config.initial_capital
    position: VirtualPosition | None = None
    pending = []
    trades = []
    decisions = []
    equity = []
    fee_rate = config.fee_percent / 100
    slip = config.slippage_percent / 100

    def close(candle, raw_price, reason, quantity=None):
        nonlocal capital, position
        quantity = quantity or position.quantity
        price = raw_price * (1 - slip if position.direction == "LONG" else 1 + slip)
        side = 1 if position.direction == "LONG" else -1
        gross = (price - position.entry_price) * quantity * side
        fees = price * quantity * fee_rate
        days = max(0, candle.timestamp - position.entry_time) / 86_400_000
        funding = position.entry_price * quantity * config.funding_percent_per_day / 100 * days * side
        pnl = gross - fees - funding
        capital += pnl
        position.realized += pnl
        position.fees += fees
        position.quantity -= quantity
        if position.quantity > 1e-12:
            position.stop = position.entry_price
            return
        trades.append({
            "id": len(trades) + 1, "direction": position.direction, "entry_time": position.entry_time,
            "exit_time": candle.timestamp, "entry_price": position.entry_price, "exit_price": price,
            "quantity": position.initial_quantity, "pnl": position.realized,
            "pnl_percent": position.realized / max(position.entry_price * position.initial_quantity / config.leverage, 1e-12) * 100,
            "fees": position.fees, "funding": funding, "reason": reason,
            "scenario_id": position.scenario_id, "template_id": position.template_id,
            "confidence": position.confidence,
        })
        position = None

    for candle in events:
        result = pipeline.process(candle)
        key = (candle.symbol, candle.timeframe)
        generated = manager.generate(
            candle.symbol, candle.timeframe, pipeline.obs[key], pipeline.fvgs[key], pipeline.liquidity[key],
            set(config.template_ids) or None, candle.timestamp,
        )
        for scenario in generated:
            confidence = model.probability(scenario.setup_type, scenario.confidence) if model else scenario.confidence
            allowed = confidence >= config.confidence_threshold and (
                config.direction_mode == DirectionMode.BOTH or config.direction_mode.value == scenario.direction
            )
            decisions.append({
                "timestamp": candle.timestamp, "scenario_id": scenario.id, "template_id": scenario.setup_type,
                "confidence": confidence, "decision": "PENDING" if allowed else "REJECTED",
            })
            if allowed:
                pending.append((scenario, confidence))
        if candle.timeframe != Timeframe(primary_timeframe):
            continue
        pending = [item for item in pending if item[0].expires_at >= candle.timestamp]
        if position:
            liquidation = position.entry_price * (
                1 - 1 / config.leverage + config.maintenance_margin_percent / 100
                if position.direction == "LONG"
                else 1 + 1 / config.leverage - config.maintenance_margin_percent / 100
            )
            liquidated = config.leverage > 1 and (
                candle.low <= liquidation if position.direction == "LONG" else candle.high >= liquidation
            )
            stop_hit = candle.low <= position.stop if position.direction == "LONG" else candle.high >= position.stop
            reached = [target for target in position.targets if candle.high >= target] if position.direction == "LONG" else [target for target in position.targets if candle.low <= target]
            if liquidated:
                close(candle, liquidation, "LIQUIDATION")
            elif stop_hit:
                gap_price = min(candle.open, position.stop) if position.direction == "LONG" else max(candle.open, position.stop)
                close(candle, gap_price, "STOP_LOSS")
            elif reached:
                target = reached[0]
                position.targets.remove(target)
                close(candle, target, "TAKE_PROFIT", position.quantity / 2 if position.targets else position.quantity)
        if position is None:
            candidates = [item for item in pending if candle.timestamp > item[0].created_at and candle.low <= item[0].entry_zone_high and candle.high >= item[0].entry_zone_low]
            if candidates:
                scenario, confidence = max(candidates, key=lambda item: item[1])
                raw_entry = min(max(candle.open, scenario.entry_zone_low), scenario.entry_zone_high)
                entry = raw_entry * (1 + slip if scenario.direction == "LONG" else 1 - slip)
                risk_distance = abs(entry - scenario.stop_loss_price)
                kelly = max(0, 2 * confidence - 1) * config.kelly_fraction * 100
                risk_percent = min(config.risk_per_trade_percent, kelly)
                quantity = min(capital * risk_percent / 100 / max(risk_distance, 1e-12), capital * config.leverage / entry)
                if quantity > 0:
                    entry_fee = entry * quantity * fee_rate
                    capital -= entry_fee
                    position = VirtualPosition(
                        scenario.direction, entry, candle.timestamp, quantity, scenario.stop_loss_price,
                        list(scenario.take_profit_prices), scenario.id, scenario.setup_type, confidence, quantity,
                        fees=entry_fee,
                    )
                pending.clear()
        unrealized = 0
        if position:
            unrealized = (candle.close - position.entry_price) * position.quantity * (1 if position.direction == "LONG" else -1)
        equity.append({"timestamp": candle.timestamp, "equity": capital + unrealized})
    if position and primary:
        last = primary[max(primary)]
        close(last, last.close, "END_OF_DATA")
        equity.append({"timestamp": last.timestamp, "equity": capital})
    return _report(config, candles_by_tf[primary_timeframe], capital, trades, equity, decisions, model)


def _report(config, candles, capital, trades, equity, decisions, model):
    peak = config.initial_capital
    drawdown = 0.0
    for point in equity:
        peak = max(peak, point["equity"])
        drawdown = max(drawdown, (peak - point["equity"]) / max(peak, 1e-12) * 100)
    wins = [item for item in trades if item["pnl"] > 0]
    gross_profit = sum(item["pnl"] for item in wins)
    gross_loss = abs(sum(item["pnl"] for item in trades if item["pnl"] < 0))
    returns = [equity[index]["equity"] / equity[index - 1]["equity"] - 1 for index in range(1, len(equity)) if equity[index - 1]["equity"]]
    sharpe = mean(returns) / pstdev(returns) * sqrt(252) if len(returns) > 1 and pstdev(returns) else 0
    net = capital - config.initial_capital
    closes = [float(item["close"]) for item in candles]
    distribution = {}
    for trade in trades:
        item = distribution.setdefault(trade["template_id"], {"trades": 0, "wins": 0, "pnl": 0})
        item["trades"] += 1
        item["wins"] += trade["pnl"] > 0
        item["pnl"] += trade["pnl"]
    return {
        "initial_capital": config.initial_capital, "final_capital": capital, "net_profit": net,
        "total_return_percent": net / config.initial_capital * 100, "max_drawdown_percent": drawdown,
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "profit_factor": gross_profit / gross_loss if gross_loss else None, "total_trades": len(trades),
        "average_trade": net / len(trades) if trades else 0, "sharpe_ratio": sharpe,
        "benchmark_return_percent": (closes[-1] / closes[0] - 1) * 100 if closes else 0,
        "trades": trades, "equity": equity, "decisions": decisions,
        "template_distribution": distribution, "dataset": {
            "test_candles": len(candles),
            "test_from": min((item["timestamp"] for item in candles), default=None),
            "test_to": max((item["timestamp"] for item in candles), default=None),
            "closed_candles_only": True,
        }, "model_training": {
            "mode": "LOCAL_RETRAIN" if isinstance(model, TemplateModel) else "PRETRAINED" if model else "BASELINE",
            "version": model.version if isinstance(model, FrozenModel) else None,
            "samples": sum(map(len, model.outcomes.values())) if isinstance(model, TemplateModel) else 0,
        },
    }
