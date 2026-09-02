import pytest

from src.performance import extended_performance


def ts(value: str) -> int:
    from datetime import datetime
    return int(datetime.fromisoformat(value).timestamp() * 1000)


def test_extended_performance_reports_monthly_losses_and_curve_quality():
    equity = [
        {"timestamp": ts("2024-01-31T00:00:00+00:00"), "equity": 110},
        {"timestamp": ts("2024-02-29T00:00:00+00:00"), "equity": 99},
        {"timestamp": ts("2024-03-31T00:00:00+00:00"), "equity": 108.9},
    ]
    result = extended_performance(100, 108.9, equity)
    assert result["average_monthly_return_percent"] == pytest.approx(10 / 3)
    assert result["losing_months"] == 1
    assert result["losing_months_percent"] == pytest.approx(100 / 3)
    assert result["average_losing_month_percent"] == pytest.approx(-10)
    assert result["recovery_factor"] == pytest.approx(8.9 / 11)
    assert 0 <= result["equity_curve_r_squared"] <= 1


def test_extended_performance_handles_empty_curve():
    result = extended_performance(100, 100, [])
    assert result["average_monthly_return_percent"] == 0
    assert result["annualized_return_percent"] == 0
    assert result["losing_months"] == 0
    assert result["recovery_factor"] is None
