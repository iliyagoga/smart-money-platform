import pytest

from backtest_core.elliott import Pattern, Pivot
from backtest_core.models import BacktestConfig
from src.elliott_live import _entry_plan, normalize_config


def test_normalize_config_accepts_ui_camel_case():
    assert normalize_config({
        "riskPerTradePercent": 1,
        "elliott": {"entryTimeframe": "M15", "breakEvenAtOneR": True},
    }) == {
        "risk_per_trade_percent": 1,
        "elliott": {"entry_timeframe": "M15", "break_even_at_one_r": True},
    }


def pattern():
    p0=Pivot(0,0,60_000,90,"LOW",1);p1=Pivot(1,60_000,120_000,100,"HIGH",1)
    p2=Pivot(2,120_000,180_000,95,"LOW",1)
    return Pattern("pattern","LONG",{"P0":p0,"P1":p1,"P2":p2},"WAVE3_POTENTIAL",
                   {"choch_level":100,"choch_close":104},signal_time=120_000)


def candles():
    return [{"timestamp":index*60_000,"open":100,"high":110,"low":98,"close":105,"volume":1000}
            for index in range(4)]


@pytest.mark.parametrize(("entry_model","order_type"),[
    ("CHOCH_MARKET","MARKET"),("CHOCH_RETRACE","LIMIT"),
    ("WAVE1_BREAK_RETRACE","LIMIT"),("WAVE1_BREAK_MARKET","MARKET"),
    ("WAVE1_BREAK_STOP","STOP"),
])
def test_live_entry_plans_use_model_specific_backtest_rules(entry_model,order_type):
    config=BacktestConfig(elliott={"entry_timeframe":"M1","structure_timeframe":"H1",
                                   "macro_timeframe":"H4","entry_model":entry_model})
    plan=_entry_plan(pattern(),config,candles(),[],240_000)
    assert plan is not None and plan["entry_type"]==order_type
    assert plan["stop"]<plan["entry"]<plan["targets"][0]


def test_wave1_break_retrace_waits_for_a_post_signal_break_candle():
    series=candles()[:2]
    assert _entry_plan(pattern(),config("WAVE1_BREAK_RETRACE"),series,[],120_000) is None


def test_live_entry_plan_honours_direction_latency_and_expiry():
    item=pattern();series=candles()
    short_only=BacktestConfig(direction_mode="SHORT",elliott={"entry_timeframe":"M1","structure_timeframe":"H1",
                                                               "macro_timeframe":"H4","entry_model":"CHOCH_MARKET"})
    delayed=BacktestConfig(execution_latency_ms=200_000,elliott={"entry_timeframe":"M1","structure_timeframe":"H1",
                                                                 "macro_timeframe":"H4","entry_model":"CHOCH_MARKET"})
    expired=BacktestConfig(elliott={"entry_timeframe":"M1","structure_timeframe":"H1","macro_timeframe":"H4",
                                    "entry_model":"CHOCH_MARKET","entry_expiry_bars":1})
    assert _entry_plan(item,short_only,series,[],240_000) is None
    assert _entry_plan(item,delayed,series,[],240_000) is None
    assert _entry_plan(item,expired,series,[],300_000) is None


def config(entry_model, **elliott):
    return BacktestConfig(elliott={"entry_timeframe":"M1","structure_timeframe":"H1",
      "macro_timeframe":"H4","entry_model":entry_model,**elliott})


def test_confirmation_and_retracement_entry_models_are_executable():
    series=candles()
    retest=_entry_plan(pattern(),config("WAVE1_BREAK_RETEST_CONFIRM"),series,[],240_000)
    displacement=_entry_plan(pattern(),config("DISPLACEMENT_RETRACE",displacement_min_body_ratio=.4),series,[],240_000)
    swept=[*series[:-1],{**series[-1],"low":94}]
    sweep=_entry_plan(pattern(),config("P2_LIQUIDITY_SWEEP",sweep_min_wick_ratio=.3),swept,[],240_000)
    assert retest and retest["entry_type"]=="MARKET"
    assert displacement and displacement["entry_type"]=="LIMIT"
    assert sweep and sweep["entry_type"]=="STOP"


def test_micro_wave_and_trendline_entry_models_are_executable():
    micro=[Pivot(3,130_000,140_000,96,"LOW",1),Pivot(4,150_000,160_000,101,"HIGH",1),
           Pivot(5,170_000,180_000,98,"LOW",1)]
    micro_plan=_entry_plan(pattern(),config("MICRO_WAVE3"),candles(),micro,240_000)
    trend_pivots=[Pivot(1,70_000,130_000,101,"HIGH",1),Pivot(2,130_000,190_000,102,"HIGH",1)]
    series=[*candles()];series[-2]={**series[-2],"close":101}
    trend=_entry_plan(pattern(),config("WAVE2_TRENDLINE_BREAK"),series,trend_pivots,240_000)
    assert micro_plan and micro_plan["entry_type"]=="MARKET"
    assert trend and trend["entry_type"]=="MARKET"


def test_indicator_expansion_entry_models_are_executable(monkeypatch):
    import backtest_core.elliott as replay
    series=candles()
    monkeypatch.setattr(replay,"_adx",lambda values,period:([0,1,2,3],[0,1,2,4],[0,0,0,0]))
    adx=_entry_plan(pattern(),config("ADX_ACCELERATION"),series,[],240_000)
    monkeypatch.setattr(replay,"_true_ranges",lambda values:[1,1,1,4])
    monkeypatch.setattr(replay,"_rolling",lambda values,period:([1,1,1,3] if period==14 else [2,2,2,2]))
    volatility=_entry_plan(pattern(),config("VOLATILITY_EXPANSION"),series,[],240_000)
    assert adx and adx["entry_type"]=="MARKET"
    assert volatility and volatility["entry_type"]=="MARKET"


def test_volume_expansion_entry_model_is_executable():
    series=[{"timestamp":index*60_000,"open":100,"high":110,"low":98,"close":105,
             "volume":1000 if index==20 else 100} for index in range(21)]
    plan=_entry_plan(pattern(),config("VOLUME_EXPANSION",entry_expiry_bars=100,
      volume_expansion_min_body_ratio=.4),series,[],1_260_000)
    assert plan and plan["entry_type"]=="STOP"
