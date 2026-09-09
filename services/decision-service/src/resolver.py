from .models import *

class ConflictResolver:
    def __init__(self,threshold=.6,min_delta=.1):self.threshold=threshold;self.min_delta=min_delta
    def select(self,scenarios:list[Scenario])->tuple[Scenario|None,dict[str,str]]:
        active=[x for x in scenarios if x.status=="ACTIVE" and x.confidence>=self.threshold]
        rejected={x.id:"Confidence below threshold" for x in scenarios if x.status=="ACTIVE" and x.confidence<self.threshold}
        if not active:return None,rejected
        longs=sorted((x for x in active if x.direction=="LONG"),key=lambda x:x.confidence,reverse=True)
        shorts=sorted((x for x in active if x.direction=="SHORT"),key=lambda x:x.confidence,reverse=True)
        if longs and shorts and abs(longs[0].confidence-shorts[0].confidence)<=self.min_delta:
            rejected.update({longs[0].id:"Direction conflict is inconclusive",shorts[0].id:"Direction conflict is inconclusive"});return None,rejected
        best=max(active,key=lambda x:x.confidence)
        rejected.update({x.id:"A stronger scenario was selected" for x in active if x.id!=best.id})
        return best,rejected
    def signal(self,s:Scenario)->TradeSignal:
        return TradeSignal(scenario_id=s.id,symbol=s.symbol,direction=s.direction,entry_price=(s.entry_zone_low+s.entry_zone_high)/2,
          entry_type=s.entry_type,
          stop_loss_price=s.stop_loss_price,take_profit_prices=s.take_profit_prices,confidence=s.confidence,
          target_allocations=s.target_allocations,
          target_rrs=s.target_rrs,
          break_even_rule=s.break_even_rule,
          move_stop_to_break_even_after_target=s.move_stop_to_break_even_after_target,
          one_trade_per_zone=s.one_trade_per_zone,cooldown_bars_after_stop=s.cooldown_bars_after_stop,
          deduplication_key=s.deduplication_key,expires_at=s.expires_at)
