from datetime import datetime, timezone


def extended_performance(initial_capital: float, final_capital: float, equity: list[dict]) -> dict:
    """Calendar returns and simple equity-curve quality metrics."""
    points = sorted(equity, key=lambda item: item["timestamp"])
    month_ends: dict[tuple[int, int], float] = {}
    for point in points:
        date = datetime.fromtimestamp(point["timestamp"] / 1000, tz=timezone.utc)
        month_ends[(date.year, date.month)] = float(point["equity"])

    previous = float(initial_capital)
    monthly_returns = []
    for value in month_ends.values():
        monthly_returns.append((value / previous - 1) * 100 if previous else 0.0)
        previous = value
    losing_months = [value for value in monthly_returns if value < 0]

    duration_years = 0.0
    if len(points) > 1:
        duration_years = (points[-1]["timestamp"] - points[0]["timestamp"]) / (365.2425 * 86_400_000)
    annualized = 0.0
    if initial_capital > 0 and final_capital >= 0:
        annualized = ((final_capital / initial_capital) ** (1 / duration_years) - 1) * 100 \
            if duration_years >= 1 / 12 else (final_capital / initial_capital - 1) * 100

    peak = float(initial_capital)
    max_drawdown_value = 0.0
    for point in points:
        value = float(point.get("intrabar_min_equity", point["equity"]))
        peak = max(peak, float(point["equity"]))
        max_drawdown_value = max(max_drawdown_value, peak - value)
    net_profit = final_capital - initial_capital
    recovery_factor = net_profit / max_drawdown_value if max_drawdown_value else None

    r_squared = 0.0
    if len(points) > 1:
        xs = [(point["timestamp"] - points[0]["timestamp"]) / 86_400_000 for point in points]
        ys = [float(point["equity"]) for point in points]
        x_mean, y_mean = sum(xs) / len(xs), sum(ys) / len(ys)
        x_variance = sum((value - x_mean) ** 2 for value in xs)
        if x_variance:
            slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / x_variance
            predicted = [y_mean + slope * (x - x_mean) for x in xs]
            total_variance = sum((y - y_mean) ** 2 for y in ys)
            if total_variance:
                residual = sum((y - estimate) ** 2 for y, estimate in zip(ys, predicted))
                r_squared = max(0.0, min(1.0, 1 - residual / total_variance))

    return {
        "average_monthly_return_percent": sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0.0,
        "annualized_return_percent": annualized,
        "losing_months": len(losing_months),
        "losing_months_percent": len(losing_months) / len(monthly_returns) * 100 if monthly_returns else 0.0,
        "average_losing_month_percent": sum(losing_months) / len(losing_months) if losing_months else 0.0,
        "equity_curve_r_squared": r_squared,
        "recovery_factor": recovery_factor,
    }
