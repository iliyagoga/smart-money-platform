from __future__ import annotations
from collections import defaultdict
from .models import *


def atr(candles:list[Candle], period:int=14)->float:
    if len(candles)<2: return max(candles[-1].high-candles[-1].low,1e-12) if candles else 0
    values=[]
    for previous,current in zip(candles[-period-1:-1],candles[-period:]):
        values.append(max(current.high-current.low,abs(current.high-previous.close),abs(current.low-previous.close)))
    return sum(values)/len(values)


class SwingEngine:
    def __init__(self,lookback:int=5,min_distance_atr:float=.3): self.lookback=lookback; self.min_distance_atr=min_distance_atr
    def detect(self,candles:list[Candle],existing:list[Swing])->list[Swing]:
        n=self.lookback
        if len(candles)<2*n+1:return []
        center=candles[-n-1]; left=candles[-2*n-1:-n-1]; right=candles[-n:]
        candidates=[]
        if center.high>max(x.high for x in left) and center.high>max(x.high for x in right): candidates.append((SwingType.HIGH,center.high))
        if center.low<min(x.low for x in left) and center.low<min(x.low for x in right): candidates.append((SwingType.LOW,center.low))
        result=[]; current_atr=atr(candles)
        for kind,price in candidates:
            previous=next((x for x in reversed(existing) if x.type==kind),None)
            if previous and abs(price-previous.price)<self.min_distance_atr*current_atr: continue
            item=Swing(symbol=center.symbol,timeframe=center.timeframe,timestamp=center.timestamp,price=price,type=kind,lookback=n,
                       strength=sum(1 for x in left+right if (price>x.high if kind==SwingType.HIGH else price<x.low)))
            if existing: item.prev_swing_id=existing[-1].id; existing[-1].next_swing_id=item.id
            result.append(item)
        return result


class TrendEngine:
    def calculate(self,swings:list[Swing],timestamp:int)->Trend|None:
        highs=[x for x in swings if x.type==SwingType.HIGH]; lows=[x for x in swings if x.type==SwingType.LOW]
        if len(highs)<2 or len(lows)<2:return None
        up=highs[-1].price>highs[-2].price and lows[-1].price>lows[-2].price
        down=highs[-1].price<highs[-2].price and lows[-1].price<lows[-2].price
        direction=TrendDirection.UP if up else TrendDirection.DOWN if down else TrendDirection.SIDEWAYS
        movement=(abs(highs[-1].price-highs[-2].price)+abs(lows[-1].price-lows[-2].price))/max(highs[-2].price+lows[-2].price,1e-12)
        return Trend(symbol=swings[-1].symbol,timeframe=swings[-1].timeframe,direction=direction,strength=min(1,movement*50),timestamp=timestamp)


class StructureEngine:
    def detect(self,candle:Candle,swings:list[Swing],trend:Trend|None,seen:set[tuple])->list[StructureChange]:
        if not trend:return []
        highs=[x for x in swings if x.type==SwingType.HIGH]; lows=[x for x in swings if x.type==SwingType.LOW]; found=[]
        def add(kind,direction,level):
            key=(kind,direction,level)
            if key not in seen: seen.add(key); found.append(StructureChange(symbol=candle.symbol,timeframe=candle.timeframe,type=kind,direction=direction,break_level_price=level,timestamp=candle.timestamp))
        if trend.direction==TrendDirection.UP and highs and candle.close>highs[-1].price:add("BOS",Direction.BULLISH,highs[-1].price)
        if trend.direction==TrendDirection.DOWN and lows and candle.close<lows[-1].price:add("BOS",Direction.BEARISH,lows[-1].price)
        if trend.direction==TrendDirection.UP and lows and candle.close<lows[-1].price:add("CHOCH",Direction.BEARISH,lows[-1].price)
        if trend.direction==TrendDirection.DOWN and highs and candle.close>highs[-1].price:add("CHOCH",Direction.BULLISH,highs[-1].price)
        if trend.direction==TrendDirection.UP and len(lows)>1 and candle.close<lows[-2].price:add("MSS",Direction.BEARISH,lows[-2].price)
        if trend.direction==TrendDirection.DOWN and len(highs)>1 and candle.close>highs[-2].price:add("MSS",Direction.BULLISH,highs[-2].price)
        return found


class FVGEngine:
    def update(self,candles:list[Candle],active:list[FVG])->tuple[list[FVG],list[FVG]]:
        candle=candles[-1]; changed=[]
        for item in active:
            if item.is_filled:continue
            if candle.high>=item.zone_low and candle.low<=item.zone_high:
                overlap=max(0,min(candle.high,item.zone_high)-max(candle.low,item.zone_low)); item.fill_percent=min(1,overlap/(item.zone_high-item.zone_low));
                if (item.type==Direction.BULLISH and candle.close<=item.zone_low) or (item.type==Direction.BEARISH and candle.close>=item.zone_high):item.fill_percent=1;item.is_filled=True
                changed.append(item)
        created=[]
        if len(candles)>=3:
            first,last=candles[-3],candles[-1]
            if first.high<last.low:created.append(FVG(symbol=last.symbol,timeframe=last.timeframe,type=Direction.BULLISH,zone_low=first.high,zone_high=last.low,created_at=last.timestamp))
            elif first.low>last.high:created.append(FVG(symbol=last.symbol,timeframe=last.timeframe,type=Direction.BEARISH,zone_low=last.high,zone_high=first.low,created_at=last.timestamp))
        return created,changed


