from src.app import analyze_trades


def test_analyze_trades_calculates_metrics_and_entry_quality():
    result = analyze_trades([
        {"position_id": "win", "symbol": "BTC-USDT", "direction": "LONG", "entry_price": 100,
         "exit_price": 110, "pnl": 10, "pnl_percent": 10, "r_multiple": 2, "max_unrealized_pnl": 20,
         "duration_seconds": 120, "reason": "TAKE_PROFIT", "closed_at": 1},
        {"position_id": "loss", "symbol": "BTC-USDT", "direction": "LONG", "entry_price": 100,
         "exit_price": 95, "pnl": -5, "pnl_percent": -5, "r_multiple": -1, "max_unrealized_pnl": 0,
         "duration_seconds": 60, "reason": "STOP_LOSS", "closed_at": 2},
    ])

    assert result["metrics"] == {
        "total_trades": 2, "net_pnl": 5.0, "win_rate": 50.0, "profit_factor": 2.0,
        "expectancy": 2.5, "payoff_ratio": 2.0, "average_r": 0.5, "average_duration_seconds": 90.0,
    }
    assert result["entry_points"][0]["capture_rate"] == 50.0
    assert result["entry_points"][1]["capture_rate"] is None


def test_analyze_trades_handles_empty_and_legacy_records():
    assert analyze_trades([])["metrics"]["total_trades"] == 0
    result = analyze_trades([{"position_id": "legacy", "pnl": 1}])
    assert result["metrics"]["average_r"] is None
    assert result["entry_points"][0]["pnl_percent"] == 0
