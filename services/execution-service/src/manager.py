from .models import *

class PositionManager:
    def update(self,p:Position,c:Candle)->list[tuple[str,dict]]:
        if p.status=="CLOSED":return []
        p.current_price=c.close;u=p.unrealized();p.max_unrealized_pnl=max(p.max_unrealized_pnl,u);p.max_unrealized_loss=min(p.max_unrealized_loss,u);events=[]
        stop_hit=p.stop_loss_price is not None and (c.low<=p.stop_loss_price if p.direction=="LONG" else c.high>=p.stop_loss_price)
        if stop_hit:return [("close",{"price":p.stop_loss_price,"reason":"STOP_LOSS","quantity":p.quantity})]
        targets=sorted(p.take_profit_prices,reverse=p.direction=="SHORT")
        reached=[x for x in targets if (c.high>=x if p.direction=="LONG" else c.low<=x)]
        if reached:
            target=reached[0]
            target_index=p.take_profit_prices.index(target)
            if p.break_even_rule=="AFTER_TARGET" and len(targets)>1:
                p.take_profit_prices.remove(target)
                if p.target_allocations:p.target_allocations.pop(target_index)
                p.targets_hit+=1
                p.stop_loss_price=p.entry_price;p.protected=True;p.status="PROTECTED"
                events.append(("updated",{"stop_loss_price":p.entry_price,"status":"PROTECTED"}))
                return events
            if len(targets)>1 and p.quantity>p.initial_quantity*.25:
                allocation=(p.target_allocations[target_index] if len(p.target_allocations)==len(p.take_profit_prices)
                            else .5)
                quantity=min(p.quantity,p.initial_quantity*allocation)
                events.append(("partial",{"price":target,"reason":"TAKE_PROFIT","quantity":quantity}));p.take_profit_prices.remove(target)
                if p.target_allocations:p.target_allocations.pop(target_index)
                p.targets_hit+=1
            else:return [("close",{"price":target,"reason":"TAKE_PROFIT","quantity":p.quantity})]
        initial_risk=abs(p.entry_price-(p.stop_loss_price or p.entry_price))
        one_r=p.entry_price+initial_risk*(1 if p.direction=="LONG" else -1)
        target_based_protection=(p.break_even_rule=="AFTER_TARGET"
                                 and p.move_stop_to_break_even_after_target is not None
                                 and p.targets_hit>=p.move_stop_to_break_even_after_target)
        one_r_protection=(p.break_even_rule=="ONE_R" and (
            c.high>=one_r if p.direction=="LONG" else c.low<=one_r
        ))
        if not p.protected and initial_risk>0 and (target_based_protection or one_r_protection):
            p.stop_loss_price=p.entry_price;p.protected=True;p.status="PROTECTED";events.append(("updated",{"stop_loss_price":p.entry_price,"status":"PROTECTED"}))
        return events