class OrderBlockEngine:
    def __init__(self,impulse_bars:int=3,threshold_atr:float=1.5):self.bars=impulse_bars;self.threshold=threshold_atr
    def update(self,candles:list[Candle],active:list[OrderBlock])->tuple[list[OrderBlock],list[OrderBlock]]:
        candle=candles[-1];changed=[]
        for item in active:
            if item.is_broken:continue
            touches=candle.high>=item.zone_low and candle.low<=item.zone_high
            broken=(item.type==Direction.BULLISH and candle.close<item.zone_low) or (item.type==Direction.BEARISH and candle.close>item.zone_high)
            if broken:item.is_broken=True;item.is_active=False;changed.append(item)
            elif touches:
                item.is_active=True;item.retest_count+=1
                penetration=(item.zone_high-candle.low if item.type==Direction.BULLISH else candle.high-item.zone_low)/(item.zone_high-item.zone_low)
                item.mitigation_depth=max(item.mitigation_depth,min(1,max(0,penetration)));changed.append(item)
        created=[]
        if len(candles)>=self.bars+1:
            base=candles[-self.bars-1]; move=candle.close-candles[-self.bars].open; limit=self.threshold*atr(candles)
            if move>limit and base.close<base.open:created.append(OrderBlock(symbol=candle.symbol,timeframe=candle.timeframe,type=Direction.BULLISH,zone_low=base.low,zone_high=base.high,created_at=base.timestamp))
            elif move<-limit and base.close>base.open:created.append(OrderBlock(symbol=candle.symbol,timeframe=candle.timeframe,type=Direction.BEARISH,zone_low=base.low,zone_high=base.high,created_at=base.timestamp))
        return created,changed


class LiquidityEngine:
    def __init__(self,offset_atr:float=.5,equal_tolerance_atr:float=.15):self.offset=offset_atr;self.tolerance=equal_tolerance_atr
    def create(self,swing:Swing,all_swings:list[Swing],current_atr:float)->LiquidityZone:
        peers=[x for x in all_swings[:-1] if x.type==swing.type and abs(x.price-swing.price)<=self.tolerance*current_atr]
        strong=.9 if peers else .5; level=(swing.price+self.offset*current_atr if swing.type==SwingType.HIGH else swing.price-self.offset*current_atr)
        return LiquidityZone(symbol=swing.symbol,timeframe=swing.timeframe,type="BUY_STOP" if swing.type==SwingType.HIGH else "SELL_STOP",price_level=level,strength=strong,created_at=swing.timestamp)
    def sweep(self,candle:Candle,zones:list[LiquidityZone])->list[LiquidityZone]:
        changed=[]
        for z in zones:
            if not z.swept and ((z.type=="BUY_STOP" and candle.high>=z.price_level and candle.close<z.price_level) or (z.type=="SELL_STOP" and candle.low<=z.price_level and candle.close>z.price_level)):
                z.swept=True;z.swept_at=candle.timestamp;changed.append(z)
        return changed


class AnalysisPipeline:
    def __init__(self,lookback=5):
        self.candles=defaultdict(list);self.swings=defaultdict(list);self.trends={};self.changes=defaultdict(list);self.seen=defaultdict(set)
        self.obs=defaultdict(list);self.fvgs=defaultdict(list);self.liquidity=defaultdict(list)
        self.swing_engine=SwingEngine(lookback);self.trend_engine=TrendEngine();self.structure_engine=StructureEngine();self.ob_engine=OrderBlockEngine();self.fvg_engine=FVGEngine();self.liquidity_engine=LiquidityEngine()
    def process(self,candle:Candle)->AnalysisResult:
        key=(candle.symbol,candle.timeframe);bars=self.candles[key]
        if bars and candle.timestamp<=bars[-1].timestamp:
            bars[:]=[x for x in bars if x.timestamp!=candle.timestamp]
        bars.append(candle);bars.sort(key=lambda x:x.timestamp);del bars[:-500]
        new_swings=self.swing_engine.detect(bars,self.swings[key]);self.swings[key].extend(new_swings)
        trend=self.trend_engine.calculate(self.swings[key],candle.timestamp);self.trends[key]=trend
        changes=self.structure_engine.detect(candle,self.swings[key],trend,self.seen[key]);self.changes[key].extend(changes)
        new_obs,changed_obs=self.ob_engine.update(bars,self.obs[key]);self.obs[key].extend(new_obs)
        new_fvgs,changed_fvgs=self.fvg_engine.update(bars,self.fvgs[key]);self.fvgs[key].extend(new_fvgs)
        new_liq=[self.liquidity_engine.create(x,self.swings[key],atr(bars)) for x in new_swings];self.liquidity[key].extend(new_liq);changed_liq=self.liquidity_engine.sweep(candle,self.liquidity[key])
        # Scenario generation only needs active POIs plus a bounded recent history of
        # structure/sweeps. Without pruning every new candle scanned the full market
        # history, which made long replays progressively slower.
        self.swings[key][:]=self.swings[key][-500:]
        self.changes[key][:]=self.changes[key][-500:]
        self.obs[key][:]=[item for item in self.obs[key] if not item.is_broken][-500:]
        self.fvgs[key][:]=[item for item in self.fvgs[key] if not item.is_filled][-500:]
        active_liquidity=[item for item in self.liquidity[key] if not item.swept]
        swept_liquidity=[item for item in self.liquidity[key] if item.swept][-100:]
        self.liquidity[key][:]=(active_liquidity[-500:]+swept_liquidity)
        return AnalysisResult(swings=new_swings,trend=trend,changes=changes,order_blocks=new_obs+changed_obs,fvgs=new_fvgs+changed_fvgs,liquidity_zones=new_liq+changed_liq)
