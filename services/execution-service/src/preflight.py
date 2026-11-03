"""Lot feasibility at today's price; this does not predict a future entry/stop."""
from decimal import Decimal, ROUND_CEILING


def value(config, camel, snake, default):
    return config.get(camel, config.get(snake, default))


def positive(raw, name):
    number = Decimal(str(raw))
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def asset_preflight(symbol, config, spec, risk, available):
    lot = positive(spec["lot_size"], "lot size")
    contract = positive(spec["contract_value"], "contract value")
    minimum = max(positive(spec["minimum_order_size"], "minimum order size"),
                  positive(risk.get("min_position_size", .0001), "risk minimum size"))
    tick = positive(spec["tick_size"], "tick size")
    price = positive(spec["price"], "current price")
    capital = positive(value(config, "currentCapital", "current_capital", 0), "capital")
    allocation = positive(value(config, "portfolioAllocationPercent", "portfolio_allocation_percent", 100), "allocation")
    allocated = value(config, "portfolioCapitalMode", "portfolio_capital_mode", "SEQUENTIAL") == "ALLOCATED"
    # Match decision-service: cap capital by account availability before allocation.
    budget = min(capital, positive(available, "available balance")) * (1 if allocated else allocation / 100)
    elliott = config.get("elliott", {})
    leverage = min(int(config.get("leverage", 1)), int(risk.get("leverage", 1))) if value(elliott, "useMargin", "use_margin", False) else 1
    leverage = positive(leverage, "leverage")
    risk_limit = positive(risk.get("max_risk_per_trade_percent", 1), "risk limit")
    requested = Decimal(str(value(config, "riskPerTradePercent", "risk_per_trade_percent", risk_limit)))
    if not requested.is_finite() or requested < 0:
        raise ValueError("risk percent must be finite and not negative")
    effective_risk = min(requested, risk_limit) if requested else risk_limit
    allocations = [Decimal(1)]
    count = int(value(elliott, "takeProfitCount", "take_profit_count", 2))
    action = value(elliott, "firstTakeAction", "first_take_action", "PARTIAL_CLOSE")
    # MOVE_TO_BREAK_EVEN intentionally closes no volume at the first target.
    one_r = value(elliott, "breakEvenAtOneR", "break_even_at_one_r", False)
    if count > 1 and (action != "MOVE_TO_BREAK_EVEN" or one_r):
        allocations = [Decimal(str(x)) for x in value(elliott, "takeProfitAllocations", "take_profit_allocations", [.5, .5])]
        if len(allocations) != count or any(not x.is_finite() or x <= 0 for x in allocations) or abs(sum(allocations) - 1) > Decimal(".000001"):
            raise ValueError("Invalid take-profit allocations")
    # Intermediate exits floor to lots; the final exit receives the remainder.
    # Elliott currently supports at most two targets.
    if len(allocations) > 2:
        raise ValueError("Only one or two Elliott targets are supported")
    exit_lots = (positive(spec["minimum_order_size"], "minimum order size") / lot).to_integral_value(rounding=ROUND_CEILING)
    lots = max((minimum / lot).to_integral_value(rounding=ROUND_CEILING), exit_lots)
    if len(allocations) == 2:
        lots = max(lots, (exit_lots / allocations[0]).to_integral_value(rounding=ROUND_CEILING),
                   ((exit_lots - 1) // (1 - allocations[0])) + 1)
    quantity = lots * lot
    first = ((quantity * allocations[0]) // lot) * lot if len(allocations) == 2 else quantity
    takes = [first, quantity - first] if len(allocations) == 2 else [quantity]
    margin = quantity * price / leverage
    risk_budget = budget * effective_risk / 100
    max_stop = risk_budget / quantity
    errors = []
    if margin > budget:
        errors.append("Недостаточно бюджета для минимальной позиции и всех тейков")
    if max_stop < tick:
        errors.append("Допустимый риск не покрывает даже один шаг цены до стопа")
    return {"symbol": symbol, "valid": not errors, "errors": errors,
            "budget": float(budget), "price": float(price), "lot_size": float(lot),
            "contract_value": float(contract), "leverage": float(leverage),
            "minimum_quantity": float(quantity), "minimum_contracts": float(quantity / contract),
            "take_quantities": [float(x) for x in takes], "required_margin": float(margin),
            "risk_percent": float(effective_risk), "risk_budget": float(risk_budget),
            "max_stop_distance": float(max_stop), "max_stop_percent": float(max_stop / price * 100)}
