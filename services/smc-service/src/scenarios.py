from time import time
from .models import *

class ScenarioManager:
    def __init__(self):self.items:dict[str,Scenario]={}
    def generate(self,symbol:str,timeframe:Timeframe,obs:list[OrderBlock],fvgs:list[FVG],liquidity:list[LiquidityZone])->list[Scenario]:
        created=[]
        for ob in [x for x in obs if not x.is_broken]:
            overlaps=[x for x in fvgs if not x.is_filled and x.type==ob.type and x.zone_low<=ob.zone_high and x.zone_high>=ob.zone_low]
            if not overlaps:continue
            direction="LONG" if ob.type==Direction.BULLISH else "SHORT"; width=ob.zone_high-ob.zone_low
            target=next((z.price_level for z in liquidity if not z.swept and ((direction=="LONG" and z.type=="BUY_STOP") or (direction=="SHORT" and z.type=="SELL_STOP"))),ob.zone_high+3*width if direction=="LONG" else ob.zone_low-3*width)
            confidence=min(.9,.55+.1*len(overlaps)+.05*(1-ob.mitigation_depth))
            key=f"{ob.id}:{overlaps[0].id}"
            if key in self.items:continue
            scenario=Scenario(id=str(__import__('uuid').uuid5(__import__('uuid').NAMESPACE_URL,key)),symbol=symbol,timeframe=timeframe,direction=direction,
              setup_type="OB_FVG_CONFLUENCE",confidence=confidence,entry_zone_low=max(ob.zone_low,overlaps[0].zone_low),entry_zone_high=min(ob.zone_high,overlaps[0].zone_high),
              stop_loss_price=ob.zone_low-.1*width if direction=="LONG" else ob.zone_high+.1*width,take_profit_prices=[target],
              reasons=["Order Block overlaps Fair Value Gap"],objects_used=[{"type":"OB","id":ob.id},{"type":"FVG","id":overlaps[0].id}],expires_at=int(time()*1000)+24*3600*1000)
            self.items[key]=scenario;created.append(scenario)
        return created
    def list(self,symbol:str|None=None,status:str|None=None):
        now=int(time()*1000)
        for x in self.items.values():
            if x.status=="ACTIVE" and x.expires_at<now:x.status="EXPIRED"
        return [x for x in self.items.values() if (not symbol or x.symbol==symbol.upper()) and (not status or x.status==status)]
