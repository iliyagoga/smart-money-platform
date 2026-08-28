from collections import defaultdict
from types import SimpleNamespace

from src.algorithm import AlgorithmConfig, AlgorithmEngine, adx
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

def test_precomputed_external_pattern_is_released_only_after_confirmation():
    patterns={"M1":([{"id":"external-swing","timestamp":1,"available_at":3,"price":11,"type":"HIGH"}],[],[],[],[])}
    pipeline=AnalysisPipeline(lookback=1,use_external=False,external_patterns=patterns)
    assert pipeline.process(candle(1,10,11,9,10)).swings==[]
    assert pipeline.process(candle(2,10,11,9,10)).swings==[]
    result=pipeline.process(candle(3,10,11,9,10))
    assert [item.id for item in result.swings]==["external-swing"]
    assert any(item.id=="external-swing" for item in pipeline.swings[("BTC-USDT",Timeframe.M1)])

def test_algorithm_uses_m15_trend_and_nearest_higher_timeframe_ob():
    config=AlgorithmConfig(id="DEMO",name="Demo",execution_timeframes=["M1"],
        require_ob_caused_bos=False,require_liquidity_sweep_before_ob=False,
        require_ob_in_ote_zone=False,minimum_ob_strength=0,minimum_impulse_atr=0,
        minimum_volume_ratio=0,minimum_adx=0,minimum_rr=1.5)
    store=SimpleNamespace(enabled=lambda selected:[config])
    engine=AlgorithmEngine(store)
    current=candle(10,100,101,99,100)
    m1=("BTC-USDT",Timeframe.M1);m15=("BTC-USDT",Timeframe.M15);h1=("BTC-USDT",Timeframe.H1)
    source_h1=Candle(symbol="BTC-USDT",timeframe="H1",timestamp=9,open=100,high=101,low=99,close=100,volume=1)
    pipeline=SimpleNamespace(
        candles=defaultdict(list,{m1:[current],h1:[source_h1]}),
        trends={m1:Trend(symbol="BTC-USDT",timeframe="M1",direction="DOWN",strength=1,timestamp=10),
                m15:Trend(symbol="BTC-USDT",timeframe="M15",direction="UP",strength=1,timestamp=10)},
        obs=defaultdict(list,{m1:[OrderBlock(id="m1-ob",symbol="BTC-USDT",timeframe="M1",type="BULLISH",zone_low=94,zone_high=96,created_at=1)],
                                  h1:[OrderBlock(id="h1-ob",symbol="BTC-USDT",timeframe="H1",type="BULLISH",zone_low=97,zone_high=98,created_at=1)]}),
        changes=defaultdict(list),swings=defaultdict(list),fvgs=defaultdict(list),
        liquidity=defaultdict(list,{h1:[LiquidityZone(id="h1-target",symbol="BTC-USDT",timeframe="H1",type="BUY_STOP",price_level=102,created_at=1)]}),
    )
    signals=engine.generate(current,pipeline)
    assert len(signals)==1
    assert signals[0].direction=="LONG"
    assert signals[0].timeframe==Timeframe.H1
    assert signals[0].zone_id=="h1-ob"
