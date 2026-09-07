from src.elliott_live import normalize_config


def test_normalize_config_accepts_ui_camel_case():
    assert normalize_config({
        "riskPerTradePercent": 1,
        "elliott": {"entryTimeframe": "M15", "breakEvenAtOneR": True},
    }) == {
        "risk_per_trade_percent": 1,
        "elliott": {"entry_timeframe": "M15", "break_even_at_one_r": True},
    }
