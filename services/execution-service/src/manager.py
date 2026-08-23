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
            if len(targets)>1 and p.quantity>p.initial_quantity*.25:
                events.append(("partial",{"price":target,"reason":"TAKE_PROFIT","quantity":p.quantity/2}));p.take_profit_prices.remove(target)
            else:return [("close",{"price":target,"reason":"TAKE_PROFIT","quantity":p.quantity})]
        initial_risk=abs(p.entry_price-(p.stop_loss_price or p.entry_price))
        one_r=p.entry_price+initial_risk*(1 if p.direction=="LONG" else -1)
        if not p.protected and initial_risk>0 and (c.high>=one_r if p.direction=="LONG" else c.low<=one_r):
            p.stop_loss_price=p.entry_price;p.protected=True;p.status="PROTECTED";events.append(("updated",{"stop_loss_price":p.entry_price,"status":"PROTECTED"}))
        return events
