from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from math import ceil, floor, sqrt
from statistics import mean, pstdev
from math import exp

from smc_core.engines import AnalysisPipeline
from smc_core.models import Candle, Timeframe
from smc_core.scenarios import ScenarioManager, TemplateStore

from .models import BacktestConfig, DirectionMode

TIMEFRAME_MILLISECONDS = {
    Timeframe.M1: 60_000, Timeframe.M5: 300_000, Timeframe.M15: 900_000, Timeframe.M30: 1_800_000,
    Timeframe.H1: 3_600_000, Timeframe.H4: 14_400_000, Timeframe.D1: 86_400_000,
}


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
    target_allocations: list[float] = field(default_factory=list)
    break_even_rule: str = "ONE_R"
    move_stop_to_break_even_after_target: int | None = 1
    targets_hit: int = 0
    realized: float = 0
    fees: float = 0
    funding: float = 0
    last_funding_time: int = 0


@dataclass
class TemplateModel:
    outcomes: dict[str, list[int]] = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    folds: list[dict] = field(default_factory=list)

    def probability(self, template_id: str, fallback: float) -> float:
        values = self.outcomes.get(template_id, [])
        posterior = (sum(values) + 2 * fallback) / (len(values) + 2)
        return fallback * .65 + posterior * .35

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


