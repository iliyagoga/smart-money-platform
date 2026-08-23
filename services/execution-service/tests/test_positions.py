from src.manager import PositionManager
from src.models import *

def position(**changes):
    data=dict(order_id="o",symbol="BTC-USDT",direction="LONG",entry_price=100,current_price=100,quantity=10,initial_quantity=10,stop_loss_price=95,take_profit_prices=[110])
    data.update(changes);return Position(**data)
def candle(low,high,close):return Candle(symbol="BTC-USDT",timeframe="M1",timestamp=1,open=100,low=low,high=high,close=close)
def test_stop_has_conservative_priority():
    events=PositionManager().update(position(),candle(94,111,105));assert events[0][0]=="close" and events[0][1]["reason"]=="STOP_LOSS"
def test_take_profit_closes_single_target():
    events=PositionManager().update(position(),candle(99,111,110));assert events[0][0]=="close" and events[0][1]["reason"]=="TAKE_PROFIT"
def test_one_r_protects_position():
    p=position(take_profit_prices=[120]);events=PositionManager().update(p,candle(99,106,105));assert p.stop_loss_price==100 and p.status=="PROTECTED" and events[0][0]=="updated"
def test_short_stop():
    p=position(direction="SHORT",stop_loss_price=105,take_profit_prices=[90]);events=PositionManager().update(p,candle(89,106,95));assert events[0][1]["reason"]=="STOP_LOSS"
