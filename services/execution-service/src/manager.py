from math import ceil,floor

from .models import *

def fee_adjusted_break_even(p:Position)->float:
    entry_fee=p.entry_fee_percent/100;taker=p.taker_fee_percent/100;slip=p.slippage_percent/100
    funding_per_unit=p.funding/max(p.quantity,1e-12)
    if p.direction=="LONG":
        executed=(p.entry_price*(1+entry_fee)+funding_per_unit)/max(1-taker,1e-12)
        return ceil(executed/max(1-slip,1e-12)/p.tick_size)*p.tick_size
    executed=(p.entry_price*(1-entry_fee)-funding_per_unit)/(1+taker)
    return floor(executed/(1+slip)/p.tick_size)*p.tick_size

def liquidation_price(p:Position)->float:
    quantity=p.quantity;entry=p.entry_price;margin=entry*quantity/max(p.leverage,1)
    maintenance=entry*quantity*p.maintenance_margin_percent/100
    entry_cost=entry*quantity*p.entry_fee_percent/100
    exit_cost_rate=(p.taker_fee_percent+p.liquidation_fee_percent)/100
    if p.direction=="LONG":
        return (entry*quantity-margin+maintenance+entry_cost+p.funding)/max(quantity*(1-exit_cost_rate),1e-12)
    return (entry*quantity+margin-maintenance-entry_cost-p.funding)/max(quantity*(1+exit_cost_rate),1e-12)

class PositionManager:
    def update(self,p:Position,c:Candle)->list[tuple[str,dict]]:
        if p.status=="CLOSED":return []
        p.current_price=c.close;u=p.unrealized();p.max_unrealized_pnl=max(p.max_unrealized_pnl,u);p.max_unrealized_loss=min(p.max_unrealized_loss,u);events=[]
        side=1 if p.direction=="LONG" else -1
        terminal=p.stop_loss_price
        liquidation=liquidation_price(p) if p.leverage>1 else None
        if liquidation is not None:
            terminal=max(terminal,liquidation) if side==1 and terminal is not None else (
                min(terminal,liquidation) if terminal is not None else liquidation)
        stop_hit=terminal is not None and (c.low<=terminal if side==1 else c.high>=terminal)
        if stop_hit:
            gap_price=min(c.open,terminal) if side==1 else max(c.open,terminal)
            liquidated=liquidation is not None and (terminal==liquidation or (c.open<=liquidation if side==1 else c.open>=liquidation))
            reason="LIQUIDATION" if liquidated else ("BREAK_EVEN" if p.protected else "STRUCTURAL_STOP")
            return [("close",{"price":gap_price,"reason":reason,"quantity":p.quantity})]
        targets=sorted(p.take_profit_prices,reverse=p.direction=="SHORT")
        reached=[x for x in targets if (c.high>=x if p.direction=="LONG" else c.low<=x)]
        for target in reached:
            target_index=p.take_profit_prices.index(target)
            if p.break_even_rule=="AFTER_TARGET" and len(targets)>1:
                p.take_profit_prices.remove(target)
                if p.target_allocations:p.target_allocations.pop(target_index)
                p.targets_hit+=1
                p.stop_loss_price=fee_adjusted_break_even(p);p.protected=True;p.status="PROTECTED"
                events.append(("updated",{"stop_loss_price":p.stop_loss_price,"status":"PROTECTED"}))
                targets.remove(target)
                continue
            if len(targets)>1 and p.quantity>p.initial_quantity*.25:
                allocation=(p.target_allocations[target_index] if len(p.target_allocations)==len(p.take_profit_prices)
                            else .5)
                quantity=min(p.quantity,p.initial_quantity*allocation)
                events.append(("partial",{"price":target,"reason":"FIXED_RR_TARGET","quantity":quantity}));p.take_profit_prices.remove(target)
                if p.target_allocations:p.target_allocations.pop(target_index)
                p.targets_hit+=1
                targets.remove(target)
            else:
                events.append(("close",{"price":target,"reason":"FIXED_RR_TARGET","quantity":p.quantity}))
                return events
        initial_risk=abs(p.entry_price-(p.initial_stop_loss_price or p.entry_price))
        one_r=p.entry_price+initial_risk*side
        target_based_protection=(p.break_even_rule=="AFTER_TARGET"
                                 and p.move_stop_to_break_even_after_target is not None
                                 and p.targets_hit>=p.move_stop_to_break_even_after_target)
        one_r_protection=(p.break_even_rule=="ONE_R" and (
            c.high>=one_r if p.direction=="LONG" else c.low<=one_r
        ))
        if not p.protected and initial_risk>0 and (target_based_protection or one_r_protection):
            p.stop_loss_price=fee_adjusted_break_even(p);p.protected=True;p.status="PROTECTED";events.append(("updated",{"stop_loss_price":p.stop_loss_price,"status":"PROTECTED"}))
        return events