def _chart_candles(candles: list[dict], maximum: int = 3000) -> list[dict]:
    """Bound chart payload/DOM size while preserving OHLC extremes and volume."""
    if len(candles) <= maximum:
        return [{key: item[key] for key in ("timestamp", "open", "high", "low", "close", "volume")} for item in candles]
    bucket_size = max(1, (len(candles) + maximum - 1) // maximum)
    result = []
    for offset in range(0, len(candles), bucket_size):
        bucket = candles[offset:offset + bucket_size]
        result.append({
            "timestamp": bucket[0]["timestamp"], "open": bucket[0]["open"],
            "high": max(item["high"] for item in bucket), "low": min(item["low"] for item in bucket),
            "close": bucket[-1]["close"], "volume": sum(item["volume"] for item in bucket),
        })
    return result


def _execution_plan(entry: float, scenario, minimum_stop_percent: float, tick_size: float,
                    fixed_ratios: list[float] | None = None, minimum_target_rr: float = 1.5,
                    maximum_target_rr: float = 8, fixed_only: bool = False) -> tuple[float, list[float]]:
    """Rebase the structural plan on the actual fill and enforce a usable stop distance."""
    side = 1 if scenario.direction == "LONG" else -1
    planned_entry = (scenario.entry_zone_low + scenario.entry_zone_high) / 2
    planned_risk = (planned_entry - scenario.stop_loss_price) * side
    structural_risk = (entry - scenario.stop_loss_price) * side
    minimum_risk = entry * minimum_stop_percent / 100
    risk = max(structural_risk, minimum_risk, tick_size)

    # Preserve each scenario target's intended R multiple, but measure it from
    # the actual fill and the corrected stop instead of the zone midpoint.
    ratios = []
    if planned_risk > 0 and not fixed_only:
        ratios = [
            (target - planned_entry) * side / planned_risk
            for target in scenario.take_profit_prices
            if (target - planned_entry) * side > 0
        ]
    ratios = [ratio for ratio in ratios if minimum_target_rr <= ratio <= maximum_target_rr]
    fixed = [ratio for ratio in (fixed_ratios or [2, 3]) if minimum_target_rr <= ratio <= maximum_target_rr]
    # Keep at most one structural/liquidity objective and always retain a
    # deterministic RR objective so a nearby pool cannot consume every target.
    ratios = ratios[:1]
    for ratio in fixed:
        if all(abs(ratio - item) > 1e-9 for item in ratios):
            ratios.append(ratio)
        if len(ratios) >= max(1, len(scenario.take_profit_prices)):
            break
    if not ratios:
        ratios = [minimum_target_rr]

    if side > 0:
        stop = floor((entry - risk) / tick_size) * tick_size
        targets = [ceil((entry + risk * ratio) / tick_size) * tick_size for ratio in ratios]
    else:
        stop = ceil((entry + risk) / tick_size) * tick_size
        targets = [floor((entry - risk * ratio) / tick_size) * tick_size for ratio in ratios]
    return stop, list(dict.fromkeys(targets))


def _template_stop_distance_allowed(entry: float, stop: float, template) -> bool:
    """Check the template's structural-stop band against the actual executable fill."""
    stop_percent = abs(entry - stop) / entry * 100
    minimum = getattr(template, "minimum_stop_percent", None)
    maximum = getattr(template, "maximum_stop_percent", None)
    return ((minimum is None or stop_percent >= minimum)
            and (maximum is None or stop_percent <= maximum))


def _target_allocations(template, target_count: int) -> list[float]:
    configured = list(getattr(template, "target_allocations", []) or [])
    if configured and len(configured) == target_count:
        return configured
    return [1 / target_count] * target_count if target_count else []


def _scenario_zone_key(scenario) -> str | None:
    zone = next((item for item in getattr(scenario, "objects_used", []) if item.get("type") == "ORDER_BLOCK"), None)
    return f"{scenario.setup_type}:{zone['id']}" if zone else None


def _scenario_outcome(scenario, future: list[Candle], start: int = 0, ready_at: int | None = None,
                      config: BacktestConfig | None = None, fixed_ratios: list[float] | None = None,
                      template=None) -> int | None:
    entered = False
    stop = scenario.stop_loss_price
    target = scenario.take_profit_prices[0]
    ready_at = ready_at if ready_at is not None else scenario.created_at
    expires_at = ready_at + max(0, scenario.expires_at - scenario.created_at)
    for index in range(start, len(future)):
        candle = future[index]
        available_at = candle.timestamp + TIMEFRAME_MILLISECONDS[candle.timeframe]
        if available_at > expires_at:
            break
        if available_at <= ready_at:
            continue
        if not entered:
            entered = candle.low <= scenario.entry_zone_high and candle.high >= scenario.entry_zone_low
            if not entered:
                continue
            if config:
                raw_entry = min(max(candle.open, scenario.entry_zone_low), scenario.entry_zone_high)
                entry = round(raw_entry / config.tick_size) * config.tick_size
                target_rr = config.smc_target_rr
                stop, targets = _execution_plan(
                    entry, scenario, config.smc_min_stop_percent, config.tick_size,
                    [target_rr] if target_rr is not None else fixed_ratios,
                    target_rr if target_rr is not None else (template.minimum_target_rr if template and template.minimum_target_rr is not None else config.smc_min_target_rr),
                    target_rr if target_rr is not None else (template.maximum_target_rr if template and template.maximum_target_rr is not None else config.smc_max_target_rr),
                    fixed_only=target_rr is not None,
                )
                target = targets[0]
        stop_hit = candle.low <= stop if scenario.direction == "LONG" else candle.high >= stop
        target_hit = candle.high >= target if scenario.direction == "LONG" else candle.low <= target
        if stop_hit:
            return 0
        if target_hit:
            return 1
    return None


def train_local_model(
    candles_by_tf: dict[str, list[dict]], primary_timeframe: str, config: BacktestConfig, template_dir: str,
) -> TemplateModel:
    pipeline = AnalysisPipeline()
    manager = ScenarioManager(TemplateStore(template_dir))
    model = TemplateModel()
    primary = [_candle(item) for item in candles_by_tf[primary_timeframe]]
    primary_timestamps = [item.timestamp + TIMEFRAME_MILLISECONDS[item.timeframe] for item in primary]
    rank = {Timeframe.D1: 0, Timeframe.H4: 1, Timeframe.H1: 2, Timeframe.M30: 3,
            Timeframe.M15: 4, Timeframe.M5: 5, Timeframe.M1: 6}
    events = sorted((_candle(item) for values in candles_by_tf.values() for item in values),
                    key=lambda item: (item.timestamp + TIMEFRAME_MILLISECONDS[item.timeframe], rank[item.timeframe]))
    for candle in events:
        ready_at = candle.timestamp + TIMEFRAME_MILLISECONDS[candle.timeframe]
        pipeline.process(candle)
        generated = manager.generate_top_down(candle.symbol, candle, pipeline, set(config.template_ids) or None)
        for scenario in generated:
            start = bisect_right(primary_timestamps, ready_at)
            template = manager.store.get(scenario.setup_type)
            outcome = _scenario_outcome(
                scenario, primary, start, ready_at, config, template.risk_reward if template else None, template,
            )
            if outcome is not None:
                model.learn(scenario.setup_type, outcome)
    all_outcomes=[(template,value) for template,values in model.outcomes.items() for value in values]
    folds=[]
    for fold in range(3):
        train_end=max(1,int(len(all_outcomes)*(.5+fold*.15)));validation_end=min(len(all_outcomes),train_end+max(1,len(all_outcomes)//6))
        training=all_outcomes[:train_end];validation=all_outcomes[train_end:validation_end]
        probabilities={}
        for template,value in training:probabilities.setdefault(template,[]).append(value)
        predictions=[(sum(probabilities.get(template,[]))+1)/(len(probabilities.get(template,[]))+2) for template,_ in validation]
        accuracy=sum((probability>=.5)==bool(item[1]) for probability,item in zip(predictions,validation))/len(validation) if validation else 0
        brier=sum((probability-item[1])**2 for probability,item in zip(predictions,validation))/len(validation) if validation else 0
        folds.append({"fold":fold+1,"training_samples":len(training),"validation_samples":len(validation),"accuracy":accuracy,"brier_score":brier})
    model.folds=folds;valid=[item for item in folds if item["validation_samples"]]
    model.metrics={
        "accuracy":mean(item["accuracy"] for item in valid) if valid else 0,
        "brier_score":mean(item["brier_score"] for item in valid) if valid else 0,
        "folds":len(valid),
    }
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
    rank = {Timeframe.D1: 0, Timeframe.H4: 1, Timeframe.H1: 2, Timeframe.M30: 3,
            Timeframe.M15: 4, Timeframe.M5: 5, Timeframe.M1: 6}
    events = sorted((_candle(item) for values in candles_by_tf.values() for item in values),
                    key=lambda item: (item.timestamp + TIMEFRAME_MILLISECONDS[item.timeframe], rank[item.timeframe]))
    primary = {item.timestamp + TIMEFRAME_MILLISECONDS[item.timeframe]: item
               for item in (_candle(value) for value in candles_by_tf[primary_timeframe])}
    capital = config.initial_capital
    position: VirtualPosition | None = None
    pending = []
    traded_zone_keys: set[str] = set()
    last_stop_by_template: dict[str, int] = {}
    trades = []
    decisions = []
    scenarios = []
    scenario_reports = {}
    decision_reports = {}
    equity = []
    maker_rate = (config.maker_fee_percent if config.maker_fee_percent is not None else config.fee_percent) / 100
    taker_rate = (config.taker_fee_percent if config.taker_fee_percent is not None else config.fee_percent) / 100
    slip = config.slippage_percent / 100

    def price_tick(value: float) -> float:
        return round(value / config.tick_size) * config.tick_size

    def set_scenario_status(scenario_id: str, status: str):
        if scenario_id in scenario_reports:
            scenario_reports[scenario_id]["decision"] = status
        if scenario_id in decision_reports:
            decision_reports[scenario_id]["decision"] = status

    def close(candle, raw_price, reason, quantity=None):
        nonlocal capital, position
        quantity = quantity or position.quantity
        price = raw_price * (1 - slip if position.direction == "LONG" else 1 + slip)
        side = 1 if position.direction == "LONG" else -1
        gross = (price - position.entry_price) * quantity * side
        exit_rate = maker_rate if reason == "TAKE_PROFIT" else taker_rate
        # Keep all costs on the trade close: entry commission is allocated to
        # the quantity closed in this fill, then added to the exit commission.
        entry_fee = position.entry_price * quantity * maker_rate
        fees = entry_fee + price * quantity * exit_rate
        liquidation_fee = price * quantity * config.liquidation_fee_percent / 100 if reason == "LIQUIDATION" else 0
        pnl = gross - fees - liquidation_fee
        capital += pnl
        position.realized += pnl
        position.fees += fees
        position.quantity -= quantity
        if position.quantity > 1e-12:
            position.targets_hit += 1
            if (position.break_even_rule == "AFTER_TARGET"
                    and position.move_stop_to_break_even_after_target is not None
                    and position.targets_hit >= position.move_stop_to_break_even_after_target):
                position.stop = position.entry_price
            return
        trades.append({
            "id": len(trades) + 1, "direction": position.direction, "entry_time": position.entry_time,
            "exit_time": candle.timestamp + TIMEFRAME_MILLISECONDS[candle.timeframe],
            "entry_price": position.entry_price, "exit_price": price,
            "quantity": position.initial_quantity, "pnl": position.realized,
            "pnl_percent": position.realized / max(position.entry_price * position.initial_quantity / config.leverage, 1e-12) * 100,
            "fees": position.fees + liquidation_fee, "funding": position.funding, "reason": reason,
            "scenario_id": position.scenario_id, "template_id": position.template_id,
            "confidence": position.confidence,
        })
        if reason == "STOP_LOSS":
            last_stop_by_template[position.template_id] = candle.timestamp + TIMEFRAME_MILLISECONDS[candle.timeframe]
        position = None

    for candle in events:
        available_at = candle.timestamp + TIMEFRAME_MILLISECONDS[candle.timeframe]
        pipeline.process(candle)
        generated = manager.generate_top_down(candle.symbol, candle, pipeline, set(config.template_ids) or None)
        for scenario in generated:
            confidence = model.probability(scenario.setup_type, scenario.confidence) if model else scenario.confidence
            allowed = confidence >= config.confidence_threshold and (
                config.direction_mode == DirectionMode.BOTH or config.direction_mode.value == scenario.direction
            )
            decision = {
                "timestamp": available_at, "scenario_id": scenario.id, "template_id": scenario.setup_type,
                "confidence": confidence, "decision": "PENDING" if allowed else "REJECTED",
            }
            decisions.append(decision); decision_reports[scenario.id] = decision
            report_scenario = {
                "id": scenario.id, "timestamp": available_at,
                "expires_at": available_at + max(0, scenario.expires_at - scenario.created_at),
                "timeframe": scenario.timeframe, "direction": scenario.direction,
                "template_id": scenario.setup_type, "priority": scenario.priority, "confidence": confidence,
                "entry_zone_low": scenario.entry_zone_low, "entry_zone_high": scenario.entry_zone_high,
                "stop_loss_price": scenario.stop_loss_price,
                "take_profit_prices": scenario.take_profit_prices, "reasons": scenario.reasons,
                "decision": "PENDING" if allowed else "REJECTED",
            }
            scenarios.append(report_scenario); scenario_reports[scenario.id] = report_scenario
            if allowed:
                pending.append((scenario, confidence, available_at, report_scenario["expires_at"]))
        if candle.timeframe != Timeframe(primary_timeframe):
            continue
        expired = [item for item in pending if item[3] < available_at]
        for item in expired: set_scenario_status(item[0].id, "EXPIRED")
        pending = [item for item in pending if item[3] >= available_at]
        had_position = position is not None
        if position:
            interval = config.funding_interval_hours * 3_600_000
            funding_events = max(0, (available_at - position.last_funding_time) // interval)
            if funding_events:
                funding = (
                    position.entry_price * position.quantity * config.funding_percent_per_day / 100
                    * config.funding_interval_hours / 24 * funding_events
                )
                signed_funding = funding * (1 if position.direction == "LONG" else -1)
                capital -= signed_funding
                position.realized -= signed_funding
                position.funding += signed_funding
                position.last_funding_time += funding_events * interval
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
                target_index = position.targets.index(target)
                position.targets.remove(target)
                allocation = position.target_allocations.pop(target_index)
                close(candle, target, "TAKE_PROFIT", min(
                    position.quantity,
                    position.initial_quantity * allocation if position.targets else position.quantity,
                ))
            if position and position.break_even_rule == "ONE_R":
                initial_risk = abs(position.entry_price - position.stop)
                one_r = position.entry_price + initial_risk * (1 if position.direction == "LONG" else -1)
                if candle.high >= one_r if position.direction == "LONG" else candle.low <= one_r:
                    position.stop = position.entry_price
        if position is None and not had_position:
            candidates = [item for item in pending if available_at > item[2] + config.execution_latency_ms
                          and candle.low <= item[0].entry_zone_high and candle.high >= item[0].entry_zone_low]
            if candidates:
                executable = []
                rejected_ids = set()
                for candidate in candidates:
                    scenario, confidence, _, _ = candidate
                    raw_entry = min(max(candle.open, scenario.entry_zone_low), scenario.entry_zone_high)
                    entry = price_tick(raw_entry * (1 + slip if scenario.direction == "LONG" else 1 - slip))
                    template = manager.store.get(scenario.setup_type)
                    zone_key = _scenario_zone_key(scenario)
                    if template and getattr(template, "one_trade_per_zone", False) and zone_key in traded_zone_keys:
                        set_scenario_status(scenario.id, "REJECTED_ZONE_REUSE")
                        rejected_ids.add(scenario.id)
                        continue
                    last_stop = last_stop_by_template.get(scenario.setup_type)
                    cooldown = (getattr(template, "cooldown_bars_after_stop", 0) * TIMEFRAME_MILLISECONDS[Timeframe(primary_timeframe)]
                                if template else 0)
                    if last_stop is not None and available_at <= last_stop + cooldown:
                        set_scenario_status(scenario.id, "REJECTED_COOLDOWN")
                        rejected_ids.add(scenario.id)
                        continue
                    target_rr = config.smc_target_rr
                    stop, targets = _execution_plan(
                        entry, scenario, config.smc_min_stop_percent, config.tick_size,
                        [target_rr] if target_rr is not None else (template.risk_reward if template else None),
                        target_rr if target_rr is not None else (template.minimum_target_rr if template and getattr(template, "minimum_target_rr", None) is not None else config.smc_min_target_rr),
                        target_rr if target_rr is not None else (template.maximum_target_rr if template and getattr(template, "maximum_target_rr", None) is not None else config.smc_max_target_rr),
                        fixed_only=target_rr is not None,
                    )
                    if template and not _template_stop_distance_allowed(entry, stop, template):
                        set_scenario_status(scenario.id, "REJECTED_STOP_DISTANCE")
                        rejected_ids.add(scenario.id)
                    else:
                        executable.append((candidate, entry, stop, targets))
                if rejected_ids:
                    pending[:] = [item for item in pending if item[0].id not in rejected_ids]
                if executable:
                    (scenario, confidence, _, _), entry, stop, targets = max(
                        executable, key=lambda item: (item[0][0].priority, item[0][1])
                    )
                    risk_distance = abs(entry - stop)
                    kelly = max(0, 2 * confidence - 1) * config.kelly_fraction * 100
                    risk_percent = min(config.risk_per_trade_percent, kelly)
                    quantity = min(
                        capital * risk_percent / 100 / max(risk_distance, 1e-12),
                        capital * config.leverage / entry,
                        candle.volume * config.volume_participation_percent / 100,
                    )
                    quantity = floor(quantity / config.lot_size) * config.lot_size
                    if quantity >= config.minimum_order_size:
                        position = VirtualPosition(
                            scenario.direction, entry, available_at, quantity, stop,
                            targets, scenario.id, scenario.setup_type, confidence, quantity,
                            target_allocations=_target_allocations(template, len(targets)),
                            break_even_rule=getattr(template, "break_even_rule", "ONE_R") if template else "ONE_R",
                            move_stop_to_break_even_after_target=(
                                getattr(template, "move_stop_to_break_even_after_target", 1) if template else 1
                            ),
                            realized=0, fees=0, last_funding_time=available_at,
                        )
                        zone_key = _scenario_zone_key(scenario)
                        if template and getattr(template, "one_trade_per_zone", False) and zone_key:
                            traded_zone_keys.add(zone_key)
                        report_scenario = scenario_reports[scenario.id]
                        set_scenario_status(scenario.id, "EXECUTED")
                        report_scenario["entry_price"] = entry
                        report_scenario["entry_time"] = available_at
                        report_scenario["stop_loss_price"] = stop
                        report_scenario["take_profit_prices"] = targets
                    else:
                        set_scenario_status(scenario.id, "REJECTED_SIZE")
                    for item in pending:
                        if item[0].id != scenario.id: set_scenario_status(item[0].id, "SUPERSEDED")
                    pending.clear()
        unrealized = 0
        if position:
            unrealized = (candle.close - position.entry_price) * position.quantity * (1 if position.direction == "LONG" else -1)
        equity.append({"timestamp": available_at, "equity": capital + unrealized})
    for item in pending: set_scenario_status(item[0].id, "NOT_FILLED")
    if position and primary:
        last = primary[max(primary)]
        close(last, last.close, "END_OF_DATA")
        equity.append({"timestamp": max(primary), "equity": capital})
    report = _report(config, candles_by_tf[primary_timeframe], capital, trades, equity, decisions, model)
    report["scenarios"] = scenarios
    report["pattern_diagnostics"] = manager.diagnostics
    report["chart_candles"] = _chart_candles(candles_by_tf[primary_timeframe])
    report["chart_candles_by_timeframe"] = {
        timeframe: _chart_candles(candles) for timeframe, candles in candles_by_tf.items()
    }
    return report


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
            "metrics": model.metrics if isinstance(model, TemplateModel) else {},
            "folds": model.folds if isinstance(model, TemplateModel) else [],
        },
    }
