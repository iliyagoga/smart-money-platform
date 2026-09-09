from __future__ import annotations
from time import time
from uuid import uuid4
from pydantic import BaseModel,Field,model_validator

now_ms=lambda:int(time()*1000)

class Scenario(BaseModel):
    id:str;symbol:str;timeframe:str;direction:str;setup_type:str;confidence:float=0
    entry_zone_low:float;entry_zone_high:float;stop_loss_price:float;take_profit_prices:list[float]
    status:str="ACTIVE";reasons:list[str]=[];objections:list[str]=[];objects_used:list[dict]=[]
    target_allocations:list[float]=[];target_rrs:list[float]=[];break_even_rule:str="ONE_R";move_stop_to_break_even_after_target:int|None=1
    entry_type:str="LIMIT"
    one_trade_per_zone:bool=False;cooldown_bars_after_stop:int=0;deduplication_key:str|None=None
    created_at:int=Field(default_factory=now_ms);expires_at:int
    @model_validator(mode="after")
    def valid(self):
        if self.entry_zone_low>self.entry_zone_high:raise ValueError("invalid entry zone")
        return self

class TradeSignal(BaseModel):
    signal_id:str=Field(default_factory=lambda:str(uuid4()));scenario_id:str;symbol:str;direction:str
    entry_price:float;entry_type:str="LIMIT";stop_loss_price:float;take_profit_prices:list[float]
    target_allocations:list[float]=[];target_rrs:list[float]=[];break_even_rule:str="ONE_R";move_stop_to_break_even_after_target:int|None=1
    one_trade_per_zone:bool=False;cooldown_bars_after_stop:int=0;deduplication_key:str|None=None
    confidence:float;created_at:int=Field(default_factory=now_ms);expires_at:int|None=None

class RiskConfig(BaseModel):
    max_daily_loss_percent:float=Field(default=5,gt=0,le=100);max_positions:int=Field(default=1,ge=1,le=100)
    max_risk_per_trade_percent:float=Field(default=1,gt=0,le=10);kelly_fraction:float=Field(default=.25,gt=0,le=1)
    leverage:int=Field(default=1,ge=1,le=125);min_position_size:float=Field(default=.0001,gt=0)
    loss_size_multiplier:float=Field(default=.5,gt=0,le=1)
    two_loss_cooldown_hours:int=Field(default=12,ge=1,le=168)
    loss_streak_daily_stop:int=Field(default=3,ge=3,le=100)
    daily_stop_hours:int=Field(default=24,ge=1,le=168)

class RiskConfigPatch(BaseModel):
    max_daily_loss_percent:float|None=Field(default=None,gt=0,le=100);max_positions:int|None=Field(default=None,ge=1,le=100)
    max_risk_per_trade_percent:float|None=Field(default=None,gt=0,le=10);kelly_fraction:float|None=Field(default=None,gt=0,le=1)
    leverage:int|None=Field(default=None,ge=1,le=125);min_position_size:float|None=Field(default=None,gt=0)
    loss_size_multiplier:float|None=Field(default=None,gt=0,le=1)
    two_loss_cooldown_hours:int|None=Field(default=None,ge=1,le=168)
    loss_streak_daily_stop:int|None=Field(default=None,ge=3,le=100)
    daily_stop_hours:int|None=Field(default=None,ge=1,le=168)

class RiskCalculateRequest(BaseModel):signal_id:str;capital:float|None=Field(default=None,gt=0)
class RiskDecision(BaseModel):
    signal_id:str;approved:bool;position_size:float=0;position_value:float=0;leverage:int=1
    risk_amount:float=0;risk_percent_of_capital:float=0;rejection_reason:str|None=None;timestamp:int=Field(default_factory=now_ms)
    capital_multiplier:float=1;consecutive_losses:int=0;cooldown_until:int|None=None
