from __future__ import annotations
from time import time
from uuid import uuid4
from pydantic import BaseModel,Field,model_validator
now_ms=lambda:int(time()*1000)

class OrderCreate(BaseModel):
    symbol:str;side:str;type:str="LIMIT";price:float|None=None;quantity:float=Field(gt=0)
    stop_loss_price:float|None=None;take_profit_prices:list[float]=[];signal_id:str|None=None
    target_allocations:list[float]=[];target_rrs:list[float]=[];break_even_rule:str="ONE_R";move_stop_to_break_even_after_target:int|None=1
    deduplication_key:str|None=None
    leverage:int=Field(default=1,ge=1,le=125);margin_mode:str="cross"
    execution_mode:str="PAPER";expires_at:int|None=None
    slippage_percent:float=Field(default=0,ge=0,le=10);tick_size:float=Field(default=.01,gt=0)
    lot_size:float=Field(default=.000001,gt=0);minimum_order_size:float=Field(default=.000001,gt=0)
    volume_participation_percent:float=Field(default=5,gt=0,le=100)
    maker_fee_percent:float=Field(default=0,ge=-1,le=10);taker_fee_percent:float=Field(default=0,ge=0,le=10)
    funding_percent_per_day:float=Field(default=0,ge=-10,le=10);funding_interval_hours:int=Field(default=8,ge=1,le=24)
    maintenance_margin_percent:float=Field(default=.5,ge=0,le=20);liquidation_fee_percent:float=Field(default=.5,ge=0,le=10)
    @model_validator(mode="after")
    def valid(self):
        self.symbol=self.symbol.strip().upper();self.side=self.side.upper();self.type=self.type.upper()
        if self.side not in {"BUY","SELL"}:raise ValueError("side must be BUY or SELL")
        if self.type not in {"LIMIT","MARKET","STOP"}:raise ValueError("unsupported order type")
        if self.type!="MARKET" and self.price is None:raise ValueError("price is required")
        self.margin_mode=self.margin_mode.lower()
        if self.margin_mode not in {"cross","isolated"}:raise ValueError("unsupported margin mode")
        self.execution_mode=self.execution_mode.upper()
        if self.execution_mode not in {"PAPER","DEMO","PRODUCTION"}:raise ValueError("unsupported execution mode")
        return self
class Order(OrderCreate):
    id:str=Field(default_factory=lambda:str(uuid4()));status:str="PENDING";exchange_order_id:str|None=None
    rejection_reason:str|None=None
    created_at:int=Field(default_factory=now_ms);filled_at:int|None=None;filled_price:float|None=None
class Position(BaseModel):
    id:str=Field(default_factory=lambda:str(uuid4()));signal_id:str|None=None;scenario_id:str|None=None;order_id:str
    strategy:str="UNKNOWN";setup_type:str="UNKNOWN"
    symbol:str;direction:str;entry_price:float;current_price:float;quantity:float;initial_quantity:float;leverage:int=1
    execution_mode:str="PAPER";margin_mode:str="cross"
    stop_loss_price:float|None=None;take_profit_prices:list[float]=[];status:str="OPENED";opened_at:int=Field(default_factory=now_ms);closed_at:int|None=None
    initial_stop_loss_price:float|None=None
    target_allocations:list[float]=[];break_even_rule:str="ONE_R";move_stop_to_break_even_after_target:int|None=1;targets_hit:int=0
    entry_fee_percent:float=0;maker_fee_percent:float=0;taker_fee_percent:float=0;slippage_percent:float=0;tick_size:float=.01
    funding_percent_per_day:float=0;funding_interval_hours:int=8;maintenance_margin_percent:float=.5;liquidation_fee_percent:float=.5
    fees:float=0;funding:float=0;last_funding_at:int|None=None
    realized_pnl:float=0;max_unrealized_pnl:float=0;max_unrealized_loss:float=0;partial_takes:list[dict]=[];protected:bool=False
    def unrealized(self,price:float|None=None):
        gross=((price or self.current_price)-self.entry_price)*self.quantity*(1 if self.direction=="LONG" else -1)
        return gross-self.entry_price*self.quantity*self.entry_fee_percent/100
class CloseRequest(BaseModel):quantity:float|None=Field(default=None,gt=0);reason:str="MANUAL";price:float|None=Field(default=None,gt=0)
class Candle(BaseModel):symbol:str;timeframe:str;timestamp:int;open:float;high:float;low:float;close:float;volume:float=0;is_closed:bool=True
