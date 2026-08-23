from math import sqrt
from statistics import mean,pstdev

def equity_curve(initial:float,trades:list[dict]):
    value=initial;result=[{"timestamp":0,"value":initial}]
    for x in sorted(trades,key=lambda i:i["closed_at"]):value+=float(x["pnl"]);result.append({"timestamp":x["closed_at"],"value":value})
    return result
def drawdown(curve):
    peak=curve[0]["value"] if curve else 0;maximum=0;maximum_percent=0;start=end=None;peak_time=None
    for point in curve:
        if point["value"]>peak:peak=point["value"];peak_time=point["timestamp"]
        loss=peak-point["value"]
        if loss>maximum:maximum=loss;maximum_percent=loss/peak*100 if peak else 0;start=peak_time;end=point["timestamp"]
    return {"max_drawdown_percent":maximum_percent,"max_drawdown_value":maximum,"start_date":start,"end_date":end}
def statistics(trades):
    pnls=[float(x["pnl"]) for x in trades];wins=[x for x in pnls if x>0];losses=[x for x in pnls if x<0]
    returns=[float(x.get("pnl_percent",0))/100 for x in trades]
    sharpe=mean(returns)/pstdev(returns)*sqrt(252) if len(returns)>1 and pstdev(returns)>0 else 0
    return {"total_trades":len(pnls),"win_rate":len(wins)/len(pnls)*100 if pnls else 0,"profit_factor":sum(wins)/abs(sum(losses)) if losses else None,"sharpe_ratio":sharpe,"total_pnl":sum(pnls)}
