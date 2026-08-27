from src.algorithm import AlgorithmConfig, adx
from src.engines import AnalysisPipeline,FVGEngine,SwingEngine
from src.models import *

def candle(ts,o,h,l,c):return Candle(symbol="BTC-USDT",timeframe="M1",timestamp=ts,open=o,high=h,low=l,close=c,volume=1)

def test_bullish_fvg():
    bars=[candle(1,10,11,9,10),candle(2,11,14,10,13),candle(3,15,16,14,15)]
    created,_=FVGEngine().update(bars,[])
    assert len(created)==1 and created[0].type==Direction.BULLISH
    assert created[0].zone_low==11 and created[0].zone_high==14

def test_confirmed_swing_high():
    bars=[candle(i,10,h,9,10) for i,h in enumerate([10,11,15,12,11])]
    found=SwingEngine(lookback=2).detect(bars,[])
    assert len(found)==1 and found[0].type==SwingType.HIGH and found[0].price==15

def test_pipeline_deduplicates_replaced_candle():
    pipeline=AnalysisPipeline(lookback=1)
    pipeline.process(candle(1,10,11,9,10));pipeline.process(candle(2,10,12,9,11));pipeline.process(candle(2,10,13,9,12))
    assert len(pipeline.candles[("BTC-USDT",Timeframe.M1)])==2

def test_algorithm_config_contains_parameters_not_scenario_relations():
    config=AlgorithmConfig(id="DEMO",name="Demo")
    assert config.entry_source=="ORDER_BLOCK"
    assert "relations" not in config.model_dump()
    assert "event_sequence" not in config.model_dump()

def test_adx_needs_enough_closed_bars():
    assert adx([candle(i,10,11,9,10) for i in range(10)],14)==0
