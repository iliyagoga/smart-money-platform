from __future__ import annotations
from time import time
from uuid import uuid4
from pydantic import BaseModel,Field,model_validator
now_ms=lambda:int(time()*1000)

class OrderCreate(BaseModel):
    symbol:str;side:str;type:str="LIMIT";price:float|None=None;quantity:float=Field(gt=0)
    stop_loss_price:float|None=None;take_profit_prices:list[float]=[];signal_id:str|None=None
    target_allocations:list[float]=[];break_even_rule:str="ONE_R";move_stop_to_break_even_after_target:int|None=1
    deduplication_key:str|None=None
    @model_validator(mode="after")
    def valid(self):
        self.symbol=self.symbol.strip().upper();self.side=self.side.upper();self.type=self.type.upper()
        if self.side not in {"BUY","SELL"}:raise ValueError("side must be BUY or SELL")
        if self.type not in {"LIMIT","MARKET","STOP"}:raise ValueError("unsupported order type")
        if self.type!="MARKET" and self.price is None:raise ValueError("price is required")
        return self
class Order(OrderCreate):
    id:str=Field(default_factory=lambda:str(uuid4()));status:str="PENDING";exchange_order_id:str|None=None
    created_at:int=Field(default_factory=now_ms);filled_at:int|None=None;filled_price:float|None=None
class Position(BaseModel):
    id:str=Field(default_factory=lambda:str(uuid4()));signal_id:str|None=None;scenario_id:str|None=None;order_id:str
    symbol:str;direction:str;entry_price:float;current_price:float;quantity:float;initial_quantity:float;leverage:int=1
    stop_loss_price:float|None=None;take_profit_prices:list[float]=[];status:str="OPENED";opened_at:int=Field(default_factory=now_ms);closed_at:int|None=None
    target_allocations:list[float]=[];break_even_rule:str="ONE_R";move_stop_to_break_even_after_target:int|None=1;targets_hit:int=0
    realized_pnl:float=0;max_unrealized_pnl:float=0;max_unrealized_loss:float=0;partial_takes:list[dict]=[];protected:bool=False
    def unrealized(self,price:float|None=None):return ((price or self.current_price)-self.entry_price)*self.quantity*(1 if self.direction=="LONG" else -1)
class CloseRequest(BaseModel):quantity:float|None=Field(default=None,gt=0);reason:str="MANUAL";price:float|None=Field(default=None,gt=0)
class Candle(BaseModel):symbol:str;timeframe:str;timestamp:int;open:float;high:float;low:float;close:float;volume:float=0;is_closed:bool=True
