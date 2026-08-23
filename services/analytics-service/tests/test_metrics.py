from src.metrics import *
def trades():return [{"closed_at":1,"pnl":100,"pnl_percent":1},{"closed_at":2,"pnl":-50,"pnl_percent":-.5},{"closed_at":3,"pnl":150,"pnl_percent":1.5}]
def test_equity_curve():assert equity_curve(10000,trades())[-1]["value"]==10200
def test_drawdown():assert drawdown(equity_curve(10000,trades()))["max_drawdown_value"]==50
def test_statistics():
    result=statistics(trades());assert result["win_rate"]==2/3*100 and result["profit_factor"]==5
